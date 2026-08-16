from flask import session
from flask_login import current_user

from app.models import Trainer


def current_trainer():
    """관리자가 특정 트레이너를 '이 트레이너로 보기' 중이면 그 트레이너를, 아니면 로그인한 본인을 반환."""
    if current_user.is_authenticated and current_user.role == "admin":
        impersonate_id = session.get("impersonate_trainer_id")
        if impersonate_id:
            impersonated = Trainer.query.get(impersonate_id)
            if impersonated:
                return impersonated
    return current_user
