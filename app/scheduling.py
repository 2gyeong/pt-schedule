import math
from datetime import date, datetime, time, timedelta

from app import db
from app.models import (
    Member,
    RecurringAvailability,
    RecurringTrainerAvailability,
    RoundQuota,
    RoundSubmission,
    ScheduleEvent,
    TrainerBlackout,
)


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _to_dt(d: date, t: time) -> datetime:
    return datetime.combine(d, t)


def _overlaps(start_a, end_a, start_b, end_b) -> bool:
    return start_a < end_b and start_b < end_a


def _intersect(start_a, end_a, start_b, end_b):
    start = max(start_a, start_b)
    end = min(end_a, end_b)
    return (start, end) if start < end else None


def _distance(loc_a, loc_b) -> float:
    if loc_a is None or loc_b is None or loc_a.id == loc_b.id:
        return 0.0
    return haversine_km(loc_a.lat, loc_a.lng, loc_b.lat, loc_b.lng)


AVG_TRAVEL_SPEED_KMH = 25  # 도심 이동(주차/이동 포함) 가정 평균 속도
MIN_TRAVEL_BUFFER_MIN = 10  # 지점이 달라지면 아무리 가까워도 최소 이 정도는 비워둠


def _travel_minutes(loc_a, loc_b) -> int:
    """서로 다른 지점 사이를 이동하는 데 필요한 최소 시간(분). 같은 지점이면 0."""
    if loc_a is None or loc_b is None or loc_a.id == loc_b.id:
        return 0
    km = haversine_km(loc_a.lat, loc_a.lng, loc_b.lat, loc_b.lng)
    return max(MIN_TRAVEL_BUFFER_MIN, math.ceil(km / AVG_TRAVEL_SPEED_KMH * 60))


def _has_conflict(day_entries, cursor, slot_end, location) -> bool:
    """시간이 겹치거나, 지점이 달라 이동시간이 부족하면 충돌로 본다."""
    for entry_start, entry_end, entry_loc in day_entries:
        if _overlaps(cursor, slot_end, entry_start, entry_end):
            return True
        buffer_min = _travel_minutes(entry_loc, location)
        if buffer_min <= 0:
            continue
        buffer = timedelta(minutes=buffer_min)
        if entry_end <= cursor and (cursor - entry_end) < buffer:
            return True
        if slot_end <= entry_start and (entry_start - slot_end) < buffer:
            return True
    return False


def _insertion_cost(day_entries, start_dt, end_dt, location):
    """day_entries: sorted list of (start_dt, end_dt, location). Cost of inserting
    a new session at [start_dt, end_dt] with the given location, based on the
    extra travel distance versus its immediate neighbors in time."""
    before = None
    after = None
    for entry_start, entry_end, entry_loc in day_entries:
        if entry_end <= start_dt:
            if before is None or entry_end > before[1]:
                before = (entry_start, entry_end, entry_loc)
        if entry_start >= end_dt:
            if after is None or entry_start < after[0]:
                after = (entry_start, entry_end, entry_loc)

    cost = 0.0
    if before is not None:
        cost += _distance(before[2], location)
    if after is not None:
        cost += _distance(location, after[2])
    if before is not None and after is not None:
        cost -= _distance(before[2], after[2])
    return cost


def _dates_in_range(start_date, end_date):
    d = start_date
    while d <= end_date:
        yield d
        d += timedelta(days=1)


def _find_best_slot(windows, day_timeline, location, session_len, step, is_blacked_out):
    best = None  # (cost, date, start_dt, end_dt)
    for window_date, w_start_dt, w_end_dt in windows:
        cursor = w_start_dt
        while cursor + session_len <= w_end_dt:
            slot_end = cursor + session_len
            if not is_blacked_out(window_date, cursor, slot_end):
                day_entries = day_timeline.get(window_date, [])
                if not _has_conflict(day_entries, cursor, slot_end, location):
                    cost = _insertion_cost(day_entries, cursor, slot_end, location)
                    if best is None or cost < best[0]:
                        best = (cost, window_date, cursor, slot_end)
            cursor += step
    return best


def _day_has_feasible_slot(window_date, w_start_dt, w_end_dt, day_timeline, location, session_len, step, is_blacked_out):
    cursor = w_start_dt
    while cursor + session_len <= w_end_dt:
        slot_end = cursor + session_len
        if not is_blacked_out(window_date, cursor, slot_end):
            day_entries = day_timeline.get(window_date, [])
            if not _has_conflict(day_entries, cursor, slot_end, location):
                return True
        cursor += step
    return False


def _pick_spaced_days(feasible_days, count):
    """가능한 날짜 중 count개를, 가능하면 하루 이상 띄워서(최소 간격 2일) 고른다.
    그 간격으로 count개를 못 채우면 인접일(간격 1일)까지 허용해서 다시 시도한다."""
    feasible_days = sorted(feasible_days)

    def greedy_pick(min_gap):
        picked = []
        for d in feasible_days:
            if not picked or (d - picked[-1]).days >= min_gap:
                picked.append(d)
            if len(picked) == count:
                return picked
        return None

    return greedy_pick(2) or greedy_pick(1)


def member_available_background(trainer_id, member_id, start_date, end_date):
    """회원의 고정 가능 시간(선생님 가능 시간과 겹치는 부분) 중, 다른 예약과 안 겹치는 구간을
    (날짜, 시작, 종료) 목록으로 반환. 달력에서 특정 회원을 선택했을 때 배경으로 보여주는 용도."""
    member = Member.query.filter_by(id=member_id, trainer_id=trainer_id).first()
    if not member:
        return []

    trainer_by_weekday = {}
    for t in RecurringTrainerAvailability.query.filter_by(trainer_id=trainer_id).all():
        trainer_by_weekday.setdefault(t.weekday, []).append((t.start_time, t.end_time))

    member_avail = RecurringAvailability.query.filter_by(member_id=member_id).all()

    existing = ScheduleEvent.query.filter(
        ScheduleEvent.trainer_id == trainer_id,
        ScheduleEvent.status.in_(["확정", "완료", "요청"]),
    ).all()
    busy_by_date = {}
    for e in existing:
        busy_by_date.setdefault(e.date, []).append(
            (_to_dt(e.date, e.start_time), _to_dt(e.date, e.end_time))
        )

    result = []
    for d in _dates_in_range(start_date, end_date):
        weekday = d.weekday()
        for r in member_avail:
            if r.weekday != weekday:
                continue
            for t_start, t_end in trainer_by_weekday.get(weekday, []):
                overlap = _intersect(
                    _to_dt(d, r.start_time), _to_dt(d, r.end_time),
                    _to_dt(d, t_start), _to_dt(d, t_end),
                )
                if not overlap:
                    continue
                busy = busy_by_date.get(d, [])
                if not any(_overlaps(overlap[0], overlap[1], bs, be) for bs, be in busy):
                    result.append((d, overlap[0].time(), overlap[1].time()))

    return result


def valid_slots_for_member(round_obj, member_id, exclude_event_id=None):
    """이 라운드 기간 동안 해당 회원이 실제로 배정 가능한 (날짜, 시작, 종료) 후보를 모두 반환.
    선생님이 배정 결과를 수동으로 조정할 때, 고를 수 있는 선택지를 제한하는 데 사용."""
    session_len = timedelta(minutes=round_obj.session_minutes)
    step = timedelta(minutes=15)
    dates = list(_dates_in_range(round_obj.start_date, round_obj.end_date))

    member = Member.query.filter_by(id=member_id, trainer_id=round_obj.trainer_id).first()
    if member is None or member.location is None:
        return []

    trainer_by_weekday = {}
    for t in RecurringTrainerAvailability.query.filter_by(trainer_id=round_obj.trainer_id).all():
        trainer_by_weekday.setdefault(t.weekday, []).append((t.start_time, t.end_time))

    one_off_blackouts = TrainerBlackout.query.filter_by(trainer_id=round_obj.trainer_id).all()

    def is_blacked_out(d, start_dt, end_dt):
        for b in one_off_blackouts:
            if b.date == d and _overlaps(start_dt, end_dt, _to_dt(d, b.start_time), _to_dt(d, b.end_time)):
                return True
        return False

    day_timeline = {}
    member_other_dates = set()  # 이 회원이 (수정 중인 건 제외하고) 이미 배정된 날짜들 - 하루 중복 방지용
    existing_events = ScheduleEvent.query.filter(
        ScheduleEvent.trainer_id == round_obj.trainer_id,
        ScheduleEvent.status.in_(["확정", "완료", "요청"]),
    ).all()
    for e in existing_events:
        if exclude_event_id and e.id == exclude_event_id:
            continue
        day_timeline.setdefault(e.date, []).append(
            (_to_dt(e.date, e.start_time), _to_dt(e.date, e.end_time), e.location)
        )
        if e.member_id == member_id:
            member_other_dates.add(e.date)

    recurring = RecurringAvailability.query.filter_by(member_id=member_id).all()

    slots = []
    for r in recurring:
        for d in dates:
            if d.weekday() != r.weekday or d in member_other_dates:
                continue
            for t_start, t_end in trainer_by_weekday.get(r.weekday, []):
                overlap = _intersect(
                    _to_dt(d, r.start_time), _to_dt(d, r.end_time),
                    _to_dt(d, t_start), _to_dt(d, t_end),
                )
                if not overlap:
                    continue
                cursor = overlap[0]
                while cursor + session_len <= overlap[1]:
                    slot_end = cursor + session_len
                    if not is_blacked_out(d, cursor, slot_end):
                        day_entries = day_timeline.get(d, [])
                        if not _has_conflict(day_entries, cursor, slot_end, member.location):
                            slots.append((d, cursor.time(), slot_end.time()))
                    cursor += step

    return sorted(set(slots))


def generate_schedule(round_obj):
    """round_obj의 RoundQuota(회원별 이번 라운드 희망 횟수)를 기준으로 배정한다.
    반환값: (assigned 이벤트 목록, [(member, 부족한 횟수, 이유), ...])
    """
    session_len = timedelta(minutes=round_obj.session_minutes)
    step = timedelta(minutes=15)

    # 재실행 지원: 이 라운드에서 이전에 생성했던 '요청' 상태 제안은 지우고 다시 계산
    ScheduleEvent.query.filter_by(round_id=round_obj.id, status="요청").delete()
    db.session.flush()

    dates = list(_dates_in_range(round_obj.start_date, round_obj.end_date))

    one_off_blackouts = TrainerBlackout.query.filter_by(trainer_id=round_obj.trainer_id).all()
    trainer_availability = RecurringTrainerAvailability.query.filter_by(trainer_id=round_obj.trainer_id).all()
    existing_events = ScheduleEvent.query.filter(
        ScheduleEvent.trainer_id == round_obj.trainer_id,
        ScheduleEvent.status.in_(["확정", "완료"]),
    ).all()

    # 날짜별 타임라인: [(start_dt, end_dt, location)]
    day_timeline = {}
    for e in existing_events:
        day_timeline.setdefault(e.date, []).append(
            (_to_dt(e.date, e.start_time), _to_dt(e.date, e.end_time), e.location)
        )

    # 요일별 선생님 가능 시간대 (반복 패턴)
    trainer_by_weekday = {}
    for t in trainer_availability:
        trainer_by_weekday.setdefault(t.weekday, []).append((t.start_time, t.end_time))

    def is_blacked_out(d, start_dt, end_dt):
        for b in one_off_blackouts:
            if b.date == d and _overlaps(start_dt, end_dt, _to_dt(d, b.start_time), _to_dt(d, b.end_time)):
                return True
        return False

    # 이번 라운드에 명시적으로 "제출"한 회원만 계산 대상에 포함 (이 트레이너 소속 회원으로 한정)
    trainer_member_ids = {m.id for m in Member.query.filter_by(trainer_id=round_obj.trainer_id).all()}
    submitted_member_ids = {
        s.member_id for s in RoundSubmission.query.filter_by(round_id=round_obj.id).all()
    } & trainer_member_ids

    # 회원별 (날짜, 시작, 종료) 후보 윈도우: 회원 반복 가능시간 X 선생님 반복 가능시간 교집합
    recurring = (
        RecurringAvailability.query.filter(
            RecurringAvailability.member_id.in_(submitted_member_ids)
        ).all()
        if submitted_member_ids
        else []
    )
    by_member = {}
    for r in recurring:
        for d in dates:
            if d.weekday() != r.weekday:
                continue
            for t_start, t_end in trainer_by_weekday.get(r.weekday, []):
                overlap = _intersect(
                    _to_dt(d, r.start_time), _to_dt(d, r.end_time),
                    _to_dt(d, t_start), _to_dt(d, t_end),
                )
                if overlap:
                    by_member.setdefault(r.member_id, []).append((d, overlap[0], overlap[1]))

    # 이번 라운드 회원별 희망 횟수 (잔여 횟수를 넘지 않게 제한)
    quotas = {q.member_id: q.count for q in RoundQuota.query.filter_by(round_id=round_obj.id).all()}

    # 후보 슬롯 개수가 적은(제약이 많은) 회원부터 배정
    member_ids = sorted(
        (mid for mid in by_member if quotas.get(mid, 0) > 0),
        key=lambda mid: len(by_member[mid]),
    )

    assigned = []
    unassigned = []

    for member_id in member_ids:
        member = Member.query.get(member_id)
        windows = by_member[member_id]
        location = member.location
        requested = min(quotas.get(member_id, 0), member.remaining_sessions)

        if location is None:
            if requested > 0:
                unassigned.append((member, requested, "지점이 설정되지 않음"))
            continue

        # 먼저 "어느 날짜에 배정할지"를 정한다 (하루 걸러 배정을 최대한 우선), 그 다음에
        # 각 날짜 안에서 이동거리가 최소가 되는 시간을 고른다. 이렇게 날짜 선택을 먼저 해야
        # 이동거리 최적화 때문에 원하는 요일 간격이 깨지는 걸 막을 수 있다.
        feasible_days = sorted(
            {
                w[0]
                for w in windows
                if _day_has_feasible_slot(w[0], w[1], w[2], day_timeline, location, session_len, step, is_blacked_out)
            }
        )
        target_days = _pick_spaced_days(feasible_days, requested) or feasible_days[:requested]

        done = 0
        for target_date in target_days:
            day_windows = [w for w in windows if w[0] == target_date]
            best = _find_best_slot(day_windows, day_timeline, location, session_len, step, is_blacked_out)
            if best is None:
                continue
            _, best_date, best_start, best_end = best
            event = ScheduleEvent(
                trainer_id=round_obj.trainer_id,
                member_id=member.id,
                round_id=round_obj.id,
                location_id=location.id,
                date=best_date,
                start_time=best_start.time(),
                end_time=best_end.time(),
                source="member",
                status="요청",
            )
            db.session.add(event)
            day_timeline.setdefault(best_date, []).append((best_start, best_end, location))
            assigned.append(event)
            done += 1

        if done < requested:
            unassigned.append((member, requested - done, "겹치는 시간이 이미 다 참"))

    # 이번 라운드에 배정을 요청했지만(quota>0) 후보 시간대가 아예 없었던 회원 - 이유를 구분해서 안내
    range_weekdays = {d.weekday() for d in dates}
    for member_id, count in quotas.items():
        if count <= 0 or member_id in by_member:
            continue
        member = Member.query.get(member_id)
        if member_id not in submitted_member_ids:
            reason = "이번 라운드에 제출하지 않음"
            unassigned.append((member, count, reason))
            continue
        member_availability = [r for r in recurring if r.member_id == member_id]
        if not member_availability:
            reason = "고정 가능 시간 미설정"
        elif not any(r.weekday in range_weekdays for r in member_availability):
            reason = "설정한 요일이 이 라운드 기간에 없음"
        else:
            reason = "선생님 가능 시간과 겹치지 않음"
        unassigned.append((member, count, reason))

    round_obj.status = "계산됨"
    db.session.commit()
    return assigned, unassigned
