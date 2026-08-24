#!/bin/zsh
set -euo pipefail

project_dir="/Users/jiangwendi/Projects/食品标签解释与替代品agent"
cd "$project_dir"

config_file="$HOME/.config/food-label-agent/.env"
if [[ -f "$config_file" ]]; then
  set -a
  source "$config_file"
  set +a
fi

export PYTHONPATH="$project_dir/src"
export FOOD_LABEL_OCR_PROVIDER="${FOOD_LABEL_OCR_PROVIDER:-tencent}"
export FOOD_LABEL_PRODUCT_CATALOG="${FOOD_LABEL_PRODUCT_CATALOG:-official_cn_expanded}"
export FOOD_LABEL_HOST="127.0.0.1"
export FOOD_LABEL_PORT="8000"

exec "$project_dir/.venv/bin/python" -m uvicorn \
  food_label_agent.web.app:app \
  --host "$FOOD_LABEL_HOST" \
  --port "$FOOD_LABEL_PORT"
