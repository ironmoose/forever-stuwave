#!/usr/bin/env python3
"""Exercise the raid grid (RaidFrames.lua) against a headless WoW API.

Loads the real Layout, Config, FrameHelpers, PartyFrames and RaidFrames over the party harness's
mock client, plus a per-unit raid roster: GetNumGroupMembers, GetRaidRosterInfo, UnitInRaid and a
health, power, class, name, role, range and aura record for every raid token. Secure frames (a
SecureUnitButtonTemplate button and every frame above one) raise on SetPoint, SetSize, Show and Hide
under combat lockdown, the way the client blocks them, and every refusal is recorded.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"


def _load_party_harness():
    spec = importlib.util.spec_from_file_location("partyframes_harness", HERE / "partyframes-harness.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = _load_party_harness()

RAID_KEY = "raid.shown"
PARTY_KEY = "gunsight.pieces.party"

# The two looks (mockups/raid-frames-2026-11-09.html, its A and C spec objects): cell size, column
# gap, row gap and the group label band above the cells.
LOOK_A = {"w": 84, "h": 30, "gx": 4, "gy": 3, "hdr": 12}
LOOK_C = {"w": 58, "h": 40, "gx": 3, "gy": 3, "hdr": 12}

RAID_MOCK = r"""
__members={}
__playerIndex=1
__playerIndexSecret=false
__unitIsUnitSecret=false
__subSecret=false
__rangeSecret=false
__auraReads=0
__unitDebuffs={}
__watched={}
__blocked={}
__combat=false
function InCombatLockdown() return __combat end
function IsInGroup() return true end

-- A record per raid token; "player" is the member at __playerIndex, or __solo outside a raid.
__solo={name='Solo',class=__playerClass,sub=1,hp=1,max=1000,power=50,powerMax=100,powerType=0,
    state='live',role='NONE'}
local function memberOf(unit)
    if type(unit)~='string' then return nil end
    if unit=='player' then return __members[__playerIndex] or __solo end
    local i=tonumber(unit:match('^raid(%d+)$'))
    return i and __members[i] or nil
end
__memberOf=memberOf

function GetNumGroupMembers() return #__members end
function GetRaidRosterInfo(i)
    local m=__members[i]
    if not m then return nil end
    local sub=__subSecret and __secret or m.sub
    return m.name,0,sub,60,m.class,m.class,'Zone',m.state~='offline',m.state=='dead','NONE',false
end
function UnitInRaid(unit)
    if unit=='player' then
        if __playerIndexSecret then return __secret end
        return __members[__playerIndex] and __playerIndex or nil
    end
    local i=type(unit)=='string' and tonumber(unit:match('^raid(%d+)$'))
    return i and __members[i] and i or nil
end
-- A secret boolean answer is a plain true that FS.IsSecret flags for the next check (the party
-- harness's __secretPending): code that skips the guard reads it as "this is the player".
local partyUnitIsUnit=UnitIsUnit
function UnitIsUnit(a,b)
    if a=='player' or b=='player' then
        local other=a=='player' and b or a
        if __unitIsUnitSecret then __secretPending=true return true end
        __secretPending=false
        return other=='player' or other=='raid'..__playerIndex
    end
    return partyUnitIsUnit(a,b)
end
function UnitExists(unit) return memberOf(unit)~=nil end
function UnitIsPlayer() return true end
function UnitIsConnected(unit) local m=memberOf(unit) return not m or m.state~='offline' end
function UnitIsDeadOrGhost(unit)
    local m=memberOf(unit) return m~=nil and (m.state=='dead' or m.state=='ghost')
end
function UnitIsGhost(unit) local m=memberOf(unit) return m~=nil and m.state=='ghost' end
function UnitHealth(unit)
    local m=memberOf(unit) if not m then return 0 end
    if m.secret then return __secret end
    return m.hp*m.max
end
function UnitHealthMax(unit)
    local m=memberOf(unit) if not m then return 0 end
    if m.secret then return __secret end
    return m.max
end
function UnitHealthPercent(unit,usePredicted,curve)
    assert(usePredicted==false,'UnitHealthPercent predicted flag must be false')
    local m=memberOf(unit)
    local f=m and m.hp or 0
    if not curve then
        if m and m.secret then return setmetatable({secret=true,nativeNumber=f},getmetatable(__secret)) end
        return f
    end
    if m and m.secret and curve.kind~=Enum.LuaCurveType.Step then
        assert(#curve.points==2 and curve.points[1][1]==0 and curve.points[1][2]==0
            and curve.points[2][1]==1 and curve.points[2][2]==100,
            'secret-safe text percent requires native scale-to-100 curve')
        return setmetatable({secret=true,nativeNumber=f*100},getmetatable(__secret))
    end
    local previous=curve.points[1]
    for _,p in ipairs(curve.points) do
        if f<p[1] then
            if curve.kind==Enum.LuaCurveType.Step then return previous[2] end
            return previous[2]+(f-previous[1])/(p[1]-previous[1])*(p[2]-previous[2])
        end
        previous=p
    end
    return previous[2]
end
function UnitPower(unit)
    local m=memberOf(unit) if not m then return 0 end
    if m.secret then return __secret end
    return m.power
end
function UnitPowerMax(unit)
    local m=memberOf(unit) if not m then return 0 end
    if m.secret then return __secret end
    return m.powerMax
end
function UnitPowerType(unit) local m=memberOf(unit) return (m and m.powerType) or 0,'MANA' end
function UnitClass(unit)
    local m=memberOf(unit)
    if unit=='player' then
        return __playerClass:sub(1,1)..__playerClass:sub(2):lower(),__playerClass
    end
    if not m then return nil end
    if m.classSecret then return __secret,__secret end
    return m.class:sub(1,1)..m.class:sub(2):lower(),m.class
end
-- A secret name is a table with no string methods: name:upper() on it throws.
__secretName=setmetatable({secret=true},{__eq=function() error('compare on secret name') end})
function UnitName(unit)
    local m=memberOf(unit)
    if m and m.nameSecret then return __secretName end
    return m and m.name or nil
end
function GetUnitName(unit) return UnitName(unit) end
function UnitGroupRolesAssigned(unit) local m=memberOf(unit) return m and m.role or 'NONE' end
-- UnitInRange: (inRange, checked). Under __rangeSecret the answer is a secret boolean, modelled as a
-- table that throws on compare; a truth test on it is always true (so a guard-free branch reads every
-- member as in range).
function UnitInRange(unit)
    local m=memberOf(unit)
    if not m then return false,false end
    local v=not m.far
    if __rangeSecret then return setmetatable({secret=true,native=v},getmetatable(__secret)),true end
    return v,true
end
function Region_SetAlphaFromBoolean(self,v,a,b)
    if type(v)=='table' then v=v.native end
    self:SetAlpha(v and a or b)
end

-- Per-unit harmful auras: __unitDebuffs[unit] is a list of dispel types. Every read is counted.
local function raidAuraAt(unit,index,filter)
    __auraReads=__auraReads+1
    if filter:find('HELPFUL') then return nil end
    local kept={}
    for _,d in ipairs(__unitDebuffs[unit] or {}) do
        if not filter:find('RAID') or __raid[d] then kept[#kept+1]=d end
    end
    local d=kept[index]
    if d then
        return {name='Debuff '..d,icon='icon',applications=1,dispelName=d,duration=0,
            expirationTime=0,sourceUnit='target'}
    end
end
C_UnitAuras={GetAuraDataByIndex=raidAuraAt}
FS.AurasReadable=function() return not InCombatLockdown() end

RAID_CLASS_COLORS={PRIEST={r=.9,g=.8,b=.1},WARRIOR={r=.78,g=.61,b=.43},MAGE={r=.25,g=.78,b=.92},
    SHAMAN={r=0,g=.44,b=.87}}

__timers={}
__tickers={}
C_Timer={
    After=function(_,fn) __timers[#__timers+1]=fn end,
    NewTicker=function(interval,fn)
        local t={interval=interval,fn=fn,cancelled=false}
        function t:Cancel() self.cancelled=true end
        __tickers[#__tickers+1]=t
        return t
    end,
}
-- Bounded: a timer that queues another runs in the next round, at most five rounds.
function __runTimers()
    for _=1,5 do
        local due=__timers __timers={}
        if #due==0 then return end
        for _,fn in ipairs(due) do fn() end
    end
end
function __tick() for _,t in ipairs(__tickers) do if not t.cancelled then t.fn() end end end

function RegisterUnitWatch(f) __watched[#__watched+1]=f f.unitWatched=true end

-- Secure frames: a SecureUnitButtonTemplate button and every frame above it (up to UIParent) refuse
-- these calls in combat, and each refusal is recorded in __blocked.
local GUARDED={'SetPoint','ClearAllPoints','SetAllPoints','SetSize','SetWidth','SetHeight','SetScale',
    'Show','Hide','SetShown','SetAttribute'}
local function guard(f)
    if f.guarded then return end
    f.guarded=true
    for _,m in ipairs(GUARDED) do
        local orig=f[m]
        f[m]=function(self,...)
            if InCombatLockdown() then
                __blocked[#__blocked+1]=tostring(self.name or self.kind)..':'..m
                error('ADDON_ACTION_BLOCKED: '..m,0)
            end
            return orig(self,...)
        end
    end
end
local partyCreate=CreateFrame
function CreateFrame(kind,name,parent,template,...)
    local f=partyCreate(kind,name,parent,template,...)
    f.template=template
    f.SetAlphaFromBoolean=Region_SetAlphaFromBoolean
    f.attrs={}
    local setAttribute=f.SetAttribute
    f.SetAttribute=function(self,k,v) self.attrs[k]=v return setAttribute(self,k,v) end
    f.RegisterForClicks=function(self,...) self.clicks=table.concat({...},',') end
    f.RegisterUnitEvent=function(self,event,...)
        self.registered[event]=true
        self.unitFilter=self.unitFilter or {}
        self.unitFilter[event]={...}
    end
    f.IsProtected=function(self) return self.guarded==true end
    if template=='SecureUnitButtonTemplate' then
        f.secure=true
        guard(f)
        local p=parent
        while p and p~=UIParent do guard(p) p=p.parent end
    end
    return f
end

-- Fires `event` for `unit` on every frame registered for it whose unit filter (if any) lists it.
function __fireUnit(event,unit)
    for _,frame in ipairs(__frames) do
        if frame.registered[event] and frame.scripts.OnEvent then
            local filter=frame.unitFilter and frame.unitFilter[event]
            local match=filter==nil or #filter==0
            for _,u in ipairs(filter or {}) do if u==unit then match=true end end
            if match then frame.scripts.OnEvent(frame,event,unit) end
        end
    end
end
"""

# CompactRaidFrameContainer's children on this client (Blizzard_CompactRaidFrameContainer.lua and
# CompactRaidGroup.lua): flow unit frames "CompactRaidFrameN" made lazily as its children, and
# group frames "CompactRaidGroupN" with members "CompactRaidGroupNMemberM", each unit frame holding
# buttons of its own. Every one throws on Hide, HookScript, SetScript and SetParent.
BLIZZARD_RAID = r"""
function __blizzRaidUnit(name,parent) return __blizzCompactUnit(name,parent) end
function __blizzRaid()
    local c=CompactRaidFrameContainer
    for i=1,3 do __blizzRaidUnit('CompactRaidFrame'..i,c) end
    for g=1,2 do
        local group=__blizzFrame('Frame','CompactRaidGroup'..g,c)
        for m=1,5 do __blizzRaidUnit('CompactRaidGroup'..g..'Member'..m,group) end
    end
end
__blizzRaid()
function __underContainer(f)
    while f do
        if f.name=='CompactRaidFrameContainer' then return true end
        f=f.parent
    end
    return false
end
"""

TRACK_PARTY = P.TRACK_CONTAINER


def _theme_tokens_lua() -> str:
    extra = " ".join(
        "FS.Theme.{0}={{{1}}}".format(n, ",".join(repr(v) for v in P._theme_color(n)))
        for n in ("COLOR_HEALTH", "COLOR_BORDER", "COLOR_RED"))
    return P._theme_tokens_lua() + " " + extra


def _runtime(*, before_load: str = "", parent_height: int = 1440, player_class: str = "PRIEST",
             quiet: bool = True) -> LuaRuntime:
    rt = LuaRuntime(unpack_returned_tuples=False)
    rt.execute(P.MOCK)
    rt.execute(_theme_tokens_lua())
    rt.execute(f"__playerClass='{player_class}'")
    rt.execute(TRACK_PARTY)
    rt.execute(RAID_MOCK)
    rt.execute(P.BLIZZARD_PARTY)
    rt.execute("__blizzParty(true)")
    rt.execute(BLIZZARD_RAID)
    rt.execute("function UnitGUID() return 'Player-1-AAAA' end")
    if before_load:
        rt.execute(before_load)
    rt.globals().UIParent.SetHeight(rt.globals().UIParent, parent_height)
    load = rt.eval(P.LOAD)
    fs = rt.globals().FS
    load((ADDON / "Core/Layout.lua").read_text(encoding="utf-8"), "@Core/Layout.lua", fs)
    rt.eval(P.LOAD_AS_ADDON)(
        (ADDON / "Core/Config.lua").read_text(encoding="utf-8"), "@Core/Config.lua", "forever-stuwave", fs)
    for filename in ("Core/FrameHelpers.lua", "Modules/UnitFrames/PartyFrames.lua"):
        load((ADDON / filename).read_text(encoding="utf-8"), f"@{filename}", fs)
    rt.execute("__tickersBeforeRaid=#__tickers __framesBeforeRaid=#__frames")
    load((ADDON / "Modules/UnitFrames/RaidFrames.lua").read_text(encoding="utf-8"),
         "@Modules/UnitFrames/RaidFrames.lua", fs)
    if quiet:
        _assert_quiet(rt)
    return rt


def _assert_quiet(rt: LuaRuntime) -> None:
    messages = list(rt.globals().__messages.values())
    assert not messages, messages


def _assert_unblocked(rt: LuaRuntime) -> None:
    blocked = list(rt.globals().__blocked.values())
    assert not blocked, f"protected calls in combat: {blocked}"


def _event(rt: LuaRuntime, name: str, arg: str = "nil") -> None:
    P._event(rt, name, arg)


def _unit_event(rt: LuaRuntime, name: str, unit: str) -> None:
    rt.execute(f"__fireUnit('{name}','{unit}')")


def _settle(rt: LuaRuntime) -> None:
    rt.execute("__runTimers()")


def _client(*, saved: str = "", before_load: str = "", parent_height: int = 1440,
            player_class: str = "PRIEST") -> LuaRuntime:
    """A client past ADDON_LOADED and PLAYER_LOGIN, out of a raid, with every deferred call run."""
    rt = _runtime(before_load=saved + "\n" + before_load, parent_height=parent_height,
                  player_class=player_class)
    _event(rt, "ADDON_LOADED", "'forever-stuwave'")
    _event(rt, "PLAYER_LOGIN")
    _settle(rt)
    rt.execute("FS.partyContainer.log = {}")
    return rt


CLASSES = ("WARRIOR", "MAGE", "SHAMAN", "PRIEST")


def _roster(rt: LuaRuntime, n: int, *, groups=None, player: int = 1, fire: bool = True,
            **fields) -> None:
    """Puts `n` members in the raid (subgroup ceil(i / 5) unless `groups` lists them), the player
    at index `player`, and fires GROUP_ROSTER_UPDATE plus the deferred calls."""
    lines = ["__members={}"]
    for i in range(1, n + 1):
        sub = groups[i - 1] if groups else (i - 1) // 5 + 1
        cls = rt.globals().__playerClass if i == player else CLASSES[i % len(CLASSES)]
        lines.append(
            f"__members[{i}]={{name='Member{i}',class='{cls}',sub={sub},hp=1,max=1000,power=50,"
            f"powerMax=100,powerType=0,state='live',role='DAMAGER'}}")
    lines.append(f"__playerIndex={player} __inRaid={'true' if n > 0 else 'false'}")
    for key, value in fields.items():
        lines.append(f"for _,m in ipairs(__members) do m.{key}={value} end")
    rt.execute("\n".join(lines))
    if fire:
        _event(rt, "GROUP_ROSTER_UPDATE")
        _settle(rt)


def _member(rt: LuaRuntime, i: int, **fields) -> None:
    rt.execute(" ".join(f"__members[{i}].{k}={v}" for k, v in fields.items()))


def _cell(rt: LuaRuntime, i: int):
    return rt.eval("FS.raidCells")[i]


def _parts(rt: LuaRuntime, i: int):
    return _cell(rt, i).parts


def _state(rt: LuaRuntime):
    return rt.eval("FS.RaidFrames.state")


def _top_left(frame) -> tuple[float, float]:
    p = frame.points.TOPLEFT
    assert p is not None, f"{frame.name or frame.kind} has no TOPLEFT point"
    return p.x, p.y


def _close(a: float, b: float, tol: float = 1e-6) -> bool:
    return math.isclose(a, b, abs_tol=tol)


def _rgb(region) -> tuple[float, float, float]:
    c = region.color
    return c[1], c[2], c[3]


def _same_rgb(actual, expected) -> bool:
    return all(_close(a, e, 1e-4) for a, e in zip(list(actual)[:3], list(expected)[:3], strict=True))


def _shown(region) -> bool:
    """Shown up its parent chain (the mock's IsShown is the region's own flag)."""
    f = region
    while f is not None:
        if not f.shown:
            return False
        f = f.parent
    return True


def _effective_alpha(region) -> float:
    a, f = 1.0, region
    while f is not None:
        a *= f.alpha
        f = f.parent
    return a


def _grid_size(spec: dict, columns: int, rows: int) -> tuple[float, float]:
    return (columns * spec["w"] + (columns - 1) * spec["gx"],
            spec["hdr"] + rows * spec["h"] + (rows - 1) * spec["gy"])


def _expect_cell_at(rt, i: int, spec: dict, column: int, row: int) -> None:
    cell = _cell(rt, i)
    x, y = _top_left(cell)
    want = (column * (spec["w"] + spec["gx"]), -(spec["hdr"] + row * (spec["h"] + spec["gy"])))
    assert _close(x, want[0]) and _close(y, want[1]), f"cell {i} at {(x, y)}, want {want}"
    assert P._same(rt, cell.points.TOPLEFT.rel, rt.eval("FS.raidContent")), f"cell {i} is not seated on the grid"
    assert (cell.w, cell.h) == (spec["w"], spec["h"]), f"cell {i} is {cell.w}x{cell.h}"


# ---------------------------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------------------------

def _check_forty_secure_cells() -> None:
    """Init builds 40 of our own secure unit buttons, raid1..raid40, each with its attributes set
    once (left click targets, right click opens the unit menu), any-up clicks, a unit watch and a
    non-secure visual child that holds the chrome. Outside a raid the grid is hidden."""
    rt = _client()
    cells = rt.eval("FS.raidCells")
    assert len(cells) == 40, f"{len(cells)} cells"
    # Distinct watched frames, counted in Lua (lupa hands back a fresh wrapper per access).
    watched = rt.eval("(function() local seen, n = {}, 0 for _, f in ipairs(__watched) do"
                      " if not seen[f] then seen[f] = true n = n + 1 end end return n end)()")
    for i in range(1, 41):
        c = cells[i]
        assert c.kind == "Button" and c.template == "SecureUnitButtonTemplate", f"cell {i}: {c.kind} {c.template}"
        assert c.attrs.unit == f"raid{i}" and c.unit == f"raid{i}", f"cell {i} unit {c.attrs.unit}"
        assert c.attrs["*type1"] == "target" and c.attrs["*type2"] == "togglemenu", f"cell {i} click attributes"
        assert c.clicks == "AnyUp", f"cell {i} clicks {c.clicks}"
        assert c.unitWatched, f"cell {i} has no unit watch"
        assert c.visual is not None and P._same(rt, c.visual.parent, c) and c.visual.template is None, (
            f"cell {i} has no plain visual child")
        assert c.name == f"ForeverSTUwaveRaidCell{i}", c.name
    assert watched >= 40, f"{watched} unit watches"
    container = rt.eval("FS.raidContainer")
    assert container.name == "ForeverSTUwaveRaidContainer"
    assert not container.shown, "the grid shows outside a raid"
    assert rt.eval("FS.RaidFrames.CONFIG_KEY") == RAID_KEY
    assert rt.eval(f"FS.Config.Get('{RAID_KEY}')") is True, "on by default"
    _assert_quiet(rt)


def _check_look_a_at_ten() -> None:
    """Ten members or fewer: look A, 84 x 30 cells in group columns 4 apart, rows 3 apart under a
    12 high label band. The grid is sized from the cells shown and its top left is the party
    frame's top left."""
    rt = _client()
    _roster(rt, 10)
    assert _state(rt).look == "A"
    container, content = rt.eval("FS.raidContainer"), rt.eval("FS.raidContent")
    assert container.shown, "the grid did not show in a raid"
    for i in range(1, 11):
        _expect_cell_at(rt, i, LOOK_A, (i - 1) // 5, (i - 1) % 5)
        parts = _parts(rt, i)
        assert parts.look == "A" and _shown(parts.frame), f"cell {i} does not show look A"
    w, h = _grid_size(LOOK_A, 2, 5)
    assert (w, h) == (172, 174)
    assert (content.w, content.h) == (w, h), f"grid {content.w}x{content.h}"
    scale = rt.eval("FS.Layout.Scale()")
    assert _close(container.w, w * scale) and _close(container.h, h * scale)
    party = rt.eval("FS.partyContainer")
    grid, seat = container.GetBounds(container), party.GetBounds(party)
    assert _close(grid.x, seat.x) and _close(grid.y, seat.y), (
        f"grid top left {(grid.x, grid.y)} is not the party top left {(seat.x, seat.y)}")
    _assert_quiet(rt)


def _check_look_c_at_eleven_and_forty() -> None:
    """Eleven or more: look C, 58 x 40 tiles 3 apart. 11 members fill three columns; 40 fill all
    eight. Going from ten to eleven switches the look out of combat."""
    rt = _client()
    _roster(rt, 10)
    a_parts = _parts(rt, 1)
    _roster(rt, 11)
    assert _state(rt).look == "C"
    assert not _shown(a_parts.frame), "look A still shows under look C"
    for i in range(1, 12):
        _expect_cell_at(rt, i, LOOK_C, (i - 1) // 5, (i - 1) % 5)
        assert _parts(rt, i).look == "C"
    content = rt.eval("FS.raidContent")
    assert (content.w, content.h) == _grid_size(LOOK_C, 3, 5) == (180, 224)
    _roster(rt, 40)
    assert (content.w, content.h) == _grid_size(LOOK_C, 8, 5) == (485, 224)
    for i in range(1, 41):
        _expect_cell_at(rt, i, LOOK_C, (i - 1) // 5, (i - 1) % 5)
    _roster(rt, 7)
    assert _state(rt).look == "A" and _shown(_parts(rt, 1).frame) and _parts(rt, 1).look == "A"
    assert (content.w, content.h) == _grid_size(LOOK_A, 2, 5)
    _assert_quiet(rt)


def _check_height_follows_the_tallest_column() -> None:
    """Twelve members in two full groups and one pair: the grid is as tall as a full column."""
    rt = _client()
    _roster(rt, 4, groups=[1, 1, 2, 2])
    content = rt.eval("FS.raidContent")
    assert (content.w, content.h) == _grid_size(LOOK_A, 2, 2), f"{content.w}x{content.h}"
    _assert_quiet(rt)


def _check_columns_by_subgroup() -> None:
    """One column per subgroup that has members, five cells down by roster order. The player's
    group comes first, then the others ascending; empty groups are skipped. Above each column a
    G<n> label: the player's group pink, the others violet, unused labels hidden."""
    rt = _client()
    groups = [3, 3, 1, 1, 1, 4, 4, 4, 4, 3, 1, 3]
    _roster(rt, 12, groups=groups, player=6)
    assert list(_state(rt).columns.values()) == [4, 1, 3], list(_state(rt).columns.values())
    order = {4: [6, 7, 8, 9], 1: [3, 4, 5, 11], 3: [1, 2, 10, 12]}
    for column, group in enumerate((4, 1, 3)):
        for row, i in enumerate(order[group]):
            _expect_cell_at(rt, i, LOOK_C, column, row)
    labels = rt.eval("FS.raidLabels")
    pink, violet = P._theme_color("COLOR_HEALTH"), P._theme_color("COLOR_BORDER")
    for k, (group, color) in enumerate(((4, pink), (1, violet), (3, violet)), start=1):
        label = labels[k]
        assert label.shown and label.text == f"G{group}", f"label {k}: {label.text}"
        assert _same_rgb(label.textColor.values(), color), f"label G{group} colour {list(label.textColor.values())}"
        x, _ = label.points.LEFT.x, label.points.LEFT.y
        assert _close(x, (k - 1) * (LOOK_C["w"] + LOOK_C["gx"]) + 2), f"label {k} x {x}"
    for k in range(4, 9):
        assert not labels[k].shown, f"label {k} shows with no column under it"
    content = rt.eval("FS.raidContent")
    assert (content.w, content.h) == _grid_size(LOOK_C, 3, 4)
    _assert_quiet(rt)


def _check_secret_subgroup_falls_back() -> None:
    """A secret subgroup is never compared: the member goes to group ceil(i / 5)."""
    rt = _client()
    rt.execute("__subSecret=true")
    _roster(rt, 12, groups=[2] * 12)
    assert list(_state(rt).columns.values()) == [1, 2, 3]
    _expect_cell_at(rt, 11, LOOK_C, 2, 0)
    _assert_quiet(rt)


def _check_player_group_unknown() -> None:
    """With UnitInRaid and UnitIsUnit both secret the player's index is unknown: groups ascend,
    no label is pink and no cell has the tick. With only UnitInRaid secret, UnitIsUnit finds it."""
    rt = _client()
    rt.execute("__playerIndexSecret=true __unitIsUnitSecret=true")
    _roster(rt, 12, groups=[1, 1, 2, 2, 3, 3, 1, 1, 2, 2, 3, 3], player=3)
    assert list(_state(rt).columns.values()) == [1, 2, 3]
    violet = P._theme_color("COLOR_BORDER")
    for k in range(1, 4):
        assert _same_rgb(rt.eval("FS.raidLabels")[k].textColor.values(), violet), f"label {k} is not violet"
    for i in range(1, 13):
        assert not _shown(_parts(rt, i).tick), f"cell {i} has the tick with no known player"
    rt.execute("__unitIsUnitSecret=false")
    _event(rt, "GROUP_ROSTER_UPDATE")
    _settle(rt)
    assert list(_state(rt).columns.values()) == [2, 1, 3], "UnitIsUnit did not find the player"
    assert _shown(_parts(rt, 3).tick)
    _assert_quiet(rt)


def _check_own_cell_tick() -> None:
    """The player's own cell gets a 2 wide pink tick down its left side, outside the cell; no other
    cell has one. Both looks."""
    pink = P._theme_color("COLOR_HEALTH")
    for n, spec in ((10, LOOK_A), (25, LOOK_C)):
        rt = _client()
        _roster(rt, n, player=4)
        for i in range(1, n + 1):
            tick = _parts(rt, i).tick
            assert _shown(tick) == (i == 4), f"{n}-man cell {i} tick shown {_shown(tick)}"
        tick = _parts(rt, 4).tick
        assert tick.w == 2 and tick.h == spec["h"] - (8 if spec is LOOK_A else 10), f"tick {tick.w}x{tick.h}"
        assert tick.points.TOPLEFT.x == -3, tick.points.TOPLEFT.x
        assert _same_rgb(_rgb(tick), pink), "tick is not pink"
        _assert_quiet(rt)


# ---------------------------------------------------------------------------------------------
# Combat: reflow, resize, visibility
# ---------------------------------------------------------------------------------------------

def _check_reflow_waits_out_combat() -> None:
    """A roster change in combat moves and resizes nothing (the grid and its cells are protected):
    the cells' contents refresh, a joiner's cell waits parked clear of the grid, and the reflow and
    the look switch land on PLAYER_REGEN_ENABLED."""
    rt = _client()
    _roster(rt, 10)
    content, container = rt.eval("FS.raidContent"), rt.eval("FS.raidContainer")
    before = (content.w, content.h, container.w, container.h)
    rt.execute("__combat=true")
    _roster(rt, 15)
    _assert_unblocked(rt)
    assert _state(rt).look == "A", "the look switched in combat"
    assert (content.w, content.h, container.w, container.h) == before, "the grid resized in combat"
    # The parked cells sit right of the grid, so a member who joins in combat never covers one.
    grid_right = before[0]
    for i in range(11, 16):
        x, _ = _top_left(_cell(rt, i))
        assert x >= grid_right, f"joiner cell {i} at x {x} overlaps the grid ({grid_right} wide)"
        assert _parts(rt, i).name.text == f"MEMBER{i}", "a joiner's cell was not painted in combat"
    rt.execute("__combat=false")
    _event(rt, "PLAYER_REGEN_ENABLED")
    _settle(rt)
    _assert_unblocked(rt)
    assert _state(rt).look == "C"
    assert (content.w, content.h) == _grid_size(LOOK_C, 3, 5)
    for i in range(1, 16):
        _expect_cell_at(rt, i, LOOK_C, (i - 1) // 5, (i - 1) % 5)
    _assert_quiet(rt)


def _check_party_rows_give_way_in_a_raid() -> None:
    """In a raid the grid shows and the party rows hide (their wanted state is untouched); out of
    it the grid hides and the party rows come back. In combat neither moves until regen."""
    rt = _client()
    party = rt.eval("FS.partyContainer")
    assert party.shown
    _roster(rt, 10)
    assert not party.shown and rt.eval("table.concat(FS.partyContainer.log, ',')") == "Hide"
    assert rt.eval("FS.PartyFrames.IsShown()") is True, "the party switch itself was changed"
    _roster(rt, 0)
    assert party.shown and not rt.eval("FS.raidContainer").shown
    assert rt.eval("table.concat(FS.partyContainer.log, ',')") == "Hide,Show@1"
    rt.execute("FS.partyContainer.log={} __combat=true")
    _roster(rt, 10)
    _assert_unblocked(rt)
    assert party.shown and not rt.eval("FS.raidContainer").shown, "a raid joined in combat swapped frames"
    rt.execute("__combat=false")
    _event(rt, "PLAYER_REGEN_ENABLED")
    _settle(rt)
    _assert_unblocked(rt)
    assert not party.shown and rt.eval("FS.raidContainer").shown
    # A party switched off stays off when the raid ends.
    rt.execute("FS.PartyFrames.SetShown(false)")
    _roster(rt, 0)
    assert not party.shown, "leaving the raid showed party rows the player had switched off"
    _assert_quiet(rt)


def _check_party_harness_contract() -> None:
    """PartyFrames exports what the grid reuses through one table and a suppress switch."""
    rt = _client()
    for name in ("UpdateRowLowHealth", "UpdateHealthPercentText", "RowDownState", "ReadHealthMax",
                 "ScanDebuffs", "GetDispelColor", "BuildDashEdge", "TintDashes", "ApplyRangeAlpha",
                 "DisableMouseTree"):
        assert rt.eval(f"type(FS.PartyFrames.shared.{name})") == "function", name
    for name in ("ROLE_STYLE", "DISPELS", "POWER_COLORS"):
        assert rt.eval(f"type(FS.PartyFrames.shared.{name})") == "table", name
    assert rt.eval("type(FS.PartyFrames.SetSuppressed)") == "function"


# ---------------------------------------------------------------------------------------------
# The switch and Blizzard's raid frames
# ---------------------------------------------------------------------------------------------

def _blizzard_raid_frames(rt) -> list:
    under = rt.eval("__underContainer")
    return [f for f in rt.eval("__blizz").values() if under(f)]


def _assert_blizzard_raid_untouched(rt, label: str) -> None:
    frames = _blizzard_raid_frames(rt)
    assert len(frames) > 10, "the fixture made no raid frames"
    container = rt.globals().CompactRaidFrameContainer
    assert container.alpha == 1 and rt.eval("next")(container.registered), f"{label}: container dimmed"
    for f in frames:
        assert f.alpha == 1 and f.mouse is True, f"{label}: {f.name or f.kind} was touched"


def _assert_blizzard_raid_silenced(rt, label: str) -> None:
    silenced = rt.eval("__silenced")
    for f in _blizzard_raid_frames(rt):
        assert silenced(f), (f"{label}: {f.name or f.kind} still draws or listens "
                             f"(alpha {_effective_alpha(f)}, mouse {f.mouse})")


def _check_blizzard_raid_dimmed() -> None:
    """While the grid is on, CompactRaidFrameContainer and every frame under it draws nothing,
    takes no mouse and listens to nothing, the dim-not-hide way (the fixture throws on Hide,
    HookScript, SetScript and SetParent). Nothing is touched before PLAYER_LOGIN, when the saved
    switch is known. The manager tab stays the party module's: given back in a raid."""
    rt = _runtime()
    _assert_blizzard_raid_untouched(rt, "before login")
    _event(rt, "ADDON_LOADED", "'forever-stuwave'")
    _event(rt, "PLAYER_LOGIN")
    _settle(rt)
    _assert_blizzard_raid_silenced(rt, "after login")
    _roster(rt, 10)
    manager = rt.globals().CompactRaidFrameManager
    assert manager.alpha == 1 and manager.mouse is True, "the raid manager tab is not back in a raid"
    _assert_quiet(rt)


def _check_blizzard_raid_late_frames() -> None:
    """Unit frames Blizzard makes later are swept one frame after the roster, enter-world and Edit
    Mode layout events (after Blizzard's own handlers), and only out of combat."""
    for event in ("GROUP_ROSTER_UPDATE", "PLAYER_ENTERING_WORLD", "EDIT_MODE_LAYOUTS_UPDATED"):
        rt = _client()
        rt.execute("__late=__blizzRaidUnit('CompactRaidFrame9',CompactRaidFrameContainer)")
        _event(rt, event)
        assert not rt.eval("__silenced")(rt.globals().__late), f"{event}: swept before Blizzard's handlers"
        _settle(rt)
        _assert_blizzard_raid_silenced(rt, f"after {event}")
    rt = _client()
    rt.execute("__late=__blizzRaidUnit('CompactRaidGroup2Member6',CompactRaidGroup2) __combat=true")
    _event(rt, "GROUP_ROSTER_UPDATE")
    _settle(rt)
    assert rt.globals().__late.mouse is True, "swept in combat"
    rt.execute("__combat=false")
    _event(rt, "PLAYER_REGEN_ENABLED")
    _settle(rt)
    _assert_blizzard_raid_silenced(rt, "after combat")
    _assert_quiet(rt)


def _check_switched_off_leaves_blizzard_alone() -> None:
    """raid.shown off: ours never show (in a raid the party rows stay) and Blizzard's raid frames are
    left alone. Switching on dims them and shows the grid; switching off again hides the grid and
    gives the party rows back, and the row asks for a reload to restore Blizzard's (their events
    cannot be put back)."""
    saved = ("ForeverSTUwaveDB={profiles={Default={settings={['" + RAID_KEY + "']=false}}},"
             "profileKeys={},profileLabels={}}")
    rt = _client(saved=saved)
    _roster(rt, 10)
    assert rt.eval("FS.RaidFrames.IsShown()") is False
    assert not rt.eval("FS.raidContainer").shown and rt.eval("FS.partyContainer").shown
    _assert_blizzard_raid_untouched(rt, "switched off")
    assert rt.eval("FS.RaidFrames.NeedsReload()") is None
    assert rt.eval("FS.RaidFrames.SetShown(true)") is True
    _settle(rt)
    assert rt.eval("FS.raidContainer").shown and not rt.eval("FS.partyContainer").shown
    _assert_blizzard_raid_silenced(rt, "switched on")
    assert rt.eval("FS.RaidFrames.NeedsReload()") is None
    rt.execute(f"FS.Config.Set('{RAID_KEY}', false)")
    _settle(rt)
    assert not rt.eval("FS.raidContainer").shown and rt.eval("FS.partyContainer").shown
    line = rt.eval("FS.RaidFrames.NeedsReload()")
    assert line == "Reload to restore the game's raid frames", line
    assert len(line) <= 40
    _assert_quiet(rt)


def _check_switch_in_combat_waits() -> None:
    """Switching the grid off in combat changes nothing protected until regen."""
    rt = _client()
    _roster(rt, 10)
    rt.execute(f"__combat=true FS.Config.Set('{RAID_KEY}', false)")
    _settle(rt)
    _assert_unblocked(rt)
    assert rt.eval("FS.raidContainer").shown
    rt.execute("__combat=false")
    _event(rt, "PLAYER_REGEN_ENABLED")
    _settle(rt)
    assert not rt.eval("FS.raidContainer").shown and rt.eval("FS.partyContainer").shown
    _assert_unblocked(rt)
    _assert_quiet(rt)


# ---------------------------------------------------------------------------------------------
# The edge: dispel, low health, dead and offline
# ---------------------------------------------------------------------------------------------

def _ring(parts):
    return parts.edge.fsSkin.border.ring


def _glow(parts):
    return parts.edge.fsSkin.glow


def _check_dispel_edge() -> None:
    """A debuff the player can remove lights the edge in its dispel colour (a Priest removes Magic,
    not Curse). Look A keeps the cyan edge at full strength with a glow; look C keeps it dim (.55,
    no glow) until something needs the player."""
    magic = P._dispel_colors()["Magic"]
    cyan = P._theme_color("COLOR_POWER")
    for n in (10, 25):
        rt = _client()
        _roster(rt, n)
        rt.execute("__unitDebuffs.raid3={'Magic'} __unitDebuffs.raid4={'Curse'}")
        _unit_event(rt, "UNIT_AURA", "raid3")
        _unit_event(rt, "UNIT_AURA", "raid4")
        lit, plain = _parts(rt, 3), _parts(rt, 4)
        assert _same_rgb(_rgb(_ring(lit)), magic), f"{n}: Magic edge {_rgb(_ring(lit))}"
        assert _same_rgb(_rgb(_ring(plain)), cyan), f"{n}: an undispellable Curse lit the edge"
        assert _shown(_ring(lit)) and _shown(_glow(lit)) and _glow(lit).alphaSlot > 0
        if n == 25:
            assert _close(_ring(plain).color[4], 0.55), f"look C cyan edge alpha {_ring(plain).color[4]}"
            assert not _shown(_glow(plain)) or _glow(plain).alphaSlot == 0, "look C cyan edge glows"
            assert _close(_ring(lit).color[4], 1)
        else:
            assert _close(_ring(plain).color[4], 1) and _shown(_glow(plain))
        rt.execute("__unitDebuffs.raid3={}")
        _unit_event(rt, "UNIT_AURA", "raid3")
        assert _same_rgb(_rgb(_ring(_parts(rt, 3))), cyan), "the dispel colour stayed after the debuff went"
        _assert_quiet(rt)


def _check_low_health_red() -> None:
    """At 35% or less the red edge layer comes in, the base edge goes out and the percent shows
    in red; above it the reverse. Both looks, through the engine-side curves."""
    red = P._theme_color("COLOR_RED")
    for n in (10, 25):
        rt = _client()
        _roster(rt, n)
        _member(rt, 2, hp=0.3)
        _unit_event(rt, "UNIT_HEALTH", "raid2")
        parts = _parts(rt, 2)
        assert parts.red.alpha == 1 and parts.edge.alpha == 0, f"{n}: low edge {parts.red.alpha}/{parts.edge.alpha}"
        assert parts.pct.alpha == 1 and parts.pct.text == "30%", f"{n}: percent {parts.pct.text} at {parts.pct.alpha}"
        assert _same_rgb(parts.pct.textColor.values(), red), "the percent is not red"
        assert _same_rgb(_rgb(parts.red.fsSkin.border.ring), red)
        _member(rt, 2, hp=0.5)
        _unit_event(rt, "UNIT_HEALTH", "raid2")
        assert parts.red.alpha == 0 and parts.edge.alpha == 1 and parts.pct.alpha == 0
        _assert_quiet(rt)


def _check_dead_and_offline_dashed() -> None:
    """Dead or offline: steel dashes replace the ring and glow, DEAD or OFF shows, the name turns
    steel and the cell's contents drop to .55. Back to live, the ring returns."""
    steel = P._theme_color("COLOR_STEEL")
    for n in (10, 25):
        rt = _client()
        _roster(rt, n)
        _member(rt, 3, state="'dead'", hp=0)
        _unit_event(rt, "UNIT_HEALTH", "raid3")
        parts = _parts(rt, 3)
        assert _shown(parts.dashHost) and not _shown(_ring(parts)) and not _shown(_glow(parts))
        dashes = list(parts.dashes.values())
        assert dashes and all(_same_rgb(_rgb(d), steel) for d in dashes), "dashes are not steel"
        assert parts.state.text == "DEAD" and _shown(parts.state), f"state text {parts.state.text}"
        assert _same_rgb(parts.name.textColor.values(), steel), "a dead member's name is not steel"
        assert _close(parts.name.alpha, 0.55), f"dimmed name alpha {parts.name.alpha}"
        assert parts.red.alpha == 0 and parts.pct.alpha == 0, "a dead member reads as low health"
        _member(rt, 3, state="'offline'")
        _unit_event(rt, "UNIT_CONNECTION", "raid3")
        assert parts.state.text == "OFF", parts.state.text
        _member(rt, 3, state="'live'", hp=1)
        _unit_event(rt, "UNIT_HEALTH", "raid3")
        assert not _shown(parts.dashHost) and _shown(_ring(parts)) and not _shown(parts.state)
        assert _close(parts.name.alpha, 1)
        _assert_quiet(rt)


# ---------------------------------------------------------------------------------------------
# Secrets, range, auras
# ---------------------------------------------------------------------------------------------

def _check_secrets_never_compared() -> None:
    """Secret health, max, power, names and range go only to engine setters: a whole roster with
    every value secret reflows, updates and ticks without one compare, and the range still dims
    an out-of-range member through SetAlphaFromBoolean."""
    for n in (10, 25):
        rt = _client()
        rt.execute("__rangeSecret=true")
        _roster(rt, n, secret="true", nameSecret="true")
        _member(rt, 5, far="true")
        for event in ("UNIT_HEALTH", "UNIT_MAXHEALTH", "UNIT_POWER_UPDATE", "UNIT_MAXPOWER",
                      "UNIT_NAME_UPDATE", "UNIT_AURA", "UNIT_CONNECTION"):
            _unit_event(rt, event, "raid5")
        rt.execute("__tick()")
        g = rt.globals()
        parts = _parts(rt, 5)
        assert P._same(rt, parts.health.value, g.__secret) and P._same(rt, parts.health.max, g.__secret)
        assert P._same(rt, parts.mana.value, g.__secret)
        assert P._same(rt, parts.name.text, g.__secretName), "a secret name did not go straight to SetText"
        assert _close(_cell(rt, 5).visual.alpha, 0.4), f"far member alpha {_cell(rt, 5).visual.alpha}"
        assert _close(_cell(rt, 6).visual.alpha, 1.0)
        _assert_quiet(rt)


def _check_range_one_ticker() -> None:
    """One shared range ticker for all 40 cells and no per-frame OnUpdate. An out-of-range member's
    whole cell is at .4; the player's own cell never dims."""
    rt = _client()
    g = rt.globals()
    assert len(g.__tickers) - g.__tickersBeforeRaid == 1, "the grid needs exactly one ticker"
    frames = list(g.__frames.values())[g.__framesBeforeRaid:]
    assert not [f for f in frames if f.scripts.OnUpdate], "a raid frame runs an OnUpdate"
    _roster(rt, 10, player=2)
    _member(rt, 4, far="true")
    _member(rt, 2, far="true")
    rt.execute("__tick()")
    assert _close(_cell(rt, 4).visual.alpha, 0.4) and _close(_cell(rt, 3).visual.alpha, 1.0)
    assert _close(_cell(rt, 2).visual.alpha, 1.0), "the player's own cell dimmed"
    _assert_quiet(rt)


def _check_auras_gated_in_combat() -> None:
    """Aura reads are refused under lockdown (a refusal leaks): UNIT_AURA in combat reads nothing,
    and PLAYER_REGEN_ENABLED scans again. Auras are event driven: the range ticker reads none."""
    magic = P._dispel_colors()["Magic"]
    rt = _client()
    _roster(rt, 10)
    rt.execute("__combat=true __auraReads=0 __unitDebuffs.raid3={'Magic'}")
    _unit_event(rt, "UNIT_AURA", "raid3")
    rt.execute("__tick()")
    assert rt.globals().__auraReads == 0, f"{rt.globals().__auraReads} aura reads in combat"
    assert not _same_rgb(_rgb(_ring(_parts(rt, 3))), magic)
    rt.execute("__combat=false")
    _event(rt, "PLAYER_REGEN_ENABLED")
    _settle(rt)
    assert rt.globals().__auraReads > 0
    assert _same_rgb(_rgb(_ring(_parts(rt, 3))), magic), "the regen scan did not light the edge"
    rt.execute("__auraReads=0 __tick()")
    assert rt.globals().__auraReads == 0, "the range ticker reads auras"
    # The shared retry chain (FS.OnAurasReadable) repaints too.
    rt.execute("__unitDebuffs.raid3={} for _,fn in ipairs(__readableCallbacks) do fn() end")
    assert not _same_rgb(_rgb(_ring(_parts(rt, 3))), magic), "the readable callback did not rescan"
    _assert_quiet(rt)


# ---------------------------------------------------------------------------------------------
# Contents: names, class colours, roles, rails
# ---------------------------------------------------------------------------------------------

def _check_names_classes_roles() -> None:
    """Look A: the name upper-cased in the class colour, the role letter before it. Look C: the
    name as is, in white. A secret class token falls back to the flat colour; NONE hides the
    role."""
    rt = _client()
    _roster(rt, 10)
    _member(rt, 2, role="'HEALER'")
    _member(rt, 3, role="'NONE'")
    rt.execute("__members[4].classSecret=true")
    _event(rt, "PLAYER_ROLES_ASSIGNED")
    _event(rt, "GROUP_ROSTER_UPDATE")
    _settle(rt)
    parts = _parts(rt, 2)
    cls = rt.eval("RAID_CLASS_COLORS")[CLASSES[2 % 4]]
    assert parts.name.text == "MEMBER2", parts.name.text
    assert _same_rgb(parts.name.textColor.values(), (cls.r, cls.g, cls.b)), "look A name not in class colour"
    assert parts.role.text == "H" and _shown(parts.role)
    assert _same_rgb(parts.role.textColor.values(), P._theme_color("COLOR_HEAL"))
    assert not _shown(_parts(rt, 3).role), "role NONE still shows a letter"
    assert _same_rgb(parts.health.fsRail.spark.color.values(), (cls.r, cls.g, cls.b)), "health rail not in class colour"
    assert _same_rgb(_parts(rt, 4).name.textColor.values(), P._theme_color("COLOR_HEALTH")), (
        "a secret class token did not fall back")
    _roster(rt, 25)
    _member(rt, 2, role="'TANK'")
    _event(rt, "PLAYER_ROLES_ASSIGNED")
    parts = _parts(rt, 2)
    assert parts.name.text == "Member2", parts.name.text
    assert _same_rgb(parts.name.textColor.values(), (1, 1, 1)), "look C name is not white"
    assert parts.role.text == "T" and _same_rgb(parts.role.textColor.values(), P._theme_color("COLOR_POWER"))
    _assert_quiet(rt)


def _check_look_c_fill() -> None:
    """Look C fills bottom up: a vertical bar inside the tile, its fill a vertical gradient from the
    class colour mixed 35% into #0d0620 at the foot to the class colour at the top, a 1 high white
    gloss at .6 on the fill's top edge, and the corners erased at the tile's chamfer."""
    rt = _client()
    _roster(rt, 25)
    parts = _parts(rt, 2)
    bar = parts.health
    cls = rt.eval("RAID_CLASS_COLORS")[CLASSES[2 % 4]]
    grad = bar.GetStatusBarTexture(bar).gradient
    assert grad is not None and grad.orientation == "VERTICAL", "no vertical gradient on the fill"
    deep = tuple(0.65 * b / 255 + 0.35 * c for b, c in zip((13, 6, 32), (cls.r, cls.g, cls.b)))
    assert _same_rgb((grad.min.r, grad.min.g, grad.min.b), deep), f"foot {grad.min.r, grad.min.g, grad.min.b}"
    assert _same_rgb((grad.max.r, grad.max.g, grad.max.b), (cls.r, cls.g, cls.b)), "top is not the class colour"
    gloss = parts.gloss
    assert gloss.h == 1 and P._same(rt, gloss.points.TOPLEFT.rel, bar.GetStatusBarTexture(bar))
    assert _same_rgb(_rgb(gloss), (1, 1, 1)) and _close(gloss.color[4], 0.6)
    assert parts.corners.cutErase is not None and parts.corners.cutErase.chamfer == 4
    _assert_quiet(rt)


def _check_layout_entry() -> None:
    """FS.Layout.raid records the grid's seat: its top left at the party frame's top left. With no
    party container the grid seats from that entry."""
    rt = _client()
    entry, party = rt.eval("FS.Layout.raid"), rt.eval("FS.Layout.party")
    assert (entry.point, entry.relPoint) == ("TOPLEFT", "CENTER")
    assert _close(entry.x, party.x - party.w / 2) and _close(entry.y, party.y + party.h / 2)
    rt.execute("FS.partyContainer=nil")
    _roster(rt, 10)
    point = rt.eval("FS.raidContainer").points.TOPLEFT
    assert P._same(rt, point.rel, rt.globals().UIParent) and point.rp == "CENTER"
    assert _close(point.x, entry.x) and _close(point.y, entry.y)
    _assert_quiet(rt)


def _check_rescaled_grid() -> None:
    """At a 1200 high UI the grid is in design units under the layout scale."""
    rt = _client(parent_height=1200)
    _roster(rt, 10)
    scale = 1200 / 1440
    content, container = rt.eval("FS.raidContent"), rt.eval("FS.raidContainer")
    assert _close(content.scale, scale), content.scale
    assert _close(container.w, 172 * scale) and _close(container.h, 174 * scale)
    _assert_quiet(rt)


def main() -> int:
    cases = [
        ("40 secure cells built at Init", _check_forty_secure_cells),
        ("look A at ten members", _check_look_a_at_ten),
        ("look C at eleven and forty", _check_look_c_at_eleven_and_forty),
        ("grid height follows the tallest column", _check_height_follows_the_tallest_column),
        ("columns by subgroup, player's first, empty skipped", _check_columns_by_subgroup),
        ("secret subgroup falls back to roster order", _check_secret_subgroup_falls_back),
        ("player's group unknown: ascending, no pink", _check_player_group_unknown),
        ("own cell tick", _check_own_cell_tick),
        ("reflow and resize wait out combat", _check_reflow_waits_out_combat),
        ("party rows give way in a raid", _check_party_rows_give_way_in_a_raid),
        ("PartyFrames shared export and suppress switch", _check_party_harness_contract),
        ("Blizzard raid frames dimmed", _check_blizzard_raid_dimmed),
        ("Blizzard raid frames made later are swept", _check_blizzard_raid_late_frames),
        ("switched off leaves Blizzard alone", _check_switched_off_leaves_blizzard_alone),
        ("switch in combat waits for regen", _check_switch_in_combat_waits),
        ("dispel edge", _check_dispel_edge),
        ("low health red", _check_low_health_red),
        ("dead and offline dashed", _check_dead_and_offline_dashed),
        ("secrets never compared", _check_secrets_never_compared),
        ("one range ticker", _check_range_one_ticker),
        ("auras gated in combat", _check_auras_gated_in_combat),
        ("names, class colours, roles", _check_names_classes_roles),
        ("look C fill", _check_look_c_fill),
        ("Layout raid entry", _check_layout_entry),
        ("rescaled grid", _check_rescaled_grid),
    ]
    failures = 0
    for label, fn in cases:
        try:
            fn()
            print(f"PASS  {label}")
        except Exception as exc:  # noqa: BLE001 - report every case
            failures += 1
            print(f"FAIL  {label}: {type(exc).__name__}: {exc}")
    print(f"{len(cases) - failures}/{len(cases)} raid frame checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
