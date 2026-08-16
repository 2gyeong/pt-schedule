from datetime import date

from flask import Blueprint, flash, jsonify, redirect, render_template, url_for
from flask_login import login_required

from app import db
from app.context import current_trainer
from app.models import ChangeRequest
from app.scheduling import slot_conflicts

change_requests_bp = Blueprint("change_requests", __name__)


@change_requests_bp.route("/change-requests", methods=["GET"])
@login_required
def list_change_requests():
    trainer = current_trainer()
    pending = (
        ChangeRequest.query.filter_by(trainer_id=trainer.id, status="대기")
        .order_by(ChangeRequest.created_at)
        .all()
    )
    handled = (
        ChangeRequest.query.filter(
            ChangeRequest.trainer_id == trainer.id, ChangeRequest.status != "대기"
        )
        .order_by(ChangeRequest.created_at.desc())
        .limit(10)
        .all()
    )
    initial_date = min((r.requested_date for r in pending), default=date.today())
    return render_template(
        "change_requests.html", pending=pending, handled=handled, initial_date=initial_date
    )


@change_requests_bp.route("/api/change-requests/count", methods=["GET"])
@login_required
def change_requests_count():
    trainer = current_trainer()
    count = ChangeRequest.query.filter_by(trainer_id=trainer.id, status="대기").count()
    return jsonify({"count": count})


@change_requests_bp.route("/change-requests/<int:request_id>/accept", methods=["POST"])
@login_required
def accept_change_request(request_id):
    trainer = current_trainer()
    req = ChangeRequest.query.filter_by(id=request_id, trainer_id=trainer.id, status="대기").first_or_404()
    event = req.event

    if req.requested_end_time <= req.requested_start_time:
        flash("이 요청은 시간 값이 올바르지 않아 수락할 수 없어요. 거절 후 회원에게 다시 요청해달라고 안내해주세요.")
        return redirect(url_for("change_requests.list_change_requests"))

    conflict = slot_conflicts(
        trainer.id,
        req.requested_date,
        req.requested_start_time,
        req.requested_end_time,
        event.location,
        exclude_event_id=event.id,
    )
    if conflict:
        flash("이 시간은 다른 예약과 겹치거나 이동 시간이 부족해서 수락할 수 없어요. 선생님이 직접 다른 시간으로 조정해주세요.")
        return redirect(url_for("change_requests.list_change_requests"))

    event.date = req.requested_date
    event.start_time = req.requested_start_time
    event.end_time = req.requested_end_time
    req.status = "수락됨"
    db.session.commit()
    flash(f"{req.member.name}님의 변경 요청을 수락했습니다.")
    return redirect(url_for("change_requests.list_change_requests"))


@change_requests_bp.route("/change-requests/<int:request_id>/reject", methods=["POST"])
@login_required
def reject_change_request(request_id):
    trainer = current_trainer()
    req = ChangeRequest.query.filter_by(id=request_id, trainer_id=trainer.id, status="대기").first_or_404()
    req.status = "거절됨"
    db.session.commit()
    flash(f"{req.member.name}님의 변경 요청을 거절했습니다.")
    return redirect(url_for("change_requests.list_change_requests"))
