-- Forever STUwave: KICK style tags on the target box (outlines in the box's own tone: steel, pink while kickable, red for INTERRUPTED), the level on the top edge and health percent and target of target on the bottom edge, each with an FS.Config toggle.
-- The target of target tag is a SecureUnitButtonTemplate button that targets that unit on a click; in combat it only takes SetAlpha and text.
-- A second secure button, the target menu, covers the whole target box and opens the unit context menu (Invite, Inspect, Whisper...) on a right click.
-- Unit values go straight to SetFormattedText / SetText and are never compared, since they may be secret.

local _, FS = ...

local Gunsight = FS.Gunsight
if type(Gunsight) ~= "table" or type(Gunsight.OnReady) ~= "function" then return end

local GunsightTags = {}
FS.GunsightTags = GunsightTags

local Config = FS.Config
local ui = Gunsight.ui
local IsSecret = FS.IsSecret or function() return false end

-- Mockup tag() / tags() (gunsight-modules-concepts-v7): x and w are image px, dx from the target box's left edge.
-- RISE is how far the level tag's top stands above the box top, OVERLAP how far the bottom tags reach above the box bottom.
local C = {
    H = 15, CHAMFER = 5, FILL_A = 0.95, TEXT_SIZE = 11,
    LEVEL = { dx = 1, pad = 5, gap = 3, minW = 15, advance = 575 / 1024 },   -- no fixed width: pad, [icon, gap], digits, pad; advance is Mononoki's digit width in em
    -- The target of target plate is 89 wide: the target box grew 20 image px to the right (mockups/gunsight-target-wider-2026-10-09.html)
    -- and the plate with it, still 4 short of the box's right edge. It holds the ping reticle, then the name.
    HEALTH = { dx = 4, w = 32 }, TOT = { dx = 41, w = 89 },
    -- Reticle A (mockups/gunsight-tot-icon-2026-10-09.html): a 9 x 9 glyph at (x, y) inside the plate's left pad, then a gap, then the
    -- label, which takes the rest: 89 - 3 - 3 - 11 = 72 image px. Parts are { x, y, w, h } in the glyph box, image px: a ring (radius 2.5,
    -- stroke 1, so a 6 square from 1.5, a texture), four 1 px ticks and a 1 px centre dot (solid textures).
    RETICLE = {
        size = 9, gap = 2, x = 3, y = 3,
        ring = { 1.5, 1.5, 6, 6 },
        top = { 4, 0, 1, 2 }, bottom = { 4, 7, 1, 2 }, left = { 0, 4, 2, 1 }, right = { 7, 4, 2, 1 },
        dot = { 4, 4, 1, 1 },
    },
    RISE = 8, OVERLAP = 7,
    MIN_FONT = 6, TOT_PAD = 3,
    TOT_FLOOR = 8,   -- the target of target name shrinks no further than this (image px) before the first names shorten to initials
    FRAME_LEVEL = 6,   -- the level and health tags' frame level above the box: over the edge strokes (+1) and the bars (+1 to +3)
    -- Level icons by UnitClassification, square sizes in image px (tools/assets/generate_level_icons.py). tex and tint name
    -- Theme tokens; tint = false draws the texture untinted (rare elite has its gold and silver baked in). A world boss
    -- is the skull alone: the mockup draws no digits beside it. normal, trivial and minus are absent: no icon.
    ICONS = {
        elite = { tex = "LEVEL_CROWN_TEXTURE", size = 11, tint = "COLOR_GOLD" },
        rare = { tex = "LEVEL_STAR_TEXTURE", size = 10, tint = "COLOR_SILVER" },
        rareelite = { tex = "LEVEL_CROWN_STAR_TEXTURE", size = 14, tint = false },
        worldboss = { tex = "LEVEL_SKULL_TEXTURE", size = 11, tint = "COLOR_RED", bare = true },
    },
}
GunsightTags.C = C
local RETICLE_PARTS = { "ring", "top", "bottom", "left", "right", "dot" }

local KEY = "gunsight.tags."
local SETTINGS = {
    level = { key = KEY .. "level", default = true },
    health = { key = KEY .. "health", default = true },
    tot = { key = KEY .. "tot", default = true },
}
GunsightTags.SETTINGS = SETTINGS
for _, def in pairs(SETTINGS) do Config.RegisterDefault(def.key, def.default) end

local Tags = { colors = nil, box = nil, events = nil, pendingTot = false, pendingSeat = false, pendingMenu = false,
    levelState = "none", levelChars = 0, iconW = 0, iconH = 0, iconKind = nil }

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() == true
end

local function Logged(key, msg)
    if FS.LogDegradeOnce then FS.LogDegradeOnce(key, msg) end
end

local function Guard(fn, ...)
    local ok, err = pcall(fn, ...)
    if ok or Tags.warned then return end
    Tags.warned = true
    Logged("gunsighttags_update", "|cffff4488Forever STUwave|r: box tags update failed: " .. tostring(err))
end

local function FontSize()
    return math.max(C.MIN_FONT, math.floor(ui(C.TEXT_SIZE) + 0.5))
end

local function Setting(def)
    return Config.Get(def.key) == true
end

-- The KICK tag's look: a chamfered plate, an outline in the box's tone (see below) and one centred label. The tags straddle the box edge, so
-- the plate must mask the edge line behind the text (the mockup draws them after the box): a plain tag takes its own
-- frame level above everything the box holds, since sibling frames of equal level have no promised draw order.
-- The secure button is left at its holder's level (a protected frame's level is not ours to set in combat).
-- Thin pieces sit on the pixel grid so a 1 px tick or the ring is not smeared across two screen rows.
local function Crisp(tex)
    if tex.SetSnapToPixelGrid then pcall(tex.SetSnapToPixelGrid, tex, true) end
    if tex.SetTexelSnappingBias then pcall(tex.SetTexelSnappingBias, tex, 0) end
end

-- The reticle in one tone frame: plain textures in the frame's own colour, over the outline and under the label. They
-- carry no alpha or flag of their own, so the frame's alpha and visibility (the flag lists, the verdict) tint them with
-- the outline. SeatReticle sizes and seats them.
local function AddReticle(tone, color)
    local Theme = FS.Theme
    local parts = {}
    for _, name in ipairs(RETICLE_PARTS) do
        local part = tone:CreateTexture(nil, "ARTWORK")
        if name == "ring" then
            part:SetTexture(Theme.RETICLE_RING_TEXTURE)
            part:SetVertexColor(color[1], color[2], color[3], color[4] or 1)
        else
            part:SetColorTexture(color[1], color[2], color[3], color[4] or 1)
        end
        Crisp(part)
        parts[name] = part
    end
    tone.reticle = parts
end

-- Seats the reticle parts of every tone frame of the plate in the glyph's place (image px from the plate's top left).
local function SeatReticle(frame)
    local R, k = C.RETICLE, ui(1)
    for _, tone in pairs(frame.tones) do
        for _, name in ipairs(RETICLE_PARTS) do
            local part, rect = tone.reticle and tone.reticle[name], R[name]
            if part then
                part:ClearAllPoints()
                part:SetPoint("TOPLEFT", tone, "TOPLEFT", (R.x + rect[1]) * k, -(R.y + rect[2]) * k)
                part:SetSize(rect[3] * k, rect[4] * k)
            end
        end
    end
end

local function NewTag(parent, kind, name, template, withReticle)
    local Theme, colors = FS.Theme, Tags.colors
    local frame = CreateFrame(kind, name, parent, template)
    if not template then frame:SetFrameLevel(parent:GetFrameLevel() + C.FRAME_LEVEL) end
    local bg = colors.bg
    Theme.AddCut2Texture(frame, Theme.SLICE_CUT2_FILL_TEXTURE, { bg[1], bg[2], bg[3], C.FILL_A }, "BACKGROUND", 0)
    -- The outline is the box's own tone, not a colour of the tag's: steel at rest and while the cast cannot be kicked,
    -- pink while it can, red for INTERRUPTED. The tone frames join the box's flag lists (GunsightBoxes.NewChrome), so
    -- the one flag write that tints the box edge tints this outline; this file never sees the flag. They are plain
    -- child frames, so the shield and the verdict drive them in combat, on the secure button's too. The fill and the
    -- label stay on the tag; the label colours carry data (level, health, names) and are not toned.
    -- A plate with a reticle draws it in the same three tone frames, so it is in the same flag lists as the outline, once.
    frame.tones = FS.GunsightBoxes.NewChrome(Tags.box, frame, function(tone, color)
        Theme.AddCut2Texture(tone, Theme.SLICE_CUT2_OUTLINE_TEXTURE, color, "BORDER")
        if withReticle then AddReticle(tone, color) end
    end)
    local label = frame:CreateFontString(nil, "OVERLAY")
    Theme.ApplyMono(label, FontSize(), colors.white)
    label:SetPoint("CENTER", frame, "CENTER", 0, 0)
    label:SetText("")
    frame.label = label
    return frame
end

local function SeatPlain(frame, relPoint, spec, dy, color)
    local k = ui(1)
    frame:ClearAllPoints()
    frame:SetPoint("TOPLEFT", Tags.box.frame, relPoint, spec.dx * k, dy * k)
    if spec.w then frame:SetSize(spec.w * k, C.H * k) end
    FS.Theme.ApplyMono(frame.label, FontSize(), color)
end

-------------------------------------------------------------------------------
-- Level and class
-------------------------------------------------------------------------------

-- The level number in white, on a plate sized to it: pad, [icon, gap], digits, pad, never under minW (mockups/
-- gunsight-level-tag-2026-10-08.html). The plate keeps its seat and grows to the right. The level goes to
-- SetFormattedText as an argument (it may be secret); a level below 1 reads "??". The classification has no text: its
-- icon (C.ICONS) fills the icon slot (SetLevelIcon), which costs no width while it is empty. A world boss shows the
-- skull alone, no digits, as the mockup does.

-- What the plain text in the label takes on one line, in screen px (GetUnboundedStringWidth: GetStringWidth is bounded
-- by the FontString's own width); nil when the client cannot measure. Never called on a secret.
local function PlainWidth(fs)
    local fn = fs.GetUnboundedStringWidth or fs.GetStringWidth
    local ok, w = pcall(fn, fs)
    if ok and type(w) == "number" and not IsSecret(w) and w > 0 then return w end
    return nil
end

-- Sizes the plate to what the label holds. A secret level is never measured: two digits are reserved, which is also
-- what a plain two digit level takes. A font that lands a frame late measures the old size, so a rescale re-runs this
-- next frame (RefitLevelLater).
local function FitLevel()
    local frame = Tags.level
    if not frame then return end
    local L, k = C.LEVEL, ui(1)
    local digits = L.advance * C.TEXT_SIZE
    local tw = 0
    if Tags.levelState == "secret" then
        tw = 2 * digits
    elseif Tags.levelState == "plain" then
        local m = PlainWidth(frame.label)
        tw = m and m / k or Tags.levelChars * digits
    end
    local lead = (Tags.iconW > 0) and (Tags.iconW + (tw > 0 and L.gap or 0)) or 0
    local content = lead + tw
    local w = math.max(L.minW, math.ceil(2 * L.pad + content - 1e-6))
    frame:SetSize(w * k, C.H * k)
    frame.label:ClearAllPoints()
    frame.label:SetPoint("CENTER", frame, "CENTER", lead / 2 * k, 0)
    local icon = frame.icon
    icon:ClearAllPoints()
    icon:SetPoint("LEFT", frame, "LEFT", (w - content) / 2 * k, 0)
    icon:SetSize(Tags.iconW * k, Tags.iconH * k)
    icon:SetShown(Tags.iconW > 0)
end

local function RefitLevelLater()
    if Tags.levelRefit or type(C_Timer) ~= "table" or type(C_Timer.After) ~= "function" then return end
    Tags.levelRefit = true
    C_Timer.After(0, function()
        Tags.levelRefit = false
        Guard(FitLevel)
    end)
end

-- The icon slot: its width (and height, square by default) in image px; 0 empties it. PaintIcon sets the texture on
-- `GunsightTags.level.icon` and sizes it through this.
function GunsightTags.SetLevelIcon(width, height)
    Tags.iconW = math.max(0, tonumber(width) or 0)
    Tags.iconH = Tags.iconW > 0 and (tonumber(height) or Tags.iconW) or 0
    Guard(FitLevel)
end

-- The classification word of the target: its C.ICONS key, nil for no icon. A secret word (combat is unverified) keeps the
-- kind drawn now, which is nothing on a new target; it is checked before anything else touches it and never compared.
local function ClassificationKind()
    local class = UnitClassification("target")
    if IsSecret(class) then return Tags.iconKind end
    if type(class) == "string" and C.ICONS[class] then return class end
    return nil
end

-- Sets the icon texture, tint and size for `kind` (nil empties the slot); the caller fits the plate. A kind whose
-- texture token is missing from Theme counts as no icon (iconKind cleared), so a skull's bare plate shows digits.
local function PaintIcon(kind)
    local spec = kind and C.ICONS[kind]
    local Theme, icon = FS.Theme, Tags.level.icon
    if not (spec and Theme and Theme[spec.tex]) then
        Tags.iconKind = nil
        Tags.iconW, Tags.iconH = 0, 0
        return
    end
    Tags.iconKind = kind
    icon:SetTexture(Theme[spec.tex])
    local tint = spec.tint and Theme[spec.tint] or { 1, 1, 1, 1 }
    icon:SetVertexColor(tint[1], tint[2], tint[3], tint[4] or 1)
    Tags.iconW, Tags.iconH = spec.size, spec.size
end

local function WriteLevel()
    local label = Tags.level and Tags.level.label
    if not label then return end
    Tags.levelState, Tags.levelChars = "none", 0
    if not FS.HasTarget() then
        label:SetText("")
        PaintIcon(nil)
        return FitLevel()
    end
    PaintIcon(ClassificationKind())
    local kind = Tags.iconKind
    if kind and C.ICONS[kind].bare then
        label:SetText("")
        return FitLevel()
    end
    local level = UnitLevel("target")
    if IsSecret(level) then
        Tags.levelState = "secret"
        label:SetFormattedText("%d", level)
    elseif type(level) == "number" then
        Tags.levelState = "plain"
        if level >= 1 then
            Tags.levelChars = #tostring(math.floor(level))
            label:SetFormattedText("%d", level)
        else
            Tags.levelChars = 2
            label:SetText("??")
        end
    else
        label:SetText("")
    end
    FitLevel()
end

-- A new target (or a world load) starts with an empty icon slot; WriteLevel fills it from a readable classification.
local function WriteLevelForNewTarget()
    Tags.iconKind = nil
    WriteLevel()
end

local function ApplyLevel()
    local frame = Tags.level
    if not frame then return end
    local on = Setting(SETTINGS.level)
    frame:SetShown(on)
    if on then Guard(WriteLevel) end
end

-------------------------------------------------------------------------------
-- Health percent: the target box writes it (its WritePercent) through box.healthTag
-------------------------------------------------------------------------------

local function ApplyHealth()
    local frame, box = Tags.health, Tags.box
    if not frame then return end
    local on = Setting(SETTINGS.health)
    frame:SetShown(on)
    box.healthTag = on and frame.label or nil
    if on then
        FS.GunsightBoxes.Refresh(box)
    else
        frame.label:SetText("")
    end
end

-------------------------------------------------------------------------------
-- Target of target: a secure button, so only SetAlpha, text and (out of combat) Show / Hide / EnableMouse
-------------------------------------------------------------------------------

local SyncTot
local SeatMenu, SyncMenu   -- the target menu button's reseat and mouse state, defined with BuildMenu

-- The size the target of target name is shrunk to at most: the line's floor, never over the base size.
local function TotFloorSize()
    return math.min(FontSize(), math.max(C.MIN_FONT, math.floor(ui(C.TOT_FLOOR) + 0.5)))
end

-- The measuring FontString is given the floor size here, and only when the floor size changes (a rescale).
local function SetProbeSize(size)
    local probe = Tags.totProbe
    if not probe or Tags.probeSize == size then return end
    Tags.probeSize = size
    FS.Theme.ApplyMono(probe, size, Tags.colors.white)
end

-- The seat and the button's size are the only geometry; both wait for the end of combat.
local function SeatTot()
    local seat, button = Tags.seat, Tags.tot
    if not seat then return end
    if InCombat() then
        Tags.pendingSeat = true
        return
    end
    Tags.pendingSeat = false
    local k = ui(1)
    seat:ClearAllPoints()
    seat:SetPoint("TOPLEFT", Gunsight.anchors.boxR, "BOTTOMLEFT", C.TOT.dx * k, C.OVERLAP * k)
    seat:SetSize(C.TOT.w * k, C.H * k)
    -- The label takes what is right of the reticle: a pad, the glyph and its gap in, a pad at the right edge, and is centred there.
    local lead = C.RETICLE.size + C.RETICLE.gap
    local labelW = C.TOT.w - 2 * C.TOT_PAD - lead
    local wmax = labelW * k
    button.label:ClearAllPoints()
    button.label:SetPoint("CENTER", button, "LEFT", (C.TOT_PAD + lead + labelW / 2) * k, 0)
    button.label:SetWidth(wmax)
    SeatReticle(button)
    Tags.totLine.wmax = wmax
    SetProbeSize(TotFloorSize())
    Tags.totName = nil
    Tags.totShort = false
    SyncTot()   -- fits the name again at the new width; the font is only set when the fit changes the size
end

-- "Bartholomew Oldlight" -> "B. Oldlight": every word but the last becomes its first character (a whole UTF-8
-- character) and a dot. nil for a single word. Plain strings only; a secret is never abbreviated.
local function AbbreviateName(name)
    local words = {}
    for word in name:gmatch("%S+") do words[#words + 1] = word end
    if #words < 2 then return nil end
    for i = 1, #words - 1 do
        words[i] = (words[i]:match("^[%z\1-\127\194-\244][\128-\191]*") or words[i]) .. "."
    end
    return table.concat(words, " ")
end

-- The size the label is really drawn at, read back from the client; fallback when it cannot be read.
local function LabelFontSize(label, fallback)
    if type(label.GetFont) ~= "function" then return fallback end
    local ok, _, size = pcall(label.GetFont, label)
    if ok and type(size) == "number" and not IsSecret(size) and size > 0 then return size end
    return fallback
end

-- Fits a plain name to the label with the box name's own fit (GunsightBoxes' text line: shrinks step by step to
-- C.TOT_FLOOR, SetFont only when the size changes). The decision to shorten the first names to initials is MEASURED AT
-- THE FLOOR SIZE, on a hidden FontString of the ToT (Tags.totProbe) that holds the floor font and the full name: the
-- name is abbreviated only when it is still wider than the label there (width does not scale linearly with the font
-- size, so a width scaled from another size would decide wrongly). A name that fits at the floor is written whole
-- and shrunk; what is still too wide after the abbreviation is left to the FontString's ellipsis. The label never
-- holds the full name of an abbreviated one. A probe that cannot measure falls back to the label's own width at the
-- size it HAS, scaled linearly to the floor. The line's size is set to the label's real font size first: a font
-- reapplied behind the line's back (the cold-start retry puts the base size back) would otherwise leave the fit's
-- SetFont skipped as "unchanged". Tags.totShort records that the shown text is the abbreviated one.
local function FitTotName(full)
    local line, label, probe = Tags.totLine, Tags.tot.label, Tags.totProbe
    local size = LabelFontSize(label, line.size)
    line.size = size
    local text = full
    local wide
    if probe then
        if pcall(probe.SetText, probe, full) then
            local pw = PlainWidth(probe)
            if pw then wide = pw > line.wmax + 1e-6 end
        end
    end
    if wide == nil then
        label:SetText(full)
        local w = PlainWidth(label)
        if w and size and size > 0 then wide = w * TotFloorSize() / size > line.wmax + 1e-6 end
    end
    if wide then text = AbbreviateName(full) or full end
    Tags.totShort = text ~= full
    FS.GunsightBoxes.WriteTextLine(line, text)
end

-- A client may apply SetFont a frame late, and then the width measured right after a size change is the old font's.
-- A write that changed the size, or that shows the abbreviated name (its decision may have come from a wrong
-- measurement, and the abbreviated text fits at the current size, so no size change would ever call for a second
-- look), re-runs the decision from the full name on the next frame, at most three times (the shown text may be the
-- abbreviated one; only the full name is decided from).
local RefitTotLater
local function RunTotRefit(step)
    local full = Tags.totName
    if not full then return end
    local before = Tags.totLine.size
    FitTotName(full)
    if (Tags.totLine.size ~= before or Tags.totShort) and step < 3 then RefitTotLater(step + 1) end
end
function RefitTotLater(step)
    Tags.totStep = step
    if Tags.totRefitPending or type(C_Timer) ~= "table" or type(C_Timer.After) ~= "function" then return end
    Tags.totRefitPending = true
    C_Timer.After(0, function()
        Tags.totRefitPending = false
        Guard(RunTotRefit, Tags.totStep)
    end)
end

-- Writes the name into the label. A secret name goes straight to SetText: it is never measured, compared or
-- abbreviated. The same plain name as last time is already fitted, and writing it again would set the font to the
-- base size and back every event; `Tags.totName` (the full plain name, not the shown text) records it after a
-- successful write, a secret or empty write clears it, and a rescale clears it too.
local function WriteTotName(name)
    local line = Tags.totLine
    if IsSecret(name) then
        Tags.totName = nil
        Tags.totShort = false
        FS.GunsightBoxes.WriteTextLine(line, name)
        return
    end
    if name == Tags.totName then return end
    Tags.totName = nil
    if name == "" then
        Tags.totShort = false
        FS.GunsightBoxes.WriteTextLine(line, "")
        return
    end
    local before = line.size
    FitTotName(name)
    Tags.totName = name
    if line.size ~= before or Tags.totShort then RefitTotLater(1) end
end

-- The name (first + surname: UnitName alone drops the surname on this server) goes to the label from
-- FS.GetFullUnitName (UnitFrames.lua, loaded earlier, read at call time) else UnitName. Visibility is alpha and text
-- only; out of combat the button is shown
-- with its mouse on while the toggle and the tgt piece are on, so a target of target that appears in combat is clickable.
function SyncTot()
    local button = Tags.tot
    if not button then return end
    local on = Setting(SETTINGS.tot) and Gunsight.IsPieceOn("tgt")
    local has = false
    if on and FS.HasTarget() then
        local exists = UnitExists("targettarget")
        has = IsSecret(exists) or exists == true
    end
    local name
    if has then
        if type(FS.GetFullUnitName) == "function" then
            name = FS.GetFullUnitName("targettarget")
        else
            name = UnitName("targettarget")
        end
    end
    if has and (IsSecret(name) or type(name) == "string") then
        WriteTotName(name)
    else
        WriteTotName("")
    end
    button:SetAlpha(has and 1 or 0)
    if InCombat() then return end
    button:SetShown(on)
    button:EnableMouse(on)
end

-------------------------------------------------------------------------------
-- The target menu: a right click on the target box opens the unit context menu
-------------------------------------------------------------------------------

-- An invisible SecureUnitButtonTemplate button over the target box, set up like UnitFrames' target frame (unit, "*type2" =
-- "togglemenu": click handling is C side, so no snippet is involved) but registered for RightButtonUp alone.
--   * Left clicks and left drags (targeting, click to move, camera turns) and middle clicks must still reach what is behind the box,
--     so they are passed through with SetPassThroughButtons. That call, and the read back (ShouldButtonPassThrough), are in the 16001
--     widget dump but UNVERIFIED in game; if either is missing or does not take, the button never gets its mouse (it would swallow
--     the left click) and one chat line says so. The mouse wheel is never enabled on it.
--   * No target: RegisterUnitWatch (the client's own show and hide, as on the unit frames) keeps the button hidden, so it takes no
--     click. If the client's unit watch does not run, the button stays shown and a right click opens nothing (togglemenu opens no
--     menu for a unit that does not exist). We never call Show or Hide on it.
--   * Mouse on: out of combat only, while the tgt piece is on (a piece changed in combat is alpha only, like the target of target).
--   * Right-drag camera turns that start over the box are taken by the menu while there is a target (left and middle pass through).
-- The button hangs from the box ANCHOR with the box frame's own offsets (the box frame itself moves and resizes in combat and so must
-- stay out of the button's anchor family) and so is reseated out of combat only: build, a rescale, and the box growing up for the
-- numbers row (box.onGrow). A reseat that falls in combat waits for PLAYER_REGEN_ENABLED. Its frame level is the box's own, under the
-- hover-only icon tile (which keeps its tooltip, its clicks pass through) and under the target of target (which keeps its clicks).
-- No texture, no region, no child, no script: nothing is drawn and no tooltip is added.
function SeatMenu()
    local button, box = Tags.menu, Tags.box
    if not button or not box then return end
    if InCombat() then
        Tags.pendingMenu = true
        return
    end
    Tags.pendingMenu = false
    local anchor = Gunsight.anchors.boxR
    button:ClearAllPoints()
    button:SetPoint("TOPLEFT", anchor, "TOPLEFT", 0, (box.grow or 0) * ui(1))
    button:SetPoint("BOTTOMRIGHT", anchor, "BOTTOMRIGHT", 0, 0)
end

-- Accepted limit: EnableMouse on a secure frame is blocked in combat, so a tgt piece turned off mid fight leaves the invisible box
-- taking right clicks until PLAYER_REGEN_ENABLED (and one turned on mid fight waits the same way).
function SyncMenu()
    local button = Tags.menu
    if not button or InCombat() then return end
    button:EnableMouse(Tags.menuReady == true and Gunsight.IsPieceOn("tgt") == true)
end

-- Left and middle fall through; true only when the client says they now do.
local function PassClicksThrough(button)
    if type(button.SetPassThroughButtons) ~= "function" or type(button.ShouldButtonPassThrough) ~= "function" then return false end
    if not pcall(button.SetPassThroughButtons, button, "LeftButton", "MiddleButton") then return false end
    local ok, left = pcall(button.ShouldButtonPassThrough, button, "LeftButton")
    return ok and left == true
end

-- Out of combat only (BuildTot's caller guarantees it).
local function BuildMenu(holder)
    local box = Tags.box
    local button = CreateFrame("Button", "ForeverSTUwaveGunsightTargetMenu", holder, "SecureUnitButtonTemplate")
    button:SetFrameLevel(box.frame:GetFrameLevel())
    button:SetAttribute("unit", "target")
    button:SetAttribute("*type2", "togglemenu")
    button:RegisterForClicks("RightButtonUp")
    button:EnableMouse(false)
    Tags.menuReady = PassClicksThrough(button)
    if not Tags.menuReady then
        Logged("gunsighttags_menu", "|cffff4488Forever STUwave|r: the target box right click menu is off: this client cannot pass left clicks through the button.")
    end
    Tags.menu = button
    GunsightTags.menu = button
    RegisterUnitWatch(button)
    SeatMenu()
    SyncMenu()
end

-- Out of combat only: SecureUnitButtonTemplate attributes are set from plain Lua (secure snippets do not run here).
-- The holder is never shown or hidden, so no parent of the protected button is hidden in combat (the box, piece and gate are).
local function BuildTot()
    local box = Tags.box
    local holder = CreateFrame("Frame", nil, Gunsight.root)
    holder:SetSize(1, 1)
    holder:SetPoint("CENTER", Gunsight.root, "CENTER", 0, 0)
    holder:SetFrameLevel(box.frame:GetFrameLevel() + 4)
    Guard(BuildMenu, holder)   -- first, so the target of target is built over it; a failure here leaves the target of target alone
    local seat = CreateFrame("Frame", nil, holder)
    local button = NewTag(holder, "Button", "ForeverSTUwaveGunsightTargetOfTarget", "SecureUnitButtonTemplate", true)
    button.label:SetJustifyH("CENTER")
    button.label:SetWordWrap(false)
    -- The name fits through GunsightBoxes' text line; the font NewTag set is the line's current size (no second SetFont).
    local line = FS.GunsightBoxes.NewTextLine({ button.label }, C.TEXT_SIZE, nil, C.TOT_FLOOR)
    -- The hidden measuring FontString (a plain one: no combat restriction) holds the floor font from the start (a
    -- FontString with no font throws on SetText); SeatTot sets it again only when a rescale moves the floor.
    local probe = holder:CreateFontString(nil, "OVERLAY")
    probe:Hide()
    Tags.totProbe, Tags.probeSize = probe, nil
    GunsightTags.totProbe = probe
    SetProbeSize(TotFloorSize())
    line.colors[1], line.size = Tags.colors.white, FontSize()
    line.ownSettle = true   -- RefitTotLater re-decides from the full name; the line's own size-only settle would race it
    Tags.totLine = line
    button:SetAttribute("type1", "target")
    button:SetAttribute("unit", "targettarget")
    button:RegisterForClicks("AnyUp")
    button:EnableMouse(false)
    button:ClearAllPoints()
    button:SetPoint("TOPLEFT", seat, "TOPLEFT", 0, 0)
    button:SetPoint("BOTTOMRIGHT", seat, "BOTTOMRIGHT", 0, 0)
    Tags.seat, Tags.tot = seat, button
    GunsightTags.holder, GunsightTags.seat, GunsightTags.tot = holder, seat, button
    SeatTot()
    SyncTot()
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

local function Register(frame, event, unit)
    if unit and pcall(frame.RegisterUnitEvent, frame, event, unit) then return end
    pcall(frame.RegisterEvent, frame, event)
end

local function Layout()
    SeatPlain(Tags.level, "TOPLEFT", C.LEVEL, C.RISE, Tags.colors.white)
    FitLevel()
    RefitLevelLater()
    SeatPlain(Tags.health, "BOTTOMLEFT", C.HEALTH, C.OVERLAP, Tags.colors.green)
    if Tags.tot then SeatTot() end
    if Tags.menu then SeatMenu() end
end

local function Build()
    if not Gunsight.IsEnabled() then return end
    local tape = FS.GunsightTape
    local box = type(tape) == "table" and tape.tgt and tape.tgt.box
    local Boxes = FS.GunsightBoxes
    if type(box) ~= "table" or not box.frame or type(Boxes) ~= "table" or not Boxes.colors then
        Logged("gunsighttags_nobox", "|cffff4488Forever STUwave|r: the target box is missing; the box tags are not drawn.")
        return
    end
    local colors = Boxes.colors
    Tags.box, Tags.colors = box, colors

    local level = NewTag(box.frame, "Frame")
    level.icon = level:CreateTexture(nil, "OVERLAY")
    level.icon:Hide()
    local health = NewTag(box.frame, "Frame")
    Tags.level, Tags.health = level, health
    GunsightTags.level, GunsightTags.health = level, health
    Layout()
    ApplyLevel()
    ApplyHealth()
    -- The numbers row grows the box up; the tape's own hook (set when the box was built) keeps running, then the button follows.
    local grown = box.onGrow
    box.onGrow = function(b)
        if grown then grown(b) end
        Guard(SeatMenu)
    end

    if InCombat() then
        Tags.pendingTot = true
    else
        BuildTot()
    end

    local events = CreateFrame("Frame", nil, box.frame)
    Tags.events = events
    for _, event in ipairs({ "PLAYER_TARGET_CHANGED", "PLAYER_ENTERING_WORLD" }) do Register(events, event) end
    for _, event in ipairs({ "UNIT_LEVEL", "UNIT_CLASSIFICATION_CHANGED", "UNIT_TARGET" }) do Register(events, event, "target") end
    events:SetScript("OnEvent", function(_, event, unit)
        if not IsSecret(unit) and type(unit) == "string" and unit ~= "target" then return end
        if event == "PLAYER_TARGET_CHANGED" or event == "PLAYER_ENTERING_WORLD" then
            Guard(WriteLevelForNewTarget)
        elseif event ~= "UNIT_TARGET" then
            Guard(WriteLevel)
        end
        if event ~= "UNIT_LEVEL" and event ~= "UNIT_CLASSIFICATION_CHANGED" then Guard(SyncTot) end
    end)

    local regen = CreateFrame("Frame")
    regen:RegisterEvent("PLAYER_REGEN_ENABLED")
    regen:SetScript("OnEvent", function()
        if Tags.pendingTot then
            Tags.pendingTot = false
            Guard(BuildTot)
        end
        if Tags.pendingSeat then Guard(SeatTot) end
        if Tags.pendingMenu then Guard(SeatMenu) end
        Guard(SyncTot)
        Guard(SyncMenu)
    end)

    if FS.Layout and FS.Layout.OnRescale then FS.Layout.OnRescale(function() Guard(Layout) end) end
    if type(Gunsight.OnPieceChanged) == "function" then
        Gunsight.OnPieceChanged(function(key)
            if key == "tgt" then
                Guard(SyncTot)
                Guard(SyncMenu)
            end
        end)
    end
end

Config.OnChange(SETTINGS.level.key, ApplyLevel)
Config.OnChange(SETTINGS.health.key, ApplyHealth)
Config.OnChange(SETTINGS.tot.key, SyncTot)

Gunsight.OnReady(function()
    local ok, err = pcall(Build)
    if not ok then
        Logged("gunsighttags_build", "|cffff4488Forever STUwave|r: box tags build failed: " .. tostring(err))
        for _, frame in ipairs({ Tags.level or false, Tags.health or false }) do
            if frame then pcall(frame.Hide, frame) end
        end
    end
end)
