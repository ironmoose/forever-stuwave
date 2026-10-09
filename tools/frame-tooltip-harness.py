#!/usr/bin/env python3
"""Runs the real Core/FrameHelpers.lua tooltip helper family headless against a mock WoW API.

The family gives every icon surface a tooltip that survives combat: HoverOnly (motion-only mouse, never a
click-taking frame), SetTipSpell (validated spell id and name cached on the frame, no allocation), SpellIDForName
(session cache over C_Spell.GetSpellInfo), AttachSpellTooltip / RefreshSpellTooltip (the OnEnter/OnLeave/OnHide
lifecycle) and the combat branch of ShowAuraTooltip. The checks pin:

  * HoverOnly enables motion and disables clicks; a client missing either call gets no mouse at all, and
    EnableMouse(true) is never called;
  * SetTipSpell stores only a plain positive number and a plain non-empty string (a secret, nil, zero or the
    wrong type clears the field), and refreshes an open tooltip when the id or name changed;
  * SpellIDForName caches hits and out-of-combat misses (SPELLS_CHANGED wipes both, at PLAYER_REGEN_ENABLED when
    it fired in combat), looks a combat miss up once per combat, never touches a secret name or a secret result;
  * ReleaseSpellTip / ReleaseGatedTips take down a tip whose owner's gate now says no;
  * the secret stand-ins report type() "number" / "string" and throw on arithmetic, comparison, concat and
    indexing, so stripping an IsSecret guard fails a check (== against a plain string cannot be trapped in Lua);
  * a hovered frame that hides or loses the mouse leaves no tooltip behind; opts.gate = false shows nothing;
  * the tooltip prefers the live aura slot, then SetSpellByID, then the cached name; a stale aura slot, a
    missing or a throwing SetSpellByID each fall through to the next;
  * ShowAuraTooltip in combat uses the cached spell id when it has one.

Core/Theme.lua is NOT loaded: FS.IsSecret and FS.AurasReadable are stubs with the same contract.

    python3 tools/frame-tooltip-harness.py

Exit 0 = every check passed. FRAMETOOLTIP_LUA=<path> runs another file in place of Core/FrameHelpers.lua.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
HELPERS = Path(os.environ.get("FRAMETOOLTIP_LUA") or ADDON / "Core/FrameHelpers.lua")

MOCK = r"""
IN_COMBAT = false
READABLE = true
SPELL_CALLS = 0
SPELL_INFO = {}       -- name -> spellID, for C_Spell.GetSpellInfo
SPELL_RAW = {}        -- name -> the exact value GetSpellInfo returns (overrides SPELL_INFO)

function check(c, msg) if not c then error(msg or "check failed", 2) end end
function InCombatLockdown() return IN_COMBAT end

-- Secret values: errors on anything but being passed along. type() is shadowed so a secret reports the
-- type of the thing it stands in for ("number" / "string"), as in the client, where only IsSecret tells
-- them apart. SECRET_INFO stands in for a secret table (type() says "table"; indexing it throws).
-- Lua cannot trap == against a plain string or use as a table key; those are the two touches the mock misses.
local function boom() error("secret value touched", 2) end
local function secret()
    return setmetatable({}, { __lt = boom, __le = boom, __add = boom, __sub = boom, __mul = boom, __div = boom,
        __mod = boom, __pow = boom, __concat = boom, __len = boom, __unm = boom, __index = boom,
        __newindex = boom, __call = boom, __eq = boom })
end
SECRET_NUM, SECRET_STR, SECRET_INFO = secret(), secret(), secret()
local realtype = type
function type(v)
    if rawequal(v, SECRET_NUM) then return "number" end
    if rawequal(v, SECRET_STR) then return "string" end
    return realtype(v)
end
function isSecretValue(v) return rawequal(v, SECRET_NUM) or rawequal(v, SECRET_STR) or rawequal(v, SECRET_INFO) end

-- The tooltip records what it was asked to show. owner/shown/spellID/text/lines describe the current state.
local TT = {}
GameTooltip = TT
function TT:Reset() self.owner, self.anchor, self.shown, self.spellID, self.text, self.lines, self.aura = nil, nil, false, nil, nil, {}, nil end
function TT:SetOwner(o, anchor) self:Reset(); self.owner, self.anchor = o, anchor end
function TT:GetOwner() return self.owner end
function TT:IsOwned(f) return self.owner == f end
function TT:SetText(t) self.text = t end
function TT:AddLine(t) self.lines[#self.lines + 1] = t end
function TT:Show() self.shown = true end
function TT:Hide() self.shown = false; self.owner = nil end
function TT:SetUnitAura(unit, index, filter)
    if self.auraThrows then error("stale aura slot") end
    self.aura = unit .. ":" .. index .. ":" .. filter; self.shown = true end
function TT:SetSpellByID(id)
    if self.throws then error("SetSpellByID refused") end
    self.spellID = id; self.shown = true
end
TT:Reset()

local Frame = {}
Frame.__index = Frame
function Frame:HookScript(n, fn) self.hooks[n] = self.hooks[n] or {}; table.insert(self.hooks[n], fn) end
function Frame:SetScript(n, fn) self.scripts[n] = fn end
function Frame:Run(n) for _, fn in ipairs(self.hooks[n] or {}) do fn(self) end end
function Frame:Hide() self.hidden = true; self:Run("OnHide") end
function Frame:EnableMouse(on) if on then error("EnableMouse(true) on a pass-through frame") end end
function Frame:SetMouseMotionEnabled(on) self.motion = on end
function Frame:SetMouseClickEnabled(on) self.click = on end
function Frame:RegisterEvent(e) self.events[e] = true end
CREATED = {}
function CreateFrame() local f = newFrame(); CREATED[#CREATED + 1] = f; return f end   -- event frames made at load
function fireEvent(e) for _, f in ipairs(CREATED) do if f.events[e] and f.scripts.OnEvent then f.scripts.OnEvent(f, e) end end end
function newFrame() return setmetatable({ hooks = {}, scripts = {}, events = {} }, Frame) end
"""

PRELUDE = r"""
local function boot()
    IN_COMBAT, READABLE, SPELL_CALLS, SPELL_INFO, SPELL_RAW, CREATED = false, true, 0, {}, {}, {}
    GameTooltip.throws, GameTooltip.auraThrows = nil, nil
    GameTooltip:Reset()
    FS = { Theme = {} }
    FS.IsSecret = isSecretValue
    FS.AurasReadable = function() return READABLE and not IN_COMBAT end
    C_Spell = { GetSpellInfo = function(name)
        SPELL_CALLS = SPELL_CALLS + 1
        if isSecretValue(name) then error("secret name reached the API") end
        if SPELL_RAW[name] ~= nil then return SPELL_RAW[name] end
        local id = SPELL_INFO[name]
        if id == nil then return nil end
        return { name = name, spellID = id }
    end }
    local fn = assert(loadstring(HELPERS_SRC, "@Core/FrameHelpers.lua"))
    fn("forever-stuwave", FS)
    return FS.FrameHelpers
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


case("hover_only_is_motion_only_and_missing_calls_leave_no_mouse")(r"""
local H = boot()
local f = newFrame()
H.HoverOnly(f)
check(f.motion == true and f.click == false, "motion on, clicks off")
local g = newFrame()
g.SetMouseMotionEnabled = false           -- a client without the call
H.HoverOnly(g)
check(g.motion == nil and g.click == nil, "no mouse state at all when either call is missing")
""")

case("set_tip_spell_stores_only_plain_valid_values")(r"""
local H = boot()
local f = newFrame()
H.SetTipSpell(f, 133, "Fireball")
check(f.fsSpellID == 133 and f.fsName == "Fireball", "valid pair is written")
H.SetTipSpell(f, SECRET_NUM, SECRET_STR)
check(f.fsSpellID == nil and f.fsName == nil, "secret id and name clear both fields, never stored")
H.SetTipSpell(f, 133, "Fireball")
for _, bad in ipairs({ 0, -4, "133", {} }) do
    H.SetTipSpell(f, bad, "Fireball")
    check(f.fsSpellID == nil, "invalid id cleared: " .. type(bad))
    H.SetTipSpell(f, 133, "Fireball")
end
H.SetTipSpell(f, nil, "")
check(f.fsSpellID == nil and f.fsName == nil, "nil id and empty name clear")
""")

case("spell_id_for_name_caches_hits_and_misses")(r"""
local H = boot()
SPELL_INFO["Fireball"] = 133
check(H.SpellIDForName("Fireball") == 133 and H.SpellIDForName("Fireball") == 133, "resolves")
check(SPELL_CALLS == 1, "a hit is cached, got " .. SPELL_CALLS .. " calls")
check(H.SpellIDForName("Nope") == nil and H.SpellIDForName("Nope") == nil, "miss is nil")
check(SPELL_CALLS == 2, "a miss out of combat is cached, got " .. SPELL_CALLS)
IN_COMBAT = true
H.SpellIDForName("Later"); H.SpellIDForName("Later")
check(SPELL_CALLS == 3, "a miss in combat is looked up once per combat, got " .. SPELL_CALLS)
check(H.SpellIDForName(SECRET_STR) == nil and H.SpellIDForName(nil) == nil and H.SpellIDForName("") == nil, "bad names are nil")
check(SPELL_CALLS == 3, "bad names never reach the API")
C_Spell = nil
GetSpellInfo = function(name) SPELL_CALLS = SPELL_CALLS + 1; return name, nil, nil, 0, 0, 0, 77 end
check(H.SpellIDForName("Global") == 77, "falls back to the global GetSpellInfo when C_Spell is missing")
""")

case("attach_installs_once_and_clicks_opt_keeps_the_mouse_alone")(r"""
local H = boot()
local f = newFrame()
H.AttachSpellTooltip(f, {})
H.AttachSpellTooltip(f, {})
check(#f.hooks.OnEnter == 1 and #f.hooks.OnLeave == 1 and #f.hooks.OnHide == 1, "one hook per script")
check(f.motion == true and f.click == false, "hover only by default")
local g = newFrame()
H.AttachSpellTooltip(g, { clicks = true })
check(g.motion == nil and g.click == nil, "clicks=true leaves the mouse to the caller")
""")

case("tooltip_prefers_spell_id_and_falls_back_to_the_cached_name")(r"""
local H = boot()
local f = newFrame()
H.AttachSpellTooltip(f, { anchor = "ANCHOR_RIGHT" })
H.SetTipSpell(f, 133, "Fireball")
f:Run("OnEnter")
check(GameTooltip.owner == f and GameTooltip.anchor == "ANCHOR_RIGHT" and GameTooltip.spellID == 133, "spell id tooltip")
f:Run("OnLeave")
GameTooltip.throws = true                  -- SetSpellByID refuses
IN_COMBAT = true
f:Run("OnEnter")
check(GameTooltip.text == "Fireball" and GameTooltip.shown, "a throwing SetSpellByID falls back to the name")
check(GameTooltip.lines[1] == "Details unavailable in combat.", "grey combat line in combat")
f:Run("OnLeave")
GameTooltip.throws = nil
IN_COMBAT = false
GameTooltip.SetSpellByID = nil             -- a client without the call
f:Run("OnEnter")
check(GameTooltip.text == "Fireball" and #GameTooltip.lines == 0, "missing SetSpellByID falls back to the name, no combat line out of combat")
H.SetTipSpell(f, nil, nil)
f:Run("OnLeave"); f:Run("OnEnter")
check(not GameTooltip.shown, "nothing cached means hidden")
""")

case("aura_frame_uses_the_live_slot_when_readable_and_the_spell_id_in_combat")(r"""
local H = boot()
local f = newFrame()
f.unit, f.auraIndex, f.filter = "player", 3, "HELPFUL"
H.AttachSpellTooltip(f, {})
H.SetTipSpell(f, 133, "Fireball")
f:Run("OnEnter")
check(GameTooltip.aura == "player:3:HELPFUL" and GameTooltip.spellID == nil, "live slot out of combat")
f:Run("OnLeave")
IN_COMBAT = true
f:Run("OnEnter")
check(GameTooltip.spellID == 133 and GameTooltip.aura == nil, "spell id in combat")
""")

case("hide_or_leave_while_hovered_leaves_no_stranded_tooltip")(r"""
local H = boot()
local f, other = newFrame(), newFrame()
H.AttachSpellTooltip(f, {})
H.SetTipSpell(f, 133, "Fireball")
f:Run("OnEnter")
check(f.fsHover and GameTooltip.shown, "setup")
f:Hide()
check(f.fsHover == nil and not GameTooltip.shown, "hide clears hover and the tooltip")
f:Run("OnEnter")
GameTooltip:SetOwner(other, "ANCHOR_TOP"); GameTooltip:Show()   -- someone else took the tooltip
f:Run("OnLeave")
check(GameTooltip.shown and GameTooltip.owner == other, "a tooltip owned by another frame is left alone")
""")

case("gate_false_shows_nothing")(r"""
local H = boot()
local f = newFrame()
local open = false
H.AttachSpellTooltip(f, { gate = function() return open end })
H.SetTipSpell(f, 133, "Fireball")
f:Run("OnEnter")
check(not GameTooltip.shown and GameTooltip.owner == nil, "gate false: no owner, nothing shown")
open = true
f:Run("OnEnter")
check(GameTooltip.spellID == 133, "gate true: shown")
open = false
H.RefreshSpellTooltip(f)
check(not GameTooltip.shown, "the gate closing takes down the tooltip it owns")
""")

case("set_tip_spell_refreshes_an_open_tooltip_only_when_changed")(r"""
local H = boot()
local f = newFrame()
H.AttachSpellTooltip(f, {})
H.SetTipSpell(f, 133, "Fireball")
H.SetTipSpell(f, 134, "Frostbolt")
check(not GameTooltip.shown, "not hovered: no tooltip")
f:Run("OnEnter")
GameTooltip.spellID = nil
H.SetTipSpell(f, 133, "Fireball")
check(GameTooltip.spellID == 133, "hovered and changed: refreshed")
GameTooltip.spellID = nil
H.SetTipSpell(f, 133, "Fireball")
check(GameTooltip.spellID == nil, "hovered and unchanged: left alone")
""")

case("set_tip_spell_secret_id_or_name_alone_clears_only_that_field")(r"""
local H = boot()
local f = newFrame()
H.SetTipSpell(f, 133, "Fireball")
H.SetTipSpell(f, SECRET_NUM, "Fireball")
check(f.fsSpellID == nil and f.fsName == "Fireball", "secret id clears the id only")
H.SetTipSpell(f, 133, SECRET_STR)
check(f.fsSpellID == 133 and f.fsName == nil, "secret name clears the name only")
""")

case("set_tip_spell_over_a_secret_old_name_counts_as_changed")(r"""
local H = boot()
local f = newFrame()
H.AttachSpellTooltip(f, {})
H.SetTipSpell(f, 133, "Fireball")
f:Run("OnEnter")
f.fsName = SECRET_STR                      -- written by other code
GameTooltip.spellID = nil
H.SetTipSpell(f, 133, "Fireball")          -- must not compare the secret, must redraw
check(f.fsName == "Fireball" and GameTooltip.spellID == 133, "secret old name is replaced and the open tooltip redrawn")
""")

case("spell_id_for_name_never_touches_a_secret_result")(r"""
local H = boot()
SPELL_RAW["Whole"] = SECRET_INFO
check(H.SpellIDForName("Whole") == nil, "a secret info table is a miss, never indexed")
SPELL_RAW["Field"] = { spellID = SECRET_NUM }
check(H.SpellIDForName("Field") == nil, "a secret spellID is a miss, never compared")
SPELL_RAW["Bad"] = { spellID = -1 }
check(H.SpellIDForName("Bad") == nil, "a non-positive spellID is a miss")
""")

case("spells_changed_wipes_hits_and_misses_out_of_combat")(r"""
local H = boot()
SPELL_INFO["Rank"] = 100
check(H.SpellIDForName("Rank") == 100 and H.SpellIDForName("Later") == nil, "setup: a hit and a miss cached")
local e0 = H.SpellCacheEpoch()
SPELL_INFO["Rank"] = 200                   -- a new rank trained
SPELL_INFO["Later"] = 999                  -- learned since
check(H.SpellIDForName("Rank") == 100 and H.SpellIDForName("Later") == nil, "both still cached before the event")
fireEvent("SPELLS_CHANGED")
check(H.SpellIDForName("Rank") == 200, "the hit follows the new rank")
check(H.SpellIDForName("Later") == 999, "the miss is retried")
check(H.SpellCacheEpoch() ~= e0, "the epoch moves with the wipe")
""")

case("spells_changed_in_combat_wipes_at_regen_enabled")(r"""
local H = boot()
SPELL_INFO["Rank"] = 100
check(H.SpellIDForName("Rank") == 100, "setup")
IN_COMBAT = true
SPELL_INFO["Rank"] = 200
fireEvent("SPELLS_CHANGED")
check(H.SpellIDForName("Rank") == 100, "no wipe in combat: the hit stays")
IN_COMBAT = false
fireEvent("PLAYER_REGEN_ENABLED")
check(H.SpellIDForName("Rank") == 200, "wiped when combat ends")
local calls = SPELL_CALLS
fireEvent("PLAYER_REGEN_ENABLED")
check(H.SpellIDForName("Rank") == 200 and SPELL_CALLS == calls, "a second regen with nothing dirty wipes nothing")
""")

case("combat_miss_is_looked_up_once_per_combat")(r"""
local H = boot()
IN_COMBAT = true
for _ = 1, 5 do check(H.SpellIDForName("Later") == nil, "miss") end
check(SPELL_CALLS == 1, "one lookup for five renders, got " .. SPELL_CALLS)
SPELL_INFO["Later"] = 999
check(H.SpellIDForName("Later") == nil and SPELL_CALLS == 1, "still not retried mid combat")
IN_COMBAT = false
fireEvent("PLAYER_REGEN_ENABLED")
check(H.SpellIDForName("Later") == 999, "retried after combat")
IN_COMBAT = true
check(H.SpellIDForName("Gone") == nil, "setup: another miss")
local calls = SPELL_CALLS
SPELL_INFO["Gone"] = 5
fireEvent("SPELLS_CHANGED")
check(H.SpellIDForName("Gone") == 5 and SPELL_CALLS == calls + 1, "SPELLS_CHANGED clears the combat misses")
""")

case("release_spell_tip_is_public_and_gated_release_follows_the_gate")(r"""
local H = boot()
local on = true
local f, g = newFrame(), newFrame()
H.AttachSpellTooltip(f, { gate = function() return on end })
H.AttachSpellTooltip(g, {})
H.SetTipSpell(f, 133, "Fireball"); H.SetTipSpell(g, 134, "Frostbolt")
f:Run("OnEnter")
check(GameTooltip.shown and GameTooltip.owner == f, "setup: tip up")
H.ReleaseGatedTips()
check(GameTooltip.shown and f.fsHover, "gate still open: nothing released")
on = false
H.ReleaseGatedTips()
check(not GameTooltip.shown and f.fsHover == nil, "gate closed: tip down, hover cleared")
g:Run("OnEnter")
H.ReleaseGatedTips()
check(GameTooltip.shown and GameTooltip.owner == g, "an ungated tip is left alone")
local other = newFrame()
GameTooltip:SetOwner(other, "ANCHOR_TOP"); GameTooltip:Show()
H.ReleaseGatedTips()
check(GameTooltip.shown and GameTooltip.owner == other, "a tooltip owned by an unrelated frame is left alone")
on = true
f:Run("OnEnter")
check(GameTooltip.shown and GameTooltip.owner == f, "setup: f owns the tip")
H.ReleaseSpellTip(g)
check(GameTooltip.shown and GameTooltip.owner == f, "releasing a frame that is not the owner leaves the owner's tip")
H.ReleaseSpellTip(f)
check(not GameTooltip.shown and f.fsHover == nil, "ReleaseSpellTip hides the owner's tip")
""")

case("stale_aura_slot_falls_through_to_the_cached_spell")(r"""
local H = boot()
local f = newFrame()
f.unit, f.auraIndex, f.filter = "player", 3, "HELPFUL"
H.AttachSpellTooltip(f, {})
H.SetTipSpell(f, 133, "Fireball")
GameTooltip.auraThrows = true              -- the slot no longer holds this aura
f:Run("OnEnter")
check(GameTooltip.spellID == 133 and GameTooltip.shown, "falls through to the cached spell id")
f:Run("OnLeave")
H.SetTipSpell(f, nil, "Fireball")
f:Run("OnEnter")
check(GameTooltip.text == "Fireball" and GameTooltip.shown, "then to the cached name")
f:Run("OnLeave")
H.SetTipSpell(f, nil, nil)
f:Run("OnEnter")
check(not GameTooltip.shown, "nothing cached: hidden")
""")

case("refresh_leaves_a_tooltip_owned_by_another_frame_alone")(r"""
local H = boot()
local f, other = newFrame(), newFrame()
H.AttachSpellTooltip(f, {})
H.SetTipSpell(f, 133, "Fireball")
f:Run("OnEnter")
GameTooltip:SetOwner(other, "ANCHOR_TOP"); GameTooltip:Show()
H.SetTipSpell(f, 134, "Frostbolt")         -- changed and hovered, but not the owner
check(GameTooltip.owner == other and GameTooltip.spellID == nil, "no redraw over another owner")
GameTooltip.IsOwned = nil                  -- a client without IsOwned falls back to GetOwner
H.SetTipSpell(f, 135, "Pyroblast")
check(GameTooltip.owner == other and GameTooltip.spellID == nil, "GetOwner fallback agrees")
f:Run("OnLeave")
check(GameTooltip.shown and GameTooltip.owner == other, "leave leaves it alone too")
""")

case("show_aura_tooltip_combat_branch_uses_the_cached_spell_id")(r"""
local H = boot()
local f = newFrame()
f.auraIndex, f.unit, f.filter, f.fsName, f.fsSpellID = 2, "player", "HELPFUL", "Fireball", 133
IN_COMBAT = true
H.ShowAuraTooltip(f)
check(GameTooltip.spellID == 133, "spell id used in combat")
f.fsSpellID = nil
GameTooltip:Reset()
H.ShowAuraTooltip(f)
check(GameTooltip.text == "Fireball" and GameTooltip.lines[1] == "Details unavailable in combat.", "name-only without an id")
f.fsSpellID = 133; GameTooltip:Reset(); GameTooltip.throws = true
H.ShowAuraTooltip(f)
check(GameTooltip.text == "Fireball", "a refused SetSpellByID falls back to the name")
""")


def run_case(name: str, body: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().HELPERS_SRC = HELPERS.read_text(encoding="utf-8")
    try:
        lua.execute(PRELUDE + "\n" + body)
    except LuaError as e:
        return str(e)
    return None


def main() -> int:
    failures = 0
    for name, body in CASES:
        try:
            err = run_case(name, body)
        except LuaError as e:
            err = f"harness error: {e}"
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
