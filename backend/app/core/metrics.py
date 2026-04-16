from collections import Counter
from threading import Lock

_COUNTERS: Counter[str] = Counter()
_LOCK = Lock()


def incr(metric: str, amount: int = 1) -> None:
    with _LOCK:
        _COUNTERS[metric] += amount


def snapshot() -> dict[str, int]:
    with _LOCK:
        return dict(_COUNTERS)


def reset() -> None:
    with _LOCK:
        _COUNTERS.clear()
