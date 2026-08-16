from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.context import current_trainer

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings", methods=["GET"])
@login_required
def show_settings():
    return render_template("settings.html")


@settings_bp.route("/settings/password", methods=["GET"])
@login_required
def show_password_page():
    return render_template("change_password.html")


@settings_bp.route("/settings/password", methods=["POST"])
@login_required
def change_password():
    trainer = current_trainer()
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    new_password_confirm = request.form.get("new_password_confirm", "")

    if not check_password_hash(trainer.password_hash, current_password):
        flash("현재 비밀번호가 일치하지 않습니다.")
    elif not new_password:
        flash("새 비밀번호를 입력해주세요.")
    elif new_password != new_password_confirm:
        flash("새 비밀번호가 서로 일치하지 않습니다.")
    else:
        trainer.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash("비밀번호를 변경했습니다.")
        return redirect(url_for("settings.show_settings"))
    return redirect(url_for("settings.show_password_page"))
