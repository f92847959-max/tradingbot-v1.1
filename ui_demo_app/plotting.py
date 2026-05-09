"""Terminal plot renderers with an optional plotext backend."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rich.text import Text

try:
    import plotext as _plotext
except ImportError:  # pragma: no cover - depends on optional local dependency
    _plotext = None


class PlotextRenderable:
    def __init__(
        self,
        data1: Sequence[float],
        name1: str,
        color1: str,
        data2: Sequence[float] | None = None,
        name2: str = "",
        color2: str = "",
        title: str = "",
    ) -> None:
        self.data1 = list(data1)
        self.name1 = name1
        self.color1 = color1
        self.data2 = list(data2) if data2 is not None else None
        self.name2 = name2
        self.color2 = color2
        self.title = title

    def __rich_console__(self, console: Any, options: Any) -> Any:
        if _plotext is None or not _supports_plotext_output(console):
            yield Text(self._fallback_text())
            return

        _plotext.clf()
        _plotext.plotsize(options.max_width, options.max_height)
        _plotext.plot(self.data1, marker="braille", color=self.color1, label=self.name1)
        if self.data2 is not None:
            _plotext.plot(self.data2, marker="braille", color=self.color2, label=self.name2)
        _plotext.title(self.title)
        _plotext.theme("clear")
        _plotext.xaxes(1, 0)
        _plotext.yaxes(1, 0)
        yield Text.from_ansi(_plotext.build())

    def _fallback_text(self) -> str:
        lines = [f"{self.title or self.name1}"]
        lines.append(_series_summary(self.name1, self.data1))
        if self.data2 is not None:
            lines.append(_series_summary(self.name2, self.data2))
        return "\n".join(lines)


def _series_summary(label: str, values: Sequence[float]) -> str:
    if not values:
        return f"{label}: --"
    return f"{label}: {values[0]:.3f} -> {values[-1]:.3f} ({len(values)} pts)"


def _supports_plotext_output(console: Any) -> bool:
    encoding = getattr(getattr(console, "file", None), "encoding", "") or ""
    return "utf" in encoding.lower()
