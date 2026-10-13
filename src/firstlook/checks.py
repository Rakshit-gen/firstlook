"""Hold the model's conclusion to what the tools actually returned."""

import re

from .finding import Action, Finding


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def check_finding(f: Finding, tool_answers: list[str], services: list[str]):
    """Returns (corrected finding, notes). Quotes that no tool returned are
    dropped. A finding with no real evidence, or about a service that doesn't
    exist, is not acted on: it becomes an escalation with low confidence."""
    notes = []
    corpus = _norm("\n".join(tool_answers))
    real = [q for q in f.evidence if q.strip() and _norm(q) in corpus]
    fake = [q for q in f.evidence if q not in real]
    if fake:
        notes.append("evidence not found in any tool answer: " + "; ".join(repr(q) for q in fake))
    update = {"evidence": real}
    if f.service not in services:
        notes.append(f"{f.service!r} is not a service in this system")
    if not real or f.service not in services:
        if f.action.kind not in ("escalate", "none"):
            notes.append(f"not acting on it: {f.action.kind} on {f.action.service} needs evidence")
        update["confidence"] = "low"
        update["action"] = Action(kind="escalate", service=f.action.service, detail="")
    elif f.action.service not in services:
        notes.append(f"the action names {f.action.service!r}, which is not a service")
        update["action"] = Action(kind="escalate", service=f.service, detail="")
    return f.model_copy(update=update), notes
