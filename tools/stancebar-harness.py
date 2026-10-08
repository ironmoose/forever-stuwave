#!/usr/bin/env python3
"""Runs the real StanceBar.lua headless, in sealbar-harness's world (the actionbars mock, FrameHelpers.lua,
ActionBars.lua, Console.lua, PetActionBar.lua) plus PetDock.lua and ClassShoulder.lua.

Two things are pinned here:

  * the stock Blizzard stance bar stays dimmed. Blizzard can bring it back (alpha restored, a stock
    button's own hotkey drawing under ours), so the dim is repeated on the events that follow a
    binding or a form change, out of combat, and deferred to PLAYER_REGEN_ENABLED inside a fight;
  * the Warrior's stances stand on the class shoulder (mockup `LS_*`, `{id:'st',x:LS_X,n:3,rows:1}`): three
    fixed slots, Battle, Defensive, Berserker, 38 design px apart by 4.8, seated by `StanceBar.HostPoint` and
    `StanceBar.SlotPoint`, which answer from the shoulder while it stands and fall back to the stance
    bar's own seat when it does not. Every other class keeps the stance bar it had.

The mock is strict and is NOT the real client.

    python3 tools/stancebar-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


csh = _load("classshoulder_harness", "classshoulder-harness.py")
sb = csh.sb
g = sb.g
fire = sb.fire
set_combat = sb.set_combat
blocked = sb.blocked
approx = sb.approx

WARRIOR_STANCES = csh.WARRIOR_FORMS
MU = sb.MU
PITCH = MU["BTN"] + MU["BG"]
SCALES = csh.SCALES

# Layout.lua's re-seat list and watcher, which the console mock leaves out: Apply records the frame, a rescale
# re-seats every recorded frame before the callbacks run (FS.Layout's layoutWatcher), and the stance container
# is protected like any frame that parents secure buttons.
PATCH = r"""
FS.Layout._applied = {}
__applyCalls = {}
local realApply = FS.Layout.Apply
FS.Layout.Apply = function(frame, id, parent)
    local L = realApply(frame, id, parent)
    FS.Layout._applied[frame] = { id = id, parent = parent }
    __applyCalls[id] = (__applyCalls[id] or 0) + 1
    return L
end
local realRescale = __rescale
function __rescale(s)
    __scale = s
    UIParent._w, UIParent._h = 2560 * s, 1440 * s
    for frame, info in pairs(FS.Layout._applied) do realApply(frame, info.id, info.parent) end
    __fire_rescale()
end
local create = CreateFrame
function CreateFrame(kind, name, ...)
    local f = create(kind, name, ...)
    if name == "FSStanceBar" then f._protected = true end
    return f
end
"""


def warrior(scale: float = 1.0, forms=WARRIOR_STANCES, **kw):
    """A Warrior in the class shoulder harness's world, with the Layout bookkeeping above."""
    pre = PATCH + kw.pop("pre_login", "")
    return csh.boot(scale, klass="WARRIOR", forms=list(forms), pre_login=pre, **kw)


def other(klass: str, scale: float = 1.0, **kw):
    pre = PATCH + kw.pop("pre_login", "")
    return csh.boot(scale, klass=klass, pre_login=pre, **kw)


def stance(lua, i):
    return g(lua)[f"FSStanceButton{i}"]


def D(lua, frame):
    return csh.D(lua, frame)


# ---------------------------------------------------------------------------------------------
# The stock bar stays dimmed
# ---------------------------------------------------------------------------------------------

STOCK_EVENTS = ("UPDATE_BINDINGS", "UPDATE_SHAPESHIFT_FORM", "PLAYER_REGEN_ENABLED")


def restore_stock(lua):
    """Blizzard brings its stance bar and button back to full alpha."""
    lua.execute("StanceBar:SetAlpha(1); StanceButton1:SetAlpha(1); StanceButton1:EnableMouse(true)")


def stock_alphas(lua):
    return g(lua).StanceBar._alpha, g(lua).StanceButton1._alpha


def check_the_stock_bar_is_dimmed_at_login():
    lua = sb.boot(klass="WARRIOR", forms=list(WARRIOR_STANCES))
    assert stock_alphas(lua) == (0, 0), f"stock bar alpha at login: {stock_alphas(lua)}"


def check_the_stock_bar_is_dimmed_again_when_blizzard_restores_it():
    for event in STOCK_EVENTS:
        lua = sb.boot(klass="WARRIOR", forms=list(WARRIOR_STANCES))
        restore_stock(lua)
        assert stock_alphas(lua) == (1, 1), "setup: the stock bar should be restored"
        fire(lua, event)
        assert stock_alphas(lua) == (0, 0), f"{event} left the stock bar visible: {stock_alphas(lua)}"
        assert g(lua).StanceButton1._mouse is False, f"{event} left the stock button clickable"
        assert g(lua).StanceBar._shown, f"{event}: the Edit Mode bar was hidden (Blizzard's HideOverride)"


def check_the_stock_bar_is_dimmed_again_for_a_paladin_too():
    for event in STOCK_EVENTS:
        lua = sb.boot()
        restore_stock(lua)
        fire(lua, event)
        assert stock_alphas(lua) == (0, 0), f"Paladin, {event}: {stock_alphas(lua)}"


def check_a_restore_in_combat_waits_for_the_end_of_combat():
    for event in ("UPDATE_BINDINGS", "UPDATE_SHAPESHIFT_FORM"):
        lua = sb.boot(klass="WARRIOR", forms=list(WARRIOR_STANCES))
        set_combat(lua, True)
        restore_stock(lua)
        fire(lua, event)
        assert stock_alphas(lua) == (1, 1), f"{event} touched the stock bar in combat"
        assert blocked(lua) == 0, "a protected operation was refused in combat"
        set_combat(lua, False)
        fire(lua, "PLAYER_REGEN_ENABLED")
        assert stock_alphas(lua) == (0, 0), "the dim owed from combat was not paid at regen"
        assert blocked(lua) == 0


def check_the_dim_runs_no_blizzard_script():
    lua = sb.boot(klass="WARRIOR", forms=list(WARRIOR_STANCES))
    lua.execute("""
        __hits = 0
        for _, f in ipairs({ StanceBar, StanceButton1 }) do
            for _, m in ipairs({ "Hide", "SetParent", "SetScript", "HookScript", "UnregisterAllEvents" }) do
                local base = f[m]
                f[m] = function(...) __hits = __hits + 1; return base(...) end
            end
        end
    """)
    restore_stock(lua)
    for event in STOCK_EVENTS:
        fire(lua, event)
    assert g(lua).__hits == 0, "the re-dim ran a Blizzard method that can taint"


# ---------------------------------------------------------------------------------------------
# The Warrior's stances on the class shoulder
# ---------------------------------------------------------------------------------------------


def check_a_warriors_stances_stand_in_the_shoulder_slots_at_both_scales(scale):
    lua = warrior(scale)
    block = D(lua, csh.shoulder(lua).art)
    host = D(lua, g(lua).FSStanceBar)
    for k in ("x", "y", "w", "h"):
        approx(host[k], block[k], f"the stance host's {k} is the block's", 0.01)
    for slot in range(1, 4):
        btn = stance(lua, slot)
        assert btn is not None and sb.shown(btn), f"stance {slot} is not shown"
        r = D(lua, btn)
        approx(r["w"], MU["BTN"], f"slot {slot} width in design px", 0.01)
        approx(r["h"], MU["BTN"], f"slot {slot} height in design px", 0.01)
        approx(r["x"], block["x"] + MU["PAD"] + (slot - 1) * PITCH, f"slot {slot} x", 0.01)
        approx(r["y"], block["y"] + MU["PT"], f"slot {slot} y", 0.01)
        p = btn._points[1]
        assert (p.point, p.relPoint) == ("BOTTOMLEFT", "BOTTOMLEFT") and sb.same(lua, p.rel, g(lua).FSStanceBar)
        assert sb.same(lua, btn._parent, g(lua).FSStanceBar), "the stance button left its host"
    for slot in range(1, 3):
        a, b = D(lua, stance(lua, slot)), D(lua, stance(lua, slot + 1))
        approx(b["x"] - (a["x"] + a["w"]), MU["BG"], f"the gap after slot {slot}", 0.01)
    last = D(lua, stance(lua, 3))
    approx(block["x"] + block["w"] - (last["x"] + last["w"]), MU["PAD"], "right padding", 0.01)
    approx(block["y"] + block["h"] - (last["y"] + last["h"]), MU["PB"], "bottom padding", 0.01)
    assert g(lua).FS.StanceBar.OwnsShoulder() is True, "the Warrior's StanceBar does not own the shoulder"


def check_the_stance_buttons_wear_the_paladin_button_look():
    lua = warrior()
    pal = csh.boot()
    ref = sb.aura(pal, 1)
    for slot in range(1, 4):
        btn = stance(lua, slot)
        assert btn._secure and btn._attrs["type"] == "spell"
        assert btn.fsStancePlate is not None and ref.fsSealPlate is not None
        a, b = btn.fsSkin, ref.fsSkin
        assert a is not None and b is not None, "a button lost its cut skin"
        for part in ("ring", "glow"):
            ta = a.border.ring if part == "ring" else a.glow
            tb = b.border.ring if part == "ring" else b.glow
            for i in range(1, 5):
                approx(ta._vertex[i], tb._vertex[i], f"{part} colour channel {i} against the Paladin's aura button")
        approx(btn._w, ref._w, "button edge against the Paladin's"), approx(btn._h, ref._h, "button edge")


def check_an_unlearned_stance_leaves_its_slot_empty_and_learning_it_fills_it():
    lua = warrior(forms=WARRIOR_STANCES[:2])
    assert stance(lua, 3) is None, "a button was built for a stance the Warrior has not learned"
    block = D(lua, csh.shoulder(lua).art)
    approx(block["w"], csh.WR["W"], "the block stays 3 wide with two stances", 0.01)
    assert sb.shown(stance(lua, 1)) and sb.shown(stance(lua, 2))
    x2 = stance(lua, 2)._points[1].x
    sb.set_forms(lua, WARRIOR_STANCES)
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert stance(lua, 3) is not None and sb.shown(stance(lua, 3)), "the learned stance did not appear"
    approx(D(lua, stance(lua, 3))["x"], block["x"] + MU["PAD"] + 2 * PITCH, "the new stance stands in slot 3", 0.01)
    approx(stance(lua, 2)._points[1].x, x2, "the others did not move")
    assert stance(lua, 3)._attrs["spell"] == sb.form_id(lua, WARRIOR_STANCES[2])
    sb.set_forms(lua, WARRIOR_STANCES[:2])
    fire(lua, "UPDATE_SHAPESHIFT_FORMS")
    assert not sb.shown(stance(lua, 3)), "a stance that went away kept its button"


def check_a_slot_is_the_stances_place_in_the_mockup_order_not_the_form_index():
    lua = warrior(forms=(WARRIOR_STANCES[1], WARRIOR_STANCES[0]))     # form 1 is Defensive, form 2 is Battle
    block = D(lua, csh.shoulder(lua).art)
    approx(D(lua, stance(lua, 1))["x"], block["x"] + MU["PAD"] + PITCH, "Defensive stands in slot 2", 0.01)
    approx(D(lua, stance(lua, 2))["x"], block["x"] + MU["PAD"], "Battle stands in slot 1", 0.01)
    # the key follows the FORM, not the slot
    assert stance(lua, 1).commandName == "SHAPESHIFTBUTTON1" and stance(lua, 2).commandName == "SHAPESHIFTBUTTON2"
    assert stance(lua, 1)._attrs["spell"] == sb.form_id(lua, WARRIOR_STANCES[1])
    g(lua).__bindings["SHAPESHIFTBUTTON1"] = "F1"
    fire(lua, "UPDATE_BINDINGS")
    assert stance(lua, 1).HotKey._text not in (None, ""), "the form's key was not drawn"
    assert stance(lua, 2).HotKey._text in (None, "")
    lua = warrior(forms=(WARRIOR_STANCES[0], WARRIOR_STANCES[2]))     # Battle and Berserker: slot 2 stays empty
    block = D(lua, csh.shoulder(lua).art)
    approx(D(lua, stance(lua, 1))["x"], block["x"] + MU["PAD"], "Battle in slot 1", 0.01)
    approx(D(lua, stance(lua, 2))["x"], block["x"] + MU["PAD"] + 2 * PITCH, "Berserker in slot 3, slot 2 empty", 0.01)


def check_forms_the_client_names_otherwise_take_the_slot_of_their_index():
    lua = warrior(forms=("Kampfhaltung", "Verteidigungshaltung", "Berserkerhaltung"))
    block = D(lua, csh.shoulder(lua).art)
    for slot in range(1, 4):
        assert sb.shown(stance(lua, slot)), f"stance {slot} hidden on a client with other spell names"
        approx(D(lua, stance(lua, slot))["x"], block["x"] + MU["PAD"] + (slot - 1) * PITCH, f"slot {slot}", 0.01)
    lua = warrior(forms=("Kampfhaltung", WARRIOR_STANCES[2]))     # one named, one not: no two share a slot
    xs = sorted(round(stance(lua, i)._points[1].x, 3) for i in (1, 2) if sb.shown(stance(lua, i)))
    assert len(xs) == len(set(xs)), f"two stances share a slot: {xs}"


def check_layout_does_not_reseat_the_container_while_it_stands_on_the_shoulder():
    lua = warrior(1.0)
    container = g(lua).FSStanceBar
    assert g(lua).FS.Layout._applied[container] is None, "the container is still on Layout's re-seat list"
    seats = int(g(lua).__applyCalls["stance"])
    lua.eval("__rescale")(0.64)
    assert int(g(lua).__applyCalls["stance"]) == seats, "Layout.Apply re-seated the stance container"
    assert g(lua).FS.Layout._applied[container] is None
    p = container._points[1]
    assert p.rel._name == "FSConsole", f"the container is anchored to {p.rel._name}"
    block = D(lua, csh.shoulder(lua).art)
    host = D(lua, container)
    for k in ("x", "y", "w", "h"):
        approx(host[k], block[k], f"{k} after a rescale", 0.01)
    for slot in range(1, 4):
        approx(D(lua, stance(lua, slot))["x"], block["x"] + MU["PAD"] + (slot - 1) * PITCH, f"slot {slot} after a rescale", 0.01)
        approx(stance(lua, slot)._w, MU["BTN"] * 0.64, "the button edge follows the scale", 0.01)


def check_without_the_console_the_stances_keep_the_stance_bar_seat():
    for kw in ({"console": False}, {}):
        lua = warrior(**kw)
        if not kw:
            csh.console(lua).SetActive(False)
        container = g(lua).FSStanceBar
        assert g(lua).FS.Layout._applied[container] is not None, "the container is not on Layout's list"
        assert g(lua).FS.StanceBar.HostPoint() is None and g(lua).FS.StanceBar.SlotPoint(1) is None
        b1, b2 = stance(lua, 1), stance(lua, 2)
        p1, p2 = b1._points[1], b2._points[1]
        assert (p1.point, p1.relPoint) == ("LEFT", "LEFT") and sb.same(lua, p1.rel, container)
        assert (p2.point, p2.relPoint) == ("LEFT", "RIGHT") and sb.same(lua, p2.rel, b1)
        approx(p2.x, 4, "the stance bar's own gap")
        assert all(sb.shown(stance(lua, i)) for i in (1, 2, 3))
        assert not any(r.rel is not None and r.rel._name == "FSConsole" for r in sb_points(container))


def sb_points(frame):
    return [frame._points[i] for i in range(1, len(frame._points) + 1)]


def check_the_console_toggle_moves_the_stances_to_the_stance_seat_and_back():
    lua = warrior()
    container = g(lua).FSStanceBar
    buttons = [stance(lua, i) for i in (1, 2, 3)]
    csh.console(lua).SetActive(False)
    assert g(lua).FS.Layout._applied[container] is not None
    assert buttons[0]._points[1].rel is not None and sb.same(lua, buttons[0]._points[1].rel, container)
    assert buttons[1]._points[1].point == "LEFT" and buttons[1]._points[1].relPoint == "RIGHT"
    csh.console(lua).SetActive(True)
    assert g(lua).FS.Layout._applied[container] is None, "back on the shoulder, the container left Layout's list"
    assert container._points[1].rel._name == "FSConsole"
    block = D(lua, csh.shoulder(lua).art)
    for slot, btn in enumerate(buttons, 1):
        assert sb.same(lua, stance(lua, slot), btn), "a stance button was re-created"
        approx(D(lua, btn)["x"], block["x"] + MU["PAD"] + (slot - 1) * PITCH, f"slot {slot} after the toggle", 0.01)


def check_other_classes_keep_the_stance_bar_exactly():
    for klass in ("DRUID", "ROGUE", "PRIEST", "MAGE", "WARLOCK"):
        lua = other(klass)
        stance_api = g(lua).FS.StanceBar
        assert stance_api.OwnsShoulder() is False, klass
        assert stance_api.HostPoint() is None and stance_api.SlotPoint(1) is None, klass
        assert csh.shoulder(lua) is None and not csh.cs(lua).IsShown() and csh.calls(lua) == [], klass
        container = g(lua).FSStanceBar
        assert g(lua).FS.Layout._applied[container] is not None, f"{klass}: the container left Layout's list"
        assert int(g(lua).__applyCalls["stance"]) >= 1
        assert not any(r.rel is not None and r.rel._name == "FSConsole" for r in sb_points(container)), klass
        b1, b2 = stance(lua, 1), stance(lua, 2)
        assert b1 is not None and sb.shown(b1) and sb.shown(b2), klass
        p2 = b2._points[1]
        assert (p2.point, p2.relPoint) == ("LEFT", "RIGHT") and sb.same(lua, p2.rel, b1), klass
        approx(p2.x, 4, f"{klass}: the stance bar's own gap")


def check_the_paladin_is_unchanged_stance_bar_builds_nothing():
    lua = csh.boot(pre_login=PATCH)
    assert g(lua).FS.StanceBar.OwnsShoulder() is False
    assert g(lua).FS.SealBar.OwnsForms() is True and csh.cs(lua).IsShown()
    assert stance(lua, 1) is None or not sb.shown(stance(lua, 1)), "a Paladin got stance buttons"
    assert not g(lua).FSStanceBar._shown


def check_combat_defers_every_secure_change_to_regen():
    lua = warrior(1.0)
    container = g(lua).FSStanceBar
    set_combat(lua, True)
    before = {i: (stance(lua, i)._points[1].x, stance(lua, i)._points[1].y, stance(lua, i)._w) for i in (1, 2, 3)}
    seat = (container._points[1].x, container._w, container._h, container._level)
    lua.eval("__rescale")(0.64)
    csh.console(lua).SetActive(False)
    sb.set_forms(lua, WARRIOR_STANCES[:2])
    for event in ("UPDATE_SHAPESHIFT_FORMS", "PLAYER_ENTERING_WORLD", "UPDATE_SHAPESHIFT_FORM", "UPDATE_BINDINGS"):
        fire(lua, event)
    assert blocked(lua) == 0, "a protected operation was refused in combat"
    assert g(lua).__protectedTouch == 0, "something was created or anchored under a protected frame in combat"
    assert (container._points[1].x, container._w, container._h, container._level) == seat, "the host moved in combat"
    for i in (1, 2, 3):
        now = (stance(lua, i)._points[1].x, stance(lua, i)._points[1].y, stance(lua, i)._w)
        assert now == before[i], f"stance {i} moved or resized in combat"
        assert sb.shown(stance(lua, i)), f"stance {i} was shown or hidden in combat"
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert blocked(lua) == 0
    assert g(lua).FS.Layout._applied[container] is not None, "the deferred toggle never reached the stance seat"
    assert not sb.shown(stance(lua, 3)), "the deferred form change never reached the buttons"
    assert stance(lua, 1)._points[1].point == "LEFT"


def check_a_warrior_login_in_combat_seats_the_stances_at_regen():
    lua = warrior(combat=True)
    assert stance(lua, 1) is None and csh.shoulder(lua) is None
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert csh.shoulder(lua) is not None and csh.cs(lua).IsShown(), "no shoulder at regen"
    block = D(lua, csh.shoulder(lua).art)
    for slot in range(1, 4):
        approx(D(lua, stance(lua, slot))["x"], block["x"] + MU["PAD"] + (slot - 1) * PITCH, f"slot {slot}", 0.01)
    assert blocked(lua) == 0 and g(lua).__protectedTouch == 0


def check_nothing_secure_hangs_off_the_shoulder_art():
    lua = warrior()
    art_frames = [csh.shoulder(lua).art] + csh.frames_under(csh.shoulder(lua).art)
    for f in csh.seq(lua.eval("__frames")):
        if f._name and re.match(r"FSStanceButton\d$", f._name) or f._name == "FSStanceBar":
            for p in csh.seq(f._points):
                assert p.rel is None or all(not sb.same(lua, p.rel, a) for a in art_frames), f"{f._name} is anchored to the art"
            parent = f._parent
            while parent is not None:
                assert all(not sb.same(lua, parent, a) for a in art_frames), f"{f._name} is parented under the art"
                parent = parent._parent


def check_a_throwing_shoulder_refresh_leaves_the_stances_on_their_own_seat():
    lua = warrior(pre_login="FS.ClassShoulder.Refresh = function() error('boom') end")
    assert g(lua).__degraded["stancebar_shoulder"], "the failure was not logged"
    assert all(sb.shown(stance(lua, i)) for i in (1, 2, 3))
    assert stance(lua, 2)._points[1].point == "LEFT" and stance(lua, 2)._points[1].relPoint == "RIGHT"


def check_each_stance_has_one_hotkey_label_on_the_shoulder():
    lua = warrior()
    g(lua).__bindings["SHAPESHIFTBUTTON2"] = "F2"
    for _ in range(3):
        fire(lua, "UPDATE_SHAPESHIFT_FORMS")
        fire(lua, "UPDATE_BINDINGS")
    for slot in range(1, 4):
        btn = stance(lua, slot)
        labels = [r for r in csh.seq(btn._regions) if r._kind == "FontString"]
        for h in csh.frames_under(btn):
            labels += [r for r in csh.seq(h._regions) if r._kind == "FontString"]
        assert len(labels) == 1, f"stance {slot} carries {len(labels)} font strings"
        assert sb.same(lua, labels[0], btn.HotKey), f"stance {slot}: the one font string is not the HotKey"
    assert stance(lua, 2).HotKey._text not in (None, ""), "slot 2 is bound but its label is empty"


def check_a_shouldered_warrior_stance_wears_the_seal_buttons_hotkey_plate_and_others_do_not():
    lua = warrior()
    pal = csh.boot()
    g(pal).__bindings["SHAPESHIFTBUTTON1"] = "F1"
    ref = sb.aura(pal, 1)
    g(lua).__bindings["SHAPESHIFTBUTTON1"] = "F1"
    fire(lua, "UPDATE_BINDINGS")
    fire(pal, "UPDATE_BINDINGS")
    for slot in range(1, 4):
        btn = stance(lua, slot)
        hot, plate = btn.HotKey, btn.fsHotkeyPlate
        assert plate is not None, f"stance {slot}: no hotkey plate"
        assert sb.same(lua, plate._parent, hot._parent), "plate and label sit on different hosts"
        assert (hot._layer, hot._sub, plate._layer, plate._sub) == ("OVERLAY", 4, "OVERLAY", 3)
        assert hot._mono["size"] == 10 and tuple(hot._mono["color"][i] for i in (1, 2, 3)) == (1, 1, 1)
        p = hot._points[1]
        assert (p.point, p.relPoint, p.x, p.y) == ("TOPRIGHT", "TOPRIGHT", -3, -2) and sb.same(lua, p.rel, btn)
        assert tuple(plate._color[i] for i in (1, 2, 3, 4)) == (0.024, 0.012, 0.071, 0.78)
        for i, want in ((1, ("TOPLEFT", -3, 2)), (2, ("BOTTOMRIGHT", 3, -2))):
            q = plate._points[i]
            assert (q.point, q.x, q.y) == want and sb.same(lua, q.rel, hot)
        a, b = btn.fsSkin, ref.fsSkin
        for part in ("ring", "glow"):
            ta = a.border.ring if part == "ring" else a.glow
            tb = b.border.ring if part == "ring" else b.glow
            for i in range(1, 5):
                approx(ta._vertex[i], tb._vertex[i], f"{part} channel {i}")
    assert sb.shown(stance(lua, 1).fsHotkeyPlate) and sb.shown(stance(lua, 1).HotKey), "bound: plate shown"
    assert not sb.shown(stance(lua, 2).fsHotkeyPlate), "unbound: plate hidden"
    g(lua).__bindings["SHAPESHIFTBUTTON1"] = None
    fire(lua, "UPDATE_BINDINGS")
    assert not sb.shown(stance(lua, 1).fsHotkeyPlate), "unbinding left the plate"
    # off the shoulder the buttons are the stance bar's own again
    g(lua).__bindings["SHAPESHIFTBUTTON1"] = "F1"
    csh.console(lua).SetActive(False)
    btn = stance(lua, 1)
    assert not sb.shown(btn.fsHotkeyPlate), "plate still drawn off the shoulder"
    p = btn.HotKey._points[1]
    assert (p.x, p.y) == (-2, -2), f"hotkey not back on the stance bar's seat: {p.x} {p.y}"
    csh.console(lua).SetActive(True)
    assert sb.shown(stance(lua, 1).fsHotkeyPlate) and stance(lua, 1).HotKey._points[1].x == -3
    for klass in ("DRUID", "ROGUE"):
        lua = other(klass)
        g(lua).__bindings["SHAPESHIFTBUTTON1"] = "F1"
        fire(lua, "UPDATE_BINDINGS")
        b1 = stance(lua, 1)
        assert b1.fsHotkeyPlate is None, f"{klass}: a plate on a stance bar button"
        p = b1.HotKey._points[1]
        assert (p.x, p.y) == (-2, -2) and b1.HotKey._sub != 4, f"{klass}: hotkey restyled"


def check_a_shoulder_that_answers_no_slot_hides_the_button_and_the_build_goes_on():
    lua = warrior(pre_login="FS.ClassShoulder.SlotPoint = function() return nil end")
    assert "failed to build" not in str(g(lua).__say or ""), g(lua).__say
    for i in (1, 2, 3):
        assert stance(lua, i) is not None, f"the build stopped before stance {i}"
        assert not sb.shown(stance(lua, i)), f"stance {i} is shown without a seat"
    assert g(lua).FSStanceBar._shown, "the host was left hidden"
    assert blocked(lua) == 0


def check_the_stances_follow_the_shoulder_whatever_order_regen_reaches_them():
    # the shoulder's own geometry notice is left out, so its PLAYER_REGEN_ENABLED replay is what brings it up;
    # StanceBar's regen handler runs first (load order) and must still end on the shoulder
    lua = warrior(drop=("geo",))
    csh.console(lua).SetActive(False)
    csh.cs(lua).Refresh()
    g(lua).FS.StanceBar.Rebuild()
    assert not csh.cs(lua).IsShown(), "setup: the shoulder should be down with the Console off"
    assert g(lua).FS.Layout._applied[g(lua).FSStanceBar] is not None, "setup: the stances should be on their own seat"
    set_combat(lua, True)
    csh.console(lua).SetActive(True)
    csh.cs(lua).Refresh()
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")
    assert csh.cs(lua).IsShown(), "the shoulder did not come back at regen"
    point = g(lua).FSStanceBar._points[1]
    assert point is not None and point.rel._name == "FSConsole", "the stances stayed on the stance bar seat"
    assert g(lua).FS.Layout._applied[g(lua).FSStanceBar] is None
    assert blocked(lua) == 0


def check_no_em_dashes_in_the_new_files():
    for path in (csh.ADDON / "Modules/ActionBars/StanceBar.lua", Path(__file__)):
        assert chr(0x2014) not in path.read_text(encoding="utf-8"), f"{path.name} has an em dash"


CHECKS = [
    check_the_stock_bar_is_dimmed_at_login,
    check_the_stock_bar_is_dimmed_again_when_blizzard_restores_it,
    check_the_stock_bar_is_dimmed_again_for_a_paladin_too,
    check_a_restore_in_combat_waits_for_the_end_of_combat,
    check_the_dim_runs_no_blizzard_script,
    check_the_stance_buttons_wear_the_paladin_button_look,
    check_an_unlearned_stance_leaves_its_slot_empty_and_learning_it_fills_it,
    check_a_slot_is_the_stances_place_in_the_mockup_order_not_the_form_index,
    check_forms_the_client_names_otherwise_take_the_slot_of_their_index,
    check_layout_does_not_reseat_the_container_while_it_stands_on_the_shoulder,
    check_without_the_console_the_stances_keep_the_stance_bar_seat,
    check_the_console_toggle_moves_the_stances_to_the_stance_seat_and_back,
    check_other_classes_keep_the_stance_bar_exactly,
    check_the_paladin_is_unchanged_stance_bar_builds_nothing,
    check_combat_defers_every_secure_change_to_regen,
    check_a_warrior_login_in_combat_seats_the_stances_at_regen,
    check_nothing_secure_hangs_off_the_shoulder_art,
    check_a_throwing_shoulder_refresh_leaves_the_stances_on_their_own_seat,
    check_each_stance_has_one_hotkey_label_on_the_shoulder,
    check_a_shouldered_warrior_stance_wears_the_seal_buttons_hotkey_plate_and_others_do_not,
    check_a_shoulder_that_answers_no_slot_hides_the_button_and_the_build_goes_on,
    check_the_stances_follow_the_shoulder_whatever_order_regen_reaches_them,
    check_no_em_dashes_in_the_new_files,
]
SCALED_CHECKS = [
    check_a_warriors_stances_stand_in_the_shoulder_slots_at_both_scales,
]


def main() -> int:
    failed = total = 0

    def run(label, fn, *args):
        nonlocal failed, total
        total += 1
        try:
            fn(*args)
            print(f"ok    {label}")
        except (AssertionError, LuaError, FileNotFoundError, AttributeError, TypeError, KeyError, IndexError) as err:
            failed += 1
            print(f"FAIL  {label}\n      " + f"{type(err).__name__}: {err}".replace("\n", "\n      "))

    for fn in CHECKS:
        run(fn.__name__, fn)
    for fn in SCALED_CHECKS:
        for scale in SCALES:
            run(f"{fn.__name__} @scale={scale:.4f}", fn, scale)
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
