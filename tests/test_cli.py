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


def test_pause_then_decide_later(monkeypatch, capsys, tmp_path):
    db = str(tmp_path / "runs.db")
    fake_model(monkeypatch)
    assert main(["run", "bad-deploy", "--model", "groq:test", "--pause", "--db", db, "-q"]) == 0
    out = capsys.readouterr().out
    assert "Proposed: roll back payments" in out
    thread = out.split("Saved as ")[1].split(".")[0]
    assert thread.startswith("bad-deploy-")
    # A fresh process: nothing carried over but the database.
    fake_model(monkeypatch)
    assert main(["decide", thread, "yes", "--by", "sam", "--db", db]) == 0
    assert "Approved by sam." in capsys.readouterr().out
    assert main(["decide", thread, "no", "--db", db]) == 2
    assert "not waiting for a decision" in capsys.readouterr().err
    assert main(["decide", "nope", "yes", "--db", db]) == 2


def test_pause_needs_a_model(capsys):
    assert main(["run", "bad-deploy", "--model", "rules", "--pause"]) == 2


def test_note_to_a_file(tmp_path, capsys):
    out = tmp_path / "note.md"
    assert main(["run", "bad-deploy", "--model", "rules", "-o", str(out)]) == 0
    assert out.read_text().startswith("# Checkout failing for some customers")
    assert capsys.readouterr().out == ""
