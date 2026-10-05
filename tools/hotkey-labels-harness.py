#!/usr/bin/env python3
"""Focused hotkey formatting and Paladin label regressions against the real Lua.

Run: python3 tools/hotkey-labels-harness.py
The mock records styling; actual rendering still needs an in-game check.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sealbar_harness", HERE / "sealbar-harness.py")
sh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sh)

PRELUDE = r"""
__bindingTextCalls = {}
function GetBindingText(key, abbreviated)
    __bindingTextCalls[#__bindingTextCalls + 1] = { key, abbreviated }
    return "localized:" .. key
end
function __Region:SetJustifyH(value) self._justifyH = value end
local applyMono = FS.Theme.ApplyMono
function FS.Theme.ApplyMono(text, size, color)
    applyMono(text, size)
    text._monoColor = color
end
"""


def check_formatter_preserves_mouse_identity_and_blizzard_keyboard_labels():
    lua = sh.boot(extra_lua=PRELUDE)
    formatter = lua.globals().FS.FrameHelpers.FormatBindingText
    assert formatter is not None, "shared FormatBindingText is missing"
    cases = [
        (None, ""), ("", ""), ("BUTTON3", "MM"), ("BUTTON4", "MB4"),
        ("BUTTON12", "MB12"), ("SHIFT-BUTTON3", "S-MM"),
        ("CTRL-BUTTON4", "C-MB4"), ("ALT-SHIFT-BUTTON5", "A-S-MB5"),
        ("SHIFT-F", "localized:SHIFT-F"), ("PAD1", "localized:PAD1"),
    ]
    for key, expected in cases:
        assert formatter(key) == expected, f"{key!r} should display {expected!r}"
    calls = lua.globals().__bindingTextCalls
    assert all(calls[i][2] == 1 for i in range(1, len(calls) + 1)), (
        "Blizzard binding text must use abbreviation mode"
    )


def check_every_bar_uses_compact_mouse_labels_and_rebinding_refreshes():
    worlds = [
        (sh.boot(extra_lua=PRELUDE), [
            ("FSActionButton1_1", "ACTIONBUTTON1"),
            ("FSSealButton1", "CLICK FSSealButton1:LeftButton"),
            ("FSAuraButton1", "SHAPESHIFTBUTTON1"),
            ("FSPetActionButton1", "BONUSACTIONBUTTON1"),
        ]),
        (sh.abh.boot(PRELUDE), [("FSStanceButton1", "SHAPESHIFTBUTTON1")]),
    ]
    for lua, buttons in worlds:
        for name, command in buttons:
            lua.globals().__bindings[command] = "CTRL-BUTTON4"
        sh.fire(lua, "UPDATE_BINDINGS")
        for name, command in buttons:
            button = lua.globals()[name]
            assert button.HotKey.GetText(button.HotKey) == "C-MB4", name
            lua.globals().__bindings[command] = "BUTTON3"
        lua.eval("__trigger")("KeybindListener.RebindSuccess")
        for name, _ in buttons:
            button = lua.globals()[name]
            assert button.HotKey.GetText(button.HotKey) == "MM", f"rebind: {name}"


def check_seal_and_aura_labels_match_actionbar_plate_and_hide_when_unbound():
    lua = sh.boot(scale=1.0, extra_lua=PRELUDE)
    for name, command in [
        ("FSSealButton1", "CLICK FSSealButton1:LeftButton"),
        ("FSAuraButton1", "SHAPESHIFTBUTTON1"),
    ]:
        button = lua.globals()[name]
        hotkey, plate = button.HotKey, button.fsHotkeyPlate
        assert plate is not None, f"{name}: missing dark hotkey plate"
        assert sh.same(lua, plate.GetParent(plate), hotkey.GetParent(hotkey)), name
        assert hotkey._layer == "OVERLAY" and hotkey._sub == 4, name
        assert plate._layer == "OVERLAY" and plate._sub == 3, name
        assert hotkey._font[2] == 10 and hotkey._justifyH == "RIGHT", name
        assert tuple(hotkey._monoColor[i] for i in (1, 2, 3)) == (1, 1, 1), name
        point = hotkey._points[1]
        assert (point.point, point.relPoint, point.x, point.y) == (
            "TOPRIGHT", "TOPRIGHT", -3, -2
        ), name
        assert sh.same(lua, point.rel, button) and hotkey._w == 0, name
        assert tuple(plate._color[i] for i in (1, 2, 3, 4)) == (0.024, 0.012, 0.071, 0.78), name
        for index, expected in [(1, ("TOPLEFT", -3, 2)), (2, ("BOTTOMRIGHT", 3, -2))]:
            point = plate._points[index]
            assert (point.point, point.x, point.y) == expected, name
            assert sh.same(lua, point.rel, hotkey), name
        assert not sh.shown(plate) and not sh.shown(hotkey), f"unbound: {name}"
        lua.globals().__bindings[command] = "BUTTON3"
        sh.fire(lua, "UPDATE_BINDINGS")
        assert sh.shown(plate) and sh.shown(hotkey), f"bound: {name}"
        lua.globals().__bindings[command] = None
        lua.eval("__trigger")("KeybindListener.RebindSuccess")
        assert not sh.shown(plate) and not sh.shown(hotkey), f"unbound rebind: {name}"


def main() -> int:
    checks = [
        check_formatter_preserves_mouse_identity_and_blizzard_keyboard_labels,
        check_every_bar_uses_compact_mouse_labels_and_rebinding_refreshes,
        check_seal_and_aura_labels_match_actionbar_plate_and_hide_when_unbound,
    ]
    failed = 0
    for check in checks:
        try:
            check()
            print(f"ok    {check.__name__}")
        except (AssertionError, sh.LuaError, AttributeError, TypeError) as error:
            failed += 1
            print(f"FAIL  {check.__name__}: {error}")
    print(f"{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
