from firstlook.baseline import baseline
from firstlook.env import ScenarioEnv
from firstlook.scenario import builtin, parse


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


def test_tie_goes_to_the_called_service_whatever_the_names():
    s = parse(
        {
            "name": "tie",
            "title": "tie",
            "start": "2026-10-01T00:00:00Z",
            "services": {"a-db": {}, "b-api": {"depends_on": ["a-db"]}},
            "effects": [
                {"service": "a-db", "metric": "error_rate", "to": 0.3, "at": 60},
                {"service": "b-api", "metric": "error_rate", "to": 0.3, "at": 60},
            ],
        }
    )
    assert baseline(ScenarioEnv(s)).service == "a-db"


def test_baseline_escalates_to_the_vendor_not_the_fresh_release():
    f = baseline(ScenarioEnv(builtin("slow-vendor")))
    assert (f.service, f.cause, f.action.kind) == ("geo-vendor", "dependency", "escalate")


def test_baseline_reads_an_expired_certificate_as_traffic():
    # A known miss: requests stop reaching auth, so the deepest change is a
    # drop in users-db traffic, and the rules can't tell a drop from a flood.
    f = baseline(ScenarioEnv(builtin("cert-expiry")))
    assert (f.service, f.cause, f.action.kind) == ("users-db", "traffic", "rate_limit")


def test_baseline_misses_a_slow_disk_fill():
    # A known miss: the shift detector looks for steps, and a disk filling over
    # an hour isn't one, so the first change it sees is the errors at the end.
    f = baseline(ScenarioEnv(builtin("disk-full")))
    assert (f.service, f.cause, f.action.kind) == ("ingest", "unknown", "escalate")


def test_baseline_rate_limits_the_cache_in_a_flash_sale():
    # A known miss: the extra traffic reaches every layer in the same minute,
    # and the tie rule picks the deepest one, which isn't the one struggling.
    f = baseline(ScenarioEnv(builtin("traffic-spike")))
    assert (f.service, f.cause, f.action.kind) == ("cache", "traffic", "rate_limit")
