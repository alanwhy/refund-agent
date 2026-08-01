import pytest
from pydantic import SecretStr

from refund_agent.config import Settings


def test_model_configuration_is_required() -> None:
    settings = Settings(
        _env_file=None,
        llm_base_url=None,
        llm_api_key=None,
        llm_model=None,
    )
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        settings.require_model_config()


def test_model_secret_is_not_exposed_in_repr() -> None:
    settings = Settings(
        _env_file=None,
        llm_base_url="https://gateway.example/v1",
        llm_api_key=SecretStr("highly-secret"),
        llm_model="gpt-test",
    )
    assert settings.require_model_config() == (
        "https://gateway.example/v1",
        "highly-secret",
        "gpt-test",
    )
    assert "highly-secret" not in repr(settings)
