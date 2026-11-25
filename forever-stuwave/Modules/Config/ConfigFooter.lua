-- Forever STUwave: the footer of the /fsconfig window (ticket B2)
-- Left: RELOAD UI (a count chip, a pink edge and glow while anything waits on a reload) and RESET PAGE (a count chip of
-- the changed settings on the page, dimmed at 0, asks first) and EDIT LAYOUT (closes the window and opens the layout editor;
-- DONE comes back to the page you were on). Right: the muted "changes apply instantly" and CLOSE. The
-- window position is remembered account wide. Everything is built into CW.FooterSlot the first time the window shows, and
-- repaints with every RefreshAll (a global refresh function, so the shown page and the counts always agree).
--
-- Reload goes through FS.SecureReload (ErrorLog.lua): addon code cannot reload on this client, so the secure /click
-- button is laid over the Reload button while the pointer is on it and the click lands there. The click that reaches this
-- button instead (in combat, or no cover could be placed) only says why nothing happened.
-- Sizes come from CW.Spec; the mockup is mockups/config-window-2026-11-25.html (.foot, .btn, .rl, .dlg).

local _, FS = ...

local CW = FS.ConfigWindow
local I = CW.I
local S = CW.Spec
local C = CW.C

local Theme = FS.Theme
local Config = FS.Config

local Mix, Label, Outline, Tint = I.Mix, I.Label, I.Outline, I.Tint

local Footer = {}
CW.Footer = Footer

local CHAMFER = 4            -- .ch4 of the mockup: a footer button and the dialog buttons
local BTN_GAP = 8            -- between footer buttons, and from the message to CLOSE
local CHIP_PAD = 4           -- .rl: 3 units of padding and the 1 unit edge, each side
local PULSE_PERIOD = 1.6     -- the Reload glow breathes this slowly while a reload waits
local KEYS_KEEP = { ESCAPE = true, ENTER = true, NUMPADENTER = true }
local POS_X, POS_Y = "winX", "winY"   -- account wide, next to winW and winH in ForeverSTUwaveDB.ui

local reloadBtn, resetBtn, editBtn, closeBtn, message
local dialog                 -- { overlay, panel, title, message, keep, reset, row, keys, page }
local sources = {}           -- extra pending reload lists (see CW.AddReloadSource)

-------------------------------------------------------------------------------
-- Pending reloads
-------------------------------------------------------------------------------

-- Another file whose reload waits are not rows of a built tab (a nav power button, a page nobody opened) adds a source:
-- fn() returns a list of labels, or of { label, line }. The footer counts and names them with the rows.
function CW.AddReloadSource(fn)
    if type(fn) ~= "function" then return false end
    sources[#sources + 1] = fn
    return true
end

-- Every change that waits on a reload, once per label: the registry rows whose `reload` function names one (the line it
-- returns is what the row's Reload button shows), then the extra sources. { { label, line }, ... }
function Footer.Pending()
    local list, seen = {}, {}
    local function add(label, line)
        label = tostring(label or "")
        if label == "" or seen[label] then return end
        seen[label] = true
        list[#list + 1] = { label = label, line = type(line) == "string" and line or nil }
    end
    for _, entry in ipairs(CW.Rows()) do
        if type(entry.reload) == "function" then
            local ok, line = pcall(entry.reload)
            if ok and line then add(entry.label or entry.key, line) end
        end
    end
    for _, source in ipairs(sources) do
        local ok, found = pcall(source)
        if ok and type(found) == "table" then
            for _, item in ipairs(found) do
                if type(item) == "table" then add(item.label or item[1], item.line or item[2]) else add(item) end
            end
        end
    end
    return list
end

-------------------------------------------------------------------------------
-- The changed settings of the page on screen
-------------------------------------------------------------------------------

-- The saved keys that differ from their default on the shown page (one entry per key), and the page's key.
function Footer.PageKeys()
    local page = CW.Current()
    local keys, seen = {}, {}
    if page then
        for _, key in ipairs(CW.ChangedKeys(page)) do
            if not seen[key] then
                seen[key] = true
                keys[#keys + 1] = key
            end
        end
    end
    return keys, page
end

local function PageLabel(page)
    for _, cat in ipairs(CW.Categories()) do
        if cat.key == page then return cat.label end
    end
    return tostring(page or "")
end

-------------------------------------------------------------------------------
-- Buttons: hover, pressed, disabled and the hot Reload
-------------------------------------------------------------------------------

local PINK_FILL = Mix(C.ink, C.pink, 0.08)       -- .btn.pk: the dark pink face of RESET N

-- The glow of a hot Reload breathes between 0.2 and 0.5.
local function HotGlow(b)
    return 0.2 + 0.3 * (0.5 + 0.5 * math.sin(2 * math.pi * (b.fsClock or 0) / PULSE_PERIOD))
end

-- Paints one button from its state: `fsHot` (pink edge, glow breathing), `fsPink` (the dialog's RESET N), `fsOver`,
-- `fsDown`. A disabled button shows no hover or press; I.SetLook dims it. Nothing is touched when the state is the one
-- already painted (RefreshAll calls this often); the breathing glow is retinted by its own OnUpdate.
local function Look(b)
    local enabled = b:IsEnabled() and true or false
    local sig = table.concat({ tostring(b.fsHot), tostring(b.fsPink), tostring(b.fsOver and enabled), tostring(b.fsDown and enabled) }, ",")
    if b.fsLookSig == sig then return end
    b.fsLookSig = sig
    local ring, text, fill, glow = C.violet, C.cyan, C.ink, 0.35
    if b.fsHot then
        ring, text, glow = C.pink, C.pink, HotGlow(b)
    elseif b.fsPink then
        ring, text, fill, glow = C.pink, C.text, PINK_FILL, 0.5
    end
    if enabled then
        if b.fsDown then fill = Mix(fill, ring, 0.3) elseif b.fsOver then fill = Mix(fill, ring, 0.16) end
    end
    I.Restyle(b, ring, text, fill, glow)
end
Footer.Look = Look

local function ShowTip(owner, lines)
    GameTooltip:SetOwner(owner, "ANCHOR_TOP")
    GameTooltip:SetText(lines[1], 1, 1, 1, 1, true)
    for i = 2, #lines do
        local line = lines[i]
        if type(line) == "table" then
            GameTooltip:AddLine(line[1], line[2][1], line[2][2], line[2][3], true)
        else
            GameTooltip:AddLine(line, C.muted[1], C.muted[2], C.muted[3], true)
        end
    end
    GameTooltip:Show()
end

local function HideTip(owner)
    if GameTooltip:GetOwner() == owner then GameTooltip:Hide() end
end

-- A button of the footer or the dialog: MakeButton's chamfered look, its label and optional count chip centred as one
-- group, the box sized by its text rounded up to TEXT_SNAP. `tip()` returns the tooltip lines (or nil).
local function NewButton(parent, text, opts)
    opts = opts or {}
    local b = I.MakeButton(parent, { height = S.BTN_H, ring = C.violet, textColor = C.cyan, chamfer = CHAMFER, text = text })
    b.fsText = text
    b.fsPink = opts.pink == true
    b.fsTipFn = opts.tip
    b.fsLabel:ClearAllPoints()
    local chip = CreateFrame("Frame", nil, b)
    chip:SetHeight(S.COUNT_H)
    chip.fsEdges = Outline(chip, C.pink, 0.5)
    chip.fsText = Label(chip, "", S.SMALL, C.pink)
    chip.fsText:SetPoint("CENTER", chip, "CENTER", 0, 0)
    chip:Hide()
    b.fsChip = chip

    b:SetScript("OnEnter", function(self)
        self.fsOver = true
        Look(self)
        if self.fsTipFn then
            local lines = self.fsTipFn()
            if lines then ShowTip(self, lines) end
        end
    end)
    b:SetScript("OnLeave", function(self)
        self.fsOver, self.fsDown = false, false
        Look(self)
        HideTip(self)
    end)
    b:SetScript("OnMouseDown", function(self) self.fsDown = true; Look(self) end)
    b:SetScript("OnMouseUp", function(self) self.fsDown = false; Look(self) end)
    return b
end

-- The count on a button: a chip after the label, or none at 0. The button's width follows (label and chip are one group).
local function SetCount(b, count)
    local chip = b.fsChip
    count = count or 0
    local sig = tostring(b.fsLabel:GetText()) .. "|" .. count
    if b.fsCountSig == sig then return end
    b.fsCountSig = sig
    local label = math.ceil(b.fsLabel:GetStringWidth() or 0)
    local content, chipW = label, 0
    if count > 0 then
        chip.fsText:SetText(tostring(count))
        chipW = S.Snap(math.ceil(chip.fsText:GetStringWidth() or 0) + 2 * CHIP_PAD)
        chip:SetWidth(chipW)
        content = label + BTN_GAP + chipW
    end
    local width = S.Snap(content + 2 * S.BTN_PAD_X)
    b:SetWidth(width)
    local x = math.floor((width - content) / 2)
    b.fsLabel:ClearAllPoints()
    b.fsLabel:SetPoint("LEFT", b, "LEFT", x, 0)
    chip:ClearAllPoints()
    if chipW > 0 then chip:SetPoint("LEFT", b.fsLabel, "RIGHT", BTN_GAP, 0) end
    chip:SetShown(chipW > 0)
    b.fsCount = count
end

-- The pink edge and glow of a Reload that has something to do. The glow breathes through an OnUpdate that exists only
-- while it is hot.
local function SetHot(b, hot)
    hot = hot == true
    if b.fsHot == hot then return end
    b.fsHot = hot
    b.fsClock = 0
    if hot then
        b:SetScript("OnUpdate", function(self, dt)
            self.fsClock = ((self.fsClock or 0) + (dt or 0)) % PULSE_PERIOD
            Tint(self.fsSkin and self.fsSkin.glow, C.pink, HotGlow(self))
        end)
    else
        b:SetScript("OnUpdate", nil)
    end
    Look(b)
end

-------------------------------------------------------------------------------
-- Reset page: the dialog
-------------------------------------------------------------------------------

local function CloseDialog()
    if dialog and dialog.overlay:IsShown() then dialog.overlay:Hide() end
end
Footer.CloseReset = CloseDialog

-- The dialog's frames once it has been built (nil before the first RESET PAGE), for a check to read.
function Footer.Dialog() return dialog end

-- KEEP THEM is the default: Enter and Esc both take it, and both are consumed so Esc does not also close the window.
local function DialogKey(self, key)
    if KEYS_KEEP[key] then
        self:SetPropagateKeyboardInput(false)
        CloseDialog()
    else
        self:SetPropagateKeyboardInput(true)
    end
end

local function EnsureDialog()
    if dialog then return dialog end
    local frame = I.ui.frame
    local overlay = CreateFrame("Frame", nil, frame)
    overlay:SetAllPoints(frame)
    overlay:SetFrameLevel(frame:GetFrameLevel() + 40)      -- above the generic confirm dialog (+30)
    overlay:EnableMouse(true)
    overlay:SetScript("OnShow", function(self) self:EnableKeyboard(true) end)
    overlay:SetScript("OnHide", function(self) self:EnableKeyboard(false) end)
    overlay:SetScript("OnKeyDown", DialogKey)
    local dim = overlay:CreateTexture(nil, "BACKGROUND")
    dim:SetColorTexture(C.track[1], C.track[2], C.track[3], 0.72)
    dim:SetAllPoints(overlay)

    local panel = CreateFrame("Frame", "ForeverSTUwaveConfigResetDialog", overlay)
    panel:SetSize(S.DLG_W, S.DLG_H)
    panel:SetPoint("CENTER", overlay, "CENTER", 0, 0)
    panel:EnableMouse(true)
    Theme.SkinPanel(panel, { strip = false, accent = C.pink, fillColor = { C.track[1], C.track[2], C.track[3], 1 }, glowAlpha = 0.35 })

    local title = Label(panel, "RESET PAGE", S.TEXT, C.pink)
    title:SetPoint("TOP", panel, "TOP", 0, -S.PAD)
    local text = Label(panel, "", S.TEXT, C.text)
    text:SetWidth(S.DLG_W - 2 * S.PAD - 2)
    text:SetHeight(48)
    text:SetJustifyH("CENTER")
    text:SetJustifyV("TOP")
    text:SetWordWrap(true)
    text:SetPoint("TOP", panel, "TOP", 0, -(S.PAD + 16 + 12))

    local row = CreateFrame("Frame", nil, panel)
    row:SetHeight(S.BTN_H)
    row:SetPoint("BOTTOM", panel, "BOTTOM", 0, S.PAD)
    local keep = NewButton(row, "KEEP THEM")
    keep:SetPoint("LEFT", row, "LEFT", 0, 0)
    keep:SetScript("OnClick", CloseDialog)
    local reset = NewButton(row, "RESET", { pink = true })
    reset:SetPoint("RIGHT", row, "RIGHT", 0, 0)
    reset:SetScript("OnClick", function()
        local keys = dialog.keys
        CloseDialog()
        if keys and #keys > 0 then CW.ResetKeys(keys) end
    end)
    SetCount(keep, 0)
    SetCount(reset, 0)
    Look(keep)
    Look(reset)
    overlay:Hide()
    dialog = { overlay = overlay, panel = panel, title = title, message = text, keep = keep, reset = reset, row = row }
    return dialog
end

-- Asks first: the dialog names the count and the page; nothing is written until RESET N. False (and nothing shown) when
-- the page has no changed setting or the settings are read-only.
function Footer.OpenReset()
    if not Footer.Build() or Config.IsReadOnly() then return false end
    local keys, page = Footer.PageKeys()
    if #keys == 0 then return false end
    local d = EnsureDialog()
    if I.CloseMenu then I.CloseMenu() end
    if I.CloseDialog then I.CloseDialog() end
    local n = #keys
    d.keys, d.page = keys, page
    d.message:SetText(("Put the %d changed %s on %s back to %s?"):format(
        n, n == 1 and "setting" or "settings", PageLabel(page), n == 1 and "its default" or "their defaults"))
    d.reset.fsLabel:SetText("RESET " .. n)
    SetCount(d.keep, 0)
    SetCount(d.reset, 0)
    d.row:SetWidth(d.keep:GetWidth() + BTN_GAP + d.reset:GetWidth())
    d.overlay:Show()
    return true
end

-------------------------------------------------------------------------------
-- Window position
-------------------------------------------------------------------------------

-- Keeps the whole window on the screen: left in [0, pw - w], top in [min(h, ph), ph] (y goes up). A window bigger than the
-- screen is seated at the top left corner.
function Footer.ClampPosition(left, top, w, h, pw, ph)
    left = math.min(math.max(0, pw - w), math.max(0, left))
    top = math.max(math.min(ph, h), math.min(ph, top))
    return left, top
end

-- Saves the window's top left corner account wide as an offset from the top left of the screen, so a new resolution keeps
-- its place. Never part of a profile.
function Footer.SavePosition()
    local f = I.ui.frame
    if not f then return false end
    local left, top = f:GetLeft(), f:GetTop()
    local ph = UIParent:GetHeight()
    if type(left) ~= "number" or type(top) ~= "number" or type(ph) ~= "number" then return false end
    local s = f:GetEffectiveScale() / UIParent:GetEffectiveScale()
    CW.UIState(POS_X, math.floor(left * s + 0.5))
    CW.UIState(POS_Y, math.floor(top * s - ph + 0.5))
    return true
end

-- Seats the saved position, clamped to the screen now. False when nothing was saved.
function Footer.RestorePosition()
    local f = I.ui.frame
    local x, y = CW.UIState(POS_X), CW.UIState(POS_Y)
    if not f or type(x) ~= "number" or type(y) ~= "number" then return false end
    local pw, ph = UIParent:GetWidth(), UIParent:GetHeight()
    if type(pw) ~= "number" or type(ph) ~= "number" or pw <= 0 or ph <= 0 then return false end
    local s = f:GetEffectiveScale() / UIParent:GetEffectiveScale()
    local left, top = Footer.ClampPosition(x, ph + y, f:GetWidth() * s, f:GetHeight() * s, pw, ph)
    f:ClearAllPoints()
    f:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", left / s, top / s)
    return true
end

-------------------------------------------------------------------------------
-- Building and repainting
-------------------------------------------------------------------------------

local function ReloadTip()
    local pending = Footer.Pending()
    local lines = { "Reload UI", "Applies the changes that only a reload can." }
    if #pending == 0 then
        lines[#lines + 1] = "Nothing is waiting on a reload."
    else
        lines[#lines + 1] = { "Waiting on a reload:", C.text }
        for _, item in ipairs(pending) do lines[#lines + 1] = { "\226\128\162 " .. item.label, C.cyan } end
    end
    return lines
end

local function ResetTip()
    if Config.IsReadOnly() then return { "Reset page", "Settings are read-only this session." } end
    if (resetBtn.fsCount or 0) == 0 then return { "Reset page", "Nothing on this page differs from its defaults." } end
    return { "Reset page", "Puts every changed setting on this page back to its default. Asks first." }
end

-- Repaints the counts, the Reload edge and the Reset page state from the settings now. Runs with every RefreshAll.
function Footer.Update()
    if not reloadBtn then return end
    local pending = #Footer.Pending()
    SetCount(reloadBtn, pending)
    SetHot(reloadBtn, pending > 0)
    local keys = Footer.PageKeys()
    SetCount(resetBtn, #keys)
    I.SetLook(resetBtn, #keys > 0 and not Config.IsReadOnly())
    Look(reloadBtn)
    Look(resetBtn)
    Look(editBtn)
end

-- The footer buttons, once. The Reload button is covered by the secure reload button while the pointer is on it.
function Footer.Build()
    if reloadBtn then return true end
    local left, right = CW.FooterSlot("left"), CW.FooterSlot("right")
    if not (left and right) then return false end

    reloadBtn = NewButton(left, "RELOAD UI", { tip = ReloadTip })
    reloadBtn:SetPoint("LEFT", left, "LEFT", 0, 0)
    reloadBtn:SetScript("OnClick", function()
        local SR = FS.SecureReload
        if SR and SR.Explain then SR.Explain() end
    end)
    reloadBtn:HookScript("OnEnter", function(self)
        local SR = FS.SecureReload
        if SR and SR.Cover then SR.Cover(self) end
    end)
    -- The cover takes the pointer from this button, so the leave that follows keeps the look and the tip: they go when the
    -- pointer leaves the cover (which runs this button's OnLeave again) or the button hides.
    reloadBtn:SetScript("OnLeave", function(self)
        local SR = FS.SecureReload
        if SR and SR.Covering and SR.Covering() == self then return end
        self.fsOver, self.fsDown = false, false
        Look(self)
        HideTip(self)
    end)
    reloadBtn:HookScript("OnHide", function(self)
        local SR = FS.SecureReload
        if SR and SR.Covering and SR.Covering() == self and SR.Uncover then SR.Uncover() end
    end)
    SetCount(reloadBtn, 0)

    resetBtn = NewButton(left, "RESET PAGE", { tip = ResetTip })
    resetBtn:SetPoint("LEFT", reloadBtn, "RIGHT", BTN_GAP, 0)
    resetBtn:SetScript("OnClick", function(self)
        if self:IsEnabled() then Footer.OpenReset() end
    end)
    SetCount(resetBtn, 0)

    editBtn = NewButton(left, "EDIT LAYOUT", { tip = function()
        return { "Edit layout", "Move and resize frames on screen (/fsedit). Done brings you back here." }
    end })
    editBtn:SetPoint("LEFT", resetBtn, "RIGHT", BTN_GAP, 0)
    editBtn:SetScript("OnClick", function()
        local LE = FS.LayoutEdit
        if LE and LE.EnterFromConfig then LE.EnterFromConfig(CW.Current()) end
    end)
    SetCount(editBtn, 0)

    closeBtn = NewButton(right, "CLOSE")
    closeBtn:SetPoint("RIGHT", right, "RIGHT", 0, 0)
    closeBtn:SetScript("OnClick", function() CW.Close() end)
    SetCount(closeBtn, 0)

    message = Label(right, "changes apply instantly", S.SMALL, C.muted)
    message:SetPoint("RIGHT", closeBtn, "LEFT", -BTN_GAP, 0)
    message:SetJustifyH("RIGHT")

    Footer.reload, Footer.reset, Footer.edit, Footer.close, Footer.message = reloadBtn, resetBtn, editBtn, closeBtn, message
    I.ui.frame:HookScript("OnDragStop", function() Footer.SavePosition() end)
    table.insert(I.controls, Footer.Update)
    Footer.RestorePosition()
    Footer.Update()
    return true
end

-- Closing the window with a reload waiting says so once, in plain words.
local function SayWaiting()
    local n = #Footer.Pending()
    if n == 0 then return end
    I.Say(("%d %s for a reload. Use Reload UI in /fsconfig."):format(n, n == 1 and "change waits" or "changes wait"))
end

CW.On("show", function()
    if Footer.Build() then Footer.Update() end
end)

CW.On("hide", function()
    CloseDialog()
    SayWaiting()
end)
