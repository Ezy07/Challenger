"""인터넷 시각 (한국 표준시).

PC 시계가 틀려도 구역 적용 시간을 맞추려고, 잘 알려진 사이트의 HTTP Date 를 받는다.
받지 못하면 이 PC 의 한국 시각을 쓴다. 한국은 서머타임이 없어서 UTC+9 로 고정한다.
"""

import email.utils
import time
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
_CACHE_SEC = 20
_cache: tuple[float, datetime, str] | None = None


def _from_http_date() -> datetime | None:
    req = urllib.request.Request("https://www.cloudflare.com", method="HEAD", headers={"User-Agent": "safety-control"})
    try:
        with urllib.request.urlopen(req, timeout=2) as res:
            raw = res.headers.get("Date")
    except Exception:
        return None
    if not raw:
        return None
    try:
        return email.utils.parsedate_to_datetime(raw).astimezone(KST)
    except (TypeError, ValueError, OverflowError):
        return None


def now_kst() -> tuple[datetime, str]:
    """(한국 시각, "internet" | "local"). 20초 동안은 같은 값을 다시 쓴다."""
    global _cache
    if _cache and time.monotonic() - _cache[0] < _CACHE_SEC:
        return _cache[1], _cache[2]
    fetched = _from_http_date()
    if fetched is None:
        now, source = datetime.now(KST), "local"
    else:
        now, source = fetched, "internet"
    _cache = (time.monotonic(), now, source)
    return now, source
