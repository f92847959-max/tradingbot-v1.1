"""Session filter — determines if current time is within trading hours."""

from datetime import datetime, timezone, time
from typing import Optional

from shared.utils import current_session


class SessionFilter:
    """Filters trades based on trading session and hours.

    Active sessions: London (07:00–16:00 UTC) and New York (13:00–22:00 UTC).
    No trading on weekends or outside session hours.
    """

    TRADING_START = time(7, 0)   # 07:00 UTC = 09:00 MEZ
    TRADING_END = time(22, 0)    # 22:00 UTC = 00:00 MEZ

    SESSION_QUALITY = {
        "Overlap": 1.0,     # London + NY overlap — best liquidity
        "London": 0.9,      # London session — very good
        "NewYork": 0.8,     # NY session — good
        "Off": 0.0,         # Outside trading hours
    }

    def is_active(self, dt: Optional[datetime] = None) -> bool:
        """Return True if trading should be allowed at the given time."""
        if dt is None:
            dt = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.weekday() >= 5:
            return False
        t = dt.time()
        return self.TRADING_START <= t < self.TRADING_END

    def current_session(self, dt: Optional[datetime] = None) -> str:
        """Return name of current trading session."""
        return current_session(dt)

    def session_quality(self, dt: Optional[datetime] = None) -> float:
        """Return session quality score 0.0–1.0 for scoring purposes."""
        session = self.current_session(dt)
        return self.SESSION_QUALITY.get(session, 0.0)
