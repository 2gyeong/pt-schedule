from flask import session
from flask_login import current_user

from app.models import ChangeRequest, Trainer


def current_trainer():
    """관리자가 특정 트레이너를 '이 트레이너로 보기' 중이면 그 트레이너를, 아니면 로그인한 본인을 반환."""
    if current_user.is_authenticated and current_user.role == "admin":
        impersonate_id = session.get("impersonate_trainer_id")
        if impersonate_id:
            impersonated = Trainer.query.get(impersonate_id)
            if impersonated:
                return impersonated
    return current_user


def pending_change_requests_count():
    if not current_user.is_authenticated:
        return 0
    trainer = current_trainer()
    if not isinstance(trainer, Trainer) or trainer.role != "trainer":
        return 0
    return ChangeRequest.query.filter_by(trainer_id=trainer.id, status="대기").count()
