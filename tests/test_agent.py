from fakes import scripted

from firstlook.agent import build_agent
from firstlook.env import ScenarioEnv
from firstlook.scenario import load

ENV = ScenarioEnv(load("scenarios/bad-deploy.json"))


def test_intake_briefs_the_model_with_the_alerts():
    out = build_agent(scripted([]), ENV).invoke({})
    system, human = out["messages"]
    assert "first responder" in system.content
    assert human.content.startswith("It is 2026-10-01 16:00 UTC. You've been paged.")
    assert "HighErrorRate on checkout" in human.content
