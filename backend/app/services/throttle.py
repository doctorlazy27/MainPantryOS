from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException

WINDOW_SECONDS = 15 * 60
MAX_FAILURES = 10
_failures: dict[str, deque] = defaultdict(deque)


def check_throttle(key: str) -> None:
    attempts = _failures[key]
    cutoff = monotonic() - WINDOW_SECONDS
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    if len(attempts) >= MAX_FAILURES:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")


def record_failure(key: str) -> None:
    _failures[key].append(monotonic())


def clear_failures(key: str) -> None:
    _failures.pop(key, None)
