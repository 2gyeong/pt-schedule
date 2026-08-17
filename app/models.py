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
    schedule_start_hour = db.Column(db.Integer, nullable=False, default=6)  # 가능 시간 표에 표시할 시작 시각
    schedule_end_hour = db.Column(db.Integer, nullable=False, default=22)  # 가능 시간 표에 표시할 종료 시각(미포함)


class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"))
    name = db.Column(db.String(50), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    color = db.Column(db.String(7), nullable=False, default="#7c98c2")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TravelTime(db.Model):
    """지점 간(또는 집-지점 간) 실제 이동 시간을 선생님이 직접 입력한 값.
    있으면 거리 기반 자동 계산 대신 이 값을 그대로 사용한다. location_a_id/location_b_id가
    NULL이면 '집'을 뜻한다."""

    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"), nullable=False)
    location_a_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=True)
    location_b_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=True)
    minutes = db.Column(db.Integer, nullable=False)

    location_a = db.relationship("Location", foreign_keys=[location_a_id])
    location_b = db.relationship("Location", foreign_keys=[location_b_id])


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
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    is_prospect = db.Column(db.Boolean, nullable=False, default=False)  # 상담만 진행한 미등록 신규 문의자
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    location = db.relationship("Location")
    events = db.relationship(
        "ScheduleEvent", backref="member", cascade="all, delete-orphan"
    )
    recurring_availability = db.relationship(
        "RecurringAvailability", backref="member", cascade="all, delete-orphan"
    )

    def latest_message_preview(self):
        msg = (
            MemberMessage.query.filter_by(member_id=self.id, status="전송됨")
            .order_by(MemberMessage.created_at.desc())
            .first()
        )
        return msg.content if msg else None


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


class WeekdayStartLocation(db.Model):
    """요일별로 선생님이 그날 첫 세션을 시작하고 싶은 지점 (요일 0=월 ~ 6=일). 한 번 정하면 계속 유지됨."""

    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"), nullable=False)
    weekday = db.Column(db.Integer, nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=False)

    location = db.relationship("Location")


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
    session_minutes = db.Column(db.Integer, default=50)
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
    event_type = db.Column(db.String(10), nullable=False, default="PT")  # PT / 상담
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    location = db.relationship("Location")


class ChangeRequest(db.Model):
    """회원이 이미 확정된 예약의 날짜/시간 변경을 요청한 건."""

    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("schedule_event.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    requested_date = db.Column(db.Date, nullable=False)
    requested_start_time = db.Column(db.Time, nullable=False)
    requested_end_time = db.Column(db.Time, nullable=False)
    requested_location_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=True)
    memo = db.Column(db.String(255))
    status = db.Column(db.String(20), default="대기")  # 대기 / 수락됨 / 거절됨 / 취소됨
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    event = db.relationship("ScheduleEvent")
    member = db.relationship("Member")
    requested_location = db.relationship("Location")


class Announcement(db.Model):
    """선생님이 회원들에게 보여주는 공지사항."""

    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"), nullable=False)
    round_id = db.Column(db.Integer, db.ForeignKey("scheduling_round.id"), nullable=True)  # 회차 시작 알림이면 그 회차
    content = db.Column(db.Text, nullable=False)
    is_published = db.Column(db.Boolean, nullable=False, default=True)  # 미게시로 내려두면 회원에게 안 보임
    publish_at = db.Column(db.DateTime, nullable=True)  # 설정하면 이 시각 전까지는 회원에게 안 보임 (예약 게시)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_live(self) -> bool:
        if not self.is_published:
            return False
        if self.publish_at and self.publish_at > datetime.utcnow():
            return False
        return True


class MemberMessage(db.Model):
    """회원이 선생님에게 보내는 메시지. 취소해도 기록은 지우지 않고 상태만 바꾼다."""

    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey("trainer.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="전송됨")  # 전송됨 / 취소됨
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    member = db.relationship("Member")
