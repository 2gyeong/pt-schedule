import secrets
from datetime import datetime

from flask_login import UserMixin

from app import db


class Trainer(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False, default="trainer")  # trainer / admin
    status = db.Column(db.String(20), nullable=False, default="대기")  # 대기 / 승인됨 / 거절됨
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"))
    name = db.Column(db.String(50), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    color = db.Column(db.String(7), nullable=False, default="#2c6fbb")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"))
    name = db.Column(db.String(50), nullable=False)
    memo = db.Column(db.String(255))
    note = db.Column(db.Text)  # 회원이 선생님께 남기는 비고
    location_id = db.Column(db.Integer, db.ForeignKey("location.id"))
    remaining_sessions = db.Column(db.Integer, nullable=False, default=0)
    booking_token = db.Column(
        db.String(32), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(16)
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    location = db.relationship("Location")
    events = db.relationship(
        "ScheduleEvent", backref="member", cascade="all, delete-orphan"
    )
    recurring_availability = db.relationship(
        "RecurringAvailability", backref="member", cascade="all, delete-orphan"
    )


class TrainerBlackout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"))
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    memo = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class RecurringTrainerAvailability(db.Model):
    """선생님이 매주 반복해서 가능한 시간 블록 (요일 0=월 ~ 6=일)."""

    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"))
    weekday = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class RecurringAvailability(db.Model):
    """회원이 매주 반복해서 가능한 시간 블록 (요일 0=월 ~ 6=일)."""

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    weekday = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SchedulingRound(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    session_minutes = db.Column(db.Integer, default=60)
    status = db.Column(db.String(20), default="대기")  # 대기 / 계산됨 / 확정
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    events = db.relationship("ScheduleEvent", backref="round")
    quotas = db.relationship(
        "RoundQuota", backref="round", cascade="all, delete-orphan"
    )
    submissions = db.relationship(
        "RoundSubmission", backref="round", cascade="all, delete-orphan"
    )


class RoundSubmission(db.Model):
    """회원이 이 라운드에 대해 고정 가능 시간을 제출(확인)했는지 여부."""

    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey("scheduling_round.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    member = db.relationship("Member")


class RoundQuota(db.Model):
    """이 라운드에서 해당 회원을 몇 번 배정 시도할지 (선생님이 지정)."""

    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey("scheduling_round.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    count = db.Column(db.Integer, nullable=False, default=0)

    member = db.relationship("Member")


class ScheduleEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"))
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    round_id = db.Column(db.Integer, db.ForeignKey("scheduling_round.id"))
    location_id = db.Column(db.Integer, db.ForeignKey("location.id"))
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    memo = db.Column(db.String(255))
    source = db.Column(db.String(10), default="trainer")  # trainer / member
    status = db.Column(db.String(20), default="확정")  # 요청 / 확정 / 완료 / 취소
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    location = db.relationship("Location")
