# Mac backup collector

## Why it exists

The primary collector is the GitHub Actions workflow `.github/workflows/collect.yml`. It runs daily and archives the
city's weekly inspection PDF. The city overwrites one URL every week, so a missed week is lost for good. If Cloudflare
starts blocking GitHub's runners, nothing gets saved. This launchd job is a second collector that runs from a home
IP address. Duplicate archiving is harmless: the PDF is stored only if its bytes are new (dedupe by hash).

`scripts/collect_mac.sh` works in its own clone, never your working checkout. It runs `git pull --ff-only`,
`uv sync --frozen --no-dev` and `uv run --no-dev nm-health archive`. If `data/archive` changed, it commits only that
directory as a bot identity (`Archive inspection report <files> (Mac collector)`) and pushes. If the push is rejected
because GitHub's collector got there first, it does `git pull --rebase` once and pushes again. A rebase conflict
(for example on `manifest.jsonl`) is aborted, logged, and the script exits non-zero so a human can look.

## Prerequisites

- `uv` (`brew install uv`)
- `git`
- poppler, for `pdftotext` (`brew install poppler`)
- git access to the GitHub repo that works without a prompt (credential helper, `gh auth setup-git`, or an SSH key
  loaded for non-interactive use). The script needs no secrets of its own.

## Install

The repo must have a GitHub remote first.

```sh
REMOTE=git@github.com:OWNER/nm_health.git          # the repo's URL
SCRIPT="$PWD/scripts/collect_mac.sh"
LOG="$HOME/Library/Logs/nm-health-collector.log"
AGENT_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
PLIST="$HOME/Library/LaunchAgents/local.nm-health.collector.plist"

sed -e "s|__SCRIPT__|$SCRIPT|" -e "s|__LOG__|$LOG|" -e "s|__REMOTE__|$REMOTE|" -e "s|__PATH__|$AGENT_PATH|" \
  scripts/nm-health-collector.plist.template > "$PLIST"
plutil -lint "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
```

Test it now instead of waiting for 09:00 (the first run creates the clone):

```sh
launchctl kickstart -k "gui/$(id -u)/local.nm-health.collector"
```

If `uv` lives elsewhere (`command -v uv`), put its directory in `AGENT_PATH`. The `__REMOTE__` value is only used
on the first run; afterwards the clone's own `origin` is used.

## Logs

```sh
tail -f ~/Library/Logs/nm-health-collector.log
launchctl print "gui/$(id -u)/local.nm-health.collector" | rg 'last exit|state'
```

Each line is timestamped. "report unchanged; nothing to do" is the normal outcome on most days. A non-zero last exit
means look at the log: a failed `--ff-only` pull or a rebase conflict needs a human.

## Uninstall

```sh
launchctl bootout "gui/$(id -u)/local.nm-health.collector"
rm ~/Library/LaunchAgents/local.nm-health.collector.plist
rm -rf "$HOME/Library/Application Support/nm-health-collector"   # optional: deletes the private clone
```

## Awake only

launchd runs the job only while the Mac is awake. A calendar job whose time passed during sleep runs once on wake.
A Mac that is off or asleep all day misses that day, which is fine because the report stays up for a week.

## Settings for `config.toml`

Not yet in `config.toml`; the parent session should add them under `[mac_collector]`. Today they are fixed in the
script and plist template, or taken from environment variables.

| Key         | Suggested value                                                | Meaning                                                    |
|-------------|----------------------------------------------------------------|------------------------------------------------------------|
| `clone_dir` | `"~/Library/Application Support/nm-health-collector/repo"`     | Collector's private clone (env `NM_HEALTH_COLLECTOR_DIR`)  |
| `hour`      | `9`                                                            | Local hour of the daily run (`Hour` in the plist)          |
| `minute`    | `0`                                                            | Local minute of the daily run                              |
| `label`     | `"local.nm-health.collector"`                                   | launchd label                                              |
| `log_path`  | `"~/Library/Logs/nm-health-collector.log"`                      | Where launchd writes stdout and stderr                     |
| `bot_name`  | `"nm-health-mac-collector"`                                     | Commit author name                                         |
| `bot_email` | `"nm-health-mac-collector@users.noreply.github.com"`            | Commit author email                                        |
