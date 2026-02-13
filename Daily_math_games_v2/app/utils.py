from __future__ import annotations

from datetime import datetime, timezone


def today_local_date_str() -> str:
    return datetime.now().date().isoformat()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_valid_date_str(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False
