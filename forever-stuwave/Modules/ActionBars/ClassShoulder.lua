-- Forever STUwave: the class shoulder CHROME (Paladin, Warrior, Shaman)
--
-- The approved Gunsight mockup draws a shoulder block on the Console chassis' top edge, behind the Paladin's
-- seal and aura buttons (`LS_*`: 306.8 x 91.8 design px, 36 in from the chassis left) and behind the Warrior's
-- three stances (`{id:'st',n:3,rows:1}`: 135.6 x 49). The Shaman's totem tab (TotemBar.lua) takes the same
-- chrome as a 6 x 1 block (264 x 49). In the mockup's default
-- Console style (`PS === 'cn'`) it is NOT the pet panel's recipe (`lsLive` runs only for the other styles):
-- `cnTrace` carries the shoulders, so `cnBake` strokes it with the chassis outline (A(.72)), halos it with
-- the very halo the chassis gets and fills it with the chassis gradient, whose top stop is all a shoulder
-- above the chassis ever shows. This file builds that: `PetDock.NewShoulder` with `opts.chassis` (the
-- Console's own fill tint and stroke alpha and the Console's own baked halo, `Console.GLOW`, drawn strip for
-- strip with vertex alpha 1, no fill overrun into the line row), seated on the Console root, owning the
-- Console's top gap while it stands. The halo is therefore the Console's own profile by construction (the
-- mockup's stepped composite of four nested strokes: .546 at the edge, stepping down to nothing by 10 px).
--
-- It builds ONLY for a class in OWNERS (a Paladin whose SealBar owns the forms, a Warrior whose StanceBar does, a
-- Shaman whose TotemBar is built; the Shaman's forms stay on the stance bar),
-- ONLY while the Console is drawn, ONLY out of combat. Every other class gets none.
-- The art is a plain non-secure child of the Console root. The owner's host (protected, it parents the secure
-- buttons) is its own frame anchored to the Console root, NEVER to this art: nothing secure may be anchored to
-- or parented under it, which is what keeps Seat/Rescale/Show/Hide legal here. They still wait for
-- PLAYER_REGEN_ENABLED in combat, like everything on the chassis. SealBar and StanceBar ask HostPoint/SlotPoint
-- for their seat and fall back to their own when this returns nil (no Console, a failed build).
--
-- GAP: the Console's top outline is open under the shoulder, so while it stands PetDock is told to leave the
-- gap alone (YieldGap, out of combat, BEFORE our SetDockGap) and the gap is ours: line [37, 351.8], halo
-- [25, 357.8] (the shoulder's own halo pieces start 11 px left of its side and the flare piece ends 15 px right
-- of it; the Console's glow ends where they begin).
-- When the shoulder goes (Console off) the gap is closed and handed back (ReclaimGap).
--
-- A class may own a SECOND shoulder (`also`): the Shaman's buff tab (BuffTab.lua, 2 x 1, 92.8 x 49) stands on the
-- Console's top edge 16 design px right of the totem tab's right side (316 with the six stock cells, further right
-- by 42.8 for each preset cell the totem tab grows by): the totem tab ends at 300 and its flare reaches 310, so 6 px of
-- chassis top line stay visible between the two. A def may carry `colsFn`, its column count asked on every Refresh;
-- the art is built once per width (NewShoulder has no resize) and the one that fits is shown. Each shoulder is its own art
-- (NewShoulder has no resize) with its own `wants` and `changed`. The Console has ONE dock gap, so while several
-- stand the gap is the union of their spans, and the stretch of top line that union opens between two shoulders is
-- joined with a plain line texture of the Console's own colour (a hole the mockup does not have). Every function that
-- answers a seat takes an optional `key` (default: the class's first shoulder, so the Paladin, Warrior and totem tab
-- callers are unchanged).
--
-- The five second rule tab (FiveSecondTab.lua, 2 x 1, 92.8 x 49) is a shoulder of EVERY mana class, not of one owner:
-- it stands after the class's own tab(s), 16 design px right of the last one's right side (the totem tab ends at 300 and
-- its flare at 310, the buff tab starts at 316, so the same 6 px of top line stay visible), or at the first seat (36)
-- when the class has no tab. Its seat is worked out on every Refresh from the shoulders that stand, so a class tab that
-- arrives or goes after it moves it; a changed seat tells the owner like a shown or hidden one.
--
-- Loads after PetDock.lua and ConsoleKeys.lua, before SealBar.lua, TotemBar.lua, BuffTab.lua and FiveSecondTab.lua.
-- Nothing here is verified in game.

local _, FS = ...

local ClassShoulder = {}
FS.ClassShoulder = ClassShoulder

local C = {
    OWNER = "classshoulder",
    DX = 36,      -- LS_X 755 less the chassis left 719, design px
    PAD = 6,      -- LS_PAD
    PT = 6,       -- LS_PT
    PB = 5,       -- LS_PB
    BTN = 38,     -- LS_BTN
    GAP = 4.8,    -- LS_BG
    COLS = 7,     -- the Paladin block (OWNERS carries each class's own)
    ROWS = 2,
    HALO_ALPHA = 1,    -- vertex alpha on the Console's own baked halo (1 = the Console's profile, as is)
}
local function BlockSize(cols, rows)
    return 2 * C.PAD + cols * C.BTN + (cols - 1) * C.GAP, C.PT + rows * C.BTN + (rows - 1) * C.GAP + C.PB
end
ClassShoulder.C = C

-- The classes that own a shoulder, by class token: the block (mockup lsRowW(cols) wide, `rows` tall) and the
-- question whose answer says the class's bar is up. Append only; a class not listed here never gets one.
local OWNERS = {
    PALADIN = {
        key = "paladin", cols = C.COLS, rows = C.ROWS,
        wants = function()
            local seal = FS.SealBar
            return seal and seal.OwnsForms and seal.OwnsForms()
        end,
    },
    WARRIOR = {
        key = "warrior", cols = 3, rows = 1,
        wants = function()
            local stance = FS.StanceBar
            return stance and stance.OwnsShoulder and stance.OwnsShoulder()
        end,
        -- the shoulder came or went: the stances re-seat whatever order the regen handlers ran in
        changed = function()
            if FS.StanceBar and FS.StanceBar.Rebuild then FS.StanceBar.Rebuild() end
        end,
    },
    SHAMAN = {
        key = "shaman", cols = 6, rows = 1,
        -- the totem tab grows by a cell for each preset cell the player has on (TotemPresets.lua): 6 to 8
        colsFn = function()
            local totems = FS.TotemBar
            return totems and totems.Cols and totems.Cols() or 6
        end,
        wants = function()
            local totems = FS.TotemBar
            return totems and totems.OwnsShoulder and totems.OwnsShoulder()
        end,
        -- the shoulder came or went: the totem tab re-seats (it does nothing in combat and replays at regen)
        changed = function()
            if FS.TotemBar and FS.TotemBar.Sync then FS.TotemBar.Sync() end
        end,
        -- the buff tab: IMBUE and SHIELD, right of the totem tab (mockup shaman-buff-tab-2026-10-12)
        also = {
            {
                key = "shamanbuff", after = 16, cols = 2, rows = 1,
                wants = function()
                    local tab = FS.BuffTab
                    return tab and tab.OwnsShoulder and tab.OwnsShoulder()
                end,
                changed = function()
                    if FS.BuffTab and FS.BuffTab.Sync then FS.BuffTab.Sync() end
                end,
            },
        },
    },
}
-- The five second rule tab: a shoulder of any class whose FiveSecondTab says so, seated after the class's own.
local FIVE = {
    key = "fivesecond", cols = 2, rows = 1, after = 16,
    wants = function()
        local tab = FS.FiveSecondTab
        return tab and tab.OwnsShoulder and tab.OwnsShoulder()
    end,
    changed = function()
        if FS.FiveSecondTab and FS.FiveSecondTab.Sync then FS.FiveSecondTab.Sync() end
    end,
}
-- every shoulder def, flat: the owner's first, then its `also` list, then the five second rule tab
local DEFS = {}
for _, owner in pairs(OWNERS) do
    owner.dx = owner.dx or C.DX
    owner.w, owner.h = BlockSize(owner.cols, owner.rows)
    DEFS[owner.key] = owner
    for _, extra in ipairs(owner.also or {}) do
        extra.dx = extra.dx or C.DX
        extra.w, extra.h = BlockSize(extra.cols, extra.rows)
        DEFS[extra.key] = extra
    end
end
FIVE.dx = C.DX
FIVE.w, FIVE.h = BlockSize(FIVE.cols, FIVE.rows)
DEFS[FIVE.key] = FIVE

local stands = {}      -- key -> { shoulder, shown }: built once per def, never resized (NewShoulder has no resize)
local primary             -- the def of the player's class's first shoulder (what the key-less calls answer)
local holdsGap = false
local gapKey              -- the span in force, so an unchanged gap is not asked for again
local links = {}        -- plain line textures over the top line between two shoulders
local pending = false
local failed = false
local warned = {}
ClassShoulder.shoulder = nil     -- the first shoulder's art object while it stands

local function Scale()
    return (FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1
end

-- One chat line per distinct problem (LogDegradeOnce does not dedupe).
local function WarnOnce(key, text)
    if warned[key] then return end
    warned[key] = true
    if FS.LogDegradeOnce then FS.LogDegradeOnce(key, "|cffff4488Forever STUwave|r: " .. text) end
end

local function Console()
    local console = FS.Console
    if type(console) == "table" and type(console.IsDrawn) == "function" and console.root then return console end
end

-- The player's class token, or nil when it cannot be read plainly.
local function PlayerClass()
    local ok, _, token = pcall(UnitClass, "player")
    if not ok or FS.IsSecret(token) or type(token) ~= "string" then return nil end
    return token
end

-- The shoulders the player's class wants right now, in order (the Console drawn is the first condition), and the
-- console.
local function Wanted()
    local owner = OWNERS[PlayerClass()]
    primary = owner
    local console = Console()
    if not (console and console.IsDrawn()) then return console, {} end
    local list = {}
    -- a def's size follows its colsFn; a def with `after` stands that far right of the one before it
    local function Seat(def)
        if def.colsFn then
            local ok, cols = pcall(def.colsFn)
            if ok and type(cols) == "number" and cols >= 1 and cols ~= def.cols then
                def.cols = cols
                def.w, def.h = BlockSize(cols, def.rows)
            end
        end
        if def.after then
            local last = list[#list]
            def.dx = last and (last.dx + last.w + def.after) or C.DX
        end
        list[#list + 1] = def
    end
    if owner then
        if owner.wants() then Seat(owner) end
        for _, extra in ipairs(owner.also or {}) do
            if extra.wants() then Seat(extra) end
        end
    end
    if FIVE.wants() then Seat(FIVE) end
    return console, list
end

local function Build(console, def)
    if failed then return nil end
    local dock = FS.PetDock
    if not (dock and dock.NewShoulder) then
        failed = true
        WarnOnce("classshoulder_nodock", "no PetDock, the class shoulder is not drawn")
        return nil
    end
    local top = console.FILL_TOP
    local stroke = console.OUTLINE_ALPHA
    local glow = console.GLOW
    if not (type(top) == "table" and type(stroke) == "number" and type(glow) == "table") then
        failed = true
        WarnOnce("classshoulder_notokens", "the Console exports no chassis look, the class shoulder is not drawn")
        return nil
    end
    local ok, made, why = pcall(dock.NewShoulder, console.root, def.w, def.h, {
        chassis = {
            fill = { top[1], top[2], top[3], top[4] },
            strokeAlpha = stroke,
            haloAlpha = C.HALO_ALPHA,
            halo = glow,
        },
    })
    if not ok or not made then
        failed = true
        WarnOnce("classshoulder_build", "the class shoulder failed to build (" .. tostring(ok and why or made) .. ")")
        return nil
    end
    return made
end

local function Stand(key)
    local def = key and DEFS[key] or primary
    local st = def and stands[def.key]
    if st and st.shown and st.shoulder then return st, def end
end

-- The Console gap for the shoulders standing: line x0, x1 and halo x0, x1, each the widest of every shoulder's own
-- span (the spans of neighbours overlap or touch; the stretch of line a union opens between two is joined).
local function UnionSpan(list)
    local a, b, c, d
    for _, item in ipairs(list) do
        local x0, x1, h0, h1 = item.st.shoulder:GapSpan(item.def.dx)
        if x0 then
            a, c = math.min(a or x0, x0), math.min(c or h0, h0)
            b, d = math.max(b or x1, x1), math.max(d or h1, h1)
        end
    end
    return a, b, c, d
end

-- Plain line pieces over the Console's top line where the union of the gaps opened it between two shoulders
-- (their own halo pieces already cover the glow there). One texture per such stretch, the Console's line colour.
local function SeatLinks(console, list)
    local used = 0
    local art = console.art
    local theme = FS.Theme
    local colour = theme and theme.COLOR_BORDER
    if art and colour and type(console.OUTLINE_ALPHA) == "number" then
        local sorted = {}
        for _, item in ipairs(list) do sorted[#sorted + 1] = item end
        table.sort(sorted, function(l, r) return l.def.dx < r.def.dx end)
        for i = 1, #sorted - 1 do
            local _, endsAt = sorted[i].st.shoulder:GapSpan(sorted[i].def.dx)
            local startsAt = sorted[i + 1].st.shoulder:GapSpan(sorted[i + 1].def.dx)
            if endsAt and startsAt and startsAt > endsAt then
                used = used + 1
                local tex = links[used]
                if not tex then
                    tex = art:CreateTexture(nil, "BORDER", nil, 0)
                    links[used] = tex
                end
                tex:SetColorTexture(colour[1], colour[2], colour[3], console.OUTLINE_ALPHA)
                tex:ClearAllPoints()
                tex:SetPoint("TOPLEFT", art, "TOPLEFT", endsAt, 0)
                tex:SetSize(startsAt - endsAt, 1)
                tex:Show()
            end
        end
    end
    for i = used + 1, #links do links[i]:Hide() end
end

-- Takes the Console's top gap (PetDock yields first) for the shoulders standing, and widens or narrows it when the
-- set changes. Nothing is asked of the Console while the span is the one already in force.
local function SyncGap(console, list)
    local dock = FS.PetDock
    if #list == 0 then
        SeatLinks(console, list)
        if holdsGap then
            holdsGap, gapKey = false, nil
            if console.SetDockGap then console.SetDockGap(nil, nil) end
            if dock and dock.ReclaimGap then dock.ReclaimGap(C.OWNER) end
        end
        return
    end
    if not holdsGap and not (dock and dock.YieldGap and dock.YieldGap(C.OWNER)) then
        WarnOnce("classshoulder_gap", "another module holds the Console's top gap, the class shoulder leaves it alone")
        return
    end
    local a, b, c, d = UnionSpan(list)
    local key = tostring(a) .. ":" .. tostring(b) .. ":" .. tostring(c) .. ":" .. tostring(d)
    if holdsGap and gapKey == key then
        SeatLinks(console, list)
        return
    end
    if console.SetDockGap(a, b, c, d) then
        holdsGap, gapKey = true, key
        SeatLinks(console, list)
    else
        pending = true
    end
end

-- Seats and shows one shoulder; true when it was not standing before.
local function ShowOne(console, def)
    local st = stands[def.key]
    if not st then
        st = {}
        stands[def.key] = st
    end
    -- the art for this width (built once per width: NewShoulder has no resize); the one before it goes
    st.byCols = st.byCols or {}
    local art = st.byCols[def.cols]
    if not art then
        art = Build(console, def)
        st.byCols[def.cols] = art
    end
    local resized = st.shoulder ~= nil and st.shoulder ~= art
    if resized then st.shoulder.art:Hide() end
    st.shoulder = art or st.shoulder
    if not st.shoulder then return false end
    -- Seat first (the art stands on the chassis top edge), then the scale and level; the art shows only
    -- once it is where it belongs.
    st.shoulder:Seat("BOTTOMLEFT", console.root, "TOPLEFT", def.dx, 0)
    st.shoulder:Rescale()
    st.shoulder.art:Show()
    local was, seat = st.shown, st.dx
    st.shown, st.dx = true, def.dx
    return not was or seat ~= def.dx or resized
end

-- The one entry: builds, seats, shows or hides to match the world. Out of combat only; a request in combat
-- waits for PLAYER_REGEN_ENABLED. The owners are told once per change, after the gap is settled.
function ClassShoulder.Refresh()
    if InCombatLockdown() then
        pending = true
        return
    end
    pending = false
    local console, wanted = Wanted()
    local want, told = {}, {}
    for _, def in ipairs(wanted) do want[def.key] = true end
    for key, st in pairs(stands) do
        if st.shown and not want[key] then
            if st.shoulder then st.shoulder.art:Hide() end
            st.shown = false
            told[#told + 1] = DEFS[key]
        end
    end
    local list = {}
    for _, def in ipairs(wanted) do
        if ShowOne(console, def) then told[#told + 1] = def end
        local st = stands[def.key]
        if st and st.shown then list[#list + 1] = { st = st, def = def } end
    end
    -- the first shoulder's art object stays reachable after it hides (it is built once)
    local first = primary and stands[primary.key]
    if first and first.shoulder then ClassShoulder.shoulder = first.shoulder end
    if console then
        SyncGap(console, list)
    elseif holdsGap then
        holdsGap, gapKey = false, nil
        local bare = FS.Console
        if type(bare) == "table" and bare.SetDockGap then bare.SetDockGap(nil, nil) end
        if FS.PetDock and FS.PetDock.ReclaimGap then FS.PetDock.ReclaimGap(C.OWNER) end
    end
    for _, def in ipairs(told) do
        if def.changed then pcall(def.changed) end
    end
end

-- true while the shoulder (the class's first, or the one named by `key`) stands.
function ClassShoulder.IsShown(key)
    return Stand(key) ~= nil
end

-- The shoulder object (PetDock.NewShoulder's) of the class's first shoulder, or the one named by `key`, while it
-- stands; nil otherwise. The owner draws on it (the totem tab's hover bump opens the top rail through it).
function ClassShoulder.Shoulder(key)
    local st = Stand(key)
    return st and st.shoulder or nil
end

-- The standing block's size and button edge in UI units (design px x the layout scale), or nil while no
-- shoulder stands.
function ClassShoulder.BlockSize(key)
    local st, def = Stand(key)
    if not st then return nil end
    local s = Scale()
    return def.w * s, def.h * s, C.BTN * s
end

-- Calls fn(dx, width, height) for every shoulder standing right now, in no particular order: how far in from
-- the chassis left, how wide and how tall the block is, all in design px (the block itself, its halo not
-- counted); it stands on the chassis top line. Nothing is visited while the Console is not drawn. For whoever has
-- to keep clear of the Console art without keeping a list of the class tabs (the cast bars, CastBars.lua).
function ClassShoulder.EachStanding(fn)
    for key, st in pairs(stands) do
        local def = DEFS[key]
        if st.shown and st.shoulder and def then fn(def.dx, def.w, def.h) end
    end
end

-- The owner's seat, from the same numbers: nil while no shoulder stands (the owner then uses its own).
function ClassShoulder.HostPoint(key)
    local st, def = Stand(key)
    if not st then return nil end
    return "BOTTOMLEFT", st.shoulder.parent, "TOPLEFT", def.dx * Scale(), 0
end

function ClassShoulder.SlotPoint(host, row, col, key)
    local st, def = Stand(key)
    if not st then return nil end
    local s, pitch = Scale(), C.BTN + C.GAP
    return "BOTTOMLEFT", host, "BOTTOMLEFT", (C.PAD + (col - 1) * pitch) * s, (C.PB + (def.rows - row) * pitch) * s
end

-- The Console geometry callback and the rescale watcher register at file load, ahead of SealBar's own
-- (login time), so the shoulder is up before SealBar seats its host on a notice.
if FS.ActionBars and FS.ActionBars.OnGeometry then FS.ActionBars.OnGeometry(ClassShoulder.Refresh) end
if FS.Layout and FS.Layout.OnRescale then FS.Layout.OnRescale(ClassShoulder.Refresh) end

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:SetScript("OnEvent", function()
    if pending then ClassShoulder.Refresh() end
end)
