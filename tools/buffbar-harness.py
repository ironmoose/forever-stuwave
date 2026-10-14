#!/usr/bin/env python3
"""Runs the real ShamanBuffs.lua and BuffTab.lua (the Shaman buff tab: IMBUE and SHIELD tiles) headless, in
totembar-harness's world: the actionbars mock, FrameHelpers.lua, ActionBars.lua, Console.lua, StanceBar.lua,
PetActionBar.lua, PetDock.lua, ClassShoulder.lua, TotemPiece.lua and TotemBar.lua.

The tab is a second Shaman shoulder on the Console's top edge (mockups/shaman-buff-tab-2026-10-12.html): 2 columns x
1 row (92.8 x 49 design px) at 316 design px, right of the totem tab. The numbers and colours below are read out of
the mockup, so a mockup move fails here. Checked:

  * the weapon tooltip parse (C_TooltipInfo.GetInventoryItem lines such as "Rockbiter 1 (56 min)"): minutes, seconds,
    hours, with and without a rank, localized strings, lines that are not an imbue, secret and unreadable answers;
  * the imbue model: both hands read, the least time shows, a weapon hand without an imbue asks for one (a shield or an
    empty off hand never does), the tooltip is NEVER read in combat, the clock counts down from the last read, a cast
    in combat starts a fresh hour on the right hand and a weapon swapped in combat is forgotten, not guessed;
  * the shield model: orbs from the aura snapshot, the expiring time, the combat estimate, Water Shield is not nagged,
    a Water Shield cast in combat clears the pending Lightning Shield cast, and a missing aura end is the application
    time plus the duration, not the last read plus ten minutes;
  * the tiles: states and colours from the mockup (quiet gold, pink expiring, red hollow missing, hollow "?"), the
    locked dotted mold with its level, the absent imbue tile, the hover border and the tooltip lines; every string of
    every state fits inside its tile at each UI scale (measured with the real font's advances);
  * the secure buttons: type "spell" with the spell name, written out of combat only and queued for regen, never a
    field or attribute Blizzard's secure click path reads, built once, bound through Bindings.xml;
  * the seat: shoulder block, host and buttons at the mockup's geometry, the Console gap and the bridge between the
    two shoulders, Console on and off, a rescale, a player who is not a Shaman gets nothing, and a failed build leaves
    no listener running;
  * visibility needs no target.

The mock is strict and is NOT the real client. BUFFTAB_LUA, SHAMANBUFFS_LUA, BINDINGS_XML and TOC_FILE point the
harness at mutant copies (a check must fail on a broken one).

    python3 tools/buffbar-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
BUFFTAB = Path(os.environ.get("BUFFTAB_LUA", ADDON / "Modules/ActionBars/BuffTab.lua"))
SHAMANBUFFS = Path(os.environ.get("SHAMANBUFFS_LUA", ADDON / "Modules/ActionBars/ShamanBuffs.lua"))
BINDINGS = Path(os.environ.get("BINDINGS_XML", ADDON / "Bindings.xml"))
TOC = Path(os.environ.get("TOC_FILE", ADDON / "forever-stuwave.toc"))
MOCKUP = HERE.parent / "mockups" / "shaman-buff-tab-2026-10-12.html"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tbh = _load("totembar_harness", "totembar-harness.py")
csh = tbh.csh
sb = csh.sb
g = sb.g


def fire(lua, event, *args):
    lua.eval("__fire_event")(event, *args)


approx = sb.approx
set_combat = sb.set_combat
blocked = sb.blocked
SCALES = csh.SCALES


# ---------------------------------------------------------------------------------------------
# The mockup's numbers
# ---------------------------------------------------------------------------------------------


def _hex(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def mockup() -> dict:
    src = MOCKUP.read_text(encoding="utf-8")
    pal = sb._m(r"var C=\{(.*?)\};", src, "palette").group(1)
    colors = {k: _hex(v) for k, v in re.findall(r"(\w+):'(#[0-9a-fA-F]{6})'", pal)}
    geo = sb._m(r"var G=\{(.*?)\};", src, "geometry").group(1)
    num = {k: float(v) for k, v in re.findall(r"(\w+):([\d.]+)", geo)}
    chip = sb._m(r"function chip\(cx,cy,code,m\)\{(.*?)\n\}", src, "chip").group(1)
    warn_fill = float(sb._m(r"m==='warn'\)\{s=C\.red;f=mix\(C\.bg,C\.red,([\d.]+)\)", chip, "warn chip fill").group(1))
    exp_fill = float(sb._m(r"m==='exp'\)\{s=C\.pink;f=mix\(C\.bg,C\.pink,([\d.]+)\)", chip, "exp chip fill").group(1))
    on_fill = float(sb._m(r"else\{s=C\.gold;f=mix\(C\.bg,C\.gold,([\d.]+)\)", chip, "on chip fill").group(1))
    body = sb._m(r"function tileBody\(x,y,st\)\{(.*?)\n\}", src, "tileBody").group(1)
    alphas = {}
    for mode, a in re.findall(r"if\(m==='(exp|warn|hollow)'\)\{bc=C\.\w+;ba=([\d.]+);", body):
        alphas[mode] = float(a)
    alphas["on"] = float(sb._m(r"else\{bc=C\.violet;ba=([\d.]+);", body, "quiet border alpha").group(1))
    on_text = float(sb._m(r"op:m==='on'\?([\d.]+):1", body, "quiet text alpha").group(1))
    return dict(colors=colors, num=num, warn_fill=warn_fill, exp_fill=exp_fill, on_fill=on_fill, ring_alpha=alphas,
                on_text=on_text)


MK = mockup()
C = MK["colors"]
N = MK["num"]
BG = C["bg"]

# ---------------------------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------------------------

IMBUE_IDS = {"Rockbiter Weapon": 8017, "Flametongue Weapon": 8024, "Frostbrand Weapon": 8033, "Windfury Weapon": 8232}
SHIELD_ID, WATER_ID = 324, 24398
ALL_SPELLS = dict(IMBUE_IDS, **{"Lightning Shield": SHIELD_ID, "Water Shield": WATER_ID})
GUID = tbh.GUID

MOCKS = r"""
FS.Theme.COLOR_HEALTH = FS.Theme.COLOR_HEALTH or { 1, 0.18, 0.592, 1 }
FS.Theme.COLOR_POWER = FS.Theme.COLOR_POWER or { 0.133, 0.878, 1, 1 }
FS.Theme.COLOR_BORDER = FS.Theme.COLOR_BORDER or { 0.659, 0.333, 0.969, 1 }
FS.Theme.COLOR_AMBER = FS.Theme.COLOR_AMBER or { 1, 0.7137, 0.2824, 1 }
FS.Theme.COLOR_RED = FS.Theme.COLOR_RED or { 1, 0.2314, 0.3059, 1 }
FS.Theme.COLOR_MUTED = FS.Theme.COLOR_MUTED or { 0.6157, 0.5765, 0.7686, 1 }
-- the host parents secure buttons, so it is restricted in combat like the Console root
do
    local create = CreateFrame
    function CreateFrame(kind, name, ...)
        if name and name == __failBuild then error("CreateFrame blew up for " .. name) end
        local f = create(kind, name, ...)
        if name == "FSBuffTab" then f._protected = true end
        return f
    end
end
__now = 10000
-- spell icons: 100000 + the spell id; __iconMode "nil" answers nothing, "secret" a secret value, "legacy" only the global
function __Region:SetDesaturated(v) self._desat = v and true or false end
C_Spell = C_Spell or {}
local function iconOf(id)
    if __iconMode == "nil" then return nil end
    if __iconMode == "secret" then return __SECRET end
    return 100000 + id
end
C_Spell.GetSpellTexture = function(id) if __iconMode == "legacy" then return nil end return iconOf(id) end
GetSpellTexture = function(id) return iconOf(id) end

-- Region geometry (y up): GetLeft / GetTop resolved from the anchors, so a check can ask where a slot really stands.
-- UIParent's origin is its bottom left.
do
    local function anchorPos(box, point)
        local l, t, w, h = box.l, box.t, box.w, box.h
        local x = l + ((point:find("RIGHT") and w) or (point:find("LEFT") and 0) or w / 2)
        local y = t - ((point:find("BOTTOM") and h) or (point:find("TOP") and 0) or h / 2)
        return x, y
    end
    local function box(r)
        if r == UIParent then return { l = 0, t = r._h, w = r._w, h = r._h } end
        local pts = r._points or {}
        if #pts == 0 then
            local parent = r._parent or UIParent
            local b = box(parent)
            return { l = b.l, t = b.t, w = r._w, h = r._h }
        end
        local function at(p)
            local rb = box(p.rel or r._parent or UIParent)
            local x, y = anchorPos(rb, p.relPoint or p.point)
            return x + (p.x or 0), y + (p.y or 0)
        end
        if #pts >= 2 then
            local tl, br
            for _, p in ipairs(pts) do
                if p.point == "TOPLEFT" then tl = p elseif p.point == "BOTTOMRIGHT" then br = p end
            end
            if tl and br then
                local x1, y1 = at(tl)
                local x2, y2 = at(br)
                return { l = x1, t = y1, w = x2 - x1, h = y1 - y2 }
            end
        end
        local p = pts[1]
        local x, y = at(p)
        local w, h = r._w or 0, r._h or 0
        local dx = (p.point:find("RIGHT") and w) or (p.point:find("LEFT") and 0) or w / 2
        local dy = (p.point:find("BOTTOM") and h) or (p.point:find("TOP") and 0) or h / 2
        return { l = x - dx, t = y + dy, w = w, h = h }
    end
    function __Region:GetLeft()
        if __noRect then return nil end
        if self._forceLeft then return self._forceLeft end
        return box(self).l
    end
    function __Region:GetTop()
        if __noRect then return nil end
        if self._forceTop then return self._forceTop end
        return box(self).t
    end
end

-- The engine's AuraContainer, strict like combathud-harness's: only what the addon is allowed to call. __template: the
-- client has the template; __acThrows (true: always, a number: that many builds) / __acSlotThrows ("shield" or
-- "imbue") / __acEnchThrows (true, "main" or "off") / __noEnchantApi: a failing build, slot or item enchantment;
-- __acRefuse: SetEnabled / Show / Hide are refused without a raise. Every call that writes the container is logged in
-- __acLog with the combat state it ran in. Slot frames are RESTRICTED in combat (SetPoint, SetAllPoints and every
-- write to a region of theirs is refused and counted in __slotBlocked) except inside initializeFrame.
-- __acLazy: initializeFrame runs later, from __acFlush(), as the engine does when it first needs a frame;
-- __acOverride: "init" (the engine re-anchors a slot right after init; SetAllPoints fixes it) or "sticky" (the engine's
-- layout owns the anchor and SetAllPoints cannot fix it); __acMouseOn: the engine turns the slot's mouse back on after
-- init; __acPropagate: the slot has SetPropagateMouseClicks / Motion.
__acs, __acLog, __acAttempts, __acPending, __slotBlocked = {}, {}, 0, {}, 0
__template, __acThrows, __acSlotThrows, __acEnchThrows, __noEnchantApi, __acRefuse = false, false, nil, false, false, false
__acLazy, __acOverride, __acMouseOn, __acPropagate, __noRect = false, nil, false, false, false
C_XMLUtil = { GetTemplateInfo = function(name)
    if __template and name == "CustomAuraContainerTemplate" then return { name = name } end
end }
AuraContainerSortMethod = { Default = 0 }
AuraContainerSortDirection = { Normal = 0 }
AuraContainerItemEnchantmentSlot = { MainHand = 1, OffHand = 2 }
do
    local create = CreateFrame
    local function logged(f, name, fn)
        f[name] = function(self, ...)
            __acLog[#__acLog + 1] = { name = name, combat = __combat and true or false, arg = (...) }
            return fn(self, ...)
        end
    end
    local function guarded(r, names)
        for _, n in ipairs(names) do
            local base = r[n]
            r[n] = function(me, ...)
                if __combat and (me._slotOwner or me)._slotRestricted then __slotBlocked = __slotBlocked + 1; return end
                return base(me, ...)
            end
        end
    end
    local function newSlot(parent)
        local slot = create("Frame", nil, parent)
        slot._order = {}
        guarded(slot, { "SetPoint", "SetAllPoints", "ClearAllPoints" })
        local mkTex, mkFs = slot.CreateTexture, slot.CreateFontString
        local function inherit(region)
            region._slotOwner = region._parent
            guarded(region, { "SetTexture", "SetPoint", "ClearAllPoints", "SetAllPoints", "SetText", "SetVertexColor",
                "SetColorTexture", "SetTexCoord" })
            return region
        end
        slot.CreateTexture = function(me, ...) return inherit(mkTex(me, ...)) end
        slot.CreateFontString = function(me, ...) return inherit(mkFs(me, ...)) end
        for _, n in ipairs({ "SetMouseMotionEnabled", "SetMouseClickEnabled" }) do
            slot[n] = function(me, v) me._order[#me._order + 1] = n; me["_" .. n] = v end
        end
        slot.SetHideTooltipInCombat = function(me, v) me._order[#me._order + 1] = "SetHideTooltipInCombat" end
        slot.IsMouseClickEnabled = function(me) return me._SetMouseClickEnabled ~= false end
        slot.IsMouseMotionEnabled = function(me) return me._SetMouseMotionEnabled ~= false end
        if __acPropagate then
            slot.SetPropagateMouseClicks = function(me, v) me._propClicks = v end
            slot.SetPropagateMouseMotion = function(me, v) me._propMotion = v end
        end
        slot.SetIcon = function(me, tex) me._order[#me._order + 1] = "SetIcon"; me._icon = tex end
        slot.SetDurationText = function(me, fs) me._order[#me._order + 1] = "SetDurationText"; me._durationText = fs end
        slot.SetApplicationCount = function(me, fs) me._order[#me._order + 1] = "SetApplicationCount"; me._countText = fs end
        return slot
    end
    local function runInit(slot, opts)
        slot._slotRestricted = false          -- initializeFrame runs before the frame turns restricted
        opts.initializeFrame(slot)
        slot._slotRestricted = true
        if __acMouseOn then slot._SetMouseClickEnabled, slot._SetMouseMotionEnabled = true, true end
        if __acOverride == "init" then
            slot._points = {}
            slot._SetPointDirect = true
            slot._points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "BOTTOMLEFT", x = 7, y = 9 }
        elseif __acOverride == "sticky" then
            slot._forceLeft, slot._forceTop = 7, 9
        end
    end
    function __acFlush()
        local list = __acPending
        __acPending = {}
        for _, e in ipairs(list) do runInit(e.slot, e.opts) end
    end
    local function install(me, slot, opts)
        if __acLazy then __acPending[#__acPending + 1] = { slot = slot, opts = opts } else runInit(slot, opts) end
    end
    function CreateFrame(kind, name, parent, tmpl)
        if kind ~= "AuraContainer" then return create(kind, name, parent, tmpl) end
        __acAttempts = __acAttempts + 1
        if __acThrows == true then error("boom: CreateFrame AuraContainer") end
        if type(__acThrows) == "number" and __acThrows > 0 then
            __acThrows = __acThrows - 1
            error("boom: CreateFrame AuraContainer")
        end
        assert(tmpl == "CustomAuraContainerTemplate", "wrong template")
        local f = create("Frame", name, parent)
        f._kind = "AuraContainer"
        f._slots, f._ench, f._enabled = {}, {}, false
        __acs[#__acs + 1] = f
        logged(f, "SetUnit", function(me, u) me._unit = u end)
        logged(f, "SetEnabled", function(me, v) if not __acRefuse then me._enabled = v and true or false end end)
        f.IsEnabled = function(me) return me._enabled end
        local show, hide = f.Show, f.Hide
        logged(f, "Show", function(me) if not __acRefuse then show(me) end end)
        logged(f, "Hide", function(me) if not __acRefuse then hide(me) end end)
        local setAlpha = f.SetAlpha
        logged(f, "SetAlpha", function(me, a) setAlpha(me, a) end)
        local setSize, setPoint = f.SetSize, f.SetPoint
        logged(f, "SetSize", function(me, ...) setSize(me, ...) end)
        logged(f, "SetPoint", function(me, ...) setPoint(me, ...) end)
        logged(f, "SetFrameLevel", function(me, l) me._level = l end)
        logged(f, "AddAuraSlot", function(me, key, filter, opts)
            assert(type(key) == "string" and key ~= "", "slotKey must be a non-empty string")
            assert(filter == "HELPFUL", "bad filter " .. tostring(filter))
            assert(type(opts) == "table" and type(opts.initializeFrame) == "function", "initializeFrame required")
            local ids = opts.candidateFilters and opts.candidateFilters.includeSpellIDs
            assert(type(ids) == "table", "includeSpellIDs must be a table")
            for id, v in pairs(ids) do assert(type(id) == "number" and v == true, "includeSpellIDs is id -> true") end
            if __acSlotThrows == "shield" then error("boom: AddAuraSlot") end
            local slot = newSlot(me)
            me._slots[key] = { filter = filter, ids = ids, frame = slot }
            install(me, slot, opts)
            return slot
        end)
        if not __noEnchantApi then
            logged(f, "SetItemEnchantmentLayout", function(me, layout) assert(type(layout) == "table"); me._layout = layout end)
            logged(f, "AddItemEnchantment", function(me, which, opts)
                assert(which == 1 or which == 2, "bad enchantment slot")
                assert(type(opts) == "table" and type(opts.initializeFrame) == "function", "initializeFrame required")
                if __acEnchThrows == true or __acSlotThrows == "imbue" or (__acEnchThrows == "main" and which == 1)
                    or (__acEnchThrows == "off" and which == 2) then
                    error("boom: AddItemEnchantment")
                end
                local slot = newSlot(me)
                me._ench[which] = slot
                me._enchOrder = me._enchOrder or {}
                me._enchOrder[#me._enchOrder + 1] = which
                install(me, slot, opts)
                return slot
            end)
        end
        return f
    end
end
-- equipment: slot -> item id, item id -> equip location
__eq, __loc, __eqMode = {}, {}, nil
function GetInventoryItemID(unit, slot)
    if __eqMode == "throw" then error("GetInventoryItemID blew up") end
    if __eqMode == "secret" then return __SECRET end
    return __eq[slot]
end
C_Item = C_Item or {}
C_Item.GetItemInfoInstant = function(id) return id, "Weapon", "Sword", __loc[id], 1 end
function __weapon(slot, loc)
    __nextItem = (__nextItem or 500) + 1
    __eq[slot] = __nextItem
    __loc[__nextItem] = loc or "INVTYPE_WEAPON"
end
-- the weapon tooltip: slot -> list of left texts ("<secret>" is a secret one)
__tip, __tipMode, __tipCalls = {}, nil, {}
C_TooltipInfo = {
    GetInventoryItem = function(unit, slot)
        __tipCalls[#__tipCalls + 1] = { slot = slot, combat = __combat and true or false }
        if __tipMode == "throw" then error("GetInventoryItem blew up") end
        if __tipMode == "secret" then return __SECRET end
        if __tipMode == "nolines" then return {} end
        local lines = __tip[slot]
        if not lines then return nil end
        local out = {}
        for i, text in ipairs(lines) do out[i] = { leftText = (text == "<secret>") and __SECRET or text, type = 0 } end
        return { lines = out }
    end,
}
-- GetWeaponEnchantInfo answers false/nil on this client; a case may make it answer true
__gwei = { false, 0, 0, 0, false, 0, 0, 0 }
function GetWeaponEnchantInfo() return unpack(__gwei) end
-- the player aura snapshot (frozen in combat)
__snap = { buffs = {} }
FS.PlayerAuras = { Get = function() return __snap end, IsFrozen = function() return __combat and true or false end }
function __shield(count, remaining, duration)
    __snap = { buffs = { { name = "Lightning Shield", count = count, spellId = 324,
        expirationTime = remaining and (__now + remaining) or 0, duration = duration or 600 } } }
end
function __water() __snap = { buffs = { { name = "Water Shield", count = 3, spellId = 24398, expirationTime = __now + 600 } } } end
function __noshield() __snap = { buffs = { { name = "Mark of the Wild", count = 0, expirationTime = 0 } } } end
function __castOk(id) __fire_event("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", id) end
function __tickAll(dt)
    __advance(dt)
    local list = {}
    for _, f in ipairs(__frames) do if f._scripts.OnUpdate then list[#list + 1] = f end end
    for _, f in ipairs(list) do f._scripts.OnUpdate(f, dt) end
end
"""


def boot(scale: float = 1.0, *, klass: str = "SHAMAN", spells=("Rockbiter Weapon", "Lightning Shield"),
         weapons=None, tips=None, combat: bool = False, console: bool = True, pre_login: str = ""):
    """A Shaman world. `spells`: spell names the spellbook knows; `weapons`: {slot: equip location}; `tips`: {slot:
    [tooltip lines]}."""
    mocks = tbh.MOCKS % dict(guid=GUID, bar=tbh.BAR, all="{}") + "\n" + MOCKS
    setup = []
    for name, sid in ALL_SPELLS.items():
        setup.append(f'__spell("{name}", {sid}, {"true" if name in spells else "false"})')
    for slot, loc in (weapons or {}).items():
        setup.append(f'__weapon({slot}, "{loc}")')
    for slot, lines in (tips or {}).items():
        items = ",".join('"%s"' % x for x in lines)
        setup.append(f"__tip[{slot}] = {{{items}}}")
    return sb.boot(scale, klass=klass, known=[], combat=combat, console=console,
                   extra_lua=csh.PATCH + mocks + "\n" + "\n".join(setup),
                   extra_files=(csh.PETDOCK, csh.CLASSSHOULDER, tbh.TOTEMPIECE, tbh.TOTEMBAR, SHAMANBUFFS, BUFFTAB),
                   pre_login=csh.SPIES + pre_login)


def btn(lua, i):
    return g(lua)[f"FSBuffTabButton{i}"]


IMBUE, SHIELD = 1, 2


def attr(b, name):
    return b._attrs[name]


def shown(b) -> bool:
    return bool(b._shown)


def bt(lua):
    return g(lua).FS.BuffTab


def sbuf(lua):
    return g(lua).FS.ShamanBuffs


def view(lua, key):
    return sbuf(lua).View()[key]


def update(lua):
    """One tick of the tab: the data refreshed and the tiles repainted."""
    sbuf(lua).Update()
    bt(lua).Paint()


def tick(lua, dt):
    lua.eval("__tickAll")(dt)


def run(lua, code):
    lua.execute(code)


def tip(lua, slot, lines):
    items = "nil" if lines is None else "{" + ",".join('"%s"' % x for x in lines) + "}"
    run(lua, f"__tip[{slot}] = {items}")


def cast(lua, name):
    run(lua, f"__castOk({ALL_SPELLS[name]})")


def leave_combat(lua):
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")


def rgb(v):
    return tuple(float(v[i]) for i in (1, 2, 3))


def close(a, b, what, tol=1.2e-2):
    for i in range(3):
        assert abs(a[i] - b[i]) <= tol, f"{what}: {tuple(round(x, 4) for x in a)} != {tuple(round(x, 4) for x in b)}"


def tip_calls(lua):
    t = g(lua).__tipCalls
    return [(int(t[i].slot), bool(t[i].combat)) for i in range(1, len(t) + 1)]


def tile(lua, i):
    """What a tile shows: chip code, text, chip stroke / fill colours and alpha, border, underline."""
    b = btn(lua, i)
    return dict(
        code=b.fsChip.code._text, text=b.fsText._text, chip=rgb(b.fsChip.ring._vertex),
        fill=rgb(b.fsChip.fill._vertex), fill_a=float(b.fsChip.fill._vertex[4]),
        ring=rgb(b.fsSkin.border.ring._vertex), ring_a=float(b.fsSkin.border.ring._vertex[4]),
        text_color=rgb(b.fsText._textColor), text_a=float(b.fsText._textColor[4]),
        code_color=rgb(b.fsChip.code._textColor), line=rgb(b.fsLine._vertex), line_a=float(b.fsLine._vertex[4]),
        dashes=[float(d._alpha) for d in [b.fsDashes[k] for k in range(1, 5)]],
        plate=rgb(b.fsPlate._vertex), plate_a=float(b.fsPlate._vertex[4]),
        glow=rgb(b.fsSkin.glow._vertex), glow_a=float(b.fsSkin.glow._vertex[4]),
        chip_glow=rgb(b.fsChip.glow._vertex), px=float(b.fsText._font[2]),
    )


def tip_text(lua, i):
    b = btn(lua, i)
    run(lua, "GameTooltip._lines = {}")
    lua.eval("__Region.Fire")(b, "OnEnter")
    return [str(x) for x in csh.seq(g(lua).GameTooltip._lines)]


MIN = 60


def assert_warn_is_red(t, what):
    """The missing state is the alert red on EVERY part: border, glow, plate, chip stroke, chip glow, chip fill, code,
    word and underline (not amber, which does not pop)."""
    red = C["red"]
    for part in ("ring", "glow", "chip", "chip_glow", "code_color", "text_color", "line"):
        close(t[part], red, f"{what} {part}")
    close(t["fill"], _mix(BG, red, MK["warn_fill"]), f"{what} chip fill")
    close(t["plate"], _mix(BG, red, 0.1), f"{what} plate")
    approx(t["ring_a"], MK["ring_alpha"]["warn"], f"{what} border alpha")
    for part in ("ring", "chip", "code_color", "text_color", "line"):
        assert dist(t[part], C["amber"]) > 0.2, f"{what} {part} is still amber"


def one_hand(lua, line="Rockbiter 1 (56 min)"):
    """Boot-after helper: a main hand weapon carrying `line`, read."""
    tip(lua, 16, [line])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)


def world(scale: float = 1.0, **kw):
    """A Shaman with a main hand weapon (and what `tips` says is on it), after the first sync."""
    kw.setdefault("weapons", {16: "INVTYPE_WEAPON"})
    return boot(scale, **kw)


# ---------------------------------------------------------------------------------------------
# Checks: the tooltip parse
# ---------------------------------------------------------------------------------------------


def parse(lua, text):
    r = sbuf(lua).ParseImbueLine(text)
    if r is None:
        return None
    code, secs, unit = r
    return str(code), float(secs), float(unit)


def check_parse_reads_minutes_seconds_hours_with_and_without_a_rank():
    lua = boot()
    cases = {
        "Rockbiter 1 (56 min)": ("RB", 56 * 60, 60),
        "Rockbiter 7 (1 min)": ("RB", 60, 60),
        "Flametongue 3 (59 min)": ("FT", 59 * 60, 60),
        "Frostbrand 2 (30 sec)": ("FB", 30, 1),
        "Windfury 1 (1 hour)": ("WF", 3600, 3600),
        "Windfury Weapon (5 min)": ("WF", 300, 60),
        "Rockbiter (12 min)": ("RB", 720, 60),
        "Flametongue IV (12 min)": ("FT", 720, 60),
        "|cff1eff00Frostbrand 1|r (45 min)": ("FB", 2700, 60),
    }
    for text, want in cases.items():
        assert parse(lua, text) == want, f"{text!r} parsed as {parse(lua, text)}, want {want}"


def check_parse_ignores_lines_that_are_not_an_imbue_with_a_time():
    lua = boot()
    for text in ("Crusader (56 min)", "Rockbiter 1", "Rockbiter 1 (56 min) extra", "Durability 100 / 100", "",
                 "Flametongue Totem (5 min)", "Requires Level 10", "(56 min)", "Rockbiter 1 (soon)"):
        assert parse(lua, text) is None, f"{text!r} parsed as {parse(lua, text)}"
    for bad in ("nil", "42", "{}", "__SECRET"):
        assert lua.eval(f"FS.ShamanBuffs.ParseImbueLine({bad})") is None, f"{bad} parsed"


def check_parse_follows_the_clients_own_enchant_time_strings_and_spell_names():
    # a localized client: the spell names and Blizzard's time strings come from the client, not from this file
    lua = boot(pre_login=r"""
        ITEM_ENCHANT_TIME_LEFT_MIN = "%s (%d |4Minute:Min;)"
        ITEM_ENCHANT_TIME_LEFT_SEC = "%s [%d s]"
        __idNames[8017] = "Armeroc Arme"
        __spells["Armeroc Arme"] = 8017
    """)
    assert parse(lua, "Armeroc 2 (40 Min)") == ("RB", 2400, 60), parse(lua, "Armeroc 2 (40 Min)")
    assert parse(lua, "Armeroc Arme [20 s]") == ("RB", 20, 1), parse(lua, "Armeroc Arme [20 s]")
    # the English short names keep working next to the localized ones
    assert parse(lua, "Flametongue 1 (3 Min)") == ("FT", 180, 60)
    # a client with none of the Blizzard strings falls back to the English ones
    lua = boot(pre_login="ITEM_ENCHANT_TIME_LEFT_MIN = nil; ITEM_ENCHANT_TIME_LEFT_SEC = 12")
    assert parse(lua, "Rockbiter 1 (56 min)") == ("RB", 3360, 60)
    assert parse(lua, "Rockbiter 1 (9 sec)") == ("RB", 9, 1)


def check_the_imbue_names_come_from_the_spell_ids_not_from_english_text():
    lua = boot(pre_login='__idNames[8024] = "Zungenflamme Waffe"; __spells["Zungenflamme Waffe"] = 8024')
    assert parse(lua, "Zungenflamme 1 (10 min)") == ("FT", 600, 60)


def read_tip(lua, slot):
    r = sbuf(lua).ReadTooltip(slot)
    return r if isinstance(r, str) else r


def check_tooltip_reads_say_imbue_none_or_unreadable():
    lua = world(tips={16: ["Heavy Axe", "Rockbiter 1 (56 min)", "Durability 90 / 100"]})
    r = sbuf(lua).ReadTooltip(16)
    assert tuple(r)[:1] == ("imbue",), r
    tip(lua, 16, ["Heavy Axe", "Durability 90 / 100"])
    assert str(sbuf(lua).ReadTooltip(16)) == "none"
    tip(lua, 16, ["Heavy Axe", "<secret>", "Durability 90 / 100"])
    assert str(sbuf(lua).ReadTooltip(16)) == "unreadable", "a secret line could hide the imbue"
    tip(lua, 16, ["Rockbiter 1 (56 min)", "<secret>"])
    assert str(sbuf(lua).ReadTooltip(16)[0]) == "imbue", "a plain imbue line wins over a secret one"
    for mode in ("throw", "secret", "nolines"):
        run(lua, f'__tipMode = "{mode}"')
        assert str(sbuf(lua).ReadTooltip(16)) == "unreadable", mode
    run(lua, "__tipMode = nil; C_TooltipInfo = nil")
    assert str(sbuf(lua).ReadTooltip(16)) == "unreadable", "no tooltip API"


# ---------------------------------------------------------------------------------------------
# Checks: the imbue model
# ---------------------------------------------------------------------------------------------


def check_the_main_hand_imbue_shows_its_code_and_time_in_the_quiet_look():
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    v = view(lua, "imbue")
    assert (v.mode, v.code, v.text) == ("on", "RB", "56m"), (v.mode, v.code, v.text)
    t = tile(lua, IMBUE)
    assert (t["code"], t["text"]) == ("RB", "56m")
    close(t["chip"], C["gold"], "quiet chip stroke")
    close(t["fill"], _mix(BG, C["gold"], MK["on_fill"]), "quiet chip fill")
    close(t["ring"], C["violet"], "quiet border")
    approx(t["ring_a"], MK["ring_alpha"]["on"], "quiet border alpha")
    close(t["code_color"], C["white"], "quiet code", 0.06)
    close(t["text_color"], C["fg"], "quiet text")
    approx(t["text_a"], MK["on_text"], "quiet text alpha")
    close(t["line"], C["gold"], "quiet underline")
    assert t["dashes"] == [0.0] * 4, "the dashes are the shield estimate's only"
    for code, name in (("FT", "Flametongue"), ("FB", "Frostbrand"), ("WF", "Windfury")):
        tip(lua, 16, [f"{name} 1 (59 min)"])
        fire(lua, "UNIT_INVENTORY_CHANGED", "player")
        update(lua)
        assert tile(lua, IMBUE)["code"] == code, name


def check_under_five_minutes_the_tile_turns_pink_and_under_one_minute_counts_seconds():
    lua = world(tips={16: ["Rockbiter 1 (5 min)"]})
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("exp", "5m"), (v.mode, v.text)
    t = tile(lua, IMBUE)
    close(t["chip"], C["pink"], "expiring chip")
    close(t["fill"], _mix(BG, C["pink"], MK["exp_fill"]), "expiring chip fill")
    close(t["ring"], C["pink"], "expiring border"), approx(t["ring_a"], MK["ring_alpha"]["exp"], "expiring border alpha")
    close(t["text_color"], C["pink"], "expiring text"), approx(t["text_a"], 1.0, "expiring text alpha")
    close(t["line"], C["pink"], "expiring underline")
    tip(lua, 16, ["Rockbiter 1 (6 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert view(lua, "imbue").mode == "on", "six minutes is still quiet"
    tip(lua, 16, ["Rockbiter 1 (42 sec)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)
    assert (view(lua, "imbue").mode, tile(lua, IMBUE)["text"]) == ("exp", "42s")


def check_a_missing_imbue_is_a_red_hollow_word_and_an_unreadable_one_a_hollow_question_mark():
    lua = world(tips={16: ["Heavy Axe"]})
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("warn", "IMBUE"), (v.mode, v.text)
    t = tile(lua, IMBUE)
    assert_warn_is_red(t, "missing imbue")
    assert t["text"] == "IMBUE"
    # nothing to go on: no tooltip data at all
    lua = world(pre_login='__tipMode = "throw"')
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("hollow", "?"), (v.mode, v.text)
    t = tile(lua, IMBUE)
    close(t["ring"], C["muted"], "hollow border"), approx(t["ring_a"], MK["ring_alpha"]["hollow"], "hollow alpha")
    close(t["text_color"], C["muted"], "hollow ?"), assert_eq(t["text"], "?")
    close(t["line"], C["muted"], "hollow underline")
    # no weapon at all: nothing to imbue, so no nagging
    lua = boot(weapons={})
    assert view(lua, "imbue").mode == "hollow", view(lua, "imbue").mode


def assert_eq(a, b, what=""):
    assert a == b, f"{what} {a!r} != {b!r}"


def check_dual_wield_shows_the_least_time_and_asks_for_the_missing_hand():
    lua = boot(weapons={16: "INVTYPE_WEAPONMAINHAND", 17: "INVTYPE_WEAPONOFFHAND"},
               tips={16: ["Windfury 1 (50 min)"], 17: ["Flametongue 1 (20 min)"]})
    v = view(lua, "imbue")
    assert (v.mode, v.code, v.text, v.hand) == ("on", "FT", "20m", "off"), (v.mode, v.code, v.text, v.hand)
    tip(lua, 17, ["Light Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    v = view(lua, "imbue")
    assert (v.mode, v.text, v.lackHand) == ("warn", "IMBUE", "off"), (v.mode, v.text, v.lackHand)
    tip(lua, 16, ["Heavy Axe"])
    tip(lua, 17, ["Windfury 1 (9 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert (view(lua, "imbue").mode, view(lua, "imbue").lackHand) == ("warn", "main")


def check_a_shield_or_an_empty_off_hand_never_asks_for_an_imbue():
    for off in ({}, {17: "INVTYPE_SHIELD"}, {17: "INVTYPE_HOLDABLE"}):
        lua = boot(weapons={**{16: "INVTYPE_2HWEAPON" if not off else "INVTYPE_WEAPON"}, **off},
                   tips={16: ["Rockbiter 1 (30 min)"], 17: ["Block 12", "Rockbiter 1 (30 min)"]})
        v = view(lua, "imbue")
        assert (v.mode, v.text) == ("on", "30m"), f"{off}: {v.mode} {v.text}"
    lua = boot(weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (30 min)"]})
    run(lua, "__loc[__eq[16]] = nil")        # an item the client cannot class: nothing to say about that hand
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert view(lua, "imbue").mode != "warn"


def check_a_two_handed_weapon_without_an_imbue_asks_for_one():
    lua = boot(weapons={16: "INVTYPE_2HWEAPON"}, tips={16: ["Great Maul"]})
    assert view(lua, "imbue").mode == "warn"


def check_the_tooltip_is_never_read_in_combat_and_the_clock_counts_down_from_the_last_read():
    lua = world(tips={16: ["Rockbiter 1 (10 min)"]})
    before = len(tip_calls(lua))
    assert view(lua, "imbue").text == "10m"
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    for event in ("UNIT_INVENTORY_CHANGED", "PLAYER_EQUIPMENT_CHANGED", "SPELLS_CHANGED"):
        fire(lua, event, "player")
    tick(lua, 30)
    tick(lua, 30)
    tick(lua, 400)
    assert all(not c for _, c in tip_calls(lua)), f"the tooltip was read in combat: {tip_calls(lua)}"
    assert len(tip_calls(lua)) == before, "no read at all happened in combat"
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("exp", "2m"), (v.mode, v.text)         # 10 min less 460 s is 2m 20s
    tick(lua, 60)
    assert view(lua, "imbue").text == "1m", view(lua, "imbue").text
    tick(lua, 30)
    assert view(lua, "imbue").text == "50s", view(lua, "imbue").text
    tick(lua, 60)
    assert view(lua, "imbue").mode == "warn", "an imbue that ran out in combat asks for another"


def check_the_slow_tick_reads_out_of_combat_and_a_read_does_not_stair_step_the_clock():
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    reads = len(tip_calls(lua))
    tick(lua, 1)
    assert len(tip_calls(lua)) == reads, "the slow tick is not every second"
    tick(lua, 6)
    assert len(tip_calls(lua)) > reads, "the slow tick reads the weapon out of combat"
    # one minute later the tooltip says 55: the clock stays continuous
    tick(lua, 54)
    tip(lua, 16, ["Rockbiter 1 (55 min)"])
    tick(lua, 6)
    r = float(view(lua, "imbue").remaining)
    assert 3300 - 5 <= r <= 3360 + 1, f"remaining {r} jumped"
    # a real change (the tooltip says 40) is taken at once
    tip(lua, 16, ["Rockbiter 1 (40 min)"])
    tick(lua, 6)
    approx(float(view(lua, "imbue").remaining), 2400, "a real change is taken", 1.0)


def check_a_cast_starts_a_fresh_hour_and_the_next_read_takes_over():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"), tips={16: ["Heavy Axe"]})
    assert view(lua, "imbue").mode == "warn"
    cast(lua, "Flametongue Weapon")
    update(lua)
    v = view(lua, "imbue")
    assert (v.mode, v.code, v.text) == ("on", "FT", "60m"), (v.mode, v.code, v.text)
    tip(lua, 16, ["Flametongue 1 (59 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert (view(lua, "imbue").code, view(lua, "imbue").text) == ("FT", "59m")


def check_a_cast_in_combat_counts_a_fresh_hour_and_a_weapon_swapped_in_combat_is_forgotten():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"), tips={16: ["Rockbiter 1 (3 min)"]})
    set_combat(lua, True)
    cast(lua, "Flametongue Weapon")
    update(lua)
    v = view(lua, "imbue")
    assert (v.mode, v.code, v.text) == ("on", "FT", "60m"), (v.mode, v.code, v.text)
    assert all(not c for _, c in tip_calls(lua))
    fire(lua, "PLAYER_EQUIPMENT_CHANGED", 16, True)
    update(lua)
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("hollow", "?"), "a weapon swapped in combat shows nothing rather than a stale time"
    tip(lua, 16, ["Frostbrand 1 (25 min)"])
    leave_combat(lua)
    v = view(lua, "imbue")
    assert (v.mode, v.code, v.text) == ("on", "FB", "25m"), (v.mode, v.code, v.text)


def check_two_imbue_casts_back_to_back_each_go_to_their_own_hand():
    # the old chip taught one enchant id from two casts; the model now has no ids to teach (old finding 1)
    lua = boot(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
               weapons={16: "INVTYPE_WEAPONMAINHAND", 17: "INVTYPE_WEAPONOFFHAND"}, tips={16: ["Heavy"], 17: ["Light"]})
    set_combat(lua, True)
    cast(lua, "Rockbiter Weapon")
    cast(lua, "Flametongue Weapon")
    v = view(lua, "imbue")
    assert v.mode == "on" and v.text == "60m", (v.mode, v.text)
    set_combat(lua, False)
    tip(lua, 16, ["Rockbiter 1 (59 min)"])
    tip(lua, 17, ["Flametongue 1 (59 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert view(lua, "imbue").mode == "on"


def check_a_recast_on_the_other_hand_does_not_hide_the_sooner_expiring_one():
    # old finding 2: the same imbue cast again showed 60m for up to ten seconds, hiding the 5m hand
    lua = boot(weapons={16: "INVTYPE_WEAPONMAINHAND", 17: "INVTYPE_WEAPONOFFHAND"},
               tips={16: ["Rockbiter 1 (5 min)"], 17: ["Heavy"]})
    assert view(lua, "imbue").mode == "warn"
    cast(lua, "Rockbiter Weapon")           # lands on the off hand (the one without)
    update(lua)
    v = view(lua, "imbue")
    assert (v.mode, v.hand, v.text) == ("exp", "main", "5m"), (v.mode, v.hand, v.text)
    # both imbued: a recast replaces the main hand
    tip(lua, 17, ["Rockbiter 1 (59 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    cast(lua, "Rockbiter Weapon")
    update(lua)
    assert view(lua, "imbue").hand == "off" and view(lua, "imbue").text == "59m"


def check_a_pending_cast_outlasts_an_early_none_read_only_for_the_grace():
    lua = world(spells=("Rockbiter Weapon", "Lightning Shield"), tips={16: ["Heavy Axe"]})
    cast(lua, "Rockbiter Weapon")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")          # the weapon has not caught up yet
    assert view(lua, "imbue").mode == "on"
    tick(lua, 3)                                            # the scheduled reads ran: it never caught up
    assert view(lua, "imbue").mode == "warn", view(lua, "imbue").mode


def check_get_weapon_enchant_info_counts_only_when_it_answers_true():
    lua = world(tips={16: ["Heavy Axe"]})
    assert view(lua, "imbue").mode == "warn"
    run(lua, f"__gwei = {{ true, 1800000, 0, 0, false, 0, 0, 0 }}")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    v = view(lua, "imbue")
    assert (v.mode, v.text) == ("on", "30m"), (v.mode, v.text)
    # secret or false answers add nothing
    lua = world(tips={16: ["Heavy Axe"]})
    run(lua, "__gwei = { __SECRET, __SECRET, 0, 0, __SECRET, __SECRET, 0, 0 }")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert view(lua, "imbue").mode == "warn"


def check_no_imbue_known_means_no_tile_and_learning_one_brings_it():
    lua = boot(spells=("Lightning Shield",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Heavy Axe"]})
    b = btn(lua, IMBUE)
    assert not shown(b), "the imbue tile is absent while no imbue is known"
    assert attr(b, "spell") is None and attr(b, "type") is None
    run(lua, '__learn("Rockbiter Weapon")')
    run(lua, '__spell("Rockbiter Weapon", 8017, true)')
    fire(lua, "SPELLS_CHANGED")
    assert shown(b) and attr(b, "spell") == "Rockbiter Weapon" and not b.fsLocked
    # an imbue on the weapon from another source is shown even with none known
    lua = boot(spells=("Lightning Shield",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Windfury 1 (30 min)"]})
    assert view(lua, "imbue").mode == "on"


# ---------------------------------------------------------------------------------------------
# Checks: the shield model
# ---------------------------------------------------------------------------------------------


def check_the_shield_shows_ls_and_its_orbs_then_its_time_when_expiring():
    lua = world()
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    t = tile(lua, SHIELD)
    assert (t["code"], t["text"]) == ("LS", "3"), t
    close(t["chip"], C["gold"], "shield chip")
    run(lua, "__shield(1, 480)")
    fire(lua, "UNIT_AURA", "player")
    assert (tile(lua, SHIELD)["text"]) == "1" or view(lua, "shield").text == "1"
    run(lua, "__shield(2, 240)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    v = view(lua, "shield")
    assert (v.mode, v.text) == ("exp", "4m"), (v.mode, v.text)
    close(tile(lua, SHIELD)["chip"], C["pink"], "expiring shield chip")
    run(lua, "__shield(2, 38)")
    fire(lua, "UNIT_AURA", "player")
    assert view(lua, "shield").text == "38s"


def check_a_missing_shield_is_red_and_no_snapshot_yet_is_a_hollow_question_mark():
    lua = world()
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    v = view(lua, "shield")
    assert (v.mode, v.text) == ("warn", "SHIELD"), (v.mode, v.text)
    t = tile(lua, SHIELD)
    assert_warn_is_red(t, "missing shield")
    lua = world(pre_login="FS.PlayerAuras = nil")
    v = view(lua, "shield")
    assert (v.mode, v.text) == ("hollow", "?"), (v.mode, v.text)
    run(lua, "FS.PlayerAuras = { Get = function() return __snap end, IsFrozen = function() return false end }; __noshield()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert btn(lua, SHIELD).fsTextPx < 11, "the word SHIELD is set small to fit the tile"


def check_in_combat_the_shield_is_an_estimate_with_a_tilde_and_dashes():
    lua = world()
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    update(lua)
    v = view(lua, "shield")
    assert (v.mode, v.text, bool(v.estimate)) == ("on", "~3", True), (v.mode, v.text, v.estimate)
    assert tile(lua, SHIELD)["dashes"] == [1.0] * 4, "the estimate underline is dashed"
    assert any("cannot be read in combat" in x for x in tip_text(lua, SHIELD))
    leave_combat(lua)
    tick(lua, 1)
    assert tile(lua, SHIELD)["dashes"] == [0.0] * 4 and view(lua, "shield").text == "3"


def check_a_shield_cast_in_combat_shows_three_orbs_and_a_pending_cast_expires_with_the_clock():
    lua = world()
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    cast(lua, "Lightning Shield")
    update(lua)
    assert (view(lua, "shield").mode, view(lua, "shield").text) == ("on", "~3")
    tick(lua, 601)
    assert view(lua, "shield").mode == "warn", "after its ten minutes with nothing to confirm it, the shield is asked for"


def check_water_shield_is_never_nagged_and_a_water_shield_cast_in_combat_clears_the_lightning_cast():
    lua = world(spells=("Rockbiter Weapon", "Lightning Shield", "Water Shield"))
    run(lua, "__water()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    v = view(lua, "shield")
    assert (v.mode, v.text, bool(v.other)) == ("hollow", "WS", True), (v.mode, v.text, v.other)
    assert any("Water Shield is active" in x for x in tip_text(lua, SHIELD))
    # old finding 3: a Water Shield cast in combat must clear the pending cast and not nag
    lua = world(spells=("Rockbiter Weapon", "Lightning Shield", "Water Shield"))
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    cast(lua, "Lightning Shield")
    cast(lua, "Water Shield")
    update(lua)
    v = view(lua, "shield")
    assert (v.mode, bool(v.other)) == ("hollow", True), (v.mode, v.other)
    tick(lua, 5)
    assert view(lua, "shield").mode == "hollow", "the stale Lightning Shield cast no longer makes the shield 'up'"
    # and a Lightning Shield cast over a Water Shield takes the quiet state back
    cast(lua, "Lightning Shield")
    update(lua)
    assert view(lua, "shield").mode == "on"


def check_a_shield_with_no_aura_end_ends_at_its_application_not_at_the_last_read():
    # old finding 4: the fallback was the last live read plus ten minutes, which outlives a shield read mid life
    lua = world()
    run(lua, "__shield(3, nil)")                  # expirationTime 0: the aura told no end
    fire(lua, "UNIT_AURA", "player")
    start = float(g(lua).__now)
    tick(lua, 400)
    run(lua, "__shield(2, nil)")                  # a charge went: a later live read, same application
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    update(lua)
    assert view(lua, "shield").mode in ("on", "exp")
    tick(lua, 150)                                # 550 s since the application, 150 s since the last read
    assert view(lua, "shield").mode in ("on", "exp"), view(lua, "shield").mode
    tick(lua, 60)                                 # 610 s since the application: gone, though the last read was 210 s ago
    assert view(lua, "shield").mode == "warn", f"started {start}, now {g(lua).__now}: {view(lua, 'shield').mode}"
    # the aura's own end wins when it has one
    lua = world()
    run(lua, "__shield(3, 100)")
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    tick(lua, 50)
    assert view(lua, "shield").mode == "exp"
    tick(lua, 60)
    assert view(lua, "shield").mode == "warn"


def check_lightning_shield_is_a_locked_dotted_mold_until_it_is_known():
    lua = boot(spells=("Rockbiter Weapon",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (30 min)"]})
    b = btn(lua, SHIELD)
    assert shown(b), "a locked tile is dimmed by alpha, never hidden"
    assert b.fsLocked and abs(float(b._alpha) - 0.4) < 1e-6, f"alpha {b._alpha}"
    assert view(lua, "shield").mode == "locked"
    assert attr(b, "type") is None and attr(b, "spell") is None, "a locked tile carries nothing castable"
    assert shown(b.fsMold) and shown(b.fsLockText) and b.fsLockText._text == "L8", b.fsLockText._text
    assert not shown(b.fsFace), "the face is hidden while locked"
    assert "Opens at level 8." in tip_text(lua, SHIELD)
    # learned: the mold goes, the tile is live
    run(lua, '__spell("Lightning Shield", 324, true)')
    fire(lua, "SPELLS_CHANGED")
    assert not b.fsLocked and abs(float(b._alpha) - 1.0) < 1e-6
    assert shown(b.fsFace) and not shown(b.fsMold) and not shown(b.fsLockText)
    assert attr(b, "type") == "spell" and attr(b, "spell") == "Lightning Shield"
    # the imbue tile never locks
    assert not btn(lua, IMBUE).fsLocked and btn(lua, IMBUE).fsDef.unlock is None
    # the level on the mold is the spell's, the mockup's
    assert int(btn(lua, SHIELD).fsDef.unlock) == 8
    assert "L8" in MOCKUP.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Checks: secure buttons
# ---------------------------------------------------------------------------------------------


def check_two_named_secure_buttons_in_the_fixed_order_built_once():
    lua = world(tips={16: ["Rockbiter 1 (30 min)"]})
    for i, key in ((1, "imbue"), (2, "shield")):
        b = btn(lua, i)
        assert b is not None and b._secure, f"FSBuffTabButton{i} is not a secure template button"
        assert b.fsKey == key, f"button {i} is {b.fsKey!r}"
        assert [b._clicks[k] for k in range(1, len(b._clicks) + 1)] == ["AnyUp", "AnyDown"]
    for event in ("SPELLS_CHANGED", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED", "UPDATE_BINDINGS"):
        fire(lua, event)
    frames = [f for f in g(lua).__frames.values() if f._name and re.match(r"FSBuffTabButton\d$", f._name)]
    assert len(frames) == 2, f"{len(frames)} named buff buttons, expected exactly 2"


def check_click_attributes_are_a_spell_by_name_and_follow_the_imbue_shown():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Flametongue 1 (30 min)"]})
    imb, shd = btn(lua, IMBUE), btn(lua, SHIELD)
    assert (attr(imb, "type"), attr(imb, "spell")) == ("spell", "Flametongue Weapon"), "casts the imbue its chip shows"
    assert (attr(shd, "type"), attr(shd, "spell")) == ("spell", "Lightning Shield")
    assert sorted(str(k) for k in imb._attrs.keys() if imb._attrs[k] is not None) == ["spell", "type"], \
        "nothing but type and spell"
    # none up: the imbue the tile still shows (the last one seen), else the best known
    tip(lua, 16, ["Heavy Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert attr(imb, "spell") == "Flametongue Weapon", attr(imb, "spell")
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"), tips={16: ["Heavy Axe"]})
    assert attr(btn(lua, IMBUE), "spell") == "Flametongue Weapon", "the best known imbue when none was ever up"
    lua = world(tips={16: ["Heavy Axe"]})
    assert attr(btn(lua, IMBUE), "spell") == "Rockbiter Weapon"


def check_attributes_are_written_out_of_combat_only_and_queued_for_regen():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (30 min)"]})
    imb = btn(lua, IMBUE)
    assert attr(imb, "spell") == "Rockbiter Weapon"
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    cast(lua, "Flametongue Weapon")          # the chip now reads FT
    fire(lua, "UNIT_AURA", "player")
    tip(lua, 16, ["Flametongue 1 (59 min)"])
    tick(lua, 3)
    assert view(lua, "imbue").code == "FT"
    assert attr(imb, "spell") == "Rockbiter Weapon", "an attribute changed in combat"
    assert blocked(lua) == 0, f"{blocked(lua)} protected writes were attempted in combat"
    assert tile(lua, IMBUE)["code"] == "FT", "the paint follows in combat (texture and font writes)"
    leave_combat(lua)
    assert attr(imb, "spell") == "Flametongue Weapon", "regen aims the click at the imbue shown"
    assert blocked(lua) == 0


def check_nothing_protected_is_touched_in_combat_by_events_ticks_and_paint():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield", "Water Shield"),
                tips={16: ["Rockbiter 1 (30 min)"]})
    set_combat(lua, True)
    for event, args in (("UNIT_AURA", ("player",)), ("UNIT_INVENTORY_CHANGED", ("player",)),
                        ("PLAYER_EQUIPMENT_CHANGED", (16, True)), ("SPELLS_CHANGED", ()), ("UPDATE_BINDINGS", ()),
                        ("PLAYER_LEVEL_UP", (20,)), ("PLAYER_ENTERING_WORLD", ())):
        fire(lua, event, *args)
    cast(lua, "Flametongue Weapon")
    cast(lua, "Water Shield")
    tick(lua, 5)
    for i in (IMBUE, SHIELD):
        lua.eval("__Region.Fire")(btn(lua, i), "OnEnter")
        lua.eval("__Region.Fire")(btn(lua, i), "OnLeave")
    assert blocked(lua) == 0, f"{blocked(lua)} protected writes in combat"
    assert int(g(lua).__protectedTouch) == 0, "a frame under the protected host was created or moved in combat"


def check_no_forbidden_field_or_attribute_is_ever_written_on_a_secure_button():
    # Blizzard's secure click path reads .bar, .isExtra, .buttonType, CalculateAction and the useparent-* attributes
    # off the button; an addon written value there taints the click (a real bug fixed in ActionBars.lua, 2026-10-12)
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (30 min)"]})
    forbidden = ("bar", "isExtra", "buttonType", "CalculateAction", "action", "actionButton", "useparent",
                 "UpdateAction", "GetActionId", "GetAction", "HasAction", "SetActionUI")
    for _ in range(2):
        for i in (IMBUE, SHIELD):
            b = btn(lua, i)
            for name in forbidden:
                assert lua.eval("rawget")(b, name) is None, f"button {i} carries a .{name} field"
            for name, value in b._attrs.items():
                assert not str(name).startswith("useparent"), f"button {i} carries {name}"
                assert str(name) in ("type", "spell"), f"button {i} carries the attribute {name}"
        cast(lua, "Flametongue Weapon")
        fire(lua, "SPELLS_CHANGED")
        fire(lua, "PLAYER_ENTERING_WORLD")
    text = BUFFTAB.read_text(encoding="utf-8")
    for name in ("bar", "isExtra", "buttonType", "CalculateAction"):
        assert not re.search(rf"(button|self|b)\.{name}\s*=", text), f"BuffTab.lua writes a .{name} field"
    assert "useparent" not in text, "BuffTab.lua mentions a useparent attribute"


def check_the_files_use_no_snippets_and_no_state_drivers():
    for path in (BUFFTAB, SHAMANBUFFS):
        text = path.read_text(encoding="utf-8")
        for token in ("SecureHandler", "RegisterStateDriver", "RegisterAttributeDriver", "_onstate", "WrapScript",
                      "SetFrameRef", "loadstring", "Execute("):
            assert token not in text, f"{path.name} uses {token}"


# ---------------------------------------------------------------------------------------------
# Checks: tooltip, hover, keybinds
# ---------------------------------------------------------------------------------------------


def check_tooltip_lines_follow_the_mockups_wording():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (59 min)"]})
    text = tip_text(lua, IMBUE)
    assert text == ["Rockbiter Weapon", "Main hand imbue, 59 min left.", "Click: cast Rockbiter Weapon."], text
    tip(lua, 16, ["Rockbiter 1 (42 sec)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert tip_text(lua, IMBUE)[1] == "Main hand imbue, 42 sec left."
    tip(lua, 16, ["Heavy Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert tip_text(lua, IMBUE) == ["Rockbiter Weapon", "No imbue on your main hand.", "Click: cast Rockbiter Weapon."], \
        tip_text(lua, IMBUE)
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    assert tip_text(lua, SHIELD) == ["Lightning Shield", "3 charges, 8 min left.", "Click: cast Lightning Shield."], \
        tip_text(lua, SHIELD)
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    assert tip_text(lua, SHIELD) == ["Lightning Shield", "Not active.", "Click: cast Lightning Shield."]
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    update(lua)
    assert tip_text(lua, SHIELD)[1] == "Charges cannot be read in combat. About 3 left."
    # titles take the tile colour
    lines = bt(lua).TipLines("imbue")
    assert str(lines[1][1]) and len(lines) == 3


def check_the_tooltip_colours_are_gold_pink_red_and_muted():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    def title(key):
        return rgb(bt(lua).TipLines(key)[1][2])
    close(title("imbue"), C["gold"], "quiet title")
    tip(lua, 16, ["Rockbiter 1 (42 sec)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    close(title("imbue"), C["pink"], "expiring title")
    tip(lua, 16, ["Heavy Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    close(title("imbue"), C["red"], "missing title")
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    close(rgb(bt(lua).TipLines("shield")[1][2]), C["red"], "missing shield title")


def check_hover_turns_the_border_cyan_and_leaving_restores_the_state_colour():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    b = btn(lua, IMBUE)
    lua.eval("__Region.Fire")(b, "OnEnter")
    t = tile(lua, IMBUE)
    close(t["ring"], C["cyan"], "hover border")
    lua.eval("__Region.Fire")(b, "OnLeave")
    t = tile(lua, IMBUE)
    close(t["ring"], C["violet"], "border after leaving"), approx(t["ring_a"], MK["ring_alpha"]["on"], "alpha after leaving")
    assert not shown(g(lua).GameTooltip)


def check_hotkey_text_and_quick_keybind_commands():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    for i in (IMBUE, SHIELD):
        b = btn(lua, i)
        assert b.commandName == f"CLICK FSBuffTabButton{i}:LeftButton", f"{i}: {b.commandName!r}"
        assert b.fsQuickKeybindOverlay is not None
    g(lua).__bindings["CLICK FSBuffTabButton2:LeftButton"] = "SHIFT-F"
    fire(lua, "UPDATE_BINDINGS")
    b = btn(lua, SHIELD)
    assert shown(b.HotKey) and b.HotKey._text == "SHIFT-F", f"hotkey {b.HotKey._text!r}"
    g(lua).__bindings["CLICK FSBuffTabButton2:LeftButton"] = None
    lua.eval("__trigger")("KeybindListener.RebindSuccess")
    assert not shown(b.HotKey)


def check_bindings_xml_declares_the_two_buff_tab_commands_after_the_totems():
    root = ET.parse(BINDINGS).getroot()
    names = [b.get("name") for b in root.findall("Binding")]
    want = [f"CLICK FSBuffTabButton{i}:LeftButton" for i in (1, 2)]
    assert names[-2:] == want, f"binding names {names}"
    assert names[:-2] == [f"CLICK FSSealButton{i}:LeftButton" for i in range(1, 8)] + [
        f"CLICK FSTotemButton{i}:LeftButton" for i in range(1, 7)], "the earlier commands moved"
    assert all(b.get("category") == "ADDONS" and not b.get("header") for b in root.findall("Binding")[-2:])


def check_binding_labels_exist_for_every_class():
    for klass in ("SHAMAN", "PALADIN", "WARRIOR"):
        lua = boot(klass=klass)
        for i, label in ((1, "Weapon imbue"), (2, "Lightning Shield")):
            text = g(lua)[f"BINDING_NAME_CLICK FSBuffTabButton{i}:LeftButton"]
            assert text == label, f"{klass}: label {i} is {text!r}, want {label!r}"


# ---------------------------------------------------------------------------------------------
# Checks: the seat
# ---------------------------------------------------------------------------------------------


def check_the_shoulder_is_the_two_by_one_block_at_316_and_the_buttons_sit_inside_it(scale):
    lua = world(scale, tips={16: ["Rockbiter 1 (59 min)"]})
    cs = csh.cs(lua)
    assert cs.IsShown() and cs.IsShown("shamanbuff"), "the buff shoulder does not stand"
    w = 2 * N["PAD"] + 2 * N["BTN"] + N["GAP"]
    h = N["PT"] + N["BTN"] + N["PB"]
    approx(w, N["BUFF_W"], "block width against the mockup"), approx(h, N["BH"], "block height against the mockup")
    # the mockup's own sh(): the totem tab ends at 300 and its foot flare reaches 310, six px before the buff tab
    approx(N["TOTEM_X"] + N["TOTEM_W"] + N["FLARE"] + 6, N["BUFF_X"], "six px of chassis line between the tabs")
    stand = None
    for f in g(lua).__frames.values():
        pts = f._points
        if f._kind == "Frame" and len(pts) == 1 and pts[1].rel is not None and pts[1].rel._name == "FSConsole" \
                and abs(float(pts[1].x) - N["BUFF_X"] * scale) < 0.5 * scale:
            stand = f
    assert stand is not None, "no frame is seated at 316 design px on the Console"
    d = csh.D(lua, stand)
    approx(d["w"], w, "art width in design px", 0.01), approx(d["h"], h, "art height in design px", 0.01)
    approx(d["x"], N["BUFF_X"], "art left", 0.5)
    bw, bh, edge = cs.BlockSize("shamanbuff")
    approx(bw, w * scale, "BlockSize width"), approx(bh, h * scale, "BlockSize height")
    host = g(lua).FSBuffTab
    p = host._points[1]
    assert (p.point, p.rel._name, p.relPoint) == ("BOTTOMLEFT", "FSConsole", "TOPLEFT")
    approx(p.x, N["BUFF_X"] * scale, "host x", 0.5 * scale), approx(p.y, 0, "host y")
    pitch = N["BTN"] + N["GAP"]
    for col in (1, 2):
        b = btn(lua, col)
        q = b._points[1]
        assert sb.same(lua, q.rel, host) and (q.point, q.relPoint) == ("BOTTOMLEFT", "BOTTOMLEFT")
        approx(q.x, (N["PAD"] + (col - 1) * pitch) * scale, f"button {col} x")
        approx(q.y, N["PB"] * scale, f"button {col} y")
        approx(b._w, N["BTN"] * scale, f"button {col} width"), approx(b._h, N["BTN"] * scale, f"button {col} height")
    assert host._level > sb.top_level(g(lua).FSConsole), "the buttons must draw above the chassis"
    assert host._shown
    # the totem tab keeps its own seat and block
    totem = g(lua).FSTotemBar._points[1]
    approx(totem.x, N["TOTEM_X"] * scale, "totem host x", 0.5 * scale)


def check_the_console_gap_is_the_union_and_the_top_line_is_bridged_between_the_tabs():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    gaps = [c for c in csh.calls(lua) if str(c).startswith("gap:")]
    last = [float(x) for x in str(gaps[-1]).split(":")[1:]]
    # line: from the totem tab's left side + 1 to the buff tab's flare foot; halo: a pixel out each side
    approx(last[0], N["TOTEM_X"] + 1, "gap line start"), approx(last[1], N["BUFF_X"] + N["BUFF_W"] + N["FLARE"] - 1, "gap line end")
    approx(last[2], N["TOTEM_X"] - 11, "gap halo start"), approx(last[3], N["BUFF_X"] + N["BUFF_W"] + 15, "gap halo end")
    art = g(lua).FS.Console.art
    bridges = [r for r in csh.seq(art._regions) if r._kind == "Texture" and r._color is not None and r._h == 1
               and r._points[1].x > 300 and r._points[1].x < 320]
    assert len(bridges) == 1 and shown(bridges[0]), f"{len(bridges)} bridge textures"
    br = bridges[0]
    approx(br._points[1].x, N["TOTEM_X"] + N["TOTEM_W"] + N["FLARE"] - 1, "bridge start")
    approx(br._points[1].x + br._w, N["BUFF_X"] + 1, "bridge end")
    approx(br._color[4], g(lua).FS.Console.OUTLINE_ALPHA, "bridge alpha is the Console line's")
    # both tabs leaving takes the gap back
    csh.console(lua).SetActive(False)
    assert not shown(bridges[0]) and not csh.cs(lua).IsShown("shamanbuff")


def check_the_tab_follows_the_console_on_and_off_and_sits_beside_the_totem_tab():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    host = g(lua).FSBuffTab
    csh.console(lua).SetActive(False)
    assert not csh.cs(lua).IsShown("shamanbuff")
    p = host._points[1]
    assert p.rel._name == "FSTotemBar" and (p.point, p.relPoint) == ("BOTTOMLEFT", "BOTTOMRIGHT"), \
        f"Console off: {p.rel._name} {p.relPoint}"
    approx(p.x, 16.0, "gap beside the totem tab")
    assert host._shown and shown(btn(lua, IMBUE)) and shown(btn(lua, SHIELD))
    csh.console(lua).SetActive(True)
    assert csh.cs(lua).IsShown("shamanbuff") and host._points[1].rel._name == "FSConsole"
    # no Console at all: still a seat, no crash
    lua = world(console=False, tips={16: ["Rockbiter 1 (59 min)"]})
    assert g(lua).FSBuffTab._shown


def check_a_rescale_resizes_and_reseats_out_of_combat():
    lua = world(1.0, tips={16: ["Rockbiter 1 (59 min)"]})
    lua.eval("__rescale")(1 / 1.2)
    s = 1 / 1.2
    approx(btn(lua, 2)._w, N["BTN"] * s, "button width after a rescale")
    q = btn(lua, 2)._points[1]
    approx(q.x, (N["PAD"] + N["BTN"] + N["GAP"]) * s, "button 2 x after a rescale")


def check_no_secure_frame_is_anchored_to_the_shoulder_art():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    stand = [s for s in (csh.cs(lua).shoulder,) if s]
    arts = {id(a) for a in [csh.cs(lua).shoulder.art]}
    for f in g(lua).__frames.values():
        for p in csh.seq(f._points):
            if p.rel is not None and p.rel._name is None and p.rel._kind == "Frame":
                assert f._kind not in ("Button",), "a button is anchored to anonymous art"
    for i in (IMBUE, SHIELD):
        assert btn(lua, i)._parent._name == "FSBuffTab"
    assert g(lua).FSBuffTab._parent is g(lua).UIParent or g(lua).FSBuffTab._parent._name == "UIParent"


def check_a_seat_change_in_combat_waits_for_regen():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    set_combat(lua, True)
    lua.eval("__rescale")(1 / 1.2)
    csh.console(lua).SetActive(False)
    assert blocked(lua) == 0, "a protected write was attempted in combat"
    leave_combat(lua)
    assert blocked(lua) == 0


def check_a_login_in_combat_builds_at_regen():
    lua = world(combat=True, tips={16: ["Rockbiter 1 (59 min)"]})
    assert btn(lua, IMBUE) is None, "built in combat"
    leave_combat(lua)
    assert btn(lua, IMBUE) is not None and shown(btn(lua, IMBUE))


# ---------------------------------------------------------------------------------------------
# Checks: who gets a tab, listeners, visibility
# ---------------------------------------------------------------------------------------------


def listeners(lua, event):
    return [f for f in g(lua).__frames.values() if f._registered[event]]


def check_only_a_shaman_gets_a_tab():
    for klass in ("PALADIN", "WARRIOR", "PRIEST", "MAGE", "DRUID"):
        lua = boot(klass=klass)
        assert btn(lua, 1) is None and btn(lua, 2) is None, f"{klass} got a buff button"
        assert g(lua).FSBuffTab is None, f"{klass} got a buff host"
        assert not bt(lua).OwnsShoulder(), f"{klass}: the buff tab claims a shoulder"
        assert not csh.cs(lua).IsShown("shamanbuff"), f"{klass}: the buff shoulder stands"
        for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_INVENTORY_CHANGED", "PLAYER_EQUIPMENT_CHANGED"):
            assert not listeners(lua, event), f"{klass}: something listens to {event}"
        assert not [f for f in g(lua).__frames.values() if f._scripts.OnUpdate and f._name is None
                    and False], "x"
    lua = boot(klass="THROW")
    assert btn(lua, 1) is None
    lua = boot(klass="SECRET")
    assert btn(lua, 1) is None


def check_a_failed_build_leaves_no_listener_running():
    lua = boot(pre_login='__failBuild = "FSBuffTabButton2"')
    # the second button could not be built: the tab is not up and nothing listens for the data
    assert btn(lua, 2) is None
    assert not bt(lua).OwnsShoulder(), "a failed build still claims the shoulder"
    assert not csh.cs(lua).IsShown("shamanbuff")
    for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_INVENTORY_CHANGED", "PLAYER_EQUIPMENT_CHANGED", "UNIT_AURA"):
        assert not listeners(lua, event), f"a listener for {event} runs for a tab that never drew"
    cast(lua, "Rockbiter Weapon")        # and a cast changes nothing
    assert sbuf(lua).View().imbue.mode is None


def check_the_listeners_start_once_the_tiles_exist_and_only_for_the_unit_player():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_INVENTORY_CHANGED", "UNIT_AURA", "PLAYER_EQUIPMENT_CHANGED"):
        assert len(listeners(lua, event)) == 1, f"{event}: {len(listeners(lua, event))} listeners"
    # another unit's cast, aura or inventory changes nothing
    run(lua, '__shield(3, 480)')
    fire(lua, "UNIT_AURA", "player")
    run(lua, '__noshield()')
    fire(lua, "UNIT_AURA", "target")
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "target", "guid", 8017)
    assert view(lua, "shield").mode == "on", view(lua, "shield").mode
    reads = len(tip_calls(lua))
    fire(lua, "UNIT_INVENTORY_CHANGED", "target")
    assert len(tip_calls(lua)) == reads


def check_the_tab_needs_no_target_and_hangs_on_the_ui_not_the_gunsight():
    text = "\n".join(ln for p in (BUFFTAB, SHAMANBUFFS) for ln in p.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("--"))
    for token in ("UnitExists", "HasTarget", "PLAYER_TARGET_CHANGED", "Gunsight", "GunsightAreas", "TakesDots"):
        assert token not in text, f"the buff tab mentions {token}: it is a self buff reminder"
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    run(lua, "UnitExists = function() return false end")
    fire(lua, "PLAYER_TARGET_CHANGED")
    fire(lua, "SPELLS_CHANGED")
    host = g(lua).FSBuffTab
    assert host._shown and shown(btn(lua, IMBUE)) and shown(btn(lua, SHIELD)), "the tab needs no target"
    assert host._parent._name == "UIParent"


def check_the_tab_stands_with_the_gunsight_hud_off():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]}, pre_login="FS.Gunsight = nil; FS.GunsightAreas = nil")
    assert g(lua).FSBuffTab._shown and shown(btn(lua, IMBUE))


# ---------------------------------------------------------------------------------------------
# Checks: robustness, files
# ---------------------------------------------------------------------------------------------


def check_unreadable_sources_keep_the_last_known_imbue_and_never_log_or_throw():
    # a broken source adds nothing: the imbue read before it broke keeps counting down, and no failure reaches chat
    for setup in ('__eqMode = "throw"', '__eqMode = "secret"', '__tipMode = "throw"', '__tipMode = "secret"',
                  "GetWeaponEnchantInfo = nil", "C_Item.GetItemInfoInstant = nil", "GetInventoryItemID = nil",
                  "C_TooltipInfo = nil"):
        lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
        before = int(g(lua).__degradeCount)
        run(lua, setup)
        for event, args in (("UNIT_INVENTORY_CHANGED", ("player",)), ("SPELLS_CHANGED", ()),
                            ("PLAYER_EQUIPMENT_CHANGED", (16, True))):
            fire(lua, event, *args)
        tick(lua, 7)
        v = view(lua, "imbue")
        assert (v.mode, v.code, v.text) == ("on", "RB", "58m"), f"{setup}: {v.mode} {v.code} {v.text}"
        assert shown(btn(lua, IMBUE)) and attr(btn(lua, IMBUE), "spell") == "Rockbiter Weapon", setup
        assert int(g(lua).__degradeCount) == before, f"{setup}: a failure was logged to chat"
    # no timer API: a cast still counts, only the follow-up reads are lost
    lua = world(tips={16: ["Heavy Axe"]})
    run(lua, "C_Timer = nil")
    cast(lua, "Rockbiter Weapon")
    tick(lua, 7)
    assert (view(lua, "imbue").mode, view(lua, "imbue").code) in (("on", "RB"), ("warn", "RB"))
    # no aura snapshot: the shield is "?", never a made up count
    lua = world()
    run(lua, "FS.PlayerAuras = nil")
    fire(lua, "UNIT_AURA", "player")
    tick(lua, 2)
    assert view(lua, "shield").mode in ("hollow", "warn"), view(lua, "shield").mode


def check_toc_lists_the_buff_files_after_the_totem_bar():
    lines = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines()]
    mods = [ln for ln in lines if ln.endswith(".lua")]
    for f in ("Modules/ActionBars/ShamanBuffs.lua", "Modules/ActionBars/BuffTab.lua"):
        assert f in mods, f"{f} is not in the .toc"
    assert mods.index("Modules/ActionBars/ShamanBuffs.lua") < mods.index("Modules/ActionBars/BuffTab.lua")
    for dep in ("Modules/ActionBars/ClassShoulder.lua", "Modules/ActionBars/TotemBar.lua", "Modules/Pet/PetDock.lua",
                "Core/FrameHelpers.lua", "Modules/Auras/Buffs.lua", "Core/Theme.lua"):
        assert mods.index(dep) < mods.index("Modules/ActionBars/ShamanBuffs.lua"), f"{dep} must load before ShamanBuffs.lua"


def check_no_em_dashes_and_no_flagged_words_in_the_new_files():
    for path in (BUFFTAB, SHAMANBUFFS, Path(__file__)):
        assert path.exists(), f"{path} is missing"
        text = path.read_text(encoding="utf-8")
        assert chr(0x2014) not in text, f"{path.name} has an em dash"
    for path in (BUFFTAB, SHAMANBUFFS):
        strings = re.findall(r'"([^"\n]*)"', path.read_text(encoding="utf-8"))
        for s in strings:
            if " " not in s and "_" in s or s.startswith(("Interface", "CLICK", "UNIT_", "PLAYER_")):
                continue
            assert not re.search(r"\b(probe|bot|monitor|test)\b", s, re.I), f"{path.name}: player text {s!r}"


def check_the_old_class_module_chips_are_gone_from_the_gunsight_file():
    text = (ADDON / "Modules/CombatHud/GunsightShaman.lua").read_text(encoding="utf-8")
    for token in ("GetWeaponEnchantInfo", "IMBUE", "SHIELD", "BuildChip", "UNIT_SPELLCAST"):
        assert token not in text.replace("IMBUE and SHIELD chips", ""), f"GunsightShaman.lua still has {token}"


def font_sizes(lua, i):
    b = btn(lua, i)
    return (float(b.fsText._font[2]), float(b.fsChip.code._font[2]), float(b.fsLockText._font[2]))


def check_tile_fonts_are_the_design_size_at_every_scale_and_after_a_rescale():
    # like the totem and seal tabs: text is not scaled with the UI scale, and a rescale leaves it as it was
    lua = world(1.0, tips={16: ["Rockbiter 1 (59 min)"]})
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert btn(lua, SHIELD).fsText._text == "SHIELD"
    assert font_sizes(lua, IMBUE) == (11.0, 10.0, 11.0), font_sizes(lua, IMBUE)
    assert font_sizes(lua, SHIELD) == (9.0, 10.0, 11.0), font_sizes(lua, SHIELD)
    lua.eval("__rescale")(1 / 1.2)
    update(lua)
    assert font_sizes(lua, IMBUE) == (11.0, 10.0, 11.0), font_sizes(lua, IMBUE)
    assert font_sizes(lua, SHIELD) == (7.5, 10.0, 11.0), font_sizes(lua, SHIELD)   # the word is fitted to the narrower tile
    # and from a boot at the small scale
    lua = world(1 / 1.2, tips={16: ["Rockbiter 1 (59 min)"]})
    assert font_sizes(lua, IMBUE) == (11.0, 10.0, 11.0), font_sizes(lua, IMBUE)
    # a word set small, then back to the time: the size follows the text, also after a rescale
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert font_sizes(lua, SHIELD)[0] == 11.0


def check_the_missing_imbue_word_stays_at_the_full_size_where_it_fits_and_only_shield_starts_small():
    # the mockup drops only SHIELD to 9 (`m==='warn'&&k==='shield'?9:11`): IMBUE is 11 where it fits, fitted below that
    lua = world(1.0, tips={16: ["Heavy Axe"]})
    assert btn(lua, IMBUE).fsText._text == "IMBUE"
    assert font_sizes(lua, IMBUE)[0] == 11.0, font_sizes(lua, IMBUE)
    lua = world(0.8333, tips={16: ["Heavy Axe"]})
    size = font_sizes(lua, IMBUE)[0]
    assert size < 11.0, "the word IMBUE must still shrink at Parker's live scale, where 11 px overflows the tile"
    assert_tile_text_fits(lua, IMBUE, 0.8333, "imbue missing at 0.8333")


def check_a_fitted_tile_string_never_goes_below_six_pixels():
    lua = world(0.25, tips={16: ["Heavy Axe"]})
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert btn(lua, SHIELD).fsText._text == "SHIELD"
    assert font_sizes(lua, IMBUE)[0] == 6.0, font_sizes(lua, IMBUE)
    assert font_sizes(lua, SHIELD)[0] == 6.0, font_sizes(lua, SHIELD)


def counting(lua):
    run(lua, "__changes = 0; FS.ShamanBuffs.OnChange(function() __changes = __changes + 1 end)")
    return lambda: int(g(lua).__changes)


def check_an_irrelevant_cast_is_a_no_op_and_an_unknown_id_with_the_shield_name_is_ignored():
    lua = world(spells=("Rockbiter Weapon", "Lightning Shield", "Water Shield"), tips={16: ["Rockbiter 1 (59 min)"]})
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    changes = counting(lua)
    run(lua, '__idNames[4242] = "Frost Shock"')
    for sid in (4242, 99999):
        run(lua, f"__castOk({sid})")
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "player", "guid", None)
    assert changes() == 0, "a cast that is not an imbue or a shield reached the tab"
    # an orb proc: the same name as Lightning Shield, an id the player does not know
    run(lua, '__idNames[26364] = "Lightning Shield"')
    update(lua)
    assert view(lua, "shield").mode == "warn"
    run(lua, "__castOk(26364)")
    update(lua)
    assert view(lua, "shield").mode == "warn", "an orb proc faked a fresh Lightning Shield cast"
    assert changes() == 0
    run(lua, '__idNames[26365] = "Water Shield"')
    run(lua, "__castOk(26365)")
    update(lua)
    assert not view(lua, "shield").other and changes() == 0, "an unknown Water Shield id was taken"
    # the real ids still count
    cast(lua, "Lightning Shield")
    update(lua)
    assert view(lua, "shield").mode == "on" and changes() == 1


def check_leaving_combat_keeps_the_shield_an_estimate_until_the_next_tick_reads_the_snapshot():
    lua = world()
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    set_combat(lua, True)
    update(lua)
    assert view(lua, "shield").text == "~3"
    run(lua, "__shield(1, 470)")                       # the snapshot catches up a moment after regen
    leave_combat(lua)
    update(lua)
    assert view(lua, "shield").text.startswith("~"), "regen read a snapshot that may lag: " + view(lua, "shield").text
    tick(lua, 1)
    assert view(lua, "shield").text == "1" and not view(lua, "shield").estimate, view(lua, "shield").text


def check_a_tooltip_read_that_contradicts_a_fresh_cast_waits_for_the_grace():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (10 min)"]})
    assert view(lua, "imbue").code == "RB"
    cast(lua, "Flametongue Weapon")                    # replaces the main hand imbue
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")      # the weapon still says Rockbiter
    update(lua)
    v = view(lua, "imbue")
    assert (v.code, v.text) == ("FT", "60m"), (v.code, v.text)
    tip(lua, 16, ["Flametongue 1 (60 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert view(lua, "imbue").code == "FT"
    # a weapon that never took the cast: the tooltip wins once the grace is over
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (10 min)"]})
    cast(lua, "Flametongue Weapon")
    tick(lua, 3)
    v = view(lua, "imbue")
    assert (v.code, v.text) == ("RB", "10m"), (v.code, v.text)


def event_frames(lua):
    """Every other frame that hears the spellbook events, and the data model's own (it has UNIT_SPELLCAST_SUCCEEDED)."""
    data = listeners(lua, "UNIT_SPELLCAST_SUCCEEDED")
    assert len(data) == 1, len(data)
    others = [f for f in g(lua).__frames.values()
              if f._registered["SPELLS_CHANGED"] and f._scripts.OnEvent and f is not data[0]]
    assert others, "nobody else hears the spellbook events"
    return others, data[0]


def deliver_data_last(lua, event):
    """The worst order: the data model hears of the event after everything else, the tab included."""
    others, data = event_frames(lua)
    for f in others:
        f._scripts.OnEvent(f, event)
    data._scripts.OnEvent(data, event)


def check_learning_lightning_shield_unlocks_the_tile_whichever_handler_runs_first():
    for event in ("SPELLS_CHANGED", "PLAYER_ENTERING_WORLD", "PLAYER_LEVEL_UP"):
        lua = boot(spells=("Rockbiter Weapon",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (30 min)"]})
        b = btn(lua, SHIELD)
        assert b.fsLocked
        run(lua, '__spell("Lightning Shield", 324, true)')
        deliver_data_last(lua, event)
        assert not b.fsLocked and abs(float(b._alpha) - 1.0) < 1e-6, f"{event}: still locked"
        assert attr(b, "type") == "spell" and attr(b, "spell") == "Lightning Shield", event
        assert shown(b.fsFace) and not shown(b.fsMold)
    # a spell the first look missed (false answers do not stick): the world entering asks again
    lua = boot(spells=("Rockbiter Weapon",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (30 min)"]})
    run(lua, '__spell("Lightning Shield", 324, true)')
    fire(lua, "PLAYER_ENTERING_WORLD")
    assert not btn(lua, SHIELD).fsLocked
    # learned in combat: nothing protected is touched, the regen finishes it
    lua = boot(spells=("Rockbiter Weapon",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (30 min)"]})
    set_combat(lua, True)
    run(lua, '__spell("Lightning Shield", 324, true)')
    fire(lua, "SPELLS_CHANGED")
    tick(lua, 2)
    assert blocked(lua) == 0 and btn(lua, SHIELD).fsLocked
    leave_combat(lua)
    assert not btn(lua, SHIELD).fsLocked and attr(btn(lua, SHIELD), "spell") == "Lightning Shield"
    # and the imbue tile appears when the first imbue is learned, handler order aside
    lua = boot(spells=("Lightning Shield",), weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Heavy Axe"]})
    assert not shown(btn(lua, IMBUE))
    run(lua, '__spell("Rockbiter Weapon", 8017, true)')
    deliver_data_last(lua, "SPELLS_CHANGED")
    assert shown(btn(lua, IMBUE)) and attr(btn(lua, IMBUE), "spell") == "Rockbiter Weapon"


def check_an_unchanged_tick_allocates_nothing_in_or_out_of_combat():
    for combat in (False, True):
        lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
        run(lua, "__shield(3, 480)")
        fire(lua, "UNIT_AURA", "player")
        if combat:
            set_combat(lua, True)
        run(lua, """
            if jit then jit.off() end        -- compiled traces would count as allocation; the client runs plain Lua 5.1
            local ShamanBuffs, BuffTab = FS.ShamanBuffs, FS.BuffTab
            local t = __now
            local function step(i) ShamanBuffs.Update(t + i * 0.01); BuffTab.Paint() end
            for i = 1, 50 do step(i) end
            collectgarbage("collect"); collectgarbage("stop")
            local before = collectgarbage("count")
            for i = 51, 450 do step(i) end
            __grew = (collectgarbage("count") - before) * 1024
            collectgarbage("restart")
        """)
        # a table per tick would be 56+ bytes each (the first version grew 100 KB); the rest is the mock itself (about 600 B)
        assert float(g(lua).__grew) < 2000, f"combat={combat}: 400 idle ticks allocated {float(g(lua).__grew):.0f} bytes"


# ---------------------------------------------------------------------------------------------
# Checks: usability feedback (out of mana -> blue, unusable -> grey, usable -> the approved look)
# ---------------------------------------------------------------------------------------------


def use_theme(lua, name):
    return tbh.theme_color(lua, name)


def use_spell(lua, name, ok, no_mana=False):
    """What the spell API answers for a spell, by the name the tile casts."""
    tbh.usable(lua, "spell", '"%s"' % name, ok, no_mana)


def dist(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


FOREGROUND = ("chip", "text_color", "code_color", "line")


def check_low_mana_tints_the_tile_foreground_blue_unusable_grey_and_usable_is_the_approved_look():
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    base = tile(lua, IMBUE)
    oom, grey = use_theme(lua, "COLOR_OOM"), use_theme(lua, "COLOR_UNUSABLE")
    use_spell(lua, "Rockbiter Weapon", False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    t = tile(lua, IMBUE)
    for part in FOREGROUND:
        assert dist(t[part], oom) < dist(base[part], oom), f"out of mana: {part} did not move toward blue"
        assert t[part][2] > t[part][0], f"out of mana: {part} is not blue {t[part]}"
    # what is not the foreground keeps the approved look: the cut border, the chip fill, the alphas, the text
    close(t["ring"], base["ring"], "border"), close(t["fill"], base["fill"], "chip fill")
    approx(t["ring_a"], base["ring_a"], "border alpha"), approx(t["text_a"], base["text_a"], "text alpha")
    assert (t["code"], t["text"]) == (base["code"], base["text"]), "the words changed"
    use_spell(lua, "Rockbiter Weapon", False, False)
    fire(lua, "SPELL_UPDATE_USABLE")
    t = tile(lua, IMBUE)
    for part in FOREGROUND:
        assert dist(t[part], grey) < dist(base[part], grey), f"unusable: {part} did not move toward grey"
    use_spell(lua, "Rockbiter Weapon", True, False)
    fire(lua, "SPELL_UPDATE_USABLE")
    t = tile(lua, IMBUE)
    for part in FOREGROUND + ("ring", "fill"):
        close(t[part], base[part], f"usable again: {part}", 1e-6)
    approx(t["text_a"], base["text_a"], "usable again: text alpha")


def check_the_tint_blends_with_each_state_colour_pink_red_and_hollow():
    lua = world(tips={16: ["Rockbiter 1 (42 sec)"]})
    pink = tile(lua, IMBUE)
    use_spell(lua, "Rockbiter Weapon", False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    oom = use_theme(lua, "COLOR_OOM")
    t = tile(lua, IMBUE)
    assert dist(t["chip"], oom) < dist(pink["chip"], oom) and t["chip"] != pink["chip"]
    assert t["code"] == pink["code"]
    # the state moves on under the tint: the tint stays, the colours follow the new state
    tip(lua, 16, ["Rockbiter 1 (59 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)
    quiet = tile(lua, IMBUE)
    assert quiet["chip"] != t["chip"], "the tint froze the old state colour"
    assert dist(quiet["chip"], oom) < dist(C["gold"], oom), "the tint was lost when the state changed"
    # a missing imbue (red hollow word) is tinted too, and hover keeps its cyan border
    tip(lua, 16, ["Heavy Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)
    b = btn(lua, IMBUE)
    lua.eval("__Region.Fire")(b, "OnEnter")
    close(tile(lua, IMBUE)["ring"], C["cyan"], "hover border under the tint")
    assert dist(tile(lua, IMBUE)["chip"], oom) < dist(C["red"], oom)


THEME = ADDON / "Core/Theme.lua"


def check_the_red_is_the_themes_red_token_and_the_mockups():
    src = THEME.read_text(encoding="utf-8")
    m = sb._m(r"Theme\.COLOR_RED\s*=\s*\{([^}]*)\}", src, "COLOR_RED")
    vals = tuple(float(x) for x in m.group(1).split(",")[:3])
    close(vals, C["red"], "Theme.COLOR_RED vs the mockup's red", 1e-3)
    assert BUFFTAB.read_text(encoding="utf-8").count("COLOR_RED") >= 1, "BuffTab does not use Theme.COLOR_RED"


def check_gold_and_pink_are_unchanged_and_only_the_missing_state_is_red():
    lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
    t = tile(lua, IMBUE)
    for part in ("chip", "line"):
        close(t[part], C["gold"], f"quiet {part}")
    close(t["fill"], _mix(BG, C["gold"], MK["on_fill"]), "quiet fill")
    approx(t["ring_a"], MK["ring_alpha"]["on"], "quiet border alpha")
    tip(lua, 16, ["Rockbiter 1 (42 sec)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    t = tile(lua, IMBUE)
    for part in ("chip", "ring", "text_color", "line", "glow", "chip_glow"):
        close(t[part], C["pink"], f"expiring {part}")
    close(t["fill"], _mix(BG, C["pink"], MK["exp_fill"]), "expiring fill")
    close(t["plate"], _mix(BG, C["pink"], 0.1), "expiring plate")
    assert dist(C["red"], C["pink"]) > 0.25, "the alert red must not read as the expiring pink"


def check_the_missing_red_composes_with_the_usability_tints():
    lua = world(tips={16: ["Heavy Axe"]})
    base = tile(lua, IMBUE)
    assert_warn_is_red(base, "missing")
    oom, grey = use_theme(lua, "COLOR_OOM"), use_theme(lua, "COLOR_UNUSABLE")
    for name, tint, no_mana in (("out of mana", oom, True), ("unusable", grey, False)):
        use_spell(lua, "Rockbiter Weapon", False, no_mana)
        fire(lua, "SPELL_UPDATE_USABLE")
        t = tile(lua, IMBUE)
        for part in FOREGROUND:
            close(t[part], _mix(C["red"], tint, 0.6), f"{name}: red blended 60% toward the tint, {part}", 5e-3)
        close(t["chip_glow"], _mix(C["red"], tint, 0.6), f"{name}: the chip glow follows the chip stroke", 5e-3)
        # the cut border, glow, plate and chip fill keep the red state
        for part in ("ring", "glow", "plate", "fill"):
            close(t[part], base[part], f"{name}: {part} stays the state colour", 1e-6)
        assert dist(t["chip"], C["red"]) > 0.1, f"{name}: the tint did not show on the red chip"
    # the blended red is still told from the blended pink (expiring) under the same tint
    use_spell(lua, "Rockbiter Weapon", False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    red_oom = tile(lua, IMBUE)["chip"]
    tip(lua, 16, ["Rockbiter 1 (42 sec)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)
    assert dist(red_oom, tile(lua, IMBUE)["chip"]) > 0.08, "tinted red and tinted pink are not told apart"


# Mononoki Bold, the font every tile string is set in: advances read from the font file, not from the Lua under test
def _advance(text: str) -> float:
    from fontTools.ttLib import TTFont
    font = TTFont(str(ADDON / "Media/Fonts/MononokiNerdFontMono-Bold.ttf"))
    cmap, hmtx, em = font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm
    return sum(hmtx[cmap[ord(ch)]][0] for ch in text) / em


TEXT_INSET = 3      # design px kept clear on each side of a tile string (the chamfer of the cut border)


def assert_tile_text_fits(lua, i, scale, what):
    b = btn(lua, i)
    text, size = str(b.fsText._text), float(b.fsText._font[2])
    width, room = _advance(text) * size, (N["BTN"] - 2 * TEXT_INSET) * scale
    assert width <= room + 1e-6, f"{what}: {text!r} is {width:.1f} wide at {size}px, the tile allows {room:.1f}"
    code, csize = str(b.fsChip.code._text), float(b.fsChip.code._font[2])
    assert _advance(code) * csize <= (22 - 2 * 2) * scale + 1e-6, f"{what}: chip code {code!r} overflows the chip"
    return size


def check_every_tile_string_fits_inside_its_tile_in_every_state(scale):
    lua = world(scale, tips={16: ["Heavy Axe"]})
    assert_tile_text_fits(lua, IMBUE, scale, "imbue missing")
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert btn(lua, SHIELD).fsText._text == "SHIELD"
    words = assert_tile_text_fits(lua, SHIELD, scale, "shield missing")
    assert words >= 7, f"the word SHIELD shrank to {words}px, past legible"
    for line in ("Rockbiter 1 (59 min)", "Rockbiter 1 (42 sec)", "Rockbiter 1 (3 min)"):
        tip(lua, 16, [line])
        fire(lua, "UNIT_INVENTORY_CHANGED", "player")
        update(lua)
        assert_tile_text_fits(lua, IMBUE, scale, f"imbue {line}")
    tip(lua, 16, ["Heavy Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)
    assert_tile_text_fits(lua, IMBUE, scale, "imbue missing again")
    for count, remaining in ((3, 480), (0, 480), (1, 45)):
        run(lua, f"__shield({count}, {remaining})")
        fire(lua, "UNIT_AURA", "player")
        update(lua)
        assert_tile_text_fits(lua, SHIELD, scale, f"shield {count} / {remaining}")
    run(lua, "__water()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert_tile_text_fits(lua, SHIELD, scale, "shield water")
    set_combat(lua, True)
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert_tile_text_fits(lua, SHIELD, scale, "shield estimate in combat")
    if scale == 1.0:
        # a rescale refits the word
        leave_combat(lua)
        run(lua, "__noshield()")
        fire(lua, "UNIT_AURA", "player")
        update(lua)
        lua.eval("__rescale")(1 / 1.2)
        update(lua)
        assert_tile_text_fits(lua, SHIELD, 1 / 1.2, "shield missing after a rescale")
        assert_tile_text_fits(lua, IMBUE, 1 / 1.2, "imbue missing after a rescale")


def check_a_nil_first_answer_is_unusable_and_a_secret_mana_flag_does_not_hide_a_plain_false():
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    base = tile(lua, IMBUE)
    grey = use_theme(lua, "COLOR_UNUSABLE")
    # the old 1-or-nil style: the call answered, the first value is nil = not usable (grey)
    tbh.use_mode(lua, "nilvalue")
    fire(lua, "SPELL_UPDATE_USABLE")
    t = tile(lua, IMBUE)
    for part in FOREGROUND:
        assert dist(t[part], grey) < dist(base[part], grey), f"nil answer: {part} did not go grey"
    # an answer of nothing at all still cannot be told: the tint stays
    tbh.use_mode(lua, "none")
    fire(lua, "SPELL_UPDATE_USABLE")
    assert tile(lua, IMBUE) == t, "no answer at all moved the tint"
    # a plain usable flag + a secret mana flag cannot be told (no change); plain false is grey whatever the mana is
    tbh.use_mode(lua, None)
    use_spell(lua, "Rockbiter Weapon", True, False)
    fire(lua, "SPELL_UPDATE_USABLE")
    assert tile(lua, IMBUE) == base
    tbh.use_mode(lua, "secretmana")
    use_spell(lua, "Rockbiter Weapon", True, False)
    fire(lua, "SPELL_UPDATE_USABLE")
    assert tile(lua, IMBUE) == base, "a secret mana flag with a usable spell moved the tint"
    use_spell(lua, "Rockbiter Weapon", False, False)
    fire(lua, "SPELL_UPDATE_USABLE")
    t = tile(lua, IMBUE)
    for part in FOREGROUND:
        assert dist(t[part], grey) < dist(base[part], grey), f"secret mana, plain false: {part} did not go grey"


def check_a_tile_whose_spell_goes_nil_drops_its_tint():
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    base = tile(lua, IMBUE)
    use_spell(lua, "Rockbiter Weapon", False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    assert tile(lua, IMBUE) != base
    run(lua, "FS.ShamanBuffs.View().imbue.spell = nil")
    bt(lua).UpdateUsable()
    assert btn(lua, IMBUE).fsUsable is None, "fsUsable survived the spell going nil"
    assert tile(lua, IMBUE) == base, "the tint stayed after the spell went nil"


def check_the_tile_asks_the_spell_api_about_the_spell_it_casts():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"), tips={16: ["Rockbiter 1 (50 min)"]})
    lua.execute("__use_reset()")
    fire(lua, "SPELL_UPDATE_USABLE")
    asked = {str(k) for k in g(lua).__use.seen.spell.keys()}
    assert asked == {"Lightning Shield", "Rockbiter Weapon"}, f"asked about {sorted(asked)}"
    # the imbue the tile now casts changes with no usability event: the new spell is judged at the next repaint
    use_spell(lua, "Flametongue Weapon", False, True)
    tip(lua, 16, ["Flametongue 1 (50 min)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)
    assert str(view(lua, "imbue").spell) == "Flametongue Weapon"
    tick(lua, 1.5)
    oom = use_theme(lua, "COLOR_OOM")
    t = tile(lua, IMBUE)
    assert dist(t["chip"], oom) < dist(C["gold"], oom) and t["chip"][2] > t["chip"][0], "the new imbue was not judged"


def check_a_secret_missing_or_raising_answer_leaves_the_tile_tint_as_it_was():
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    base = tile(lua, IMBUE)
    use_spell(lua, "Rockbiter Weapon", False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    tinted = tile(lua, IMBUE)
    assert tinted["chip"] != base["chip"]
    lua.execute('__use.throwOn["Rockbiter Weapon"] = true; __use.throwOn["Lightning Shield"] = true')
    for mode in ("secret", "throw", "none"):
        tbh.use_mode(lua, mode)
        fire(lua, "SPELL_UPDATE_USABLE")
        assert tile(lua, IMBUE) == tinted, f"{mode}: the tint moved"
    set_combat(lua, True)
    tbh.use_mode(lua, "secret")
    fire(lua, "SPELL_UPDATE_USABLE")
    update(lua)
    assert tile(lua, IMBUE) == tinted, "combat secret: the tint moved"
    tbh.use_mode(lua, None)
    use_spell(lua, "Rockbiter Weapon", True, False)
    fire(lua, "ACTIONBAR_UPDATE_USABLE")
    for part in FOREGROUND:
        close(tile(lua, IMBUE)[part], base[part], f"a plain answer in combat: {part}", 1e-6)
    assert blocked(lua) == 0, "usability touched a protected frame in combat"


def check_the_tint_follows_each_usability_event_and_leaving_combat():
    for event in ("SPELL_UPDATE_USABLE", "ACTIONBAR_UPDATE_USABLE", "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED"):
        lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
        base = tile(lua, IMBUE)
        use_spell(lua, "Rockbiter Weapon", False, True)
        if event == "PLAYER_REGEN_ENABLED":
            set_combat(lua, True)
            set_combat(lua, False)
        fire(lua, event)
        assert tile(lua, IMBUE)["chip"] != base["chip"], f"{event} did not refresh the tint"
    # the shield tile reads its own spell
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    base = tile(lua, SHIELD)
    use_spell(lua, "Lightning Shield", False, False)
    fire(lua, "SPELL_UPDATE_USABLE")
    assert tile(lua, SHIELD)["chip"] != base["chip"], "the shield tile did not follow its spell"


def check_a_locked_or_absent_tile_is_never_asked_and_never_tinted():
    lua = world(spells=("Rockbiter Weapon",), tips={16: ["Rockbiter 1 (30 min)"]})
    b = btn(lua, SHIELD)
    assert b.fsLocked
    lua.execute("__use_reset()")
    use_spell(lua, "Lightning Shield", False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    asked = {str(k) for k in g(lua).__use.seen.spell.keys()}
    assert "Lightning Shield" not in asked, "a locked tile was asked"
    assert shown(b.fsMold) and not shown(b.fsFace)
    # learned while the usable answer says out of mana: the tile comes up already tinted
    run(lua, '__spell("Lightning Shield", 324, true)')
    fire(lua, "SPELLS_CHANGED")
    assert not b.fsLocked
    oom = use_theme(lua, "COLOR_OOM")
    tinted = tile(lua, SHIELD)["chip"]
    use_spell(lua, "Lightning Shield", True, False)
    fire(lua, "SPELL_UPDATE_USABLE")
    plain = tile(lua, SHIELD)["chip"]
    assert tinted != plain and dist(tinted, oom) < dist(plain, oom), "an unlocked tile came up without the usability"
    # no imbue known: the tile is absent and not asked
    lua = world(spells=("Lightning Shield",))
    lua.execute("__use_reset()")
    fire(lua, "SPELL_UPDATE_USABLE")
    asked = {str(k) for k in g(lua).__use.seen.spell.keys()}
    assert asked <= {"Lightning Shield"}, f"an absent imbue tile was asked: {sorted(asked)}"


def check_a_tinted_idle_tick_allocates_nothing_in_or_out_of_combat():
    for combat in (False, True):
        lua = world(tips={16: ["Rockbiter 1 (59 min)"]})
        run(lua, "__shield(3, 480)")
        fire(lua, "UNIT_AURA", "player")
        use_spell(lua, "Rockbiter Weapon", False, True)
        use_spell(lua, "Lightning Shield", False, False)
        fire(lua, "SPELL_UPDATE_USABLE")
        if combat:
            set_combat(lua, True)
        run(lua, """
            if jit then jit.off() end        -- compiled traces would count as allocation; the client runs plain Lua 5.1
            local ShamanBuffs, BuffTab = FS.ShamanBuffs, FS.BuffTab
            local t = __now
            local function step(i) ShamanBuffs.Update(t + i * 0.01); BuffTab.UpdateUsable(); BuffTab.Paint() end
            for i = 1, 50 do step(i) end
            collectgarbage("collect"); collectgarbage("stop")
            local before = collectgarbage("count")
            for i = 51, 450 do step(i) end
            __grew = (collectgarbage("count") - before) * 1024
            collectgarbage("restart")
        """)
        assert float(g(lua).__grew) < 2000, f"combat={combat}: 400 tinted ticks allocated {float(g(lua).__grew):.0f} bytes"



# ---------------------------------------------------------------------------------------------
# Checks: the spell icon on each tile
# ---------------------------------------------------------------------------------------------


def icon(lua, i):
    """What a tile shows as its icon: the texture, whether it and the chip stand, the colour, desaturation, the plate."""
    b = btn(lua, i)
    tex = b.icon._texture
    return dict(
        tex=None if tex is None else int(tex), shown=shown(b.icon),
        vertex=rgb(b.icon._vertex) if b.icon._vertex else None,
        desat=bool(b.icon._desat), chip=shown(b.fsChip.ring) and shown(b.fsChip.fill) and shown(b.fsChip.code),
        chip_any=shown(b.fsChip.ring) or shown(b.fsChip.fill) or shown(b.fsChip.glow) or shown(b.fsChip.code),
        plate=shown(b.fsTextPlate), text=b.fsText._text,
    )


def check_each_tile_wears_the_icon_of_the_spell_it_casts_and_the_chip_steps_aside():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Frostbrand Weapon", "Windfury Weapon",
                        "Lightning Shield", "Water Shield"), tips={16: ["Rockbiter 1 (56 min)"]})
    t = icon(lua, IMBUE)
    assert t["shown"] and t["tex"] == 100000 + IMBUE_IDS["Rockbiter Weapon"], t
    assert not t["chip_any"], "the chip still shows under the icon"
    assert t["plate"] and t["text"] == "56m", "the time stays on the tile, on a label plate"
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    t = icon(lua, SHIELD)
    assert t["shown"] and t["tex"] == 100000 + SHIELD_ID and not t["chip_any"], t
    assert t["plate"] and t["text"] == "3", "the orb count stays on the tile"
    # the icon is the spell's own, not a fixed one: it follows the imbue the tile shows
    for name, line in (("Flametongue Weapon", "Flametongue 1 (59 min)"), ("Frostbrand Weapon", "Frostbrand 1 (59 min)"),
                       ("Windfury Weapon", "Windfury 1 (59 min)"), ("Rockbiter Weapon", "Rockbiter 1 (59 min)")):
        tip(lua, 16, [line])
        fire(lua, "UNIT_INVENTORY_CHANGED", "player")
        update(lua)
        assert icon(lua, IMBUE)["tex"] == 100000 + IMBUE_IDS[name], (name, icon(lua, IMBUE))


def check_the_missing_imbue_icon_is_the_one_the_click_casts():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"), tips={16: ["Heavy Axe"]})
    v = view(lua, "imbue")
    assert v.mode == "warn"
    t = icon(lua, IMBUE)
    best = IMBUE_IDS["Flametongue Weapon"]
    assert t["tex"] == 100000 + best, f"a missing imbue shows the best known one, which is what the click casts: {t}"
    assert str(attr(btn(lua, IMBUE), "spell")) == "Flametongue Weapon"


def check_water_shield_up_shows_its_own_icon_dimmed():
    lua = world(spells=("Rockbiter Weapon", "Lightning Shield", "Water Shield"), tips={16: ["Rockbiter 1 (56 min)"]})
    run(lua, "__water()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert view(lua, "shield").other
    t = icon(lua, SHIELD)
    assert t["tex"] == 100000 + WATER_ID, t
    assert t["desat"] and max(t["vertex"]) < 0.7, "Water Shield is another shield: dimmed and desaturated"


def check_missing_and_unreadable_states_dim_and_desaturate_the_icon_and_quiet_ones_do_not():
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    t = icon(lua, IMBUE)
    assert not t["desat"] and t["vertex"] == (1.0, 1.0, 1.0), f"quiet: {t}"
    tip(lua, 16, ["Rockbiter 1 (42 sec)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)
    t = icon(lua, IMBUE)
    assert not t["desat"] and t["vertex"] == (1.0, 1.0, 1.0), f"expiring keeps the lit icon (the pink says it): {t}"
    tip(lua, 16, ["Heavy Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)
    miss = icon(lua, IMBUE)
    assert miss["desat"] and all(abs(c - 0.45) < 1e-3 for c in miss["vertex"]), f"missing: {miss}"
    assert miss["text"] == "IMBUE" and miss["plate"], "the red word stays, on its plate"
    tip(lua, 16, None)
    run(lua, "__tipMode = 'nolines'")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    assert not icon(lua, SHIELD)["desat"]
    run(lua, "__noshield()")
    fire(lua, "UNIT_AURA", "player")
    update(lua)
    miss = icon(lua, SHIELD)
    assert miss["desat"] and miss["vertex"][0] < 0.5, f"a shield that is not up: {miss}"
    # the estimate in combat is a lit icon (the shield was up)
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    set_combat(lua, True)
    update(lua)
    assert not icon(lua, SHIELD)["desat"]


def check_the_usability_tint_reaches_the_icon():
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    base = icon(lua, IMBUE)["vertex"]
    use_spell(lua, "Rockbiter Weapon", False, True)
    fire(lua, "SPELL_UPDATE_USABLE")
    t = icon(lua, IMBUE)["vertex"]
    assert t[2] > t[0] and t != base, f"out of mana: the icon is blue ({t})"
    use_spell(lua, "Rockbiter Weapon", True, False)
    fire(lua, "SPELL_UPDATE_USABLE")
    assert icon(lua, IMBUE)["vertex"] == base


def check_a_spell_the_client_has_no_icon_for_keeps_the_chip_and_picks_the_icon_up_later():
    for mode in ("nil", "secret"):
        lua = boot(weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (56 min)"]},
                   pre_login=f'__iconMode = "{mode}"')
        fire(lua, "UNIT_INVENTORY_CHANGED", "player")
        update(lua)
        t = icon(lua, IMBUE)
        assert not t["shown"] and t["chip"] and not t["plate"], f"{mode}: the chip is the fallback {t}"
        assert (tile(lua, IMBUE)["code"], tile(lua, IMBUE)["text"]) == ("RB", "56m")
        close(tile(lua, IMBUE)["chip"], C["gold"], "fallback chip stroke")
        run(lua, "__iconMode = nil")
        tick(lua, 5)
        t = icon(lua, IMBUE)
        assert t["shown"] and t["tex"] == 100000 + 8017 and not t["chip_any"], f"{mode}: icon after the client answers {t}"
    lua = boot(weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (56 min)"]}, pre_login='__iconMode = "legacy"')
    update(lua)
    assert icon(lua, IMBUE)["tex"] == 100000 + 8017, "the legacy GetSpellTexture answers when C_Spell has none"


def check_no_imbue_known_has_no_spell_id_and_the_chip_label_stays():
    lua = world(spells=("Lightning Shield",), tips={16: ["Heavy Axe"]})
    assert not shown(btn(lua, IMBUE)), "no imbue known: the tile is absent"
    assert view(lua, "imbue").spellId is None
    assert view(lua, "shield").spellId == SHIELD_ID


def check_a_locked_shield_hides_its_icon_and_learning_it_brings_the_icon_back():
    lua = world(spells=("Rockbiter Weapon",), tips={16: ["Rockbiter 1 (56 min)"]})
    assert not shown(btn(lua, SHIELD).icon), "a locked tile shows its mold, not an icon"
    lua.execute('__spell("Lightning Shield", 324, true)')
    fire(lua, "SPELLS_CHANGED")
    update(lua)
    assert shown(btn(lua, SHIELD).icon) and icon(lua, SHIELD)["tex"] == 100000 + SHIELD_ID
    # and back: a tile that was showing its icon hides it when the spell goes away
    lua.execute('__spell("Lightning Shield", 324, false)')
    fire(lua, "SPELLS_CHANGED")
    update(lua)
    if btn(lua, SHIELD).fsLocked:
        assert not shown(btn(lua, SHIELD).icon), "a tile that locks again keeps no icon over its mold"


def check_an_icon_change_in_combat_is_a_texture_write_only():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (30 min)"]})
    before = blocked(lua)
    set_combat(lua, True)
    cast(lua, "Flametongue Weapon")
    tick(lua, 5)
    assert icon(lua, IMBUE)["tex"] == 100000 + IMBUE_IDS["Flametongue Weapon"], "the icon follows a cast in combat"
    assert blocked(lua) == before, "a protected write happened painting an icon in combat"
    leave_combat(lua)
    assert icon(lua, IMBUE)["shown"]


def check_the_tooltip_leads_with_the_spell_name_in_every_state():
    lua = world(spells=("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield"),
                tips={16: ["Rockbiter 1 (59 min)"]})
    assert tip_text(lua, IMBUE)[0] == "Rockbiter Weapon"
    tip(lua, 16, ["Rockbiter 1 (42 sec)"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert tip_text(lua, IMBUE)[0] == "Rockbiter Weapon"
    tip(lua, 16, ["Heavy Axe"])
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    assert tip_text(lua, IMBUE)[0] == "Rockbiter Weapon", "a missing imbue names the spell the click casts (the last one up)"
    tip(lua, 16, None)
    run(lua, "__tipMode = 'nolines'")
    fire(lua, "UNIT_INVENTORY_CHANGED", "player")
    update(lua)
    assert tip_text(lua, IMBUE)[0] in ("Rockbiter Weapon", "Flametongue Weapon"), tip_text(lua, IMBUE)
    for setup in ("__shield(3, 480)", "__noshield()"):
        run(lua, setup)
        fire(lua, "UNIT_AURA", "player")
        update(lua)
        text = tip_text(lua, SHIELD)
        assert text[0] == "Lightning Shield" and text[-1] == "Click: cast Lightning Shield.", text


def check_an_icon_the_client_never_answers_costs_nothing_between_retries():
    lua = boot(weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (56 min)"]}, pre_login='__iconMode = "nil"')
    run(lua, """
        if jit then jit.off() end
        local ShamanBuffs, BuffTab = FS.ShamanBuffs, FS.BuffTab
        local t = __now
        local function step(i) ShamanBuffs.Update(t + i * 0.01); BuffTab.Paint() end
        for i = 1, 50 do step(i) end
        collectgarbage("collect"); collectgarbage("stop")
        local before = collectgarbage("count")
        for i = 51, 450 do step(i) end
        __grew = (collectgarbage("count") - before) * 1024
        collectgarbage("restart")
    """)
    assert float(g(lua).__grew) < 2000, f"an unanswered icon repainted every call: {float(g(lua).__grew):.0f} bytes"


# ---------------------------------------------------------------------------------------------
# Checks: the engine drawn state in combat (the AuraContainer slots)
# ---------------------------------------------------------------------------------------------

LS_RANKS = (324, 325, 905, 945, 8134, 10431, 10432, 25469, 25472)
WS_RANKS = (24398, 33736)


def acs(lua):
    return [g(lua).__acs[i] for i in range(1, len(g(lua).__acs) + 1)]


def ac_log(lua):
    t = g(lua).__acLog
    return [(str(t[i].name), bool(t[i].combat)) for i in range(1, len(t) + 1)]


def same(lua, a, b) -> bool:
    return bool(lua.eval("function(a, b) return a == b end")(a, b))


def engine_world(pre="", **kw):
    kw.setdefault("tips", {16: ["Rockbiter 1 (30 min)"]})
    kw.setdefault("spells", ("Rockbiter Weapon", "Flametongue Weapon", "Lightning Shield", "Water Shield"))
    kw.setdefault("weapons", {16: "INVTYPE_WEAPON"})
    return boot(pre_login="__template = true\n" + pre, **kw)


def engine_cap(lua):
    return g(lua).FS.BuffTab.Engine


def order_of(slot):
    return [str(slot._order[i]) for i in range(1, len(slot._order) + 1)]


def shield_aura_up(lua):
    run(lua, "__shield(3, 480)")
    fire(lua, "UNIT_AURA", "player")
    update(lua)


def check_the_combat_container_is_built_once_out_of_combat_with_both_slots():
    lua = engine_world()
    cs = acs(lua)
    assert len(cs) == 1, f"{len(cs)} containers"
    c = cs[0]
    assert same(lua, c._parent, g(lua).FSBuffTab), "the container hangs off the tab host"
    assert c._unit == "player" and c._enabled and shown(c) and float(c._alpha) == 0, "armed, unit player, invisible"
    assert c._slots["shield"].filter == "HELPFUL"
    got = {int(k) for k in c._slots["shield"].ids.keys()}
    assert set(LS_RANKS + WS_RANKS) <= got, f"missing rank ids {set(LS_RANKS + WS_RANKS) - got}"
    # both hands, the main hand added last (it draws on top of the off hand)
    assert [int(c._enchOrder[i]) for i in (1, 2)] == [2, 1], "the off hand goes first, the main hand last"
    for _ in range(3):
        fire(lua, "SPELLS_CHANGED")
        leave_combat(lua)
        tick(lua, 5)
    assert len(acs(lua)) == 1 and int(g(lua).__acAttempts) == 1, "built more than once"
    for name, in_combat in ac_log(lua):
        assert not in_combat, f"{name} ran in combat"


def check_the_shield_slot_seats_on_the_icon_and_draws_icon_time_and_count():
    lua = engine_world()
    c = acs(lua)[0]
    slot = c._slots["shield"].frame
    order = order_of(slot)
    assert "SetIcon" in order and "SetDurationText" in order and "SetApplicationCount" in order, order
    assert slot._SetMouseMotionEnabled is False and slot._SetMouseClickEnabled is False, "the slot would eat clicks"
    assert order.index("SetMouseMotionEnabled") < order.index("SetIcon"), "mouse is switched off first"
    b = btn(lua, SHIELD)
    assert same(lua, slot._points[1].rel, b.icon), "the slot sits on the tile's icon rect"
    assert slot._icon is not None and slot._durationText is not None and slot._countText is not None
    dur = slot._durationText._points[1]
    assert same(lua, dur.rel, b) and dur.point == "CENTER", "the engine time sits where the tile's time does"
    assert slot._countText._points[1].point == "TOPRIGHT"
    assert float(c._level) > float(g(lua).FSBuffTab._level), "the container is above the tiles"


def parts_of(lua, i):
    eng = btn(lua, i).fsEngine
    return [eng.parts[k] for k in range(1, len(eng.parts) + 1)]


def check_the_imbue_slots_carry_our_lit_icon_and_the_engine_time_on_both_hands():
    lua = engine_world()
    c = acs(lua)[0]
    b = btn(lua, IMBUE)
    parts = parts_of(lua, IMBUE)
    assert len(parts) == 2, "both hands keep their own parts"
    assert btn(lua, IMBUE).fsEngine.declared == 2
    for hand in (1, 2):
        slot = c._ench[hand]
        order = order_of(slot)
        assert "SetDurationText" in order and "SetIcon" not in order, f"hand {hand}: {order}"
        assert same(lua, slot._points[1].rel, b.icon)
    assert {bool(same(lua, p.slot, c._ench[h])) for p in parts for h in (1, 2) if same(lua, p.slot, c._ench[h])} == {True}
    for part in parts:
        assert int(part.lit._texture) == 100000 + 8017, "each hand's lit icon is the pick"
        assert part.dur._points[1].rel is not None and part.durPlate is not None, "time seated at init, on a plate"
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    cast(lua, "Flametongue Weapon")
    tick(lua, 5)
    assert int(g(lua).__slotBlocked) == 0, "a slot region was written in combat"
    for part in parts:
        assert int(part.lit._texture) == 100000 + 8017, "no lit icon write in combat"
    tip(lua, 16, ["Flametongue 1 (59 min)"])
    leave_combat(lua)
    tick(lua, 5)
    for part in parts:
        assert int(part.lit._texture) == 100000 + 8024, "the regen repaint writes BOTH hands' lit icons"


def check_in_combat_the_tiles_drop_to_the_dim_base_and_only_the_alpha_is_written():
    lua = engine_world()
    shield_aura_up(lua)
    assert (tile(lua, IMBUE)["text"], tile(lua, SHIELD)["text"]) == ("30m", "3")
    c = acs(lua)[0]
    mark = len(ac_log(lua))
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    assert float(c._alpha) == 1 and tile(lua, SHIELD)["text"] == "", "the combat state starts at the combat edge, not a second later"
    tick(lua, 5)
    assert float(c._alpha) == 1, "the slots are shown in combat"
    for i in (IMBUE, SHIELD):
        t, ic = tile(lua, i), icon(lua, i)
        assert t["text"] == "" and not ic["plate"], f"tile {i} shows a frozen word in combat: {t['text']!r}"
        assert t["dashes"] == [0.0] * 4 and t["line_a"] == 0, "no estimate dashes or underline in combat"
        assert ic["desat"] and all(abs(x - 0.6) < 1e-3 for x in ic["vertex"]), f"the dim base: {ic}"
    for name, in_combat in ac_log(lua)[mark:]:
        assert name == "SetAlpha" and in_combat, f"{name} written in combat"
    assert blocked(lua) == 0
    # regen: invisible again, the plain reads are back
    leave_combat(lua)
    assert float(c._alpha) == 0, "invisible out of combat"
    tick(lua, 5)
    assert (tile(lua, IMBUE)["text"], tile(lua, SHIELD)["text"]) in (("30m", "3"), ("29m", "3")), "the plain reads are back"
    assert not icon(lua, IMBUE)["desat"] and not icon(lua, SHIELD)["desat"]
    assert icon(lua, IMBUE)["plate"] and icon(lua, SHIELD)["plate"]


def check_regen_arms_a_container_that_reads_back_off_and_a_combat_login_builds_at_regen():
    lua = engine_world()
    c = acs(lua)[0]
    run(lua, "__acs[1]._enabled = false")
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    assert not c._enabled and not [e for e in ac_log(lua) if e[0] == "SetEnabled" and e[1]], "never enabled in combat"
    leave_combat(lua)
    assert c._enabled, "regen arms it again"
    lua = engine_world(combat=True)
    assert acs(lua) == [], "a container was built in combat"
    leave_combat(lua)
    assert len(acs(lua)) == 1 and acs(lua)[0]._enabled


def check_nothing_is_built_in_combat_whoever_asks():
    lua = engine_world()
    run(lua, "FS.BuffTab.Engine.container = nil")
    set_combat(lua, True)
    bt(lua).EnsureEngine()
    fire(lua, "SPELLS_CHANGED")
    tick(lua, 5)
    assert len(acs(lua)) == 1 and int(g(lua).__acAttempts) == 1, "a container was built in combat"
    leave_combat(lua)
    assert int(g(lua).__acAttempts) == 2 and len(acs(lua)) == 2, "the next out of combat pass builds it"


def check_a_failed_build_logs_once_leaves_today_and_gives_up_after_three_passes():
    lua = engine_world(pre="__acThrows = true\n__logs = 0\nFS.LogDegradeOnce = function() __logs = __logs + 1 end")
    assert int(g(lua).__acAttempts) == 1, "the login burst of syncs is one pass, one attempt"
    for _ in range(6):
        fire(lua, "SPELLS_CHANGED")
    assert int(g(lua).__acAttempts) == 1, "more syncs in the same pass do not try again"
    assert not engine_cap(lua).gaveUp
    for n in (2, 3):
        set_combat(lua, True)
        fire(lua, "PLAYER_REGEN_DISABLED")
        leave_combat(lua)
        assert int(g(lua).__acAttempts) == n, f"pass {n}"
    assert engine_cap(lua).gaveUp is True
    leave_combat(lua)
    assert int(g(lua).__acAttempts) == 3
    assert int(g(lua).__logs) == 1, f"{int(g(lua).__logs)} log lines"
    assert acs(lua) == []
    tick(lua, 5)
    shield_aura_up(lua)
    set_combat(lua, True)
    update(lua)
    assert btn(lua, SHIELD).fsEngine is None
    # today's combat look: the estimate with its tilde, undimmed
    assert tile(lua, SHIELD)["text"] == "~3", tile(lua, SHIELD)["text"]
    assert not icon(lua, SHIELD)["desat"]


def check_a_client_without_the_template_or_item_enchantments_keeps_todays_tiles():
    lua = boot(weapons={16: "INVTYPE_WEAPON"}, tips={16: ["Rockbiter 1 (30 min)"]})        # no template
    assert acs(lua) == [] and engine_cap(lua).gaveUp is True
    shield_aura_up(lua)
    set_combat(lua, True)
    update(lua)
    assert tile(lua, SHIELD)["text"] == "~3"
    lua = engine_world(pre="__noEnchantApi = true")
    assert btn(lua, IMBUE).fsEngine is None and btn(lua, SHIELD).fsEngine is not None, "only the imbue tile loses its slot"
    shield_aura_up(lua)
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    update(lua)
    assert tile(lua, IMBUE)["text"] == "30m", "the imbue tile keeps its estimate"
    assert tile(lua, SHIELD)["text"] == ""


def check_a_failed_shield_slot_costs_only_its_own_tile():
    lua = engine_world(pre='__acSlotThrows = "shield"')
    assert len(acs(lua)) == 1, "the container itself stands"
    assert btn(lua, SHIELD).fsEngine is None and btn(lua, IMBUE).fsEngine is not None
    shield_aura_up(lua)
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    update(lua)
    assert tile(lua, IMBUE)["text"] == "", "the kept tile is in engine mode"
    assert tile(lua, SHIELD)["text"] != "", "the lost tile keeps today's text"


def check_a_half_failed_imbue_pair_parks_the_container_and_rebuilds_without_imbue_slots():
    for hand in ("main", "off", True):
        lua = engine_world(pre=f"__acEnchThrows = {hand!r}".replace("True", "true").replace("'", '"'))
        cs = acs(lua)
        assert len(cs) == 2, f"{hand}: the failed container and its replacement"
        old, new = cs
        assert not old._enabled and not shown(old) and float(old._alpha) == 0, f"{hand}: the failed container is parked"
        assert new._enabled and shown(new) and not new._ench[1] and "shield" in [str(k) for k in new._slots.keys()]
        assert len(list(new._ench.keys())) == 0, f"{hand}: no stray enchantment slot on the live container"
        assert btn(lua, IMBUE).fsEngine is None and btn(lua, SHIELD).fsEngine is not None
        assert len(g(lua).FS.BuffTab.Engine.parked) == 1
        for _ in range(3):
            fire(lua, "SPELLS_CHANGED")
        assert len(acs(lua)) == 2, f"{hand}: the imbue slots are not tried again"


def check_a_lazily_built_slot_seats_its_texts_and_icon_on_its_own():
    lua = engine_world(pre="__acLazy = true")
    assert parts_of(lua, SHIELD) == [] and btn(lua, SHIELD).fsEngine.declared == 1, "init has not run yet"
    update(lua)
    leave_combat(lua)                 # a Sync and a regen pass, with no frame yet: nothing depends on them
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    run(lua, "__acFlush()")           # the engine first needs the frames in combat
    assert int(g(lua).__slotBlocked) == 0, "initializeFrame was treated as restricted"
    for i, n in ((SHIELD, 1), (IMBUE, 2)):
        parts = parts_of(lua, i)
        assert len(parts) == n, (i, len(parts))
        for part in parts:
            assert part.dur is not None and len(part.dur._points) == 1, "the time is seated by initializeFrame itself"
            assert same(lua, part.dur._points[1].rel, btn(lua, i))
            assert part.durPlate is not None
        if i == SHIELD:
            assert parts[0].count is not None and parts[0].count._points[1].point == "TOPRIGHT"
            assert parts[0].countPlate is not None, "the count has a label plate too"
    # the unproven state is not trusted yet: no layout was read, so the slot is kept
    assert btn(lua, SHIELD).fsEngine.bad is False
    leave_combat(lua)
    assert [len(parts_of(lua, i)) for i in (SHIELD, IMBUE)] == [1, 2]


def check_the_engine_state_is_entered_only_on_a_proven_arm():
    lua = engine_world()
    shield_aura_up(lua)
    c = acs(lua)[0]
    assert engine_cap(lua).armed is True
    # a re-arm the engine refuses: the container reads back off, so combat shows today's estimate, not "not active"
    run(lua, "__acs[1]._enabled = false\n__acRefuse = true")
    set_combat(lua, True)
    leave_combat(lua)
    assert engine_cap(lua).armed is False, "the readback says it is not armed"
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    update(lua)
    assert float(c._alpha) == 0, "a container that is not armed is never shown"
    assert tile(lua, SHIELD)["text"] == "~3" and not icon(lua, SHIELD)["desat"], "today's frozen estimate"
    assert not bt(lua).EngineLive("shield")
    # the engine takes the arm at the next out of combat pass: proven again
    run(lua, "__acRefuse = false")
    leave_combat(lua)
    assert engine_cap(lua).armed is True and c._enabled
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    assert float(c._alpha) == 1 and bt(lua).EngineLive("shield")


def check_a_slot_that_is_not_on_its_tiles_icon_clears_that_tiles_engine_state():
    # the engine's layout re-anchors the slot for good: no tile can be trusted
    lua = engine_world(pre='__acOverride = "sticky"\n__logs = 0\nFS.LogDegradeOnce = function() __logs = __logs + 1 end')
    shield_aura_up(lua)
    for i in (SHIELD, IMBUE):
        assert btn(lua, i).fsEngine.bad is True, i
    assert int(g(lua).__logs) == 1 and g(lua).FS.BuffTab.BT.warned.bufftab_engine_layout, "logged once"
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    update(lua)
    assert not bt(lua).EngineLive("shield") and not bt(lua).EngineLive("imbue")
    assert tile(lua, SHIELD)["text"] == "~3" and not icon(lua, SHIELD)["desat"], "today's estimate stays"
    # a re-anchor done once at init is put right by the next seat, and the tile is proven again
    lua = engine_world(pre='__acOverride = "init"')
    for i in (SHIELD, IMBUE):
        assert btn(lua, i).fsEngine.bad is False, i
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    assert bt(lua).EngineLive("shield") and bt(lua).EngineLive("imbue")
    # a client that cannot say where anything stands proves nothing either way: the slot is kept
    lua = engine_world(pre="__noRect = true")
    assert btn(lua, SHIELD).fsEngine.bad is False


def check_the_setting_turns_the_combat_state_off_and_back_on():
    lua = engine_world()
    shield_aura_up(lua)
    c = acs(lua)[0]
    cfg = g(lua).FS.Config
    assert cfg.Get("buffs.combatstate") is True, "on by default"
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    assert float(c._alpha) == 1
    cfg.Set("buffs.combatstate", False)
    update(lua)
    assert float(c._alpha) == 0 and tile(lua, SHIELD)["text"] == "~3", "off in combat: the estimate, the slots hidden"
    assert [t for t in tip_text(lua, SHIELD)][1].startswith("Charges cannot be read in combat")
    cfg.Set("buffs.combatstate", True)
    update(lua)
    assert float(c._alpha) == 1 and tile(lua, SHIELD)["text"] == ""
    leave_combat(lua)
    cfg.Set("buffs.combatstate", False)
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    assert float(c._alpha) == 0 and tile(lua, SHIELD)["text"] != ""
    # a world that starts with it off never builds a container
    lua = engine_world(pre="FS.Config.Set('buffs.combatstate', false)")
    assert acs(lua) == []
    leave_combat(lua)
    g(lua).FS.Config.Set("buffs.combatstate", True)
    assert len(acs(lua)) == 1, "switching it on out of combat builds it"


def check_the_in_combat_tooltip_says_the_game_shows_the_state_and_that_any_enchant_lights_the_imbue():
    lua = engine_world()
    shield_aura_up(lua)
    before = tip_text(lua, IMBUE)
    assert before[1] == "Main hand imbue, 30 min left."
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")
    imbue, shield = tip_text(lua, IMBUE), tip_text(lua, SHIELD)
    assert imbue == ["Rockbiter Weapon", "The game shows the imbue time in combat.",
                     "In combat this shows any weapon enchant.", "Click: cast Rockbiter Weapon."], imbue
    assert shield == ["Lightning Shield", "The game shows your shield and its time in combat.",
                      "Click: cast Lightning Shield."], shield
    for line in imbue + shield:
        assert "min left" not in line and "charges" not in line.lower(), f"a frozen number as fact: {line}"
    leave_combat(lua)
    tick(lua, 5)
    assert tip_text(lua, IMBUE)[1].startswith("Main hand imbue")


def check_a_slot_found_with_the_mouse_on_is_made_click_through_and_logged():
    lua = engine_world(pre="__acMouseOn = true\n__logs = 0\nFS.LogDegradeOnce = function() __logs = __logs + 1 end")
    c = acs(lua)[0]
    slots = [c._slots["shield"].frame, c._ench[1], c._ench[2]]
    for slot in slots:
        assert slot._SetMouseClickEnabled is False and slot._SetMouseMotionEnabled is False, "mouse turned off again"
    assert int(g(lua).__logs) == 1
    # where the client has them, propagating clicks and motion keeps the tile's tooltip and click working
    lua = engine_world(pre="__acMouseOn = true\n__acPropagate = true")
    c = acs(lua)[0]
    for slot in (c._slots["shield"].frame, c._ench[1], c._ench[2]):
        assert slot._propClicks is True and slot._propMotion is True
    # a slot with the mouse already off is left alone
    lua = engine_world(pre="__logs = 0\nFS.LogDegradeOnce = function() __logs = __logs + 1 end")
    assert int(g(lua).__logs) == 0


def check_a_changed_spellbook_rebuilds_the_container_with_the_new_shield_ids():
    lua = engine_world()
    old = acs(lua)[0]
    assert 99999 not in {int(k) for k in old._slots["shield"].ids.keys()}
    fire(lua, "SPELLS_CHANGED")
    assert len(acs(lua)) == 1, "an unchanged id set keeps the container"
    run(lua, '__spell("Lightning Shield", 99999, true)')
    set_combat(lua, True)
    fire(lua, "SPELLS_CHANGED")
    assert len(acs(lua)) == 1, "nothing is rebuilt in combat"
    leave_combat(lua)
    cs = acs(lua)
    assert len(cs) == 2, "the changed ids rebuild"
    assert not old._enabled and not shown(old) and float(old._alpha) == 0, "the old container is parked"
    assert 99999 in {int(k) for k in cs[1]._slots["shield"].ids.keys()}
    assert cs[1]._enabled and shown(cs[1])
    assert len(g(lua).FS.BuffTab.Engine.parked) == 1
    assert btn(lua, SHIELD).fsEngine is not None and parts_of(lua, SHIELD)[0].slot is not None


def check_the_chip_and_ring_chrome_numbers_are_pinned_by_value():
    lua = world(tips={16: ["Rockbiter 1 (56 min)"]})
    t = tile(lua, IMBUE)
    approx(float(t["chip_glow"][1]) if False else float(btn(lua, IMBUE).fsChip.glow._vertex[4]), 0.35, "chip glow alpha")
    assert float(bt(lua).BT.CHIP_GLOW_A) == 0.35
    L = bt(lua).Looks()
    assert (float(L.on.ringA), float(L.on.glowA)) == (0.35, 0.0)
    assert (float(L.exp.ringA), float(L.exp.glowA)) == (0.9, 0.5)
    assert (float(L.warn.ringA), float(L.warn.glowA)) == (0.85, 0.5)
    assert (float(L.hollow.ringA), float(L.hollow.glowA)) == (0.6, 0.0)
    assert (float(L.cyan.ringA), float(L.cyan.glowA)) == (1.0, 0.6)


def check_a_rescale_reseats_every_engine_text_out_of_combat_only():
    lua = engine_world()
    texts = [(p.dur, float(p.dur._points[1].y)) for i in (SHIELD, IMBUE) for p in parts_of(lua, i)]
    assert len(texts) == 3, "the shield's time and both hands' times"
    set_combat(lua, True)
    lua.eval("__rescale")(0.8333)
    assert int(g(lua).__slotBlocked) == 0, "a rescale in combat wrote a slot region"
    assert all(float(d._points[1].y) == y0 for d, y0 in texts), "nothing is re-seated in combat"
    leave_combat(lua)
    for dur, y0 in texts:
        y1 = float(dur._points[1].y)
        assert y1 != y0 and abs(y1 / y0 - 0.8333) < 0.01, (y0, y1)
    assert int(g(lua).__slotBlocked) == 0


CHECKS = [
    check_parse_reads_minutes_seconds_hours_with_and_without_a_rank,
    check_parse_ignores_lines_that_are_not_an_imbue_with_a_time,
    check_parse_follows_the_clients_own_enchant_time_strings_and_spell_names,
    check_the_imbue_names_come_from_the_spell_ids_not_from_english_text,
    check_tooltip_reads_say_imbue_none_or_unreadable,
    check_the_main_hand_imbue_shows_its_code_and_time_in_the_quiet_look,
    check_under_five_minutes_the_tile_turns_pink_and_under_one_minute_counts_seconds,
    check_a_missing_imbue_is_a_red_hollow_word_and_an_unreadable_one_a_hollow_question_mark,
    check_dual_wield_shows_the_least_time_and_asks_for_the_missing_hand,
    check_a_shield_or_an_empty_off_hand_never_asks_for_an_imbue,
    check_a_two_handed_weapon_without_an_imbue_asks_for_one,
    check_the_tooltip_is_never_read_in_combat_and_the_clock_counts_down_from_the_last_read,
    check_tile_fonts_are_the_design_size_at_every_scale_and_after_a_rescale,
    check_the_missing_imbue_word_stays_at_the_full_size_where_it_fits_and_only_shield_starts_small,
    check_a_fitted_tile_string_never_goes_below_six_pixels,
    check_an_irrelevant_cast_is_a_no_op_and_an_unknown_id_with_the_shield_name_is_ignored,
    check_leaving_combat_keeps_the_shield_an_estimate_until_the_next_tick_reads_the_snapshot,
    check_a_tooltip_read_that_contradicts_a_fresh_cast_waits_for_the_grace,
    check_learning_lightning_shield_unlocks_the_tile_whichever_handler_runs_first,
    check_an_unchanged_tick_allocates_nothing_in_or_out_of_combat,
    check_the_slow_tick_reads_out_of_combat_and_a_read_does_not_stair_step_the_clock,
    check_a_cast_starts_a_fresh_hour_and_the_next_read_takes_over,
    check_a_cast_in_combat_counts_a_fresh_hour_and_a_weapon_swapped_in_combat_is_forgotten,
    check_two_imbue_casts_back_to_back_each_go_to_their_own_hand,
    check_a_recast_on_the_other_hand_does_not_hide_the_sooner_expiring_one,
    check_a_pending_cast_outlasts_an_early_none_read_only_for_the_grace,
    check_get_weapon_enchant_info_counts_only_when_it_answers_true,
    check_no_imbue_known_means_no_tile_and_learning_one_brings_it,
    check_the_shield_shows_ls_and_its_orbs_then_its_time_when_expiring,
    check_a_missing_shield_is_red_and_no_snapshot_yet_is_a_hollow_question_mark,
    check_in_combat_the_shield_is_an_estimate_with_a_tilde_and_dashes,
    check_a_shield_cast_in_combat_shows_three_orbs_and_a_pending_cast_expires_with_the_clock,
    check_water_shield_is_never_nagged_and_a_water_shield_cast_in_combat_clears_the_lightning_cast,
    check_a_shield_with_no_aura_end_ends_at_its_application_not_at_the_last_read,
    check_lightning_shield_is_a_locked_dotted_mold_until_it_is_known,
    check_two_named_secure_buttons_in_the_fixed_order_built_once,
    check_click_attributes_are_a_spell_by_name_and_follow_the_imbue_shown,
    check_attributes_are_written_out_of_combat_only_and_queued_for_regen,
    check_nothing_protected_is_touched_in_combat_by_events_ticks_and_paint,
    check_no_forbidden_field_or_attribute_is_ever_written_on_a_secure_button,
    check_the_files_use_no_snippets_and_no_state_drivers,
    check_tooltip_lines_follow_the_mockups_wording,
    check_the_tooltip_colours_are_gold_pink_red_and_muted,
    check_hover_turns_the_border_cyan_and_leaving_restores_the_state_colour,
    check_hotkey_text_and_quick_keybind_commands,
    check_bindings_xml_declares_the_two_buff_tab_commands_after_the_totems,
    check_binding_labels_exist_for_every_class,
    check_the_console_gap_is_the_union_and_the_top_line_is_bridged_between_the_tabs,
    check_the_tab_follows_the_console_on_and_off_and_sits_beside_the_totem_tab,
    check_a_rescale_resizes_and_reseats_out_of_combat,
    check_no_secure_frame_is_anchored_to_the_shoulder_art,
    check_a_seat_change_in_combat_waits_for_regen,
    check_a_login_in_combat_builds_at_regen,
    check_only_a_shaman_gets_a_tab,
    check_a_failed_build_leaves_no_listener_running,
    check_the_listeners_start_once_the_tiles_exist_and_only_for_the_unit_player,
    check_the_tab_needs_no_target_and_hangs_on_the_ui_not_the_gunsight,
    check_the_tab_stands_with_the_gunsight_hud_off,
    check_unreadable_sources_keep_the_last_known_imbue_and_never_log_or_throw,
    check_toc_lists_the_buff_files_after_the_totem_bar,
    check_no_em_dashes_and_no_flagged_words_in_the_new_files,
    check_the_old_class_module_chips_are_gone_from_the_gunsight_file,
    check_low_mana_tints_the_tile_foreground_blue_unusable_grey_and_usable_is_the_approved_look,
    check_the_tint_blends_with_each_state_colour_pink_red_and_hollow,
    check_the_red_is_the_themes_red_token_and_the_mockups,
    check_gold_and_pink_are_unchanged_and_only_the_missing_state_is_red,
    check_the_missing_red_composes_with_the_usability_tints,
    check_a_nil_first_answer_is_unusable_and_a_secret_mana_flag_does_not_hide_a_plain_false,
    check_a_tile_whose_spell_goes_nil_drops_its_tint,
    check_the_tile_asks_the_spell_api_about_the_spell_it_casts,
    check_a_secret_missing_or_raising_answer_leaves_the_tile_tint_as_it_was,
    check_the_tint_follows_each_usability_event_and_leaving_combat,
    check_a_locked_or_absent_tile_is_never_asked_and_never_tinted,
    check_a_tinted_idle_tick_allocates_nothing_in_or_out_of_combat,
    check_each_tile_wears_the_icon_of_the_spell_it_casts_and_the_chip_steps_aside,
    check_the_missing_imbue_icon_is_the_one_the_click_casts,
    check_water_shield_up_shows_its_own_icon_dimmed,
    check_missing_and_unreadable_states_dim_and_desaturate_the_icon_and_quiet_ones_do_not,
    check_the_usability_tint_reaches_the_icon,
    check_a_spell_the_client_has_no_icon_for_keeps_the_chip_and_picks_the_icon_up_later,
    check_no_imbue_known_has_no_spell_id_and_the_chip_label_stays,
    check_a_locked_shield_hides_its_icon_and_learning_it_brings_the_icon_back,
    check_an_icon_change_in_combat_is_a_texture_write_only,
    check_the_tooltip_leads_with_the_spell_name_in_every_state,
    check_an_icon_the_client_never_answers_costs_nothing_between_retries,
    check_the_combat_container_is_built_once_out_of_combat_with_both_slots,
    check_the_shield_slot_seats_on_the_icon_and_draws_icon_time_and_count,
    check_the_imbue_slots_carry_our_lit_icon_and_the_engine_time_on_both_hands,
    check_in_combat_the_tiles_drop_to_the_dim_base_and_only_the_alpha_is_written,
    check_regen_arms_a_container_that_reads_back_off_and_a_combat_login_builds_at_regen,
    check_nothing_is_built_in_combat_whoever_asks,
    check_a_failed_build_logs_once_leaves_today_and_gives_up_after_three_passes,
    check_a_client_without_the_template_or_item_enchantments_keeps_todays_tiles,
    check_a_failed_shield_slot_costs_only_its_own_tile,
    check_a_half_failed_imbue_pair_parks_the_container_and_rebuilds_without_imbue_slots,
    check_a_lazily_built_slot_seats_its_texts_and_icon_on_its_own,
    check_the_engine_state_is_entered_only_on_a_proven_arm,
    check_a_slot_that_is_not_on_its_tiles_icon_clears_that_tiles_engine_state,
    check_the_setting_turns_the_combat_state_off_and_back_on,
    check_the_in_combat_tooltip_says_the_game_shows_the_state_and_that_any_enchant_lights_the_imbue,
    check_a_slot_found_with_the_mouse_on_is_made_click_through_and_logged,
    check_a_changed_spellbook_rebuilds_the_container_with_the_new_shield_ids,
    check_the_chip_and_ring_chrome_numbers_are_pinned_by_value,
    check_a_rescale_reseats_every_engine_text_out_of_combat_only,
]
SCALED_CHECKS = [
    check_the_shoulder_is_the_two_by_one_block_at_316_and_the_buttons_sit_inside_it,
    check_every_tile_string_fits_inside_its_tile_in_every_state,
]


def main() -> int:
    failed = total = 0

    def run_check(label, fn, *args):
        nonlocal failed, total
        total += 1
        try:
            fn(*args)
            print(f"ok    {label}")
        except (AssertionError, LuaError, FileNotFoundError, AttributeError, TypeError, KeyError, IndexError) as err:
            failed += 1
            print(f"FAIL  {label}\n      " + f"{type(err).__name__}: {err}".replace("\n", "\n      "))

    for fn in CHECKS:
        run_check(fn.__name__, fn)
    for fn in SCALED_CHECKS:
        for scale in SCALES:
            run_check(f"{fn.__name__} @scale={scale:.4f}", fn, scale)
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
