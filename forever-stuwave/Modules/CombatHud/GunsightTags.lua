-- Forever STUwave: KICK style tags on the target box, level and class on the top edge and health percent and target of target on the bottom edge, each with an FS.Config toggle.
-- The target of target tag is a SecureUnitButtonTemplate button that targets that unit on a click; in combat it only takes SetAlpha and text.
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
    LEVEL = { dx = 1, w = 68 }, HEALTH = { dx = 4, w = 32 }, TOT = { dx = 41, w = 69 },
    RISE = 8, OVERLAP = 7,
    MIN_FONT = 6, TOT_PAD = 3,
    FRAME_LEVEL = 6,   -- the level and health tags' frame level above the box: over the edge strokes (+1) and the bars (+1 to +3)
}
GunsightTags.C = C

local KEY = "gunsight.tags."
local SETTINGS = {
    level = { key = KEY .. "level", default = true },
    health = { key = KEY .. "health", default = true },
    tot = { key = KEY .. "tot", default = true },
}
GunsightTags.SETTINGS = SETTINGS
for _, def in pairs(SETTINGS) do Config.RegisterDefault(def.key, def.default) end

local WORDS = { worldboss = "BOSS", elite = "ELITE", rare = "RARE", rareelite = "RARE" }

local Tags = { colors = nil, box = nil, events = nil, pendingTot = false, pendingSeat = false }

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

-- The KICK tag's look: a chamfered plate, a pink outline and one centred label. The tags straddle the box edge, so
-- the plate must mask the edge line behind the text (the mockup draws them after the box): a plain tag takes its own
-- frame level above everything the box holds, since sibling frames of equal level have no promised draw order.
-- The secure button is left at its holder's level (a protected frame's level is not ours to set in combat).
local function NewTag(parent, kind, name, template)
    local Theme, colors = FS.Theme, Tags.colors
    local frame = CreateFrame(kind, name, parent, template)
    if not template then frame:SetFrameLevel(parent:GetFrameLevel() + C.FRAME_LEVEL) end
    local bg = colors.bg
    Theme.AddCut2Texture(frame, Theme.SLICE_CUT2_FILL_TEXTURE, { bg[1], bg[2], bg[3], C.FILL_A }, "BACKGROUND", 0)
    Theme.AddCut2Texture(frame, Theme.SLICE_CUT2_OUTLINE_TEXTURE, colors.pink, "BORDER")
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
    frame:SetSize(spec.w * k, C.H * k)
    FS.Theme.ApplyMono(frame.label, FontSize(), color)
end

-------------------------------------------------------------------------------
-- Level and class
-------------------------------------------------------------------------------

-- "L62" in white, the classification word in gold. The level goes to SetFormattedText as an argument (it may be
-- secret); a secret classification leaves the word out; level -1 reads "??".
local function WriteLevel()
    local label = Tags.level and Tags.level.label
    if not label then return end
    if not FS.HasTarget() then
        label:SetText("")
        return
    end
    local level = UnitLevel("target")
    local class
    if type(UnitClassification) == "function" then class = UnitClassification("target") end
    local word
    if not IsSecret(class) and type(class) == "string" then word = WORDS[class] end
    local head, useLevel
    if IsSecret(level) then
        head, useLevel = "L%d", true
    elseif type(level) == "number" then
        if level >= 1 then head, useLevel = "L%d", true else head = "??" end
    else
        label:SetText("")
        return
    end
    local fmt = head
    if word then fmt = head .. " " .. Tags.gold .. word .. "|r" end
    if useLevel then label:SetFormattedText(fmt, level) else label:SetFormattedText(fmt) end
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
    FS.Theme.ApplyMono(button.label, FontSize(), Tags.colors.white)
    button.label:SetWidth((C.TOT.w - 2 * C.TOT_PAD) * k)
end

-- The name goes from UnitName straight to SetText. Visibility is alpha and text only; out of combat the button is shown
-- with its mouse on while the toggle and the tgt piece are on, so a target of target that appears in combat is clickable.
local function SyncTot()
    local button = Tags.tot
    if not button then return end
    local on = Setting(SETTINGS.tot) and Gunsight.IsPieceOn("tgt")
    local has = false
    if on and FS.HasTarget() then
        local exists = UnitExists("targettarget")
        has = IsSecret(exists) or exists == true
    end
    local name
    if has then name = UnitName("targettarget") end
    if has and (IsSecret(name) or type(name) == "string") then
        button.label:SetText(name)
    else
        button.label:SetText("")
    end
    button:SetAlpha(has and 1 or 0)
    if InCombat() then return end
    button:SetShown(on)
    button:EnableMouse(on)
end

-- Out of combat only: SecureUnitButtonTemplate attributes are set from plain Lua (secure snippets do not run here).
-- The holder is never shown or hidden, so no parent of the protected button is hidden in combat (the box, piece and gate are).
local function BuildTot()
    local box = Tags.box
    local holder = CreateFrame("Frame", nil, Gunsight.root)
    holder:SetSize(1, 1)
    holder:SetPoint("CENTER", Gunsight.root, "CENTER", 0, 0)
    holder:SetFrameLevel(box.frame:GetFrameLevel() + 4)
    local seat = CreateFrame("Frame", nil, holder)
    local button = NewTag(holder, "Button", "ForeverSTUwaveGunsightTargetOfTarget", "SecureUnitButtonTemplate")
    button.label:SetJustifyH("CENTER")
    button.label:SetWordWrap(false)
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
    SeatPlain(Tags.health, "BOTTOMLEFT", C.HEALTH, C.OVERLAP, Tags.colors.green)
    if Tags.tot then SeatTot() end
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
    Tags.gold = string.format("|cff%02x%02x%02x", math.floor(colors.gold[1] * 255 + 0.5),
        math.floor(colors.gold[2] * 255 + 0.5), math.floor(colors.gold[3] * 255 + 0.5))

    local level = NewTag(box.frame, "Frame")
    local health = NewTag(box.frame, "Frame")
    Tags.level, Tags.health = level, health
    GunsightTags.level, GunsightTags.health = level, health
    Layout()
    ApplyLevel()
    ApplyHealth()

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
        if event ~= "UNIT_TARGET" then Guard(WriteLevel) end
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
        Guard(SyncTot)
    end)

    if FS.Layout and FS.Layout.OnRescale then FS.Layout.OnRescale(function() Guard(Layout) end) end
    if type(Gunsight.OnPieceChanged) == "function" then
        Gunsight.OnPieceChanged(function(key) if key == "tgt" then Guard(SyncTot) end end)
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
