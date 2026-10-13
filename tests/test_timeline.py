from firstlook.env import ScenarioEnv
from firstlook.scenario import builtin
from firstlook.timeline import timeline


def test_deploys_and_alerts_in_order():
    rows = [(f"{t:%H:%M}", text) for t, text in timeline(ScenarioEnv(builtin("bad-deploy")))]
    assert rows == [
        ("14:20", "deploy inventory v3.2.1: Bump logging library"),
        ("14:58", "deploy payments v2.14.0: Refactor refund handler to the new card token format"),
        ("15:01", "alert HighErrorRate on checkout"),
        ("15:01", "alert HighErrorRate on payments"),
    ]
