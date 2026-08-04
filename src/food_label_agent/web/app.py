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

from food_label_agent.ocr.models import ConfirmLabelRequest
from food_label_agent.ocr.paddle_provider import create_ocr_provider
from food_label_agent.ocr.provider import OCRProvider, OCRProviderError
from food_label_agent.ocr.quality import ImageQualityError
from food_label_agent.ocr.service import InvalidImageError, OCRService

STATIC_DIR = Path(__file__).with_name("static")


def create_app(provider: OCRProvider | None = None) -> Starlette:
    service = OCRService(provider or create_ocr_provider())

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
        except Exception:
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
        except Exception:
            return _error("确认标签时发生错误，请重试。", status_code=500)

    routes = [
        Route("/", endpoint=index),
        Route("/api/health", endpoint=health),
        Route("/api/v1/ocr/analyze", endpoint=analyze_label, methods=["POST"]),
        Route("/api/v1/labels/confirm", endpoint=confirm_label, methods=["POST"]),
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

    uvicorn.run(
        "food_label_agent.web.app:app",
        host=os.getenv("FOOD_LABEL_HOST", "127.0.0.1"),
        port=int(os.getenv("FOOD_LABEL_PORT", "8000")),
        reload=False,
    )
