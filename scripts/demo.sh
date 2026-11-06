#!/usr/bin/env bash
# Runs the whole app on this machine for a demo, with no docker build:
#   Postgres + MinIO   two containers (docker compose up -d postgres minio), the only thing docker does
#   ML service         python (ml-service/.venv), port 8000
#   Backend            java -jar backend/target/*.jar, port 8080
#   Frontend           python http.server, port 4200
# The three app services are started detached (nohup setsid), so they keep running after this
# terminal or session closes. Logs and pids go to .demo/ (git-ignored).
#
#   scripts/demo.sh start     start everything and wait until it answers
#   scripts/demo.sh status    which parts answer
#   scripts/demo.sh stop      stop the three app services (Postgres and MinIO keep their data)
#
# Set APP_ADMIN_EMAILS=you@example.com to make that account an admin when it registers or logs in.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RUN=$ROOT/.demo
mkdir -p "$RUN"

is_up() { curl -s -o /dev/null --max-time 3 "$1"; }

wait_for() {  # name url seconds
  local name=$1 url=$2 limit=$3 waited=0
  until is_up "$url"; do
    sleep 2; waited=$((waited + 2))
    if [ "$waited" -ge "$limit" ]; then echo "  $name did not answer within ${limit}s; see $RUN/${name}.log" >&2; return 1; fi
  done
  echo "  $name is up"
}

start_detached() {  # name, then the command
  local name=$1; shift
  nohup setsid "$@" > "$RUN/$name.log" 2>&1 &
  echo $! > "$RUN/$name.pid"
}

start() {
  echo "Postgres and MinIO (docker):"
  (cd "$ROOT" && docker compose up -d postgres minio 2>&1 | tail -2)

  if is_up http://localhost:8000/health; then echo "ML service already running"; else
    echo "Starting the ML service (loads the models, about 20 s) ..."
    (cd "$ROOT/ml-service" && start_detached ml .venv/bin/uvicorn app.main:app --port 8000)
  fi
  if is_up http://localhost:8080/actuator/health; then echo "Backend already running"; else
    jar=$(ls "$ROOT"/backend/target/backend-*.jar 2>/dev/null | head -1 || true)
    [ -n "$jar" ] || { echo "No backend jar. Build it: cd backend && mvn -DskipTests package" >&2; exit 1; }
    echo "Starting the backend ..."
    (cd "$ROOT/backend" && APP_ADMIN_EMAILS="${APP_ADMIN_EMAILS:-}" start_detached backend java -Xmx512m -jar "$jar")
  fi
  if is_up http://localhost:4200/; then echo "Frontend already running"; else
    (cd "$ROOT" && start_detached frontend python3 -m http.server 4200 --directory frontend/src)
  fi

  wait_for ml http://localhost:8000/health 120
  wait_for backend http://localhost:8080/actuator/health 120
  wait_for frontend http://localhost:4200/ 20
  echo
  echo "Open http://localhost:4200"
}

stop() {
  for name in frontend backend ml; do
    if [ -f "$RUN/$name.pid" ]; then
      kill -- "-$(cat "$RUN/$name.pid")" 2> /dev/null || kill "$(cat "$RUN/$name.pid")" 2> /dev/null || true
      rm -f "$RUN/$name.pid"; echo "  stopped $name"
    fi
  done
}

status() {
  for pair in "postgres+minio:docker" "ml:http://localhost:8000/health" "backend:http://localhost:8080/actuator/health" "frontend:http://localhost:4200/"; do
    name=${pair%%:*}; url=${pair#*:}
    if [ "$url" = docker ]; then
      docker ps --format '{{.Names}}' 2> /dev/null | grep -q postgres && echo "  $name: running" || echo "  $name: NOT running (docker compose up -d postgres minio)"
    elif is_up "$url"; then echo "  $name: up"; else echo "  $name: down"; fi
  done
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
