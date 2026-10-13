import pytest
from fakes import calls, scripted
from langchain_core.messages import AIMessage

from firstlook.evals import run_one, score, table
from firstlook.finding import Action, Finding
from firstlook.scenario import builtin


def finding(service="payments", cause="deploy", kind="rollback", on="payments"):
    return Finding(
        service=service,
        cause=cause,
        summary="x",
        evidence=["a", "b"],
        confidence="high",
        action=Action(kind=kind, service=on),
    )


def test_right_answer_is_solved():
    s = score(finding(), builtin("bad-deploy"), tool_calls=4)
    assert s.solved and not s.harmful
    assert s.to_dict()["solved"] is True
    assert (s.evidence, s.tool_calls) == (2, 4)


def test_wrong_rollback_is_harmful_but_escalating_is_not():
    wrong = score(finding(on="checkout"), builtin("bad-deploy"))
    assert wrong.service and not wrong.fix and wrong.harmful
    safe = score(finding(kind="escalate"), builtin("bad-deploy"))
    assert not safe.solved and not safe.harmful


def test_needs_a_known_answer():
    s = builtin("bad-deploy")
    s.truth = None
    with pytest.raises(ValueError, match="no known answer"):
        score(finding(), s)


def test_run_one_with_rules_and_with_a_model():
    rules = run_one(None, builtin("bad-deploy"))
    assert rules.solved
    good = finding().model_dump()
    good["evidence"] = ["payments v2.14.0"]
    model = scripted([calls(("recent_deploys", {})), AIMessage("done")], [good])
    agent = run_one(model, builtin("bad-deploy"))
    assert agent.solved and agent.tool_calls == 1 and agent.evidence == 1
    out = table([rules, agent])
    assert out.splitlines()[-1] == "solved 2/2, harmful actions 0"
