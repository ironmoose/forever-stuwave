-- Forever STUwave: Config, profile export and import
-- The // SHARE section of the Profiles page (Export this profile, Import a profile) and the two dialogs behind it. Export
-- shows the active profile as one string, selected, for Ctrl+C. Import takes a pasted string, shows what is inside (or one
-- pink reason), and adds it as a new profile under a name that is checked; it never overwrites and never switches. The string
-- format, the validation and the encoding are Core/ProfileCodec.lua; the profile itself is made by Config.ImportProfile. The
-- module switches a string carries go into the new profile only when the dialog's box is ticked (a profile made without them
-- starts with every module on); they apply when the profile is switched to, like any profile change.
--
-- CW.Share: OpenExport, OpenImport, Close, Inspect(text), SuggestName(name), Apply(text, name, withModules); Share.ui holds
-- the dialog's frames for the harness (tools/profilecodec-harness.py).

local _, FS = ...

local CW = FS.ConfigWindow
local UI, I, S, C = CW.UI, CW.I, CW.Spec, CW.C
local Theme, Config, Codec = FS.Theme, FS.Config, FS.ProfileCodec

local Share = CW.Share or {}
CW.Share = Share
local ui = Share.ui or {}
Share.ui = ui

local LINE_H = 16
local NOTE_H = 16
local ROW_H = 24
local MODULES_H = 32          -- the modules checkbox row and the gap above it
local NAME_SHOWN = 16         -- characters of the profile's name in the line

local WHAT = {
    { value = "all", text = "All" },
    { value = "settings", text = "Settings" },
    { value = "layout", text = "Layout" },
}

local TIP_EXPORT = "The text is already selected: Ctrl+C copies it. Paste it into Import on another character, or send it to a friend."
local TIP_IMPORT = "Always makes a new profile, so nothing you have is overwritten. Switch to it on the Profiles page when you want it."

-------------------------------------------------------------------------------
-- Where the rows' own limits come from
-------------------------------------------------------------------------------

-- { [key] = { min, max, options } } for every keyed slider and segmented row built so far. Rows of a tab nobody has opened
-- are not here: a number for one of those is only held to the codec's general bound.
local function LimitIndex()
    local index = {}
    for _, entry in ipairs(CW.Rows()) do
        local key = entry.cfgKey
        if key and not index[key] then
            local lo, hi = entry.min, entry.max
            if entry.kind == "slider" then lo, hi = lo or 0, hi or 100 end
            local options
            local o = entry.opts
            if entry.kind == "segmented" and type(o) == "table" and type(o.options) == "table" then
                options = {}
                for _, option in ipairs(o.options) do options[#options + 1] = option.value end
            end
            if lo ~= nil or hi ~= nil or options then index[key] = { min = lo, max = hi, options = options } end
        end
    end
    return index
end

if Codec and Codec.SetLimitSource then Codec.SetLimitSource(LimitIndex) end

-------------------------------------------------------------------------------
-- Names
-------------------------------------------------------------------------------

local function NameMax() return Config.NAME_MAX or 32 end

local function CharCount(text)
    local _, n = text:gsub("[^\128-\191]", "")
    return n
end

local function TrimChars(text, max)
    local count = 0
    for start in text:gmatch("()[\1-\127\194-\244][\128-\191]*") do
        count = count + 1
        if count > max then return text:sub(1, start - 1) end
    end
    return text
end

local function CleanBase(name)
    if type(name) ~= "string" then return nil end
    name = name:gsub("[%c|]", "")
    name = name:match("^%s*(.-)%s*$")
    if name == "" then return nil end
    return name
end

-- "<name> 2", or 3, 4 ... the first one no profile has (names compare without case), trimmed to fit Config.NAME_MAX.
function Share.SuggestName(base)
    base = CleanBase(base) or "Imported"
    local taken = {}
    for _, name in ipairs(Config.ListProfiles()) do taken[name:lower()] = true end
    local n = 2
    while true do
        local suffix = " " .. n
        local head = TrimChars(base, NameMax() - CharCount(suffix)):gsub("%s+$", "")
        local candidate = head .. suffix
        if not taken[candidate:lower()] then return candidate end
        n = n + 1
    end
end

-- The reason a name cannot be used for the new profile, or nil.
local function NameProblem(name)
    if type(name) ~= "string" then name = "" end
    name = name:match("^%s*(.-)%s*$")
    if name == "" then return "The name is empty" end
    if CharCount(name) > NameMax() then return ("The name is longer than %d characters"):format(NameMax()) end
    if name:find("%c") or name:find("|", 1, true) then return "The name has characters that are not allowed" end
    local lowered = name:lower()
    for _, existing in ipairs(Config.ListProfiles()) do
        if existing:lower() == lowered then return "A profile with that name exists" end
    end
end

-------------------------------------------------------------------------------
-- What a string holds, and putting it in
-------------------------------------------------------------------------------

local function ModuleSwitch()
    local switch = FS.ModuleSwitch
    if type(switch) == "table" and type(switch.Set) == "function" and type(switch.Snapshot) == "function" then return switch end
end

-- The module switches the string would turn off in the new profile (a new profile starts with every module on, so a switch
-- the string holds as on changes nothing): { { key, label, on = false, live } ... } sorted by label.
local function ModuleChanges(modules)
    local switch = ModuleSwitch()
    local list = {}
    if not (switch and modules) then return list end
    for key, on in pairs(modules) do
        if on == false then
            local labelOk, label = true, nil
            if type(switch.Label) == "function" then labelOk, label = pcall(switch.Label, key) end
            local live = false
            if type(switch.IsLive) == "function" then
                local liveOk, answer = pcall(switch.IsLive, key)
                live = liveOk and answer == true
            end
            list[#list + 1] = { key = key, label = (labelOk and label) or key, on = false, live = live }
        end
    end
    table.sort(list, function(a, b) return a.label < b.label end)
    return list
end

local function ModuleTip(list)
    if #list == 0 then return "Every module in this string is on, the same as a new profile starts." end
    local off, waits = {}, false
    for _, item in ipairs(list) do
        off[#off + 1] = item.label
        if not item.live then waits = true end
    end
    local lines = { "The new profile starts with these off: " .. table.concat(off, ", ") .. "." }
    if waits then lines[#lines + 1] = "Switching to it takes a Reload UI." end
    return table.concat(lines, "\n")
end

-- Reads `text`: { ok = true, payload, info, hasModules, moduleChanges, ignored, clamped } or { ok = false, code, reason }.
function Share.Inspect(text)
    local result, code, reason = Codec.Read(text)
    if not result then return { ok = false, code = code, reason = reason } end
    local modules = result.payload.modules
    return {
        ok = true, payload = result.payload, info = result.info, kind = result.kind,
        hasModules = modules ~= nil and next(modules) ~= nil,
        moduleChanges = ModuleChanges(modules),
        ignored = result.report.ignored, clamped = result.report.clamped,
    }
end

-- Adds the profile `name` from the string `text`; with `withModules` the new profile also gets the module switches the string
-- carries (without it every module starts on). Returns true and the name made, or false and a reason. Nothing is switched to,
-- and nothing is overwritten.
function Share.Apply(text, name, withModules)
    local result = Share.Inspect(text)
    if not result.ok then return false, result.reason end
    if Config.IsReadOnly() then return false, "Settings are read-only this session" end
    local problem = NameProblem(name)
    if problem then return false, problem end
    local data = result.payload
    if not withModules and data.modules ~= nil then
        data = {}
        for key, value in pairs(result.payload) do
            if key ~= "modules" then data[key] = value end
        end
    end
    local ok, made = Config.ImportProfile(name, data)
    if not ok then return false, made end
    return true, made
end

-- "Name / 48 settings and 14 frame positions / v1.0.0" (export) or "... / made on v1.0.0" (import).
local function Describe(info, made)
    local name = info.name or "Profile"
    if CharCount(name) > NAME_SHOWN then name = TrimChars(name, NAME_SHOWN) .. "..." end
    local line = ("%s / %s"):format(name, Codec.CountsText(info))
    if info.addon then line = line .. (" / %sv%s"):format(made and "made on " or "", info.addon) end
    return line
end

-- "2 skipped, 1 adjusted to fit", or nil when nothing was touched.
local function NoteText(result)
    local parts = {}
    if (result.ignored or 0) > 0 then parts[#parts + 1] = ("%d skipped"):format(result.ignored) end
    if (result.clamped or 0) > 0 then parts[#parts + 1] = ("%d adjusted to fit"):format(result.clamped) end
    if #parts == 0 then return nil end
    return table.concat(parts, ", ")
end

-------------------------------------------------------------------------------
-- The dialog
-------------------------------------------------------------------------------

local function Safe(obj, method, ...)
    local fn = obj[method]
    if type(fn) == "function" then pcall(fn, obj, ...) end
end

local function MakeWell(parent, edgeColor)
    local well = CreateFrame("Frame", nil, parent)
    local fill = well:CreateTexture(nil, "BACKGROUND")
    fill:SetColorTexture(C.track[1], C.track[2], C.track[3], 1)
    fill:SetAllPoints(well)
    well.fsEdges = I.Outline(well, edgeColor, 1)
    return well
end

local function Paint(edges, color)
    for _, t in ipairs(edges) do I.Tint(t, color) end
end

local function MakeBox(parent, text, ring, textColor)
    local b = I.MakeButton(parent, { height = S.BTN_H, ring = ring, textColor = textColor, chamfer = 6, text = text })
    b:SetWidth(S.Snap(b.fsLabel:GetStringWidth() + 2 * S.BTN_PAD_X))
    I.HoverStyle(b, ring)
    return b
end

local function Escape(frame, close)
    frame:SetScript("OnShow", function(self) self:EnableKeyboard(true) end)
    frame:SetScript("OnHide", function(self) self:EnableKeyboard(false) end)
    frame:SetScript("OnKeyDown", function(self, key)
        if key == "ESCAPE" then
            self:SetPropagateKeyboardInput(false)
            close()
        else
            self:SetPropagateKeyboardInput(true)
        end
    end)
end

local X0 = S.PAD + 1                         -- the panel's border plus the window padding
local CONTENT_W = S.SHARE_W - 2 * X0
local BOX_VIEW_W = CONTENT_W - 14
local BOX_VIEW_H = S.SHARE_BOX_H - 16        -- five lines of 16, clipped to whole lines

local Render                                  -- set below

local function SelectAll()
    if not ui.box then return end
    ui.box:SetFocus()
    ui.box:HighlightText()
    -- text set this frame can need the selection asked for once more after it has laid out
    local timer = _G.C_Timer
    if timer and timer.After then
        timer.After(0, function()
            if Share.mode == "export" and ui.overlay:IsShown() and ui.box:HasFocus() then ui.box:HighlightText() end
        end)
    end
end

local function SetWhat(what)
    ui.what = what
    for value, b in pairs(ui.whatButtons) do
        b.fsSelected = value == what
        if b.fsSelected then
            I.Restyle(b, C.cyan, C.cyan, I.Mix(C.ink, C.cyan, 0.2), 0.5)
        else
            I.Restyle(b, C.line, C.muted, C.ink, 0)
        end
    end
    local text, info = Codec.Export(what)
    ui.exported = text or ""
    ui.exportInfo = text and info or nil
    ui.settingText = true
    ui.box:SetText(ui.exported)
    ui.settingText = false
    Render()
    SelectAll()
end

local function Close()
    if not ui.overlay then return end
    if ui.box then ui.box:ClearFocus() end
    if ui.saveEdit then ui.saveEdit:ClearFocus() end
    ui.overlay:Hide()
    Share.mode = nil
end
Share.Close = Close

local function Accept()
    if Share.mode ~= "import" then return end
    local ok, made = Share.Apply(ui.box:GetText(), ui.saveEdit:GetText(), ui.modulesBox.fsChecked == true)
    if not ok then
        Render(made)
        return
    end
    Close()
    I.Say(("added the profile %s. Pick it under Profile in use to switch to it."):format(made))
    CW.RefreshAll()
end

local function MakeCheckbox(parent)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(16, 16)
    b:RegisterForClicks("LeftButtonUp")
    local fill = b:CreateTexture(nil, "BACKGROUND")
    fill:SetColorTexture(C.track[1], C.track[2], C.track[3], 1)
    fill:SetAllPoints(b)
    b.fsEdges = I.Outline(b, C.line, 1)
    b.fsMark = b:CreateTexture(nil, "OVERLAY")
    b.fsMark:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    b.fsMark:SetPoint("TOPLEFT", b, "TOPLEFT", 4, -4)
    b.fsMark:SetPoint("BOTTOMRIGHT", b, "BOTTOMRIGHT", -4, 4)
    b.fsChecked = false
    function b.SetChecked(self, on)
        self.fsChecked = on == true
        self.fsMark:SetShown(self.fsChecked)
        Paint(self.fsEdges, self.fsChecked and C.cyan or C.line)
    end
    b:SetChecked(false)
    b:SetScript("OnClick", function(self)
        if not self:IsEnabled() then return end
        self:SetChecked(not self.fsChecked)
    end)
    return b
end

local function Build()
    if ui.overlay then return end
    if not I.ui.frame then CW.EnsureBuilt() end
    local window = I.ui.frame
    local overlay = CreateFrame("Frame", nil, window)
    overlay:SetAllPoints(window)
    overlay:SetFrameLevel(window:GetFrameLevel() + 30)
    overlay:EnableMouse(true)
    Escape(overlay, Close)
    local dim = overlay:CreateTexture(nil, "BACKGROUND")
    dim:SetColorTexture(7 / 255, 3 / 255, 14 / 255, 0.72)
    dim:SetAllPoints(overlay)
    local panel = CreateFrame("Frame", "ForeverSTUwaveShareDialog", overlay)
    panel:SetSize(S.SHARE_W, S.SHARE_H)
    panel:SetPoint("CENTER", overlay, "CENTER", 0, 0)
    panel:EnableMouse(true)
    Theme.SkinPanel(panel, { strip = false })
    ui.overlay, ui.panel = overlay, panel

    ui.title = I.Label(panel, "", S.TEXT, C.pink)
    ui.help = UI.HelpIcon(panel, "")
    ui.help:SetPoint("LEFT", ui.title, "RIGHT", S.Q_GAP, 0)

    -- the Share choice (export only)
    ui.whatRow = CreateFrame("Frame", nil, panel)
    ui.whatRow:SetSize(CONTENT_W, ROW_H)
    ui.whatLabel = I.Label(ui.whatRow, "Share", S.TEXT, C.text)
    ui.whatLabel:SetPoint("LEFT", ui.whatRow, "LEFT", 0, 0)
    local holder = CreateFrame("Frame", nil, ui.whatRow)
    holder:SetPoint("RIGHT", ui.whatRow, "RIGHT", 0, 0)
    ui.whatButtons = {}
    local x = 0
    for _, option in ipairs(WHAT) do
        local b = I.MakeButton(holder, { height = S.SEG_H, ring = C.line, textColor = C.muted, chamfer = 4, size = S.TEXT,
            glow = 0, text = option.text })
        b:SetWidth(S.Snap(b.fsLabel:GetStringWidth() + 2 * S.SEG_PAD_X))
        b:SetPoint("LEFT", holder, "LEFT", x, 0)
        x = x + b:GetWidth() + S.SEG_GAP
        b:SetScript("OnClick", function() if Share.mode == "export" then SetWhat(option.value) end end)
        ui.whatButtons[option.value] = b
    end
    holder:SetSize(math.max(x - S.SEG_GAP, 1), S.SEG_H)

    -- the string box: a cyan edged well, a clipped scroll frame, one multi line edit box
    ui.well = MakeWell(panel, C.cyan)
    ui.well:SetSize(CONTENT_W, S.SHARE_BOX_H)
    local scroll = CreateFrame("ScrollFrame", nil, ui.well)
    scroll:SetPoint("TOPLEFT", ui.well, "TOPLEFT", 7, -7)
    scroll:SetSize(BOX_VIEW_W, BOX_VIEW_H)
    local box = CreateFrame("EditBox", nil, scroll)
    box:SetMultiLine(true)
    box:SetAutoFocus(false)
    box:SetFont(Theme.FONT_MONO, S.TEXT, "")
    box:SetTextColor(C.text[1], C.text[2], C.text[3], 1)
    Safe(box, "SetSpacing", 2)   -- the font is about 14 tall at this size, so a line lands near the prototype's 16
    box:SetMaxLetters(0)
    Safe(box, "SetMaxBytes", 0)
    box:SetWidth(BOX_VIEW_W)
    box:SetHeight(BOX_VIEW_H)
    scroll:SetScrollChild(box)
    ui.scroll, ui.box = scroll, box
    ui.placeholder = I.Label(ui.well, "Paste a profile here (Ctrl+V)", S.TEXT, C.knob)
    ui.placeholder:SetPoint("TOPLEFT", ui.well, "TOPLEFT", 7, -7)

    box:SetScript("OnTextChanged", function(self, userInput)
        if ui.settingText then return end
        if Share.mode == "export" then
            -- read only in effect: a typed or pasted change is put straight back, select and copy still work
            if userInput and self:GetText() ~= ui.exported then
                ui.settingText = true
                self:SetText(ui.exported)
                ui.settingText = false
            end
            return
        end
        Render()
    end)
    box:SetScript("OnEscapePressed", Close)
    box:SetScript("OnEditFocusGained", function(self)
        if Share.mode == "export" then self:HighlightText() end
        Paint(ui.well.fsEdges, C.cyan)
    end)
    box:SetScript("OnEditFocusLost", function()
        if Share.mode == "import" and ui.box:GetText() == "" then Paint(ui.well.fsEdges, C.line) end
    end)
    box:SetScript("OnMouseUp", function(self)
        if Share.mode == "export" then
            self:SetFocus()
            self:HighlightText()
        end
    end)
    box:SetScript("OnCursorChanged", function(_, _, y, _, h)
        if type(y) ~= "number" or type(h) ~= "number" then return end
        local top = scroll:GetVerticalScroll() or 0
        local at = -y
        if at < top then
            scroll:SetVerticalScroll(at)
        elseif at + h > top + BOX_VIEW_H then
            scroll:SetVerticalScroll(at + h - BOX_VIEW_H)
        end
    end)
    -- a click anywhere in the well reaches the box, which fills it
    ui.well:EnableMouse(true)
    ui.well:SetScript("OnMouseUp", function() ui.box:SetFocus() end)

    ui.line = I.Label(panel, "", S.TEXT, C.cyan)
    ui.line:SetWidth(CONTENT_W)
    ui.line:SetJustifyH("LEFT")
    ui.line:SetWordWrap(false)
    ui.note = I.Label(panel, "", S.TEXT, C.amber)
    ui.note:SetWidth(CONTENT_W)
    ui.note:SetJustifyH("LEFT")
    ui.note:SetWordWrap(false)

    -- Save as (import only)
    ui.saveRow = CreateFrame("Frame", nil, panel)
    ui.saveRow:SetSize(CONTENT_W, ROW_H)
    ui.saveLabel = I.Label(ui.saveRow, "Save as", S.TEXT, C.text)
    ui.saveLabel:SetPoint("LEFT", ui.saveRow, "LEFT", 0, 0)
    ui.saveWell = MakeWell(ui.saveRow, C.line)
    ui.saveWell:SetSize(S.SHARE_IN_W, ROW_H)
    ui.saveWell:SetPoint("RIGHT", ui.saveRow, "RIGHT", 0, 0)
    local edit = CreateFrame("EditBox", nil, ui.saveWell)
    edit:SetPoint("TOPLEFT", ui.saveWell, "TOPLEFT", 7, -2)
    edit:SetPoint("BOTTOMRIGHT", ui.saveWell, "BOTTOMRIGHT", -7, 2)
    edit:SetFont(Theme.FONT_MONO, S.TEXT, "")
    edit:SetTextColor(C.cyan[1], C.cyan[2], C.cyan[3], 1)
    edit:SetAutoFocus(false)
    edit:SetMaxLetters(NameMax())
    edit:SetScript("OnTextChanged", function(_, userInput)
        if ui.settingName then return end
        if userInput then ui.named = true end
        Render()
    end)
    edit:SetScript("OnEnterPressed", function() if ui.accept:IsEnabled() then Accept() end end)
    edit:SetScript("OnEscapePressed", Close)
    edit:SetScript("OnEditFocusGained", function() Paint(ui.saveWell.fsEdges, C.cyan) end)
    edit:SetScript("OnEditFocusLost", function() Paint(ui.saveWell.fsEdges, C.line) end)
    ui.saveEdit = edit

    -- the modules checkbox (import, only when the string carries module switches)
    ui.modulesRow = CreateFrame("Frame", nil, panel)
    ui.modulesRow:SetSize(CONTENT_W, ROW_H)
    ui.modulesBox = MakeCheckbox(ui.modulesRow)
    ui.modulesBox:SetPoint("LEFT", ui.modulesRow, "LEFT", 0, 0)
    ui.modulesLabel = I.Label(ui.modulesRow, "Also set which modules are on", S.TEXT, C.text)
    ui.modulesLabel:SetPoint("LEFT", ui.modulesBox, "RIGHT", S.CTL_GAP, 0)
    ui.modulesHelp = UI.HelpIcon(ui.modulesRow, "")
    ui.modulesHelp:SetPoint("LEFT", ui.modulesLabel, "RIGHT", S.Q_GAP, 0)

    -- the buttons
    ui.done = MakeBox(panel, "DONE", C.pink, C.cyan)
    ui.done:SetScript("OnClick", Close)
    ui.cancel = MakeBox(panel, "CANCEL", C.violet, C.cyan)
    ui.cancel:SetScript("OnClick", Close)
    ui.accept = MakeBox(panel, "IMPORT AS NEW PROFILE", C.pink, C.cyan)
    ui.accept:SetScript("OnClick", function(self) if self:IsEnabled() then Accept() end end)
    ui.done:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", -X0, X0)
    ui.accept:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", -X0, X0)
    ui.cancel:SetPoint("RIGHT", ui.accept, "LEFT", -S.CTL_GAP, 0)

    -- the window closing takes the dialog with it
    CW.On("hide", Close)
    overlay:Hide()
end

-- Seats the parts of the open dialog from the top, the buttons from the bottom, and sizes the panel to fit.
local function Layout(noteShown, modulesShown)
    local panel = ui.panel
    local y = X0
    ui.title:ClearAllPoints()
    ui.title:SetPoint("TOPLEFT", panel, "TOPLEFT", X0, -y)
    y = y + LINE_H + 12
    if Share.mode == "export" then
        ui.whatRow:ClearAllPoints()
        ui.whatRow:SetPoint("TOPLEFT", panel, "TOPLEFT", X0, -y)
        y = y + ROW_H + 12
    end
    ui.well:ClearAllPoints()
    ui.well:SetPoint("TOPLEFT", panel, "TOPLEFT", X0, -y)
    y = y + S.SHARE_BOX_H + 8
    ui.line:ClearAllPoints()
    ui.line:SetPoint("TOPLEFT", panel, "TOPLEFT", X0, -y - (LINE_H - S.TEXT) / 2)
    y = y + LINE_H
    if noteShown then
        ui.note:ClearAllPoints()
        ui.note:SetPoint("TOPLEFT", panel, "TOPLEFT", X0, -y - (NOTE_H - S.TEXT) / 2)
        y = y + NOTE_H
    end
    if Share.mode == "import" then
        y = y + 12
        ui.saveRow:ClearAllPoints()
        ui.saveRow:SetPoint("TOPLEFT", panel, "TOPLEFT", X0, -y)
        y = y + ROW_H
        if modulesShown then
            y = y + 8
            ui.modulesRow:ClearAllPoints()
            ui.modulesRow:SetPoint("TOPLEFT", panel, "TOPLEFT", X0, -y)
            y = y + ROW_H
        end
    end
    -- at least the prototype's height, more when a note or the modules row needs room above the buttons
    panel:SetHeight(math.max(S.SHARE_H, y + 12 + S.BTN_H + X0))
end

local function SetLine(text, color)
    ui.line:SetText(text or "")
    Theme.ApplyMono(ui.line, S.TEXT, color)
end

-- Repaints the open dialog from its parts. `problem` (import) is a reason from a failed Apply to show now.
function Render(problem)
    if not ui.overlay then return end
    if Share.mode == "export" then
        if ui.exportInfo then
            SetLine(Describe(ui.exportInfo, false), C.cyan)
        else
            SetLine("The profile could not be written as a string", C.pink)
        end
        ui.note:SetText("")
        ui.note:Hide()
        Layout(false, false)
        return
    end
    if Share.mode ~= "import" then return end
    local text = ui.box:GetText() or ""
    if ui.parsedText ~= text then
        ui.parsedText = text
        ui.result = text ~= "" and Share.Inspect(text) or nil
        ui.modulesBox:SetChecked(false)
        if ui.result and ui.result.ok and not ui.named then
            ui.settingName = true
            ui.saveEdit:SetText(Share.SuggestName(ui.result.info.name))
            ui.settingName = false
        elseif not ui.result then
            ui.named = false
            ui.settingName = true
            ui.saveEdit:SetText("")
            ui.settingName = false
        end
    end
    local result = ui.result
    ui.placeholder:SetShown(text == "")
    local valid = result ~= nil and result.ok == true
    local reason, color = nil, C.pink
    if result and not result.ok then
        reason = result.reason
    elseif valid then
        reason = Config.IsReadOnly() and "Settings are read-only this session" or NameProblem(ui.saveEdit:GetText())
    end
    if problem then reason = problem end
    if reason then
        SetLine(reason, C.pink)
    elseif valid then
        SetLine(Describe(result.info, true), C.cyan)
    else
        SetLine("", C.cyan)
    end
    local note = valid and NoteText(result) or nil
    ui.note:SetText(note or "")
    ui.note:SetShown(note ~= nil)
    local modulesShown = valid and result.hasModules and ModuleSwitch() ~= nil
    ui.modulesRow:SetShown(modulesShown == true)
    if modulesShown then ui.modulesHelp.fsTip = ModuleTip(result.moduleChanges) end
    local ready = valid and reason == nil
    I.SetLook(ui.accept, ready)
    Layout(note ~= nil, modulesShown == true)
end

local function Open(mode)
    Build()
    I.CloseMenu()
    if I.CloseDialog then I.CloseDialog() end
    Share.mode = mode
    local export = mode == "export"
    ui.title:SetText(export and "EXPORT PROFILE" or "IMPORT PROFILE")
    ui.help.fsTip = export and TIP_EXPORT or TIP_IMPORT
    ui.whatRow:SetShown(export)
    ui.saveRow:SetShown(not export)
    ui.modulesRow:Hide()
    ui.placeholder:SetShown(not export)
    ui.done:SetShown(export)
    ui.cancel:SetShown(not export)
    ui.accept:SetShown(not export)
    ui.overlay:Show()
    if export then
        ui.exported = ""
        SetWhat("all")
    else
        ui.parsedText, ui.result, ui.named = nil, nil, false
        ui.settingText, ui.settingName = true, true
        ui.box:SetText("")
        ui.saveEdit:SetText("")
        ui.settingText, ui.settingName = false, false
        ui.modulesBox:SetChecked(false)
        Paint(ui.well.fsEdges, C.cyan)
        Render()
        ui.box:SetFocus()
    end
end

function Share.OpenExport() Open("export") end
function Share.OpenImport() Open("import") end

-------------------------------------------------------------------------------
-- The // SHARE section of the Profiles page (after Manage, before Modules and Saved data)
-------------------------------------------------------------------------------

CW.ExtendTab("profiles", "p", { title = "Share" }, function(content)
    UI.Button(content, {
        label = "Export this profile", regKey = "share.export", text = "EXPORT",
        tip = "Makes a text string of this profile to paste on another character or give to a friend.",
        onClick = function() Share.OpenExport() end,
    })
    UI.Button(content, {
        label = "Import a profile", regKey = "share.import", text = "IMPORT",
        tip = "Paste a string to add it as a new profile.",
        onClick = function() Share.OpenImport() end,
    })
end, 100)
