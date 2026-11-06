#!/usr/bin/env bash
# Runs ON the beta VM (deploy/README.md), from a clone of the repository:
#
#   bash deploy/setup.sh docker            install Docker and the compose plugin
#   bash deploy/setup.sh env ADMIN_EMAIL   write deploy/.env: this VM's sslip.io address
#                                          and fresh random secrets (kept if .env exists)
#   bash deploy/setup.sh up                build and start the stack
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"

install_docker() {
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker.io docker-compose-v2 > /dev/null
  sudo usermod -aG docker "$USER"
  docker --version || sudo docker --version
}

write_env() {
  local admin=${1:-}
  if [ -f "$DIR/.env" ]; then
    echo "deploy/.env exists; keeping it (its secrets protect existing data)."
    return
  fi
  local ip
  ip=$(curl -s -H 'Metadata-Flavor: Google' \
    http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip)
  secret() { head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 40; }
  sed -e "s|^SITE_ADDRESS=.*|SITE_ADDRESS=${ip//./-}.sslip.io|" \
      -e "s|^APP_ADMIN_EMAILS=.*|APP_ADMIN_EMAILS=$admin|" \
      -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(secret)|" \
      -e "s|^MINIO_ROOT_PASSWORD=.*|MINIO_ROOT_PASSWORD=$(secret)|" \
      -e "s|^JWT_SECRET=.*|JWT_SECRET=$(secret)$(secret)|" \
      "$DIR/.env.example" > "$DIR/.env"
  chmod 600 "$DIR/.env"
  grep '^SITE_ADDRESS=' "$DIR/.env"
}

up() {
  (cd "$DIR" && sudo docker compose up -d --build)
  (cd "$DIR" && sudo docker compose ps)
}

case "${1:-}" in
  docker) install_docker ;;
  env) write_env "${2:-}" ;;
  up) up ;;
  *) echo "usage: bash deploy/setup.sh docker|env ADMIN_EMAIL|up" >&2; exit 2 ;;
esac
