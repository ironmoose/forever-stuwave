-- Forever STUwave: Config page, Help
-- Getting started: the commands. Class modules: the module pictures. A row of class tabs (opens on the player's own class), a
-- second row for the Druid forms and Mage specs, then the module's picture with numbered pins and the numbered lines.
-- Pictures, pins, words and the layout come from HelpModules.lua; the art is help_pictures.tga (HelpPicturesArt.lua
-- says where).

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local I = CW.I
local S = CW.Spec
local D = CW.D
local C = CW.C
local Theme = FS.Theme

local Label, Outline, Mix = I.Label, I.Outline, I.Mix
local MakeButton, Restyle, HoverStyle, Track = I.MakeButton, I.Restyle, I.HoverStyle, I.Track
local Capitalize = I.Capitalize
local HelpModules = FS.HelpModules

-- The Help page: the commands, then the class modules. A row of class tabs (opens on the player's own class), a second row
-- for the Druid forms and Mage specs, then the module's picture with numbered pins and the numbered lines. Pictures, pins,
-- words and the layout come from HelpModules.lua; the art is help_pictures.tga (HelpPicturesArt.lua says where).
local HELP_TEX = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local HELP_TAB_H, HELP_SUB_H, HELP_GAP = 24, 20, 10

local function HelpClassName(token)
    return (LOCALIZED_CLASS_NAMES_MALE and LOCALIZED_CLASS_NAMES_MALE[token]) or Capitalize(token:lower())
end

local function PictureSize(name)
    local r = FS.HelpPicturesArt and FS.HelpPicturesArt.rects[name]
    if r then return r[3], r[4] end
    return 0, 0
end

local function HelpPicture(parent, name, x, y, scale)
    local art = FS.HelpPicturesArt
    local r = art and art.rects[name]
    local t = parent:CreateTexture(nil, "ARTWORK")
    if not r then return t end
    t:SetTexture(HELP_TEX .. art.file, "CLAMP", "CLAMP", "NEAREST")
    t:SetTexCoord(r[1] / art.width, (r[1] + r[3]) / art.width, r[2] / art.height, (r[2] + r[4]) / art.height)
    t:SetSize(r[3] * scale, r[4] * scale)
    t:SetPoint("TOPLEFT", parent, "TOPLEFT", x, -y)
    return t
end

local function HelpRect(parent, x, y, w, h, color, layer)
    local t = parent:CreateTexture(nil, layer or "OVERLAY")
    t:SetColorTexture(color[1], color[2], color[3], color[4] or 1)
    t:SetSize(w, h)
    t:SetPoint("TOPLEFT", parent, "TOPLEFT", x, -y)
    return t
end

-- A pink square with the line number in ink; `dashed` draws only a muted outline (a part with no picture).
local function HelpBadge(parent, n, x, y, dashed)
    local size = HelpModules.PIN
    local holder = CreateFrame("Frame", nil, parent)
    holder:SetSize(size, size)
    holder:SetPoint("TOPLEFT", parent, "TOPLEFT", x, -y)
    if dashed then
        Outline(holder, C.muted, 1)
    else
        HelpRect(holder, 0, 0, size, size, C.pink, "ARTWORK")
    end
    local fs = Label(holder, tostring(n), 11, dashed and C.muted or C.ink)
    fs:SetPoint("CENTER", holder, "CENTER", 0, 0)
    holder.fsNumber = fs
    return holder
end

-- One page (a class, or one form or spec): the picture block, then the numbered lines. Returns the frame and its height.
local function BuildHelpModulePage(parent, page)
    local f = CreateFrame("Frame", nil, parent)
    f:SetWidth(D.CONTENT_W)
    local L = HelpModules.Layout(page, D.CONTENT_W, PictureSize)
    local bx, by, bw, bh = L.box[1], L.box[2], L.box[3], L.box[4]
    local box = CreateFrame("Frame", nil, f)
    box:SetSize(bw, bh)
    box:SetPoint("TOPLEFT", f, "TOPLEFT", bx, -by)
    -- The fill goes on the page, under the picture and arrows: the box is a child frame, so anything it draws covers
    -- the page's own textures. The box keeps only its outline.
    HelpRect(f, bx, by, bw, bh, C.track, "BACKGROUND")
    Outline(box, C.line, 1)
    f.fsPicture = HelpPicture(f, L.picture[1], L.picture[2], L.picture[3], HelpModules.SCALE)
    f.fsArrows = {}
    for _, r in ipairs(L.arrows) do f.fsArrows[#f.fsArrows + 1] = HelpRect(f, r[1], r[2], r[3], r[4], C.cyan) end
    f.fsPins = {}
    for _, p in ipairs(L.pins) do f.fsPins[#f.fsPins + 1] = HelpBadge(f, p[1], p[2], p[3]) end
    if L.caption then
        local cap = Label(f, "OTHER STATES", 9, C.muted)
        cap:SetPoint("TOPLEFT", f, "TOPLEFT", 0, -(L.caption + 4))
    end
    for _, e in ipairs(L.extras) do
        local n, name, x, y, w, h = e[1], e[2], e[3], e[4], e[5], e[6]
        local holder = CreateFrame("Frame", nil, f)
        holder:SetSize(w, h)
        holder:SetPoint("TOPLEFT", f, "TOPLEFT", x, -y)
        HelpPicture(holder, name, 0, 0, 1)
        Outline(holder, C.line, 1)
        HelpBadge(holder, n, 0, 0)
    end
    local shown = {}
    for _, p in ipairs(page.pins or {}) do shown[p[1]] = true end
    for _, e in ipairs(page.extras or {}) do shown[e.n] = true end
    local y = L.h + HELP_GAP
    local textW = D.CONTENT_W - HelpModules.PIN - 8
    local function line(text, color, badge, dashed)
        local fs = Label(f, text, 11, color)
        fs:SetWidth(textW)
        fs:SetJustifyH("LEFT")
        fs:SetJustifyV("TOP")
        fs:SetSpacing(3)
        fs:SetPoint("TOPLEFT", f, "TOPLEFT", HelpModules.PIN + 8, -(y + 3))
        if badge then HelpBadge(f, badge, 0, y, dashed) end
        y = y + math.max(HelpModules.PIN, math.ceil(fs:GetStringHeight() or 0) + 4) + 6
        return fs
    end
    for n, ln in ipairs(page.lines) do
        line("|cffff2e97" .. ln[1] .. ":|r " .. ln[2], C.text, n, not shown[n])
    end
    if page.note then line(page.note, C.muted) end
    f:SetHeight(y)
    return f, y
end

-- A tab row: one MakeButton per item, `widths` given, the selected one pink.
local function HelpTabs(parent, items, height, size, onPick)
    local row = CreateFrame("Frame", nil, parent)
    row:SetSize(D.CONTENT_W, height)
    row.fsButtons = {}
    local x = 0
    for i, it in ipairs(items) do
        local b = MakeButton(row, { width = it.width, height = height, ring = C.line, text = it.text, size = size, textColor = C.muted })
        b:SetPoint("TOPLEFT", row, "TOPLEFT", x, 0)
        b.fsValue = it.value
        HoverStyle(b, C.cyan)
        b:SetScript("OnClick", function() onPick(it.value) end)
        row.fsButtons[i] = b
        x = x + it.width + 3
    end
    function row.Mark(value)
        for _, b in ipairs(row.fsButtons) do
            local on = b.fsValue == value
            b.fsSelected = on
            if on then Restyle(b, C.pink, C.text, Mix(C.ink, C.pink, 0.22), 0.5) else Restyle(b, C.line, C.muted, C.ink, 0) end
        end
    end
    return row
end

-- The page the player most likely needs: a Druid in bear or cat form sees that form.
local function OwnPageIndex(token)
    if token == "DRUID" and type(GetShapeshiftFormID) == "function" then
        local form = GetShapeshiftFormID()
        if form == 5 or form == 8 then return 2 end
        if form == 1 then return 3 end
    end
    return 1
end

-- The class modules block. Like UI.Text it must be the last row on its page: it resizes with the class shown.
function UI.HelpModules(content)
    local block = CreateFrame("Frame", nil, content)
    block:SetHeight(HELP_TAB_H)
    block.fsOnResize = function() block:SetWidth(D.CONTENT_W) end
    UI.Stack(content, block)
    local own
    if type(UnitClass) == "function" then own = select(2, UnitClass("player")) end
    local state = { token = HelpModules.CLASSES[own or ""] and own or HelpModules.ORDER[1] }
    state.page = state.token == own and OwnPageIndex(own) or 1
    local built, subRows = {}, {}
    local render
    local n = #HelpModules.ORDER
    local tabW = math.floor((D.CONTENT_W - 3 * (n - 1)) / n)
    local items = {}
    for i, token in ipairs(HelpModules.ORDER) do items[i] = { value = token, text = HelpClassName(token), width = tabW } end
    local tabs = HelpTabs(block, items, HELP_TAB_H, 10, function(token)
        if token ~= state.token then state.token, state.page = token, 1 end
        render()
    end)
    tabs:SetPoint("TOPLEFT", block, "TOPLEFT", 0, 0)
    block.fsTabs = tabs
    local rule = HelpRect(block, 0, HELP_TAB_H, D.CONTENT_W, 1, C.pink, "ARTWORK")
    block.fsRule = rule
    render = function()
        tabs.Mark(state.token)
        local pages = HelpModules.CLASSES[state.token].pages
        local y = HELP_TAB_H + 1 + HELP_GAP
        for token, sub in pairs(subRows) do sub:SetShown(token == state.token) end
        if #pages > 1 then
            local sub = subRows[state.token]
            if not sub then
                local list = {}
                for i, page in ipairs(pages) do list[i] = { value = i, text = page.label, width = #page.label * 7 + 24 } end
                sub = HelpTabs(block, list, HELP_SUB_H, 10, function(i) state.page = i; render() end)
                sub:SetPoint("TOPLEFT", block, "TOPLEFT", 0, -y)
                subRows[state.token] = sub
            end
            sub:Show()
            sub.Mark(state.page)
            y = y + HELP_SUB_H + HELP_GAP
        end
        local key = state.token .. state.page
        for k, entry in pairs(built) do entry.frame:SetShown(k == key) end
        local entry = built[key]
        if not entry then
            local frame, h = BuildHelpModulePage(block, pages[state.page])
            entry = { frame = frame, h = h }
            built[key] = entry
        end
        entry.frame:ClearAllPoints()
        entry.frame:SetPoint("TOPLEFT", block, "TOPLEFT", 0, -y)
        entry.frame:Show()
        local h = y + entry.h
        block:SetHeight(h)
        CW.RefreshScroll()
    end
    block.fsState = state
    Track(render)
    return block
end

CW.RegisterCategory({
    key = "help", label = "Help", group = "GENERAL", order = 3,
    tabs = { { key = "h", label = "Help", build = function(content)
        UI.Section(content, { title = "Getting started" })
        UI.Info(content, { label = "/fsconfig", value = "this window, or the STU key on the minimap" })
        UI.Info(content, { label = "/fsedit", value = "move and resize frames" })
        UI.Info(content, { label = "/fsgun on | off", value = "the Gunsight HUD" })
        UI.Info(content, { label = "/fsbug", value = "saves a bug report to paste into a GitHub issue" })
        UI.Info(content, { label = "~ before a timer", value = "counted from your own cast" })
        UI.Section(content, { title = "Class modules" })
        if HelpModules and FS.HelpPicturesArt then UI.HelpModules(content) end
    end } },
})
