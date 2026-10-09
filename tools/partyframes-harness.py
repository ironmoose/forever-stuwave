#!/usr/bin/env python3
"""Exercise the real party layout and health readouts against a headless WoW API."""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
PARTY_SRC = (ADDON / "Modules/UnitFrames/PartyFrames.lua").read_text(encoding="utf-8")

MOCK = r"""
__frames, __messages = {}, {}
local Region = {}
Region.__index = Region
local function newRegion(parent)
    return setmetatable({parent=parent, points={}, scripts={}, shown=true, alpha=1,
        regions={}, registered={}}, Region)
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
function Region:Show() self.shown=true end
function Region:Hide() self.shown=false end
function Region:SetShown(v) self.shown=v end
function Region:IsShown() return self.shown end
-- The engine keeps ONE alpha for a texture: SetAlpha after SetVertexColor(r,g,b,a) replaces the
-- vertex alpha (the 2026-10-03 double border: the low-HP curve's SetAlpha(1) turned the glow's
-- .5 into 1). `alphaSlot` models that single slot; `alpha` stays what SetAlpha last wrote, and a
-- frame's alpha multiplies everything under it.
function Region:SetAlpha(a) self.alpha=a self.alphaSlot=a end
function Region:GetAlpha() return self.alpha end
function Region:SetText(t)
    if self.mono==nil then self.textBeforeFont=true end
    self.text=t
end
function Region:SetFormattedText(fmt,...)
    local args={...}
    -- Engine text setters accept secrets; Lua arithmetic on them must still fail.
    for i,v in ipairs(args) do
        if type(v)=='table' and v.nativeNumber then args[i]=v.nativeNumber end
    end
    self.text=string.format(fmt,unpack(args))
end
function Region:GetStringWidth() return #(self.text or '')*6 end
function Region:SetTextColor(...) self.textColor={...} end
function Region:SetColorTexture(...) self.color={...} end
function Region:SetVertexColor(...)
    self.color={...}
    if select('#',...)>=4 then self.alphaSlot=select(4,...) end
end
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
function Region:RegisterUnitEvent(event) self.registered[event]=true end
function Region:CreateFontString() return newRegion(self) end
function Region:SetScript(k,fn) self.scripts[k]=fn end
function Region:GetFrameLevel() return self.frameLevel or 1 end
function Region:SetFrameLevel(v) self.frameLevel=v end
function Region:SetAttribute(k,v) self[k]=v end
function Region:CreateAnimationGroup()
    local a={}
    for _,m in ipairs({'SetLooping','Play','SetFromAlpha','SetToAlpha','SetDuration',
        'SetSmoothing'}) do a[m]=function() end end
    a.CreateAnimation=function() return a end
    return a
end
for _,m in ipairs({'SetOrientation','SetFont','SetJustifyH','SetJustifyV','SetWordWrap',
    'SetNonSpaceWrap','SetMaxLines','SetShadowOffset',
    'RegisterForClicks','SetHorizTile','SetVertTile',
    'UnregisterEvent','HookScript'}) do Region[m]=function() end end
function Region:SetClipsChildren(v) self.clipsChildren=v end
function Region:UnregisterAllEvents() self.registered={} end
function Region:EnableMouse(v) self.mouse=v end
-- Children in creation order (a texture or font string is a region, not a child frame).
function Region:GetChildren()
    local out={}
    for _,f in ipairs(__frames) do if f.parent==self then out[#out+1]=f end end
    return unpack(out)
end
function CreateColor(r,g,b,a)
    for _,v in ipairs({r,g,b,a}) do assert(type(v)=='number','CreateColor needs 4 numbers') end
    return {r=r,g=g,b=b,a=a}
end
function CreateFrame(kind,name,parent)
    local f=newRegion(parent) f.kind,f.name=kind,name
    -- A new frame draws one level above its parent, as in the client.
    f.frameLevel=(parent and parent:GetFrameLevel() or 0)+1
    __frames[#__frames+1]=f
    if name then _G[name]=f end
    return f
end
UIParent=CreateFrame('Frame','UIParent') UIParent:SetSize(2560,1440)
SlashCmdList={}
function print(msg) __messages[#__messages+1]=msg end
function RegisterUnitWatch() end
function InCombatLockdown() return false end
function IsInGroup() return true end
function UnitExists() return true end
-- __target: the unit token the player has targeted (nil = none). __targetSecret makes
-- UnitIsUnit answer a SECRET boolean (the addon-restricted-map case); __targetThrows makes it
-- raise. A secret boolean is modelled as a plain `true` that FS.IsSecret flags for exactly the
-- next check: LuaJIT cannot make `secret == true` or a truth test throw (__eq only fires between
-- two tables), so what a guard-free `same == true` would do is read it as targeted. Removing
-- the IsSecret guard therefore paints the edge purple, which the secret cases assert against.
__target=nil __targetSecret=false __targetThrows=false __secretPending=false
function UnitIsUnit(a,b)
    if __targetThrows then error('UnitIsUnit: restricted') end
    if __targetSecret then __secretPending=true return true end
    __secretPending=false
    local u=(a=='target' and b) or (b=='target' and a) or nil
    return __target~=nil and u==__target
end
-- Party members are always Priests; the PLAYER's class is __playerClass (the tray's buff table
-- is keyed by it).
__playerClass='PRIEST'
function UnitClass(unit)
    if unit=='player' then
        return __playerClass:sub(1,1)..__playerClass:sub(2):lower(),__playerClass
    end
    return 'Priest','PRIEST'
end
function UnitName() return 'First' end
function GetUnitName(unit,showServer) assert(showServer==true) return __unitName or 'First Surname' end
__role,__level='NONE',60
function UnitGroupRolesAssigned() return __role end
CLASS_ICON_TCOORDS={PRIEST={.5,.75,.25,.5},WARLOCK={.75,1,.25,.5},MAGE={.25,.5,0,.25},
    DRUID={.75,1,0,.25}}
function UnitLevel() return __level end
function GetMaxPlayerLevel() return 60 end
function UnitPowerType() return 0,'MANA' end
function UnitPower() return 50 end
function UnitPowerMax() return 100 end
-- __debuffs: dispel types of the unit's harmful auras, in slot order. Both aura readers honor
-- the filter: HELPFUL returns __buffs[unit] (entries {name,caster,duration,expiration,icon}) and
-- the RAID pre-filter keeps only what a Priest dispels.
__debuffs={}
__buffs={}
-- __debuffIds: dispel type -> the spellId its harmful aura reports (nil: none; may be __secret).
__debuffIds={}
-- __raid: the dispel types the RAID pre-filter keeps (default: what a Priest dispels).
__raid={Magic=true,Disease=true}
local function auraAt(unit,index,filter)
    if filter:find('HELPFUL') then
        local b=(__buffs[unit] or {})[index]
        if b then
            return {name=b.name,icon=b.icon or 'bufficon',applications=1,dispelName='',
                duration=b.duration or 0,expirationTime=b.expiration or 0,
                sourceUnit=b.caster or 'target'}
        end
        return nil
    end
    local kept={}
    for _,d in ipairs(__debuffs) do
        if not filter:find('RAID') or __raid[d] then kept[#kept+1]=d end
    end
    local d=kept[index]
    if d then
        return {name='Debuff '..d,icon='icon',applications=1,dispelName=d,duration=0,
            expirationTime=0,sourceUnit='target',spellId=__debuffIds[d]}
    end
end
C_UnitAuras={GetAuraDataByIndex=function(unit,index,filter) return auraAt(unit,index,filter) end}
function UnitAura(unit,index,filter)
    local a=auraAt(unit,index,filter)
    if a then
        return a.name,a.icon,a.applications,a.dispelName,a.duration,a.expirationTime,a.sourceUnit
    end
end
-- Spell book: __spellIds maps a name to the id C_Spell.GetSpellInfo resolves it to (a name that
-- is not in the map does not resolve), __knownIds is what the spellbook APIs call known.
__spellIds,__knownIds={},{}
C_Spell={
    GetSpellInfo=function(x)
        local id=type(x)=='number' and x or __spellIds[x]
        if not id then return nil end
        return {name=type(x)=='string' and x or 'spell'..id,spellID=id,iconID=5000+id}
    end,
    GetSpellTexture=function(x) return 'spelltex:'..tostring(x) end,
}
-- __dispelKnown: spell ids known for the dispel set, kept apart from __knownIds (which the buff
-- checks replace wholesale). Defaults to a Priest's Dispel Magic and Cure Disease.
__dispelKnown={[527]=true,[528]=true}
C_SpellBook={IsSpellKnown=function(id) return __knownIds[id]==true or __dispelKnown[id]==true end}
-- Colors distinct from the theme's .5 grey, the dead grey (.35) and each other.
RAID_CLASS_COLORS={PRIEST={r=.9,g=.8,b=.1}}
-- No DebuffTypeColor: the global does not exist on 16001, the palette is FS.Theme.DISPEL_COLORS.
__readableCallbacks={}
function GetTime() return 0 end
__state='live' __health=100 __max=100 __fraction=1
function UnitIsConnected() return __state~='offline' end
function UnitIsDeadOrGhost() return __state=='dead' or __state=='ghost' end
function UnitIsGhost() return __state=='ghost' end
local function forbidden() error('arithmetic/comparison on secret health') end
__secret=setmetatable({secret=true},{__div=forbidden,__mul=forbidden,__add=forbidden,
    __sub=forbidden,__lt=forbidden,__le=forbidden,__eq=forbidden})
function UnitHealth() return __health end
__incoming,__absorb=0,0
function UnitGetIncomingHeals() return __incoming end
function UnitGetTotalAbsorbs() return __absorb end
function UnitHealthMax() return __max end
Enum={LuaCurveType={Linear=0,Step=1}}
C_CurveUtil={CreateCurve=function()
    return {points={},SetType=function(self,t) self.kind=t end,
        AddPoint=function(self,x,y) self.points[#self.points+1]={x,y} end}
end}
function UnitHealthPercent(unit,usePredicted,curve)
    assert(usePredicted==false,'UnitHealthPercent predicted flag must be false')
    if not curve then
        if __health==__secret then
            return setmetatable({secret=true,nativeNumber=__fraction},getmetatable(__secret))
        end
        return __fraction
    end
    local previous=curve.points[1]
    if __health==__secret and curve.kind~=Enum.LuaCurveType.Step then
        assert(#curve.points==2 and curve.points[1][1]==0 and curve.points[1][2]==0
            and curve.points[2][1]==1 and curve.points[2][2]==100,
            'secret-safe text percent requires native scale-to-100 curve')
        return setmetatable({secret=true,nativeNumber=__fraction*100},getmetatable(__secret))
    end
    for _,p in ipairs(curve.points) do
        if __fraction<p[1] then
            if curve.kind==Enum.LuaCurveType.Step then return previous[2] end
            return previous[2]+(__fraction-previous[1])/(p[1]-previous[1])*(p[2]-previous[2])
        end
        previous=p
    end
    return previous[2]
end
FS={IsSecret=function(v)
        if v==true and __secretPending then __secretPending=false return true end
        return type(v)=='table' and v.secret==true
    end,
    AurasReadable=function() return true end,
    OnAurasReadable=function(fn) __readableCallbacks[#__readableCallbacks+1]=fn end,Theme={},Layout={},
    LogDegradeOnce=function(key,msg) __messages[#__messages+1]=key..': '..msg end}
local t=FS.Theme
for _,k in ipairs({'COLOR_BG','COLOR_BORDER','COLOR_BAR_TRACK','COLOR_BAR_BORDER',
    'COLOR_HEALTH','COLOR_POWER'}) do t[k]={.5,.5,.5,1} end
-- Distinct from COLOR_BG's grey so a panel fill bound to the wrong token is observable.
t.COLOR_HUD_SCRIM={.25,.5,.75,.4675}
t.BAR_RADIUS,t.BAR_FILL_INSET,t.BAR_CORNER_MASK_LEVEL=4,2,3
t.PANEL_RADIUS,t.LEVEL_RADIUS=6,2
t.FONT_MONO,t.FONT_ORBITRON,t.FLAT_TEXTURE='mono','orbitron','flat'
t.COLOR_HEAL,t.HATCH_TEXTURE={.2,1,.1,1},'hatch'
for _,k in ipairs({'ApplyFontGeneric','ApplyMono','AddOuterGlow','AddRoundedFill',
    'AddGradientBorder'}) do t[k]=function() end end
-- ApplyMono records what it was asked for, so a check can tell the font was set (and before
-- any SetText, via Region:SetText's textBeforeFont flag).
t.ApplyMono=function(fontString,size,color) fontString.mono={size=size,color=color} end
-- Theme.SkinButton's contract for the alert ring: button.fsSkin.glow and .border.ring are the
-- two regions a caller retints (idempotent, like the real one).
t.SkinButton=function(button,opts)
    if button.fsSkin then return button.fsSkin end
    button.skinOpts=opts
    button.fsSkin={glow=button:CreateTexture(),border={ring=button:CreateTexture()},
        chamfer=opts and opts.chamfer}
    return button.fsSkin
end
t.COLOR_RED={1,0.2314,0.3059,1}  -- #ff3b4e, Theme.lua's --red
t.AddOuterGlow=function(frame,r,g,b,size,alpha,radius) frame.glowRadius=radius end
t.AddRoundedFill=function(frame,color,radius) frame.roundedRadius=radius frame.roundedColor=color end
t.AddGradientBorder=function(frame,color,thickness,radius) frame.borderRadius=radius end
local function cornerHandle(radius)
    local handle={quads={},radius=radius}
    handle.SetRadius=function(r) handle.radius=r end
    return handle
end
t.AddCornerMask=function(host,anchor,color,radius) host.maskRadius=radius return {} end
t.AddFillCorners=function(host,bar,color,radius) return cornerHandle(radius) end
-- Theme.AddCutFillErase(host, plate, color, chamfer): the nine-sliced fill erase. Records what it
-- was asked for on the host; nil under round or when __eraseUnavailable is set (a client that
-- cannot slice a texture), which is the caller's cue to take AddCornerMask.
-- Theme.AddCutSliceFill(panel, color, radius): the box fill as one nine-slice. Records what it was
-- asked for on the panel; nil under round or when __sliceFillUnavailable is set (no slicing).
t.AddCutSliceFill=function(panel,color,radius)
    if t.CHROME_CORNERS~='cut' or __sliceFillUnavailable then return nil end
    panel.sliceFill={color=color,radius=radius}
    return {}
end
t.AddCutFillErase=function(host,plate,color,chamfer)
    if t.CHROME_CORNERS~='cut' or __eraseUnavailable then return nil end
    host.cutErase={plate=plate,color=color,chamfer=chamfer}
    return {texture={},frame={}}
end
t.AddLeadingEdgeCorners=function(host,bar,color,radius) return cornerHandle(radius) end
-- Theme.CHROME_CORNERS ("cut" is the default; "round" is the untouched old path) and
-- the two chamfer helpers, mirroring Theme.lua's SnapForHeight: the largest of {2,3,4,6}
-- <= clamp(floor(h / divisor), 2, 6, floor(h / 2)), 0 under h = 4. The expected values in
-- the checks below are hard-coded, not derived from this stub.
t.CHROME_CORNERS='cut'
local function snapForHeight(h,divisor)
    if not h then return 0 end
    local want=math.min(math.max(math.floor(h/divisor),2),6,math.floor(h/2))
    if want<2 then return 0 end
    local best=2
    for _,c in ipairs({2,3,4,6}) do if c<=want then best=c end end
    return best
end
t.CutSize=function(h) return snapForHeight(h,3) end
t.CutSizeIcon=function(h) return snapForHeight(h,5) end
FS.Layout=nil
"""

LOAD = "function(src,name,fs) assert(loadstring(src,name))(name,fs) end"

# Blizzard's own party frames on the 12.x engine, shaped after Blizzard_UnitFrame (PartyFrame.lua,
# PartyMemberFrame.lua, CompactPartyFrame.lua): PartyFrame owns pooled PartyMemberFrameTemplate
# members (each with a PetFrame and a UnitFrame_Initialize healthbar/manabar) and parents
# CompactPartyFrame, which holds memberUnitFrames and petUnitFrames. Every call that would taint
# the frame's secure path (Hide, HookScript, SetScript, SetParent) throws, so the addon cannot
# pass by using one. CompactRaidFrameContainer and CompactRaidFrameManager are the frames the
# party sweep must leave alone.
BLIZZARD_PARTY = r"""
__blizz={}
function __blizzFrame(kind,name,parent)
    local f=CreateFrame(kind,name,parent)
    for _,m in ipairs({'Hide','HookScript','SetScript','SetParent'}) do
        f[m]=function() error(m..' on Blizzard frame '..tostring(name or kind)) end
    end
    f:RegisterEvent('GROUP_ROSTER_UPDATE') f:RegisterEvent('UNIT_AURA')
    f.mouse=true
    __blizz[#__blizz+1]=f
    return f
end
-- A plain child with no events of its own (a container, an aura button, a nested bar).
function __blizzLeaf(kind,parent)
    local f=__blizzFrame(kind,nil,parent)
    f.registered={}
    return f
end
-- PartyMemberFrameTemplate: HealthBarContainer.HealthBar forwards OnMouseUp to the member's
-- Click and is what UnitFrame_Initialize stores as .healthbar; AuraFrameContainer (member and
-- pet) parents the PartyAuraFrameTemplate buttons, which are mouse-enabled and made lazily.
function __blizzMember(party)
    local m=__blizzFrame('Button',nil,party)
    m.HealthBarContainer=__blizzLeaf('Frame',m)
    m.healthbar=__blizzFrame('StatusBar',nil,m.HealthBarContainer)
    m.HealthBarContainer.HealthBar=m.healthbar
    m.manabar=__blizzFrame('StatusBar',nil,m)
    m.PowerBarAlt=__blizzFrame('Frame',nil,m)  -- capital P on the party member, unlike Player
    m.AuraFrameContainer=__blizzLeaf('Frame',m)
    m.PetFrame=__blizzFrame('Button',nil,m)
    m.PetFrame.healthbar=__blizzFrame('StatusBar',nil,m.PetFrame)
    m.PetFrame.AuraFrameContainer=__blizzLeaf('Frame',m.PetFrame)
    return m
end
-- A compact unit frame's aura and status buttons are children, some with children of their own.
function __blizzCompactUnit(name,parent)
    local f=__blizzFrame('Button',name,parent)
    local buff=__blizzLeaf('Button',f)
    __blizzLeaf('Frame',buff)
    return f
end
function __blizzCompact(parent)
    local c=__blizzFrame('Frame','CompactPartyFrame',parent)
    c.memberUnitFrames,c.petUnitFrames={},{}
    for i=1,5 do c.memberUnitFrames[i]=__blizzCompactUnit('CompactPartyFrameMember'..i,c) end
    for i=1,3 do c.petUnitFrames[i]=__blizzCompactUnit(nil,c) end
    return c
end
function __blizzParty(compact)
    PartyFrame=__blizzFrame('Frame','PartyFrame',UIParent)
    PartyFrame.members={}
    for i=1,4 do PartyFrame.members[i]=__blizzMember(PartyFrame) end
    if compact then __blizzCompact(PartyFrame) end
    CompactRaidFrameContainer=__blizzFrame('Frame','CompactRaidFrameContainer',UIParent)
    CompactRaidFrameManager=__blizzFrame('Frame','CompactRaidFrameManager',UIParent)
end
function __effAlpha(f)
    local a=1
    while f do a=a*f.alpha f=f.parent end
    return a
end
-- A Blizzard frame is silenced once it draws nothing, takes no mouse and has no events.
function __silenced(f)
    return __effAlpha(f)==0 and f.mouse==false and next(f.registered)==nil
end
-- How many party-tree frames are NOT silenced and are neither `skip` nor under it.
function __unsilencedOutside(skip)
    local n=0
    for _,f in ipairs(__blizz) do
        if f.name~='CompactRaidFrameContainer' and f.name~='CompactRaidFrameManager' then
            local under,p=false,f
            while p do if p==skip then under=true end p=p.parent end
            if not under and not __silenced(f) then n=n+1 end
        end
    end
    return n
end
"""

BLIZZARD_PARTY_MODES = {
    "full": "__blizzParty(true)",
    "no_compact": "__blizzParty(false)",
    "compact_only": "__blizzCompact(UIParent)",
    "none": "",
    # PartyMemberFrame1..4 are the pre-12.x names: absent from this client's globals dump.
    "decoy": "PartyMemberFrame1=__blizzFrame('Button','PartyMemberFrame1',UIParent)",
}

THEME_SRC = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")


def _theme_color(name: str) -> tuple[float, float, float, float]:
    """The rgba of `Theme.NAME = { r, g, b, a }` straight from Theme.lua (so a missing or
    drifted token fails here, not in the client)."""
    alias = re.search(rf"^Theme\.{name}\s*=\s*Theme\.(\w+)\s*(?:--.*)?$", THEME_SRC, re.M)
    if alias:  # e.g. `Theme.COLOR_HEAL = Theme.COLOR_CARET_HEALTH`
        return _theme_color(alias.group(1))
    match = re.search(
        rf"^Theme\.{name}\s*=\s*\{{\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)",
        THEME_SRC, re.M)
    assert match, f"Theme.lua has no color token {name}"
    return tuple(float(v) for v in match.groups())


def _dispel_colors() -> dict[str, tuple[float, float, float]]:
    """Theme.DISPEL_COLORS straight from Theme.lua, rgb per dispel type."""
    block = re.search(r"^Theme\.DISPEL_COLORS = \{\n(.*?)^\}", THEME_SRC, re.M | re.S)
    assert block, "Theme.lua has no Theme.DISPEL_COLORS table"
    out = {}
    for name, r, g, b in re.findall(
            r"(\w+)\s*=\s*\{\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*1\s*\}", block.group(1)):
        out[name] = (float(r), float(g), float(b))
    assert set(out) == {"Magic", "Curse", "Disease", "Poison"}, out
    return out


def _dispel_colors_lua() -> str:
    parts = ",".join(f"{n}={{{r!r},{g!r},{b!r},1}}" for n, (r, g, b) in _dispel_colors().items())
    return f"FS.Theme.DISPEL_COLORS={{{parts}}}"


def _theme_tokens_lua() -> str:
    return _dispel_colors_lua() + " " + " ".join(
        "FS.Theme.{0}={{{1}}}".format(n, ",".join(repr(v) for v in _theme_color(n)))
        for n in ("COLOR_POWER", "COLOR_STEEL", "COLOR_MUTED", "COLOR_HEAL", "COLOR_TARGET"))


def _const(name: str) -> float:
    """Read a numeric `local NAME = 12` constant from PartyFrames.lua."""
    match = re.search(rf"^local {name}\s*=\s*(-?[\d.]+)", PARTY_SRC, re.M)
    assert match, f"PartyFrames.lua has no numeric local {name}"
    return float(match.group(1))


def _color(name: str) -> tuple[float, float, float]:
    """Read the rgb of a `local NAME = { r, g, b, a }` constant from PartyFrames.lua."""
    match = re.search(
        rf"^local {name}\s*=\s*\{{\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", PARTY_SRC, re.M
    )
    assert match, f"PartyFrames.lua has no color local {name}"
    return tuple(float(v) for v in match.groups())


def _close(actual, expected) -> bool:
    return all(math.isclose(a, e, abs_tol=1e-6) for a, e in zip(actual, expected, strict=True))


def _runtime(
    native_percent: bool = True,
    parent_height: int = 1440,
    c_unitauras: bool = True,
    chrome: str = "cut",
    player_class: str = "PRIEST",
    before_load: str = "",
    quiet: bool = True,
    blizzard_party: str = "full",
) -> LuaRuntime:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.execute(MOCK)
    rt.execute(_theme_tokens_lua())
    rt.execute(f"__playerClass='{player_class}'")
    rt.execute(BLIZZARD_PARTY)
    rt.execute(BLIZZARD_PARTY_MODES[blizzard_party])
    if before_load:
        rt.execute(before_load)
    rt.execute(f"FS.Theme.CHROME_CORNERS='{chrome}'")
    rt.globals().UIParent.SetHeight(rt.globals().UIParent, parent_height)
    if not native_percent:
        rt.execute("UnitHealthPercent=nil")
    if not c_unitauras:
        rt.execute("C_UnitAuras=nil")  # FrameHelpers.ReadAuraSlot then takes the UnitAura path
    load = rt.eval(LOAD)
    for filename in ("Core/Layout.lua", "Core/FrameHelpers.lua", "Modules/UnitFrames/PartyFrames.lua"):
        load((ADDON / filename).read_text(encoding="utf-8"), f"@{filename}", rt.globals().FS)
    if quiet:
        _assert_quiet(rt)
    return rt


def _assert_quiet(rt: LuaRuntime) -> None:
    """Every print and LogDegradeOnce lands in __messages; a latched degrade must fail."""
    messages = list(rt.globals().__messages.values())
    assert not messages, messages


def _fire(row, event: str) -> None:
    row.events.scripts.OnEvent(row.events, event, row.unit)


def _check_layout(rt: LuaRuntime) -> None:
    fs = rt.globals().FS
    panel = fs.partyContainer.GetBounds(fs.partyContainer)
    scale = fs.Layout.Scale()
    panel_h = fs.Layout.party.h
    pad, row_gap = _const("PANEL_PAD"), _const("ROW_GAP")
    rows = int(_const("ROW_COUNT"))
    header, name_gap = _const("NAME_ROW_HEIGHT"), _const("NAME_GAP")
    core_h, pair_gap = _const("RAIL_CORE_HEIGHT"), _const("RAIL_PAIR_GAP")
    assert abs(panel.h - panel_h * scale) < 0.001, f"panel height changed: {panel.h}"
    assert len(fs.partyRows) == rows, f"party must contain {rows} rows"
    row_design_h = (panel_h - 2 * pad - (rows - 1) * row_gap) / rows
    row_height = row_design_h * scale
    for index, row in fs.partyRows.items():
        member = row.GetBounds(row)
        pet = row.petFrame.GetBounds(row.petFrame)
        hp = row.health.shell.GetBounds(row.health.shell)
        power = row.power.shell.GetBounds(row.power.shell)
        name = row.name.parent.GetBounds(row.name.parent)
        expected_y = panel.y + pad * scale + (index - 1) * (row_height + row_gap * scale)
        assert abs(member.y - expected_y) < 0.001, (
            f"row {index} top {member.y}: expected {expected_y}"
        )
        assert abs(member.h - row_height) < 0.001, (
            f"row {index} height {member.h}: expected {row_height}"
        )
        assert abs(pet.h - member.h) < .001 and abs(pet.w - _const("PET_WIDTH") * scale) < .001, (
            f"row {index} pet bounds differ"
        )
        assert member.x >= panel.x + pad * scale - .001 and member.right <= pet.x + .001, (
            "member/pet overlap"
        )
        assert pet.right <= panel.right - pad * scale + .001, "pet escapes panel padding"
        assert member.bottom <= panel.bottom - pad * scale + 0.001, (
            "member escapes panel padding"
        )
        assert abs(name.h - header * scale) < .001 and abs(name.y - member.y) < .001, (
            "header must be compact and at row top"
        )
        # The rail shells are exactly their cores. The HP/mana pair is centered in the
        # space under the name row (below NAME_GAP) down to the row bottom, with the
        # cores' facing edges RAIL_PAIR_GAP apart.
        assert abs(hp.h - core_h * scale) < .001, f"health shell height {hp.h}"
        assert abs(power.h - core_h * scale) < .001, f"power shell height {power.h}"
        assert abs(power.y - hp.bottom - pair_gap * scale) < .001, (
            f"core edge gap {power.y - hp.bottom}: expected {pair_gap * scale}"
        )
        space_top = name.bottom + name_gap * scale
        assert hp.y >= space_top - .001 and power.bottom <= member.bottom + .001, (
            "rail pair escapes the space under the name row"
        )
        assert abs((hp.y - space_top) - (member.bottom - power.bottom)) < .001, (
            "rail pair not vertically centered under the name row"
        )
        assert hp.right <= pet.x + .001 and power.right <= pet.x + .001, "bars overlap pet"
        assert abs(hp.x - name.x) < .001 and abs(hp.right - name.right) < .001, (
            "health shell must span the header width (the row's inner width)"
        )
        assert abs(power.x - hp.x) < .001 and abs(power.right - hp.right) < .001, (
            "bar widths differ"
        )
        # Each core fills its shell, and the HP text is centered on the HP core.
        for bar, shell in ((row.health, hp), (row.power, power)):
            core = bar.GetBounds(bar)
            assert abs(core.h - core_h * scale) < .001, (
                f"rail core height {core.h}: expected {core_h}"
            )
            assert abs(core.y - shell.y) < .001, "core not aligned to its shell"
            assert abs(core.x - shell.x) < .001 and abs(core.right - shell.right) < .001, (
                "core must span its shell"
            )
        core = row.health.GetBounds(row.health)
        text = row.health.text.GetBounds(row.health.text)
        assert abs((text.x + text.w / 2) - (core.x + core.w / 2)) < .001, (
            "HP text not horizontally centered on the HP core"
        )
        assert abs((text.y + text.h / 2) - (core.y + core.h / 2)) < .001, (
            "HP text not vertically centered on the HP core"
        )


def _check_late_rescale() -> None:
    rt = _runtime(parent_height=768)
    _check_layout(rt)
    rt.globals().UIParent.SetHeight(rt.globals().UIParent, 1200)
    rt.execute("""
        for _,frame in ipairs(__frames) do
            if frame.registered.PLAYER_LOGIN then
                frame.scripts.OnEvent(frame,'PLAYER_LOGIN')
            end
        end
    """)
    _check_layout(rt)
    _assert_quiet(rt)


def _check_full_name() -> None:
    rt = _runtime()
    row = rt.globals().FS.partyRows[1]
    _fire(row, "UNIT_NAME_UPDATE")
    assert row.name.text == "FIRST SURNAME", f"full name lost: {row.name.text!r}"


def _check_class_icon() -> None:
    """The class atlas icon sits on a 16 square cut plate (chamfer 3, dark fill, cyan stroke at
    .85, no class-colour stroke), inset 2 so its square corners clear the chamfer."""
    rt = _runtime()
    row = rt.globals().FS.partyRows[1]
    plate = row.classPlate
    icons = [region for region in plate.regions.values()
             if region.texture == "Interface\\WorldStateFrame\\Icons-Classes"]
    assert len(icons) == 1, f"expected one class atlas icon, found {len(icons)}"
    icon = icons[0]
    assert icon.shown, "class icon hidden when role is NONE"
    assert list(icon.texcoords.values()) == [.5, .75, .25, .5], "incorrect class atlas crop"
    assert (plate.w, plate.h) == (16, 16), f"plate size {plate.w}x{plate.h}"
    assert plate.roundedRadius == 3 and plate.skinOpts.chamfer == 3, "plate chamfer must be 3"
    assert _close(_rgba(plate.roundedColor), (.024, .012, .071, .85 * .9)), "plate fill"
    cyan = _theme_color("COLOR_POWER")[:3]
    assert _close(_rgba(plate.fsSkin.border.ring.color), (*cyan, .85)), "stroke is cyan at .85"
    bounds, tile = icon.GetBounds(icon), plate.GetBounds(plate)
    scale = rt.globals().FS.Layout.Scale()
    assert abs(bounds.x - tile.x - 2 * scale) < .001 and abs(tile.right - bounds.right - 2 * scale) < .001, (
        "icon must be inset 2 from the plate's left and right")
    header, name = row.name.parent.GetBounds(row.name.parent), row.name.GetBounds(row.name)
    assert abs(tile.x - header.x) < .001 and tile.right <= name.x, "plate at the header's left, clear of the name"
    assert tile.y >= header.y and tile.bottom <= header.bottom, "class plate escapes compact header"


def _health_textures(row):
    """The health rail's textures that carry its color and desaturation."""
    rail = row.health.fsRail
    return {
        "core fill": row.health.GetStatusBarTexture(row.health),
        "spark": rail.spark,
        "bloom top": rail.bloomTop,
        "bloom bottom": rail.bloomBottom,
    }


def _assert_rail_color(row, expected, label: str) -> None:
    """What the textures actually received: the core fill's tip color and the spark's tint."""
    tip = _health_textures(row)["core fill"].gradient.max
    spark = row.health.fsRail.spark.color
    assert _close((tip.r, tip.g, tip.b), expected), f"{label}: core fill tip {tip.r, tip.g, tip.b}"
    assert _close((spark[1], spark[2], spark[3]), expected), (
        f"{label}: spark tint {spark[1], spark[2], spark[3]}"
    )


def _assert_desaturated(row, expected: bool, label: str) -> None:
    for name, texture in _health_textures(row).items():
        assert bool(texture.desaturated) == expected, (
            f"{label}: {name} desaturated={texture.desaturated}, expected {expected}"
        )


def _class_rgb(rt: LuaRuntime) -> tuple[float, float, float]:
    color = rt.globals().RAID_CLASS_COLORS.PRIEST
    return color.r, color.g, color.b


def _check_paladin_first_login() -> None:
    """First login as a Paladin (no harness had booted as one): the rows build, every unit
    resolves PALADIN, the rail and name take the class colour from RAID_CLASS_COLORS, and a
    class with no party buff entry raises no alert and no degrade message, even with a
    resolvable known buff spell and every unit missing its aura (so a Paladin entry in
    PARTY_BUFFS would show a tile)."""
    rt = _runtime(
        player_class="PALADIN",
        before_load=(
            "function UnitClass() return 'Paladin','PALADIN' end "
            "RAID_CLASS_COLORS.PALADIN={r=.96,g=.55,b=.73} "
            "CLASS_ICON_TCOORDS.PALADIN={0,.25,.5,.75} "
            "__spellIds={['Blessing of Kings']=5001} __knownIds={[5001]=true}"
        ),
    )
    g = rt.globals()
    rows = int(_const("ROW_COUNT"))
    assert len(g.FS.partyRows) == rows, f"party must contain {rows} rows"
    want = (.96, .55, .73)
    for index, row in g.FS.partyRows.items():
        _fire(row, "UNIT_HEALTH")
        _fire(row, "UNIT_NAME_UPDATE")
        _fire(row, "UNIT_AURA")
        _assert_rail_color(row, want, f"paladin row {index}")
        assert _close(_rgba(row.name.textColor)[:3], want), f"row {index} name colour"
        assert _tiles(row) == [], f"row {index}: a paladin has no party buff alert"
        classIcons = [r for r in row.classPlate.regions.values()
                      if r.texture == "Interface\\WorldStateFrame\\Icons-Classes"]
        assert len(classIcons) == 1 and classIcons[0].shown, f"row {index} class icon"
        assert list(classIcons[0].texcoords.values()) == [0, .25, .5, .75], (
            f"row {index}: the class icon crops CLASS_ICON_TCOORDS.PALADIN")
    _assert_quiet(rt)


def _check_dead_then_live_rail() -> None:
    rt = _runtime()
    globals_ = rt.globals()
    row = globals_.FS.partyRows[1]
    class_rgb = _class_rgb(rt)
    rail = row.health.fsRail

    # Live: the class color on the textures, through a horizontal tail-to-tip alpha gradient.
    _assert_rail_color(row, class_rgb, "live")
    gradient = _health_textures(row)["core fill"].gradient
    assert gradient.orientation == "HORIZONTAL", "core fill gradient must run tail to tip"
    assert math.isclose(gradient.min.a, _const("RAIL_TAIL_ALPHA"), abs_tol=1e-6), "tail alpha"
    assert math.isclose(gradient.max.a, 1, abs_tol=1e-6), "tip alpha"

    globals_.__state = "dead"
    _fire(row, "UNIT_HEALTH")
    _assert_rail_color(row, _color("STATE_BAR_COLOR"), "dead")
    _assert_desaturated(row, True, "dead")

    globals_.__state = "live"
    _fire(row, "UNIT_HEALTH")
    _assert_rail_color(row, class_rgb, "restored")
    _assert_desaturated(row, False, "restored")
    assert rail.host.shown, "glow host not restored"
    assert row.health.shell.alpha == 1, "live shell alpha not restored"
    _assert_quiet(rt)


def _assert_halo(halo, rgb, alpha: float) -> None:
    """Both outer ends fade to 0 and meet at `alpha` in the center, in the dispel color."""
    for side, expected in {"left": (0, alpha), "right": (alpha, 0)}.items():
        strips = list(getattr(halo, side).values())
        assert len(strips) == 2, f"halo {side} must have a strip above and below"
        for strip in strips:
            low, high = strip.gradient.min, strip.gradient.max
            assert math.isclose(low.a, expected[0], abs_tol=1e-6), f"halo {side} start alpha"
            assert math.isclose(high.a, expected[1], abs_tol=1e-6), f"halo {side} end alpha"
            assert _close((low.r, low.g, low.b), rgb), f"halo {side} tint {low.r, low.g, low.b}"
            assert _close((high.r, high.g, high.b), rgb), "halo gradient ends differ in color"


def _same(rt: LuaRuntime, a, b) -> bool:
    """Lua identity: lupa hands back a fresh wrapper per access, so Python `==` is always False."""
    return rt.eval("function(a, b) return a == b end")(a, b)


def _assert_halo_offset(rt: LuaRuntime, row) -> None:
    """The halo wraps the HP + mana pair, starting just outside the bloom at each end.

    The top strips sit above the HP core and the bottom strips below the mana core, both offset
    by the bloom size. Every strip pins to a core bar itself, never the fill, so the halo reads
    at any HP, and none may overlap either core.
    """
    rail = row.health.fsRail
    halo = rail.halo
    offset = _const("RAIL_BLOOM_SIZE")
    assert math.isclose(rail.bloomTop.h, offset), f"bloom top height {rail.bloomTop.h}"
    assert math.isclose(halo.left[1].h, _const("RAIL_HALO_SIZE")), "halo strip height"

    # Vertical overlap: bounds are top-down (y is the top edge, bottom = y + h).
    cores = {"HP": row.health.GetBounds(row.health), "mana": row.power.GetBounds(row.power)}
    for side in (halo.left, halo.right):
        for strip in side.values():
            box = strip.GetBounds(strip)
            for name, core in cores.items():
                overlap = min(box.bottom, core.bottom) - max(box.y, core.y)
                assert overlap <= 1e-6, (
                    f"halo strip [{box.y}, {box.bottom}] overlaps the {name} core "
                    f"[{core.y}, {core.bottom}] by {overlap}"
                )
    above, below = halo.left[1], halo.left[2]
    assert above.GetBounds(above).bottom <= cores["HP"].y + 1e-6, "top strip must sit above HP"
    assert below.GetBounds(below).y >= cores["mana"].bottom - 1e-6, "bottom strip below mana"

    top, bottom = halo.left[1].points.BOTTOMLEFT, halo.left[2].points.TOPLEFT
    assert math.isclose(top.y, offset), f"halo top offset {top.y}, expected {offset}"
    assert math.isclose(bottom.y, -offset), f"halo bottom offset {bottom.y}, expected {-offset}"
    for side in (halo.left, halo.right):
        for index, bar in ((1, row.health), (2, row.power)):
            for point in side[index].points.values():
                assert _same(rt, point.rel, bar), (
                    f"halo strip {index} must anchor to the {'HP' if index == 1 else 'mana'} core"
                )

    # One host spanning the whole pair.
    assert _same(rt, halo.host.parent, row.health.shell), (
        "halo host must be a child of the health shell (dead/offline dimming)"
    )
    host = halo.host.GetBounds(halo.host)
    assert math.isclose(host.y, cores["HP"].y), "halo host must start at the HP core top"
    assert math.isclose(host.bottom, cores["mana"].bottom), "halo host must end at the mana core"


def _check_rail_parity() -> None:
    """The health rail is the power recipe: same spark, bloom and flat fill, text above the glow."""
    rt = _runtime()
    fs = rt.globals().FS
    scale = fs.Layout.Scale()
    spark_size, bloom_size = _const("RAIL_SPARK_SIZE"), _const("RAIL_BLOOM_SIZE")
    flat = fs.Theme.FLAT_TEXTURE
    for index, row in fs.partyRows.items():
        for name, bar in (("health", row.health), ("power", row.power)):
            rail = bar.fsRail
            label = f"row {index} {name}"
            spark = rail.spark.GetBounds(rail.spark)
            assert math.isclose(spark.w, spark_size * scale), f"{label} spark width {spark.w}"
            assert math.isclose(spark.h, spark_size * scale), f"{label} spark height {spark.h}"
            for edge in (rail.bloomTop, rail.bloomBottom):
                assert math.isclose(edge.h, bloom_size), f"{label} bloom height {edge.h}"
            fill = bar.GetStatusBarTexture(bar)
            assert fill.texture == flat, f"{label} fill texture {fill.texture!r}, expected flat"
        # Text draws over the glow host, which draws over the core bar.
        health = row.health
        text_level = health.text.parent.GetFrameLevel(health.text.parent)
        host_level = health.fsRail.host.GetFrameLevel(health.fsRail.host)
        assert text_level > host_level > health.GetFrameLevel(health), (
            f"frame levels text {text_level}, glow {host_level}, "
            f"bar {health.GetFrameLevel(health)}"
        )


def _check_health_overlays() -> None:
    """Heal and absorb overlays sit on the HP rail only, chained fill -> heal -> absorb, and are
    fed the raw (secret) max and amounts with no Lua arithmetic."""
    rt = _runtime()
    globals_ = rt.globals()
    fs = globals_.FS
    for index, row in fs.partyRows.items():
        health, heal, absorb = row.health, row.health.healOverlay, row.health.absorbOverlay
        assert heal and absorb, f"row {index} HP rail missing an overlay"
        assert not row.power.healOverlay and not row.power.absorbOverlay, "mana rail has overlays"
        fill, heal_fill = health.GetStatusBarTexture(health), heal.GetStatusBarTexture(heal)
        assert _same(rt, heal.points.LEFT.rel, fill) and heal.points.LEFT.rp == "RIGHT", (
            "heal must start at the HP fill's right edge"
        )
        assert _same(rt, absorb.points.LEFT.rel, heal_fill) and absorb.points.LEFT.rp == "RIGHT", (
            "absorb must start at the heal fill's right edge"
        )
        level = health.GetFrameLevel(health)
        assert level < heal.GetFrameLevel(heal) < health.fsRail.host.GetFrameLevel(
            health.fsRail.host), "overlays must sit between the core bar and the glow host"
        for overlay in (heal, absorb):  # the right edge and both rows ride the HP bar itself
            for side in ("RIGHT", "TOP", "BOTTOM"):
                assert _same(rt, overlay.points[side].rel, health), f"overlay {side} not on HP bar"
        for event in ("UNIT_HEAL_PREDICTION", "UNIT_ABSORB_AMOUNT_CHANGED"):
            assert row.events.registered[event], f"row {index} must register {event}"

    row = fs.partyRows[2]
    same = rt.eval("function(a, b) return a == b end")
    globals_.__health = globals_.__max = globals_.__incoming = globals_.__absorb = globals_.__secret
    _fire(row, "UNIT_HEAL_PREDICTION")
    for overlay in (row.health.healOverlay, row.health.absorbOverlay):
        assert same(overlay.max, globals_.__secret), "secret max must pass straight through"
        assert same(overlay.value, globals_.__secret), "secret amount must pass straight through"
    assert not row.health.healOverlay.glow.shown, "glow must stay hidden for a secret amount"

    globals_.__health = globals_.__max = 100
    globals_.__incoming, globals_.__absorb = 25, 10
    _fire(row, "UNIT_ABSORB_AMOUNT_CHANGED")
    assert row.health.healOverlay.value == 25 and row.health.absorbOverlay.value == 10
    assert row.health.healOverlay.max == 100 and row.health.healOverlay.glow.shown

    globals_.__state = "dead"
    _fire(row, "UNIT_HEAL_PREDICTION")
    assert row.health.healOverlay.value == 0 and row.health.absorbOverlay.value == 0, (
        "dead row must zero its overlays"
    )
    assert not row.health.healOverlay.glow.shown, "dead row must hide the heal glow"

    # The full-row health path (UNIT_HEALTH), not just the prediction path.
    def values():
        heal, absorb = row.health.healOverlay, row.health.absorbOverlay
        return heal.value, absorb.value, heal.glow.shown

    globals_.__state, globals_.__incoming, globals_.__absorb = "live", 30, 12
    _fire(row, "UNIT_HEALTH")
    assert values() == (30, 12, True), f"live health path must pass amounts through: {values()}"
    globals_.__incoming = globals_.__absorb = 0
    _fire(row, "UNIT_HEALTH")
    assert values() == (0, 0, False), f"zero amounts must show nothing: {values()}"
    for state in ("dead", "offline"):
        globals_.__state, globals_.__incoming, globals_.__absorb = "live", 30, 12
        _fire(row, "UNIT_HEALTH")
        globals_.__state = state
        _fire(row, "UNIT_HEALTH")
        assert values() == (0, 0, False), f"{state} health path must zero overlays: {values()}"
    _assert_quiet(rt)


def _check_dispel_halo(c_unitauras: bool) -> None:
    rt = _runtime(c_unitauras=c_unitauras)
    globals_ = rt.globals()
    row = globals_.FS.partyRows[1]
    halo = row.health.fsRail.halo
    set_debuffs = rt.eval("function(...) __debuffs={...} end")
    alpha = _const("RAIL_HALO_ALPHA")
    colors = _dispel_colors()
    assert not halo.host.shown, "dispel halo must start hidden"
    _assert_halo_offset(rt, row)

    # Curse is first but a Priest cannot dispel it; Disease is the first cleansable, so its
    # color must win over both the first harmful aura and the later Magic.
    set_debuffs("Curse", "Disease", "Magic")
    _fire(row, "UNIT_AURA")
    assert halo.host.shown, "cleansable debuff must show the halo"
    _assert_halo(halo, colors['Disease'], alpha)

    set_debuffs("Curse")
    _fire(row, "UNIT_AURA")
    assert not halo.host.shown, "uncleansable debuff must not show the halo"

    set_debuffs("Magic")
    _fire(row, "UNIT_AURA")
    assert halo.host.shown, "halo must come back for a new cleansable debuff"
    _assert_halo(halo, colors['Magic'], alpha)

    set_debuffs()
    _fire(row, "UNIT_AURA")
    assert not halo.host.shown, "halo must hide once nothing is cleansable"
    _assert_quiet(rt)


ALL_RAID = "__raid={Magic=true,Disease=true,Poison=true,Curse=true}"
PURIFY, CLEANSE, DISPEL_MAGIC, DISPEL_MAGIC_2, CURE_DISEASE = 1152, 4987, 527, 988, 528
SPELLBOOK_DISPEL_EVENTS = ("SPELLS_CHANGED", "LEARNED_SPELL_IN_TAB", "PLAYER_LEVEL_UP")


def _dispel_rt(player_class: str, known, extra: str = "") -> LuaRuntime:
    """A runtime for `player_class` whose spellbook knows exactly the ids in `known`, with a RAID
    pre-filter that keeps every type (the class check is the authority, not the filter)."""
    ids = ",".join(f"[{i}]=true" for i in known)
    return _runtime(player_class=player_class,
                    before_load=f"{ALL_RAID} __dispelKnown={{{ids}}} {extra}")


def _lit(rt, *types: str) -> set:
    """Which of `types` light the player row's dispel halo, one debuff of that type at a time."""
    row = rt.globals().FS.partyRows[1]
    halo = row.health.fsRail.halo
    lit = set()
    for dispel_type in types:
        rt.execute(f"__debuffs={{'{dispel_type}'}}")
        _fire(row, "UNIT_AURA")
        if halo.host.shown:
            lit.add(dispel_type)
    return lit


def _spell_event(rt, event: str) -> None:
    frame = rt.globals().FS.partySpellEvents
    assert frame.registered[event], f"nothing registered for {event}"
    frame.scripts.OnEvent(frame, event)


def _assert_describes(rt, player_class: str, dispels: str) -> None:
    """The /fsparty report names the class and the dispel types it can remove."""
    g = rt.globals()
    rt.execute("__messages={}")
    g.SlashCmdList.FSPARTY("")
    text = "\n".join(str(m) for m in g.__messages.values())
    assert f"class {player_class} dispels {dispels}" in text, f"/fsparty dispel line:\n{text}"


def _check_dispel_paladin_purify() -> None:
    rt = _dispel_rt("PALADIN", (PURIFY,))
    assert _lit(rt, "Poison", "Disease", "Magic", "Curse") == {"Poison", "Disease"}, (
        "a level 10 Paladin with Purify removes Poison and Disease, not Magic")
    _assert_quiet(rt)
    _assert_describes(rt, "PALADIN", "Disease/Poison")


def _check_dispel_paladin_cleanse() -> None:
    for known in ((PURIFY, CLEANSE), (CLEANSE,)):
        rt = _dispel_rt("PALADIN", known)
        assert _lit(rt, "Poison", "Disease", "Magic", "Curse") == {"Poison", "Disease", "Magic"}, (
            f"Cleanse adds Magic ({known})")
        _assert_quiet(rt)
    rt = _dispel_rt("PALADIN", ())
    assert _lit(rt, "Poison", "Disease", "Magic") == set(), "a Paladin who knows neither: nothing"
    _assert_quiet(rt)


def _check_dispel_priest_gated() -> None:
    rt = _dispel_rt("PRIEST", (CURE_DISEASE,))
    assert _lit(rt, "Magic", "Disease", "Poison", "Curse") == {"Disease"}, (
        "a Priest without Dispel Magic has no Magic")
    for known in ((DISPEL_MAGIC,), (DISPEL_MAGIC_2,)):
        rt = _dispel_rt("PRIEST", known)
        assert _lit(rt, "Magic", "Disease") == {"Magic"}, f"any Dispel Magic rank gives Magic {known}"
    rt = _dispel_rt("PRIEST", (DISPEL_MAGIC, 552))
    assert _lit(rt, "Magic", "Disease") == {"Magic", "Disease"}, "Abolish Disease gives Disease"
    _assert_quiet(rt)


def _check_dispel_other_classes() -> None:
    cases = (
        ("DRUID", (2782,), {"Curse"}), ("DRUID", (8946,), {"Poison"}),
        ("DRUID", (2893,), {"Poison"}), ("DRUID", (2782, 2893), {"Curse", "Poison"}),
        ("MAGE", (475,), {"Curse"}), ("MAGE", (), set()),
        ("SHAMAN", (526,), {"Poison"}), ("SHAMAN", (2870,), {"Disease"}),
        ("SHAMAN", (526, 2870), {"Poison", "Disease"}),
    )
    for player_class, known, want in cases:
        rt = _dispel_rt(player_class, known)
        got = _lit(rt, "Magic", "Disease", "Poison", "Curse")
        assert got == want, f"{player_class} knowing {known}: lit {got}, want {want}"
        _assert_quiet(rt)


def _check_dispel_recomputed_on_spellbook_events() -> None:
    rt = _dispel_rt("PALADIN", (PURIFY,))
    assert _lit(rt, "Magic") == set()
    rt.execute(f"__dispelKnown[{CLEANSE}]=true")
    assert _lit(rt, "Magic") == set(), "the known set is cached between spellbook events"
    _spell_event(rt, "SPELLS_CHANGED")
    assert _lit(rt, "Magic") == {"Magic"}, "SPELLS_CHANGED must recompute the dispel set"
    rt.execute("__dispelKnown={}")
    _spell_event(rt, "SPELLS_CHANGED")
    assert _lit(rt, "Magic", "Poison") == set(), "forgotten spells stop lighting"
    for event in SPELLBOOK_DISPEL_EVENTS:
        assert rt.globals().FS.partySpellEvents.registered[event], f"{event} must be registered"
    _assert_quiet(rt)


def _check_dispel_no_dispel_class() -> None:
    rt = _dispel_rt("WARLOCK", (PURIFY, CLEANSE, DISPEL_MAGIC))
    assert _lit(rt, "Magic", "Disease", "Poison", "Curse") == set(), "no dispels, nothing lit"
    _assert_quiet(rt)
    _assert_describes(rt, "WARLOCK", "nothing")


def _check_dispel_throwing_spell_api() -> None:
    # IsPlayerSpell raises but another spellbook API answers: the answer still counts.
    # Cleanse is readably unknown through the API that works, so Magic must stay dark: a
    # readable "no" beats an API that raised.
    rt = _dispel_rt("PALADIN", (PURIFY,), extra="function IsPlayerSpell() error('boom') end")
    assert _lit(rt, "Poison", "Disease", "Magic", "Curse") == {"Poison", "Disease"}, (
        "one throwing API must not hide the others, nor turn a readable no into a yes")
    _assert_quiet(rt)
    # Every API raises (or answers secret): fall back to the class's full set rather than
    # raising or lighting nothing, and ask again later instead of caching the unreadable answer.
    throw = ("function IsPlayerSpell() error('boom') end "
             "C_SpellBook.IsSpellKnown=function() if __mode=='secret' then return __secret end "
             "error('boom') end __mode='error'")
    for mode in ("error", "secret"):
        rt = _dispel_rt("PALADIN", (), extra=throw)
        rt.globals().__mode = mode
        assert _lit(rt, "Poison", "Disease", "Magic", "Curse") == {"Poison", "Disease", "Magic"}, (
            f"unreadable spellbook ({mode}) falls back to the class's full set")
        rt.execute("C_SpellBook.IsSpellKnown=function(id) return id==1152 end "
                   "function IsPlayerSpell() return false end")
        assert _lit(rt, "Poison", "Magic") == {"Poison"}, "an unreadable answer is not cached"
        _assert_quiet(rt)


def _check_dispel_name_fallback() -> None:
    # Rank ids the table lacks: the spell resolves by name to an id the spellbook does know.
    rt = _dispel_rt("PALADIN", (9999,), extra="__spellIds={['Purify']=9999}")
    assert _lit(rt, "Poison", "Disease", "Magic") == {"Poison", "Disease"}, (
        "a known spell found by name counts for the types it removes")
    _assert_quiet(rt)


def _check_dispel_class_read_lazily_and_cached() -> None:
    """The class is read when the set is first needed, and the set is cached with it: a class
    change shows up only after a spellbook event drops the cache."""
    rt = _dispel_rt("PALADIN", (PURIFY, 2782))
    g = rt.globals()
    assert _lit(rt, "Poison", "Curse") == {"Poison"}
    g.__playerClass = "DRUID"
    assert _lit(rt, "Poison", "Curse") == {"Poison"}, "scans reuse the cached set"
    _spell_event(rt, "SPELLS_CHANGED")
    assert _lit(rt, "Poison", "Curse") == {"Curse"}, "the event recomputes for the current class"
    _assert_quiet(rt)


def _check_readout(native: bool, health: int, maximum: int, fraction: float,
                   state: str, expected: str, secret: bool = False) -> None:
    rt = _runtime(native)
    globals_ = rt.globals()
    globals_.__health = globals_.__secret if secret else health
    globals_.__max = globals_.__secret if secret else maximum
    globals_.__fraction, globals_.__state = fraction, state
    row = globals_.FS.partyRows[1]
    _fire(row, "UNIT_HEALTH")
    _assert_quiet(rt)
    assert row.health.text.text == expected, (
        f"readout {row.health.text.text!r}: expected {expected!r}"
    )
    assert row.health.text.shown, "health readout hidden"
    live = state == "live"
    expected_alpha = 1 if live else _const("STATE_ROW_ALPHA")
    assert math.isclose(row.health.shell.alpha, expected_alpha), "health state tint lost"
    assert row.health.fsRail.host.shown == live, (
        "glow host (spark, bloom) must hide while dead/offline"
    )
    _assert_desaturated(row, not live, state)
    if not live:
        assert row.health.value == 0, "dead/offline fill must be empty"


# Theme.CutSize(h) for the heights these checks build: h / 3 clamped to 2..6 and <= h / 2,
# snapped to {2, 3, 4, 6}. Hard-coded on purpose so the stub in MOCK cannot agree with
# the code by construction.
CUT_SIZE = {4: 2, 8: 2, 16: 4, 24: 6}
CUT_ICON_SIZE = {22: 4}


def _check_shared_pill_bar(chrome: str = "cut") -> None:
    """FrameHelpers.CreatePillBar is shared with UnitFrames/PetFrame; party rows do not use it."""
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.execute(MOCK)
    rt.execute(f"FS.Theme.CHROME_CORNERS='{chrome}'")
    # Count the leading-edge quad builds: under cut the fill must get none (a quad riding the
    # fill's moving right edge carves a travelling bottom-right notch into the fill and the
    # caret; playtest 2026-10-04), under round it keeps them.
    rt.execute(
        "leadingBuilds = 0\n"
        "local real = FS.Theme.AddLeadingEdgeCorners\n"
        "FS.Theme.AddLeadingEdgeCorners = function(...)\n"
        "    leadingBuilds = leadingBuilds + 1\n"
        "    return real(...)\n"
        "end"
    )
    rt.eval(LOAD)(
        (ADDON / "Core/FrameHelpers.lua").read_text(encoding="utf-8"),
        "@FrameHelpers.lua",
        rt.globals().FS,
    )
    FS = rt.globals().FS
    build = rt.eval("""
        function(height, inset)
            return FS.FrameHelpers.CreatePillBar(UIParent, {
                height=height, fillInset=inset,
                fillColor=FS.Theme.COLOR_POWER,
                styleText=function() end,
            })
        end
    """)

    def assert_pill(bar, height: float, inset: float) -> None:
        chrome_host = bar.fsChromeHost
        if chrome == "round":
            # The chrome (track, border, glow) is a true pill on the child host: radius = h / 2.
            assert chrome_host.roundedRadius == height / 2, (
                f"track radius {chrome_host.roundedRadius}"
            )
            assert chrome_host.borderRadius == height / 2, (
                f"border radius {chrome_host.borderRadius}"
            )
            assert chrome_host.glowRadius == height / 2, f"glow radius {chrome_host.glowRadius}"
            assert bar.fsLeadingCorners is not None, "round keeps the leading-edge quads"
            for handle in (bar.fsFillCorners, bar.fsLeadingCorners):
                assert handle.radius == height / 2 - inset, (
                    f"fill corner radius {handle.radius}: expected {height / 2 - inset}"
                )
            assert bar.fsBorderHost is None, "round keeps the border on the chrome host"
            return
        # Cut: track, border, glow AND both fill masks use the one chamfer Theme.CutSize(h).
        chamfer = CUT_SIZE[int(height)]
        assert chrome_host.roundedRadius == chamfer, f"track chamfer {chrome_host.roundedRadius}"
        assert chrome_host.glowRadius == chamfer, f"glow chamfer {chrome_host.glowRadius}"
        border_host = bar.fsBorderHost
        assert border_host is not None, "cut needs a separate border host above the corner mask"
        assert border_host.borderRadius == chamfer, f"border chamfer {border_host.borderRadius}"
        assert chrome_host.borderRadius is None, "cut border must not sit on the track host"
        assert bar.fsFillCorners.radius == chamfer, (
            f"fill mask chamfer {bar.fsFillCorners.radius}: want {chamfer}"
        )
        # Cut has NO leading-edge quad: the fill's right end stays square mid-bar.
        assert bar.fsLeadingCorners is None, "cut must not build a leading-edge erase quad"
        # R2: the erase quads would overpaint the diagonal stroke, so the border draws on a
        # frame ABOVE the corner mask (and above the fill bar), the track fill stays below.
        mask_level = bar.cornerMask.GetFrameLevel(bar.cornerMask)
        border_level = border_host.GetFrameLevel(border_host)
        assert border_level > mask_level, (
            f"border level {border_level} must be above the erase layer {mask_level}"
        )
        assert chrome_host.GetFrameLevel(chrome_host) < bar.GetFrameLevel(bar), (
            "track fill must stay below the fill bar"
        )
        # Full stack, creation-order independent: track < bar < heal/absorb overlay (bar + 1)
        # < caret host (bar + 2) < mask < border < text host. The text host must sit strictly
        # above the border, not tie with it.
        caret = FS.FrameHelpers.CreateCaret(bar, FS.Theme.COLOR_POWER)
        caret_level = caret.host.GetFrameLevel(caret.host)
        text_level = bar.text.parent.GetFrameLevel(bar.text.parent)
        bar_level = bar.GetFrameLevel(bar)
        assert border_level > caret_level > bar_level + 1, (
            f"border {border_level} must clear the caret host {caret_level} and overlays"
        )
        assert border_level > bar_level + 1, "border must clear the heal/absorb overlay level"
        assert border_level <= text_level - 1, (
            f"border level {border_level} must be strictly below the text host {text_level}"
        )

    short = build(4, 1)  # a 4px bar must not get corners that overlap
    tall = build(24, 2)
    assert_pill(short, 4, 1)
    assert_pill(tall, 24, 2)

    old_chrome, old_border = short.fsChromeHost, short.fsBorderHost
    short.SetPillHeight(short, 8, 1)
    assert not old_chrome.shown, "old chrome host must be hidden after a height change"
    if chrome == "cut":
        assert not old_border.shown, "old border host must be hidden after a height change"
    assert short.shell.h == 8, "shell height not applied"
    assert_pill(short, 8, 1)
    sixteen = build(16, 1)  # the unit-frame health and power bar height
    assert_pill(sixteen, 16, 1)
    builds = int(rt.globals().leadingBuilds)
    if chrome == "cut":
        assert builds == 0, f"cut built {builds} leading-edge quad sets: want 0"
    else:
        assert builds == 3, f"round built {builds} leading-edge quad sets: want one per bar built (3)"


def _check_shared_pill_bar_round() -> None:
    _check_shared_pill_bar("round")


def _check_level_chip(chrome: str) -> None:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.execute(MOCK)
    rt.execute(f"FS.Theme.CHROME_CORNERS='{chrome}'")
    rt.eval(LOAD)(
        (ADDON / "Core/FrameHelpers.lua").read_text(encoding="utf-8"),
        "@FrameHelpers.lua",
        rt.globals().FS,
    )
    chip = rt.eval(
        "function(w,h) return FS.FrameHelpers.CreateLevelChip(UIParent,{width=w,height=h}) end"
    )
    for height in (14, 16):
        c = chip(26, height)
        want = 4 if chrome == "cut" else 2  # CutSize(14) = CutSize(16) = 4; mock LEVEL_RADIUS 2
        assert c.glowRadius == want, f"chip {height} glow {c.glowRadius}: want {want}"
        assert c.roundedRadius == want, f"chip {height} fill {c.roundedRadius}: want {want}"
        assert c.borderRadius == want, f"chip {height} border {c.borderRadius}: want {want}"


def _row_pet(chrome: str):
    rt = _runtime(chrome=chrome)
    row = rt.globals().FS.partyRows[1]
    return rt, row


def _check_pet_slot(chrome: str) -> None:
    """The pet column is a box from 17 below the row top to the row bottom (chamfer 4), the health
    fill inset 1 inside it above its fill, a dashed steel placeholder on the same box."""
    rt, row = _row_pet(chrome)
    scale = rt.globals().FS.Layout.Scale()
    pet = row.petFrame
    chamfer = int(_const("PET_CHAMFER"))
    assert chamfer == 4, "PET_CHAMFER is the pet box chamfer (4)"
    member, box = pet.GetBounds(pet), pet.box
    b = box.GetBounds(box)
    assert abs(b.x - member.x) < .001 and abs(b.w - member.w) < .001, "pet box spans the column"
    assert abs(b.y - (member.y + BOX_TOP * scale)) < .001, f"pet box top {b.y}"
    assert abs(b.bottom - member.bottom) < .001, "pet box runs to the slot bottom"
    # The fill, the ring (SkinButton, nine-sliced over this rect) and the erase scale together only
    # if the fill is a nine-slice of the same rect too: under cut one AddCutSliceFill at the box
    # chamfer in PET_FILL, no flat rects and triangles; round keeps AddRoundedFill.
    if chrome == "cut":
        assert box.roundedRadius is None, "cut must not also draw the unit-sized fill"
        assert box.sliceFill is not None, "cut draws the box fill as a nine-slice"
        assert box.sliceFill.radius == chamfer, f"pet box chamfer {box.sliceFill.radius}"
        assert _close(_rgba(box.sliceFill.color), PET_FILL), f"pet box fill {_rgba(box.sliceFill.color)}"
    else:
        assert box.sliceFill is None, "round keeps the old fill"
        assert box.roundedRadius == chamfer, f"pet box chamfer {box.roundedRadius}"
        assert _close(_rgba(box.roundedColor), PET_FILL), f"pet box fill {_rgba(box.roundedColor)}"
    assert math.isclose(pet.health.color[4], PET_PINK_ALPHA), f"pet pink alpha {pet.health.color[4]}"
    # The pink fill is inset 1 inside the box and draws above the box fill.
    inset = int(_const("PET_FILL_INSET"))
    tl, br = pet.health.points.TOPLEFT, pet.health.points.BOTTOMRIGHT
    assert _same(rt, tl.rel, box) and _same(rt, br.rel, box), "fill must anchor to the box"
    assert (tl.x, tl.y, br.x, br.y) == (inset, -inset, -inset, inset), "fill inset 1 in the box"
    assert _level(pet.health) > _level(box)
    # The pink fill's corners. Under cut the edge ring is a NINE-SLICE (SkinButton at chamfer 4), so
    # the erase is one too: Theme.AddCutFillErase over the BOX rect (the rect the ring is sliced
    # over, `pet.edge` is SetAllPoints(box)) at the ring's chamfer, on a clipping host that covers
    # the fill, in the box's own fill colour (opaque). The unit-sized AddCornerMask quads are not
    # built then. Round keeps the concentric AddCornerMask at chamfer - PET_FILL_INSET.
    same = rt.eval("rawequal")
    hosts = [f for f in rt.globals().__frames.values() if same(f.parent, pet.visual)
             and (f.cutErase is not None or f.maskRadius is not None)]
    assert len(hosts) == 1, f"expected one pet corner host, got {len(hosts)}"
    host = hosts[0]
    assert _same(rt, host.points.TOPLEFT.rel, pet.health) and _same(rt, host.points.BOTTOMRIGHT.rel, pet.health), (
        "the corner host covers the pink fill")
    assert _level(host) > _level(pet.health), "the erase draws above the fill"
    if chrome == "cut":
        erase = host.cutErase
        assert erase is not None and host.maskRadius is None, "cut uses the nine-slice erase, not quads"
        assert host.clipsChildren is True, "the host must clip the box-sized wedge to the fill rect"
        assert _same(rt, erase.plate, box), "the wedge is sliced over the BOX rect, the ring's own"
        assert erase.chamfer == chamfer, f"erase chamfer {erase.chamfer}: want the ring's {chamfer}"
        assert _close(_rgba(erase.color)[:3], PET_FILL[:3]), (
            f"erase colour {_rgba(erase.color)}: want the box fill's rgb {PET_FILL[:3]}")
        edge_tl, edge_br = pet.edge.points.TOPLEFT, pet.edge.points.BOTTOMRIGHT
        assert _same(rt, edge_tl.rel, box) and _same(rt, edge_br.rel, box), (
            "the ring is sliced over the box rect")
        assert pet.edge.skinOpts.chamfer == erase.chamfer, "ring and wedge share one chamfer"
    else:
        assert host.cutErase is None and host.maskRadius == chamfer - inset, (
            f"round mask {host.maskRadius}: want {chamfer - inset}")
    assert _level(pet.edge) > _level(host), "the edge stroke must sit above the erase"

    # Dashed placeholder: same box, steel at .5. Each edge starts/ends where the straight run
    # does: under cut TL and BR are cut, TR and BL square.
    placeholder = pet.placeholder
    assert math.isclose(placeholder.alpha, 0.5), f"placeholder alpha {placeholder.alpha}"
    assert _close(_rgba(placeholder.roundedColor), PET_EMPTY_FILL), "placeholder fill .85 x .5"
    steel = _theme_color("COLOR_STEEL")[:3]
    pb = placeholder.GetBounds(placeholder)
    assert (pb.x, pb.y, pb.w, pb.h) == (b.x, b.y, b.w, b.h), "placeholder is the shorter box"
    width, height = _const("PET_WIDTH"), b.h / scale
    dash = _const("PET_DASH_SIZE")
    runs = {"LEFT": [], "RIGHT": [], "TOP": [], "BOTTOM": []}
    for region in placeholder.regions.values():
        assert _close(_rgba(region.color)[:3], steel), "placeholder dashes are COLOR_STEEL"
        points = {name: p for name, p in region.points.items()}
        if "TOPLEFT" in points and region.w == 1:
            runs["LEFT"].append(-points["TOPLEFT"].y)
        elif "TOPRIGHT" in points and region.w == 1:
            runs["RIGHT"].append(-points["TOPRIGHT"].y)
        elif "TOPLEFT" in points:
            runs["TOP"].append(points["TOPLEFT"].x)
        elif "BOTTOMLEFT" in points:
            runs["BOTTOM"].append(points["BOTTOMLEFT"].x)
    assert all(runs.values()), f"missing dash edge: {({k: len(v) for k, v in runs.items()})}"
    if chrome == "round":
        for edge in ("LEFT", "RIGHT"):
            assert min(runs[edge]) == chamfer and max(runs[edge]) <= height - chamfer - dash
        for edge in ("TOP", "BOTTOM"):
            assert min(runs[edge]) == chamfer and max(runs[edge]) <= width - chamfer - dash
        return
    assert min(runs["LEFT"]) == chamfer, f"left dashes start {min(runs['LEFT'])}: want {chamfer}"
    assert max(runs["LEFT"]) <= height - 1 - dash, "left dashes run into the square BL corner"
    assert min(runs["RIGHT"]) == 1, f"right dashes start {min(runs['RIGHT'])}: want 1"
    assert max(runs["RIGHT"]) <= height - chamfer - dash, "right dashes cross the BR cut"
    assert min(runs["TOP"]) == chamfer, f"top dashes start {min(runs['TOP'])}: want {chamfer}"
    assert max(runs["TOP"]) <= width - dash, "top dashes overrun the square TR corner"
    assert min(runs["BOTTOM"]) == 0, f"bottom dashes start {min(runs['BOTTOM'])}: want 0"
    assert max(runs["BOTTOM"]) <= width - chamfer - dash, "bottom dashes cross the BR cut"


def _check_pet_erase_falls_back_to_quads() -> None:
    """A client that cannot slice (AddCutFillErase answers nil) still gets the pink fill's corners
    cut, by the unit-sized AddCornerMask at the box chamfer: no unerased square corner."""
    rt = _runtime(before_load="__eraseUnavailable=true")
    row = rt.globals().FS.partyRows[1]
    same = rt.eval("rawequal")
    hosts = [f for f in rt.globals().__frames.values() if same(f.parent, row.petFrame.visual)
             and (f.cutErase is not None or f.maskRadius is not None)]
    assert len(hosts) == 1 and hosts[0].cutErase is None, "the fallback must not half-build an erase"
    assert not hosts[0].clipsChildren, "the quad fallback needs no clip"
    assert hosts[0].maskRadius == int(_const("PET_CHAMFER")), f"fallback quads {hosts[0].maskRadius}"


def _check_pet_fill_falls_back_to_rounded_fill() -> None:
    """A client that cannot slice (AddCutSliceFill answers nil) keeps the box filled by the old
    AddRoundedFill at the same chamfer and colour, and draws no nine-slice fill."""
    rt = _runtime(before_load="__sliceFillUnavailable=true")
    box = rt.globals().FS.partyRows[1].petFrame.box
    assert box.sliceFill is None, "nothing half built"
    assert box.roundedRadius == int(_const("PET_CHAMFER")), f"fallback chamfer {box.roundedRadius}"
    assert _close(_rgba(box.roundedColor), PET_FILL), f"fallback fill {_rgba(box.roundedColor)}"


def _check_pet_edge_and_label() -> None:
    """With a pet: a cyan .85 edge with a .5 glow and a PET label (mono 6.5, --muted at .8)
    centred 3.5 above the box top, font set before its text; with no pet the label is hidden."""
    rt = _runtime()
    g = rt.globals()
    pet = g.FS.partyRows[2].petFrame
    cyan = _theme_color("COLOR_POWER")[:3]
    ring, glow = pet.edge.fsSkin.border.ring, pet.edge.fsSkin.glow
    assert pet.edge.skinOpts.chamfer == 4
    assert _close(_rgba(ring.color), (*cyan, 0.85)), f"pet ring {_rgba(ring.color)}"
    assert _close(_rgba(glow.color), (*cyan, 0.5)), f"pet glow {_rgba(glow.color)}"
    label = pet.petLabel
    assert label.text == "PET" and label.mono.size == 6.5, "label text and size"
    assert not label.textBeforeFont, "the label font must be set before any SetText"
    muted = _theme_color("COLOR_MUTED")[:3]
    assert _close(_rgba(label.mono.color), (*muted, 0.8)), f"label colour {_rgba(label.mono.color)}"
    bottom = label.points.BOTTOM
    assert bottom.rp == "TOP" and _same(rt, bottom.rel, pet.box), "label sits on the box top"
    assert math.isclose(bottom.x, 0.5) and math.isclose(bottom.y, _const("PET_LABEL_GAP"))
    assert label.shown, "label shows while a pet exists"
    rt2 = _runtime(before_load="UnitExists=function(u) return not u:find('pet') end")
    pet2 = rt2.globals().FS.partyRows[2].petFrame
    assert not pet2.petLabel.shown, "no pet, no PET label"
    assert pet2.placeholder.shown, "the dashed placeholder shows when there is no pet"


def _check_alert_backing(chrome: str) -> None:
    rt, row = _row_pet(chrome)
    icon = row.alertIcons[1]
    size = int(_const("ALERT_ICON_SIZE"))
    square = [
        r for r in icon.regions.values()
        if "TOPLEFT" in r.points and r.points["TOPLEFT"].x == -1 and r.points["TOPLEFT"].y == 1
    ]
    if chrome == "round":
        assert len(square) == 1, "round keeps the 1px-outset square backing texture"
        return
    # Cut: no square backing (it would poke past the TL and BR cuts); a fill following the
    # ring's chamfer sits on a child frame BELOW the icon, outset 1px like the old square.
    assert not square, "cut must not keep the square backing"
    chamfer = CUT_ICON_SIZE[size]
    same = rt.eval("rawequal")
    hosts = [f for f in rt.globals().__frames.values()
             if same(f.parent, icon) and f.roundedRadius is not None]
    assert len(hosts) == 1, f"expected one cut backing host, got {len(hosts)}"
    host = hosts[0]
    assert host.roundedRadius == chamfer, f"backing chamfer {host.roundedRadius}: want {chamfer}"
    assert host.points["TOPLEFT"].x == -1 and host.points["TOPLEFT"].y == 1
    assert host.points["BOTTOMRIGHT"].x == 1 and host.points["BOTTOMRIGHT"].y == -1
    assert host.GetFrameLevel(host) < icon.GetFrameLevel(icon), "backing must sit under the icon"


def _check_alert_tray_left() -> None:
    """The alert tray sits OUTSIDE the panel's LEFT edge (the right side is the Gunsight's left
    cast tape), mirrored: slot 1 nearest the panel, later slots stepping away, level with the row."""
    rt = _runtime()
    fs = rt.globals().FS
    panel = fs.partyContainer.GetBounds(fs.partyContainer)
    scale = fs.Layout.Scale()
    inset, gap = _const("ALERT_TRAY_INSET") * scale, _const("ALERT_GAP") * scale
    for index, row in fs.partyRows.items():
        member = row.GetBounds(row)
        previous = None
        for slot, icon in row.alertIcons.items():
            b = icon.GetBounds(icon)
            assert b.right <= panel.x - inset + .001, (
                f"row {index} alert {slot} right edge {b.right} not left of panel {panel.x} - {inset}"
            )
            centre, row_centre = b.y + b.h / 2, member.y + member.h / 2
            assert abs(centre - row_centre) < .001, (
                f"row {index} alert {slot} centre {centre} not on row centre {row_centre}"
            )
            if previous is None:
                assert abs(b.right - (panel.x - inset)) < .001, (
                    f"row {index} slot 1 right {b.right}: want panel left minus inset"
                )
            else:
                assert abs(b.right - (previous.x - gap)) < .001, (
                    f"row {index} alert {slot} must step left by the gap"
                )
            previous = b


def _check_no_panel_chrome() -> None:
    """Box-matched has no panel-level chrome: the content host that holds the rows carries no
    fill, border or glow (the old HUD scrim panel is gone)."""
    rt = _runtime()
    content = rt.globals().FS.partyRows[1].parent
    for field in ("roundedRadius", "roundedColor", "borderRadius", "glowRadius"):
        assert content[field] is None, f"content still has panel chrome ({field})"
    assert not list(content.regions.values()), "content owns textures, expected a bare host"
    assert rt.globals().FS.partyContainer.roundedRadius is None


# Box-matched row chrome (mockup 'bx'): fill rgba(13,6,32) at .85 x .82, a 6 chamfer, 17 below
# the row top. Hard-coded on purpose, not read back from the module.
BOX_FILL = (0.051, 0.024, 0.125, 0.697)
PET_FILL = (0.051, 0.024, 0.125, 0.765)  # mockup pA(.9) x .85 while a pet exists
PET_EMPTY_FILL = (0.051, 0.024, 0.125, 0.85)  # x placeholder alpha .5 = .425
PET_PINK_ALPHA = 0.95  # mockup pPetFill pA(.95)
STATE_ALPHA = 0.55
BOX_TOP = 17


def _rgba(color) -> list:
    return [color[k] for k in (1, 2, 3, 4)]


def _level(frame) -> int:
    return frame.GetFrameLevel(frame)


def _check_member_box() -> None:
    """A cut box (chamfer 6, 17 below the row top, as wide as the row, to the row bottom) sits
    under the rails, the header and the red edge layer, and moves no rail."""
    rt = _runtime()
    fs = rt.globals().FS
    scale = fs.Layout.Scale()
    for index, row in fs.partyRows.items():
        member, box = row.GetBounds(row), row.box
        b = box.GetBounds(box)
        assert abs(b.x - member.x) < .001 and abs(b.w - member.w) < .001, f"row {index} box x/w"
        assert abs(b.y - (member.y + BOX_TOP * scale)) < .001, f"row {index} box top {b.y}"
        assert abs(b.bottom - member.bottom) < .001, f"row {index} box bottom {b.bottom}"
        assert box.roundedRadius == 6 and box.edge.skinOpts.chamfer == 6, "box chamfer must be 6"
        assert _close(_rgba(box.roundedColor), BOX_FILL), f"box fill {_rgba(box.roundedColor)}"
        below = (row.health.shell, row.power.shell, row.name.parent)
        assert all(_level(box) < _level(x) for x in below), "box must draw below rails and header"
        assert _level(row.box.dashHost) > _level(box), "the dash host must sit above the fill"
        assert _level(box) < _level(row.box.edge) < _level(row.boxRed) < min(
            _level(x) for x in below), (
            "fill below, then the base edge, then the red layer, all still below the rails")
        for layer in (row.box.edge, row.boxRed):
            r = layer.GetBounds(layer)
            assert (r.x, r.y, r.w, r.h) == (b.x, b.y, b.w, b.h), "edge layers must share the rect"


def _edge(row):
    """The base edge's ring and glow: they live on the base edge FRAME (`box.edge`), not on the
    fill frame, so the low-HP curve can drive that frame's alpha without touching their own."""
    skin = row.box.edge.fsSkin
    return skin.border.ring, skin.glow


def _check_box_edge_live_and_dispel() -> None:
    """Live: a solid cyan edge with a glow; a cleansable debuff retints it to the dispel colour
    (the halo's own colour), and clearing it goes back to cyan."""
    rt = _runtime()
    row = rt.globals().FS.partyRows[2]
    cyan, magic = _theme_color("COLOR_POWER")[:3], _dispel_colors()['Magic']
    ring, glow = _edge(row)
    assert _close(_rgba(ring.color), (*cyan, 1)), f"live ring {_rgba(ring.color)}"
    assert _close(_rgba(glow.color), (*cyan, 0.5)), f"live glow {_rgba(glow.color)}"
    assert ring.shown and glow.shown and not row.box.dashHost.shown, "live edge is solid"
    rt.execute("__debuffs={'Magic'}")
    _fire(row, "UNIT_AURA")
    assert _close(_rgba(ring.color), (*magic, 1)), "dispel colour must beat cyan"
    assert _close(_rgba(glow.color), (*magic, 0.5)), "the glow follows the dispel colour"
    rt.execute("__debuffs={}")
    _fire(row, "UNIT_AURA")
    assert _close(_rgba(ring.color), (*cyan, 1)), "edge returns to cyan"
    _assert_quiet(rt)


def _check_box_edge_down_dashed() -> None:
    """Dead/ghost/offline: the solid edge and glow go, a steel dashed edge (4 on, 3 off, straight
    edges only, alpha .7) takes over; the box itself is NOT dimmed (the mockup draws it with A(),
    not pA()); a dispel colour still wins over steel; going live restores the solid edge."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    steel = _theme_color("COLOR_STEEL")[:3]
    ring, glow = _edge(row)
    g.__state = "dead"
    _fire(row, "UNIT_HEALTH")
    assert not ring.shown and not glow.shown and row.box.dashHost.shown, "dashed edge only"
    assert row.box.alpha == 1, f"a down row's box keeps full strength, got {row.box.alpha}"
    assert _close(_rgba(row.box.roundedColor), BOX_FILL), "the box fill stays at .82 x .85"
    assert _base_alpha(row) == 1, "a down row's base edge layer stays at 1"
    assert _low(row) == 0, "a down row never shows red"
    dashes = list(row.box.dashes.values())
    assert all(_close(_rgba(d.color), (*steel, 0.7)) for d in dashes), "steel dashes at .7"
    top = sorted(d.points.TOPLEFT.x for d in dashes if d.w == 4 and "TOPLEFT" in d.points)
    bottom = sorted(d.points.BOTTOMLEFT.x for d in dashes if d.w == 4 and "BOTTOMLEFT" in d.points)
    assert top == list(range(6, 184, 7)), f"top dashes start at the cut, 4 on 3 off: {top}"
    assert bottom == list(range(0, 178, 7)), f"bottom dashes end at the cut: {bottom}"
    rt.execute("__debuffs={'Magic'}")
    _fire(row, "UNIT_AURA")
    assert all(_close(_rgba(d.color)[:3], _dispel_colors()['Magic']) for d in dashes), "dispel beats steel"
    rt.execute("__debuffs={}")
    g.__state = "live"
    _fire(row, "UNIT_HEALTH")
    _fire(row, "UNIT_AURA")
    assert ring.shown and glow.shown and not row.box.dashHost.shown, "live restores the solid edge"
    assert row.box.alpha == 1, "live keeps the full alpha"
    _assert_quiet(rt)


def _target_changed(g) -> None:
    """Dispatch PLAYER_TARGET_CHANGED to the module event frame, but only if the addon really
    registered it: calling OnEvent directly would pass with the registration deleted."""
    ev = g.FS.partyEvents
    assert ev.registered.PLAYER_TARGET_CHANGED, "PLAYER_TARGET_CHANGED is not registered"
    ev.scripts.OnEvent(ev, "PLAYER_TARGET_CHANGED")


def _retarget(rt, unit) -> None:
    """Point the mock target at `unit` (None clears it) and fire PLAYER_TARGET_CHANGED on the
    module event frame, as the client does."""
    g = rt.globals()
    g.__target = unit
    _target_changed(g)


def _check_target_edge_purple() -> None:
    """The row whose unit is the player's target wears the purple edge (ring and glow) instead of
    cyan; retargeting moves it, clearing the target restores cyan, the player's own row counts."""
    rt = _runtime()
    g = rt.globals()
    rows = g.FS.partyRows
    cyan, purple = _theme_color("COLOR_POWER")[:3], _theme_color("COLOR_TARGET")[:3]
    assert not _close(cyan, purple), "the target colour must differ from cyan"

    def expect(row, rgb, label) -> None:
        ring, glow = _edge(row)
        assert _close(_rgba(ring.color), (*rgb, 1)), f"{label} ring {_rgba(ring.color)}"
        assert _close(_rgba(glow.color), (*rgb, 0.5)), f"{label} glow {_rgba(glow.color)}"
        assert ring.shown and glow.shown and not row.box.dashHost.shown, f"{label} stays solid"

    for index in (1, 2, 3):
        expect(rows[index], cyan, f"untargeted row {index}")
    _retarget(rt, "party1")
    expect(rows[2], purple, "targeted party1")
    expect(rows[3], cyan, "other row")
    expect(rows[1], cyan, "player row")
    _retarget(rt, "party2")
    expect(rows[2], cyan, "party1 after retarget")
    expect(rows[3], purple, "retargeted party2")
    _retarget(rt, "player")
    expect(rows[1], purple, "the player's own row")
    expect(rows[3], cyan, "party2 after targeting the player")
    _retarget(rt, None)
    for index in (1, 2, 3):
        expect(rows[index], cyan, f"cleared row {index}")
    # A repaint (any health or aura event) re-reads the target, so it holds across updates.
    _retarget(rt, "party1")
    _fire(rows[2], "UNIT_HEALTH")
    _fire(rows[2], "UNIT_AURA")
    expect(rows[2], purple, "targeted row after a repaint")
    _assert_quiet(rt)


def _check_target_edge_precedence() -> None:
    """Edge precedence: red low-HP layer > dispel colour > target purple > steel dashes > cyan.
    A targeted low row shows red only (the base edge fades out under it); a targeted dispel row
    keeps the dispel colour; a targeted dead or offline row keeps the dashes, tinted purple."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    purple, magic = _theme_color("COLOR_TARGET")[:3], _dispel_colors()['Magic']
    steel = _theme_color("COLOR_STEEL")[:3]
    ring, glow = _edge(row)
    _retarget(rt, "party1")

    _set_hp(g, .2)
    _fire(row, "UNIT_HEALTH")
    assert _low(row) == 1 and _base_alpha(row) == 0, "low HP: red layer on, base edge off"
    assert _close(_rgba(row.boxRed.fsSkin.border.ring.color), (*RED, 1)), "the red layer stays red"
    _set_hp(g, 1)
    _fire(row, "UNIT_HEALTH")
    assert _low(row) == 0 and _base_alpha(row) == 1, "healthy again: the base edge is back"
    assert _close(_rgba(ring.color), (*purple, 1)), "and it is still the target purple"

    rt.execute("__debuffs={'Magic'}")
    _fire(row, "UNIT_AURA")
    assert _close(_rgba(ring.color), (*magic, 1)) and _close(_rgba(glow.color), (*magic, 0.5)), (
        "dispel colour beats target purple")
    rt.execute("__debuffs={}")
    _fire(row, "UNIT_AURA")
    assert _close(_rgba(ring.color), (*purple, 1)), "clearing the dispel returns to purple"

    dashes = list(row.box.dashes.values())
    for state in ("dead", "ghost", "offline"):
        g.__state = state
        _fire(row, "UNIT_HEALTH")
        assert not ring.shown and not glow.shown and row.box.dashHost.shown, f"{state}: dashes"
        assert all(_close(_rgba(d.color), (*purple, 0.7)) for d in dashes), (
            f"a targeted {state} row has purple dashes at .7")
        assert _low(row) == 0, f"{state}: never red"
    rt.execute("__debuffs={'Magic'}")
    _fire(row, "UNIT_AURA")
    assert all(_close(_rgba(d.color)[:3], magic) for d in dashes), "dispel beats purple dashes"
    rt.execute("__debuffs={}")
    _fire(row, "UNIT_AURA")
    _retarget(rt, None)
    assert all(_close(_rgba(d.color), (*steel, 0.7)) for d in dashes), "untargeted down row: steel"
    _retarget(rt, "party1")
    assert all(_close(_rgba(d.color), (*purple, 0.7)) for d in dashes), "retargeted: purple again"
    g.__state = "live"
    _fire(row, "UNIT_HEALTH")
    assert ring.shown and glow.shown and not row.box.dashHost.shown, "live restores the solid edge"
    assert _close(_rgba(ring.color), (*purple, 1)), "a live targeted row is purple again"
    _assert_quiet(rt)


def _check_target_secret_degrades() -> None:
    """UnitIsUnit is SecretWhenUnitComparisonRestricted (secret on addon-restricted maps): a
    secret answer is never branched on, the edge just stays untargeted (cyan), and nothing throws."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    cyan = _theme_color("COLOR_POWER")[:3]
    g.__target, g.__targetSecret = "party1", True
    _target_changed(g)
    _fire(row, "UNIT_HEALTH")
    ring, glow = _edge(row)
    assert _close(_rgba(ring.color), (*cyan, 1)) and _close(_rgba(glow.color), (*cyan, 0.5)), (
        f"a secret comparison leaves the edge cyan, got {_rgba(ring.color)}")
    g.__targetSecret = False
    _target_changed(g)
    assert _close(_rgba(ring.color)[:3], _theme_color("COLOR_TARGET")[:3]), "readable again: purple"
    _assert_quiet(rt)


def _check_target_event_registered() -> None:
    """The module event frame must register PLAYER_TARGET_CHANGED itself (the harness dispatches
    OnEvent directly, so only this assert notices a deleted registration)."""
    rt = _runtime()
    ev = rt.globals().FS.partyEvents
    assert ev.registered.PLAYER_TARGET_CHANGED, "PLAYER_TARGET_CHANGED is not registered"
    assert ev.registered.GROUP_ROSTER_UPDATE, "GROUP_ROSTER_UPDATE is not registered"


def _check_target_edge_follows_roster_change() -> None:
    """A roster change can move who holds a row token (the target stays the same person): the
    GROUP_ROSTER_UPDATE repaint (UpdateAll -> UpdateRowHealth -> ApplyBoxEdge) re-reads the target
    test, so the purple moves with no PLAYER_TARGET_CHANGED."""
    rt = _runtime()
    g = rt.globals()
    rows = g.FS.partyRows
    cyan, purple = _theme_color("COLOR_POWER")[:3], _theme_color("COLOR_TARGET")[:3]
    _retarget(rt, "party1")
    assert _close(_rgba(_edge(rows[2])[0].color), (*purple, 1)), "party1 starts targeted"
    g.__target = "party2"  # the roster re-seated: the targeted person now holds party2
    ev = g.FS.partyEvents
    assert ev.registered.GROUP_ROSTER_UPDATE, "GROUP_ROSTER_UPDATE is not registered"
    ev.scripts.OnEvent(ev, "GROUP_ROSTER_UPDATE")
    assert _close(_rgba(_edge(rows[2])[0].color), (*cyan, 1)), "party1 loses the purple"
    assert _close(_rgba(_edge(rows[3])[0].color), (*purple, 1)), "party2 takes the purple"
    assert _close(_rgba(_edge(rows[3])[1].color), (*purple, 0.5)), "and its glow"
    _assert_quiet(rt)


def _pet_edge(row) -> tuple:
    skin = row.petFrame.edge.fsSkin
    return _rgba(skin.border.ring.color), _rgba(skin.glow.color)


def _check_pet_edge_target_purple() -> None:
    """A targeted party pet wears the purple edge (ring at the pet .85, glow at .5) instead of
    cyan; clearing the target or retargeting restores cyan; a pet repaint (pet appears or
    changes) re-reads it; a member row's own edge is untouched by a pet target."""
    rt = _runtime()
    g = rt.globals()
    rows = g.FS.partyRows
    cyan, purple = _theme_color("COLOR_POWER")[:3], _theme_color("COLOR_TARGET")[:3]
    alpha = _const("PET_EDGE_ALPHA")
    glow_alpha = _const("BOX_GLOW_ALPHA")

    def expect(row, rgb, label) -> None:
        ring, glow = _pet_edge(row)
        assert _close(ring, (*rgb, alpha)) and _close(glow, (*rgb, glow_alpha)), (
            f"{label}: ring {ring} glow {glow}")

    expect(rows[2], cyan, "untargeted pet")
    _retarget(rt, "partypet1")
    expect(rows[2], purple, "targeted pet")
    expect(rows[3], cyan, "other pet")
    assert _close(_rgba(_edge(rows[2])[0].color), (*cyan, 1)), "a pet target leaves the member box"
    _retarget(rt, "partypet2")
    expect(rows[2], cyan, "pet after retarget")
    expect(rows[3], purple, "retargeted pet")
    _retarget(rt, None)
    expect(rows[3], cyan, "cleared target")
    # A pet repaint (UNIT_PET / UNIT_HEALTH on the row) re-reads the target.
    g.__target = "partypet1"
    _fire(rows[2], "UNIT_PET")
    expect(rows[2], purple, "pet repaint while targeted")
    g.__target = None
    _fire(rows[2], "UNIT_HEALTH")
    expect(rows[2], cyan, "pet repaint after the target cleared")
    # Targeting the member (not the pet) never tints the pet.
    _retarget(rt, "party1")
    expect(rows[2], cyan, "member targeted, pet stays cyan")
    _assert_quiet(rt)


def _check_pet_edge_secret_degrades() -> None:
    """A secret UnitIsUnit answer for a pet counts as not targeted: cyan, nothing thrown."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    cyan = _theme_color("COLOR_POWER")[:3]
    g.__target, g.__targetSecret = "partypet1", True
    _target_changed(g)
    _fire(row, "UNIT_PET")
    ring, glow = _pet_edge(row)
    assert _close(ring, (*cyan, _const("PET_EDGE_ALPHA"))), f"secret pet ring {ring}"
    assert _close(glow, (*cyan, _const("BOX_GLOW_ALPHA"))), f"secret pet glow {glow}"
    g.__targetSecret = False
    _target_changed(g)
    assert _close(_pet_edge(row)[0][:3], _theme_color("COLOR_TARGET")[:3]), "readable again: purple"
    _assert_quiet(rt)


def _check_unit_is_unit_error_degrades() -> None:
    """A UnitIsUnit that RAISES (no such API, or a restricted call) is caught by the pcall in
    ApplyBoxEdge and ApplyTargetEdge: member and pet edges fall back to cyan from purple, nothing
    reaches TryStep (a raise there prints, which _assert_quiet fails), and both recover."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    cyan, purple = _theme_color("COLOR_POWER")[:3], _theme_color("COLOR_TARGET")[:3]
    ring = _edge(row)[0]
    _retarget(rt, "party1")
    assert _close(_rgba(ring.color)[:3], purple), "member starts purple"
    g.__targetThrows = True
    _target_changed(g)
    assert _close(_rgba(ring.color)[:3], cyan), "a raising UnitIsUnit degrades the member to cyan"
    _retarget(rt, "partypet1")  # target the pet while still raising, then clear the flag and re-dispatch
    g.__targetThrows = False
    _target_changed(g)
    assert _close(_pet_edge(row)[0][:3], purple), "pet starts purple"
    g.__targetThrows = True
    _target_changed(g)
    _fire(row, "UNIT_PET")
    assert _close(_pet_edge(row)[0][:3], cyan), "a raising UnitIsUnit degrades the pet to cyan"
    assert _close(_pet_edge(row)[1][:3], cyan), "and its glow"
    g.__targetThrows = False
    _target_changed(g)
    assert _close(_pet_edge(row)[0][:3], purple), "readable again: the pet is purple"
    _assert_quiet(rt)


def _check_pet_edge_resets_without_pet() -> None:
    """ApplyTargetEdge runs BEFORE UpdateRowPet's no-pet early return: a targeted pet that goes
    away (target cleared, UnitExists false) repaints through UNIT_PET alone, no
    PLAYER_TARGET_CHANGED, and the edge goes back to cyan instead of keeping the purple."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    cyan, purple = _theme_color("COLOR_POWER")[:3], _theme_color("COLOR_TARGET")[:3]
    _retarget(rt, "partypet1")
    assert _close(_pet_edge(row)[0][:3], purple), "the targeted pet is purple"
    rt.execute("UnitExists=function(u) return not u:find('pet') end")
    g.__target = None  # the pet is gone, so the client drops the target; no event is sent here
    _fire(row, "UNIT_PET")
    assert not row.petFrame.petLabel.shown, "no pet: the label hides (the early return ran)"
    ring, glow = _pet_edge(row)
    assert _close(ring, (*cyan, _const("PET_EDGE_ALPHA"))), f"the edge resets to cyan, got {ring}"
    assert _close(glow, (*cyan, _const("BOX_GLOW_ALPHA"))), f"and its glow, got {glow}"
    _assert_quiet(rt)


def _check_pet_edge_retints_only_on_change() -> None:
    """The pet edge retints only when the targeted state changes: repaints and target events with
    nothing changed make no SetVertexColor call, a real change makes exactly the ring and glow."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    rt.execute("""
        __vc = 0
        local skin = FS.partyRows[2].petFrame.edge.fsSkin
        for _, tex in ipairs({skin.border.ring, skin.glow}) do
            local orig = tex.SetVertexColor
            tex.SetVertexColor = function(self, ...) __vc = __vc + 1 return orig(self, ...) end
        end
    """)
    _retarget(rt, "partypet1")
    assert g.__vc == 2, f"a real change retints the ring and the glow once each, got {g.__vc}"
    g.__vc = 0
    _fire(row, "UNIT_PET")
    _fire(row, "UNIT_HEALTH")
    _target_changed(g)
    assert g.__vc == 0, f"a repaint with no change must not retint, got {g.__vc} calls"
    _retarget(rt, None)
    assert g.__vc == 2, f"clearing the target is a real change, got {g.__vc}"
    g.__vc = 0
    _fire(row, "UNIT_PET")
    _target_changed(g)
    assert g.__vc == 0, f"untargeted repaints must not retint either, got {g.__vc} calls"
    _assert_quiet(rt)


def _low(row) -> float:
    return row.boxRed.alpha


def _base_alpha(row) -> float:
    """Alpha of the base edge layer: its frame's alpha (the ring and glow only, never the box
    fill, which is a different frame)."""
    return row.box.edge.alpha


def _set_hp(g, fraction: float, state: str = "live") -> None:
    g.__fraction, g.__health, g.__max, g.__state = fraction, round(fraction * 100), 100, state


def _check_low_hp_red_layer() -> None:
    """The red edge layer (its own frame, red ring and glow) takes its alpha from the Step curve
    through UnitHealthPercent: 1 at or below 35%, 0 above, 0 for a down row; a secret health
    reaches it with no compare. frame.lowHealthTargets is the driver's target list."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    ring, glow = row.boxRed.fsSkin.border.ring, row.boxRed.fsSkin.glow
    assert _close(_rgba(ring.color), (*RED, 1)) and _close(_rgba(glow.color), (*RED, 0.5))
    assert _same(rt, row.lowHealthTargets[1], row.boxRed), "the red layer is a driver target"
    for fraction, want in ((.2, 1), (.35, 1), (.36, 0), (.9, 0)):
        _set_hp(g, fraction)
        _fire(row, "UNIT_HEALTH")
        assert _low(row) == want, f"red alpha {_low(row)} at {fraction}: want {want}"
    _set_hp(g, .1, "dead")
    _fire(row, "UNIT_HEALTH")
    assert _low(row) == 0, "a dead row never shows red"
    _set_hp(g, .2)
    g.__health = g.__max = g.__secret
    _fire(row, "UNIT_HEALTH")
    assert _low(row) == 1, "secret health still drives the red layer through the curve"
    _assert_quiet(rt)


def _check_low_hp_base_edge_yields_to_red() -> None:
    """A low row's edge is red only: the base ring and glow take the inverse Step curve (0 at or
    below 35%, 1 above) so cyan or dispel colour cannot bleed under the red glow. Never the box
    fill. Down rows keep the base at 1; a secret health goes through the curve; no curve API:
    plain compare only when neither value is secret, an unknown leaves base 1 and red 0."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    for fraction, base, red in ((.2, 0, 1), (.35, 0, 1), (.36, 1, 0), (.9, 1, 0)):
        _set_hp(g, fraction)
        _fire(row, "UNIT_HEALTH")
        assert _base_alpha(row) == base, f"base edge {_base_alpha(row)} at {fraction}"
        assert _low(row) == red, f"red {_low(row)} at {fraction}"
        assert _close(_rgba(row.box.roundedColor), BOX_FILL) and row.box.alpha == 1, "fill stays"
    _set_hp(g, .2)
    g.__health = g.__max = g.__secret
    _fire(row, "UNIT_HEALTH")
    assert _base_alpha(row) == 0 and _low(row) == 1, "secret health still swaps the layers"
    _set_hp(g, .2, "offline")
    _fire(row, "UNIT_HEALTH")
    assert _base_alpha(row) == 1 and _low(row) == 0, "a down row keeps the steel edge"
    _assert_quiet(rt)
    rt = _runtime(native_percent=False)
    g = rt.globals()
    row = g.FS.partyRows[2]
    for fraction, base, red in ((.2, 0, 1), (.8, 1, 0)):
        _set_hp(g, fraction)
        _fire(row, "UNIT_HEALTH")
        assert _base_alpha(row) == base and _low(row) == red, f"plain fallback at {fraction}"
    _set_hp(g, .2)
    g.__health = g.__max = g.__secret
    _fire(row, "UNIT_HEALTH")
    assert _base_alpha(row) == 1 and _low(row) == 0, "unknown health: base 1, red 0"
    _assert_quiet(rt)


def _check_low_hp_without_curve() -> None:
    """No percent API: plain cur/max only when neither is secret; a secret leaves red hidden and
    is never compared."""
    rt = _runtime(native_percent=False)
    g = rt.globals()
    row = g.FS.partyRows[2]
    _set_hp(g, .2)
    _fire(row, "UNIT_HEALTH")
    assert _low(row) == 1, "plain fallback marks 20% low"
    _set_hp(g, .8)
    _fire(row, "UNIT_HEALTH")
    assert _low(row) == 0
    _set_hp(g, .2)
    g.__health = g.__max = g.__secret
    _fire(row, "UNIT_HEALTH")
    assert _low(row) == 0, "a secret health leaves the red layer hidden"
    _assert_quiet(rt)  # a secret compare would have been caught and printed by TryStep


def _check_low_hp_curve_failure_latches() -> None:
    """A curve call that errors latches: one degrade message for the session, then the plain
    fallback drives the layer."""
    rt = _runtime(before_load=(
        "local real=UnitHealthPercent "
        "UnitHealthPercent=function(u,p,c) "
        "if c and c.kind==Enum.LuaCurveType.Step then error('refused') end return real(u,p,c) end"),
        quiet=False)  # the refusal is the point of this case
    g = rt.globals()
    row = g.FS.partyRows[2]
    assert len(list(g.__messages.values())) == 1, "the first refusal logs once"
    for fraction, want in ((.2, 1), (.8, 0), (.1, 1)):
        _set_hp(g, fraction)
        _fire(row, "UNIT_HEALTH")
        assert _low(row) == want, f"fallback alpha {_low(row)} at {fraction}"
        assert _base_alpha(row) == 1 - want, "fallback drives the base edge too"
    assert len(list(g.__messages.values())) == 1, "a latched curve must not log again"


# ---------------------------------------------------------------------------------------------
# Box-matched header (mockup 'bx' pClassTile / pRoleTag / pHead)
# ---------------------------------------------------------------------------------------------

ROLE_STYLE = {"TANK": ("T", "COLOR_POWER"), "HEALER": ("H", "COLOR_HEAL"), "DAMAGER": ("D", "COLOR_RED")}


def _head(rt, row):
    """Design-unit geometry of the header pieces, relative to the header's top-left."""
    scale = rt.globals().FS.Layout.Scale()
    header = row.name.parent.GetBounds(row.name.parent)

    def rel(region):
        b = region.GetBounds(region)
        return ((b.x - header.x) / scale, (b.y - header.y) / scale,
                (b.right - header.x) / scale, (b.bottom - header.y) / scale)
    return rel


def _check_role_tag() -> None:
    """A 13 x 12 cut tag (chamfer 4, Theme.CutSize(12), chosen over the 3 that 3.5 would snap to) 3 right of the
    class plate and 2 below the row top: dark fill (.95 x .95), 1px stroke in the role colour at .9, the T/H/D
    letter in mono 8.5 in that colour. No role hides it; the name's x is the same either way."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[1]
    rel = _head(rt, row)
    tag = row.roleTag
    assert (tag.w, tag.h) == (13, 12) and tag.roundedRadius == 4 and tag.skinOpts.chamfer == 4
    assert _close(_rgba(tag.roundedColor), (.051, .024, .125, .95 * .95)), "tag fill: mockup pA(.95) x .95"
    assert not tag.shown, "no assigned role hides the tag"
    hidden_name_x = rel(row.name)[0]
    for role, (letter, token) in ROLE_STYLE.items():
        g.__role = role
        _fire(row, "UNIT_NAME_UPDATE")
        want = _theme_color(token)[:3]
        assert tag.shown and row.roleLetter.text == letter, f"{role}: letter {row.roleLetter.text}"
        assert _close(_rgba(tag.fsSkin.border.ring.color), (*want, .9)), f"{role} stroke"
        assert _close(_rgba(row.roleLetter.textColor), (*want, 1)), f"{role} letter colour"
        assert row.roleLetter.mono.size == 8.5, "role letter is mono 8.5"
        assert rel(tag)[:2] == (19, 2), f"{role} tag at {rel(tag)[:2]}: want 3 right of the plate, 2 down"
        assert rel(row.name)[0] == hidden_name_x == 35, "name x must not depend on the tag"
    g.__role = "NONE"
    _fire(row, "UNIT_NAME_UPDATE")
    assert not tag.shown, "role cleared hides the tag again"
    _assert_quiet(rt)


def _check_header_name() -> None:
    """The name is mono 10.5 in the class colour at .95, upper-cased only when it is a plain
    string, starts 3 right of the role tag, and a secret name reaches SetText untouched (a string
    op on it would throw)."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[1]
    rel = _head(rt, row)
    _fire(row, "UNIT_NAME_UPDATE")
    assert row.name.text == "FIRST SURNAME", row.name.text
    assert row.name.mono.size == 10.5, "mono 10.5"
    assert _close(_rgba(row.name.textColor), (.9, .8, .1, .95)), f"name colour {_rgba(row.name.textColor)}"
    assert rel(row.name)[0] == rel(row.roleTag)[2] + 3, "name starts 3 right of the role tag"
    g.__unitName = g.__secret
    _fire(row, "UNIT_NAME_UPDATE")
    assert _same(rt, row.name.text, g.__secret), "a secret name must reach SetText untouched"
    _assert_quiet(rt)


def _check_name_without_get_unit_name() -> None:
    """With GetUnitName absent the name falls back to UnitName: a plain name is used as is, nil
    becomes an empty string, and a secret reaches SetText untouched with no throw. (The mock
    cannot throw on a truth test of a secret, so the IsSecret-before-`or` order in
    GetFullUnitName is a source rule here, not something this proves.)"""
    rt = _runtime(before_load="GetUnitName=nil")
    g = rt.globals()
    row = g.FS.partyRows[1]
    _fire(row, "UNIT_NAME_UPDATE")
    assert row.name.text == "FIRST", row.name.text
    rt.execute("function UnitName() return nil end")
    _fire(row, "UNIT_NAME_UPDATE")
    assert row.name.text == "", f"nil name must become '' not {row.name.text!r}"
    rt.execute("function UnitName() return __secret end")
    _fire(row, "UNIT_NAME_UPDATE")
    assert _same(rt, row.name.text, g.__secret), "a secret UnitName must reach SetText untouched"
    _assert_quiet(rt)


def _check_header_level_and_low_tag() -> None:
    """'LV n' is right-aligned at the rail's right edge + 1 (mono 8.5, muted at .9) and hidden at
    max level. The 25 x 12 LOW tag sits 2 below the row top with its right edge 2 left of the
    rail edge + 1, plus the 36 level reserve (the mockup's tw) while the level shows; the name's
    right edge is anchored 3 left of it. Every header FontString has its font before any SetText."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[1]
    rel = _head(rt, row)
    inner = rel(row.health.shell)[2]  # the rail's right edge, in header units
    muted = _theme_color("COLOR_MUTED")[:3]
    low = row.lowHealthTargets[2]
    _fire(row, "UNIT_NAME_UPDATE")
    assert not row.levelText.shown, "level text hidden at max level"
    assert (low.w, low.h) == (25, 12) and low.roundedRadius == 4, "LOW tag is a 25 x 12 chamfer 4 cut tag"
    assert rel(low)[1] == 2 and rel(low)[2] == inner + 1 - 2, f"max level LOW tag at {rel(low)}"
    name_right = row.name.points.RIGHT
    assert _same(rt, name_right.rel, low) and name_right.rp == "LEFT" and name_right.x == -3, \
        "name RIGHT anchors to the LOW tag's LEFT, 3 left"
    g.__level, g.__role = 45, "HEALER"
    _fire(row, "UNIT_NAME_UPDATE")
    assert row.levelText.shown and row.levelText.text == "LV 45", row.levelText.text
    assert rel(row.levelText)[2] == inner + 1, "LV text right edge is the rail edge + 1"
    assert row.levelText.mono.size == 8.5 and _close(_rgba(row.levelText.mono.color), (*muted, .9))
    assert rel(low)[2] == inner + 1 - 36 - 2, f"LOW tag with a level at {rel(low)}"
    assert rel(row.name)[2] == rel(low)[0] - 3, "the name edge follows the re-seated LOW tag"
    assert _close(_rgba(low.roundedColor), (.051, .024, .125, .95 * .95)), "LOW tag fill: .95 x .95"
    for font_string in (row.roleLetter, row.levelText, row.lowText, row.name):
        assert font_string.text is not None and not font_string.textBeforeFont, \
            "every header FontString gets its font before its first SetText"
    assert row.lowText.text == "LOW" and row.lowText.mono.size == 8, "LOW label is mono 8"
    assert _close(_rgba(row.lowText.mono.color), _theme_color("COLOR_RED")), "LOW label red"
    assert _close(_rgba(low.fsSkin.border.ring.color), (*RED, 1)), "LOW stroke red"
    _assert_quiet(rt)


def _check_low_tag_follows_red_layer() -> None:
    """The LOW tag is a low-HP driver target: its alpha is the red box layer's, 1 at or below 35%
    and 0 above or for a down row, by alpha only."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    low = row.lowHealthTargets[2]
    for fraction, state, want in ((.2, "live", 1), (.8, "live", 0), (.2, "dead", 0)):
        _set_hp(g, fraction, state)
        _fire(row, "UNIT_HEALTH")
        assert low.alpha == _low(row) == want, f"LOW alpha {low.alpha} at {fraction} {state}"
    assert low.shown, "the tag is never Shown/Hidden by health"
    _assert_quiet(rt)


def _check_header_dims_when_down() -> None:
    """A dead row dims the class plate, role tag, name and level text to the row alpha; going
    live restores them."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    g.__role, g.__level = "HEALER", 45
    pieces = (row.classPlate, row.roleTag, row.name, row.levelText)
    g.__state = "dead"
    _fire(row, "UNIT_HEALTH")
    assert all(math.isclose(p.alpha, STATE_ALPHA) for p in pieces), [p.alpha for p in pieces]
    g.__state = "live"
    _fire(row, "UNIT_HEALTH")
    assert all(p.alpha == 1 for p in pieces), [p.alpha for p in pieces]
    _assert_quiet(rt)


# ---------------------------------------------------------------------------------------------
# Alert tray: party buffs the player can provide and a member lacks
# ---------------------------------------------------------------------------------------------

FORT, SPIRIT, SHADOW = "Power Word: Fortitude", "Divine Spirit", "Shadow Protection"
SPELL_IDS = {FORT: 1001, SPIRIT: 1002, SHADOW: 1003, "Arcane Intellect": 2001,
             "Mark of the Wild": 3001, "Shadow Bolt": 4001}


def _buff_rt(player_class: str = "PRIEST", known=(FORT, SPIRIT, SHADOW), extra: str = "",
             **kwargs) -> LuaRuntime:
    """A runtime whose spellbook resolves every SPELL_IDS name and knows only `known`.
    `extra` is Lua run after the spellbook is set up (the mock APIs already exist)."""
    ids = ",".join(f"['{n}']={i}" for n, i in SPELL_IDS.items())
    knows = ",".join(f"[{SPELL_IDS[n]}]=true" for n in known)
    return _runtime(
        player_class=player_class,
        before_load=f"__spellIds={{{ids}}} __knownIds={{{knows}}} {extra}",
        **kwargs,
    )


def _set_buffs(rt, unit: str, auras: str) -> None:
    """auras is a Lua list literal of {name=,caster=,duration=,expiration=} entries."""
    rt.execute(f"__buffs['{unit}']={auras}")


def _tiles(row) -> list:
    return [i for i in range(1, 4) if row.alertIcons[i].shown]


def _color_alpha(name: str) -> float:
    """The alpha of a `local NAME = { r, g, b, a }` constant from PartyFrames.lua."""
    match = re.search(
        rf"^local {name}\s*=\s*\{{\s*[\d.]+,\s*[\d.]+,\s*[\d.]+,\s*([\d.]+)", PARTY_SRC, re.M
    )
    assert match, f"PartyFrames.lua has no alpha on color local {name}"
    return float(match.group(1))


def _is_tint(icon, color: str) -> bool:
    """rgb and alpha of the tile's tint both match the named constant."""
    want = (*_color(color), _color_alpha(color))
    return _close([icon.tex.color[k] for k in (1, 2, 3, 4)], want)


def _party1(rt):
    return rt.globals().FS.partyRows[2]


def _check_buff_missing(c_unitauras: bool = True) -> None:
    rt = _buff_rt(c_unitauras=c_unitauras, known=(FORT,))
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1], f"one known missing buff must give one tile: {_tiles(row)}"
    icon = row.alertIcons[1]
    assert icon.tex.texture == f"spelltex:{FORT}", f"tile must wear the spell icon: {icon.tex.texture}"
    assert _is_tint(icon, "MAINT_MISSING_COLOR"), "missing look is the dim red tint"
    assert icon.missingText == f"Missing: {FORT}", f"tooltip text {icon.missingText}"
    # Giving the member the buff clears it.
    _set_buffs(rt, "party1", f"{{{{name='{FORT}',caster='player',duration=1800,expiration=1700}}}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], f"buff present and fresh: no tile: {_tiles(row)}"
    _assert_quiet(rt)


RED = (1, 0.2314, 0.3059)  # Theme.COLOR_RED, #ff3b4e


def _ring_glow(icon) -> tuple[list, list]:
    skin = icon.fsSkin
    assert skin.border.ring.color is not None and skin.glow.color is not None, (
        "the alert ring and glow were never tinted")
    return ([skin.border.ring.color[k] for k in (1, 2, 3, 4)],
            [skin.glow.color[k] for k in (1, 2, 3, 4)])


def _check_missing_ring_red() -> None:
    rt = _buff_rt(known=(FORT,))
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    icon = row.alertIcons[1]
    assert _is_tint(icon, "MAINT_MISSING_COLOR"), "missing tile keeps the dim red icon tint"
    ring, glow = _ring_glow(icon)
    assert _close(ring, (*RED, 0.95)), f"missing ring is Theme.COLOR_RED at .95: {ring}"
    assert _close(glow, (*RED, 0.5)), f"missing glow is the same red at .5: {glow}"
    _assert_quiet(rt)


def _check_ring_follows_tile_use() -> None:
    """Alert tiles are pooled: a tile that showed a debuff then a missing buff then a debuff
    again must wear each use's ring, never the previous one's."""
    rt = _buff_rt(known=(FORT,))
    row = _party1(rt)
    magic = _dispel_colors()['Magic']
    ring_a, glow_a = _const("ALERT_RING_ALPHA"), _const("ALERT_GLOW_ALPHA")

    def expect(label, rgb, ring_alpha, glow_alpha):
        ring, glow = _ring_glow(row.alertIcons[1])
        assert _close(ring, (*rgb, ring_alpha)), f"{label}: ring {ring}"
        assert _close(glow, (*rgb, glow_alpha)), f"{label}: glow {glow}"

    rt.execute("__debuffs={'Magic'}")
    _set_buffs(rt, "party1", f"{{{{name='{FORT}',caster='party2',duration=1800,expiration=1700}}}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1]
    expect("debuff tile", magic, ring_a, glow_a)
    rt.execute("__debuffs={}")
    _set_buffs(rt, "party1", "{}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1]
    expect("same tile reused for a missing buff", RED, 0.95, 0.5)
    rt.execute("__debuffs={'Magic'}")
    _set_buffs(rt, "party1", f"{{{{name='{FORT}',caster='party2',duration=1800,expiration=1700}}}}")
    _fire(row, "UNIT_AURA")
    expect("back to a debuff", magic, ring_a, glow_a)
    _assert_quiet(rt)


def _check_buff_other_caster_and_group() -> None:
    rt = _buff_rt(known=(FORT,))
    row = _party1(rt)
    _set_buffs(rt, "party1", "{{name='Prayer of Fortitude',caster='party2',duration=3600,expiration=3000}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], "Prayer of Fortitude from another caster satisfies Fortitude"
    _set_buffs(rt, "party1", f"{{{{name='{FORT}',caster='party3',duration=1800,expiration=1500}}}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], "the single buff from another caster satisfies it too"
    _set_buffs(rt, "party1", "{{name='Renew',caster='player',duration=15,expiration=10}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1], "an unrelated player buff must not satisfy Fortitude"
    _assert_quiet(rt)


def _check_buff_present_never_alerts() -> None:
    """Parker: show a buff alert only when the buff is MISSING. Any buff that is up, however
    little time it has left, gives no tile."""
    rt = _buff_rt(known=(FORT,))
    row = _party1(rt)
    for label, aura in {
        "10 s left": f"{{name='{FORT}',caster='party2',duration=1800,expiration=10}}",
        "1 s left": f"{{name='{FORT}',caster='party2',duration=1800,expiration=1}}",
        "no expiry": f"{{name='{FORT}',caster='party2'}}",
    }.items():
        _set_buffs(rt, "party1", "{" + aura + "}")
        _fire(row, "UNIT_AURA")
        assert _tiles(row) == [], f"a buff with {label} is up, so no alert: {_tiles(row)}"
    _assert_quiet(rt)


def _check_buff_toggle_and_default_off() -> None:
    rt = _buff_rt()
    g = rt.globals()
    row = _party1(rt)
    _set_buffs(rt, "party1", f"{{{{name='{FORT}',duration=1800,expiration=1700}},"
                              f"{{name='{SPIRIT}',duration=1800,expiration=1700}}}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], "Shadow Protection is OFF by default: no tile for it"
    rt.execute("__messages={}")
    g.SlashCmdList.FSPARTY("buff shadowprot on")
    assert g.ForeverSTUwaveDB.partyBuffs.shadowprot is True, "toggle on must persist true"
    assert _tiles(row) == [1], f"toggling on repaints the rows: {_tiles(row)}"
    assert row.alertIcons[1].missingText == f"Missing: {SHADOW}"
    g.SlashCmdList.FSPARTY("buff shadowprot off")
    assert g.ForeverSTUwaveDB.partyBuffs.shadowprot is False
    assert _tiles(row) == [], "toggling off hides it again"
    g.SlashCmdList.FSPARTY("buff fortitude off")
    _set_buffs(rt, "party1", "{}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1], f"Spirit still alerts with Fortitude off: {_tiles(row)}"
    assert row.alertIcons[_tiles(row)[0]].missingText == f"Missing: {SPIRIT}"
    rt.execute("__messages={}")
    g.SlashCmdList.FSPARTY("buff nonsense on")
    msgs = list(g.__messages.values())
    assert msgs and "nonsense" in msgs[0], f"unknown key must be reported: {msgs}"
    # A saved override beats the default in a fresh session.
    rt2 = _runtime(before_load=(
        "ForeverSTUwaveDB={partyBuffs={fortitude=false,shadowprot=true}} "
        f"__spellIds={{['{FORT}']=1001,['{SHADOW}']=1003}} __knownIds={{[1001]=true,[1003]=true}}"))
    row2 = _party1(rt2)
    _fire(row2, "UNIT_AURA")
    assert _tiles(row2) == [1] and row2.alertIcons[1].missingText == f"Missing: {SHADOW}", (
        "saved overrides: Fortitude off, Shadow Protection on"
    )


def _check_buff_unknown_spell() -> None:
    rt = _buff_rt(known=())
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], "spells the player has not learned never alert"
    rt = _runtime(before_load="__spellIds={} __knownIds={}")
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], "a name that does not resolve is not known"
    # No spellbook-known API at all: a name-resolvable spell id counts as known.
    rt = _runtime(before_load=f"__spellIds={{['{FORT}']=1001}} C_SpellBook=nil")
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1], "no known-API: a resolvable name means known"
    rt = _runtime(before_load=f"__spellIds={{['{FORT}']=1001}} C_SpellBook=nil C_Spell.GetSpellInfo=nil")
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], "nothing resolves the name: not known"


SPELLBOOK_EVENTS = ("SPELLS_CHANGED", "LEARNED_SPELL_IN_TAB", "PLAYER_LEVEL_UP",
                    "CHARACTER_POINTS_CHANGED", "PLAYER_TALENT_UPDATE")


def _check_buff_known_cache_events() -> None:
    # One fresh runtime per event, so each event is proven on its own.
    for event in SPELLBOOK_EVENTS:
        rt = _buff_rt(known=())
        g = rt.globals()
        row = _party1(rt)
        _fire(row, "UNIT_AURA")
        assert _tiles(row) == [], event
        rt.execute(f"__knownIds[{SPELL_IDS[FORT]}]=true")
        _fire(row, "UNIT_AURA")
        assert _tiles(row) == [], "known state is cached between spellbook events"
        frames = [f for f in g.__frames.values() if f.registered[event]]
        assert frames, f"nothing registered for {event}"
        frames[0].scripts.OnEvent(frames[0], event)
        assert _tiles(row) == [1], f"{event} must refresh known state and repaint: {_tiles(row)}"
        rt.execute("__knownIds={}")
        frames[0].scripts.OnEvent(frames[0], event)
        assert _tiles(row) == [], f"{event}: unlearned spell clears the tile"
        _assert_quiet(rt)


def _check_buff_icon_lookup_cached() -> None:
    # Every unit has Spirit from the start (the rows paint once while loading) and lacks
    # Fortitude: only the missing spell ever asks for its texture.
    up = f"{{{{name='{SPIRIT}',caster='player',duration=1800,expiration=1700}}}}"
    rt = _buff_rt(known=(FORT, SPIRIT), extra=(
        f"for _,u in ipairs({{'player','party1','party2','party3','party4'}}) do __buffs[u]={up} end "
        "__tex={} local real=C_Spell.GetSpellTexture "
        "C_Spell.GetSpellTexture=function(x) __tex[x]=(__tex[x] or 0)+1 return real(x) end"))
    g = rt.globals()
    row = _party1(rt)
    for _ in range(4):
        _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1], _tiles(row)
    assert g.__tex[FORT] == 1, f"one texture call per missing spell, got {g.__tex[FORT]}"
    assert g.__tex[SPIRIT] is None, "a satisfied buff must never look up its texture"
    # A spellbook event drops the cache, so the next missing paint asks again, once.
    frames = [f for f in g.__frames.values() if f.registered["SPELLS_CHANGED"]]
    frames[0].scripts.OnEvent(frames[0], "SPELLS_CHANGED")
    for _ in range(3):
        _fire(row, "UNIT_AURA")
    assert g.__tex[FORT] == 2, f"a fresh call after a spellbook event, got {g.__tex[FORT]}"
    assert g.__tex[SPIRIT] is None
    _assert_quiet(rt)


def _check_buff_scratch_reuse_across_units() -> None:
    rt = _buff_rt(known=(FORT,))
    row_a, row_b = rt.globals().FS.partyRows[2], rt.globals().FS.partyRows[3]
    assert row_a.unit != row_b.unit
    _set_buffs(rt, row_b.unit, f"{{{{name='{FORT}',caster='player',duration=1800,expiration=1700}}}}")
    for label in ("first", "after the satisfied unit"):
        _fire(row_a, "UNIT_AURA")
        assert _tiles(row_a) == [1], f"unit A is missing the buff ({label}): {_tiles(row_a)}"
        assert row_a.alertIcons[1].tex.texture == f"spelltex:{FORT}", f"icon ({label})"
        assert _is_tint(row_a.alertIcons[1], "MAINT_MISSING_COLOR"), f"look ({label})"
        _fire(row_b, "UNIT_AURA")
        assert _tiles(row_b) == [], f"unit B has the buff: {_tiles(row_b)}"
    _assert_quiet(rt)


def _check_buff_report_reads_live_entries() -> None:
    rt = _buff_rt(known=(FORT, SPIRIT))
    g = rt.globals()

    def report() -> str:
        rt.execute("__messages={}")
        g.SlashCmdList.FSPARTY("")
        return "\n".join(str(m) for m in g.__messages.values())

    text = report()
    assert "MISSING" in text and "Divine Spirit" in text and FORT in text, text
    g.SlashCmdList.FSPARTY("buff spirit off")
    text = report()
    assert FORT in text, text
    assert "Divine Spirit" not in text, f"a disabled buff leaves no stale report line:\n{text}"


def _check_buff_warlock_and_classes() -> None:
    rt = _buff_rt(player_class="WARLOCK", known=tuple(SPELL_IDS))
    for row in rt.globals().FS.partyRows.values():
        _fire(row, "UNIT_AURA")
        assert _tiles(row) == [], "a warlock has no party buff: no buff alerts at all"
    rt.execute("__messages={}")
    rt.globals().SlashCmdList.FSPARTY("buffs")
    assert any("no party buffs" in str(m).lower() for m in rt.globals().__messages.values())
    for cls, spell in (("MAGE", "Arcane Intellect"), ("DRUID", "Mark of the Wild")):
        rt = _buff_rt(player_class=cls, known=(spell,))
        row = _party1(rt)
        _fire(row, "UNIT_AURA")
        assert _tiles(row) == [1] and row.alertIcons[1].missingText == f"Missing: {spell}", cls
    rt = _buff_rt(player_class="MAGE", known=("Arcane Intellect",))
    _set_buffs(rt, "party1", "{{name='Arcane Brilliance',caster='x',duration=3600,expiration=3000}}")
    _fire(_party1(rt), "UNIT_AURA")
    assert _tiles(_party1(rt)) == [], "Arcane Brilliance satisfies Arcane Intellect"
    rt = _buff_rt(player_class="DRUID", known=("Mark of the Wild",))
    _set_buffs(rt, "party1", "{{name='Gift of the Wild',caster='x',duration=3600,expiration=3000}}")
    _fire(_party1(rt), "UNIT_AURA")
    assert _tiles(_party1(rt)) == [], "Gift of the Wild satisfies Mark of the Wild"


def _check_buff_combat_holds() -> None:
    rt = _buff_rt(known=(FORT,))
    g = rt.globals()
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1]
    rt.execute("FS.AurasReadable=function() return false end")
    _set_buffs(rt, "party1", f"{{{{name='{FORT}',duration=1800,expiration=1700}}}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1], "in combat the last display is held, not cleared"
    rt.execute("FS.AurasReadable=function() return true end")
    _fire(row, "PLAYER_REGEN_ENABLED")
    assert _tiles(row) == [], "leaving combat re-scans and clears the satisfied tile"
    # And the other direction: nothing is invented in combat either.
    rt.execute("FS.AurasReadable=function() return false end")
    _set_buffs(rt, "party1", "{}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], "no new alert appears while auras are unreadable"
    _assert_quiet(rt)


def _check_aura_readable_callback() -> None:
    """Every row registers its refresh with FS.OnAurasReadable, so a regen whose read was
    refused (the client still says secret) is made up when reads become possible."""
    rt = _buff_rt(known=(FORT,))
    g = rt.globals()
    row = _party1(rt)
    callbacks = [g.__readableCallbacks[i] for i in range(1, len(g.__readableCallbacks) + 1)]
    assert len(callbacks) >= 1, "PartyFrames registered nothing with FS.OnAurasReadable"
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1], "one missing buff to start with"
    rt.execute("FS.AurasReadable=function() return false end")
    _set_buffs(rt, "party1", f"{{{{name='{FORT}',duration=1800,expiration=1700}}}}")
    _fire(row, "PLAYER_REGEN_ENABLED")   # the regen read was refused: held
    assert _tiles(row) == [1], "a refused regen refresh must hold the display"
    rt.execute("FS.AurasReadable=function() return true end")
    for fn in callbacks:
        fn()
    assert _tiles(row) == [], "the readable callback did not refresh the row"
    _assert_quiet(rt)


def _check_buff_after_debuffs() -> None:
    rt = _buff_rt(known=(FORT, SPIRIT))
    row = _party1(rt)
    rt.execute("__debuffs={'Magic'}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1, 2, 3], f"1 debuff + 2 missing buffs fill the tray: {_tiles(row)}"
    assert row.alertIcons[1].tex.texture == "icon", "the cleansable debuff comes first"
    assert row.alertIcons[2].missingText == f"Missing: {FORT}"
    assert row.alertIcons[3].missingText == f"Missing: {SPIRIT}"
    rt.execute("__debuffs={'Magic','Disease'}")
    _fire(row, "UNIT_AURA")
    assert row.alertIcons[1].tex.texture == "icon" and row.alertIcons[2].tex.texture == "icon"
    assert row.alertIcons[3].missingText == f"Missing: {FORT}", "two debuffs leave one buff slot"
    rt.execute("__debuffs={}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1, 2], "no debuffs: buff tiles move up"
    _assert_quiet(rt)


def _check_buff_secret_fields() -> None:
    # Count what the module hands to IsSecret: the wrapper must exist before the module loads
    # and captures FS.IsSecret.
    rt = _runtime(before_load=(
        f"__spellIds={{['{FORT}']=1001}} __knownIds={{[1001]=true}} __seen={{}} "
        "local real=FS.IsSecret "
        "FS.IsSecret=function(v) __seen[#__seen+1]=v return real(v) end"))
    g = rt.globals()
    row = _party1(rt)
    # A secret name cannot be told apart from Fortitude: no false nag, no throw.
    rt.execute("__buffs['party1']={{name=__secret,duration=1800,expiration=1700}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], f"unreadable aura names must not produce a missing alert: {_tiles(row)}"
    # A secret name beside the real buff: the real one still satisfies it.
    rt.execute(f"__buffs['party1']={{{{name=__secret}},{{name='{FORT}',duration=1800,expiration=1700}}}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == []
    # A secret expiration or duration is never read: the buff is up, so no alert.
    rt.execute(f"__buffs['party1']={{{{name='{FORT}',duration=__secret,expiration=__secret}}}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], "a present buff with secret timing gives no alert"
    # A secret caster is never touched (any caster satisfies).
    rt.execute(f"__buffs['party1']={{{{name='{FORT}',caster=__secret,duration=1800,expiration=1700}}}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == []
    same = rt.eval("rawequal")
    assert any(same(v, g.__secret) for v in g.__seen.values()), "aura names must be IsSecret-guarded"
    _assert_quiet(rt)


def _check_buff_tooltip_and_report() -> None:
    rt = _buff_rt(known=(FORT,))
    g = rt.globals()
    rt.execute("""
        __tip={}
        GameTooltip={SetOwner=function(_,o) __tip.owner=o end,
            SetText=function(_,t) __tip.text=t end,AddLine=function() end,
            Show=function() __tip.shown=true end,Hide=function() __tip.shown=false end}
    """)
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    icon = row.alertIcons[1]
    icon.scripts.OnEnter(icon)
    assert g.__tip.text == f"Missing: {FORT}" and g.__tip.shown, "missing tile tooltip names the spell"
    rt.execute("__messages={}")
    g.SlashCmdList.FSPARTY("")
    text = "\n".join(str(m) for m in g.__messages.values())
    assert "MISSING" in text and FORT in text, f"/fsparty must report the missing buff:\n{text}"
    rt.execute("__messages={}")
    g.SlashCmdList.FSPARTY("buffs")
    text = "\n".join(str(m) for m in g.__messages.values())
    for key in ("fortitude", "spirit", "shadowprot"):
        assert key in text, f"/fsparty buffs must list {key}:\n{text}"
    assert "known" in text and "off" in text and "on" in text


def _tip_rt() -> LuaRuntime:
    """A buff runtime whose GameTooltip records the spell it was asked for (__tip.spell), the name
    (__tip.text) and its extra lines."""
    rt = _buff_rt(known=(FORT,))
    rt.execute("""
        GameTooltip={SetOwner=function(_,o) __tip={owner=o,lines={}} end,
            SetText=function(_,t) __tip.text=t end,AddLine=function(_,t) table.insert(__tip.lines,t) end,
            SetSpellByID=function(_,id) __tip.spell=id end,
            Show=function() __tip.shown=true end,Hide=function() __tip.shown=false end}
    """)
    return rt


def _hover_in_combat(rt, icon) -> None:
    """Hover the tile with aura reads refused, the way mid-fight hovering is."""
    rt.execute("FS.AurasReadable=function() return false end")
    icon.scripts.OnEnter(icon)
    rt.execute("FS.AurasReadable=function() return true end")


def _check_cleanse_tooltip_in_combat() -> None:
    rt = _tip_rt()
    g = rt.globals()
    row = _party1(rt)
    rt.execute("__debuffIds={Magic=2001} __debuffs={'Magic'}")
    _fire(row, "UNIT_AURA")
    icon = row.alertIcons[1]
    _hover_in_combat(rt, icon)
    assert g.__tip.spell == 2001, f"a cleanse tile hovered in combat must show its spell: {g.__tip.spell}"
    # The tile is reused for another debuff whose id is secret: the old spell must not follow.
    rt.execute("__debuffIds={Disease=__secret} __debuffs={'Disease'}")
    _fire(row, "UNIT_AURA")
    _hover_in_combat(rt, icon)
    assert g.__tip.spell is None, f"a reused tile kept the previous spell: {g.__tip.spell}"
    assert g.__tip.text == "Debuff Disease", f"the new aura's name instead: {g.__tip.text}"
    _assert_quiet(rt)


def _check_missing_tooltip_shows_spell() -> None:
    rt = _tip_rt()
    g = rt.globals()
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    icon = row.alertIcons[1]
    assert icon.missingText == f"Missing: {FORT}"
    icon.scripts.OnEnter(icon)
    assert g.__tip.spell == SPELL_IDS[FORT], f"the Missing tile must show the spell: {g.__tip.spell}"
    assert f"Missing: {FORT}" in list(g.__tip.lines.values()), "the Missing line is kept under the spell"
    # A client without SetSpellByID still names the spell.
    rt.execute("GameTooltip.SetSpellByID=nil")
    icon.scripts.OnEnter(icon)
    assert g.__tip.text == f"Missing: {FORT}", f"fallback text {g.__tip.text}"
    _assert_quiet(rt)


def _check_buff_down_members() -> None:
    rt = _runtime(
        before_load=(
            f"__spellIds={{['{FORT}']=1001}} __knownIds={{[1001]=true}} __helpful=0 "
            "local real=C_UnitAuras.GetAuraDataByIndex "
            "C_UnitAuras.GetAuraDataByIndex=function(u,i,f) "
            "if f:find('HELPFUL') then __helpful=__helpful+1 end return real(u,i,f) end"))
    g = rt.globals()
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1], "a live member missing the buff still alerts"
    for state in ("dead", "ghost", "offline"):
        reads = g.__helpful
        g.__state = state
        _fire(row, "UNIT_AURA")
        assert _tiles(row) == [], f"a {state} member must get no buff tile: {_tiles(row)}"
        assert g.__helpful == reads, f"the first {state} fire must already cost no buff aura read"
        _fire(row, "UNIT_AURA")
        assert g.__helpful == reads, f"a {state} member must cost no buff aura read"
        g.__state = "live"
        _fire(row, "UNIT_AURA")
        assert _tiles(row) == [1], f"alert returns when the {state} member is live again"
    _assert_quiet(rt)


def _check_buff_solo_player_row() -> None:
    rt = _buff_rt(known=(FORT,))
    row = rt.globals().FS.partyRows[1]
    assert row.unit == "player"
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1] and row.alertIcons[1].missingText == f"Missing: {FORT}", (
        "the player's own row alerts for a buff the player lacks"
    )
    _set_buffs(rt, "player", f"{{{{name='{FORT}',caster='player',duration=1800,expiration=1700}}}}")
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], "the player's own buff clears the tile"


def _check_buff_legacy_spellinfo() -> None:
    legacy = (
        "C_Spell.GetSpellInfo=nil C_Spell.GetSpellTexture=nil "
        "GetSpellInfo=function(n) local id=__spellIds[n] if not id then return nil end "
        "return n,nil,5000+id,0,0,0,id end "
        f"__spellIds={{['{FORT}']=1001}} __knownIds={{[1001]=true}}")
    rt = _runtime(before_load=legacy)
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1], "legacy GetSpellInfo resolves the id: known, so it alerts"
    assert row.alertIcons[1].tex.texture == 5000 + 1001, "legacy icon is the spell icon"
    rt = _runtime(before_load=legacy.replace("__knownIds={[1001]=true}", "__knownIds={}"))
    row = _party1(rt)
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [], "legacy path, spell not in the spellbook: no alert"
    _assert_quiet(rt)


def _check_buff_unreadable_known() -> None:
    rt = _runtime(before_load=(
        f"__spellIds={{['{FORT}']=1001}} __knownIds={{[1001]=true}} __mode='error' "
        "C_SpellBook.IsSpellKnown=function(id) "
        "if __mode=='error' then error('boom') elseif __mode=='secret' then return __secret end "
        "return __knownIds[id]==true end"))
    g = rt.globals()
    row = _party1(rt)
    for mode in ("error", "secret"):
        g.__mode = mode
        _fire(row, "UNIT_AURA")
        assert _tiles(row) == [], f"an unreadable known check ({mode}) must not claim missing"
    g.__mode = "ok"
    _fire(row, "UNIT_AURA")
    assert _tiles(row) == [1], "an unreadable answer is not cached: it is asked again"
    _assert_quiet(rt)


def _check_buff_aura_read_error() -> None:
    for c_unitauras in (True, False):
        wrap = (
            "local real=C_UnitAuras.GetAuraDataByIndex "
            "C_UnitAuras.GetAuraDataByIndex=function(u,i,f) "
            "if __throw and f:find('HELPFUL') then error('boom') end return real(u,i,f) end "
            "local realLegacy=UnitAura "
            "UnitAura=function(u,i,f) "
            "if __throw and f:find('HELPFUL') then error('boom') end return realLegacy(u,i,f) end")
        rt = _runtime(c_unitauras=c_unitauras, before_load=(
            f"__spellIds={{['{FORT}']=1001}} __knownIds={{[1001]=true}} __throw=false " + wrap))
        g = rt.globals()
        row = _party1(rt)
        g.__throw = True
        _fire(row, "UNIT_AURA")
        assert _tiles(row) == [], f"a throwing aura read is unreadable, not empty (C={c_unitauras})"
        g.__throw = False
        _fire(row, "UNIT_AURA")
        assert _tiles(row) == [1], "once the read works, an empty list is missing again"


def _check_buff_report_default_label() -> None:
    rt = _buff_rt()
    g = rt.globals()

    def report() -> dict:
        rt.execute("__messages={}")
        g.SlashCmdList.FSPARTY("buffs")
        lines = [str(m) for m in g.__messages.values()]
        return {k: next(line for line in lines if line.split()[0] == k)
                for k in ("fortitude", "spirit", "shadowprot")}

    lines = report()
    assert "(default)" in lines["shadowprot"], "unset and off by default says so"
    g.SlashCmdList.FSPARTY("buff shadowprot off")
    g.SlashCmdList.FSPARTY("buff spirit off")
    lines = report()
    assert "(default)" not in lines["shadowprot"], "an explicit saved false is not the default"
    assert "(default)" not in lines["spirit"] and "off" in lines["spirit"]


def _effective_alpha(rt: LuaRuntime, texture) -> float:
    """What the engine would draw: the texture's one alpha slot times every ancestor frame's alpha."""
    return rt.eval("""function(tex)
        local a = tex.alphaSlot or 1
        local f = tex.parent
        while f do a = a * (f.alpha or 1) f = f.parent end
        return a
    end""")(texture)


def _check_base_glow_alpha_survives_low_health_update() -> None:
    """Live bug 2026-10-03 (a "double border" on the row box): the low-HP curve called SetAlpha(1)
    on the base ring and glow TEXTURES, replacing the glow's BOX_GLOW_ALPHA, so the innermost glow
    texel read as a second cyan line. The base edge is now its own frame (`box.edge`, the same way
    `boxRed` is built), `lowHealthBase` lists that FRAME, and the curve drives frame alpha, which
    multiplies the glow's own alpha instead of replacing it."""
    rt = _runtime()
    g = rt.globals()
    row = g.FS.partyRows[2]
    ring, glow = _edge(row)
    want_glow = _const("BOX_GLOW_ALPHA")
    assert want_glow < 1, "the test needs a glow that is not already full strength"
    assert len(row.lowHealthBase) == 1 and _same(rt, row.lowHealthBase[1], row.box.edge), (
        "the curve must drive the base edge FRAME, not its textures")
    assert _same(rt, ring.parent, row.box.edge) and _same(rt, glow.parent, row.box.edge)
    assert row.box.fsSkin is None, "the fill frame carries no ring or glow of its own"
    for fraction in (1, .9, .2, 1):
        _set_hp(g, fraction)
        _fire(row, "UNIT_HEALTH")
        low = fraction <= .35
        ring_alpha, glow_alpha = _effective_alpha(rt, ring), _effective_alpha(rt, glow)
        if low:
            assert ring_alpha == 0 and glow_alpha == 0, f"low HP hides the base edge ({fraction})"
        else:
            assert _close((ring_alpha, glow_alpha), (1, want_glow)), (
                f"healthy base edge draws ring {ring_alpha}, glow {glow_alpha} at {fraction}: "
                f"the glow must stay at {want_glow}")
        red_ring, red_glow = row.boxRed.fsSkin.border.ring, row.boxRed.fsSkin.glow
        assert _close((_effective_alpha(rt, red_ring), _effective_alpha(rt, red_glow)),
                      (1, want_glow) if low else (0, 0)), f"red layer at {fraction}"
    _assert_quiet(rt)


def _snap_runtime(phys_w: int, phys_h: int, ui_h: int) -> LuaRuntime:
    """A client whose UIParent is `ui_h` tall for a `phys_w` x `phys_h` screen: UIParent's own
    scale is 768 / ui_h (the engine's), GetPhysicalScreenSize answers, UIParent:GetCenter exists."""
    ui_w = phys_w * ui_h / phys_h
    return _runtime(parent_height=ui_h, before_load=f"""
        GetPhysicalScreenSize=function() return {phys_w},{phys_h} end
        UIParent:SetScale(768/{ui_h}) UIParent:SetWidth({ui_w})
        UIParent.GetCenter=function(self) return self.w/2,self.h/2 end
    """)


def _container_edges_in_pixels(rt: LuaRuntime, phys_h: int, ui_h: int) -> tuple[float, float]:
    """The container's left edge and top edge, in whole-screen physical pixels from the screen's
    left and from its bottom, read off the CENTER offset the module seated."""
    fs = rt.globals().FS
    entry = fs.Layout.party
    scale = fs.Layout.Scale()
    point = fs.partyContainer.points.CENTER
    px = ui_h / phys_h  # UIParent units per physical pixel
    ui_w = rt.globals().UIParent.w
    left = (ui_w / 2 + point.x - entry.w * scale / 2) / px
    top = (ui_h / 2 + point.y + entry.h * scale / 2) / px
    return left, top


def _check_party_container_on_whole_pixels() -> None:
    """The party container is 231 design px wide at x = -389: on a screen whose width is even in
    pixels that puts its edges (and every row edge, since all the design sizes are whole pixels at
    a 1440 high screen) on half pixels, where the ring and the glow of a row box round in
    different directions and open a one pixel gap on the right edge (live, 5120x1440, UIParent
    1200 tall). The module snaps the container's left and top edges to whole physical pixels from
    the physical screen height and UIParent's effective scale."""
    for phys_w, phys_h, ui_h, half in ((5120, 1440, 1200, True), (2560, 1440, 1200, True),
                                       (2560, 1440, 1440, True), (1920, 1080, 768, False),
                                       (1920, 1080, 900, False), (1680, 1050, 1050, False)):
        label = f"{phys_w}x{phys_h} UIParent {ui_h}"
        rt = _snap_runtime(phys_w, phys_h, ui_h)
        fs = rt.globals().FS
        left, top = _container_edges_in_pixels(rt, phys_h, ui_h)
        assert abs(left - round(left)) < 1e-6 and abs(top - round(top)) < 1e-6, (
            f"{label}: container edges at ({left}, {top}) px are not whole pixels")
        # Not vacuous: where Layout alone puts the container on a half pixel, snapping moved it.
        scale = fs.Layout.Scale()
        raw_left = (rt.globals().UIParent.w / 2 + fs.Layout.party.x * scale
                    - fs.Layout.party.w * scale / 2) / (ui_h / phys_h)
        if half:
            assert abs(raw_left % 1 - .5) < 1e-6, f"{label}: expected a half pixel before the snap"
        # At a 1440 high screen one design px is one physical pixel, so every row, box and pet
        # edge is a whole pixel once the container is (member width 187, pet 24, pad 8, gap 4).
        if phys_h == 1440:
            to_px = phys_h / 768  # a bound is in 768 high screen units
            for index, row in fs.partyRows.items():
                for name, frame in (("row", row), ("box", row.box), ("pet", row.petFrame)):
                    b = frame.GetBounds(frame)
                    for edge in (b.x, b.right):
                        assert abs(edge * to_px - round(edge * to_px)) < 1e-6, (
                            f"{label}: row {index} {name} edge {edge * to_px} px is not whole")
        _assert_quiet(rt)


def _check_party_container_resnaps_and_waits_out_combat() -> None:
    """A UI scale or display change re-snaps (through Layout's rescale callbacks, after Layout
    re-seats the container). In combat the container (the parent of secure unit buttons, so
    protected) is left alone, and the snap lands on PLAYER_REGEN_ENABLED."""
    rt = _snap_runtime(5120, 1440, 1200)
    g = rt.globals()
    fs = g.FS
    rt.execute("__combat=false function InCombatLockdown() return __combat end")

    def event(name: str) -> None:
        rt.execute(f"""for _,frame in ipairs(__frames) do
            if frame.registered.{name} and frame.scripts.OnEvent then
                frame.scripts.OnEvent(frame,'{name}')
            end
        end""")

    def settle(ui_h: int) -> None:
        g.UIParent.SetScale(g.UIParent, 768 / ui_h)
        g.UIParent.SetSize(g.UIParent, 5120 * ui_h / 1440, ui_h)

    settle(1100)
    event("UI_SCALE_CHANGED")
    left, top = _container_edges_in_pixels(rt, 1440, 1100)
    assert abs(left - round(left)) < 1e-6 and abs(top - round(top)) < 1e-6, (
        f"after a scale change the container is at ({left}, {top}) px")
    g.__combat = True
    settle(1200)
    event("UI_SCALE_CHANGED")
    left, top = _container_edges_in_pixels(rt, 1440, 1200)
    assert abs(left % 1 - .5) < 1e-6, "in combat the module must not re-seat the container"
    g.__combat = False
    event("PLAYER_REGEN_ENABLED")
    left, top = _container_edges_in_pixels(rt, 1440, 1200)
    assert abs(left - round(left)) < 1e-6 and abs(top - round(top)) < 1e-6, (
        f"after combat the container is at ({left}, {top}) px")
    _assert_quiet(rt)


# ---------------------------------------------------------------------------------------------
# Blizzard's own party frames (PartyFrame, CompactPartyFrame) are silenced without taint
# ---------------------------------------------------------------------------------------------

TIMER_QUEUE = """__timers={}
C_Timer={After=function(_,fn) __timers[#__timers+1]=fn end}
function __runTimers()
    local due=__timers __timers={}
    for _,fn in ipairs(due) do fn() end
end"""


def _blizzard_frames(rt) -> list:
    return list(rt.eval("__blizz").values())


def _assert_silenced(rt, label: str) -> None:
    """Every Blizzard frame the fixture made except the raid frames (the party tree) is
    invisible, mouse-less and event-less."""
    checked = 0
    for frame in _blizzard_frames(rt):
        if frame.name in ("CompactRaidFrameContainer", "CompactRaidFrameManager"):
            continue
        checked += 1
        assert rt.eval("__silenced")(frame), (
            f"{label}: {frame.name or frame.kind} still draws or listens "
            f"(effective alpha {rt.eval('__effAlpha')(frame)}, mouse {frame.mouse})")
    assert checked, f"{label}: the fixture made no party frames"


def _assert_raid_untouched(rt) -> None:
    g = rt.globals()
    for name in ("CompactRaidFrameContainer", "CompactRaidFrameManager"):
        frame = g[name]
        assert frame.alpha == 1 and frame.mouse is True and rt.eval("next")(frame.registered), (
            f"{name} was touched: the addon does not replace raid frames")


def _check_blizzard_party_dimmed() -> None:
    """Both of Blizzard's party variants on this client (PartyFrame with its pooled member and
    pet frames, and the raid-style CompactPartyFrame under it) are dimmed. The fixture throws on
    Hide, HookScript, SetScript and SetParent, so only the alpha-only path can pass."""
    rt = _runtime()
    _assert_silenced(rt, "load")
    _assert_raid_untouched(rt)


def _check_blizzard_party_one_variant_only() -> None:
    """Feature-detect each variant on its own: PartyFrame without a CompactPartyFrame yet, and
    a CompactPartyFrame with no PartyFrame, are both handled and neither is a degrade."""
    _assert_silenced(_runtime(blizzard_party="no_compact"), "PartyFrame only")
    _assert_silenced(_runtime(blizzard_party="compact_only"), "CompactPartyFrame only")


def _check_blizzard_party_old_names_not_relied_on() -> None:
    """PartyMemberFrame1..4 do not exist on this client. A frame under the old name is not
    swept, and with no PartyFrame or CompactPartyFrame the sweep says so (once, by key)."""
    rt = _runtime(blizzard_party="decoy", quiet=False)
    g = rt.globals()
    assert g.PartyMemberFrame1.alpha == 1 and rt.eval("next")(g.PartyMemberFrame1.registered), (
        "the pre-12.x PartyMemberFrame1 name is still swept")
    messages = list(g.__messages.values())
    assert len(messages) == 1 and messages[0].startswith("partyframes_noblizzardparty:"), messages
    assert len(g.FS.partyRows) == 5, "the party rows must still build"


def _check_blizzard_party_late_frames(event: str) -> None:
    """Member frames come from a pool and CompactPartyFrame is generated on demand, both
    possibly after Init, and Blizzard's Setup re-registers events on a pooled member. The sweep
    reruns on the roster, enter-world and Edit Mode layout events, one frame later so it lands
    after Blizzard's own handlers of the same event."""
    rt = _runtime(blizzard_party="no_compact", before_load=TIMER_QUEUE)
    g = rt.globals()
    rt.execute("""PartyFrame.members[1]:RegisterEvent('UNIT_AURA')   -- Setup re-registers
        __lateMember=__blizzMember(PartyFrame)
        __lateCompact=__blizzCompact(PartyFrame)""")
    rt.execute(f"""for _,frame in ipairs(__frames) do
        if frame.registered.{event} and frame.scripts.OnEvent then frame.scripts.OnEvent(frame,'{event}') end
    end""")
    assert not rt.eval("__silenced")(g.__lateMember), (
        f"{event}: swept before Blizzard's own handlers had run")
    rt.execute("__runTimers()")
    _assert_silenced(rt, f"after {event}")
    _assert_raid_untouched(rt)


def _check_blizzard_party_sweep_waits_out_combat() -> None:
    """DimBlizzardFrame's EnableMouse touches protected unit buttons, so in combat the sweep is
    skipped and lands on PLAYER_REGEN_ENABLED."""
    rt = _runtime(before_load="__combat=false function InCombatLockdown() return __combat end "
                  + TIMER_QUEUE)
    g = rt.globals()
    rt.execute("__lateMember=__blizzMember(PartyFrame) __combat=true")

    def fire(name: str) -> None:
        rt.execute(f"""for _,frame in ipairs(__frames) do
            if frame.registered.{name} and frame.scripts.OnEvent then frame.scripts.OnEvent(frame,'{name}') end
        end __runTimers()""")

    fire("GROUP_ROSTER_UPDATE")
    assert g.__lateMember.alpha == 1 and g.__lateMember.mouse is True, "swept during combat"
    g.__combat = False
    fire("PLAYER_REGEN_ENABLED")
    _assert_silenced(rt, "after combat")


def _check_blizzard_party_sweep_error_is_contained() -> None:
    """A throw while silencing Blizzard's frames must not take the party rows down with it, and
    must not abort the frames after it: it is logged as one degrade and Init carries on."""
    rt = _runtime(before_load="PartyFrame.members[2].UnregisterAllEvents=function() error('boom') end",
                  quiet=False)
    g = rt.globals()
    assert len(g.FS.partyRows) == 5, "a sweep error stopped the party rows from building"
    messages = list(g.__messages.values())
    assert len(messages) == 1 and "boom" in messages[0], messages
    assert not rt.eval("__silenced")(g.PartyFrame.members[2]), "the fixture did not throw"
    assert rt.eval("__unsilencedOutside")(g.PartyFrame.members[2]) == 0, (
        "one throwing frame aborted the sweep of the others")
    assert g.PartyFrame.members[2].mouse is False, "the mouse sweep depends on the event sweep"


def _check_blizzard_party_mouse_reaches_descendants() -> None:
    """Alpha 0 still hit-tests, and the mouse does not inherit: the aura buttons under a member
    and its pet, the health bar (it forwards OnMouseUp to the member's Click) and a compact
    frame's nested buttons would be invisible click and tooltip targets. The load sweep covers
    every descendant; buttons Blizzard makes later are caught on the next UNIT_AURA."""
    rt = _runtime()
    _assert_silenced(rt, "descendants")  # includes HealthBar, containers, compact buttons


def _check_blizzard_party_lazy_aura_buttons() -> None:
    """PartyAuraFrameTemplate buttons are created on demand after the sweep. One UNIT_AURA burst
    schedules ONE deferred mouse sweep, which runs out of combat only."""
    rt = _runtime(before_load="__combat=false function InCombatLockdown() return __combat end "
                  + TIMER_QUEUE)
    g = rt.globals()

    def fire() -> None:
        rt.execute("""for _,frame in ipairs(__frames) do
            if frame.registered.UNIT_AURA and frame.scripts.OnEvent then
                frame.scripts.OnEvent(frame,'UNIT_AURA','party1')
            end
        end""")

    rt.execute("""__a1=__blizzLeaf('Button',PartyFrame.members[1].AuraFrameContainer)
        __a2=__blizzLeaf('Button',PartyFrame.members[3].PetFrame.AuraFrameContainer)""")
    for _ in range(3):
        fire()
    assert g.__a1.mouse is True and g.__a2.mouse is True, "swept before Blizzard's handlers"
    assert len(g.__timers) == 1, f"a UNIT_AURA burst queued {len(g.__timers)} sweeps"
    rt.execute("__runTimers()")
    assert g.__a1.mouse is False and g.__a2.mouse is False, "aura buttons still take the mouse"
    _assert_silenced(rt, "after the aura sweep")

    rt.execute("__combat=true __a3=__blizzLeaf('Button',PartyFrame.members[2].AuraFrameContainer)")
    fire()
    rt.execute("__runTimers()")
    assert g.__a3.mouse is True, "swept in combat"
    g.__combat = False
    rt.execute("""for _,frame in ipairs(__frames) do
        if frame.registered.PLAYER_REGEN_ENABLED and frame.scripts.OnEvent then
            frame.scripts.OnEvent(frame,'PLAYER_REGEN_ENABLED')
        end
    end __runTimers()""")
    assert g.__a3.mouse is False, "the combat-skipped aura button was not caught up"


def main() -> int:
    """Run the focused regressions and return a failing exit code on any error."""
    cases = [
        ("layout after late UIParent rescale", _check_late_rescale),
        ("full surname readout", _check_full_name),
        ("class atlas icon", _check_class_icon),
        ("shared FrameHelpers CreatePillBar (cut)", _check_shared_pill_bar),
        ("shared FrameHelpers CreatePillBar (round)", _check_shared_pill_bar_round),
        ("level chip chamfer (cut)", lambda: _check_level_chip("cut")),
        ("level chip radius (round)", lambda: _check_level_chip("round")),
        ("pet box rect, fill inset, mask and steel dashed placeholder (cut)",
         lambda: _check_pet_slot("cut")),
        ("pet box rect, fill inset, mask and steel dashed placeholder (round)",
         lambda: _check_pet_slot("round")),
        ("pet fill corners fall back to quads when the client cannot slice",
         _check_pet_erase_falls_back_to_quads),
        ("pet box fill falls back to AddRoundedFill when the client cannot slice",
         _check_pet_fill_falls_back_to_rounded_fill),
        ("pet edge cyan with glow, PET label only with a pet", _check_pet_edge_and_label),
        ("alert icon backing follows the cut", lambda: _check_alert_backing("cut")),
        ("alert icon backing square (round)", lambda: _check_alert_backing("round")),
        ("alert tray outside the panel's left edge", _check_alert_tray_left),
        ("health rail matches power rail recipe", _check_rail_parity),
        ("heal and absorb overlays on the HP rail", _check_health_overlays),
        ("rows refresh through FS.OnAurasReadable when a regen read was refused", _check_aura_readable_callback),
        ("dispel halo (C_UnitAuras path)", lambda: _check_dispel_halo(True)),
        ("dispel halo (UnitAura path)", lambda: _check_dispel_halo(False)),
        ("dispel set: Paladin with Purify lights Poison and Disease, not Magic",
         _check_dispel_paladin_purify),
        ("dispel set: Cleanse adds Magic", _check_dispel_paladin_cleanse),
        ("dispel set: Priest needs Dispel Magic for Magic", _check_dispel_priest_gated),
        ("dispel set: druid, mage and shaman gated per spell", _check_dispel_other_classes),
        ("dispel set: recomputed on SPELLS_CHANGED and friends",
         _check_dispel_recomputed_on_spellbook_events),
        ("dispel set: a class with no dispels lights nothing", _check_dispel_no_dispel_class),
        ("dispel set: a throwing spell API falls back safely", _check_dispel_throwing_spell_api),
        ("dispel set: a spell found by name counts", _check_dispel_name_fallback),
        ("dispel set: class read lazily, set cached", _check_dispel_class_read_lazily_and_cached),
        ("paladin first login: rows build, class colour from RAID_CLASS_COLORS",
         _check_paladin_first_login),
        ("dead then live rail", _check_dead_then_live_rail),
        ("no panel-level chrome on the content host", _check_no_panel_chrome),
        ("member row box: rect, chamfer, fill, below the rails", _check_member_box),
        ("box edge: live cyan, dispel colour wins", _check_box_edge_live_and_dispel),
        ("box edge: dead steel dashed, dispel beats steel, live restores",
         _check_box_edge_down_dashed),
        ("base edge glow keeps BOX_GLOW_ALPHA through low-HP updates",
         _check_base_glow_alpha_survives_low_health_update),
        ("party container edges land on whole physical pixels",
         _check_party_container_on_whole_pixels),
        ("party container re-snaps on rescale and waits out combat",
         _check_party_container_resnaps_and_waits_out_combat),
        ("target edge: purple on the targeted row, retarget and clear",
         _check_target_edge_purple),
        ("target edge: red > dispel > target > steel dashes > cyan", _check_target_edge_precedence),
        ("target edge: a secret UnitIsUnit degrades to cyan", _check_target_secret_degrades),
        ("target edge: PLAYER_TARGET_CHANGED and GROUP_ROSTER_UPDATE are registered",
         _check_target_event_registered),
        ("target edge: a roster change that re-seats the token moves the purple",
         _check_target_edge_follows_roster_change),
        ("pet edge: purple while the pet is targeted, normal on clear or repaint",
         _check_pet_edge_target_purple),
        ("pet edge: a secret UnitIsUnit answer stays cyan", _check_pet_edge_secret_degrades),
        ("target edge: a raising UnitIsUnit degrades member and pet to cyan",
         _check_unit_is_unit_error_degrades),
        ("pet edge: resets to cyan when a targeted pet goes away (before the early return)",
         _check_pet_edge_resets_without_pet),
        ("pet edge: retints only on a real change", _check_pet_edge_retints_only_on_change),
        ("low HP red edge layer from the Step curve", _check_low_hp_red_layer),
        ("low HP base edge yields to the red layer", _check_low_hp_base_edge_yields_to_red),
        ("low HP without the curve API: plain, secret stays hidden", _check_low_hp_without_curve),
        ("low HP curve failure latches once", _check_low_hp_curve_failure_latches),
        ("header role tag: colour and letter per role, hidden with none", _check_role_tag),
        ("header name: mono class colour, upper-cased unless secret", _check_header_name),
        ("header name falls back to UnitName: nil and secret safe", _check_name_without_get_unit_name),
        ("header LV text and LOW tag placement, name anchor", _check_header_level_and_low_tag),
        ("LOW tag alpha follows the red low-HP layer", _check_low_tag_follows_red_layer),
        ("dead row dims the header pieces", _check_header_dims_when_down),
        ("buff alert: missing shows the spell icon red (C_UnitAuras)", _check_buff_missing),
        ("buff alert: missing shows the spell icon red (UnitAura)", lambda: _check_buff_missing(False)),
        ("cleanse alert: hovered in combat it shows its spell, and a reused tile keeps no stale one",
         _check_cleanse_tooltip_in_combat),
        ("buff alert: the Missing tooltip shows the spell", _check_missing_tooltip_shows_spell),
        ("buff alert: other caster and group buff satisfy", _check_buff_other_caster_and_group),
        ("buff alert: a present buff never alerts, however little time is left",
         _check_buff_present_never_alerts),
        ("buff alert: missing tile ring and glow are red", _check_missing_ring_red),
        ("buff alert: ring colour follows the tile's use (debuff, missing, debuff)",
         _check_ring_follows_tile_use),
        ("buff alert: Shadow Protection default off, toggle and saved overrides",
         _check_buff_toggle_and_default_off),
        ("buff alert: unknown spell never alerts", _check_buff_unknown_spell),
        ("buff alert: known state cached, refreshed on spellbook events", _check_buff_known_cache_events),
        ("buff alert: missing icon looked up once per missing spell", _check_buff_icon_lookup_cached),
        ("buff alert: scratch list reuse across units", _check_buff_scratch_reuse_across_units),
        ("buff alert: /fsparty reports only live entries", _check_buff_report_reads_live_entries),
        ("buff alert: warlock none, mage and druid tables", _check_buff_warlock_and_classes),
        ("buff alert: combat holds the last display", _check_buff_combat_holds),
        ("buff alert: debuffs first, tray cap", _check_buff_after_debuffs),
        ("buff alert: secret aura fields never compared", _check_buff_secret_fields),
        ("buff alert: tooltip and /fsparty report", _check_buff_tooltip_and_report),
        ("buff alert: dead, ghost and offline members get none", _check_buff_down_members),
        ("buff alert: solo player row alerts", _check_buff_solo_player_row),
        ("buff alert: legacy GetSpellInfo path", _check_buff_legacy_spellinfo),
        ("buff alert: unreadable known check never claims", _check_buff_unreadable_known),
        ("buff alert: aura read error is unreadable, not empty", _check_buff_aura_read_error),
        ("buff alert: /fsparty buffs default label", _check_buff_report_default_label),
        ("Blizzard party frames: PartyFrame and CompactPartyFrame dimmed, raid untouched",
         _check_blizzard_party_dimmed),
        ("Blizzard party frames: each variant detected on its own",
         _check_blizzard_party_one_variant_only),
        ("Blizzard party frames: pre-12.x PartyMemberFrame names not relied on",
         _check_blizzard_party_old_names_not_relied_on),
        ("Blizzard party frames: late pool members re-swept on GROUP_ROSTER_UPDATE",
         lambda: _check_blizzard_party_late_frames("GROUP_ROSTER_UPDATE")),
        ("Blizzard party frames: re-swept on PLAYER_ENTERING_WORLD",
         lambda: _check_blizzard_party_late_frames("PLAYER_ENTERING_WORLD")),
        ("Blizzard party frames: re-swept on EDIT_MODE_LAYOUTS_UPDATED (raid-style toggle)",
         lambda: _check_blizzard_party_late_frames("EDIT_MODE_LAYOUTS_UPDATED")),
        ("Blizzard party frames: sweep waits out combat",
         _check_blizzard_party_sweep_waits_out_combat),
        ("Blizzard party frames: a sweep error is contained, logged once, others still swept",
         _check_blizzard_party_sweep_error_is_contained),
        ("Blizzard party frames: mouse off on aura containers, health bar, compact buttons",
         _check_blizzard_party_mouse_reaches_descendants),
        ("Blizzard party frames: lazily made aura buttons swept on UNIT_AURA, coalesced, not in combat",
         _check_blizzard_party_lazy_aura_buttons),
        ("layout proportions and bounds", lambda: _check_layout(_runtime())),
        ("native percent", lambda: _check_readout(True, 37, 100, .37, "live", "37%")),
        ("native percent with secret health", lambda: _check_readout(
            True, 0, 0, .73, "live", "73%", secret=True)),
        ("plain fallback percent", lambda: _check_readout(False, 37, 100, .37, "live", "37%")),
        ("dead state", lambda: _check_readout(True, 0, 100, 0, "dead", "Dead")),
        ("ghost state", lambda: _check_readout(True, 0, 100, 0, "ghost", "Ghost")),
        ("offline state", lambda: _check_readout(True, 37, 100, .37, "offline", "Offline")),
    ]
    failures = 0
    for name, check in cases:
        try:
            check()
        except (AssertionError, RuntimeError, LuaError, LookupError, AttributeError, TypeError) as exc:
            print(f"FAIL: {name}: {exc}")
            failures += 1
        else:
            print(f"PASS: {name}")
    print(f"{len(cases) - failures}/{len(cases)} party regressions passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
