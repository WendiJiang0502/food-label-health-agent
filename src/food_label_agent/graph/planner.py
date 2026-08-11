"""Model-assisted action proposals behind a deterministic policy boundary."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_PLANNER_MODEL = "gpt-5.6-terra"


@dataclass(frozen=True, slots=True)
class PlannerSettings:
    provider: str = "deterministic"
    model: str = DEFAULT_PLANNER_MODEL
    timeout_seconds: float = 8.0
    reasoning_effort: str = "low"
    base_url: str = OPENAI_RESPONSES_URL
    api_key: str | None = None

    @classmethod
    def from_environment(
        cls, source: Mapping[str, str] | None = None
    ) -> PlannerSettings:
        values = source if source is not None else os.environ
        provider = values.get("FOOD_LABEL_PLANNER_PROVIDER", "deterministic").strip()
        if provider not in {"deterministic", "openai"}:
            raise ValueError(
                "FOOD_LABEL_PLANNER_PROVIDER must be deterministic or openai"
            )
        effort = values.get("FOOD_LABEL_PLANNER_REASONING_EFFORT", "low").strip()
        if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Unsupported planner reasoning effort")
        timeout = float(values.get("FOOD_LABEL_PLANNER_TIMEOUT_SECONDS", "8"))
        if not 0.5 <= timeout <= 60:
            raise ValueError("Planner timeout must be between 0.5 and 60 seconds")
        return cls(
            provider=provider,
            model=values.get("FOOD_LABEL_PLANNER_MODEL", DEFAULT_PLANNER_MODEL).strip(),
            timeout_seconds=timeout,
            reasoning_effort=effort,
            base_url=values.get(
                "FOOD_LABEL_PLANNER_BASE_URL", OPENAI_RESPONSES_URL
            ).strip(),
            api_key=values.get("OPENAI_API_KEY") or None,
        )


@dataclass(frozen=True, slots=True)
class PlannerProposal:
    action_id: str
    provider: str
    model: str
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class ActionProposer(Protocol):
    provider: str
    model: str

    def propose(
        self,
        *,
        context: dict[str, Any],
        candidates: Sequence[dict[str, str]],
    ) -> PlannerProposal: ...


class ModelPlannerError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


PlannerTransport = Callable[[str, dict[str, str], dict[str, Any], float], dict]


class OpenAIActionProposer:
    """Ask an OpenAI model to select one policy-generated action ID only."""

    provider = "openai"

    def __init__(
        self,
        settings: PlannerSettings,
        *,
        transport: PlannerTransport | None = None,
    ) -> None:
        self.settings = settings
        self.model = settings.model
        self._transport = transport or _post_json

    def propose(
        self,
        *,
        context: dict[str, Any],
        candidates: Sequence[dict[str, str]],
    ) -> PlannerProposal:
        if not candidates:
            raise ModelPlannerError("planner_has_no_candidate_actions")
        if not self.settings.api_key:
            raise ModelPlannerError("planner_api_key_missing")
        action_ids = [item["action_id"] for item in candidates]
        payload = {
            "model": self.settings.model,
            "instructions": (
                "Select exactly one next evidence-gathering action from the supplied "
                "candidate action IDs. Do not diagnose, change risk levels, invent an "
                "action, or generate tool arguments. Return only the required JSON."
            ),
            "input": json.dumps(
                {"context": context, "candidate_actions": list(candidates)},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "reasoning": {"effort": self.settings.reasoning_effort},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "food_label_planner_action",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "action_id": {"type": "string", "enum": action_ids}
                        },
                        "required": ["action_id"],
                        "additionalProperties": False,
                    },
                }
            },
            "max_output_tokens": 128,
            "store": False,
            "safety_identifier": _safety_identifier(context),
        }
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = self._transport(
                self.settings.base_url,
                headers,
                payload,
                self.settings.timeout_seconds,
            )
        except ModelPlannerError:
            raise
        except Exception as exc:
            raise ModelPlannerError(
                "planner_provider_unavailable", retryable=True
            ) from exc
        if response.get("status") != "completed":
            raise ModelPlannerError("planner_response_incomplete", retryable=True)
        output_text = _response_output_text(response)
        try:
            parsed = json.loads(output_text)
            action_id = str(parsed["action_id"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ModelPlannerError("planner_response_invalid") from exc
        usage = response.get("usage") or {}
        return PlannerProposal(
            action_id=action_id,
            provider=self.provider,
            model=str(response.get("model") or self.model),
            response_id=response.get("id"),
            input_tokens=_optional_int(usage.get("input_tokens")),
            output_tokens=_optional_int(usage.get("output_tokens")),
        )


def create_action_proposer(
    settings: PlannerSettings | None = None,
) -> ActionProposer | None:
    configured = settings or PlannerSettings.from_environment()
    if configured.provider == "deterministic":
        return None
    return OpenAIActionProposer(configured)


def planner_public_status(
    settings: PlannerSettings | None = None,
) -> dict[str, Any]:
    configured = settings or PlannerSettings.from_environment()
    return {
        "provider": configured.provider,
        "model": configured.model if configured.provider != "deterministic" else None,
        "configured": (
            configured.provider == "deterministic" or bool(configured.api_key)
        ),
        "remote_processing": configured.provider == "openai",
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
        raise ModelPlannerError(
            f"planner_provider_http_{exc.code}", retryable=retryable
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ModelPlannerError("planner_provider_unavailable", retryable=True) from exc


def _response_output_text(response: dict[str, Any]) -> str:
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "refusal":
                raise ModelPlannerError("planner_model_refused")
            if content.get("type") == "output_text":
                return str(content.get("text", ""))
    raise ModelPlannerError("planner_response_missing_output")


def _safety_identifier(context: dict[str, Any]) -> str:
    request_id = str(context.get("task", {}).get("request_id", "anonymous"))
    return "food-label-" + hashlib.sha256(request_id.encode()).hexdigest()[:32]


def _optional_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) else None
