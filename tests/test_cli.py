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
