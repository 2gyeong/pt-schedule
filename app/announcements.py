from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
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
    published = [a for a in announcements if a.is_live()]
    unpublished = [a for a in announcements if not a.is_live()]
    return render_template("announcements.html", published=published, unpublished=unpublished)


def _parse_publish_at():
    raw = request.form.get("publish_at", "").strip()
    if not raw:
        return None
    return datetime.fromisoformat(raw)


@announcements_bp.route("/announcements", methods=["POST"])
@login_required
def create_announcement():
    trainer = current_trainer()
    content = request.form.get("content", "").strip()
    if content:
        db.session.add(
            Announcement(trainer_id=trainer.id, content=content, publish_at=_parse_publish_at())
        )
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
        announcement.publish_at = _parse_publish_at()
        db.session.commit()
        flash("공지사항을 수정했습니다.")
    return redirect(url_for("announcements.list_announcements"))


@announcements_bp.route("/announcements/<int:announcement_id>/toggle-published", methods=["POST"])
@login_required
def toggle_published(announcement_id):
    trainer = current_trainer()
    announcement = Announcement.query.filter_by(
        id=announcement_id, trainer_id=trainer.id
    ).first_or_404()
    announcement.is_published = not announcement.is_published
    db.session.commit()
    return jsonify({"ok": True, "is_published": announcement.is_published, "is_live": announcement.is_live()})


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
