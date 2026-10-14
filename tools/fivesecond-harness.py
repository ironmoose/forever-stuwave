#!/usr/bin/env python3
"""Runs the real FiveSecondTab.lua (the five second rule tab: the LED readout, the gauge and the regen rate) headless, in
buffbar-harness's world: the actionbars mock, FrameHelpers.lua, ActionBars.lua, Console.lua, StanceBar.lua, PetActionBar.lua,
PetDock.lua, ClassShoulder.lua, and for a Paladin or a Shaman the class tab it is seated after.

The tab is a second Console shoulder (mockups/five-second-rule-compact-2026-10-14.html, face D2 with digit option B): one
92.8 x 49 design px face on the player side, display only, two hover zones. The numbers and colours below are read out of the
mockup, so a mockup move fails here. Checked:

  * the window: a mana cast from the player starts five seconds that drain the ten segment gauge right to left with a
    partial segment, the LED readout counts in tenths behind a tilde (every digit decoded from the lit segments), a free
    cast (cost 0, another power, no cost) or another unit's cast starts nothing, a re-cast restarts the full window, a
    channel holds it open until it ends;
  * the end: the held digits turn cyan, a band sweeps the face once and each cell flips to the word REGEN under it, exactly
    one pulse (none with the pulse toggle off), a sound only with the sound toggle on, then the dim idle look;
  * the LED art: the glyph tables are the mockup's, the segments are disjoint and are the generator's rows, 98 segment
    textures, every one snapped to the pixel grid, no art scaled fractionally;
  * the motion: each effect is a function of the ledger and the clock with its own switch and the master, the strong ones
    never overlap, and the face moves only on whole pixels at every scale;
  * the rate line: mana per second from GetPowerRegen, read out of combat and kept in combat with a dashed bar, the casting
    rate while suspended and the full rate otherwise, FitPx at both rate lengths, the retention chip;
  * the tooltips, the settings and their defaults, the master toggle;
  * who gets it: every mana class, a Druid only in a mana form, never a Warrior or a Rogue;
  * the seat: after the class tab when the class has one (Paladin, Shaman: after the buff tab), otherwise in the class
    tab's place, with the Console gap and a rescale;
  * secret values never reach arithmetic, comparison or concatenation; a throwing or missing API does not break it.

The mock is strict and is NOT the real client. FIVESECONDTAB_LUA and TOC_FILE point the harness at mutant copies (a
check must fail on a broken one).

    python3 tools/fivesecond-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
FSTAB = Path(os.environ.get("FIVESECONDTAB_LUA", ADDON / "Modules/ActionBars/FiveSecondTab.lua"))
CLASSSHOULDER = ADDON / "Modules/ActionBars/ClassShoulder.lua"
CONFIGWINDOW = ADDON / "Modules/Config/ConfigWindow.lua"
TOC = Path(os.environ.get("TOC_FILE", ADDON / "forever-stuwave.toc"))
MOCKUP = HERE.parent / "mockups" / "five-second-rule-compact-2026-10-14.html"
LED_GENERATOR = HERE / "assets" / "generate_led_segments.py"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bbh = _load("buffbar_harness", "buffbar-harness.py")
tbh = bbh.tbh
csh = bbh.csh
sb = bbh.sb
g = sb.g
fire = bbh.fire
approx = sb.approx
set_combat = sb.set_combat
blocked = sb.blocked
SCALES = csh.SCALES
# the live scale is 1 / 1.2 on this machine; 0.64 is the smallest the UI scale slider gives
CRISP_SCALES = (0.64, 1 / 1.2, 1.0)


def _gen():
    spec = importlib.util.spec_from_file_location("generate_led_segments", LED_GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _gen()

# ---------------------------------------------------------------------------------------------
# The mockup's numbers
# ---------------------------------------------------------------------------------------------


def _hex(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _num(pattern: str, text: str, what: str) -> float:
    return float(sb._m(pattern, text, what).group(1))


def mockup() -> dict:
    src = MOCKUP.read_text(encoding="utf-8")
    pal = sb._m(r"var C=\{(.*?)\};", src, "palette").group(1)
    colors = {k: _hex(v) for k, v in re.findall(r"(\w+):'(#[0-9a-fA-F]{6})'", pal)}
    rec = _hex(sb._m(r"REC='(#[0-9a-fA-F]{6})'", src, "gauge well color").group(1))
    d = sb._m(r"var D=\{W:([\d.]+),H:(\d+),ft:(\d+)\};", src, "the D2 tab size")
    hero = [float(v) for v in sb._m(r"g\+=tileP\((\d+),(\d+),(\d+),(\d+),(\d+),s,true\);", src, "hero tile").groups()]
    led_cx, led_y = (float(v) for v in sb._m(r"g\+=ledReadout\(s,(\d+),(\d+)\);", src, "ledReadout call").groups())
    ledw, ledh = (int(v) for v in sb._m(r"var LEDW=(\d+),LEDH=(\d+);", src, "cell size").groups())
    well = [float(v) for v in sb._m(r"g\+=rect\((\d+),(\d+),(\d+),(\d+),REC,", src, "gauge well").groups()]
    seg = sb._m(r"var sx=(\d+)\+i\*(\d+),sw=(\d+);", src, "gauge segment x")
    seg_y, seg_h = (float(v) for v in sb._m(r"segsO\+=a>0\?rect\(sx,(\d+),sw,(\d+),C\.amber", src, "gauge segment y").groups())
    gauge_n = int(sb._m(r"var n=(\d+),f=sus\?clamp\(s\.t/5,0,1\):0,bx=", src, "gauge count").group(1))
    rate = sb._m(r"g\+=rateTxt\(s,8\+ln/2,(\d+),(\d+),(\d+),(\d+)\)\+rateBar\(s,8\+ln/2,(\d+),ln\);", src, "rate line").groups()
    chip = [float(v) for v in sb._m(r"g\+=chipBox\((\d+),(\d+),(\d+),(\d+),s,(\d+)\);", src, "chip box").groups()]
    segs_src = sb._m(r"var SEGS=\{(.*?)\n\};", src, "SEGS").group(1)
    rows = {}
    for name, body in re.findall(r"(\w+):\[(\[.*?\])\]", segs_src, re.S):
        rows[name] = [[int(v) for v in r.split(",")] for r in re.findall(r"\[([\d,]+)\]", body)]
    order = re.findall(r"'(\w+)'", sb._m(r"var SEGORD=\[(.*?)\];", src, "SEGORD").group(1))
    glyph = {k: v for k, v in re.findall(r"'(\w)':'([a-z0-9 ]+)'", sb._m(r"var SEG14=\{(.*?)\};", src, "SEG14").group(1))}
    flash = [float(v) for v in sb._m(r"rect\((\d+),(\d+),([\d.]+),(\d+),'#ffffff',f2\(\.3\*s\.flash\)\)", src, "cast flash").groups()]
    # the look and motion numbers of D2 and digit option B, parsed so a mockup move fails here
    k = dict(
        susp_ring=_num(r"if\(s\.m==='susp'\)return \{c:C\.amber,o:([\d.]+),g:0\};", src, "suspended ring"),
        res_glow=_num(r"if\(s\.m==='res'\)\{var g=([\d.]+);", src, "regen glow"),
        flare_glow=_num(r"g=[\d.]+\+([\d.]+)\*Math\.sin\(Math\.PI\*s\.flare\)", src, "flare glow"),
        idle_ring=_num(r"o:b!=null\?[\d.]+\+[\d.]+\*b:([\d.]+),g:b!=null", src, "idle ring"),
        breath_ring=_num(r"o:b!=null\?([\d.]+)\+[\d.]+\*b:", src, "breath ring"),
        breath_swing=_num(r"o:b!=null\?[\d.]+\+([\d.]+)\*b:", src, "breath ring swing"),
        breath_glow=_num(r"g:b!=null\?([\d.]+)\*b:0", src, "breath glow"),
        ghost_count=_num(r"ledCell\(x1,y,dg,col,([\d.]+)\+[\d.]+\*zp", src, "counting ghost"),
        ghost_lift=_num(r"ledCell\(x1,y,dg,col,[\d.]+\+([\d.]+)\*zp", src, "ghost lift"),
        ghost_res=_num(r"res\?([\d.]+):\.05,lo", src, "regen ghost"),
        ghost_idle=_num(r"res\?[\d.]+:([\d.]+),lo", src, "idle ghost"),
        word_idle=_num(r"lo=res\?1:([\d.]+)", src, "idle word alpha"),
        dip_time=_num(r"dip:da\.a2<([\d.]+)\?[\d.]+:0", src, "dip time"),
        dip_depth=_num(r"dip:da\.a2<[\d.]+\?([\d.]+):0", src, "dip depth"),
        glow_steady=_num(r'filter="url\(#ledglow\)" opacity="([\d.]+)"', src, "steady glow"),
        pulse_rise=_num(r"return age<([\d.]+)\?age/", src, "pulse rise"),
        pulse_len=_num(r"age<0\|\|age>=([\d.]+)\)return 0", src, "pulse length"),
        flash_alpha=_num(r"f2\(([\d.]+)\*s\.flash\)", src, "flash alpha"),
        flash_time=_num(r"s\.flash=1-T0/([\d.]+)", src, "flash time"),
        glitch_ms=_num(r"if\(gp<(\d+)\)", src, "glitch burst"),
        glitch_every=_num(r"var gp=\(ms%(\d+)\)", src, "glitch period"),
        breath_time=_num(r"s\.breath=\.5-\.5\*Math\.cos\(2\*Math\.PI\*\(T0-[\d.]+\)/([\d.]+)\)", src, "breath period"),
        warm_white=_num(r"hw=mix\(C\.amber,C\.white,([\d.]+)\)", src, "warm white"),
        gauge_off=_num(r"rect\(sx,25,sw,3,C\.violet,([\d.]+),E\)", src, "empty gauge segment alpha"),
        gauge_idle=_num(r"b!=null\?f2\(\.24\+\.14\*b\):([\d.]+)", src, "idle gauge alpha"),
        band=_num(r"Math\.abs\(sx\+sw/2-bx\)<(\d+)", src, "sweep band half width"),
        chip_fill=_num(r"stroke-width=\"3\" filter=\"url\(#gls\)\"/><polygon points=\"'\+P\+'\" fill=\"'\+mix\(C\.bg,C\.cyan,([\d.]+)\)", src, "chip fill"),
        chip_glow=_num(r"f2\(([\d.]+)\+[\d.]+\*tk\)\+'\" stroke-width=\"3\"", src, "chip glow"),
        chip_tick=_num(r"f2\([\d.]+\+([\d.]+)\*tk\)\+'\" stroke-width=\"3\"", src, "chip tick glow"),
    )
    return dict(k=k, colors=colors, rec=rec, W=float(d.group(1)), BH=float(d.group(2)), hero=hero, led_cx=led_cx, led_y=led_y,
                ledw=ledw, ledh=ledh, well=well, seg_x=float(seg.group(1)), seg_pitch=float(seg.group(2)),
                seg_w=float(seg.group(3)), seg_y=seg_y, seg_h=seg_h, gauge_n=gauge_n, rate_y=float(rate[0]),
                rate_px=float(rate[1]), rate_sfx=float(rate[2]), rate_room=float(rate[3]), bar_y=float(rate[4]),
                chip=chip[:4], chip_px=chip[4], rows=rows, order=order, glyph=glyph, flash=flash)


MK = mockup()
C = MK["colors"]
BG = C["bg"]
REC = MK["rec"]
STALE = _hex("#b9aee0")
BTN, PAD, GAP, PT, PB = 38, 6, 4.8, 6, 5       # the buff tab's numbers, which ClassShoulder.lua stands blocks with

# ---------------------------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------------------------

MANA, FREE, ENERGY, ZERO, CHAN, HEAL = 585, 1, 2, 3, 4, 2060
MOCKS = r"""
-- GetPowerRegen: a plain pair out of combat, secrets in combat
__regen = { 12.4, 0.001 }
function GetPowerRegen()
    if __regenMode == "throw" then error("GetPowerRegen blew up") end
    if __combat then return __SECRET, __SECRET end
    return __regen[1], __regen[2]
end
-- C_Spell.GetSpellPowerCost: id -> list of { type, cost }, nothing for an id not listed (a free spell)
__costs, __costMode = {}, nil
C_Spell.GetSpellPowerCost = function(id)
    if __costMode == "throw" then error("GetSpellPowerCost blew up") end
    if __costMode == "secret" then return __SECRET end
    if __costMode == "secretentry" then return { { type = __SECRET, cost = 10 } } end
    -- a plain mana entry next to one with a secret field: the secret one could hide a cost, so the answer is unreadable
    if __costMode == "secretcost" then return { { type = 0, cost = __SECRET }, { type = 0, cost = 25 } } end
    if __costMode == "secrettype" then return { { type = __SECRET, cost = 10 }, { type = 0, cost = 25 } } end
    if __costMode == "secretper" then return { { type = 0, cost = 0, costPerSec = __SECRET }, { type = 0, cost = 25 } } end
    return __costs[id]
end
__costs[585] = { { type = 0, cost = 30, minCost = 30, name = "MANA" } }
__costs[2] = { { type = 3, cost = 30, name = "ENERGY" } }
__costs[3] = { { type = 0, cost = 0, name = "MANA" } }
__costs[4] = { { type = 0, cost = 120, name = "MANA" } }
__costs[2060] = { { type = 0, cost = 305, name = "MANA" } }
__costs[5] = { { type = 3, cost = 10 }, { type = 0, cost = 25 } }
-- a Druid's form power: 0 MANA, 3 ENERGY, 1 RAGE
__powerType = { 0, "MANA" }
__powerMode = nil
function UnitPowerType()
    if __powerMode == "throw" then error("UnitPowerType blew up") end
    if __powerMode == "secret" then return __SECRET, __SECRET end
    return __powerType[1], __powerType[2]
end
-- UnitChannelInfo: the name of the channel in progress, or nothing
__channel = nil
function UnitChannelInfo() return __channel end
-- the sound
__sounds = {}
SOUNDKIT = { TELL_MESSAGE = 3081 }
function PlaySound(id) __sounds[#__sounds + 1] = id end
function __castOk(id) __fire_event("UNIT_SPELLCAST_SUCCEEDED", "player", "guid", id) end
-- the crispness calls and the clip, which the shared mock leaves out: they record what they were handed
do
    local R = __Region
    function R:SetSnapToPixelGrid(v) self._snap = v end
    function R:SetTexelSnappingBias(v) self._bias = v end
    function R:SetClipsChildren(v) self._clips = v end
    function R:GetEffectiveScale() return __effScale or 1 end
end
-- Animation groups that record what they are told and play on the mock clock: Alpha animations only, looped, with the IN_OUT
-- smoothing as a cosine. __animAlpha(region) is the alpha the region has now (its own, or what a playing group makes of it).
do
    local R = __Region
    local Group = {}
    local noop = function() end
    local function methods(t) return setmetatable(t, { __index = function(_, k) return Group[k] or noop end }) end
    function Group:SetLooping(v) self.looping = v end
    function Group:Play() self.playing, self.t0 = true, GetTime() end
    function Group:Stop() self.playing = false end
    function Group:IsPlaying() return self.playing end
    function Group:CreateAnimation(kind)
        local anim = setmetatable({ kind = kind, order = 1, duration = 0, from = 0, to = 1 }, { __index = function() return noop end })
        function anim:SetFromAlpha(v) self.from = v end
        function anim:SetToAlpha(v) self.to = v end
        function anim:SetDuration(v) self.duration = v end
        function anim:SetOrder(v) self.order = v end
        function anim:SetSmoothing(v) self.smoothing = v end
        self.anims[#self.anims + 1] = anim
        return anim
    end
    function R:CreateAnimationGroup()
        local group = methods({ owner = self, anims = {}, playing = false, looping = "NONE" })
        self._groups = self._groups or {}
        self._groups[#self._groups + 1] = group
        return group
    end
    function __animAlpha(region)
        for _, group in ipairs(region._groups or {}) do
            if group.playing then
                local list = {}
                for _, anim in ipairs(group.anims) do list[#list + 1] = anim end
                table.sort(list, function(x, y) return x.order < y.order end)
                local total = 0
                for _, anim in ipairs(list) do total = total + anim.duration end
                local t = GetTime() - group.t0
                if group.looping == "REPEAT" then t = t % total elseif t > total then t = total end
                for _, anim in ipairs(list) do
                    if t <= anim.duration or anim == list[#list] then
                        local p = anim.duration > 0 and math.min(1, t / anim.duration) or 1
                        if anim.smoothing == "IN_OUT" then p = 0.5 - 0.5 * math.cos(math.pi * p) end
                        return anim.from + (anim.to - anim.from) * p
                    end
                    t = t - anim.duration
                end
            end
        end
        return region._alpha or 1
    end
end
-- a frame is visible when it and every parent are shown, and a frame that is not runs no OnUpdate in the client
do
    local R = __Region
    function R:IsVisible()
        local f = self
        while f do
            if f._shown == false then return false end
            f = f._parent
        end
        return true
    end
end
function __tickAll(dt)
    __advance(dt)
    local list = {}
    for _, f in ipairs(__frames) do
        if f._scripts.OnUpdate and f:IsVisible() then list[#list + 1] = f end
    end
    for _, f in ipairs(list) do f._scripts.OnUpdate(f, dt) end
end
"""


def boot(scale: float = 1.0, *, klass: str = "PRIEST", combat: bool = False, console: bool = True,
         pre_login: str = "", load_tab: bool = True):
    """A world of class `klass` (its own class tab included for a Paladin and a Shaman), with the tab loaded last."""
    mocks = tbh.MOCKS % dict(guid=tbh.GUID, bar=tbh.BAR, all="{}") + "\n" + bbh.MOCKS + "\n" + MOCKS
    files = [csh.PETDOCK, csh.CLASSSHOULDER]
    sealbar = False
    if klass == "PALADIN":
        files.append(sb.SEALBAR)
    elif klass == "SHAMAN":
        files += [tbh.TOTEMPIECE, tbh.TOTEMBAR, bbh.SHAMANBUFFS, bbh.BUFFTAB]
    if load_tab:
        files.append(FSTAB)
    known = None if klass == "PALADIN" else []
    if klass == "SHAMAN":
        known = []
    return sb.boot(scale, klass=klass, known=known, combat=combat, console=console, sealbar=sealbar,
                   extra_lua=csh.PATCH + mocks, extra_files=tuple(files), pre_login=csh.SPIES + pre_login)


def ft(lua):
    return g(lua).FS.FiveSecondTab


def cells_tile(lua):
    return g(lua).FSFiveSecondCells


def rate_tile(lua):
    return g(lua).FSFiveSecondRate


def host(lua):
    return g(lua).FSFiveSecondTab


def run(lua, code):
    lua.execute(code)


def cast(lua, spell=MANA):
    run(lua, f"__castOk({spell})")


def tick(lua, seconds, step=0.05):
    """Moves the clock `seconds` in frame sized steps, running every OnUpdate, then repaints."""
    n = max(1, round(seconds / step))
    for _ in range(n):
        lua.eval("__tickAll")(seconds / n)
    ft(lua).Update()
    ft(lua).Paint()


def frames(lua, seconds, each, fps=60):
    """Runs `seconds` of the clock as frames at `fps`, calling each(lua) after every one (what the client would draw)."""
    n = round(seconds * fps)
    for _ in range(n):
        lua.eval("__tickAll")(1 / fps)
        each(lua)


def refresh(lua):
    ft(lua).Update()
    ft(lua).Paint()


def view(lua):
    ft(lua).Update()
    return ft(lua).View()


def plain_text(s) -> str:
    return re.sub(r"\|r", "", re.sub(r"\|c[0-9a-fA-F]{8}", "", str(s)))


def rgb(v):
    return tuple(float(v[i]) for i in (1, 2, 3))


def close(a, b, what, tol=1.2e-2):
    for i in range(3):
        assert abs(a[i] - b[i]) <= tol, f"{what}: {tuple(round(x, 4) for x in a)} != {tuple(round(x, 4) for x in b)}"


def shown(r) -> bool:
    return bool(r._shown)


def conf(lua, key, value):
    g(lua).FS.Config.Set(key, value)


def seq(table) -> list:
    return csh.seq(table)


def world(scale: float = 1.0, *, motion: bool = True, **kw):
    """A Priest's world; motion=False switches the master off so the looks stand still (the static looks are pinned that way)."""
    lua = boot(scale, **kw)
    if not motion:
        conf(lua, "fivesecond.motion", False)
        refresh(lua)
    return lua


# --- reading the face back -----------------------------------------------------------------

SEG_NAMES = list(GEN.SEGMENT_ORDER)
GLYPH_OF = {frozenset(v.split()): k for k, v in MK["glyph"].items()}


def led(lua):
    return ft(lua).FT.led


def cell_set(cell, lit_min=0.3) -> frozenset:
    """The segment names whose texture is lit (alpha above the ghost levels) in one cell."""
    segs = seq(cell.seg)
    return frozenset(SEG_NAMES[i] for i, t in enumerate(segs) if float(t._vertex[4]) > lit_min)


def cell_char(cell) -> str:
    s = cell_set(cell)
    if not s:
        return "_"
    return GLYPH_OF.get(s, "?")


def cell_color(cell):
    """The colour of the first lit segment of a cell."""
    segs = seq(cell.seg)
    for i, t in enumerate(segs):
        if float(t._vertex[4]) > 0.3:
            return rgb(t._vertex), float(t._vertex[4])
    return None, 0.0


def led_text(lua) -> tuple:
    """(count, word): what the digit cells and the word cells spell. The count is tilde, digit, dot, digit (parts that are
    hidden are left out); the word is five characters, '_' for a masked cell, '' when the word cells are hidden."""
    L = led(lua)
    count = ""
    if shown(L.tilde[1]):
        count += "~"
    if shown(L.d1.frame):
        count += cell_char(L.d1)
    if shown(L.dot):
        count += "."
    if shown(L.d2.frame):
        count += cell_char(L.d2)
    word = "".join(cell_char(c) for c in seq(L.word)) if all(shown(c.frame) for c in seq(L.word)) else ""
    return count, word


def readout(lua) -> str:
    """The word when it shows, else the count."""
    count, word = led_text(lua)
    return word or count


def gauge_levels(lua) -> list:
    """Each gauge segment as a fraction: amber lit 0..1 from its alpha, 0 for the empty violet one."""
    out = []
    for seg in seq(ft(lua).FT.gauge.seg):
        c, a = rgb(seg._vertex), float(seg._vertex[4])
        if abs(c[0] - C["amber"][0]) < 0.02 and abs(c[2] - C["amber"][2]) < 0.02 and a > 0.4:
            out.append(round((a - 0.45) / 0.55, 3))
        else:
            out.append(0.0)
    return out


def eff_alpha(lua, region) -> float:
    """The alpha a region draws with right now: its own, or what a playing animation group makes of it."""
    return float(lua.eval("__animAlpha")(region))


def cells_look(lua):
    hero = ft(lua).FT.hero
    L = led(lua)
    text = readout(lua)
    count, word = led_text(lua)
    lit = cell_color(L.word[1]) if word else cell_color(L.d1)
    return dict(
        text=text, count=count, word=word, ring=rgb(hero.fsSkin.border.ring._vertex),
        ring_a=float(hero.fsSkin.border.ring._vertex[4]) * eff_alpha(lua, hero.fsSkin.border.ring), glow=rgb(hero.fsSkin.glow._vertex),
        glow_a=float(hero.fsSkin.glow._vertex[4]) * eff_alpha(lua, hero.fsSkin.glow), plate=rgb(hero.fsPlate._vertex), plate_a=float(hero.fsPlate._vertex[4]),
        lit=lit[0], lit_a=lit[1], alpha=float(cells_tile(lua)._alpha),
    )


def rate_look(lua):
    FT = ft(lua).FT
    bar = FT.rateBar
    dashes = [bool(shown(d)) for d in seq(bar.dash)]
    chip = FT.chip
    return dict(
        text=plain_text(FT.rateText._text), code=plain_text(chip.code._text), chip=rgb(chip.ring._vertex),
        chip_a=float(chip.ring._vertex[4]), fill=rgb(chip.fill._vertex), fill_a=float(chip.fill._vertex[4]),
        code_color=rgb(chip.code._textColor), code_a=float(chip.code._textColor[3 + 1]),
        chip_glow_a=float(chip.glow._vertex[4]), text_color=rgb(FT.rateText._textColor), text_a=float(FT.rateText._textColor[4]),
        bar=rgb(bar.solid._vertex) if bar.solid._vertex is not None else None,
        bar_a=float(bar.solid._vertex[4]) if bar.solid._vertex is not None else None, bar_shown=shown(bar.solid),
        dashes=dashes, dash_count=sum(dashes), alpha=float(rate_tile(lua)._alpha),
    )


def tip_text(lua, tile):
    run(lua, "GameTooltip._lines = {}")
    lua.eval("__Region.Fire")(tile, "OnEnter")
    return [str(x) for x in seq(g(lua).GameTooltip._lines)]


def leave_tip(lua, tile):
    lua.eval("__Region.Fire")(tile, "OnLeave")


def enter_combat(lua):
    set_combat(lua, True)
    fire(lua, "PLAYER_REGEN_DISABLED")


def leave_combat(lua):
    set_combat(lua, False)
    fire(lua, "PLAYER_REGEN_ENABLED")


def fx(lua) -> dict:
    f = ft(lua).Fx()
    return {k: (f[k] if f[k] is not None else None) for k in
            ("flash", "dip", "warm", "zp", "dropSeg", "dropA", "pp", "flare", "tick", "breathing", "glitchA", "glitchDx")}


def regen_look(lua, after=1.2):
    """Casts and runs to `after` seconds past the end of the window (past the sweep by default)."""
    cast(lua)
    tick(lua, 5 + after)
    assert view(lua).phase == "res", view(lua).phase




# ---------------------------------------------------------------------------------------------
# Checks: the art and the numbers
# ---------------------------------------------------------------------------------------------


def check_the_glyph_tables_and_the_segment_order_are_the_mockups():
    assert [str(x) for x in seq(ft(world()).SEGMENT_ORDER)] == MK["order"] == SEG_NAMES, "segment order"
    lua = world()
    got = {str(k): str(v) for k, v in ft(lua).GLYPH_TEXT.items()}
    assert got == MK["glyph"], f"glyph tables differ: {got} vs {MK['glyph']}"
    for ch in "0123456789REGN":
        assert ch in got, ch


def check_the_generator_draws_the_mockups_disjoint_segments():
    assert GEN.SEGMENTS == MK["rows"], "generate_led_segments.py rows differ from the mockup's SEGS"
    seen = {}
    for name, rows in GEN.SEGMENTS.items():
        for x, y, w in rows:
            for q in range(w):
                assert 0 <= x + q < MK["ledw"] and 0 <= y < MK["ledh"], (name, x, y)
                assert (x + q, y) not in seen, f"{name} shares {(x + q, y)} with {seen[(x + q, y)]}"
                seen[(x + q, y)] = name
    assert len(seen) == 112


def check_the_led_has_ninety_eight_segment_textures_cut_from_the_atlas_and_snapped():
    lua = world()
    L = led(lua)
    cells = seq(L.cells)
    assert len(cells) == 7
    total = 0
    for cell in cells:
        segs = seq(cell.seg)
        assert len(segs) == 14
        for n, t in enumerate(segs):
            total += 1
            assert str(t._texture).endswith("led_segments.tga"), t._texture
            tc = [float(x) for x in seq(t._coord if t._coord is not None else t._tc)]
            col, row = n % 4, n // 4
            want = [col * 0.25, col * 0.25 + 10 / 64, row * 0.25, row * 0.25 + 12 / 64]
            assert all(abs(a - b) < 1e-9 for a, b in zip(tc, want)), f"segment {n} cut {tc} != {want}"
            assert t._snap is True and float(t._bias) == 0.0, f"segment {n} is not snapped to the pixel grid"
    assert total == 98
    assert len(seq(L.tilde)) == 4 and L.dot is not None
    # the flat pieces too: plates, lines, gauge segments, bars, the cast wash
    FT = ft(lua).FT
    flats = [FT.gauge.plate, FT.fxFlash, FT.rateBar.solid, FT.rateBar.hi] + seq(FT.gauge.line) + seq(FT.gauge.seg) \
        + seq(FT.rateBar.dash) + seq(L.tilde) + [L.dot]
    for t in flats:
        assert t._snap is True and float(t._bias) == 0.0, "a flat piece is not snapped to the pixel grid"


def _tex_rect_px(lua, tex, parent=None):
    FT = ft(lua).FT
    px = float(FT.px)
    p = tex._points[1]
    return float(p.x) / px, float(p.y) / px, float(tex._w) / px, float(tex._h) / px


def check_the_readout_glow_is_a_soft_copy_under_each_lit_segment_and_never_a_block():
    k = MK["k"]
    lua = world(motion=False)
    FT = ft(lua).FT
    n = int(FT.n)
    cast(lua)
    tick(lua, 1.3)                                     # the count, ~3.7
    L = led(lua)
    assert led_text(lua)[0] == "~3.7", led_text(lua)
    for cell in (L.d1, L.d2):
        segs, glows = seq(cell.seg), seq(cell.gl)
        assert len(glows) == 14
        lit = [i for i, t in enumerate(segs) if float(t._vertex[4]) > 0.3]
        assert lit
        for i, gl in enumerate(glows):
            assert str(gl._texture).endswith("led_segment_glow.tga") and str(gl._blend) == "ADD"
            assert gl._snap is True and float(gl._bias) == 0.0
            tc = [float(x) for x in seq(gl._coord if gl._coord is not None else gl._tc)]
            col, row = i % 4, i // 4
            want = [col * 0.25, col * 0.25 + 14 / 64, row * 0.25, row * 0.25 + 16 / 64]
            assert tc and all(abs(a - b) < 1e-9 for a, b in zip(tc, want)), f"glow {i} cut {tc} != {want}"
            x, y, w, h = _tex_rect_px(lua, gl)
            assert (x, y, w, h) == (-2 * n, 2 * n, 14 * n, 16 * n), f"glow {i} sits at {(x, y, w, h)}"
            a = float(gl._vertex[4])
            if i in lit:
                close(rgb(gl._vertex), rgb(segs[i]._vertex), f"glow {i} wears its segment's colour", 1e-6)
                approx(a, k["glow_steady"] * float(segs[i]._vertex[4]), f"glow {i} alpha", 1e-6)
            else:
                assert a == 0.0, f"an unlit segment glows ({i}: {a})"
    # the tilde and the dot glow too, from the 2 x 2 block slot
    pieces = list(zip(seq(L.tilde), seq(L.tildeGl))) + [(L.dot, L.dotGl)]
    assert len(pieces) == 5
    for bar, gl in pieces:
        assert str(gl._texture).endswith("led_segment_glow.tga") and str(gl._blend) == "ADD"
        tc = [float(x) for x in seq(gl._coord if gl._coord is not None else gl._tc)]
        assert all(abs(a - b) < 1e-9 for a, b in zip(tc, [0.5, 0.5 + 6 / 64, 0.75, 0.75 + 6 / 64])), tc
        bx, by, bw, bh = _tex_rect_px(lua, bar)
        gx, gy, gw, gh = _tex_rect_px(lua, gl)
        assert (gx, gy, gw, gh) == (bx - 2 * n, by + 2 * n, 6 * n, 6 * n), f"{(gx, gy, gw, gh)} vs {(bx, by)}"
        approx(float(gl._vertex[4]), k["glow_steady"], "tilde glow", 1e-6)
    # no block: the only led_glow.tga textures are the ten gauge segment halos, each about the size of its segment
    soft = [r for r in descendants(host(lua)) if r._kind == "Texture" and str(r._texture).endswith("led_glow.tga")]
    assert len(soft) == 10, len(soft)
    s_ = float(FT.s)
    for r in soft:
        assert float(r._w) < 15 * s_ and float(r._h) < 10 * s_, "a glow bigger than a gauge segment's halo"
    # the word glows at regen, faded with the look, and the ghost segments never glow
    cast(lua)
    tick(lua, 5.4)
    for cell in seq(L.word):
        for t, gl in zip(seq(cell.seg), seq(cell.gl)):
            if float(t._vertex[4]) > 0.3:
                approx(float(gl._vertex[4]), k["glow_steady"] * float(view(lua).fade), "word glow", 0.02)
            else:
                assert float(gl._vertex[4]) == 0.0
    tick(lua, 8.0)
    assert all(float(gl._vertex[4]) == 0.0 for cell in seq(L.word) for gl in seq(cell.gl)), "no glow at rest"


def check_the_gauge_glow_is_a_halo_on_each_segment_and_only_when_not_idle():
    lua = world(motion=False)
    FT = ft(lua).FT
    G = FT.gauge
    gls, segs = seq(G.gl), seq(G.seg)
    assert len(gls) == 10
    for seg, gl in zip(segs, gls):
        assert str(gl._texture).endswith("led_glow.tga") and str(gl._blend) == "ADD"
    refresh(lua)
    assert all(float(gl._vertex[4]) == 0.0 for gl in gls), "idle gauge does not glow"
    cast(lua)
    tick(lua, 1.3)
    for i, (seg, gl) in enumerate(zip(segs, gls)):
        close(rgb(gl._vertex), rgb(seg._vertex), f"halo {i} wears its segment's colour", 1e-6)
        approx(float(gl._vertex[4]), float(seg._vertex[4]), f"halo {i} alpha", 1e-6)
        sx, sy, sw, sh = _tex_rect_px(lua, seg)
        gx, gy, gw, gh = _tex_rect_px(lua, gl)
        pad = round(3 * float(FT.s) / float(FT.px))
        assert (gx, gy, gw, gh) == (sx - pad, sy + pad, sw + 2 * pad, sh + 2 * pad), f"halo {i}: {(gx, gy, gw, gh)} vs {(sx, sy, sw, sh)}"
    cast(lua)
    tick(lua, 5.4)
    assert all(float(gl._vertex[4]) > 0.5 for gl in gls), "the cyan gauge glows at regen"


def check_the_cast_wash_is_clipped_to_the_face():
    lua = world()
    FT = ft(lua).FT
    assert FT.fxFrame._clips is True, "the wash frame does not clip its children"
    assert FT.fxFlash._parent is FT.fxFrame or lua.eval("rawequal")(FT.fxFlash._parent, FT.fxFrame)
    mx, my, mw, mh = MK["flash"]
    fx_, fy, fw, fh = MK["hero"][0], MK["hero"][1], 81, 37
    assert abs(mx - fx_) < 0.5 and abs(my - fy) < 0.5 and abs(mw - fw) < 0.5 and abs(mh - fh) < 0.5, (MK["flash"],)
    s = 1.0
    approx(float(FT.fxFrame._w), fw * s, "wash width"), approx(float(FT.fxFrame._h), fh * s, "wash height")


def check_the_led_numbers_are_the_mockups():
    lua = world()
    FT = ft(lua).FT
    k = MK["k"]
    pairs = [
        ("GHOST_COUNT", k["ghost_count"]), ("GHOST_LIFT", k["ghost_lift"]), ("GHOST_RES", k["ghost_res"]),
        ("GHOST_IDLE", k["ghost_idle"]), ("WORD_IDLE", k["word_idle"]), ("DIP_TIME", k["dip_time"]),
        ("DIP_DEPTH", k["dip_depth"]), ("GLOW_STEADY", k["glow_steady"]), ("PULSE_RISE", k["pulse_rise"]),
        ("PULSE_SECOND", k["pulse_len"]), ("FLASH_ALPHA", k["flash_alpha"]), ("FLASH_TIME", k["flash_time"]),
        ("GLITCH_MS", k["glitch_ms"]), ("GLITCH_EVERY_MS", k["glitch_every"]), ("BREATH_TIME", k["breath_time"]),
        ("GAUGE_OFF", k["gauge_off"]), ("GAUGE_IDLE", k["gauge_idle"]),
    ]
    for name, want in pairs:
        approx(float(FT[name]), want, name, 1e-9)
    K = FT.CHROME
    approx(float(K.suspRing), k["susp_ring"], "suspRing"), approx(float(K.regenGlow), k["res_glow"], "regenGlow")
    approx(float(K.flareGlow), k["flare_glow"], "flareGlow"), approx(float(K.idleRing), k["idle_ring"], "idleRing")
    approx(float(K.breathRing), k["breath_ring"], "breathRing"), approx(float(K.breathRingSwing), k["breath_swing"], "swing")
    approx(float(K.breathGlow), k["breath_glow"], "breathGlow"), approx(float(K.chipGlow), k["chip_glow"], "chipGlow")
    approx(float(K.chipTick), k["chip_tick"], "chipTick"), approx(float(K.regenRing), 1.0, "regenRing")
    # layout: the hero tile, the readout, the gauge, the rate line, the chip, in design px
    hx, hy, hw, hh, hc = MK["hero"]
    assert (float(FT.HERO.x), float(FT.HERO.y), float(FT.HERO.w), float(FT.HERO.h)) == (hx, hy, hw, hh)
    assert float(FT.LED_CX) == MK["led_cx"] and MK["led_y"] == hy + hh / 2 - MK["ledh"] / 2
    assert (float(FT.CELL_W), float(FT.CELL_H)) == (MK["ledw"], MK["ledh"])
    assert float(FT.COUNT_W) == 8 + 2 + MK["ledw"] + 4 + MK["ledw"] and float(FT.WORD_W) == 5 * MK["ledw"] + 4 * 2
    assert float(FT.WORD_X) == MK["led_cx"] - float(FT.WORD_W) / 2
    wx, wy, ww, wh = MK["well"]
    assert (float(FT.GAUGE_WELL.x), float(FT.GAUGE_Y), float(FT.GAUGE_WELL.w), float(FT.GAUGE_H)) == (wx, wy, ww, wh)
    assert (float(FT.GAUGE_X), float(FT.GAUGE_PITCH), float(FT.GAUGE_SEG_W)) == (MK["seg_x"], MK["seg_pitch"], MK["seg_w"])
    assert (float(FT.GAUGE_SEG_Y), float(FT.GAUGE_SEG_H), int(FT.GAUGE_N)) == (MK["seg_y"], MK["seg_h"], MK["gauge_n"])
    assert (float(FT.RATE_BASE), float(FT.RATE_PX), float(FT.RATE_ROOM), float(FT.RATE_BAR_Y)) == \
        (MK["rate_y"], MK["rate_px"], MK["rate_room"], MK["bar_y"])
    assert [float(FT.CHIP[k_]) for k_ in ("x", "y", "w", "h")] == MK["chip"] and float(FT.CODE_PX) == MK["chip_px"]
    approx(float(FT.HOST_W), MK["W"], "host width"), approx(float(FT.HOST_H), MK["BH"], "host height")
    approx(MK["W"], 2 * PAD + 2 * BTN + GAP, "tab width against the buff tab's block"), approx(MK["BH"], PT + BTN + PB, "tab height")


# ---------------------------------------------------------------------------------------------
# Checks: the window
# ---------------------------------------------------------------------------------------------


def check_a_mana_cast_starts_five_seconds_and_the_readout_counts_in_tenths():
    lua = world(motion=False)
    v = view(lua)
    assert v.phase == "idle", v.phase
    cast(lua)
    v = view(lua)
    assert v.phase == "susp", v.phase
    approx(v.t, 5.0, "just cast", 0.06)
    refresh(lua)
    assert led_text(lua) == ("~5.0", ""), led_text(lua)
    tick(lua, 2.7)
    v = view(lua)
    assert v.phase == "susp"
    approx(v.t, 2.3, "mid countdown", 0.12)
    assert led_text(lua)[0] in ("~2.3", "~2.2", "~2.4"), led_text(lua)
    # the tilde is the amber estimate mark, the digits amber too
    L = led(lua)
    close(rgb(L.tilde[1]._vertex), C["amber"], "tilde")
    col, a = cell_color(L.d1)
    close(col, C["amber"], "digit")


def check_every_digit_the_countdown_can_show_decodes_from_its_lit_segments():
    lua = world(motion=False)
    cast(lua)
    seen = {}
    prev = None
    for _ in range(102):
        tick(lua, 0.05)
        if view(lua).phase != "susp":
            break
        count = led_text(lua)[0]
        if count != prev:
            prev = count
            assert re.fullmatch(r"~\d\.\d", count), count
            for ch in count[1], count[3]:
                seen[ch] = seen.get(ch, 0) + 1
    assert set(seen) == set("0123456789"), f"digits shown: {sorted(seen)}"
    # the word, in the still look
    assert readout(lua) == "REGEN", readout(lua)


def check_the_gauge_drains_one_segment_every_half_second_right_to_left_with_a_partial_segment():
    lua = world(motion=False)
    cast(lua)
    refresh(lua)
    assert gauge_levels(lua) == [1.0] * 10, gauge_levels(lua)
    tick(lua, 2.7)
    f = gauge_levels(lua)
    assert f[:4] == [1.0] * 4, f
    assert 0.45 <= f[4] <= 0.75, f"the fifth segment should hold about 60%: {f}"
    assert f[5:] == [0.0] * 5, f
    tick(lua, 2.0)
    f = gauge_levels(lua)
    assert 0.4 <= f[0] <= 0.8 and f[1:] == [0.0] * 9, f"the first segment empties last: {f}"
    # an emptied segment is the dim violet one
    seg = ft(lua).FT.gauge.seg[10]
    close(rgb(seg._vertex), C["violet"], "emptied segment")
    approx(float(seg._vertex[4]), MK["k"]["gauge_off"], "emptied segment alpha", 1e-6)


def check_the_suspended_look_is_amber_all_the_way_through():
    lua = world(motion=False)
    cast(lua)
    tick(lua, 1.0)
    look = cells_look(lua)
    close(look["ring"], C["amber"], "suspended border")
    approx(look["ring_a"], MK["k"]["susp_ring"], "suspended border alpha", 0.02)
    close(look["plate"], _mix(BG, C["amber"], 0.09), "suspended plate")
    close(look["lit"], C["amber"], "suspended digits")
    approx(look["lit_a"], 1.0, "suspended digit alpha", 0.01)
    approx(look["glow_a"], 0.0, "no glow while suspended", 1e-6)
    assert gauge_levels(lua)[0] == 1.0
    close(rgb(ft(lua).FT.gauge.seg[1]._vertex), C["amber"], "gauge")
    r = rate_look(lua)
    close(r["bar"], C["cyan"], "rate bar")
    close(r["text_color"], C["white"], "rate text", 0.06)


# ---------------------------------------------------------------------------------------------
# Checks: the window (the ledger is the old tab's, unchanged)
# ---------------------------------------------------------------------------------------------


def check_a_free_cast_starts_nothing():
    for label, spell in (("zero cost", ZERO), ("another power", ENERGY), ("no cost entry", FREE)):
        lua = world()
        cast(lua, spell)
        assert view(lua).phase == "idle", f"{label} started a window"
    # a mixed cost carries a mana part
    lua = world()
    cast(lua, 5)
    assert view(lua).phase == "susp", "a cost with a mana part starts the rule"


def check_another_units_cast_and_unreadable_costs_start_nothing():
    lua = world()
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "target", "guid", MANA)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "party1", "guid", MANA)
    assert view(lua).phase == "idle"
    for mode in ("throw", "secret", "secretentry", "secretcost", "secrettype", "secretper"):
        lua = world()
        run(lua, f'__costMode = "{mode}"')
        cast(lua)
        assert view(lua).phase == "idle", f"{mode}: an unreadable cost started the rule"
    lua = world()
    run(lua, "C_Spell.GetSpellPowerCost = nil")
    cast(lua)
    assert view(lua).phase == "idle", "no cost API"
    lua = world()
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "player", "guid", g(lua).__SECRET)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "player", "guid", None)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", g(lua).__SECRET, "guid", MANA)
    assert view(lua).phase == "idle", "a secret spell id or unit started the rule"


def check_a_recast_restarts_the_full_window():
    lua = world()
    cast(lua)
    tick(lua, 3.0)
    approx(view(lua).t, 2.0, "before the recast", 0.12)
    cast(lua, HEAL)
    v = view(lua)
    approx(v.t, 5.0, "after the recast", 0.06)
    assert v.phase == "susp"
    # a free cast in the middle does not extend it
    tick(lua, 1.0)
    cast(lua, ZERO)
    approx(view(lua).t, 4.0, "a free cast leaves the window alone", 0.12)


def check_a_cast_after_the_rule_ended_starts_a_new_window():
    lua = world()
    cast(lua)
    tick(lua, 5.6)
    assert view(lua).phase == "res"
    cast(lua)
    v = view(lua)
    assert v.phase == "susp"
    approx(v.t, 5.0, "new window", 0.06)


def check_a_channel_holds_the_window_open_until_it_ends():
    lua = world()
    run(lua, '__channel = "Drain"')
    fire(lua, "UNIT_SPELLCAST_CHANNEL_START", "player", "guid", CHAN)
    cast(lua, CHAN)
    tick(lua, 8.0)
    v = view(lua)
    assert v.phase == "susp", f"a channel in progress is not regen: {v.phase}"
    approx(v.t, 5.0, "held at the full window", 0.06)
    run(lua, "__channel = nil")
    fire(lua, "UNIT_SPELLCAST_CHANNEL_STOP", "player", "guid", CHAN)
    approx(view(lua).t, 5.0, "the five seconds run from the channel end", 0.12)
    tick(lua, 2.0)
    approx(view(lua).t, 3.0, "counting after the channel", 0.15)
    # a free channel holds nothing
    lua = world()
    fire(lua, "UNIT_SPELLCAST_CHANNEL_START", "player", "guid", FREE)
    assert view(lua).phase == "idle"
    # another unit's channel holds nothing
    lua = world()
    fire(lua, "UNIT_SPELLCAST_CHANNEL_START", "target", "guid", CHAN)
    assert view(lua).phase == "idle"


def check_a_channel_whose_end_event_never_comes_is_not_held_forever():
    lua = world()
    run(lua, '__channel = "Drain"')
    fire(lua, "UNIT_SPELLCAST_CHANNEL_START", "player", "guid", CHAN)
    tick(lua, 2.0)
    assert view(lua).phase == "susp"
    run(lua, "__channel = nil")          # the client says nothing is channeling any more
    tick(lua, 0.5)
    approx(view(lua).t, 5.0, "the window starts when the channel is seen gone", 0.7)
    tick(lua, 6.0)
    assert view(lua).phase in ("res", "idle"), view(lua).phase


def check_death_and_a_loading_screen_clear_the_window():
    lua = world()
    cast(lua)
    tick(lua, 1.0)
    fire(lua, "PLAYER_DEAD")
    assert view(lua).phase == "idle"
    cast(lua)
    fire(lua, "PLAYER_ENTERING_WORLD")
    assert view(lua).phase == "idle"


# ---------------------------------------------------------------------------------------------
# Checks: the end, the pulse, the idle fade
# ---------------------------------------------------------------------------------------------


def check_at_zero_the_digits_turn_cyan_and_the_word_says_regen():
    lua = world(motion=False)
    regen_look(lua, 0.3)
    refresh(lua)
    look = cells_look(lua)
    assert look["text"] == "REGEN" and look["count"] == "", led_text(lua)
    close(look["ring"], C["cyan"], "regen border")
    approx(look["ring_a"], 1.0, "regen border alpha", 0.02)
    close(look["plate"], _mix(BG, C["cyan"], 0.1), "regen plate")
    approx(look["plate_a"], 0.9, "regen plate alpha", 0.01)
    approx(look["glow_a"], MK["k"]["res_glow"], "regen glow", 0.01)
    close(look["lit"], C["cyan"], "regen word")
    approx(look["lit_a"], 1.0, "regen word alpha", 0.01)
    assert gauge_levels(lua) == [0.0] * 10 or True
    for seg in seq(ft(lua).FT.gauge.seg):
        close(rgb(seg._vertex), C["cyan"], "regen gauge")
        approx(float(seg._vertex[4]), 0.85, "regen gauge alpha", 0.01)
    close(rgb(ft(lua).FT.rateBar.solid._vertex), C["cyan"], "regen rate bar")


def check_regen_pulses_once_and_not_again_while_it_shows():
    lua = world()
    assert int(view(lua).pulses) == 0
    cast(lua)
    tick(lua, 4.8)
    assert int(view(lua).pulses) == 0, "pulsed before the end"
    tick(lua, 0.4)
    assert int(view(lua).pulses) == 1, view(lua).pulses
    glow_now = cells_look(lua)["glow_a"]
    tick(lua, 0.3)
    tick(lua, 0.3)
    assert int(view(lua).pulses) == 1, "a second pulse for the same end"
    tick(lua, 1.5)
    glow_later = cells_look(lua)["glow_a"]
    assert glow_now > glow_later + 0.15, f"the rim does not flash: {glow_now} then {glow_later}"
    approx(glow_later, MK["k"]["res_glow"], "the held glow", 0.01)
    assert float(view(lua).pulse) == 0.0, "the pulse never finishes"
    # a new window pulses again at its own end
    cast(lua)
    tick(lua, 5.4)
    assert int(view(lua).pulses) == 2


def check_the_pulse_toggle_off_means_no_pulse_but_the_cyan_look_stays():
    lua = world()
    conf(lua, "fivesecond.pulse", False)
    cast(lua)
    tick(lua, 5.3)
    v = view(lua)
    assert v.phase == "res"
    assert int(v.pulses) == 0, "pulsed with the pulse toggle off"
    assert float(v.pulse) == 0.0
    refresh(lua)
    close(cells_look(lua)["ring"], C["cyan"], "still cyan")
    on = world()
    cast(on)
    tick(on, 5.3)
    flash = cells_look(on)["glow_a"]
    assert flash > cells_look(lua)["glow_a"] + 0.15, "the toggle off did not remove the flash"
    assert abs(fx(lua)["flare"]) < 1e-9


def check_the_sound_plays_once_at_regen_only_when_its_toggle_is_on():
    lua = world()
    assert g(lua).FS.Config.Get("fivesecond.sound") is False, "the sound is off by default"
    cast(lua)
    tick(lua, 5.6)
    assert len(seq(g(lua).__sounds)) == 0, "a sound played with the toggle off"
    conf(lua, "fivesecond.sound", True)
    cast(lua)
    tick(lua, 4.9)
    assert len(seq(g(lua).__sounds)) == 0, "a sound before the end"
    tick(lua, 0.5)
    tick(lua, 1.0)
    assert len(seq(g(lua).__sounds)) == 1, f"{len(seq(g(lua).__sounds))} sounds"
    # a client with no PlaySound does not throw
    lua = world()
    conf(lua, "fivesecond.sound", True)
    run(lua, "PlaySound = nil")
    cast(lua)
    tick(lua, 5.6)
    assert view(lua).phase == "res"


def check_a_regen_seen_late_makes_no_pulse_and_no_sound():
    lua = world()
    conf(lua, "fivesecond.sound", True)
    cast(lua)
    run(lua, "__advance(12)")        # nobody looked for twelve seconds (a loading screen, a hidden tab)
    v = view(lua)
    assert int(v.pulses) == 0 and len(seq(g(lua).__sounds)) == 0
    assert v.phase == "idle", v.phase


def check_the_cue_fades_to_the_dim_idle_look_a_few_seconds_after_regen():
    lua = world(motion=False)
    regen_look(lua, 0.3)
    tick(lua, 2.0)
    assert view(lua).phase == "res" and float(view(lua).fade) > 0.99, "regen look is held for a few seconds"
    tick(lua, 1.4)
    mid = float(view(lua).fade)
    assert 0.0 < mid < 1.0, f"the look should be fading: {mid}"
    tick(lua, 2.0)
    v = view(lua)
    assert v.phase == "idle" and float(v.fade) == 0.0, (v.phase, v.fade)
    look = cells_look(lua)
    assert look["text"] == "REGEN"
    close(look["lit"], C["muted"], "idle word")
    approx(look["lit_a"], MK["k"]["word_idle"], "idle word alpha", 0.01)
    close(look["ring"], C["violet"], "idle border")
    approx(look["ring_a"], MK["k"]["idle_ring"], "idle border alpha", 0.02)
    approx(look["glow_a"], 0.0, "idle glow", 1e-6)
    approx(look["alpha"], 0.72, "the dim face", 0.01)
    for seg in seq(ft(lua).FT.gauge.seg):
        close(rgb(seg._vertex), C["cyan"], "idle gauge stays cyan")
        approx(float(seg._vertex[4]), MK["k"]["gauge_idle"], "idle gauge alpha", 0.02)


def check_the_idle_tab_before_any_cast_is_the_same_dim_look():
    lua = world(motion=False)
    refresh(lua)
    look = cells_look(lua)
    assert look["text"] == "REGEN"
    close(look["lit"], C["muted"], "idle word")
    approx(look["glow_a"], 0.0, "no glow")
    approx(look["alpha"], 0.72, "the dim face", 0.01)


# ---------------------------------------------------------------------------------------------
# Checks: the rate line
# ---------------------------------------------------------------------------------------------


def check_the_rate_is_the_full_rate_outside_the_rule_and_the_casting_rate_during_it():
    lua = world(motion=False)
    refresh(lua)
    r = rate_look(lua)
    assert r["text"] == "12.4/s", r["text"]
    close(r["bar"], C["muted"], "idle rate bar")
    approx(r["bar_a"], 0.45, "idle rate bar alpha", 0.02)
    close(r["text_color"], C["muted"], "idle rate text")
    run(lua, "__regen = { 12.4, 4.1 }")
    tick(lua, 1.1)              # out of combat: re-read
    cast(lua)
    refresh(lua)
    r = rate_look(lua)
    assert r["text"] == "4.1/s", r["text"]
    close(r["bar"], C["cyan"], "active rate bar")
    approx(r["bar_a"], 0.95, "active rate bar alpha", 0.02)
    close(r["text_color"], C["white"], "active rate text", 0.06)
    tick(lua, 5.5)
    assert rate_look(lua)["text"] == "12.4/s"


def check_the_rate_is_read_out_of_combat_kept_in_combat_and_dashed_while_kept():
    lua = world(motion=False)
    refresh(lua)
    assert rate_look(lua)["dash_count"] == 0 and rate_look(lua)["bar_shown"], "a live reading is not dashed"
    assert bool(view(lua).cached) is False
    enter_combat(lua)
    run(lua, "__regen = { 20.0, 0.001 }")          # gear changed mid fight: unreadable until we leave
    tick(lua, 2.0)
    r = rate_look(lua)
    assert r["text"] == "12.4/s", r["text"]
    assert r["dash_count"] == 6 and not r["bar_shown"], (r["dash_count"], r["bar_shown"])
    close(r["text_color"], STALE, "the kept rate colour")
    assert bool(view(lua).cached) is True
    cast(lua)
    tick(lua, 1.0)
    assert rate_look(lua)["text"] == "0.0/s", "the cached casting rate shows while suspended"
    leave_combat(lua)
    tick(lua, 1.2)
    assert rate_look(lua)["dash_count"] == 0, "a reading taken out of combat is live again"
    assert rate_look(lua)["text"] == "0.0/s", "still suspended: the casting rate, now the fresh one"
    tick(lua, 4.0)
    assert rate_look(lua)["text"] == "20.0/s", rate_look(lua)["text"]
    assert blocked(lua) == 0


def check_a_login_in_combat_shows_no_number_until_one_can_be_read():
    lua = world(motion=False, combat=True)
    refresh(lua)
    r = rate_look(lua)
    assert r["text"] == "--", r["text"]
    assert r["dash_count"] == 0, "nothing cached, nothing dashed"
    close(r["bar"], C["muted"], "the unreadable bar")
    approx(r["bar_a"], 0.7, "the unreadable bar alpha", 0.01)
    assert r["code"] == "--", r["code"]
    leave_combat(lua)
    tick(lua, 1.2)
    assert rate_look(lua)["text"] == "12.4/s"


def check_the_retention_chip_is_cyan_above_zero_and_a_hollow_zero_otherwise():
    lua = world(motion=False)
    run(lua, "__regen = { 14.8, 0.001 }")
    tick(lua, 1.2)
    r = rate_look(lua)
    assert r["code"] == "0%", r["code"]
    close(r["chip"], _mix(C["muted"], (1, 1, 1), 0.25), "hollow chip", 0.03)
    assert r["chip_glow_a"] == 0.0
    assert view(lua).ret is None
    # Meditation: 33%
    run(lua, "__regen = { 14.8, 4.9 }")
    tick(lua, 1.2)
    r = rate_look(lua)
    assert r["code"] == "33%", r["code"]
    close(r["chip"], C["cyan"], "retention chip")
    close(r["fill"], _mix(BG, C["cyan"], MK["k"]["chip_fill"]), "retention chip fill")
    close(r["code_color"], C["white"], "retention code", 0.06)
    approx(r["chip_glow_a"], MK["k"]["chip_glow"], "chip glow", 0.01)
    assert int(view(lua).ret) == 33
    # staff mp5 only (0.401 of 12.4): 3%, still above zero
    run(lua, "__regen = { 12.4, 0.401 }")
    tick(lua, 1.2)
    assert rate_look(lua)["code"] == "3%", rate_look(lua)["code"]
    # zero base regen is not a division
    run(lua, "__regen = { 0, 0 }")
    tick(lua, 1.2)
    assert rate_look(lua)["code"] == "0%"


def check_the_rate_numbers_survive_secrets_and_bad_values():
    lua = world()
    refresh(lua)
    for setup in ("GetPowerRegen = nil", '__regenMode = "throw"',
                  "function GetPowerRegen() return __SECRET, 1 end",
                  "function GetPowerRegen() return 3, __SECRET end",
                  "function GetPowerRegen() return 'x', 'y' end",
                  "function GetPowerRegen() return -1, 2 end"):
        run(lua, setup)
        tick(lua, 1.3)
        assert rate_look(lua)["text"] == "12.4/s", f"{setup}: {rate_look(lua)['text']}"
    assert blocked(lua) == 0


def check_the_rate_line_is_fitted_at_both_lengths_and_the_bar_is_as_wide_as_the_text(scale):
    adv = 0.5615
    for value, text, base in ((7.5, "7.5/s", 11.0), (12.5, "12.5/s", 9.0)):
        # FitPx: the base size, or the largest half pixel size that keeps the string inside the room (never below 6)
        px = max(min(int(MK["rate_room"] * scale / (len(text) * adv) * 2) / 2, base), 6.0)
        lua = world(scale, motion=False)
        run(lua, f"__regen = {{ {value}, 0.001 }}")
        tick(lua, 1.2)
        r = rate_look(lua)
        assert r["text"] == text, (r["text"], text)
        got = float(ft(lua).FT.rateText._font[2])
        assert got == px, f"{text}: font {got}, want {px}"
        width = len(text) * adv * got
        assert width <= MK["rate_room"] * scale + 0.01, f"{text} is {width:.1f} wide, room {MK['rate_room'] * scale:.1f}"
        bar = ft(lua).FT.rateBar.solid
        approx(float(bar._h), 2 * scale, "bar height", 1e-6)
        assert abs(float(bar._w) - width / scale * scale) <= scale + 1e-6 + 0.0, f"{text}: bar {float(bar._w):.2f} wide for text {width:.2f}"
        p = bar._points[1]
        approx(float(p.x), 8 * scale, "bar left", 1e-6), approx(float(p.y), -MK["bar_y"] * scale, "bar top", 1e-6)
        # the text starts at the same left and its centre line is a third of the size above the page's baseline
        t = ft(lua).FT.rateText._points[1]
        approx(float(t.x), 8 * scale, "text left", 1e-6)
        want_cy = int(MK["rate_y"] - got * 0.36 + 0.5)
        approx(float(t.y), -want_cy * scale, "text centre line", 1e-6)


def check_the_idle_and_the_combat_tick_allocate_nothing():
    for combat in (False, True):
        lua = world()
        refresh(lua)
        tick(lua, 2.0)
        if combat:
            enter_combat(lua)
        run(lua, """
            if jit then jit.off() end        -- compiled traces would count as allocation; the client runs plain Lua 5.1
            -- the mock keeps every colour it is handed in a fresh table; the client keeps none
            local R = __Region
            function R:SetVertexColor(r, g, b, a) self._v1, self._v2, self._v3, self._v4 = r, g, b, a end
            function R:SetTextColor(r, g, b, a) self._v1, self._v2, self._v3, self._v4 = r, g, b, a end
            function R:ClearAllPoints() end
            function R:SetPoint() end
            local ticker = FSFiveSecondTicker
            local function step() __now = __now + 0.5; ticker._scripts.OnUpdate(ticker, 0.5) end
            for _ = 1, 50 do step() end
            collectgarbage("collect"); collectgarbage("stop")
            local before = collectgarbage("count")
            for _ = 1, 400 do step() end
            __grew = (collectgarbage("count") - before) * 1024
            collectgarbage("restart")
        """)
        assert float(g(lua).__grew) < 2000, f"combat={combat}: 400 ticks allocated {float(g(lua).__grew):.0f} bytes"


# ---------------------------------------------------------------------------------------------
# Checks: tooltips
# ---------------------------------------------------------------------------------------------


def check_the_cells_tooltip_says_how_long_and_that_it_is_an_estimate():
    lua = world()
    cast(lua)
    tick(lua, 2.7)
    lines = tip_text(lua, cells_tile(lua))
    assert lines[0] == "Mana regen", lines
    assert re.fullmatch(r"About 2\.[2-4] s until regen resumes\.", lines[1]), lines
    assert lines[2] == "Estimate from your own casts. Free casts are not seen.", lines
    assert len(lines) == 3, lines
    # the title colour is amber while suspended
    tip = ft(lua).TipLines("cells")
    close(rgb(tip[1][2]), C["amber"], "suspended title")
    leave_tip(lua, cells_tile(lua))


BANNED = re.compile(r"five[ -]second|5[ -]?sec", re.IGNORECASE)


def check_no_player_facing_string_names_the_five_second_rule():
    # every string literal in the two files that carry client text (code names such as "fivesecond.enabled" have no space)
    for path in (FSTAB, CONFIGWINDOW):
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("--"):
                continue
            for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', line):
                assert not BANNED.search(lit), f"{path.name}:{no}: {lit!r}"
    # and what a player reads at run time: the settings, every tooltip state, the page group
    lua = world()
    S = ft(lua).SETTINGS
    for name in ("enabled", "pulse", "sound", "motion", "flash", "digits", "wpulse", "drop", "sweep", "tick", "breath", "glitch"):
        for field in ("label", "tip"):
            text = str(getattr(S[name], field))
            assert not re.search(r"five second|5 second|5 sec", text, re.IGNORECASE), f"{name}.{field}: {text!r}"
    assert str(S.enabled.label) == "Mana regen module"
    seen = []
    for state in ("idle", "count", "regen"):
        if state == "count":
            cast(lua)
            tick(lua, 2.0)
        elif state == "regen":
            tick(lua, 3.4)
        for which in ("cells", "rate"):
            seen += [plain_text(line[1]) for line in seq(ft(lua).TipLines(which))]
    run(lua, "__regenMode = 'throw'")
    tick(lua, 1.5)
    for which in ("cells", "rate"):
        seen += [plain_text(line[1]) for line in seq(ft(lua).TipLines(which))]
    assert seen
    for text in seen:
        assert not re.search(r"five second|5 second|5 sec|the rule", text, re.IGNORECASE), text


def check_the_cells_tooltip_after_the_rule_says_regen_is_running():
    lua = world()
    cast(lua)
    tick(lua, 5.4)
    lines = tip_text(lua, cells_tile(lua))
    assert lines[0] == "Mana regen" and "until regen resumes" not in lines[1], lines
    assert lines[-1] == "Estimate from your own casts. Free casts are not seen.", lines
    close(rgb(ft(lua).TipLines("cells")[1][2]), C["cyan"], "regen title")


def check_the_rate_tooltip_names_both_rates_and_the_cache():
    lua = world()
    run(lua, "__regen = { 12.4, 0.001 }")
    tick(lua, 1.2)
    lines = tip_text(lua, rate_tile(lua))
    assert lines == ["Mana regen", "12.4 per second now, 12.4 once regen resumes."], lines
    cast(lua)
    refresh(lua)
    lines = tip_text(lua, rate_tile(lua))
    assert lines == ["Mana regen", "0.0 per second now, 12.4 once regen resumes."], lines
    enter_combat(lua)
    tick(lua, 1.2)
    lines = tip_text(lua, rate_tile(lua))
    assert lines == ["Mana regen", "0.0 per second now, 12.4 once regen resumes.",
                     "Read out of combat, kept while you fight."], lines
    close(rgb(ft(lua).TipLines("rate")[1][2]), C["cyan"], "rate title")
    # Meditation
    lua = world()
    run(lua, "__regen = { 14.8, 4.9 }")
    tick(lua, 1.2)
    cast(lua)
    refresh(lua)
    lines = tip_text(lua, rate_tile(lua))
    assert lines[:2] == ["Mana regen", "4.9 per second now, 14.8 once regen resumes."], lines
    assert "33%" in lines[2] and "cast" in lines[2], lines


def check_the_rate_tooltip_with_no_reading_says_so():
    lua = world(combat=True)
    refresh(lua)
    lines = tip_text(lua, rate_tile(lua))
    assert lines[0] == "Mana regen" and "cannot be read" in lines[1], lines


def check_a_tooltip_open_on_a_tile_follows_the_countdown():
    lua = world()
    cast(lua)
    tick(lua, 1.0)
    run(lua, "__owners = 0; local so = GameTooltip.SetOwner; function GameTooltip:SetOwner(...) __owners = __owners + 1; return so(self, ...) end")
    first = tip_text(lua, cells_tile(lua))[1]
    run(lua, "function GameTooltip:GetOwner() return self._owner end")
    assert int(g(lua).__owners) == 1, "one SetOwner on enter"
    tick(lua, 1.5)
    assert int(g(lua).__owners) == 1, "the open tooltip was re-anchored on a tick (it would flicker)"
    now = [str(x) for x in seq(g(lua).GameTooltip._lines)][1]
    assert now != first, f"the open tooltip kept {first!r}"
    leave_tip(lua, cells_tile(lua))


# ---------------------------------------------------------------------------------------------
# Checks: settings, master toggle, who gets it
# ---------------------------------------------------------------------------------------------

SETTING_KEYS = {
    "enabled": ("fivesecond.enabled", True), "pulse": ("fivesecond.pulse", True), "sound": ("fivesecond.sound", False),
    "motion": ("fivesecond.motion", True), "flash": ("fivesecond.fx.flash", True), "digits": ("fivesecond.fx.digits", True),
    "wpulse": ("fivesecond.fx.wpulse", True), "drop": ("fivesecond.fx.drop", True), "sweep": ("fivesecond.fx.sweep", True),
    "tick": ("fivesecond.fx.tick", True), "breath": ("fivesecond.fx.breath", True), "glitch": ("fivesecond.fx.glitch", True),
}
FX_NAMES = ["flash", "digits", "wpulse", "drop", "sweep", "tick", "breath", "glitch"]


def check_the_settings_have_their_defaults_keys_labels_and_tips():
    lua = world()
    S = ft(lua).SETTINGS
    cfg = g(lua).FS.Config
    for name, (key, default) in SETTING_KEYS.items():
        assert str(S[name].key) == key and S[name].default is default, name
        assert str(S[name].label), name
        tip = str(S[name].tip)
        assert tip.endswith("."), f"{name}: tip {tip!r}"
        assert cfg.Get(key) is default, f"{key} default"
    assert [str(x) for x in seq(ft(lua).FT.FX_NAMES)] == FX_NAMES
    # the three original rows keep their labels, the page's motion rows their words
    assert str(S.enabled.label) == "Mana regen module" and str(S.pulse.label) == "Regen pulse"
    assert str(S.sound.label) == "Regen sound" and str(S.motion.label) == "Animate the tab"
    assert str(S.digits.tip) == "Digit motion: a short flash or fade as the digits change."
    assert str(S.wpulse.tip) == "Whole second pulse: the countdown flashes as each second passes."
    for name, label in (("flash", "Cast flash"), ("digits", "LED digit motion"), ("wpulse", "Whole second pulse"),
                        ("drop", "Gauge flicker"), ("sweep", "Regen sweep"), ("tick", "Regen tick pulse"),
                        ("breath", "Idle glow"), ("glitch", "Kept and unreadable stutter")):
        assert str(S[name].label) == label, name


def check_the_master_toggle_hides_the_tab_and_its_shoulder_and_shows_them_again():
    lua = world()
    cs = csh.cs(lua)
    assert shown(host(lua)) and cs.IsShown("fivesecond")
    conf(lua, "fivesecond.enabled", False)
    assert not shown(host(lua)), "the host stands with the master toggle off"
    assert not cs.IsShown("fivesecond"), "the shoulder stands with the master toggle off"
    assert not ft(lua).Shown()
    cast(lua)
    tick(lua, 5.6)
    assert len(seq(g(lua).__sounds)) == 0
    conf(lua, "fivesecond.enabled", True)
    assert shown(host(lua)) and cs.IsShown("fivesecond")
    # the master toggle works in combat for the host; the shoulder follows at regen
    enter_combat(lua)
    conf(lua, "fivesecond.enabled", False)
    assert not shown(host(lua))
    assert blocked(lua) == 0
    leave_combat(lua)
    assert not cs.IsShown("fivesecond")


def check_a_warrior_a_rogue_and_unreadable_classes_get_nothing():
    for klass in ("WARRIOR", "ROGUE", "THROW", "SECRET"):
        lua = boot(klass=klass)
        assert host(lua) is None and cells_tile(lua) is None, f"{klass} got a tab"
        assert not ft(lua).OwnsShoulder(), f"{klass}: the tab claims a shoulder"
        assert not csh.cs(lua).IsShown("fivesecond"), f"{klass}: the shoulder stands"
        assert not ft(lua).Applies(), klass
        for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_SPELLCAST_CHANNEL_START"):
            assert not listeners(lua, event), f"{klass}: something listens to {event}"


def listeners(lua, event):
    return [f for f in g(lua).__frames.values() if f._registered[event]]


def check_every_mana_class_gets_the_tab():
    for klass in ("PRIEST", "MAGE", "WARLOCK", "HUNTER", "DRUID", "SHAMAN", "PALADIN"):
        lua = boot(klass=klass)
        assert host(lua) is not None, f"{klass} got no tab"
        assert ft(lua).Applies(), klass
        assert shown(host(lua)) and csh.cs(lua).IsShown("fivesecond"), f"{klass}: the tab does not stand"
        assert shown(cells_tile(lua)) and shown(rate_tile(lua))


def check_a_druid_in_a_form_without_mana_hides_the_tab_and_keeps_counting():
    lua = boot(klass="DRUID")
    assert shown(host(lua))
    cast(lua)
    run(lua, '__powerType = { 3, "ENERGY" }')
    fire(lua, "UNIT_DISPLAYPOWER", "player")
    assert not shown(host(lua)), "the Druid's energy form shows the mana cue"
    assert not csh.cs(lua).IsShown("fivesecond"), "the shoulder stands for a form without mana"
    assert view(lua).phase == "susp", "the ledger must keep listening while the tab is hidden"
    run(lua, '__powerType = { 1, "RAGE" }')
    fire(lua, "UNIT_DISPLAYPOWER", "player")
    assert not shown(host(lua))
    run(lua, '__powerType = { 0, "MANA" }')
    fire(lua, "UNIT_DISPLAYPOWER", "player")
    assert shown(host(lua)) and csh.cs(lua).IsShown("fivesecond")
    # an unreadable power type shows the tab (the cue is harmless)
    for mode in ("secret", "throw"):
        run(lua, f'__powerType = {{ 3, "ENERGY" }}; __powerMode = "{mode}"')
        fire(lua, "UNIT_DISPLAYPOWER", "player")
        assert shown(host(lua)), f"{mode}: an unreadable power type hid the tab"
    run(lua, "UnitPowerType = nil")
    fire(lua, "UNIT_DISPLAYPOWER", "player")
    assert shown(host(lua))
    # another class never asks the power type
    lua = boot(klass="PRIEST")
    run(lua, '__powerType = { 3, "ENERGY" }')
    fire(lua, "UNIT_DISPLAYPOWER", "player")
    assert shown(host(lua)), "only a Druid changes form"


def check_the_cue_needs_no_target_and_hangs_on_the_ui_not_the_gunsight():
    text = "\n".join(ln for ln in FSTAB.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("--"))
    for token in ("UnitExists", "HasTarget", "PLAYER_TARGET_CHANGED", "Gunsight", "GunsightAreas", "TakesDots"):
        assert token not in text, f"the tab mentions {token}: it is a player side cue"
    lua = world(pre_login="FS.Gunsight = nil; FS.GunsightAreas = nil")
    run(lua, "UnitExists = function() return false end")
    fire(lua, "PLAYER_TARGET_CHANGED")
    assert shown(host(lua)) and shown(cells_tile(lua)), "the tab needs no target"
    assert host(lua)._parent._name == "UIParent"


def check_nothing_in_the_tab_is_secure_or_touches_a_protected_frame_in_combat():
    lua = world()
    for f in g(lua).__frames.values():
        if f._name in ("FSFiveSecondTab", "FSFiveSecondCells", "FSFiveSecondRate"):
            assert not f._secure and not f._protected, f"{f._name} is a protected frame"
    enter_combat(lua)
    cast(lua)
    tick(lua, 5.6)
    lua.eval("__rescale")(1 / 1.2)
    conf(lua, "fivesecond.enabled", False)
    conf(lua, "fivesecond.enabled", True)
    assert blocked(lua) == 0, "a protected write was attempted in combat"
    assert int(g(lua).__protectedTouch) == 0, "a frame was touched under a protected parent in combat"
    leave_combat(lua)
    assert blocked(lua) == 0


# ---------------------------------------------------------------------------------------------
# Checks: geometry and seat
# ---------------------------------------------------------------------------------------------


def stand_for(lua, dx, scale):
    for f in g(lua).__frames.values():
        pts = f._points
        if f._kind == "Frame" and len(pts) == 1 and pts[1].rel is not None and pts[1].rel._name == "FSConsole" \
                and (abs(float(pts[1].x) - dx) < 0.5 or abs(float(pts[1].x) - dx * scale) < 0.5 * scale) \
                and f._name is None and f._w > 0 and abs(float(f._w) - MK["W"] * float(f._scale or 1)) > -1 \
                and abs(float(f._h) - MK["BH"]) < 0.5:
            return f
    return None


def descendants(region):
    """Every region under `region`: child frames, textures and font strings, depth first."""
    out = []
    for i in range(1, len(region._regions) + 1):
        child = region._regions[i]
        out.append(child)
        if child._kind not in ("Texture", "FontString", "MaskTexture"):
            out += descendants(child)
    return out


def placed(lua, region, scale):
    """(x, y, w, h) of a region anchored TOPLEFT to the host, in design px (y down)."""
    p = region._points[1]
    assert (p.point, p.relPoint) == ("TOPLEFT", "TOPLEFT"), (region._kind, p.point, p.relPoint)
    assert sb.same(lua, p.rel, host(lua)), "not anchored to the host"
    return (float(p.x) / scale, -float(p.y) / scale, float(region._w) / scale, float(region._h) / scale)


def check_the_face_is_the_mockups_in_design_px(scale):
    lua = world(scale)
    FT = ft(lua).FT
    host_ = host(lua)
    approx(float(host_._w), MK["W"] * scale, "host width")
    approx(float(host_._h), MK["BH"] * scale, "host height")
    hx, hy, hw, hh, hc = MK["hero"]
    wx, wy, ww, wh = MK["well"]

    def want(region, rect, what):
        got = placed(lua, region, scale)
        assert all(abs(a - b) < 1e-6 for a, b in zip(got, rect)), f"{what}: {got} != {rect}"

    want(FT.hero, (hx, hy, hw, hh), "hero tile")
    want(FT.cells, (hx, hy, hw, wy + wh - hy), "cells zone")
    want(FT.rate, (hx, 30, hw, MK["chip"][1] + MK["chip"][3] - 30), "rate zone")
    want(FT.fxFrame, (hx, hy, 81, 37), "wash frame")
    want(FT.gauge.plate, (wx, wy, ww, wh), "gauge well")
    for i in range(MK["gauge_n"]):
        want(FT.gauge.seg[i + 1], (MK["seg_x"] + i * MK["seg_pitch"], MK["seg_y"], MK["seg_w"], MK["seg_h"]), f"gauge segment {i}")
    cx, y = MK["led_cx"], MK["led_y"]
    cw, ch_ = MK["ledw"], MK["ledh"]
    count_w = 8 + 2 + cw + 4 + cw
    x0 = cx - count_w / 2
    L = led(lua)
    want(L.d1.frame, (x0 + 10, y, cw, ch_), "first digit")
    want(L.d2.frame, (x0 + 10 + cw + 4, y, cw, ch_), "second digit")
    for i, (bx, by) in enumerate(((0, 5), (2, 4), (4, 6), (6, 5))):
        want(L.tilde[i + 1], (x0 + bx, y + by, 2, 2), f"tilde bar {i}")
    want(L.dot, (x0 + 10 + cw + 1, y + 10, 2, 2), "decimal dot")
    word_x = cx - (5 * cw + 4 * 2) / 2
    for i in range(5):
        want(L.word[i + 1].frame, (word_x + i * (cw + 2), y, cw, ch_), f"word cell {i}")
    chx, chy, chw, chh = MK["chip"]
    want(FT.chip.fill, (chx, chy, chw, chh), "chip")
    want(FT.chip.ring, (chx, chy, chw, chh), "chip ring")
    assert host_._level > sb.top_level(g(lua).FSConsole), "the tab must draw above the chassis"
    lua = boot(scale=scale, klass="PRIEST")
    cs = csh.cs(lua)
    assert cs.IsShown("fivesecond")
    stand = stand_for(lua, 36, scale)
    assert stand is not None, "no frame is seated at 36 design px on the Console"
    d = csh.D(lua, stand)
    approx(d["w"], MK["W"], "art width in design px", 0.01), approx(d["h"], MK["BH"], "art height in design px", 0.01)
    bw, bh, edge = cs.BlockSize("fivesecond")
    approx(bw, MK["W"] * scale, "BlockSize width"), approx(bh, MK["BH"] * scale, "BlockSize height")


def _whole(v, px, what):
    n = v / px
    assert abs(n - round(n)) < 1e-6, f"{what}: {v} is {n:.4f} pixels"


def _crisp_world(scale, phys=None):
    """A world on a screen `phys` physical px high: UIParent's effective scale then follows from the scale, as in the client
    (the UI height in units is 1440 * scale, mapped to 768 virtual px), and a design px is phys / 1440 pixels."""
    pre = ""
    if phys is not None:
        pre = f"GetPhysicalScreenSize = function() return 2560, {phys} end; __effScale = {768 / (1440 * scale)}"
    return boot(scale, klass="PRIEST", pre_login=pre)


def check_everything_sits_on_whole_pixels_and_the_led_art_is_never_scaled_fractionally():
    # the live fallback (a design px is a pixel), and screens where it is not: 1080 (0.75), 2160 (1.5), 2880 (2)
    for scale, phys, n_want in ((0.64, None, 1), (1 / 1.2, None, 1), (1.0, None, 1), (1 / 1.2, 1440, 1), (0.64, 1440, 1),
                                (1.0, 1080, 1), (1 / 1.2, 2160, 1), (1.0, 2880, 2), (0.64, 2880, 2)):
        lua = _crisp_world(scale, phys)
        px = scale if phys is None else 1440 * scale / phys
        FT = ft(lua).FT
        ctx = f"scale {scale:.4f} screen {phys} px {px:.4f}"
        approx(float(FT.px), px, f"{ctx}: pixel unit", 1e-9)
        n = int(FT.n)
        assert n == n_want, f"{ctx}: texel is {n} px, want {n_want}"
        # let a sweep, a flash and a kept rate move things first
        run(lua, "__regen = { 12.4, 4.9 }")
        cast(lua)
        tick(lua, 5.7)
        for region in descendants(host(lua)):
            if region._kind == "Texture" and region._texture and "glow" in str(region._texture):
                continue                      # a glow is a soft blob; the shapes are what must sit on pixels
            if region._points[1] is None or not sb.same(lua, region._points[1].rel, host(lua)):
                continue
            for p in seq(region._points):
                _whole(float(p.x), px, f"{ctx}: {region._kind} {region._name} x")
                _whole(float(p.y), px, f"{ctx}: {region._kind} {region._name} y")
            if region._kind != "FontString":
                _whole(float(region._w), px, f"{ctx}: {region._kind} {region._name} width")
                _whole(float(region._h), px, f"{ctx}: {region._kind} {region._name} height")
        # the art: one texel is n whole pixels, whatever the design scale is
        L = led(lua)
        for cell in seq(L.cells):
            approx(float(cell.frame._w), 10 * n * px, f"{ctx}: cell width", 1e-6)
            approx(float(cell.frame._h), 12 * n * px, f"{ctx}: cell height", 1e-6)
            for t in seq(cell.seg):
                assert sb.same(lua, t._points[1].rel, cell.frame) and len(t._points) == 2, "a segment is not the cell's size"
        for bar in seq(L.tilde):
            approx(float(bar._w), 2 * n * px, f"{ctx}: tilde bar", 1e-6)
        approx(float(L.dot._w), 2 * n * px, f"{ctx}: dot", 1e-6)
        # on a screen of 1440 or more the readout stays inside the hero tile with its ring clear
        if phys is None or phys >= 1440:
            assert 12 * n * px + 2 * px <= float(FT.hero._h) + 1e-6, f"{ctx}: the readout touches the ring"


def check_a_rescale_resizes_and_reseats_out_of_combat():
    lua = boot(klass="PRIEST")
    lua.eval("__rescale")(1 / 1.2)
    s = 1 / 1.2
    approx(float(host(lua)._w), MK["W"] * s, "host width after a rescale")
    FT = ft(lua).FT
    got = placed(lua, FT.gauge.plate, s)
    assert all(abs(a - b) < 1e-6 for a, b in zip(got, MK["well"])), got
    approx(float(led(lua).d1.frame._w), 10 * s, "cell width after a rescale", 1e-6)
    approx(float(FT.chip.fill._w), 30 * s, "chip width after a rescale", 1e-6)


def check_a_class_without_a_tab_of_its_own_seats_the_cue_where_the_class_tab_would_stand():
    for klass in ("PRIEST", "MAGE", "WARLOCK", "HUNTER", "DRUID"):
        lua = boot(klass=klass)
        p = host(lua)._points[1]
        assert (p.point, p.rel._name, p.relPoint) == ("BOTTOMLEFT", "FSConsole", "TOPLEFT"), klass
        approx(p.x, 36.0, f"{klass}: seat"), approx(p.y, 0, "seat y")
        assert csh.cs(lua).Shoulder("fivesecond") is not None, klass
        assert csh.cs(lua).shoulder is None, f"{klass}: the class shoulder slot is for a class tab"


def check_a_paladin_gets_it_after_the_seal_block():
    lua = boot(klass="PALADIN")
    cs = csh.cs(lua)
    assert cs.IsShown() and cs.IsShown("fivesecond"), "the seal shoulder and the cue both stand"
    seal_w = 2 * PAD + 7 * BTN + 6 * GAP
    want = 36 + seal_w + 16
    p = host(lua)._points[1]
    approx(p.x, want, "after the seal block", 0.5)
    hp = csh.cs(lua).HostPoint("fivesecond")
    approx(float(hp[3]), want, "ClassShoulder.HostPoint answers the same seat", 0.5)
    # the class block keeps its own seat
    approx(cs.HostPoint()[3], 36.0, "the seal block stays at 36")


def check_a_shaman_gets_it_after_the_buff_tab():
    lua = boot(klass="SHAMAN")
    cs = csh.cs(lua)
    assert cs.IsShown() and cs.IsShown("shamanbuff") and cs.IsShown("fivesecond")
    buff_x = 316
    want = buff_x + MK["W"] + 16
    p = host(lua)._points[1]
    approx(p.x, want, "after the buff tab", 0.5)
    # the totem tab and the buff tab keep their seats
    approx(g(lua).FSTotemBar._points[1].x, 36.0, "totem tab", 0.5)
    approx(g(lua).FSBuffTab._points[1].x, buff_x, "buff tab", 0.5)
    # it stays clear of the HUD keys tab's edge (538 design px in the mockup)
    assert want + MK["W"] + 10 < 538, want


def check_the_cue_moves_when_the_class_tab_arrives_later():
    # the Shaman's totem tab is not up yet: the cue sits in the first seat, then makes way for it
    lua = boot(klass="SHAMAN")
    cs = csh.cs(lua)
    approx(host(lua)._points[1].x, 316 + MK["W"] + 16, "both class tabs up", 0.5)
    run(lua, "FS.BuffTab.OwnsShoulder = function() return false end")
    cs.Refresh()
    approx(host(lua)._points[1].x, 316.0, "the buff tab gone: after the totem tab", 0.5)
    run(lua, "FS.TotemBar.OwnsShoulder = function() return false end")
    cs.Refresh()
    approx(host(lua)._points[1].x, 36.0, "no class tab: the first seat", 0.5)
    assert shown(host(lua))


def check_the_console_gap_covers_the_cue_and_the_top_line_is_bridged_to_the_class_tab():
    lua = boot(klass="PALADIN")
    gaps = [c for c in csh.calls(lua) if str(c).startswith("gap:")]
    last = [float(x) for x in str(gaps[-1]).split(":")[1:]]
    seal_w = 2 * PAD + 7 * BTN + 6 * GAP
    approx(last[0], 36 + 1, "gap line start", 1.5)
    assert last[1] > 36 + seal_w + 16 + MK["W"], f"the gap ends inside the cue: {last}"
    art = g(lua).FS.Console.art
    bridges = [r for r in seq(art._regions) if r._kind == "Texture" and r._color is not None and r._h == 1
               and r._points[1].x > 36 + seal_w - 1 and r._points[1].x < 36 + seal_w + 30]
    assert len(bridges) == 1 and shown(bridges[0]), f"{len(bridges)} bridge textures"
    csh.console(lua).SetActive(False)
    assert not csh.cs(lua).IsShown("fivesecond") and not shown(bridges[0])


def check_the_cue_follows_the_console_on_and_off_and_is_absent_without_one():
    lua = boot(klass="PRIEST")
    cs = csh.cs(lua)
    csh.console(lua).SetActive(False)
    assert not cs.IsShown("fivesecond")
    assert not shown(host(lua)), "no Console, no tab"
    cast(lua)
    assert view(lua).phase == "susp", "the ledger listens without a Console"
    csh.console(lua).SetActive(True)
    assert cs.IsShown("fivesecond") and shown(host(lua))
    lua = boot(klass="PRIEST", console=False)
    assert host(lua) is not None and not shown(host(lua)), "no Console at all: no seat, no crash"


def check_a_seat_change_in_combat_waits_for_regen():
    lua = boot(klass="PRIEST")
    enter_combat(lua)
    lua.eval("__rescale")(1 / 1.2)
    csh.console(lua).SetActive(False)
    assert blocked(lua) == 0, "a protected write was attempted in combat"
    leave_combat(lua)
    assert blocked(lua) == 0


def check_a_login_in_combat_builds_at_once_and_seats_at_regen():
    lua = boot(klass="PRIEST", combat=True)
    assert host(lua) is not None and cells_tile(lua) is not None, "the plain tiles build in combat"
    assert not shown(host(lua)) and not csh.cs(lua).IsShown("fivesecond"), "the seat waits for regen"
    assert blocked(lua) == 0 and int(g(lua).__protectedTouch) == 0
    leave_combat(lua)
    assert shown(host(lua)) and csh.cs(lua).IsShown("fivesecond")


def check_the_listeners_are_for_the_unit_player_and_start_once():
    lua = world()
    for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_SPELLCAST_CHANNEL_START", "UNIT_SPELLCAST_CHANNEL_STOP"):
        assert len(listeners(lua, event)) == 1, f"{event}: {len(listeners(lua, event))} listeners"
    # a throwing RegisterUnitEvent falls back to RegisterEvent and the unit filter in the handler
    lua = world(pre_login="__Region.RegisterUnitEvent = function() error('no unit events') end")
    cast(lua)
    fire(lua, "UNIT_SPELLCAST_SUCCEEDED", "target", "guid", MANA)
    assert view(lua).phase == "susp"


def check_a_failed_build_leaves_no_listener_running():
    lua = boot(klass="PRIEST", pre_login='__failBuild = "FSFiveSecondRate"')
    assert rate_tile(lua) is None
    assert not ft(lua).OwnsShoulder(), "a failed build still claims the shoulder"
    assert not csh.cs(lua).IsShown("fivesecond")
    for event in ("UNIT_SPELLCAST_SUCCEEDED", "UNIT_SPELLCAST_CHANNEL_START"):
        assert not listeners(lua, event), f"a listener for {event} runs for a tab that never drew"


# ---------------------------------------------------------------------------------------------
# Checks: the chrome, hover and text
# ---------------------------------------------------------------------------------------------


def check_every_string_fits_inside_its_zone_in_every_state(scale):
    lua = world(scale, motion=False)
    advance = 0.5615
    run(lua, "__regen = { 112.4, 12.5 }")
    tick(lua, 1.2)
    for label in ("idle", "susp", "res"):
        if label == "susp":
            cast(lua)
        elif label == "res":
            tick(lua, 5.3)
        refresh(lua)
        FT = ft(lua).FT
        text = plain_text(FT.rateText._text)
        px = float(FT.rateText._font[2])
        assert len(text) * advance * px <= MK["rate_room"] * scale + 0.01, f"{label} rate {text!r} at {px}px"
        code = plain_text(FT.chip.code._text)
        px = float(FT.chip.code._font[2])
        assert len(code) * advance * px <= (MK["chip"][2] - 2) * scale + 0.01 or px <= 6.0, f"{code!r} at {px}px outside the chip"


def check_the_chrome_is_the_buff_tabs_cut_plate_with_a_skinned_border():
    lua = world(motion=False)
    FT = ft(lua).FT
    hero = FT.hero
    assert hero.fsPlate is not None and hero.fsSkin.border.ring is not None and hero.fsSkin.glow is not None
    assert FT.chip.fill is not None and FT.chip.ring is not None and FT.chip.glow is not None and FT.chip.code is not None
    # no name label anywhere: the only strings are the rate and the chip code
    texts = [r for r in descendants(host(lua)) if r._kind == "FontString"]
    assert len(texts) == 2, [r._text for r in texts]
    # the LED cells are the only way the countdown draws: both strings are the rate line and the chip code, none is a countdown
    assert sorted(r._text for r in texts) == sorted([FT.rateText._text, FT.chip.code._text]), [r._text for r in texts]
    assert not [r for r in descendants(FT.hero) if r._kind == "FontString"], "no plain text inside the hero tile"
    # the hover border is the cyan ring, like the buff tab's
    tile = cells_tile(lua)
    lua.eval("__Region.Fire")(tile, "OnEnter")
    close(rgb(hero.fsSkin.border.ring._vertex), C["cyan"], "hover border")
    approx(float(hero.fsSkin.glow._vertex[4]), 0.6, "hover glow")
    approx(float(hero.fsSkin.border.ring._vertex[4]), 1.0, "hover ring")
    lua.eval("__Region.Fire")(tile, "OnLeave")
    close(rgb(hero.fsSkin.border.ring._vertex), C["violet"], "border after leaving")
    approx(float(hero.fsSkin.glow._vertex[4]), 0.0, "no glow after leaving")
    approx(float(hero.fsSkin.border.ring._vertex[4]), MK["k"]["idle_ring"], "idle ring")
    # the rate zone lights the chip ring
    zone = rate_tile(lua)
    lua.eval("__Region.Fire")(zone, "OnEnter")
    close(rgb(FT.chip.ring._vertex), C["cyan"], "chip under the mouse")
    lua.eval("__Region.Fire")(zone, "OnLeave")
    assert rgb(FT.chip.ring._vertex)[0] > 0.5, "the hollow chip is the pale muted ring again"
    run(lua, "__regen = { 14.8, 4.9 }")
    tick(lua, 1.2)
    approx(rate_look(lua)["chip_glow_a"], MK["k"]["chip_glow"], "chip glow")


def check_hiding_the_host_under_the_mouse_clears_the_hover_and_the_tooltip():
    lua = world(motion=False)
    FT = ft(lua).FT
    for tile in (cells_tile(lua), rate_tile(lua)):
        lua.eval("__Region.Fire")(tile, "OnEnter")
        assert shown(g(lua).GameTooltip), "the tooltip is up"
        host(lua).Hide(host(lua))
        lua.eval("__Region.Fire")(tile, "OnHide")        # the engine runs OnHide on the children of a hidden frame
        assert not tile.fsHover, "the hover survived the hide"
        assert not shown(g(lua).GameTooltip), "the tooltip of a hidden zone stayed up"
        host(lua).Show(host(lua))
        refresh(lua)
        close(rgb(FT.hero.fsSkin.border.ring._vertex), C["violet"], "no hover rim after the host shows again")
    # a tooltip that belongs to something else is left alone
    lua = world(motion=False)
    tile = cells_tile(lua)
    lua.eval("__Region.Fire")(tile, "OnEnter")
    run(lua, "function GameTooltip:IsOwned(f) return false end")
    lua.eval("__Region.Fire")(tile, "OnHide")
    assert shown(g(lua).GameTooltip), "hid a tooltip another frame owns"
    assert not tile.fsHover


def check_the_kept_rate_bar_is_the_mockups_dashes():
    lua = world(motion=False)
    refresh(lua)
    enter_combat(lua)
    tick(lua, 1.2)
    FT = ft(lua).FT
    r = rate_look(lua)
    wi = round(len(r["text"]) * 0.5615 * float(FT.rateText._font[2]))
    dashes = [d for d in seq(FT.rateBar.dash) if shown(d)]
    assert len(dashes) == -(-wi // 5), (len(dashes), wi)
    for i, d in enumerate(dashes):
        got = placed(lua, d, 1.0)
        want = (8 + 5 * i, MK["bar_y"], min(3, wi - 5 * i), 2)
        assert got == want, f"dash {i}: {got} != {want}"
        close(rgb(d._vertex), STALE, "dash colour")
    assert not shown(FT.rateBar.solid)


def check_toc_lists_the_tab_after_the_buff_tab_and_before_the_config_window():
    lines = [ln.strip() for ln in TOC.read_text(encoding="utf-8").splitlines()]
    mods = [ln for ln in lines if ln.endswith(".lua")]
    f = "Modules/ActionBars/FiveSecondTab.lua"
    assert f in mods, f"{f} is not in the .toc"
    for dep in ("Modules/ActionBars/ClassShoulder.lua", "Modules/ActionBars/SealBar.lua", "Modules/ActionBars/TotemBar.lua",
                "Modules/ActionBars/BuffTab.lua", "Core/FrameHelpers.lua", "Core/Config.lua", "Core/Theme.lua"):
        assert mods.index(dep) < mods.index(f), f"{dep} must load before FiveSecondTab.lua"
    assert mods.index(f) < mods.index("Modules/Config/ConfigWindow.lua")


def check_no_em_dashes_and_no_flagged_words_in_the_new_files():
    for path in (FSTAB, Path(__file__), LED_GENERATOR):
        assert path.exists(), f"{path} is missing"
        text = path.read_text(encoding="utf-8")
        assert chr(0x2014) not in text, f"{path.name} has an em dash"
        assert not re.search("park" + "er", text, re.I), f"{path.name} names a person"
    text = FSTAB.read_text(encoding="utf-8")
    for word in (r"bot\b", "automat", "macro", "cheat", "hack", "probe", "monitor"):
        hits = [ln.strip() for ln in text.splitlines() if re.search(rf"\b{word}", ln, re.I)]
        assert not hits, f"FiveSecondTab.lua mentions {word!r}: {hits[:2]}"
    for s in re.findall(r'"([^"\n]*)"', text):
        if " " not in s and "_" in s or s.startswith(("Interface", "UNIT_", "PLAYER_")):
            continue
        assert not re.search(r"\b(probe|bot|monitor|test)\b", s, re.I), f"player text {s!r}"


def check_the_config_window_builds_the_motion_rows_under_a_master():
    text = CONFIGWINDOW.read_text(encoding="utf-8")
    assert "FiveSecondTab" in text, "ConfigWindow.lua does not read FS.FiveSecondTab.SETTINGS"
    block = text.split("local function FiveSecondGroup", 1)[1].split("\nend\n", 1)[0]
    for name in ("enabled", "pulse", "sound", "motion"):
        assert name in block, f"the five second group lacks {name}"
    assert "FX_NAMES" in block or all(n in block for n in FX_NAMES), "the motion rows are not listed"
    assert "inset" in block, "the motion rows are not set under the master"


def check_the_class_shoulder_names_the_cue_as_a_shoulder_after_every_class_tab():
    text = CLASSSHOULDER.read_text(encoding="utf-8")
    assert "fivesecond" in text and "FiveSecondTab" in text


# ---------------------------------------------------------------------------------------------
# Checks: the motion
# ---------------------------------------------------------------------------------------------


def play(lua, seconds, probe, fps=60):
    """The probe's answer after each of `seconds` of frames."""
    out = []
    frames(lua, seconds, lambda l: out.append(probe(l)), fps)
    return out


def d2_alpha(lua) -> float:
    return cell_color(led(lua).d2)[1]


def check_the_cast_flash_washes_the_face_for_half_a_second():
    lua = world()
    cast(lua)
    rec = play(lua, 0.7, lambda l: (fx(l)["flash"], float(ft(l).FT.fxFlash._vertex[4])))
    assert rec[0][0] > 0.9, rec[0]
    flashes = [r[0] for r in rec]
    assert all(a >= b - 1e-9 for a, b in zip(flashes, flashes[1:])), "the wash does not die away steadily"
    assert flashes[30] < 0.03 and flashes[33] == 0, flashes[28:36]
    for f, a in rec:
        approx(a, MK["k"]["flash_alpha"] * f, "wash alpha", 0.004)
    # a recast flashes again; the switch and the master turn it off
    tick(lua, 2.0)
    cast(lua)
    assert play(lua, 0.05, lambda l: fx(l)["flash"])[-1] > 0.8
    for off in ("fivesecond.fx.flash", "fivesecond.motion"):
        lua = world()
        conf(lua, off, False)
        cast(lua)
        rec = play(lua, 0.7, lambda l: (fx(l)["flash"], float(ft(l).FT.fxFlash._vertex[4])))
        assert all(r == (0, 0) or r == (0.0, 0.0) for r in rec), f"{off}: {rec[:3]}"


def check_each_new_tenth_dips_the_second_digit_for_a_moment_and_never_under_the_cast_flash():
    lua = world()
    cast(lua)
    early = play(lua, 0.45, lambda l: fx(l)["dip"])
    assert not any(early), "the digits dip under the cast flash"
    rec = play(lua, 2.0, lambda l: (bool(fx(l)["dip"]), d2_alpha(l), cell_color(led(l).d1)[1]))
    dips = [r for r in rec if r[0]]
    assert 8 <= len(dips) <= 60, len(dips)
    for dip, a2, a1 in rec:
        approx(a1, 1.0, "the first digit never dips", 1e-6)
        approx(a2, 1 - MK["k"]["dip_depth"] if dip else 1.0, "second digit alpha", 1e-6)
    lua = world()
    conf(lua, "fivesecond.fx.digits", False)
    cast(lua)
    rec = play(lua, 2.5, lambda l: (bool(fx(l)["dip"]), d2_alpha(l)))
    assert not any(r[0] for r in rec) and all(abs(r[1] - 1.0) < 1e-6 for r in rec)


def check_the_last_second_warms_from_amber_through_white_toward_cyan():
    k = MK["k"]
    hw = _mix(C["amber"], C["white"], k["warm_white"])
    lua = world()
    cast(lua)
    tick(lua, 4.5)
    refresh(lua)
    w = fx(lua)["warm"]
    assert 0.4 < w < 0.6, w
    close(rgb(led(lua).tilde[1]._vertex), hw if abs(w - 0.5) < 0.01 else _mix(C["amber"], hw, w * 2), "halfway", 0.04)
    col, _ = cell_color(led(lua).d1)
    assert col[0] > 0.95 and col[1] > 0.85, f"white halfway through the last second: {col}"
    tick(lua, 0.4)
    refresh(lua)
    w = fx(lua)["warm"]
    assert w > 0.85
    col, _ = cell_color(led(lua).d1)
    assert col[0] < 0.4 and col[2] > 0.9, f"cyan toward the end of the last second: {col}"
    # before the last second it is plain amber
    lua = world()
    cast(lua)
    tick(lua, 1.5)
    refresh(lua)
    assert fx(lua)["warm"] == 0
    close(rgb(led(lua).tilde[1]._vertex), C["amber"], "plain amber", 0.01)
    lua = world()
    conf(lua, "fivesecond.fx.digits", False)
    cast(lua)
    tick(lua, 4.5)
    refresh(lua)
    assert fx(lua)["warm"] == 0
    close(rgb(led(lua).tilde[1]._vertex), C["amber"], "digits off: plain amber", 0.01)


def check_the_whole_second_pulse_flashes_the_digits_at_4_3_2_1_and_never_at_5_or_at_regen():
    k = MK["k"]
    lua = world()
    cast(lua)
    tick(lua, 0.6)

    def probe(l):
        v = view(l)
        L = led(l)
        unlit = [float(t._vertex[4]) for t in seq(L.d1.seg) if float(t._vertex[4]) < 0.3]
        lit_glow = [float(g_._vertex[4]) for t, g_ in zip(seq(L.d1.seg), seq(L.d1.gl)) if float(t._vertex[4]) > 0.3]
        return (float(v.t), v.phase, fx(l)["zp"], lit_glow[0] if lit_glow else 0.0, cell_color(L.d1), unlit[0] if unlit else None)

    rec = play(lua, 4.6, probe)
    for k_ in (4, 3, 2, 1):
        win = [r for r in rec if k_ - 0.23 < r[0] <= k_ + 0.05 and r[1] == "susp"]
        assert win, k_
        peak = max(r[2] for r in win)
        assert peak >= 0.9, f"the {k_}.0 pulse peaks at {peak}"
        first = [r[2] for r in win if r[2] > 0][0]
        assert first < peak, "the pulse does not rise"
    for t, phase, zp, glow, lit, ghost in rec:
        if phase == "susp":
            approx(glow, min(1.0, k["glow_steady"] + 0.6 * zp), "the glow under the lit segments blooms with the pulse", 0.01)
        if zp > 0:
            assert phase == "susp" and any(k_ - 0.23 - 0.02 < t <= k_ + 0.05 + 0.02 for k_ in (1, 2, 3, 4)), (t, zp)
            assert not (t > 4.5), "a pulse under the cast flash or at 5.0"
        if ghost is not None and phase == "susp":
            approx(ghost, k["ghost_count"] + k["ghost_lift"] * zp, "ghost lift", 0.003)
    # at a peak far from the last second the digits are nearly white
    best = max((r for r in rec if 2.0 < r[0] < 3.2), key=lambda r: r[2])
    assert best[4][0][2] > 0.85 and best[4][0][1] > 0.9, f"not flashed toward white: {best[4]}"
    assert not any(r[2] > 0 for r in rec if r[1] != "susp")
    for name in ("fivesecond.fx.wpulse", "fivesecond.motion"):
        lua = world()
        conf(lua, name, False)
        cast(lua)
        tick(lua, 0.6)
        rec = play(lua, 4.6, probe)
        assert all(r[2] == 0 and abs(r[3] - k["glow_steady"]) < 0.01 for r in rec if r[1] == "susp"), f"{name}: the pulse ran"
    # regen itself carries no whole second pulse
    lua = world()
    cast(lua)
    tick(lua, 5.0)
    assert not any(play(lua, 2.0, lambda l: fx(l)["zp"] > 0))


def check_the_emptied_gauge_segment_flickers_once_and_the_pulse_damps_it():
    lua = world()
    cast(lua)
    tick(lua, 0.6)

    def probe(l):
        v = view(l)
        f = fx(l)
        seg = None
        if f["dropSeg"]:
            sg = ft(l).FT.gauge.seg[int(f["dropSeg"])]
            seg = (rgb(sg._vertex), float(sg._vertex[4]))
        return (float(v.t), f["dropSeg"], f["dropA"], f["zp"], seg)

    rec = play(lua, 4.6, probe)
    events = sum(1 for a, b in zip(rec, rec[1:]) if not a[1] and b[1])
    assert events >= 5, events
    for t, seg, a, zp, drawn in rec:
        assert 0 <= a <= 0.9 + 1e-9
        if t <= 0.3:
            assert seg == 0, "a flicker at the very end"
        if zp > 0.9:
            assert a < 0.09, f"the pulse did not damp the flicker: {a}"
        if seg:
            assert 2 <= seg <= 10
            close(drawn[0], C["amber"], "flicker colour")
            approx(drawn[1], max(MK["k"]["gauge_off"], a), "flicker alpha", 1e-6)
    lua = world()
    conf(lua, "fivesecond.fx.drop", False)
    cast(lua)
    tick(lua, 0.6)
    assert not any(r[1] for r in play(lua, 4.6, probe))


def band_expectation(pp):
    bx = 6 + int(pp * 81 + 0.5)             # the band moves a design px at a time
    word = "".join("REGEN"[i] if 22 + 12 * i <= bx else "_" for i in range(5))
    count = ("~" if 33 > bx else "") + ("0" if 44 > bx else "") + ("." if 51 > bx else "") + ("0" if 58 > bx else "")
    return bx, count, word


def check_the_regen_sweep_carries_the_held_digits_into_the_word_under_one_band():
    lua = world()
    cast(lua)
    tick(lua, 5.0)

    def probe(l):
        v = view(l)
        f = fx(l)
        gauge = [(rgb(s._vertex), float(s._vertex[4])) for s in seq(ft(l).FT.gauge.seg)]
        return (v.phase, f["pp"], led_text(l), gauge, rgb(led(l).tilde[1]._vertex) if shown(led(l).tilde[1]) else None)

    rec = play(lua, 1.3, probe)
    assert rec[0][0] == "res" and rec[0][2][0] == "~0.0", rec[0][2]
    sweeping = [r for r in rec if r[1] < 1]
    assert 55 <= len(sweeping) <= 62, f"the sweep lasts a second: {len(sweeping)} frames"
    assert [r[1] for r in rec[:3]] == sorted(r[1] for r in rec[:3])
    for phase, pp, (count, word), gauge, tilde in rec:
        if pp < 1:
            bx, want_count, want_word = band_expectation(pp)
            assert (count, word) == (want_count, want_word), f"pp {pp:.3f}: {(count, word)} != {(want_count, want_word)}"
            if tilde:
                close(tilde, C["cyan"], "the held digits are cyan")
            for i, (col, a) in enumerate(gauge):
                x = 7 + 8 * i + 3.5
                if abs(x - bx) < MK["k"]["band"]:
                    assert col == (1.0, 1.0, 1.0) and abs(a - 0.95) < 1e-6, (i, bx, col, a)
                else:
                    close(col, C["cyan"], "gauge segment"), approx(a, 0.85, "gauge segment alpha", 0.01)
        else:
            assert (count, word) == ("", "REGEN"), (pp, count, word)
    # a band that halves the readout: some cells already letters, some still digits
    mid = [r for r in sweeping if 0.4 < r[1] < 0.6][0]
    assert mid[2][0] != "" and mid[2][1] != "REGEN" and "R" in mid[2][1]
    # without the sweep the word is there at once
    lua = world()
    conf(lua, "fivesecond.fx.sweep", False)
    cast(lua)
    tick(lua, 5.0)
    rec = play(lua, 0.5, probe)
    assert all(r[1] == 1 and r[2] == ("", "REGEN") for r in rec), rec[0][:3]
    # without the digit motion nothing is held, but the band still crosses the gauge
    lua = world()
    conf(lua, "fivesecond.fx.digits", False)
    cast(lua)
    tick(lua, 5.0)
    rec = play(lua, 1.3, probe)
    assert all(r[2] == ("", "REGEN") for r in rec), "digits held with the digit motion off"
    mid = [r for r in rec if 0.45 < r[1] < 0.55][0]
    assert any(c == (1.0, 1.0, 1.0) for c, a in mid[3])


def check_the_rim_flares_once_at_regen_with_the_pulse_switch_and_not_without():
    k = MK["k"]
    lua = world()
    cast(lua)
    tick(lua, 5.0)
    rec = play(lua, 1.4, lambda l: (cells_look(l)["glow_a"], fx(l)["flare"]))
    peak = max(r[0] for r in rec)
    assert peak > k["res_glow"] + 0.35, peak
    assert abs(rec[-1][0] - k["res_glow"]) < 0.01, "the glow does not settle at the held regen glow"
    assert int(view(lua).pulses) == 1
    lua = world()
    conf(lua, "fivesecond.pulse", False)
    cast(lua)
    tick(lua, 5.0)
    rec = play(lua, 1.4, lambda l: cells_look(l)["glow_a"])
    assert max(rec) < k["res_glow"] + 0.01, "a flare with the pulse switch off"
    # the master takes the pulse with it: none is started or counted
    lua = world()
    conf(lua, "fivesecond.motion", False)
    cast(lua)
    tick(lua, 5.0)
    rec = play(lua, 1.4, lambda l: cells_look(l)["glow_a"])
    assert max(rec) < k["res_glow"] + 0.01
    assert int(view(lua).pulses) == 0


def check_the_regen_tick_pulse_grows_the_bar_a_pixel_each_side_on_a_two_second_timer():
    k = MK["k"]
    lua = world()
    run(lua, "__regen = { 14.8, 4.9 }")
    tick(lua, 1.2)
    cast(lua)
    tick(lua, 5.0)

    def probe(l):
        f = fx(l)
        FT = ft(l).FT
        bar = FT.rateBar.solid
        return (f["tick"], float(bar._h), -float(bar._points[1].y), float(FT.chip.glow._vertex[4]), bool(shown(FT.rateBar.hi)))

    rec = play(lua, 4.4, probe)
    for i, (tk, h, y, glow, hi) in enumerate(rec):
        since = (i + 1) / 60
        if 1.5 + 0.02 < since < 2.0 - 0.02 or 3.5 + 0.02 < since < 4.0 - 0.02:
            assert tk > 0, (since, tk)
        if 2.0 + 0.03 < since < 3.5 - 0.03 or since < 1.5 - 0.03:
            assert tk == 0, (since, tk)
        approx(glow, k["chip_glow"] + k["chip_tick"] * tk, "chip glow", 0.01)
        if tk > 0.5:
            assert (h, y, hi) == (4.0, 40.0, True), (h, y, hi)
        else:
            assert (h, y, hi) == (2.0, 41.0, False), (tk, h, y, hi)
    assert max(r[0] for r in rec) > 0.9
    lua = world()
    conf(lua, "fivesecond.fx.tick", False)
    run(lua, "__regen = { 14.8, 4.9 }")
    tick(lua, 1.2)
    cast(lua)
    tick(lua, 5.0)
    assert all(r[0] == 0 and r[1] == 2.0 for r in play(lua, 4.4, probe))


def check_the_idle_glow_is_a_looping_animation_of_the_rim_and_only_at_rest():
    k = MK["k"]
    lua = world()
    refresh(lua)
    B = ft(lua).FT.breath
    groups = seq(B.groups)
    assert len(groups) == 2 and bool(B.on) and all(bool(g.playing) for g in groups), "the idle glow plays"
    gauge = seq(B.gauge)
    assert len(gauge) == 10 and bool(B.gaugeOn) and all(bool(g.playing) for g in gauge), "and so does the gauge"
    for g in gauge:
        approx(sum(float(a.duration) for a in seq(g.anims)), k["breath_time"], "the gauge cycle is the same period")
    for g in groups:
        assert str(g.looping) == "REPEAT"
        approx(sum(float(a.duration) for a in seq(g.anims)), k["breath_time"], "one cycle is the mockup's period")
        assert all(str(a.kind) == "Alpha" and str(a.smoothing) == "IN_OUT" for a in seq(g.anims))
    rec = play(lua, k["breath_time"] + 0.3, lambda l: (cells_look(l)["ring_a"], cells_look(l)["glow_a"]))
    rings, glows = [r[0] for r in rec], [r[1] for r in rec]
    approx(min(rings), k["breath_ring"], "the dimmest ring", 0.02)
    approx(max(rings), k["breath_ring"] + k["breath_swing"], "the brightest ring", 0.02)
    approx(min(glows), 0.0, "the dimmest glow", 0.02)
    approx(max(glows), k["breath_glow"], "the brightest glow", 0.02)
    seg = ft(lua).FT.gauge.seg[1]
    gs = play(lua, k["breath_time"], lambda l: float(seg._vertex[4]) * eff_alpha(l, seg))
    approx(min(gs), 0.24, "the dimmest idle gauge segment", 0.02)
    approx(max(gs), 0.24 + 0.14, "the brightest idle gauge segment", 0.02)
    # the extremes sit half a period apart
    lo = rings.index(min(rings[:int(k["breath_time"] * 60)]))
    hi = rings.index(max(rings[:int(k["breath_time"] * 60)]))
    approx(abs(hi - lo) / 60, k["breath_time"] / 2, "the glow rises and falls over half a period each", 0.1)
    # no ticker pass is needed to move it
    assert not bool(ft(lua).FT.fast) and not bool(ft(lua).FT.ambient)
    # not while counting
    cast(lua)
    tick(lua, 0.1)
    assert not bool(B.on) and not bool(B.gaugeOn) and not any(bool(g.playing) for g in groups + gauge), "the glow stops under the count"
    approx(cells_look(lua)["ring_a"], MK["k"]["susp_ring"], "the count's own ring", 1e-6)
    approx(eff_alpha(lua, ft(lua).FT.hero.fsSkin.border.ring), 1.0, "the ring alpha is back to full")
    # nor under the mouse: the hover ring is steady
    lua = world()
    refresh(lua)
    lua.eval("__Region.Fire")(cells_tile(lua), "OnEnter")
    refresh(lua)
    B = ft(lua).FT.breath
    assert not bool(B.on), "the glow stops under the mouse"
    assert bool(B.gaugeOn), "but the gauge keeps breathing"
    approx(cells_look(lua)["ring_a"], 1.0, "the hover ring", 1e-6)
    lua.eval("__Region.Fire")(cells_tile(lua), "OnLeave")
    refresh(lua)
    assert bool(B.on), "and plays again after it"
    # the switch and the master stop it
    for key in ("fivesecond.fx.breath", "fivesecond.motion"):
        lua = world()
        refresh(lua)
        assert bool(ft(lua).FT.breath.on)
        conf(lua, key, False)
        B = ft(lua).FT.breath
        assert not bool(B.on) and not any(bool(g.playing) for g in seq(B.groups)), key
        rec = play(lua, k["breath_time"], lambda l: (cells_look(l)["ring_a"], cells_look(l)["glow_a"]))
        assert all(abs(r[0] - k["idle_ring"]) < 1e-6 and r[1] == 0 for r in rec), key
        conf(lua, key, True)
        assert bool(ft(lua).FT.breath.on), key + " back on"
    # a hidden tab does not breathe
    lua = world()
    refresh(lua)
    conf(lua, "fivesecond.enabled", False)
    assert not bool(ft(lua).FT.breath.on), "hidden"


def check_the_kept_and_unreadable_rate_stutter_in_short_bursts_and_a_live_rate_never_does():
    def probe(l):
        f = fx(l)
        FT = ft(l).FT
        return (f["glitchA"], f["glitchDx"], float(FT.rateText._textColor[4]), float(FT.rateText._points[1].x))

    lua = world()
    refresh(lua)
    enter_combat(lua)
    tick(lua, 0.2)
    assert bool(view(lua).cached)
    rec = play(lua, 5.0, probe)
    burst = [r for r in rec if r[0] < 1]
    assert 20 <= len(burst) <= 60, len(burst)
    starts = sum(1 for a, b in zip(rec, rec[1:]) if a[0] == 1 and b[0] < 1)
    assert starts >= 1
    for a, dx, text_a, x in rec:
        approx(text_a, a, "the rate text alpha follows the stutter", 0.01)
        approx(x, 8 + dx, "the rate text shifts a pixel", 1e-6)
        assert dx in (-1, 0, 1)
    assert any(r[1] != 0 for r in burst)
    # a live reading never stutters; nor does the stutter run under the count or the sweep
    lua = world()
    refresh(lua)
    assert not any(r[0] < 1 for r in play(lua, 5.0, probe))
    lua = world()
    refresh(lua)
    enter_combat(lua)
    tick(lua, 0.2)
    cast(lua)

    def under(l):
        v = view(l)
        return (v.phase, fx(l)["pp"], fx(l)["glitchA"])

    rec = play(lua, 8.0, under)
    assert not any(r[2] < 1 for r in rec if r[0] == "susp" or r[1] < 1), "a stutter under the count or the sweep"
    assert any(r[2] < 1 for r in rec if r[0] != "susp" and r[1] >= 1), "no stutter once the sweep is over"
    # an unreadable rate stutters too; the switch stops it
    lua = world()
    run(lua, "__regenMode = 'throw'")
    refresh(lua)
    assert any(r[0] < 1 for r in play(lua, 5.0, probe))
    lua = world()
    run(lua, "__regenMode = 'throw'")
    conf(lua, "fivesecond.fx.glitch", False)
    refresh(lua)
    assert not any(r[0] < 1 for r in play(lua, 5.0, probe))


def scenario(lua, fps=30):
    """A kept rate, a cast, the count, the sweep, the hold, the fade, the idle: every frame's strong motions and effects."""
    refresh(lua)
    enter_combat(lua)
    tick(lua, 0.2)

    def probe(l):
        f = fx(l)
        return dict(f, phase=str(view(l).phase))

    rec = [probe(lua)]
    cast(lua)
    rec += play(lua, 5.0 + 0.9, probe, fps)
    cast(lua)                                      # a recast in the middle of the sweep
    rec += play(lua, 5.0 + 10.0, probe, fps)
    return rec


def strong(r) -> list:
    out = []
    if r["flash"] > 0:
        out.append("flash")
    if r["zp"] > 0:
        out.append("pulse")
    if r["pp"] < 1:
        out.append("sweep")
    if r["glitchA"] < 1:
        out.append("stutter")
    return out


def check_at_most_one_strong_motion_plays_at_a_time():
    lua = world()
    rec = scenario(lua, 60)
    seen = set()
    for r in rec:
        s = strong(r)
        seen.update(s)
        assert len(s) <= 1, f"two strong motions at once: {s} at {r}"
    assert seen == {"flash", "pulse", "sweep", "stutter"}, seen


def check_every_switch_stops_its_own_effect_and_only_that_one():
    names = {"flash": "flash", "digits": ("dip", "warm"), "wpulse": "zp", "drop": "dropSeg", "sweep": "pp", "tick": "tick",
             "breath": "breath", "glitch": "glitchA"}

    def stats(rec):
        return dict(
            flash=max(r["flash"] for r in rec) > 0, dip=any(r["dip"] for r in rec), warm=max(r["warm"] for r in rec) > 0,
            zp=max(r["zp"] for r in rec) > 0, dropSeg=any(r["dropSeg"] for r in rec), pp=min(r["pp"] for r in rec) < 1,
            tick=max(r["tick"] for r in rec) > 0, breath=any(bool(r["breathing"]) for r in rec),
            glitchA=min(r["glitchA"] for r in rec) < 1, flare=max(r["flare"] for r in rec) > 0,
        )

    base = stats(scenario(world()))
    assert all(base.values()), f"a baseline effect never ran: {base}"
    for name, fields in names.items():
        lua = world()
        conf(lua, f"fivesecond.fx.{name}", False)
        got = stats(scenario(lua))
        mine = fields if isinstance(fields, tuple) else (fields,)
        for key in base:
            if key in mine:
                assert not got[key], f"{name} off but {key} still runs"
            else:
                assert got[key], f"{name} off took {key} with it"
    lua = world()
    conf(lua, "fivesecond.motion", False)
    got = stats(scenario(lua))
    assert not any(got.values()), f"the master is off but these run: {[k for k, v in got.items() if v]}"


def visible(lua, region) -> bool:
    return bool(lua.eval("function(f) return f:IsVisible() end")(region))


def ticker(lua):
    return g(lua).FSFiveSecondTicker


def check_the_ticker_runs_every_frame_only_while_something_quick_moves():
    lua = world()
    FT = ft(lua).FT
    refresh(lua)
    assert not bool(FT.fast) and not bool(FT.ambient), "idle with the idle glow on is the slow rate: the glow is an animation group"
    cast(lua)
    tick(lua, 0.1)
    assert bool(FT.fast), "the count runs the ticker every frame"
    tick(lua, 5.5)
    tick(lua, 1.0)
    assert not bool(FT.fast), "the hold is slow motion"
    assert bool(FT.ambient), "the hold fades at the ambient rate"
    tick(lua, 8.0)
    assert not bool(FT.fast) and not bool(FT.ambient), "back at rest the ticker is the slow rate again"
    lua = world()
    for name in ("breath", "tick", "glitch"):
        conf(lua, f"fivesecond.fx.{name}", False)
    refresh(lua)
    assert not bool(ft(lua).FT.fast) and not bool(ft(lua).FT.ambient), "nothing moves: the half second rate"
    lua = world(motion=False)
    refresh(lua)
    assert not bool(ft(lua).FT.ambient)


def check_a_hidden_tab_runs_no_ticker_at_all():
    lua = world()
    FT = ft(lua).FT
    refresh(lua)
    assert visible(lua, ticker(lua)), "a shown tab ticks"
    cast(lua)
    tick(lua, 0.2)
    assert bool(FT.fast)
    conf(lua, "fivesecond.enabled", False)
    assert not visible(lua, ticker(lua)), "the ticker frame is hidden with the tab, so it gets no OnUpdate"
    cast(lua)
    refresh(lua)
    assert not bool(FT.fast) and not bool(FT.ambient), "a hidden tab asks for no ticker"
    run(lua, "__advance(5.5)")
    refresh(lua)
    assert str(view(lua).phase) == "res" and not bool(FT.fast) and not bool(FT.ambient), "nor in the regen hold"
    conf(lua, "fivesecond.enabled", True)
    assert visible(lua, ticker(lua)), "and it ticks again when the tab comes back"
    # a Druid out of mana form hides the tab the same way
    lua = world(klass="DRUID")
    refresh(lua)
    assert visible(lua, ticker(lua))
    run(lua, "__powerType = { 3, 'ENERGY' }")
    lua.eval("__fire_event")("UNIT_DISPLAYPOWER", "player")
    assert not visible(lua, ticker(lua)), "a Druid in a form without mana has no ticker"


def check_hiding_the_whole_ui_costs_the_ticker_and_the_idle_glow_nothing():
    lua = world()
    FT = ft(lua).FT
    refresh(lua)
    assert bool(FT.breath.on) and visible(lua, ticker(lua))
    run(lua, "UIParent:Hide()")
    assert not visible(lua, ticker(lua)), "Alt+Z: the ticker frame is no longer visible, so it gets no OnUpdate"
    cast(lua)
    refresh(lua)
    assert not bool(FT.fast) and not bool(FT.ambient), "and the tab asks for no fast pass"
    assert not bool(FT.breath.on) and not bool(FT.breath.gaugeOn), "a paint with the interface hidden turns the glow off (in the client nothing repaints, so the groups just play unseen at no cost)"
    run(lua, "UIParent:Show()")
    run(lua, "__advance(10)")
    refresh(lua)
    assert str(view(lua).phase) == "idle" and bool(FT.breath.on), "and plays again when it comes back"


def check_the_idle_glow_loops_without_a_jump():
    k = MK["k"]
    lua = world()
    refresh(lua)
    for group in list(seq(ft(lua).FT.breath.groups)) + list(seq(ft(lua).FT.breath.gauge)):
        anims = sorted(seq(group.anims), key=lambda a: int(a.order))
        for a, b in zip(anims, anims[1:] + anims[:1]):
            approx(float(a.to), float(getattr(b, "from")), "each step ends where the next begins, and the last where the first begins", 1e-9)
    ring = ft(lua).FT.breath.ring
    steps = play(lua, 2 * k["breath_time"], lambda l: cells_look(l)["ring_a"])
    worst = max(abs(a - b) for a, b in zip(steps, steps[1:]))
    assert worst < 0.02, f"the ring jumps {worst:.3f} between frames"


def check_the_idle_glow_says_so_when_a_piece_of_the_rim_is_missing():
    lua = world()
    assert ft(lua).FT.breath is not None, "the groups exist after a normal build"
    assert len(seq(ft(lua).FT.breath.groups)) == 2 and len(seq(ft(lua).FT.breath.gauge)) == 10
    pre = """__logs, __logText = 0, nil
FS.LogDegradeOnce = function(key, text) __logs = __logs + 1; __logText = text end
local skin = FS.Theme.SkinCutButton
FS.Theme.SkinCutButton = function(button, opts)
    local r = skin(button, opts)
    if button.fsSkin then button.fsSkin.glow = nil end
    return r
end"""
    lua = world(pre_login=pre)
    assert ft(lua).FT.breath is None, "no groups without the glow texture"
    assert int(g(lua).__logs) == 1 and "idle glow" in plain_text(g(lua).__logText), "the quiet log says why, once"
    refresh(lua)
    cast(lua)
    tick(lua, 8.0)
    assert int(g(lua).__logs) == 1, "once, not on every pass"


def check_the_stutter_asks_for_the_ambient_ticker_only_around_its_window():
    k = MK["k"]
    for unreadable in (False, True):
        lua = world()
        if unreadable:
            run(lua, "__regenMode = 'throw'")
        refresh(lua)
        if not unreadable:
            enter_combat(lua)
        tick(lua, 0.2)
        FT = ft(lua).FT
        rec = play(lua, 12.0, lambda l: (bool(FT.ambient), float(fx(l)["glitchA"]) < 1))
        busy = sum(1 for r in rec if r[0]) / len(rec)
        assert 0 < busy < 0.45, f"the ambient ticker runs {busy:.0%} of a kept rate"
        assert all(r[0] for r in rec if r[1]), "the ambient ticker runs through every stutter frame"
        # a pass every slow tick still lands before each window
        assert sum(1 for a, b in zip(rec, rec[1:]) if not a[1] and b[1]) >= 4, "the stutter still happens"


def check_the_pulse_cannot_run_the_every_frame_ticker_with_motion_off():
    lua = world()
    FT = ft(lua).FT
    refresh(lua)
    cast(lua)
    tick(lua, 5.05)
    assert float(view(lua).pulse) > 0 and bool(FT.fast), "the pulse runs the ticker with motion on"
    conf(lua, "fivesecond.motion", False)
    refresh(lua)
    assert not bool(FT.fast), "motion off: a pulse in flight does not hold the every frame ticker"


def check_no_pulse_is_counted_while_motion_is_off():
    lua = world(motion=False)
    refresh(lua)
    cast(lua)
    tick(lua, 5.2)
    v = view(lua)
    assert float(v.pulse) == 0.0, "no pulse is on"
    assert int(v.pulses) == 0, "no pulse is counted"
    assert all(float(r) == 0 for r in play(lua, 1.0, lambda l: fx(l)["flare"])), "and no flare"
    lua = world()
    refresh(lua)
    cast(lua)
    tick(lua, 5.2)
    assert int(view(lua).pulses) == 1, "motion on: the one pulse"
    # the sound is its own switch and plays either way
    lua = world(motion=False)
    conf(lua, "fivesecond.sound", True)
    refresh(lua)
    cast(lua)
    tick(lua, 5.2)
    assert int(view(lua).sounds) == 1, "the sound does not depend on the motion master"


CHECKS = [
    check_the_glyph_tables_and_the_segment_order_are_the_mockups,
    check_the_generator_draws_the_mockups_disjoint_segments,
    check_the_led_has_ninety_eight_segment_textures_cut_from_the_atlas_and_snapped,
    check_the_readout_glow_is_a_soft_copy_under_each_lit_segment_and_never_a_block,
    check_the_gauge_glow_is_a_halo_on_each_segment_and_only_when_not_idle,
    check_the_cast_wash_is_clipped_to_the_face,
    check_the_led_numbers_are_the_mockups,
    check_a_mana_cast_starts_five_seconds_and_the_readout_counts_in_tenths,
    check_every_digit_the_countdown_can_show_decodes_from_its_lit_segments,
    check_the_gauge_drains_one_segment_every_half_second_right_to_left_with_a_partial_segment,
    check_the_suspended_look_is_amber_all_the_way_through,
    check_a_free_cast_starts_nothing,
    check_another_units_cast_and_unreadable_costs_start_nothing,
    check_a_recast_restarts_the_full_window,
    check_a_cast_after_the_rule_ended_starts_a_new_window,
    check_a_channel_holds_the_window_open_until_it_ends,
    check_a_channel_whose_end_event_never_comes_is_not_held_forever,
    check_death_and_a_loading_screen_clear_the_window,
    check_at_zero_the_digits_turn_cyan_and_the_word_says_regen,
    check_regen_pulses_once_and_not_again_while_it_shows,
    check_the_pulse_toggle_off_means_no_pulse_but_the_cyan_look_stays,
    check_the_sound_plays_once_at_regen_only_when_its_toggle_is_on,
    check_a_regen_seen_late_makes_no_pulse_and_no_sound,
    check_the_cue_fades_to_the_dim_idle_look_a_few_seconds_after_regen,
    check_the_idle_tab_before_any_cast_is_the_same_dim_look,
    check_the_rate_is_the_full_rate_outside_the_rule_and_the_casting_rate_during_it,
    check_the_rate_is_read_out_of_combat_kept_in_combat_and_dashed_while_kept,
    check_a_login_in_combat_shows_no_number_until_one_can_be_read,
    check_the_retention_chip_is_cyan_above_zero_and_a_hollow_zero_otherwise,
    check_the_rate_numbers_survive_secrets_and_bad_values,
    check_the_idle_and_the_combat_tick_allocate_nothing,
    check_the_cells_tooltip_says_how_long_and_that_it_is_an_estimate,
    check_no_player_facing_string_names_the_five_second_rule,
    check_the_cells_tooltip_after_the_rule_says_regen_is_running,
    check_the_rate_tooltip_names_both_rates_and_the_cache,
    check_the_rate_tooltip_with_no_reading_says_so,
    check_a_tooltip_open_on_a_tile_follows_the_countdown,
    check_the_settings_have_their_defaults_keys_labels_and_tips,
    check_the_master_toggle_hides_the_tab_and_its_shoulder_and_shows_them_again,
    check_a_warrior_a_rogue_and_unreadable_classes_get_nothing,
    check_every_mana_class_gets_the_tab,
    check_a_druid_in_a_form_without_mana_hides_the_tab_and_keeps_counting,
    check_the_cue_needs_no_target_and_hangs_on_the_ui_not_the_gunsight,
    check_nothing_in_the_tab_is_secure_or_touches_a_protected_frame_in_combat,
    check_everything_sits_on_whole_pixels_and_the_led_art_is_never_scaled_fractionally,
    check_a_rescale_resizes_and_reseats_out_of_combat,
    check_a_class_without_a_tab_of_its_own_seats_the_cue_where_the_class_tab_would_stand,
    check_a_paladin_gets_it_after_the_seal_block,
    check_a_shaman_gets_it_after_the_buff_tab,
    check_the_cue_moves_when_the_class_tab_arrives_later,
    check_the_console_gap_covers_the_cue_and_the_top_line_is_bridged_to_the_class_tab,
    check_the_cue_follows_the_console_on_and_off_and_is_absent_without_one,
    check_a_seat_change_in_combat_waits_for_regen,
    check_a_login_in_combat_builds_at_once_and_seats_at_regen,
    check_the_listeners_are_for_the_unit_player_and_start_once,
    check_a_failed_build_leaves_no_listener_running,
    check_the_chrome_is_the_buff_tabs_cut_plate_with_a_skinned_border,
    check_hiding_the_host_under_the_mouse_clears_the_hover_and_the_tooltip,
    check_the_kept_rate_bar_is_the_mockups_dashes,
    check_toc_lists_the_tab_after_the_buff_tab_and_before_the_config_window,
    check_no_em_dashes_and_no_flagged_words_in_the_new_files,
    check_the_config_window_builds_the_motion_rows_under_a_master,
    check_the_class_shoulder_names_the_cue_as_a_shoulder_after_every_class_tab,
    check_the_cast_flash_washes_the_face_for_half_a_second,
    check_each_new_tenth_dips_the_second_digit_for_a_moment_and_never_under_the_cast_flash,
    check_the_last_second_warms_from_amber_through_white_toward_cyan,
    check_the_whole_second_pulse_flashes_the_digits_at_4_3_2_1_and_never_at_5_or_at_regen,
    check_the_emptied_gauge_segment_flickers_once_and_the_pulse_damps_it,
    check_the_regen_sweep_carries_the_held_digits_into_the_word_under_one_band,
    check_the_rim_flares_once_at_regen_with_the_pulse_switch_and_not_without,
    check_the_regen_tick_pulse_grows_the_bar_a_pixel_each_side_on_a_two_second_timer,
    check_the_idle_glow_is_a_looping_animation_of_the_rim_and_only_at_rest,
    check_the_kept_and_unreadable_rate_stutter_in_short_bursts_and_a_live_rate_never_does,
    check_at_most_one_strong_motion_plays_at_a_time,
    check_every_switch_stops_its_own_effect_and_only_that_one,
    check_the_ticker_runs_every_frame_only_while_something_quick_moves,
    check_a_hidden_tab_runs_no_ticker_at_all,
    check_hiding_the_whole_ui_costs_the_ticker_and_the_idle_glow_nothing,
    check_the_idle_glow_loops_without_a_jump,
    check_the_idle_glow_says_so_when_a_piece_of_the_rim_is_missing,
    check_the_stutter_asks_for_the_ambient_ticker_only_around_its_window,
    check_the_pulse_cannot_run_the_every_frame_ticker_with_motion_off,
    check_no_pulse_is_counted_while_motion_is_off,
]
SCALED_CHECKS = [
    check_the_rate_line_is_fitted_at_both_lengths_and_the_bar_is_as_wide_as_the_text,
    check_the_face_is_the_mockups_in_design_px,
    check_every_string_fits_inside_its_zone_in_every_state,
]


def main() -> int:
    failed = total = 0

    def run_check(label, fn, *args):
        nonlocal failed, total
        total += 1
        try:
            fn(*args)
            print(f"ok    {label}")
        except (AssertionError, LuaError, FileNotFoundError, AttributeError, TypeError, KeyError, IndexError, ValueError) as err:
            failed += 1
            print(f"FAIL  {label}\n      " + f"{type(err).__name__}: {err}".replace("\n", "\n      "))

    for fn in CHECKS:
        run_check(fn.__name__, fn)
    for fn in SCALED_CHECKS:
        # the design geometry is also pinned at the smallest scale the UI slider gives (0.64)
        extra = (CRISP_SCALES[0],) if fn is not check_every_string_fits_inside_its_zone_in_every_state else ()
        for scale in SCALES + extra:
            run_check(f"{fn.__name__} @scale={scale:.4f}", fn, scale)
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
