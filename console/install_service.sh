#!/usr/bin/env bash
# Run the Lola-Bla console as a systemd service. Starting at boot is a separate, optional switch.
#   ./console/install_service.sh              install the service and start it now (it does NOT start at boot yet)
#   ./console/install_service.sh --boot on    start it at every boot
#   ./console/install_service.sh --boot off   do not start it at boot
#   ./console/install_service.sh --start | --stop | --status
#   ./console/install_service.sh --remove     stop it, turn boot start off and delete the service
# The system parts use sudo. The service runs as the user who runs this script.
set -euo pipefail

UNIT="/etc/systemd/system/lola-console.service"
NAME="lola-console.service"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"
VENV="$HOME/lola-bla-agents/venv"
DATA="$HOME/lola-bla-agents/reachy_mini_conversation_app/local_data"
CONF="$HOME/.config/lola-bla"

boot_state() { systemctl is-enabled "$NAME" 2>/dev/null || true; }
need_unit() { [ -f "$UNIT" ] || { echo "The service is not installed yet. Run: ./console/install_service.sh"; exit 1; }; }
page_answers() {
  local code=""
  for _ in $(seq 1 12); do
    code="$(curl -sk -o /dev/null -w '%{http_code}' --max-time 3 https://localhost:9443/login || true)"
    [ "$code" = "200" ] && return 0
    sleep 1
  done
  echo "The console did not answer (last HTTP code: ${code:-none}). Last log lines:"
  sudo journalctl -u "$NAME" -n 30 --no-pager || true
  return 1
}
report() {
  if systemctl is-active --quiet "$NAME"; then echo "Running now: yes"; else echo "Running now: no"; fi
  if [ "$(boot_state)" = "enabled" ]; then echo "Starts at boot: yes (turn off with --boot off)"; else echo "Starts at boot: no (turn on with --boot on)"; fi
}

case "${1:-}" in
  --remove)
    sudo systemctl disable --now "$NAME" 2>/dev/null || true
    sudo rm -f "$UNIT"
    sudo systemctl daemon-reload
    echo "Removed. The console's data, certificate and settings were not touched."
    echo "Start it by hand again with: python3 console/run.py"
    exit 0 ;;
  --status)
    need_unit; report; exit 0 ;;
  --start)
    need_unit; sudo systemctl start "$NAME"
    page_answers || exit 1
    echo "The console is running: https://reachy-mini.local:9443/"; report; exit 0 ;;
  --stop)
    need_unit; sudo systemctl stop "$NAME"; echo "Stopped."; report; exit 0 ;;
  --boot)
    need_unit
    case "${2:-}" in
      on)  sudo systemctl enable "$NAME" > /dev/null 2>&1; echo "The console will start at every boot." ;;
      off) sudo systemctl disable "$NAME" > /dev/null 2>&1; echo "The console will not start at boot." ;;
      *)   echo "Use: --boot on   or   --boot off"; exit 1 ;;
    esac
    report; exit 0 ;;
  "") ;;
  *) echo "Unknown option: $1"; sed -n '2,9p' "${BASH_SOURCE[0]}"; exit 1 ;;
esac

[ -x "$VENV/bin/python" ] || { echo "Python environment not found: $VENV. Nothing changed."; exit 1; }
[ -d "$DATA" ] || { echo "Data folder not found: $DATA. Nothing changed."; exit 1; }
[ -f "$CONF/tls/cert.pem" ] || { echo "No certificate yet. Run: python3 console/manage.py make-cert. Nothing changed."; exit 1; }
[ -f "$CONF/console_secret.key" ] || { echo "No session key yet: start the console once by hand first. Nothing changed."; exit 1; }
[ "$(sqlite3 "$DATA/lola.db" 'SELECT COUNT(*) FROM users' 2>/dev/null || echo 0)" -ge 1 ] || { echo "No console user yet. Run: python3 console/manage.py create-user. Nothing changed."; exit 1; }
if ! systemctl is-active --quiet "$NAME" && ss -ltn | grep -q ':9443 '; then
  echo "Port 9443 is already in use (a console started by hand?). Stop it first with Ctrl+C there. Nothing changed."
  exit 1
fi

sudo tee "$UNIT" > /dev/null << EOF_UNIT
[Unit]
Description=Lola-Bla configuration console
After=network-online.target docker.service
Wants=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$REPO/console
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV/bin/python $REPO/console/run.py
Restart=on-failure
RestartSec=5
# Sandbox: the console may write only to the database folder and its own settings folder.
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$DATA $CONF
InaccessiblePaths=-$HOME/.ssh -$DATA/hf_token
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
CapabilityBoundingSet=
SystemCallArchitectures=native

[Install]
WantedBy=multi-user.target
EOF_UNIT

sudo systemctl daemon-reload
sudo systemctl restart "$NAME"
page_answers || { echo "To undo: ./console/install_service.sh --remove"; exit 1; }
echo "The console is running as a service: https://reachy-mini.local:9443/"
report
echo "  logs:    journalctl -u lola-console -n 50 --no-pager"
echo "  undo:    ./console/install_service.sh --remove"
