import random

import pytest

from firstlook.generate import series
from firstlook.scenario import builtin
from firstlook.shift import find_shift


def test_finds_the_step_in_the_bad_deploy():
    s = builtin("bad-deploy")
    shift = find_shift(series(s, "payments", "error_rate"))
    assert shift.index == 59
    assert shift.after / shift.before == pytest.approx(105, rel=0.05)
    assert shift.score > 20


def test_noise_alone_scores_low():
    rng = random.Random(1)
    flat = [100 * (1 + rng.uniform(-0.03, 0.03)) for _ in range(120)]
    assert find_shift(flat).score < 2


def test_too_short():
    assert find_shift([1, 2, 3]) is None
