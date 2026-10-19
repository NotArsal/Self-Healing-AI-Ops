#!/usr/bin/env bash
#
# `make offline` — the P8 offline rehearsal.
#
# ROADMAP P8 asks for: "no network, local model only, no GEMINI_API_KEY
# present". This runs the full four-act demo with every cloud provider key
# forced empty, PROVES they are empty inside the container rather than
# asserting it, and puts everything back afterwards.
#
# IT NEVER TOUCHES .env
# The obvious implementation edits .env, blanks the keys and writes them
# back at the end - and loses five real API keys the first time it is
# interrupted at the wrong moment. It is not worth the risk for a rehearsal.
#
# Docker Compose resolves `${VAR:-}` from the shell BEFORE --env-file, so
# exporting a variable empty overrides the file without modifying it.
# Verified 2026-10-19: `KAVACH_GEMINI_API_KEY= docker compose --env-file
# .env config` renders `KAVACH_GEMINI_API_KEY: ""` while .env still holds
# the key. The file is read-only throughout this script.
#
# THE NETWORK HALF NEEDS A HUMAN
# A script cannot honestly turn off its own machine's networking - and one
# that tried would be a worse idea than the test it is running. So it pauses
# and asks, when there is somebody there to ask. With --no-prompt it skips
# the pause and tests only the no-cloud-key half, which it then says
# plainly rather than claiming an offline run it did not do.
#
#   make offline                 interactive: pauses for you to pull the network
#   make offline ARGS=--no-prompt  unattended: keys-only, weaker claim, stated
#
set -u

# NOT WSL. `bash` on a Windows PATH is usually WSL's, and `make` under
# PowerShell shells out through cmd.exe, which picks exactly that one -
# observed 2026-10-19: "wsl: Failed to translate '\?\C'". WSL sees a
# different filesystem, has no uv and no Docker socket, so it would fail
# several steps in, after the trap had already recreated the API. Stop here.
if [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/version 2>/dev/null; then
  echo "FAILED: this is WSL bash, which cannot run the rehearsal."
  echo "        Open Git Bash in the repo and run 'make offline' there."
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

COMPOSE=(docker compose --env-file .env -f infra/docker-compose.yml)
API="http://127.0.0.1:8080"
ARTIFACT="harness/reports/scenario-offline.json"

# Every cloud key in the table. A provider added to llm/providers.py without
# a line here would silently stay reachable and quietly void the claim this
# script exists to make, so the list is checked against the table below.
CLOUD_KEYS=(
  KAVACH_OPENROUTER_API_KEY
  KAVACH_GROQ_API_KEY
  KAVACH_GEMINI_API_KEY
  KAVACH_OPENCODEZEN_API_KEY
  KAVACH_OLLAMACLOUD_API_KEY
  KAVACH_NVIDIA_API_KEY
  KAVACH_TOKENROUTER_API_KEY
)

say() { printf '%s\n' "$*"; }
die() { say "FAILED: $*"; exit 1; }

restore() {
  say ""
  say "--- restoring the normal configuration ---"
  # UNSET FIRST. These are still exported empty in this shell, and compose
  # resolves the shell before --env-file - which is the whole trick this
  # script runs on. Restoring without unsetting them brings the API back up
  # with the keys still blanked, silently, and the next person to use a
  # cloud provider finds it "unavailable" for no visible reason.
  for k in "${CLOUD_KEYS[@]}"; do unset "$k"; done
  "${COMPOSE[@]}" up -d --no-build --force-recreate api >/dev/null 2>&1
  for _ in $(seq 1 30); do
    curl -fsS "$API/v1/mode" >/dev/null 2>&1 && break
    sleep 2
  done
  if curl -fsS "$API/v1/mode" >/dev/null 2>&1; then
    say "    API back up with its usual keys. .env was never modified."
  else
    say "    WARNING: the API did not come back. Run 'make up'."
  fi
}
say "=============================================================================="
say "  OFFLINE REHEARSAL"
say "=============================================================================="

# --- the provider table must not have outgrown this script -------------------
TABLE_KEYS=$(uv --directory apps/control-plane run python -c "
from kavach.llm import providers
print(' '.join(sorted(s.key_env for s in providers.PROVIDERS.values())))" 2>/dev/null)
for k in $TABLE_KEYS; do
  case " ${CLOUD_KEYS[*]} " in
    *" $k "*) ;;
    *) die "providers.py has $k and this script does not blank it. Add it to CLOUD_KEYS." ;;
  esac
done
say "  provider table     $(echo "$TABLE_KEYS" | wc -w) keys, all covered"

# --- blast radius ------------------------------------------------------------
INWIN=$(docker exec kavach-postgres psql -U kavach -d kavach -t -A \
        -c "select count(*) from incidents where detected_at > now() - interval '1 hour';" \
        2>/dev/null | tr -d '[:space:]')
say "  incidents this hour ${INWIN:-?} of 5 (a run costs 4)"
if [ "${INWIN:-9}" -gt 1 ]; then
  say ""
  say "  REFUSING: permit() allows five incident starts an hour and this run"
  say "  needs four. Starting now would park acts on the blast-radius limiter"
  say "  and the rehearsal would fail for a reason that is not a defect."
  say "  Wait for the window to clear, then run again."
  exit 1
fi

# --- bring the API up with no cloud keys -------------------------------------
say ""
say "--- recreating the API with every cloud key empty ---"
# The trap goes up HERE, not at the top of the script. Armed earlier it
# fires on the pre-check refusals too, and "refused to start" would then
# recreate a container it never touched - which, with the compose file
# having changed this morning, is a real restart of a healthy API in the
# middle of whatever else is running.
trap restore EXIT INT TERM
for k in "${CLOUD_KEYS[@]}"; do export "$k="; done
"${COMPOSE[@]}" up -d --no-build --force-recreate api >/dev/null 2>&1 \
  || die "could not recreate the API"
for _ in $(seq 1 45); do
  curl -fsS "$API/v1/mode" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS "$API/v1/mode" >/dev/null 2>&1 || die "the API did not come up"

# --- PROVE it, inside the container ------------------------------------------
say ""
say "--- verifying, from inside the container ---"
LEAKED=0
for k in "${CLOUD_KEYS[@]}"; do
  v=$(docker inspect kavach-api --format "{{range .Config.Env}}{{println .}}{{end}}" \
      | grep "^$k=" | cut -d= -f2-)
  if [ -n "$v" ]; then
    say "    $k is STILL SET"
    LEAKED=1
  fi
done
[ "$LEAKED" -eq 0 ] || die "a cloud key reached the container; the claim would be false"
say "    no cloud key present       ${#CLOUD_KEYS[@]}/${#CLOUD_KEYS[@]} empty"

MODEL=$(curl -fsS "$API/v1/system" | python -c "
import json,sys
for d in json.load(sys.stdin)['dependencies']:
    if str(d.get('name','')).startswith('Ollama, Kavach'):
        print(str(d.get('detail','')).removeprefix('model ').strip()); break" 2>/dev/null)
BASE=$(grep -m1 '^KAVACH_LLM_BASE_URL=' .env | cut -d= -f2-)
say "    model                      ${MODEL:-UNKNOWN}"
say "    model endpoint             ${BASE:-compose default (host.docker.internal)}"
case "${BASE:-host.docker.internal}" in
  *localhost*|*127.0.0.1*|*host.docker.internal*) ;;
  *) die "KAVACH_LLM_BASE_URL is not local: $BASE" ;;
esac
[ -n "$MODEL" ] || die "/v1/system did not name a model"

# --- the human half ----------------------------------------------------------
OFFLINE_CLAIMED="keys only"
if [ "${1:-}" != "--no-prompt" ] && [ -t 0 ]; then
  say ""
  say "  >>> DISCONNECT THE NETWORK NOW (wifi off / cable out), then press Enter."
  say "      Everything the demo needs is local: the target, Prometheus and"
  say "      Ollama all run on this machine."
  read -r _
  OFFLINE_CLAIMED="network down + keys"
else
  say ""
  say "  NOT pausing for the network. This run proves only that the demo"
  say "  passes with no cloud key present - a weaker claim than the P8 box"
  say "  asks for, and recorded as such."
fi

# --- the demo ----------------------------------------------------------------
say ""
uv --directory apps/control-plane run python -I ../../harness/scenario.py \
   --name "offline-rehearsal" --json-out "../../$ARTIFACT"
RC=$?

if [ "${1:-}" != "--no-prompt" ] && [ -t 0 ]; then
  say ""
  say "  >>> RECONNECT THE NETWORK, then press Enter."
  read -r _
fi

say ""
say "=============================================================================="
if [ "$RC" -eq 0 ]; then
  say "  OFFLINE REHEARSAL: PASS   (claim: $OFFLINE_CLAIMED)"
else
  say "  OFFLINE REHEARSAL: FAIL   (scenario exit $RC)"
fi
say "  artifact $ARTIFACT"
say "=============================================================================="
exit "$RC"
