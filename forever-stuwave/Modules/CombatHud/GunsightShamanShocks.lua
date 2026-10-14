-- Forever STUwave: Gunsight Shaman Class Module, lane 2: the SHOCK TRACE and the FIRE NOVA RING.
--
-- The approved design is mockups/gunsight-class-module-shaman-2026-10-08.html, Concept A "Totem Poles", poleMod(): the ground the
-- totem poles stand on is also the shock gauge. A zigzag trace under the ground line charges left to right as the shared Earth /
-- Flame / Frost Shock cooldown runs, and a bolt at its end lights (RDY) when a shock can be cast; a cyan ring around the Fire
-- totem's head says Fire Nova is ready (drawn over the head, on a frame above it), with a NOVA tag in the footer. There is no Earth Shock KICK tag here: KICK comes
-- from GunsightTape.lua's class neutral tag on the target box. GunsightShaman.lua owns the module frame and the totem poles and calls this file:
--
--   FS.GunsightShamanShocks = { Build(frame) -> section, Seat(section, rect, scale), OnShow(section), OnHide(section) }
--
-- `frame` is the class module frame (a child of the area host), `rect` the module rect in image px { x, y, w, h } (every piece
-- sits at the mockup's offset from rect.x and rect.y, so either area works), `scale` is unused (ui() carries it). Nothing here
-- is built at file load. The poles tell the ring where the Fire totem is through two functions that live on the SECTION, not on
-- the table:
--
--   section.SetFire(up, headY)   up: true (the Fire totem stands), false (it is gone: no ring, no NOVA tag), nil (not known,
--                                the default: a Fire Nova that reads unusable for a reason other than mana counts as "no
--                                totem"); headY: the Fire head's centre in image px from rect.y (default 24, a full pole's),
--                                or false when the head's place cannot be known (it rides an engine drawn timer bar): no ring,
--                                the NOVA tag stays; nil leaves it as it was
--
-- THE SHOCK. Earth, Flame and Frost Shock share one cooldown (6 s), so one record answers for all three. READY comes from the
-- cooldown's plain isActive (plain in combat, probe 2026-10-01): false is ready, whatever else; a plain isOnGCD or a cooldown no
-- longer than the global one is ready too. The seconds are secret in combat. Out of combat the label is the plain start and
-- duration. In combat it is an ESTIMATE ("~") from our own last cast (UNIT_SPELLCAST_SUCCEEDED of the player, any rank, matched by
-- name, kept on through OnHide because a cast while hidden cannot be re-read), exactly the rule HudLogic's CooldownState uses:
-- with isActive true and the timing secret the ledger decides, ready unless its cast plus the learned cooldown length is still
-- ahead; a cast the ledger never saw reads ready (it fails toward suggesting the spell). A secret isActive is UNKNOWN: "?", no
-- charge, never a guess. The trace's own fill is the ENGINE's: C_Spell.GetSpellCooldownDuration -> StatusBar:SetTimerDuration
-- takes the (secret-bearing) duration object in combat and draws the crop; without that API the fill is a plain number from the
-- same plain or estimated timing. No secret is ever compared or computed on: it is only handed to SetTimerDuration.
--
-- FIRE NOVA. Ring and tag need the spell in the book (resolved by name, ids as a fallback, IsPlayerSpell and its siblings), then
-- the same cooldown reading with a 10 s ledger. The ring shows while it is ready and the Fire totem stands; the footer tag
-- (a dashed pip and NOVA) stays while the totem stands, cyan when ready and muted when not. It cannot know whether an enemy is
-- within 10 yd of the totem: the ring is advice, not a guarantee.
--
-- EVENTS AND TICKER. The cast ledger listens from Build on and stays on through OnHide (it only records). Everything else
-- listens from OnShow to OnHide: SPELL_UPDATE_COOLDOWN and SPELL_UPDATE_USABLE, the spellbook events and PLAYER_REGEN_*. Nothing
-- here reads the target. One OnUpdate (a tenth of a second) runs only while a shock or Fire Nova counts down, and stops itself. The per frame path allocates nothing on the addon side: the time strings come
-- from tables built at load and a text or colour is written only when it changes. Plain frames only, nothing secure.

local _, FS = ...

local Gunsight = FS.Gunsight
if not (Gunsight and Gunsight.G and Gunsight.ui and Gunsight.Point) then return end

local ui, Point = Gunsight.ui, Gunsight.Point
local IsSecret = FS.IsSecret or function() return false end

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local floor = math.floor

-------------------------------------------------------------------------------
-- Constants (image px from the module rect's top left; the harness re-reads the mockup's numbers)
-------------------------------------------------------------------------------

local C = {
    GY = 78,                                            -- poleMod: gy = y0 + 78, the ground line the poles stand on
    TRACE_X = 7, TRACE_W = 162, TRACE_DY = 5,           -- the trace runs x0 1220 .. 1382 (rect.x is 1213) on the line gy + 5
    TRACE_H = 20.25, GLOW_PAD = 8, GLOW_H = 22.25,      -- the canvases: 256 x 32 texels over 162 x 20.25 px, the glow 8 px wider each side
    TRACE_BASE_A = 0.4,                                 -- the unlit trace: violet, stroke-opacity .4
    BOLT_X = 183, BOLT_DY = -30, BOLT_K = 0.95,         -- bolt(1396, gy - 30, .95)
    BOLT_CANVAS = 32, BOLT_OX = 16, BOLT_OY = 2,        -- the bolt canvas is 32 px, the bolt's origin at (16, 2)
    DARK_A = 0.7,                                       -- the unlit bolt body: rgba(13, 6, 32, .7)
    LABEL_X = 183, LABEL_DY = 19, LABEL_SIZE = 12,      -- txt(1396, gy + 19, 'RDY' | seconds, 12, middle)
    FIRE_X = 32, FIRE_Y = 24, RING = 44,                -- the Fire pole's centre (1245) and a full pole's head (gy - 48 - 15 + 9); the ring canvas
    RING_A = 0.95,                                      -- circ(.., cyan, .95): the outer ring's .35 is baked into the texture
    FOOT_DY = 22, PIP_X = 11, PIP_DY = 7, PIP = 10,     -- fy = gy + 22; the pip centred at (1224, fy + 7), 10 px canvas
    NOVA_X = 19, NOVA_BASE = 11, NOVA_SIZE = 10,        -- txt(1232, fy + 11, 'NOVA', 10)
    OFF_PIP_A = 0.8, OFF_TEXT_A = 0.75,                 -- the not ready tag: muted, .8 and .75
    SHOCK_CD = 6, NOVA_CD = 10, GCD_WINDOW = 1.6,       -- seconds: the shared shock cooldown, Fire Nova's, the longest global cooldown
    TICK = 0.1,                                         -- the ticker's period
    RING_LEVEL = 3,                                     -- the ring's frame sits this far above the module frame: the Fire head is at +2 and its opaque fill would hide the arcs
    -- Mononoki Bold: the line box's middle sits 325 / 1024 of the size above the baseline (GunsightSeals.lua's CAP)
    CAP = 325 / 1024,
}

-- Spells by NAME first (a name answers with the player's own rank), ids only as a fallback. Earth Shock rank 1 is 8042; the
-- others are the classic rank 1 ids and Fire Nova's published id, all only tried when the name does not resolve.
local GROUPS = {
    shock = { cd = C.SHOCK_CD, members = {
        { name = "Earth Shock", ids = { 8042 } },
        { name = "Flame Shock", ids = { 8050 } },
        { name = "Frost Shock", ids = { 8056 } },
    } },
    nova = { cd = C.NOVA_CD, members = {
        { name = "Fire Nova", ids = { 408341 } },
    } },
}

-- "4s" above 3 s, "2.2s" under it (the mockup's fmt), and the same with a "~" for an estimate; built once, the tick only indexes
local SECS, EST_SECS, TENTHS, EST_TENTHS = {}, {}, {}, {}
for i = 0, 99 do
    SECS[i] = i .. "s"
    EST_SECS[i] = "~" .. i .. "s"
end
for i = 0, 30 do
    TENTHS[i] = string.format("%.1fs", i / 10)
    EST_TENTHS[i] = "~" .. TENTHS[i]
end

local function FormatRemaining(rem, est)
    if rem < 3 then
        local i = floor(rem * 10 + 0.5)
        if i < 0 then i = 0 end
        return est and EST_TENTHS[i] or TENTHS[i]
    end
    local i = floor(rem + 0.5)
    if i > 99 then i = 99 end
    return est and EST_SECS[i] or SECS[i]
end

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightshamanshocks_" .. key, "|cffff4488Forever STUwave|r: gunsight shaman shocks: " .. tostring(msg))
    end
end

-------------------------------------------------------------------------------
-- Secret safe reads
-------------------------------------------------------------------------------

-- v when it is plain and of that type, else nil. A false boolean comes back as false.
local function PlainOf(v, kind)
    if IsSecret(v) then return nil end
    if type(v) == kind then return v end
    return nil
end

local function SpellIdByName(name)
    local fn = C_Spell and C_Spell.GetSpellInfo
    if fn then
        local ok, info = pcall(fn, name)
        if ok and type(info) == "table" and not IsSecret(info) then return PlainOf(info.spellID, "number") end
        return nil
    end
    if GetSpellInfo then
        local ok, _, _, _, _, _, _, id = pcall(GetSpellInfo, name)
        if ok then return PlainOf(id, "number") end
    end
    return nil
end

local nameCache = {}
local function SpellNameOf(id)
    local hit = nameCache[id]
    if hit then return hit end
    local name
    if C_Spell and C_Spell.GetSpellName then
        local ok, n = pcall(C_Spell.GetSpellName, id)
        if ok then name = PlainOf(n, "string") end
    end
    if not name and C_Spell and C_Spell.GetSpellInfo then
        local ok, info = pcall(C_Spell.GetSpellInfo, id)
        if ok and type(info) == "table" and not IsSecret(info) then name = PlainOf(info.name, "string") end
    end
    if name then nameCache[id] = name end
    return name
end

-- true / false / nil (cannot tell) for "does the player know this spell id", over the three book APIs a client may have
local function KnownFn(i)
    if i == 1 then return IsPlayerSpell end
    if i == 2 then return IsSpellKnown end
    return C_SpellBook and C_SpellBook.IsSpellKnown
end

local function IsKnownId(id)
    local sawFalse, unreadable = false, false
    for i = 1, 3 do
        local fn = KnownFn(i)
        if fn then
            local ok, r = pcall(fn, id)
            if ok and not IsSecret(r) then
                if r then return true end
                sawFalse = true
            else
                unreadable = true
            end
        end
    end
    if unreadable then return nil end
    if sawFalse then return false end
    return nil
end

-- isActive, isOnGCD, startTime, duration of a spell's cooldown, each plain or nil. Nothing at all (no API, a throw) is four nils.
local function ReadCooldown(id)
    local fn = C_Spell and C_Spell.GetSpellCooldown
    if fn then
        local ok, cd = pcall(fn, id)
        if not ok or type(cd) ~= "table" or IsSecret(cd) then return nil end
        return PlainOf(cd.isActive, "boolean"), PlainOf(cd.isOnGCD, "boolean"), PlainOf(cd.startTime, "number"), PlainOf(cd.duration, "number")
    end
    if GetSpellCooldown then
        local ok, start, dur = pcall(GetSpellCooldown, id)
        start, dur = PlainOf(start, "number"), PlainOf(dur, "number")
        if ok and start and dur then return dur > 0, nil, start, dur end
    end
    return nil
end

-------------------------------------------------------------------------------
-- The spellbook and the cooldown ledger
-------------------------------------------------------------------------------

-- Resolves every member of a group: its id (the player's rank by name, else a fallback id) and whether it is known. A group is
-- known when any member is; its id (the one asked for the shared cooldown) is the first known member's.
local function ResolveGroup(g)
    g.known, g.id = false, nil
    for _, m in ipairs(g.members) do
        m.id, m.known, m.localName = nil, false, nil
        local id = SpellIdByName(m.name)
        if id and IsKnownId(id) == true then
            m.id, m.known = id, true
        else
            for _, fid in ipairs(m.ids) do
                if IsKnownId(fid) == true then m.id, m.known = fid, true; break end
            end
        end
        if m.known then
            m.localName = SpellNameOf(m.id)
            if not g.known then g.known, g.id = true, m.id end
        end
    end
end

-- Fills g.mode ("none" not known, "ready", "charging", "unknown"), g.rem (plain seconds left, charging only), g.est (the
-- seconds come from the cast ledger) and g.span (the cooldown's own length, for a plain fill).
local function ReadGroup(g, now)
    g.rem, g.est = nil, false
    if not g.known then g.mode = "none"; return end
    local active, onGcd, start, dur = ReadCooldown(g.id)
    if active == nil then g.mode = "unknown"; return end
    if active == false then g.mode, g.plainEnd = "ready", nil; return end
    if onGcd == true then g.mode = "ready"; return end
    if start and dur and dur > 0 then
        if dur <= C.GCD_WINDOW then g.mode, g.plainEnd = "ready", nil; return end
        -- the length is learned only from a cooldown that began at our own cast (a lockout or a shared start says nothing)
        if g.lastAt and math.abs(start - g.lastAt) <= C.GCD_WINDOW then g.len = dur end
        g.plainEnd = start + dur
        local rem = start + dur - now
        if rem <= 0 then g.mode = "ready"; return end
        g.mode, g.rem, g.span = "charging", rem, dur
        return
    end
    -- isActive true and the timing secret: the ledger decides (see the header)
    local ends = g.plainEnd
    local last = g.lastAt
    if last and now >= last then
        local e = last + g.len
        if not ends or e > ends then ends = e end
    end
    if ends and now < ends then
        g.mode, g.rem, g.est, g.span = "charging", ends - now, true, g.len
    else
        g.mode = "ready"
    end
end

-------------------------------------------------------------------------------
-- Drawing helpers
-------------------------------------------------------------------------------

local function Tok(name, fallback)
    local T = FS.Theme
    local v = T and T[name]
    if type(v) == "table" then return v end
    return fallback
end

-- A part shown or hidden only when its answer changes
local function SetOn(region, on)
    on = on and true or false
    if region.fsOn ~= on then
        region.fsOn = on
        region:SetShown(on)
    end
end

local function Tint(tex, c, a)
    local v = tex.fsTint
    if not v then v = { false, false, false, false }; tex.fsTint = v end
    if v[1] ~= c or v[4] ~= a then
        v[1], v[4] = c, a
        tex:SetVertexColor(c[1], c[2], c[3], a)
    end
end

local function TextTint(fs, c, a)
    if fs.fsC ~= c or fs.fsA ~= a then
        fs.fsC, fs.fsA = c, a
        fs:SetTextColor(c[1], c[2], c[3], a)
    end
end

-- Theme.ApplyMono resets a font string's colour: the font is set again at every seat, so the colour worn is put back after it
local function SeatFont(fs, size, fallback)
    local c = fs.fsC or fallback
    FS.Theme.ApplyMono(fs, ui(size), c)
    fs:SetTextColor(c[1], c[2], c[3], fs.fsA or 1)
end

local function SetLabel(fs, text)
    if fs.fsText ~= text then
        fs.fsText = text
        fs:SetText(text)
    end
end

local function NewTex(parent, layer, sub, file)
    local t = parent:CreateTexture(nil, layer, nil, sub)
    t:SetTexture(MEDIA .. file)
    t:Hide()
    t.fsOn = false
    return t
end

local function NewText(parent, size, justify, color)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    fs.fsSize, fs.fsJustify = size, justify
    FS.Theme.ApplyMono(fs, ui(size), color)
    fs:SetJustifyH(justify)
    fs:SetText("")
    fs:Hide()
    fs.fsOn = false
    return fs
end

local function At(s, region, anchor, x, y)
    Point(region, anchor, s.ox + x, s.oy + y)
end

-------------------------------------------------------------------------------
-- Painting (each write only on a change)
-------------------------------------------------------------------------------

local function SetBolt(s, mode)
    local K = s.colors
    if mode == "none" then
        SetOn(s.boltFill, false); SetOn(s.boltLine, false); SetOn(s.boltGlow, false)
        return
    end
    local line = mode == "unknown" and K.muted or K.cyan
    if mode == "ready" then Tint(s.boltFill, K.cyan, 1) else Tint(s.boltFill, K.scrim, C.DARK_A) end
    Tint(s.boltLine, line, 1)
    Tint(s.boltGlow, line, 1)
    SetOn(s.boltFill, true); SetOn(s.boltLine, true); SetOn(s.boltGlow, mode == "ready")
end

-- Starts the engine's fill from the shock's duration object; false when the client cannot (then the fill is a plain number).
local function StartTimer(s, g)
    local fn = C_Spell and C_Spell.GetSpellCooldownDuration
    local bar = s.bar
    if not (fn and bar.SetTimerDuration and g.id) then return false end
    local ok, obj = pcall(fn, g.id)
    if not ok or obj == nil then return false end
    return (pcall(bar.SetTimerDuration, bar, obj))
end

local function PaintShock(s, restart)
    local g, K = s.shock, s.colors
    local mode = g.mode
    local known = mode ~= "none"
    SetOn(s.base, known)
    if s.shockMode ~= mode then
        s.shockMode = mode
        s.barTimer = false
        SetOn(s.ready, mode == "ready")
        SetOn(s.glow, mode == "ready")
        SetOn(s.bar, mode == "charging")
        SetBolt(s, mode)
        SetOn(s.label, known)
        restart = true
    end
    if not known then return end
    if mode == "ready" then
        SetLabel(s.label, "RDY")
        TextTint(s.label, K.cyan, 1)
    elseif mode == "unknown" then
        SetLabel(s.label, "?")
        TextTint(s.label, K.muted, 1)
    else
        SetLabel(s.label, FormatRemaining(g.rem, g.est))
        TextTint(s.label, K.white, 1)
        if restart or not s.barTimer then s.barTimer = StartTimer(s, g) end
        if not s.barTimer then
            local span = g.span
            local p = (span and span > 0) and (1 - g.rem / span) or 0
            if p < 0 then p = 0 elseif p > 1 then p = 1 end
            if not s.barValue or math.abs(p - s.barValue) > 0.002 then
                s.barValue = p
                s.bar:SetValue(p)
            end
        end
    end
end

-- Whether a Fire totem stands: what the poles said, else Fire Nova's own usability (a mana shortfall is not a missing totem).
local function FireUp(s)
    if s.fireUp ~= nil then return s.fireUp end
    local g = s.nova
    local fn = C_Spell and C_Spell.IsSpellUsable
    if not (fn and g.id) then return true end
    local ok, usable, noMana = pcall(fn, g.id)
    if not ok or IsSecret(usable) or IsSecret(noMana) then return true end
    if usable == false and noMana ~= true then return false end
    return true
end

local function PaintNova(s)
    local g, K = s.nova, s.colors
    local show = g.known and FireUp(s)
    local ready = show and g.mode == "ready"
    local ring = ready and not s.headLost
    SetOn(s.ring, ring); SetOn(s.ringGlow, ring)
    SetOn(s.pip, show); SetOn(s.novaText, show)
    if not show then return end
    if ready then
        Tint(s.ring, K.cyan, C.RING_A); Tint(s.ringGlow, K.cyan, 1)
        Tint(s.pip, K.cyan, 1)
        TextTint(s.novaText, K.cyan, 1)
    else
        Tint(s.pip, K.muted, C.OFF_PIP_A)
        TextTint(s.novaText, K.muted, C.OFF_TEXT_A)
    end
end

-------------------------------------------------------------------------------
-- The live layer
-------------------------------------------------------------------------------

local Sync

local function Refresh(s, now, restart)
    now = now or GetTime()
    ReadGroup(s.shock, now)
    ReadGroup(s.nova, now)
    PaintShock(s, restart)
    PaintNova(s)
    Sync(s)
end

local function NeedsTick(s)
    return s.shock.mode == "charging" or (s.nova.known and s.nova.mode == "charging")
end

local function Tick(frame)
    local s = frame.fsSection
    if not (s and s.live) then return end
    local now = GetTime()
    if now - s.lastTick < C.TICK then return end
    s.lastTick = now
    local ok, err = pcall(Refresh, s, now, false)
    if not ok then
        LogOnce("tick", "tick failed: " .. tostring(err))
        s.holder:SetScript("OnUpdate", nil)
        s.ticking = false
    end
end

Sync = function(s)
    local need = s.live and NeedsTick(s)
    if need and not s.ticking then
        s.ticking, s.lastTick = true, GetTime()
        s.holder:SetScript("OnUpdate", Tick)
    elseif not need and s.ticking then
        s.ticking = false
        s.holder:SetScript("OnUpdate", nil)
    end
end

local function ResolveAll(s)
    ResolveGroup(s.shock)
    ResolveGroup(s.nova)
end

local function Reread(s, restart)
    if not s.live then return end
    local ok, err = pcall(Refresh, s, nil, restart)
    if not ok then LogOnce("refresh", "refresh failed: " .. tostring(err)) end
end

local BOOK_EVENTS = { SPELLS_CHANGED = true, LEARNED_SPELL_IN_SKILL_LINE = true, PLAYER_LEVEL_UP = true }
local COOLDOWN_EVENTS = { SPELL_UPDATE_COOLDOWN = true, SPELL_UPDATE_USABLE = true, PLAYER_REGEN_ENABLED = true, PLAYER_REGEN_DISABLED = true }

local function OnViewEvent(s, event)
    if not s.live then return end
    if BOOK_EVENTS[event] then
        ResolveAll(s)
        Reread(s, true)
    elseif COOLDOWN_EVENTS[event] then
        Reread(s, true)
    end
end

-- The player's own casts: any rank of a shock starts the shared cooldown, a Fire Nova its own. A ledger only, kept on through OnHide.
local function OnOwnCast(s, _, _, _, spellID)
    if IsSecret(spellID) or type(spellID) ~= "number" then return end
    local name = SpellNameOf(spellID)
    if not name then return end
    local now = GetTime()
    local hit = false
    for i = 1, 2 do
        local g = i == 1 and s.shock or s.nova
        for _, m in ipairs(g.members) do
            if m.name == name or (m.localName and m.localName == name) then g.lastAt, hit = now, true end
        end
    end
    if hit and s.live then Reread(s, true) end
end

local VIEW_EVENTS = {
    "SPELL_UPDATE_COOLDOWN", "SPELL_UPDATE_USABLE", "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP",
    "PLAYER_REGEN_ENABLED", "PLAYER_REGEN_DISABLED",
}

-- A client refuses an event it does not know: FrameHelpers skips it and records it in the saved variables, no chat line
local function SetViewEvents(s, on)
    local ev = s.events
    if on then
        FS.FrameHelpers.RegisterEvents(ev, VIEW_EVENTS)
    else
        for _, e in ipairs(VIEW_EVENTS) do pcall(ev.UnregisterEvent, ev, e) end
    end
end

-------------------------------------------------------------------------------
-- Build, Seat, OnShow, OnHide
-------------------------------------------------------------------------------

local function NewGroups()
    local list = {}
    for key, def in pairs(GROUPS) do
        local g = { cd = def.cd, len = def.cd, mode = "none", members = {} }
        for i, m in ipairs(def.members) do g.members[i] = { name = m.name, ids = m.ids } end
        list[key] = g
    end
    return list
end

local function BuildSection(frame)
    local s = { ox = 0, oy = 0, live = false, ticking = false, lastTick = 0, groups = NewGroups(), fireUp = nil, fireY = C.FIRE_Y }
    s.shock, s.nova = s.groups.shock, s.groups.nova
    s.colors = {
        cyan = Tok("COLOR_POWER", { 0.133, 0.878, 1, 1 }),
        muted = Tok("COLOR_MUTED", { 0.6157, 0.5765, 0.7686, 1 }), white = Tok("COLOR_TEXT_WHITE", { 1, 1, 1, 1 }),
        violet = Tok("COLOR_BORDER", { 0.659, 0.333, 0.969, 1 }), scrim = Tok("COLOR_HUD_SCRIM", { 0.051, 0.024, 0.125, 1 }),
    }
    local K = s.colors

    local holder = CreateFrame("Frame", nil, frame)
    holder:SetAllPoints(frame)
    holder:EnableMouse(false)
    holder.fsSection = s
    s.holder = holder

    -- the shock trace: dim base, the engine's fill, the full trace and its glow
    s.base = NewTex(holder, "ARTWORK", 0, "shock_trace_line.tga")
    Tint(s.base, K.violet, C.TRACE_BASE_A)
    s.ready = NewTex(holder, "ARTWORK", 1, "shock_trace_line.tga")
    Tint(s.ready, K.cyan, 1)
    s.glow = NewTex(holder, "BACKGROUND", 0, "shock_trace_glow.tga")
    Tint(s.glow, K.cyan, 1)
    local bar = CreateFrame("StatusBar", nil, holder)
    bar:SetFrameLevel(holder:GetFrameLevel() + 1)
    bar:EnableMouse(false)
    bar:SetStatusBarTexture(MEDIA .. "shock_trace_line.tga")
    bar:SetStatusBarColor(K.cyan[1], K.cyan[2], K.cyan[3], 1)
    bar:SetMinMaxValues(0, 1)
    bar:SetValue(0)
    bar:Hide()
    bar.fsOn = false
    s.bar = bar

    -- the bolt and its label
    s.boltGlow = NewTex(holder, "BACKGROUND", 1, "shock_bolt_glow.tga")
    s.boltFill = NewTex(holder, "ARTWORK", 2, "shock_bolt_fill.tga")
    s.boltLine = NewTex(holder, "ARTWORK", 3, "shock_bolt_line.tga")
    s.label = NewText(holder, C.LABEL_SIZE, "CENTER", K.white)

    -- Fire Nova: the ring on the Fire head, the footer pip and word
    local ringFrame = CreateFrame("Frame", nil, holder)
    ringFrame:SetAllPoints(holder)                  -- a frame with no rect draws nothing on this client (see Gunsight.lua's root)
    ringFrame:SetFrameLevel(frame:GetFrameLevel() + C.RING_LEVEL)
    ringFrame:EnableMouse(false)
    s.ringFrame = ringFrame
    s.ringGlow = NewTex(ringFrame, "BACKGROUND", 2, "nova_ring_glow.tga")
    s.ring = NewTex(ringFrame, "ARTWORK", 4, "nova_ring.tga")
    s.pip = NewTex(holder, "ARTWORK", 5, "nova_pip.tga")
    s.novaText = NewText(holder, C.NOVA_SIZE, "LEFT", K.cyan)
    SetLabel(s.novaText, "NOVA")

    -- the view events (off until OnShow) and the player's cast ledger (on from here)
    local ev = CreateFrame("Frame", nil, holder)
    ev:SetScript("OnEvent", function(_, event) OnViewEvent(s, event) end)
    s.events = ev
    local rec = CreateFrame("Frame", nil, holder)
    rec:SetScript("OnEvent", function(_, event, ...) OnOwnCast(s, event, ...) end)
    local okReg, errReg = pcall(rec.RegisterUnitEvent, rec, "UNIT_SPELLCAST_SUCCEEDED", "player")
    if not okReg then LogOnce("ledger", "the cast ledger cannot listen (" .. tostring(errReg) .. ")") end
    s.recorder = rec

    s.SetFire = function(up, headY)
        if up == nil or up == true or up == false then s.fireUp = up end
        if headY == false then
            s.headLost = true                        -- the head's place is not knowable (a timer bar pole): no ring, the tag stays
        elseif type(headY) == "number" and not IsSecret(headY) then
            s.headLost = false
            s.fireY = headY
            if s.ring then
                At(s, s.ring, "TOPLEFT", C.FIRE_X - C.RING / 2, s.fireY - C.RING / 2)
                At(s, s.ringGlow, "TOPLEFT", C.FIRE_X - C.RING / 2, s.fireY - C.RING / 2)
            end
        end
        if s.live then Reread(s, false) end
    end
    s.built = true
    return s
end

local function SeatSection(s, rect)
    s.ox, s.oy = rect.x, rect.y
    local k = ui(1)
    local gy = C.GY
    local zy = gy + C.TRACE_DY
    -- the trace and its fill, its glow with a margin
    for _, r in ipairs({ s.base, s.ready, s.bar }) do
        At(s, r, "TOPLEFT", C.TRACE_X, zy - C.TRACE_H / 2)
        r:SetSize(C.TRACE_W * k, C.TRACE_H * k)
    end
    At(s, s.glow, "TOPLEFT", C.TRACE_X - C.GLOW_PAD, zy - C.GLOW_H / 2)
    s.glow:SetSize((C.TRACE_W + 2 * C.GLOW_PAD) * k, C.GLOW_H * k)
    -- the bolt: origin (BOLT_X, gy + BOLT_DY), scaled; its canvas puts the origin at (16, 2)
    local bk = C.BOLT_K
    for _, r in ipairs({ s.boltGlow, s.boltFill, s.boltLine }) do
        At(s, r, "TOPLEFT", C.BOLT_X - C.BOLT_OX * bk, gy + C.BOLT_DY - C.BOLT_OY * bk)
        r:SetSize(C.BOLT_CANVAS * bk * k, C.BOLT_CANVAS * bk * k)
    end
    SeatFont(s.label, C.LABEL_SIZE, s.colors.white)
    At(s, s.label, "CENTER", C.LABEL_X, gy + C.LABEL_DY - C.CAP * C.LABEL_SIZE)
    -- the Nova ring on the Fire head, the footer
    for _, r in ipairs({ s.ring, s.ringGlow }) do
        At(s, r, "TOPLEFT", C.FIRE_X - C.RING / 2, s.fireY - C.RING / 2)
        r:SetSize(C.RING * k, C.RING * k)
    end
    local fy = gy + C.FOOT_DY
    At(s, s.pip, "TOPLEFT", C.PIP_X - C.PIP / 2, fy + C.PIP_DY - C.PIP / 2)
    s.pip:SetSize(C.PIP * k, C.PIP * k)
    SeatFont(s.novaText, C.NOVA_SIZE, s.colors.cyan)
    At(s, s.novaText, "LEFT", C.NOVA_X, fy + C.NOVA_BASE - C.CAP * C.NOVA_SIZE)
end

local Shocks = {}
FS.GunsightShamanShocks = Shocks

function Shocks.Build(frame)
    local ok, result = pcall(BuildSection, frame)
    if ok then return result end
    LogOnce("build", "build failed: " .. tostring(result))
    return { built = false }
end

function Shocks.Seat(s, rect, scale)
    if type(s) ~= "table" or not s.built then return end
    if type(rect) ~= "table" or type(rect.x) ~= "number" or type(rect.y) ~= "number" or IsSecret(rect.x) or IsSecret(rect.y) then return end
    local ok, err = pcall(SeatSection, s, rect)
    if not ok then LogOnce("seat", "seat failed: " .. tostring(err)) end
end

function Shocks.OnShow(s)
    if type(s) ~= "table" or not s.built then return end
    s.live = true
    ResolveAll(s)
    s.shockMode = nil
    SetViewEvents(s, true)
    Reread(s, true)
end

function Shocks.OnHide(s)
    if type(s) ~= "table" or not s.built then return end
    s.live = false
    SetViewEvents(s, false)
    if s.ticking then
        s.ticking = false
        s.holder:SetScript("OnUpdate", nil)
    end
end
