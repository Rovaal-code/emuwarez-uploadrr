"""A shared wall-clock deadline the whole analysis run is measured against.

Every step that can be skipped when time is short (bitstream sampling, in
particular) asks `Budget.remaining()` before starting and sizes its own
sub-timeout to whatever's left, rather than each step carrying a fixed
timeout that could sum well past the global target."""
from __future__ import annotations

import time


class Budget:
    def __init__(self, total_s: float):
        self.total_s = total_s
        self._start = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def remaining(self) -> float:
        return max(0.0, self.total_s - self.elapsed())

    def exhausted(self) -> bool:
        return self.remaining() <= 0
