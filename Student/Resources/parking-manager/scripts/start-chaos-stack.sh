#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.runtime-logs"
mkdir -p "$LOG_DIR"
FRONTEND_DIR="$ROOT_DIR/frontend/parking-manager"

PIDS=()

ensure_dependencies() {
  local service_dir="$1"
  if [[ ! -d "$service_dir/node_modules" ]]; then
    echo "📦 Installing dependencies in $service_dir"
    (
      cd "$service_dir"
      npm install
    )
  fi
}

needs_frontend_build() {
  local build_index="$FRONTEND_DIR/build/index.html"

  if [[ "${FORCE_FRONTEND_BUILD:-0}" == "1" ]]; then
    return 0
  fi

  if [[ ! -f "$build_index" ]]; then
    return 0
  fi

  if find \
    "$FRONTEND_DIR/src" \
    "$FRONTEND_DIR/public" \
    -type f \
    -newer "$build_index" \
    -print -quit | grep -q .; then
    return 0
  fi

  if [[ "$FRONTEND_DIR/server.js" -nt "$build_index" ]] || \
     [[ "$FRONTEND_DIR/package.json" -nt "$build_index" ]] || \
     [[ "$FRONTEND_DIR/tsconfig.json" -nt "$build_index" ]]; then
    return 0
  fi

  return 1
}

start_service() {
  local name="$1"
  local service_dir="$2"
  local command="$3"

  echo "▶️  Starting $name"
  (
    cd "$service_dir"
    eval "$command" >"$LOG_DIR/${name}.log" 2>&1
  ) &

  local pid=$!
  PIDS+=("$pid")
  echo "   PID: $pid | log: $LOG_DIR/${name}.log"
}

cleanup() {
  echo
  echo "🛑 Stopping all services..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  wait || true
  echo "✅ All services stopped"
}

trap cleanup EXIT INT TERM

echo "🚀 Starting local chaos stack"
echo "   Workspace: $ROOT_DIR"

CHAOS_URL="${CHAOS_CONTROL_URL:-http://localhost:3090}"

ensure_dependencies "$ROOT_DIR/backend/chaos-control"
ensure_dependencies "$ROOT_DIR/backend/vm-health-control"
ensure_dependencies "$ROOT_DIR/backend/lisbon-parking-api"
ensure_dependencies "$ROOT_DIR/backend/madrid-parking-api"
ensure_dependencies "$ROOT_DIR/backend/paris-parking-api"
ensure_dependencies "$ROOT_DIR/backend/berlin-parking-api"
ensure_dependencies "$FRONTEND_DIR"

if needs_frontend_build; then
  echo "🏗️  Frontend changes detected. Building..."
  (
    cd "$FRONTEND_DIR"
    npm run build
  )
else
  echo "✅ Frontend build is up to date"
fi

start_service "chaos-control" "$ROOT_DIR/backend/chaos-control" "npm run start"
start_service "vm-health-control" "$ROOT_DIR/backend/vm-health-control" "npm run start"
start_service "lisbon-api" "$ROOT_DIR/backend/lisbon-parking-api" "CHAOS_CONTROL_URL='$CHAOS_URL' npm run start"
start_service "madrid-api" "$ROOT_DIR/backend/madrid-parking-api" "CHAOS_CONTROL_URL='$CHAOS_URL' npm run start"
start_service "paris-api" "$ROOT_DIR/backend/paris-parking-api" "CHAOS_CONTROL_URL='$CHAOS_URL' npm run start"
start_service "berlin-api" "$ROOT_DIR/backend/berlin-parking-api" "CHAOS_CONTROL_URL='$CHAOS_URL' npm run start"
start_service "frontend" "$FRONTEND_DIR" "REACT_APP_LISBON_API_URL='http://localhost:3001' REACT_APP_MADRID_API_URL='http://localhost:3002' REACT_APP_PARIS_API_URL='http://localhost:3003' REACT_APP_BERLIN_API_URL='http://localhost:3004' REACT_APP_CHAOS_CONTROL_URL='$CHAOS_URL' REACT_APP_VM_HEALTH_CONTROL_URL='http://localhost:3095' PORT='8080' node server.js"

echo

echo "✅ Chaos stack is running"
echo "   Frontend:      http://localhost:8080"
echo "   Chaos control: $CHAOS_URL/health"
echo "   Logs:          $LOG_DIR"
echo
echo "Press Ctrl+C to stop all services"

wait
