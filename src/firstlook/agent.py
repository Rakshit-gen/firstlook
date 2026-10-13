"""The incident agent as a LangGraph graph."""

from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .env import Env
from .prompts import SYSTEM, brief
from .tools import make_tools


class State(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    tool_calls: int  # tool calls made so far
    notes: list[str]  # things the run should report about itself


MAX_TOOL_CALLS = 12


def build_agent(model, env: Env, checkpointer=None, max_tool_calls: int = MAX_TOOL_CALLS):
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
    g.add_node("tools", ToolNode(tools))
    g.add_node("over_budget", over_budget)
    g.add_edge(START, "intake")
    g.add_edge("intake", "investigate")
    g.add_conditional_edges(
        "investigate", route, {"tools": "count", "over_budget": "over_budget", END: END}
    )
    g.add_edge("count", "tools")
    g.add_edge("tools", "investigate")
    g.add_edge("over_budget", END)
    return g.compile(checkpointer=checkpointer)
