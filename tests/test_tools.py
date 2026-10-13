from firstlook.env import ScenarioEnv
from firstlook.scenario import load
from firstlook.tools import make_tools

TOOLS = {t.name: t for t in make_tools(ScenarioEnv(load("scenarios/bad-deploy.json")))}


def call(name, **args):
    return TOOLS[name].invoke(args)


def test_list_alerts():
    out = call("list_alerts").splitlines()
    assert out[0].startswith("HighErrorRate on checkout")
    assert out[-1] == "Services: checkout, inventory, payments, payments-db, web"
