from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.context import current_trainer
from app.models import Location, TravelTime

locations_bp = Blueprint("locations", __name__)

COLOR_PALETTE = ["#7c98c2", "#6fae8b", "#dda85e", "#a48cc4", "#d98080", "#5fada6", "#c99b6a", "#8891c7"]


def _pair_key(a, b):
    return f"{'home' if a is None else a}_{'home' if b is None else b}"


@locations_bp.route("/locations", methods=["GET"])
@login_required
def list_locations():
    trainer = current_trainer()
    locations = Location.query.filter_by(trainer_id=trainer.id).order_by(Location.name).all()

    # 모든 지점 쌍 (이동 시간 입력용)
    pairs = []
    for i in range(len(locations)):
        for j in range(i + 1, len(locations)):
            pairs.append((locations[i], locations[j]))

    existing = {
        frozenset({t.location_a_id, t.location_b_id}): t.minutes
        for t in TravelTime.query.filter_by(trainer_id=trainer.id).all()
    }
    pair_rows = [
        {
            "key": _pair_key(loc_a.id, loc_b.id),
            "a_name": loc_a.name,
            "b_name": loc_b.name,
            "minutes": existing.get(frozenset({loc_a.id, loc_b.id})),
        }
        for loc_a, loc_b in pairs
    ]

    return render_template("locations.html", locations=locations, pair_rows=pair_rows)


@locations_bp.route("/locations", methods=["POST"])
@login_required
def create_location():
    trainer = current_trainer()
    name = request.form.get("name", "").strip()
    if name:
        count = Location.query.filter_by(trainer_id=trainer.id).count()
        color = COLOR_PALETTE[count % len(COLOR_PALETTE)]
        location = Location(name=name, lat=0.0, lng=0.0, color=color, trainer_id=trainer.id)
        db.session.add(location)
        db.session.commit()
    return redirect(url_for("locations.list_locations"))


@locations_bp.route("/locations/<int:location_id>/name", methods=["POST"])
@login_required
def set_name(location_id):
    trainer = current_trainer()
    location = Location.query.filter_by(id=location_id, trainer_id=trainer.id).first_or_404()
    name = request.form.get("name", "").strip()
    if name:
        location.name = name
        db.session.commit()
    return redirect(url_for("locations.list_locations"))


@locations_bp.route("/locations/<int:location_id>/color", methods=["POST"])
@login_required
def set_color(location_id):
    trainer = current_trainer()
    location = Location.query.filter_by(id=location_id, trainer_id=trainer.id).first_or_404()
    color = request.form.get("color", "").strip()
    if color:
        location.color = color
        db.session.commit()
    return redirect(url_for("locations.list_locations"))


@locations_bp.route("/locations/travel-times", methods=["POST"])
@login_required
def save_travel_times():
    trainer = current_trainer()
    location_ids = {loc.id for loc in Location.query.filter_by(trainer_id=trainer.id).all()}

    TravelTime.query.filter_by(trainer_id=trainer.id).delete()
    for key, value in request.form.items():
        if not key.startswith("travel_"):
            continue
        value = value.strip()
        if not value or not value.isdigit():
            continue
        a_raw, b_raw = key[len("travel_"):].split("_")
        a_id = None if a_raw == "home" else int(a_raw)
        b_id = None if b_raw == "home" else int(b_raw)
        if (a_id is not None and a_id not in location_ids) or (b_id is not None and b_id not in location_ids):
            continue
        db.session.add(
            TravelTime(trainer_id=trainer.id, location_a_id=a_id, location_b_id=b_id, minutes=int(value))
        )
    db.session.commit()
    return redirect(url_for("locations.list_locations"))


@locations_bp.route("/locations/<int:location_id>/delete", methods=["POST"])
@login_required
def delete_location(location_id):
    trainer = current_trainer()
    location = Location.query.filter_by(id=location_id, trainer_id=trainer.id).first_or_404()
    db.session.delete(location)
    db.session.commit()
    return redirect(url_for("locations.list_locations"))
