from firstlook.alerts import fired
from firstlook.scenario import builtin

S = builtin("bad-deploy")


def test_error_alerts_fire_after_the_hold_time():
    alerts = fired(S)
    assert [(a.name, a.service) for a in alerts] == [
        ("HighErrorRate", "checkout"),
        ("HighErrorRate", "payments"),
    ]  # web's 4% errors stay under the 5% threshold
    assert alerts[0].fired.strftime("%H:%M") == "15:01"  # errors from 14:59, held 3 minutes
    assert alerts[0].describe().startswith("HighErrorRate on checkout: error_rate 0.1")
