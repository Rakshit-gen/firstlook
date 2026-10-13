"""Find when a metric changed, so a tool can say "errors jumped at 14:59"
instead of handing the model 120 numbers."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Shift:
    index: int  # first point of the new level
    before: float  # mean before
    after: float  # mean from index on
    score: float  # mean change in units of the noise; above ~5 is a real change

    @property
    def ratio(self) -> float:
        return self.after / self.before if self.before else math.inf


def find_shift(values: list[float], min_side: int = 3) -> Shift | None:
    """The single split that best separates the series into two levels.

    Scored as the change in mean over the pooled standard deviation, using
    prefix sums so it's one pass. None if the series is too short.
    """
    n = len(values)
    if n < 2 * min_side:
        return None
    s1 = [0.0]
    s2 = [0.0]
    for v in values:
        s1.append(s1[-1] + v)
        s2.append(s2[-1] + v * v)
    best = None
    for k in range(min_side, n - min_side + 1):
        a, b = k, n - k
        ma, mb = s1[k] / a, (s1[n] - s1[k]) / b
        va = max(s2[k] / a - ma * ma, 0.0)
        vb = max((s2[n] - s2[k]) / b - mb * mb, 0.0)
        sd = math.sqrt((a * va + b * vb) / n)
        scale = max(sd, 1e-6 * max(abs(ma), abs(mb), 1e-9))
        score = abs(mb - ma) / scale
        if best is None or score > best.score:
            best = Shift(k, ma, mb, score)
    return best
