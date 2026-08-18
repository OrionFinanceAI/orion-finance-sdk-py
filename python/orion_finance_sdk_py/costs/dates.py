"""User-facing date parsing for execution cost estimates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_DATE_FMT = "%Y-%m-%d"


def parse_cost_timestamp(timestamp: str | None) -> tuple[str, int]:
    """Parse a manager-facing as-of date into ``(YYYY-MM-DD, unix_seconds)``.

    ``None`` means now (UTC). A calendar date is the last second of that UTC
    day so the snapshot is end-of-day state.
    """
    if timestamp is None:
        now = datetime.now(timezone.utc)
        return now.strftime(_DATE_FMT), int(now.timestamp())

    try:
        day = datetime.strptime(timestamp, _DATE_FMT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"timestamp must be YYYY-MM-DD, got {timestamp!r}") from exc

    end_of_day = day + timedelta(days=1) - timedelta(seconds=1)
    return timestamp, int(end_of_day.timestamp())
