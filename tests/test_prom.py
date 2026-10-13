from datetime import UTC, datetime

import pytest
from promfake import FakeProm

from firstlook.prom import PromError, Prometheus

T0 = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)


@pytest.fixture
def prom():
    fake = FakeProm(
        {
            "up": [{"metric": {"job": "api"}, "value": [T0.timestamp(), "1"]}],
            "rate(x[1m])": [
                {"metric": {}, "values": [[T0.timestamp(), "0.5"], [T0.timestamp() + 60, "NaN"]]}
            ],
            "bad(": "parse error: unclosed left parenthesis",
        }
    )
    yield fake
    fake.close()


def test_instant_and_range_queries(prom):
    p = Prometheus(prom.url + "/")
    assert p.query("up") == [({"job": "api"}, 1.0)]
    assert p.query_range("rate(x[1m])", T0, T0) == [(T0, 0.5)]  # NaN dropped
    assert p.query_range("nothing", T0, T0) == []
    assert prom.asked[1]["path"] == "/api/v1/query_range" and prom.asked[1]["step"] == "60"


def test_errors_carry_the_reason(prom):
    with pytest.raises(PromError, match="bad_data: parse error"):
        Prometheus(prom.url).query("bad(")
    with pytest.raises(PromError, match="127.0.0.1:9"):
        Prometheus("http://127.0.0.1:9", timeout=1).query("up")
