from firstlook.executor import DryRun, ScenarioExecutor
from firstlook.finding import Action
from firstlook.scenario import load

ROLLBACK = Action(kind="rollback", service="payments", detail="to v2.13.2")


def test_dry_run_records_and_changes_nothing():
    ex = DryRun()
    assert ex.run(ROLLBACK) == "dry run: would roll back payments (to v2.13.2)"
    assert ex.done == [ROLLBACK]


def test_scenario_executor_knows_the_real_fix():
    ex = ScenarioExecutor(load("scenarios/bad-deploy.json"))
    assert ex.run(ROLLBACK).endswith("the alerts cleared")
    assert ex.run(Action(kind="restart", service="payments")).endswith("still firing")
    assert ex.run(Action(kind="rollback", service="inventory")).endswith("still firing")
