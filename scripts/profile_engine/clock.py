"""Display times in the owner's time zone (profile.toml `timezone`).

Data is stored and compared in UTC; only what people read is converted.
Daylight saving is handled by the zone itself (e.g. EDT in summer, EST in winter).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

DEFAULT_TZ = "America/New_York"


def local(d: dt.datetime | str, tz: str | None = None) -> dt.datetime:
    if isinstance(d, str):
        d = dt.datetime.fromisoformat(d.replace("Z", "+00:00"))
    return d.astimezone(ZoneInfo(tz or DEFAULT_TZ))


def stamp(d: dt.datetime | str, tz: str | None = None) -> str:
    """'2026-10-16 12:01 EDT'"""
    t = local(d, tz)
    return f"{t:%Y-%m-%d %H:%M} {t.tzname()}"
