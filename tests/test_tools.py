from firstlook.env import ScenarioEnv
from firstlook.scenario import load
from firstlook.tools import make_tools

TOOLS = {t.name: t for t in make_tools(ScenarioEnv(load("scenarios/bad-deploy.json")))}


def call(name, **args):
    return TOOLS[name].invoke(args)


def test_list_alerts():
    out = call("list_alerts").splitlines()
    assert out[0].startswith("HighErrorRate on checkout")
    assert out[-1] == "Services: checkout, inventory, payments, payments-db, web"


def test_query_metric_says_when_it_changed():
    out = call("query_metric", service="payments", metric="error_rate", minutes=120)
    assert out.startswith("payments error_rate over the last 120 min: now 0.2")
    assert out.endswith("at 14:59 UTC.")
    assert " rose from 0.001996 to 0.2103 (105x)" in out


def test_query_metric_flat_and_bad_input():
    out = call("query_metric", service="inventory", metric="cpu")
    assert out.endswith("No real change in this window.")
    assert call("query_metric", service="web", metric="vibes").startswith("Unknown metric")
