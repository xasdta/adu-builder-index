#!/bin/zsh
# Weekly data refresh: re-pull Seattle permits + WA licenses, rebuild site,
# push only if data actually changed. Run by com.aduindex.refresh (launchd).
set -euo pipefail
cd "$(dirname "$0")/.."
LOG=logs/refresh.log
mkdir -p logs
{
  echo "=== refresh $(date '+%Y-%m-%d %H:%M') ==="
  python3 pipeline/fetch_seattle.py
  python3 pipeline/fetch_bellevue.py
  python3 pipeline/build_rankings.py
  python3 pipeline/generate_site.py
  if [[ -n "$(git status --porcelain data docs)" ]]; then
    git add data docs
    git commit -m "Weekly data refresh $(date '+%Y-%m-%d')"
    git push
    echo "pushed refresh"
  else
    echo "no changes"
  fi
} >> "$LOG" 2>&1
