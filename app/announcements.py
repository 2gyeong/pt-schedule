from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.context import current_trainer
from app.models import Announcement

announcements_bp = Blueprint("announcements", __name__)


@announcements_bp.route("/announcements", methods=["GET"])
@login_required
def list_announcements():
    trainer = current_trainer()
    announcements = (
        Announcement.query.filter_by(trainer_id=trainer.id)
        .order_by(Announcement.created_at.desc())
        .all()
    )
    return render_template("announcements.html", announcements=announcements)


@announcements_bp.route("/announcements", methods=["POST"])
@login_required
def create_announcement():
    trainer = current_trainer()
    content = request.form.get("content", "").strip()
    if content:
        db.session.add(Announcement(trainer_id=trainer.id, content=content))
        db.session.commit()
        flash("공지사항을 등록했습니다.")
    return redirect(url_for("announcements.list_announcements"))


@announcements_bp.route("/announcements/<int:announcement_id>/edit", methods=["POST"])
@login_required
def edit_announcement(announcement_id):
    trainer = current_trainer()
    announcement = Announcement.query.filter_by(
        id=announcement_id, trainer_id=trainer.id
    ).first_or_404()
    content = request.form.get("content", "").strip()
    if content:
        announcement.content = content
        db.session.commit()
        flash("공지사항을 수정했습니다.")
    return redirect(url_for("announcements.list_announcements"))


@announcements_bp.route("/announcements/<int:announcement_id>/delete", methods=["POST"])
@login_required
def delete_announcement(announcement_id):
    trainer = current_trainer()
    announcement = Announcement.query.filter_by(
        id=announcement_id, trainer_id=trainer.id
    ).first_or_404()
    db.session.delete(announcement)
    db.session.commit()
    return redirect(url_for("announcements.list_announcements"))
