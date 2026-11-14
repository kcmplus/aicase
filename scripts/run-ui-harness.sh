#!/usr/bin/env bash
# User-operated launcher; never starts a business run during `check`.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TASK_ID="storefront-v35-migration"
TASK_FILE="$PROJECT_ROOT/harness/tasks/$TASK_ID.json"
HARNESS="$SCRIPT_DIR/codex_harness.py"
ACTION="${1:-help}"
if [[ $# -gt 0 ]]; then shift; fi

help_text() {
  cat <<'HELP'
新版 UI 整体替换 — 本地 harness

用法：bash scripts/run-ui-harness.sh <操作> [运行参数]
  check    只检查配置，不启动模型、开发或测试
  start    从干净功能分支开始，每轮开发/测试交接自动提交
  status   查看本仓库最近一次完整 UI 任务
  stop     请求停止该任务，保留已完成的修改
  resume   继续该任务，重新规划并验收
  help     查看说明

start/resume 默认最多 12 轮、8 小时，单次 agent 最多 60 分钟。
可追加 --max-cycles N --max-seconds N --agent-timeout N 覆盖。
轮数和总时长分别设为 0 表示不限，单次 agent 超时仍生效。
status/stop/resume 只选择本任务的最近一次运行，不选择其他任务。
默认实时显示 agent 公开说明、工具结果和交接内容；追加 --quiet 可关闭。
保持运行终端打开；Ctrl+C 可中断，之后用 resume 继续。
HELP
}

case "$ACTION" in
  help|-h|--help) help_text; exit 0 ;;
  check|start|resume|status|stop) ;;
  *) echo "未知操作：$ACTION" >&2; help_text >&2; exit 2 ;;
esac
command -v python3 >/dev/null || { echo '未找到 python3。' >&2; exit 2; }
cd -- "$PROJECT_ROOT"
if [[ "$ACTION" == start || "$ACTION" == check || "$ACTION" == resume ]]; then
  git merge-base --is-ancestor origin/main HEAD || {
    echo '当前分支未包含 origin/main 基线，请先在功能分支合并主分支。' >&2
    exit 2
  }
fi

latest_run() {
  python3 - "$PROJECT_ROOT" "$TASK_ID" <<'PY'
import json
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
for directory in sorted((root / '.codex-harness/runs').glob('*'), reverse=True):
    if not directory.is_dir() or directory.is_symlink():
        continue
    try:
        state = json.loads((directory / 'status.json').read_text())
    except (OSError, ValueError):
        continue
    if (state.get('task_id') == sys.argv[2]
            and state.get('repo_root') == str(root)
            and state.get('run_dir') == str(directory)):
        print(directory)
        break
else:
    sys.exit('尚无完整 UI 任务运行记录。先使用 check 检查，再用 start 启动。')
PY
}

case "$ACTION" in
  check|start)
    [[ -f "$TASK_FILE" && -f "$HARNESS" ]] || { echo '任务文件或执行器缺失。' >&2; exit 2; }
    if [[ "$ACTION" == check ]]; then
      exec python3 "$HARNESS" run --task "$TASK_FILE" --git-checkpoints \
        --max-cycles 12 --max-seconds 28800 --agent-timeout 3600 "$@" --dry-run
    fi
    echo '启动：整站新版 UI + 现有业务接入 + 单份打印 + RGB 颜色管理。'
    echo '产品 Astra → 开发 Sol → 独立测试 Terra → 固定检查 → 产品复核。'
    echo '默认最多 12 轮 / 8 小时；每轮交接自动本地提交，不推送或部署。'
    exec python3 "$HARNESS" run --task "$TASK_FILE" --git-checkpoints \
      --max-cycles 12 --max-seconds 28800 --agent-timeout 3600 "$@"
    ;;
  status|stop)
    [[ $# == 0 ]] || { echo '此操作不接受额外参数。' >&2; exit 2; }
    RUN_DIR="$(latest_run)"
    exec python3 "$HARNESS" "$ACTION" --run-dir "$RUN_DIR"
    ;;
  resume)
    RUN_DIR="$(latest_run)"
    echo "继续运行：$RUN_DIR"
    exec python3 "$HARNESS" resume --run-dir "$RUN_DIR" --git-checkpoints \
      --max-cycles 12 --max-seconds 28800 --agent-timeout 3600 "$@"
    ;;
esac
