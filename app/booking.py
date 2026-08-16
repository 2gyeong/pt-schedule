from datetime import date, datetime, time

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from app import db
from app.models import (
    Announcement,
    ChangeRequest,
    Location,
    Member,
    MemberMessage,
    RecurringAvailability,
    RecurringTrainerAvailability,
    RoundSubmission,
    ScheduleEvent,
    SchedulingRound,
    Trainer,
)
from app.scheduling import trainer_open_background

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
    trainer = Trainer.query.get(member.trainer_id)
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
    pending_change_request_by_event = {
        r.event_id: r.id
        for r in ChangeRequest.query.filter_by(member_id=member.id, status="대기").all()
    }
    announcements = (
        Announcement.query.filter_by(trainer_id=member.trainer_id)
        .order_by(Announcement.created_at.desc())
        .all()
    )
    messages = (
        MemberMessage.query.filter_by(member_id=member.id)
        .order_by(MemberMessage.created_at.desc())
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
        pending_change_request_by_event=pending_change_request_by_event,
        announcements=announcements,
        messages=messages,
        schedule_start_hour=trainer.schedule_start_hour,
        schedule_end_hour=trainer.schedule_end_hour,
    )


@booking_bp.route("/book/<token>/confirmed", methods=["GET"])
def confirmed_events_api(token):
    member = Member.query.filter_by(booking_token=token).first_or_404()
    events = (
        ScheduleEvent.query.filter_by(member_id=member.id, status="확정")
        .order_by(ScheduleEvent.date, ScheduleEvent.start_time)
        .all()
    )
    pending_change_request_by_event = {
        r.event_id: r.id
        for r in ChangeRequest.query.filter_by(member_id=member.id, status="대기").all()
    }
    return jsonify(
        [
            {
                "id": e.id,
                "date": e.date.isoformat(),
                "start_time": e.start_time.strftime("%H:%M"),
                "end_time": e.end_time.strftime("%H:%M"),
                "location_name": e.location.name if e.location else None,
                "change_pending": e.id in pending_change_request_by_event,
                "change_request_id": pending_change_request_by_event.get(e.id),
            }
            for e in events
        ]
    )


@booking_bp.route("/book/<token>/events/<int:event_id>/change-request", methods=["POST"])
def create_change_request(token, event_id):
    member = Member.query.filter_by(booking_token=token).first_or_404()
    event = ScheduleEvent.query.filter_by(id=event_id, member_id=member.id, status="확정").first_or_404()

    data = request.get_json()
    if not data or not data.get("date") or not data.get("start_time") or not data.get("end_time"):
        abort(400)

    req_date = datetime.fromisoformat(data["date"]).date()
    req_start = datetime.strptime(data["start_time"], "%H:%M").time()
    req_end = datetime.strptime(data["end_time"], "%H:%M").time()
    if datetime.combine(req_date, req_start) < datetime.now():
        abort(400, description="지난 날짜/시간으로는 요청할 수 없습니다.")
    if req_end <= req_start:
        abort(400, description="종료 시간이 시작 시간보다 늦어야 합니다.")

    existing = ChangeRequest.query.filter_by(event_id=event.id, status="대기").first()
    if existing:
        existing.requested_date = req_date
        existing.requested_start_time = req_start
        existing.requested_end_time = req_end
        existing.memo = data.get("memo") or None
        existing.created_at = datetime.utcnow()
    else:
        db.session.add(
            ChangeRequest(
                trainer_id=member.trainer_id,
                event_id=event.id,
                member_id=member.id,
                requested_date=req_date,
                requested_start_time=req_start,
                requested_end_time=req_end,
                memo=data.get("memo") or None,
            )
        )
    db.session.commit()
    return jsonify({"ok": True}), 201


@booking_bp.route("/book/<token>/events/<int:change_request_id>/change-request/cancel", methods=["POST"])
def cancel_change_request(token, change_request_id):
    """회원이 자기가 보낸 변경 요청을 취소한다. 기록은 지우지 않고 상태만 취소됨으로 바꾼다."""
    member = Member.query.filter_by(booking_token=token).first_or_404()
    req = ChangeRequest.query.filter_by(
        id=change_request_id, member_id=member.id, status="대기"
    ).first_or_404()
    req.status = "취소됨"
    db.session.commit()
    return jsonify({"ok": True}), 200


@booking_bp.route("/book/<token>/messages", methods=["POST"])
def send_message(token):
    member = Member.query.filter_by(booking_token=token).first_or_404()
    content = request.form.get("content", "").strip()
    if content:
        db.session.add(MemberMessage(trainer_id=member.trainer_id, member_id=member.id, content=content))
        db.session.commit()
    return redirect(url_for("booking.book_page", token=token))


@booking_bp.route("/book/<token>/messages/<int:message_id>/cancel", methods=["POST"])
def cancel_message(token, message_id):
    """회원이 자기가 보낸 메시지를 취소한다. 기록은 지우지 않고 상태만 취소됨으로 바꾼다."""
    member = Member.query.filter_by(booking_token=token).first_or_404()
    message = MemberMessage.query.filter_by(id=message_id, member_id=member.id, status="전송됨").first_or_404()
    message.status = "취소됨"
    db.session.commit()
    return redirect(url_for("booking.book_page", token=token))


@booking_bp.route("/book/<token>/my-events", methods=["GET"])
def my_events(token):
    """이 회원 본인의 확정된 예약만 (다른 회원 예약은 절대 섞이지 않음). 달력에 실제 제목을 달아 보여주고,
    클릭하면 바로 수정 요청으로 이어지는 용도."""
    member = Member.query.filter_by(booking_token=token).first_or_404()
    query = ScheduleEvent.query.filter_by(status="확정", member_id=member.id)
    start = request.args.get("start")
    end = request.args.get("end")
    if start:
        query = query.filter(ScheduleEvent.date >= datetime.fromisoformat(start).date())
    if end:
        query = query.filter(ScheduleEvent.date <= datetime.fromisoformat(end).date())

    result = []
    for e in query.all():
        location_name = e.location.name if e.location else "지점 미정"
        color = e.location.color if e.location else "#888"
        result.append(
            {
                "id": e.id,
                "title": f"{member.name} ({location_name})",
                "start": f"{e.date.isoformat()}T{e.start_time.isoformat()}",
                "end": f"{e.date.isoformat()}T{e.end_time.isoformat()}",
                "backgroundColor": color,
                "borderColor": "#37352f",
                "extendedProps": {
                    "mine": True,
                    "date": e.date.isoformat(),
                    "start_time": e.start_time.strftime("%H:%M"),
                    "end_time": e.end_time.strftime("%H:%M"),
                },
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
    """다른 회원들의 예약 시간(익명, 지점/이름 없이 회색 블록으로만). 본인 예약은 my_events()에서
    실제 제목을 달아 따로 보여주므로 여기서는 제외한다."""
    member = Member.query.filter_by(booking_token=token).first_or_404()

    query = ScheduleEvent.query.filter(
        ScheduleEvent.trainer_id == member.trainer_id,
        ScheduleEvent.status != "취소",
        ScheduleEvent.member_id != member.id,
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


@booking_bp.route("/book/<token>/open-times", methods=["GET"])
def open_times(token):
    member = Member.query.filter_by(booking_token=token).first_or_404()
    start = request.args.get("start")
    end = request.args.get("end")
    start_date = datetime.fromisoformat(start).date() if start else date.today()
    end_date = datetime.fromisoformat(end).date() if end else start_date
    blocks = trainer_open_background(member.trainer_id, start_date, end_date)
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


