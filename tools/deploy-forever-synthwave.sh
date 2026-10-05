#!/usr/bin/env bash
# Deploy the Forever STUwave addon from this repo to the live WoW Forever
# beta in the Fedora Lutris Battle.net prefix. WOW_ROOT can override the default
# for another installation.
#
# Usage:
#   ./deploy-forever-synthwave.sh          # deploy to the beta client
#   WOW_FLAVOR=_classic_ ./deploy-...sh    # deploy to TBC Anniversary instead
#   WOW_ROOT=/other/wow/root ./deploy-...sh  # override the install location
#   FS_SKIP_GATES=1 ./deploy-...sh         # install a trusted tester checkout without Python
#
# Pre-deploy gates (run before anything is copied; a failure aborts the deploy):
#   parse-gate.py  every .lua must compile as Lua 5.1 (a bad file is skipped
#                  silently by the client); also run over libs/**/*.lua
#   lua-lint.py --fail-on high
#                  HIGH findings only: a global read of a name that is declared
#                  `local` LATER in the file (use-before-declaration). Medium
#                  (unknown global) and low findings are shown but never block.
# Needs python3 with lupa. FS_SKIP_GATES=1 skips both, with a loud warning.
#
# After it runs: /reload in-client to pick up the new copy.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO/addon/ForeverSynthwave"

WOW_ROOT="${WOW_ROOT:-$HOME/Games/battlenet/drive_c/Program Files (x86)/World of Warcraft}"
WOW_FLAVOR="${WOW_FLAVOR:-_classic_beta_}"   # _classic_beta_ = Forever beta; _classic_ = TBC Anniversary
DST="$WOW_ROOT/$WOW_FLAVOR/Interface/AddOns/ForeverSynthwave/"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

if [[ "${FS_SKIP_GATES:-}" == "1" ]]; then
  echo "!!!!------------------------------------------------------------!!!!" >&2
  echo "WARNING: FS_SKIP_GATES=1 -- parse gate and lint gate are SKIPPED." >&2
  echo "A file that does not parse, or uses a local before declaring it, will" >&2
  echo "ship and silently take its component down in-client." >&2
  echo "!!!!------------------------------------------------------------!!!!" >&2
else
  echo "== parse gate =="
  if ! "$PYTHON" "$SCRIPT_DIR/parse-gate.py"; then
    echo "ERROR: parse gate failed; deploy aborted. Fix the files above." >&2
    echo "(FS_SKIP_GATES=1 overrides, at your own risk.)" >&2
    exit 1
  fi
  # rsync also ships libs/**, which the parse gate's default scan (top-level
  # *.lua) does not cover. Parse-check the vendored libs too; lint is NOT run
  # on them (third-party code, would be noise).
  echo "== parse gate (vendored libs) =="
  mapfile -t LIB_LUA < <(find "$SRC/libs" -name '*.lua' 2>/dev/null | sort)
  if (( ${#LIB_LUA[@]} > 0 )); then
    if ! "$PYTHON" "$SCRIPT_DIR/parse-gate.py" "${LIB_LUA[@]}"; then
      echo "ERROR: a vendored lib under libs/ does not parse; deploy aborted." >&2
      echo "(FS_SKIP_GATES=1 overrides, at your own risk.)" >&2
      exit 1
    fi
  fi
  echo "== lint gate (HIGH findings block; medium/low are informational) =="
  if ! "$PYTHON" "$SCRIPT_DIR/lua-lint.py" --fail-on high; then
    echo "ERROR: lua-lint reported HIGH findings (local used before its declaration)" >&2
    echo "or could not run; deploy aborted. Fix the files above." >&2
    echo "(FS_SKIP_GATES=1 overrides, at your own risk.)" >&2
    exit 1
  fi
fi

if [[ ! -d "$WOW_ROOT/$WOW_FLAVOR" ]]; then
  echo "ERROR: WoW client not found at: $WOW_ROOT/$WOW_FLAVOR" >&2
  echo "Is the Lutris Battle.net install present? Set WOW_ROOT/WOW_FLAVOR to override." >&2
  exit 1
fi

# Never mirror a source checkout onto itself or prune a tester's Git checkout.
SRC_REAL="$(realpath "$SRC")"
DST_REAL="$(realpath -m "$DST")"
if [[ "$DST_REAL" == "$REPO" || "$DST_REAL" == "$REPO/"* || "$DST_REAL" == "$SRC_REAL" || "$DST_REAL" == "$SRC_REAL/"* || -e "$DST/.git" ]]; then
  echo "ERROR: destination is a source/Git checkout. Move the checkout outside AddOns, then deploy." >&2
  exit 1
fi
mkdir -p "$DST"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp "$SRC"/*.lua "$SRC/ForeverSynthwave.toc" "$SRC/Bindings.xml" "$REPO/LICENSE" "$STAGE/"
mkdir -p "$STAGE/media" "$STAGE/fonts"
find "$SRC/media" -maxdepth 1 -name '*.tga' -exec cp -t "$STAGE/media" {} +
find "$SRC/fonts" -maxdepth 1 -type f \( -name '*.ttf' -o -name 'OFL*.txt' -o -name 'LICENSE*.txt' -o -name 'COPYING*.txt' \) -exec cp -t "$STAGE/fonts" {} +
rsync -a --delete "$STAGE/" "$DST"
echo "Deployed Forever STUwave -> $WOW_FLAVOR"
echo "  $DST"
echo "Restart the client when files were added; otherwise /reload."
