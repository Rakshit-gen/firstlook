"""The incident agent as a LangGraph graph."""

from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .env import Env
from .prompts import SYSTEM, brief
from .tools import make_tools


class State(TypedDict, total=False):
    messages: Annotated[list, add_messages]


def build_agent(model, env: Env, checkpointer=None):
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
        return "tools" if state["messages"][-1].tool_calls else END

    g = StateGraph(State)
    g.add_node("intake", intake)
    g.add_node("investigate", investigate)
    g.add_node("tools", ToolNode(tools))
    g.add_edge(START, "intake")
    g.add_edge("intake", "investigate")
    g.add_conditional_edges("investigate", route, ["tools", END])
    g.add_edge("tools", "investigate")
    return g.compile(checkpointer=checkpointer)
