"""Time helpers.

Centralizes timestamp creation so we don't sprinkle deprecated
`datetime.utcnow()` across the codebase.
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Timezone-aware UTC 'now'."""
    return datetime.now(timezone.utc)
