import pytest

from firstlook.scenario import SCENARIOS, ScenarioError, builtin, load_all, parse

DOC = {
    "name": "x",
    "title": "x",
    "start": "2026-10-01T14:00:00Z",
    "services": {"a": {"depends_on": ["b"]}, "b": {"baseline": {"rps": 7}}},
}


def test_loads_the_bad_deploy_scenario():
    s = builtin("bad-deploy")
    assert s.truth.service == "payments" and s.truth.fix == "rollback"
    assert [d.version for d in s.deploys] == ["v3.2.1", "v2.14.0"]
    assert s.depends_on("checkout") == ["payments", "inventory"]
    assert s.baseline("payments-db", "p99_ms") == 12
    assert s.baseline("payments", "p99_ms") == 180.0  # default
    assert [x.name for x in load_all(SCENARIOS)][0] == "bad-deploy"


@pytest.mark.parametrize(
    "change, message",
    [
        ({"services": {"a": {"depends_on": ["zz"]}}}, "unknown service zz"),
        ({"effects": [{"service": "a", "metric": "vibes", "to": 1, "at": 1}]}, "unknown metric"),
        ({"deploys": [{"service": "q", "version": "1", "at": 1}]}, "unknown service q"),
        ({"start": "yesterday"}, "bad scenario"),
    ],
)
def test_rejects_broken_scenarios(change, message):
    with pytest.raises(ScenarioError, match=message):
        parse({**DOC, **change})


def test_unknown_builtin_names_the_real_ones():
    with pytest.raises(ScenarioError, match="have: bad-deploy"):
        builtin("bad-deplo")
