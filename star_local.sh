#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.local_runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_DIR="$RUNTIME_DIR/pids"

BLACKJACK_PORT="${BLACKJACK_PORT:-5101}"
YAHTZEE_PORT="${YAHTZEE_PORT:-5102}"
MATH_PORT="${MATH_PORT:-5103}"
HUB_PORT="${HUB_PORT:-8080}"
HOST_BIND="${HOST_BIND:-0.0.0.0}"

mkdir -p "$LOG_DIR" "$PID_DIR"

usage() {
  cat <<'EOF'
Usage:
  ./star_local.sh start    # Start all local services
  ./star_local.sh stop     # Stop all local services
  ./star_local.sh status   # Show service status
  ./star_local.sh restart  # Restart all local services

Optional environment variables:
  BLACKJACK_PORT (default: 5101)
  YAHTZEE_PORT   (default: 5102)
  MATH_PORT      (default: 5103)
  HUB_PORT       (default: 8080)
  HOST_BIND      (default: 0.0.0.0)
EOF
}

is_running() {
  local pid_file="$1"
  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_one() {
  local name="$1"
  local cwd="$2"
  local pid_file="$PID_DIR/$name.pid"
  local log_file="$LOG_DIR/$name.log"
  shift 2

  if is_running "$pid_file"; then
    echo "[$name] already running (PID $(cat "$pid_file"))."
    return 0
  fi

  rm -f "$pid_file"
  (
    cd "$cwd"
    nohup "$@" >"$log_file" 2>&1 &
    echo $! >"$pid_file"
  )

  if is_running "$pid_file"; then
    echo "[$name] started (PID $(cat "$pid_file"))"
    echo "[$name] log: $log_file"
  else
    echo "[$name] failed to start. Check $log_file"
    return 1
  fi
}

stop_one() {
  local name="$1"
  local pid_file="$PID_DIR/$name.pid"

  if ! is_running "$pid_file"; then
    rm -f "$pid_file"
    echo "[$name] not running."
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"
  kill "$pid" 2>/dev/null || true

  for _ in {1..20}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$pid_file"
      echo "[$name] stopped."
      return 0
    fi
    sleep 0.2
  done

  kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  echo "[$name] force-stopped."
}

print_status_one() {
  local name="$1"
  local pid_file="$PID_DIR/$name.pid"
  if is_running "$pid_file"; then
    echo "[$name] running (PID $(cat "$pid_file"))"
  else
    echo "[$name] stopped"
  fi
}

require_file() {
  local file="$1"
  local hint="$2"
  if [[ ! -f "$file" ]]; then
    echo "Missing: $file"
    echo "Hint: $hint"
    exit 1
  fi
}

print_urls() {
  local lan_ip
  lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -z "$lan_ip" ]]; then
    lan_ip="YOUR_UBUNTU_IP"
  fi

  echo
  echo "Open locally:"
  echo "  Hub:       http://localhost:$HUB_PORT"
  echo "  Blackjack: http://localhost:$BLACKJACK_PORT"
  echo "  Yahtzee:   http://localhost:$YAHTZEE_PORT"
  echo "  DailyMath: http://localhost:$MATH_PORT"
  echo
  echo "Open from another device:"
  echo "  Hub:       http://$lan_ip:$HUB_PORT"
}

start_all() {
  require_file "$ROOT_DIR/blackjack-game/.venv/bin/python" "Create venv in blackjack-game and install requirements."
  require_file "$ROOT_DIR/yahtzee-game/.venv/bin/python" "Create venv in yahtzee-game and install requirements."
  require_file "$ROOT_DIR/Daily_math_games_v2/.venv/bin/python" "Create venv in Daily_math_games_v2 and install requirements."
  require_file "$ROOT_DIR/home-page/index.html" "The homepage file should exist at home-page/index.html."

  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "[daily-math] OPENAI_API_KEY is not set. App will run, but /generate will fail until key is set."
  fi

  start_one "blackjack" "$ROOT_DIR/blackjack-game" \
    env PORT="$BLACKJACK_PORT" "$ROOT_DIR/blackjack-game/.venv/bin/python" app.py

  start_one "yahtzee" "$ROOT_DIR/yahtzee-game" \
    env PORT="$YAHTZEE_PORT" "$ROOT_DIR/yahtzee-game/.venv/bin/python" app.py

  start_one "daily-math" "$ROOT_DIR/Daily_math_games_v2" \
    env OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
    "$ROOT_DIR/Daily_math_games_v2/.venv/bin/python" -m uvicorn app.main:app --host "$HOST_BIND" --port "$MATH_PORT"

  start_one "home-page" "$ROOT_DIR" \
    python3 -m http.server "$HUB_PORT" --bind "$HOST_BIND" --directory home-page

  print_urls
  echo
  echo "Logs: $LOG_DIR"
  echo "Stop all: ./star_local.sh stop"
}

stop_all() {
  stop_one "home-page"
  stop_one "daily-math"
  stop_one "yahtzee"
  stop_one "blackjack"
}

status_all() {
  print_status_one "blackjack"
  print_status_one "yahtzee"
  print_status_one "daily-math"
  print_status_one "home-page"
}

ACTION="${1:-start}"

case "$ACTION" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  status)
    status_all
    ;;
  restart)
    stop_all
    start_all
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
