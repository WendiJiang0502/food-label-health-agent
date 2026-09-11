"""Starlette application serving the platform UI and milestone APIs."""

from __future__ import annotations

import base64
import hmac
import json
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import ClassVar

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from food_label_agent.alternatives.catalog import OfficialChinaCatalog
from food_label_agent.alternatives.category import suggest_product_category
from food_label_agent.alternatives.discovery import OfficialProductDiscovery
from food_label_agent.alternatives.models import AlternativeWorkflowRequest
from food_label_agent.conversation.provider import (
    ConversationProviderError,
    conversation_public_status,
)
from food_label_agent.conversation.service import ConversationAgent
from food_label_agent.conversation.state import (
    StructuredConversationState,
    update_structured_state,
)
from food_label_agent.conversation.store import SQLiteConversationStore
from food_label_agent.domain.models import LabelField
from food_label_agent.graph.planner import planner_public_status
from food_label_agent.graph.runtime import run_agent_graph
from food_label_agent.graph.state import create_initial_state
from food_label_agent.graph.workflows import (
    run_alternative_workflow,
    run_regulatory_workflow,
)
from food_label_agent.ingredients.api_models import (
    SafetyEvaluationRequest,
)
from food_label_agent.ingredients.service import evaluate_user_constraints_result
from food_label_agent.ocr.config import OCRConfigurationError
from food_label_agent.ocr.models import ConfirmLabelRequest
from food_label_agent.ocr.paddle_provider import create_ocr_provider
from food_label_agent.ocr.provider import OCRProvider, OCRProviderError
from food_label_agent.ocr.quality import ImageQualityError
from food_label_agent.ocr.service import InvalidImageError, OCRService
from food_label_agent.persistence.sqlite import (
    SQLiteCheckpointStore,
    SQLiteMemoryStore,
    default_database_path,
    serialize_agent_state,
)
from food_label_agent.regulations.semantic import rag2_public_status

STATIC_DIR = Path(__file__).with_name("static")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply a conservative browser security baseline to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'; object-src 'none'; img-src 'self' data: blob:; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), payment=()"
        )
        if request.url.scheme == "https" or os.getenv("FOOD_LABEL_FORCE_HTTPS") == "1":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


class RequestBoundaryMiddleware(BaseHTTPMiddleware):
    """Reject declared oversized bodies before form or JSON parsing allocates them."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    declared = int(content_length)
                except ValueError:
                    return _error("请求体长度无效。", status_code=400)
                limit = (
                    MAX_IMAGE_BYTES + 1024 * 1024
                    if request.url.path == "/api/v1/ocr/analyze"
                    else MAX_JSON_BYTES
                )
                if declared > limit:
                    return _error("请求内容过大。", status_code=413)
        return await call_next(request)


class SiteAccessMiddleware(BaseHTTPMiddleware):
    """Protect a Remote deployment with a shared access gate.

    Successful HTTP Basic authentication mints an HttpOnly same-site cookie so
    workflow endpoints can continue using their independent Bearer capability
    tokens without an Authorization-header collision.
    """

    def __init__(self, app, *, token: str) -> None:
        super().__init__(app)
        self._token = token
        self._cookie_value = sha256(token.encode()).hexdigest()

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path == "/api/ready":
            return await call_next(request)
        authorized, mint_cookie = self._authorized(request)
        if not authorized:
            return JSONResponse(
                {"status": "error", "message": "该 Remote 实例需要访问凭证。"},
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Food Label Agent"'},
            )
        response = await call_next(request)
        if mint_cookie:
            response.set_cookie(
                "food_label_site_access",
                self._cookie_value,
                max_age=8 * 60 * 60,
                httponly=True,
                secure=request.url.scheme == "https"
                or os.getenv("FOOD_LABEL_FORCE_HTTPS") == "1",
                samesite="strict",
            )
        return response

    def _authorized(self, request: Request) -> tuple[bool, bool]:
        cookie = request.cookies.get("food_label_site_access", "")
        if hmac.compare_digest(cookie, self._cookie_value):
            return True, False
        supplied = request.headers.get("x-food-label-site-token", "")
        if hmac.compare_digest(supplied, self._token):
            return True, True
        authorization = request.headers.get("authorization", "")
        scheme, _, encoded = authorization.partition(" ")
        if scheme.casefold() != "basic" or not encoded:
            return False, False
        try:
            _, _, password = base64.b64decode(encoded).decode().partition(":")
        except (ValueError, UnicodeDecodeError):
            return False, False
        return hmac.compare_digest(password, self._token), True


class SameOriginWriteMiddleware(BaseHTTPMiddleware):
    """Reject cross-site browser writes and fail closed for cookie-authenticated writes."""

    _UNSAFE_METHODS: ClassVar[frozenset[str]] = frozenset(
        {"POST", "PUT", "PATCH", "DELETE"}
    )

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in self._UNSAFE_METHODS:
            return await call_next(request)
        origin = request.headers.get("origin", "").strip()
        uses_site_cookie = bool(
            {"food_label_site_access", "food_label_memory_access"}
            & request.cookies.keys()
        )
        if not origin:
            if uses_site_cookie:
                return _error(
                    "无法验证写请求来源，请从当前站点重新操作。",
                    status_code=403,
                    code="ORIGIN_REQUIRED",
                )
            return await call_next(request)
        expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if not hmac.compare_digest(origin.rstrip("/"), expected.rstrip("/")):
            return _error(
                "已阻止跨站写请求。",
                status_code=403,
                code="CROSS_SITE_REQUEST_BLOCKED",
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Small single-instance abuse guard; production proxies should add a second layer."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    async def dispatch(self, request: Request, call_next) -> Response:
        limit = self._limit_for(request)
        if limit is None:
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        key = (client, request.url.path)
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - 60:
                events.popleft()
            if len(events) >= limit:
                return _error(
                    "请求过于频繁，请稍后再试。",
                    status_code=429,
                    code="RATE_LIMITED",
                    headers={"Retry-After": "60"},
                )
            events.append(now)
        return await call_next(request)

    @staticmethod
    def _limit_for(request: Request) -> int | None:
        if request.method not in {"POST", "PUT", "DELETE"}:
            return None
        if request.url.path == "/api/v1/ocr/analyze":
            return int(os.getenv("FOOD_LABEL_OCR_REQUESTS_PER_MINUTE", "10"))
        if request.url.path == "/api/v1/alternatives/discovery/refresh":
            return int(os.getenv("FOOD_LABEL_DISCOVERY_REFRESHES_PER_MINUTE", "2"))
        return int(os.getenv("FOOD_LABEL_WRITE_REQUESTS_PER_MINUTE", "60"))


def create_app(
    provider: OCRProvider | None = None,
    *,
    checkpoint_store: SQLiteCheckpointStore | None = None,
    memory_store: SQLiteMemoryStore | None = None,
    conversation_store: SQLiteConversationStore | None = None,
    conversation_agent: ConversationAgent | None = None,
    discovery_service: OfficialProductDiscovery | None = None,
    production_mode: bool = False,
    site_access_token: str | None = None,
    allowed_hosts: list[str] | None = None,
) -> Starlette:
    service = OCRService(provider or create_ocr_provider())
    checkpoints = checkpoint_store or SQLiteCheckpointStore()
    memories = memory_store or SQLiteMemoryStore()
    chat_retention_hours = int(os.getenv("FOOD_LABEL_CHAT_RETENTION_HOURS", "24"))
    conversations = conversation_store or SQLiteConversationStore(
        retention_hours=chat_retention_hours
    )
    conversations.purge_expired()
    chat_agent = conversation_agent or ConversationAgent()
    discovery = discovery_service or OfficialProductDiscovery()
    memory_retention_days = int(os.getenv("FOOD_LABEL_MEMORY_RETENTION_DAYS", "30"))
    memories.purge_expired(retention_days=memory_retention_days)

    async def index(_: Request) -> FileResponse:
        return FileResponse(
            STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"}
        )

    async def developer(_: Request) -> FileResponse:
        return FileResponse(
            STATIC_DIR / "developer.html", headers={"Cache-Control": "no-cache"}
        )

    async def developer_traces(request: Request) -> JSONResponse:
        configured = os.getenv("FOOD_LABEL_DEV_TOKEN")
        try:
            supplied = _bearer_token(request)
        except PermissionError:
            supplied = None
        if not configured or supplied != configured:
            return _error("开发者轨迹需要有效的开发者令牌。", status_code=403)
        path = Path(
            os.getenv("FOOD_LABEL_TRACE_REPORT", "/tmp/internal-pilot-suite.json")
        )
        if not path.exists():
            return JSONResponse({"status": "empty", "traces": [], "metrics": {}})
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _error("轨迹报告暂时无法读取。", status_code=503)
        return JSONResponse({"status": "found", "report_path": str(path), **payload})

    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "service": "food-label-platform",
                "version": "0.3.0",
                "ocr_provider": service.provider.name,
                "synthetic_ocr": service.provider.synthetic,
                "remote_processing": getattr(
                    service.provider, "remote_processing", False
                ),
                "planner": planner_public_status(),
                "conversation": conversation_public_status(
                    chat_agent.provider.settings
                ),
                "rag": rag2_public_status(),
                "product_catalog": os.getenv(
                    "FOOD_LABEL_PRODUCT_CATALOG", "official_cn_expanded"
                ),
                "public_url": os.getenv("FOOD_LABEL_PUBLIC_BASE_URL") or None,
                "processing_disclosure_verified": True,
                "storage": {
                    "durable": checkpoints.durable and memories.durable,
                    "mode": "sqlite_file"
                    if checkpoints.durable and memories.durable
                    else "ephemeral_memory",
                    "memory_retention_days": memory_retention_days,
                },
                "conversation_storage": {
                    "durable": conversations.durable,
                    "retention_hours": chat_retention_hours,
                },
            }
        )

    async def ready(_: Request) -> JSONResponse:
        checks: dict[str, dict[str, object]] = {}
        try:
            checks["checkpoint_store"] = {
                "ok": checkpoints.healthcheck(),
                "durable": checkpoints.durable,
            }
            checks["memory_store"] = {
                "ok": memories.healthcheck(),
                "durable": memories.durable,
            }
            checks["conversation_store"] = {
                "ok": conversations.healthcheck(),
                "durable": conversations.durable,
            }
        except Exception as exc:  # noqa: BLE001 - readiness must report, not crash
            checks["persistence"] = {"ok": False, "error": type(exc).__name__}
        try:
            coverage = OfficialChinaCatalog().coverage()
            checks["product_catalog"] = {
                "ok": int(coverage.get("total", 0)) > 0,
                "records": int(coverage.get("total", 0)),
            }
            if production_mode:
                complete_packaging = int(
                    coverage.get("complete_packaging_snapshot_count", 0)
                )
                total_products = int(coverage.get("total", 0))
                checks["product_packaging_evidence"] = {
                    "ok": total_products > 0 and complete_packaging == total_products,
                    "verified_records": complete_packaging,
                    "records": total_products,
                }
                expired_count = int(coverage.get("expired_evidence_count", 0))
                stale_count = int(coverage.get("stale_evidence_count", 0))
                checks["product_evidence_freshness"] = {
                    "ok": expired_count == 0 and stale_count == 0,
                    "expired_records": expired_count,
                    "stale_records": stale_count,
                    "records": total_products,
                }
                purchase_rate = float(
                    coverage.get("purchase_availability_rate", 0.0)
                )
                minimum_purchase_rate = float(
                    os.getenv("FOOD_LABEL_MIN_PURCHASE_AVAILABILITY_RATE", "1.0")
                )
                checks["product_purchase_availability"] = {
                    "ok": total_products > 0
                    and purchase_rate >= minimum_purchase_rate,
                    "verified_records": int(
                        coverage.get("current_purchase_evidence_count", 0)
                    ),
                    "records": total_products,
                    "coverage_rate": purchase_rate,
                    "minimum_rate": minimum_purchase_rate,
                }
        except Exception as exc:  # noqa: BLE001
            checks["product_catalog"] = {"ok": False, "error": type(exc).__name__}
        checks["ocr"] = {
            "ok": not production_mode or not service.provider.synthetic,
            "provider": service.provider.name,
            "external_dependency_verified": False,
        }
        checks["site_access"] = {
            "ok": not production_mode or bool(site_access_token),
        }
        checks["conversation"] = {
            "ok": not production_mode or chat_agent.configured,
            "configured": chat_agent.configured,
            "model": chat_agent.provider.settings.model,
        }
        ok = all(bool(item.get("ok")) for item in checks.values())
        return JSONResponse(
            {"status": "ready" if ok else "not_ready", "checks": checks},
            status_code=200 if ok else 503,
        )

    async def official_catalog_coverage(request: Request) -> JSONResponse:
        category = request.query_params.get("category") or None
        return JSONResponse(OfficialChinaCatalog().coverage(category=category))

    async def official_catalog_review_queue(request: Request) -> JSONResponse:
        category = request.query_params.get("category") or None
        return JSONResponse(OfficialChinaCatalog().review_queue(category=category))

    async def official_discovery_status(request: Request) -> JSONResponse:
        category = request.query_params.get("category") or None
        return JSONResponse(discovery.status(category=category))

    async def refresh_official_discovery(request: Request) -> JSONResponse:
        try:
            _require_discovery_admin(request, production_mode=production_mode)
            payload = await request.json()
            category = str(payload.get("category") or "").strip() or None
            result = await run_in_threadpool(discovery.refresh, category=category)
            return JSONResponse(result.to_dict())
        except PermissionError:
            return _error("自动发现刷新需要有效的管理员令牌。", status_code=403)
        except (TypeError, ValueError) as exc:
            return _error(str(exc), status_code=422)

    async def review_official_discovery(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
            item = discovery.review(
                candidate_id=str(payload.get("candidate_id") or ""),
                decision=str(payload.get("decision") or ""),
                review_token=_bearer_token(request),
                product=payload.get("product"),
            )
            return JSONResponse({"status": "reviewed", "item": item})
        except PermissionError:
            return _error("目录审核凭证无效。", status_code=403)
        except KeyError:
            return _error("没有找到这条待复核商品。", status_code=404)
        except (TypeError, ValueError, ValidationError) as exc:
            return _error(str(exc), status_code=422)

    async def analyze_label(request: Request) -> JSONResponse:
        try:
            form = await request.form(
                max_files=1, max_fields=4, max_part_size=MAX_IMAGE_BYTES
            )
            upload = form.get("image")
            if not isinstance(upload, UploadFile):
                return _error("请选择一张食品标签图片。", status_code=422)
            content = await _read_upload_limited(upload, MAX_IMAGE_BYTES)
            result = await service.analyze(
                content=content,
                file_name=upload.filename or "label-image",
                media_type=upload.content_type or "application/octet-stream",
            )
            state = create_initial_state(
                request_id=result.request_id,
                jurisdiction="CN",
                applicable_date=datetime.now(UTC).date().isoformat(),
            )
            state["label_fields"] = {
                field.name: LabelField(
                    name=field.name,
                    raw_text=field.raw_text,
                    confidence=field.confidence,
                    confirmed_by_user=False,
                )
                for field in result.fields
            }
            state["ocr_evidence"] = {
                **result.evidence_quality.model_dump(mode="json"),
                "status": "needs_confirmation",
                "provider": result.provider,
                "synthetic": result.synthetic,
            }
            state["warnings"] = list(result.warnings)
            state = run_agent_graph(state)
            checkpoint = checkpoints.save(state)
            payload = result.model_dump(mode="json")
            payload["checkpoint"] = checkpoint.to_dict()
            payload["workflow_trace"] = [
                asdict(item) for item in state["workflow_trace"]
            ]
            return JSONResponse(payload)
        except (InvalidImageError, ImageQualityError) as exc:
            return _error(str(exc), status_code=422)
        except OCRProviderError as exc:
            return _error(str(exc), status_code=503, code=exc.code)
        except OCRConfigurationError as exc:
            return _error(str(exc), status_code=503, code="OCR_CONFIGURATION_ERROR")
        except Exception:  # noqa: BLE001 - sanitize unexpected provider failures
            return _error("识别服务暂时不可用，请稍后重试。", status_code=500)

    async def confirm_label(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
            parsed = ConfirmLabelRequest.model_validate(payload)
            result = service.confirm(parsed)
            response = result.model_dump(mode="json")
            response["alternative_category_suggestion"] = suggest_product_category(
                parsed.fields
            )
            if parsed.resume_token:
                state = checkpoints.load_latest(parsed.request_id, parsed.resume_token)
                state["jurisdiction"] = parsed.jurisdiction
                state["applicable_date"] = parsed.applicable_date
                state["label_fields"] = {
                    name: LabelField(
                        name=name,
                        raw_text=value,
                        confidence=1.0,
                        confirmed_by_user=True,
                        bounding_box=(
                            state["label_fields"][name].bounding_box
                            if name in state["label_fields"]
                            else None
                        ),
                    )
                    for name, value in parsed.fields.items()
                }
                state["ocr_evidence"] = {**state["ocr_evidence"], "status": "confirmed"}
                state = run_agent_graph(state)
                response["normalized_label"] = state["normalized_label"]
                response["normalization_issues"] = [
                    {
                        **issue,
                        "field": field,
                    }
                    for field, issues in [
                        ("ingredients", state["normalized_label"].get("issues", [])),
                        (
                            "nutrition_table",
                            (state["normalized_label"].get("nutrition") or {}).get(
                                "issues", []
                            ),
                        ),
                    ]
                    for issue in issues
                ]
                response["status"] = state["status"].value
                response["next_route"] = (
                    "evaluate_safety"
                    if "user_constraints_required" in state["unknowns"]
                    else state["stage"].value
                )
                response["workflow_trace"] = [
                    asdict(item) for item in state["workflow_trace"]
                ]
                response["checkpoint"] = checkpoints.save(
                    state, resume_token=parsed.resume_token
                ).to_dict()
            return JSONResponse(response)
        except PermissionError:
            return _error("该分析会话需要有效的恢复令牌。", status_code=403)
        except KeyError:
            return _error("没有找到这个分析会话。", status_code=404)
        except ValidationError as exc:
            message = "标签字段不完整，请确认配料表后重试。"
            if exc.errors():
                message = str(exc.errors()[0].get("ctx", {}).get("error", message))
            return _error(message, status_code=422)
        except Exception:  # noqa: BLE001 - sanitize unexpected confirmation failures
            return _error("确认标签时发生错误，请重试。", status_code=500)

    async def evaluate_label(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
            parsed = SafetyEvaluationRequest.model_validate(payload)
            response = evaluate_user_constraints_result(parsed)
            result = response.model_dump(mode="json")
            result["alternative_category_suggestion"] = suggest_product_category(
                parsed.confirmed_fields
            )
            resumed_state = (
                checkpoints.load_latest(parsed.request_id, parsed.resume_token)
                if parsed.resume_token
                else None
            )
            evidence, final_state = run_regulatory_workflow(
                parsed, response, state=resumed_state
            )
            result["evidence"] = evidence
            if evidence["final_status"] in {
                "completed",
                "blocked",
                "needs_confirmation",
            }:
                result["status"] = evidence["final_status"]
                result["next_route"] = evidence["final_status"]
            checkpoint = checkpoints.save(final_state, resume_token=parsed.resume_token)
            result["checkpoint"] = checkpoint.to_dict()
            return JSONResponse(result)
        except PermissionError:
            return _error("该分析会话需要有效的恢复令牌。", status_code=403)
        except KeyError:
            return _error("没有找到这个分析会话。", status_code=404)
        except (ValidationError, ValueError) as exc:
            message = "请选择至少一项个人约束。"
            if isinstance(exc, ValidationError) and exc.errors():
                message = str(exc.errors()[0].get("ctx", {}).get("error", message))
            return _error(message, status_code=422)
        except Exception:  # noqa: BLE001 - sanitize unexpected evaluation failures
            return _error("个人约束规则评估暂时无法完成，请重试。", status_code=500)

    async def get_workflow_checkpoint(request: Request) -> JSONResponse:
        try:
            request_id = request.path_params["request_id"]
            token = _bearer_token(request)
            state = checkpoints.load_latest(request_id, token)
            return JSONResponse(
                {
                    "status": "found",
                    "state": serialize_agent_state(state),
                    "history": checkpoints.history(request_id, token),
                }
            )
        except KeyError:
            return _error("没有找到这个分析会话。", status_code=404)
        except PermissionError:
            return _error("恢复令牌无效。", status_code=403)

    async def find_alternatives(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
            parsed = AlternativeWorkflowRequest.model_validate(payload)
            resumed_state = checkpoints.load_latest(
                parsed.request_id, parsed.resume_token
            )
            result, final_state = run_alternative_workflow(parsed, state=resumed_state)
            result["discovery"] = {
                "status": "cached",
                "summary": discovery.status(category=parsed.category),
                "warnings": [],
            }
            checkpoint = checkpoints.save(final_state, resume_token=parsed.resume_token)
            result["checkpoint"] = checkpoint.to_dict()
            return JSONResponse(result)
        except PermissionError:
            return _error("该分析会话需要有效的恢复令牌。", status_code=403)
        except KeyError:
            return _error("没有找到这个分析会话。", status_code=404)
        except (ValidationError, ValueError) as exc:
            message = "请选择要查找的同类商品类别。"
            if isinstance(exc, ValidationError) and exc.errors():
                message = str(exc.errors()[0].get("ctx", {}).get("error", message))
            return _error(message, status_code=422)
        except Exception:  # noqa: BLE001 - sanitize catalog/tool failures
            return _error("替代品复核暂时无法完成，请稍后重试。", status_code=500)

    async def delete_workflow_checkpoint(request: Request) -> JSONResponse:
        try:
            request_id = request.path_params["request_id"]
            deleted = checkpoints.delete(request_id, _bearer_token(request))
            return JSONResponse({"status": "deleted", "deleted_checkpoints": deleted})
        except KeyError:
            return _error("没有找到这个分析会话。", status_code=404)
        except PermissionError:
            return _error("恢复令牌无效。", status_code=403)

    async def create_conversation_session(_: Request) -> JSONResponse:
        receipt = conversations.create_session()
        return JSONResponse(
            {
                "status": "created",
                "session": receipt.to_dict(),
                "retention_hours": conversations.retention_hours,
                "remote_processing": True,
            },
            status_code=201,
        )

    async def get_conversation_session(request: Request) -> JSONResponse:
        try:
            session_id = request.path_params["session_id"]
            return JSONResponse(
                {
                    "status": "found",
                    "session": conversations.session(
                        session_id, _bearer_token(request)
                    ),
                }
            )
        except KeyError:
            return _error("没有找到这个对话，可能已经过期。", status_code=404)
        except PermissionError:
            return _error("对话访问令牌无效。", status_code=403)
        except ValueError as exc:
            return _error(str(exc), status_code=422)

    async def delete_conversation_session(request: Request) -> JSONResponse:
        try:
            session_id = request.path_params["session_id"]
            deleted = conversations.delete(session_id, _bearer_token(request))
            return JSONResponse({"status": "deleted", "deleted_sessions": deleted})
        except KeyError:
            return _error("没有找到这个对话，可能已经过期。", status_code=404)
        except PermissionError:
            return _error("对话访问令牌无效。", status_code=403)
        except ValueError as exc:
            return _error(str(exc), status_code=422)

    async def conversation_feedback(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise TypeError("反馈请求必须是对象。")
            if not isinstance(payload.get("helpful"), bool):
                raise TypeError("请选择这条回答是否有帮助。")
            session_id = request.path_params["session_id"]
            feedback = conversations.record_feedback(
                session_id,
                _bearer_token(request),
                message_id=str(payload.get("message_id") or "").strip(),
                helpful=payload["helpful"],
                reason=payload.get("reason"),
                retry_requested=payload.get("retry_requested") is True,
            )
            return JSONResponse(
                {
                    "status": "recorded",
                    "feedback": feedback,
                    "privacy": {
                        "raw_conversation_stored": False,
                        "retention_days": 30,
                    },
                },
                status_code=201,
            )
        except KeyError:
            return _error("没有找到这条对话回答。", status_code=404)
        except PermissionError:
            return _error("对话访问令牌无效。", status_code=403)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return _error(str(exc), status_code=422)

    async def pilot_metrics(request: Request) -> JSONResponse:
        configured = os.getenv("FOOD_LABEL_DEV_TOKEN", "").strip()
        try:
            supplied = _bearer_token(request)
        except PermissionError:
            supplied = ""
        if not configured or not hmac.compare_digest(supplied, configured):
            return _error("试用指标需要有效的开发者令牌。", status_code=403)
        summary = conversations.feedback_summary()
        thresholds = {
            "minimum_feedback_count": 100,
            "minimum_unique_sessions": 20,
            "minimum_helpful_rate": 0.80,
        }
        gates = {
            "feedback_volume": summary["feedback_count"]
            >= thresholds["minimum_feedback_count"],
            "session_coverage": summary["unique_session_count"]
            >= thresholds["minimum_unique_sessions"],
            "helpful_rate": summary["helpful_rate"] is not None
            and summary["helpful_rate"] >= thresholds["minimum_helpful_rate"],
        }
        return JSONResponse(
            {
                "status": "feedback_thresholds_met"
                if all(gates.values())
                else "collecting",
                "summary": summary,
                "thresholds": thresholds,
                "gates": gates,
                "feedback_gate_passed": all(gates.values()),
                "pilot_outcome_validated": False,
                "validation_note": (
                    "聚合反馈不能替代带审核声明的真人任务、严重事件和延迟验收。"
                ),
            }
        )

    async def conversation_message(request: Request) -> Response:
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise TypeError("对话请求必须是对象。")
            content = str(payload.get("content") or "").strip()
            if not content or len(content) > 4_000:
                raise ValueError("请输入 1 到 4000 个字符。")
            emergency_message = _is_emergency_message(content)
            if payload.get("remote_processing_consent") is not True and not emergency_message:
                return _error(
                    "发送普通问题前，需要明确同意本次短期对话使用 OpenAI。",
                    status_code=412,
                    code="REMOTE_PROCESSING_CONSENT_REQUIRED",
                )
            session_id = request.path_params["session_id"]
            access_token = _bearer_token(request)
            # Authorize before returning a streaming response, so HTTP errors remain clear.
            conversations.session(session_id, access_token)
            workflow_request_id = str(
                payload.get("workflow_request_id") or ""
            ).strip()
            workflow_token = str(payload.get("workflow_resume_token") or "").strip()
            workflow_state = None
            if workflow_request_id or workflow_token:
                if not workflow_request_id or not workflow_token:
                    raise ValueError("关联标签需要完整的分析编号和恢复令牌。")
                workflow_state = checkpoints.load_latest(
                    workflow_request_id, workflow_token
                )
            if not chat_agent.configured and not emergency_message:
                return _error(
                    "自由对话尚未配置模型访问凭证。",
                    status_code=503,
                    code="CONVERSATION_NOT_CONFIGURED",
                )
            structured_state = update_structured_state(
                StructuredConversationState.from_dict(
                    conversations.structured_state(session_id, access_token)
                ),
                message=content,
                workflow_state=workflow_state,
            )
            conversations.save_structured_state(
                session_id, access_token, structured_state.to_dict()
            )
            conversations.append_message(
                session_id,
                access_token,
                role="user",
                content=content,
                metadata={
                    "workflow_request_id": workflow_request_id or None,
                    "trusted_label_attached": workflow_state is not None,
                },
            )
            history = conversations.messages(session_id, access_token, limit=24)

            async def event_stream():
                yield _sse_event(
                    "status",
                    {
                        "stage": "thinking",
                        "message": "正在理解你的问题",
                    },
                )
                try:
                    reply = await run_in_threadpool(
                        chat_agent.reply,
                        session_id=session_id,
                        messages=history,
                        state=workflow_state,
                        conversation_state=structured_state,
                    )
                    for tool_event in reply.tool_events:
                        yield _sse_event(
                            "tool",
                            {
                                **tool_event,
                                "message": _conversation_tool_label(
                                    str(tool_event.get("name") or "")
                                ),
                            },
                        )
                    for chunk in _text_chunks(reply.text, 42):
                        yield _sse_event("delta", {"text": chunk})
                    assistant_message = conversations.append_message(
                        session_id,
                        access_token,
                        role="assistant",
                        content=reply.text,
                        metadata={
                            "model": reply.model,
                            "response_id": reply.response_id,
                            "input_tokens": reply.input_tokens,
                            "output_tokens": reply.output_tokens,
                            "latency_ms": reply.latency_ms,
                            "request_count": reply.request_count,
                            "first_token_ms": reply.first_token_ms,
                            "cost_usd": reply.cost_usd,
                            "reasoning_effort": reply.reasoning_effort,
                            "boundary": reply.boundary,
                            "tool_events": list(reply.tool_events),
                            "trusted_label_attached": workflow_state is not None,
                        },
                    )
                    yield _sse_event(
                        "done",
                        {
                            "model": reply.model,
                            "boundary": reply.boundary,
                            "tool_calls": len(reply.tool_events),
                            "latency_ms": reply.latency_ms,
                            "first_token_ms": reply.first_token_ms,
                            "cost_usd": reply.cost_usd,
                            "reasoning_effort": reply.reasoning_effort,
                            "trusted_label_attached": workflow_state is not None,
                            "message_id": assistant_message["message_id"],
                        },
                    )
                except ConversationProviderError as exc:
                    yield _sse_event(
                        "error",
                        {
                            "code": exc.code,
                            "message": _conversation_error_message(exc.code),
                            "retryable": exc.retryable,
                        },
                    )
                except Exception:  # noqa: BLE001 - do not leak provider details
                    yield _sse_event(
                        "error",
                        {
                            "code": "conversation_failed",
                            "message": "这次回答没有完成，请稍后再试。",
                            "retryable": True,
                        },
                    )

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-store",
                    "X-Accel-Buffering": "no",
                },
            )
        except KeyError:
            return _error("没有找到这个对话或标签分析。", status_code=404)
        except PermissionError:
            return _error("对话或标签分析的访问令牌无效。", status_code=403)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return _error(str(exc), status_code=422)

    async def grant_memory_consent(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
            receipt = memories.grant_consent(
                str(payload.get("profile_id", "")),
                str(payload.get("purpose", "")),
                explicit_consent=payload.get("explicit_consent") is True,
            )
            return_token = (
                request.headers.get("x-food-label-token-delivery", "").casefold()
                == "bearer"
            )
            response = JSONResponse(
                {
                    "status": "consent_granted",
                    "consent_id": receipt.consent_id,
                    "profile_id": receipt.profile_id,
                    "purpose": receipt.purpose,
                    "granted_at": receipt.granted_at,
                    **(
                        {"access_token": receipt.access_token}
                        if return_token
                        else {}
                    ),
                    "notice": (
                        "Bearer 访问令牌仅返回一次；撤销授权会删除关联记忆。"
                        if return_token
                        else "浏览器凭证已保存为 HttpOnly Cookie；撤销授权会删除关联记忆。"
                    ),
                },
                status_code=201,
            )
            if not return_token:
                response.set_cookie(
                    "food_label_memory_access",
                    receipt.access_token,
                    max_age=memory_retention_days * 24 * 60 * 60,
                    httponly=True,
                    secure=request.url.scheme == "https"
                    or os.getenv("FOOD_LABEL_FORCE_HTTPS") == "1",
                    samesite="strict",
                    path="/api/v1/",
                )
            return response
        except PermissionError:
            return _error("必须由用户明确授权后才能保存长期记忆。", status_code=403)
        except (TypeError, ValueError) as exc:
            return _error(str(exc), status_code=422)

    async def memory_items(request: Request) -> JSONResponse:
        try:
            profile_id = _profile_id(request)
            token = _memory_token(request)
            if request.method == "GET":
                return JSONResponse(
                    {
                        "status": "ok",
                        "items": memories.list_items(profile_id, token),
                    }
                )
            payload = await request.json()
            item = memories.upsert_item(
                profile_id,
                token,
                kind=str(payload.get("kind", "")),
                value=payload.get("value"),
            )
            return JSONResponse({"status": "saved", "item": item}, status_code=201)
        except PermissionError:
            return _error("长期记忆授权或访问令牌无效。", status_code=403)
        except (TypeError, ValueError) as exc:
            return _error(str(exc), status_code=422)

    async def establish_memory_session(request: Request) -> JSONResponse:
        try:
            profile_id = _profile_id(request)
            token = _bearer_token(request)
            memories.list_items(profile_id, token)
            response = JSONResponse({"status": "session_established"})
            response.set_cookie(
                "food_label_memory_access",
                token,
                max_age=memory_retention_days * 24 * 60 * 60,
                httponly=True,
                secure=request.url.scheme == "https"
                or os.getenv("FOOD_LABEL_FORCE_HTTPS") == "1",
                samesite="strict",
                path="/api/v1/",
            )
            return response
        except PermissionError:
            return _error("长期记忆授权或访问令牌无效。", status_code=403)
        except ValueError as exc:
            return _error(str(exc), status_code=422)

    async def memory_item(request: Request) -> JSONResponse:
        try:
            profile_id = _profile_id(request)
            token = _memory_token(request)
            memory_id = request.path_params["memory_id"]
            if request.method == "DELETE":
                memories.delete_item(profile_id, token, memory_id)
                return JSONResponse({"status": "deleted", "memory_id": memory_id})
            payload = await request.json()
            item = memories.upsert_item(
                profile_id,
                token,
                kind=str(payload.get("kind", "")),
                value=payload.get("value"),
                memory_id=memory_id,
            )
            return JSONResponse({"status": "updated", "item": item})
        except KeyError:
            return _error("没有找到这条长期记忆。", status_code=404)
        except PermissionError:
            return _error("长期记忆授权或访问令牌无效。", status_code=403)
        except (TypeError, ValueError) as exc:
            return _error(str(exc), status_code=422)

    async def revoke_memory_consent(request: Request) -> JSONResponse:
        try:
            profile_id = _profile_id(request)
            deleted = memories.revoke_consent(profile_id, _memory_token(request))
            response = JSONResponse(
                {
                    "status": "consent_revoked",
                    "deleted_memory_items": deleted,
                }
            )
            response.delete_cookie("food_label_memory_access", path="/api/v1/")
            return response
        except PermissionError:
            return _error("长期记忆授权或访问令牌无效。", status_code=403)
        except ValueError as exc:
            return _error(str(exc), status_code=422)

    async def export_profile_data(request: Request) -> JSONResponse:
        try:
            return JSONResponse(
                {
                    "status": "exported",
                    "data": memories.export_profile(
                        _profile_id(request), _memory_token(request)
                    ),
                }
            )
        except PermissionError:
            return _error("长期记忆授权或访问令牌无效。", status_code=403)
        except ValueError as exc:
            return _error(str(exc), status_code=422)

    async def delete_profile_data(request: Request) -> JSONResponse:
        try:
            deleted = memories.delete_profile(
                _profile_id(request), _memory_token(request)
            )
            response = JSONResponse({"status": "deleted", "deleted": deleted})
            response.delete_cookie("food_label_memory_access", path="/api/v1/")
            return response
        except PermissionError:
            return _error("长期记忆授权或访问令牌无效。", status_code=403)
        except ValueError as exc:
            return _error(str(exc), status_code=422)

    routes = [
        Route("/", endpoint=index),
        Route("/developer", endpoint=developer),
        Route("/api/developer-traces", endpoint=developer_traces),
        Route("/api/health", endpoint=health),
        Route("/api/ready", endpoint=ready),
        Route(
            "/api/v1/alternatives/catalog-coverage",
            endpoint=official_catalog_coverage,
        ),
        Route(
            "/api/v1/alternatives/catalog-review-queue",
            endpoint=official_catalog_review_queue,
        ),
        Route(
            "/api/v1/alternatives/discovery",
            endpoint=official_discovery_status,
            methods=["GET"],
        ),
        Route(
            "/api/v1/alternatives/discovery/refresh",
            endpoint=refresh_official_discovery,
            methods=["POST"],
        ),
        Route(
            "/api/v1/alternatives/discovery/review",
            endpoint=review_official_discovery,
            methods=["POST"],
        ),
        Route("/api/v1/ocr/analyze", endpoint=analyze_label, methods=["POST"]),
        Route("/api/v1/labels/confirm", endpoint=confirm_label, methods=["POST"]),
        Route("/api/v1/labels/evaluate", endpoint=evaluate_label, methods=["POST"]),
        Route(
            "/api/v1/alternatives/search",
            endpoint=find_alternatives,
            methods=["POST"],
        ),
        Route(
            "/api/v1/workflows/{request_id}",
            endpoint=get_workflow_checkpoint,
            methods=["GET"],
        ),
        Route(
            "/api/v1/workflows/{request_id}",
            endpoint=delete_workflow_checkpoint,
            methods=["DELETE"],
        ),
        Route(
            "/api/v1/chat/sessions",
            endpoint=create_conversation_session,
            methods=["POST"],
        ),
        Route(
            "/api/v1/chat/sessions/{session_id}",
            endpoint=get_conversation_session,
            methods=["GET"],
        ),
        Route(
            "/api/v1/chat/sessions/{session_id}",
            endpoint=delete_conversation_session,
            methods=["DELETE"],
        ),
        Route(
            "/api/v1/chat/sessions/{session_id}/messages",
            endpoint=conversation_message,
            methods=["POST"],
        ),
        Route(
            "/api/v1/chat/sessions/{session_id}/feedback",
            endpoint=conversation_feedback,
            methods=["POST"],
        ),
        Route("/api/v1/pilot/metrics", endpoint=pilot_metrics, methods=["GET"]),
        Route(
            "/api/v1/memory/consents",
            endpoint=grant_memory_consent,
            methods=["POST"],
        ),
        Route("/api/v1/memory/items", endpoint=memory_items, methods=["GET", "POST"]),
        Route(
            "/api/v1/memory/session",
            endpoint=establish_memory_session,
            methods=["POST"],
        ),
        Route(
            "/api/v1/memory/items/{memory_id}",
            endpoint=memory_item,
            methods=["PUT", "DELETE"],
        ),
        Route(
            "/api/v1/memory/consents/current",
            endpoint=revoke_memory_consent,
            methods=["DELETE"],
        ),
        Route(
            "/api/v1/privacy/export",
            endpoint=export_profile_data,
            methods=["GET"],
        ),
        Route(
            "/api/v1/privacy/profile",
            endpoint=delete_profile_data,
            methods=["DELETE"],
        ),
        Mount("/static", app=StaticFiles(directory=STATIC_DIR), name="static"),
    ]
    application = Starlette(debug=False, routes=routes)
    if allowed_hosts:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=allowed_hosts,
            www_redirect=False,
        )
    application.add_middleware(SameOriginWriteMiddleware)
    if site_access_token:
        application.add_middleware(SiteAccessMiddleware, token=site_access_token)
    application.add_middleware(RateLimitMiddleware)
    application.add_middleware(RequestBoundaryMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    return application


def _sse_event(event: str, payload: dict[str, object]) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def _text_chunks(value: str, size: int) -> list[str]:
    return [value[index : index + size] for index in range(0, len(value), size)]


def _is_emergency_message(value: str) -> bool:
    return any(
        term in value.casefold()
        for term in (
            "呼吸困难",
            "喘不过气",
            "喉头水肿",
            "喉咙肿",
            "意识不清",
            "昏厥",
            "过敏性休克",
            "anaphylaxis",
        )
    )


def _conversation_tool_label(name: str) -> str:
    return {
        "search_current_regulations": "已核对适用法规依据",
        "explain_current_ingredient": "已核对当前标签中的配料",
        "verify_current_claims": "已核对包装声称与标签事实",
        "compare_confirmed_products": "已按确认标签对比两个商品",
        "guide_label_correction": "已整理需要人工核对的标签问题",
    }.get(name, "已完成证据核对")


def _conversation_error_message(code: str) -> str:
    if code == "conversation_tool_budget_exhausted":
        return "这次问题需要的核对步骤过多，请缩小问题范围后重试。"
    if code == "conversation_model_refused":
        return "这个问题暂时无法回答，你可以换一种方式询问食品标签事实。"
    if code == "conversation_api_key_missing":
        return "自由对话尚未配置模型访问凭证。"
    if code.startswith("conversation_provider_http_429"):
        return "对话请求较多，请稍后再试。"
    if code == "conversation_cost_budget_exhausted":
        return "这次回答已达成本上限，请缩小问题范围后重试。"
    return "对话服务暂时不可用，请稍后再试。"


def _error(
    message: str,
    *,
    status_code: int,
    code: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {"status": "error", "message": message, **({"code": code} if code else {})},
        status_code=status_code,
        headers=headers,
    )


app = create_app()


def create_production_app() -> Starlette:
    """Construct the deployment app with durable storage and a mandatory access gate."""

    os.environ.setdefault("FOOD_LABEL_OCR_PROVIDER", "tencent")
    os.environ.setdefault("FOOD_LABEL_PRODUCT_CATALOG", "official_cn_expanded")
    token = os.getenv("FOOD_LABEL_SITE_ACCESS_TOKEN", "").strip()
    if len(token) < 24:
        raise RuntimeError(
            "FOOD_LABEL_SITE_ACCESS_TOKEN must contain at least 24 characters"
        )
    if not os.getenv("FOOD_LABEL_DISCOVERY_ADMIN_TOKEN", "").strip():
        raise RuntimeError("FOOD_LABEL_DISCOVERY_ADMIN_TOKEN is required")
    allowed_hosts = [
        host.strip()
        for host in os.getenv("FOOD_LABEL_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    ]
    if not allowed_hosts:
        raise RuntimeError("FOOD_LABEL_ALLOWED_HOSTS is required")
    if "*" in allowed_hosts:
        raise RuntimeError("FOOD_LABEL_ALLOWED_HOSTS must not contain '*' in production")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OPENAI_API_KEY is required for the conversation agent")
    database_path = default_database_path()
    return create_app(
        checkpoint_store=SQLiteCheckpointStore(database_path),
        memory_store=SQLiteMemoryStore(database_path),
        conversation_store=SQLiteConversationStore(
            database_path,
            retention_hours=int(
                os.getenv("FOOD_LABEL_CHAT_RETENTION_HOURS", "24")
            ),
        ),
        production_mode=True,
        site_access_token=token,
        allowed_hosts=allowed_hosts,
    )


def run() -> None:
    import uvicorn

    # Set deployment defaults before constructing the application.  Provider
    # construction is intentionally eager so a bad OCR installation or missing
    # cloud dependency fails at startup instead of on the first upload.
    # Credentials remain in the SDK credential chain and are never stored here.
    os.environ.setdefault("FOOD_LABEL_OCR_PROVIDER", "tencent")
    os.environ.setdefault("FOOD_LABEL_PRODUCT_CATALOG", "official_cn_expanded")
    uvicorn.run(
        create_production_app(),
        host=os.getenv("FOOD_LABEL_HOST", "127.0.0.1"),
        port=int(os.getenv("FOOD_LABEL_PORT", os.getenv("PORT", "8000"))),
        reload=False,
    )


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token:
        raise PermissionError("Bearer token required")
    return token


def _memory_token(request: Request) -> str:
    cookie = request.cookies.get("food_label_memory_access", "")
    if cookie:
        return cookie
    return _bearer_token(request)


def _profile_id(request: Request) -> str:
    profile_id = request.query_params.get("profile_id", "").strip()
    if not profile_id:
        raise ValueError("profile_id is required")
    return profile_id


async def _read_upload_limited(upload: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(min(1024 * 1024, limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise InvalidImageError("图片不能超过 10 MB。")
        chunks.append(chunk)
    return b"".join(chunks)


def _require_discovery_admin(request: Request, *, production_mode: bool) -> None:
    configured = os.getenv("FOOD_LABEL_DISCOVERY_ADMIN_TOKEN", "").strip()
    if not configured:
        if production_mode:
            raise PermissionError("Discovery admin token is not configured")
        return
    supplied = _bearer_token(request)
    if not hmac.compare_digest(supplied, configured):
        raise PermissionError("Invalid discovery admin token")
