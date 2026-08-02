from collections import deque
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field


class ScriptedModel(BaseChatModel):
    responses: list[AIMessage] = Field(default_factory=list)
    bound_tool_names: list[str] = Field(default_factory=list)
    captured_messages: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted-test-model"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        del tool_choice, kwargs
        names: list[str] = []
        for item in tools:
            name = getattr(item, "name", None) or getattr(item, "__name__", None)
            names.append(str(name))
        self.bound_tool_names = names
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        self.captured_messages.append(list(messages))
        queue = deque(self.responses)
        if not queue:
            raise RuntimeError("ScriptedModel has no remaining responses")
        response = queue.popleft()
        self.responses = list(queue)
        return ChatResult(generations=[ChatGeneration(message=response)])
