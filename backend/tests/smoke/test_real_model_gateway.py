import os

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from refund_agent.adapters.llm import build_chat_model
from refund_agent.agent.schemas import RequestUserInput, SubmitRefundContext
from refund_agent.agent.tools import READ_TOOLS

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_MODEL_SMOKE") != "1",
    reason="set RUN_REAL_MODEL_SMOKE=1 to call the configured gateway",
)


def test_configured_model_returns_a_refund_agent_tool_call() -> None:
    model = build_chat_model().bind_tools(
        [*READ_TOOLS, RequestUserInput, SubmitRefundContext]
    )
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    "You are a refund assistant. Always use one provided tool. "
                    "The user has not provided an order number, so request it."
                )
            ),
            HumanMessage(content="我想退款"),
        ]
    )

    assert response.tool_calls
    assert response.tool_calls[0]["name"] in {
        tool.name for tool in READ_TOOLS
    } | {RequestUserInput.__name__, SubmitRefundContext.__name__}
