from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import Trainer

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        trainer = Trainer.query.filter_by(name=name).first()
        if trainer and check_password_hash(trainer.password_hash, password):
            if trainer.status == "대기":
                flash("가입 승인 대기 중입니다. 관리자 승인 후 로그인할 수 있어요.")
            elif trainer.status == "거절됨":
                flash("가입이 거절된 계정입니다.")
            else:
                login_user(trainer)
                if trainer.role == "admin":
                    return redirect(url_for("admin.list_trainers"))
                return redirect(url_for("schedule.calendar_view"))
        else:
            flash("이름 또는 비밀번호가 올바르지 않습니다.")
    return render_template("login.html")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if not name or not password:
            flash("이름과 비밀번호를 입력해주세요.")
        elif password != password_confirm:
            flash("비밀번호가 서로 일치하지 않습니다.")
        elif Trainer.query.filter_by(name=name).first():
            flash("이미 사용 중인 이름입니다.")
        else:
            trainer = Trainer(
                name=name,
                password_hash=generate_password_hash(password),
                role="trainer",
                status="대기",
            )
            db.session.add(trainer)
            db.session.commit()
            flash("가입 신청이 완료되었습니다. 관리자 승인 후 로그인할 수 있어요.")
            return redirect(url_for("auth.login"))
    return render_template("signup.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
