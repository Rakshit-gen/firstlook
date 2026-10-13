import json
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from promfake import FakeProm

from firstlook.live import LiveEnv
from firstlook.tools import make_tools

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
ERRORS = 'sum(rate(http_errors_total{service="{service}"}[1m]))'


@pytest.fixture
def setup(tmp_path):
    points = [
        [(NOW - timedelta(minutes=m)).timestamp(), "0.2" if m < 10 else "0.001"]
        for m in range(30, -1, -1)
    ]
    fake = FakeProm(
        {
            'ALERTS{alertstate="firing"}': [
                {"metric": {"alertname": "HighErrorRate", "service": "api"}, "value": [0, "1"]}
            ],
            "ALERTS_FOR_STATE": [
                {
                    "metric": {"alertname": "HighErrorRate", "service": "api"},
                    "value": [0, str((NOW - timedelta(minutes=7)).timestamp())],
                }
            ],
            ERRORS.replace("{service}", "api"): [{"metric": {}, "values": points}],
        }
    )
    (tmp_path / "deploys.jsonl").write_text(
        json.dumps({"service": "api", "version": "v7", "at": "2026-10-09T11:48:00Z"})
        + "\n"
        + json.dumps({"service": "db", "version": "old", "at": "2026-10-08T11:48:00Z"})
        + "\n"
    )
    (tmp_path / "logs.jsonl").write_text(
        json.dumps(
            {"time": "2026-10-09T11:51:00Z", "service": "api", "level": "error", "message": "boom"}
        )
        + "\n"
    )
    (tmp_path / "runbooks").mkdir()
    (tmp_path / "runbooks" / "api.md").write_text("Roll back first.")
    config = {
        "prometheus": fake.url,
        "deploys": "deploys.jsonl",
        "logs": "logs.jsonl",
        "runbooks": "runbooks",
        "queries": {"error_rate": ERRORS},
        "services": {"api": {"depends_on": ["db"]}, "db": {}},
    }
    yield LiveEnv(config, tmp_path, now=NOW)
    fake.close()


def test_reads_each_source(setup):
    env = setup
    (alert,) = env.alerts()
    assert alert.describe() == "HighErrorRate on api since 11:53 UTC"
    assert [d.version for _, d in env.deploys(60)] == ["v7"]
    assert [line.message for line in env.logs("api", 30)] == ["boom"]
    assert env.runbook("api") == "Roll back first." and env.runbook("db") is None
    assert env.depends_on("api") == ["db"]
    assert env.metric("db", "error_rate", 30) == []  # Prometheus has nothing for db
    assert env.metric("api", "cpu", 30) == []  # no query configured


def test_the_agent_tools_work_on_it(setup):
    tools = {t.name: t for t in make_tools(setup)}
    out = tools["query_metric"].invoke({"service": "api", "metric": "error_rate", "minutes": 30})
    assert "rose from 0.001 to 0.2" in out and "at 11:51 UTC" in out
    assert "no service 'nope'" in tools["search_logs"].invoke({"service": "nope"})


def test_config_mistakes_are_named(tmp_path):
    with pytest.raises(ValueError, match="needs prometheus"):
        LiveEnv({"services": {}}, tmp_path)
    with pytest.raises(ValueError, match="unknown metric in \\[queries\\]: errors"):
        LiveEnv({"prometheus": "x", "services": {}, "queries": {"errors": "q"}}, tmp_path)


def test_the_example_config_is_valid():
    path = Path(__file__).parent.parent / "examples" / "live" / "firstlook.toml"
    config = tomllib.loads(path.read_text())
    env = LiveEnv(config, path.parent, prom=object(), now=NOW)  # never queried here
    assert env.services() == ["checkout", "payments", "web"]
    assert [d.version for _, d in env.deploys(60)] == ["v2.14.0"]
    assert env.runbook("payments").startswith("Errors right after a deploy")


def test_a_prometheus_error_is_an_answer_not_a_crash(tmp_path):
    q = ERRORS.replace("{service}", "api")
    fake = FakeProm({q: "exceeded maximum resolution of 11,000 points per timeseries"})
    config = {"prometheus": fake.url, "queries": {"error_rate": ERRORS}, "services": {"api": {}}}
    try:
        tools = {t.name: t for t in make_tools(LiveEnv(config, tmp_path, now=NOW))}
        out = tools["query_metric"].invoke(
            {"service": "api", "metric": "error_rate", "minutes": 20000}
        )
    finally:
        fake.close()
    assert out.startswith("Error from Prometheus: bad_data: exceeded maximum resolution")
