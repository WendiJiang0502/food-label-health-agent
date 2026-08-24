#!/bin/zsh
set -euo pipefail

project_dir="/Users/jiangwendi/Projects/食品标签解释与替代品agent"
launch_agents_dir="$HOME/Library/LaunchAgents"
plist_path="$launch_agents_dir/com.foodlabel.agent.plist"
log_dir="$HOME/Library/Logs/food-label-agent"

mkdir -p "$launch_agents_dir" "$log_dir"
cat > "$plist_path" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.foodlabel.agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>exec "$project_dir/scripts/run_local_platform.sh"</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$project_dir</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$log_dir/platform.out.log</string>
  <key>StandardErrorPath</key>
  <string>$log_dir/platform.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)" "$plist_path" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$plist_path"
launchctl enable "gui/$(id -u)/com.foodlabel.agent"
launchctl kickstart -k "gui/$(id -u)/com.foodlabel.agent"

echo "已安装本地自动启动：$plist_path"
echo "健康检查：curl http://127.0.0.1:8000/api/health"
