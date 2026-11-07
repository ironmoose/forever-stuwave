#!/usr/bin/env python3
"""Runs the real WarriorShouts.lua and GunsightWarrior.lua headless against a mock client.

The Warrior Class Module draws the design mockup "Warrior Roaring Helm, rune ring" (2026-11-07): a Battle Shout ring and a
Demoralizing Shout ring, each a helm in the middle and 8 orbiting rune tiles. These checks pin:

  * the data: an out of combat aura read is the truth, a cast in combat stamps the ledger (shown with "~"), Demoralizing Shout
    is always the ledger, a secret spell id is ignored, a shout runs out on Tick;
  * the rune count ceil(remaining / duration * 8), the amber last rune, the dark ones, the gone and locked looks;
  * the helm frame for each state: the roar's beard whip on a Battle Shout cast, one still frame while it breathes, growl on a Demoralizing Shout cast, cold
    when gone, hidden while Demoralizing Shout is not learned;
  * the labels (3m, ~2m, SHOUT, L14, ~30s, amber on the last rune);
  * onHide stops the ticker and the subscription, onShow brings both back;
  * the baked textures exist and the atlas frame order matches the generator.

    python3 tools/gunsightwarrior-harness.py

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
function Obj:SetPoint(p, rel, rp, x, y) self.pt = { p, rel, rp, x or 0, y or 0 } end
function Obj:ClearAllPoints() self.pt = nil end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:Show() self.shown = true end
function Obj:Hide() self.shown = false end
function Obj:IsShown() return self.shown end
function Obj:SetScript(n, fn) self.scripts = self.scripts or {}; self.scripts[n] = fn end
function Obj:GetScript(n) return self.scripts and self.scripts[n] end
function Obj:RegisterEvent(e) self.events = self.events or {}; self.events[e] = true end
function Obj:RegisterUnitEvent(e) self.events = self.events or {}; self.events[e] = true end
function Obj:SetTexture(p) self.tex = p end
function Obj:SetTexCoord(l, r, t, b) self.tc = { l, r, t, b } end
function Obj:SetVertexColor(r, g, b, a) self.color = { r, g, b, a } end
function Obj:SetText(t) self.text = t end
function Obj:SetTextColor(r, g, b, a) self.tcolor = { r, g, b, a } end
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
function IsPlayerSpell(id) return __known[id] == true end
__names = {}
for _, id in ipairs({ 25289, 11551, 11550, 11549, 6192, 5242, 6673 }) do __names[id] = "Battle Shout" end
for _, id in ipairs({ 11556, 11555, 11554, 6190, 1160 }) do __names[id] = "Demoralizing Shout" end
__names[133] = "Fireball"
__aura = nil                                     -- { expirationTime =, duration = } or nil
C_Spell = { GetSpellName = function(id) return __names[id] end }
C_UnitAuras = {
    GetPlayerAuraBySpellID = function(id) if id == 25289 then return __aura end return nil end,
}
SECRET = setmetatable({}, { __tostring = function() return "secret" end })
__cfg = {}
local Areas = { specs = {} }
function Areas.RegisterModule(id, spec) Areas.specs[#Areas.specs + 1] = { id = id, spec = spec }; return true end
FS = {
    IsSecret = function(v) return v == SECRET end,
    AurasReadable = function() return not __combat end,
    Gunsight = { ui = function(px) return px end, Point = function(f, p, x, y) f.pt = { p, "root", "CENTER", x, y } end, G = {} },
    GunsightAreas = Areas,
    Theme = { ApplyMono = function(fs, size, cur) fs.size = size end },
    FrameHelpers = {
        RegisterEvent = function(f, e) f.events = f.events or {}; f.events[e] = true end,
        RegisterEvents = function(f, list) f.events = f.events or {}; for _, e in ipairs(list) do f.events[e] = true end end,
    },
    LogDegradeOnce = function(k, m) __logged = __logged or {}; __logged[k] = m end,
}
assert(loadstring(SHOUTS_SRC, "@WarriorShouts.lua"))("forever-stuwave", FS)
assert(loadstring(MODULE_SRC, "@GunsightWarrior.lua"))("forever-stuwave", FS)
Shouts, W = FS.WarriorShouts, FS.GunsightWarrior
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

case("demoralizing_shout_not_learned_is_a_locked_ring", """
    Build()
    Tick(0.05)
    assert(Rows("demo") == "55555555", Rows("demo"))
    assert(Ring("demo").helm.shown == false)
    assert(Ring("demo").label.text == "L14")
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


def run_case(body: str) -> str | None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.SHOUTS_SRC, g.MODULE_SRC = SHOUTS, MODULE
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
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
