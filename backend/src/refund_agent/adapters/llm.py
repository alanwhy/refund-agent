import json
import re
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from refund_agent.config import get_settings
from refund_agent.domain.enums import TicketIntent


@dataclass(frozen=True)
class Classification:
    intent: TicketIntent
    order_number: str | None
    confidence: float


class LLMClient:
    def classify(self, text: str) -> Classification:
        raise NotImplementedError


class FakeLLMClient(LLMClient):
    def classify(self, text: str) -> Classification:
        normalized = text.lower()
        if "换" in text or "exchange" in normalized:
            intent = TicketIntent.EXCHANGE
        elif "异常" in text or "破损" in text or "exception" in normalized:
            intent = TicketIntent.EXCEPTION
        elif "退" in text or "refund" in normalized:
            intent = TicketIntent.REFUND
        else:
            intent = TicketIntent.CONSULTATION
        match = re.search(r"ORD-[A-Z0-9-]+", text.upper())
        return Classification(intent, match.group(0) if match else None, 0.98)


class OpenAICompatibleClient(LLMClient):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key or not settings.openai_model:
            raise ValueError("Compatible LLM mode requires OPENAI_API_KEY and OPENAI_MODEL")
        self.model = settings.openai_model
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=15,
            max_retries=2,
        )

    def classify(self, text: str) -> Classification:
        settings = get_settings()
        prompt_path = settings.prompts_dir / "classifier.md"
        if not prompt_path.exists():
            prompt_path = Path(__file__).resolve().parents[3] / "prompts" / "classifier.md"
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        prompt_path.read_text(encoding="utf-8") + "\nReturn JSON with intent "
                        "(REFUND, EXCHANGE, EXCEPTION, CONSULTATION), order_number, confidence. "
                    ),
                },
                {"role": "user", "content": f"<untrusted_user_input>{text}</untrusted_user_input>"},
            ],
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        return Classification(
            TicketIntent(payload["intent"]),
            payload.get("order_number"),
            float(payload["confidence"]),
        )


def get_llm_client() -> LLMClient:
    return OpenAICompatibleClient() if get_settings().llm_mode == "compatible" else FakeLLMClient()
