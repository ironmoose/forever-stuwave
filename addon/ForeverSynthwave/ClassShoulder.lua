-- Forever Synthwave: the Paladin shoulder CHROME
--
-- The approved Gunsight mockup draws a shoulder block on the Console chassis' top edge, behind the Paladin's
-- seal and aura buttons (`LS_*`: 306.8 x 91.8 design px, 36 in from the chassis left). In the mockup's default
-- Console style (`PS === 'cn'`) it is NOT the pet panel's recipe (`lsLive` runs only for the other styles):
-- `cnTrace` carries the shoulders, so `cnBake` strokes it with the chassis outline (A(.72)), halos it with
-- the very halo the chassis gets and fills it with the chassis gradient, whose top stop is all a shoulder
-- above the chassis ever shows. This file builds that: `PetDock.NewShoulder` with `opts.chassis` (the
-- Console's own fill tint and stroke alpha and the Console's own baked halo, `Console.GLOW`, drawn strip for
-- strip with vertex alpha 1, no fill overrun into the line row), seated on the Console root, owning the
-- Console's top gap while it stands. The halo is therefore the Console's own profile by construction (the
-- mockup's stepped composite of four nested strokes: .546 at the edge, stepping down to nothing by 10 px).
--
-- It builds ONLY for a Paladin (SealBar owns the forms), ONLY while the Console is drawn, ONLY out of combat.
-- The art is a plain non-secure child of the Console root. SealBar's host (protected, it parents the secure
-- buttons) is its own frame anchored to the Console root, NEVER to this art: nothing secure may be anchored to
-- or parented under it, which is what keeps Seat/Rescale/Show/Hide legal here. They still wait for
-- PLAYER_REGEN_ENABLED in combat, like everything on the chassis. SealBar asks HostPoint/SlotPoint for its
-- seat and falls back to its own when this returns nil (no Console, a failed build).
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
    COLS = 7,
    ROWS = 2,
    HALO_ALPHA = 1,    -- vertex alpha on the Console's own baked halo (1 = the Console's profile, as is)
}
C.W = 2 * C.PAD + C.COLS * C.BTN + (C.COLS - 1) * C.GAP
C.H = C.PT + C.ROWS * C.BTN + (C.ROWS - 1) * C.GAP + C.PB
ClassShoulder.C = C

local shoulder
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

local function Wanted()
    local seal = FS.SealBar
    if not (seal and seal.OwnsForms and seal.OwnsForms()) then return nil end
    local console = Console()
    if console and console.IsDrawn() then return console end
end

local function Build(console)
    if failed then return nil end
    local dock = FS.PetDock
    if not (dock and dock.NewShoulder) then
        failed = true
        WarnOnce("classshoulder_nodock", "no PetDock, the Paladin shoulder is not drawn")
        return nil
    end
    local top = console.FILL_TOP
    local stroke = console.OUTLINE_ALPHA
    local glow = console.GLOW
    if not (type(top) == "table" and type(stroke) == "number" and type(glow) == "table") then
        failed = true
        WarnOnce("classshoulder_notokens", "the Console exports no chassis look, the Paladin shoulder is not drawn")
        return nil
    end
    local ok, made, why = pcall(dock.NewShoulder, console.root, C.W, C.H, {
        chassis = {
            fill = { top[1], top[2], top[3], top[4] },
            strokeAlpha = stroke,
            haloAlpha = C.HALO_ALPHA,
            halo = glow,
        },
    })
    if not ok or not made then
        failed = true
        WarnOnce("classshoulder_build", "the Paladin shoulder failed to build (" .. tostring(ok and why or made) .. ")")
        return nil
    end
    ClassShoulder.shoulder = made
    return made
end

-- Takes the Console's top gap (PetDock yields first), once per stretch the shoulder stands.
local function TakeGap(console)
    local dock = FS.PetDock
    if holdsGap then return end
    if not (dock and dock.YieldGap and dock.YieldGap(C.OWNER)) then
        WarnOnce("classshoulder_gap", "another module holds the Console's top gap, the Paladin shoulder leaves it alone")
        return
    end
    if console.SetDockGap(shoulder:GapSpan(C.DX)) then
        holdsGap = true
    else
        pending = true
    end
end

local function Show(console)
    shoulder = shoulder or Build(console)
    if not shoulder then return end
    -- Seat first (the art stands on the chassis top edge), then the scale and level; the art shows only
    -- once it is where it belongs.
    shoulder:Seat("BOTTOMLEFT", console.root, "TOPLEFT", C.DX, 0)
    shoulder:Rescale()
    shoulder.art:Show()
    shown = true
    TakeGap(console)
end

local function Hide()
    if shoulder and shown then shoulder.art:Hide() end
    shown = false
    if holdsGap then
        holdsGap = false
        local console = FS.Console
        if type(console) == "table" and console.SetDockGap then console.SetDockGap(nil, nil) end
        if FS.PetDock and FS.PetDock.ReclaimGap then FS.PetDock.ReclaimGap(C.OWNER) end
    end
end

-- The one entry: builds, seats, shows or hides to match the world. Out of combat only; a request in combat
-- waits for PLAYER_REGEN_ENABLED.
function ClassShoulder.Refresh()
    if InCombatLockdown() then
        pending = true
        return
    end
    pending = false
    local console = Wanted()
    if console then Show(console) else Hide() end
end

function ClassShoulder.IsShown()
    return shown
end

-- SealBar's seat, from the same numbers: nil while no shoulder stands (SealBar then uses its own).
function ClassShoulder.HostPoint()
    if not (shown and shoulder) then return nil end
    return "BOTTOMLEFT", shoulder.parent, "TOPLEFT", C.DX * Scale(), 0
end

function ClassShoulder.SlotPoint(host, row, col)
    if not (shown and shoulder) then return nil end
    local s, pitch = Scale(), C.BTN + C.GAP
    return "BOTTOMLEFT", host, "BOTTOMLEFT", (C.PAD + (col - 1) * pitch) * s, (C.PB + (C.ROWS - row) * pitch) * s
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
