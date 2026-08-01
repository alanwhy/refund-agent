from typing import Any

from pydantic import SecretStr

from refund_agent.adapters import llm
from refund_agent.config import Settings


def test_gateway_configuration_is_passed_to_openai_compatible_client(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, Any] = {}
    sentinel = object()

    def fake_client(**kwargs: Any) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(llm, "ChatOpenAI", fake_client)
    settings = Settings(
        _env_file=None,
        llm_base_url="https://gateway.example/v1",
        llm_api_key=SecretStr("test-secret"),
        llm_model="provider/model-name",
        llm_timeout_seconds=12,
        llm_max_retries=1,
    )

    assert llm.build_chat_model(settings) is sentinel
    assert captured == {
        "model": "provider/model-name",
        "base_url": "https://gateway.example/v1",
        "api_key": "test-secret",
        "timeout": 12,
        "max_retries": 1,
        "temperature": 0,
    }
