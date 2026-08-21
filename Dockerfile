FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    FOOD_LABEL_OCR_PROVIDER=tencent \
    FOOD_LABEL_TENCENT_REGION=ap-guangzhou \
    FOOD_LABEL_PRODUCT_CATALOG=official_cn \
    FOOD_LABEL_HOST=0.0.0.0 \
    FOOD_LABEL_PORT=8000

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e '.[cloud-ocr]'

EXPOSE 8000
CMD ["uvicorn", "food_label_agent.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
