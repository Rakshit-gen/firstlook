"""The tools the agent can call. Each returns a short plain-text answer: the
model reads text, and short answers keep the context small."""

from langchain_core.tools import tool

from .env import Env


def make_tools(env: Env) -> list:
    @tool
    def list_alerts() -> str:
        """List the alerts that are firing, oldest first, with the system's services."""
        alerts = env.alerts()
        lines = [a.describe() for a in alerts] or ["No alerts firing."]
        lines.append("Services: " + ", ".join(env.services()))
        return "\n".join(lines)

    return [list_alerts]
