from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "로그인이 필요합니다."
    csrf.init_app(app)

    from app.models import Trainer
    from app.auth import auth_bp
    from app.members import members_bp
    from app.schedule import schedule_bp
    from app.booking import booking_bp
    from app.locations import locations_bp
    from app.blackouts import blackouts_bp
    from app.rounds import rounds_bp
    from app.admin import admin_bp
    from app.change_requests import change_requests_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(locations_bp)
    app.register_blueprint(blackouts_bp)
    app.register_blueprint(rounds_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(change_requests_bp)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return Trainer.query.get(int(user_id))
        except (TypeError, ValueError):
            return None

    from app.context import current_trainer, pending_change_requests_count

    @app.context_processor
    def inject_current_trainer():
        return {
            "current_trainer": current_trainer,
            "pending_change_requests_count": pending_change_requests_count,
        }

    with app.app_context():
        db.create_all()
        _bootstrap_admin(app)

    return app


def _bootstrap_admin(app):
    from werkzeug.security import generate_password_hash

    from app.models import Trainer

    if not Trainer.query.filter_by(role="admin").first():
        admin = Trainer(
            name=app.config["ADMIN_NAME"],
            password_hash=generate_password_hash(app.config["ADMIN_PASSWORD"]),
            role="admin",
            status="승인됨",
        )
        db.session.add(admin)
        db.session.commit()
