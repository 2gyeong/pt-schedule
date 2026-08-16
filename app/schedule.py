from datetime import date, datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from app import db
from app.context import current_trainer
from app.holidays import KR_HOLIDAYS
from app.models import Location, Member, RecurringTrainerAvailability, ScheduleEvent
from app.rounds import active_round_for, round_panel_context
from app.scheduling import member_available_background, slot_conflicts

schedule_bp = Blueprint("schedule", __name__)


def _display_hour_range(trainer):
    """달력에 표시할 시간대. 선생님이 지정해둔 표시 범위가 실제 반복 가능 시간보다 좁으면
    자동으로 넓혀서, 생성된 일정이 화면 밖으로 밀려 안 보이는 일이 없게 한다."""
    start_hour = trainer.schedule_start_hour
    end_hour = trainer.schedule_end_hour
    for t in RecurringTrainerAvailability.query.filter_by(trainer_id=trainer.id).all():
        start_hour = min(start_hour, t.start_time.hour)
        end_hour = max(end_hour, t.end_time.hour + (1 if t.end_time.minute else 0))
    return start_hour, min(end_hour, 24)


def _apply_status(event: ScheduleEvent, new_status: str):
    """상태가 확정으로/확정에서 바뀔 때 회원의 잔여 횟수를 함께 조정한다.
    상담(신규 문의자)은 잔여 횟수 개념이 없으므로 건드리지 않는다."""
    if event.status == new_status:
        return
    if event.event_type != "상담":
        if new_status == "확정" and event.status != "확정":
            event.member.remaining_sessions -= 1
        elif event.status == "확정" and new_status != "확정":
            event.member.remaining_sessions += 1
    event.status = new_status


def event_to_dict(event: ScheduleEvent) -> dict:
    start = f"{event.date.isoformat()}T{event.start_time.isoformat()}"
    end = f"{event.date.isoformat()}T{event.end_time.isoformat()}"
    location_name = event.location.name if event.location else None
    prefix = "[상담] " if event.event_type == "상담" else ""
    title = f"{prefix}{event.member.name} ({location_name})" if location_name else f"{prefix}{event.member.name}"
    return {
        "id": event.id,
        "title": title,
        "start": start,
        "end": end,
        "backgroundColor": event.location.color if event.location else "#888",
        "borderColor": event.location.color if event.location else "#888",
        "extendedProps": {
            "member_id": event.member_id,
            "member_name": event.member.name,
            "location_id": event.location_id,
            "location_name": location_name,
            "round_id": event.round_id,
            "memo": event.memo or "",
            "status": event.status,
            "source": event.source,
            "event_type": event.event_type,
        },
    }


@schedule_bp.route("/")
@schedule_bp.route("/calendar")
@login_required
def calendar_view():
    trainer = current_trainer()
    members = (
        Member.query.filter_by(trainer_id=trainer.id, is_deleted=False, is_prospect=False)
        .order_by(Member.name)
        .all()
    )
    locations = Location.query.filter_by(trainer_id=trainer.id).order_by(Location.name).all()

    active_round = active_round_for(trainer)
    round_context = round_panel_context(active_round, trainer) if active_round else None
    display_start_hour, display_end_hour = _display_hour_range(trainer)

    return render_template(
        "calendar.html",
        members=members,
        locations=locations,
        holidays=KR_HOLIDAYS,
        active_round=active_round,
        round_context=round_context,
        display_start_hour=display_start_hour,
        display_end_hour=display_end_hour,
    )


@schedule_bp.route("/api/events", methods=["GET"])
@login_required
def list_events():
    trainer = current_trainer()
    query = ScheduleEvent.query.filter_by(trainer_id=trainer.id)
    start = request.args.get("start")
    end = request.args.get("end")
    if start:
        query = query.filter(ScheduleEvent.date >= datetime.fromisoformat(start).date())
    if end:
        query = query.filter(ScheduleEvent.date <= datetime.fromisoformat(end).date())
    events = query.all()
    return jsonify([event_to_dict(e) for e in events])


@schedule_bp.route("/api/events", methods=["POST"])
@login_required
def create_event():
    trainer = current_trainer()
    data = request.get_json()
    event_type = data.get("event_type") if data.get("event_type") in ("PT", "상담") else "PT"

    if event_type == "상담":
        prospect_name = (data.get("prospect_name") or "").strip()
        if not prospect_name:
            return jsonify({"error": "상담 받으실 분의 이름을 입력해주세요."}), 400
        member = Member(
            trainer_id=trainer.id,
            name=prospect_name,
            is_prospect=True,
            remaining_sessions=0,
        )
        db.session.add(member)
        db.session.flush()
        location_id = data.get("location_id")
    else:
        member = Member.query.filter_by(id=data["member_id"], trainer_id=trainer.id, is_prospect=False).first_or_404()
        location_id = data.get("location_id") or member.location_id

    event_date = datetime.fromisoformat(data["date"]).date()
    start_time = datetime.strptime(data["start_time"], "%H:%M").time()
    end_time = datetime.strptime(data["end_time"], "%H:%M").time()
    if end_time <= start_time:
        return jsonify({"error": "종료 시간이 시작 시간보다 늦어야 해요."}), 400

    location = Location.query.filter_by(id=location_id, trainer_id=trainer.id).first() if location_id else None
    if slot_conflicts(trainer.id, event_date, start_time, end_time, location):
        return jsonify({"error": "이 시간은 다른 예약과 겹치거나 이동 시간이 부족해요."}), 400

    event = ScheduleEvent(
        trainer_id=trainer.id,
        member_id=member.id,
        location_id=location_id,
        date=event_date,
        start_time=start_time,
        end_time=end_time,
        memo=data.get("memo") or None,
        source="trainer",
        status="요청",  # _apply_status로 확정 전환시켜 잔여 횟수 차감
        event_type=event_type,
    )
    db.session.add(event)
    db.session.flush()
    _apply_status(event, "확정")
    db.session.commit()
    return jsonify(event_to_dict(event)), 201


@schedule_bp.route("/api/events/<int:event_id>", methods=["PUT"])
@login_required
def update_event(event_id):
    trainer = current_trainer()
    event = ScheduleEvent.query.filter_by(id=event_id, trainer_id=trainer.id).first_or_404()
    data = request.get_json()

    new_date = datetime.fromisoformat(data["date"]).date() if data.get("date") else event.date
    new_start = datetime.strptime(data["start_time"], "%H:%M").time() if data.get("start_time") else event.start_time
    new_end = datetime.strptime(data["end_time"], "%H:%M").time() if data.get("end_time") else event.end_time
    if new_end <= new_start:
        return jsonify({"error": "종료 시간이 시작 시간보다 늦어야 해요."}), 400

    new_location_id = data.get("location_id") or event.location_id
    new_location = (
        Location.query.filter_by(id=new_location_id, trainer_id=trainer.id).first() if new_location_id else None
    )
    if slot_conflicts(trainer.id, new_date, new_start, new_end, new_location, exclude_event_id=event.id):
        return jsonify({"error": "이 시간은 다른 예약과 겹치거나 이동 시간이 부족해요."}), 400

    new_event_type = data["event_type"] if data.get("event_type") in ("PT", "상담") else event.event_type
    if new_event_type == "상담":
        prospect_name = (data.get("prospect_name") or "").strip()
        if prospect_name and event.member and event.member.is_prospect:
            event.member.name = prospect_name
        elif prospect_name and not (event.member and event.member.is_prospect):
            member = Member(trainer_id=trainer.id, name=prospect_name, is_prospect=True, remaining_sessions=0)
            db.session.add(member)
            db.session.flush()
            event.member_id = member.id
    elif data.get("member_id"):
        member = Member.query.filter_by(id=data["member_id"], trainer_id=trainer.id, is_prospect=False).first()
        if member:
            event.member_id = member.id
    event.event_type = new_event_type
    event.location_id = new_location_id
    event.date = new_date
    event.start_time = new_start
    event.end_time = new_end
    event.memo = data.get("memo", event.memo)
    if data.get("status"):
        _apply_status(event, data["status"])
    db.session.commit()
    return jsonify(event_to_dict(event))


@schedule_bp.route("/api/events/<int:event_id>", methods=["DELETE"])
@login_required
def delete_event(event_id):
    trainer = current_trainer()
    event = ScheduleEvent.query.filter_by(id=event_id, trainer_id=trainer.id).first_or_404()
    if event.status == "확정" and event.event_type != "상담":
        event.member.remaining_sessions += 1
    db.session.delete(event)
    db.session.commit()
    return "", 204


@schedule_bp.route("/api/members/<int:member_id>/available", methods=["GET"])
@login_required
def member_available(member_id):
    trainer = current_trainer()
    member = Member.query.filter_by(id=member_id, trainer_id=trainer.id).first_or_404()
    start = request.args.get("start")
    end = request.args.get("end")
    start_date = datetime.fromisoformat(start).date() if start else date.today()
    end_date = datetime.fromisoformat(end).date() if end else start_date
    blocks = member_available_background(trainer.id, member.id, start_date, end_date)
    return jsonify(
        [
            {
                "start": f"{d.isoformat()}T{s.isoformat()}",
                "end": f"{d.isoformat()}T{e.isoformat()}",
                "display": "background",
                "color": "#a9d9be",
            }
            for d, s, e in blocks
        ]
    )


@schedule_bp.route("/api/events/<int:event_id>/approve", methods=["POST"])
@login_required
def approve_event(event_id):
    trainer = current_trainer()
    event = ScheduleEvent.query.filter_by(id=event_id, trainer_id=trainer.id).first_or_404()
    _apply_status(event, "확정")
    db.session.commit()
    return jsonify(event_to_dict(event))
