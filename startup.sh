#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${WASA_BACKEND_PORT:-8000}"
FRONTEND_PORT="${WASA_FRONTEND_PORT:-5173}"
HOST="${WASA_HOST:-127.0.0.1}"

RUNTIME_DIR="$ROOT_DIR/.runtime"
LOG_DIR="$RUNTIME_DIR/logs"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"

BACKEND_URL="http://$HOST:$BACKEND_PORT"
FRONTEND_URL="http://$HOST:$FRONTEND_PORT"

usage() {
  cat <<EOF
AKShare-wasa 快捷管理脚本

用法:
  ./startup.sh start      启动后端和前端
  ./startup.sh stop       关闭本项目的后端和前端
  ./startup.sh restart    重启后端和前端
  ./startup.sh status     查看运行状态

环境变量:
  WASA_BACKEND_PORT=8000
  WASA_FRONTEND_PORT=5173
  WASA_HOST=127.0.0.1
EOF
}

ensure_runtime_dirs() {
  mkdir -p "$LOG_DIR"
}

is_pid_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

pid_command() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null || true
}

port_pids() {
  local port="$1"
  lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u || true
}

pid_belongs_to_project() {
  local pid="$1"
  local command
  command="$(pid_command "$pid")"
  [[ "$command" == *"$ROOT_DIR"* ]] && return 0
  lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | grep -Fq "n$ROOT_DIR"
}

pid_is_descendant_of() {
  local pid="$1"
  local ancestor="$2"
  local parent

  while is_pid_running "$pid"; do
    parent="$(ps -p "$pid" -o ppid= 2>/dev/null | tr -d '[:space:]')"
    [[ -z "$parent" || "$parent" == "0" ]] && return 1
    [[ "$parent" == "$ancestor" ]] && return 0
    pid="$parent"
  done

  return 1
}

adopt_project_port_pid() {
  local port="$1"
  local pid_file="$2"
  local pid

  ensure_runtime_dirs
  for pid in $(port_pids "$port"); do
    if pid_belongs_to_project "$pid"; then
      echo "$pid" > "$pid_file"
      return 0
    fi
  done

  return 1
}

read_pid_file() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && tr -d '[:space:]' < "$pid_file" || true
}

python_bin() {
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    echo "$ROOT_DIR/.venv/bin/python"
  else
    command -v python3
  fi
}

start_detached() {
  local cwd="$1"
  local log_file="$2"
  shift 2

  "$(python_bin)" - "$cwd" "$log_file" "$@" <<'PY'
import os
import subprocess
import sys

cwd, log_file, *command = sys.argv[1:]
os.makedirs(os.path.dirname(log_file), exist_ok=True)
log = open(log_file, "ab", buffering=0)
process = subprocess.Popen(
    command,
    cwd=cwd,
    stdin=subprocess.DEVNULL,
    stdout=log,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
print(process.pid)
PY
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts=40

  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "✓ $label 已就绪: $url"
      return 0
    fi
    sleep 0.25
  done

  echo "⚠ $label 启动中，但健康检查暂未通过: $url"
  return 1
}

start_backend() {
  local pid

  pid="$(read_pid_file "$BACKEND_PID_FILE")"
  if is_pid_running "$pid"; then
    echo "✓ 后端已在运行 (PID $pid)"
    return 0
  fi

  if adopt_project_port_pid "$BACKEND_PORT" "$BACKEND_PID_FILE"; then
    pid="$(read_pid_file "$BACKEND_PID_FILE")"
    echo "✓ 后端已在运行，已接管 PID $pid"
    return 0
  fi

  if [[ -n "$(port_pids "$BACKEND_PORT")" ]]; then
    echo "✗ 后端端口 $BACKEND_PORT 已被非本项目进程占用，未启动。"
    lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN || true
    return 1
  fi

  if [[ ! -f "$ROOT_DIR/.venv/bin/activate" ]]; then
    echo "✗ 找不到虚拟环境: $ROOT_DIR/.venv"
    return 1
  fi

  ensure_runtime_dirs
  pid="$(
    start_detached \
      "$ROOT_DIR/backend" \
      "$LOG_DIR/backend.log" \
      bash -lc "source '$ROOT_DIR/.venv/bin/activate' && export PYTHONPATH=. && exec uvicorn app.main:app --reload --host '$HOST' --port '$BACKEND_PORT'"
  )"
  echo "$pid" > "$BACKEND_PID_FILE"
  echo "→ 后端启动中 (PID $pid, log: $LOG_DIR/backend.log)"
  wait_for_url "$BACKEND_URL/api/health" "后端" || true
}

start_frontend() {
  local pid

  pid="$(read_pid_file "$FRONTEND_PID_FILE")"
  if is_pid_running "$pid"; then
    echo "✓ 前端已在运行 (PID $pid)"
    return 0
  fi

  if adopt_project_port_pid "$FRONTEND_PORT" "$FRONTEND_PID_FILE"; then
    pid="$(read_pid_file "$FRONTEND_PID_FILE")"
    echo "✓ 前端已在运行，已接管 PID $pid"
    return 0
  fi

  if [[ -n "$(port_pids "$FRONTEND_PORT")" ]]; then
    echo "✗ 前端端口 $FRONTEND_PORT 已被非本项目进程占用，未启动。"
    lsof -nP -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN || true
    return 1
  fi

  if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
    echo "✗ 找不到前端依赖: $ROOT_DIR/frontend/node_modules"
    echo "  请先执行: cd frontend && npm install"
    return 1
  fi

  ensure_runtime_dirs
  pid="$(
    start_detached \
      "$ROOT_DIR/frontend" \
      "$LOG_DIR/frontend.log" \
      bash -lc "exec npm run dev -- --host '$HOST' --port '$FRONTEND_PORT' --strictPort"
  )"
  echo "$pid" > "$FRONTEND_PID_FILE"
  echo "→ 前端启动中 (PID $pid, log: $LOG_DIR/frontend.log)"
  wait_for_url "$FRONTEND_URL" "前端" || true
}

start_all() {
  start_backend
  start_frontend
  echo
  echo "打开前端: $FRONTEND_URL"
  echo "API 文档:  $BACKEND_URL/docs"
}

kill_pid_tree() {
  local pid="$1"
  local child

  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    kill_pid_tree "$child"
  done

  if is_pid_running "$pid"; then
    kill "$pid" 2>/dev/null || true
  fi
}

stop_service() {
  local label="$1"
  local pid_file="$2"
  local port="$3"
  local stopped=0
  local pid
  local candidates=()
  local owned_roots=()
  local owner
  local owned

  pid="$(read_pid_file "$pid_file")"
  if is_pid_running "$pid"; then
    candidates+=("$pid")
  fi

  for pid in $(port_pids "$port"); do
    candidates+=("$pid")
  done

  if [[ "${#candidates[@]}" -eq 0 ]]; then
    rm -f "$pid_file"
    echo "• $label 未运行"
    return 0
  fi

  for pid in $(printf "%s\n" "${candidates[@]}" | sort -u); do
    if is_pid_running "$pid" && pid_belongs_to_project "$pid"; then
      owned_roots+=("$pid")
    fi
  done

  for pid in $(printf "%s\n" "${candidates[@]}" | sort -u); do
    if ! is_pid_running "$pid"; then
      continue
    fi

    owned=0
    if pid_belongs_to_project "$pid"; then
      owned=1
    else
      for owner in "${owned_roots[@]}"; do
        if pid_is_descendant_of "$pid" "$owner"; then
          owned=1
          break
        fi
      done
    fi

    if [[ "$owned" -eq 1 ]]; then
      kill_pid_tree "$pid"
      stopped=1
      echo "✓ 已关闭 $label PID $pid"
    else
      echo "⚠ 跳过 $label 端口 $port 上的非本项目进程 PID $pid"
    fi
  done

  sleep 0.5
  rm -f "$pid_file"

  if [[ "$stopped" -eq 0 ]]; then
    echo "• $label 没有可关闭的本项目进程"
  fi
}

stop_all() {
  stop_service "前端" "$FRONTEND_PID_FILE" "$FRONTEND_PORT"
  stop_service "后端" "$BACKEND_PID_FILE" "$BACKEND_PORT"
}

service_status() {
  local label="$1"
  local pid_file="$2"
  local port="$3"
  local url="$4"
  local health_path="${5:-}"
  local pid
  local project_pids=()
  local other_pids=()

  pid="$(read_pid_file "$pid_file")"
  if is_pid_running "$pid"; then
    project_pids+=("$pid")
  fi

  for pid in $(port_pids "$port"); do
    if pid_belongs_to_project "$pid"; then
      project_pids+=("$pid")
    else
      other_pids+=("$pid")
    fi
  done

  project_pids=($(printf "%s\n" "${project_pids[@]:-}" | sed '/^$/d' | sort -u))
  other_pids=($(printf "%s\n" "${other_pids[@]:-}" | sed '/^$/d' | sort -u))

  echo "$label"
  if [[ "${#project_pids[@]}" -gt 0 ]]; then
    echo "  状态: 运行中"
    echo "  PID:  ${project_pids[*]}"
    echo "  URL:  $url"
  elif [[ "${#other_pids[@]}" -gt 0 ]]; then
    echo "  状态: 端口被非本项目进程占用"
    echo "  PID:  ${other_pids[*]}"
    echo "  URL:  $url"
  else
    echo "  状态: 未运行"
    echo "  URL:  $url"
  fi

  if [[ -n "$health_path" ]] && curl -fsS "$url$health_path" >/dev/null 2>&1; then
    echo "  健康检查: 通过"
  elif [[ -z "$health_path" ]] && curl -fsSI "$url" >/dev/null 2>&1; then
    echo "  健康检查: 通过"
  else
    echo "  健康检查: 未通过"
  fi
}

status_all() {
  service_status "后端" "$BACKEND_PID_FILE" "$BACKEND_PORT" "$BACKEND_URL" "/api/health"
  echo
  service_status "前端" "$FRONTEND_PID_FILE" "$FRONTEND_PORT" "$FRONTEND_URL"
  echo
  echo "日志目录: $LOG_DIR"
}

case "${1:-}" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    start_all
    ;;
  status)
    status_all
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "未知命令: $1"
    echo
    usage
    exit 1
    ;;
esac
