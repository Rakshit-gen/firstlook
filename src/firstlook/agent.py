"""The incident agent as a LangGraph graph."""

from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from .env import Env
from .prompts import SYSTEM, brief


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

    g = StateGraph(State)
    g.add_node("intake", intake)
    g.add_edge(START, "intake")
    g.add_edge("intake", END)
    return g.compile(checkpointer=checkpointer)
