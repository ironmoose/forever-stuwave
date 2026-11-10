#!/usr/bin/env python3
"""Keeps every WoW taint log that records a blocked action, before a /reload wipes it.

The client writes Logs/taint.log while taintLog is on (ErrorLog.lua turns it on at
every login) and truncates the file each time the UI loads, so a block recorded
before a /reload is gone a second later. This polls the file once a second, keeps
the current contents in memory, and whenever they contain a blocked or forbidden
action line, writes them to debug/taint/taint-<start>.log (one file per UI load,
rewritten as it grows). A truncation starts a new capture.

    python3 tools/taint-watch.py            # runs until stopped
    python3 tools/taint-watch.py --once     # one pass, for tests

Exit 0 on --once. Reads only; never touches the client's files.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = Path.home() / "Games/battlenet/drive_c/Program Files (x86)/World of Warcraft/_forever_/Logs/taint.log"
DEFAULT_OUT = ROOT / "debug/taint"

# The client's wording for a refused protected call, plus the action names our error log has seen.
BLOCK = re.compile(r"blocked|forbidden|UseContainerItem|ADDON_ACTION", re.IGNORECASE)


class Watcher:
    def __init__(self, log: Path, out: Path) -> None:
        self.log, self.out = log, out
        self.ident: tuple[int, int] | None = None  # (inode, device) of the file being followed
        self.buf = b""
        self.started = ""
        self.saved_len = 0

    def _new_capture(self) -> None:
        self.buf, self.saved_len = b"", 0
        self.started = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    def poll(self) -> Path | None:
        """One pass. Returns the capture file written this pass, if any."""
        try:
            st = os.stat(self.log)
        except FileNotFoundError:
            return None
        ident = (st.st_ino, st.st_dev)
        if ident != self.ident or st.st_size < len(self.buf):
            # Rotated or truncated: what we held is already saved if it had a block.
            self.ident = ident
            self._new_capture()
        if st.st_size > len(self.buf):
            with open(self.log, "rb") as f:
                f.seek(len(self.buf))
                self.buf += f.read(st.st_size - len(self.buf))
        if len(self.buf) == self.saved_len or not BLOCK.search(self.buf.decode("utf-8", "replace")):
            return None
        self.out.mkdir(parents=True, exist_ok=True)
        dest = self.out / f"taint-{self.started}.log"
        dest.write_bytes(self.buf)
        self.saved_len = len(self.buf)
        return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    w = Watcher(args.log, args.out)
    if args.once:
        dest = w.poll()
        if dest:
            print(dest)
        return 0
    print(f"watching {args.log} -> {args.out}", flush=True)
    while True:
        dest = w.poll()
        if dest:
            print(f"{datetime.now():%H:%M:%S} saved {dest} ({w.saved_len} bytes)", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
