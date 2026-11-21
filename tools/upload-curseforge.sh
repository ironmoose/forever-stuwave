#!/usr/bin/env bash
# Upload a release of Forever STUwave to CurseForge (project 1820348).
#
# Builds the zip with tools/package-forever-stuwave.sh (comment strip, parse,
# lint and wording gates), takes this version's section of CHANGELOG.md as the
# file's changelog, looks up the game version from the .toc Interface number,
# and posts it to the CurseForge Upload API.
#
#   tools/upload-curseforge.sh            # upload
#   tools/upload-curseforge.sh --dry-run  # build and show what would be sent
#
# Token: $CURSEFORGE_TOKEN, else the file $CURSEFORGE_TOKEN_FILE (default
# .curseforge next to the repo), holding the token alone or as token=<value>.
# The token is passed to curl through a header file, never on a command line.
#
# Refuses when the addon folder differs from the v<version> tag, so a file on
# CurseForge always matches a tagged release.
set -euo pipefail

PROJECT_ID=1820348
API=https://wow.curseforge.com/api
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
TOC="$REPO/forever-stuwave/forever-stuwave.toc"

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

for tool in curl git python3 unzip; do
  command -v "$tool" >/dev/null || { echo "ERROR: $tool not found" >&2; exit 1; }
done

VER="$(tr -d '\r' < "$TOC" | sed -n 's/^## Version: *//p')"
IFACE="$(tr -d '\r' < "$TOC" | sed -n 's/^## Interface: *//p')"
[[ -n "$VER" && -n "$IFACE" ]] || { echo "ERROR: no Version or Interface in $TOC" >&2; exit 1; }

case "$VER" in
  *alpha*) RTYPE=alpha ;;
  *beta*)  RTYPE=beta ;;
  *)       RTYPE=release ;;
esac

TAG="v$VER"
git -C "$REPO" rev-parse -q --verify "refs/tags/$TAG" >/dev/null \
  || { echo "ERROR: tag $TAG does not exist; tag the release first." >&2; exit 1; }
if ! git -C "$REPO" diff --quiet "$TAG" HEAD -- forever-stuwave; then
  echo "ERROR: forever-stuwave/ at HEAD differs from $TAG; bump the version and tag, or check out the tag." >&2
  exit 1
fi

# This version's changelog section: from its heading to the next "## ".
CHANGELOG="$(awk -v v="$VER" '
  $0 ~ "^## " { if (found) exit; if (index($0, "## " v " ") == 1 || $0 == "## " v) { found = 1; next } }
  found { print }
' "$REPO/CHANGELOG.md" | sed -e '/./,$!d')"
[[ -n "$CHANGELOG" ]] || { echo "ERROR: no '## $VER' section in CHANGELOG.md" >&2; exit 1; }

# Token into a private header file.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if [[ -n "${CURSEFORGE_TOKEN:-}" ]]; then
  TOKEN="$CURSEFORGE_TOKEN"
else
  TF="${CURSEFORGE_TOKEN_FILE:-$REPO/../.curseforge}"
  [[ -r "$TF" ]] || { echo "ERROR: no CURSEFORGE_TOKEN and no readable token file $TF" >&2; exit 1; }
  TOKEN="$(tr -d '[:space:]' < "$TF" | sed 's/^[^=]*=//')"
fi
[[ -n "$TOKEN" ]] || { echo "ERROR: empty CurseForge token" >&2; exit 1; }
( umask 077; printf 'X-Api-Token: %s\n' "$TOKEN" > "$TMP/auth" )
unset TOKEN

# Game version id for this Interface number.
curl -fsS -H @"$TMP/auth" "$API/game/versions" -o "$TMP/versions.json" \
  || { echo "ERROR: could not read CurseForge game versions (bad token?)" >&2; exit 1; }
GV_ID="$(python3 - "$TMP/versions.json" "$IFACE" <<'PY'
import json, sys
vs = [v for v in json.load(open(sys.argv[1])) if str(v.get("apiVersion")) == sys.argv[2]]
print(vs[0]["id"] if len(vs) == 1 else "")
PY
)"
[[ -n "$GV_ID" ]] || { echo "ERROR: no single CurseForge game version for interface $IFACE" >&2; exit 1; }

# Build the zip from HEAD with the release gates.
OUT="$(uv run --project "$REPO" bash "$REPO/tools/package-forever-stuwave.sh" | tee /dev/stderr | sed -n 's/^zip: *//p')"
[[ -f "$OUT" ]] || { echo "ERROR: packager did not report a zip" >&2; exit 1; }
ZIP="$TMP/ForeverSTUwave-$VER.zip"
cp "$OUT" "$ZIP"
unzip -Z1 "$ZIP" | grep -qiE '(^|/)[^/]*\.md$' && { echo "ERROR: a .md file is in the zip" >&2; exit 1; }

printf '%s\n' "$CHANGELOG" > "$TMP/changelog.md"
python3 - "$TMP/metadata.json" "$TMP/changelog.md" "$VER" "$RTYPE" "$GV_ID" <<'PY'
import json, sys
out, log, ver, rtype, gv = sys.argv[1:]
json.dump({"changelog": open(log).read(), "changelogType": "markdown",
           "displayName": f"Forever STUwave {ver}", "gameVersions": [int(gv)],
           "releaseType": rtype}, open(out, "w"))
PY

echo
echo "version:  $VER ($RTYPE), interface $IFACE -> game version id $GV_ID"
echo "file:     $(basename "$ZIP") ($(stat -c %s "$ZIP") bytes, $(unzip -Z1 "$ZIP" | grep -vc '/$') files)"
echo "changelog:"
printf '%s\n' "$CHANGELOG" | sed 's/^/  | /'

if (( DRY )); then
  echo
  echo "dry run: nothing uploaded"
  exit 0
fi

HTTP="$(curl -sS -H @"$TMP/auth" -o "$TMP/resp.json" -w '%{http_code}' \
  -F "metadata=<$TMP/metadata.json;type=application/json" \
  -F "file=@$ZIP;type=application/zip" \
  "$API/projects/$PROJECT_ID/upload-file")"
if [[ "$HTTP" != 200 ]]; then
  echo "ERROR: upload failed, HTTP $HTTP: $(cat "$TMP/resp.json")" >&2
  exit 1
fi
echo
echo "uploaded: CurseForge file id $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$TMP/resp.json")"
