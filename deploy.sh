#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="ubuntu"
APP_DIR="/home/ubuntu/watid_houda"
VENV="$APP_DIR/venv"
SERVICE="watid_houda"
BRANCH="${BRANCH:-master}"   # <-- mets ta branche par défaut ici
FLAG="/etc/nginx/maintenance.on"
GIT_SSH='ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'

log(){ echo -e "\n==> $*"; }
need_root(){ [[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }; }
enable_maintenance(){ touch "$FLAG"; nginx -t; systemctl reload nginx; }
disable_maintenance(){ rm -f "$FLAG" || true; nginx -t; systemctl reload nginx; }
as_app(){ sudo -u "$APP_USER" -H bash -lc "$*"; }

need_root
trap 'disable_maintenance' EXIT

log "Maintenance ON"; enable_maintenance

log "Prépare venv"
as_app "[[ -d '$VENV' ]] || python3 -m venv '$VENV'"
as_app "source '$VENV/bin/activate' && python -m pip install -U pip wheel"

ENV_SRC=""; [[ -f "$APP_DIR/.env" ]] && ENV_SRC="set -a; source '$APP_DIR/.env'; set +a;"

log "git fetch/pull ($BRANCH) avec clé SSH forcée"
as_app "cd '$APP_DIR' && $ENV_SRC GIT_SSH_COMMAND=\"$GIT_SSH\" git fetch origin '$BRANCH'"
as_app "cd '$APP_DIR' && GIT_SSH_COMMAND=\"$GIT_SSH\" git checkout -B '$BRANCH' origin/'$BRANCH' || git checkout '$BRANCH'"
as_app "cd '$APP_DIR' && GIT_SSH_COMMAND=\"$GIT_SSH\" git pull --ff-only origin '$BRANCH'"

if [[ -f "$APP_DIR/requirements.txt" ]]; then
  log "pip install -r requirements.txt"
  as_app "source '$VENV/bin/activate' && $ENV_SRC pip install -r '$APP_DIR/requirements.txt'"
fi

if as_app "source '$VENV/bin/activate' && command -v flask >/dev/null 2>&1"; then
  log "flask db upgrade"
  as_app "cd '$APP_DIR' && source '$VENV/bin/activate' && $ENV_SRC flask db upgrade"
fi

log "Restart service $SERVICE"
systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" || { journalctl -u "$SERVICE" -n 50 --no-pager; exit 1; }

log "Reload nginx"
nginx -t
systemctl reload nginx

log "OK (trap va couper la maintenance)"
