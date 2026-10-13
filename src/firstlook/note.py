"""The incident note: what a person reads when they pick the incident up."""

from langchain_core.messages import AIMessage

from .env import Env
from .executor import describe
from .timeline import timeline


def tool_trail(messages) -> list[str]:
    out = []
    for m in messages:
        if isinstance(m, AIMessage):
            for c in m.tool_calls:
                args = ", ".join(f"{k}={v!r}" for k, v in c["args"].items())
                out.append(f"{c['name']}({args})")
    return out


def incident_note(state: dict, env: Env, title: str = "Incident") -> str:
    f = state.get("finding")
    out = [f"# {title}", "", f"First look at {env.now:%Y-%m-%d %H:%M} UTC.", ""]
    if f is None:
        out.append("No conclusion was reached.")
    else:
        out += [
            "## What happened",
            "",
            f.summary,
            "",
            f"- Where it starts: **{f.service}**",
            f"- Cause: {f.cause} ({f.confidence} confidence)",
            "",
            "## Evidence",
            "",
        ]
        out += [f"- `{q}`" for q in f.evidence] or ["- none that checks out"]
        out += ["", "## Action", ""]
        if f.action.kind in ("escalate", "none"):
            out.append(f"{f.action.kind}: needs a person.")
        else:
            out.append(f"Proposed: {describe(f.action)}.")
            if "approved" in state:
                verdict = "approved" if state["approved"] else "declined"
                out.append(f"{verdict.capitalize()} by {state.get('approver', 'unknown')}.")
            if state.get("result"):
                out.append(f"Result: {state['result']}.")
            if "approved" not in state:
                # Without messages this is the rules baseline, which only proposes.
                out.append("Waiting for approval." if state.get("messages") else "Not carried out.")
    out += ["", "## Timeline", ""]
    out += [f"- {t:%H:%M} {text}" for t, text in timeline(env)]
    if state.get("messages"):
        trail = tool_trail(state["messages"])
        noun = "tool call" if len(trail) == 1 else "tool calls"
        out += ["", f"## How the agent got there ({len(trail)} {noun})", ""]
        out += [f"{i}. `{call}`" for i, call in enumerate(trail, 1)]
    if state.get("notes"):
        out += ["", "## Notes", ""] + [f"- {n}" for n in state["notes"]]
    return "\n".join(out) + "\n"
