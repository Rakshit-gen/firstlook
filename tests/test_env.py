import pytest

from firstlook.env import ScenarioEnv
from firstlook.scenario import builtin

ENV = ScenarioEnv(builtin("bad-deploy"))


def test_windows_count_back_from_now():
    assert ENV.now.strftime("%H:%M") == "16:00"
    points = ENV.metric("payments", "error_rate", 30)
    assert len(points) == 30 and points[0][0].strftime("%H:%M") == "15:30"
    assert [d.version for _, d in ENV.deploys(70)] == ["v2.14.0"]
    assert [d.version for _, d in ENV.deploys(120)] == ["v3.2.1", "v2.14.0"]
    assert len(ENV.logs("payments", 10)) == 250


def test_unknown_service_names_the_real_ones():
    with pytest.raises(KeyError, match="have: checkout, inventory, payments"):
        ENV.metric("payment", "cpu", 10)


def test_map_and_runbooks():
    assert ENV.depends_on("payments") == ["payments-db"]
    assert ENV.runbook("payments").startswith("Errors right after a deploy")
    assert ENV.runbook("web") is None
