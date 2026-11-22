#!/usr/bin/env python3
"""Desktop notification for new comments on the CurseForge project page.

Polls the public comments feed the CurseForge site itself uses
(www.curseforge.com/api/v1/mods/<id>/comments) and raises one notify-send
toast per new top-level comment. Seen comment ids live in
~/.local/state/forever-stuwave/curseforge-comments.json; the first run only
records what is already there. Each new comment is also appended to
curseforge-comments.log in the same folder.

Run by the forever-stuwave-comments.timer user unit (see
tools/systemd/). Run by hand with --test to fire a sample toast.
"""
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ID = 1820348
FEED = f"https://www.curseforge.com/api/v1/mods/{PROJECT_ID}/comments?page=0&size=50"
PAGE = "https://www.curseforge.com/wow/addons/forever-stuwave/comments"
STATE_DIR = Path.home() / ".local/state/forever-stuwave"
SEEN = STATE_DIR / "curseforge-comments.json"
LOG = STATE_DIR / "curseforge-comments.log"


def notify(title: str, body: str) -> None:
    subprocess.run(
        ["notify-send", "--app-name=Forever STUwave", "--icon=mail-unread", title, body],
        check=False,
    )


def fetch() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["data"]


def main() -> int:
    if "--test" in sys.argv:
        notify("CurseForge comment from tester", "This is what a new comment looks like.\n" + PAGE)
        return 0

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    first_run = not SEEN.exists()
    seen = set() if first_run else set(json.loads(SEEN.read_text()))

    try:
        comments = fetch()
    except Exception as exc:  # network or site change; say so in the journal, no toast
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1

    new = [c for c in comments if c["id"] not in seen]
    for c in sorted(new, key=lambda c: c.get("datePosted", 0)):
        who = c.get("author", {}).get("username", "someone")
        text = " ".join(c.get("text", "").split())
        when = datetime.fromtimestamp(c.get("datePosted", time.time() * 1000) / 1000)
        with LOG.open("a") as fh:
            fh.write(f"{when:%Y-%m-%d %H:%M} {who}: {text}\n")
        if not first_run:
            notify(f"CurseForge comment from {who}", (text[:200] + "...") if len(text) > 200 else text)

    seen.update(c["id"] for c in comments)
    SEEN.write_text(json.dumps(sorted(seen)))
    print(f"{len(comments)} comments, {len(new)} new" + (" (first run, recorded only)" if first_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
