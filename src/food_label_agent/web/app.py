"""Starlette application serving the platform UI and milestone APIs."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from food_label_agent.alternatives.category import suggest_product_category
from food_label_agent.alternatives.models import AlternativeWorkflowRequest
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

STATIC_DIR = Path(__file__).with_name("static")


def create_app(
    provider: OCRProvider | None = None,
    *,
    checkpoint_store: SQLiteCheckpointStore | None = None,
    memory_store: SQLiteMemoryStore | None = None,
) -> Starlette:
    service = OCRService(provider or create_ocr_provider())
    checkpoints = checkpoint_store or SQLiteCheckpointStore()
    memories = memory_store or SQLiteMemoryStore()

    async def index(_: Request) -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "service": "food-label-platform",
                "version": "0.2.0",
                "ocr_provider": service.provider.name,
                "synthetic_ocr": service.provider.synthetic,
                "remote_processing": getattr(
                    service.provider, "remote_processing", False
                ),
                "product_catalog": os.getenv("FOOD_LABEL_PRODUCT_CATALOG", "curated"),
            }
        )

    async def analyze_label(request: Request) -> JSONResponse:
        try:
            form = await request.form()
            upload = form.get("image")
            if not isinstance(upload, UploadFile):
                return _error("请选择一张食品标签图片。", status_code=422)
            content = await upload.read()
            result = await service.analyze(
                content=content,
                file_name=upload.filename or "label-image",
                media_type=upload.content_type or "application/octet-stream",
            )
            return JSONResponse(result.model_dump(mode="json"))
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
            return JSONResponse(result.model_dump(mode="json"))
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
            evidence, final_state = run_regulatory_workflow(parsed, response)
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
            result, final_state = run_alternative_workflow(parsed)
            checkpoint = checkpoints.save(final_state, resume_token=parsed.resume_token)
            result["checkpoint"] = checkpoint.to_dict()
            return JSONResponse(result)
        except PermissionError:
            return _error("该分析会话需要有效的恢复令牌。", status_code=403)
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

    async def grant_memory_consent(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
            receipt = memories.grant_consent(
                str(payload.get("profile_id", "")),
                str(payload.get("purpose", "")),
                explicit_consent=payload.get("explicit_consent") is True,
            )
            return JSONResponse(
                {
                    "status": "consent_granted",
                    **receipt.to_dict(),
                    "notice": "访问令牌仅返回一次；撤销授权会删除关联记忆。",
                },
                status_code=201,
            )
        except PermissionError:
            return _error("必须由用户明确授权后才能保存长期记忆。", status_code=403)
        except (TypeError, ValueError) as exc:
            return _error(str(exc), status_code=422)

    async def memory_items(request: Request) -> JSONResponse:
        try:
            profile_id = _profile_id(request)
            token = _bearer_token(request)
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

    async def memory_item(request: Request) -> JSONResponse:
        try:
            profile_id = _profile_id(request)
            token = _bearer_token(request)
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
            deleted = memories.revoke_consent(profile_id, _bearer_token(request))
            return JSONResponse(
                {
                    "status": "consent_revoked",
                    "deleted_memory_items": deleted,
                }
            )
        except PermissionError:
            return _error("长期记忆授权或访问令牌无效。", status_code=403)
        except ValueError as exc:
            return _error(str(exc), status_code=422)

    routes = [
        Route("/", endpoint=index),
        Route("/api/health", endpoint=health),
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
            "/api/v1/memory/consents",
            endpoint=grant_memory_consent,
            methods=["POST"],
        ),
        Route("/api/v1/memory/items", endpoint=memory_items, methods=["GET", "POST"]),
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
        Mount("/static", app=StaticFiles(directory=STATIC_DIR), name="static"),
    ]
    return Starlette(debug=False, routes=routes)


def _error(message: str, *, status_code: int, code: str | None = None) -> JSONResponse:
    return JSONResponse(
        {"status": "error", "message": message, **({"code": code} if code else {})},
        status_code=status_code,
    )


app = create_app()


def run() -> None:
    import uvicorn

    # The project CLI intentionally defaults to the configured Tencent provider.
    # Credentials remain in the SDK credential chain and are never stored here.
    os.environ.setdefault("FOOD_LABEL_OCR_PROVIDER", "tencent")
    os.environ.setdefault("FOOD_LABEL_PRODUCT_CATALOG", "hybrid")
    database_path = default_database_path()
    uvicorn.run(
        create_app(
            checkpoint_store=SQLiteCheckpointStore(database_path),
            memory_store=SQLiteMemoryStore(database_path),
        ),
        host=os.getenv("FOOD_LABEL_HOST", "127.0.0.1"),
        port=int(os.getenv("FOOD_LABEL_PORT", "8000")),
        reload=False,
    )


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token:
        raise PermissionError("Bearer token required")
    return token


def _profile_id(request: Request) -> str:
    profile_id = request.query_params.get("profile_id", "").strip()
    if not profile_id:
        raise ValueError("profile_id is required")
    return profile_id
