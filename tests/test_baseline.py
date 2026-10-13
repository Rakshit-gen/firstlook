from firstlook.baseline import baseline
from firstlook.env import ScenarioEnv
from firstlook.scenario import load


def test_baseline_blames_the_payments_deploy():
    f = baseline(ScenarioEnv(load("scenarios/bad-deploy.json")))
    assert (f.service, f.cause, f.action.kind) == ("payments", "deploy", "rollback")
    assert f.evidence[-1] == "14:58 UTC payments v2.14.0"
    assert f.summary == "payments error_rate changed at 14:59, 1 min after v2.14.0 was deployed."
