from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.context import current_trainer
from app.models import Location, Member

members_bp = Blueprint("members", __name__)


@members_bp.route("/members", methods=["GET"])
@login_required
def list_members():
    trainer = current_trainer()
    members = (
        Member.query.filter_by(trainer_id=trainer.id, is_deleted=False, is_prospect=False)
        .order_by(Member.name)
        .all()
    )
    deleted_members = (
        Member.query.filter_by(trainer_id=trainer.id, is_deleted=True, is_prospect=False)
        .order_by(Member.name)
        .all()
    )
    locations = Location.query.filter_by(trainer_id=trainer.id).order_by(Location.name).all()
    return render_template(
        "members.html", members=members, deleted_members=deleted_members, locations=locations
    )


@members_bp.route("/members", methods=["POST"])
@login_required
def create_member():
    trainer = current_trainer()
    name = request.form.get("name", "").strip()
    if name:
        location_id = request.form.get("location_id") or None
        if location_id:
            location = Location.query.filter_by(id=int(location_id), trainer_id=trainer.id).first()
            location_id = location.id if location else None
        sessions = request.form.get("remaining_sessions", "0").strip()
        member = Member(
            name=name,
            trainer_id=trainer.id,
            memo=request.form.get("memo", "").strip() or None,
            location_id=location_id,
            remaining_sessions=int(sessions) if sessions.isdigit() else 0,
        )
        db.session.add(member)
        db.session.commit()
    return redirect(url_for("members.list_members"))


@members_bp.route("/members/<int:member_id>/adjust_sessions", methods=["POST"])
@login_required
def adjust_sessions(member_id):
    trainer = current_trainer()
    member = Member.query.filter_by(id=member_id, trainer_id=trainer.id).first_or_404()
    delta = request.form.get("delta", "0").strip()
    try:
        member.remaining_sessions = max(0, member.remaining_sessions + int(delta))
    except ValueError:
        pass
    db.session.commit()
    return redirect(url_for("members.list_members"))


@members_bp.route("/members/<int:member_id>/set_location", methods=["POST"])
@login_required
def set_location(member_id):
    trainer = current_trainer()
    member = Member.query.filter_by(id=member_id, trainer_id=trainer.id).first_or_404()
    location_id = request.form.get("location_id") or None
    if location_id:
        location = Location.query.filter_by(id=int(location_id), trainer_id=trainer.id).first()
        location_id = location.id if location else None
    member.location_id = location_id
    db.session.commit()
    return redirect(url_for("members.list_members"))


@members_bp.route("/members/<int:member_id>/memo", methods=["POST"])
@login_required
def set_memo(member_id):
    trainer = current_trainer()
    member = Member.query.filter_by(id=member_id, trainer_id=trainer.id).first_or_404()
    member.memo = request.form.get("memo", "").strip() or None
    db.session.commit()
    return redirect(url_for("members.list_members"))


@members_bp.route("/members/<int:member_id>/delete", methods=["POST"])
@login_required
def delete_member(member_id):
    trainer = current_trainer()
    member = Member.query.filter_by(id=member_id, trainer_id=trainer.id).first_or_404()
    member.is_deleted = True
    db.session.commit()
    return redirect(url_for("members.list_members"))


@members_bp.route("/members/<int:member_id>/restore", methods=["POST"])
@login_required
def restore_member(member_id):
    trainer = current_trainer()
    member = Member.query.filter_by(id=member_id, trainer_id=trainer.id).first_or_404()
    member.is_deleted = False
    db.session.commit()
    return redirect(url_for("members.list_members"))
