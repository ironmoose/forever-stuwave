-- Forever STUwave: the shared style blocks for the frame Style tabs (Unit Frames, Party frames, Raid frames, Pet bar).
-- One table of sections (Bars.SECTIONS) is built by one function (Bars.BuildStyleTab) for every page: a row names its
-- setting by suffix (bars.<frame>.<suffix>, see FrameStyle.lua), its label, tip and range, and the frames it shows on, so
-- a frame page only says which frames it has. Rows hide by frame, never by copy; a section whose rows are all hidden for the
-- picked frame does not draw. The preview band at the top draws the picked frame with the real frame code
-- (FS.UnitFrames.NewPreview) or a page's own preview function (Bars.RegisterFrame), and follows every setting.
--
-- Pending the owner's review: every visual here follows the prototype (mockups/config-window-2026-11-25.html).

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local I = CW.I
local S = CW.Spec
local C = CW.C
local Config = FS.Config
local Style = FS.FrameStyle
if not Style then return end   -- without the frame style module there is nothing to set (the pages leave their Style tab empty)

local Bars = {}
FS.ConfigBars = Bars

-------------------------------------------------------------------------------
-- Frames: Bars.RegisterFrame{ key, label, preview = function(stage, key) -> { frame, Restyle } }
-------------------------------------------------------------------------------

Bars.frames = {}

function Bars.RegisterFrame(def)
    if type(def) ~= "table" or type(def.key) ~= "string" then return false end
    Bars.frames[def.key] = def
    return true
end

for _, key in ipairs({ "player", "target", "focus", "boss" }) do
    Bars.RegisterFrame({
        key = key, label = Style.LABELS[key],
        preview = function(stage)
            local unitFrames = FS.UnitFrames
            if not (unitFrames and unitFrames.NewPreview) then return nil end
            local f = unitFrames.NewPreview(stage, key)
            return { frame = f, Restyle = f.Restyle }
        end,
    })
end

Bars.RegisterFrame({
    key = "raid", label = "Raid",
    preview = function(stage)
        local raid = FS.RaidFrames
        if not (raid and raid.NewStylePreview) then return nil end
        return raid.NewStylePreview(stage)
    end,
})
Bars.RegisterFrame({
    key = "party", label = "Party",
    preview = function(stage)
        local party = FS.PartyFrames
        if not (party and party.NewStylePreview) then return nil end
        return party.NewStylePreview(stage)
    end,
})

local UNIT4 = { "player", "target", "focus", "boss" }
local ALL = { "player", "target", "focus", "boss", "party", "raid", "pet" }

local function Is(list, key)
    for _, v in ipairs(list) do if v == key then return true end end
    return false
end

-- Every frame except the ones named.
local function Except(...)
    local out, skip = {}, { ... }
    for _, key in ipairs(ALL) do
        if not Is(skip, key) then out[#out + 1] = key end
    end
    return out
end

-------------------------------------------------------------------------------
-- The rows. kind: slider (sl), toggle (sw), segmented (seg), dropdown (dd), swatch, note.
-- frames: the frames it shows on (all when nil). needs / nl: the switch it depends on (a suffix) and its label.
-- Ranges: lim = { unit4 = {min, max, step}, other = {...} } for sliders whose range differs by frame family.
-------------------------------------------------------------------------------

local FMT_TIP_UNAVAILABLE = "Percent and Num + % need the percent read this client does not offer here; the frame keeps the number."

local function FormatOptions(list, kind)
    local out = {}
    for _, item in ipairs(list) do
        local needsPercent = item[1] == "percent" or item[1] == "both"
        if not needsPercent or Style.PercentAvailable(kind) then out[#out + 1] = { value = item[1], text = item[2] } end
    end
    return out
end

local function OptionList(list)
    local out = {}
    for i, item in ipairs(list) do out[i] = { value = item[1], text = item[2] } end
    return out
end

local CORNERS = { { "topleft", "Top left" }, { "topright", "Top right" }, { "bottomleft", "Bottom left" }, { "bottomright", "Bottom right" } }

Bars.SECTIONS = {
    { title = "Frame", tip = "The whole frame. Height grows or shrinks the health bar; the data row and power bar keep their size.", rows = {
        { kind = "sl", suffix = "w", label = "Width", min = 60, max = 400, step = 2, unit = "px", combat = true,
          tip = "Every frame has its own width and height." },
        { kind = "sl", suffix = "fh", label = "Height", step = 1, unit = "px", combat = true, derived = true },
        { kind = "sl", suffix = "alpha", label = "Opacity", min = 10, max = 100, step = 5, unit = "%",
          tip = "The whole frame: background, bars and text." },
        { kind = "sl", suffix = "bgAlpha", label = "Background opacity", min = 0, max = 100, step = 5, unit = "%",
          tip = "Only the dark fill behind the bars. 0 shows the bars and text with nothing behind them." },
        { kind = "sw", suffix = "glow", label = "Border glow", frames = Except("raid"), tip = "The soft violet glow around the frame." },
        { kind = "sl", suffix = "glowAmt", label = "Glow strength", frames = Except("raid"), min = 10, max = 100 + 100, step = 10,
          unit = "%", sub = true, needs = "glow", nl = "Border glow" },
    } },
    { title = "Health bar", rows = {
        { kind = "dd", suffix = "hpStyle", label = "Bar style", frames = Except("raid"), looks = true,
          tip = "The bar looks STUwave already draws elsewhere: cut corner (player and target today), laser rail (party today), flat, LED segments (mana regen and quest timer), slant cells (XP bar), chevron (cast bars) and Blizzard's stock bar." },
        { kind = "seg", suffix = "raidLook", label = "Look", frames = { "raid" }, options = { { "auto", "Auto" }, { "boxes", "Mini boxes" }, { "tiles", "Tiles" } },
          tip = "Auto is today: mini boxes with a health rail at 10 players or fewer, tiles that fill from the bottom in a bigger raid. The Raid layout picker above the preview shows each." },
        { kind = "seg", suffix = "raidFmt", label = "Text", frames = { "raid" }, options = Style.RAID_TEXT_FORMATS,
          tip = "Low only shows the percent in red at 35% health or less, as today." },
        { kind = "sl", suffix = "hpH", label = "Height", min = 2, max = 60, step = 1, unit = "px", tip = "Changes the frame height with it." },
        { kind = "seg", suffix = "hpFmt", label = "Text", frames = Except("raid"), formats = "text", kind2 = "health" },
        { kind = "sl", suffix = "hpTs", label = "Text size", lim = { unit4 = { 6, 20, 0.5 }, other = { 5, 20, 0.5 } }, unit = "px", sub = true },
        { kind = "seg", suffix = "hpTa", label = "Text position", frames = Except("raid"), options = Style.TEXT_POSITIONS, sub = true,
          tip = "Where the text sits on the bar. Offset then nudges it left or right." },
        { kind = "sl", suffix = "hpTx", label = "Text offset", min = -60, max = 60, step = 1, unit = "px", sub = true,
          tip = "Below 0 moves the text left, above 0 moves it right." },
    } },
    { title = "Power bar", rows = {
        { kind = "dd", suffix = "mpStyle", label = "Bar style", frames = Except("raid"), looks = true, tip = "Its own pick, so the power bar can differ from the health bar." },
        { kind = "sl", suffix = "mpH", label = "Height", min = 0, max = 40, step = 1, unit = "px",
          tip = "0 hides the power bar. Changes the frame height with it." },
        { kind = "seg", suffix = "mpFmt", label = "Text", frames = Except("raid"), formats = "text", kind2 = "power" },
        { kind = "sl", suffix = "mpTs", label = "Text size", frames = Except("raid"), lim = { unit4 = { 6, 20, 0.5 }, other = { 5, 20, 0.5 } }, unit = "px", sub = true },
        { kind = "seg", suffix = "mpTa", label = "Text position", frames = Except("raid"), options = Style.TEXT_POSITIONS, sub = true,
          tip = "Where the text sits on the bar. Offset then nudges it left or right." },
        { kind = "sl", suffix = "mpTx", label = "Text offset", frames = Except("raid"), min = -60, max = 60, step = 1, unit = "px", sub = true,
          tip = "Below 0 moves the text left, above 0 moves it right." },
    } },
    { title = "Data", rows = {
        { kind = "sw", suffix = "name", label = "Show name", tip = "Off leaves only the bars, for small frames." },
        { kind = "sl", suffix = "nameSize", label = "Name size", lim = { unit4 = { 10, 20, 1 }, other = { 6, 20, 0.5 } }, unit = "px",
          needs = "name", nl = "Show name", tip = "The name text. The data row grows with the biggest part on it." },
        { kind = "sl", suffix = "nameX", label = "Name offset", min = -60, max = 60, step = 1, unit = "px", sub = true, needs = "name",
          nl = "Show name", tip = "Below 0 moves it left, above 0 moves it right." },
        { kind = "sw", suffix = "classIcon", label = "Class icon", frames = Except("raid", "pet"),
          tip = "Always on your own frame and on other players. Creatures never show one." },
        { kind = "sl", suffix = "iconSize", label = "Icon size", frames = Except("raid", "pet"), min = 12, max = 28, step = 1, unit = "px",
          sub = true, needs = "classIcon", nl = "Class icon" },
        { kind = "sl", suffix = "iconX", label = "Icon offset", frames = Except("raid", "pet"), min = -60, max = 60, step = 1, unit = "px",
          sub = true, needs = "classIcon", nl = "Class icon", tip = "Below 0 moves it left, above 0 moves it right." },
        { kind = "sw", suffix = "level", label = "Level", frames = Except("raid") },
        { kind = "sl", suffix = "levelSize", label = "Level size", frames = Except("raid"), lim = { unit4 = { 8, 14, 1 }, other = { 6, 14, 0.5 } },
          unit = "px", sub = true, needs = "level", nl = "Level" },
        { kind = "sl", suffix = "levelX", label = "Level offset", frames = Except("raid"), min = -60, max = 60, step = 1, unit = "px", sub = true,
          needs = "level", nl = "Level", tip = "Below 0 moves it left, above 0 moves it right." },
        { kind = "sw", suffix = "role", label = "Role tag", frames = { "party", "raid" }, tip = "The T, H or D tag after the class tile. Hidden when no role is set." },
        { kind = "sw", suffix = "lowTag", label = "LOW tag", frames = { "party" }, tip = "A red LOW tag on the name row at 35% health or less." },
        { kind = "sw", suffix = "raidMark", label = "Raid marker", frames = Except("raid", "pet"), tip = "The skull, star and the rest, when someone marks the unit." },
        { kind = "sl", suffix = "markX", label = "Marker offset", frames = Except("raid", "pet"), min = -60, max = 60, step = 1, unit = "px", sub = true,
          needs = "raidMark", nl = "Raid marker", tip = "Below 0 moves it left, above 0 moves it right." },
        { kind = "sw", suffix = "resting", label = "Resting icon", frames = { "player" }, tip = "The Zzz on your class icon in an inn or a city." },
    } },
    { title = "Extras", tip = "Small parts a frame can wear. Each is off until you turn it on.", rows = {
        { kind = "sw", suffix = "elite", label = "Elite and rare mark", frames = { "target", "focus", "boss" },
          tip = "The gold elite or silver rare level icon the Gunsight target box already draws, on the level chip." },
        { kind = "sw", suffix = "tot", label = "Target of target", frames = { "target", "focus", "boss" },
          tip = "A line under the frame with who this unit is targeting. The Gunsight target box already reads it." },
        { kind = "sw", suffix = "combat", label = "Combat icon", frames = { "player" },
          tip = "Crossed swords on the name row while you are in combat." },
        { kind = "sw", suffix = "pet", label = "Pet slot", frames = { "party" },
          tip = "The narrow slot beside each row with that member's pet health. Dashed and empty when they have no pet." },
        { kind = "sw", suffix = "portrait", label = "Portrait", frames = { "player", "target", "focus", "party", "boss" },
          tip = "A face portrait in the class icon spot, at the icon size. Creatures get one too." },
        { kind = "sw", suffix = "cast", label = "Cast bar on the frame", frames = { "target", "focus", "boss" },
          tip = "A thin cast bar under the frame with the spell name. Needs a quick check in game first: other units' cast times may be hidden from addons." },
        { kind = "sw", suffix = "pvp", label = "PvP flag", frames = { "player", "target", "focus", "party" },
          tip = "A small PVP tag on the name row when the unit is flagged." },
        { kind = "sw", suffix = "leader", label = "Group leader crown", frames = { "player", "party" },
          tip = "A small crown on the leader of your group." },
    } },
    { title = "Aggro", tip = "Who a mob is attacking, and how close you are to pulling it. Read live in combat: on this client the threat numbers are not hidden from addons.", rows = {
        { kind = "sw", suffix = "threat", label = "Aggro status", frames = Except("pet"),
          tip = "Target, focus and boss: the border goes orange as you near the top of that mob's threat, pink when it turns to you. Player: pink while any mob is on you. Party and raid: pink on whoever a mob is attacking." },
        { kind = "swatch", label = "Colours", frames = Except("pet"), sub = true, needs = "threat", nl = "Aggro status",
          colors = { { { 1, 0.7137, 0.2824 }, "close" }, { { 1, 0.180, 0.592 }, "has aggro" } } },
        { kind = "sw", suffix = "threatPct", label = "Aggro %", frames = Except("pet", "player"), sub = true, needs = "threat", nl = "Aggro status",
          tip = "Share of the mob's threat, 100 means it is on them. Target, focus and boss: yours on that mob. Party and raid: each member's on your target." },
        { kind = "sl", suffix = "threatX", label = "Aggro % offset", frames = Except("pet", "player"), min = -60, max = 60, step = 1, unit = "px",
          sub = true, needs = "threatPct", nl = "Aggro %", tip = "Below 0 moves it left, above 0 moves it right." },
    } },
}

-- What a frame's rows already change on the live frame. Unit frames apply every row; the party, raid and pet frames list
-- theirs, and the rest show greyed with a reason instead of doing nothing silently.
Bars.WIRED = {
    raid = { w = true, alpha = true, nameSize = true, role = true, raidLook = true },
    party = { alpha = true },
    pet = {},
}
local NOT_WIRED = "This setting is not applied to this frame yet."
function Bars.IsWired(frame, suffix)
    local set = Bars.WIRED[frame]
    return set == nil or set[suffix] == true
end

-------------------------------------------------------------------------------
-- Row building
-------------------------------------------------------------------------------

local function RowShown(row, frame)
    return row.frames == nil or Is(row.frames, frame)
end

local function SectionShown(sec, frame)
    for _, row in ipairs(sec.rows) do
        if RowShown(row, frame) then return true end
    end
    return false
end

local function Family(frame)
    return Is(UNIT4, frame) and "unit4" or "other"
end

local function Limits(row, frame)
    if row.lim then
        local lim = row.lim[Family(frame)]
        return lim[1], lim[2], lim[3]
    end
    if row.derived then
        local lo, hi = Style.HeightRange(frame)
        return lo, hi, row.step
    end
    return row.min, row.max, row.step
end

local function UnitFormat(row)
    if row.unit == "%" then return "%s%%" end
    if row.unit then return "%s " .. row.unit end
    return "%s"
end

-- Builds one row of a section for the page described by ctx (ctx.frame() is the picked frame key).
local function BuildRow(content, row, ctx)
    local suffix = row.suffix
    local function frame() return ctx.frame() end
    local entry = {
        label = row.label, tip = row.tip, sub = row.sub, regKey = suffix and ("bars." .. suffix) or nil,
        when = function() return RowShown(row, frame()) end,
        isChanged = function() return Style.IsStored(frame(), row.derived and "hpH" or suffix) end,
        reset = function() Style.Reset(frame(), row.derived and "hpH" or suffix) end,
    }
    if row.needs or Bars.WIRED[ctx.firstFrame] ~= nil or ctx.firstFrame ~= frame() then
        local needsReason = row.needs and ("Requires |cffffffff" .. (row.nl or row.needs) .. "|r to be on.") or nil
        entry.enabled = function()
            if row.suffix and not Bars.IsWired(frame(), row.suffix) and not row.derived then entry.reason = NOT_WIRED; return false end
            if row.needs and Style.Get(frame(), row.needs) ~= true then entry.reason = needsReason; return false end
            return true
        end
        entry.reason = needsReason or NOT_WIRED
    end
    if row.derived then
        entry.get = function() return Style.FrameHeight(frame()) end
        entry.set = function(value) return Style.SetFrameHeight(frame(), value) end
    else
        entry.get = function() return Style.Get(frame(), suffix) end
        entry.set = function(value) return Style.Set(frame(), suffix, value) end
    end

    if row.kind == "swatch" then
        return UI.Swatch(content, { label = row.label, sub = row.sub, colors = row.colors, tip = row.tip,
            when = entry.when, enabled = entry.enabled, reason = entry.reason })
    end
    local built
    if row.kind == "sw" then
        built = UI.Toggle(content, entry)
    elseif row.kind == "sl" then
        local lo, hi, step = Limits(row, ctx.firstFrame)
        entry.min, entry.max, entry.step, entry.fmt = lo, hi, step, UnitFormat(row)
        built = UI.Slider(content, entry)
    elseif row.kind == "seg" then
        if row.formats then
            entry.options = FormatOptions(Style.TEXT_FORMATS, row.kind2)
            if not Style.PercentAvailable(row.kind2) then
                entry.tip = (row.tip and (row.tip .. "\n") or "") .. FMT_TIP_UNAVAILABLE
            end
        else
            entry.options = OptionList(row.options)
        end
        built = UI.Segmented(content, entry)
    elseif row.kind == "dd" then
        entry.items = function() return Bars.LookItems(frame(), suffix) end
        entry.text = function(value) return Bars.LookLabel(value) end
        built = UI.Dropdown(content, entry)
    end
    if built and row.combat and built.fsEntry then
        -- a secure size waits out combat: the tip says so while it is true
        local record = built.fsEntry
        local base = record.opts.tip
        I.TrackState(function()
            local inCombat = type(InCombatLockdown) == "function" and InCombatLockdown()
            record.opts.tip = (base and (base .. "\n") or "") .. "Applies after combat." .. ""
            if not inCombat then record.opts.tip = base end
            if record.opts.tip then
                if not built.fsHelp then
                    built.fsHelp = UI.HelpIcon(built, "")
                    built.fsHelp:SetPoint("LEFT", built.fsLabel, "RIGHT", S.Q_GAP, 0)
                end
                I.RefreshTip(built)
            end
        end)
    end
    return built
end

local function LookName(value)
    for _, item in ipairs(Style.BAR_STYLES) do
        if item[1] == value then return item[2] end
    end
    return tostring(value)
end
Bars.LookLabel = LookName

-- The looks a frame's bar offers: every look whose builder exists (FrameHelpers.CreateBarLook, ticket C1d).
function Bars.LookItems(frame, _)
    local out = {}
    for _, item in ipairs(Style.BAR_STYLES) do
        if Style.LookAvailable(item[1], frame) then out[#out + 1] = { value = item[1], text = item[2] } end
    end
    return out
end

-- Section builders other lanes' tickets add after the shared ones (extras, aggro, markers, alert tray): each is
-- { title, tip, rows } like SECTIONS, appended in order.
function Bars.AddSection(sec)
    Bars.SECTIONS[#Bars.SECTIONS + 1] = sec
end

-------------------------------------------------------------------------------
-- The preview band
-------------------------------------------------------------------------------

local BAND_H = 168       -- header row plus the stage
local HEAD_H = 28
local STAGE_PAD = 12

local function PickerButton(parent, label)
    local b = I.MakeButton(parent, { height = S.SEG_H, ring = C.line, textColor = C.muted, chamfer = 4, size = S.TEXT, glow = 0, text = label })
    b:SetWidth(S.Snap(b.fsLabel:GetStringWidth() + 2 * S.SEG_PAD_X))
    return b
end
Bars.PickerButton = PickerButton

-- Paints a picker button as picked or not.
function Bars.MarkPicker(b, selected)
    b.fsSelected = selected
    if selected then
        I.Restyle(b, C.cyan, C.cyan, I.Mix(C.ink, C.cyan, 0.2), 0.5)
    else
        I.Restyle(b, C.line, C.muted, C.ink, 0)
    end
end

-- hover: the row the pointer is on turns its feature on in the preview for the moment
local active = nil     -- the preview of the tab on screen: { page, tab, redraw = fn(override) }

CW.On("rowEnter", function(entry)
    if not (active and entry.page == active.page and entry.tab == active.tab) then return end
    local suffix = type(entry.key) == "string" and entry.key:match("^bars%.(.+)$")
    if suffix and entry.kind == "switch" then active.redraw({ suffix = suffix, value = true }) end
end)
CW.On("rowLeave", function(entry)
    if active and entry.page == active.page and entry.tab == active.tab then active.redraw(nil) end
end)

-- spec: { page, tab, frames = { keys }, header = function(band, ctx) }
-- Builds the preview band, then every section of Bars.SECTIONS for the frames of the page.
function Bars.BuildStyleTab(content, spec)
    local frames = spec.frames
    local ctx = { firstFrame = frames[1], page = spec.page, tab = spec.tab }
    function ctx.frame()
        if #frames == 1 then return frames[1] end
        local picked = Config.Get("bars.module")
        if Is(frames, picked) then return picked end
        return frames[1]
    end

    local band = UI.Band(content, BAND_H)
    local stage
    local previews = {}
    local picker = {}
    if band then
        local title = I.Label(band, "PREVIEW", S.TEXT, C.violet)
        title:SetPoint("TOPLEFT", band, "TOPLEFT", 0, -6)
        local help = UI.HelpIcon(band, spec.previewTip or "The frame as it is drawn with the settings below. Pointing at a setting turns that feature on here for a moment.")
        help:SetPoint("LEFT", title, "RIGHT", S.Q_GAP, 0)
        if #frames > 1 then
            local prev
            for _, key in ipairs(frames) do
                local b = PickerButton(band, Style.LABELS[key])
                if prev then b:SetPoint("LEFT", prev, "RIGHT", S.SEG_GAP, 0) else b:SetPoint("LEFT", help, "RIGHT", S.CTL_GAP * 2, 0) end
                b:SetScript("OnClick", function()
                    Config.Set("bars.module", key)
                    CW.RefreshAll()
                end)
                picker[key] = b
                prev = b
            end
        end
        if spec.header then spec.header(band, ctx, title, help) end
        stage = CreateFrame("Frame", nil, band)
        stage:SetPoint("TOPLEFT", band, "TOPLEFT", 0, -HEAD_H)
        stage:SetPoint("BOTTOMRIGHT", band, "BOTTOMRIGHT", 0, 0)
    end

    local override = nil
    local function Redraw(with)
        override = with
        if not stage then return end
        local key = ctx.frame()
        local def = Bars.frames[key]
        if not previews[key] and def and def.preview then
            previews[key] = def.preview(stage, key) or false
        end
        for other, p in pairs(previews) do
            if p and other ~= key then p.frame:Hide() end
        end
        local p = previews[key]
        if not p then return end
        Style.override = override and { frame = key, suffix = override.suffix, value = override.value } or nil
        local ok, err = pcall(p.Restyle)
        Style.override = nil
        if not ok then I.Forward(err) end
        local w, h = p.frame:GetWidth(), p.frame:GetHeight()
        local room = BAND_H - HEAD_H - 2 * STAGE_PAD
        local scale = (h and h > room) and (room / h) or 1
        p.frame:SetScale(scale)
        p.frame:ClearAllPoints()
        p.frame:SetPoint("CENTER", stage, "CENTER", 0, 0)
        p.frame:Show()
    end
    if band then
        active = { page = spec.page, tab = spec.tab, redraw = Redraw }
        CW.On("select", function(page, tab)
            if page == spec.page and tab == spec.tab then active = { page = spec.page, tab = spec.tab, redraw = Redraw } end
        end)
        I.Track(function()
            local key = ctx.frame()
            for k, b in pairs(picker) do
                local selected = k == key
                b.fsSelected = selected
                if selected then
                    I.Restyle(b, C.cyan, C.cyan, I.Mix(C.ink, C.cyan, 0.2), 0.5)
                else
                    I.Restyle(b, C.line, C.muted, C.ink, 0)
                end
            end
            Redraw(override)
        end)
    end

    if spec.before then spec.before(content, ctx) end
    for _, sec in ipairs(Bars.SECTIONS) do
        UI.Section(content, {
            title = sec.title, tip = sec.tip,
            when = function() return SectionShown(sec, ctx.frame()) end,
        })
        for _, row in ipairs(sec.rows) do
            BuildRow(content, row, ctx)
        end
    end
    return ctx
end
