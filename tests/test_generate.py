from dataclasses import replace

import pytest

from firstlook.generate import logs, series
from firstlook.scenario import Effect, builtin

S = builtin("bad-deploy")


def test_baseline_then_step():
    errors = series(S, "payments", "error_rate")
    assert len(errors) == 120
    assert all(0.002 * 0.97 <= x <= 0.002 * 1.03 for x in errors[:59])
    assert all(x == pytest.approx(0.21, rel=0.031) for x in errors[59:])


def test_untouched_metrics_stay_at_baseline_and_are_stable():
    rps = series(S, "web", "rps")
    assert all(x == pytest.approx(400, rel=0.031) for x in rps)
    assert rps == series(S, "web", "rps")


def test_ramp():
    s = replace(S, effects=[Effect("web", "cpu", 0.95, at=10, ramp=4)])
    cpu = series(s, "web", "cpu")
    assert cpu[9] == pytest.approx(0.35, rel=0.031)
    assert cpu[10] == pytest.approx(0.35 + 0.6 / 4, rel=0.031)
    assert cpu[13] == pytest.approx(0.95, rel=0.031)


def test_logs():
    lines = logs(S, "payments")
    assert len(lines) == 25 * (120 - 59)
    assert lines == sorted(lines, key=lambda x: x.time)
    assert lines[0].time >= S.start.replace(hour=14, minute=59)
    assert logs(S, "inventory") == []
