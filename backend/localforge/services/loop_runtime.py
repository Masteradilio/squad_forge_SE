import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from localforge.models import domain
from localforge.models.enums import TriggerKind

INTERVAL_RE = re.compile(r"^(?P<count>[1-9][0-9]*)(?P<unit>s|m|h|d)$")
MINUTE_RE = re.compile(r"^\*/(?P<step>[1-9][0-9]*)$")


@dataclass(frozen=True)
class ScheduleState:
    timezone: str
    misfire_policy: str
    trigger_revision: int
    next_run_at: datetime | None
    last_trigger_at: datetime | None


def validate_schedule(trigger: domain.LoopTrigger) -> None:
    if trigger.kind == TriggerKind.INTERVAL:
        if not trigger.schedule or not INTERVAL_RE.match(trigger.schedule.strip()):
            raise ValueError("Interval loop schedule must use '<positive-int><s|m|h|d>'.")
        return
    if trigger.kind == TriggerKind.CRON:
        if not trigger.schedule:
            raise ValueError("Cron loop schedule is required.")
        _parse_cron(trigger.schedule)
        return
    if trigger.kind in (TriggerKind.MANUAL, TriggerKind.EVENT):
        return
    raise ValueError(f"Unsupported loop trigger kind: {trigger.kind}")


def read_schedule_state(trigger: domain.LoopTrigger) -> ScheduleState:
    metadata = trigger.metadata or {}
    timezone = str(metadata.get("timezone") or "UTC")
    _timezone(timezone)
    misfire_policy = str(metadata.get("misfire_policy") or "skip")
    if misfire_policy not in {"skip", "bounded_catchup"}:
        raise ValueError("misfire_policy must be 'skip' or 'bounded_catchup'.")
    return ScheduleState(
        timezone=timezone,
        misfire_policy=misfire_policy,
        trigger_revision=int(metadata.get("trigger_revision") or 0),
        next_run_at=_parse_datetime(metadata.get("next_run_at")),
        last_trigger_at=_parse_datetime(metadata.get("last_trigger_at")),
    )


def initialize_schedule_metadata(
    trigger: domain.LoopTrigger, *, now: datetime | None = None
) -> domain.LoopTrigger:
    validate_schedule(trigger)
    if trigger.kind not in (TriggerKind.INTERVAL, TriggerKind.CRON):
        return trigger
    now_utc = _utc(now)
    state = read_schedule_state(trigger)
    metadata = dict(trigger.metadata or {})
    metadata.setdefault("timezone", state.timezone)
    metadata.setdefault("misfire_policy", state.misfire_policy)
    metadata.setdefault("trigger_revision", state.trigger_revision)
    metadata["next_run_at"] = _iso_utc(state.next_run_at or next_run_at(trigger, now=now_utc))
    return trigger.model_copy(update={"metadata": metadata})


def claim_schedule_metadata(
    trigger: domain.LoopTrigger, *, now: datetime | None = None
) -> tuple[domain.LoopTrigger | None, str | None]:
    validate_schedule(trigger)
    if trigger.kind not in (TriggerKind.INTERVAL, TriggerKind.CRON):
        return None, None
    now_utc = _utc(now)
    state = read_schedule_state(trigger)
    due_at = state.next_run_at or next_run_at(trigger, now=now_utc)
    if due_at > now_utc:
        return None, None

    key = f"{trigger.kind.value.lower()}:{_iso_utc(due_at)}:rev:{state.trigger_revision}"
    metadata = dict(trigger.metadata or {})
    metadata["last_trigger_at"] = _iso_utc(due_at)
    metadata["last_idempotency_key"] = key
    metadata["trigger_revision"] = state.trigger_revision + 1
    metadata["next_run_at"] = _iso_utc(_next_after_misfire(trigger, due_at=due_at, now=now_utc))
    return trigger.model_copy(update={"metadata": metadata}), key


def next_run_at(trigger: domain.LoopTrigger, *, now: datetime | None = None) -> datetime:
    validate_schedule(trigger)
    now_utc = _utc(now)
    if trigger.kind == TriggerKind.INTERVAL:
        return now_utc + _interval_delta(trigger.schedule or "")
    if trigger.kind == TriggerKind.CRON:
        timezone = read_schedule_state(trigger).timezone
        return _next_cron_at(trigger.schedule or "", now_utc, timezone)
    raise ValueError(f"Trigger kind {trigger.kind.value} does not have a schedule.")


def _next_after_misfire(
    trigger: domain.LoopTrigger, *, due_at: datetime, now: datetime
) -> datetime:
    state = read_schedule_state(trigger)
    if state.misfire_policy == "bounded_catchup":
        return _advance_once(trigger, due_at)
    next_at = _advance_once(trigger, due_at)
    while next_at <= now:
        next_at = _advance_once(trigger, next_at)
    return next_at


def _advance_once(trigger: domain.LoopTrigger, anchor: datetime) -> datetime:
    if trigger.kind == TriggerKind.INTERVAL:
        return anchor + _interval_delta(trigger.schedule or "")
    if trigger.kind == TriggerKind.CRON:
        timezone = read_schedule_state(trigger).timezone
        return _next_cron_at(trigger.schedule or "", anchor, timezone)
    raise ValueError(f"Trigger kind {trigger.kind.value} does not have a schedule.")


def _interval_delta(schedule: str) -> timedelta:
    match = INTERVAL_RE.match(schedule.strip())
    if not match:
        raise ValueError("Invalid interval schedule.")
    count = int(match.group("count"))
    unit = match.group("unit")
    if unit == "s":
        return timedelta(seconds=count)
    if unit == "m":
        return timedelta(minutes=count)
    if unit == "h":
        return timedelta(hours=count)
    return timedelta(days=count)


def _parse_cron(schedule: str) -> tuple[str, str, str, str, str]:
    parts = schedule.strip().split()
    if len(parts) != 5:
        raise ValueError("Cron schedule must contain exactly five fields.")
    minute, hour, day, month, weekday = parts
    _validate_cron_field(minute, 0, 59, allow_step=True)
    _validate_cron_field(hour, 0, 23)
    _validate_cron_field(day, 1, 31)
    _validate_cron_field(month, 1, 12)
    _validate_cron_field(weekday, 0, 6)
    return minute, hour, day, month, weekday


def _validate_cron_field(value: str, minimum: int, maximum: int, *, allow_step: bool = False) -> None:
    if value == "*":
        return
    if allow_step and MINUTE_RE.match(value):
        step_match = MINUTE_RE.match(value)
        assert step_match is not None
        step = int(step_match.group("step"))
        if step > maximum + 1:
            raise ValueError("Cron minute step exceeds valid range.")
        return
    try:
        numeric = int(value)
    except ValueError as exc:
        raise ValueError(f"Unsupported cron field: {value}") from exc
    if numeric < minimum or numeric > maximum:
        raise ValueError(f"Cron field {value} outside range {minimum}-{maximum}.")


def _next_cron_at(schedule: str, now_utc: datetime, timezone: str) -> datetime:
    minute, hour, day, month, weekday = _parse_cron(schedule)
    tz = _timezone(timezone)
    cursor = now_utc.astimezone(tz).replace(second=0, microsecond=0) + timedelta(minutes=1)
    deadline = cursor + timedelta(days=366)
    while cursor <= deadline:
        if (
            _cron_matches(cursor.minute, minute)
            and _cron_matches(cursor.hour, hour)
            and _cron_matches(cursor.day, day)
            and _cron_matches(cursor.month, month)
            and _cron_matches(cursor.weekday(), weekday)
        ):
            return cursor.astimezone(UTC)
        cursor += timedelta(minutes=1)
    raise ValueError("Cron schedule did not produce a run within one year.")


def _cron_matches(value: int, field: str) -> bool:
    if field == "*":
        return True
    step_match = MINUTE_RE.match(field)
    if step_match:
        return value % int(step_match.group("step")) == 0
    return value == int(field)


def _timezone(name: str) -> tzinfo:
    if name.upper() == "UTC":
        # UTC is part of the standard library. Keep the default schedule
        # usable in minimal Windows environments without an installed tzdata
        # wheel; named zones still require the packaged timezone database.
        return UTC
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(parsed)


def _iso_utc(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")
