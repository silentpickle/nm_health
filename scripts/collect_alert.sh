#!/usr/bin/env bash
# Keep one open GitHub issue while the daily collect run is failing: open it on the first failure, comment on each
# repeat, close it on the next good run. GitHub's own failure email is easy to miss; an open issue is not.
# Called by collect.yml. Needs: GH_TOKEN, GH_REPO, RUN_URL, OUTCOME ("success" or "failure").
set -euo pipefail

readonly TITLE="Daily collect is failing"

open_issue() {
  gh issue list --state open --limit 100 --json number,title \
    --jq "map(select(.title == \"$TITLE\")) | .[0].number // empty"
}

report_failure() {
  local number="$1"
  if [ -n "$number" ]; then
    gh issue comment "$number" --body "Failed again: $RUN_URL"
    return
  fi
  gh issue create --title "$TITLE" --body "The daily collect run failed: $RUN_URL

The PDF is saved before anything parses it, so a failure in the site build loses no data, but the site stops
updating until it is fixed. This issue closes itself on the next good run."
}

main() {
  local number
  number="$(open_issue)"
  if [ "$OUTCOME" = "failure" ]; then
    report_failure "$number"
    return
  fi
  if [ -n "$number" ]; then
    gh issue close "$number" --comment "Recovered: $RUN_URL"
  fi
}

main
