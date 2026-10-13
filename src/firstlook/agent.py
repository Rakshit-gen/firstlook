"""The incident agent as a LangGraph graph."""

import json
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from .checks import check_finding
from .env import Env
from .executor import DryRun, Executor
from .finding import Finding
from .prompts import CONCLUDE, SYSTEM, brief
from .tools import make_tools


class State(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    tool_calls: int  # tool calls made so far
    notes: list[str]  # things the run should report about itself
    finding: Finding
    approved: bool  # a person's answer to the proposed action
    approver: str
    result: str  # what the executor reported


MAX_TOOL_CALLS = 12


def build_agent(
    model,
    env: Env,
    checkpointer=None,
    max_tool_calls: int = MAX_TOOL_CALLS,
    executor: Executor | None = None,
):
    executor = executor or DryRun()

    def intake(state: State):
        alerts = "\n".join(a.describe() for a in env.alerts()) or "No alerts firing."
        return {
            "messages": [
                SystemMessage(SYSTEM),
                HumanMessage(brief(alerts, f"{env.now:%Y-%m-%d %H:%M}")),
            ]
        }

    tools = make_tools(env)
    with_tools = model.bind_tools(tools)

    def investigate(state: State):
        return {"messages": [with_tools.invoke(state["messages"])]}

    def route(state: State):
        pending = state["messages"][-1].tool_calls
        if not pending:
            return END
        if state.get("tool_calls", 0) + len(pending) > max_tool_calls:
            return "over_budget"
        return "tools"

    def count(state: State):
        return {"tool_calls": state.get("tool_calls", 0) + len(state["messages"][-1].tool_calls)}

    runner = ToolNode(tools)

    def key(call) -> str:
        return call["name"] + json.dumps(call["args"], sort_keys=True)

    def run_tools(state: State):
        """Run the requested tools, but not ones already asked with the same
        arguments: the answer hasn't changed, and models do get stuck asking."""
        *earlier, last = state["messages"]
        asked = {key(c) for m in earlier if isinstance(m, AIMessage) for c in m.tool_calls}
        fresh = [c for c in last.tool_calls if key(c) not in asked]
        out = [
            ToolMessage(
                "You already made this exact call; its answer is above. Try something else.",
                tool_call_id=c["id"],
                name=c["name"],
            )
            for c in last.tool_calls
            if key(c) in asked
        ]
        if fresh:
            out += runner.invoke({"messages": [AIMessage("", tool_calls=fresh)]})["messages"]
        return {"messages": out}

    concluder = model.with_structured_output(Finding).with_retry(stop_after_attempt=3)

    def conclude(state: State):
        raw = concluder.invoke([*state["messages"], HumanMessage(CONCLUDE)])
        answers = [m.content for m in state["messages"] if isinstance(m, ToolMessage)]
        finding, notes = check_finding(raw, answers, env.services())
        return {"finding": finding, "notes": [*state.get("notes", []), *notes]}

    def needs_approval(state: State):
        return "approve" if state["finding"].action.kind not in ("escalate", "none") else END

    def approve(state: State):
        """Nothing changes in production without a person saying yes. The graph
        stops here; it resumes with {"approved": bool, "by": name}."""
        f = state["finding"]
        answer = interrupt(
            {
                "action": f.action.model_dump(),
                "service": f.service,
                "cause": f.cause,
                "summary": f.summary,
                "confidence": f.confidence,
                "evidence": f.evidence,
            }
        )
        if not isinstance(answer, dict) or not isinstance(answer.get("approved"), bool):
            raise ValueError('resume with {"approved": true or false, "by": "name"}')
        return {"approved": answer["approved"], "approver": str(answer.get("by", "unknown"))}

    def act(state: State):
        if not state["approved"]:
            return {"result": f"not done: {state['approver']} declined"}
        return {"result": executor.run(state["finding"].action)}

    def over_budget(state: State):
        # Every tool call needs an answer, or the next model call is rejected.
        pending = state["messages"][-1].tool_calls
        skipped = [
            ToolMessage(
                f"Not run: the budget of {max_tool_calls} tool calls is used up.",
                tool_call_id=c["id"],
                name=c["name"],
            )
            for c in pending
        ]
        note = f"stopped investigating at the budget of {max_tool_calls} tool calls"
        return {"messages": skipped, "notes": [*state.get("notes", []), note]}

    g = StateGraph(State)
    g.add_node("intake", intake)
    g.add_node("investigate", investigate)
    g.add_node("count", count)
    g.add_node("tools", run_tools)
    g.add_node("over_budget", over_budget)
    g.add_edge(START, "intake")
    g.add_edge("intake", "investigate")
    g.add_conditional_edges(
        "investigate", route, {"tools": "count", "over_budget": "over_budget", END: "conclude"}
    )
    g.add_edge("count", "tools")
    g.add_edge("tools", "investigate")
    g.add_node("conclude", conclude)
    g.add_edge("over_budget", "conclude")
    g.add_node("approve", approve)
    g.add_conditional_edges("conclude", needs_approval, ["approve", END])
    g.add_node("act", act)
    g.add_edge("approve", "act")
    g.add_edge("act", END)
    return g.compile(checkpointer=checkpointer)
