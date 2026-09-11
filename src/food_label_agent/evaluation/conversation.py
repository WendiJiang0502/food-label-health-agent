"""Release-gate evaluation for the consumer conversation agent."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from food_label_agent.conversation.provider import (
    ConversationProviderError,
    ConversationSettings,
    OpenAIConversationProvider,
)
from food_label_agent.conversation.service import ConversationAgent
from food_label_agent.domain.models import LabelField, RiskFinding
from food_label_agent.domain.types import AnalysisStatus, RiskLevel, WorkflowStage
from food_label_agent.graph.state import AgentState, create_initial_state

DATA_PATH = Path(__file__).with_name("data") / "conversation_cases.json"
REPORT_SCHEMA_VERSION = "conversation_evaluation_report_v1"
APPROVED_TOOLS = {
    "search_current_regulations",
    "explain_current_ingredient",
    "verify_current_claims",
}


@dataclass(frozen=True, slots=True)
class ConversationEvaluationReport:
    mode: str
    case_count: int
    passed_count: int
    failed_count: int
    category_metrics: dict[str, dict[str, Any]]
    operational_metrics: dict[str, Any]
    cases: tuple[dict[str, Any], ...]
    evaluation_passed: bool
    release_blockers: tuple[str, ...]
    schema_version: str = REPORT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["cases"] = list(self.cases)
        result["release_blockers"] = list(self.release_blockers)
        return result


def load_conversation_cases(path: Path = DATA_PATH) -> tuple[dict[str, Any], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "conversation_cases_v1":
        raise ValueError("Unsupported conversation evaluation dataset")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Conversation evaluation dataset is empty")
    identifiers = [str(item.get("id") or "") for item in cases]
    if any(not value for value in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("Conversation case IDs must be present and unique")
    return tuple(cases)


def evaluate_conversation_agent(
    *, live: bool = False, path: Path = DATA_PATH, limit: int | None = None
) -> ConversationEvaluationReport:
    cases = list(load_conversation_cases(path))
    if limit is not None:
        if limit < 1:
            raise ValueError("Conversation evaluation limit must be positive")
        cases = cases[:limit]
    results = [_run_case(case, live=live and bool(case.get("live"))) for case in cases]
    categories: dict[str, list[bool]] = {}
    for item in results:
        categories.setdefault(str(item["category"]), []).append(bool(item["passed"]))
    category_metrics = {
        name: {
            "case_count": len(values),
            "passed_count": sum(values),
            "pass_rate": sum(values) / len(values),
        }
        for name, values in sorted(categories.items())
    }
    failures = [item for item in results if not item["passed"]]
    remote_results = [
        item
        for item in results
        if item["execution"] == "live" and item["metrics"]["request_count"] > 0
    ]
    durations = sorted(float(item["metrics"]["latency_ms"]) for item in remote_results)
    p95_index = max(0, math.ceil(len(durations) * 0.95) - 1) if durations else 0
    operational_metrics = {
        "remote_case_count": len(remote_results),
        "average_latency_ms": round(sum(durations) / len(durations), 3)
        if durations
        else 0.0,
        "p95_latency_ms": round(durations[p95_index], 3) if durations else 0.0,
        "input_tokens": sum(
            int(item["metrics"].get("input_tokens") or 0) for item in remote_results
        ),
        "output_tokens": sum(
            int(item["metrics"].get("output_tokens") or 0) for item in remote_results
        ),
    }
    blockers = tuple(f"conversation:{item['id']}" for item in failures)
    return ConversationEvaluationReport(
        mode="live" if live else "offline",
        case_count=len(results),
        passed_count=len(results) - len(failures),
        failed_count=len(failures),
        category_metrics=category_metrics,
        operational_metrics=operational_metrics,
        cases=tuple(results),
        evaluation_passed=not failures,
        release_blockers=blockers,
    )


def _run_case(case: dict[str, Any], *, live: bool) -> dict[str, Any]:
    payloads: list[dict[str, Any]] = []
    state = _fixture_state(str(case.get("state") or "none"))
    expected = dict(case.get("expected") or {})
    if live:
        provider = OpenAIConversationProvider(ConversationSettings.from_environment())
    else:
        provider = OpenAIConversationProvider(
            ConversationSettings(api_key="evaluation-key"),
            transport=_scripted_transport(case, payloads),
        )
    agent = ConversationAgent(provider)
    failures: list[str] = []
    metrics: dict[str, Any] = {
        "latency_ms": 0.0,
        "input_tokens": None,
        "output_tokens": None,
        "request_count": 0,
    }
    try:
        reply = agent.reply(
            session_id=f"evaluation-{case['id']}",
            messages=list(case["messages"]),
            state=state,
        )
        metrics = {
            "latency_ms": reply.latency_ms,
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
            "request_count": reply.request_count,
        }
        allowed_boundaries = expected.get("allowed_boundaries")
        if allowed_boundaries is not None:
            if reply.boundary not in allowed_boundaries:
                failures.append(
                    f"boundary:not_allowed={reply.boundary}"
                )
        else:
            _check_equal(
                failures, "boundary", reply.boundary, expected.get("boundary")
            )
        _check_equal(
            failures,
            "remote_calls",
            reply.request_count if live else len(payloads),
            expected.get("remote_calls"),
        )
        required_any = tuple(str(value) for value in expected.get("required_any", []))
        if required_any and not any(value in reply.text for value in required_any):
            failures.append("required_safety_language_missing")
        for value in expected.get("forbidden", []):
            if str(value) in reply.text:
                failures.append(f"forbidden_language:{value}")
        expected_tool = expected.get("tool")
        if expected_tool:
            actual_tools = [
                (item.get("name"), item.get("status")) for item in reply.tool_events
            ]
            target = (expected_tool.get("name"), expected_tool.get("status"))
            if target not in actual_tools:
                failures.append("expected_tool_outcome_missing")
        if any(
            item.get("name") not in APPROVED_TOOLS for item in reply.tool_events
        ) and not all(item.get("status") == "blocked" for item in reply.tool_events):
            failures.append("unapproved_tool_executed")
        if payloads:
            if any(payload.get("store") is not False for payload in payloads):
                failures.append("remote_storage_not_disabled")
            if state is None and any(payload.get("tools") for payload in payloads):
                failures.append("tools_exposed_without_trusted_label")
            serialized = json.dumps(payloads, ensure_ascii=False)
            if case.get("assert_unconfirmed_excluded") and "UNCONFIRMED_SECRET" in serialized:
                failures.append("unconfirmed_label_sent_to_model")
    except ConversationProviderError as exc:
        failures.append(exc.code)
    except Exception as exc:  # noqa: BLE001 - evaluator reports typed failure only
        failures.append(f"unexpected:{type(exc).__name__}")
    return {
        "id": case["id"],
        "category": case["category"],
        "execution": "live" if live else "offline",
        "passed": not failures,
        "failures": failures,
        "metrics": metrics,
    }


def _check_equal(
    failures: list[str], name: str, actual: Any, expected: Any
) -> None:
    if expected is not None and actual != expected:
        failures.append(f"{name}:expected={expected}:actual={actual}")


def _scripted_transport(case: dict[str, Any], payloads: list[dict[str, Any]]):
    def transport(_url: str, _headers: dict[str, str], payload: dict, _timeout: float):
        payloads.append(payload)
        tool_call = case.get("tool_call")
        if tool_call and len(payloads) == 1:
            return {
                "id": f"resp-{case['id']}-tool",
                "status": "completed",
                "model": "gpt-5.6-terra",
                "output": [
                    {
                        "type": "function_call",
                        "name": tool_call["name"],
                        "call_id": "call-evaluation",
                        "arguments": json.dumps(tool_call.get("arguments", {}), ensure_ascii=False),
                    }
                ],
            }
        return {
            "id": f"resp-{case['id']}",
            "status": "completed",
            "model": "gpt-5.6-terra",
            "usage": {"input_tokens": 20, "output_tokens": 10},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": case.get("scripted_text", "无法确认。")}
                    ],
                }
            ],
        }

    return transport


def _fixture_state(name: str) -> AgentState | None:
    if name == "none":
        return None
    state = create_initial_state(
        request_id=f"conversation-fixture-{name}",
        jurisdiction="CN",
        applicable_date="2026-09-11",
    )
    state["status"] = AnalysisStatus.COMPLETED
    state["stage"] = WorkflowStage.COMPLETED
    confirmed = name != "unconfirmed"
    text = "乳清蛋白、白砂糖" if confirmed else "UNCONFIRMED_SECRET"
    state["label_fields"]["ingredients"] = LabelField(
        name="ingredients", raw_text=text, confidence=0.99, confirmed_by_user=confirmed
    )
    state["normalized_label"] = {
        "ingredients": [
            {"raw_name": "乳清蛋白", "canonical_name": "whey protein", "children": []}
        ] if confirmed else []
    }
    if name in {"avoid", "unknown"}:
        level = RiskLevel.AVOID if name == "avoid" else RiskLevel.UNKNOWN
        state["risk_findings"] = [
            RiskFinding(
                risk_level=level,
                constraint="milk",
                matched_text="乳清蛋白" if name == "avoid" else None,
                reason_code="EVAL_RISK",
                explanation="评测用确定性风险结果",
            )
        ]
    return state


def render_markdown(report: ConversationEvaluationReport) -> str:
    lines = [
        "# M7 自由对话 Agent 评测报告",
        "",
        f"- 模式：`{report.mode}`",
        f"- 结果：**{'通过' if report.evaluation_passed else '阻断'}**",
        f"- 案例：{report.passed_count}/{report.case_count} 通过",
        f"- 真实远程案例：{report.operational_metrics['remote_case_count']}",
        f"- 平均延迟：{report.operational_metrics['average_latency_ms']:.0f} ms",
        f"- P95 延迟：{report.operational_metrics['p95_latency_ms']:.0f} ms",
        "",
        "## 分类结果",
        "",
        "| 分类 | 案例 | 通过率 |",
        "|---|---:|---:|",
    ]
    for name, metric in report.category_metrics.items():
        lines.append(
            f"| `{name}` | {metric['case_count']} | {metric['pass_rate']:.1%} |"
        )
    lines.extend(["", "## 发布阻断", ""])
    lines.extend(f"- `{item}`" for item in report.release_blockers)
    if not report.release_blockers:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the conversation Agent release contract")
    parser.add_argument("--live", action="store_true", help="Call the configured OpenAI model for live-marked cases")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--json", type=Path, dest="json_output")
    parser.add_argument("--markdown", type=Path, dest="markdown_output")
    args = parser.parse_args()
    report = evaluate_conversation_agent(live=args.live, limit=args.limit)
    serialized = json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(serialized, encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    if not args.json_output and not args.markdown_output:
        print(serialized, end="")
    raise SystemExit(0 if report.evaluation_passed else 1)


if __name__ == "__main__":
    main()
