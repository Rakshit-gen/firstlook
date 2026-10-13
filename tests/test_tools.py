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


def test_search_logs_groups_messages():
    out = call("search_logs", service="payments", minutes=120).splitlines()
    assert out[0] == "1525 error lines for payments in the last 120 minutes:"
    assert out[1].startswith("- 1525x since 14:59:")
    assert out[1].endswith(
        "UTC: TypeError: cannot read property 'last4' of undefined at RefundHandler.tokenize"
    )
    assert call("search_logs", service="payments", contains="timeout").startswith(
        "No error logs for payments in the last 30 minutes containing 'timeout'."
    )
    assert call("search_logs", service="inventory").startswith("No error logs")


def test_recent_deploys_newest_first():
    out = call("recent_deploys").splitlines()
    assert out == [
        "- 14:58 UTC payments v2.14.0 by ci: Refactor refund handler to the new card token format",
        "- 14:20 UTC inventory v3.2.1 by ci: Bump logging library",
    ]
    assert call("recent_deploys", service="web") == "No deploys in the last 120 minutes to web."


def test_dependencies_both_ways():
    assert call("dependencies", service="payments") == (
        "payments calls: payments-db.\nCalled by: checkout."
    )
    assert call("dependencies", service="web").endswith("Called by: nothing.")


def test_runbook():
    assert call("read_runbook", service="payments").startswith("Errors right after a deploy")
    assert call("read_runbook", service="web") == "No runbook for web."


def test_a_wrong_service_name_is_an_answer_not_a_crash():
    for name in ("query_metric", "search_logs", "dependencies", "read_runbook"):
        args = {"service": "paymnts"}
        if name == "query_metric":
            args["metric"] = "cpu"
        out = call(name, **args)
        assert out.startswith("Error: no service 'paymnts' (have: checkout,"), name
