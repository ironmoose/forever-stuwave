#!/usr/bin/env bash
# Build a tester zip of the Forever STUwave addon from COMMITTED HEAD (not the
# working tree). Output: dist/ForeverSTUwave-<toc Version>-<shortsha>-<date>.zip
# The zip's top folder is exactly ForeverSynthwave/ (Theme paths hardcode
# Interface\AddOns\ForeverSynthwave\...). Existing zips are never overwritten.
#
# Excluded (dev-only, same spirit as the deploy scripts): mockups/, __pycache__,
# *.md, *.py, *.png, *.bak, *-backup, .luacheckrc. The *.png files are only
# mockup previews; no .lua or .toc references them (the game art is all .tga).
# Kept: media/*.tga, fonts/*.ttf (+ OFL licence txt), libs/, all .lua, the .toc.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PYTHON="${PYTHON:-python3}"

for tool in zip unzip git python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: required tool not found: $tool" >&2; exit 1; }
done

SHA="$(git -C "$REPO" rev-parse --short HEAD)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Select committed runtime files explicitly. Developer tooling and prototypes
# remain in the repository but never enter the installed addon.
mapfile -t RUNTIME < <(git -C "$REPO" ls-tree -r --name-only HEAD | \
  "$PYTHON" -c 'import sys,re; print("\n".join(p for p in sys.stdin.read().splitlines() if re.fullmatch(r"[^/.][^/]*\.lua|ForeverSynthwave\.toc|Bindings\.xml|LICENSE|media/[^/]+\.tga|fonts/[^/]+\.ttf|fonts/(?:OFL|LICENSE|COPYING)(?:[-_][^/]+)?\.txt", p)))')
(( ${#RUNTIME[@]} > 0 )) || { echo "ERROR: no committed runtime files" >&2; exit 1; }
STAGE="$TMP/ForeverSynthwave"
mkdir -p "$STAGE"
git -C "$REPO" archive HEAD "${RUNTIME[@]}" | tar -x -C "$STAGE"

# Version comes from the staged copy (committed HEAD), not the working tree.
VERSION="$(sed -n 's/^## Version:[[:space:]]*//p' "$STAGE/ForeverSynthwave.toc" | tr -d '\r' | head -1)"
[[ -n "$VERSION" ]] || { echo "ERROR: no '## Version:' in the staged .toc" >&2; exit 1; }

# Every file the .toc loads must exist in what we ship.
echo "== toc check =="
missing=0
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%$'\r'}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "$line" || "$line" == \#* ]] && continue
  rel="${line//\\//}"
  if [[ ! -f "$STAGE/$rel" ]]; then
    echo "ERROR: .toc entry missing from the staged addon: $line" >&2
    missing=$((missing + 1))
  fi
done < "$STAGE/ForeverSynthwave.toc"
(( missing == 0 )) || { echo "ERROR: $missing .toc entries missing; no zip built." >&2; exit 1; }

# Parse gate (Lua 5.1 via lupa) over the exact files being shipped, libs included,
# then lint (HIGH only) on the top-level addon files, libs/ excluded (third party).
# Fails closed: no lupa means no gates, so no zip unless FS_SKIP_GATES=1.
if [[ "${FS_SKIP_GATES:-}" == "1" ]]; then
  echo "!!!!------------------------------------------------------------!!!!" >&2
  echo "WARNING: FS_SKIP_GATES=1 -- parse gate and lint gate are SKIPPED." >&2
  echo "A file that does not parse, or uses a local before declaring it, will" >&2
  echo "ship in this zip and silently take its component down in-client." >&2
  echo "!!!!------------------------------------------------------------!!!!" >&2
else
  if ! "$PYTHON" -c 'import lupa.luajit21' 2>/dev/null; then
    echo "ERROR: $PYTHON cannot import lupa.luajit21; the parse and lint gates cannot run." >&2
    echo "Install lupa for that python, or set PYTHON. (FS_SKIP_GATES=1 overrides, at your own risk.)" >&2
    exit 1
  fi
  echo "== parse gate =="
  mapfile -t LUA < <(find "$STAGE" -name '*.lua' | sort)
  "$PYTHON" "$SCRIPT_DIR/parse-gate.py" "${LUA[@]}" \
    || { echo "ERROR: parse gate failed; no zip built. (FS_SKIP_GATES=1 overrides.)" >&2; exit 1; }
  echo "== lint gate (HIGH findings block) =="
  mapfile -t TOP_LUA < <(find "$STAGE" -maxdepth 1 -name '*.lua' | sort)
  "$PYTHON" "$SCRIPT_DIR/lua-lint.py" --fail-on high "${TOP_LUA[@]}" \
    || { echo "ERROR: lua-lint reported HIGH findings; no zip built. (FS_SKIP_GATES=1 overrides.)" >&2; exit 1; }
fi

mkdir -p "$REPO/dist"
BASE="ForeverSTUwave-$VERSION-$SHA-$(date +%F)"
BUILT="$TMP/$BASE.zip"
(cd "$TMP" && zip -qr -X "$BUILT" ForeverSynthwave)

# Atomic, no-overwrite publish: mv -n never clobbers, so on a name clash (or a
# race with another run) leave the source in place and try the next suffix.
OUT="$REPO/dist/$BASE.zip"
n=2
while :; do
  [[ -e "$OUT" ]] || mv -n "$BUILT" "$OUT"
  [[ -e "$BUILT" ]] || break
  OUT="$REPO/dist/$BASE-$n.zip"
  n=$((n + 1))
done

echo "zip:   $OUT"
echo "size:  $(du -h "$OUT" | cut -f1) ($(stat -c %s "$OUT") bytes)"
echo "files: $(unzip -Z1 "$OUT" | grep -vc '/$')"
