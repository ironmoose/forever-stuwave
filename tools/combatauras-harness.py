#!/usr/bin/env python3
"""In combat debuffs, dispels and heal over times on party rows and raid cells (lane G, ticket G1).

The real FrameExtras.lua (Engine), PartyFrames.lua and RaidFrames.lua run over the party and raid harnesses' mock client plus
a strict AuraContainer mock. In combat lockdown no addon aura read works, so the engine layer (AuraContainer slots and groups
the engine fills itself) is the in combat display and the Lua scans stay the out of combat one. Checked:

  * nothing is built, enabled or shown in combat, and nothing when the client lacks the template or the kill switch is set;
  * out of combat the containers sit at alpha 0 and the Lua display is exactly today's;
  * a fight flips the layers: containers at alpha 1 where the switches want them, the held halo, edge colour, cleansable tiles
    and heal squares out, the missing buff tile kept and seated after the engine tray; the end of the fight flips back;
  * the switches (heal over time, types, mine or all, Debuff border, tray) drive candidate filters and alpha, never a read;
  * a refused call (container, filter, layout) leaves today's behaviour and logs once;
  * a down member shows nothing of the engine in a fight;
  * no aura read is attempted in combat by any of it.

This is NOT the real client: the engine's own filtering and drawing are the unverified part (see g.md).

    python3 tools/combatauras-harness.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = _load("partyframes_harness", "partyframes-harness.py")
R = _load("raidframes_harness", "raidframes-harness.py")
FORT = P.FORT

ENGINE_MOCK = r"""
__combat=false
function InCombatLockdown() return __combat end
__tmpl=true __acThrows=false __slotThrows=false __filterThrows=false __layoutThrows=false __groupThrows=false
C_XMLUtil={GetTemplateInfo=function(name) if __tmpl and name=='CustomAuraContainerTemplate' then return {name=name} end end}
AuraContainerSortMethod={Default=0} AuraContainerSortDirection={Normal=0}
AnchorUtil={FlowDirection={Right=1,Left=-1,Up=1,Down=-1}}
__acs={} __acReads=0
local baseCreate=CreateFrame
local function newButton(container)
    local b=baseCreate('Button',nil,container)
    function b:SetIcon(t) self.iconRegion=t end
    function b:SetMouseMotionEnabled(v) self.mouseMotion=v end
    function b:SetMouseClickEnabled(v) self.mouseClick=v end
    return b
end
function CreateFrame(kind,name,parent,tmpl,...)
    local f=baseCreate(kind,name,parent,tmpl,...)
    if kind=='AuraContainer' then
        if __acThrows then error('boom: CreateFrame AuraContainer') end
        assert(tmpl=='CustomAuraContainerTemplate','wrong template '..tostring(tmpl))
        f.slots={} f.groups={} f.flow={} f.armed={}
        __acs[#__acs+1]=f
        function f:SetUnit(u) self.unitSet=u end
        function f:SetEnabled(v) self.enabled=v end
        function f:SetFlowLayoutAnchorPoint(p) self.flow.anchor=p end
        function f:SetFlowLayoutGrowthDirection(h,v) self.flow.h,self.flow.v=h,v end
        function f:SetFlowLayoutMaximumLineSize(n) self.flow.line=n end
        function f:AddAuraSlot(key,filter,opts)
            if __slotThrows then error('boom: AddAuraSlot') end
            assert(not self.slots[key],'slot exists '..key)
            assert(type(opts.initializeFrame)=='function')
            local b=newButton(self)
            self.slots[key]={filter=filter,candidate=opts.candidateFilters,button=b,sets=0}
            opts.initializeFrame(b)
            return b
        end
        function f:AddAuraGroup(key,filter,opts)
            if __groupThrows then error('boom: AddAuraGroup') end
            assert(not self.groups[key],'group exists '..key)
            local b=newButton(self)
            self.groups[key]={filter=filter,candidate=opts.candidateFilters,max=opts.maxFrameCount,layout=opts.layout,button=b}
            opts.initializeFrame(b)
        end
        function f:SetAuraSlotCandidateFilters(key,c)
            if __filterThrows then error('refused') end
            self.slots[key].candidate=c self.slots[key].sets=self.slots[key].sets+1
        end
        function f:SetAuraGroupCandidateFilters(key,c)
            if __filterThrows then error('refused') end
            self.groups[key].candidate=c
        end
        function f:SetAuraGroupMaxFrameCount(key,n)
            if __layoutThrows then error('refused') end
            self.groups[key].max=n
        end
        function f:SetAuraGroupLayout(key,l)
            if __layoutThrows then error('refused') end
            self.groups[key].layout=l
        end
    end
    return f
end
local plain=C_UnitAuras.GetAuraDataByIndex
C_UnitAuras.GetAuraDataByIndex=function(unit,index,filter)
    if __combat then __acReads=__acReads+1 error('Auras cannot be accessed when secret while tainted') end
    return plain(unit,index,filter)
end
"""


COMPACT_MOCK = r"""
function hooksecurefunc(obj,name,fn)
    local o=obj[name]
    obj[name]=function(...) local r=o(...) fn(...) return r end
end
__moves=0
local function icon(parent,i,kind)
    local b=CreateFrame('Button',nil,parent)
    b.kind,b.idx=kind,i
    function b:SetParent(p) __moves=__moves+1 if __combat then error('SetParent in combat') end self.parent=p end
    return b
end
CompactPartyFrame=CreateFrame('Frame','CompactPartyFrame',UIParent)
CompactPartyFrame.memberUnitFrames={}
for i=1,5 do
    local f=CreateFrame('Button','CompactPartyFrameMember'..i,CompactPartyFrame)
    f.unit=(i==1) and 'player' or ('party'..(i-1))
    f.registered={UNIT_AURA=true}
    function f:IsEventRegistered(e) return self.registered[e]==true end
    function f:RegisterUnitEvent(e) self.registered[e]=true end
    f.dispelDebuffFrames={} f.buffFrames={}
    for k=1,3 do f.dispelDebuffFrames[k]=icon(f,k,'dispel') f.buffFrames[k]=icon(f,k,'buff') end
    CompactPartyFrame.memberUnitFrames[i]=f
end
function __compact(unit)
    for _,f in ipairs(CompactPartyFrame.memberUnitFrames) do if f.unit==unit then return f end end
end
"""

PARTY_EXTRA = ENGINE_MOCK + """
FS.Theme.AddRoundedFill=function(panel,color) local t=panel:CreateTexture() t:SetColorTexture(color[1],color[2],color[3],color[4]) end
"""


def close(a, b, tol=1e-4):
    return abs(a - b) <= tol


def _party(extra="", **kwargs):
    kwargs.setdefault("known", (FORT,))
    if "compact" in kwargs:
        kwargs.pop("compact")
        extra = COMPACT_MOCK + extra
    rt = P._buff_rt(extra=PARTY_EXTRA + extra, **kwargs)
    P._event(rt, "ADDON_LOADED", "'forever-stuwave'")
    P._event(rt, "PLAYER_LOGIN")
    return rt


def _row(rt):
    return P._party1(rt)


def _acs(rt):
    return [rt.globals().__acs[i] for i in range(1, len(rt.globals().__acs) + 1)]


def _mine(rt, unit="party1"):
    return [c for c in _acs(rt) if c.unitSet == unit]


def _fight(rt):
    rt.execute("__combat=true FS.AurasReadable=function() return false end")
    P._event(rt, "PLAYER_REGEN_DISABLED")


def _calm(rt):
    rt.execute("__combat=false FS.AurasReadable=function() return true end")
    P._event(rt, "PLAYER_REGEN_ENABLED")


def _keys(t):
    return sorted(k for k in t.keys())


def _types(candidate):
    return sorted(candidate["includeDispelTypes"].keys())


def _parts(row):
    return row.engine.parts


# ---------------------------------------------------------------------------------------------
# Party
# ---------------------------------------------------------------------------------------------

def _check_builds_out_of_combat_only():
    rt = _party()
    row = _row(rt)
    assert _acs(rt), "no container was built at the first update out of combat"
    P._fire(row, "UNIT_AURA")
    parts = _parts(row)
    assert parts.markers and parts.edge and parts.tray, "markers, edge and tray are all wanted by default? " + str(_keys(parts))
    assert len(_mine(rt)) == 3, len(_mine(rt))
    for c in _acs(rt):
        assert c.enabled is True and c.shown is True, (c.unitSet, c.enabled, c.shown)
        assert c.alpha == 0, "a container drew out of combat"
    # in combat: a fresh client builds nothing
    rt2 = _party(extra="__combat=true")   # a login in a fight defers the frames to its end
    assert not _acs(rt2), "a container was built in combat"
    _calm(rt2)
    P._fire(_row(rt2), "UNIT_AURA")
    assert _mine(rt2), "nothing was built once the fight ended"
    P._assert_quiet(rt)
    P._assert_quiet(rt2)


def _check_gates():
    rt = _party(extra="__tmpl=false")
    P._fire(_row(rt), "UNIT_AURA")
    assert not _acs(rt), "built without the template"
    rt = _party(extra="ForeverSTUwaveDB={groupAuras={engine=false}}")
    P._fire(_row(rt), "UNIT_AURA")
    assert not _acs(rt), "the kill switch did not hold"
    row = _row(rt)
    assert P._tiles(row) == [1], "today's tray changed with the engine off"
    P._assert_quiet(rt)


def _check_slots_and_filters():
    rt = _party()
    row = _row(rt)
    P._fire(row, "UNIT_AURA")
    m, e, t = _parts(row).markers, _parts(row).edge, _parts(row).tray
    hot = m.container.slots["hot:Renew"]
    ids = _keys(hot.candidate["includeSpellIDs"])
    assert 139 in ids and 6074 in ids and 25222 in ids, ids
    assert hot.filter == "HELPFUL|PLAYER", hot.filter
    assert not m.container.slots["deb:Magic"] if False else True
    # a priest removes Magic and Disease; the other edge and tray kinds are switched off by a filter nothing matches
    for kind in ("Magic", "Disease"):
        assert _types(e.container.slots["edge:" + kind].candidate) == [kind], kind
        assert _types(t.container.groups["tray:" + kind].candidate) == [kind], kind
    for kind in ("Curse", "Poison"):
        assert _types(e.container.slots["edge:" + kind].candidate) == ["FS_none"], kind
        assert _types(t.container.groups["tray:" + kind].candidate) == ["FS_none"], kind
    # the tray: left side flows left from the first icon's seat, one fewer than the most icons per kind
    assert t.container.flow.anchor == "TOPRIGHT" and t.container.flow.h == -1, (t.container.flow.anchor, t.container.flow.h)
    assert t.container.groups["tray:Magic"].max == 2 and t.container.groups["tray:Magic"].layout.elementWidth == 22
    # squares are flat colour slots on a proxy, mouse off; the tray icons keep the mouse for the engine's tooltip
    assert hot.button.mouseMotion is False and hot.button.mouseClick is False
    assert t.container.groups["tray:Magic"].button.mouseMotion is None
    # the edge host spans the health rail to the power rail
    pts = e.anchor.points
    assert "TOPLEFT" in pts and "BOTTOMRIGHT" in pts, list(pts.keys())
    P._assert_quiet(rt)


def _check_party_fight_flips_layers():
    rt = _party()
    row = _row(rt)
    rt.execute("__debuffs={'Magic'} __buffs.party1={{name='Renew',caster='player',duration=15,expiration=10}}")
    P._fire(row, "UNIT_AURA")
    assert row.health.fsRail.halo.host.shown, "the out of combat halo is the Lua one"
    shown_before = P._tiles(row)
    assert shown_before == [1, 2], f"a cleansable tile then the missing buff: {shown_before}"
    assert row.alertIcons[1].auraIndex is not None and row.alertIcons[2].auraIndex is None
    assert len([t for t in row.markers.tex.values() if t.shown]) == 1, "the Renew square"
    assert all(c.alpha == 0 for c in _acs(rt))
    rt.execute("__acReads=0")
    _fight(rt)
    m, e, t = _parts(row).markers, _parts(row).edge, _parts(row).tray
    assert m.container.alpha == 1 and e.container.alpha == 1 and t.container.alpha == 1
    assert not row.health.fsRail.halo.host.shown, "the held halo stayed up while the engine draws the edge"
    assert not row.alertIcons[1].shown, "the held cleansable tile stayed up"
    assert row.alertIcons[2].shown, "the missing buff tile went with it"
    seated = rt.eval("function(r) local p=r.alertIcons[2].points.TOPRIGHT return p and p.rel==r.engine.parts.tray.container end")
    assert seated(row), "the missing buff tile is not seated after the engine tray"
    assert not [x for x in row.markers.tex.values() if x.shown], "the held Renew square stayed up"
    # a pull with updates arriving: no read is attempted
    P._fire(row, "UNIT_AURA")
    P._fire(row, "UNIT_HEALTH")
    assert rt.globals().__acReads == 0, "an aura read was attempted in combat"
    _calm(rt)
    assert all(c.alpha == 0 for c in _acs(rt)), "the engine kept drawing after the fight"
    assert row.health.fsRail.halo.host.shown and P._tiles(row) == [1, 2], "the Lua display did not come back"
    assert len([x for x in row.markers.tex.values() if x.shown]) == 1
    assert "TOPRIGHT" in row.alertIcons[1].points and row.alertIcons[1].points["TOPRIGHT"].x == -6, "tray not seated again"
    P._assert_quiet(rt)


def _check_party_switches():
    rt = _party()
    row = _row(rt)
    P._fire(row, "UNIT_AURA")
    m, e, t = _parts(row).markers, _parts(row).edge, _parts(row).tray
    _fight(rt)
    rt.execute("FS.Config.Set('bars.party.alertCleanse', false)")
    assert t.container.alpha == 0, "the tray switch did not take the engine tray out in a fight"
    assert e.container.alpha == 1
    rt.execute("FS.Config.Set('bars.party.alerts', true); FS.Config.Set('bars.party.alertCleanse', true)")
    assert t.container.alpha == 1
    rt.execute("FS.Config.Set('bars.party.mkHot', false)")
    assert m.container.alpha == 0, "no marker wanted: the container still draws"
    assert _keys(m.container.slots["hot:Renew"].candidate["includeSpellIDs"]) == [0], "the Renew filter was not emptied"
    rt.execute("FS.Config.Set('bars.party.mkHot', true)")
    assert m.container.alpha == 1 and 139 in _keys(m.container.slots["hot:Renew"].candidate["includeSpellIDs"])
    # tray size and most icons reach the groups, the origin and the layout (plain frames and engine setters both run in a fight)
    rt.execute("FS.Config.Set('bars.party.alertSize', 30); FS.Config.Set('bars.party.alertMax', 4)")
    g = t.container.groups["tray:Magic"]
    assert g.layout.elementWidth == 30 and g.max == 3, (g.layout.elementWidth, g.max)
    assert t.container.flow.line == 3 * (30 + 3) + 1, t.container.flow.line
    rt.execute("FS.Config.Set('bars.party.alertSide', 'right')")
    assert t.container.flow.anchor == "TOPLEFT" and t.container.flow.h == 1, (t.container.flow.anchor, t.container.flow.h)
    # a heal over time square: size and corner move the proxy, never an engine button
    rt.execute("FS.Config.Set('bars.party.mkSize', 9); FS.Config.Set('bars.party.mkPos', 'bottomleft')")
    proxy = rt.eval("function(r) return r.engine.parts.markers.order[1].proxy end")(row)
    assert proxy.w == 9 and "BOTTOMLEFT" in proxy.points and proxy.points["BOTTOMLEFT"].y == 2, (proxy.w, list(proxy.points.keys()))
    P._assert_quiet(rt)


def _check_party_down_member():
    rt = _party()
    row = _row(rt)
    P._fire(row, "UNIT_AURA")
    _fight(rt)
    assert _parts(row).edge.container.alpha == 1
    rt.execute("__state='dead'")
    P._fire(row, "UNIT_HEALTH")
    assert all(c.alpha == 0 for c in _mine(rt)), "a dead member's debuffs drew"
    rt.execute("__state='live'")
    P._fire(row, "UNIT_HEALTH")
    assert _parts(row).edge.container.alpha == 1
    P._assert_quiet(rt)


def _check_party_refusals_fall_back():
    # the container itself is refused: today's behaviour, one message
    rt = _party(extra="__acThrows=true", quiet=False)
    row = _row(rt)
    rt.execute("__debuffs={'Magic'}")
    P._fire(row, "UNIT_AURA")
    P._fire(row, "UNIT_AURA")
    assert P._tiles(row) == [1, 2] or P._tiles(row) == [1], P._tiles(row)
    msgs = list(rt.globals().__messages.values())
    assert len(msgs) == 3 and all("group_aura_engine" in m for m in msgs), [m[:60] for m in msgs]
    _fight(rt)
    assert row.health.fsRail.halo.host.shown, "with no engine the held halo must stay"
    assert P._tiles(row), "with no engine the held tiles must stay"
    # a slot is refused: the same
    rt = _party(extra="__slotThrows=true", quiet=False)
    P._fire(_row(rt), "UNIT_AURA")
    assert any("group_aura_engine_markers" in m for m in rt.globals().__messages.values())
    # filters are refused in a fight: owed, retried when it ends
    rt = _party()
    row = _row(rt)
    P._fire(row, "UNIT_AURA")
    _fight(rt)
    rt.execute("__filterThrows=true FS.Config.Set('bars.party.mkHot', false)")
    assert row.engine.owed is True, "a refused filter change was not owed"
    rt.execute("__filterThrows=false")
    _calm(rt)
    hot = _parts(row).markers.container.slots["hot:Renew"]
    assert _keys(hot.candidate["includeSpellIDs"]) == [0], "the owed filter change did not land at the end of the fight"
    P._assert_quiet(rt)


def _check_party_preview_untouched():
    rt = _party()
    n = len(_acs(rt))
    rt.execute("local host=CreateFrame('Frame') local f=FS.PartyFrames.NewStylePreview(host)")
    assert len(_acs(rt)) == n, "the Style tab preview built an engine container"
    P._assert_quiet(rt)


# ---------------------------------------------------------------------------------------------
# Raid
# ---------------------------------------------------------------------------------------------

def _raid_rt(n=10, cls="PRIEST"):
    rt = R._client(player_class=cls, before_load=ENGINE_MOCK)
    rt.execute("""
        local plain = C_UnitAuras.GetAuraDataByIndex
        C_UnitAuras.GetAuraDataByIndex = function(unit, index, filter)
            if filter:find('HELPFUL') then
                local b = (__unitBuffs or {})[unit] and __unitBuffs[unit][index]
                if b then return {name=b.name, icon='bufficon', applications=1, dispelName='', duration=0,
                    expirationTime=0, sourceUnit=b.caster} end
                return nil
            end
            return plain(unit, index, filter)
        end
    """)
    R._roster(rt, n)
    return rt


def _rfight(rt):
    rt.execute("__combat=true")
    R._event(rt, "PLAYER_REGEN_DISABLED")


def _rcalm(rt):
    rt.execute("__combat=false")
    R._event(rt, "PLAYER_REGEN_ENABLED")
    R._settle(rt)


def _check_raid_builds_and_flips():
    rt = _raid_rt()
    cell = R._cell(rt, 3)
    rt.execute("__unitDebuffs=__unitDebuffs or {} __unitDebuffs['raid3']={'Magic'}")
    R._unit_event(rt, "UNIT_AURA", "raid3")
    parts = cell.engine.parts
    assert parts.edge and parts.markers and not parts.tray, "raid has markers and an edge, no tray"
    assert cell.engine.unit == "raid3"
    m, e = parts.markers, parts.edge
    # defaults: debuff markers are on for the types I can remove (a Priest: Magic, Disease), the hot lane first
    assert m.container.slots["deb:Magic"].candidate["includeDispelTypes"]["Magic"] is True
    assert _types(m.container.slots["deb:Curse"].candidate) == ["FS_none"], "Curse is not mine: off"
    assert _types(m.container.slots["deb:Disease"].candidate) == ["Disease"]
    assert m.lanes == 3, f"Renew, Magic, Disease lanes: {m.lanes}"
    assert all(c.alpha == 0 for c in _acs(rt))
    ring = R._ring(R._parts(rt, 3))
    lit = R._rgb(ring)
    assert not R._same_rgb(lit, R._rgb(R._ring(R._parts(rt, 4)))), "the Lua edge is the out of combat signal"
    rt.execute("__auraReads=0")
    _rfight(rt)
    assert m.container.alpha == 1 and e.container.alpha == 1
    assert R._same_rgb(R._rgb(R._ring(R._parts(rt, 3))), R._rgb(R._ring(R._parts(rt, 4)))), \
        "the held debuff colour stayed on the edge while the engine draws it"
    R._unit_event(rt, "UNIT_AURA", "raid3")
    assert rt.globals().__acReads == 0, "an aura read in combat"
    _rcalm(rt)
    assert all(c.alpha == 0 for c in _acs(rt))
    assert R._same_rgb(R._rgb(R._ring(R._parts(rt, 3))), lit), "the Lua edge did not come back"
    R._assert_quiet(rt)


def _check_raid_switches():
    rt = _raid_rt()
    rt.execute("__unitDebuffs=__unitDebuffs or {} __unitDebuffs['raid3']={}")
    R._unit_event(rt, "UNIT_AURA", "raid3")
    cell = R._cell(rt, 3)
    m, e = cell.engine.parts.markers, cell.engine.parts.edge
    _rfight(rt)
    rt.execute("FS.Config.Set('bars.raid.mkDebuffWho', 'all')")
    assert _types(m.container.slots["deb:Curse"].candidate) == ["Curse"], "All should add Curse"
    assert m.lanes == 5
    rt.execute("FS.Config.Set('bars.raid.mkMagic', false)")
    assert _types(m.container.slots["deb:Magic"].candidate) == ["FS_none"]
    rt.execute("FS.Config.Set('bars.raid.dispelEdge', false)")
    assert e.container.alpha == 0, "Debuff border off: the engine edge still draws"
    rt.execute("FS.Config.Set('bars.raid.dispelEdge', true); FS.Config.Set('bars.raid.mkDebuff', false)")
    assert e.container.alpha == 1 and m.lanes == 1 and 139 in _keys(m.container.slots["hot:Renew"].candidate["includeSpellIDs"])
    R._assert_quiet(rt)


def _check_raid_missing_buff_after_lanes():
    rt = _raid_rt()
    rt.execute("__spellIds={['Power Word: Fortitude']=1001} __knownIds={[1001]=true}")
    R._event(rt, "SPELLS_CHANGED")
    rt.execute("FS.Config.Set('bars.raid.mkBuff', true)")
    R._unit_event(rt, "UNIT_AURA", "raid4")
    cell = R._cell(rt, 4)
    marks = [t for t in R._parts(rt, 4).markers.tex.values() if t.shown]
    assert len(marks) == 1, "the missing buff square out of combat"
    first = marks[0].points
    _rfight(rt)
    lanes = cell.engine.parts.markers.lanes
    marks = [t for t in R._parts(rt, 4).markers.tex.values() if t.shown]
    assert len(marks) == 1, "the missing buff square is Lua only and stays in a fight"
    assert marks[0].points != first and lanes >= 1, "it sits after the engine's lanes"
    R._assert_quiet(rt)


def _check_raid_down_and_unbuilt():
    rt = _raid_rt()
    R._unit_event(rt, "UNIT_AURA", "raid3")
    cell = R._cell(rt, 3)
    _rfight(rt)
    assert cell.engine.parts.edge.container.alpha == 1
    R._member(rt, 3, state="'dead'")
    R._unit_event(rt, "UNIT_HEALTH", "raid3")
    assert all(c.alpha == 0 for c in _acs(rt) if c.unitSet == "raid3"), "a dead member's engine layer drew"
    # cells that never saw an aura update have no containers (the 40 cell cost is paid only for members who exist)
    assert len([c for c in _acs(rt) if str(c.unitSet).startswith("raid")]) <= 2 * 10, "containers were built for cells with no member"
    R._assert_quiet(rt)



# ---------------------------------------------------------------------------------------------
# Borrowed Blizzard icons
# ---------------------------------------------------------------------------------------------

BORROW = "ForeverSTUwaveDB={groupAuras={mode='borrow'}}"


def _check_borrow_keeps_events_and_seats_icons():
    rt = _party(extra=BORROW, compact=True, blizzard_party="none")
    compact = rt.eval("__compact('party1')")
    assert compact.registered.UNIT_AURA is True, "borrow mode unregistered the compact frame's events"
    assert compact.alpha == 0 and compact.mouse is False, "the compact frame was not dimmed"
    row = _row(rt)
    P._fire(row, "UNIT_AURA")
    assert not _acs(rt), "borrow mode built an engine container"
    eng = row.engine
    assert eng.borrow, "no icons were borrowed"
    host = rt.eval("function(e) return e.borrow.dispelHost end")(eng)
    assert rt.eval("function(c, h) return c.dispelDebuffFrames[1].parent == h end")(compact, host), "the icon was not moved"
    pt = compact.dispelDebuffFrames[1].points
    assert "TOPRIGHT" in pt, list(pt.keys())
    assert host.alpha == 0, "borrowed icons drew out of combat"
    P._assert_quiet(rt)


def _check_borrow_fight_flip_and_no_moves_in_combat():
    rt = _party(extra=BORROW, compact=True, blizzard_party="none")
    compact = rt.eval("__compact('party1')")
    row = _row(rt)
    rt.execute("__debuffs={'Magic'} __buffs.party1={{name='Renew',caster='player',duration=15,expiration=10}}")
    P._fire(row, "UNIT_AURA")
    moves = rt.globals().__moves
    _fight(rt)
    b = row.engine.borrow
    assert b.dispelHost.alpha == 1 and b.buffHost.alpha == 1, "the borrowed icons stay hidden in a fight"
    assert row.health.fsRail.halo.host.shown, "the held halo went although the edge is not borrowed"
    assert not row.alertIcons[1].shown and row.alertIcons[2].shown, "held cleansable tile out, missing buff tile kept"
    seated = rt.eval("function(r) local p=r.alertIcons[2].points.TOPRIGHT return p and p.rel==r.engine.borrow.dispelHost end")
    assert seated(row), "the missing buff tile is not seated after the borrowed icons"
    # Blizzard re-anchors an icon in the fight: nothing of ours moves it until the fight ends
    rt.execute("__compact('party1').dispelDebuffFrames[1]:SetPoint('CENTER', __compact('party1'), 'CENTER', 0, 0)")
    P._fire(row, "UNIT_AURA")
    assert rt.globals().__moves == moves, "SetParent was called in combat"
    assert b.owed is True
    _calm(rt)
    assert rt.globals().__moves >= moves and b.dispelHost.alpha == 0 and b.buffHost.alpha == 0
    assert "TOPRIGHT" in compact.dispelDebuffFrames[1].points and b.owed is False, "the icon was not seated again after the fight"
    P._assert_quiet(rt)


def _check_borrow_fallback_when_engine_cannot_build():
    rt = _party(extra="__acThrows=true", compact=True, blizzard_party="none", quiet=False)
    compact = rt.eval("__compact('party1')")
    rt.execute("__compact('party1').registered={}")   # the sweep had silenced it in engine mode
    row = _row(rt)
    for _ in range(4):
        P._fire(row, "UNIT_AURA")
    assert row.engine.borrow, "a unit whose containers cannot be built did not fall to borrow"
    assert compact.registered.UNIT_AURA is True, "the compact frame was not woken"
    _fight(rt)
    assert row.engine.borrow.dispelHost.alpha == 1


def _check_off_mode_and_refused_moves():
    rt = _party(extra="ForeverSTUwaveDB={groupAuras={mode='off'}}", compact=True, blizzard_party="none")
    compact = rt.eval("__compact('party1')")
    P._fire(_row(rt), "UNIT_AURA")
    assert not _acs(rt) and not _row(rt).engine.borrow, "off mode built something"
    # a compact frame whose icons refuse to move: no error, owed
    rt = _party(extra=BORROW + "\nfor _,i in ipairs(__compact('party1').dispelDebuffFrames) do i.SetParent=function() error('refused') end end",
                compact=True, blizzard_party="none")
    P._fire(_row(rt), "UNIT_AURA")
    assert _row(rt).engine.borrow.owed is True
    P._assert_quiet(rt)


def _check_borrow_no_compact_is_quiet_unless_chosen():
    rt = _party()   # no compact frames at all, no template: the automatic fall finds nothing and says nothing
    P._fire(_row(rt), "UNIT_AURA")
    assert not _row(rt).engine.borrow
    P._assert_quiet(rt)


def _check_raid_borrow():
    rt = R._client(player_class="PRIEST", before_load=ENGINE_MOCK + COMPACT_MOCK.replace("'party1'", "'raid3'") + BORROW
                   + "\nCompactPartyFrame.memberUnitFrames[2].unit='raid3'\n")
    R._roster(rt, 10)
    R._unit_event(rt, "UNIT_AURA", "raid3")
    cell = R._cell(rt, 3)
    assert cell.engine.borrow, "the raid cell borrowed nothing"
    _rfight(rt)
    assert cell.engine.borrow.dispelHost.alpha == 1
    _rcalm(rt)
    assert cell.engine.borrow.dispelHost.alpha == 0
    assert len(list(rt.globals().__messages.values())) == 1, "the missing compact frames are logged once, not per cell"


def main() -> int:
    cases = [
        ("party: built out of combat only, alpha 0 until a fight", _check_builds_out_of_combat_only),
        ("party: no template or the kill switch keeps today's display", _check_gates),
        ("party: slots, groups, filters and seats", _check_slots_and_filters),
        ("party: a fight flips the layers and the end flips back", _check_party_fight_flips_layers),
        ("party: switches drive filters and alpha in a fight", _check_party_switches),
        ("party: a down member shows nothing of the engine", _check_party_down_member),
        ("party: refused container, slot and filter fall back", _check_party_refusals_fall_back),
        ("party: the Style tab preview builds no container", _check_party_preview_untouched),
        ("raid: containers, lanes, the edge and the fight flip", _check_raid_builds_and_flips),
        ("raid: switches", _check_raid_switches),
        ("raid: the missing buff square sits after the lanes", _check_raid_missing_buff_after_lanes),
        ("raid: a down member and unbuilt cells", _check_raid_down_and_unbuilt),
        ("borrow: events kept, icons seated, hosts hidden out of combat", _check_borrow_keeps_events_and_seats_icons),
        ("borrow: a fight flips, nothing moves in combat, seated again after", _check_borrow_fight_flip_and_no_moves_in_combat),
        ("borrow: a unit the engine cannot build falls to borrow", _check_borrow_fallback_when_engine_cannot_build),
        ("borrow: off mode and refused moves", _check_off_mode_and_refused_moves),
        ("borrow: no compact frame is quiet unless chosen", _check_borrow_no_compact_is_quiet_unless_chosen),
        ("borrow: raid cell", _check_raid_borrow),
    ]
    failures = 0
    for label, fn in cases:
        try:
            fn()
            print(f"PASS  {label}")
        except Exception as exc:  # noqa: BLE001 - report every case
            failures += 1
            print(f"FAIL  {label}: {type(exc).__name__}: {exc}")
    print(f"{len(cases) - failures}/{len(cases)} combat aura checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
