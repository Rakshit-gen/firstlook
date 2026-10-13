import json

from fakes import calls, scripted
from langchain_core.messages import AIMessage

from firstlook.cli import main


def test_lists_scenarios(capsys):
    assert main(["scenarios"]) == 0
    assert capsys.readouterr().out.startswith("bad-deploy           Checkout failing")


def test_run_with_rules_writes_a_note(capsys):
    assert main(["run", "bad-deploy"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Checkout failing for some customers")
    assert "- Where it starts: **payments**" in out
    assert "- rules only: no model was used" in out


def test_unknown_scenario(capsys):
    assert main(["run", "nope"]) == 2
    assert "no scenario 'nope'" in capsys.readouterr().err


GOOD = {
    "service": "payments",
    "cause": "deploy",
    "summary": "payments v2.14.0 broke refunds.",
    "evidence": ["payments v2.14.0"],
    "confidence": "high",
    "action": {"kind": "rollback", "service": "payments"},
}


def fake_model(monkeypatch):
    model = scripted([calls(("recent_deploys", {})), AIMessage("the deploy")], [GOOD])
    monkeypatch.setattr("firstlook.cli.make_model", lambda spec: model)


def test_run_with_a_model_asks_before_acting(monkeypatch, capsys):
    fake_model(monkeypatch)
    answers = iter(["maybe", "y"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert main(["run", "bad-deploy", "--model", "groq:test"]) == 0
    out = capsys.readouterr().out
    assert "Proposed: roll back payments  (high confidence)" in out
    assert "Result: roll back payments: done, and the alerts cleared." in out


def test_declining_and_auto_approve(monkeypatch, capsys):
    fake_model(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    main(["run", "bad-deploy", "--model", "groq:test"])
    assert "Declined by" in capsys.readouterr().out
    fake_model(monkeypatch)
    main(["run", "bad-deploy", "--model", "groq:test", "--approve"])
    assert "Approved by --approve." in capsys.readouterr().out


def test_default_model_depends_on_the_key(monkeypatch, capsys):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    main(["run", "bad-deploy"])
    assert "rules only" in capsys.readouterr().out


def test_progress_goes_to_stderr(monkeypatch, capsys):
    fake_model(monkeypatch)
    main(["run", "bad-deploy", "--model", "groq:test", "--approve"])
    err = capsys.readouterr().err
    assert "Investigating bad-deploy with groq:test" in err
    assert "  recent_deploys()" in err
    assert "  done looking; writing up" in err
    fake_model(monkeypatch)
    main(["run", "bad-deploy", "--model", "groq:test", "--approve", "-q"])
    assert capsys.readouterr().err == ""


def test_eval_rules(monkeypatch, capsys):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert main(["eval", "bad-deploy", "-q"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("model: rules\n")
    assert "solved 1/1, harmful actions 0" in out
    main(["eval", "bad-deploy", "-q", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["scores"][0]["solved"] is True
