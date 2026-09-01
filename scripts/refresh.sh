#!/bin/zsh
# Weekly data refresh: re-pull permits + WA licenses, rebuild site, push only
# if data changed. Run by com.aduindex.refresh (launchd).
#
# launchd does NOT inherit an interactive PATH: bare `python3` resolves to
# /usr/bin/python3 (3.9), which cannot run the pipeline. Resolve an explicit
# interpreter and fail loudly if none is new enough.
set -euo pipefail
cd "$(dirname "$0")/.."
LOG=logs/refresh.log
mkdir -p logs

PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 || true)"; do
  [[ -x "$c" ]] || continue
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done

{
  echo "=== refresh $(date '+%Y-%m-%d %H:%M') ==="
  if [[ -z "$PY" ]]; then
    echo "FATAL: no python3 >= 3.12 found; pipeline not run"
    exit 1
  fi
  echo "using $PY ($("$PY" --version 2>&1))"
  "$PY" pipeline/fetch_seattle.py
  "$PY" pipeline/fetch_bellevue.py
  "$PY" pipeline/build_rankings.py
  "$PY" pipeline/generate_site.py
  if [[ -n "$(git status --porcelain data docs)" ]]; then
    git add data docs
    git commit -m "Weekly data refresh $(date '+%Y-%m-%d')"
    # The API endpoints commit data/*.json straight to origin, so this checkout
    # is routinely behind. Rebase before pushing or the push is rejected and
    # the refresh silently stops publishing.
    if ! git pull --rebase --autostash origin master; then
      echo "FATAL: rebase onto origin/master failed — resolve by hand"
      exit 1
    fi
    "$PY" pipeline/generate_site.py   # regenerate against the merged data
    if [[ -n "$(git status --porcelain data docs)" ]]; then
      git add data docs
      git commit --amend --no-edit
    fi
    git push
    echo "pushed refresh"
  else
    echo "no changes"
  fi
  echo "=== ok $(date '+%H:%M') ==="
} >> "$LOG" 2>&1
