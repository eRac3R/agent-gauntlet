"""Best-effort per-IP rate limiting for the public demo.

State is in memory, so on a serverless host each warm instance counts separately.
That is enough to stop casual abuse of the free model quota; it is not a security boundary.
"""
from __future__ import annotations

import collections
import time

from fastapi import HTTPException, Request

WINDOW_S = 60
_hits: dict[tuple[str, str], collections.deque] = collections.defaultdict(collections.deque)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def check(request: Request, bucket: str, per_minute: int) -> None:
    now = time.time()
    q = _hits[(bucket, client_ip(request))]
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= per_minute:
        raise HTTPException(429, f"Rate limit: {per_minute} {bucket} requests per minute. Try again shortly.")
    q.append(now)


def reset() -> None:
    _hits.clear()
