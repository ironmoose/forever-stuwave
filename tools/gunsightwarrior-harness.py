#!/usr/bin/env python3
"""Runs the real WarriorShouts.lua and GunsightWarrior.lua headless against a mock client.

The Warrior Class Module draws the design mockup "Warrior Roaring Helm, rune ring" (2026-11-07): a Battle Shout ring and a
Demoralizing Shout ring, each a helm in the middle and 8 orbiting rune tiles. These checks pin:

  * the data: an out of combat aura read is the truth, a cast in combat stamps the ledger (shown with "~"), Demoralizing Shout
    is always the ledger, a secret spell id is ignored, a shout runs out on Tick;
  * the rune count ceil(remaining / duration * 8), the amber last rune, the dark ones, the gone look, a shout not learned hidden;
  * the helm frame for each state: the roar's beard whip on a Battle Shout cast, one still frame while it breathes, growl on a Demoralizing Shout cast, cold
    when gone, hidden while Demoralizing Shout is not learned;
  * the labels (3m, ~2m, SHOUT, ~30s, amber on the last rune);
  * onHide stops the ticker and the subscription, onShow brings both back;
  * the baked textures exist and the atlas frame order matches the generator;
  * the strike window lane (design mockup "Warrior Overpower Cue", 2026-11-12, variant A without the stance chip) and its data,
    WarriorWindows.lua, for Overpower, Revenge and Victory Rush: hidden with no window; opened by an overlay glow or by a plain
    usable flip, never by a secret value; the drain, the amber last 1.5 s and the tick mark; the pink cast flash; the amber
    dotted outline on expiry; the health gate; the least-time-left rule when two windows are open; an unknown spell is never
    shown. `--png PREFIX` also renders the lane's frozen states (and the helms behind it) for a look.

    python3 tools/gunsightwarrior-harness.py [--png debug/warrior-lane]

Exit 0 = every check passed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ROOT = Path(__file__).resolve().parent.parent
SHOUTS = (ROOT / "forever-stuwave/Modules/CombatHud/WarriorShouts.lua").read_text(encoding="utf-8")
WINDOWS = (ROOT / "forever-stuwave/Modules/CombatHud/WarriorWindows.lua").read_text(encoding="utf-8")
TOC = (ROOT / "forever-stuwave/forever-stuwave.toc").read_text(encoding="utf-8")
MODULE = (ROOT / "forever-stuwave/Modules/CombatHud/GunsightWarrior.lua").read_text(encoding="utf-8")
GENERATOR = (ROOT / "tools/assets/generate_warrior_helm.py").read_text(encoding="utf-8")
MEDIA = ROOT / "forever-stuwave/Media/Textures"

MOCK = r"""
local Obj = {}
Obj.__index = function(t, k)
    local v = rawget(Obj, k)
    if v ~= nil then return v end
    if type(k) == "string" and k:match("^%u") then return function() end end
end
function New(kind) return setmetatable({ kind = kind, shown = true }, Obj) end
function Obj:SetPoint(p, rel, rp, x, y) self.nw = (self.nw or 0) + 1; self.pt = { p, rel, rp, x or 0, y or 0 } end
function Obj:ClearAllPoints() self.pt = nil end
function Obj:SetSize(w, h) self.nw = (self.nw or 0) + 1; self.w, self.h = w, h end
function Obj:Show() self.nw = (self.nw or 0) + 1; self.shown = true end
function Obj:Hide() self.nw = (self.nw or 0) + 1; self.shown = false end
function Obj:IsShown() return self.shown end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:GetScript(n) return self.scripts and self.scripts[n] end
function Obj:RegisterEvent(e) self.events = self.events or {}; self.events[e] = true end
function Obj:RegisterUnitEvent(e) self.events = self.events or {}; self.events[e] = true end
function Obj:SetTexture(p) self.tex = p end
function Obj:SetTexCoord(l, r, t, b) self.tc = { l, r, t, b } end
function Obj:SetVertexColor(r, g, b, a) self.nw = (self.nw or 0) + 1; self.color = { r, g, b, a } end
function Obj:SetText(t) self.nw = (self.nw or 0) + 1; self.text = t end
function Obj:SetTextColor(r, g, b, a) self.nw = (self.nw or 0) + 1; self.tcolor = { r, g, b, a } end
function Obj:CreateTexture() local t = New("Texture"); __textures[#__textures + 1] = t; return t end
function Obj:CreateFontString() local f = New("FontString"); __fonts[#__fonts + 1] = f; return f end
__textures, __fonts, __frames = {}, {}, {}
function CreateFrame(kind, name, parent)
    local f = New("Frame"); f.name = name; f.parent = parent
    __frames[#__frames + 1] = f
    return f
end
__now = 1000
function GetTime() return __now end
C_Timer = { After = function(_, fn) __after = fn end }
__combat = false
function InCombatLockdown() return __combat end
__known = { [25289] = true }                     -- Battle Shout only; Demoralizing Shout not learned
__resolve = {}                                   -- spell name -> the id the client resolves it to
function IsPlayerSpell(id) return __known[id] == true end
__names = {}
for _, id in ipairs({ 25289, 11551, 11550, 11549, 6192, 5242, 6673 }) do __names[id] = "Battle Shout" end
for _, id in ipairs({ 11556, 11555, 11554, 6190, 1160 }) do __names[id] = "Demoralizing Shout" end
for _, id in ipairs({ 11585, 11584, 7887, 7384 }) do __names[id] = "Overpower" end
for _, id in ipairs({ 30357, 25269, 25288, 11601, 11600, 7379, 6574, 6572 }) do __names[id] = "Revenge" end
__names[34428] = "Victory Rush"
__names[55555] = "Overpower"                    -- a rank the id table does not list: known by NAME only
__names[133] = "Fireball"
__aura = nil                                     -- { expirationTime =, duration = } or nil
__usable = { Overpower = false, Revenge = false, ["Victory Rush"] = false }     -- by spell name: true, false or SECRET
__cd = {}                                        -- by spell name (61304 = "GCD"): { isActive =, isOnGCD = } or nil
__names[61304] = "GCD"
C_Spell = {
    GetSpellCooldown = function(spell)
        if type(spell) == "number" then spell = __names[spell] end
        return __cd[spell] or { isActive = false, isEnabled = true, startTime = 0, duration = 0 }
    end,
    GetSpellName = function(id) return __names[id] end,
    IsSpellUsable = function(spell)
        if type(spell) == "number" then spell = __names[spell] end
        return __usable[spell], false
    end,
}
__hp, __hpmax, __hppct = 100, 100, nil           -- player health; __hppct feeds UnitHealthPercent when set
function UnitHealth() return __hp end
function UnitHealthMax() return __hpmax end
function UnitHealthPercent() return __hppct end
C_UnitAuras = {
    GetPlayerAuraBySpellID = function(id) if id == 25289 then return __aura end return nil end,
}
local function Deny() error("a secret value was used") end
SECRET = setmetatable({}, { __tostring = function() return "secret" end, __lt = Deny, __le = Deny, __add = Deny, __sub = Deny,
    __mul = Deny, __div = Deny, __concat = Deny, __len = Deny, __index = Deny, __call = Deny })
__cfg = {}
local Areas = { specs = {} }
function Areas.RegisterModule(id, spec) Areas.specs[#Areas.specs + 1] = { id = id, spec = spec }; return true end
FS = {
    IsSecret = function(v) return v == SECRET end,
    AurasReadable = function() return not __combat end,
    Gunsight = { ui = function(px) return px end, Point = function(f, p, x, y) f.pt = { p, "root", "CENTER", x, y } end, G = {} },
    GunsightAreas = Areas,
    Theme = {
        ApplyMono = function(fs, size, cur) fs.size = size end,
        COLOR_POWER = { 0.133, 0.878, 1, 1 }, COLOR_AMBER = { 1, 0.7137, 0.2824, 1 }, COLOR_HEALTH = { 1, 0.180, 0.592, 1 },
        COLOR_BORDER = { 0.659, 0.333, 0.969, 1 }, COLOR_BUTTON_INK = { 0.090, 0.047, 0.165, 1 },
    },
    FrameHelpers = {
        IsKnownSpellId = function(id) return __known[id] == true end,
        ResolveSpell = function(name) return __resolve[name] end,
        RegisterEvent = function(f, e) f.events = f.events or {}; f.events[e] = true end,
        RegisterEvents = function(f, list) f.events = f.events or {}; for _, e in ipairs(list) do f.events[e] = true end end,
    },
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m end,
}
assert(loadstring(SHOUTS_SRC, "@WarriorShouts.lua"))("forever-stuwave", FS)
assert(loadstring(WINDOWS_SRC, "@WarriorWindows.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@GunsightWarrior.lua"))("forever-stuwave", FS)
Shouts, W, Win = FS.WarriorShouts, FS.GunsightWarrior, FS.WarriorWindows
SPEC = Areas.specs[1].spec
HOST = New("Frame")
function Build()
    local m = SPEC.build(HOST)
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    SPEC.onShow("lower")
    return m
end
function Tick(dt) __now = __now + dt; W.frame.scripts.OnUpdate(W.frame, 1) end
function Cast(id) Shouts._OnCast(id) end
function Ring(k) return W.rings[k] end
function Row(t) return t.tc and math.floor(t.tc[3] * 256 / 28 + 0.5) end
function HelmFrame(k)
    local tc = Ring(k).helm.tc
    return math.floor(tc[1] * 4 + 0.5) + 4 * math.floor(tc[3] * 4 + 0.5)
end
function Rows(k) local o = {} for i = 1, 8 do o[i] = Row(Ring(k).runes[i]) end return table.concat(o, "") end

-- the strike window lane
function Lane() return W.lane end
function WinFrame()
    for _, f in ipairs(__frames) do
        if f.events and f.events.SPELL_UPDATE_USABLE then return f end
    end
end
function Fire(event, ...) local f = WinFrame(); f.scripts.OnEvent(f, event, ...) end
function Glow(id, shown) Fire(shown and "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW" or "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE", id) end
function CastEv(id) Fire("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", id) end
-- the poll lands on the next frame, so run the queued timer as that frame
function UsableEv() __after = nil; Fire("SPELL_UPDATE_USABLE"); local f = __after; __after = nil; if f then f() end end
function Open(k) return Win.Get(k).open end
function Shown(list) for _, t in ipairs(list) do if t.shown then return true end end return false end
function AllShown(list) for _, t in ipairs(list) do if not t.shown then return false end end return true end
function LaneUp() local L = Lane(); return Shown(L.windowParts) or Shown(L.castParts) or Shown(L.dots) or L.label.shown == true end
function Writes() local n = 0 local L = Lane()
    for _, list in ipairs({ L.windowParts, L.castParts, L.dots, { L.label } }) do for _, t in ipairs(list) do n = n + (t.nw or 0) end end
    return n end
function Close3(a, b) return math.abs(a - b) < 1e-6 end
function SameColor(c, tok) return Close3(c[1], tok[1]) and Close3(c[2], tok[2]) and Close3(c[3], tok[3]) end
function Px(v) return v * W.C.SPX end                  -- sprite px -> the mock's UI units
function LogClean() for k in pairs(__logged or {}) do if k:find("^warriorwindows") or k:find("^gunsightwarrior") then return false, k end end return true end
-- Dump: every drawn region as a flat op list, for the PNG renderer
function Dump()
    local ops, mod = {}, W.frame
    for _, t in ipairs(__textures) do
        if t.shown and t.pt and t.w and t.h then
            ops[#ops + 1] = { kind = "tex", l = t.pt[4], t = -t.pt[5], w = t.w, h = t.h, color = t.color, tex = t.tex, tc = t.tc,
                alpha = t.fsA2 }
        end
    end
    for _, f in ipairs(__fonts) do
        if f.shown and f.pt and f.text and f.text ~= "" then
            ops[#ops + 1] = { kind = "text", cx = f.pt[4], cy = -f.pt[5], text = f.text, size = f.size, color = f.tcolor }
        end
    end
    return ops
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


case("registers_the_class_module_for_warriors_only", """
    assert(SPEC and SPEC.classes[1] == "WARRIOR" and #SPEC.classes == 1)
    local m = Build()
    assert(m and m.name == "ForeverSTUwaveGunsightWarrior")
""")

case("an_out_of_combat_aura_read_is_the_truth", """
    __aura = { expirationTime = __now + 180, duration = 180 }
    Build()
    local st = Shouts.Get("battle")
    assert(st.up and st.source == "aura" and st.duration == 180)
    assert(Shouts.Lit("battle", __now) == 8)
    assert(Shouts.Lit("battle", __now + 50) == 6, Shouts.Lit("battle", __now + 50))
    assert(Shouts.Lit("battle", __now + 179) == 1)
    Tick(0.05)
    assert(Rows("battle") == "00000000", Rows("battle"))
    assert(Ring("battle").label.text == "3m", Ring("battle").label.text)
""")

case("a_cast_in_combat_stamps_the_ledger_and_reads_as_an_estimate", """
    Build()
    __combat = true
    Cast(25289)
    local st = Shouts.Get("battle")
    assert(st.up and st.source == "cast" and st.expires == __now + 180)
    Tick(60)
    assert(Ring("battle").label.text == "~2m", Ring("battle").label.text)
    assert(Rows("battle") == "00000033", Rows("battle"))
""")

case("a_secret_or_foreign_spell_id_is_ignored", """
    Build()
    Cast(SECRET)
    Cast(133)
    assert(not Shouts.Get("battle").up and not Shouts.Get("demo").up)
""")

case("the_last_rune_is_amber_and_the_label_turns_amber", """
    __aura = { expirationTime = __now + 14, duration = 180 }
    Build()
    Tick(0.05)
    assert(Rows("battle") == "23333333", Rows("battle"))
    local c = Ring("battle").label.tcolor
    assert(c[1] == 1 and c[2] > 0.7 and c[3] < 0.3, "the last rune's label is amber")
""")

case("gone_is_dashed_runes_a_cold_helm_and_no_label", """
    Build()
    Tick(0.05)
    assert(Rows("battle") == "44444444", Rows("battle"))
    local f = HelmFrame("battle")
    assert(f == W.FRAME.cold or f == W.FRAME.coldFlick, f)
    assert(Ring("battle").label.text == "", "no label when gone")
""")

case("gone_is_calm_on_a_friendly_target_and_nudges_in_combat_or_on_an_attackable_one", """
    __canAttack = false
    UnitCanAttack = function(a, b) return __canAttack end
    Build()
    local p = Ring("battle")
    local frames, alphas = {}, {}
    for i = 1, 45 do
        Tick(1 / 30)
        frames[HelmFrame("battle")] = true
        alphas[p.runes[1].fsA2] = true
    end
    assert(frames[W.FRAME.cold] and not frames[W.FRAME.coldFlick], "calm: dark eyes, no blink")
    local n = 0
    for _ in pairs(alphas) do n = n + 1 end
    assert(n == 1 and alphas[W.C.CALM_A], "calm: the dashes hold still and dim")
    assert(Rows("battle") == "44444444", "calm: the plain dash row")
    assert(not p.halo.shown, "calm: no halo")
    __canAttack = true
    alphas = {}
    for i = 1, 45 do
        Tick(1 / 30)
        assert(HelmFrame("battle") == W.FRAME.coldFlick, "nudge: amber eyes, steady")
        alphas[p.runes[1].fsA2] = true
    end
    n = 0
    for _ in pairs(alphas) do n = n + 1 end
    assert(n >= 4, "nudge: the dashes breathe, saw " .. n .. " alphas")
    assert(Rows("battle") == "55555555", "nudge: the glowing dash row, got " .. Rows("battle"))
    assert(p.halo.shown, "nudge: the halo shows")
    __canAttack = false
    __combat = true
    Tick(1 / 30)
    assert(HelmFrame("battle") == W.FRAME.coldFlick, "in combat it nudges too")
    __combat = false
    UnitCanAttack = function() return __secret end
    __secret = setmetatable({}, { __secret = true })
    Tick(1 / 30)
    assert(HelmFrame("battle") == W.FRAME.cold, "a secret or odd answer is calm")
""")

case("a_shout_runs_out_on_tick", """
    __aura = { expirationTime = __now + 2, duration = 180 }
    Build()
    __aura = nil
    Tick(3)
    assert(not Shouts.Get("battle").up)
    assert(Ring("battle").label.text == "", "no label when gone")
""")

case("a_battle_shout_cast_roars_then_breathes", """
    __aura = { expirationTime = __now + 180, duration = 180 }
    Build()
    Cast(25289)
    Tick(0.05)
    local f = HelmFrame("battle")
    assert(f >= W.FRAME.roar1 and f <= W.FRAME.roar4, "roar frame, got " .. f)
    local poses = {}
    for i = 1, 8 do Tick(1 / 30); poses[HelmFrame("battle")] = true end
    local n = 0
    for _ in pairs(poses) do n = n + 1 end
    assert(n >= 3, "the beard whips through its poses while it roars, saw " .. n)
    assert(Ring("battle").lines[1].shown, "scream lines show while it roars")
    -- after the roar, the breath: one still frame, the helm lifting on the inhale and puffing on the exhale
    Tick(1.3)
    assert(not Ring("battle").lines[1].shown, "scream lines go after the roar")
    local ys, sawPuff = {}, false
    for i = 1, 60 do
        Tick(1 / 30)
        assert(HelmFrame("battle") == W.FRAME.hot, "the beard holds still between shouts, got " .. HelmFrame("battle"))
        ys[Ring("battle").helm.pt[5]] = true
        if Ring("battle").puffs[1].shown then sawPuff = true end
    end
    local n = 0
    for _ in pairs(ys) do n = n + 1 end
    assert(n == 2 and sawPuff, "the helm breathes: it lifts and puffs")
""")

case("demoralizing_shout_not_learned_is_not_drawn", """
    Build()
    Tick(0.05)
    for i = 1, 8 do assert(Ring("demo").runes[i].shown == false, "rune " .. i .. " hidden") end
    assert(Ring("demo").helm.shown == false)
    assert(Ring("demo").label.text == "")
    assert(not Ring("demo").halo.shown, "no nudge for a shout not learned")
    __known[11556] = true
    Build()
    Tick(0.05)
    for i = 1, 8 do assert(Ring("demo").runes[i].shown ~= false, "rune " .. i .. " shows once learned") end
    assert(Ring("demo").helm.shown)
""")

case("a_demoralizing_shout_cast_growls_and_reads_as_an_estimate", """
    __known[11556] = true
    Build()
    Cast(11556)
    Tick(0.4)
    local g = HelmFrame("demo")
    assert(g >= W.FRAME.growl1 and g <= W.FRAME.growl4, g)
    local rip = 0
    for _, t in ipairs(Ring("demo").ripple) do if t.shown then rip = rip + 1 end end
    assert(rip > 0, "the ripple of dread shows during the growl")
    assert(Ring("demo").label.text == "~30s", Ring("demo").label.text)
    Tick(1.5)
    assert(HelmFrame("demo") < W.FRAME.growl1 or HelmFrame("demo") > W.FRAME.growl4)
    for _, t in ipairs(Ring("demo").ripple) do assert(not t.shown, "the ripple ends") end
""")

case("on_hide_stops_the_ticker_and_the_subscription_on_show_restarts", """
    Build()
    assert(W.frame.scripts.OnUpdate, "ticking while shown")
    SPEC.onHide("lower")
    assert(W.frame.scripts.OnUpdate == nil, "the OnUpdate stops on hide")
    -- a cast while hidden is still recorded
    __combat = true
    Cast(25289)
    assert(Shouts.Get("battle").up)
    SPEC.onShow("lower")
    assert(W.frame.scripts.OnUpdate, "the OnUpdate is back on show")
""")

case("the_orbit_moves_the_runes", """
    __aura = { expirationTime = __now + 180, duration = 180 }
    Build()
    Tick(0.05)
    local p = Ring("battle").runes[1].pt
    local x1, y1 = p[4], p[5]
    Tick(3)
    p = Ring("battle").runes[1].pt
    assert(p[4] ~= x1 or p[5] ~= y1, "rune 1 moved along the orbit")
""")


# ---------------------------------------------------------------------------------------------------------------------------
# The strike window lane (WarriorWindows.lua + the lane in GunsightWarrior.lua)
# ---------------------------------------------------------------------------------------------------------------------------

case("the_lane_is_hidden_when_no_window_is_open", """
    __known[7384] = true
    Build()
    for i = 1, 30 do Tick(0.1) end
    assert(not LaneUp(), "no window, no lane")
    assert(Win.Urgent(__now) == nil)
    assert(Win.Get("overpower").known and not Open("overpower"))
""")

case("the_lane_matches_the_mockups_geometry_and_has_no_other_text", """
    local LN = W.C.LANE
    assert(LN.X == 22 and LN.Y == 80 and LN.W == 106 and LN.H == 8)
    assert(LN.X * 2 + LN.W == W.C.SW, "the bar is centred on the canvas")
    assert(LN.LABEL_BASE * W.C.SPX + W.C.DROP <= 128, "the label stays inside the 128 px area")
    __known[7384] = true
    Build()
    assert(#__fonts == 3, "two ring labels and the lane's one label, no chip, got " .. #__fonts)
    local L = Lane()
    assert(Close3(L.label.pt[4], Px(LN.X + LN.W / 2)), "the label is centred under the bar")
    local set, n = {}, 0
    local function add(x, y) local k = x * 1000 + y if not set[k] then set[k] = true n = n + 1 end end
    for i = 0, LN.W - 1, 2 do add(LN.X + i, LN.Y); add(LN.X + i, LN.Y + LN.H - 1) end
    for j = 0, LN.H - 1, 2 do add(LN.X, LN.Y + j); add(LN.X + LN.W - 1, LN.Y + j) end
    assert(#L.dots == n, "the dashed outline is the mockup's pixels, got " .. #L.dots .. " want " .. n)
""")

case("an_overlay_glow_opens_the_lane_and_it_drains_toward_the_left", """
    __known[7384] = true
    Build()
    Glow(7384, true)
    local st = Win.Get("overpower")
    assert(st.open and st.source == "glow" and st.length == 5 and st.expires == __now + 5)
    Tick(0.2)
    local L = Lane()
    assert(L.bg.shown and L.fill.shown and L.mark.shown and L.label.shown)
    assert(L.label.text == "OVERPOWER", L.label.text)
    local left = L.bg.pt[4]
    assert(Close3(L.bg.w, Px(106)) and Close3(left, Px(22)), "the full box")
    assert(Close3(left, Px(W.C.SW) - (left + L.bg.w)), "centred: equal margins")
    local w1 = L.fill.w
    assert(Close3(w1, Px(100)), "4.8 of 5 s is 100 of 104 inner px, got " .. w1 / W.C.SPX)
    Tick(2)
    assert(Close3(L.fill.w, Px(58)), "2.8 of 5 s is 58 inner px, got " .. L.fill.w / W.C.SPX)
    assert(Close3(L.fill.pt[4], Px(23)), "the fill stays anchored at the left, so it shrinks toward the left")
    assert(SameColor(L.fill.color, FS.Theme.COLOR_POWER), "cyan fill from the theme token")
    assert(SameColor(L.edgeT.color, FS.Theme.COLOR_BORDER), "violet edge from the theme token")
    assert(SameColor(L.label.tcolor, FS.Theme.COLOR_POWER), "cyan label")
    assert(SameColor(L.bg.color, FS.Theme.COLOR_BUTTON_INK), "the track is the ink token")
    Tick(1)
    assert(Open("overpower"), "a glow window the usable read never confirmed still runs its length")
    assert(LogClean())
""")

case("the_box_opens_from_its_middle_before_the_fill_and_label_show", """
    __known[7384] = true
    Build()
    Glow(7384, true)
    Tick(0.05)
    local L = Lane()
    assert(L.bg.shown and Close3(L.bg.w, Px(35)), "a third open, got " .. L.bg.w / W.C.SPX)
    assert(Close3(L.bg.pt[4], Px(22 + 36)), "opening from the middle")
    assert(not L.fill.shown and not L.label.shown and not L.mark.shown, "fill and label wait for the open box")
    Tick(0.2)
    assert(Close3(L.bg.w, Px(106)) and L.fill.shown and L.label.shown)
""")

case("the_last_one_and_a_half_seconds_are_amber_with_the_tick_mark", """
    __known[7384] = true
    Build()
    Glow(7384, true)
    Tick(3.3)
    local L = Lane()
    assert(SameColor(L.fill.color, FS.Theme.COLOR_POWER) and SameColor(L.label.tcolor, FS.Theme.COLOR_POWER), "1.7 s left is still cyan")
    assert(L.mark.shown and Close3(L.mark.pt[4], Px(23 + 31)), "the tick sits at the 1.5 s point, 31 inner px in")
    assert(Close3(L.mark.h, Px(10)) and Close3(L.mark.pt[5], -Px(79)), "the tick is taller than the bar")
    Tick(0.4)
    assert(SameColor(L.fill.color, FS.Theme.COLOR_AMBER), "1.3 s left: amber fill")
    assert(SameColor(L.label.tcolor, FS.Theme.COLOR_AMBER), "amber label")
    assert(SameColor(L.edgeT.color, FS.Theme.COLOR_AMBER) and SameColor(L.edgeL.color, FS.Theme.COLOR_AMBER), "amber edge")
    assert(L.mark.shown and Close3(L.mark.pt[4], Px(23 + 31)), "the tick stays")
""")

case("a_plain_usable_flip_from_false_to_true_opens_the_lane", """
    __known[7384] = true
    Build()
    Tick(0.3)
    assert(not Open("overpower"), "a plain false read opens nothing")
    __usable.Overpower = true
    UsableEv()
    local st = Win.Get("overpower")
    assert(st.open and st.source == "usable", "SPELL_UPDATE_USABLE reads it at once")
    Tick(0.2)
    assert(Lane().fill.shown and Lane().label.text == "OVERPOWER")
""")

case("the_poll_finds_a_usable_flip_with_no_event", """
    __known[7384] = true
    Build()
    Tick(0.3)
    __usable.Overpower = true
    Tick(0.3)
    assert(Open("overpower") and Win.Get("overpower").source == "usable")
""")

case("a_first_read_of_true_does_not_open_and_true_to_false_closes_quietly", """
    __known[7384] = true
    __usable.Overpower = true
    Build()
    for i = 1, 10 do Tick(0.3) end
    assert(not Open("overpower"), "a first read of true says nothing about when the window began")
    __usable.Overpower = false
    Tick(0.3)
    __usable.Overpower = true
    Tick(0.3)
    assert(Open("overpower"), "false then true is the flip")
    Tick(0.5)
    __usable.Overpower = false
    Tick(0.3)
    local st = Win.Get("overpower")
    assert(not st.open and st.closedWhy == "usable")
    assert(not LaneUp(), "a quiet close: no flash, no outline, the lane just goes")
    assert(Lane().mode == nil)
""")

case("a_secret_usable_value_never_opens_the_lane_and_never_errors", """
    __known[7384] = true
    __usable.Overpower = SECRET
    Build()
    for i = 1, 20 do Tick(0.1); UsableEv() end
    assert(not Open("overpower"), "a secret answer is unavailable, not true")
    assert(not LaneUp())
    local ok, bad = LogClean()
    assert(ok, "no error was logged, saw " .. tostring(bad))
    -- the glow still works while the usable answer is secret, and a secret answer never closes the window
    Glow(7384, true)
    Tick(0.5)
    UsableEv()
    assert(Open("overpower") and LaneUp())
    Tick(5)
    assert(not Open("overpower") and Win.Get("overpower").closedWhy == "expire")
    ok, bad = LogClean()
    assert(ok, "no error was logged, saw " .. tostring(bad))
    -- a secret spell id in an event is ignored
    Glow(SECRET, true)
    CastEv(SECRET)
    assert(not Open("overpower"))
    ok, bad = LogClean()
    assert(ok, "no error was logged, saw " .. tostring(bad))
""")

case("the_players_cast_snaps_the_lane_shut_with_a_pink_flash", """
    __known[7384] = true
    Build()
    Glow(7384, true)
    Tick(1)
    CastEv(7384)
    local st, L = Win.Get("overpower"), Lane()
    assert(not st.open and st.closedWhy == "cast")
    assert(L.mode == "cast" and L.bar.shown and L.glow.shown and L.line.shown, "the flash shows at once")
    assert(not Shown(L.windowParts) and not L.label.shown, "the drain bar and its label are gone")
    assert(SameColor(L.bar.color, FS.Theme.COLOR_HEALTH), "pink")
    assert(Close3(L.bar.w, Px(106)))
    Tick(0.1)
    assert(Close3(L.bar.w, Px(47)), "the pink bar snaps in from both ends, got " .. L.bar.w / W.C.SPX)
    assert(Close3(L.bar.pt[4], Px(22 + 30)), "and stays centred")
    Tick(0.1)
    assert(not L.bar.shown and L.glow.shown and L.line.shown, "the bar is gone, the glow and the centre line still fade")
    Tick(0.3)
    assert(not LaneUp() and L.mode == nil, "the flash is over")
""")

case("a_cast_of_another_spell_or_a_secret_one_leaves_the_window_open", """
    __known[7384] = true
    Build()
    Glow(7384, true)
    CastEv(SECRET)
    CastEv(133)
    CastEv(25289)
    assert(Open("overpower"))
    assert(LogClean())
""")

case("a_cast_just_after_the_glow_drops_still_flashes_but_a_late_one_does_not", """
    __known[7384] = true
    Build()
    Glow(7384, true)
    Tick(1)
    Glow(7384, false)
    local st, L = Win.Get("overpower"), Lane()
    assert(not st.open and st.closedWhy == "glow")
    assert(not LaneUp(), "a glow that drops closes the lane quietly")
    Tick(0.3)
    CastEv(7384)
    assert(L.mode == "cast" and L.bar.shown, "the cast event arriving a beat after the glow hid still flashes")
    Tick(1)
    Glow(7384, true)
    Tick(0.5)
    Glow(7384, false)
    Tick(0.8)
    CastEv(7384)
    assert(L.mode == nil and not LaneUp(), "a cast long after the window closed is not a flash")
""")

case("a_window_that_runs_out_shows_the_amber_dotted_outline_then_hides", """
    __known[7384] = true
    Build()
    Glow(7384, true)
    Tick(4.9)
    assert(Open("overpower"))
    Tick(0.2)
    local st, L = Win.Get("overpower"), Lane()
    assert(not st.open and st.closedWhy == "expire")
    assert(L.mode == "expire" and AllShown(L.dots), "the outline shows")
    assert(not Shown(L.windowParts) and not L.label.shown, "no bar, no label")
    assert(SameColor(L.dots[1].color, FS.Theme.COLOR_AMBER) and Close3(L.dots[1].color[4], 0.6), "amber at 0.6")
    Tick(0.2)
    assert(AllShown(L.dots) and L.dots[1].color[4] < 0.6, "it fades")
    Tick(0.3)
    assert(not LaneUp() and L.mode == nil, "then it hides")
""")

case("a_spell_the_player_does_not_know_is_never_shown", """
    Build()
    Glow(7384, true)
    Glow(6572, true)
    Glow(34428, true)
    Tick(0.3)
    __usable.Overpower, __usable.Revenge, __usable["Victory Rush"] = true, true, true
    Tick(0.3)
    UsableEv()
    CastEv(7384)
    for _, k in ipairs(Win.ORDER) do assert(not Open(k) and not Win.Get(k).known, k) end
    assert(not LaneUp() and Win.Urgent(__now) == nil)
    assert(LogClean())
""")

case("a_spell_known_only_by_name_counts_as_known", """
    __resolve["Overpower"] = 55555
    __known[55555] = true
    Build()
    assert(Win.Get("overpower").known, "the id the name resolves to is checked")
    Glow(55555, true)
    assert(Open("overpower"), "and the glow is matched by name")
""")

case("a_glow_for_another_spell_is_ignored", """
    __known[7384] = true
    Build()
    Glow(133, true)
    Glow(25289, true)
    Glow(SECRET, true)
    Glow(nil, true)
    Glow(133, false)
    Tick(0.3)
    assert(not Open("overpower") and not LaneUp())
    assert(LogClean())
    Glow(7384, true)
    Glow(133, false)
    assert(Open("overpower"), "another spell's glow hiding does not close it")
""")

case("revenge_has_the_same_lane", """
    __known[6572] = true
    Build()
    Tick(0.3)
    Glow(6572, true)
    Tick(0.2)
    local st, L = Win.Get("revenge"), Lane()
    assert(Open("revenge") and not Open("overpower") and st.length == 5 and st.source == "glow")
    assert(L.label.text == "REVENGE" and Close3(L.fill.w, Px(100)) and SameColor(L.fill.color, FS.Theme.COLOR_POWER))
    Tick(3.5)
    assert(SameColor(L.fill.color, FS.Theme.COLOR_AMBER), "amber in its last 1.5 s")
    CastEv(25288)
    assert(L.mode == "cast" and L.bar.shown, "a cast of any rank flashes")
    Tick(1)
    __usable.Revenge = true
    UsableEv()
    assert(Open("revenge") and st.source == "usable", "the usable flip opens it too")
    Tick(5.3)
    assert(L.mode == "expire" and AllShown(L.dots), "and running out shows the outline")
""")

case("victory_rush_has_the_same_lane_with_a_twenty_second_window", """
    __known[34428] = true
    __hp = 50
    Build()
    Tick(0.3)
    Glow(34428, true)
    Tick(0.2)
    local st, L = Win.Get("victoryrush"), Lane()
    assert(Open("victoryrush") and st.length == 20)
    assert(L.label.text == "VICTORY RUSH", L.label.text)
    assert(Close3(L.fill.w, Px(103)), "19.8 of 20 s is 103 inner px, got " .. L.fill.w / W.C.SPX)
    assert(Close3(L.mark.pt[4], Px(23 + 8)), "the 1.5 s tick scales with the window, got " .. L.mark.pt[4] / W.C.SPX)
    Tick(10)
    assert(Close3(L.fill.w, Px(51)), "9.8 of 20 s, got " .. L.fill.w / W.C.SPX)
    Tick(8.1)
    assert(SameColor(L.fill.color, FS.Theme.COLOR_POWER))
    Tick(0.4)
    assert(SameColor(L.fill.color, FS.Theme.COLOR_AMBER) and SameColor(L.label.tcolor, FS.Theme.COLOR_AMBER))
    CastEv(34428)
    assert(L.mode == "cast")
    Tick(1)
    Glow(34428, true)
    Tick(21)
    assert(L.mode == "expire" and Win.Get("victoryrush").closedWhy == "expire", "twenty seconds is the length, then the outline")
    Tick(0.5)
    assert(L.mode == nil and not LaneUp())
""")

case("victory_rush_is_held_back_while_health_is_above_ninety_percent", """
    __known[34428] = true
    __hp, __hpmax = 95, 100
    Build()
    Tick(0.3)
    Glow(34428, true)
    Tick(0.3)
    local st, L = Win.Get("victoryrush"), Lane()
    assert(st.open and st.hidden and not LaneUp(), "open but not shown at 95 percent")
    assert(Win.Urgent(__now) == nil)
    __hp = 90
    Tick(0.3)
    assert(not st.hidden and LaneUp(), "exactly 90 percent is not above it")
    __hp = 91
    Tick(0.3)
    assert(st.hidden and not LaneUp(), "back above")
    __hp = 40
    Tick(0.3)
    assert(LaneUp() and L.label.text == "VICTORY RUSH", "low health shows it, with the time it has left")
    -- a window the lane never showed has no flash and no outline
    __hp = 99
    Tick(0.3)
    CastEv(34428)
    assert(not st.open and not st.shownAtClose and L.mode == nil and not LaneUp(), "a cast while held back plays nothing")
    Tick(1)
    Glow(34428, true)
    Tick(21)
    assert(not st.open and st.closedWhy == "expire" and L.mode == nil and not LaneUp(), "nor does a window that ran out unseen")
""")

case("victory_rush_health_gate_never_compares_a_secret", """
    __known[34428] = true
    __hp, __hpmax = SECRET, SECRET
    Build()
    Tick(0.3)
    Glow(34428, true)
    Tick(0.3)
    local st = Win.Get("victoryrush")
    assert(st.open and not st.hidden and LaneUp(), "a secret health read means the gate does not apply: shown")
    __hppct = 95
    Tick(0.3)
    assert(st.hidden and not LaneUp(), "UnitHealthPercent is used when its answer is plain")
    __hppct = SECRET
    Tick(0.3)
    assert(not st.hidden and LaneUp(), "a secret percent shows it")
    assert(LogClean())
""")

case("two_open_windows_show_the_one_with_less_time_left", """
    __known[7384], __known[6572], __known[34428] = true, true, true
    __hp = 50
    Build()
    Tick(0.3)
    Glow(34428, true)
    Tick(17.5)
    Glow(6572, true)
    Tick(0.2)
    local L = Lane()
    assert(Win.Urgent(__now) == "victoryrush", "2.3 s left beats 4.8 s")
    assert(L.label.text == "VICTORY RUSH")
    Tick(2.4)
    assert(L.mode == "expire", "the one that ran out gets its outline first")
    Tick(0.5)
    assert(L.mode == "window" and L.label.text == "REVENGE", "then the other one shows")
    CastEv(6572)
    Tick(0.5)
    assert(L.mode == nil and not LaneUp(), "nothing is left open")
    -- a tie goes to the first in the list
    Glow(6572, true)
    Glow(7384, true)
    assert(Win.Urgent(__now) == "overpower")
    Tick(0.3)
    assert(L.label.text == "OVERPOWER")
""")

case("a_dodge_while_hidden_is_recorded_and_the_lane_catches_up_on_show", """
    __known[7384] = true
    Build()
    local L = Lane()
    SPEC.onHide("lower")
    assert(W.frame.scripts.OnUpdate == nil)
    Glow(7384, true)
    assert(Open("overpower"), "the ledger listens while the module is hidden")
    __now = __now + 1
    SPEC.onShow("lower")
    Tick(0.1)
    assert(L.fill.shown and Close3(L.fill.w, Px(81)), "3.9 of 5 s is 81 inner px, got " .. L.fill.w / W.C.SPX)
    SPEC.onHide("lower")
    local mode = L.mode
    CastEv(7384)
    assert(L.mode == mode, "a hidden lane is not repainted by a cast")
    SPEC.onShow("lower")
    Tick(0.5)
    assert(L.mode == nil and not LaneUp(), "and plays no flash for a cast it missed")
""")

case("a_block_while_revenge_is_on_its_own_cooldown_waits_for_the_cooldown", """
    __known[6572] = true
    Build()
    Tick(0.3)
    __cd.Revenge = { isActive = true, isOnGCD = false }
    Glow(6572, true)
    Tick(0.3)
    assert(Open("revenge"), "the block still opens the window")
    assert(not Win.Shown("revenge", __now) and not LaneUp(), "but it is not shown while Revenge is cooling")
    __cd.Revenge = nil
    Tick(0.3)
    assert(Win.Shown("revenge", __now) and LaneUp(), "it shows once the cooldown ends inside the window")
    Tick(5)
    __cd.Revenge = { isActive = true, isOnGCD = true }
    Glow(6572, true)
    Tick(0.3)
    assert(Win.Shown("revenge", __now), "the global cooldown alone does not hold it back")
    __cd.Revenge = { isActive = true }
    __cd.GCD = { isActive = true }
    Tick(0.3)
    assert(Win.Shown("revenge", __now), "no isOnGCD answer while the GCD spell cools: still shown")
    __cd.GCD = nil
    Tick(0.3)
    assert(not Win.Shown("revenge", __now), "its own cooldown with the GCD done holds it back")
""")

case("the_lane_listens_for_the_overlay_glow_usable_and_cast_events_and_never_the_combat_log", """
    __known[7384] = true
    Build()
    local f = WinFrame()
    assert(f, "the windows frame registered")
    for _, e in ipairs({ "UNIT_SPELLCAST_SUCCEEDED", "SPELL_ACTIVATION_OVERLAY_GLOW_SHOW",
        "SPELL_ACTIVATION_OVERLAY_GLOW_HIDE", "SPELL_UPDATE_USABLE", "SPELL_UPDATE_COOLDOWN" }) do
        assert(f.events[e], "missing " .. e)
    end
    for _, fr in ipairs(__frames) do
        assert(not (fr.events and fr.events.COMBAT_LOG_EVENT_UNFILTERED), "the combat log is protected on this client")
    end
""")

case("the_lane_writes_only_what_changed_and_reseats_at_a_rescale", """
    __known[7384] = true
    Build()
    Glow(7384, true)
    Tick(0.3)
    local L = Lane()
    local w0 = Writes()
    for i = 1, 10 do Tick(0) end
    assert(Writes() == w0, "an unchanged tick writes nothing, wrote " .. (Writes() - w0))
    local n0 = L.fill.nw
    for i = 1, 30 do Tick(1 / 30) end
    assert(L.fill.nw - n0 <= 23, "one second of drain is about 21 whole px steps, wrote " .. (L.fill.nw - n0))
    local w = L.fill.w
    SPEC.seat({ x = 0, y = 0, w = 200, h = 128 })
    assert(L.fill.w == w and L.fill.pt, "a rescale puts the size and place back")
""")

case("the_windows_data_file_is_keyed_so_a_spell_is_one_entry", """
    assert(#Win.ORDER == 3 and Win.ORDER[1] == "overpower" and Win.ORDER[2] == "revenge" and Win.ORDER[3] == "victoryrush")
    for _, k in ipairs(Win.ORDER) do
        local d = Win.DEFS[k]
        assert(type(d.name) == "string" and type(d.label) == "string" and #d.ids > 0 and d.length > 0, k)
        assert(Win.Get(k).key == k)
    end
    assert(Win.DEFS.victoryrush.hideAboveHealth == 90 and Win.DEFS.overpower.hideAboveHealth == nil)
""")


# The lane's frozen states, as the mockup's frozen frames: the two helms behind a Battle Shout at 2m and a Demoralizing Shout
# at ~18s, then the lane open (3.2 s left), in its last 0.9 s, the cast flash and the expiry outline.
SCENE_BASE = """
    __known[7384], __known[11556] = true, true
    __aura = { expirationTime = __now + 132, duration = 180 }
    Build()
    Cast(11556)
    Tick(12)
"""
SCENES = {
    "open": SCENE_BASE + "Glow(7384, true) Tick(1.8)",
    "amber": SCENE_BASE + "Glow(7384, true) Tick(4.1)",
    "cast": SCENE_BASE + "Glow(7384, true) Tick(1) CastEv(7384) Tick(0.1)",
    "expired": SCENE_BASE + "Glow(7384, true) Tick(5) Tick(0.1)",
}
FONT = ROOT / "forever-stuwave/Media/Fonts/MononokiNerdFontMono-Bold.ttf"


def render(prefix: str) -> None:
    """Draw each scene's regions (flat colours and baked atlases) at 4x, one PNG per scene and one sheet."""
    from PIL import Image, ImageDraw, ImageFont

    scale, width, height = 4, 190, 132
    shots = []
    for name, code in SCENES.items():
        rt = LuaRuntime(unpack_returned_tuples=False)
        g = rt.globals()
        g.SHOUTS_SRC, g.MODULE_SRC, g.WINDOWS_SRC = SHOUTS, MODULE, WINDOWS
        rt.execute(MOCK)
        ops = rt.execute("local function main()\n" + code + "\nreturn Dump()\nend\nreturn main()")
        img = Image.new("RGBA", (width * scale, height * scale), (10, 4, 22, 255))
        font = ImageFont.truetype(str(FONT), 11 * scale)
        cache: dict[str, Image.Image] = {}
        for i in range(1, len(ops) + 1):
            op = ops[i]
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            if op["kind"] == "text":
                c = op["color"]
                col = tuple(int(c[k] * 255 + 0.5) for k in (1, 2, 3)) + (255,)
                ImageDraw.Draw(layer).text((op["cx"] * scale, op["cy"] * scale), op["text"], font=font, fill=col, anchor="mm")
            else:
                box = (round(op["l"] * scale), round(op["t"] * scale), round((op["l"] + op["w"]) * scale), round((op["t"] + op["h"]) * scale))
                if box[2] <= box[0] or box[3] <= box[1]:
                    continue
                alpha = op["alpha"] if op["alpha"] is not None else 1
                tex = op["tex"] or ""
                if tex.endswith(".tga") and op["tc"] is not None:
                    atlas = cache.setdefault(tex, Image.open(MEDIA / tex.replace("\\", "/").split("/")[-1]).convert("RGBA"))
                    aw, ah = atlas.size
                    tc = op["tc"]
                    part = atlas.crop((round(tc[1] * aw), round(tc[3] * ah), round(tc[2] * aw), round(tc[4] * ah)))
                    part = part.resize((box[2] - box[0], box[3] - box[1]), Image.NEAREST)
                    if alpha < 1:
                        part.putalpha(part.getchannel("A").point(lambda v: int(v * alpha)))
                    layer.paste(part, box[:2])
                else:
                    c = op["color"]
                    a = c[4] * alpha if c[4] is not None else alpha
                    ImageDraw.Draw(layer).rectangle([box[0], box[1], box[2] - 1, box[3] - 1],
                                                    fill=tuple(int(c[k] * 255 + 0.5) for k in (1, 2, 3)) + (int(a * 255 + 0.5),))
            img = Image.alpha_composite(img, layer)
        out = f"{prefix}-{name}.png"
        img.convert("RGB").save(out)
        print("wrote", out)
        shots.append(img)
    sheet = Image.new("RGB", (width * scale * 2 + 8, height * scale * 2 + 8), (30, 20, 50))
    for i, shot in enumerate(shots):
        sheet.paste(shot.convert("RGB"), ((i % 2) * (width * scale + 8), (i // 2) * (height * scale + 8)))
    sheet.save(f"{prefix}-frames.png")
    print("wrote", f"{prefix}-frames.png")


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.SHOUTS_SRC, g.MODULE_SRC, g.WINDOWS_SRC = SHOUTS, MODULE, WINDOWS
    try:
        rt.execute(MOCK)
        rt.execute("local function main()\n" + body + "\nend\nreturn main()")
    except LuaError as exc:
        return str(exc)
    return None


def static_checks() -> list[str]:
    errs = []
    for name in ("warrior_helm", "warrior_runes_big", "warrior_runes_small", "warrior_helm_glow"):
        if not (MEDIA / f"{name}.tga").exists():
            errs.append(f"missing texture {name}.tga (run tools/assets/generate_warrior_helm.py)")
        if f"{name}" not in MODULE and f'"{name}"' not in MODULE and name != "warrior_helm":
            errs.append(f"the module does not reference {name}")
    toc = [line.strip() for line in TOC.splitlines()]
    try:
        order = [toc.index(f"Modules/CombatHud/{n}.lua") for n in ("WarriorShouts", "WarriorWindows", "GunsightWarrior")]
        if order != sorted(order):
            errs.append("the toc must load WarriorShouts, WarriorWindows, GunsightWarrior in that order")
    except ValueError:
        errs.append("the toc does not list WarriorWindows.lua beside the other Warrior files")
    for needle in ("COMBAT_LOG_EVENT_UNFILTERED",):
        for name, text in (("WarriorWindows.lua", WINDOWS), ("GunsightWarrior.lua", MODULE)):
            for line in text.splitlines():
                if needle in line and not line.lstrip().startswith("--"):
                    errs.append(f"{name} must never register {needle}")
    gen = re.search(r"HELM_FRAMES = \[(.*?)\n\]", GENERATOR, re.S)
    frames = re.findall(r'\("(\w+)", "(\w+)", "(\w+)", "?(\w+)"?\)', gen.group(1)) if gen else []
    want = {
        "roar1": ("blaze", "roar", "rage", "0"), "roar2": ("blaze", "roar", "rage", "1"),
        "roar3": ("blaze", "roar", "rage", "2"), "roar4": ("blaze", "roar", "rage", "3"),
        "hot": ("hot", "shut", "rage", "still"), "red": ("red", "shut", "rage", "still"),
        "dim": ("dim", "shut", "rage", "still"),
        "grimHot": ("hot", "shut", "grim", "still"), "grimRed": ("red", "shut", "grim", "still"),
        "grimDim": ("dim", "shut", "grim", "still"),
        "growl1": ("slit", "snarl", "grim", "0"), "growl2": ("slit", "snarl", "grim", "1"),
        "growl3": ("slit", "snarl", "grim", "2"), "growl4": ("slit", "snarl", "grim", "3"),
        "cold": ("dark", "shut", "cold", "still"), "coldFlick": ("flick", "shut", "cold", "still"),
    }
    if len(frames) != 16:
        errs.append(f"the generator has {len(frames)} helm frames, want 16")
    gm = re.search(r"HELM_W, HELM_H, HELM_OX, HELM_CELL = (\d+), (\d+), (\d+), 64", GENERATOR)
    lm = re.search(r"HELM_W = (\d+), HELM_H = (\d+),", MODULE)
    lo = re.search(r"HELM_OX = (\d+),", MODULE)
    if not (gm and lm and lo and (gm.group(1), gm.group(2), gm.group(3)) == (lm.group(1), lm.group(2), lo.group(1))):
        errs.append("the module's HELM_W / HELM_H / HELM_OX do not match the generator's")
    lua_frames = dict(re.findall(r"(\w+) = (\d+)", re.search(r"local FRAME = \{(.*?)\n\}", MODULE, re.S).group(1)))
    for key, combo in want.items():
        idx = int(lua_frames.get(key, -1))
        if idx < 0 or idx >= len(frames) or frames[idx] != combo:
            errs.append(f"FRAME.{key} = {idx} does not match the generator's {combo}")
    return errs


def main() -> int:
    failures = 0
    for err in static_checks():
        failures += 1
        print(f"FAIL  static: {err}")
    for name, body in CASES:
        err = run_case(body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    total = len(CASES)
    print(f"{total - min(failures, total)}/{total} checks passed")
    if "--png" in sys.argv:
        prefix = sys.argv[sys.argv.index("--png") + 1]
        Path(prefix).parent.mkdir(parents=True, exist_ok=True)
        render(prefix)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
