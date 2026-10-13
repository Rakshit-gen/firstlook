from firstlook.baseline import baseline
from firstlook.env import ScenarioEnv
from firstlook.scenario import builtin


def test_baseline_blames_the_payments_deploy():
    f = baseline(ScenarioEnv(builtin("bad-deploy")))
    assert (f.service, f.cause, f.action.kind) == ("payments", "deploy", "rollback")
    assert f.evidence[-1] == "14:58 UTC payments v2.14.0"
    assert f.summary == "payments error_rate changed at 14:59, 1 min after v2.14.0 was deployed."


def test_baseline_restarts_the_database_in_db_pool():
    # A known miss: the rules only look below the alerting services, so they
    # never see the reports release that is holding the connections.
    f = baseline(ScenarioEnv(builtin("db-pool")))
    assert (f.service, f.action.kind) == ("orders-db", "restart")
