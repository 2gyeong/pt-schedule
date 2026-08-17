from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.context import current_trainer
from app.models import (
    Announcement,
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


def _is_ajax():
    return request.headers.get("X-Requested-With") == "fetch"


def _rounds_context(trainer):
    rounds = (
        SchedulingRound.query.filter_by(trainer_id=trainer.id)
        .order_by(SchedulingRound.created_at.desc())
        .all()
    )
    member_ids = [m.id for m in Member.query.filter_by(trainer_id=trainer.id, is_deleted=False, is_prospect=False).all()]
    active_weekdays = sorted(
        {t.weekday for t in RecurringTrainerAvailability.query.filter_by(trainer_id=trainer.id).all()}
        & {
            r.weekday
            for r in RecurringAvailability.query.filter(RecurringAvailability.member_id.in_(member_ids)).all()
        }
    ) if member_ids else []
    active_weekday_names = [WEEKDAY_NAMES[w] for w in active_weekdays]
    return rounds, active_weekday_names


def _rounds_panel_html(trainer):
    rounds, active_weekday_names = _rounds_context(trainer)
    return render_template("_rounds_panel.html", rounds=rounds, active_weekday_names=active_weekday_names)


@rounds_bp.route("/rounds", methods=["GET"])
@login_required
def list_rounds():
    trainer = current_trainer()
    if _is_ajax():
        return jsonify({"ok": True, "html": _rounds_panel_html(trainer)})
    rounds, active_weekday_names = _rounds_context(trainer)
    return render_template("rounds.html", rounds=rounds, active_weekday_names=active_weekday_names)


@rounds_bp.route("/rounds", methods=["POST"])
@login_required
def create_round():
    trainer = current_trainer()
    active = SchedulingRound.query.filter_by(trainer_id=trainer.id).filter(
        SchedulingRound.status.in_(["대기", "계산됨"])
    ).first()
    if active:
        message = "이미 진행 중인 회차가 있습니다. 먼저 승인하거나 마무리해주세요."
        if _is_ajax():
            return jsonify({"ok": False, "message": message, "html": _rounds_panel_html(trainer)})
        flash(message)
        return redirect(url_for("rounds.list_rounds"))

    start_str = request.form.get("start_date", "").strip()
    end_str = request.form.get("end_date", "").strip()
    session_minutes = request.form.get("session_minutes", "50").strip()
    if start_str and end_str:
        start_date = datetime.fromisoformat(start_str).date()
        end_date = datetime.fromisoformat(end_str).date()
        if end_date < start_date:
            message = "종료일이 시작일보다 빠를 수 없습니다."
            if _is_ajax():
                return jsonify({"ok": False, "message": message, "html": _rounds_panel_html(trainer)})
            flash(message)
            return redirect(url_for("rounds.list_rounds"))
        round_obj = SchedulingRound(
            trainer_id=trainer.id,
            start_date=start_date,
            end_date=end_date,
            session_minutes=int(session_minutes) if session_minutes else 50,
        )
        db.session.add(round_obj)
        db.session.flush()
        # 새 회차를 시작하면 회원들이 계획하기 탭에서 바로 알아챌 수 있게 공지사항으로 알린다.
        # 이 회차가 삭제되거나 확정되면(delete_round/approve) 같이 지운다.
        db.session.add(
            Announcement(trainer_id=trainer.id, round_id=round_obj.id, content="다음 예약 계획을 제출해주세요.")
        )
        db.session.commit()
        flash("새 회차를 시작했어요. 회원들에게 공지로 알렸어요.", "generate")
    if _is_ajax():
        return jsonify({"ok": True, "html": _rounds_panel_html(trainer)})
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


def active_round_for(trainer):
    return SchedulingRound.query.filter_by(trainer_id=trainer.id).filter(
        SchedulingRound.status.in_(["대기", "계산됨"])
    ).first()


def round_panel_context(round_obj, trainer):
    """활성 회차 패널(_active_round_panel.html)을 렌더링하는 데 필요한 컨텍스트.
    round_detail()과 달력 페이지(schedule.calendar_view) 양쪽에서 공유해서 쓴다."""
    members = Member.query.filter_by(trainer_id=trainer.id, is_deleted=False, is_prospect=False).order_by(Member.name).all()
    submitted_member_ids = {
        s.member_id for s in RoundSubmission.query.filter_by(round_id=round_obj.id).all()
    }
    quota_by_member = {
        q.member_id: q.count for q in RoundQuota.query.filter_by(round_id=round_obj.id).all()
    }
    events, slot_options_by_event = _events_context(round_obj)
    return dict(
        round=round_obj,
        members=members,
        submitted_member_ids=submitted_member_ids,
        quota_by_member=quota_by_member,
        events=events,
        slot_options_by_event=slot_options_by_event,
    )


def unassigned_members_for_round(round_obj):
    """이번 회차에서 희망 횟수(RoundQuota)보다 실제 배정된 건수가 적은 회원 목록.
    달력 오른쪽 '미배정' 목록에 드래그 가능한 블록으로 보여주는 용도.
    이번 회차를 제출(RoundSubmission)하지 않은 회원은 자동 생성(generate_schedule)에서도
    배정 대상에서 제외되므로, 여기서도 같은 기준으로 제외해 드래그로 강제 배정되지 않게 한다."""
    quotas = RoundQuota.query.filter_by(round_id=round_obj.id).all()
    if not quotas:
        return []
    submitted_member_ids = {
        s.member_id for s in RoundSubmission.query.filter_by(round_id=round_obj.id).all()
    }
    assigned_counts = dict(
        db.session.query(ScheduleEvent.member_id, db.func.count(ScheduleEvent.id))
        .filter(
            ScheduleEvent.round_id == round_obj.id,
            ScheduleEvent.status.in_(["요청", "확정"]),
        )
        .group_by(ScheduleEvent.member_id)
        .all()
    )
    result = []
    for q in quotas:
        if q.member_id not in submitted_member_ids:
            continue
        missing = q.count - assigned_counts.get(q.member_id, 0)
        if missing > 0:
            result.append({"member_id": q.member_id, "name": q.member.name, "missing": missing})
    result.sort(key=lambda r: r["missing"], reverse=True)
    return result


@rounds_bp.route("/rounds/<int:round_id>")
@login_required
def round_detail(round_id):
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()
    if round_obj.status != "확정":
        # 진행 중인 회차는 달력 페이지에서 관리한다 (일원화).
        return redirect(url_for("schedule.calendar_view"))
    return render_template("round_detail.html", **round_panel_context(round_obj, trainer))


@rounds_bp.route("/rounds/<int:round_id>/members/<int:member_id>/toggle-submitted", methods=["POST"])
@login_required
def toggle_submitted(round_id, member_id):
    """회원이 직접 제출하지 않았어도 선생님이 대신 제출완료로 처리하거나, 다시 미제출로 되돌린다."""
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()
    member = Member.query.filter_by(id=member_id, trainer_id=trainer.id).first_or_404()

    existing = RoundSubmission.query.filter_by(round_id=round_obj.id, member_id=member.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"ok": True, "member_id": member.id, "submitted": False})
    db.session.add(RoundSubmission(round_id=round_obj.id, member_id=member.id))
    db.session.commit()
    return jsonify({"ok": True, "member_id": member.id, "submitted": True})


@rounds_bp.route("/rounds/<int:round_id>/mark-all-submitted", methods=["POST"])
@login_required
def mark_all_submitted(round_id):
    """제출하지 않은 모든 회원을 한 번에 제출완료로 처리한다."""
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()
    members = Member.query.filter_by(trainer_id=trainer.id, is_deleted=False, is_prospect=False).all()
    already = {s.member_id for s in RoundSubmission.query.filter_by(round_id=round_obj.id).all()}

    updated_ids = []
    for member in members:
        if member.id in already:
            continue
        db.session.add(RoundSubmission(round_id=round_obj.id, member_id=member.id))
        updated_ids.append(member.id)
    db.session.commit()
    return jsonify({"ok": True, "member_ids": updated_ids})


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
                "color": "#f0cf5a",
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


@rounds_bp.route("/rounds/<int:round_id>/events/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_event(round_id, event_id):
    """이 회차의 배정 하나를 삭제한다. 이미 확정되어 잔여 횟수가 차감됐던 건이면 되돌려주고,
    이번 회차에 설정해둔 희망 횟수(RoundQuota)도 1 줄여서 실제 배정 개수와 맞춘다."""
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()
    event = ScheduleEvent.query.filter_by(id=event_id, round_id=round_id).first_or_404()

    member_id = event.member_id
    if event.status in ("확정", "완료"):
        event.member.remaining_sessions += 1

    quota = RoundQuota.query.filter_by(round_id=round_id, member_id=member_id).first()
    if quota and quota.count > 0:
        quota.count -= 1

    db.session.delete(event)
    db.session.commit()

    events, slot_options_by_event = _events_context(round_obj)
    table_html = render_template(
        "_round_events_table.html", round=round_obj, events=events,
        slot_options_by_event=slot_options_by_event,
    )
    return jsonify({
        "ok": True,
        "message": "일정을 삭제했습니다.",
        "table_html": table_html,
        "event_id": event_id,
        "member_id": member_id,
        "quota": quota.count if quota else 0,
    })


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
    for member in Member.query.filter_by(trainer_id=trainer.id, is_deleted=False, is_prospect=False).all():
        raw = request.form.get(f"quota_{member.id}", "0").strip()
        count = int(raw) if raw.isdigit() else 0
        if count > 0:
            db.session.add(RoundQuota(round_id=round_id, member_id=member.id, count=count))
    db.session.commit()

    assigned, unassigned = generate_schedule(round_obj)
    if unassigned:
        flash(f"{len(assigned)}건 배정 완료. 아래 회원은 부족해요.", "generate")
    else:
        flash(f"{len(assigned)}건 전체 배정 완료.", "generate")
    return redirect(url_for("rounds.round_detail", round_id=round_id))


@rounds_bp.route("/rounds/<int:round_id>/delete", methods=["POST"])
@login_required
def delete_round(round_id):
    trainer = current_trainer()
    round_obj = SchedulingRound.query.filter_by(id=round_id, trainer_id=trainer.id).first_or_404()
    ScheduleEvent.query.filter_by(round_id=round_id, status="요청").delete()
    Announcement.query.filter_by(round_id=round_id).delete()
    db.session.delete(round_obj)
    db.session.commit()
    if _is_ajax():
        return jsonify({"ok": True, "html": _rounds_panel_html(trainer)})
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
    Announcement.query.filter_by(round_id=round_id).delete()
    db.session.commit()
    flash(f"{len(events)}건이 확정되었습니다.")
    return redirect(url_for("schedule.calendar_view"))
