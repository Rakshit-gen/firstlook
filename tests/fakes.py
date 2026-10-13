"""A scripted chat model, so the agent's tests never call an API.

`turns` are the AIMessages the model returns from plain calls (tool calls or
text); `answers` are dicts returned from structured-output calls.
"""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


def calls(*items) -> AIMessage:
    """An AIMessage asking for tools: calls(("query_metric", {...}), ...)."""
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call_{name}_{i}"}
            for i, (name, args) in enumerate(items)
        ],
    )


class Scripted(GenericFakeChatModel):
    answers: list = []
    seen: list = []

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, input, config=None, **kwargs):
        self.seen.append(list(input))
        return super().invoke(input, config, **kwargs)

    def with_structured_output(self, schema, **kwargs):
        def answer(msgs):
            self.seen.append(list(msgs))
            return schema(**self.answers.pop(0))

        return RunnableLambda(answer)


def scripted(turns, answers=()) -> Scripted:
    return Scripted(messages=iter(turns), answers=list(answers), seen=[])
