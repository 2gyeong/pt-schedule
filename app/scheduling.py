from datetime import date, datetime, time, timedelta

from app import db
from app.models import (
    Member,
    RecurringAvailability,
    RecurringTrainerAvailability,
    RoundQuota,
    RoundSubmission,
    ScheduleEvent,
    TravelTime,
    TrainerBlackout,
    WeekdayStartLocation,
)


def _to_dt(d: date, t: time) -> datetime:
    return datetime.combine(d, t)


def display_hour_range(trainer):
    """달력/예약 화면에 표시할 시간대. 선생님이 지정해둔 표시 범위가 실제 반복 가능 시간이나
    (마스터 권한으로 그 범위 밖에 등록된) 실제 일정보다 좁으면 자동으로 넓혀서, 일정이 화면
    밖으로 밀려 안 보이는 일이 없게 한다."""
    start_hour = trainer.schedule_start_hour
    end_hour = trainer.schedule_end_hour
    for t in RecurringTrainerAvailability.query.filter_by(trainer_id=trainer.id).all():
        start_hour = min(start_hour, t.start_time.hour)
        end_hour = max(end_hour, t.end_time.hour + (1 if t.end_time.minute else 0))
    for e in ScheduleEvent.query.filter_by(trainer_id=trainer.id).filter(ScheduleEvent.status != "취소").all():
        start_hour = min(start_hour, e.start_time.hour)
        end_hour = max(end_hour, e.end_time.hour + (1 if e.end_time.minute else 0))
    return start_hour, min(end_hour, 24)


def _overlaps(start_a, end_a, start_b, end_b) -> bool:
    return start_a < end_b and start_b < end_a


def _intersect(start_a, end_a, start_b, end_b):
    start = max(start_a, start_b)
    end = min(end_a, end_b)
    return (start, end) if start < end else None


DEFAULT_TRAVEL_MIN = 30  # 지점 간 실제 이동 시간을 아직 입력하지 않았을 때 쓰는 보수적인 기본값
SAME_LOCATION_BREAK_MIN = 10  # 같은 지점에서 연달아 수업할 때 세션 사이에 두는 최소 쉬는 시간(분)
MAX_GAP_MIN = 60  # 같은 날 세션 사이에 이 시간(분)보다 더 비지 않게 한다 (공강처럼 빈 시간 방지)
MAX_MOVES_PER_DAY = 2  # 하루에 지점을 옮기는 횟수 상한. 같은 지점을 다시 가는 것도 허용하되 횟수는 제한한다.
REVISIT_PENALTY_MIN = 45  # 같은 지점을 다시 방문하게 되는 배치는, 가능하면 피하도록 주는 비용(분 단위)


def load_travel_overrides(trainer_id):
    """선생님이 직접 입력해둔 지점 간 실제 이동 시간을 조회 편의를 위해
    {frozenset({location_a_id, location_b_id}): 분} 형태로 미리 불러온다."""
    rows = TravelTime.query.filter_by(trainer_id=trainer_id).all()
    return {frozenset({r.location_a_id, r.location_b_id}): r.minutes for r in rows}


def _travel_minutes(loc_a, loc_b, overrides=None) -> int:
    """서로 다른 지점 사이를 이동하는 데 필요한 최소 시간(분). 같은 지점이면 0.
    선생님이 직접 입력해둔 실제 이동 시간이 있으면 그 값을 그대로 쓰고, 아직 입력하지 않았으면
    보수적인 기본값을 쓴다 (지점 위치 좌표에 의존하지 않음)."""
    if loc_a is None or loc_b is None or loc_a.id == loc_b.id:
        return 0
    if overrides:
        key = frozenset({loc_a.id, loc_b.id})
        if key in overrides:
            return overrides[key]
    return DEFAULT_TRAVEL_MIN


def _min_buffer_minutes(loc_a, loc_b, overrides=None) -> int:
    """세션 사이에 반드시 있어야 하는 최소 간격(분). 같은 지점이면 쉬는 시간(고정값),
    다른 지점이면 이동 시간을 그대로 쓴다 (이동 시간 외에 별도로 쉬는 시간을 더하지 않음)."""
    if loc_a is None or loc_b is None:
        return 0
    if loc_a.id == loc_b.id:
        return SAME_LOCATION_BREAK_MIN
    return _travel_minutes(loc_a, loc_b, overrides)


def _compressed_location_sequence(day_entries, cursor, slot_end, location):
    """그날 지점 방문 순서를, 연달아 같은 지점이면 하나로 뭉쳐서 반환한다.
    예: [A, A, B, A] -> [A, B, A]. 결과 리스트의 길이-1이 그날 이동 횟수다."""
    combined = sorted(day_entries + [(cursor, slot_end, location)], key=lambda e: e[0])
    sequence = []
    for _, _, loc in combined:
        loc_id = loc.id if loc is not None else None
        if not sequence or sequence[-1] != loc_id:
            sequence.append(loc_id)
    return sequence


def _location_pattern_ok(day_entries, cursor, slot_end, location) -> bool:
    """하루 이동 횟수(지점을 바꾸는 횟수)가 MAX_MOVES_PER_DAY를 넘지 않게 한다. 같은 지점을
    다시 방문하는 것 자체는 막지 않는다 (회원마다 주 2회씩 최대한 배정하려면 필요할 수 있음) -
    다만 굳이 재방문이 필요 없으면 피하도록 _insertion_cost에서 별도로 비용을 매긴다."""
    if location is None:
        return True
    sequence = _compressed_location_sequence(day_entries, cursor, slot_end, location)
    moves = len(sequence) - 1
    return moves <= MAX_MOVES_PER_DAY


def _gap_ok(day_entries, cursor, slot_end) -> bool:
    """삽입하려는 슬롯과, 하루 안에서 시간상 바로 앞/뒤에 오는 세션 사이의 빈 시간이
    MAX_GAP_MIN을 넘지 않는지 확인한다 (공강처럼 비는 시간 방지). 그날 첫/유일한
    세션이라 비교할 앞뒤 세션이 없으면 통과시킨다."""
    before_end = None
    after_start = None
    for entry_start, entry_end, _ in day_entries:
        if entry_end <= cursor and (before_end is None or entry_end > before_end):
            before_end = entry_end
        if entry_start >= slot_end and (after_start is None or entry_start < after_start):
            after_start = entry_start
    max_gap = timedelta(minutes=MAX_GAP_MIN)
    if before_end is not None and (cursor - before_end) > max_gap:
        return False
    if after_start is not None and (after_start - slot_end) > max_gap:
        return False
    return True


def _has_conflict(day_entries, cursor, slot_end, location, overrides=None) -> bool:
    """시간이 겹치거나, 세션 사이 간격이 부족하거나(같은 지점이면 쉬는 시간, 다른 지점이면
    이동 시간), 하루 이동 패턴이 비효율적이거나(지점을 너무 여러 번 옮기는 경우), 세션
    사이가 너무 비면(공강) 충돌로 본다."""
    for entry_start, entry_end, entry_loc in day_entries:
        if _overlaps(cursor, slot_end, entry_start, entry_end):
            return True
        buffer_min = _min_buffer_minutes(entry_loc, location, overrides)
        if buffer_min <= 0:
            continue
        buffer = timedelta(minutes=buffer_min)
        if entry_end <= cursor and (cursor - entry_end) < buffer:
            return True
        if slot_end <= entry_start and (entry_start - slot_end) < buffer:
            return True
    if not _location_pattern_ok(day_entries, cursor, slot_end, location):
        return True
    if not _gap_ok(day_entries, cursor, slot_end):
        return True
    return False


def _insertion_cost(day_entries, start_dt, end_dt, location, preferred_start_location=None, overrides=None):
    """day_entries: sorted list of (start_dt, end_dt, location). Cost of inserting
    a new session at [start_dt, end_dt] with the given location, based on the
    extra travel time versus its immediate neighbors in time. If this would be
    the first session of the day, prefer the trainer's configured starting location
    for that weekday (if any)."""
    before = None
    after = None
    for entry_start, entry_end, entry_loc in day_entries:
        if entry_end <= start_dt:
            if before is None or entry_end > before[1]:
                before = (entry_start, entry_end, entry_loc)
        if entry_start >= end_dt:
            if after is None or entry_start < after[0]:
                after = (entry_start, entry_end, entry_loc)

    cost = 0
    if before is not None:
        cost += _travel_minutes(before[2], location, overrides)
    if after is not None:
        cost += _travel_minutes(location, after[2], overrides)
    if before is not None and after is not None:
        cost -= _travel_minutes(before[2], after[2], overrides)
    if before is None and after is None and preferred_start_location is not None:
        cost += _travel_minutes(preferred_start_location, location, overrides)
    if location is not None:
        sequence = _compressed_location_sequence(day_entries, start_dt, end_dt, location)
        if sequence.count(location.id) > 1:
            cost += REVISIT_PENALTY_MIN
    return cost


def _dates_in_range(start_date, end_date):
    d = start_date
    while d <= end_date:
        yield d
        d += timedelta(days=1)


def _merge_intervals(intervals):
    """(start_dt, end_dt) 구간 목록을 겹치거나 맞닿은 것끼리 하나로 합친다.
    회원 가능 시간이 1시간 단위 블록 여러 개로 저장되어 있어도, 연속된 블록이면
    하나의 긴 구간으로 취급해야 그 경계를 넘나드는 세션 시작 시간(예: :20, :40)도 찾을 수 있다."""
    if not intervals:
        return []
    ivs = sorted(intervals)
    merged = [ivs[0]]
    for start, end in ivs[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _find_best_slot(
    windows, day_timeline, location, session_len, step, is_blacked_out,
    start_location_by_weekday=None, overrides=None,
):
    best = None  # (cost, date, start_dt, end_dt)
    start_location_by_weekday = start_location_by_weekday or {}
    for window_date, w_start_dt, w_end_dt in windows:
        preferred_start = start_location_by_weekday.get(window_date.weekday())
        cursor = w_start_dt
        while cursor + session_len <= w_end_dt:
            slot_end = cursor + session_len
            if not is_blacked_out(window_date, cursor, slot_end):
                day_entries = day_timeline.get(window_date, [])
                if not _has_conflict(day_entries, cursor, slot_end, location, overrides):
                    cost = _insertion_cost(day_entries, cursor, slot_end, location, preferred_start, overrides)
                    if best is None or cost < best[0]:
                        best = (cost, window_date, cursor, slot_end)
            cursor += step
    return best


def _day_has_feasible_slot(
    window_date, w_start_dt, w_end_dt, day_timeline, location, session_len, step, is_blacked_out,
    overrides=None,
):
    cursor = w_start_dt
    while cursor + session_len <= w_end_dt:
        slot_end = cursor + session_len
        if not is_blacked_out(window_date, cursor, slot_end):
            day_entries = day_timeline.get(window_date, [])
            if not _has_conflict(day_entries, cursor, slot_end, location, overrides):
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


def _subtract_busy(start, end, busy_intervals):
    """[start,end) 구간에서 busy_intervals와 겹치는 부분을 모두 제거한 남은 구간들을 반환."""
    free = [(start, end)]
    for b_start, b_end in busy_intervals:
        next_free = []
        for f_start, f_end in free:
            if b_end <= f_start or b_start >= f_end:
                next_free.append((f_start, f_end))
                continue
            if b_start > f_start:
                next_free.append((f_start, b_start))
            if b_end < f_end:
                next_free.append((b_end, f_end))
        free = next_free
    return free


def trainer_open_background(trainer_id, start_date, end_date):
    """선생님의 반복 가능 시간에서 특정 날짜 예외(블랙아웃)와 이미 예약된 시간을 뺀,
    실제로 비어있는 구간을 (날짜, 시작, 종료) 목록으로 반환. 회원이 급하게 개별 요청하거나
    예약 변경을 요청할 때, 실제로 고를 수 있는 시간대를 보여주는 용도."""
    trainer_by_weekday = {}
    for t in RecurringTrainerAvailability.query.filter_by(trainer_id=trainer_id).all():
        trainer_by_weekday.setdefault(t.weekday, []).append((t.start_time, t.end_time))

    blackouts = TrainerBlackout.query.filter_by(trainer_id=trainer_id).all()
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
        blocks = trainer_by_weekday.get(d.weekday(), [])
        if not blocks:
            continue
        intervals = [(_to_dt(d, s), _to_dt(d, e)) for s, e in blocks]
        busy = list(busy_by_date.get(d, []))
        busy += [
            (_to_dt(d, b.start_time), _to_dt(d, b.end_time)) for b in blackouts if b.date == d
        ]
        for start, end in _merge_intervals(intervals):
            for free_start, free_end in _subtract_busy(start, end, busy):
                result.append((d, free_start.time(), free_end.time()))

    return result


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


def slot_conflicts(trainer_id, d, start_time, end_time, location, exclude_event_id=None):
    """이 트레이너의 다른 예약들과 시간이 겹치거나 지점 간 이동시간이 부족하면 True.
    회원의 예약 변경 요청을 선생님이 수락할 때, 그 시간이 실제로 가능한지 확인하는 데 사용."""
    start_dt = _to_dt(d, start_time)
    end_dt = _to_dt(d, end_time)
    day_entries = []
    existing = ScheduleEvent.query.filter(
        ScheduleEvent.trainer_id == trainer_id,
        ScheduleEvent.date == d,
        ScheduleEvent.status.in_(["확정", "완료", "요청"]),
    ).all()
    for e in existing:
        if exclude_event_id and e.id == exclude_event_id:
            continue
        day_entries.append((_to_dt(e.date, e.start_time), _to_dt(e.date, e.end_time), e.location))
    overrides = load_travel_overrides(trainer_id)
    return _has_conflict(day_entries, start_dt, end_dt, location, overrides)


def valid_slots_for_member(round_obj, member_id, exclude_event_id=None):
    """이 라운드 기간 동안 해당 회원이 실제로 배정 가능한 (날짜, 시작, 종료) 후보를 모두 반환.
    선생님이 배정 결과를 수동으로 조정할 때, 고를 수 있는 선택지를 제한하는 데 사용."""
    session_len = timedelta(minutes=round_obj.session_minutes)
    step = timedelta(minutes=10)
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
    member_by_weekday = {}
    for r in recurring:
        member_by_weekday.setdefault(r.weekday, []).append((r.start_time, r.end_time))

    overrides = load_travel_overrides(round_obj.trainer_id)
    slots = []
    for d in dates:
        if d in member_other_dates:
            continue
        weekday = d.weekday()
        member_blocks = member_by_weekday.get(weekday, [])
        trainer_blocks = trainer_by_weekday.get(weekday, [])
        if not member_blocks or not trainer_blocks:
            continue
        overlaps = []
        for m_start, m_end in member_blocks:
            for t_start, t_end in trainer_blocks:
                overlap = _intersect(
                    _to_dt(d, m_start), _to_dt(d, m_end),
                    _to_dt(d, t_start), _to_dt(d, t_end),
                )
                if overlap:
                    overlaps.append(overlap)
        for start, end in _merge_intervals(overlaps):
            cursor = start
            while cursor + session_len <= end:
                slot_end = cursor + session_len
                if not is_blacked_out(d, cursor, slot_end):
                    day_entries = day_timeline.get(d, [])
                    if not _has_conflict(day_entries, cursor, slot_end, member.location, overrides):
                        slots.append((d, cursor.time(), slot_end.time()))
                cursor += step

    return sorted(set(slots))


def generate_schedule(round_obj):
    """round_obj의 RoundQuota(회원별 이번 라운드 희망 횟수)를 기준으로 배정한다.
    반환값: (assigned 이벤트 목록, [(member, 부족한 횟수, 이유), ...])
    """
    session_len = timedelta(minutes=round_obj.session_minutes)
    step = timedelta(minutes=10)

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
    # 회원별로 이미 확정/완료된 날짜 - 같은 회원이 같은 날 두 번 배정되지 않도록 (다른 회차 건 포함)
    member_existing_dates = {}
    for e in existing_events:
        day_timeline.setdefault(e.date, []).append(
            (_to_dt(e.date, e.start_time), _to_dt(e.date, e.end_time), e.location)
        )
        member_existing_dates.setdefault(e.member_id, set()).add(e.date)

    # 요일별 선생님 가능 시간대 (반복 패턴)
    trainer_by_weekday = {}
    for t in trainer_availability:
        trainer_by_weekday.setdefault(t.weekday, []).append((t.start_time, t.end_time))

    # 요일별로 그날 첫 세션을 시작하고 싶은 지점 (선생님이 지정, 계속 유지됨)
    start_location_by_weekday = {
        s.weekday: s.location
        for s in WeekdayStartLocation.query.filter_by(trainer_id=round_obj.trainer_id).all()
    }

    # 선생님이 직접 입력해둔 지점 간 실제 이동 시간 (있으면 거리 기반 자동 계산 대신 사용)
    travel_overrides = load_travel_overrides(round_obj.trainer_id)

    def is_blacked_out(d, start_dt, end_dt):
        for b in one_off_blackouts:
            if b.date == d and _overlaps(start_dt, end_dt, _to_dt(d, b.start_time), _to_dt(d, b.end_time)):
                return True
        return False

    # 이번 라운드에 명시적으로 "제출"한 회원만 계산 대상에 포함 (이 트레이너 소속 회원으로 한정)
    trainer_member_ids = {
        m.id for m in Member.query.filter_by(trainer_id=round_obj.trainer_id, is_deleted=False, is_prospect=False).all()
    }
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
    member_blocks_by_member_weekday = {}
    for r in recurring:
        member_blocks_by_member_weekday.setdefault((r.member_id, r.weekday), []).append(
            (r.start_time, r.end_time)
        )

    # 가능 시간을 하나도 설정하지 않은 회원(예: 최진택처럼 "x")이라도 제출완료 상태면
    # (직접 제출했든, 선생님이 강제로 제출완료 처리했든) 선생님의 근무 시간 전체를
    # 그대로 후보 시간으로 사용해서, 스케줄상 남는 효율적인 시간에 배치될 수 있게 한다.
    # 회원이 실제로 가능 시간을 설정해뒀으면 그 설정을 그대로 우선한다.
    members_with_own_availability = {r.member_id for r in recurring}
    for member_id in submitted_member_ids:
        if member_id in members_with_own_availability:
            continue
        for weekday, blocks in trainer_by_weekday.items():
            member_blocks_by_member_weekday.setdefault((member_id, weekday), []).extend(blocks)

    by_member = {}
    for (member_id, weekday), member_blocks in member_blocks_by_member_weekday.items():
        trainer_blocks = trainer_by_weekday.get(weekday, [])
        if not trainer_blocks:
            continue
        for d in dates:
            if d.weekday() != weekday:
                continue
            overlaps = []
            for m_start, m_end in member_blocks:
                for t_start, t_end in trainer_blocks:
                    overlap = _intersect(
                        _to_dt(d, m_start), _to_dt(d, m_end),
                        _to_dt(d, t_start), _to_dt(d, t_end),
                    )
                    if overlap:
                        overlaps.append(overlap)
            for start, end in _merge_intervals(overlaps):
                by_member.setdefault(member_id, []).append((d, start, end))

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
        member_booked_dates = member_existing_dates.get(member_id, set())
        feasible_days = sorted(
            {
                w[0]
                for w in windows
                if w[0] not in member_booked_dates
                and _day_has_feasible_slot(
                    w[0], w[1], w[2], day_timeline, location, session_len, step, is_blacked_out, travel_overrides
                )
            }
        )
        target_days = _pick_spaced_days(feasible_days, requested) or feasible_days[:requested]

        done = 0
        for target_date in target_days:
            day_windows = [w for w in windows if w[0] == target_date]
            best = _find_best_slot(
                day_windows, day_timeline, location, session_len, step, is_blacked_out,
                start_location_by_weekday, travel_overrides,
            )
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
