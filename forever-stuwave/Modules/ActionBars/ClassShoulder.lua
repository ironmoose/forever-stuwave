-- Forever STUwave: the class shoulder CHROME (Paladin, Warrior)
--
-- The approved Gunsight mockup draws a shoulder block on the Console chassis' top edge, behind the Paladin's
-- seal and aura buttons (`LS_*`: 306.8 x 91.8 design px, 36 in from the chassis left) and behind the Warrior's
-- three stances (`{id:'st',n:3,rows:1}`: 135.6 x 49). In the mockup's default
-- Console style (`PS === 'cn'`) it is NOT the pet panel's recipe (`lsLive` runs only for the other styles):
-- `cnTrace` carries the shoulders, so `cnBake` strokes it with the chassis outline (A(.72)), halos it with
-- the very halo the chassis gets and fills it with the chassis gradient, whose top stop is all a shoulder
-- above the chassis ever shows. This file builds that: `PetDock.NewShoulder` with `opts.chassis` (the
-- Console's own fill tint and stroke alpha and the Console's own baked halo, `Console.GLOW`, drawn strip for
-- strip with vertex alpha 1, no fill overrun into the line row), seated on the Console root, owning the
-- Console's top gap while it stands. The halo is therefore the Console's own profile by construction (the
-- mockup's stepped composite of four nested strokes: .546 at the edge, stepping down to nothing by 10 px).
--
-- It builds ONLY for a class in OWNERS (a Paladin whose SealBar owns the forms, a Warrior whose StanceBar does),
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
-- Loads after PetDock.lua and ConsoleKeys.lua, before SealBar.lua. Nothing here is verified in game.

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
}
for _, owner in pairs(OWNERS) do owner.w, owner.h = BlockSize(owner.cols, owner.rows) end

local shoulder
local shoulders = {}      -- built once per owner, never resized (NewShoulder has no resize)
local standing            -- the owner whose shoulder is `shoulder`
local shown = false
local holdsGap = false
local pending = false
local failed = false
local warned = {}

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

local function Wanted()
    local owner = OWNERS[PlayerClass()]
    if not (owner and owner.wants()) then return nil end
    local console = Console()
    if console and console.IsDrawn() then return console, owner end
end

local function Build(console, owner)
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
    local ok, made, why = pcall(dock.NewShoulder, console.root, owner.w, owner.h, {
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

-- Takes the Console's top gap (PetDock yields first), once per stretch the shoulder stands.
local function TakeGap(console)
    local dock = FS.PetDock
    if holdsGap then return end
    if not (dock and dock.YieldGap and dock.YieldGap(C.OWNER)) then
        WarnOnce("classshoulder_gap", "another module holds the Console's top gap, the class shoulder leaves it alone")
        return
    end
    if console.SetDockGap(shoulder:GapSpan(C.DX)) then
        holdsGap = true
    else
        pending = true
    end
end

-- Tells the owner its seat appeared or went, once per change; its failure must not stop the shoulder.
local function Notify()
    if standing and standing.changed then pcall(standing.changed) end
end

local function Show(console, owner)
    shoulders[owner.key] = shoulders[owner.key] or Build(console, owner)
    shoulder, standing = shoulders[owner.key], owner
    ClassShoulder.shoulder = shoulder
    if not shoulder then return end
    -- Seat first (the art stands on the chassis top edge), then the scale and level; the art shows only
    -- once it is where it belongs.
    shoulder:Seat("BOTTOMLEFT", console.root, "TOPLEFT", C.DX, 0)
    shoulder:Rescale()
    shoulder.art:Show()
    local was = shown
    shown = true
    TakeGap(console)
    if not was then Notify() end
end

local function Hide()
    local was = shown
    if shoulder and shown then shoulder.art:Hide() end
    shown = false
    if holdsGap then
        holdsGap = false
        local console = FS.Console
        if type(console) == "table" and console.SetDockGap then console.SetDockGap(nil, nil) end
        if FS.PetDock and FS.PetDock.ReclaimGap then FS.PetDock.ReclaimGap(C.OWNER) end
    end
    if was then Notify() end
end

-- The one entry: builds, seats, shows or hides to match the world. Out of combat only; a request in combat
-- waits for PLAYER_REGEN_ENABLED.
function ClassShoulder.Refresh()
    if InCombatLockdown() then
        pending = true
        return
    end
    pending = false
    local console, owner = Wanted()
    if console then Show(console, owner) else Hide() end
end

function ClassShoulder.IsShown()
    return shown
end

-- The standing block's size and button edge in UI units (design px x the layout scale), or nil while no
-- shoulder stands.
function ClassShoulder.BlockSize()
    if not (shown and shoulder) then return nil end
    local s = Scale()
    return standing.w * s, standing.h * s, C.BTN * s
end

-- The owner's seat, from the same numbers: nil while no shoulder stands (the owner then uses its own).
function ClassShoulder.HostPoint()
    if not (shown and shoulder) then return nil end
    return "BOTTOMLEFT", shoulder.parent, "TOPLEFT", C.DX * Scale(), 0
end

function ClassShoulder.SlotPoint(host, row, col)
    if not (shown and shoulder) then return nil end
    local s, pitch = Scale(), C.BTN + C.GAP
    return "BOTTOMLEFT", host, "BOTTOMLEFT", (C.PAD + (col - 1) * pitch) * s, (C.PB + (standing.rows - row) * pitch) * s
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
