#!/usr/bin/env bash
# Fresh install of Lola-Bla. Run from the repo: ./app/install.sh
# Needs: git, python3, sqlite3 (and sox, ffmpeg, docker to actually run it).
#   LOLA_WORKDIR   where to install (default ~/lola-bla-agents)
#   LOLA_SKIP_PIP  set to 1 to skip the Python environment (used to test this script)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${LOLA_WORKDIR:-$HOME/lola-bla-agents}"
CLONE="$WORK/reachy_mini_conversation_app"
COMMIT="$(tr -d '[:space:]' < "$REPO/app/patches/POLLEN_COMMIT")"

for tool in git python3 sqlite3; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool"; exit 1; }
done
if [ -e "$CLONE" ]; then
  echo "$CLONE already exists. Move it away first. Nothing changed."
  exit 1
fi

echo "== Pollen's app, pinned to $COMMIT"
mkdir -p "$WORK"
git clone --quiet https://github.com/pollen-robotics/reachy_mini_conversation_app.git "$CLONE"
git -C "$CLONE" checkout --quiet "$COMMIT"
git -C "$CLONE" apply "$REPO/app/patches/pollen-conversation-app.patch"

echo "== Our code (links into this repo, so there is one copy of each file)"
mkdir -p "$CLONE/local_data" "$CLONE/profiles/lola"
chmod 700 "$CLONE/local_data"
for f in messaging_executor.py messaging_agent.py background_sync.py; do
  ln -sfn "$REPO/app/local_data/$f" "$CLONE/local_data/$f"
done
for f in handle_messaging_task.py test_mic_handoff.py sleep_robot.py; do
  ln -sfn "$REPO/app/tools/$f" "$CLONE/src/reachy_mini_conversation_app/tools/$f"
done
ln -sfn "$REPO/profiles/lola/profile.md" "$CLONE/profiles/lola/profile.md"

echo "== Data (stays on this machine, outside the repo)"
mkdir -p "$CLONE/local_data/audio"
chmod 700 "$CLONE/local_data/audio"
sqlite3 "$CLONE/local_data/lola.db" < "$REPO/app/local_data/schema.sql"
chmod 600 "$CLONE/local_data/lola.db"

if [ -z "${LOLA_SKIP_PIP:-}" ]; then
  echo "== Python environment"
  python3 -m venv "$WORK/venv"
  "$WORK/venv/bin/python" -m pip install --upgrade pip
  "$WORK/venv/bin/python" -m pip install -e "$CLONE" requests
fi

cat << 'NEXT'

Installed. Still to do by hand:
  1. System tools: sox, ffmpeg, docker (check: command -v sox ffmpeg docker)
  2. Start the Signal API container and link your Signal account (not automated yet)
  3. Create local_data/hf_token (the messaging assistant's own token), mode 600
  4. Add your account and groups to the database (the config console will do this once built)
  5. Log in to Hugging Face (hf auth login), then start the app:
       REACHY_MINI_CUSTOM_PROFILE=lola reachy-mini-conversation-app --no-camera
NEXT
