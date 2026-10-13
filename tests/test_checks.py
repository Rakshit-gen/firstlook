from firstlook.checks import check_finding
from firstlook.finding import Finding

SERVICES = ["checkout", "payments"]
ANSWERS = ["- 14:58 UTC payments v2.14.0 by ci: Refactor refund handler"]


def finding(**kw):
    base = {
        "service": "payments",
        "cause": "deploy",
        "summary": "s",
        "evidence": ["14:58 UTC  payments V2.14.0"],
        "confidence": "high",
        "action": {"kind": "rollback", "service": "payments"},
    }
    return Finding(**{**base, **kw})


def test_quotes_found_in_tool_answers_pass():
    f, notes = check_finding(finding(), ANSWERS, SERVICES)
    assert notes == [] and f.action.kind == "rollback" and f.confidence == "high"


def test_made_up_quotes_are_dropped():
    f, notes = check_finding(
        finding(evidence=["14:58 UTC payments v2.14.0", "OOMKilled"]), ANSWERS, SERVICES
    )
    assert f.evidence == ["14:58 UTC payments v2.14.0"]
    assert notes == ["evidence not found in any tool answer: 'OOMKilled'"]


def test_no_real_evidence_means_no_action():
    f, notes = check_finding(finding(evidence=["OOMKilled"]), ANSWERS, SERVICES)
    assert (f.action.kind, f.confidence) == ("escalate", "low")
    assert notes[-1] == "not acting on it: rollback on payments needs evidence"


def test_unknown_services():
    f, notes = check_finding(finding(service="billing"), ANSWERS, SERVICES)
    assert f.action.kind == "escalate"
    assert "'billing' is not a service in this system" in notes
    f, notes = check_finding(
        finding(action={"kind": "restart", "service": "db"}), ANSWERS, SERVICES
    )
    assert (f.action.kind, f.action.service) == ("escalate", "payments")
