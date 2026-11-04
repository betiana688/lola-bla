#!/usr/bin/env bash
# Save your work: ./save.sh "what changed"   (scans for secrets, commits, pushes, retries the push)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
DB="$HOME/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db"
git add -A
( umask 077; sqlite3 "$DB" "SELECT signal_number FROM accounts; SELECT signal_group_id FROM groups; SELECT signal_id FROM contacts;" | grep -v '^$' | sort -u > /tmp/lola_known.txt )
hits="$(git grep --cached -l -F -f /tmp/lola_known.txt || true)"
hits2="$(git grep --cached -lE 'hf_[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY' || true)"
rm -f /tmp/lola_known.txt
[ -z "$hits$hits2" ] || { echo "STOP: a real number or ID, a token or a key is in: $hits $hits2"; git reset -q; exit 1; }
if git diff --cached --quiet; then
  echo "Nothing new to commit."
else
  [ -n "${1:-}" ] || { echo 'Usage: ./save.sh "what changed"'; git reset -q; exit 1; }
  git diff --cached --stat | tail -1
  git commit -q -m "$1"
fi
for attempt in 1 2 3; do
  if git push -q; then break; fi
  if [ "$attempt" = 3 ]; then echo "Push failed 3 times. Your work is saved locally; run ./save.sh again later."; exit 1; fi
  echo "Push failed (attempt $attempt), retrying in 5 s..."; sleep 5
done
git log --oneline | head -2
git status -sb | head -1
echo "local: $(git rev-parse --short HEAD) | GitHub: $(git ls-remote origin main | cut -c1-7)"
