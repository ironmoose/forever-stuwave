#!/usr/bin/env python3
"""Cross-references the Blizzard frame names the addon reaches for against a dump
of all globals from the live 16001 client.

Why: most of the review queue is "PANEL skin the X frame". A skin aimed at a
frame that does not exist here is a silent no-op, and on a 12.0-era engine
carrying TBC content a lot of old FrameXML names are gone. Those tasks should be
closed or re-pointed, not given a review slot.

CRITICAL CAVEAT, and the reason this script does not just print present/absent:
the dump was taken automatically at PLAYER_ENTERING_WORLD, so every
LOAD-ON-DEMAND frame was guaranteed absent at that moment whether or not it
exists. Absence is therefore only evidence for frames that should be there at
login. Names are classified:

  AT LOGIN      in the dump. Target exists; the skin had something to bite on.
  LOD          absent, but owned by a Blizzard_* module that loads on first use.
                Unknowable from this dump. Settle it by opening the window once.
  LEGACY        absent, and a pre-modern name with a known modern replacement.
                Almost certainly gone. Check the module also lists the new name.
  UNKNOWN       absent and unclassified. Worth a look.

    python tools/frame-audit.py
    python tools/frame-audit.py --module Panels.lua
"""

from __future__ import annotations

import re
import sys
import os
from pathlib import Path

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
GLOBALS_DUMP = Path(os.environ.get("FS_GLOBALS_DUMP", ADDON / "reference" / "globals.txt"))

# Only strings the addon actually uses as a global frame lookup.
PATTERNS = [
    re.compile(r'\bname\s*=\s*"([A-Z][A-Za-z0-9_]+)"'),      # { name = "X" } target lists
    re.compile(r'\bmoney\s*=\s*"([A-Z][A-Za-z0-9_]+)"'),     # money-frame siblings
    re.compile(r'_G\[\s*"([A-Z][A-Za-z0-9_]+)"\s*\]'),       # direct _G lookups
    re.compile(r'hooksecurefunc\(\s*"([A-Z][A-Za-z0-9_]+)"'),  # hooked globals
]

# Frames owned by a load-on-demand Blizzard_* module. Absent at login by design.
LOD = {
    "AuctionHouseFrame", "AuctionFrame", "PlayerTalentFrame", "TalentFrame",
    "PlayerSpellsFrame", "SpellBookFrame", "InspectFrame", "TradeSkillFrame",
    "ProfessionsFrame", "MacroFrame", "PVPFrame", "GuildFrame",
    "CommunitiesFrame", "CalendarFrame", "QuestMapFrame",
    "QuestLogPopupDetailFrame", "ItemRefTooltip", "BattlefieldMinimap",
    "PTR_IssueReporter",
}

# Pre-modern names with a known replacement on a 12.0-era engine. The value is
# the modern equivalent, so the report can say whether we already list it.
LEGACY = {
    "QuestLogFrame": "QuestMapFrame",
    "QuestWatchFrame": "ObjectiveTrackerFrame",
    "MainMenuExpBar": "StatusTrackingBarManager",
    "ReputationWatchBar": "StatusTrackingBarManager",
    "MainMenuBar": "MainMenuBar (restructured; see MicroBars/ActionBars)",
    "SpellBookFrame": "PlayerSpellsFrame",
    "TalentFrame": "PlayerSpellsFrame",
    "PlayerTalentFrame": "PlayerSpellsFrame",
    "AuctionFrame": "AuctionHouseFrame",
    "TradeSkillFrame": "ProfessionsFrame",
    "LootFrame": "LootFrame (still present on some builds; verify)",
}


def load_client_globals() -> set[str]:
    if not GLOBALS_DUMP.exists():
        sys.exit(f"client globals dump not found at {GLOBALS_DUMP}")
    return {
        line.split("\t", 1)[0].strip()
        for line in GLOBALS_DUMP.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    }


def classify(name: str, client: set[str]) -> tuple[str, str]:
    if name in client:
        return "AT LOGIN", ""
    if name in LEGACY:
        return "LEGACY", f"modern: {LEGACY[name]}"
    if name in LOD:
        return "LOD", "open the window once to settle it"
    return "UNKNOWN", ""


def main() -> int:
    argv = sys.argv[1:]
    only = None
    if "--module" in argv:
        only = argv[argv.index("--module") + 1]

    client = load_client_globals()
    files = [ADDON / only] if only else sorted(ADDON.rglob("*.lua"))

    rows = []
    for path in files:
        src = path.read_text(encoding="utf-8", errors="replace")
        found: dict[str, int] = {}
        for pat in PATTERNS:
            for m in pat.finditer(src):
                found.setdefault(m.group(1), src.count("\n", 0, m.start()) + 1)
        if not found:
            continue

        buckets: dict[str, list[str]] = {}
        for name, line in sorted(found.items()):
            kind, note = classify(name, client)
            buckets.setdefault(kind, []).append(
                f"{name}" + (f"  ({note})" if note else "")
            )

        print(f"\n=== {path.name} ===")
        for kind in ("LEGACY", "UNKNOWN", "LOD", "AT LOGIN"):
            if kind in buckets:
                names = buckets[kind]
                print(f"  {kind:8s} ({len(names)})")
                for n in names:
                    print(f"           {n}")
        rows.append((
            path.name,
            len(buckets.get("AT LOGIN", [])),
            len(buckets.get("LOD", [])),
            len(buckets.get("LEGACY", [])),
            len(buckets.get("UNKNOWN", [])),
        ))

    print("\n" + "=" * 72)
    print(f"{'module':24s} {'at login':>9s} {'LoD':>5s} {'legacy':>7s} {'unknown':>8s}")
    for name, a, l, g, u in sorted(rows, key=lambda r: -(r[3] + r[4])):
        print(f"{name:24s} {a:9d} {l:5d} {g:7d} {u:8d}")
    print("\nAT LOGIN means the target existed; it does NOT prove the skin landed.")
    print("LoD is unknowable from a login-time dump: open the window once.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
