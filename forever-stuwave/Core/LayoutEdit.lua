-- Forever STUwave: LayoutEdit
-- /fsedit: an edit mode that lays one insecure drag handle over each movable frame and
-- writes the drop through FS.Layout.SetOverride. The covered frames are never dragged, so
-- secure ones stay untouched. Loads after the modules whose frames it reads (see .toc).
-- Each raid size (5 to 40) has its own layout entry (raid5 .. raid40) and no frame of its own to cover out of a raid, so
-- while the editor is on RaidFrames.lua shows a preview grid (fake members, a size per button on the panel) at the seat
-- of the size picked, and that size's "Raid N" handle covers it.
-- A handle's outline is drawn outside the covered frame, clear of its own border, and never over the frame's content.

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
local DONE_W, DONE_H, PANEL_W, PANEL_H = 64, 24, 246, 44
-- The raid size chips, the row they sit in (under the title row) and the panel's right padding, in UI units.
local SIZE_W, SIZE_H, SIZE_GAP, SIZE_ROW, SIZE_PAD = 26, 22, 4, 30, 10

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
}

-- The ids of the raid layouts: only the previewed size's handle is ever up.
local RAID_IDS = {}
for _, def in ipairs(MOVABLE) do
    if def.raid then RAID_IDS[def.id] = true end
end

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
end

local editing = false
local selected = nil
local dragging = nil
local handles = {}
local overlay = nil
local donePanel = nil
local returnToConfig = false   -- the config page DONE or Esc reopens, when the config window started the edit
local pageRegistered = false
local blizzardHooked = false

local function Say(text)
    print(PREFIX .. text)
end

local function Cyan()
    local c = FS.Theme and FS.Theme.COLOR_POWER
    return c and c[1] or 0.133, c and c[2] or 0.878, c and c[3] or 1
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

local function HasHandle(id)
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
    end
end

local function SyncAll()
    for id in pairs(handles) do
        if handles[id]:IsShown() then SyncHandle(id) end
    end
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
        if selected == id then selected = nil end
        return true
    end
    local provider = Provider(id)
    if provider and provider.Ready() then return false end
    if AppliedFrame(id) then return false end
    if handles[id] then handles[id]:Hide() end
    if selected == id then selected = nil end
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
    selected = id
    if old then Paint(old, false) end
    if id and handles[id] then Paint(handles[id], true) end
end

local function NewHandle(def)
    local id = def.id
    local handle = CreateFrame("Frame", nil, UIParent)
    handle:SetFrameStrata("FULLSCREEN_DIALOG")
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
        if editing and button == "RightButton" then LayoutEdit.ResetOne(id) end
    end)
    handle:SetScript("OnDragStart", function(self)
        if not editing then return end
        LayoutEdit.Select(id)
        dragging = id
        self:StartMoving()
    end)
    handle:SetScript("OnDragStop", function(self)
        self:StopMovingOrSizing()
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
    local left, top = PANEL_W - SIZE_PAD - total / es, math.floor(PANEL_H * es + 0.5) / es
    for index, button in ipairs(buttons) do
        button:SetSize(w / es, h / es)
        button:ClearAllPoints()
        button:SetPoint("TOPLEFT", panel, "TOPLEFT", left + (index - 1) * (w + gap) / es, -top)
        local e = button.edges
        e[1]:ClearAllPoints(); e[1]:SetPoint("TOPLEFT", button, "TOPLEFT", 0, 0)
        e[1]:SetPoint("TOPRIGHT", button, "TOPRIGHT", 0, 0); e[1]:SetHeight(thick)
        e[2]:ClearAllPoints(); e[2]:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", 0, 0)
        e[2]:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", 0, 0); e[2]:SetHeight(thick)
        e[3]:ClearAllPoints(); e[3]:SetPoint("TOPLEFT", button, "TOPLEFT", 0, -thick)
        e[3]:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", 0, thick); e[3]:SetWidth(thick)
        e[4]:ClearAllPoints(); e[4]:SetPoint("TOPRIGHT", button, "TOPRIGHT", 0, -thick)
        e[4]:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", 0, thick); e[4]:SetWidth(thick)
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
    button.fill = button:CreateTexture(nil, "BACKGROUND")
    button.fill:SetAllPoints(button)
    button.edges = {}
    for i = 1, 4 do button.edges[i] = button:CreateTexture(nil, "BORDER") end
    SnapToPixels(button.fill)
    for _, edge in ipairs(button.edges) do SnapToPixels(edge) end
    button.label = button:CreateFontString(nil, "OVERLAY")
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
    label:SetPoint("LEFT", panel, "TOPLEFT", 16, -(PANEL_H + SIZE_H / 2))
    label:SetText("RAID")
    panel.sizeLabel = label
    panel.sizeButtons = {}
    for index, size in ipairs(preview.SIZES) do
        panel.sizeButtons[index] = NewSizeButton(panel, preview, size)
        PaintSizeButton(panel.sizeButtons[index])
    end
    SeatSizeButtons(panel)
end

-- A plain insecure panel above the handles; the overlay under them keeps the mouse off.
local function NewDonePanel()
    local Theme = FS.Theme
    local r, g, b = Cyan()
    local preview = RaidPreview()
    local panel = CreateFrame("Frame", nil, UIParent)
    panel:SetFrameStrata("FULLSCREEN_DIALOG")
    panel:SetFrameLevel(30)
    panel:SetSize(PANEL_W, preview and PANEL_H + SIZE_ROW or PANEL_H)
    panel:SetPoint("TOP", UIParent, "TOP", 0, -24)
    panel:EnableMouse(true)
    if Theme and Theme.SkinPanel then Theme.SkinPanel(panel, { strip = false, scanline = false }) end

    panel.title = panel:CreateFontString(nil, "OVERLAY")
    if Theme and Theme.ApplyMono then Theme.ApplyMono(panel.title, 11, { r, g, b, 1 }) end
    panel.title:SetPoint("LEFT", panel, "TOPLEFT", 16, -PANEL_H / 2)
    panel.title:SetText("LAYOUT EDIT")

    local done = CreateFrame("Button", nil, panel)
    done:SetSize(DONE_W, DONE_H)
    done:SetPoint("RIGHT", panel, "TOPRIGHT", -10, -PANEL_H / 2)
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
    if preview then BuildSizeRow(panel, preview) end
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
        elseif key == "ESCAPE" then
            self:SetPropagateKeyboardInput(false)
            LayoutEdit.Done()
        elseif arrow and selected then
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
            if selected == def.id then selected = nil end
            if dragging == def.id then
                handles[def.id]:StopMovingOrSizing()
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
    local chatSkipped = false
    local ok, err = pcall(function()
        EnsureOverlay()
        donePanel = donePanel or NewDonePanel()
        -- The preview first: the raid handle covers it. The saved size may have changed since the panel was built.
        local preview = RaidPreview()
        if preview then preview.Show() end
        RefreshSizeButtons()
        chatSkipped = ShowHandles()
        overlay:Show()
        overlay:EnableKeyboard(true)
        donePanel:Show()
    end)
    if not ok then
        LayoutEdit.Exit()
        FS.Layout.ForwardError(err)
        return false
    end
    Say("layout editor on: drag a piece, arrows nudge, Shift+arrow by the grid, right-click resets one, Esc leaves")
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
    for _, handle in pairs(handles) do
        handle:StopMovingOrSizing()
        handle:Hide()
    end
    if overlay then
        overlay:EnableKeyboard(false)
        overlay:Hide()
    end
    if donePanel then donePanel:Hide() end
    local preview = RaidPreview()
    if preview then pcall(preview.Hide) end
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
    local reopen = page and editing and not InCombatLockdown()
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
            "Drag any piece. Arrows nudge it, Shift+arrow by the grid step. Right-click resets one piece. Esc leaves. Out of combat only.")
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
                .. "Right-click a handle to put that size back at its default seat.")
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
    end
end)
