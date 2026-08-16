from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required

from app import db
from app.models import Trainer

admin_bp = Blueprint("admin", __name__)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@admin_bp.route("/admin")
@login_required
@admin_required
def list_trainers():
    session.pop("impersonate_trainer_id", None)
    trainers = Trainer.query.filter(Trainer.role != "admin").order_by(Trainer.created_at.desc()).all()
    return render_template("admin.html", trainers=trainers)


@admin_bp.route("/admin/trainers/<int:trainer_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_trainer(trainer_id):
    trainer = Trainer.query.get_or_404(trainer_id)
    trainer.status = "승인됨"
    db.session.commit()
    flash(f"{trainer.name}님을 승인했습니다.")
    return redirect(url_for("admin.list_trainers"))


@admin_bp.route("/admin/trainers/<int:trainer_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_trainer(trainer_id):
    trainer = Trainer.query.get_or_404(trainer_id)
    trainer.status = "거절됨"
    db.session.commit()
    flash(f"{trainer.name}님의 가입을 거절했습니다.")
    return redirect(url_for("admin.list_trainers"))


@admin_bp.route("/admin/trainers/<int:trainer_id>/impersonate", methods=["POST"])
@login_required
@admin_required
def impersonate(trainer_id):
    trainer = Trainer.query.get_or_404(trainer_id)
    session["impersonate_trainer_id"] = trainer.id
    return redirect(url_for("schedule.calendar_view"))
