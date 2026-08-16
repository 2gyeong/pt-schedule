from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.context import current_trainer
from app.models import Location

locations_bp = Blueprint("locations", __name__)

COLOR_PALETTE = ["#2c6fbb", "#27ae60", "#e67e22", "#8e44ad", "#c0392b", "#16a085", "#d35400", "#2980b9"]


@locations_bp.route("/locations", methods=["GET"])
@login_required
def list_locations():
    trainer = current_trainer()
    locations = Location.query.filter_by(trainer_id=trainer.id).order_by(Location.name).all()
    return render_template("locations.html", locations=locations)


@locations_bp.route("/locations", methods=["POST"])
@login_required
def create_location():
    trainer = current_trainer()
    name = request.form.get("name", "").strip()
    lat = request.form.get("lat", "").strip()
    lng = request.form.get("lng", "").strip()
    if name and lat and lng:
        count = Location.query.filter_by(trainer_id=trainer.id).count()
        color = COLOR_PALETTE[count % len(COLOR_PALETTE)]
        location = Location(name=name, lat=float(lat), lng=float(lng), color=color, trainer_id=trainer.id)
        db.session.add(location)
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


@locations_bp.route("/locations/<int:location_id>/delete", methods=["POST"])
@login_required
def delete_location(location_id):
    trainer = current_trainer()
    location = Location.query.filter_by(id=location_id, trainer_id=trainer.id).first_or_404()
    db.session.delete(location)
    db.session.commit()
    return redirect(url_for("locations.list_locations"))
