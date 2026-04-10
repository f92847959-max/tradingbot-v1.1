"""Economic calendar integration -- protects trading from high-impact events.

IMPORTANT: This package shadows the stdlib ``calendar`` module.  Libraries like
aiohttp depend on ``calendar.timegm``.  The fixup below ensures the stdlib
module is loaded into ``sys.modules["_calendar_stdlib"]`` *and* that our
package exposes the stdlib's ``timegm`` so ``import calendar; calendar.timegm``
still works from third-party code.
"""

import importlib
import os
import sys

# ---------------------------------------------------------------------------
# Stdlib calendar fixup
# ---------------------------------------------------------------------------
# When Python resolves ``import calendar`` it finds this package (because the
# project root is on sys.path).  aiohttp (and potentially other libs) expect
# the stdlib calendar with ``timegm``.  We solve this by:
#   1. Temporarily removing the project root from sys.path
#   2. Importing the *real* stdlib calendar
#   3. Restoring sys.path
#   4. Re-exporting ``timegm`` on this module so ``calendar.timegm(...)`` works

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_saved_path = sys.path[:]
try:
    # Remove any path entry that could resolve to this package
    sys.path = [
        p for p in sys.path
        if os.path.normcase(os.path.abspath(p)) != os.path.normcase(_project_root)
    ]
    # Also remove '' (cwd) if it would resolve here
    sys.path = [p for p in sys.path if p != "" or os.path.normcase(os.getcwd()) != os.path.normcase(_project_root)]

    # Remove ourselves from sys.modules temporarily so importlib finds stdlib
    _self = sys.modules.pop("calendar", None)
    _stdlib_cal = importlib.import_module("calendar")
    sys.modules["_calendar_stdlib"] = _stdlib_cal
finally:
    sys.path = _saved_path
    # Restore our package as the ``calendar`` module
    if _self is not None:
        sys.modules["calendar"] = _self

# Re-export stdlib timegm so ``calendar.timegm(...)`` works for aiohttp etc.
timegm = _stdlib_cal.timegm

# Clean up module namespace
del importlib, os, _project_root, _saved_path, _self, _stdlib_cal

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
from calendar.event_service import EventService
from calendar.models import EconomicEvent, EventImpact

__all__ = ["EventService", "EconomicEvent", "EventImpact"]
