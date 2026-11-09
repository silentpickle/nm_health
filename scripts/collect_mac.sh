#!/usr/bin/env bash
# Backup collector for macOS (run by launchd). Keeps its own clone, archives the city's PDF, pushes if new.
# Settings: NM_HEALTH_COLLECTOR_DIR (clone dir), NM_HEALTH_REMOTE (git URL, needed only to create the clone).
set -euo pipefail

readonly DEFAULT_CLONE_DIR="$HOME/Library/Application Support/nm-health-collector/repo"
readonly CLONE_DIR="${NM_HEALTH_COLLECTOR_DIR:-$DEFAULT_CLONE_DIR}"
readonly REMOTE="${NM_HEALTH_REMOTE:-}"
readonly ARCHIVE_DIR="data/archive"
readonly BOT_NAME="nm-health-mac-collector"
readonly BOT_EMAIL="nm-health-mac-collector@users.noreply.github.com"
readonly EXIT_FAIL=1

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*"
}

die() {
  log "ERROR: $*"
  exit "$EXIT_FAIL"
}

repo() {
  git -C "$CLONE_DIR" "$@"
}

ensure_clone() {
  if [ -d "$CLONE_DIR/.git" ]; then
    return 0
  fi
  [ -n "$REMOTE" ] || die "no clone at '$CLONE_DIR' and NM_HEALTH_REMOTE is not set; set it to the repo's git URL for the first run"
  log "cloning $REMOTE into $CLONE_DIR"
  mkdir -p "$(dirname "$CLONE_DIR")"
  git clone "$REMOTE" "$CLONE_DIR"
}

update_clone() {
  log "pulling (fast-forward only)"
  repo pull --ff-only || die "git pull --ff-only failed; leaving the clone untouched"
}

run_archive() {
  cd "$CLONE_DIR"
  uv sync --frozen --no-dev
  uv run --no-dev nm-health archive
}

new_pdf_names() {
  repo status --porcelain -- "$ARCHIVE_DIR" | awk '$NF ~ /\.pdf$/ {print $NF}' | xargs -n1 basename | tr '\n' ' ' | sed 's/ $//'
}

commit_new() {
  local names
  names="$(new_pdf_names)"
  repo add -- "$ARCHIVE_DIR"
  repo -c user.name="$BOT_NAME" -c user.email="$BOT_EMAIL" \
    commit -m "Archive inspection report $names (Mac collector)" -- "$ARCHIVE_DIR"
}

push_with_retry() {
  if repo push; then
    return 0
  fi
  log "push rejected; rebasing once onto the remote"
  if ! repo -c user.name="$BOT_NAME" -c user.email="$BOT_EMAIL" pull --rebase; then
    repo rebase --abort || true
    die "rebase conflict (likely manifest.jsonl); aborted, a human needs to look"
  fi
  repo push || die "push failed after rebase"
}

main() {
  ensure_clone
  update_clone
  run_archive
  if [ -z "$(repo status --porcelain -- "$ARCHIVE_DIR")" ]; then
    log "report unchanged; nothing to do"
    return 0
  fi
  commit_new
  push_with_retry
  log "done"
}

main "$@"
