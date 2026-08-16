from datetime import datetime, time

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.context import current_trainer
from app.models import Location, RecurringTrainerAvailability, TrainerBlackout, WeekdayStartLocation

blackouts_bp = Blueprint("blackouts", __name__)

WEEKDAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


@blackouts_bp.route("/blackouts", methods=["GET"])
@login_required
def list_blackouts():
    trainer = current_trainer()
    blackouts = TrainerBlackout.query.filter_by(trainer_id=trainer.id).order_by(TrainerBlackout.date).all()
    recurring = RecurringTrainerAvailability.query.filter_by(trainer_id=trainer.id).all()
    recurring_blocks = [{"weekday": r.weekday, "hour": r.start_time.hour} for r in recurring]
    locations = Location.query.filter_by(trainer_id=trainer.id).order_by(Location.name).all()
    start_location_by_weekday = {
        s.weekday: s.location_id
        for s in WeekdayStartLocation.query.filter_by(trainer_id=trainer.id).all()
    }
    return render_template(
        "blackouts.html",
        blackouts=blackouts,
        recurring_blocks=recurring_blocks,
        locations=locations,
        weekday_names=list(enumerate(WEEKDAY_NAMES)),
        start_location_by_weekday=start_location_by_weekday,
        schedule_start_hour=trainer.schedule_start_hour,
        schedule_end_hour=trainer.schedule_end_hour,
    )


@blackouts_bp.route("/blackouts/schedule-range", methods=["POST"])
@login_required
def save_schedule_range():
    trainer = current_trainer()
    try:
        start_hour = int(request.form.get("start_hour", ""))
        end_hour = int(request.form.get("end_hour", ""))
    except ValueError:
        flash("시간 범위를 올바르게 선택해주세요.")
        return redirect(url_for("blackouts.list_blackouts"))

    if not (0 <= start_hour < end_hour <= 24):
        flash("종료 시간이 시작 시간보다 늦어야 해요.")
        return redirect(url_for("blackouts.list_blackouts"))

    trainer.schedule_start_hour = start_hour
    trainer.schedule_end_hour = end_hour
    db.session.commit()
    flash("표시 시간 범위를 저장했습니다.")
    return redirect(url_for("blackouts.list_blackouts"))


@blackouts_bp.route("/blackouts/start-locations", methods=["POST"])
@login_required
def save_start_locations():
    trainer = current_trainer()
    WeekdayStartLocation.query.filter_by(trainer_id=trainer.id).delete()
    for weekday in range(7):
        location_id = request.form.get(f"start_location_{weekday}", "").strip()
        if location_id:
            db.session.add(
                WeekdayStartLocation(trainer_id=trainer.id, weekday=weekday, location_id=int(location_id))
            )
    db.session.commit()
    flash("요일별 시작 지점을 저장했습니다.")
    return redirect(url_for("blackouts.list_blackouts"))


@blackouts_bp.route("/blackouts/recurring", methods=["POST"])
@login_required
def save_recurring():
    trainer = current_trainer()
    data = request.get_json()
    blocks = data.get("blocks") if data else None
    if blocks is None:
        return jsonify({"error": "invalid"}), 400

    RecurringTrainerAvailability.query.filter_by(trainer_id=trainer.id).delete()
    for b in blocks:
        hour = int(b["hour"])
        db.session.add(
            RecurringTrainerAvailability(
                trainer_id=trainer.id,
                weekday=int(b["weekday"]),
                start_time=time(hour, 0),
                end_time=time(hour + 1, 0) if hour < 23 else time(23, 59),
            )
        )
    db.session.commit()
    return jsonify({"saved": len(blocks)}), 201


@blackouts_bp.route("/blackouts", methods=["POST"])
@login_required
def create_blackout():
    trainer = current_trainer()
    date_str = request.form.get("date", "").strip()
    start_str = request.form.get("start_time", "").strip()
    end_str = request.form.get("end_time", "").strip()
    if date_str and start_str and end_str:
        blackout = TrainerBlackout(
            trainer_id=trainer.id,
            date=datetime.fromisoformat(date_str).date(),
            start_time=datetime.strptime(start_str, "%H:%M").time(),
            end_time=datetime.strptime(end_str, "%H:%M").time(),
            memo=request.form.get("memo", "").strip() or None,
        )
        db.session.add(blackout)
        db.session.commit()
    return redirect(url_for("blackouts.list_blackouts"))


@blackouts_bp.route("/blackouts/<int:blackout_id>/delete", methods=["POST"])
@login_required
def delete_blackout(blackout_id):
    trainer = current_trainer()
    blackout = TrainerBlackout.query.filter_by(id=blackout_id, trainer_id=trainer.id).first_or_404()
    db.session.delete(blackout)
    db.session.commit()
    return redirect(url_for("blackouts.list_blackouts"))
