from datetime import date, datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from app import db
from app.context import current_trainer
from app.models import Location, Member, ScheduleEvent
from app.scheduling import member_available_background

schedule_bp = Blueprint("schedule", __name__)


def _apply_status(event: ScheduleEvent, new_status: str):
    """상태가 확정으로/확정에서 바뀔 때 회원의 잔여 횟수를 함께 조정한다."""
    if event.status == new_status:
        return
    if new_status == "확정" and event.status != "확정":
        event.member.remaining_sessions -= 1
    elif event.status == "확정" and new_status != "확정":
        event.member.remaining_sessions += 1
    event.status = new_status


def event_to_dict(event: ScheduleEvent) -> dict:
    start = f"{event.date.isoformat()}T{event.start_time.isoformat()}"
    end = f"{event.date.isoformat()}T{event.end_time.isoformat()}"
    location_name = event.location.name if event.location else None
    title = f"{event.member.name} ({location_name})" if location_name else event.member.name
    return {
        "id": event.id,
        "title": title,
        "start": start,
        "end": end,
        "backgroundColor": event.location.color if event.location else "#888",
        "borderColor": event.location.color if event.location else "#888",
        "extendedProps": {
            "member_id": event.member_id,
            "location_id": event.location_id,
            "location_name": location_name,
            "round_id": event.round_id,
            "memo": event.memo or "",
            "status": event.status,
            "source": event.source,
        },
    }


@schedule_bp.route("/")
@schedule_bp.route("/calendar")
@login_required
def calendar_view():
    trainer = current_trainer()
    members = Member.query.filter_by(trainer_id=trainer.id).order_by(Member.name).all()
    locations = Location.query.filter_by(trainer_id=trainer.id).order_by(Location.name).all()
    return render_template("calendar.html", members=members, locations=locations)


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
    member = Member.query.filter_by(id=data["member_id"], trainer_id=trainer.id).first_or_404()
    location_id = data.get("location_id") or member.location_id
    event = ScheduleEvent(
        trainer_id=trainer.id,
        member_id=member.id,
        location_id=location_id,
        date=datetime.fromisoformat(data["date"]).date(),
        start_time=datetime.strptime(data["start_time"], "%H:%M").time(),
        end_time=datetime.strptime(data["end_time"], "%H:%M").time(),
        memo=data.get("memo") or None,
        source="trainer",
        status="요청",  # _apply_status로 확정 전환시켜 잔여 횟수 차감
    )
    db.session.add(event)
    _apply_status(event, "확정")
    db.session.commit()
    return jsonify(event_to_dict(event)), 201


@schedule_bp.route("/api/events/<int:event_id>", methods=["PUT"])
@login_required
def update_event(event_id):
    trainer = current_trainer()
    event = ScheduleEvent.query.filter_by(id=event_id, trainer_id=trainer.id).first_or_404()
    data = request.get_json()
    if data.get("member_id"):
        member = Member.query.filter_by(id=data["member_id"], trainer_id=trainer.id).first()
        if member:
            event.member_id = member.id
    if data.get("location_id"):
        event.location_id = data["location_id"]
    if data.get("date"):
        event.date = datetime.fromisoformat(data["date"]).date()
    if data.get("start_time"):
        event.start_time = datetime.strptime(data["start_time"], "%H:%M").time()
    if data.get("end_time"):
        event.end_time = datetime.strptime(data["end_time"], "%H:%M").time()
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
    if event.status == "확정":
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
                "color": "#8ee6a0",
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
