-- Forever STUwave: LayoutEdit
-- /fsedit: an edit mode that lays one insecure drag handle over each movable frame and
-- writes the drop through FS.Layout.SetOverride. The covered frames are never dragged, so
-- secure ones stay untouched. Loads after the modules whose frames it reads (see .toc).
-- Each raid size (5 to 40) has its own layout entry (raid5 .. raid40) and no frame of its own to cover out of a raid, so
-- while the editor is on RaidFrames.lua shows a preview grid (fake members, a size per button on the panel) at the seat
-- of the size picked, and that size's "Raid N" handle covers it.
-- A handle's outline is drawn outside the covered frame, clear of its own border, and never over the frame's content.
-- While it is on, the editor also draws the snap grid (a pooled set of one pixel lines, the lattice the selected piece
-- snaps to), shows an X / Y position panel over the selected piece (type an exact spot, in pixels or grid units), and a
-- right click on a piece opens a small menu: Settings (the config page for that piece), Set position, Reset position.

local _, FS = ...

local LayoutEdit = FS.LayoutEdit or {}
FS.LayoutEdit = LayoutEdit

local PREFIX = "|cff22e0ffstuwave://layout|r  "
local GRID_CHOICES = { [4] = true, [8] = true, [16] = true, [32] = true }
local GRID_DEFAULT = 8
local MIN_HANDLE = 12
local EDGE_PX, GAP_PX = 2, 3     -- a handle's outline: a ring two physical pixels thick, three clear of the covered frame
local LABEL_GAP, LABEL_ROOM = 2, 22   -- a raid handle's label sits this far outside the ring, and needs this much screen above it
local PAGE_KEY = "layout"
-- Sizes from the frames sheet SPEC (mockups/config-rebuild-2026-11-24.html, frame H), in UI units, under the SPEC's
-- own names; the rest are this file's (they follow the same whole unit rules). One table: a file holds only so many locals.
local SPEC = {
    ROW_H = 32, SEG_H = 24, SEG_PAD_X = 8, SEG_GAP = 4, TEXT_SNAP = 4,
    SW_W = 44, SW_H = 20, KNOB_W = 16, KNOB_H = 12, KNOB_INSET = 4,
    Q = 12, MENU_W = 184, MENU_ROW_H = 24,
    BAR_PAD = 8, BAR_GAP = 8,     -- the panels' row: edge to first part, and part to part
    FIELD_W = 96, FIELD_H = 24,   -- a typed value box; the SPEC's VALUE_W 60 clips -1009.5 and its unit
    POS_GAP = 8,                  -- the position panel's clear space above (or below) the handle's ring
    MENU_PAD = 4, MENU_SEP = 1,   -- the menu's inner padding, and its rules
    MAX_LINES = 2400,             -- a grid with more lines than this (a tiny step on a huge screen) draws nothing
    GRID_ALPHA = 0.16, CROSS_ALPHA = 0.9,
    BAD_FLASH = 0.45,             -- seconds a refused field stays pink
    LIVE_EVERY = 0.05,            -- seconds between position reads while a piece is dragged
    STRATA_UP = "FULLSCREEN_DIALOG", STRATA_UNDER = "HIGH",   -- the editor's frames, and under an open config window
    GRID_UP = "FULLSCREEN", GRID_UNDER = "HIGH",
}
local DONE_W, DONE_H = 64, 24
local PANEL_H = SPEC.ROW_H + 4    -- the Done panel's and the position panel's one row
-- The raid size chips, the row they sit in (under the title row) and the panel's right padding, in UI units.
local SIZE_W, SIZE_H, SIZE_GAP, SIZE_ROW, SIZE_PAD = 26, 22, 4, 30, 8

-- Display order is also the label table; an id without an applied frame gets no handle.
local MOVABLE = {
    { id = "player",       label = "Player frame" },
    { id = "target",       label = "Target frame" },
    { id = "chat",         label = "Chat" },
    { id = "minimap",      label = "Minimap" },
    { id = "buffs",        label = "Buffs" },
    { id = "debuffs",      label = "Debuffs" },
    { id = "party",        label = "Party" },
    { id = "raid5",        label = "Raid 5",  raid = true },
    { id = "raid10",       label = "Raid 10", raid = true },
    { id = "raid15",       label = "Raid 15", raid = true },
    { id = "raid20",       label = "Raid 20", raid = true },
    { id = "raid25",       label = "Raid 25", raid = true },
    { id = "raid40",       label = "Raid 40", raid = true },
    { id = "focus",        label = "Focus" },
    { id = "boss",         label = "Boss" },
    { id = "stance",       label = "Stance bar" },
    { id = "action",       label = "Action bars" },
    { id = "professions",  label = "Professions" },
    { id = "petcontainer", label = "Pet" },
    { id = "tooltip",      label = "Tooltip" },
    { id = "tcast",        label = "Target cast bar" },
    { id = "pcast",        label = "Player cast bar" },
    { id = "objectives",   label = "Objectives" },
    { id = "warriorpowerup", label = "Warrior power-up alerts" },
    { id = "druidclearcasting", label = "Clearcasting alert" },
}

-- The ids of the raid layouts: only the previewed size's handle is ever up.
local RAID_IDS = {}
for _, def in ipairs(MOVABLE) do
    if def.raid then RAID_IDS[def.id] = true end
end

-- Where each handle's "Settings" goes: the /fsconfig page and tab (the keys of the config window's nav), and the row
-- that scrolls into view with the jump outline. `row` is optional; `none = true` is a piece that has no settings (its
-- menu row is greyed and says so): the cast bars and the buffs and debuffs pages are only a "No settings yet" note today,
-- so their entries keep the page and tab and flip to live by dropping `none` once that page has rows.
-- One entry per MOVABLE id: the harness fails when one is missing.
local PIECES = {
    player         = { page = "unit",     tab = "bars",    row = "bars.w" },
    target         = { page = "unit",     tab = "bars",    row = "bars.w" },
    focus          = { page = "unit",     tab = "bars",    row = "bars.w" },
    boss           = { page = "unit",     tab = "bars",    row = "bars.w" },
    party          = { page = "party",    tab = "style",   row = "bars.w" },
    raid5          = { page = "raid",     tab = "style",   row = "raid.scale" },
    raid10         = { page = "raid",     tab = "style",   row = "raid.scale" },
    raid15         = { page = "raid",     tab = "style",   row = "raid.scale" },
    raid20         = { page = "raid",     tab = "style",   row = "raid.scale" },
    raid25         = { page = "raid",     tab = "style",   row = "raid.scale" },
    raid40         = { page = "raid",     tab = "style",   row = "raid.scale" },
    petcontainer   = { page = "pet",      tab = "style",   row = "bars.w" },
    tcast          = { page = "cast",     tab = "g",       none = true },
    pcast          = { page = "cast",     tab = "g",       none = true },
    stance         = { page = "ab",       tab = "g" },
    action         = { page = "ab",       tab = "g" },
    buffs          = { page = "auras",    tab = "g",       none = true },
    debuffs        = { page = "auras",    tab = "g",       none = true },
    chat           = { page = "chat",     tab = "g",       row = "chat.w" },
    minimap        = { page = "mini",     tab = "g",       row = "minimap.w" },
    objectives     = { page = "track",    tab = "g",       row = "tracker.w" },
    professions    = { page = "skins",    tab = "win",     row = "professions.shown" },
    warriorpowerup = { page = "classmod", tab = "warrior", row = "gunsight.warrior.powerups" },
    druidclearcasting = { page = "classmod", tab = "druid", row = "gunsight.druid.clearcasting" },
    tooltip        = { none = true },
}

-- Pieces that FS.Layout does not seat. Each provider answers Ready, Rect, Offsets, Move(x, y) and Reset;
-- the objectives tracker is a Blizzard Edit Mode system, so its seat is written into the Edit Mode layout.
local function Provider(id)
    if id == "objectives" then
        local seat = FS.TrackerSeat
        if type(seat) == "table" and type(seat.Ready) == "function" then return seat end
    end
end

-- The raid grid's editor preview (RaidFrames.lua), or nil where the raid frames did not load. A raid layout has no frame
-- of its own out of a raid (the real grid is only seated for the size the roster fills, and may not be up), so its
-- handle covers this preview, which sits at the seat of the size being previewed.
local function RaidPreview()
    local raid = FS.RaidFrames
    local preview = type(raid) == "table" and raid.Preview
    if type(preview) == "table" and type(preview.Show) == "function" and type(preview.Rect) == "function"
        and type(preview.SeatId) == "function" then
        return preview
    end
end

-- True while the preview is up at the seat `id` and has a rect to cover.
local function RaidSeatUp(id)
    local preview = RaidPreview()
    return preview ~= nil and preview.IsShown() == true and preview.SeatId() == id and preview.Rect() ~= nil
end

local ARROWS = { UP = { 0, 1 }, DOWN = { 0, -1 }, LEFT = { -1, 0 }, RIGHT = { 1, 0 } }

if FS.Config and FS.Config.RegisterDefault then
    FS.Config.RegisterDefault("layout.snap", true)
    FS.Config.RegisterDefault("layout.grid", GRID_DEFAULT)
    FS.Config.RegisterDefault("layout.showGrid", true)
    FS.Config.RegisterDefault("layout.posUnit", "px")
end

local editing = false
local selected = nil
local dragging = nil
local handles = {}
local overlay = nil
local donePanel = nil
local gridFrame = nil       -- the pooled grid lines (RefreshGrid)
local posPanel = nil        -- the X / Y panel over the selected piece
local menu = nil            -- the right click menu and its click catcher
local configOver = false    -- the config window was opened over the editor: the editor's frames sit under it
local strata, gridStrata = SPEC.STRATA_UP, SPEC.GRID_UP
-- Forward declared: the geometry below tells the grid and the position panel when a handle moved or the pick changed.
local RefreshGrid, RefreshPosition
local returnToConfig = false   -- the config page DONE or Esc reopens, when the config window started the edit
local pageRegistered = false
local editListeners = {}   -- fn(editing) after the editor switches on or off (WarriorPowerUps.lua shows a static preview while it is on)

-- fn(editing) runs after the editor turns on (true) and after it turns off (false). A listener that throws is skipped.
function LayoutEdit.OnEditChanged(fn)
    if type(fn) == "function" then editListeners[#editListeners + 1] = fn end
end

local function EditChanged()
    for i = 1, #editListeners do pcall(editListeners[i], editing) end
end
local blizzardHooked = false

local function Say(text)
    print(PREFIX .. text)
end

local function Cyan()
    local c = FS.Theme and FS.Theme.COLOR_POWER
    return c and c[1] or 0.133, c and c[2] or 0.878, c and c[3] or 1
end

-- A theme colour by name, or the fallback table where the theme (or that token) is not loaded.
local function Token(name, fallback)
    local value = FS.Theme and FS.Theme[name]
    if type(value) == "table" then return value end
    return fallback
end

-- The frames sheet palette: pink = it is on, cyan = you are on it.
local function Palette()
    return {
        cyan = Token("COLOR_POWER", { 0.133, 0.878, 1, 1 }),
        pink = Token("COLOR_HEALTH", { 1, 0.18, 0.592, 1 }),
        violet = Token("COLOR_BORDER", { 0.659, 0.333, 0.969, 1 }),
        ink = Token("COLOR_CTRL_INK", { 0.027, 0.012, 0.055, 1 }),
        dim = Token("COLOR_CTRL_DIM", { 0.294, 0.165, 0.525, 1 }),
        sel = Token("COLOR_CTRL_SEL", { 0.165, 0.059, 0.18, 1 }),
        dis = Token("COLOR_CTRL_DIS", { 0.361, 0.329, 0.502, 1 }),
        text = Token("COLOR_CTRL_TEXT", { 0.914, 0.886, 1, 1 }),
        hair = Token("COLOR_CTRL_HAIR", { 0.227, 0.129, 0.408, 1 }),
        muted = Token("COLOR_MUTED", { 0.616, 0.576, 0.769, 1 }),
    }
end

-------------------------------------------------------------------------------
-- Settings and lookups
-------------------------------------------------------------------------------

local function SnapOn()
    return not (FS.Config and FS.Config.Get("layout.snap") == false)
end

local function GridStep()
    local value = FS.Config and FS.Config.Get("layout.grid")
    if type(value) == "number" and GRID_CHOICES[value] then return value end
    return GRID_DEFAULT
end

local function ShowGridOn()
    return not (FS.Config and FS.Config.Get("layout.showGrid") == false)
end

-- "px" (the layout's own units) or "grid" (that over the grid step) for the position boxes.
local function PosUnit()
    return FS.Config and FS.Config.Get("layout.posUnit") == "grid" and "grid" or "px"
end

local function Snap(v)
    local step = GridStep()
    return math.floor(v / step + 0.5) * step
end

local function BlizzardEditModeActive()
    local manager = _G.EditModeManagerFrame
    if type(manager) ~= "table" or type(manager.IsEditModeActive) ~= "function" then return false end
    local ok, active = pcall(manager.IsEditModeActive, manager)
    return ok and active == true
end

-- A minimised or maximised chat derives its own geometry, so it is not draggable until restored.
local function ChatIsNormal()
    local state = FS.Chat and FS.Chat.windowState
    return state == nil or state == "normal"
end

local function LegacyPetPosition()
    local saved = type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.petFrame
    return type(saved) == "table" and type(saved.pos) == "table" and saved.pos
end

local function ClearLegacyPetPosition()
    if LegacyPetPosition() then ForeverSTUwaveDB.petFrame.pos = nil end
end

-- The frame a layout id is seated on, preferring a shown one.
local function AppliedFrame(id)
    local found
    for frame, info in pairs(FS.Layout._applied) do
        if info.id == id and info.parent == nil then
            if frame.IsShown and frame:IsShown() then return frame end
            found = found or frame
        end
    end
    return found
end

-- Stack A's cast bars only draw while the Gunsight HUD is off; with its tapes up there is nothing to move.
local STACK_A = { pcast = true, tcast = true }

local function StackAIdle(id)
    if not STACK_A[id] then return false end
    local castBars = FS.CastBars
    return type(castBars) == "table" and type(castBars.IsStackActive) == "function" and castBars.IsStackActive() == false
end

-- Module power (Core/ModuleSwitch.lua): the piece of a module that is off, or not built yet, has no frame of ours to move,
-- so it gets no handle. The other pieces answer from their applied frame as before.
local MODULE_OF = {
    tcast = "m.cast", pcast = "m.cast", buffs = "m.auras", debuffs = "m.auras", minimap = "m.mini",
    objectives = "m.track", professions = "m.skins",
}

local function ModuleNotBuilt(id)
    local key = MODULE_OF[id]
    local MS = FS.ModuleSwitch
    return key ~= nil and MS ~= nil and not MS.Built(key)
end

local function HasHandle(id)
    if ModuleNotBuilt(id) then return false end
    if RAID_IDS[id] then return RaidSeatUp(id) end
    local provider = Provider(id)
    if provider then return provider.Ready() == true and provider.Rect() ~= nil end
    if id == "objectives" then return false end
    local L = FS.Layout[id]
    if StackAIdle(id) then return false end
    if type(L) ~= "table" or type(L.x) ~= "number" or type(L.y) ~= "number" then return false end
    if id == "chat" and not ChatIsNormal() then return false end
    return AppliedFrame(id) ~= nil
end

-------------------------------------------------------------------------------
-- Geometry
-------------------------------------------------------------------------------

-- Screen position of one anchor point of `frame`, in the frame's own units. The handles are
-- UIParent children, so their units are UIParent's and no scale conversion is needed.
local function PointXY(frame, point)
    local left, bottom, width, height = frame:GetLeft(), frame:GetBottom(), frame:GetWidth(), frame:GetHeight()
    if not (left and bottom and width and height) then return nil end
    local fx = point:find("LEFT") and 0 or point:find("RIGHT") and 1 or 0.5
    local fy = point:find("BOTTOM") and 0 or point:find("TOP") and 1 or 0.5
    return left + width * fx, bottom + height * fy
end

local function UnitScale(id)
    return FS.Layout.IsUnscaled(id) and 1 or FS.Layout.Scale()
end

-- The layout x/y the handle's current screen position stands for, in the entry's own units.
local function ReadLayoutXY(id, handle)
    if Provider(id) then
        local right, top = handle:GetRight(), handle:GetTop()
        if not (right and top) then return nil end
        return right - UIParent:GetRight(), top - UIParent:GetTop()
    end
    local L = FS.Layout[id]
    local hx, hy = PointXY(handle, L.point)
    local px, py = PointXY(UIParent, L.relPoint)
    if not (hx and px) then return nil end
    local scale = UnitScale(id)
    return (hx - px) / scale, (hy - py) / scale
end

local function CurrentXY(id)
    local provider = Provider(id)
    if provider then return provider.Offsets() end
    local L = FS.Layout[id]
    if id == "petcontainer" and LegacyPetPosition() and handles[id] then
        local x, y = ReadLayoutXY(id, handles[id])
        if x then return x, y end
    end
    return L.x, L.y
end

-- Puts the handle on the frame's layout rect, from layout coordinates and not from the frame.
-- A pet panel still holding an old /fspet drag position is the exception: that position wins
-- over the layout until the first move, so its handle starts on the frame itself.
local function SeatHandleOnRect(handle, left, top, width, height)
    handle:SetSize(math.max(width, MIN_HANDLE), math.max(height, MIN_HANDLE))
    handle:ClearAllPoints()
    handle:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", left, top)
end

local function SyncProviderHandle(id, provider)
    local handle = handles[id]
    local left, top, width, height = provider.Rect()
    if not (handle and left) then return end
    SeatHandleOnRect(handle, left, top, width, height)
end

-- A raid handle sits on the preview grid of its size, wherever the preview seated it.
local function SyncRaidHandle(id)
    local handle, preview = handles[id], RaidPreview()
    if not (handle and preview and preview.SeatId() == id) then return end
    local left, top, width, height = preview.Rect()
    if left then SeatHandleOnRect(handle, left, top, width, height) end
end

local function SeatHandle(id)
    if RAID_IDS[id] then return SyncRaidHandle(id) end
    local provider = Provider(id)
    if provider then return SyncProviderHandle(id, provider) end
    local handle, L = handles[id], FS.Layout[id]
    local frame = AppliedFrame(id)
    if not (handle and frame and L) then return end
    local scale = UnitScale(id)
    local w, h = L.w and L.w * scale, L.h and L.h * scale
    if L.noSize then
        local fw, fh = frame:GetWidth(), frame:GetHeight()
        if fw and fw > 0 and fh and fh > 0 then w, h = fw, fh end
    end
    handle:SetSize(math.max(w or MIN_HANDLE, MIN_HANDLE), math.max(h or MIN_HANDLE, MIN_HANDLE))
    handle:ClearAllPoints()
    local cx, cy, ux, uy
    if id == "petcontainer" and LegacyPetPosition() then
        cx, cy = frame:GetCenter()
        ux, uy = UIParent:GetCenter()
    end
    if cx and ux then
        handle:SetPoint("CENTER", UIParent, "CENTER", cx - ux, cy - uy)
    else
        handle:SetPoint(L.point, UIParent, L.relPoint, L.x * scale, L.y * scale)
    end
end

-- Physical pixels per UI unit at `frame` (FrameHelpers.PixelsPerUnit); 1 where the client will not say.
local function PixelsPerUnit(frame)
    local helpers = FS.FrameHelpers
    local ppu = helpers and type(helpers.PixelsPerUnit) == "function" and helpers.PixelsPerUnit(frame)
    if type(ppu) == "number" and ppu > 0 then return ppu end
    return 1
end

local function SnapToPixels(texture)
    if texture and texture.SetSnapToPixelGrid then
        pcall(texture.SetSnapToPixelGrid, texture, true)
        if texture.SetTexelSnappingBias then pcall(texture.SetTexelSnappingBias, texture, 0) end
    end
end

-- The handle's outline and tint sit OUTSIDE the frame it covers, GAP_PX clear of its edge and EDGE_PX thick, so the ring
-- never lies on the covered frame's own border (a party row's, a raid cell's) and reads as a second outline over it. The
-- handle frame is still exactly the covered rect (the mouse hit area, the drag maths); only its textures reach past it.
-- The four edges meet at the corners without overlapping, and sit on whole physical pixels for the scale they are seated
-- at, so this runs on every sync (a UI scale change syncs every handle).
local function SeatOutline(handle)
    local es = PixelsPerUnit(handle)
    local thick, out = EDGE_PX / es, (EDGE_PX + GAP_PX) / es
    local top, bottom, left, right = handle.edges[1], handle.edges[2], handle.edges[3], handle.edges[4]
    top:ClearAllPoints()
    top:SetPoint("TOPLEFT", handle, "TOPLEFT", -out, out)
    top:SetPoint("TOPRIGHT", handle, "TOPRIGHT", out, out)
    top:SetHeight(thick)
    bottom:ClearAllPoints()
    bottom:SetPoint("BOTTOMLEFT", handle, "BOTTOMLEFT", -out, -out)
    bottom:SetPoint("BOTTOMRIGHT", handle, "BOTTOMRIGHT", out, -out)
    bottom:SetHeight(thick)
    left:ClearAllPoints()
    left:SetPoint("TOPLEFT", handle, "TOPLEFT", -out, out - thick)
    left:SetPoint("BOTTOMLEFT", handle, "BOTTOMLEFT", -out, -(out - thick))
    left:SetWidth(thick)
    right:ClearAllPoints()
    right:SetPoint("TOPRIGHT", handle, "TOPRIGHT", out, out - thick)
    right:SetPoint("BOTTOMRIGHT", handle, "BOTTOMRIGHT", out, -(out - thick))
    right:SetWidth(thick)
    handle.fill:ClearAllPoints()
    handle.fill:SetPoint("TOPLEFT", handle, "TOPLEFT", -out, out)
    handle.fill:SetPoint("BOTTOMRIGHT", handle, "BOTTOMRIGHT", out, -out)
    handle.outline = out
end

-- A raid handle's label sits outside the ring, above it (below when the screen's top is too near), so it never covers the
-- grid's names. Every other handle's label stays centred on the piece.
local function SeatLabel(handle)
    if not handle.labelOutside then return end
    local label, out = handle.label, handle.outline or 0
    local top, screenTop = handle:GetTop(), UIParent:GetTop()
    local roomAbove = not (top and screenTop) or screenTop - top >= out + LABEL_ROOM
    label:ClearAllPoints()
    if roomAbove then
        label:SetPoint("BOTTOMLEFT", handle, "TOPLEFT", -out, out + LABEL_GAP)
    else
        label:SetPoint("TOPLEFT", handle, "BOTTOMLEFT", -out, -(out + LABEL_GAP))
    end
end

local function SyncHandle(id)
    SeatHandle(id)
    local handle = handles[id]
    if handle then
        SeatOutline(handle)
        SeatLabel(handle)
        if id == selected and RefreshPosition then RefreshPosition() end
    end
end

local function SyncAll()
    for id in pairs(handles) do
        if handles[id]:IsShown() then SyncHandle(id) end
    end
end

-- The selected piece went away (its frame left, or its handle was hidden): the grid and the position panel follow.
local function DropSelection()
    selected = nil
    if RefreshGrid then RefreshGrid() end
    if RefreshPosition then RefreshPosition() end
end

-------------------------------------------------------------------------------
-- What a position counts from
-------------------------------------------------------------------------------

-- The UIParent point a piece's x and y are counted from, and the one of its own points that sits there: its layout
-- entry's relPoint and point. The tracker is seated by its offsets from the screen's top right.
local function AnchorPoints(id)
    if Provider(id) then return "TOPRIGHT", "TOPRIGHT" end
    local L = FS.Layout[id]
    if type(L) ~= "table" then return "CENTER", "CENTER" end
    return L.point or "CENTER", L.relPoint or "CENTER"
end

-- How far along a frame (0 to 1, left to right and bottom to top) an anchor point sits.
local function Fractions(point)
    return point:find("LEFT") and 0 or point:find("RIGHT") and 1 or 0.5,
        point:find("BOTTOM") and 0 or point:find("TOP") and 1 or 0.5
end

-- Screen UI units per layout unit for `id`: a design pixel (Layout.Scale), or one UI unit for an unscaled entry and for
-- the tracker. With nothing picked it is the design pixel, the unit nearly every piece is seated in.
local function LayoutUnit(id)
    if id and Provider(id) then return 1 end
    if id and FS.Layout.IsUnscaled(id) then return 1 end
    return FS.Layout.Scale()
end

-------------------------------------------------------------------------------
-- Grid
-------------------------------------------------------------------------------

-- Snap() rounds a piece's x and y to whole steps, and x and y are counted from one UIParent point in one unit, so the
-- places a piece can land form a lattice: that point plus whole steps of (step x unit). The grid draws that lattice for
-- the piece that is picked, which is the screen centre in design pixels for nearly every piece, and a corner (or UI
-- units) for the few that are seated in raw UI units from a corner (player, target, the cast bars, the tooltip, the
-- tracker). With nothing picked it is the common one. A piece's anchor point (its centre, or the corner its layout names)
-- is what lands on a line.
local function LatticeOf(id)
    local relPoint = "CENTER"
    if id then
        local _
        _, relPoint = AnchorPoints(id)
    end
    return relPoint, GridStep() * LayoutUnit(id)
end

-- Every position, in UIParent units from the screen's left (or bottom) edge, of a line of a lattice that starts at
-- `origin` and repeats every `spacing`, up to `extent`.
local function LatticeLines(origin, spacing, extent)
    local lines = {}
    if not (spacing > 0) then return lines end
    local first = math.ceil((0 - origin) / spacing - 1e-9)
    local last = math.floor((extent - origin) / spacing + 1e-9)
    for m = first, last do lines[#lines + 1] = origin + m * spacing end
    return lines
end

local function HideGrid()
    local grid = gridFrame
    if not grid then return end
    grid.fsKey = nil
    for _, list in ipairs({ grid.v, grid.h, grid.cross }) do
        for i = 1, #list do list[i]:Hide() end
    end
    grid:Hide()
end

local function NewGridFrame()
    local grid = CreateFrame("Frame", nil, UIParent)
    grid:SetFrameStrata(gridStrata)
    grid:SetFrameLevel(1)
    grid:SetAllPoints(UIParent)
    grid:EnableMouse(false)
    grid.v, grid.h, grid.cross = {}, {}, {}
    grid:Hide()
    return grid
end

-- Lazily made, reused on a step change: the pool only ever grows to the most lines one step showed.
local function GridTexture(list, index, layer, r, g, b, a)
    local line = list[index]
    if not line then
        line = gridFrame:CreateTexture(nil, layer)
        SnapToPixels(line)
        list[index] = line
    end
    line:SetColorTexture(r, g, b, a)
    return line
end

local function SeatVertical(line, x, thick)
    line:ClearAllPoints()
    line:SetPoint("TOPLEFT", gridFrame, "TOPLEFT", x, 0)
    line:SetPoint("BOTTOMLEFT", gridFrame, "BOTTOMLEFT", x, 0)
    line:SetWidth(thick)
    line:Show()
end

local function SeatHorizontal(line, y, thick)
    line:ClearAllPoints()
    line:SetPoint("BOTTOMLEFT", gridFrame, "BOTTOMLEFT", 0, y)
    line:SetPoint("BOTTOMRIGHT", gridFrame, "BOTTOMRIGHT", 0, y)
    line:SetHeight(thick)
    line:Show()
end

-- Draws the grid (or takes it away): on while editing, snap is on and "Show grid" is on. Every line is one physical
-- pixel, on a whole pixel. Cheap to call again: it redraws only when the lattice, the screen or the pixel size changed.
RefreshGrid = function()
    if not (editing and SnapOn() and ShowGridOn()) then return HideGrid() end
    local width, height = UIParent:GetWidth(), UIParent:GetHeight()
    if not (width and height and width > 0 and height > 0) then return HideGrid() end
    gridFrame = gridFrame or NewGridFrame()
    local grid = gridFrame
    local relPoint, spacing = LatticeOf(selected)
    local es = PixelsPerUnit(grid)
    local key = ("%s|%.6f|%.3f|%.3f|%.6f"):format(relPoint, spacing, width, height, es)
    if grid.fsKey == key and grid:IsShown() then return end
    local ox, oy = PointXY(UIParent, relPoint)
    if not ox then return HideGrid() end
    local across, down = LatticeLines(ox, spacing, width), LatticeLines(oy, spacing, height)
    if #across + #down > SPEC.MAX_LINES then return HideGrid() end
    local thick = 1 / es
    local function whole(v) return math.floor(v * es + 0.5) / es end
    local r, g, b = Cyan()
    local pink = Palette().pink
    for i, x in ipairs(across) do SeatVertical(GridTexture(grid.v, i, "ARTWORK", r, g, b, SPEC.GRID_ALPHA), whole(x), thick) end
    for i, y in ipairs(down) do SeatHorizontal(GridTexture(grid.h, i, "ARTWORK", r, g, b, SPEC.GRID_ALPHA), whole(y), thick) end
    for i = #across + 1, #grid.v do grid.v[i]:Hide() end
    for i = #down + 1, #grid.h do grid.h[i]:Hide() end
    -- The centre cross on top: pink, brighter, on both axes.
    SeatVertical(GridTexture(grid.cross, 1, "OVERLAY", pink[1], pink[2], pink[3], SPEC.CROSS_ALPHA), whole(width / 2), thick)
    SeatHorizontal(GridTexture(grid.cross, 2, "OVERLAY", pink[1], pink[2], pink[3], SPEC.CROSS_ALPHA), whole(height / 2), thick)
    grid.fsKey = key
    grid:SetFrameStrata(gridStrata)
    grid:Show()
end

function LayoutEdit.GetGrid()
    if gridFrame and gridFrame:IsShown() then return gridFrame end
end

-------------------------------------------------------------------------------
-- Small controls
-------------------------------------------------------------------------------

-- The panels' own controls (step chips, switch, ? icon, value boxes) are plain textures: a flat fill and a one pixel ring,
-- snapped to the pixel grid, so they stay crisp at any UI scale. Sizes are the frames sheet SPEC's (SPEC.SEG_H, SPEC.SW_W, ...).

-- A fill and four ring edges on `frame`, the edges seated by SeatEdges.
local function AddPlate(frame)
    frame.fill = frame:CreateTexture(nil, "BACKGROUND")
    frame.fill:SetAllPoints(frame)
    frame.edges = {}
    for i = 1, 4 do frame.edges[i] = frame:CreateTexture(nil, "BORDER") end
    SnapToPixels(frame.fill)
    for _, edge in ipairs(frame.edges) do SnapToPixels(edge) end
end

-- The ring `thick` thick: top and bottom the full width, the sides between them, so no corner is drawn twice.
local function SeatEdges(frame, thick)
    local e = frame.edges
    e[1]:ClearAllPoints(); e[1]:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, 0)
    e[1]:SetPoint("TOPRIGHT", frame, "TOPRIGHT", 0, 0); e[1]:SetHeight(thick)
    e[2]:ClearAllPoints(); e[2]:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 0, 0)
    e[2]:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, 0); e[2]:SetHeight(thick)
    e[3]:ClearAllPoints(); e[3]:SetPoint("TOPLEFT", frame, "TOPLEFT", 0, -thick)
    e[3]:SetPoint("BOTTOMLEFT", frame, "BOTTOMLEFT", 0, thick); e[3]:SetWidth(thick)
    e[4]:ClearAllPoints(); e[4]:SetPoint("TOPRIGHT", frame, "TOPRIGHT", 0, -thick)
    e[4]:SetPoint("BOTTOMRIGHT", frame, "BOTTOMRIGHT", 0, thick); e[4]:SetWidth(thick)
end

local function PaintPlate(frame, fill, ring, alpha)
    frame.fill:SetColorTexture(fill[1], fill[2], fill[3], fill[4] or 1)
    for _, edge in ipairs(frame.edges) do edge:SetColorTexture(ring[1], ring[2], ring[3], alpha or 1) end
end

local function NewText(parent, text, size, color)
    local label = parent:CreateFontString(nil, "OVERLAY")
    -- The font goes on before the text: SetText on a FontString with no font throws "Font not set".
    if FS.Theme and FS.Theme.ApplyMono then FS.Theme.ApplyMono(label, size, color) end
    label:SetText(text)
    return label
end

local function TextWidth(label, text)
    local w = label.GetStringWidth and label:GetStringWidth()
    if type(w) == "number" and w > 0 then return w end
    return #text * 7
end

-- A box sized by its text rounds its width UP to the next multiple of SPEC.TEXT_SNAP (the SPEC rule).
local function SnapUp(w)
    return math.ceil(w / SPEC.TEXT_SNAP - 1e-9) * SPEC.TEXT_SNAP
end

local PRESSED_FILL = { 0.024, 0.133, 0.165, 1 }   -- #06222a, a pressed cyan control

local function ShowTip(owner, text)
    if type(text) ~= "string" or text == "" then return end
    GameTooltip:SetOwner(owner, "ANCHOR_BOTTOM")
    GameTooltip:SetText(text, 1, 1, 1, 1, true)
    GameTooltip:Show()
end

-- Hover and press state shared by the chips and the switch; `paint(self)` redraws.
local function WireHover(button, paint, tip)
    button:SetScript("OnEnter", function(self)
        self.fsHover = true
        paint(self)
        ShowTip(self, type(tip) == "function" and tip(self) or tip)
    end)
    button:SetScript("OnLeave", function(self)
        self.fsHover, self.fsPressed = false, false
        paint(self)
        GameTooltip:Hide()
    end)
    button:SetScript("OnMouseDown", function(self) self.fsPressed = true; paint(self) end)
    button:SetScript("OnMouseUp", function(self) self.fsPressed = false; paint(self) end)
    button:SetScript("OnHide", function(self) self.fsHover, self.fsPressed = false, false end)
end

-- A segment: idle is a dim ring and muted text, hover a cyan ring, the one that is on a pink ring on the selected fill.
local function PaintSeg(button)
    local c = Palette()
    local on, hover, pressed = button.fsSelected, button.fsHover, button.fsPressed
    local ring = on and c.pink or ((hover or pressed) and c.cyan or c.dim)
    PaintPlate(button, on and c.sel or (pressed and PRESSED_FILL or c.ink), ring, 1)
    if FS.Theme and FS.Theme.ApplyMono then
        FS.Theme.ApplyMono(button.label, 12, (on or hover or pressed) and c.text or c.muted)
    end
end

local function NewSeg(parent, text, onClick, tip)
    local button = CreateFrame("Button", nil, parent)
    button.fsSeg = true
    button.fsSelected, button.fsHover, button.fsPressed = false, false, false
    AddPlate(button)
    button.label = NewText(button, text, 12, Palette().muted)
    button.label:SetPoint("CENTER", button, "CENTER", 0, 0)
    button.fsWidth = SnapUp(TextWidth(button.label, text) + 2 * SPEC.SEG_PAD_X)
    button:RegisterForClicks("LeftButtonUp")
    WireHover(button, PaintSeg, tip)
    button:SetScript("OnClick", function(self) onClick(self) end)
    PaintSeg(button)
    return button
end

-- A switch: dim ring and a dim knob on the left when off; a cyan ring and a cyan knob on the right when on.
local function PaintSwitch(sw)
    local c = Palette()
    local on, hover, pressed = sw.fsOn, sw.fsHover, sw.fsPressed
    PaintPlate(sw, pressed and PRESSED_FILL or c.ink, (on or hover or pressed) and c.cyan or c.dim, 1)
    local knob = on and c.cyan or c.dis
    sw.knob:SetColorTexture(knob[1], knob[2], knob[3], 1)
    sw.knob:ClearAllPoints()
    sw.knob:SetPoint("TOPLEFT", sw, "TOPLEFT", on and sw.fsKnobOn or sw.fsKnobOff, -sw.fsKnobY)
end

local function NewSwitch(parent, onClick, tip)
    local sw = CreateFrame("Button", nil, parent)
    sw.fsSwitch = true
    sw.fsOn, sw.fsHover, sw.fsPressed = false, false, false
    AddPlate(sw)
    sw.knob = sw:CreateTexture(nil, "ARTWORK")
    SnapToPixels(sw.knob)
    sw.fsKnobOn, sw.fsKnobOff, sw.fsKnobY = SPEC.SW_W - SPEC.KNOB_INSET - SPEC.KNOB_W, SPEC.KNOB_INSET, (SPEC.SW_H - SPEC.KNOB_H) / 2
    sw.knob:SetSize(SPEC.KNOB_W, SPEC.KNOB_H)
    sw:RegisterForClicks("LeftButtonUp")
    WireHover(sw, PaintSwitch, tip)
    sw:SetScript("OnClick", function(self) onClick(self) end)
    PaintSwitch(sw)
    return sw
end

-- A circled ? whose tooltip is `fsTip`: the config window's own icon where it is loaded, a small ringed one else (the
-- second answer says which: true when it has a plate of ours to seat).
local function NewHelp(parent, tip)
    local UI = FS.ConfigWindow and FS.ConfigWindow.UI
    if type(UI) == "table" and type(UI.HelpIcon) == "function" then
        local ok, icon = pcall(UI.HelpIcon, parent, tip)
        if ok and type(icon) == "table" then return icon, false end
    end
    local icon = CreateFrame("Frame", nil, parent)
    icon:SetSize(SPEC.Q, SPEC.Q)
    icon:EnableMouse(true)
    icon.fsTip = tip
    AddPlate(icon)
    local c = Palette()
    PaintPlate(icon, c.ink, c.dim, 1)
    icon.glyph = NewText(icon, "?", 9, c.muted)
    icon.glyph:SetPoint("CENTER", icon, "CENTER", 0, 0)
    icon:SetScript("OnEnter", function(self)
        local k = Palette()
        PaintPlate(self, k.ink, k.cyan, 1)
        if FS.Theme and FS.Theme.ApplyMono then FS.Theme.ApplyMono(self.glyph, 9, k.cyan) end
        ShowTip(self, self.fsTip)
    end)
    icon:SetScript("OnLeave", function(self)
        local k = Palette()
        PaintPlate(self, k.ink, k.dim, 1)
        if FS.Theme and FS.Theme.ApplyMono then FS.Theme.ApplyMono(self.glyph, 9, k.muted) end
        GameTooltip:Hide()
    end)
    return icon, true
end

-- Places `parts` left to right on one row of `panel`, each centred in PANEL_H, on whole physical pixels for the scale
-- `panel` has now, and sets the panel's width. A part is { frame, w, h, gap } (gap before it, BAR_GAP by default; the
-- first one's is BAR_PAD) or { label = fontString, w, gap }. `plate` seats the frame's ring (AddPlate), `switch` its knob,
-- `keepSize` leaves a frame's own size alone (the config window's ? icon). Returns the row's width in UI units.
local function SeatRow(panel, parts)
    local es = PixelsPerUnit(panel)
    local function px(units) return math.max(1, math.floor(units * es + 0.5)) / es end
    local x = 0
    for index, part in ipairs(parts) do
        x = x + px(part.gap or (index == 1 and SPEC.BAR_PAD or SPEC.BAR_GAP))
        local w = px(part.w)
        if part.label then
            part.label:ClearAllPoints()
            part.label:SetPoint("LEFT", panel, "TOPLEFT", x, -px(PANEL_H / 2))
        else
            local frame = part.frame
            if not part.keepSize then frame:SetSize(w, px(part.h)) end
            frame:ClearAllPoints()
            frame:SetPoint("TOPLEFT", panel, "TOPLEFT", x, -px((PANEL_H - part.h) / 2))
            if part.plate then SeatEdges(frame, 1 / es) end
            if part.switch then
                frame.fsKnobOn, frame.fsKnobOff = px(SPEC.SW_W - SPEC.KNOB_INSET - SPEC.KNOB_W), px(SPEC.KNOB_INSET)
                frame.fsKnobY = px((SPEC.SW_H - SPEC.KNOB_H) / 2)
                frame.knob:SetSize(px(SPEC.KNOB_W), px(SPEC.KNOB_H))
                PaintSwitch(frame)
            end
        end
        x = x + w
    end
    local total = x + px(SPEC.BAR_PAD)
    panel:SetWidth(total)
    return total
end

-------------------------------------------------------------------------------
-- Writing a position
-------------------------------------------------------------------------------

-- The chat module owns its seat (it honours the minimised and maximised states); every other
-- id goes through the generic re-seat.
local function Reseat(id)
    local Chat = FS.Chat
    if id == "chat" and Chat and type(Chat.ReassertPrimaryChat) == "function" then
        local ok, err = pcall(Chat.ReassertPrimaryChat)
        if not ok then FS.Layout.ForwardError(err) end
    else
        FS.Layout.Reseat(id)
    end
end

-- A frame can leave the re-seat list mid-edit (the pet docking). Its handle goes with it.
local function FrameGone(id)
    if RAID_IDS[id] then
        if RaidSeatUp(id) then return false end
        if handles[id] then handles[id]:Hide() end
        if selected == id then DropSelection() end
        return true
    end
    local provider = Provider(id)
    if provider and provider.Ready() then return false end
    if AppliedFrame(id) then return false end
    if handles[id] then handles[id]:Hide() end
    if selected == id then DropSelection() end
    return true
end

-- Blizzard applies an Edit Mode layout as it reloads it, so the handle catches up a moment later.
local function SyncSoon(id)
    if C_Timer and C_Timer.After then
        C_Timer.After(0.1, function() if editing and handles[id] and handles[id]:IsShown() then SyncHandle(id) end end)
    end
end

local function CommitProvider(id, provider, x, y)
    local oldX, oldY = provider.Offsets()
    if oldX and math.abs(x - oldX) < 0.25 and math.abs(y - oldY) < 0.25 then
        SyncHandle(id)
        return false
    end
    local ok, reason = provider.Move(x, y)
    if not ok then
        Say("could not move that piece (" .. tostring(reason) .. ")")
        SyncHandle(id)
        return false
    end
    SyncHandle(id)
    SyncSoon(id)
    return true
end

local function Commit(id, x, y)
    local provider = Provider(id)
    if provider then return CommitProvider(id, provider, x, y) end
    local Layout = FS.Layout
    local L = Layout[id]
    if FrameGone(id) then return false end
    local oldX, oldY = L.x, L.y
    if math.abs(x - oldX) < 0.25 and math.abs(y - oldY) < 0.25
        and not (id == "petcontainer" and LegacyPetPosition()) then
        SyncHandle(id)
        return false
    end
    if not Layout.SetOverride(id, x, y) then
        Say("could not save that position (saved layout is read-only or out of range)")
        SyncHandle(id)
        return false
    end
    if id == "petcontainer" then ClearLegacyPetPosition() end
    Reseat(id)
    SyncHandle(id)
    return true
end

local function ResetProvider(id, provider)
    local ok, reason = provider.Reset()
    if not ok then
        Say("could not reset that piece (" .. tostring(reason) .. ")")
        return false
    end
    if editing then
        SyncHandle(id)
        SyncSoon(id)
    end
    return true
end

function LayoutEdit.ResetOne(id)
    local provider = Provider(id)
    if provider then return ResetProvider(id, provider) end
    local Layout = FS.Layout
    if not Layout.ClearOverride(id) then
        Say("could not reset that frame (saved layout is read-only)")
        return false
    end
    if id == "petcontainer" then ClearLegacyPetPosition() end
    Reseat(id)
    if editing then SyncHandle(id) end
    return true
end

function LayoutEdit.ResetAll()
    local Layout = FS.Layout
    if not Layout.ClearAllOverrides() then
        Say("could not reset the layout (saved layout is read-only)")
        return false
    end
    ClearLegacyPetPosition()
    Layout.ReseatAll()
    if FS.Chat and type(FS.Chat.ReassertPrimaryChat) == "function" then Reseat("chat") end
    local tracker = Provider("objectives")
    if tracker and tracker.Ready() then ResetProvider("objectives", tracker) end
    if editing then SyncAll() end
    Say("every frame is back at its design seat")
    return true
end

function LayoutEdit.Nudge(dx, dy, big)
    if not (editing and selected) then return false end
    local step = big and GridStep() or 1
    local x, y = CurrentXY(selected)
    return Commit(selected, x + dx * step, y + dy * step)
end

local function Drop(id)
    if FrameGone(id) then return end
    local handle = handles[id]
    local x, y = ReadLayoutXY(id, handle)
    if not x then
        SyncHandle(id)
        return
    end
    if SnapOn() then x, y = Snap(x), Snap(y) end
    Commit(id, x, y)
end

-------------------------------------------------------------------------------
-- Position panel
-------------------------------------------------------------------------------

-- A number as the boxes show it: at most two decimals, none when whole.
local function FormatNumber(v)
    if type(v) ~= "number" or v ~= v then return "0" end
    local text = ("%.2f"):format(v)
    text = text:gsub("0+$", "")
    text = text:gsub("%.$", "")
    if text == "-0" or text == "" then text = "0" end
    return text
end

-- What was typed, as a number, or nil: digits with an optional sign and one point. No hex, no exponent, no words.
local function ParseNumber(text)
    if type(text) ~= "string" then return nil end
    text = text:match("^%s*(.-)%s*$")
    if not (text:match("^[+-]?%d+%.?%d*$") or text:match("^[+-]?%.%d+$")) then return nil end
    local v = tonumber(text)
    if not v or v ~= v or v - v ~= 0 then return nil end
    return v
end

-- Layout x / y to what the boxes show, and back: px is the layout's own unit, grid is px over the grid step.
local function ToShown(v)
    if PosUnit() == "grid" then return v / GridStep() end
    return v
end

local function FromShown(v)
    if PosUnit() == "grid" then return v * GridStep() end
    return v
end

-- Keeps the piece on the screen: the x and y whose rect (the handle's size, from the entry's anchor point) lies inside
-- UIParent. A piece wider or taller than the screen is centred on that axis.
local function ClampToScreen(id, x, y)
    local handle = handles[id]
    local width, height = UIParent:GetWidth(), UIParent:GetHeight()
    local w, h = handle and handle:GetWidth(), handle and handle:GetHeight()
    if not (width and height and w and h) then return x, y end
    local point, relPoint = AnchorPoints(id)
    local fx, fy = Fractions(point)
    local ox, oy = PointXY(UIParent, relPoint)
    if not ox then return x, y end
    local unit = LayoutUnit(id)
    -- A saved position is a whole half, so the room is rounded inward: rounding what is typed cannot push a piece off.
    local function fit(v, lo, hi)
        if lo > hi then return (lo + hi) / 2 end
        local first, last = math.ceil(lo * 2 - 1e-9) / 2, math.floor(hi * 2 + 1e-9) / 2
        if first > last then return (lo + hi) / 2 end
        return math.min(math.max(v, first), last)
    end
    return fit(x, (w * fx - ox) / unit, (width - ox - w * (1 - fx)) / unit),
        fit(y, (h * fy - oy) / unit, (height - oy - h * (1 - fy)) / unit)
end

-- "centre", "top left corner", "middle of the top edge": one point of a rect, in words.
local function PointWords(point)
    local fx, fy = Fractions(point)
    if fx == 0.5 and fy == 0.5 then return "centre" end
    local v, h = fy == 1 and "top" or "bottom", fx == 0 and "left" or "right"
    if fx ~= 0.5 and fy ~= 0.5 then return v .. " " .. h .. " corner" end
    if fy ~= 0.5 then return "middle of the " .. v .. " edge" end
    return "middle of the " .. h .. " edge"
end

-- The ? tip: what the two numbers count from, for the piece that is picked.
local function PositionTip(id)
    local point, relPoint = AnchorPoints(id)
    local unscaled = Provider(id) ~= nil or FS.Layout.IsUnscaled(id)
    return ("Counts from the %s of the screen to the %s of the piece. X grows to the right and Y grows up. "
        .. "px is %s; grid is px over the grid step (now %d). Enter moves the piece, Esc puts the number back, Tab goes to the other box. "
        .. "A piece cannot leave the screen. A position rounds to the nearest half."):format(
        PointWords(relPoint), PointWords(point),
        unscaled and "a UI unit, the game's own screen unit" or "one unit of the 2560 x 1440 design, which stretches with your UI",
        GridStep())
end

local function PaintValueBox(box)
    local c = Palette()
    local ring = box.fsBad and c.pink or (box.fsFocus and c.cyan) or (box.fsHover and c.violet) or c.dim
    PaintPlate(box, c.ink, ring, 1)
end

-- A refused entry flashes the box pink for a moment; nothing is written.
local function FlashBad(box)
    box.fsBad = true
    PaintValueBox(box)
    if C_Timer and C_Timer.After then
        C_Timer.After(SPEC.BAD_FLASH, function()
            box.fsBad = false
            PaintValueBox(box)
        end)
    end
end

local function ReleaseFields()
    local panel = posPanel
    if not panel then return end
    panel.xBox.edit:ClearFocus()
    panel.yBox.edit:ClearFocus()
end

-- Writes the numbers into the boxes; a box being typed in keeps its text unless `force`.
local function ShowXY(x, y, force)
    local panel = posPanel
    if not (panel and x and y) then return end
    for _, pair in ipairs({ { panel.xBox, x }, { panel.yBox, y } }) do
        local box = pair[1]
        if force or box.edit:HasFocus() ~= true then box.edit:SetText(FormatNumber(ToShown(pair[2]))) end
    end
end

local function UpdateFields(force)
    if not (posPanel and selected) then return end
    local x, y = CurrentXY(selected)
    ShowXY(x, y, force)
end

-- Esc: the boxes show where the piece is again, and the keys go back to the editor.
local function RevertFields()
    ReleaseFields()
    UpdateFields(true)
end

-- Enter: both boxes are read; a bad one flashes and nothing at all is written. A good pair goes through Commit, the same
-- path a drag takes, after it is clamped onto the screen.
local function ApplyTyped()
    local id, panel = selected, posPanel
    if not (editing and id and panel and handles[id]) then return false end
    local tx, ty = ParseNumber(panel.xBox.edit:GetText()), ParseNumber(panel.yBox.edit:GetText())
    if not (tx and ty) then
        if not tx then FlashBad(panel.xBox) end
        if not ty then FlashBad(panel.yBox) end
        return false
    end
    local x, y = ClampToScreen(id, FromShown(tx), FromShown(ty))
    Commit(id, x, y)
    ReleaseFields()
    UpdateFields(true)
    return true
end

local function PaintPositionUnit()
    local panel = posPanel
    if not panel then return end
    local unit = PosUnit()
    panel.pxChip.fsSelected, panel.gridChip.fsSelected = unit == "px", unit == "grid"
    PaintSeg(panel.pxChip)
    PaintSeg(panel.gridChip)
    panel.xBox.unit:SetText(unit)
    panel.yBox.unit:SetText(unit)
end

local function SetPositionUnit(unit)
    if FS.Config and FS.Config.Set then FS.Config.Set("layout.posUnit", unit) end
end

local UNIT_W = 24   -- room for "grid" at 10 px beside the number

local function NewValueBox(parent, other)
    local c = Palette()
    local box = CreateFrame("Frame", nil, parent)
    box:SetSize(SPEC.FIELD_W, SPEC.FIELD_H)
    AddPlate(box)
    box.fsHover, box.fsFocus, box.fsBad = false, false, false
    box.unit = NewText(box, "px", 10, c.muted)
    box.unit:SetPoint("RIGHT", box, "RIGHT", -6, 0)
    local edit = CreateFrame("EditBox", nil, box)
    box.edit = edit
    edit:SetPoint("TOPLEFT", box, "TOPLEFT", 4, -1)
    edit:SetPoint("BOTTOMRIGHT", box, "BOTTOMRIGHT", -(6 + UNIT_W + 4), 1)
    if FS.Theme and FS.Theme.ApplyMono then FS.Theme.ApplyMono(edit, 12, c.cyan) end
    edit:SetJustifyH("RIGHT")
    edit:SetAutoFocus(false)
    edit:SetMaxLetters(12)
    edit:SetScript("OnEnter", function() box.fsHover = true; PaintValueBox(box) end)
    edit:SetScript("OnLeave", function() box.fsHover = false; PaintValueBox(box) end)
    edit:SetScript("OnEditFocusGained", function(self)
        box.fsFocus = true
        PaintValueBox(box)
        self:HighlightText()
    end)
    edit:SetScript("OnEditFocusLost", function() box.fsFocus = false; PaintValueBox(box) end)
    edit:SetScript("OnEnterPressed", function() ApplyTyped() end)
    edit:SetScript("OnEscapePressed", function() RevertFields() end)
    edit:SetScript("OnTabPressed", function()
        local target = other()
        if target then target.edit:SetFocus() end
    end)
    PaintValueBox(box)
    return box
end

local function LayoutPositionRow(panel)
    SeatRow(panel, {
        { label = panel.xLabel, w = TextWidth(panel.xLabel, "X") },
        { frame = panel.xBox, w = SPEC.FIELD_W, h = SPEC.FIELD_H, plate = true },
        { label = panel.yLabel, w = TextWidth(panel.yLabel, "Y") },
        { frame = panel.yBox, w = SPEC.FIELD_W, h = SPEC.FIELD_H, plate = true },
        { frame = panel.pxChip, w = panel.pxChip.fsWidth, h = SPEC.SEG_H, plate = true },
        { frame = panel.gridChip, w = panel.gridChip.fsWidth, h = SPEC.SEG_H, gap = SPEC.SEG_GAP, plate = true },
        { frame = panel.help, w = SPEC.Q, h = SPEC.Q, keepSize = true, plate = panel.helpOwn },
    })
end

local function NewPositionPanel()
    local c = Palette()
    local panel = CreateFrame("Frame", nil, UIParent)
    panel:SetFrameStrata(strata)
    panel:SetFrameLevel(30)
    panel:SetSize(360, PANEL_H)
    panel:SetClampedToScreen(true)
    panel:EnableMouse(true)
    if FS.Theme and FS.Theme.SkinPanel then FS.Theme.SkinPanel(panel, { strip = false, scanline = false, accent = c.pink }) end
    panel.xLabel = NewText(panel, "X", 12, c.muted)
    panel.yLabel = NewText(panel, "Y", 12, c.muted)
    panel.xBox = NewValueBox(panel, function() return panel.yBox end)
    panel.yBox = NewValueBox(panel, function() return panel.xBox end)
    panel.pxChip = NewSeg(panel, "px", function() SetPositionUnit("px") end,
        "Type the position in px, the units it is saved in.")
    panel.gridChip = NewSeg(panel, "grid", function() SetPositionUnit("grid") end,
        function() return ("Type the position in grid steps: 3 here is 3 times the grid step (now %d px)."):format(GridStep()) end)
    panel.help, panel.helpOwn = NewHelp(panel, "")
    LayoutPositionRow(panel)
    panel:Hide()
    return panel
end

local function SeatPositionPanel(handle)
    local panel = posPanel
    local out = handle.outline or 0
    local room = out + (handle.labelOutside and LABEL_ROOM or 0) + SPEC.POS_GAP
    local top, screenTop = handle:GetTop(), UIParent:GetTop()
    local above = not (top and screenTop) or screenTop - top >= room + PANEL_H
    panel:ClearAllPoints()
    if above then
        panel:SetPoint("BOTTOMLEFT", handle, "TOPLEFT", -out, room)
    else
        panel:SetPoint("TOPLEFT", handle, "BOTTOMLEFT", -out, -(out + SPEC.POS_GAP))
    end
end

-- Shows the panel over the picked piece with its numbers, or hides it when nothing is picked.
RefreshPosition = function(force)
    local id = selected
    local handle = id and handles[id]
    if not (editing and handle and handle:IsShown()) then
        if posPanel then posPanel:Hide() end
        return
    end
    posPanel = posPanel or NewPositionPanel()
    SeatPositionPanel(handle)
    posPanel.help.fsTip = PositionTip(id)
    PaintPositionUnit()
    UpdateFields(force)
    if not posPanel:IsShown() then posPanel:Show() end
end

-- While a piece is dragged its numbers follow the handle (where it would land, once snapped).
local function StartLive(id)
    local panel = posPanel
    if not panel then return end
    local elapsed = 0
    panel:SetScript("OnUpdate", function(_, dt)
        elapsed = elapsed + (dt or 0)
        if elapsed < SPEC.LIVE_EVERY then return end
        elapsed = 0
        local handle = handles[id]
        if not handle then return end
        local x, y = ReadLayoutXY(id, handle)
        if not x then return end
        if SnapOn() then x, y = Snap(x), Snap(y) end
        ShowXY(x, y, true)
    end)
end

local function StopLive()
    if posPanel then posPanel:SetScript("OnUpdate", nil) end
end

function LayoutEdit.GetPositionPanel()
    if posPanel and posPanel:IsShown() then return posPanel end
end

-- Set position: picks the piece and puts the cursor in its X box.
function LayoutEdit.FocusPosition(id)
    if not (editing and handles[id] and handles[id]:IsShown()) then return false end
    LayoutEdit.Select(id)
    RefreshPosition(true)
    if posPanel and posPanel:IsShown() then posPanel.xBox.edit:SetFocus() end
    return true
end

-------------------------------------------------------------------------------
-- The editor over the config window
-------------------------------------------------------------------------------

local function ConfigShown()
    local window = FS.ConfigWindow
    if type(window) ~= "table" or type(window.IsShown) ~= "function" then return false end
    local ok, shown = pcall(window.IsShown)
    return ok and shown == true
end

-- The editor's frames go in the strata (and the grid in its own): all of them are insecure.
local function ApplyStrata()
    for _, handle in pairs(handles) do handle:SetFrameStrata(strata) end
    if donePanel then donePanel:SetFrameStrata(strata) end
    if posPanel then posPanel:SetFrameStrata(strata) end
    if gridFrame then gridFrame:SetFrameStrata(gridStrata) end
end

-- The config window opened while the editor runs (the menu's Settings, or /fsconfig) must draw above the handles, which sit
-- in a higher strata than the window; so while it is up the editor's frames drop under it, and they come back when it closes.
local function SyncConfigOver()
    local over = editing and ConfigShown()
    if over == configOver then return end
    configOver = over
    strata, gridStrata = over and SPEC.STRATA_UNDER or SPEC.STRATA_UP, over and SPEC.GRID_UNDER or SPEC.GRID_UP
    ApplyStrata()
    if over and menu then menu.catcher:Hide() end
end

-------------------------------------------------------------------------------
-- Right click menu
-------------------------------------------------------------------------------

local function PieceLabel(id)
    for _, def in ipairs(MOVABLE) do
        if def.id == id then return def.label end
    end
    return tostring(id)
end

local function ConfigOpener()
    local window = FS.ConfigWindow
    if type(window) == "table" and type(window.Open) == "function" then return window end
end

-- The Settings map and the ids it has to cover (the harness fails when one is missing).
function LayoutEdit.GetPieces()
    return PIECES
end

function LayoutEdit.MovableIds()
    local ids = {}
    for _, def in ipairs(MOVABLE) do ids[#ids + 1] = def.id end
    return ids
end

-- True when the piece has a config page to open.
function LayoutEdit.HasSettings(id)
    local entry = PIECES[id]
    return entry ~= nil and entry.none ~= true and ConfigOpener() ~= nil
end

-- Opens the config window on the piece's page and tab, at its row. The editor keeps running (the window draws above the
-- handles). Open(page, tab, row) is the signature of the rebuilt window; the older one takes only a page, and a page it
-- does not know leaves it where it was.
function LayoutEdit.OpenSettings(id)
    if not LayoutEdit.HasSettings(id) then return false end
    local entry, window = PIECES[id], ConfigOpener()
    local ok, err = pcall(window.Open, entry.page, entry.tab, entry.row)
    if not ok then
        FS.Layout.ForwardError(err)
        return false
    end
    SyncConfigOver()
    return true
end

local function PaintMenuItem(item)
    local c = Palette()
    local wash = 0
    local color = c.text
    if item.fsDisabled then
        color = c.dis
    else
        if item.fsPressed then wash = 0.2 elseif item.fsHover then wash = 0.12 end
        if item.fsPressed or item.fsHover then color = c.cyan end
    end
    item.wash:SetColorTexture(c.cyan[1], c.cyan[2], c.cyan[3], wash)
    if FS.Theme and FS.Theme.ApplyMono then FS.Theme.ApplyMono(item.label, 12, color) end
end

local function NewMenuItem(parent, text, onClick, disabledTip)
    local c = Palette()
    local item = CreateFrame("Button", nil, parent)
    item.fsHover, item.fsPressed, item.fsDisabled = false, false, false
    item.wash = item:CreateTexture(nil, "BACKGROUND")
    item.wash:SetAllPoints(item)
    item.label = NewText(item, text, 12, c.text)
    item.label:SetPoint("LEFT", item, "LEFT", 12, 0)
    -- A greyed row carries a small ? that says why (its tooltip is the row's).
    item.hint = NewText(item, "?", 10, c.dis)
    item.hint:SetPoint("RIGHT", item, "RIGHT", -12, 0)
    item.hint:Hide()
    item:RegisterForClicks("LeftButtonUp")
    item:SetScript("OnEnter", function(self)
        self.fsHover = true
        PaintMenuItem(self)
        if self.fsDisabled and disabledTip then
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetText(disabledTip(), 1, 1, 1, 1, true)
            GameTooltip:Show()
        end
    end)
    item:SetScript("OnLeave", function(self)
        self.fsHover, self.fsPressed = false, false
        PaintMenuItem(self)
        GameTooltip:Hide()
    end)
    item:SetScript("OnMouseDown", function(self) self.fsPressed = true; PaintMenuItem(self) end)
    item:SetScript("OnMouseUp", function(self) self.fsPressed = false; PaintMenuItem(self) end)
    item:SetScript("OnHide", function(self) self.fsHover, self.fsPressed = false, false end)
    item:SetScript("OnClick", function(self)
        if self.fsDisabled then return end
        onClick()
    end)
    PaintMenuItem(item)
    return item
end

function LayoutEdit.CloseMenu()
    if menu then menu.catcher:Hide() end
end

function LayoutEdit.IsMenuOpen()
    return menu ~= nil and menu.catcher:IsShown() == true
end

function LayoutEdit.GetMenu()
    if menu and menu.catcher:IsShown() then return menu end
end

local function EnsureMenu()
    if menu then return menu end
    local c = Palette()
    local catcher = CreateFrame("Button", nil, UIParent)
    catcher:SetFrameStrata(SPEC.STRATA_UP)
    catcher:SetFrameLevel(55)
    catcher:SetAllPoints(UIParent)
    catcher:EnableMouse(true)
    catcher:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    catcher:SetScript("OnClick", function() LayoutEdit.CloseMenu() end)
    catcher:Hide()
    local frame = CreateFrame("Frame", nil, catcher)
    frame:SetFrameLevel(60)
    frame:EnableMouse(true)
    if FS.Theme and FS.Theme.SkinPanel then FS.Theme.SkinPanel(frame, { strip = false, scanline = false, accent = c.cyan }) end

    local inner = SPEC.MENU_W - 2
    local headerTop = 1 + SPEC.MENU_PAD
    local rule = frame:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(c.hair[1], c.hair[2], c.hair[3], 1)
    rule:SetPoint("TOPLEFT", frame, "TOPLEFT", 1, -(headerTop + SPEC.MENU_ROW_H - 1))
    rule:SetSize(inner, 1)
    SnapToPixels(rule)
    local header = NewText(frame, "", 10, c.muted)
    header:SetPoint("LEFT", frame, "TOPLEFT", 12, -(headerTop + SPEC.MENU_ROW_H / 2))

    local m = { catcher = catcher, frame = frame, header = header, items = {} }
    local function seat(item, top)
        item:SetSize(inner, SPEC.MENU_ROW_H)
        item:SetPoint("TOPLEFT", frame, "TOPLEFT", 1, -top)
    end
    local rowTop = headerTop + SPEC.MENU_ROW_H + 4
    m.items.settings = NewMenuItem(frame, "Settings", function()
        LayoutEdit.CloseMenu()
        LayoutEdit.OpenSettings(m.id)
    end, function()
        local entry = PIECES[m.id]
        if entry and entry.none then return "This piece has no settings." end
        return "The config window is not available."
    end)
    seat(m.items.settings, rowTop)
    m.items.position = NewMenuItem(frame, "Set position", function()
        LayoutEdit.CloseMenu()
        LayoutEdit.FocusPosition(m.id)
    end)
    seat(m.items.position, rowTop + SPEC.MENU_ROW_H)
    local sepTop = rowTop + 2 * SPEC.MENU_ROW_H
    local sep = frame:CreateTexture(nil, "ARTWORK")
    sep:SetColorTexture(c.hair[1], c.hair[2], c.hair[3], 1)
    sep:SetPoint("TOPLEFT", frame, "TOPLEFT", 1, -(sepTop + 4))
    sep:SetSize(inner, 1)
    SnapToPixels(sep)
    m.items.reset = NewMenuItem(frame, "Reset position", function()
        LayoutEdit.CloseMenu()
        LayoutEdit.ResetOne(m.id)
    end)
    seat(m.items.reset, sepTop + SPEC.MENU_SEP + 9)
    m.height = sepTop + SPEC.MENU_SEP + 9 + SPEC.MENU_ROW_H + SPEC.MENU_PAD + 1
    frame:SetSize(SPEC.MENU_W, m.height)
    menu = m
    return m
end

-- The cursor in UIParent units, or nil where the client will not say.
local function CursorXY()
    if type(GetCursorPosition) ~= "function" then return nil end
    local x, y = GetCursorPosition()
    local scale = UIParent:GetEffectiveScale()
    if type(x) ~= "number" or type(y) ~= "number" or type(scale) ~= "number" or scale <= 0 then return nil end
    return x / scale, y / scale
end

-- The menu's top left sits just off the cursor, flipped to the other side of it where the screen is short of room.
local function SeatMenu(m, id)
    local width, height = UIParent:GetWidth() or 0, UIParent:GetHeight() or 0
    local cx, cy = CursorXY()
    if not cx and handles[id] then cx, cy = handles[id]:GetCenter() end
    cx, cy = cx or width / 2, cy or height / 2
    local left, top = cx + 4, cy - 4
    if left + SPEC.MENU_W > width then left = cx - 4 - SPEC.MENU_W end
    if top - m.height < 0 then top = cy + 4 + m.height end
    local es = PixelsPerUnit(m.frame)
    m.frame:ClearAllPoints()
    m.frame:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", math.max(0, math.floor(left * es + 0.5) / es),
        math.floor(top * es + 0.5) / es)
end

function LayoutEdit.OpenMenu(id)
    if not (editing and PIECES[id] and handles[id]) then return false end
    local m = EnsureMenu()
    m.id = id
    m.header:SetText(PieceLabel(id):upper())
    local settings = m.items.settings
    settings.fsDisabled = not LayoutEdit.HasSettings(id)
    if settings.fsDisabled then settings.hint:Show() else settings.hint:Hide() end
    for _, item in pairs(m.items) do
        item.fsHover, item.fsPressed = false, false
        PaintMenuItem(item)
    end
    SeatMenu(m, id)
    m.catcher:Show()
    return true
end

-------------------------------------------------------------------------------
-- Handles
-------------------------------------------------------------------------------

local function Paint(handle, isSelected)
    local r, g, b = Cyan()
    local a = isSelected and 1 or 0.7
    handle.fill:SetColorTexture(r, g, b, isSelected and 0.28 or 0.14)
    for _, edge in ipairs(handle.edges) do edge:SetColorTexture(r, g, b, a) end
end

function LayoutEdit.Select(id)
    local old = selected and handles[selected]
    local changed = selected ~= id
    selected = id
    if old then Paint(old, false) end
    if id and handles[id] then Paint(handles[id], true) end
    -- A new pick takes the keys back from a box being typed in, redraws the grid for the lattice that piece snaps to, and
    -- moves the position panel onto it.
    if changed then ReleaseFields() end
    RefreshGrid()
    RefreshPosition(changed)
end

local function NewHandle(def)
    local id = def.id
    local handle = CreateFrame("Frame", nil, UIParent)
    handle:SetFrameStrata(strata)
    handle:SetFrameLevel(20)
    handle:EnableMouse(true)
    handle:SetMovable(true)
    handle:SetClampedToScreen(true)
    handle:RegisterForDrag("LeftButton")

    -- Top, bottom, left, right: seated by SeatOutline, outside the handle's rect.
    handle.fill = handle:CreateTexture(nil, "BACKGROUND")
    handle.edges = {}
    for i = 1, 4 do
        handle.edges[i] = handle:CreateTexture(nil, "BORDER")
        SnapToPixels(handle.edges[i])
    end
    SnapToPixels(handle.fill)
    SeatOutline(handle)

    handle.label = handle:CreateFontString(nil, "OVERLAY")
    if FS.Theme and FS.Theme.ApplyMono then
        local r, g, b = Cyan()
        FS.Theme.ApplyMono(handle.label, 11, { r, g, b, 1 })
    end
    handle.label:SetPoint("CENTER", handle, "CENTER")
    handle.label:SetText(def.label)
    handle.labelOutside = def.raid == true

    handle:SetScript("OnMouseDown", function()
        if editing then LayoutEdit.Select(id) end
    end)
    handle:SetScript("OnMouseUp", function(_, button)
        if editing and button == "RightButton" then LayoutEdit.OpenMenu(id) end
    end)
    handle:SetScript("OnDragStart", function(self)
        if not editing then return end
        LayoutEdit.CloseMenu()
        ReleaseFields()
        LayoutEdit.Select(id)
        dragging = id
        self:StartMoving()
        StartLive(id)
    end)
    handle:SetScript("OnDragStop", function(self)
        self:StopMovingOrSizing()
        StopLive()
        if not editing or dragging ~= id then return end
        dragging = nil
        Drop(id)
    end)

    Paint(handle, false)
    handle:Hide()
    return handle
end

function LayoutEdit.GetHandle(id)
    local handle = handles[id]
    if handle and handle:IsShown() then return handle end
end

function LayoutEdit.IsEditing()
    return editing
end

-------------------------------------------------------------------------------
-- Edit mode
-------------------------------------------------------------------------------

-- The raid size chips: one per preview size, each ONE clean ring. They are plain textures (a flat fill and four one pixel
-- edges, snapped to the pixel grid), not the shared text button skin: that skin's cut plate, ring and halo (a nine-sliced
-- glow drawn past the ring) read as two stacked outlines on a chip this small. The chip for the size on show is selected:
-- a cyan ring, a cyan wash on the fill and a cyan label; the rest are a violet ring, the ink fill and a steel label. Hover
-- and press wash the fill toward the ring colour, as the config window's controls do.
local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end

local function ChipColors()
    local Theme = FS.Theme or {}
    return Theme.COLOR_POWER or { 0.133, 0.878, 1, 1 }, Theme.COLOR_BORDER or { 0.545, 0.361, 0.965, 1 },
        Theme.COLOR_STEEL or { 0.62, 0.66, 0.74, 1 }, Theme.COLOR_BUTTON_INK or { 0.051, 0.024, 0.125, 1 }
end

local function PaintSizeButton(button)
    local cyan, violet, steel, ink = ChipColors()
    local selected, hover, pressed = button.fsSelected, button.fsHover, button.fsPressed
    local ring = selected and cyan or violet
    local wash = selected and 0.3 or (pressed and 0.32) or (hover and 0.16) or 0
    local fill = Mix(ink, ring, wash)
    button.fill:SetColorTexture(fill[1], fill[2], fill[3], 1)
    local alpha = (selected or hover or pressed) and 1 or 0.7
    for _, edge in ipairs(button.edges) do edge:SetColorTexture(ring[1], ring[2], ring[3], alpha) end
    local text = (selected or hover or pressed) and cyan or steel
    if FS.Theme and FS.Theme.ApplyMono then FS.Theme.ApplyMono(button.label, 10.5, text) end
end

-- Whole physical pixels: each chip, the gap between and the one pixel ring are rounded for the scale the panel has now, and
-- the row stays right aligned. Runs when the panel is built and again whenever the editor shows it or a size changes.
local function SeatSizeButtons(panel)
    local buttons = panel.sizeButtons
    if not buttons then return end
    local es = PixelsPerUnit(panel)
    local function px(units) return math.max(1, math.floor(units * es + 0.5)) end
    local w, h, gap, thick = px(SIZE_W), px(SIZE_H), px(SIZE_GAP), 1 / es
    local total = #buttons * w + (#buttons - 1) * gap
    local left, top = (panel:GetWidth() or 0) - SIZE_PAD - total / es, math.floor(PANEL_H * es + 0.5) / es
    for index, button in ipairs(buttons) do
        button:SetSize(w / es, h / es)
        button:ClearAllPoints()
        button:SetPoint("TOPLEFT", panel, "TOPLEFT", left + (index - 1) * (w + gap) / es, -top)
        SeatEdges(button, thick)
    end
end

-- The size is the saved setting, so a change from the config page lands here too.
local function RefreshSizeButtons()
    local buttons = donePanel and donePanel.sizeButtons
    local preview = RaidPreview()
    if not (buttons and preview) then return end
    local current = preview.Size()
    SeatSizeButtons(donePanel)
    for _, button in ipairs(buttons) do
        button.fsSelected = button.raidSize == current
        PaintSizeButton(button)
    end
end

local function NewSizeButton(panel, preview, size)
    local button = CreateFrame("Button", nil, panel)
    button.raidSize = size
    button.fsSelected, button.fsHover, button.fsPressed = false, false, false
    AddPlate(button)
    button.label = button:CreateFontString(nil, "OVERLAY")
    -- The font goes on before the text: SetText on a FontString with no font throws "Font not set".
    if FS.Theme and FS.Theme.ApplyMono then
        local _, _, steel = ChipColors()
        FS.Theme.ApplyMono(button.label, 10.5, steel)
    end
    button.label:SetPoint("CENTER", button, "CENTER", 0, 0)
    button.label:SetText(tostring(size))
    button:RegisterForClicks("LeftButtonUp")
    button:SetScript("OnEnter", function(self)
        self.fsHover = true
        PaintSizeButton(self)
        GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
        GameTooltip:SetText(("Preview and move the layout for a raid of up to %d. Each size has its own seat. Up to 10 draws mini boxes, more draws tiles."):format(size), 1, 1, 1, 1, true)
        GameTooltip:Show()
    end)
    button:SetScript("OnLeave", function(self)
        self.fsHover, self.fsPressed = false, false
        PaintSizeButton(self)
        GameTooltip:Hide()
    end)
    button:SetScript("OnMouseDown", function(self) self.fsPressed = true; PaintSizeButton(self) end)
    button:SetScript("OnMouseUp", function(self) self.fsPressed = false; PaintSizeButton(self) end)
    button:SetScript("OnHide", function(self) self.fsHover, self.fsPressed = false, false end)
    button:SetScript("OnClick", function() preview.SetSize(size) end)
    return button
end

-- A second row under the title: "RAID" and a chip per size. Only where the raid frames loaded.
local function BuildSizeRow(panel, preview)
    local Theme = FS.Theme
    local c = Theme and Theme.COLOR_STEEL
    local label = panel:CreateFontString(nil, "OVERLAY")
    if Theme and Theme.ApplyMono then
        local r, g, b = Cyan()
        Theme.ApplyMono(label, 10, c or { r, g, b, 0.7 })
    end
    label:SetPoint("LEFT", panel, "TOPLEFT", SPEC.BAR_PAD, -(PANEL_H + SIZE_H / 2))
    label:SetText("RAID")
    panel.sizeLabel = label
    panel.sizeButtons = {}
    for index, size in ipairs(preview.SIZES) do
        panel.sizeButtons[index] = NewSizeButton(panel, preview, size)
        PaintSizeButton(panel.sizeButtons[index])
    end
    SeatSizeButtons(panel)
end

-- Grid step chips and the "show grid" switch follow the saved settings, so a change from the config page lands here too.
local function PaintDoneControls()
    local panel = donePanel
    if not (panel and panel.stepChips) then return end
    local step = GridStep()
    for _, chip in ipairs(panel.stepChips) do
        chip.fsSelected = chip.fsStep == step
        PaintSeg(chip)
    end
    panel.gridSwitch.fsOn = ShowGridOn()
    PaintSwitch(panel.gridSwitch)
end

-- The panel's one row, left to right (frame H): the title, the grid step, the show grid switch, a ?, DONE.
local function LayoutDoneRow(panel)
    local parts = {
        { label = panel.title, w = TextWidth(panel.title, "EDIT MODE") },
        { label = panel.stepLabel, w = TextWidth(panel.stepLabel, "grid") },
    }
    for index, chip in ipairs(panel.stepChips) do
        parts[#parts + 1] = { frame = chip, w = chip.fsWidth, h = SPEC.SEG_H, plate = true, gap = index > 1 and SPEC.SEG_GAP or nil }
    end
    parts[#parts + 1] = { label = panel.gridLabel, w = TextWidth(panel.gridLabel, "grid") }
    parts[#parts + 1] = { frame = panel.gridSwitch, w = SPEC.SW_W, h = SPEC.SW_H, plate = true, switch = true }
    parts[#parts + 1] = { frame = panel.help, w = SPEC.Q, h = SPEC.Q, keepSize = true, plate = panel.helpOwn }
    parts[#parts + 1] = { frame = panel.done, w = DONE_W, h = DONE_H }
    SeatRow(panel, parts)
end

local DONE_TIP = "Right click a piece for its menu: Settings, Set position, Reset position. Click a piece, then use the arrows "
    .. "to nudge it, or Shift and the arrows to move it a grid step. The grid is the lines pieces snap to; the first row "
    .. "of numbers is its step. The grid shows only while Snap to grid is on in the config window. Esc leaves."

-- A plain insecure panel above the handles; the overlay under them keeps the mouse off.
local function NewDonePanel()
    local Theme = FS.Theme
    local c = Palette()
    local preview = RaidPreview()
    local panel = CreateFrame("Frame", nil, UIParent)
    panel:SetFrameStrata(strata)
    panel:SetFrameLevel(30)
    panel:SetSize(400, preview and PANEL_H + SIZE_ROW or PANEL_H)
    panel:SetPoint("TOP", UIParent, "TOP", 0, -24)
    panel:EnableMouse(true)
    if Theme and Theme.SkinPanel then Theme.SkinPanel(panel, { strip = false, scanline = false }) end

    panel.title = NewText(panel, "EDIT MODE", 11, c.text)
    panel.stepLabel = NewText(panel, "grid", 12, c.muted)
    panel.stepChips = {}
    for index, step in ipairs({ 4, 8, 16, 32 }) do
        local chip = NewSeg(panel, tostring(step), function()
            if FS.Config and FS.Config.Set then FS.Config.Set("layout.grid", step) end
        end, ("Snap and show the grid every %d px."):format(step))
        chip.fsStep = step
        panel.stepChips[index] = chip
    end
    panel.gridLabel = NewText(panel, "grid", 12, c.muted)
    panel.gridSwitch = NewSwitch(panel, function()
        if FS.Config and FS.Config.Set then FS.Config.Set("layout.showGrid", not ShowGridOn()) end
    end, "Show the grid lines. Pieces snap the same with them hidden.")
    panel.help, panel.helpOwn = NewHelp(panel, DONE_TIP)

    local done = CreateFrame("Button", nil, panel)
    done:SetSize(DONE_W, DONE_H)
    done:RegisterForClicks("LeftButtonUp")
    -- A Button needs a font object before it can hold text.
    done:SetNormalFontObject(_G.GameFontNormal)
    done:SetText("DONE")

    -- The tooltip handlers go on before the skin, which post-hooks the same scripts for its hover look.
    done:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
        GameTooltip:SetText("Save and leave layout edit. Esc does the same.", 1, 1, 1, 1, true)
        GameTooltip:Show()
    end)
    done:SetScript("OnLeave", function()
        GameTooltip:Hide()
    end)
    done:SetScript("OnClick", function() LayoutEdit.Done() end)
    -- The shared STUwave text button in cyan: the plate, ring and halo, hover and pressed looks, the label fonts.
    if FS.ButtonSkins and FS.ButtonSkins.SkinTextButton then FS.ButtonSkins.SkinTextButton(done, { accent = "cyan" }) end
    panel.done = done
    LayoutDoneRow(panel)
    if preview then BuildSizeRow(panel, preview) end

    -- The config window can be opened over the editor (the menu's Settings, /fsconfig): its strata is lower than the
    -- handles', so the editor's frames drop under it while it is up.
    local watched = 0
    panel:SetScript("OnUpdate", function(_, dt)
        watched = watched + (dt or 0)
        if watched < 0.25 then return end
        watched = 0
        SyncConfigOver()
    end)
    panel:Hide()
    return panel
end

function LayoutEdit.GetDonePanel()
    if donePanel and donePanel:IsShown() then return donePanel end
end

-- Fullscreen keyboard catcher under the handles. Unhandled keys go on to the game.
local function EnsureOverlay()
    if overlay then return overlay end
    overlay = CreateFrame("Frame", nil, UIParent)
    overlay:SetFrameStrata("FULLSCREEN_DIALOG")
    overlay:SetFrameLevel(1)
    overlay:SetAllPoints(UIParent)
    overlay:EnableMouse(false)
    overlay:Hide()
    overlay:SetScript("OnKeyDown", function(self, key)
        local arrow = ARROWS[key]
        if InCombatLockdown() then
            self:SetPropagateKeyboardInput(true)
            LayoutEdit.Exit()
        elseif configOver then
            -- The config window is up over the editor: its keys (Esc closes it) are the game's, not the editor's.
            self:SetPropagateKeyboardInput(true)
        elseif key == "ESCAPE" then
            self:SetPropagateKeyboardInput(false)
            -- Esc closes an open menu first; the next one leaves.
            if LayoutEdit.IsMenuOpen() then LayoutEdit.CloseMenu() else LayoutEdit.Done() end
        elseif arrow and selected and not LayoutEdit.IsMenuOpen() then
            self:SetPropagateKeyboardInput(false)
            LayoutEdit.Nudge(arrow[1], arrow[2], IsShiftKeyDown and IsShiftKeyDown())
        else
            self:SetPropagateKeyboardInput(true)
        end
    end)
    -- A held movement key's release must always reach the game.
    overlay:SetScript("OnKeyUp", function(self)
        self:SetPropagateKeyboardInput(true)
    end)
    return overlay
end

-- Shows a handle for every movable frame that has one and hides the rest. Returns true when the chat is
-- applied but skipped (minimised or maximised). Safe to run again while editing.
local function ShowHandles()
    local chatSkipped = false
    for _, def in ipairs(MOVABLE) do
        if HasHandle(def.id) then
            handles[def.id] = handles[def.id] or NewHandle(def)
            Paint(handles[def.id], def.id == selected)
            SyncHandle(def.id)
            handles[def.id]:Show()
        else
            if handles[def.id] then handles[def.id]:Hide() end
            if selected == def.id then DropSelection() end
            if dragging == def.id then
                handles[def.id]:StopMovingOrSizing()
                StopLive()
                dragging = nil
            end
            if def.id == "chat" and AppliedFrame("chat") then chatSkipped = true end
        end
    end
    return chatSkipped
end

-- A preview shown, resized or re-seated this very frame may not have a rect to measure yet, so its handle is not up: it
-- follows a moment later.
local function CatchUpRaidHandle()
    local preview = RaidPreview()
    local handle = preview and handles[preview.SeatId()]
    if preview and preview.IsShown() and not (handle and handle:IsShown()) and C_Timer and C_Timer.After then
        C_Timer.After(0.1, function()
            if editing then
                local ok, err = pcall(ShowHandles)
                if not ok then FS.Layout.ForwardError(err) end
            end
        end)
    end
end

local function RefuseInCombat()
    if not InCombatLockdown() then return false end
    Say("can't edit the layout in combat")
    return true
end

-- True, after saying why, when the editor cannot start now: in combat, or with Blizzard's own Edit Mode open.
local function RefuseToStart()
    if RefuseInCombat() then return true end
    if BlizzardEditModeActive() then
        Say("close Blizzard Edit Mode first")
        return true
    end
    return false
end

function LayoutEdit.Enter()
    if editing then return true end
    if RefuseToStart() then return false end
    -- Editing is on before any handle exists, so a failure part way is undone by Exit.
    editing = true
    selected = nil
    dragging = nil
    configOver = false
    strata, gridStrata = SPEC.STRATA_UP, SPEC.GRID_UP
    local chatSkipped = false
    local ok, err = pcall(function()
        EnsureOverlay()
        donePanel = donePanel or NewDonePanel()
        -- The preview first: the raid handle covers it. The saved size may have changed since the panel was built.
        local preview = RaidPreview()
        if preview then preview.Show() end
        -- The scale may have changed since the panels were built: seat them again for the one it has now.
        LayoutDoneRow(donePanel)
        if posPanel then LayoutPositionRow(posPanel) end
        ApplyStrata()
        PaintDoneControls()
        RefreshSizeButtons()
        chatSkipped = ShowHandles()
        overlay:Show()
        overlay:EnableKeyboard(true)
        donePanel:Show()
        RefreshGrid()
        SyncConfigOver()
    end)
    if not ok then
        LayoutEdit.Exit()
        FS.Layout.ForwardError(err)
        return false
    end
    EditChanged()
    Say("layout editor on: drag a piece, arrows nudge, Shift+arrow by the grid, right-click for its menu, Esc leaves")
    CatchUpRaidHandle()
    if chatSkipped then Say("restore the chat from minimised or maximised to move it") end
    return true
end

function LayoutEdit.Exit()
    returnToConfig = false
    if not editing then return end
    editing = false
    selected = nil
    dragging = nil
    LayoutEdit.CloseMenu()
    StopLive()
    ReleaseFields()
    for _, handle in pairs(handles) do
        handle:StopMovingOrSizing()
        handle:Hide()
    end
    if overlay then
        overlay:EnableKeyboard(false)
        overlay:Hide()
    end
    if posPanel then posPanel:Hide() end
    RefreshGrid()
    if donePanel then donePanel:Hide() end
    configOver = false
    strata, gridStrata = SPEC.STRATA_UP, SPEC.GRID_UP
    ApplyStrata()
    local preview = RaidPreview()
    if preview then pcall(preview.Hide) end
    EditChanged()
    Say("layout editor off")
end

-- Closes the config window and opens the editor, out of combat only (a refusal leaves the window open and says why).
-- DONE or Esc then reopens the page named here, the Layout page by default. The Layout page's button and any other page
-- with its own Move button start here, so the way back is one rule. Entering while already editing arms nothing.
-- Combat and Blizzard's Edit Mode are checked before the window closes, so a player who is refused keeps their place.
-- Only a failure while Enter builds the handles still comes after the close (Enter then switches itself off again).
function LayoutEdit.EnterFromConfig(pageKey)
    if RefuseToStart() then return false end
    local window = FS.ConfigWindow
    if type(window) == "table" and type(window.Close) == "function" then window.Close() end
    local was = editing
    local entered = LayoutEdit.Enter() == true
    returnToConfig = entered and not was and (pageKey or PAGE_KEY) or false
    return entered
end

-- DONE and Esc: leave, and go back to the page that started the edit from the config window.
function LayoutEdit.Done()
    local page = returnToConfig
    local reopen = page and editing and not InCombatLockdown() and not ConfigShown()
    LayoutEdit.Exit()
    local window = FS.ConfigWindow
    if reopen and type(window) == "table" and type(window.Open) == "function" then window.Open(page) end
end

function LayoutEdit.Toggle()
    if editing then LayoutEdit.Exit() else LayoutEdit.Enter() end
end

-------------------------------------------------------------------------------
-- Slash command
-------------------------------------------------------------------------------

function LayoutEdit.Slash(msg)
    msg = (type(msg) == "string" and msg or ""):lower():match("^%s*(.-)%s*$")
    if msg == "" then
        LayoutEdit.Toggle()
    elseif msg == "reset all" then
        Say("this puts every frame back at its design seat and cannot be undone; type /fsedit reset all confirm")
    elseif msg == "reset all confirm" then
        LayoutEdit.ResetAll()
    else
        Say("/fsedit toggles the editor; /fsedit reset all resets every frame")
    end
end

SLASH_FSEDIT1 = "/fsedit"
SlashCmdList["FSEDIT"] = function(msg) LayoutEdit.Slash(msg) end

-------------------------------------------------------------------------------
-- Blizzard Edit Mode pointer
-------------------------------------------------------------------------------

-- Read-only post-hook: it never touches Blizzard's state and never throws into its caller.
local function HookBlizzardEditMode()
    if blizzardHooked or type(hooksecurefunc) ~= "function" then return end
    local manager = _G.EditModeManagerFrame
    if type(manager) ~= "table" or type(manager.EnterEditMode) ~= "function" then return end
    blizzardHooked = pcall(hooksecurefunc, manager, "EnterEditMode", function()
        pcall(function()
            LayoutEdit.Exit()
            Say("Forever STUwave frames move with /fsedit, not Blizzard Edit Mode")
        end)
    end)
end

-------------------------------------------------------------------------------
-- Config window page
-------------------------------------------------------------------------------

local function BuildPage(content)
    local UI = FS.ConfigWindow and FS.ConfigWindow.UI
    if type(UI) ~= "table" then return end
    if UI.Header then
        UI.Header(content, "Edit mode",
            "Drag any piece. Arrows nudge it, Shift+arrow by the grid step. Right-click a piece for Settings, Set position and Reset position. Esc leaves. Out of combat only.")
    end
    if UI.Button then
        UI.Button(content, {
            text = "EDIT LAYOUT",
            big = true,
            onClick = function() LayoutEdit.EnterFromConfig(PAGE_KEY) end,
        })
    end
    local preview = RaidPreview()
    if preview then
        if UI.Header then
            UI.Header(content, "Raid frames",
                "Shows a preview raid while you edit, so you can place the grid without being in one. Each raid size has "
                .. "its own seat: pick a size here or on the editor's panel (up to 10 draws mini boxes, more draws tiles), "
                .. "then drag its handle. In a raid the grid uses the seat of the smallest size that fits the group. "
                .. "Right-click a handle and pick Reset position to put that size back at its default seat.")
        end
        if UI.Segmented then
            local options = {}
            for index, size in ipairs(preview.SIZES) do options[index] = { value = size, text = tostring(size) } end
            UI.Segmented(content, { label = "Preview size", key = preview.KEY, options = options })
        end
        if UI.Button then
            UI.Button(content, {
                text = "MOVE RAID FRAMES",
                onClick = function() LayoutEdit.EnterFromConfig(PAGE_KEY) end,
            })
        end
    end
    if UI.Header then UI.Header(content, "Snapping") end
    if UI.Toggle then
        UI.Toggle(content, { label = "Snap to grid", key = "layout.snap" })
        UI.Toggle(content, { label = "Show grid", key = "layout.showGrid",
            tip = "Draws the grid lines while you edit. They only show while Snap to grid is on." })
    end
    if UI.Segmented then
        UI.Segmented(content, {
            label = "Grid size",
            key = "layout.grid",
            options = { { value = 4, text = "4" }, { value = 8, text = "8" }, { value = 16, text = "16" }, { value = 32, text = "32" } },
        })
    end
    if UI.Header then UI.Header(content, "Reset", "Puts every piece back where the design seats it. Cannot be undone.") end
    if UI.Button then
        UI.Button(content, {
            text = "Reset all positions",
            warn = true,
            confirm = "Reset every frame to its default position?",
            onClick = function() LayoutEdit.ResetAll() end,
        })
    end
end

-- Registers once; called at load and again at PLAYER_LOGIN in case the window loaded later.
local function RegisterPage()
    if pageRegistered then return end
    local window = FS.ConfigWindow
    if type(window) ~= "table" or type(window.RegisterCategory) ~= "function" then return end
    pageRegistered = true
    local ok, err = pcall(window.RegisterCategory, { key = PAGE_KEY, label = "Layout", order = 3, build = BuildPage })
    if not ok then FS.Layout.ForwardError(err) end
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

HookBlizzardEditMode()
RegisterPage()

-- A preview resized or re-seated (a size chip, the config page, a move of a raid seat) takes its handle with it: a new size
-- swaps which raid handle is up, and the selection goes with the swap, so a nudge or a drag follows the grid on screen.
do
    local preview = RaidPreview()
    if preview and type(preview.OnChange) == "function" then
        preview.OnChange(function()
            if not editing then return end
            local followed = selected ~= nil and RAID_IDS[selected] == true
            local ok, err = pcall(ShowHandles)
            if not ok then FS.Layout.ForwardError(err) end
            local now = preview.SeatId()
            if followed and handles[now] and handles[now]:IsShown() then LayoutEdit.Select(now) end
            RefreshSizeButtons()
            CatchUpRaidHandle()
        end)
    end
end

-- The Gunsight switch can flip while /fsedit is open (the editor stays open through the config window's
-- toggle): Stack A's cast bars gain or lose their handles with it. GunsightTape.lua loads before this file, so
-- its callback has already handed the casts over (IsStackActive is current) when this one runs.
if type(FS.Gunsight) == "table" and type(FS.Gunsight.OnActiveChanged) == "function" then
    FS.Gunsight.OnActiveChanged(function()
        if not editing then return end
        local ok, err = pcall(ShowHandles)
        if not ok then FS.Layout.ForwardError(err) end
    end)
end

-- The grid step, the grid and snap switches and the position unit are saved settings: a change from the config page, a
-- profile switch or the panel's own controls lands in the same place.
if FS.Config and type(FS.Config.OnChange) == "function" then
    local function settingChanged()
        if not editing then return end
        RefreshGrid()
        PaintDoneControls()
        RefreshPosition(true)
    end
    for _, key in ipairs({ "layout.grid", "layout.snap", "layout.showGrid", "layout.posUnit" }) do
        FS.Config.OnChange(key, settingChanged)
    end
end

-- A UI scale or resolution change moves every pixel: the handles, the panels' whole pixel rows and the grid's lines.
local function ReseatPanels()
    if donePanel then
        LayoutDoneRow(donePanel)
        RefreshSizeButtons()
    end
    if posPanel then LayoutPositionRow(posPanel) end
    RefreshGrid()
end

local watcher = CreateFrame("Frame")
watcher:RegisterEvent("PLAYER_LOGIN")
watcher:RegisterEvent("PLAYER_REGEN_DISABLED")
watcher:RegisterEvent("UI_SCALE_CHANGED")
watcher:RegisterEvent("DISPLAY_SIZE_CHANGED")
if not blizzardHooked then watcher:RegisterEvent("ADDON_LOADED") end
watcher:SetScript("OnEvent", function(self, event, addon)
    if event == "PLAYER_REGEN_DISABLED" then
        LayoutEdit.Exit()
    elseif event == "PLAYER_LOGIN" then
        RegisterPage()
        HookBlizzardEditMode()
    elseif event == "ADDON_LOADED" then
        if addon == "Blizzard_EditMode" then
            HookBlizzardEditMode()
            if blizzardHooked then self:UnregisterEvent("ADDON_LOADED") end
        end
    elseif editing then
        SyncAll()
        ReseatPanels()
    end
end)
