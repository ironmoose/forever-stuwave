#!/usr/bin/env python3
"""Runs the real PetFrame.lua headless against a strict mock WoW API.

PetFrame.lua is the pet component's one panel, matching the approved console dock
option C of mockups/gunsight-hud-v2-2026-10-02 (PE_G.dc, drawPet's dc branch, peStatusDc):
a 348 x 68 panel, a 26 high top row with the HP/mana block on the left and the cast
slot on the right, and the 10 pet buttons underneath. The panel insets are 5 on top
and 6 (PE_PAD) on the sides, the buttons sit 3 below the top row, and 4 is left under
them. The parse gate proves it compiles; these checks pin the GEOMETRY against the
numbers parsed back out of the mockup itself (so a mockup edit that this file
does not follow fails here), at scale 1 and at 0.64:

  * the HP/mana slot starts at the interior left edge and is the mockup's left block wide;
  * the cast slot sits right of it by the mockup gap and ends at the interior right
    edge, on the same top;
  * the button slot is below both by the mockup row gap and spans the interior, closing
    the panel height with the bottom pad;
  * the container is the mockup panel size times the scale (real Layout.lua);
  * the HP and mana laser rails (7 high, 2 apart), the name row and every text size match;
  * the level is plain muted "LV n" text, no chip;
  * Layout.lua's petcontainer is 348 x 68 and its bottom edge stays at -444 (the FLOAT seat; the
    docked anchor onto the Console is petdock-harness.py's);
  * a rescale in combat touches no geometry, and PLAYER_REGEN_ENABLED applies it;
  * secret health / mana / name / level reach only the bar setters, SetFormattedText and
    SetText; the first rejected SetFormattedText latches the value text off;
  * in combat the visibility events make no Show/Hide call on the protected container.

The mock is strict (a widget method it does not define fails as a nil call) and is
NOT the real client. Layout.lua and FrameHelpers.lua are the real files; Theme is a
small stub (theme-harness.py is the harness that loads the real Theme).

    python3 tools/petframe-harness.py

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
ADDON = HERE.parent
# PETFRAME_LUA points the harness at a mutant copy of PetFrame.lua (a check must fail on a broken one).
PETFRAME = Path(os.environ.get("PETFRAME_LUA", ADDON / "PetFrame.lua"))
# The panel and status block come from the approved Gunsight mockup (option C, the console dock).
MOCKUP = ADDON / "mockups" / "gunsight-hud-v2-2026-10-02" / "gunsight-hud-v2-2026-10-02.html"

SCALES = (1.0, 0.64)  # UIParent height / 1440
# PetFrame.lua NAME_LEVEL_GAP: the name stops this many design px short of the LV text. Not in the
# mockup (it prints the name and the LV text at fixed x), so it is pinned here rather than parsed.
NAME_LEVEL_GAP = 4


def _grab(src: str, pattern: str, *names: str, flags: int = 0) -> dict:
    match = re.search(pattern, src, flags)
    assert match, f"mockup no longer matches {pattern!r}; update this harness with it"
    return {n: float(v) for n, v in zip(names, match.groups(), strict=True)}


def mockup_constants() -> dict:
    """Parse the option C (console dock) numbers back out of the mockup's script (a drift fails
    the checks): PE_G.dc, PE_* and drawPet's dc branch for the panel, peStatusDc for the status
    block. The cast area is NOT parsed here: petcastbar-harness.py has its own parser for
    peCastDc."""
    src = MOCKUP.read_text(encoding="utf-8")
    c: dict = {}
    # Panel: PE_G.dc = W 348, H 68, top row 26.
    c.update(_grab(src, r"dc:\{W:(\d+),H:(\d+),TOPH:(\d+)\}", "PW", "PH", "TOPH"))
    c.update(_grab(src, r"var PE_X=\d+,PE_BOT=\d+,PE_PAD=(\d+),PE_LW=(\d+),PE_GX=(\d+),PE_BTN=(\d+),"
                        r"PE_BG=(\d+),", "PAD", "LW", "GAPX", "BTN", "BGAP"))
    # drawPet's dc branch: the top inset (ty) and the row gap above the buttons.
    c.update(_grab(src, r"AB_Y0\)/AU-H;\s*ty=(\d+);tx=PE_PAD;", "TOPY"))
    c.update(_grab(src, r"peButtons\(PE_PAD,ty\+top\+\(pes==='dc'\?(\d+):\d+\)", "ROWGAP"))
    keys = re.search(r"var PE_KEYS=\[([^\]]*)\];", src)
    assert keys, "PE_KEYS not found"
    c["NUM"] = float(len(keys.group(1).split(",")))
    # peStatusDc: name size, the plain LV text size, then the rails (top, core height, gap, value size).
    c.update(_grab(src, r"function peStatusDc\(x,y,st(?:,nm)?\)\{.*?peT\((?:nm\?nm\.n:)?'Zilyal',x\+1,y\+[\d.]+,([\d.]+),"
                        r".*?peT\((?:nm\?nm\.lv:)?'LV 68',x\+PE_LW,y\+[\d.]+,([\d.]+),K\.muted,1,'right'\);"
                        r"\s*peRails\(x,y\+(\d+),PE_LW,(\d+),(\d+),st,([\d.]+),",
                   "NAMEFS", "LEVELFS", "HPY", "BARH", "RAILGAP", "BARFS", flags=re.S))
    c["MPY"] = c["HPY"] + c["BARH"] + c["RAILGAP"]
    c["BOTPAD"] = c["PH"] - (c["TOPY"] + c["TOPH"] + c["ROWGAP"] + c["BTN"])

    return c


# A strict mock in the shape partyframes-harness.py uses (anchor-resolving rects), plus
# what PetFrame.lua adds: fonts, unit reads on "pet", combat state and slash commands.
MOCK = r"""
__frames, __messages, __blocked = {}, {}, {}
__combat = false
-- On the client type() of a secret number answers "number" (it never throws), so a check like
-- `type(v) == "number"` does NOT prove a value is plain. The mock says the same: only IsSecret does.
__rawtype = type
function type(v)
    if __rawtype(v) == 'table' and v.secret == true then return 'number' end
    return __rawtype(v)
end
local Region = {}
Region.__index = Region
local function newRegion(parent)
    return setmetatable({parent=parent, points={}, scripts={}, shown=true, alpha=1,
        regions={}, registered={}, unitEvents={}}, Region)
end
function Region:SetScale(v) self.scale=v end
function Region:GetScale() return self.scale or 1 end
function Region:GetEffectiveScale()
    return self:GetScale()*(self.parent and self.parent:GetEffectiveScale() or 1)
end
function Region:SetSize(w,h) self.w,self.h=w,h end
function Region:SetWidth(w) self.w=w end
function Region:SetHeight(h) self.h=h end
function Region:SetPoint(p,rel,rp,x,y)
    if type(rel) == 'number' then x,y,rel,rp=rel,rp,self.parent,p end
    rel,rp=rel or self.parent,rp or p
    self.points[p]={rel=rel,rp=rp,x=x or 0,y=y or 0}
end
function Region:ClearAllPoints() self.points={} end
function Region:SetAllPoints(rel)
    self:ClearAllPoints()
    self:SetPoint('TOPLEFT',rel or self.parent,'TOPLEFT')
    self:SetPoint('BOTTOMRIGHT',rel or self.parent,'BOTTOMRIGHT')
end
local factors={TOPLEFT={0,0},TOP={.5,0},TOPRIGHT={1,0},LEFT={0,.5},
    CENTER={.5,.5},RIGHT={1,.5},BOTTOMLEFT={0,1},BOTTOM={.5,1},BOTTOMRIGHT={1,1}}
function Region:Axis(axis)
    local size
    if axis==1 then size=self.w else size=self.h end
    if size then size=size*self:GetEffectiveScale() end
    local first,second
    for p,a in pairs(self.points) do
        local origin,extent=a.rel:Axis(axis)
        local f=factors[p][axis]
        local offset=(axis==1 and a.x or -a.y)*self:GetEffectiveScale()
        local value=origin+factors[a.rp][axis]*extent+offset
        if not first then first={f,value}
        elseif first[1]~=f then second={f,value} end
    end
    if not first then return 0,size or 0 end
    if not size and second then size=(second[2]-first[2])/(second[1]-first[1]) end
    size=size or 0
    return first[2]-first[1]*size,size
end
function Region:GetWidth() local _,w=self:Axis(1) return w/self:GetEffectiveScale() end
function Region:GetHeight() local _,h=self:Axis(2) return h/self:GetEffectiveScale() end
function Region:GetBounds()
    local x,w=self:Axis(1) local y,h=self:Axis(2)
    return {x=x,y=y,w=w,h=h,right=x+w,bottom=y+h}
end
function Region:Show() self.shown=true self.showCalls=(self.showCalls or 0)+1 end
function Region:Hide() self.shown=false self.hideCalls=(self.hideCalls or 0)+1 end
function Region:SetShown(v)
    self.shown=v
    if v then self.showCalls=(self.showCalls or 0)+1 else self.hideCalls=(self.hideCalls or 0)+1 end
end
function Region:IsShown() return self.shown end
function Region:SetAlpha(a) self.alpha=a end
function Region:GetAlpha() return self.alpha end
-- The client throws "Font not set" for text written to a FontString before it has a font.
local function needFont(self)
    if self.isFontString and not self.fontPath then error('Font not set', 3) end
end
function Region:SetText(t) needFont(self) self.text=t end
__fail_formatted=false
function Region:SetFormattedText(fmt,...)
    needFont(self)
    self.fmtCalls=(self.fmtCalls or 0)+1
    if __fail_formatted then error('SetFormattedText rejected the value') end
    local args={...}
    for i,v in ipairs(args) do
        if __rawtype(v)=='table' and v.nativeNumber then args[i]=v.nativeNumber end
    end
    self.text=string.format(fmt,unpack(args))
end
function Region:SetFont(path,size,flags) self.fontPath,self.fontSize,self.fontFlags=path,size,flags end
function Region:GetFont() return self.fontPath,self.fontSize,self.fontFlags end
function Region:SetTextColor(...) self.textColor={...} end
function Region:SetShadowColor(...) self.shadowColor={...} end
function Region:SetShadowOffset(...) self.shadowOffset={...} end
function Region:SetColorTexture(...) self.color={...} end
function Region:SetVertexColor(...) self.color={...} end
function Region:SetTexture(t) self.texture=t return true end
function Region:GetTexture() return self.texture end
function Region:SetDesaturated(v) self.desaturated=v end
function Region:SetStatusBarColor(...) self.color={...} end
function Region:SetMinMaxValues(lo,hi) self.min,self.max=lo,hi end
function Region:SetValue(v) self.value=v end
function Region:SetStatusBarTexture(t) self.fill=newRegion(self) self.fill.texture=t end
function Region:GetStatusBarTexture() return self.fill end
function Region:CreateTexture()
    local r=newRegion(self) self.regions[#self.regions+1]=r return r
end
function Region:CreateFontString()
    local r=newRegion(self) r.isFontString=true self.regions[#self.regions+1]=r return r
end
function Region:SetTexCoord(...) self.texcoords={...} end
function Region:SetBlendMode(m) self.blendMode=m end
function Region:SetGradient(orientation,minColor,maxColor)
    assert(orientation=='HORIZONTAL' or orientation=='VERTICAL','bad gradient orientation')
    for _,c in ipairs({minColor,maxColor}) do
        assert(type(c)=='table','gradient color must be a table')
        for _,k in ipairs({'r','g','b','a'}) do
            assert(type(c[k])=='number','gradient color needs numeric '..k)
        end
    end
    self.gradient={orientation=orientation,min=minColor,max=maxColor}
end
function Region:RegisterEvent(event) self.registered[event]=true end
function Region:RegisterUnitEvent(event,unit) self.registered[event]=true self.unitEvents[event]=unit end
function Region:SetScript(k,fn) self.scripts[k]=fn end
-- Like the client, a frame created without a level sits one above its parent (read lazily here, so a
-- later SetFrameLevel on the parent carries its unset children along, as the engine does).
function Region:GetFrameLevel()
    return self.frameLevel or (self.parent and self.parent:GetFrameLevel() + 1) or 0
end
function Region:SetFrameLevel(v) self.frameLevel=v end
-- The client blocks EnableMouse on the container in combat (implicitly protected: it parents the
-- secure pet buttons): refuse it like the engine and record it, so a stray call fails a check.
function Region:EnableMouse(v)
    if __combat and self.name=='FSPetContainer' then
        __blocked[#__blocked+1]='EnableMouse:'..self.name
        return
    end
    self.mouse=v
end
function Region:SetMovable(v) self.movable=v end
function Region:RegisterForDrag() end
function Region:StartMoving() end
function Region:StopMovingOrSizing() end
function Region:CreateAnimationGroup()
    local g={animations={},playing=false,playCalls=0}
    self.groups=self.groups or {}
    self.groups[#self.groups+1]=g
    function g:SetLooping(m) self.looping=m end
    function g:Play() self.playing=true self.playCalls=self.playCalls+1 end
    function g:Stop() self.playing=false self.stopCalls=(self.stopCalls or 0)+1 end
    function g:IsPlaying() return self.playing end
    function g:CreateAnimation(kind)
        local a={kind=kind}
        function a:SetFromAlpha(v) self.from=v end
        function a:SetToAlpha(v) self.to=v end
        function a:SetDuration(v) self.duration=v end
        function a:SetSmoothing(v) self.smoothing=v end
        g.animations[#g.animations+1]=a
        return a
    end
    return g
end
function Region:GetPoint()
    local p,a=next(self.points)
    if p then return p,a.rel,a.rp,a.x,a.y end
end
for _,m in ipairs({'SetJustifyH','SetJustifyV','SetWordWrap','SetNonSpaceWrap','SetMaxLines',
    'SetClipsChildren','UnregisterAllEvents','UnregisterEvent','HookScript'}) do
    Region[m]=function() end
end
function CreateFrame(kind,name,parent)
    local f=newRegion(parent) f.kind,f.name=kind,name
    __frames[#__frames+1]=f
    if name then _G[name]=f end
    return f
end
UIParent=CreateFrame('Frame','UIParent') UIParent:SetSize(2560,1440)
SlashCmdList={}
function print(msg) __messages[#__messages+1]=msg end
function InCombatLockdown() return __combat end

-- The pet unit.
__pet={exists=true,dead=false,health=253,healthMax=253,pct=1,power=320,powerMax=320,level=11}
function UnitExists() return __pet.exists end
function UnitIsDead() return __pet.dead end
function UnitIsFeignDeath() return false end
function UnitName() return __pet.name or 'Zilyal' end
function UnitLevel() return __pet.level end
function UnitHealth() return __pet.health end
function UnitHealthMax() return __pet.healthMax end
function UnitPower() return __pet.power end
function UnitPowerMax() return __pet.powerMax end
function UnitPowerType() return 0,'MANA' end
Enum={LuaCurveType={Linear=0,Step=1}}
C_CurveUtil={CreateCurve=function()
    return {points={},SetType=function(self,t) self.kind=t end,
        AddPoint=function(self,x,y) self.points[#self.points+1]={x,y} end}
end}
function UnitPowerPercent() return 1 end
-- UnitHealthPercent is the ENGINE: it evaluates a Step curve at the pet's true health fraction
-- (__pet.pct), which Lua never sees (the health itself may be a secret). A Step curve returns the
-- y of the last point whose x is at or below the fraction. __pct_mode picks a failure: 'throw'
-- raises, 'nonnumber' answers a boolean. Every call is recorded.
__pct_calls={}
__pct_mode='ok'
function UnitHealthPercent(unit,usePredicted,curve)
    __pct_calls[#__pct_calls+1]={unit=unit,predicted=usePredicted,curve=curve}
    if __pct_mode=='throw' then error('UnitHealthPercent refused') end
    if __pct_mode=='nonnumber' then return true end
    local y
    for _,pt in ipairs(curve.points) do
        if pt[1]<=__pet.pct then y=pt[2] end
    end
    return y
end
-- Sets the pet's health to a fraction of 253: the plain value and the engine's own fraction.
function __set_hp(frac)
    __pet.pct=frac
    __pet.health=math.floor(253*frac+0.5)
    __pet.healthMax=253
end
function CreateColor(r,g,b,a) return {r=r,g=g,b=b,a=a} end

-- A secret number: any compare, arithmetic or concat on it throws. nativeNumber is what the
-- engine's own formatter would print (the mock SetFormattedText unwraps it); Lua cannot trap a
-- truth test or `== nil`, so those are covered by the source checks below.
function __secret(n)
    local function boom() error('attempt to use a secret value', 2) end
    return setmetatable({secret=true,nativeNumber=n},{__lt=boom,__le=boom,__add=boom,__sub=boom,
        __mul=boom,__div=boom,__mod=boom,__pow=boom,__unm=boom,__concat=boom,__len=boom,
        __eq=function() error('attempt to compare a secret value', 2) end})
end
FS={IsSecret=function(v) return __rawtype(v)=='table' and v.secret==true end,
    Theme={},Layout={},
    LogDegradeOnce=function(key,msg) __messages[#__messages+1]=key..': '..msg end}
local t=FS.Theme
t.COLOR_HEALTH={1,.18,.59,1}
t.COLOR_POWER={.13,.88,1,1}
t.COLOR_BORDER={.66,.33,.97,1}
t.COLOR_MUTED={.616,.576,.769,1}
t.COLOR_BAR_TRACK={.04,.02,.09,1}
t.COLOR_HUD_SCRIM={.05,.02,.125,.4675}
t.COLOR_RED={1,.2314,.3059,1}
t.FONT_MONO='mono'
t.FLAT_TEXTURE,t.GLOW_EDGE_TEXTURE,t.GLOW_ROUND_TEXTURE='flat','glow_edge','glow_round'
t.SLICE_CUT_MARGIN=6
t.SLICE_CUT2_FILL_TEXTURE,t.SLICE_CUT2_OUTLINE_TEXTURE='cut2_fill','cut2_outline'
t.CHROME_CORNERS='cut'
-- Records every call so a check can see what a font or chrome call was handed.
t.ApplyFontGeneric=function(fs,path,size,color,flags)
    fs:SetFont(path,size,flags) fs.fontColor=color
end
t.ApplyMono=function(fs,size,color) fs:SetFont('mono',size,'') fs.fontColor=color end
t.AddCut2Texture=function(frame,path,color,layer,sublevel,inset)
    local tex=frame:CreateTexture() tex.path,tex.color,tex.inset=path,color,inset or 0
    return tex
end
-- SkinButton's result shape (ring and glow textures on frame.fsSkin); the red edge retints both.
t.SkinButton=function(frame,opts)
    local ring,glow=frame:CreateTexture(),frame:CreateTexture()
    frame.fsSkin={border={ring=ring},glow=glow,chamfer=opts and opts.chamfer}
    return frame.fsSkin
end
t.AddRoundedFill=function(frame,color,radius) frame.roundedColor,frame.roundedRadius=color,radius end
t.AddGradientBorder=function(frame,color,thickness,radius) frame.borderColor,frame.borderRadius=color,radius end
FS.Layout=nil
"""

LOAD = "function(src,name,fs) assert(loadstring(src,name))(name,fs) end"

# Everything the checks poke, read straight from the world the real files built.
HELPERS = r"""
function __fire_login()
    for _,f in ipairs(__frames) do
        if f.registered.PLAYER_LOGIN and f.scripts.OnEvent then f.scripts.OnEvent(f,'PLAYER_LOGIN') end
    end
end
function __fire(event,...)
    for _,f in ipairs(__frames) do
        if f.registered[event] and f.scripts.OnEvent then f.scripts.OnEvent(f,event,...) end
    end
end
function __set_height(h)
    UIParent:SetHeight(h)
end
-- The five alphas the low-HP layer drives: red name, red rail, red edge host, normal name, normal rail.
function __alphas()
    local P=FS.PetFrame
    return table.concat({P.redName.alpha,P.redHealthBar.shell.alpha,P.lowEdge.alpha,
        P.nameText.alpha,P.healthBar.shell.alpha},',')
end
-- What the engine was asked: unit|usePredicted|curve type|points, one entry per call.
function __pct_summary()
    local out={}
    for _,c in ipairs(__pct_calls) do
        local pts={}
        for _,pt in ipairs(c.curve.points) do pts[#pts+1]=pt[1]..','..pt[2] end
        out[#out+1]=tostring(c.unit)..'|'..tostring(c.predicted)..'|'..tostring(c.curve.kind)..'|'..table.concat(pts,';')
    end
    return table.concat(out,'\n')
end
-- A flat snapshot of every anchor and size on the container's slots and rails.
function __snapshot()
    local P=FS.PetFrame
    local parts={P.container,P.castSlot,P.barSlot,P.statusSlot,P.healthBar.shell,P.powerBar.shell,
        P.healthBar,P.powerBar}
    local out={}
    for i,f in ipairs(parts) do
        local keys={}
        for p,a in pairs(f.points) do keys[#keys+1]=p..':'..a.x..','..a.y..'>'..tostring(a.rp) end
        table.sort(keys)
        out[#out+1]=i..'|'..tostring(f.w)..'x'..tostring(f.h)..'|'..table.concat(keys,';')
    end
    return table.concat(out,'\n')
end
"""


def runtime(scale: float = 1.0, setup: str = "", allow_messages: bool = False) -> LuaRuntime:
    """A booted world: the real Layout, FrameHelpers and PetFrame at UIParent height 1440 * scale.
    `setup` is Lua run after the mock and before the real files load (e.g. remove an API)."""
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.execute(MOCK)
    rt.execute(HELPERS)
    if setup:
        rt.execute(setup)
    rt.execute(f"UIParent:SetHeight({1440 * scale})")
    load = rt.eval(LOAD)
    fs = rt.globals().FS
    for filename in ("Layout.lua", "FrameHelpers.lua", "PetFrame.lua"):
        path = PETFRAME if filename == "PetFrame.lua" else ADDON / filename
        load(path.read_text(encoding="utf-8"), f"@{filename}", fs)
    rt.execute("__fire_login()")
    messages = list(rt.globals().__messages.values())
    assert allow_messages or not messages, messages
    assert rt.globals().FS.PetFrame.container is not None, "PetFrame built no container"
    return rt


def bounds(rt: LuaRuntime, frame) -> dict:
    b = frame.GetBounds(frame)
    return {k: b[k] for k in ("x", "y", "w", "h", "right", "bottom")}


def approx(actual: float, expected: float, label: str, tol: float = 1e-6) -> None:
    assert abs(actual - expected) <= tol, f"{label}: got {actual}, want {expected}"


def _slots(rt: LuaRuntime) -> dict:
    pf = rt.globals().FS.PetFrame
    return {n: bounds(rt, getattr(pf, n)) for n in ("container", "castSlot", "barSlot", "statusSlot")}


def _interior(m: dict, s: float, box: dict) -> tuple[float, float, float, float]:
    """The panel interior: PAD on the sides, TOPY on top, the bottom pad (4) under the buttons."""
    return (box["x"] + m["PAD"] * s, box["y"] + m["TOPY"] * s,
            box["right"] - m["PAD"] * s, box["bottom"] - m["BOTPAD"] * s)


def check_status_slot_is_the_left_block_at_the_interior_left() -> None:
    """(a) The HP/mana slot starts at the interior left (side inset 6, top inset 5) and is the
    mockup's 134 wide left block (about 2/5 of the interior), a top row high."""
    m = mockup_constants()
    for s in SCALES:
        slots = _slots(runtime(s))
        left, top, _, _ = _interior(m, s, slots["container"])
        st = slots["statusSlot"]
        approx(st["x"], left, f"statusSlot left at scale {s}")
        approx(st["y"], top, f"statusSlot top at scale {s}")
        approx(st["w"], m["LW"] * s, f"statusSlot is the mockup's left block at scale {s}")
        approx(st["h"], m["TOPH"] * s, f"statusSlot is the mockup's top row high at scale {s}")


def check_cast_slot_sits_right_of_the_status_slot_to_the_interior_edge() -> None:
    """(b) The cast slot is right of the status slot by the mockup gap, to the interior right."""
    m = mockup_constants()
    for s in SCALES:
        slots = _slots(runtime(s))
        _, _, right, _ = _interior(m, s, slots["container"])
        st, cs = slots["statusSlot"], slots["castSlot"]
        approx(cs["x"], st["right"] + m["GAPX"] * s, f"castSlot gap at scale {s}")
        approx(cs["right"], right, f"castSlot ends at the interior right edge at scale {s}")
        approx(cs["y"], st["y"], f"castSlot shares the top at scale {s}")
        approx(cs["h"], st["h"], f"castSlot shares the height at scale {s}")
        approx(st["w"] + m["GAPX"] * s + cs["w"], right - slots["container"]["x"] - m["PAD"] * s,
               f"the top row closes the interior at scale {s}")
        approx(cs["w"], (m["PW"] - 2 * m["PAD"] - m["LW"] - m["GAPX"]) * s, f"castSlot is 198 wide at scale {s}")
        approx(cs["h"], 26 * s, f"castSlot is 26 high (the cast bar is sized to it) at scale {s}")


def check_bar_slot_is_below_both_and_spans_the_interior() -> None:
    """(c) The button slot is under the top row, spans the interior and closes the panel."""
    m = mockup_constants()
    for s in SCALES:
        slots = _slots(runtime(s))
        left, _, right, bottom = _interior(m, s, slots["container"])
        st, cs, bar = slots["statusSlot"], slots["castSlot"], slots["barSlot"]
        approx(bar["x"], left, f"barSlot left at scale {s}")
        approx(bar["right"], right, f"barSlot right at scale {s}")
        approx(bar["y"], max(st["bottom"], cs["bottom"]) + m["ROWGAP"] * s, f"barSlot below the top row at scale {s}")
        approx(bar["h"], m["BTN"] * s, f"barSlot is one button high at scale {s}")
        approx(bar["bottom"], bottom, f"barSlot closes the panel height at scale {s}")
        buttons = m["NUM"] * m["BTN"] + (m["NUM"] - 1) * m["BGAP"]
        approx(bar["w"], buttons * s, f"barSlot holds the 10 buttons exactly at scale {s}")


def check_container_is_the_mockup_panel_size() -> None:
    """(d) The container is the mockup's panel size (348 x 68) times the scale; its own sums close."""
    m = mockup_constants()
    for s in SCALES:
        rt = runtime(s)
        box = _slots(rt)["container"]
        approx(box["w"], m["PW"] * s, f"container width at scale {s}")
        approx(box["h"], m["PH"] * s, f"container height at scale {s}")
    # The mockup's own arithmetic, so a number that stops adding up fails here, not on screen.
    # (the 10 buttons and the panel height are pinned by check (c).)
    assert (m["PW"], m["PH"], m["TOPH"]) == (348, 68, 26), "option C is 348 x 68 with a 26 high top row"
    assert (m["PAD"], m["TOPY"], m["ROWGAP"], m["BOTPAD"]) == (6, 5, 3, 4), "insets 6 / 5, row gap 3, pad 4"
    assert m["MPY"] + m["BARH"] == m["TOPH"], "the mana bar ends on the top row's bottom edge"


def check_rails_name_row_and_text_sizes_match_the_mockup() -> None:
    """The HP and mana rails (7 high, 2 apart), the 9 high name row and every text size are the
    mockup's, times the scale."""
    m = mockup_constants()
    assert (m["BARH"], m["RAILGAP"], m["NAMEFS"], m["BARFS"], m["LEVELFS"]) == (7, 2, 9, 7.5, 7.5)
    for s in SCALES:
        rt = runtime(s)
        pf = rt.globals().FS.PetFrame
        st = bounds(rt, pf.statusSlot)
        hp, mp = bounds(rt, pf.healthBar.shell), bounds(rt, pf.powerBar.shell)
        approx(hp["y"] - st["y"], m["HPY"] * s, f"HP rail top at scale {s}")
        approx(hp["h"], m["BARH"] * s, f"HP rail height at scale {s}")
        approx(mp["y"] - st["y"], m["MPY"] * s, f"mana rail top at scale {s}")
        approx(mp["h"], m["BARH"] * s, f"mana rail height at scale {s}")
        approx(mp["y"] - hp["bottom"], m["RAILGAP"] * s, f"the rails are 2 apart at scale {s}")
        for box in (hp, mp):
            approx(box["x"], st["x"], f"rail left at scale {s}")
            approx(box["w"], st["w"], f"rail spans the block at scale {s}")
        # The name row is the name's 9 high band across the top; the HP rail follows it by the row gap.
        name_row = bounds(rt, pf.nameRow)
        approx(name_row["h"], m["NAMEFS"] * s, f"name row is 9 high at scale {s}")
        approx(name_row["y"], st["y"], f"name row on the block top at scale {s}")
        approx(mp["bottom"], st["bottom"], f"the rails close the 26 high top row at scale {s}")
        # The rail's own core follows the shell: the laser rail is re-fitted, not a new bar type.
        approx(pf.healthBar.h, m["BARH"] * s, f"HP core height at scale {s}")
        approx(pf.powerBar.h, m["BARH"] * s, f"mana core height at scale {s}")
        for bar in (pf.healthBar, pf.powerBar):
            approx(bar.fsRail.bloomTop.h, 4 * s, f"bloom stays 4 at scale {s}")
            approx(bar.fsRail.spark.w, 16 * s, f"spark stays 16 wide at scale {s}")
            approx(bar.fsRail.spark.h, 16 * s, f"spark stays 16 high at scale {s}")
        sizes = {
            "name": (pf.nameText, m["NAMEFS"]),
            "level": (pf.levelText, m["LEVELFS"]),
            "hp value": (pf.healthBar.text, m["BARFS"]),
            "mana value": (pf.powerBar.text, m["BARFS"]),
        }
        for label, (fontstring, size) in sizes.items():
            approx(fontstring.fontSize, size * s, f"{label} text size at scale {s}")
        # Option C prints both numbers inside the rails.
        assert pf.healthBar.text.text == "253 / 253", pf.healthBar.text.text
        assert pf.powerBar.text.text == "320 / 320", pf.powerBar.text.text


def check_level_is_plain_muted_lv_text_with_no_chip() -> None:
    """The level is plain muted "LV n" text at the name row's right edge, 7.5 pt, and no chip is
    built: nothing calls AddRoundedFill or AddGradientBorder, and FS.PetFrame.levelChip is gone."""
    m = mockup_constants()
    for s in SCALES:
        rt = runtime(s)
        pf = rt.globals().FS.PetFrame
        assert pf.levelChip is None, "the level chip is gone"
        chipped = [f for f in rt.globals().__frames.values() if f.roundedColor or f.borderColor]
        assert not chipped, "no frame carries a rounded fill or gradient border (a chip)"
        assert pf.levelText.text == "LV 11", pf.levelText.text
        muted = rt.globals().FS.Theme.COLOR_MUTED
        for i in (1, 2, 3):
            approx(pf.levelText.fontColor[i], muted[i], f"level text is COLOR_MUTED (channel {i}) at scale {s}")
        approx(pf.levelText.fontSize, m["LEVELFS"] * s, f"level text size at scale {s}")
        st, row = bounds(rt, pf.statusSlot), bounds(rt, pf.nameRow)
        approx(row["right"], st["right"], f"the level ends on the block's right edge at scale {s}")
        # The name stops short of the level rather than running under it.
        assert rt.eval("FS.PetFrame.nameText.points.RIGHT.rel == FS.PetFrame.levelText"), "name is anchored to the LV text"
        assert rt.eval("FS.PetFrame.nameText.points.RIGHT.rp") == "LEFT", "name ends at the LV text's left edge"
        approx(rt.eval("FS.PetFrame.nameText.points.RIGHT.x"), -NAME_LEVEL_GAP * s, f"name to level gap at scale {s}")
        # The level is seated flush on the name row's right edge, no inset.
        assert rt.eval("FS.PetFrame.levelText.points.RIGHT.rel == FS.PetFrame.nameRow"), "level is anchored to the name row"
        assert rt.eval("FS.PetFrame.levelText.points.RIGHT.rp") == "RIGHT", "level hangs on the name row's right edge"
        approx(rt.eval("FS.PetFrame.levelText.points.RIGHT.x"), 0, f"level text right offset at scale {s}")
    rt = runtime(1.0)
    rt.execute("__pet.level = 0; __fire('UNIT_LEVEL','pet')")
    assert rt.globals().FS.PetFrame.levelText.text == "LV ??", rt.globals().FS.PetFrame.levelText.text


def check_layout_petcontainer_is_348_by_68_and_keeps_its_floating_bottom_edge() -> None:
    """Layout.lua's petcontainer is the mockup's 348 x 68, and moving y from -403 to -410 keeps the
    CENTER anchored bottom edge (y - h / 2) at the old -444, so the Console gap is unchanged."""
    m = mockup_constants()
    pet = runtime(1.0).globals().FS.Layout.petcontainer
    assert (pet["w"], pet["h"]) == (m["PW"], m["PH"]), (pet["w"], pet["h"])
    assert pet["point"] == "CENTER" and pet["relPoint"] == "CENTER", "the bottom edge math needs a CENTER seat"
    assert pet["y"] == -410 and pet["x"] == -363, (pet["x"], pet["y"])
    assert pet["y"] - pet["h"] / 2 == -444, "the bottom edge stays at -444"


def check_pet_panel_clears_the_console_and_the_chat() -> None:
    """(g) The FLOAT seat (what the panel returns to when the Console is not drawn; the docked seat,
    the Console's TOPLEFT plus DOCK_X, is pinned by petdock-harness.py): the pet panel sits
    CONSOLE_PET_GAP above the Console's halo (and its shoulder tab, when their x ranges overlap) and
    CHAT_CLEARANCE right of the chat terminal's outer edge, with the Console drawn by the real
    ActionBars.lua and Console.lua (console-harness.py) at both of its scales. Layout entry numbers,
    design px, x centre-relative, y up."""
    spec = importlib.util.spec_from_file_location("console_harness", HERE / "console-harness.py")
    console = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(console)
    layout = runtime(1.0).globals().FS.Layout
    pet = layout.petcontainer
    left, right = pet["x"] - pet["w"] / 2, pet["x"] + pet["w"] / 2
    bottom = pet["y"] - pet["h"] / 2
    gap, clear, chat = layout.CONSOLE_PET_GAP, layout.CHAT_CLEARANCE, layout.CHAT_CHROME_RIGHT
    assert left >= chat + clear, f"pet left {left} is not {clear} clear of the chat chrome edge {chat}"
    for s in console.SCALES:
        e = console.outer_extent(s)
        top = e["top"]
        if right > e["tabLeft"] and left < e["right"]:  # over the shoulder tab: clear it too
            top = max(top, e["tabTop"])
        assert bottom >= top + gap, f"pet bottom {bottom} is not {gap} above the Console halo top {top} at scale {s:.4f}"


def check_a_rescale_in_combat_touches_no_geometry_until_combat_ends() -> None:
    """(f) A rescale in combat leaves the slots alone; PLAYER_REGEN_ENABLED applies it."""
    m = mockup_constants()
    before = runtime(1.0).eval("__snapshot()")
    rt = runtime(1.0)
    rt.execute("__combat = true")
    # Layout.lua's own watcher re-seats the container itself (its documented combat
    # limitation); PetFrame's callbacks are the part under test, so freeze that call.
    rt.execute("FS.Layout._applied = {}")
    rt.execute("__set_height(921.6); __fire('UI_SCALE_CHANGED')")
    during = rt.eval("__snapshot()")
    assert during == before, f"geometry moved in combat:\n{before}\n--- now ---\n{during}"
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    s = 0.64
    pf = rt.globals().FS.PetFrame
    # The container itself is re-seated by Layout.Apply from the deferred path.
    box_slots = {n: bounds(rt, getattr(pf, n)) for n in ("castSlot", "barSlot", "statusSlot")}
    approx(box_slots["statusSlot"]["w"], m["LW"] * s, "statusSlot applied at the new scale after combat")
    approx(box_slots["castSlot"]["w"], (m["PW"] - 2 * m["PAD"] - m["LW"] - m["GAPX"]) * s,
           "castSlot applied at the new scale after combat")
    approx(box_slots["castSlot"]["h"], m["TOPH"] * s, "castSlot height applied at the new scale after combat")
    approx(bounds(rt, pf.nameRow)["h"], m["NAMEFS"] * s, "name row applied at the new scale after combat")
    approx(pf.powerBar.h, m["BARH"] * s, "mana rail height applied at the new scale after combat")
    approx(box_slots["barSlot"]["h"], m["BTN"] * s, "barSlot applied at the new scale after combat")
    approx(pf.healthBar.h, m["BARH"] * s, "rail height applied at the new scale after combat")
    approx(pf.healthBar.text.fontSize, m["BARFS"] * s, "value text re-sized after combat")


def check_secret_hp_and_mana_render_through_the_value_text_without_a_compare() -> None:
    """(h) Secret health, mana, name and level never reach a compare, arithmetic or concat: the
    bars get the raw values, the value text goes through SetFormattedText, the name through SetText."""
    rt = runtime(1.0)
    rt.execute(
        "__pet.health, __pet.healthMax = __secret(253), __secret(300)\n"
        "__pet.power, __pet.powerMax = __secret(120), __secret(320)\n"
        "__pet.level, __pet.name = __secret(11), __secret(0)\n"
        "__fire('PET_BAR_UPDATE')")
    messages = list(rt.globals().__messages.values())
    assert not messages, messages
    pf = rt.globals().FS.PetFrame
    assert pf.healthBar.text.text == "253 / 300", pf.healthBar.text.text
    assert pf.powerBar.text.text == "120 / 320", pf.powerBar.text.text
    assert rt.eval("rawequal(FS.PetFrame.healthBar.value, __pet.health)"), "bar got the raw secret"
    assert rt.eval("rawequal(FS.PetFrame.healthBar.max, __pet.healthMax)"), "bar got the raw secret max"
    assert rt.eval("rawequal(FS.PetFrame.nameText.text, __pet.name)"), "name went to SetText untouched"
    assert pf.levelText.text == "", "a secret level reads blank"
    # And each value event on its own (UNIT_HEALTH / UNIT_POWER_UPDATE / UNIT_NAME_UPDATE).
    rt.execute("__fire('UNIT_HEALTH','pet'); __fire('UNIT_POWER_UPDATE','pet'); "
               "__fire('UNIT_NAME_UPDATE','pet'); __fire('UNIT_LEVEL','pet')")
    assert not list(rt.globals().__messages.values())


def check_a_nil_pet_name_reads_blank() -> None:
    rt = runtime(1.0)
    rt.execute("__pet.name = false; UnitName = function() return nil end; __fire('UNIT_NAME_UPDATE','pet')")
    assert rt.globals().FS.PetFrame.nameText.text == "", "a nil name shows blank"


def check_the_name_is_never_boolean_tested() -> None:
    """Lua cannot trap `secret or ""`, so pin the source: in UpdateStatusName the IsSecret test
    comes before the first form that would boolean-test the name (`or`, `if n`, `not n`).

    Limit: a source pin of this one function; it does not catch a truth test spelled any other way,
    and a behavioral secret check cannot trap a truth test in Lua."""
    src = PETFRAME.read_text(encoding="utf-8")
    body = re.search(r"local function UpdateStatusName\(\).*?\nend\n", src, re.S)
    assert body, "UpdateStatusName not found"
    text = re.sub(r"--[^\n]*", "", body.group(0))
    secret_at = text.find("IsSecret(")
    assert secret_at >= 0, "UpdateStatusName must test IsSecret"
    truth = re.search(r"\bor\b|\bif n\b|\bnot n\b", text)
    assert truth, "expected the non-secret branch's `n or \"\"`; the pin's premise changed"
    assert secret_at < truth.start(), "the name is boolean-tested before the IsSecret test"


def check_a_failing_value_text_latches_and_later_updates_skip() -> None:
    """(i) The first SetFormattedText that throws latches valueTextBroken: both texts blank, one
    log line, and no later UNIT_HEALTH / UNIT_POWER_UPDATE calls SetFormattedText again."""
    rt = runtime(1.0)
    pf = rt.globals().FS.PetFrame
    rt.execute("__fail_formatted = true; __fire('UNIT_HEALTH','pet')")
    messages = list(rt.globals().__messages.values())
    assert len(messages) == 1 and messages[0].startswith("petframe_value_text"), messages
    assert pf.healthBar.text.text == "" and pf.powerBar.text.text == "", "both texts blanked"
    hp_calls, mp_calls = pf.healthBar.text.fmtCalls, pf.powerBar.text.fmtCalls
    rt.execute("__fail_formatted = false\n"
               "__fire('UNIT_HEALTH','pet'); __fire('UNIT_POWER_UPDATE','pet'); __fire('PET_BAR_UPDATE')")
    assert pf.healthBar.text.fmtCalls == hp_calls, "health text written after the latch"
    assert pf.powerBar.text.fmtCalls == mp_calls, "mana text written after the latch"
    assert pf.healthBar.text.text == "" and pf.powerBar.text.text == "", "text stays blank after the latch"
    assert len(list(rt.globals().__messages.values())) == 1, "logged more than once"


def mock_selftest_fontstring_without_font_throws() -> None:
    """Mock self-test, not a PetFrame check: the mock is only as strict as the client if
    SetText and SetFormattedText on a FontString with no font throw; every FontString PetFrame
    builds already has its font, or the build would have raised."""
    rt = runtime(1.0)
    for snippet in ("SetText('x')", "SetFormattedText('%d', 1)"):
        try:
            rt.execute("CreateFrame('Frame'):CreateFontString():" + snippet)
        except LuaError as exc:
            assert "Font not set" in str(exc), exc
        else:
            raise AssertionError(snippet.split("(")[0] + " on a FontString with no font did not throw")


def check_visibility_events_in_combat_make_no_show_or_hide_calls() -> None:
    """(k) In combat the container is implicitly protected: with the pet gone, UNIT_FLAGS and
    PET_BAR_UPDATE only write alpha, never Show, Hide or EnableMouse (the client blocks all three:
    ADDON_ACTION_BLOCKED on FSPetContainer:EnableMouse() in a live /fsbug). Regen does the real Hide.
    The container's own mouse is OFF from the build on and never changes: nothing needs it (no
    OnEnter, no tooltip; the drag handle and the secure buttons take their own mouse), and an invisible
    panel must not swallow world clicks while a dead pet's alpha-0 panel waits for regen."""
    rt = runtime(1.0)
    container = rt.globals().FS.PetFrame.container
    assert container.mouse is False, "the container takes no mouse of its own"
    rt.execute("local c = FS.PetFrame.container; local real = c.EnableMouse; "
               "__mouse_calls = {}; c.EnableMouse = function(self, v) __mouse_calls[#__mouse_calls + 1] = tostring(v); "
               "return real(self, v) end")
    rt.execute("__combat = true; __pet.exists = false")
    shows, hides = container.showCalls or 0, container.hideCalls or 0
    rt.execute("__fire('UNIT_FLAGS','pet'); __fire('PET_BAR_UPDATE'); __fire('UNIT_PET','player')")
    assert (container.showCalls or 0) == shows, "Show called on the container in combat"
    assert (container.hideCalls or 0) == hides, "Hide called on the container in combat"
    assert container.alpha == 0, "gone pet: alpha 0 in combat"
    assert container.shown is True, "the container is still shown (Hide is deferred)"
    rt.execute("__pet.exists = true; __fire('UNIT_FLAGS','pet'); __fire('PET_BAR_UPDATE'); __fire('UNIT_PET','player')")
    assert container.alpha == 1, "a pet back in combat shows again by alpha"
    rt.execute("__pet.exists = false; __fire('UNIT_FLAGS','pet')")
    assert not list(rt.globals().__blocked.values()), list(rt.globals().__blocked.values())
    rt.execute("__combat = false; __fire('PLAYER_REGEN_ENABLED')")
    assert container.shown is False and (container.hideCalls or 0) == hides + 1, "regen applies the real Hide"
    assert container.alpha == 1
    rt.execute("__pet.exists = true; __fire('UNIT_PET','player'); __pet.exists = false; __fire('UNIT_PET','player')")
    assert not list(rt.globals().__blocked.values()), list(rt.globals().__blocked.values())
    assert container.mouse is False, "the container's mouse came back on"
    assert not list(rt.globals().__mouse_calls.values()), "EnableMouse was called on the container after the build"


def check_the_gate_answer_reaches_petdock_in_combat_too() -> None:
    """The dock's gap patch tracks the panel by alpha, which is legal in combat, so PetFrame tells
    FS.PetDock.SetPetShown the gate's answer on EVERY Apply, not only the out-of-combat tail: a pet
    dying in combat closes the hole in the Console's top line at once, a re-summon reopens it."""
    rt = runtime(1.0)
    rt.execute("__shown_calls = {}; FS.PetDock = { SetPetShown = function(show) "
               "__shown_calls[#__shown_calls + 1] = tostring(show) .. ':' .. tostring(__combat) end }")

    def calls() -> list:
        return list(rt.globals().__shown_calls.values())

    rt.execute("__combat = true; __pet.exists = false; __fire('UNIT_FLAGS','pet')")
    assert calls()[-1:] == ["false:true"], f"a pet gone in combat was not reported: {calls()}"
    rt.execute("__pet.exists = true; __fire('UNIT_PET','player')")
    assert calls()[-1:] == ["true:true"], f"a pet back in combat was not reported: {calls()}"
    rt.execute("__pet.exists = false; __fire('UNIT_FLAGS','pet'); __combat = false; __fire('PLAYER_REGEN_ENABLED')")
    assert calls()[-1:] == ["false:false"], f"regen did not report the gate: {calls()}"
    container = rt.globals().FS.PetFrame.container
    assert container.shown is False, "regen still does the real Hide"


# ---------------------------------------------------------------------------------------------
# Low HP (step S7): a red name, a red rail twin and a red edge, driven by ALPHA from a Step curve
# ---------------------------------------------------------------------------------------------


def _alphas(rt: LuaRuntime) -> dict:
    names = ("red name", "red rail", "red edge", "name", "rail")
    return dict(zip(names, (float(v) for v in str(rt.eval("__alphas()")).split(",")), strict=True))


def _expect(rt: LuaRuntime, low: float, label: str) -> None:
    """Red layer at `low`, the normal layer at its inverse."""
    a = _alphas(rt)
    for k in ("red name", "red rail", "red edge"):
        assert a[k] == low, f"{label}: {k} alpha {a[k]}, want {low} ({a})"
    for k in ("name", "rail"):
        assert a[k] == 1 - low, f"{label}: {k} alpha {a[k]}, want {1 - low} ({a})"


def _messages(rt: LuaRuntime) -> list:
    return list(rt.globals().__messages.values())


def _party_low_constants() -> tuple[float, float]:
    src = (ADDON / "PartyFrames.lua").read_text(encoding="utf-8")
    frac = re.search(r"^local LOW_HP_FRACTION = ([\d.]+)", src, re.M)
    eps = re.search(r"^local LOW_HP_EPSILON\s*= ([\d.]+)", src, re.M)
    assert frac and eps, "PartyFrames.lua no longer defines LOW_HP_FRACTION / LOW_HP_EPSILON; update this harness"
    return float(frac.group(1)), float(eps.group(1))


def check_the_curve_driver_is_called_with_the_right_arguments() -> None:
    """UnitHealthPercent("pet", false, curve) twice per update: a Step curve that is 1 up to the
    PartyFrames LOW_HP_FRACTION (plus its epsilon) and 0 above, and its inverse."""
    frac, eps = _party_low_constants()
    step = frac + eps
    rt = runtime(1.0)
    rt.execute("__pct_calls = {}; __fire('UNIT_HEALTH','pet')")
    calls = str(rt.eval("__pct_summary()")).split("\n")
    assert len(calls) == 2, f"one low and one inverse call per update, got {calls}"
    low_call, base_call = (c.split("|") for c in calls)
    for call in (low_call, base_call):
        assert call[0] == "pet" and call[1] == "false", f"unit and usePredicted: {call}"
        assert call[2] == "1", f"the curve is a Step curve (Enum.LuaCurveType.Step): {call}"
    def points(call: list) -> list:
        return [tuple(float(v) for v in pt.split(",")) for pt in call[3].split(";")]
    assert points(low_call) == [(0.0, 1.0), (step, 0.0)], f"low curve: {low_call}"
    assert points(base_call) == [(0.0, 0.0), (step, 1.0)], f"inverse curve: {base_call}"
    approx(step - frac, eps, "the epsilon sits past the threshold", tol=1e-12)
    assert frac == 0.35, "the PartyFrames threshold is 35%"


def check_alpha_targets_are_set_and_the_inverse_targets_mirror_them() -> None:
    """Red name, red rail twin and red edge host take the low curve's alpha through SetAlpha; the
    normal name and rail take the inverse. Exactly 35% still counts as low."""
    rt = runtime(1.0)
    _expect(rt, 0, "full health")
    for frac, low in ((0.6, 0), (0.351, 0), (0.35, 1), (0.2, 1), (0.0, 1), (1.0, 0)):
        rt.execute(f"__set_hp({frac}); __fire('UNIT_HEALTH','pet')")
        _expect(rt, low, f"hp {frac}")
    # UNIT_MAXHEALTH and a plain pet change drive it too.
    rt.execute("__set_hp(0.1); __fire('UNIT_MAXHEALTH','pet')")
    _expect(rt, 1, "UNIT_MAXHEALTH")
    rt.execute("__set_hp(0.9); __fire('UNIT_PET','player')")
    _expect(rt, 0, "UNIT_PET")
    rt.execute("__set_hp(0.1); __fire('PET_BAR_UPDATE')")
    _expect(rt, 1, "PET_BAR_UPDATE")
    assert not _messages(rt), _messages(rt)


def check_the_pulse_is_an_alpha_group_on_a_child_of_the_curve_driven_host() -> None:
    """The edge host carries the curve alpha; the pulse is a looping Alpha animation on a CHILD of
    it (so the two alphas multiply) and the driver never writes the child's own alpha. The pulse
    numbers are the mockup's: .6 + .4 * pulse, period 1.1 s."""
    src = MOCKUP.read_text(encoding="utf-8")
    edge = re.search(r"A\(st\.low\?\.(\d+)\+\.(\d+)\*peS\.pulse:\.9\);ctx\.strokeStyle=col;"
                     r"ctx\.lineWidth=pLW\(\.9\);ctx\.stroke\(\);", src)
    period = re.search(r"peS\.pulse=st\.low\?\.5\+\.5\*Math\.sin\(t\*Math\.PI\*2/([\d.]+)\)", src)
    assert edge and period, "the mockup's low edge pulse no longer matches; update this harness"
    floor = float(f"0.{edge.group(1)}")
    top = round(floor + float(f"0.{edge.group(2)}"), 6)
    half = float(period.group(1)) / 2
    rt = runtime(1.0)
    rt.execute("__set_hp(0.2); __fire('UNIT_HEALTH','pet')")
    pf = rt.globals().FS.PetFrame
    assert rt.eval("FS.PetFrame.lowEdgePulse.parent == FS.PetFrame.lowEdge"), "the pulse frame is a child of the host"
    assert rt.eval("FS.PetFrame.lowEdge.alpha") == 1 and rt.eval("FS.PetFrame.lowEdgePulse.alpha") == 1
    groups = list(pf.lowEdgePulse.groups.values())
    assert len(groups) == 1, "one animation group on the pulse child"
    group = groups[0]
    anims = list(group.animations.values())
    assert group.looping == "BOUNCE" and len(anims) == 1 and anims[0].kind == "Alpha", (group.looping, len(anims))
    from_alpha = rt.eval("FS.PetFrame.lowEdgePulse.groups[1].animations[1].from")
    to_alpha = rt.eval("FS.PetFrame.lowEdgePulse.groups[1].animations[1].to")
    duration = rt.eval("FS.PetFrame.lowEdgePulse.groups[1].animations[1].duration")
    approx(from_alpha, top, "pulse starts at the mockup's full edge alpha")
    approx(to_alpha, floor, "pulse dips to the mockup's floor")
    approx(duration, half, "each leg is half the mockup's 1.1 s period")
    assert group.playing, "the pulse plays while low"
    # A group a hidden panel stopped plays again on the next low update.
    rt.execute("FS.PetFrame.lowEdgePulse.groups[1]:Stop(); __fire('UNIT_HEALTH','pet')")
    assert rt.eval("FS.PetFrame.lowEdgePulse.groups[1]:IsPlaying()"), "a stopped pulse is restarted"
    # The edge is a red ring plus glow, the mockup's red.
    red = rt.globals().FS.Theme.COLOR_RED
    ring = rt.eval("FS.PetFrame.lowEdgePulse.fsSkin.border.ring.color")
    glow = rt.eval("FS.PetFrame.lowEdgePulse.fsSkin.glow.color")
    for i in (1, 2, 3):
        approx(ring[i], red[i], f"ring is red (channel {i})")
        approx(glow[i], red[i], f"glow is red (channel {i})")


def check_the_low_look_is_the_mockups_red_name_rail_and_edge() -> None:
    """Red is Theme.COLOR_RED = the mockup's --red; the mockup turns the name (peStatusDc) and the
    HP rail (peRails) red when low, and the red name is the same text at the same size."""
    src = MOCKUP.read_text(encoding="utf-8")
    hexred = re.search(r"--red:#([0-9a-f]{6});", src)
    assert hexred and "var nc=st.low?K.red:K.white" in src and "var hc=st.low?K.red:K.pink" in src, \
        "the mockup's low name / rail rule changed; update this harness"
    token = re.search(r"^Theme\.COLOR_RED\s*=\s*\{\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),", (ADDON / "Theme.lua").read_text(encoding="utf-8"), re.M)
    assert token, "Theme.COLOR_RED not found"
    want = [int(hexred.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    for got, w in zip(token.groups(), want, strict=True):
        approx(float(got), w, "Theme.COLOR_RED is the mockup's red", tol=1e-3)
    for s in SCALES:
        rt = runtime(s)
        rt.execute("__pet.name = 'Zilyal'; __fire('UNIT_NAME_UPDATE','pet')")
        pf = rt.globals().FS.PetFrame
        assert pf.redName.text == pf.nameText.text == "Zilyal", (pf.redName.text, pf.nameText.text)
        approx(pf.redName.fontSize, pf.nameText.fontSize, f"red name size matches at scale {s}")
        assert pf.redName.fontPath == pf.nameText.fontPath, "same font"
        red = rt.globals().FS.Theme.COLOR_RED
        for i in (1, 2, 3):
            approx(pf.redName.fontColor[i], red[i], f"red name colour (channel {i}) at scale {s}")
        rail = pf.redHealthBar.fsRail
        for key, i in (("r", 1), ("g", 2), ("b", 3)):
            approx(rail[key], red[i], f"red rail twin colour ({key}) at scale {s}")


def check_the_red_twins_sit_exactly_on_the_normal_name_and_rail() -> None:
    """Same rect for the rail twin and the name, and the red name wraps and anchors like the name."""
    for s in SCALES:
        rt = runtime(s)
        pf = rt.globals().FS.PetFrame
        assert bounds(rt, pf.redHealthBar.shell) == bounds(rt, pf.healthBar.shell), f"rail twin rect at scale {s}"
        assert bounds(rt, pf.redName) == bounds(rt, pf.nameText), f"red name rect at scale {s}"
        approx(pf.redHealthBar.h, pf.healthBar.h, f"twin core height at scale {s}")
        approx(pf.redHealthBar.text.fontSize, pf.healthBar.text.fontSize, f"twin value text size at scale {s}")
        # Resting state at full health: every red part invisible.
        _expect(rt, 0, f"rest at scale {s}")


def check_the_twins_get_the_same_values_secrets_included() -> None:
    """The twin rail gets the very SetMinMaxValues / SetValue the normal rail gets (a secret
    straight through, no compare), the value text prints on both, and the red name takes the
    same name, a secret one untouched."""
    rt = runtime(1.0)
    rt.execute("__pet.health, __pet.healthMax = __secret(77), __secret(300)\n"
               "__pet.name = __secret(0)\n__pet.pct = 0.2\n"
               "__fire('UNIT_HEALTH','pet'); __fire('UNIT_NAME_UPDATE','pet')")
    assert not _messages(rt), _messages(rt)
    assert rt.eval("rawequal(FS.PetFrame.redHealthBar.value, __pet.health)"), "twin got the raw secret value"
    assert rt.eval("rawequal(FS.PetFrame.redHealthBar.max, __pet.healthMax)"), "twin got the raw secret max"
    assert rt.eval("rawequal(FS.PetFrame.redName.text, __pet.name)"), "red name got the secret name untouched"
    pf = rt.globals().FS.PetFrame
    assert pf.redHealthBar.text.text == "77 / 300" == pf.healthBar.text.text, pf.redHealthBar.text.text
    _expect(rt, 1, "secret health read by the engine curve")


def check_a_secret_health_is_never_compared() -> None:
    """With the curve working, Lua never reads the health for the layer at all; with the curve
    latched off, a secret leaves red at 0 and the base layer at 1 (the secret raises on any compare)."""
    rt = runtime(1.0)
    rt.execute("__pet.health, __pet.healthMax = __secret(10), __secret(300)\n__pet.pct = 0.05\n"
               "__fire('UNIT_HEALTH','pet')")
    _expect(rt, 1, "engine says low")
    rt.execute("__pet.pct = 0.9; __fire('UNIT_HEALTH','pet')")
    _expect(rt, 0, "engine says healthy")
    rt = runtime(1.0)
    rt.execute("__pct_mode = 'throw'\n__pet.health, __pet.healthMax = __secret(10), __secret(300)\n"
               "__fire('UNIT_HEALTH','pet'); __fire('UNIT_HEALTH','pet')")
    _expect(rt, 0, "latched off, secret health")
    assert len(_messages(rt)) == 1, _messages(rt)
    # No curve API at all, secret health: the same unknown reading.
    rt = runtime(1.0, setup="UnitHealthPercent = nil")
    rt.execute("__pet.health, __pet.healthMax = __secret(10), __secret(300); __fire('UNIT_HEALTH','pet')")
    _expect(rt, 0, "no API, secret health")
    assert not _messages(rt), "a missing API is not a failure to log"
    # A secret max with a plain current value is just as unknown.
    rt.execute("__pet.health, __pet.healthMax = 10, __secret(300); __fire('UNIT_HEALTH','pet')")
    _expect(rt, 0, "no API, secret max")


def check_a_plain_hp_falls_back_to_cur_over_max_when_the_curve_api_is_missing() -> None:
    """No UnitHealthPercent, or no C_CurveUtil: a plain cur / max <= 35% compare, only for a plain
    health. Nothing is logged for a missing API."""
    for setup in ("UnitHealthPercent = nil", "C_CurveUtil = nil", "Enum.LuaCurveType.Step = nil"):
        rt = runtime(1.0, setup=setup)
        _expect(rt, 0, f"{setup}: healthy")
        for cur, low in ((50, 1), (88, 1), (89, 0), (253, 0), (0, 1)):
            rt.execute(f"__pet.health, __pet.healthMax = {cur}, 253; __fire('UNIT_HEALTH','pet')")
            _expect(rt, low, f"{setup}: {cur}/253")
        rt.execute("__pet.health, __pet.healthMax = 5, 0; __fire('UNIT_HEALTH','pet')")
        _expect(rt, 0, f"{setup}: a zero max is unknown")
        assert not _messages(rt), (setup, _messages(rt))
        assert not list(rt.globals().__pct_calls.values()), "the engine is never asked without the API"


def check_the_first_curve_failure_latches_and_logs_once() -> None:
    """A throwing or non-numeric UnitHealthPercent latches on the first failure: one log under
    petframe_lowhp_curve, no later engine call, and the plain fallback takes over."""
    for mode in ("throw", "nonnumber"):
        rt = runtime(1.0)
        rt.execute(f"__pct_mode = '{mode}'; __pet.health = 50; __fire('UNIT_HEALTH','pet')")
        msgs = _messages(rt)
        assert len(msgs) == 1 and msgs[0].startswith("petframe_lowhp_curve"), (mode, msgs)
        _expect(rt, 1, f"{mode}: the fallback reads 50/253 as low")
        calls = len(list(rt.globals().__pct_calls.values()))
        rt.execute("__fire('UNIT_HEALTH','pet'); __fire('UNIT_MAXHEALTH','pet'); __fire('PET_BAR_UPDATE'); "
                   "__pet.health = 250; __fire('UNIT_HEALTH','pet')")
        assert len(list(rt.globals().__pct_calls.values())) == calls, f"{mode}: the engine is called again after the latch"
        assert len(_messages(rt)) == 1, f"{mode}: logged more than once: {_messages(rt)}"
        _expect(rt, 0, f"{mode}: the fallback reads 250/253 as healthy")


def check_a_curve_that_fails_to_build_latches_at_load() -> None:
    """If the curve cannot be built (SetType throws), the layer starts latched: one log on the
    first update, the plain fallback, and the engine is never asked."""
    rt = runtime(1.0, allow_messages=True,
                 setup="C_CurveUtil.CreateCurve = function() return { SetType = function() error('no') end, AddPoint = function() end } end")
    msgs = _messages(rt)
    assert len(msgs) == 1 and msgs[0].startswith("petframe_lowhp_curve"), msgs
    rt.execute("__pet.health = 40; __fire('UNIT_HEALTH','pet')")
    _expect(rt, 1, "fallback after a failed build")
    assert len(_messages(rt)) == 1 and not list(rt.globals().__pct_calls.values())


def check_pet_death_or_dismiss_forces_red_to_zero() -> None:
    """A dismissed or dead pet reads 0 red / 1 base without asking the engine about health (a
    corpse's 0% would otherwise read as critically low), and a revived low pet comes back red."""
    rt = runtime(1.0)
    rt.execute("__set_hp(0.2); __fire('UNIT_HEALTH','pet')")
    _expect(rt, 1, "low pet")
    rt.execute("__pct_calls = {}; __pet.exists = false; __fire('UNIT_PET','player')")
    _expect(rt, 0, "dismissed")
    assert not list(rt.globals().__pct_calls.values()), "no health read for a pet that is gone"
    rt.execute("__pet.exists = true; __fire('UNIT_PET','player')")
    _expect(rt, 1, "summoned again, still low")
    rt.execute("__pct_calls = {}; __set_hp(0); __pet.dead = true; __fire('UNIT_FLAGS','pet')")
    _expect(rt, 0, "dead")
    rt.execute("__fire('UNIT_HEALTH','pet'); __fire('UNIT_MAXHEALTH','pet'); __fire('PET_BAR_UPDATE')")
    _expect(rt, 0, "dead, health events keep it at 0")
    assert not list(rt.globals().__pct_calls.values()), "no health read for a dead pet"
    rt.execute("__set_hp(0.2); __pet.dead = false; __fire('UNIT_FLAGS','pet')")
    _expect(rt, 1, "revived")
    # A feign death flag is not death for the layer; a secret dead flag reads as not dead (IsPetDead).
    rt.execute("__pet.dead = __secret(1); __fire('UNIT_FLAGS','pet')")
    _expect(rt, 1, "a secret dead flag counts as not dead")
    # The player's token on a pet-less login: nothing exists, red stays 0 and no error is raised.
    rt = runtime(1.0)
    rt.execute("__pet.exists = false; __fire('PLAYER_ENTERING_WORLD')")
    _expect(rt, 0, "no pet at all")


def check_the_low_edge_is_retargetable() -> None:
    """PetDock owns the final edge art: SetLowHealthEdge(edge, base) moves the red alpha to
    another frame (the old host goes to 0 and hides) and adds frames to the inverse list."""
    rt = runtime(1.0)
    rt.execute("__set_hp(0.2); __fire('UNIT_HEALTH','pet')")
    rt.execute("OLD = FS.PetFrame.lowEdge; NEW = CreateFrame('Frame'); BASE = CreateFrame('Frame')\n"
               "RESULT = FS.PetFrame.SetLowHealthEdge(NEW, { BASE })")
    assert rt.eval("RESULT") is True
    assert rt.eval("NEW.alpha") == 1 and rt.eval("BASE.alpha") == 0, "the new targets are driven at once"
    assert rt.eval("OLD.alpha") == 0 and rt.eval("OLD.shown") is False, "the old host is retired"
    assert rt.eval("rawequal(FS.PetFrame.lowEdge, NEW)"), "FS.PetFrame.lowEdge follows the retarget"
    rt.execute("__set_hp(0.9); __fire('UNIT_HEALTH','pet')")
    assert rt.eval("NEW.alpha") == 0 and rt.eval("BASE.alpha") == 1
    assert rt.eval("OLD.alpha") == 0, "the retired host stays at 0"
    assert rt.eval("FS.PetFrame.SetLowHealthEdge(nil, {})") is False, "an edge without SetAlpha is refused"
    assert rt.eval("FS.PetFrame.SetLowHealthEdge({}, {})") is False
    assert rt.eval("rawequal(FS.PetFrame.lowEdge, NEW)"), "a refused retarget changes nothing"


# A fresh edge, base frame and animation group, with SetAlpha writes counted on the first two.
_EDGE_FIXTURE = (
    "local function counted(f)\n"
    "    f.writes = 0\n"
    "    local raw = f.SetAlpha\n"
    "    f.SetAlpha = function(s, a) s.writes = s.writes + 1 return raw(s, a) end\n"
    "    return f\n"
    "end\n"
    "function NEWFRAME() return counted(CreateFrame('Frame')) end\n"
    "function NEWPULSE() return CreateFrame('Frame'):CreateAnimationGroup() end\n"
)


def check_the_optional_pulse_group_replaces_the_previous_one() -> None:
    """SetLowHealthEdge(edge, base, pulse): the new group is the one kept playing and the previous
    group (the default pulse first) is stopped and no longer replayed. A call with no pulse, or a
    value that is not an animation group, leaves no pulse and stops the last one."""
    rt = runtime(1.0)
    rt.execute(_EDGE_FIXTURE)
    rt.execute("__set_hp(0.2); __fire('UNIT_HEALTH','pet')")
    rt.execute("DEFAULT = FS.PetFrame.lowEdgePulse.groups[1]; P1 = NEWPULSE(); P2 = NEWPULSE()")
    assert rt.eval("DEFAULT:IsPlaying()"), "the default pulse plays while low"
    assert rt.eval("FS.PetFrame.SetLowHealthEdge(NEWFRAME(), {}, P1)") is True
    assert not rt.eval("DEFAULT:IsPlaying()") and rt.eval("DEFAULT.stopCalls") == 1, "the default pulse is stopped"
    assert rt.eval("P1:IsPlaying()") and rt.eval("P1.playCalls") == 1, "the supplied pulse is played"
    # Only the supplied group is replayed from now on.
    rt.execute("P1:Stop(); DEFAULT.playCalls = 0; __fire('UNIT_HEALTH','pet')")
    assert rt.eval("P1:IsPlaying()"), "the supplied pulse is kept playing"
    assert rt.eval("DEFAULT.playCalls") == 0 and not rt.eval("DEFAULT:IsPlaying()"), "the old pulse is not replayed"
    # A second supplied group replaces the first.
    rt.execute("P1.stopCalls = 0")
    assert rt.eval("FS.PetFrame.SetLowHealthEdge(NEWFRAME(), {}, P2)") is True
    assert rt.eval("P1.stopCalls") == 1 and not rt.eval("P1:IsPlaying()") and rt.eval("P2:IsPlaying()")
    # No pulse argument, and an argument that is not a group, each retire the last group.
    assert rt.eval("FS.PetFrame.SetLowHealthEdge(NEWFRAME(), {})") is True
    assert not rt.eval("P2:IsPlaying()") and rt.eval("P2.stopCalls") == 1, "no pulse argument stops the last group"
    rt.execute("P2.playCalls = 0; P1.playCalls = 0; __fire('UNIT_HEALTH','pet')")
    assert rt.eval("P2.playCalls") == 0 and rt.eval("P1.playCalls") == 0, "nothing is replayed without a pulse"
    rt.execute("P3 = NEWPULSE(); FS.PetFrame.SetLowHealthEdge(NEWFRAME(), {}, P3)")
    assert rt.eval("FS.PetFrame.SetLowHealthEdge(NEWFRAME(), {}, {})") is True
    assert not rt.eval("P3:IsPlaying()") and rt.eval("P3.stopCalls") == 1, "a non-group pulse is ignored and the last stops"
    assert not _messages(rt), _messages(rt)


def check_setting_the_same_edge_twice_is_idempotent() -> None:
    """The same edge, base list and pulse a second time changes nothing: the edge is not hidden or
    zeroed on the way (no retire-then-redrive churn), the pulse is not stopped, and the base frame
    is still driven once per update (the list is replaced, not appended to)."""
    rt = runtime(1.0)
    rt.execute(_EDGE_FIXTURE)
    rt.execute("__set_hp(0.2); __fire('UNIT_HEALTH','pet')\n"
               "E = NEWFRAME(); B = NEWFRAME(); P = NEWPULSE()\n"
               "FS.PetFrame.SetLowHealthEdge(E, { B }, P)")
    assert rt.eval("E.alpha") == 1 and rt.eval("B.alpha") == 0 and rt.eval("P:IsPlaying()")
    rt.execute("E.writes, B.writes, P.stopCalls, P.playCalls = 0, 0, 0, 0")
    hides = rt.eval("E.hideCalls") or 0
    assert rt.eval("FS.PetFrame.SetLowHealthEdge(E, { B }, P)") is True
    assert (rt.eval("E.hideCalls") or 0) == hides and rt.eval("E.shown") is True, "the edge is not hidden"
    assert rt.eval("E.writes") == 1, f"the edge is driven once, not zeroed then redriven ({rt.eval('E.writes')})"
    assert rt.eval("P.stopCalls") == 0 and rt.eval("P:IsPlaying()"), "the pulse is not stopped"
    assert rt.eval("P.playCalls") == 0, "a pulse already playing is not restarted"
    assert rt.eval("E.alpha") == 1 and rt.eval("B.alpha") == 0, "alphas are still right"
    assert rt.eval("rawequal(FS.PetFrame.lowEdge, E)")
    # No duplicate base entry: one write per update, after one call and after several.
    rt.execute("FS.PetFrame.SetLowHealthEdge(E, { B }, P)\nB.writes = 0\n__fire('UNIT_HEALTH','pet')")
    assert rt.eval("B.writes") == 1, f"the base frame is driven once per update ({rt.eval('B.writes')})"
    rt.execute("__set_hp(0.9); __fire('UNIT_HEALTH','pet')")
    assert rt.eval("E.alpha") == 0 and rt.eval("B.alpha") == 1
    assert not _messages(rt), _messages(rt)


def check_switching_the_edge_resets_the_old_base_frames_to_alpha_one() -> None:
    """Retargeting while the pet is low: the old base frames (at 0 under the red layer) go back to
    alpha 1 at once and are no longer driven; the new base frames take over; the old edge goes to 0."""
    rt = runtime(1.0)
    rt.execute(_EDGE_FIXTURE)
    rt.execute("__set_hp(0.2); __fire('UNIT_HEALTH','pet')\n"
               "E1, B1, B1b = NEWFRAME(), NEWFRAME(), NEWFRAME()\n"
               "FS.PetFrame.SetLowHealthEdge(E1, { B1, B1b })")
    assert rt.eval("B1.alpha") == 0 and rt.eval("B1b.alpha") == 0 and rt.eval("E1.alpha") == 1, "low drives the first set"
    rt.execute("E2, B2 = NEWFRAME(), NEWFRAME()\nFS.PetFrame.SetLowHealthEdge(E2, { B2 })")
    assert rt.eval("B1.alpha") == 1 and rt.eval("B1b.alpha") == 1, "every old base frame is back to alpha 1"
    assert rt.eval("E1.alpha") == 0 and rt.eval("E1.shown") is False, "the old edge is zeroed and hidden"
    assert rt.eval("E2.alpha") == 1 and rt.eval("B2.alpha") == 0, "the new set is driven at once"
    # Later updates drive only the new set: the old base frames stay at 1 while the pet is low.
    rt.execute("__fire('UNIT_HEALTH','pet'); __fire('UNIT_MAXHEALTH','pet')")
    assert rt.eval("B1.alpha") == 1 and rt.eval("B1b.alpha") == 1, "the old base frames are no longer driven"
    assert rt.eval("E1.alpha") == 0 and rt.eval("E2.alpha") == 1 and rt.eval("B2.alpha") == 0
    assert not _messages(rt), _messages(rt)


def check_exactly_35_percent_is_low_on_every_path() -> None:
    """The boundary is inclusive: 35% reads low and just above reads healthy. The Step curve puts
    its break epsilon past 0.35 (so a pet at exactly 0.35 is still on the low side), and the plain
    cur / max fallback, taken with no curve API or after the latch, uses <= (35/100 is low, 36/100
    is not)."""
    frac, eps = _party_low_constants()
    rt = runtime(1.0)
    rt.execute("__set_hp(0.35); __fire('UNIT_HEALTH','pet')")
    _expect(rt, 1, "curve: exactly 35%")
    calls = str(rt.eval("__pct_summary()")).split("\n")
    breaks = {float(c.split("|")[3].split(";")[1].split(",")[0]) for c in calls[-2:]}
    assert len(breaks) == 1 and next(iter(breaks)) > frac, f"the curve breaks past 0.35, got {breaks}"
    approx(next(iter(breaks)) - frac, eps, "the break sits epsilon past the threshold", tol=1e-12)
    rt.execute("__set_hp(0.351); __fire('UNIT_HEALTH','pet')")
    _expect(rt, 0, "curve: just above 35%")
    for label, setup, pre in (
        ("no curve API", "UnitHealthPercent = nil", ""),
        ("latched curve", "", "__pct_mode = 'throw'; __fire('UNIT_HEALTH','pet')\n"),
    ):
        rt = runtime(1.0, setup=setup, allow_messages=True)
        rt.execute(pre + "__pet.health, __pet.healthMax = 35, 100; __fire('UNIT_HEALTH','pet')")
        _expect(rt, 1, f"{label}: 35/100")
        rt.execute("__pet.health, __pet.healthMax = 36, 100; __fire('UNIT_HEALTH','pet')")
        _expect(rt, 0, f"{label}: 36/100")
        rt.execute("__pet.health, __pet.healthMax = 34, 100; __fire('UNIT_HEALTH','pet')")
        _expect(rt, 1, f"{label}: 34/100")


def check_the_low_layer_is_legal_in_combat() -> None:
    """Every frame in the layer is a non-secure child: in combat the alphas still follow health and
    nothing calls Show or Hide on the protected container."""
    rt = runtime(1.0)
    container = rt.globals().FS.PetFrame.container
    shows, hides = container.showCalls or 0, container.hideCalls or 0
    rt.execute("__combat = true; __set_hp(0.2); __fire('UNIT_HEALTH','pet')")
    _expect(rt, 1, "low in combat")
    rt.execute("__set_hp(0.8); __fire('UNIT_HEALTH','pet')")
    _expect(rt, 0, "healthy again in combat")
    assert (container.showCalls or 0) == shows and (container.hideCalls or 0) == hides
    assert not _messages(rt), _messages(rt)


def check_the_slots_draw_strictly_above_the_fallback_red_edge() -> None:
    """With no PetDock the default red edge (ring plus glow) is the fallback. It only draws the panel
    edge, but it must not rely on creation order against the slots: the slots sit at a level strictly
    above it and above the container's own level plus one."""
    rt = runtime(1.0)
    pf = rt.globals().FS.PetFrame
    edge = pf.lowEdge
    assert edge is not None and rt.eval("FS.PetFrame.lowEdgePulse.fsSkin ~= nil"), "no fallback edge without PetDock"
    edge_level = edge.GetFrameLevel(edge)
    for name in ("castSlot", "barSlot", "statusSlot"):
        slot = getattr(pf, name)
        assert slot.GetFrameLevel(slot) > edge_level, \
            f"{name} (level {slot.GetFrameLevel(slot)}) does not draw above the red edge (level {edge_level})"


def main() -> int:
    cases = [
        ("status slot starts at the interior left", check_status_slot_is_the_left_block_at_the_interior_left),
        ("cast slot right of it to the interior edge", check_cast_slot_sits_right_of_the_status_slot_to_the_interior_edge),
        ("bar slot below both, spanning the interior", check_bar_slot_is_below_both_and_spans_the_interior),
        ("container is the mockup panel size", check_container_is_the_mockup_panel_size),
        ("rails, name row and text sizes match the mockup", check_rails_name_row_and_text_sizes_match_the_mockup),
        ("the level is plain muted LV text, no chip", check_level_is_plain_muted_lv_text_with_no_chip),
        ("Layout petcontainer is 348 x 68, bottom edge -444", check_layout_petcontainer_is_348_by_68_and_keeps_its_floating_bottom_edge),
        ("the float seat clears the Console and the chat", check_pet_panel_clears_the_console_and_the_chat),
        ("a rescale in combat waits for regen", check_a_rescale_in_combat_touches_no_geometry_until_combat_ends),
        ("secret hp, mana, name and level pass through", check_secret_hp_and_mana_render_through_the_value_text_without_a_compare),
        ("a nil pet name reads blank", check_a_nil_pet_name_reads_blank),
        ("the name is never boolean-tested", check_the_name_is_never_boolean_tested),
        ("a failing value text latches", check_a_failing_value_text_latches_and_later_updates_skip),
        ("mock self-test: a FontString without a font throws", mock_selftest_fontstring_without_font_throws),
        ("visibility events in combat never Show or Hide", check_visibility_events_in_combat_make_no_show_or_hide_calls),
        ("the gate answer reaches PetDock in combat too", check_the_gate_answer_reaches_petdock_in_combat_too),
        ("low HP: the curve driver gets the right arguments", check_the_curve_driver_is_called_with_the_right_arguments),
        ("low HP: alpha targets set, inverse targets mirror", check_alpha_targets_are_set_and_the_inverse_targets_mirror_them),
        ("low HP: the pulse is an Alpha group on a child of the host", check_the_pulse_is_an_alpha_group_on_a_child_of_the_curve_driven_host),
        ("low HP: the look is the mockup's red name, rail and edge", check_the_low_look_is_the_mockups_red_name_rail_and_edge),
        ("low HP: red twins sit exactly on the normal ones", check_the_red_twins_sit_exactly_on_the_normal_name_and_rail),
        ("low HP: the twins get the same values, secrets included", check_the_twins_get_the_same_values_secrets_included),
        ("low HP: a secret health is never compared", check_a_secret_health_is_never_compared),
        ("low HP: plain fallback without the curve API", check_a_plain_hp_falls_back_to_cur_over_max_when_the_curve_api_is_missing),
        ("low HP: the first failure latches and logs once", check_the_first_curve_failure_latches_and_logs_once),
        ("low HP: a curve that fails to build latches at load", check_a_curve_that_fails_to_build_latches_at_load),
        ("low HP: pet death or dismiss forces red to 0", check_pet_death_or_dismiss_forces_red_to_zero),
        ("low HP: the red edge is retargetable", check_the_low_edge_is_retargetable),
        ("low HP: the optional pulse group replaces the previous one", check_the_optional_pulse_group_replaces_the_previous_one),
        ("low HP: setting the same edge twice is idempotent", check_setting_the_same_edge_twice_is_idempotent),
        ("low HP: switching the edge resets the old base frames to 1", check_switching_the_edge_resets_the_old_base_frames_to_alpha_one),
        ("low HP: exactly 35% is low on the curve and plain paths", check_exactly_35_percent_is_low_on_every_path),
        ("low HP: legal in combat", check_the_low_layer_is_legal_in_combat),
        ("the slots draw strictly above the fallback red edge", check_the_slots_draw_strictly_above_the_fallback_red_edge),
    ]
    failures = 0
    for name, check in cases:
        try:
            check()
        except (AssertionError, AttributeError, RuntimeError, LuaError, TypeError) as exc:
            print(f"FAIL: {name}: {exc}")
            failures += 1
        else:
            print(f"PASS: {name}")
    print(f"{len(cases) - failures}/{len(cases)} petframe checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
