#!/usr/bin/env bash
# The bridge on a Docker host: installs it the first time, updates it after that.
# Run as root. It lives in /opt/docker/hotline-discord-bridge:
#   src/                the code (github.com/tagban/hotline_discord_bridge)
#   config.json         its settings and secrets (you put it here; mode 600, owned by uid 1000)
#   docker-compose.yml
# Run it again any time to pull the latest code and restart.
set -euo pipefail

DIR="${BRIDGE_DIR:-/opt/docker/hotline-discord-bridge}"
REPO="https://github.com/tagban/hotline_discord_bridge.git"
say() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || [ -n "${BRIDGE_DIR:-}" ] || { echo "Run this as root." >&2; exit 1; }
command -v docker >/dev/null || { echo "Docker isn't installed." >&2; exit 1; }
mkdir -p "$DIR"
cd "$DIR"

say "Code"
if [ -d src/.git ]; then git -C src pull --ff-only; else git clone --depth 1 "$REPO" src; fi
git -C src log -1 --format='%h %s (%cr)'

say "Settings"
if [ ! -f config.json ]; then
  cp src/config.example.json config.json
  chmod 600 config.json
  echo "There's no config.json yet, so I put the example at $DIR/config.json."
  echo "Fill it in (or upload your own over it), then run this again."
  exit 1
fi
if grep -q 'INSERT_' config.json; then
  echo "$DIR/config.json still has INSERT_... placeholders. Fill them in, then run this again."
  exit 1
fi
chown 1000:1000 config.json   # the container's user reads it
chmod 600 config.json
echo "Using $DIR/config.json"

cat > docker-compose.yml <<'YML'
# Written by src/deploy/vps-setup.sh; run that again to update.
services:
  hotline-discord-bridge:
    build: ./src
    image: hotline-discord-bridge:local
    container_name: hotline-discord-bridge
    restart: unless-stopped
    volumes:
      - ./config.json:/config/config.json:ro
    # A Hotline server on this same machine: "hotline_host": "host.docker.internal"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
YML

say "Starting"
docker compose up -d --build --force-recreate
sleep 10
docker compose ps
say "Log (docker compose -f $DIR/docker-compose.yml logs -f to follow)"
docker compose logs --tail 15
