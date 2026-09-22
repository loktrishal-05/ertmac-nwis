"""Process-lifetime dispatch observations; neither persistent audit nor packet capture."""
from datetime import datetime, timezone
from threading import Lock

_lock = Lock()
_started_at = datetime.now(timezone.utc)
_calls = {'local_ai_attempts': 0, 'external_ai_calls': 0}


def record_dispatch(classification):
    with _lock:
        key = 'local_ai_attempts' if classification in ('local', 'private') else 'external_ai_calls'
        _calls[key] += 1


def snapshot():
    with _lock:
        return dict(_calls, observed_since=_started_at)
