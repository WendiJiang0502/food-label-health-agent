#!/bin/zsh
set -euo pipefail

script_dir="${0:A:h}"
project_dir="${script_dir:h}"
cd "$project_dir"
umask 077

config_file="$HOME/.config/food-label-agent/.env"
if [[ -f "$config_file" ]]; then
  set -a
  source "$config_file"
  set +a
fi

export PYTHONPATH="$project_dir/src"
export PYTHONUNBUFFERED=1
export FOOD_LABEL_DATA_DIR="${FOOD_LABEL_DATA_DIR:-$HOME/.local/share/food-label-health-agent}"
export FOOD_LABEL_OCR_PROVIDER="${FOOD_LABEL_OCR_PROVIDER:-tencent}"
export FOOD_LABEL_KNOWLEDGE_OCR="${FOOD_LABEL_KNOWLEDGE_OCR:-1}"

exec "$project_dir/.venv/bin/python" -m food_label_agent.alternatives.refresh "$@"
