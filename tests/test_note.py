from fakes import calls, scripted
from langchain_core.messages import AIMessage
from langgraph.types import Command
from test_agent import ENV, GOOD

from firstlook.agent import build_agent, memory
from firstlook.note import incident_note


def run(approved=None):
    model = scripted([calls(("recent_deploys", {"minutes": 90})), AIMessage("deploy")], [GOOD])
    app = build_agent(model, ENV, checkpointer=memory())
    cfg = {"configurable": {"thread_id": "n"}}
    app.invoke({}, cfg)
    if approved is not None:
        app.invoke(Command(resume={"approved": approved, "by": "sam"}), cfg)
    return incident_note(app.get_state(cfg).values, ENV, "Checkout failing")


def test_note_while_waiting():
    note = run()
    assert note.startswith("# Checkout failing\n\nFirst look at 2026-10-01 16:00 UTC.")
    assert "- Where it starts: **payments**" in note
    assert "- `14:58 UTC payments v2.14.0`" in note
    assert "Proposed: roll back payments (previous version).\nWaiting for approval." in note
    assert "- 14:58 deploy payments v2.14.0" in note
    assert "## How the agent got there (1 tool call)\n\n1. `recent_deploys(minutes=90)`" in note


def test_note_after_approval():
    note = run(approved=True)
    assert "Approved by sam.\nResult: dry run: would roll back payments" in note
    assert "Waiting" not in note
