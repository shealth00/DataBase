"""Shared UTC clock helper for hourly patient-records jobs.

Cloud agent VMs sometimes boot with a skewed clock; prefer a network
Date header when local UTC drifts beyond CLOCK_SKEW_TOLERANCE.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)
_NETWORK_TIME_URLS = (
    "https://api.github.com",
    "https://www.google.com",
)


def utc_now() -> tuple[datetime, str]:
    """Return (aware UTC datetime, source). Prefer network Date header on skew."""
    local = datetime.now(timezone.utc)
    for url in _NETWORK_TIME_URLS:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.headers.get("Date")
            if not raw:
                continue
            net = parsedate_to_datetime(raw)
            if net.tzinfo is None:
                net = net.replace(tzinfo=timezone.utc)
            else:
                net = net.astimezone(timezone.utc)
            if abs(net - local) > CLOCK_SKEW_TOLERANCE:
                return net, f"network:{url}"
            return local, "local"
        except (urllib.error.URLError, TimeoutError, ValueError, TypeError, OSError):
            continue
    return local, "local"
