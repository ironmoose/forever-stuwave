-- Forever STUwave: System windows
-- The addon list, the addon dialog, the Quick Keybind dialog and the support (Help) frame, restyled in place from the approved SYSTEM
-- mockup (mockups/settings-system-2026-11-12.html, sections 3 to 5). The outer window chrome, the text buttons, the dropdown, the search
-- box and the scroll bar of the addon list already wear the shared panel and control skins (Panels.lua); the Game Menu is already
-- skinned (Popups.lua, Menus.lua) and gets nothing new. This file adds what was still stock. One section per window below.
--
-- Skin only, as in Commerce.lua and Settings.lua: no SetScript, no SetAttribute, no reparent, no resize or re-anchor of a Blizzard
-- frame; alpha holds (FS.HeldArt), post-hooks and our own textures. Every click, tooltip, enable, load and keybinding flow stays
-- stock. Names are the real 12.1 tree (Blizzard_AddOnList AddonList.xml, Blizzard_QuickKeybind QuickKeybind.xml, Blizzard_HelpFrame
-- HelpFrame.xml, Blizzard_SharedXML DialogTemplates.xml); each one is feature-detected and a missing frame is skipped silently. The
-- Quick Keybind frame is skinned out of combat only.
--
-- Left out on purpose, because the mockup shows a computed or invented display and the rule for this pass is "keep the functionality
-- the same as vanilla": the dependency wires and the open socket for a missing dependency, the health strip in the addon list band and
-- the "turn on" key for a disabled dependency, the lamp switch option B; the gunsight brackets, the key socket tab, the ring and the
-- conflict thread of Quick Keybind (they attach to our own action buttons, a different batch); the typed boot log and the sweeping
-- progress bar of the support frame and its "no signal" screen (the page is a real web view; the chip beside the title says the same
-- from the stock loading and error calls); the macro window (a stock list that Panels.lua already frames).

local _, FS = ...

local Theme, HeldArt, PanelSkins, Kit, Char, G = FS.Theme, FS.HeldArt, FS.PanelSkins, FS.ControlKit, FS.CharacterSkin, FS.GroupSkin
if not (Theme and HeldArt and Kit and PanelSkins and Char and G and Char.Box and Char.PaintBox and G.Bar and G.Rule and G.HoldInset
    and PanelSkins.RequireExport(Theme.ApplyMono and Theme.AddPanelChrome and Theme.SkinPanel and Kit.Plate and Kit.Reticle,
        "System.lua disabled: FS.Theme, FS.HeldArt, FS.ControlKit, FS.CharacterSkin or FS.GroupSkin missing")) then return end

local Sys = {}
FS.SystemSkin = Sys

local C = G.C
local Try, Plain, List, Weak = Kit.Try, Kit.Plain, Char.List, G.Weak
local DIS = Theme.COLOR_CTRL_DIS or C.dim

local S = {
    rows = Weak(), cats = Weak(), dialogs = Weak(), headers = Weak(), pins = Weak(), done = {}, chips = {},
}
Sys.state = S

local function Step(name, fn, ...) return G.Step("system", name, fn, ...) end

-------------------------------------------------------------------------------
-- Shared pieces (the same idioms as Settings.lua)
-------------------------------------------------------------------------------

-- Restyles a stock label in mono at `px` and pins it: `pick(r, g, b)` answers the colour for whatever colour the stock code writes
-- to it, and a SetFontObject (which gives the stock font and colour back) is undone.
local function Pin(fs, host, px, pick)
    if type(fs) ~= "table" or Kit.TypeOf(fs) ~= "FontString" then return nil end
    if S.pins[fs] then return S.pins[fs] end
    local rec = { px = px }
    S.pins[fs] = rec
    local r, g, b = Try(fs.GetTextColor, fs)
    r, g, b = Plain(r), Plain(g), Plain(b)
    rec.color = pick(type(r) == "number" and r or 1, type(g) == "number" and g or 1, type(b) == "number" and b or 1)
    Kit.RestyleLabel(fs, host, px, rec.color)
    local busy = false
    Kit.HookFunc(fs, "SetTextColor", function(_, nr, ng, nb)
        if busy then return end
        nr, ng, nb = Plain(nr), Plain(ng), Plain(nb)
        if type(nr) ~= "number" or type(ng) ~= "number" or type(nb) ~= "number" then return end
        local c = pick(nr, ng, nb)
        rec.color = c
        if nr ~= c[1] or ng ~= c[2] or nb ~= c[3] then
            busy = true
            pcall(fs.SetTextColor, fs, c[1], c[2], c[3], 1)
            busy = false
        end
    end)
    Kit.HookFunc(fs, "SetFontObject", function()
        if busy then return end
        busy = true
        Kit.RestyleLabel(fs, host, rec.px, rec.color)
        busy = false
    end)
    return rec
end

local function Const(color) return function() return color end end

-- A chevron of 2 px cells centred in `host`: dir "l", "r", "u" or "d", `n` cells across (odd). rec.cells are the textures,
-- rec.Paint(color, alpha) tints them, rec.SetShown(bool) shows or hides them all.
local function Chevron(host, dir, n, thick, step)
    thick, step = thick or 2, step or 2
    local half = (n - 1) / 2
    local horizontal = dir == "l" or dir == "r"
    local gw, gh = half * step + thick, n * thick
    if not horizontal then gw, gh = gh, gw end
    local hw, hh = Kit.SizePx(host)
    local ox, oy = math.floor(((hw or gw) - gw) / 2), math.floor(((hh or gh) - gh) / 2)
    local rec = { cells = {} }
    for i = 0, n - 1 do
        local d = math.abs(i - half)
        local x, y
        if horizontal then
            x, y = (dir == "l") and d * step or (half - d) * step, i * thick
        else
            x, y = i * thick, (dir == "u") and d * step or (half - d) * step
        end
        rec.cells[#rec.cells + 1] = Kit.Rect(host, ox + x, oy + y, thick, thick, C.violet, 1, "OVERLAY", 7)
    end
    function rec.Paint(c, a)
        for _, t in ipairs(rec.cells) do t:SetColorTexture(c[1], c[2], c[3], a or 1) end
    end
    function rec.SetShown(shown)
        for _, t in ipairs(rec.cells) do t:SetShown(shown) end
    end
    return rec
end

-- A dialog that has chrome of the stock kind only (a DialogBorderTemplate frame): its nine slice frame, background and art held, our
-- panel fill, glow and ring drawn over it and a 3 px LED edge down the left side (cyan asks).
local function Dialog(frame, accent)
    if type(frame) ~= "table" or S.dialogs[frame] or type(frame.CreateTexture) ~= "function" then return false end
    S.dialogs[frame] = true
    G.HoldInset(frame)
    Theme.AddPanelChrome(frame, { accent = accent or C.violet, fillColor = Theme.COLOR_BG, glowAlpha = 0.35 })
    G.Bar(frame, accent or C.cyan, 3, 9, 3)
    return true
end

-------------------------------------------------------------------------------
-- The addon list
-------------------------------------------------------------------------------

-- The title colours Blizzard writes: gold for a loadable addon, red for one that failed to load, gray for a disabled one.
local function TitlePick(r, g, b)
    if r > 0.9 and g < 0.3 then return C.pink end
    if math.abs(r - g) < 0.06 and r < 0.7 then return DIS end
    return C.text
end

local function PaintAddonRow(row)
    local rec = S.rows[row]
    if not rec then return end
    local hover = rec.state and (rec.state.hover or rec.state.pressed)
    Char.PaintBox(rec.box, C.violet, hover and 0.16 or 0, C.violet, 0, 1)
end

-- Enabled for some characters only (the gray check of the stock list): an amber bar over the lamp.
local function SyncAddonRow(row)
    local rec = S.rows[row]
    local enabled = row.Enabled
    if not rec or type(enabled) ~= "table" then return end
    local some = type(_G.Enum) == "table" and type(_G.Enum.AddOnEnableState) == "table" and _G.Enum.AddOnEnableState.Some
    rec.some:SetShown(some ~= nil and Plain(enabled.state) == some)
end

local function SkinAddonEntry(row)
    PanelSkins.SweepControls(row)
    PanelSkins.SweepTextButtons(row)
    if S.rows[row] then SyncAddonRow(row) return end
    HeldArt.HoldButton(row)
    local rec = { box = Char.Box(row, "BORDER") }
    S.rows[row] = rec
    G.Rule(row, C.dim, 0.45, -1, 0)
    -- on a frame of ours over the lamp: the shared check skin draws its box and mark on a child frame, which would cover a region
    local lamp = CreateFrame("Frame", nil, row.Enabled)
    lamp:SetAllPoints(row.Enabled)
    lamp:SetFrameLevel((Plain(Try(row.Enabled.GetFrameLevel, row.Enabled)) or 0) + 10)
    local w, h = Kit.SizePx(row.Enabled)
    rec.some = Kit.Rect(lamp, math.floor(((w or 24) - 10) / 2), math.floor(((h or 24) - 3) / 2), 10, 3, C.amber, 1, "OVERLAY", 4)
    Pin(row.Title, row, 12, TitlePick)
    Pin(row.Status, row, 11, Const(C.amber))
    Pin(row.Reload, row, 12, Const(C.pink))
    rec.state = Kit.Track(row, PaintAddonRow)
    PaintAddonRow(row)
    SyncAddonRow(row)
end

local function PaintAddonCategory(row)
    local rec = S.cats[row]
    if not rec then return end
    local node = row.CollapseExpand and row.CollapseExpand.treeNode
    local collapsed = type(node) == "table" and Plain(Try(node.IsCollapsed, node)) == true
    rec.open.SetShown(not collapsed)
    rec.closed.SetShown(collapsed)
    local hover = rec.state and (rec.state.hover or rec.state.pressed)
    local c = hover and C.cyan or C.muted
    rec.open.Paint(c)
    rec.closed.Paint(c)
end

local function SkinAddonCategory(row)
    if S.cats[row] then PaintAddonCategory(row) return end
    local cx = row.CollapseExpand
    HeldArt.HoldButton(row)
    HeldArt.HoldButton(cx)
    G.HoldKeys(cx, { "Normal", "Pushed", "Highlight" })
    local rec = { open = Chevron(cx, "d", 5), closed = Chevron(cx, "r", 5) }
    S.cats[row] = rec
    G.Rule(row, C.dim, 0.7, -1, 0)
    Pin(row.Title, row, 12, Const(C.cyan))
    rec.state = Kit.Track(row, PaintAddonCategory)
    Kit.HookFunc(cx, "UpdateState", function() PaintAddonCategory(row) end)
    Kit.HookFunc(cx, "SetTreeNode", function() PaintAddonCategory(row) end)
    PaintAddonCategory(row)
end

local function SkinAddonRow(row)
    if type(row) ~= "table" then return end
    if type(row.CollapseExpand) == "table" and type(row.Title) == "table" then
        SkinAddonCategory(row)
    elseif type(row.Enabled) == "table" and type(row.Title) == "table" then
        SkinAddonEntry(row)
    end
end

local function SkinAddonList(list)
    if type(list) ~= "table" or S.done.addons or type(list.CreateTexture) ~= "function" then return end
    S.done.addons = true
    list.fsSystemSkin = true
    local perf = list.Performance
    if type(perf) == "table" then
        G.HoldRegions(perf)
        Pin(perf.Header, perf, 11, Const(C.muted))
        for _, key in ipairs({ "Current", "Average", "Peak" }) do G.Mono(perf[key], perf, 11, C.text) end
        G.Rule(perf, C.dim, 1, -5, 0)
    end
    local force = list.ForceLoad
    if type(force) == "table" then
        for _, region in ipairs(List(force, "GetRegions")) do G.Mono(region, force, 11, C.muted) end
    end
    G.Rows(list.ScrollBox, function(row) Step("addon row", SkinAddonRow, row) end)
end

-- The dialog the addon list asks its questions in (a security warning, a missing dependency).
local function SkinAddonDialog(dialog)
    local bg = _G.AddonDialogBackground
    if type(dialog) ~= "table" or type(bg) ~= "table" or S.done.addonDialog then return end
    S.done.addonDialog = true
    dialog.fsSystemSkin = true
    Dialog(bg, C.violet)
    G.Mono(_G.AddonDialogText, bg, 13, C.text)
    PanelSkins.SweepOnShow(dialog)
end

-------------------------------------------------------------------------------
-- Quick Keybind
-------------------------------------------------------------------------------

local HEADER = { CUT = 5 }

local function SeatHeader(header)
    local rec = S.headers[header]
    if not rec then return end
    local w, h = Kit.SizePx(header)
    if not w then return end
    Kit.Place(rec.plate.fill, header, 0, 0, w, h)
    Kit.Place(rec.plate.ring, header, 0, 0, w, h)
    if rec.plate.ring2 then Kit.Place(rec.plate.ring2, header, 1, 1, w - 2, h - 2) end
end

-- The stock header (a metal tab that sits half over the dialog's top edge) becomes a cut tab with the title in cyan mono.
local function SkinHeader(header)
    if type(header) ~= "table" or S.headers[header] or type(header.CreateTexture) ~= "function" then return end
    G.HoldRegions(header)
    local w, h = Kit.SizePx(header)
    local rec = { plate = Kit.Plate(header, HEADER.CUT, w or 200, h or 39) }
    S.headers[header] = rec
    Kit.PaintPlate(rec.plate, C.ink, 1, C.cyan, 1, 1)
    Pin(header.Text, header, 12, Const(C.cyan))
    Kit.HookScript(header, "OnSizeChanged", function() SeatHeader(header) end)
    SeatHeader(header)
end

local function SkinQuickKeybind(frame)
    if type(frame) ~= "table" or S.done.quick or type(frame.CreateTexture) ~= "function" then return end
    S.done.quick = true
    frame.fsSystemSkin = true
    Kit.HoldFrame(frame.BG)
    Dialog(frame, C.cyan)
    SkinHeader(frame.Header)
    G.Mono(frame.InstructionText, frame, 12, C.text)
    G.Mono(frame.CancelDescriptionText, frame, 12, C.muted)
    G.Mono(frame.OutputText, frame, 12, C.amber)
    PanelSkins.SweepOnShow(frame)
end

-------------------------------------------------------------------------------
-- Help (the support browser)
-------------------------------------------------------------------------------

local CHIP = { W = 80, H = 20, CUT = 4, RIGHT = 52, TOP = 4 }
local CHIP_STATE = {
    connecting = { text = "connecting", color = C.amber },
    linked = { text = "linked", color = C.cyan },
    ["no signal"] = { text = "no signal", color = C.pink },
}

local function PaintChip(h)
    local state = CHIP_STATE[h.state] or CHIP_STATE.connecting
    h.chip.color = state.color
    h.chip.label:SetText(state.text)
    Kit.Recolor(h.chip.label, state.color)
    Kit.PaintPlate(h.chip.plate, C.ink, 1, state.color, 1, 1)
end

local function SeatHelp()
    local h = S.help
    if not h then return end
    local w, ht = Kit.SizePx(h.overlay)
    if not w then return end
    Kit.SeatReticle(h.brackets, 0, 0, w, ht, 2, 18)
end

local function SkinHelp(help)
    if type(help) ~= "table" or S.done.help or type(help.CreateTexture) ~= "function" then return end
    S.done.help = true
    help.fsHelpSkin = true
    if not help.fsPanelSkin then
        Theme.SkinPanel(help, { fillColor = Theme.COLOR_BG, borderColor = Theme.COLOR_BORDER, title = "help" })
        help.fsPanelSkin = true
    end
    local browser = help.Browser
    if type(browser) == "table" then G.HoldInset(browser.BrowserInset) end
    local h = { state = "connecting" }
    S.help = h
    -- a ring and cyan corner brackets over the page, in a frame of ours laid over the browser (the page is a real web view and
    -- cannot be restyled, so the monitor frame around it is what we own); the ring is edges only, never a fill over the page
    local overlay = CreateFrame("Frame", nil, help)
    if type(browser) == "table" then
        overlay:SetAllPoints(browser)
        if overlay.SetFrameStrata then pcall(overlay.SetFrameStrata, overlay, "HIGH") end
        overlay:SetFrameLevel((Plain(Try(browser.GetFrameLevel, browser)) or help:GetFrameLevel() or 0) + 5)
    else
        overlay:SetAllPoints(help)
    end
    h.overlay = overlay
    h.ring = Char.Box(overlay, "BORDER")
    Char.PaintBox(h.ring, C.ink, 0, C.dim, 1, 1)
    h.brackets = Kit.Reticle(overlay, "OVERLAY", 3)
    overlay:SetScript("OnSizeChanged", SeatHelp)
    Kit.OnReseat(SeatHelp)
    SeatHelp()
    -- the state chip, beside the title and clear of the close button
    local chip = CreateFrame("Frame", nil, help)
    chip:SetFrameLevel((help:GetFrameLevel() or 0) + 6)
    Kit.Place(chip, help, -CHIP.RIGHT, CHIP.TOP, CHIP.W, CHIP.H, "TOPRIGHT", "TOPRIGHT")
    h.chip = { frame = chip, plate = Kit.Plate(chip, CHIP.CUT, CHIP.W, CHIP.H) }
    h.chip.label = Kit.Label(chip, "", 11, C.amber, "OVERLAY")
    Kit.Place(h.chip.label, chip, CHIP.W / 2, CHIP.H / 2, nil, nil, "CENTER", "TOPLEFT")
    local loading = Plain(Try(help.GetInitialLoading, help))
    h.state = loading == false and "linked" or "connecting"
    PaintChip(h)
    Kit.HookFunc(help, "SetInitialLoading", function(_, now)
        now = Plain(now)
        if now == true then
            h.unavailable = false
            h.state = "connecting"
        elseif not h.unavailable then
            h.state = "linked"
        end
        PaintChip(h)
    end)
    for _, method in ipairs({ "ShowUnavailable", "OnError" }) do
        Kit.HookFunc(help, method, function()
            h.unavailable = true
            h.state = "no signal"
            PaintChip(h)
        end)
    end
end

-------------------------------------------------------------------------------
-- Drive
-------------------------------------------------------------------------------

local function Build()
    Step("addons", SkinAddonList, _G.AddonList)
    Step("addon dialog", SkinAddonDialog, _G.AddonDialog)
    Step("quick keybind", SkinQuickKeybind, _G.QuickKeybindFrame)
    Step("help", SkinHelp, _G.HelpFrame)
end

PanelSkins.RegisterInspect("System", { { name = "AddonList", guard = "fsSystemSkin" },
    { name = "AddonDialog", guard = "fsSystemSkin" }, { name = "QuickKeybindFrame", guard = "fsSystemSkin" },
    { name = "HelpFrame", guard = "fsHelpSkin" } })

PanelSkins.DeferCombat(Build)
PanelSkins.WatchAddonLoad(function() PanelSkins.DeferCombat(Build) end)
