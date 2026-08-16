from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.context import current_trainer
from app.models import (
    Member,
    RecurringAvailability,
    RecurringTrainerAvailability,
    RoundQuota,
    RoundSubmission,
    ScheduleEvent,
    SchedulingRound,
)
from app.scheduling import generate_schedule, valid_slots_for_member

rounds_bp = Blueprint("rounds", __name__)

WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


@rounds_bp.route("/rounds", methods=["GET"])
@login_required
def list_rounds():
    trainer = current_trainer()
    rounds = (
        SchedulingRound.query.filter_by(trainer_id=trainer.id)
        .order_by(SchedulingRound.created_at.desc())
        .all()
    )
    member_ids = [m.id for m in Member.query.filter_by(trainer_id=trainer.id).all()]
    active_weekdays = sorted(
        {t.weekday for t in RecurringTrainerAvailability.query.filter_by(trainer_id=trainer.id).all()}
        & {
            r.weekday
            for r in RecurringAvailability.query.filter(RecurringAvailability.member_id.in_(member_ids)).all()
        }
    ) if member_ids else []
    active_weekday_names = [WEEKDAY_NAMES[w] for w in active_weekdays]
    return render_template("rounds.html", rounds=rounds, active_weekday_names=active_weekday_names)


@rounds_bp.route("/rounds", methods=["POST"])
@login_required
def create_round():
    trainer = current_trainer()
    active = SchedulingRound.query.filter_by(trainer_id=trainer.id).filter(
        SchedulingRound.status.in_(["대기", "계산됨"])
    ).first()
    if active:
        flash("이미 진행 중인 회차가 있습니다. 먼저 승인하거나 마무리해주세요.")
        return redirect(url_for("rounds.list_rounds"))

    start_str = request.form.get("start_date", "").strip()
    end_str = request.form.get("end_date", "").strip()
    session_minutes = request.form.get("session_minutes", "50").strip()
    if start_str and end_str:
        start_date = datetime.fromisoformat(start_str).date()
        end_date = datetime.fromisoformat(end_str).date()
        if end_date < start_date:
            flash("종료일이 시작일보다 빠를 수 없습니다.")
            return redirect(url_for("rounds.list_rounds"))
        round_obj = SchedulingRound(
            trainer_id=trainer.id,
            start_date=start_date,
            end_date=end_date,
            session_minutes=int(session_minutes) if session_minutes else 50,
        )
        db.session.add(round_obj)
        db.session.commit()
    return redirect(url_for("rounds.list_rounds"))


def _events_context(round_obj):
    events = (
        ScheduleEvent.query.filter_by(round_id=round_obj.id)
        .order_by(ScheduleEvent.date, ScheduleEvent.start_time)
        .all()
    )
    slot_options_by_event = {}
    if round_obj.status != "확정":
        for e in events:
            if e.status != "요청":
                continue
            slot_options_by_event[e.id] = valid_slots_for_member(round_obj, e.member_id, exclude_event_id=e.id)
    return events, slot_options_by_event


@rounds_bp.route("/rounds/<int:round_id>")
@login_required
def round_detail(round_id):
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()
    members = Member.query.filter_by(trainer_id=trainer.id).order_by(Member.name).all()
    submitted_member_ids = {
        s.member_id for s in RoundSubmission.query.filter_by(round_id=round_id).all()
    }
    quota_by_member = {
        q.member_id: q.count for q in RoundQuota.query.filter_by(round_id=round_id).all()
    }
    events, slot_options_by_event = _events_context(round_obj)

    return render_template(
        "round_detail.html",
        round=round_obj,
        members=members,
        submitted_member_ids=submitted_member_ids,
        quota_by_member=quota_by_member,
        events=events,
        slot_options_by_event=slot_options_by_event,
    )


@rounds_bp.route("/rounds/<int:round_id>/members/<int:member_id>/valid-slots", methods=["GET"])
@login_required
def member_valid_slots(round_id, member_id):
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()
    exclude_event_id = request.args.get("exclude_event_id", type=int)
    slots = valid_slots_for_member(round_obj, member_id, exclude_event_id=exclude_event_id)
    return jsonify(
        [
            {
                "start": f"{d.isoformat()}T{s.strftime('%H:%M:%S')}",
                "end": f"{d.isoformat()}T{e.strftime('%H:%M:%S')}",
                "display": "background",
                "color": "#a9d9be",
            }
            for d, s, e in slots
        ]
    )


@rounds_bp.route("/rounds/<int:round_id>/events/<int:event_id>/reassign", methods=["POST"])
@login_required
def reassign_event(round_id, event_id):
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()
    event = ScheduleEvent.query.filter_by(id=event_id, round_id=round_id).first_or_404()
    is_ajax = request.headers.get("X-Requested-With") == "fetch"

    slot_key = request.form.get("slot", "")
    valid = valid_slots_for_member(round_obj, event.member_id, exclude_event_id=event.id)
    valid_keys = {f"{d.isoformat()}|{s.strftime('%H:%M')}|{e.strftime('%H:%M')}" for d, s, e in valid}

    if slot_key not in valid_keys:
        message = "선택한 시간은 이 회원의 가능 시간이 아니에요."
        if is_ajax:
            events, slot_options_by_event = _events_context(round_obj)
            table_html = render_template(
                "_round_events_table.html", round=round_obj, events=events,
                slot_options_by_event=slot_options_by_event,
            )
            return jsonify({"ok": False, "message": message, "table_html": table_html})
        flash(message)
        return redirect(url_for("rounds.round_detail", round_id=round_id))

    date_str, start_str, end_str = slot_key.split("|")
    event.date = datetime.fromisoformat(date_str).date()
    event.start_time = datetime.strptime(start_str, "%H:%M").time()
    event.end_time = datetime.strptime(end_str, "%H:%M").time()
    db.session.commit()

    if is_ajax:
        events, slot_options_by_event = _events_context(round_obj)
        table_html = render_template(
            "_round_events_table.html", round=round_obj, events=events,
            slot_options_by_event=slot_options_by_event,
        )
        return jsonify({
            "ok": True,
            "message": "시간을 변경했습니다.",
            "table_html": table_html,
            "event": {
                "id": event.id,
                "start": f"{event.date.isoformat()}T{event.start_time.strftime('%H:%M:%S')}",
                "end": f"{event.date.isoformat()}T{event.end_time.strftime('%H:%M:%S')}",
            },
        })

    flash("시간을 변경했습니다.")
    return redirect(url_for("rounds.round_detail", round_id=round_id))


@rounds_bp.route("/rounds/<int:round_id>/dates", methods=["POST"])
@login_required
def update_dates(round_id):
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()
    start_str = request.form.get("start_date", "").strip()
    end_str = request.form.get("end_date", "").strip()
    if start_str and end_str:
        start_date = datetime.fromisoformat(start_str).date()
        end_date = datetime.fromisoformat(end_str).date()
        if end_date < start_date:
            flash("종료일이 시작일보다 빠를 수 없습니다.")
            return redirect(url_for("rounds.round_detail", round_id=round_id))
        round_obj.start_date = start_date
        round_obj.end_date = end_date
        db.session.commit()
        flash("기간을 수정했습니다. 다시 스케줄을 생성해주세요.")
    return redirect(url_for("rounds.round_detail", round_id=round_id))


@rounds_bp.route("/rounds/<int:round_id>/generate", methods=["POST"])
@login_required
def generate(round_id):
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()

    RoundQuota.query.filter_by(round_id=round_id).delete()
    for member in Member.query.filter_by(trainer_id=trainer.id).all():
        raw = request.form.get(f"quota_{member.id}", "0").strip()
        count = int(raw) if raw.isdigit() else 0
        if count > 0:
            db.session.add(RoundQuota(round_id=round_id, member_id=member.id, count=count))
    db.session.commit()

    assigned, unassigned = generate_schedule(round_obj)
    if unassigned:
        parts = ", ".join(f"{m.name}({missing}회 부족 - {reason})" for m, missing, reason in unassigned)
        flash(f"{len(assigned)}건 배정 완료. 부족: {parts}")
    else:
        flash(f"{len(assigned)}건 전체 배정 완료.")
    return redirect(url_for("rounds.round_detail", round_id=round_id))


@rounds_bp.route("/rounds/<int:round_id>/delete", methods=["POST"])
@login_required
def delete_round(round_id):
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()
    ScheduleEvent.query.filter_by(round_id=round_id, status="요청").delete()
    db.session.delete(round_obj)
    db.session.commit()
    flash("회차를 삭제했습니다.")
    return redirect(url_for("rounds.list_rounds"))


@rounds_bp.route("/rounds/<int:round_id>/approve", methods=["POST"])
@login_required
def approve(round_id):
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()
    events = ScheduleEvent.query.filter_by(round_id=round_id, status="요청").all()
    for event in events:
        event.status = "확정"
        event.member.remaining_sessions -= 1
    round_obj.status = "확정"
    db.session.commit()
    flash(f"{len(events)}건이 확정되었습니다.")
    return redirect(url_for("rounds.round_detail", round_id=round_id))
