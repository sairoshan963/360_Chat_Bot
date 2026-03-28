import json
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

SESSION_TTL   = 1800   # 30 minutes
RATE_TTL_MIN  = 60     # 1 minute window
RATE_TTL_HOUR = 3600   # 1 hour window
MAX_PER_MIN   = 20   # raised from 10 — multi-step flows (approve/reject) need ~7 messages
MAX_PER_HOUR  = 200  # raised proportionally
HISTORY_TTL   = 86400  # 24 hours — covers full work day; old sessions restored from DB anyway
MAX_HISTORY   = 10     # 5 exchanges (user + assistant pairs)


def _session_key(user_id):
    return f"chat_session:{user_id}"

def _history_key(user_id):
    return f"chat_history:{user_id}"

def _lock_key(user_id):
    return f"chat_lock:{user_id}"

def _rate_min_key(user_id):
    return f"chat_rate:{user_id}"

def _rate_hour_key(user_id):
    return f"chat_rate_hour:{user_id}"


def get_session(user_id: str) -> dict:
    data = cache.get(_session_key(user_id))
    if data:
        return json.loads(data) if isinstance(data, str) else data
    return {}


def save_session(user_id: str, session_data: dict):
    cache.set(_session_key(user_id), session_data, timeout=SESSION_TTL)


def clear_session(user_id: str):
    cache.delete(_session_key(user_id))


def acquire_lock(user_id: str, ttl: int = 8) -> bool:
    """
    Acquire a per-user processing lock using atomic SET NX.
    Returns True if lock was acquired, False if another request holds it.
    TTL of 8s ensures the lock is always released even if the request crashes.
    """
    return bool(cache.add(_lock_key(user_id), 1, timeout=ttl))


def release_lock(user_id: str):
    """Release the per-user processing lock."""
    cache.delete(_lock_key(user_id))


def get_chat_history(user_id: str) -> list:
    """Return the stored conversation history for this user (list of {role, content})."""
    data = cache.get(_history_key(user_id))
    if data:
        return json.loads(data) if isinstance(data, str) else data
    return []


def append_chat_history(user_id: str, role: str, content: str):
    """Append one message to conversation history, keeping at most MAX_HISTORY entries."""
    history = get_chat_history(user_id)
    history.append({"role": role, "content": content[:500]})  # cap length per entry
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    cache.set(_history_key(user_id), history, timeout=HISTORY_TTL)


def clear_chat_history(user_id: str):
    cache.delete(_history_key(user_id))


def check_rate_limit(user_id: str) -> tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).
    Uses atomic cache.add + cache.incr so concurrent requests cannot
    both slip through by reading the same pre-increment counter value.
    """
    min_key  = _rate_min_key(user_id)
    hour_key = _rate_hour_key(user_id)

    try:
        # cache.add is atomic — only initialises the key if it doesn't exist yet,
        # preserving the original TTL on subsequent calls within the window.
        cache.add(min_key,  0, timeout=RATE_TTL_MIN)
        cache.add(hour_key, 0, timeout=RATE_TTL_HOUR)

        # cache.incr is atomic in Redis — race-safe
        per_min  = cache.incr(min_key)
        per_hour = cache.incr(hour_key)
    except Exception:
        # If Redis is temporarily unavailable, fail open (allow the request)
        return True, ""

    if per_min > MAX_PER_MIN:
        return False, f"Rate limit exceeded: max {MAX_PER_MIN} messages per minute."
    if per_hour > MAX_PER_HOUR:
        return False, f"Rate limit exceeded: max {MAX_PER_HOUR} messages per hour."

    return True, ""
