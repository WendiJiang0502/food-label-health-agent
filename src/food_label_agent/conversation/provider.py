"""OpenAI Responses API adapter for the consumer conversation agent."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_CONVERSATION_MODEL = "gpt-5.6-terra"


@dataclass(frozen=True, slots=True)
class ConversationSettings:
    provider: str = "openai"
    model: str = DEFAULT_CONVERSATION_MODEL
    reasoning_effort: str = "low"
    timeout_seconds: float = 20.0
    max_output_tokens: int = 1800
    max_tool_calls: int = 6
    base_url: str = RESPONSES_URL
    api_key: str | None = None

    @classmethod
    def from_environment(
        cls, source: Mapping[str, str] | None = None
    ) -> ConversationSettings:
        values = source if source is not None else os.environ
        provider = values.get("FOOD_LABEL_CHAT_PROVIDER", "openai").strip()
        if provider not in {"openai", "disabled"}:
            raise ValueError("FOOD_LABEL_CHAT_PROVIDER must be openai or disabled")
        effort = values.get("FOOD_LABEL_CHAT_REASONING_EFFORT", "low").strip()
        if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Unsupported conversation reasoning effort")
        timeout = float(values.get("FOOD_LABEL_CHAT_TIMEOUT_SECONDS", "20"))
        if not 1 <= timeout <= 60:
            raise ValueError("Conversation timeout must be between 1 and 60 seconds")
        max_output = int(values.get("FOOD_LABEL_CHAT_MAX_OUTPUT_TOKENS", "1800"))
        if not 256 <= max_output <= 8_000:
            raise ValueError("Conversation max output tokens must be 256 to 8000")
        max_tools = int(values.get("FOOD_LABEL_CHAT_MAX_TOOL_CALLS", "6"))
        if not 1 <= max_tools <= 8:
            raise ValueError("Conversation max tool calls must be 1 to 8")
        return cls(
            provider=provider,
            model=values.get(
                "FOOD_LABEL_CHAT_MODEL", DEFAULT_CONVERSATION_MODEL
            ).strip(),
            reasoning_effort=effort,
            timeout_seconds=timeout,
            max_output_tokens=max_output,
            max_tool_calls=max_tools,
            base_url=values.get("FOOD_LABEL_CHAT_BASE_URL", RESPONSES_URL).strip(),
            api_key=values.get("OPENAI_API_KEY") or None,
        )


@dataclass(frozen=True, slots=True)
class ProviderReply:
    text: str
    model: str
    response_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    tool_events: tuple[dict[str, Any], ...]


class ConversationProviderError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


ConversationTransport = Callable[[str, dict[str, str], dict[str, Any], float], dict]
ToolHandler = Callable[[str, dict[str, Any]], dict[str, Any]]


class OpenAIConversationProvider:
    provider = "openai"

    def __init__(
        self,
        settings: ConversationSettings | None = None,
        *,
        transport: ConversationTransport | None = None,
    ) -> None:
        self.settings = settings or ConversationSettings.from_environment()
        self._transport = transport or _post_json

    @property
    def configured(self) -> bool:
        return self.settings.provider == "openai" and bool(self.settings.api_key)

    def complete(
        self,
        *,
        instructions: str,
        messages: Sequence[dict[str, str]],
        tools: Sequence[dict[str, Any]],
        tool_handler: ToolHandler,
        safety_key: str,
    ) -> ProviderReply:
        if self.settings.provider == "disabled":
            raise ConversationProviderError("conversation_disabled")
        if not self.settings.api_key:
            raise ConversationProviderError("conversation_api_key_missing")
        input_items: list[dict[str, Any]] = [dict(item) for item in messages]
        tool_events: list[dict[str, Any]] = []
        total_input_tokens = 0
        total_output_tokens = 0
        for _step in range(self.settings.max_tool_calls + 1):
            payload = {
                "model": self.settings.model,
                "instructions": instructions,
                "input": input_items,
                "reasoning": {"effort": self.settings.reasoning_effort},
                "text": {"verbosity": "medium"},
                "max_output_tokens": self.settings.max_output_tokens,
                "store": False,
                "safety_identifier": _safety_identifier(safety_key),
            }
            if tools:
                payload.update(
                    {
                        "tools": list(tools),
                        "tool_choice": "auto",
                        "parallel_tool_calls": False,
                    }
                )
            response = self._request(payload)
            usage = response.get("usage") or {}
            total_input_tokens += _int_or_zero(usage.get("input_tokens"))
            total_output_tokens += _int_or_zero(usage.get("output_tokens"))
            if response.get("status") != "completed":
                raise ConversationProviderError(
                    "conversation_response_incomplete", retryable=True
                )
            function_calls = [
                item
                for item in response.get("output", [])
                if item.get("type") == "function_call"
            ]
            if not function_calls:
                text = _response_output_text(response)
                return ProviderReply(
                    text=text,
                    model=str(response.get("model") or self.settings.model),
                    response_id=response.get("id"),
                    input_tokens=total_input_tokens or None,
                    output_tokens=total_output_tokens or None,
                    tool_events=tuple(tool_events),
                )
            if len(tool_events) + len(function_calls) > self.settings.max_tool_calls:
                raise ConversationProviderError("conversation_tool_budget_exhausted")
            input_items.extend(response.get("output", []))
            for call in function_calls:
                name = str(call.get("name") or "")
                try:
                    arguments = json.loads(call.get("arguments") or "{}")
                    if not isinstance(arguments, dict):
                        raise TypeError
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ConversationProviderError(
                        "conversation_tool_arguments_invalid"
                    ) from exc
                result = tool_handler(name, arguments)
                tool_events.append(
                    {
                        "name": name,
                        "status": str(result.get("status") or "completed"),
                    }
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.get("call_id"),
                        "output": json.dumps(
                            result,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    }
                )
        raise ConversationProviderError("conversation_tool_budget_exhausted")

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        try:
            return self._transport(
                self.settings.base_url,
                headers,
                payload,
                self.settings.timeout_seconds,
            )
        except ConversationProviderError:
            raise
        except Exception as exc:
            raise ConversationProviderError(
                "conversation_provider_unavailable", retryable=True
            ) from exc


def conversation_public_status(
    settings: ConversationSettings | None = None,
) -> dict[str, Any]:
    configured = settings or ConversationSettings.from_environment()
    return {
        "provider": configured.provider,
        "model": configured.model if configured.provider == "openai" else None,
        "configured": configured.provider == "openai" and bool(configured.api_key),
        "remote_processing": configured.provider == "openai",
        "store": False,
        "max_tool_calls": configured.max_tool_calls,
    }


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        retryable = exc.code in {408, 409, 429, 500, 502, 503, 504}
        raise ConversationProviderError(
            f"conversation_provider_http_{exc.code}", retryable=retryable
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ConversationProviderError(
            "conversation_provider_unavailable", retryable=True
        ) from exc


def _response_output_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "refusal":
                raise ConversationProviderError("conversation_model_refused")
            if content.get("type") == "output_text":
                parts.append(str(content.get("text") or ""))
    text = "".join(parts).strip()
    if not text:
        raise ConversationProviderError("conversation_response_missing_output")
    return text


def _safety_identifier(value: str) -> str:
    digest = hashlib.sha256(value.encode()).hexdigest()[:40]
    return f"food-label-chat-{digest}"


def _int_or_zero(value: Any) -> int:
    return int(value) if isinstance(value, int | float) else 0
