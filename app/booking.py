from datetime import datetime, time

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from app import db
from app.models import (
    Location,
    Member,
    RecurringAvailability,
    RecurringTrainerAvailability,
    RoundSubmission,
    ScheduleEvent,
    SchedulingRound,
)

booking_bp = Blueprint("booking", __name__)


def _active_round(trainer_id):
    return (
        SchedulingRound.query.filter(
            SchedulingRound.trainer_id == trainer_id,
            SchedulingRound.status.in_(["대기", "계산됨"]),
        )
        .order_by(SchedulingRound.start_date)
        .first()
    )


@booking_bp.route("/book/<token>")
def book_page(token):
    member = Member.query.filter_by(booking_token=token).first_or_404()
    locations = Location.query.filter_by(trainer_id=member.trainer_id).order_by(Location.name).all()

    recurring = RecurringAvailability.query.filter_by(member_id=member.id).all()
    recurring_blocks = [{"weekday": r.weekday, "hour": r.start_time.hour} for r in recurring]

    trainer_availability = RecurringTrainerAvailability.query.filter_by(trainer_id=member.trainer_id).all()
    trainer_blocks = [{"weekday": t.weekday, "hour": t.start_time.hour} for t in trainer_availability]

    upcoming_round = _active_round(member.trainer_id)
    already_submitted = False
    if upcoming_round:
        already_submitted = (
            RoundSubmission.query.filter_by(round_id=upcoming_round.id, member_id=member.id).first()
            is not None
        )

    confirmed_events = (
        ScheduleEvent.query.filter_by(member_id=member.id, status="확정")
        .order_by(ScheduleEvent.date, ScheduleEvent.start_time)
        .all()
    )

    return render_template(
        "booking.html",
        member=member,
        locations=locations,
        recurring_blocks=recurring_blocks,
        trainer_blocks=trainer_blocks,
        upcoming_round=upcoming_round,
        already_submitted=already_submitted,
        confirmed_events=confirmed_events,
    )


@booking_bp.route("/book/<token>/note", methods=["POST"])
def save_note(token):
    member = Member.query.filter_by(booking_token=token).first_or_404()
    member.note = request.form.get("note", "").strip() or None
    db.session.commit()
    return redirect(url_for("booking.book_page", token=token))


@booking_bp.route("/book/<token>/schedule")
def shared_schedule(token):
    member = Member.query.filter_by(booking_token=token).first_or_404()
    return render_template("shared_schedule.html", member=member)


@booking_bp.route("/book/<token>/schedule/events")
def shared_schedule_events(token):
    member = Member.query.filter_by(booking_token=token).first_or_404()

    query = ScheduleEvent.query.filter_by(status="확정", trainer_id=member.trainer_id)
    start = request.args.get("start")
    end = request.args.get("end")
    if start:
        query = query.filter(ScheduleEvent.date >= datetime.fromisoformat(start).date())
    if end:
        query = query.filter(ScheduleEvent.date <= datetime.fromisoformat(end).date())

    result = []
    for e in query.all():
        is_mine = e.member_id == member.id
        location_name = e.location.name if e.location else "지점 미정"
        color = e.location.color if e.location else "#888"
        result.append(
            {
                "id": e.id,
                "title": f"내 예약 ({location_name})" if is_mine else location_name,
                "start": f"{e.date.isoformat()}T{e.start_time.isoformat()}",
                "end": f"{e.date.isoformat()}T{e.end_time.isoformat()}",
                "backgroundColor": color,
                "borderColor": "#222" if is_mine else color,
                "extendedProps": {"mine": is_mine},
            }
        )
    return jsonify(result)


def _mark_submitted(member):
    round_obj = _active_round(member.trainer_id)
    if not round_obj:
        return
    exists = RoundSubmission.query.filter_by(round_id=round_obj.id, member_id=member.id).first()
    if not exists:
        db.session.add(RoundSubmission(round_id=round_obj.id, member_id=member.id))


@booking_bp.route("/book/<token>/recurring", methods=["POST"])
def save_recurring(token):
    member = Member.query.filter_by(booking_token=token).first_or_404()
    data = request.get_json()
    blocks = data.get("blocks") if data else None
    if blocks is None:
        abort(400)

    trainer_allowed = {
        (t.weekday, t.start_time.hour)
        for t in RecurringTrainerAvailability.query.filter_by(trainer_id=member.trainer_id).all()
    }

    RecurringAvailability.query.filter_by(member_id=member.id).delete()
    saved = 0
    for b in blocks:
        weekday, hour = int(b["weekday"]), int(b["hour"])
        if (weekday, hour) not in trainer_allowed:
            continue
        db.session.add(
            RecurringAvailability(
                member_id=member.id,
                weekday=weekday,
                start_time=time(hour, 0),
                end_time=time(hour + 1, 0) if hour < 23 else time(23, 59),
            )
        )
        saved += 1
    _mark_submitted(member)
    db.session.commit()
    return jsonify({"saved": saved}), 201


@booking_bp.route("/book/<token>/submit", methods=["POST"])
def submit_for_round(token):
    """그리드를 바꾸지 않았어도, 이번 라운드에 지금 상태 그대로 제출 확인."""
    member = Member.query.filter_by(booking_token=token).first_or_404()
    _mark_submitted(member)
    db.session.commit()
    return jsonify({"submitted": True}), 201


@booking_bp.route("/book/<token>/busy", methods=["GET"])
def busy_times(token):
    member = Member.query.filter_by(booking_token=token).first_or_404()

    query = ScheduleEvent.query.filter(
        ScheduleEvent.trainer_id == member.trainer_id, ScheduleEvent.status != "취소"
    )
    start = request.args.get("start")
    end = request.args.get("end")
    if start:
        query = query.filter(ScheduleEvent.date >= datetime.fromisoformat(start).date())
    if end:
        query = query.filter(ScheduleEvent.date <= datetime.fromisoformat(end).date())

    events = query.all()
    return jsonify(
        [
            {
                "start": f"{e.date.isoformat()}T{e.start_time.isoformat()}",
                "end": f"{e.date.isoformat()}T{e.end_time.isoformat()}",
                "display": "background",
                "color": "#bbb",
            }
            for e in events
        ]
    )


@booking_bp.route("/book/<token>/request", methods=["POST"])
def request_booking(token):
    member = Member.query.filter_by(booking_token=token).first_or_404()
    data = request.get_json()
    if not data or not data.get("date") or not data.get("start_time") or not data.get("end_time"):
        abort(400)

    event_date = datetime.fromisoformat(data["date"]).date()
    event_start = datetime.strptime(data["start_time"], "%H:%M").time()
    if datetime.combine(event_date, event_start) < datetime.now():
        abort(400, description="지난 날짜/시간에는 요청할 수 없습니다.")

    event = ScheduleEvent(
        trainer_id=member.trainer_id,
        member_id=member.id,
        date=event_date,
        start_time=event_start,
        end_time=datetime.strptime(data["end_time"], "%H:%M").time(),
        memo=data.get("memo") or None,
        source="member",
        status="요청",
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({"id": event.id}), 201
