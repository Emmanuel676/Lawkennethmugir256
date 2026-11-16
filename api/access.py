"""Request access (Phase 14): the client address behind a proxy, and the per-address request limit.

Client address. Behind a host's proxies the connection comes from the proxy, and the visitor's address is in the
X-Forwarded-For header, which a visitor can also send themselves. So the header is used ONLY when the settings say
how many trusted proxies sit in front (FAIRLEND_PROXY_HOPS): each proxy appends the address it received the request
from, so the visitor's address is the entry that many places from the end. Vercel in front of Render is 2 hops.
With 0 (the default, and the safe fallback whenever the header is missing or too short) the direct connection
address is used, which cannot be forged.

Limit. At most `per_hour` access requests per address in any rolling hour, kept in this process's memory (one API
instance; the counts reset when it restarts). Nothing here is logged; addresses are kept only as long as needed.
"""

from __future__ import annotations

import threading
import time
from collections import deque

MAX_TRACKED = 10_000
WINDOW_SECONDS = 3600


def client_address(request, proxy_hops: int) -> str:
    """The visitor's address: from X-Forwarded-For when `proxy_hops` trusted proxies are in front, else the peer."""
    peer = request.client.host if request.client else "unknown"
    if proxy_hops <= 0:
        return peer
    header = request.headers.get("x-forwarded-for", "")
    parts = [part.strip() for part in header.split(",") if part.strip()]
    if len(parts) < proxy_hops:
        return peer
    return parts[-proxy_hops][:64]


class RequestLimiter:
    """A rolling one-hour count per address, in memory."""

    def __init__(self, per_hour: int, clock=time.monotonic):
        self.per_hour = int(per_hour)
        self._clock = clock
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, address: str) -> bool:
        """Record one request from `address`; False when it is over the limit (the request is not counted then)."""
        now = self._clock()
        with self._lock:
            if len(self._hits) > MAX_TRACKED:
                self._prune(now)
            hits = self._hits.setdefault(address, deque())
            while hits and now - hits[0] > WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= self.per_hour:
                return False
            hits.append(now)
            return True

    def _prune(self, now: float) -> None:
        for address in list(self._hits):
            hits = self._hits[address]
            while hits and now - hits[0] > WINDOW_SECONDS:
                hits.popleft()
            if not hits:
                del self._hits[address]
