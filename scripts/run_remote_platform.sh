#!/bin/zsh
set -euo pipefail

script_dir="${0:A:h}"
project_dir="${script_dir:h}"
cd "$project_dir"

export PYTHONPATH="${project_dir}/src"
export FOOD_LABEL_OCR_PROVIDER="${FOOD_LABEL_OCR_PROVIDER:-tencent}"
export FOOD_LABEL_PRODUCT_CATALOG="${FOOD_LABEL_PRODUCT_CATALOG:-official_cn_expanded}"
export FOOD_LABEL_RAG_PROFILE="${FOOD_LABEL_RAG_PROFILE:-hybrid_tfidf}"
export FOOD_LABEL_OFFICIAL_MINIMUM_RECORDS="${FOOD_LABEL_OFFICIAL_MINIMUM_RECORDS:-3}"
export FOOD_LABEL_HOST="${FOOD_LABEL_HOST:-0.0.0.0}"
export FOOD_LABEL_PORT="${FOOD_LABEL_PORT:-${PORT:-8000}}"
export FOOD_LABEL_PRODUCTION_MODE=1
export FOOD_LABEL_DATA_DIR="${FOOD_LABEL_DATA_DIR:-${project_dir}/data}"

site_access_token="${FOOD_LABEL_SITE_ACCESS_TOKEN:-}"
if [[ ${#site_access_token} -lt 24 ]]; then
  print -u2 "FOOD_LABEL_SITE_ACCESS_TOKEN 必须设置为至少 24 个字符。"
  exit 2
fi
if [[ -z "${FOOD_LABEL_DISCOVERY_ADMIN_TOKEN:-}" ]]; then
  print -u2 "FOOD_LABEL_DISCOVERY_ADMIN_TOKEN 必须设置。"
  exit 2
fi

exec "${project_dir}/.venv/bin/python" -m uvicorn \
  food_label_agent.web.app:create_production_app \
  --factory \
  --host "$FOOD_LABEL_HOST" \
  --port "$FOOD_LABEL_PORT"
