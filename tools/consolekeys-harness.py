#!/usr/bin/env python3
"""Runs the real ConsoleKeys.lua (the eight HUD keys on the Console's shoulder tab) headless against the
mock WoW API gunsight-harness.py uses, plus the real Layout.lua, Gunsight.lua, ChevronCastBar.lua and
Console.lua (the Console's geometry comes from a controllable stand-in for ActionBars.lua).

The keys are the locked mockup's (mockups/gunsight-hud-v2-2026-10-02/gunsight-hud-v2-2026-10-02.html:
DECK_DEFS, keyX, the `.cdeck.bm` key rules, the Rings block). The checks pin:

  * the eight keys are plain Buttons inside the Console tab, seated from Console.KeyRect (never from a
    copy of the tab geometry), with the mockup's key size and ONE even pitch (no group gaps), hit areas
    that tile the pitch, and NOTHING else under the tab (no annunciator ticks);
  * a key HIDES when its piece has nothing to show for the class profile (the real HudProfiles.lua
    warlock and priest data, a custom profile, none): the shown keys take consecutive slots at the
    even pitch, the Console tab is sized for the shown count with the same 15 padding, a hidden key
    is not shown or clickable and its piece state (Gunsight.SetPiece) is never touched; a profile
    that arrives late, or a change made in combat, is applied by the next geometry, entering world,
    rescale or regen hook (in combat: at regen);
  * name, description, colour, glyph and the piece each key toggles, parsed back out of the mockup;
  * a click toggles exactly its piece (in combat too, without touching a protected frame), and
    /fsgun piece changes move the keys through OnPieceChanged;
  * the look (lit, off, hover, pressed) and the tooltip text (name, ON / OFF, description);
  * ignite and outage: the ring shows and the ONE OnUpdate runs only while an animation is live, the
    outage takes 1.0 s and keeps the lit look until it ends, the ring then eases out over 0.4 s, and
    nothing is left running at rest; reduced motion, a hidden key and a missing Fx snap instead;
  * a rescale re-seats and creates nothing, in combat it waits for regen;
  * the keys follow the Console (hidden with /fsconsole off) and the Gunsight state read ONCE at
    login (not built, party piece not registered, when it was disabled then; /fsgun on|off at
    runtime changes nothing until a reload); the party frame container becomes piece `party`
    (alpha only in combat while it is protected), with one next-frame retry when it is missing at
    regen and a lazy register on the first click.

The mock is strict (a widget method it does not define fails as a nil call) and is NOT the real client.

    python3 tools/consolekeys-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
KEYS_LUA = Path(os.environ.get("CONSOLEKEYS_LUA") or ADDON / "Modules/ActionBars/ConsoleKeys.lua")
TOC = ADDON / "forever-stuwave.toc"
THEME = ADDON / "Core/Theme.lua"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gh = _load("gunsight_harness", HERE / "gunsight-harness.py")
abh = _load("actionbars_harness", HERE / "actionbars-harness.py")
ch = _load("console_harness", HERE / "console-harness.py")

SRC_FILES = {
    "LAYOUT_SRC": ADDON / "Core/Layout.lua",
    "CONFIG_SRC": ADDON / "Core/Config.lua",
    "GUNSIGHT_SRC": ADDON / "Modules/CombatHud/Gunsight.lua",
    "CHEVRON_SRC": ADDON / "Core/ChevronCastBar.lua",
    "CONSOLE_SRC": ADDON / "Modules/ActionBars/Console.lua",
    "PROFILES_SRC": ADDON / "Modules/CombatHud/HudProfiles.lua",
    "KEYS_SRC": KEYS_LUA,
}

PIECE_OF = {"your": "you", "next": "next", "shard": "shard", "buff": "buff", "target": "tgt",
            "dots": "dot", "procs": "prc", "party": "party"}


# ---------------------------------------------------------------------------------------
# Numbers the mockup owns. Read, never retyped.
# ---------------------------------------------------------------------------------------

def mockup_keys() -> dict:
    src = gh.MOCKUP.read_text(encoding="utf-8")
    defs = []
    for m in re.finditer(
            r"\{k:'(\w+)',n:'([^']*)',d:(?:'([^']*)'|\"([^\"]*)\"),c:'(\w+)',g:'(\w+)'\}", src):
        k, n, d1, d2, c, g = m.groups()
        defs.append(dict(piece=PIECE_OF[k], n=n, d=d1 if d1 is not None else d2, c=c, g=g))
    if len(defs) != 8:
        sys.exit(f"mockup: expected 8 DECK_DEFS entries, found {len(defs)}")
    # The v2 mockup names key 6 for the DoT scale; it now switches both target side areas, so only its
    # tooltip text differs from the mockup (the glyph, colour and slot are still the mockup's).
    for d in defs:
        if d["piece"] == "dot":
            d["n"], d["d"] = "Target side", "Target debuffs and class module beside the target cast bar"
    colors = {}
    for name, hexv in re.findall(r"^\s*--(cyan|gold|violet|pink|amber|green):(#[0-9a-fA-F]{6});", src, re.M):
        colors[name] = [int(hexv[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    for need in ("cyan", "gold", "violet", "pink", "amber", "green"):
        if need not in colors:
            sys.exit(f"mockup: colour token --{need} missing")
    mu = ch.mockup_constants()
    ring_n = int(gh._m(r"var RING_N = (\d+);", src, "RING_N").group(1))
    intr = int(gh._m(r"intMs: (\d+)", src, "intMs").group(1))
    fade = int(gh._m(r"clamp\(1 - \(now - ring\.rT\) / (\d+)\)", src, "ring fade ms").group(1))
    return dict(defs=defs, colors=colors, KEY_W=mu["KEY_W"], KEY_H=mu["KEY_H"], KEY_GAP=mu["KEY_GAP"],
                KEY_PAD=mu["KEY_PAD"], KEY_SH=mu["KEY_SH"], TAB_DW=mu["TAB_DW"], RING_N=ring_n,
                INTR_MS=intr, RING_FADE_MS=fade)


def lua_literal(v) -> str:
    if isinstance(v, dict):
        return "{" + ",".join(f"[{lua_literal(str(k))}]={lua_literal(x)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(lua_literal(x) for x in v) + "}"
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return repr(v)


def theme_lines() -> list[str]:
    src = THEME.read_text(encoding="utf-8")
    names = ("SLICE_MARGIN", "SLICE_CUT_MARGIN", "SLICE_CUT2_BUTTON_TEXTURE", "SLICE_CUT2_FILL_TEXTURE",
             "SLICE_CUT2_OUTLINE_TEXTURE", "SLICE_CUT2_GLOW_TEXTURE", "SLICE_CUT2_GLOW_PAD",
             "SLICE_CUT2_GLOW_MARGIN")
    return [abh._extract_theme_constant(src, n) for n in names]


def theme_functions() -> dict:
    src = THEME.read_text(encoding="utf-8")
    return {n: abh._extract_theme_function(src, n) for n in ("ApplyNineSlice", "AddSliceTexture")}


# ---------------------------------------------------------------------------------------
# Extra mock on top of gunsight-harness.py's
# ---------------------------------------------------------------------------------------

EXTRA = r"""
local FrameMT = getmetatable(UIParent)
NOW = 100            -- seconds, what GetTime returns
function GetTime() return NOW end
function FrameMT:SetScale(s) self.scale = s end
function FrameMT:GetScale() return self.scale or 1 end
function FrameMT:SetAllPoints(rel)
    self.points = {}
    self:SetPoint("TOPLEFT", rel or self.parent, "TOPLEFT", 0, 0)
    self:SetPoint("BOTTOMRIGHT", rel or self.parent, "BOTTOMRIGHT", 0, 0)
end
function FrameMT:SetHitRectInsets(l, r, t, b) self.hit = { l = l, r = r, t = t, b = b } end
function FrameMT:RegisterForClicks(...) self.clicks = { ... } end
function FrameMT:GetEffectiveScale() return 1 end
-- the real client runs OnHide when a shown frame is hidden; the base mock does not
local baseHide = FrameMT.Hide
function FrameMT:Hide()
    local was = self:IsShown()
    baseHide(self)
    if was and self.scripts and self.scripts.OnHide then self.scripts.OnHide(self) end
end

local baseCreate = CreateFrame
function CreateFrame(kind, name, parent, template)
    check(kind == "Frame" or kind == "Button", "mock builds Frames and Buttons only, got " .. tostring(kind))
    local saved = kind
    local f = baseCreate("Frame", name, parent, template)
    f.kind = saved
    if name then _G[name] = f end
    return f
end

local baseTexture = FrameMT.CreateTexture
TEXTURES = {}
function FrameMT:CreateTexture(name, layer, template, sublevel)
    local t = baseTexture(self, name, layer)
    t.sublevel = sublevel
    TEXTURES[#TEXTURES + 1] = t
    function t:SetColorTexture(r, g, b, a) self.color = { r, g, b, a } end
    function t:SetTexture(p) self.tex = p end
    function t:SetVertexColor(r, g, b, a) self.vcolor = { r, g, b, a } end
    function t:SetBlendMode(m) self.blend = m end
    function t:SetTexCoord(...) self.coords = { ... } end
    function t:SetRotation(r) self.rot = r end
    function t:SetTextureSliceMargins(l, tt, r, b) self.sliceMargins = { l, tt, r, b } end
    function t:SetTextureSliceMode(m) self.sliceMode = m end
    return t
end

GameTooltip = { lines = {}, shown = false }
function GameTooltip:SetOwner(owner, anchor) self.owner, self.anchor, self.lines, self.points = owner, anchor, {}, {} end
function GameTooltip:ClearAllPoints() self.points = {} end
function GameTooltip:SetPoint(...) self.points[#self.points + 1] = { ... } end
function GameTooltip:AddLine(text, r, g, b, wrap) self.lines[#self.lines + 1] = { text = text, wrap = wrap } end
function GameTooltip:AddDoubleLine(l, r, lr, lg, lb, rr, rg, rb)
    self.lines[#self.lines + 1] = { text = l, right = r, rcolor = { rr, rg, rb } }
end
function GameTooltip:Show() self.shown = true end
function GameTooltip:Hide() self.shown = false; self.owner = nil end
function GameTooltip:GetOwner() return self.owner end

-- ActionBars.lua stand-in: publishes geometry to subscribers in order, like the real one
AB = { callbacks = {}, consoleOn = true, published = false }
function AB.OnGeometry(fn)
    AB.callbacks[#AB.callbacks + 1] = fn
    if AB.geometry then pcall(fn, AB.geometry) end
end
function AB.Publish()
    local s = FS.Layout.Scale()
    AB.stack = AB.stack or CreateFrame("Frame", "FSActionBarStack", UIParent)
    AB.stack:SetSize(1089 * s, 178 * s)
    AB.stack:SetPoint("CENTER", UIParent, "CENTER", 0, -540 * s)
    AB.geometry = {
        stack = AB.stack, scale = s, console = AB.consoleOn, shown = true,
        fieldLeft = 40 * s, fieldTop = 20 * s, fieldRight = 1050 * s, fieldBottom = 160 * s,
        btnSize = 36 * s, rowPitch = 49.2 * s, btnPitch = 38 * s, halfX = { 0, 540 * s },
        btnX0 = 40 * s, spineX = 545 * s,
    }
    AB.published = true
    for _, fn in ipairs(AB.callbacks) do pcall(fn, AB.geometry) end
end
function AB.SetConsoleActive(on)
    AB.consoleOn = on and true or false
    if AB.published then AB.Publish() end
    return true
end
function AB.IsConsoleActive() return AB.consoleOn end

function OnUpdates()
    local n = 0
    for _, f in ipairs(FRAMES) do if f.scripts.OnUpdate then n = n + 1 end end
    return n
end
function Driver()
    for _, f in ipairs(FRAMES) do if f.scripts.OnUpdate then return f end end
end
-- Advance the clock by `ms` in 16 ms frames, running the OnUpdate each frame while one exists.
function Advance(ms)
    local t = 0
    while t < ms do
        local step = math.min(16, ms - t)
        NOW = NOW + step / 1000
        t = t + step
        local d = Driver()
        if d then d.scripts.OnUpdate(d, step / 1000) end
    end
end
function Count(kind)
    local n = 0
    for _, f in ipairs(FRAMES) do if f.kind == kind then n = n + 1 end end
    return n
end

-- The REAL Theme.lua nine-slice constants and functions (extracted by the harness), nothing else.
function MakeTheme()
    FS.Theme = {}
    loadAddonFile("local _, FS = ...\nlocal Theme = FS.Theme\nlocal warnedNoSliceMargins = false\n" ..
        THEME_LINES .. "\n" .. THEME_FUNCS .. "\n", "Theme.lua(extract)")
    -- Stand-in for the real ApplyMono's contract that matters here: it calls SetFont, so the FontString has
    -- a font (the shared mock throws "Font not set" for SetText before that, like the client).
    function FS.Theme.ApplyMono(fs, size, color) fs:SetFont("mono.ttf", size, "") end
    return FS.Theme
end
"""

PRELUDE = r"""
-- The locked mockup still says "tape"; the player-facing text says "cast bar".
local REWORD = {
    ["Cast tape and timer box"] = "Your cast bar and timer box",
    ["Held shards under your tape"] = "Held shards under your cast bar",
    ["Enemy cast tape, kick and lock state"] = "Target cast bar, kick and lock state",
}
local function reword(text) return REWORD[text] or text end

local function boot(opts)
    opts = opts or {}
    SetScreen(opts.height or 1440)
    ForeverSTUwaveDB = opts.db or {}
    NOW = 100
    IN_COMBAT = false
    MakeTheme()
    loadAddonFile(LAYOUT_SRC, "Core/Layout.lua")
    loadAddonFile(CONFIG_SRC, "Core/Config.lua")
    loadAddonFile(GUNSIGHT_SRC, "Modules/CombatHud/Gunsight.lua")
    if not opts.noFx then loadAddonFile(CHEVRON_SRC, "Core/ChevronCastBar.lua") end
    FS.ActionBars = AB
    if opts.consoleOff then AB.consoleOn = false end
    loadAddonFile(CONSOLE_SRC, "Modules/ActionBars/Console.lua")
    -- FS.Hud stand-in: HudLogic's GetProfile over the REAL HudProfiles.lua data. HUD_PROFILE is the
    -- profile "the class resolved to" and a test may change it later (a late arrival).
    loadAddonFile(PROFILES_SRC, "Modules/CombatHud/HudProfiles.lua")
    local want = opts.profile
    if want == nil then want = "WARLOCK" end
    HUD_PROFILE = type(want) == "string" and FS.HudProfiles[want] or (type(want) == "table" and want or nil)
    FS.Hud = { GetProfile = function() return HUD_PROFILE end }
    if opts.party then
        FS.partyContainer = CreateFrame("Frame", "ForeverSTUwavePartyContainer", UIParent)
        FS.partyContainer.protected = opts.partyProtected
    end
    loadAddonFile(KEYS_SRC, "Modules/ActionBars/ConsoleKeys.lua")
    fire("ADDON_LOADED", "forever-stuwave")
    if opts.geometryFirst ~= false then FS.ActionBars.Publish() end
    fire("PLAYER_LOGIN")
    if opts.geometryFirst == false then FS.ActionBars.Publish() end
    return FS.ConsoleKeys, FS.Gunsight
end

local function keyOf(CK, piece)
    for _, k in ipairs(CK.keys) do if k.key == piece then return k end end
    error("no key for piece " .. tostring(piece))
end
local function click(k) k.btn.scripts.OnClick(k.btn, "LeftButton") end
local function eq(a, b, msg) near(a, b, msg) end
"""

CASES: list[tuple[str, str]] = []


def case(name: str):
    def deco(body: str):
        CASES.append((name, body))
        return body
    return deco


# ---------------------------------------------------------------------------------------
# Build and position
# ---------------------------------------------------------------------------------------

case("keys_are_plain_buttons_in_the_console_tab")(r"""
local CK = boot({})
check(CK.IsBuilt(), "keys were not built")
check(#CK.keys == 8, "expected 8 keys, got " .. #CK.keys)
local tab = FS.Console.tab
check(tab, "the Console has no tab")
local host = CK.keys[1].btn:GetParent()
check(host:GetParent() == tab, "the key host is not a child of the Console tab")
for i, k in ipairs(CK.keys) do
    check(k.btn.kind == "Button", "key " .. i .. " is not a Button")
    check(k.btn.template == nil and k.btn:IsProtected() == false, "key " .. i .. " must be a plain non secure Button")
    check(k.btn:GetParent() == host, "key " .. i .. " is not under the host")
end
-- no annunciator ticks and nothing else hangs off the tab: the host is its only child frame/texture
local kids = 0
for _, c in ipairs(tab.children) do kids = kids + 1 end
check(kids == 1, "the tab has " .. kids .. " children, only the key host belongs there")
local n = 0
for _, c in ipairs(host.children) do n = n + 1 end
check(n == 8, "the host holds " .. n .. " children, expected the eight keys")
""")

key_layout_body = r"""
local CK = boot({ height = HEIGHT })
local s = FS.Layout.Scale()
local M = MU
local function keyX(i) return M.KEY_SH + M.KEY_PAD + i * (M.KEY_W + M.KEY_GAP) end
local first
for i, k in ipairs(CK.keys) do
    local r = FS.Console.KeyRect(i - 1, s)
    local point, rel, relPoint, x, y = k.btn:GetPoint(1)
    check(rel == FS.Console.tab and point == "TOPLEFT" and relPoint == "TOPLEFT", "key " .. i .. " is not anchored TOPLEFT to the tab")
    eq(x, r.x, "key " .. i .. " x is Console.KeyRect's"); eq(y, -r.y, "key " .. i .. " y is Console.KeyRect's")
    eq(k.btn:GetWidth(), M.KEY_W * s, "key " .. i .. " width"); eq(k.btn:GetHeight(), M.KEY_H * s, "key " .. i .. " height")
    first = first or x
    eq(x - first, (keyX(i - 1) - keyX(0)) * s, "key " .. i .. " pitch from key 1 (mockup keyX, one even pitch)")
    eq(k.art:GetScale(), s, "key " .. i .. " art scale")
    eq(k.art:GetWidth(), M.KEY_W, "key " .. i .. " art is design px wide")
    eq(k.art:GetHeight(), M.KEY_H, "key " .. i .. " art is design px tall")
end
-- the hit areas tile the pitch: the gap between two keys is shared by their insets
for i = 1, 7 do
    local a, b = CK.keys[i].btn.hit, CK.keys[i + 1].btn.hit
    local gap = (FS.Console.KeyRect(i, s).x) - (FS.Console.KeyRect(i - 1, s).x + M.KEY_W * s)
    eq(-a.r + -b.l, gap, "hit areas of key " .. i .. " and " .. (i + 1) .. " tile the gap")
end
"""
case("keys_sit_at_the_mockup_positions_at_1440")(key_layout_body.replace("HEIGHT", "1440"))
case("keys_sit_at_the_mockup_positions_at_1200")(key_layout_body.replace("HEIGHT", "1200"))

case("definitions_match_the_mockup")(r"""
local CK = boot({})
check(#MU.defs == #CK.DEFS, "key count")
for i, d in ipairs(MU.defs) do
    local def = CK.DEFS[i]
    check(def.key == d.piece, "key " .. i .. " toggles " .. def.key .. ", mockup says " .. d.piece)
    check(def.n == d.n, "key " .. i .. " name " .. def.n .. " vs " .. d.n)
    check(def.d == reword(d.d), "key " .. i .. " description " .. def.d .. " vs " .. reword(d.d))
    check(def.c == d.c, "key " .. i .. " colour " .. def.c .. " vs " .. d.c)
    check(def.g == d.g, "key " .. i .. " glyph " .. def.g .. " vs " .. d.g)
    local want, got = MU.colors[d.c], CK.COLORS[d.c]
    for j = 1, 3 do near(got[j], want[j], "colour " .. d.c .. " channel " .. j) end
    local k = CK.keys[i]
    check(k.glyph.tex:find("glyph_hud_" .. d.g .. ".tga", 1, true), "key " .. i .. " glyph texture " .. tostring(k.glyph.tex))
    check(#k.arcs == MU.RING_N, "key " .. i .. " ring has " .. #k.arcs .. " arcs")
    for n = 1, MU.RING_N do
        check(k.arcs[n].tex:find(string.format("hud_key_ring_%02d.tga", n - 1), 1, true), "arc " .. n .. " texture")
    end
end
""")

case("key_body_uses_the_cut_plate_set")(r"""
local CK = boot({})
local T = FS.Theme
local k = CK.keys[1]
check(k.body.tex == T.SLICE_CUT2_BUTTON_TEXTURE, "plate texture")
check(k.edge.tex == T.SLICE_CUT2_OUTLINE_TEXTURE, "edge texture")
check(k.wash.tex == T.SLICE_CUT2_FILL_TEXTURE and k.wash.blend == "ADD", "wash is the ADD fill")
check(k.glow.tex == T.SLICE_CUT2_GLOW_TEXTURE, "halo texture")
eq(k.body.sliceMargins[1], T.SLICE_CUT_MARGIN, "plate margin is the chamfer")
eq(k.glow.sliceMargins[1], T.SLICE_CUT2_GLOW_MARGIN, "halo margin is pad + chamfer")
""")

case("player_facing_key_text_says_cast_bar_never_tape")(r"""
local CK = boot({})
for _, def in ipairs(CK.DEFS) do
    check(not def.n:lower():find("tape", 1, true), def.key .. " name says tape: " .. def.n)
    check(not def.d:lower():find("tape", 1, true), def.key .. " description says tape: " .. def.d)
end
local function desc(key) for _, def in ipairs(CK.DEFS) do if def.key == key then return def.d end end end
check(desc("you") == "Your cast bar and timer box", "you: " .. tostring(desc("you")))
check(desc("tgt") == "Target cast bar, kick and lock state", "tgt: " .. tostring(desc("tgt")))
check(desc("shard") == "Held shards under your cast bar", "shard: " .. tostring(desc("shard")))
""")

# ---------------------------------------------------------------------------------------
# Clicks and state
# ---------------------------------------------------------------------------------------

case("click_toggles_the_right_piece")(r"""
local CK, G = boot({})
-- one key per console piece; a piece with no key (the My buffs plate) has no click to test
for _, def in ipairs(CK.DEFS) do
    local piece = def.key
    local k = keyOf(CK, piece)
    for _, other in ipairs(G.PIECES) do check(G.IsPieceOn(other), "all pieces start on") end
    click(k)
    check(not G.IsPieceOn(piece), "clicking " .. piece .. " did not turn it off")
    for _, other in ipairs(G.PIECES) do
        if other ~= piece then check(G.IsPieceOn(other), "clicking " .. piece .. " also changed " .. other) end
    end
    check(FS.Config.Get("gunsight.pieces." .. piece) == false, piece .. " off was not saved")
    click(k)
    check(G.IsPieceOn(piece), "clicking " .. piece .. " again did not turn it on")
end
""")

case("initial_state_follows_the_saved_pieces")(r"""
local CK, G = boot({ db = { gunsight = { pieces = { dot = false, tgt = false } } } })
check(keyOf(CK, "dot").phase == "off" and keyOf(CK, "tgt").phase == "off", "saved off keys start off")
check(keyOf(CK, "you").phase == "on", "a piece that is on starts on")
check(OnUpdates() == 0, "the initial sync must not animate")
check(keyOf(CK, "dot").led.vcolor[4] == 0 and keyOf(CK, "you").led.vcolor[4] == 1, "LED lit only on the on keys")
""")

case("fsgun_piece_commands_move_the_keys")(r"""
local CK, G = boot({})
SlashCmdList["FSGUN"]("piece shard off")
check(keyOf(CK, "shard").phase == "outage" or keyOf(CK, "shard").phase == "off", "/fsgun piece shard off did not reach the key")
Advance(1500)
check(keyOf(CK, "shard").phase == "off", "the key is not off after the outage")
SlashCmdList["FSGUN"]("piece shard on")
check(keyOf(CK, "shard").phase == "on", "/fsgun piece shard on did not reach the key")
""")

case("look_follows_state_hover_and_press")(r"""
local CK, G = boot({})
local k = keyOf(CK, "next")
local c = CK.COLORS.gold
-- lit
check(k.led.vcolor[4] == 1, "lit LED")
near(k.edge.vcolor[4], 0.95, "lit edge alpha"); near(k.glow.vcolor[4], 0.34, "lit halo alpha")
near(k.glyphGlow.vcolor[4], 0.5, "lit glyph glow")
near(k.glyph.vcolor[1], c[1] * 0.88 + 0.243 * 0.0 + (0xf3 / 255) * 0.12, "lit glyph red (key colour 88% toward white)")
-- hover and press (pink halo, pink wash)
k.btn.scripts.OnEnter(k.btn)
near(k.glow.vcolor[2], 0x2e / 255, "hover halo is pink"); near(k.glow.vcolor[4], 0.7, "hover halo alpha"); near(k.wash.vcolor[4], 0.15, "hover wash")
k.btn.scripts.OnMouseDown(k.btn)
near(k.glow.vcolor[4], 0.5, "pressed halo alpha"); near(k.wash.vcolor[4], 0.3, "pressed wash")
k.btn.scripts.OnMouseUp(k.btn)
k.btn.scripts.OnLeave(k.btn)
near(k.wash.vcolor[4], 0, "no wash at rest"); near(k.glow.vcolor[4], 0.34, "halo back to lit")
-- off
SlashCmdList["FSGUN"]("piece next off")
Advance(1500)
near(k.edge.vcolor[4], 0.45, "off edge alpha"); near(k.glow.vcolor[4], 0.18, "off halo alpha")
near(k.led.vcolor[4], 0, "LED dark when off")
near(k.glyph.vcolor[1], 0x5a / 255, "off glyph red"); near(k.glyph.vcolor[3], 0x70 / 255, "off glyph blue")
near(k.glyphGlow.vcolor[4], 0, "no glyph glow when off")
""")

# ---------------------------------------------------------------------------------------
# Tooltip
# ---------------------------------------------------------------------------------------

case("tooltip_shows_name_state_and_description")(r"""
local CK, G = boot({})
for i, d in ipairs(MU.defs) do
    local k = CK.keys[i]
    k.btn.scripts.OnEnter(k.btn)
    check(GameTooltip.shown and GameTooltip.owner == k.btn, "tooltip not shown on key " .. i)
    check(GameTooltip.lines[1].text == d.n, "first line is the name, got " .. tostring(GameTooltip.lines[1].text))
    check(GameTooltip.lines[1].right == "ON", "state word is ON while the piece is on")
    check(GameTooltip.lines[2].text == reword(d.d), "second line is the mockup description (cast bar wording), got " .. tostring(GameTooltip.lines[2].text))
    check(#GameTooltip.lines == 2, "tooltip carries more than name, state and description")
    check(GameTooltip.points[1][2] == k.btn, "tooltip anchored to the key")
    local corner = GameTooltip.points[1][1]
    if i <= 3 then check(corner == "BOTTOMLEFT", "keys 1 to 3 left align the tooltip") elseif i > 6 then check(corner == "BOTTOMRIGHT", "keys 7 and 8 right align it") else check(corner == "BOTTOM", "middle keys centre it") end
    k.btn.scripts.OnLeave(k.btn)
    check(not GameTooltip.shown, "tooltip stays after leaving key " .. i)
end
""")

case("tooltip_state_word_follows_a_click")(r"""
local CK, G = boot({})
local k = keyOf(CK, "prc")
k.btn.scripts.OnEnter(k.btn)
click(k)
check(GameTooltip.shown and GameTooltip.lines[1].right == "OFF", "tooltip still says ON after the click")
click(k)
check(GameTooltip.lines[1].right == "ON", "tooltip still says OFF after the second click")
""")

STR_EQ = r"""
local function eq(a, b, msg)
    if type(a) == "number" and type(b) == "number" then near(a, b, msg) elseif a ~= b then
        error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2)
    end
end
"""

case("the_paladin_dot_key_tooltip_uses_the_profile_dotlabel")(STR_EQ + r"""
local CK = boot({ profile = "PALADIN" })
local k = keyOf(CK, "dot")
check(k.btn:IsShown(), "the paladin shows the dot key")
k.btn.scripts.OnEnter(k.btn)
check(GameTooltip.shown and GameTooltip.owner == k.btn, "tooltip on the dot key")
eq(GameTooltip.lines[1].text, FS.HudProfiles.PALADIN.dotLabel.n, "title is dotLabel.n")
eq(GameTooltip.lines[1].text, "Target side", "the title is Target side")
eq(GameTooltip.lines[2].text, FS.HudProfiles.PALADIN.dotLabel.d, "description is dotLabel.d")
eq(GameTooltip.lines[2].text, "Target debuffs and the Seal module beside the target cast bar", "the description names the Seal module")
eq(GameTooltip.lines[1].right, "ON", "the state word is still there")
eq(#GameTooltip.lines, 2, "name, state and description only")
click(k)
eq(GameTooltip.lines[1].right, "OFF", "the state word follows a click")
eq(GameTooltip.lines[1].text, "Target side", "and the title stays")
k.btn.scripts.OnLeave(k.btn)
-- the other keys keep their own text
for _, piece in ipairs({ "you", "next", "tgt", "prc", "party" }) do
    local o = keyOf(CK, piece)
    local def
    for _, d in ipairs(MU.defs) do if d.piece == piece then def = d end end
    o.btn.scripts.OnEnter(o.btn)
    eq(GameTooltip.lines[1].text, def.n, piece .. " title is the mockup's")
    eq(GameTooltip.lines[2].text, reword(def.d), piece .. " description is the mockup's")
    o.btn.scripts.OnLeave(o.btn)
end
""")

case("the_warlock_and_priest_dot_key_tooltip_is_unchanged")(STR_EQ + r"""
local dotDef
for _, d in ipairs(MU.defs) do if d.piece == "dot" then dotDef = d end end
for _, name in ipairs({ "WARLOCK", "PRIEST" }) do
    local CK = boot({ profile = name })
    check(FS.HudProfiles[name].dotLabel == nil, name .. " has no dotLabel")
    local k = keyOf(CK, "dot")
    k.btn.scripts.OnEnter(k.btn)
    eq(GameTooltip.lines[1].text, dotDef.n, name .. " title")
    eq(GameTooltip.lines[2].text, dotDef.d, name .. " description")
    eq(GameTooltip.lines[1].text, "Target side", name .. " says Target side")
    k.btn.scripts.OnLeave(k.btn)
end
""")

case("the_dot_label_follows_the_profile_as_it_resolves")(STR_EQ + r"""
local CK = boot({ profile = false })
local k = keyOf(CK, "dot")
check(k.btn:IsShown(), "no profile: the dot key still shows, Target debuffs applies to every class")
local dotDef
for _, d in ipairs(MU.defs) do if d.piece == "dot" then dotDef = d end end
-- the paladin resolves late: the key appears, and its tooltip reads the label at once
HUD_PROFILE = FS.HudProfiles.PALADIN
fire("PLAYER_ENTERING_WORLD")
check(k.btn:IsShown(), "the dot key is still shown with the paladin profile")
k.btn.scripts.OnEnter(k.btn)
eq(GameTooltip.lines[2].text, FS.HudProfiles.PALADIN.dotLabel.d, "label after a late paladin profile")
k.btn.scripts.OnLeave(k.btn)
-- a re-seat under another profile swaps the text back (nothing is cached on the key)
HUD_PROFILE = FS.HudProfiles.WARLOCK
FS.ActionBars.Publish()
k.btn.scripts.OnEnter(k.btn)
eq(GameTooltip.lines[1].text, dotDef.n, "default title under the warlock profile")
eq(GameTooltip.lines[2].text, dotDef.d, "default description under the warlock profile")
k.btn.scripts.OnLeave(k.btn)
HUD_PROFILE = FS.HudProfiles.PALADIN
FS.ActionBars.Publish()
k.btn.scripts.OnEnter(k.btn)
eq(GameTooltip.lines[2].text, FS.HudProfiles.PALADIN.dotLabel.d, "and back")
k.btn.scripts.OnLeave(k.btn)
""")

case("a_partial_or_bad_dotlabel_falls_back_field_by_field")(STR_EQ + r"""
local dotDef
for _, d in ipairs(MU.defs) do if d.piece == "dot" then dotDef = d end end
local function tip(profile)
    local CK = boot({ profile = profile })
    local k = keyOf(CK, "dot")
    check(k.btn:IsShown(), "the dot key shows for the test profile")
    k.btn.scripts.OnEnter(k.btn)
    local a, b = GameTooltip.lines[1].text, GameTooltip.lines[2].text
    k.btn.scripts.OnLeave(k.btn)
    return a, b
end
local a, b = tip({ dots = { x = {} }, dotLabel = { n = "Chamber", d = "Words" } })
eq(a, "Chamber", "a profile with dots and a label uses the label (data driven)"); eq(b, "Words", "description")
a, b = tip({ dots = { x = {} }, dotLabel = { n = "Only name" } })
eq(a, "Only name", "n alone is used"); eq(b, dotDef.d, "d falls back")
a, b = tip({ dots = { x = {} }, dotLabel = { d = "Only desc" } })
eq(a, dotDef.n, "n falls back"); eq(b, "Only desc", "d alone is used")
a, b = tip({ dots = { x = {} }, dotLabel = { n = "", d = 5 } })
eq(a, dotDef.n, "an empty string falls back"); eq(b, dotDef.d, "a number falls back")
a, b = tip({ dots = { x = {} }, dotLabel = "Seal module" })
eq(a, dotDef.n, "a non table label falls back"); eq(b, dotDef.d, "and so does its description")
a, b = tip({ dots = { x = {} }, dotLabel = {} })
eq(a, dotDef.n, "an empty label falls back"); eq(b, dotDef.d, "both fields")
a, b = tip({ dots = { x = {} }, dotLabel = 5 })
eq(a, dotDef.n, "a number label falls back (indexing it would throw)"); eq(b, dotDef.d, "and so does its description")
a, b = tip({ dots = { x = {} }, dotLabel = true })
eq(a, dotDef.n, "a boolean label falls back"); eq(b, dotDef.d, "and so does its description")
-- only the dot key reads dotLabel
local CK = boot({ profile = { dots = { x = {} }, rotation = { { cast = "x", when = {} } }, dotLabel = { n = "Chamber", d = "Words" } } })
local nx = keyOf(CK, "next")
nx.btn.scripts.OnEnter(nx.btn)
eq(GameTooltip.lines[1].text, "Next Cast", "the next key ignores dotLabel")
nx.btn.scripts.OnLeave(nx.btn)
""")

# ---------------------------------------------------------------------------------------
# Animation
# ---------------------------------------------------------------------------------------

case("no_onupdate_at_rest")(r"""
local CK = boot({})
check(OnUpdates() == 0, "an OnUpdate is running at rest: " .. OnUpdates())
for _, k in ipairs(CK.keys) do check(not k.ringShown, "ring visible at rest on " .. k.key) end
""")

case("ignite_shows_the_ring_with_one_onupdate_then_clears")(r"""
local CK, G = boot({ db = { gunsight = { pieces = { you = false } } } })
local k = keyOf(CK, "you")
check(k.phase == "off", "starts off")
click(k)
check(k.phase == "on", "ignite turns the key on at once")
check(OnUpdates() == 1, "exactly one OnUpdate while animating, got " .. OnUpdates())
check(CK.IsAnimating(), "IsAnimating")
Advance(16)
check(k.ringShown, "the ring shows on the first frame of the ignite")
Advance(100)
check(k.ringShown and OnUpdates() == 1, "still animating at 100 ms")
-- a ring arc takes the key colour at some point of the ignite
local c = CK.COLORS.cyan
local lit = 0
for n = 1, #k.arcs do if k.arcs[n].vcolor and k.arcs[n].vcolor[4] > 0.14 then lit = lit + 1 end end
check(lit > 0, "no arc is above the faint unlit ring during the ignite")
Advance(2000)
check(not k.ringShown, "the ring must be gone after the ignite and its 0.4 s fade")
check(OnUpdates() == 0, "the OnUpdate must be cleared when the animation is over, got " .. OnUpdates())
check(not CK.IsAnimating(), "IsAnimating after rest")
""")

case("outage_runs_one_second_and_holds_the_lit_look")(r"""
local CK, G = boot({})
local k = keyOf(CK, "dot")
click(k)
check(not G.IsPieceOn("dot"), "the piece is off at once")
check(k.phase == "outage", "the key enters the outage, got " .. k.phase)
check(OnUpdates() == 1, "one OnUpdate")
Advance(16)
check(k.ringShown, "ring up on the first frame of the outage")
near(k.led.vcolor[4], 1, "the lit look holds through the outage")
Advance(900)
check(k.phase == "outage", "still in the outage at 0.9 s")
near(k.led.vcolor[4], 1, "lit look at 0.9 s")
Advance(200)
check(k.phase == "off", "the outage lasts about 1.0 s, phase is " .. k.phase .. " at 1.1 s")
near(k.led.vcolor[4], 0, "dark after the outage")
check(k.ringShown, "the ring eases out for 0.4 s after the outage")
Advance(600)
check(not k.ringShown and OnUpdates() == 0, "ring gone and OnUpdate cleared 1.7 s after the click")
""")

case("flip_mid_outage_reignites")(r"""
local CK, G = boot({})
local k = keyOf(CK, "buff")
click(k)
Advance(300)
check(k.phase == "outage", "outage underway")
click(k)
check(G.IsPieceOn("buff") and k.phase == "on", "turning it back on mid outage ignites")
Advance(2500)
check(k.phase == "on" and OnUpdates() == 0 and not k.ringShown, "settles on with nothing running")
""")

case("several_keys_share_one_driver")(r"""
local CK, G = boot({})
click(keyOf(CK, "you")); click(keyOf(CK, "tgt")); click(keyOf(CK, "dot"))
check(OnUpdates() == 1, "three live rings must share ONE OnUpdate, got " .. OnUpdates())
Advance(3000)
check(OnUpdates() == 0, "nothing running after all three finish")
""")

case("reduced_motion_snaps")(r"""
local CK, G = boot({ db = { reducedMotion = true } })
local k = keyOf(CK, "you")
click(k)
check(k.phase == "off" and OnUpdates() == 0 and not k.ringShown, "reduced motion: off at once, no ring, no OnUpdate")
click(k)
check(k.phase == "on" and OnUpdates() == 0 and not k.ringShown, "reduced motion: on at once")
""")

case("a_hidden_key_snaps_without_animating")(r"""
local CK, G = boot({})
SlashCmdList["FSCONSOLE"]("off")
local k = keyOf(CK, "next")
check(not k.btn:IsVisible(), "key is hidden with the console off")
G.SetPiece("next", false)
check(k.phase == "off" and OnUpdates() == 0, "a hidden key must snap, no OnUpdate")
SlashCmdList["FSCONSOLE"]("on")
check(k.btn:IsVisible(), "key is back with the console")
check(k.led.vcolor[4] == 0, "and shows the state it missed")
""")

case("missing_fx_still_toggles")(r"""
local CK, G = boot({ noFx = true })
local k = keyOf(CK, "you")
click(k)
check(not G.IsPieceOn("you") and k.phase == "off" and OnUpdates() == 0, "without the Fx the key snaps")
""")

case("arc_seeds_come_from_the_mockup")(r"""
local CK = boot({})
local fx = FS.ChevronCastBar.Fx
for i, k in ipairs(CK.keys) do
    for n = 1, #k.segs do
        local want = fx.NewSeg(9000 + (i - 1) * 977 + (n - 1) * 131)
        near(k.segs[n].ign, want.ign, "ignite length of key " .. i .. " arc " .. n)
        near(k.segs[n].a, (n - 1) / MU.RING_N, "arc start along the ring")
    end
end
near(fx.INTR_MS, MU.INTR_MS, "outage length")
""")

# ---------------------------------------------------------------------------------------
# Rescale, combat, visibility
# ---------------------------------------------------------------------------------------

case("rescale_reseats_and_creates_nothing")(r"""
local CK = boot({ height = 1440 })
local frames, textures = #FRAMES, #TEXTURES
SetScreen(1200)
fire("UI_SCALE_CHANGED")
FS.ActionBars.Publish()
local s = FS.Layout.Scale()
near(s, 1200 / 1440, "scale")
for i, k in ipairs(CK.keys) do
    local r = FS.Console.KeyRect(i - 1, s)
    local _, _, _, x, y = k.btn:GetPoint(1)
    eq(x, r.x, "key " .. i .. " x after the rescale"); eq(y, -r.y, "key " .. i .. " y after the rescale")
    eq(k.btn:GetWidth(), 34 * s, "key " .. i .. " width after the rescale")
    eq(k.art:GetScale(), s, "art scale after the rescale")
end
check(#FRAMES == frames, "a rescale created " .. (#FRAMES - frames) .. " frames")
check(#TEXTURES == textures, "a rescale created " .. (#TEXTURES - textures) .. " textures")
SetScreen(1080)
fire("DISPLAY_SIZE_CHANGED"); FS.ActionBars.Publish()
check(#FRAMES == frames and #TEXTURES == textures, "a second rescale created something")
""")

case("rescale_in_combat_waits_for_regen")(r"""
local CK = boot({ height = 1440 })
IN_COMBAT = true
SetScreen(1200)
fire("UI_SCALE_CHANGED")
local k = CK.keys[1]
local before = k.btn.calls.SetPoint
local _, _, _, x0 = k.btn:GetPoint(1)
FS.ActionBars.Publish()
check(k.btn.calls.SetPoint == before, "a key was re-anchored in combat")
near(k.art:GetScale(), 1, "art scale must wait too")
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
local s = FS.Layout.Scale()
local _, _, _, x1 = k.btn:GetPoint(1)
eq(x1, FS.Console.KeyRect(0, s).x, "the key is re-seated at regen")
eq(k.art:GetScale(), s, "art scale at regen")
""")

case("click_works_in_combat_and_touches_nothing_protected")(r"""
local CK, G = boot({ party = true, partyProtected = true })
IN_COMBAT = true
click(keyOf(CK, "you"))
check(not G.IsPieceOn("you"), "the click did nothing in combat")
Advance(200)
check(#BLOCKED == 0, "a protected action was attempted in combat")
click(keyOf(CK, "party"))
check(not G.IsPieceOn("party"), "party off in combat")
near(FS.partyContainer:GetAlpha(), 0, "the protected party container goes to alpha 0 in combat")
check(FS.partyContainer:IsShown(), "and is not Hidden in combat")
check(#BLOCKED == 0, "Show/Hide/EnableMouse was attempted on the protected frame, " .. table.concat(BLOCKED, ","))
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
check(not FS.partyContainer:IsShown(), "the real Hide runs after combat")
""")

case("party_container_becomes_piece_party")(r"""
local CK, G = boot({ party = true })
click(keyOf(CK, "party"))
Advance(10)
finishAnims()
check(not FS.partyContainer:IsShown() or FS.partyContainer:GetAlpha() == 0, "party key did not hide the party frames")
click(keyOf(CK, "party"))
finishAnims()
check(FS.partyContainer:IsShown() and FS.partyContainer:GetAlpha() == 1, "party key did not bring the party frames back")
""")

case("party_without_a_container_still_toggles_state")(r"""
local CK, G = boot({})
click(keyOf(CK, "party"))
check(not G.IsPieceOn("party"), "party state toggles without a container")
""")

case("party_container_that_appears_later_is_registered")(r"""
local CK, G = boot({})
FS.partyContainer = CreateFrame("Frame", "ForeverSTUwavePartyContainer", UIParent)
fire("PLAYER_REGEN_ENABLED")
click(keyOf(CK, "party"))
finishAnims()
check(not FS.partyContainer:IsShown() or FS.partyContainer:GetAlpha() == 0, "late container not driven by the key")
""")

case("hidden_when_the_console_is_off")(r"""
local CK = boot({})
for _, k in ipairs(CK.keys) do check(k.btn:IsVisible(), "key visible with the console on") end
SlashCmdList["FSCONSOLE"]("off")
for _, k in ipairs(CK.keys) do check(not k.btn:IsVisible(), "key " .. k.key .. " still visible with the console off") end
SlashCmdList["FSCONSOLE"]("on")
for _, k in ipairs(CK.keys) do check(k.btn:IsVisible(), "key " .. k.key .. " not back with the console") end
""")

case("console_off_at_login_builds_the_keys_when_it_comes_on")(r"""
local CK = boot({ consoleOff = true, db = { consoleEnabled = false } })
check(not CK.IsBuilt(), "keys were built before the Console had a tab")
SlashCmdList["FSCONSOLE"]("on")
check(CK.IsBuilt() and #CK.keys == 8, "keys not built once the Console is on")
for _, k in ipairs(CK.keys) do check(k.btn:IsVisible(), "key " .. k.key .. " not visible") end
""")

case("gunsight_disabled_builds_nothing_and_leaves_party_alone")(r"""
local CK, G = boot({ party = true, db = { gunsight = { enabled = false, pieces = { party = false } } } })
check(not G.IsEnabled(), "gunsight is disabled")
check(not CK.IsBuilt(), "keys were built with the Gunsight disabled")
check(FS.partyContainer:IsShown() and FS.partyContainer:GetAlpha() == 1, "the party frames were touched with the Gunsight disabled")
for _, f in ipairs(FRAMES) do check(not (f.name and f.name:find("^FSConsoleKey")), "a key frame exists: " .. tostring(f.name)) end
""")

case("fsgun_toggle_at_runtime_waits_for_a_reload")(r"""
local CK, G = boot({ party = true })
SlashCmdList["FSGUN"]("off")
FS.ActionBars.Publish()
fire("PLAYER_REGEN_ENABLED")
check(CK.keys[1].btn:IsVisible(), "keys hid on /fsgun off: the Gunsight pieces stay up until a reload, so the keys must too")
click(keyOf(CK, "you"))
check(not G.IsPieceOn("you"), "a key still works after /fsgun off")
SlashCmdList["FSGUN"]("on")
FS.ActionBars.Publish()
check(CK.keys[1].btn:IsVisible(), "keys changed on /fsgun on")
""")

case("fsgun_on_after_a_disabled_login_builds_nothing_until_a_reload")(r"""
local CK, G = boot({ party = true, db = { gunsight = { enabled = false, pieces = {} } } })
check(not CK.IsBuilt(), "keys built with the Gunsight disabled at login")
SlashCmdList["FSGUN"]("on")
FS.ActionBars.Publish()
fire("PLAYER_REGEN_ENABLED")
check(FS.Config.Get("gunsight.enabled") == true, "/fsgun on saves the setting")
check(not G.IsEnabled(), "the live state is fixed at load, so a built UI never changes under it")
check(not CK.IsBuilt(), "/fsgun on built the keys without a reload")
for _, f in ipairs(FRAMES) do check(not (f.name and f.name:find("^FSConsoleKey")), "a key frame exists: " .. tostring(f.name)) end
check(FS.partyContainer:IsShown() and FS.partyContainer:GetAlpha() == 1, "the party frames were touched after a disabled login")
G.SetPiece("party", false, true)
check(FS.partyContainer:IsShown() and FS.partyContainer:GetAlpha() == 1, "piece party was registered after a disabled login")
""")

case("party_registration_retries_once_on_the_next_frame")(r"""
local timers = {}
C_Timer = { After = function(_, fn) timers[#timers + 1] = fn end }
local CK, G = boot({})
check(#timers == 0, "a timer was scheduled before any regen")
fire("PLAYER_REGEN_ENABLED")
check(#timers == 1, "a nil container at regen schedules one retry, got " .. #timers)
fire("PLAYER_REGEN_ENABLED")
check(#timers == 1, "a second regen must not stack another retry, got " .. #timers)
FS.partyContainer = CreateFrame("Frame", "ForeverSTUwavePartyContainer", UIParent)
for _, fn in ipairs(timers) do fn() end
click(keyOf(CK, "party"))
finishAnims()
check(not FS.partyContainer:IsShown() or FS.partyContainer:GetAlpha() == 0, "the retry did not register the container")
""")

case("party_registers_lazily_on_the_first_click_when_the_retry_missed")(r"""
C_Timer = nil
local CK, G = boot({})
fire("PLAYER_REGEN_ENABLED")   -- container still nil, and no C_Timer to retry with: must not throw
FS.partyContainer = CreateFrame("Frame", "ForeverSTUwavePartyContainer", UIParent)
click(keyOf(CK, "party"))
finishAnims()
check(not G.IsPieceOn("party"), "party state flipped")
check(not FS.partyContainer:IsShown() or FS.partyContainer:GetAlpha() == 0, "the click did not register the container and apply the state")
""")

case("hide_clears_hover_and_down_and_repaints_the_look")(r"""
local CK = boot({})
local k = keyOf(CK, "you")
k.btn.scripts.OnEnter(k.btn)
k.btn.scripts.OnMouseDown(k.btn)
near(k.glow.vcolor[4], 0.5, "pressed halo before the hide")
k.btn.scripts.OnHide(k.btn)
check(not k.hover and not k.down, "hover/down not cleared on hide")
near(k.glow.vcolor[4], 0.34, "the halo was not repainted to the resting look on hide")
near(k.wash.vcolor[4], 0, "the wash was not repainted on hide")
""")

case("geometry_after_login_builds_the_keys_too")(r"""
local CK = boot({ geometryFirst = false })
check(CK.IsBuilt() and #CK.keys == 8, "keys must build when the Console geometry arrives after the Gunsight is ready")
""")


# ---------------------------------------------------------------------------------------
# Keys that hide when their piece has nothing for the class, and the tab that fits the rest
# ---------------------------------------------------------------------------------------

SHOWN_HELPERS = r"""
-- numbers compare within the harness epsilon, anything else exactly
local function eq(a, b, msg)
    if type(a) == "number" and type(b) == "number" then near(a, b, msg) elseif a ~= b then
        error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2)
    end
end
local function shownList(CK)
    local out = {}
    for _, k in ipairs(CK.keys) do if k.btn:IsShown() then out[#out + 1] = k.key end end
    return out
end
local function joined(t) return table.concat(t, ",") end
-- the tab and the keys for the count n, all read off the real frames
local function checkFits(CK, n, label)
    local s = FS.Layout.Scale()
    local M = MU
    local shown = {}
    for _, k in ipairs(CK.keys) do if k.btn:IsShown() then shown[#shown + 1] = k end end
    eq(#shown, n, label .. ": shown key count")
    eq(CK.ShownCount(), n, label .. ": ShownCount")
    eq(FS.Console.GetKeyCount(), n, label .. ": the Console is sized for the shown count")
    local tab = FS.Console.tab
    eq(tab:GetWidth(), (FS.Console.TabWidth(n) - FS.Console.C.FOOT) * s, label .. ": tab width follows the shown count")
    local last
    for slot, k in ipairs(shown) do
        local _, rel, _, x, y = k.btn:GetPoint(1)
        eq(x, FS.Console.KeyRect(slot - 1, s).x, label .. ": " .. k.key .. " sits in slot " .. (slot - 1))
        eq(y, -FS.Console.KeyRect(slot - 1, s).y, label .. ": " .. k.key .. " row")
        if last then
            eq(x - last, (M.KEY_W + M.KEY_GAP) * s, label .. ": gap before " .. k.key .. " is the even gap")
        end
        last = x
    end
    -- the same padding to the right edge of the tab, whatever the count
    local lastRect = FS.Console.KeyRect(n - 1, s)
    eq(tab:GetWidth() - (lastRect.x + lastRect.w), FS.Console.C.TP * s, label .. ": 15 padding right of the last key")
end
"""

case("warlock_profile_shows_all_eight_keys")(SHOWN_HELPERS + r"""
local CK = boot({ profile = "WARLOCK" })
check(#CK.keys == 8, "eight keys are built")
eq(joined(shownList(CK)), "you,next,shard,buff,tgt,dot,prc,party", "all eight, in order")
checkFits(CK, 8, "warlock")
eq(FS.Console.TabWidth(8), MU.TAB_DW, "the tab is the mockup's TAB_DW at eight keys")
""")

case("priest_hides_shard_and_prc_and_repacks")(SHOWN_HELPERS + r"""
local CK = boot({ profile = "PRIEST" })
eq(joined(shownList(CK)), "you,next,buff,tgt,dot,party", "priest has no shards and no procs")
checkFits(CK, 6, "priest")
-- the repack: consecutive slots, nothing left where the hidden keys were
local want = { you = 0, next = 1, buff = 2, tgt = 3, dot = 4, party = 5 }
for piece, slot in pairs(want) do
    local k = keyOf(CK, piece)
    eq(k.slot, slot, piece .. " slot")
end
check(keyOf(CK, "shard").slot == nil and keyOf(CK, "prc").slot == nil, "hidden keys hold no slot")
-- tooltips follow the slot, not the DEFS index: slots 0 to 2 left, the last two right
local function corner(piece)
    local k = keyOf(CK, piece)
    k.btn.scripts.OnEnter(k.btn)
    local c = GameTooltip.points[1][1]
    k.btn.scripts.OnLeave(k.btn)
    return c
end
eq(corner("you"), "BOTTOMLEFT", "slot 0"); eq(corner("buff"), "BOTTOMLEFT", "slot 2")
eq(corner("tgt"), "BOTTOM", "slot 3"); eq(corner("dot"), "BOTTOMRIGHT", "slot 4"); eq(corner("party"), "BOTTOMRIGHT", "slot 5")
-- the hit areas still tile the (even) pitch among the shown keys
local s = FS.Layout.Scale()
local shown = {}
for _, k in ipairs(CK.keys) do if k.btn:IsShown() then shown[#shown + 1] = k end end
for i = 1, #shown - 1 do
    local a, b = shown[i].btn.hit, shown[i + 1].btn.hit
    eq(-a.r + -b.l, MU.KEY_GAP * s, "hit areas of shown keys " .. i .. " and " .. (i + 1) .. " tile the gap")
end
""")

case("no_profile_hides_shard_prc_next_and_buff_but_the_dot_key_stays")(SHOWN_HELPERS + r"""
local CK = boot({ profile = false })
check(HUD_PROFILE == nil, "no profile")
-- shard, prc, next and buff have nothing without a profile; the dot key (Target side) needs no profile
eq(joined(shownList(CK)), "you,tgt,dot,party", "the keys that need no profile")
checkFits(CK, 4, "no profile")
eq(FS.HudProfiles.ROGUE, nil, "ROGUE has no HUD profile entry, so it takes this same path")
""")

case("a_mage_gets_the_dot_key")(SHOWN_HELPERS + r"""
-- a Mage has no HUD profile (FS.HudProfiles only holds the priest, warlock and paladin)
local CK = boot({ profile = false })
eq(FS.HudProfiles.MAGE, nil, "no mage profile")
local k = keyOf(CK, "dot")
check(k.btn:IsShown(), "key 6 shows for a mage")
eq(k.slot, 2, "and it takes its place after you and the target cast bar")
eq(CK.KeyShown("dot", nil), true, "KeyShown says so with no profile")
""")

case("paladin_profile_shows_next_prc_and_the_dot_key_for_its_seal_slot")(SHOWN_HELPERS + r"""
local CK = boot({ profile = "PALADIN" })
check(HUD_PROFILE ~= nil, "the paladin has a profile")
-- the cooldown tracker: a one rule rotation (next) and two sided procs (prc); no shards or buffs. The DoT slot
-- is a class slot: the paladin has no DoTs but a seal table, so its key stays and toggles the target side areas.
eq(joined(shownList(CK)), "you,next,tgt,dot,prc,party", "next, dot and prc, no shard or buff")
checkFits(CK, 6, "paladin")
check(next(FS.HudProfiles.PALADIN.dots) == nil and type(FS.HudProfiles.PALADIN.seals) == "table",
      "the paladin profile has no dots and a seals table (the rule under test)")
""")

case("the_dot_key_never_reads_the_profile")(SHOWN_HELPERS + r"""
local CK = boot({ profile = "WARLOCK" })
-- Target debuffs applies to every class, so the key has no rule: ClassSlot is not consulted at all
local asked = 0
local real = FS.HudProfiles.ClassSlot
FS.HudProfiles.ClassSlot = function() asked = asked + 1; return nil end
eq(CK.KeyShown("dot", {}), true, "an empty profile")
eq(CK.KeyShown("dot", { dots = {} }), true, "no dots and no seals")
eq(CK.KeyShown("dot", FS.HudProfiles.PALADIN), true, "the paladin")
eq(CK.KeyShown("dot", nil), true, "no profile")
FS.HudProfiles.ClassSlot = nil
eq(CK.KeyShown("dot", { dots = {} }), true, "no helper")
FS.HudProfiles.ClassSlot = real
eq(asked, 0, "the shared class slot helper is never asked")
""")

case("a_profile_with_no_hud_fields_hides_each_key_by_its_own_rule")(SHOWN_HELPERS + r"""
local function shownFor(profile)
    local CK = boot({ profile = profile })
    return joined(shownList(CK))
end
eq(shownFor({}), "you,tgt,dot,party", "an empty profile has nothing for any profile key")
eq(shownFor({ resource = { shards = { item = 6265 } } }), "you,shard,tgt,dot,party", "shards need resource.shards")
eq(shownFor({ resource = {} }), "you,tgt,dot,party", "a resource without shards shows no shard key")
eq(shownFor({ procs = {} }), "you,tgt,dot,party", "empty procs: no key")
eq(shownFor({ procs = { x = { label = "X" } } }), "you,tgt,dot,party", "a proc with no side draws no rung, so no key")
eq(shownFor({ procs = { x = { side = "left" } } }), "you,tgt,dot,prc,party", "a proc with a side shows the key")
eq(shownFor({ rotation = {} }), "you,tgt,dot,party", "an empty rotation has no next cast")
eq(shownFor({ rotation = { { cast = "x", when = {} } } }), "you,next,tgt,dot,party", "a rotation shows the next key")
eq(shownFor({ selfBuffs = {} }), "you,tgt,dot,party", "no self buffs: no buff key")
eq(shownFor({ selfBuffs = { { spell = "x" } } }), "you,buff,tgt,dot,party", "self buffs show the buff key")
eq(shownFor({ dots = {} }), "you,tgt,dot,party", "no dots and no seals: the dot key still shows")
eq(shownFor({ dots = { x = {} } }), "you,tgt,dot,party", "dots show the dot key")
eq(shownFor({ seals = { order = { "sor" } } }), "you,tgt,dot,party", "a seals table alone shows the dot key")
eq(shownFor({ dots = {}, seals = { order = { "sor" } } }), "you,tgt,dot,party", "empty dots plus seals shows it")
eq(shownFor({ dots = { x = {} }, seals = { order = { "sor" } } }), "you,tgt,dot,party", "dots plus seals shows it once")
eq(shownFor({ seals = true }), "you,tgt,dot,party", "a seals value that is not a table: the dot key still shows")
eq(shownFor({ dotLabel = { n = "N", d = "D" } }), "you,tgt,dot,party", "a dotLabel alone: the dot key still shows")
eq(shownFor({ rotation = { { cast = "x", when = {} } } }), "you,next,tgt,dot,party", "the other keys keep their own rules")
local CK = boot({ profile = "WARLOCK" })
eq(CK.KeyShown("dot", { dots = {} }), true, "KeyShown: no dots, no seals still shows")
eq(CK.KeyShown("dot", { seals = {} }), true, "KeyShown: a seals table")
eq(CK.KeyShown("dot", nil), true, "KeyShown: no profile")
eq(CK.KeyShown("you", nil), true, "KeyShown: the always keys")
""")

case("even_spacing_at_8_6_and_4_keys")(SHOWN_HELPERS + r"""
local function gaps(CK)
    local s = FS.Layout.Scale()
    local xs = {}
    for _, k in ipairs(CK.keys) do
        if k.btn:IsShown() then local _, _, _, x = k.btn:GetPoint(1); xs[#xs + 1] = x end
    end
    local out = {}
    for i = 2, #xs do out[#out + 1] = xs[i] - xs[i - 1] - MU.KEY_W * s end
    return out
end
local four = {}   -- an empty profile: you, tgt, dot, party
for _, case in ipairs({ { 8, "WARLOCK" }, { 6, "PRIEST" }, { 4, four } }) do
    local n, profile = case[1], case[2]
    local CK = boot({ profile = profile })
    local g = gaps(CK)
    eq(#g, n - 1, n .. " keys have " .. (n - 1) .. " gaps")
    for i, gap in ipairs(g) do eq(gap, MU.KEY_GAP * FS.Layout.Scale(), n .. " keys: gap " .. i .. " is the even gap") end
    checkFits(CK, n, n .. " keys")
end
""")

case("a_hidden_key_is_not_shown_or_clickable_and_its_piece_is_untouched")(SHOWN_HELPERS + r"""
local CK, G = boot({ profile = "PRIEST", db = { gunsight = { pieces = { shard = false } } } })
local calls = 0
local realSet = G.SetPiece
G.SetPiece = function(...) calls = calls + 1; return realSet(...) end
for _, piece in ipairs({ "shard", "prc" }) do
    local k = keyOf(CK, piece)
    check(not k.btn:IsShown() and not k.btn:IsVisible(), piece .. " key is hidden")
end
-- hiding never wrote the piece state: shard stays as saved (off), prc stays on, SetPiece never called by a refresh
check(not G.IsPieceOn("shard") and G.IsPieceOn("prc"), "piece state is as saved")
CK.Refresh(); FS.ActionBars.Publish(); fire("PLAYER_REGEN_ENABLED"); fire("PLAYER_ENTERING_WORLD")
eq(calls, 0, "ConsoleKeys never calls Gunsight.SetPiece for visibility")
check(FS.Config.Get("gunsight.pieces.prc") ~= false, "prc was not saved off by hiding its key")
-- the piece still follows /fsgun while its key is hidden, and the key is right when it comes back
SlashCmdList["FSGUN"]("piece shard on")
check(keyOf(CK, "shard").phase == "on", "a hidden key still tracks its piece")
check(not keyOf(CK, "shard").btn:IsShown(), "and stays hidden")
-- a tooltip showing on a key goes with the key when a profile change hides it
HUD_PROFILE = FS.HudProfiles.WARLOCK
FS.ActionBars.Publish()
local shard = keyOf(CK, "shard")
check(shard.btn:IsShown(), "shard key is back with the warlock profile")
shard.btn.scripts.OnEnter(shard.btn)
check(GameTooltip.shown and GameTooltip.owner == shard.btn, "tooltip on the hovered key")
HUD_PROFILE = FS.HudProfiles.PRIEST
FS.ActionBars.Publish()
check(not shard.btn:IsShown(), "the priest profile hides the shard key again")
check(GameTooltip.owner ~= shard.btn and not GameTooltip.shown, "the tooltip left with the hidden key")
check(not shard.hover, "hover cleared with the hidden key")
""")

case("a_late_profile_reruns_the_visibility_on_every_hook")(SHOWN_HELPERS + r"""
local CK = boot({ profile = false })
eq(joined(shownList(CK)), "you,tgt,dot,party", "no profile yet")
HUD_PROFILE = FS.HudProfiles.PRIEST
fire("PLAYER_ENTERING_WORLD")
eq(joined(shownList(CK)), "you,next,buff,tgt,dot,party", "entering world picks the profile up")
checkFits(CK, 6, "priest after entering world")
HUD_PROFILE = FS.HudProfiles.WARLOCK
FS.ActionBars.Publish()
eq(joined(shownList(CK)), "you,next,shard,buff,tgt,dot,prc,party", "a geometry publish picks it up")
checkFits(CK, 8, "warlock after a publish")
HUD_PROFILE = nil
fire("PLAYER_REGEN_ENABLED")
eq(joined(shownList(CK)), "you,tgt,dot,party", "regen picks it up")
HUD_PROFILE = FS.HudProfiles.PRIEST
SetScreen(1200); fire("UI_SCALE_CHANGED"); FS.ActionBars.Publish()
checkFits(CK, 6, "priest after a rescale")
-- an unchanged profile does no work: no re-anchoring, no tab resize
local tab = FS.Console.tab
local setSize, setPoint = tab.calls.SetSize, CK.keys[1].btn.calls.SetPoint
fire("PLAYER_ENTERING_WORLD")
eq(tab.calls.SetSize, setSize, "an unchanged profile does not resize the tab")
eq(CK.keys[1].btn.calls.SetPoint, setPoint, "an unchanged profile does not re-anchor the keys")
""")

case("a_profile_change_in_combat_waits_for_regen")(SHOWN_HELPERS + r"""
local CK = boot({ profile = false })
local tab = FS.Console.tab
local setSize, setPoint = tab.calls.SetSize, CK.keys[1].btn.calls.SetPoint
IN_COMBAT = true
HUD_PROFILE = FS.HudProfiles.WARLOCK
fire("PLAYER_ENTERING_WORLD")
eq(joined(shownList(CK)), "you,tgt,dot,party", "nothing shown or hidden in combat")
eq(tab.calls.SetSize, setSize, "the tab is not resized in combat")
eq(CK.keys[1].btn.calls.SetPoint, setPoint, "keys are not re-anchored in combat")
eq(FS.Console.GetKeyCount(), 4, "the Console keeps the old count in combat")
check(#BLOCKED == 0, "nothing protected was touched in combat")
IN_COMBAT = false
fire("PLAYER_REGEN_ENABLED")
checkFits(CK, 8, "warlock after regen")
""")

case("the_console_off_hides_the_shown_keys_with_the_tab")(SHOWN_HELPERS + r"""
local CK = boot({ profile = "PRIEST" })
SlashCmdList["FSCONSOLE"]("off")
for _, k in ipairs(CK.keys) do check(not k.btn:IsVisible(), k.key .. " visible with the console off") end
SlashCmdList["FSCONSOLE"]("on")
local vis = {}
for _, k in ipairs(CK.keys) do if k.btn:IsVisible() then vis[#vis + 1] = k.key end end
eq(joined(vis), "you,next,buff,tgt,dot,party", "only the shown keys come back")
checkFits(CK, 6, "priest after the console came back")
""")


def static_checks(mu: dict) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    toc = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    try:
        i = toc.index("Modules/ActionBars/ConsoleKeys.lua")
        need = ("Core/Layout.lua", "Core/Theme.lua", "Core/ChevronCastBar.lua", "Modules/ActionBars/ActionBars.lua", "Modules/ActionBars/Console.lua", "Modules/CombatHud/Gunsight.lua")
        late = [n for n in need if toc.index(n) > i]
        out.append(("toc_places_consolekeys_after_what_it_uses",
                    None if not late else f"ConsoleKeys.lua must come after {late}"))
        out.append(("toc_places_hud_profiles_before_consolekeys",
                    None if toc.index("Modules/CombatHud/HudProfiles.lua") < i else "ConsoleKeys.lua must come after HudProfiles.lua (ClassSlot)"))
        out.append(("toc_keeps_gunsight_first_among_gunsight_files",
                    None if all(toc.index("Modules/CombatHud/Gunsight.lua") < n for n, ln in enumerate(toc)
                                if ln.startswith("Gunsight") and ln != "Modules/CombatHud/Gunsight.lua")
                    else "Gunsight.lua is no longer first among the Gunsight files"))
    except ValueError as e:
        out.append(("toc_places_consolekeys_after_what_it_uses", f"{e}"))
    raw = TOC.read_bytes()
    out.append(("toc_keeps_crlf", None if raw.count(b"\r\n") == raw.count(b"\n") else "toc has bare LF lines"))
    media = [f"hud_key_ring_{n:02d}.tga" for n in range(16)] + [
        f"glyph_hud_{g}.tga" for g in ("chev", "play", "diamond", "shield", "cross", "clock", "bolt", "group")]
    missing = [m for m in media if not (ADDON / "Media" / "Textures" / m).exists()]
    out.append(("media_exists", None if not missing else f"missing {missing}"))
    glyphs = {d["g"] for d in mu["defs"]}
    out.append(("every_mockup_glyph_has_a_file",
                None if all((ADDON / "Media" / "Textures" / f"glyph_hud_{g}.tga").exists() for g in glyphs) else "a glyph file is missing"))
    return out


def run_case(body: str, mu: dict, srcs: dict, theme_consts: str, theme_funcs: str) -> str | None:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(gh.MOCK)
    lua.execute(EXTRA)
    lua.execute(f"MU = {lua_literal(mu)}")
    g = lua.globals()
    for name, src in srcs.items():
        g[name] = src
    g.THEME_LINES = theme_consts
    g.THEME_FUNCS = theme_funcs
    runner = lua.eval(
        "function(src) local f, e = loadstring(src, '=case'); if not f then return false, e end; "
        "local ok, err = pcall(f); if ok then if #BLOCKED > 0 then return false, 'ADDON_ACTION_BLOCKED: ' "
        ".. table.concat(BLOCKED, ', ') end; return true, '' end; return false, tostring(err) end")
    ok, err = runner(PRELUDE + "\n" + body)
    return None if ok else str(err)


def main() -> int:
    mu = mockup_keys()
    failures = 0

    def report(name: str, err: str | None) -> None:
        nonlocal failures
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}\n      " + err.replace("\n", "\n      "))

    statics = static_checks(mu)
    if not KEYS_LUA.exists():
        report("consolekeys_file", f"{KEYS_LUA} does not exist")
        for name, _ in CASES:
            report(name, "ConsoleKeys.lua is missing")
        for name, err in statics:
            report(name, err)
        print(f"\n{failures} failed")
        return 1

    srcs = {name: path.read_text(encoding="utf-8") for name, path in SRC_FILES.items()}
    theme_consts = "\n".join(theme_lines())
    fns = theme_functions()
    theme_funcs = "\n".join(fns[n] for n in ("ApplyNineSlice", "AddSliceTexture"))
    for name, body in CASES:
        try:
            err = run_case(body, mu, srcs, theme_consts, theme_funcs)
        except LuaError as e:  # a mock or harness bug, not a pass
            err = f"harness error: {e}"
        report(name, err)
    for name, err in statics:
        report(name, err)

    total = len(CASES) + len(statics)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
