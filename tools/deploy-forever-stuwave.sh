#!/usr/bin/env bash
# Install the runtime addon; migrate legacy settings while preserving originals.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO/forever-stuwave"
SCRIPT_DIR="$REPO/tools"
PYTHON="${PYTHON:-python3}"
WOW_ROOT="${WOW_ROOT:-$HOME/Games/battlenet/drive_c/Program Files (x86)/World of Warcraft}"
WOW_FLAVOR="${WOW_FLAVOR:-_classic_beta_}"
CLIENT="$WOW_ROOT/$WOW_FLAVOR"
DST="$CLIENT/Interface/AddOns/forever-stuwave"
LEGACY="$CLIENT/Interface/AddOns/ForeverSynthwave"

[[ -d "$CLIENT" ]] || { echo "ERROR: client not found at $CLIENT" >&2; exit 1; }
DST_REAL="$(realpath -m "$DST")"
if [[ "$DST_REAL" == "$REPO" || "$DST_REAL" == "$REPO/"* || -e "$DST/.git" || -e "$LEGACY/.git" ]]; then
  echo "ERROR: destination or legacy addon is a Git checkout; move it outside AddOns first." >&2
  exit 1
fi
if [[ "${FS_SKIP_GATES:-}" == "1" ]]; then
  echo "Installing trusted checkout without parse/lint gates."
else
  "$PYTHON" "$SCRIPT_DIR/parse-gate.py"
  "$PYTHON" "$SCRIPT_DIR/lua-lint.py" --fail-on high
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
while IFS= read -r -d '' runtime; do
  rel="${runtime#"$SRC/"}"
  mkdir -p "$STAGE/$(dirname "$rel")"
  cp -p "$runtime" "$STAGE/$rel"
done < <(find "$SRC/Core" "$SRC/Modules" -type f -name '*.lua' -print0;
  find "$SRC/Media/Textures" -type f -name '*.tga' -print0;
  find "$SRC/Media/Fonts" -type f \( -name '*.ttf' -o -name 'OFL*.txt' -o -name 'LICENSE*.txt' -o -name 'COPYING*.txt' \) -print0)
cp "$SRC/forever-stuwave.toc" "$SRC/Bindings.xml" "$REPO/LICENSE" "$STAGE/"

# Legacy source settings are retained; a newer destination always wins.
if [[ -d "$CLIENT/WTF/Account" ]]; then
  while IFS= read -r -d '' saved; do
    suffix="${saved##*ForeverSynthwave.lua}"
    target="$(dirname "$saved")/forever-stuwave.lua$suffix"
    if [[ ! -e "$target" ]]; then
      temporary="$(mktemp "$(dirname "$saved")/.forever-stuwave-XXXXXXXX")"
      if sed 's/ForeverSynthwave/ForeverSTUwave/g' "$saved" > "$temporary"; then
        mv -n "$temporary" "$target"
        [[ ! -e "$temporary" ]] || rm "$temporary"
      else
        rm "$temporary"
        exit 1
      fi
    fi
  done < <(find "$CLIENT/WTF/Account" -type f \( -path '*/SavedVariables/ForeverSynthwave.lua' -o -path '*/SavedVariables/ForeverSynthwave.lua.bak' \) -print0)
  while IFS= read -r -d '' bindings; do
    if grep -q 'ForeverSynthwave' "$bindings"; then
      [[ -e "$bindings.forever-stuwave.bak" ]] || cp -p "$bindings" "$bindings.forever-stuwave.bak"
      temporary="$(mktemp "$(dirname "$bindings")/.forever-stuwave-XXXXXXXX")"
      cp -p "$bindings" "$temporary"
      if sed 's/ForeverSynthwave/ForeverSTUwave/g' "$bindings" > "$temporary"; then
        mv "$temporary" "$bindings"
      else
        rm "$temporary"
        exit 1
      fi
    fi
  done < <(find "$CLIENT/WTF/Account" -type f -name bindings-cache.wtf -print0)
fi
if [[ -d "$LEGACY" ]]; then
  RETIRED="$CLIENT/Interface/RetiredAddOns"
  mkdir -p "$RETIRED"
  ARCHIVE="$(mktemp -d "$RETIRED/ForeverSynthwave-XXXXXXXX")"
  rmdir "$ARCHIVE"
  mv "$LEGACY" "$ARCHIVE"
fi
mkdir -p "$DST"
rsync -a --delete "$STAGE/" "$DST/"
echo "Installed Forever STUwave -> $DST"
echo "Fully restart WoW."
