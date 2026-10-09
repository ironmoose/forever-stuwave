-- Forever STUwave: LayoutEdit
-- /fsedit: an edit mode that lays one insecure drag handle over each movable frame and
-- writes the drop through FS.Layout.SetOverride. The covered frames are never dragged, so
-- secure ones stay untouched. Loads after the modules whose frames it reads (see .toc).

local _, FS = ...

local LayoutEdit = FS.LayoutEdit or {}
FS.LayoutEdit = LayoutEdit

local PREFIX = "|cff22e0ffstuwave://layout|r  "
local GRID_CHOICES = { [4] = true, [8] = true, [16] = true, [32] = true }
local GRID_DEFAULT = 8
local MIN_HANDLE = 12
local EDGE = 2
local PAGE_KEY = "layout"
local DONE_W, DONE_H, PANEL_W, PANEL_H = 64, 24, 214, 44
local INK = { 0.090, 0.047, 0.165, 1 }

-- Display order is also the label table; an id without an applied frame gets no handle.
local MOVABLE = {
    { id = "player",       label = "Player frame" },
    { id = "target",       label = "Target frame" },
    { id = "chat",         label = "Chat" },
    { id = "minimap",      label = "Minimap" },
    { id = "buffs",        label = "Buffs" },
    { id = "debuffs",      label = "Debuffs" },
    { id = "party",        label = "Party" },
    { id = "focus",        label = "Focus" },
    { id = "boss",         label = "Boss" },
    { id = "stance",       label = "Stance bar" },
    { id = "action",       label = "Action bars" },
    { id = "professions",  label = "Professions" },
    { id = "petcontainer", label = "Pet" },
    { id = "tooltip",      label = "Tooltip" },
    { id = "tcast",        label = "Target cast bar" },
    { id = "pcast",        label = "Player cast bar" },
}

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
local returnToConfig = false
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
    local L = FS.Layout[id]
    local hx, hy = PointXY(handle, L.point)
    local px, py = PointXY(UIParent, L.relPoint)
    if not (hx and px) then return nil end
    local scale = UnitScale(id)
    return (hx - px) / scale, (hy - py) / scale
end

local function CurrentXY(id)
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
local function SyncHandle(id)
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
    if AppliedFrame(id) then return false end
    if handles[id] then handles[id]:Hide() end
    if selected == id then selected = nil end
    return true
end

local function Commit(id, x, y)
    local Layout = FS.Layout
    local L = Layout[id]
    if FrameGone(id) then return false end
    local oldX, oldY = L.x, L.y
    if math.abs(x - oldX) < 0.25 and math.abs(y - oldY) < 0.25 and not (id == "petcontainer" and LegacyPetPosition()) then
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

function LayoutEdit.ResetOne(id)
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

local function NewEdge(handle, p1, p2, horizontal)
    local edge = handle:CreateTexture(nil, "BORDER")
    edge:SetPoint(p1, handle, p1)
    edge:SetPoint(p2, handle, p2)
    if horizontal then edge:SetHeight(EDGE) else edge:SetWidth(EDGE) end
    handle.edges[#handle.edges + 1] = edge
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

    handle.fill = handle:CreateTexture(nil, "BACKGROUND")
    handle.fill:SetAllPoints(handle)
    handle.edges = {}
    NewEdge(handle, "TOPLEFT", "TOPRIGHT", true)
    NewEdge(handle, "BOTTOMLEFT", "BOTTOMRIGHT", true)
    NewEdge(handle, "TOPLEFT", "BOTTOMLEFT", false)
    NewEdge(handle, "TOPRIGHT", "BOTTOMRIGHT", false)

    handle.label = handle:CreateFontString(nil, "OVERLAY")
    if FS.Theme and FS.Theme.ApplyMono then
        local r, g, b = Cyan()
        FS.Theme.ApplyMono(handle.label, 11, { r, g, b, 1 })
    end
    handle.label:SetPoint("CENTER", handle, "CENTER")
    handle.label:SetText(def.label)

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

-- A plain insecure panel above the handles; the overlay under them keeps the mouse off.
local function NewDonePanel()
    local Theme = FS.Theme
    local r, g, b = Cyan()
    local panel = CreateFrame("Frame", nil, UIParent)
    panel:SetFrameStrata("FULLSCREEN_DIALOG")
    panel:SetFrameLevel(30)
    panel:SetSize(PANEL_W, PANEL_H)
    panel:SetPoint("TOP", UIParent, "TOP", 0, -24)
    panel:EnableMouse(true)
    if Theme and Theme.SkinPanel then Theme.SkinPanel(panel, { strip = false, scanline = false }) end

    panel.title = panel:CreateFontString(nil, "OVERLAY")
    if Theme and Theme.ApplyMono then Theme.ApplyMono(panel.title, 11, { r, g, b, 1 }) end
    panel.title:SetPoint("LEFT", panel, "LEFT", 16, 0)
    panel.title:SetText("LAYOUT EDIT")

    local done = CreateFrame("Button", nil, panel)
    done:SetSize(DONE_W, DONE_H)
    done:SetPoint("RIGHT", panel, "RIGHT", -10, 0)
    done:RegisterForClicks("LeftButtonUp")
    local fill = Theme and Theme.AddCutSliceFill and Theme.AddCutSliceFill(done, INK, 6)
    if Theme and Theme.SkinButton then
        Theme.SkinButton(done, { borderColor = { r, g, b, 1 }, chamfer = 6, glowAlpha = 0.35 })
    end
    done.label = done:CreateFontString(nil, "OVERLAY")
    if Theme and Theme.ApplyMono then Theme.ApplyMono(done.label, 11, { r, g, b, 1 }) end
    done.label:SetPoint("CENTER", done, "CENTER")
    done.label:SetText("DONE")

    done:SetScript("OnEnter", function(self)
        if fill then fill:SetVertexColor(INK[1] + (r - INK[1]) * 0.16, INK[2] + (g - INK[2]) * 0.16, INK[3] + (b - INK[3]) * 0.16, 1) end
        GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
        GameTooltip:SetText("Save and leave layout edit. Esc does the same.", 1, 1, 1, 1, true)
        GameTooltip:Show()
    end)
    done:SetScript("OnLeave", function()
        if fill then fill:SetVertexColor(INK[1], INK[2], INK[3], 1) end
        GameTooltip:Hide()
    end)
    done:SetScript("OnClick", function() LayoutEdit.Done() end)
    panel.done = done
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

local function RefuseInCombat()
    if not InCombatLockdown() then return false end
    Say("can't edit the layout in combat")
    return true
end

function LayoutEdit.Enter()
    if editing then return true end
    if RefuseInCombat() then return false end
    if BlizzardEditModeActive() then
        Say("close Blizzard Edit Mode first")
        return false
    end
    -- Editing is on before any handle exists, so a failure part way is undone by Exit.
    editing = true
    selected = nil
    dragging = nil
    local chatSkipped = false
    local ok, err = pcall(function()
        EnsureOverlay()
        donePanel = donePanel or NewDonePanel()
        for _, def in ipairs(MOVABLE) do
            if HasHandle(def.id) then
                handles[def.id] = handles[def.id] or NewHandle(def)
                Paint(handles[def.id], false)
                SyncHandle(def.id)
                handles[def.id]:Show()
            else
                if handles[def.id] then handles[def.id]:Hide() end
                if def.id == "chat" and AppliedFrame("chat") then chatSkipped = true end
            end
        end
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
    Say("layout editor off")
end

-- DONE and Esc: leave, and go back to the Layout page when the config button started the edit.
function LayoutEdit.Done()
    local reopen = returnToConfig and editing and not InCombatLockdown()
    LayoutEdit.Exit()
    local window = FS.ConfigWindow
    if reopen and type(window) == "table" and type(window.Open) == "function" then window.Open(PAGE_KEY) end
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
            onClick = function()
                if RefuseInCombat() then return end
                if FS.ConfigWindow.Close then FS.ConfigWindow.Close() end
                local was = editing
                returnToConfig = LayoutEdit.Enter() == true and not was
            end,
        })
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
