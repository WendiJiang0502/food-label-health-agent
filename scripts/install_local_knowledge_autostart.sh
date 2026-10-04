#!/bin/zsh
set -euo pipefail

script_dir="${0:A:h}"
project_dir="${script_dir:h}"
launch_agents_dir="$HOME/Library/LaunchAgents"
plist_path="$launch_agents_dir/com.foodlabel.knowledge-refresh.plist"
log_dir="$HOME/Library/Logs/food-label-agent"

mkdir -p "$launch_agents_dir" "$log_dir"
"$project_dir/.venv/bin/python" - "$project_dir" "$plist_path" "$log_dir" <<'PY'
import plistlib
import sys
from pathlib import Path
project, plist, logs = map(Path, sys.argv[1:])
config = {
    "Label": "com.foodlabel.knowledge-refresh",
    "ProgramArguments": ["/bin/zsh", str(project / "scripts/run_local_knowledge_refresh.sh")],
    "WorkingDirectory": str(project),
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 60,
    "StandardOutPath": str(logs / "knowledge-refresh.out.log"),
    "StandardErrorPath": str(logs / "knowledge-refresh.err.log"),
}
plist.write_bytes(plistlib.dumps(config))
plist.chmod(0o600)
PY

launchctl bootout "gui/$(id -u)" "$plist_path" 2>/dev/null || true
launchctl enable "gui/$(id -u)/com.foodlabel.knowledge-refresh"
launchctl bootstrap "gui/$(id -u)" "$plist_path"
print "已安装并启动知识库更新服务：$plist_path"
