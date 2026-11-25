-- Forever STUwave: the Warrior's Thunder Clap tab (look A, SHOCKWAVE, of the design mockup thunderclap-tab-2026-11-12)
--
-- A 1 x 1 class shoulder on the Console's top edge, 16 design px right of the stance tab (ClassShoulder.lua seats it as the
-- Warrior's `also` shoulder `warriorclap`). One 38 px key wearing the Thunder Clap icon. DISPLAY ONLY: plain frames, no
-- secure button, no binding, no click action (the mouse is on for the tooltip alone).
--
-- Forever data (client spell data, id 6343): a 6 s cooldown of its own, 20 rage, Battle or Defensive Stance. Ranks 6343,
-- 8198, 8204, 8205, 11580, 11581; the highest known one is the id every read uses.
--
-- STATES, one at a time, in this order:
--   * hidden: not a Warrior, the setting off, or no rank known yet (levels 1 to 5): OwnsShoulder is false, so no shoulder
--     stands and the Console's top line closes.
--   * STANCE: C_Spell.IsSpellUsable says unusable while the active form is Berserker Stance (GetShapeshiftFormInfo's
--     spell id 2458): grey desaturated icon, muted ring, the word STANCE on a band. Unusable for any other reason is the
--     same grey look with no word.
--   * RAGE: IsSpellUsable's second answer (not enough power): red ring, red icon tint, red underline, the word RAGE.
--   * COOLING: the cooldown runs: the violet fill every bar key wears (FrameHelpers.SetCooldownFill, run by the ENGINE
--     from C_Spell.GetSpellCooldownDuration with the GCD left out, StatusBar:SetTimerDuration; no number is read, so it
--     runs in combat where the seconds are secret), violet underline, icon a little dim.
--   * READY: cyan ring and glow, cyan underline; the ring flashes white into cyan as the cooldown ends, and a faint
--     cyan outline pings off the key every PING_PERIOD seconds while it stays ready.
--   A usability or cooldown answer that cannot be read (nil, secret) keeps the last state painted.
--
-- READY vs COOLING (CooldownState): a plain isActive false is ready, a plain isOnGCD true is ready, plain start and duration
-- (out of combat) are exact (a duration within the GCD window is the GCD alone), and otherwise (combat: the seconds are
-- secret, isActive stays plain) our own cast ledger decides: cooling until the last Thunder Clap seen in
-- UNIT_SPELLCAST_SUCCEEDED plus COOLDOWN.
--
-- THE CLAP (each Thunder Clap rank cast by the player, our own UNIT_SPELLCAST_SUCCEEDED, plain spell id): two shockwaves,
-- the key's own cut ring in cyan then pink, scale from 1 to WAVE_SCALE and fade out (the second WAVE_DELAY later), a white
-- flash over the icon and a one pixel downward jolt of the key. All engine AnimationGroups on plain regions, started by
-- the event; nothing runs per frame for them. The `thunderclap.motion` setting turns every motion off (the colours stay).
--
-- Combat: nothing here is protected, so painting, the effects and the fill all run in combat; only the host's anchor onto
-- the Console waits for PLAYER_REGEN_ENABLED (like FiveSecondTab.lua). Loads after FiveSecondTab.lua, before
-- ConfigWindow.lua (which reads SETTINGS). UNVERIFIED in game: whether the duration object asked with the GCD left out is
-- empty during another ability's GCD, whether IsSpellUsable is false in Berserker Stance and its rage flag plain in
-- combat; tools/thunderclap-harness.py pins the logic against a mock.

local _, FS = ...

local Tab = {}
FS.ThunderClapTab = Tab

local IsSecret = FS.IsSecret

local TC = {
    KEY = "warriorclap",
    RANKS = { 6343, 8198, 8204, 8205, 11580, 11581 },
    BERSERKER = 2458,
    COOLDOWN = 6,
    GCD_WINDOW = 1.6,
    -- motion, seconds
    WAVE_SCALE = 2.9, WAVE_TIME = 0.7, WAVE2_TIME = 0.9, WAVE_DELAY = 0.12,
    FLASH_ALPHA = 0.85, FLASH_TIME = 0.3,
    JOLT_PX = 1.5, JOLT_TIME = 0.28,
    ARRIVE_TIME = 0.5,
    PING_SCALE = 1.32, PING_ALPHA = 0.6, PING_TIME = 1.04, PING_PERIOD = 2.6,
    -- look
    GLOW_READY = 0.7, GLOW_IDLE = 0.35,
    COOL_DIM = 0.7, STANCE_DIM = 0.45,
    UL_INSET = 5, UL_BELOW = 3, UL_PX = 2,         -- underline: design px in from each side, design px under the key
    BAND_TOP = 24, BAND_H = 9, BAND_SIDE = 3,       -- the word band (the buff tab's), design px
    WORD_PX = 8,
    TICK_FAST = 0.1, TICK_SLOW = 0.5,
    host = nil, key = nil,
    built = false, seated = false, pendingSync = false,
    state = nil, spellID = nil, lastCast = nil, plainEnd = nil,
    warned = {},
}
Tab.TC = TC

local SETTINGS = {
    enabled = {
        key = "thunderclap.enabled", default = true, label = "Thunder Clap tab",
        tip = "A tab on the Console, right of your stances, that shows when Thunder Clap is ready. Off hides it.",
    },
    motion = {
        key = "thunderclap.motion", default = true, label = "Shockwave motion",
        tip = "Shockwaves and a flash when you cast Thunder Clap, and a soft pulse while it is ready. "
            .. "Off keeps the tab still: only its colours change.",
    },
}
Tab.SETTINGS = SETTINGS
if FS.Config and FS.Config.RegisterDefault then
    for _, def in pairs(SETTINGS) do FS.Config.RegisterDefault(def.key, def.default) end
end

local function Setting(def)
    local config = FS.Config
    if config and config.Get then
        local value = config.Get(def.key)
        if type(value) == "boolean" then return value end
    end
    return def.default
end

local function Scale()
    return (FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1
end

local function WarnOnce(key, text)
    if TC.warned[key] then return end
    TC.warned[key] = true
    if FS.LogDegradeOnce then FS.LogDegradeOnce(key, "|cffff4488Forever STUwave|r: " .. text) end
end

local function Plain(v, kind)
    if IsSecret(v) or type(v) ~= kind then return nil end
    return v
end

local function PlayerClass()
    local ok, _, token = pcall(UnitClass, "player")
    if not ok then return nil end
    return Plain(token, "string")
end

local IS_RANK = {}
for _, id in ipairs(TC.RANKS) do IS_RANK[id] = true end

-------------------------------------------------------------------------------
-- Who gets it
-------------------------------------------------------------------------------

function Tab.Applies()
    return PlayerClass() == "WARRIOR"
end

-- The highest known rank, or nil (none learned, or the spellbook cannot say).
local function ResolveSpell()
    local FH = FS.FrameHelpers
    if not (FH and FH.IsKnownSpellId) then return nil end
    for i = #TC.RANKS, 1, -1 do
        if FH.IsKnownSpellId(TC.RANKS[i], false) then return TC.RANKS[i] end
    end
    return nil
end

function Tab.SpellID()
    return TC.spellID
end

function Tab.Shown()
    return Tab.Applies() and Setting(SETTINGS.enabled) and TC.spellID ~= nil
end

-- ClassShoulder.lua stands the block while this is true.
function Tab.OwnsShoulder()
    return TC.built and Tab.Shown() or false
end

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local function Now()
    return GetTime()
end

-- true (ready), false (cooling) or nil (cannot tell). See READY vs COOLING in the header.
function Tab.CooldownState(now)
    local id = TC.spellID
    local fn = C_Spell and C_Spell.GetSpellCooldown
    if not (id and fn) then return nil end
    local ok, cd = pcall(fn, id)
    if not ok or IsSecret(cd) or type(cd) ~= "table" then return nil end
    local active = Plain(cd.isActive, "boolean")
    if active == nil then return nil end
    if not active then
        TC.plainEnd = nil
        return true
    end
    if Plain(cd.isOnGCD, "boolean") == true then return true end
    now = now or Now()
    local start, dur = Plain(cd.startTime, "number"), Plain(cd.duration, "number")
    if start and dur and dur > 0 then
        if dur <= TC.GCD_WINDOW then
            TC.plainEnd = nil
            return true
        end
        TC.plainEnd = start + dur
        return now >= start + dur
    end
    local ends = TC.plainEnd
    if TC.lastCast then
        local e = TC.lastCast + TC.COOLDOWN
        if not ends or e > ends then ends = e end
    end
    if ends and now < ends then return false end
    return true
end

-- true when the active form is Berserker Stance (plain reads only).
local function InBerserker()
    if not (GetShapeshiftForm and GetShapeshiftFormInfo) then return false end
    local ok, form = pcall(GetShapeshiftForm)
    form = ok and Plain(form, "number") or nil
    if not form or form < 1 then return false end
    local ok2, _, _, _, spellID = pcall(GetShapeshiftFormInfo, form)
    return ok2 and Plain(spellID, "number") == TC.BERSERKER
end

-- "ready" | "cool" | "rage" | "stance" | "unusable", or nil when nothing can be told.
function Tab.ReadState(now)
    local FH = FS.FrameHelpers
    local use = FH and FH.SpellUsability and FH.SpellUsability(TC.spellID)
    if use == "oom" then return "rage" end
    if use == "unusable" then return InBerserker() and "stance" or "unusable" end
    local ready = Tab.CooldownState(now)
    if ready == true then return "ready" end
    if ready == false then return "cool" end
    return nil
end

-------------------------------------------------------------------------------
-- The key
-------------------------------------------------------------------------------

local function Color(name, fallback)
    local theme = FS.Theme
    return (theme and theme[name]) or fallback
end

local function PixelUnit(frame)
    local FH = FS.FrameHelpers
    local unit = FH and FH.PixelUnit and FH.PixelUnit(frame)
    if type(unit) ~= "number" or unit <= 0 then unit = 1 end
    return unit
end

local function NewGroup(region, looping)
    if not region.CreateAnimationGroup then return nil end
    local group = region:CreateAnimationGroup()
    if looping then group:SetLooping("REPEAT") end
    return group
end

-- A shockwave: a sliced cut ring the key's size on its own frame, centred on the key, growing and fading.
local function NewWave(parent, color, delay, time, toScale, fromAlpha)
    local theme = FS.Theme
    local frame = CreateFrame("Frame", nil, parent)
    frame:EnableMouse(false)
    local ringPath = theme.Cut2ButtonSet and theme.Cut2ButtonSet(theme.SLICE_CUT_MARGIN) or theme.SLICE_BORDER_TEXTURE
    local tex = theme.AddCut2Texture(frame, ringPath, color, "OVERLAY", 6)
    tex:SetBlendMode("ADD")
    tex:SetAlpha(0)
    local group = NewGroup(tex)
    if group then
        local scale = group:CreateAnimation("Scale")
        scale:SetScaleFrom(1, 1)
        scale:SetScaleTo(toScale, toScale)
        scale:SetOrigin("CENTER", 0, 0)
        scale:SetDuration(time)
        scale:SetStartDelay(delay)
        if scale.SetSmoothing then scale:SetSmoothing("OUT") end
        local fade = group:CreateAnimation("Alpha")
        fade:SetFromAlpha(fromAlpha)
        fade:SetToAlpha(0)
        fade:SetDuration(time)
        fade:SetStartDelay(delay)
        if fade.SetSmoothing then fade:SetSmoothing("OUT") end
    end
    return { frame = frame, tex = tex, group = group }
end

local function BuildKey()
    local theme, FH = FS.Theme, FS.FrameHelpers
    local key = CreateFrame("Frame", "FSThunderClapKey", TC.host)
    key:EnableMouse(true)
    key.fsPlate = theme.AddCut2Texture(key, theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    theme.SkinCutButton(key, { borderColor = Color("COLOR_POWER", { 0.133, 0.878, 1, 1 }), glowAlpha = TC.GLOW_IDLE })
    local icon = key:CreateTexture(nil, "ARTWORK")
    icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    key.icon = icon
    FH.SeatCutIcon(key)
    key.cooldown = CreateFrame("Cooldown", nil, key, "CooldownFrameTemplate")
    if key.cooldown.SetHideCountdownNumbers then key.cooldown:SetHideCountdownNumbers(true) end
    FH.SeatButtonCooldown(key)

    -- effects and words ride a frame over the fill (FrameHelpers.CooldownTopLevel)
    local over = CreateFrame("Frame", nil, key)
    over:SetAllPoints(key)
    over:EnableMouse(false)
    key.fsOver = over

    local flash = over:CreateTexture(nil, "OVERLAY", nil, 2)
    flash:SetColorTexture(1, 1, 1, 1)
    flash:SetAllPoints(icon)
    flash:SetAlpha(0)
    key.fsFlash = flash
    local fg = NewGroup(flash)
    if fg then
        local a = fg:CreateAnimation("Alpha")
        a:SetFromAlpha(TC.FLASH_ALPHA)
        a:SetToAlpha(0)
        a:SetDuration(TC.FLASH_TIME)
    end
    key.fsFlashGroup = fg

    -- the arrive flash: a white ring over the key's ring, fading into the cyan below it
    local white = theme.Cut2ButtonSet and theme.Cut2ButtonSet(theme.SLICE_CUT_MARGIN) or theme.SLICE_BORDER_TEXTURE
    local arrive = theme.AddCut2Texture(over, white, { 1, 1, 1, 1 }, "OVERLAY", 3)
    arrive:SetAlpha(0)
    key.fsArrive = arrive
    local ag = NewGroup(arrive)
    if ag then
        local a = ag:CreateAnimation("Alpha")
        a:SetFromAlpha(1)
        a:SetToAlpha(0)
        a:SetDuration(TC.ARRIVE_TIME)
    end
    key.fsArriveGroup = ag

    -- the word band (RAGE, STANCE): the label plate colour, a word centred on it
    local band = over:CreateTexture(nil, "OVERLAY", nil, 4)
    band:SetColorTexture(0.071, 0.039, 0.133, 0.96)
    band:Hide()
    key.fsBand = band
    local word = over:CreateFontString(nil, "OVERLAY")
    if theme.ApplyMono then theme.ApplyMono(word, TC.WORD_PX) end
    word:SetDrawLayer("OVERLAY", 5)
    word:SetJustifyH("CENTER")
    word:SetPoint("CENTER", band, "CENTER", 0, 0)
    word:Hide()
    key.fsWord = word

    -- the underline, in the shoulder's bottom padding
    local ul = TC.host:CreateTexture(nil, "OVERLAY")
    ul:SetColorTexture(1, 1, 1, 1)
    key.fsUnderline = ul

    -- the shockwaves and the ready ping live on the host, so they grow past the key
    local cyan, pink = Color("COLOR_POWER", { 0.133, 0.878, 1, 1 }), Color("COLOR_HEALTH", { 1, 0.18, 0.592, 1 })
    key.fsWaves = {
        NewWave(TC.host, cyan, 0, TC.WAVE_TIME, TC.WAVE_SCALE, 1),
        NewWave(TC.host, pink, TC.WAVE_DELAY, TC.WAVE2_TIME, TC.WAVE_SCALE, 1),
    }
    local ping = NewWave(TC.host, cyan, 0, TC.PING_TIME, TC.PING_SCALE, TC.PING_ALPHA)
    if ping.group then
        ping.group:SetLooping("REPEAT")
        local rest = ping.group:CreateAnimation("Alpha")
        rest:SetFromAlpha(0)
        rest:SetToAlpha(0)
        rest:SetStartDelay(TC.PING_TIME)
        rest:SetDuration(TC.PING_PERIOD - TC.PING_TIME)
    end
    key.fsPing = ping

    -- the jolt: the whole key nudged down and back
    local jg = NewGroup(key)
    if jg then
        local down = jg:CreateAnimation("Translation")
        down:SetOffset(0, -1)
        down:SetDuration(TC.JOLT_TIME * 0.25)
        down:SetOrder(1)
        local back = jg:CreateAnimation("Translation")
        back:SetOffset(0, 1)
        back:SetDuration(TC.JOLT_TIME * 0.75)
        back:SetOrder(2)
        key.fsJoltDown, key.fsJoltBack = down, back
    end
    key.fsJolt = jg

    key:SetScript("OnEnter", function(self) Tab.ShowTooltip(self) end)
    key:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    TC.key = key
end

-- Sizes and seats the key's pieces off the shoulder (design px x the layout scale), out of combat or in it: plain frames.
local function LayoutKey()
    local key, host = TC.key, TC.host
    if not key then return end
    local s = Scale()
    local btn = 38 * s
    local shoulder = FS.ClassShoulder
    if shoulder and shoulder.BlockSize then
        local _, _, edge = shoulder.BlockSize(TC.KEY)
        if type(edge) == "number" and edge > 0 then btn = edge end
    end
    key:SetSize(btn, btn)
    key:ClearAllPoints()
    local placed = false
    if shoulder and shoulder.SlotPoint then
        local ok, point, rel, relPoint, x, y = pcall(shoulder.SlotPoint, host, 1, 1, TC.KEY)
        if ok and point then
            key:SetPoint(point, rel, relPoint, x, y)
            placed = true
        end
    end
    if not placed then key:SetPoint("BOTTOMLEFT", host, "BOTTOMLEFT", 6 * s, 5 * s) end
    local FH = FS.FrameHelpers
    FH.SeatCutIcon(key)
    FH.SeatButtonCooldown(key)
    local top = FH.CooldownTopLevel and FH.CooldownTopLevel(key) or key:GetFrameLevel()
    key.fsOver:SetFrameLevel(top + 2)
    local unit = PixelUnit(key)
    if key.fsJoltDown then
        local px = TC.JOLT_PX * unit
        key.fsJoltDown:SetOffset(0, -px)
        key.fsJoltBack:SetOffset(0, px)
    end
    local band = key.fsBand
    band:ClearAllPoints()
    band:SetPoint("TOPLEFT", key, "TOPLEFT", TC.BAND_SIDE * s, -TC.BAND_TOP * s)
    band:SetPoint("TOPRIGHT", key, "TOPRIGHT", -TC.BAND_SIDE * s, -TC.BAND_TOP * s)
    band:SetHeight(TC.BAND_H * s)
    local ul = key.fsUnderline
    ul:ClearAllPoints()
    ul:SetPoint("TOPLEFT", key, "BOTTOMLEFT", TC.UL_INSET * s, -TC.UL_BELOW * s)
    ul:SetPoint("TOPRIGHT", key, "BOTTOMRIGHT", -TC.UL_INSET * s, -TC.UL_BELOW * s)
    ul:SetHeight(TC.UL_PX * unit)
    local level = top + 4
    for _, wave in ipairs(key.fsWaves) do
        wave.frame:ClearAllPoints()
        wave.frame:SetAllPoints(key)
        wave.frame:SetFrameLevel(level)
    end
    key.fsPing.frame:ClearAllPoints()
    key.fsPing.frame:SetAllPoints(key)
    key.fsPing.frame:SetFrameLevel(level)
end

-------------------------------------------------------------------------------
-- Painting
-------------------------------------------------------------------------------

local LOOKS = {
    ready = { ring = "COLOR_POWER", glow = TC.GLOW_READY, ul = "COLOR_POWER", icon = { 1, 1, 1 } },
    cool = { ring = "COLOR_BORDER", glow = TC.GLOW_IDLE, ul = "COLOR_BORDER", icon = { TC.COOL_DIM, TC.COOL_DIM, TC.COOL_DIM } },
    rage = { ring = "COLOR_RED", glow = TC.GLOW_IDLE, ul = "COLOR_RED", icon = { 1, 0.42, 0.42 }, word = "RAGE" },
    stance = { ring = "COLOR_MUTED", glow = 0, ul = nil, icon = { TC.STANCE_DIM, TC.STANCE_DIM, TC.STANCE_DIM },
        desat = true, ringA = 0.45, word = "STANCE" },
    unusable = { ring = "COLOR_MUTED", glow = 0, ul = nil, icon = { TC.STANCE_DIM, TC.STANCE_DIM, TC.STANCE_DIM },
        desat = true, ringA = 0.45 },
}
Tab.LOOKS = LOOKS

local function Motion()
    return Setting(SETTINGS.motion)
end

local function SetPing(on)
    local ping = TC.key and TC.key.fsPing
    if not (ping and ping.group) then return end
    if on and not ping.group:IsPlaying() then ping.group:Play()
    elseif not on and ping.group:IsPlaying() then ping.group:Stop() end
    if not on then ping.tex:SetAlpha(0) end
end

-- Paints `state` (a key of LOOKS). Texture, colour and text writes only: legal in combat.
local function PaintState(state)
    local key = TC.key
    local look = LOOKS[state]
    if not (key and look) then return end
    local was = TC.state
    TC.state = state
    local ring = Color(look.ring, { 1, 1, 1, 1 })
    local skin = key.fsSkin
    if skin and skin.border and skin.border.ring then
        skin.border.ring:SetVertexColor(ring[1], ring[2], ring[3], look.ringA or 1)
    end
    if skin and skin.glow then skin.glow:SetVertexColor(ring[1], ring[2], ring[3], look.glow) end
    local icon = key.icon
    if icon.SetDesaturated then icon:SetDesaturated(look.desat == true) end
    icon:SetVertexColor(look.icon[1], look.icon[2], look.icon[3])
    local ul = key.fsUnderline
    if look.ul then
        local c = Color(look.ul, ring)
        ul:SetVertexColor(c[1], c[2], c[3], 0.9)
        ul:Show()
    else
        ul:Hide()
    end
    if look.word then
        local c = state == "rage" and ring or Color("COLOR_MUTED", ring)
        key.fsWord:SetText(look.word)
        key.fsWord:SetTextColor(c[1], c[2], c[3], 1)
        key.fsWord:Show()
        key.fsBand:Show()
    else
        key.fsWord:Hide()
        key.fsBand:Hide()
    end
    local motion = Motion()
    if state == "ready" and was == "cool" and motion and key.fsArriveGroup then
        key.fsArriveGroup:Stop()
        key.fsArriveGroup:Play()
    end
    SetPing(state == "ready" and motion)
end

-- The fill: the engine's own, from the duration object with the GCD left out (SealBar.lua's path without the GCD swipe:
-- a tracker shows the clap's own cooldown only). A client that cannot run the fill gets the swipe of the whole cooldown.
local function UpdateCooldown()
    local key = TC.key
    if not key then return end
    local FH = FS.FrameHelpers
    local cooldown = key.cooldown
    local id = TC.spellID
    if not id then
        cooldown:Clear()
        cooldown:Hide()
        FH.ClearCooldownFill(key)
        return
    end
    local modern = C_Spell and C_Spell.GetSpellCooldownDuration
    if modern then
        if FH.HasCooldownFill(key) then
            local ok, obj = pcall(modern, id, true)
            if ok and not IsSecret(obj) and FH.SetCooldownFill(key, obj) then
                cooldown:Clear()
                cooldown:Hide()
                return
            end
        end
        FH.ClearCooldownFill(key)
        local ok, obj = pcall(modern, id)
        if ok and obj ~= nil and not IsSecret(obj) then
            cooldown:SetCooldownFromDurationObject(obj)
            cooldown:Show()
        else
            cooldown:Clear()
            cooldown:Hide()
        end
        return
    end
    local start, duration, enabled
    if C_Spell and C_Spell.GetSpellCooldown then
        local ok, info = pcall(C_Spell.GetSpellCooldown, id)
        if ok and type(info) == "table" and not IsSecret(info) then
            start, duration, enabled = info.startTime, info.duration, info.isEnabled
        end
    end
    FH.ApplyPlainCooldown(key, start, duration, enabled)
end

local function SetIcon()
    local key = TC.key
    local id = TC.spellID
    if not (key and id) then return end
    local tex
    if C_Spell and C_Spell.GetSpellTexture then
        local ok, t = pcall(C_Spell.GetSpellTexture, id)
        if ok and not IsSecret(t) then tex = t end
    end
    tex = tex or "Interface\\Icons\\Spell_Nature_ThunderClap"
    FS.FrameHelpers.SetSpellIcon(key.icon, tex)
end

function Tab.Paint(now)
    if not (TC.key and TC.host and TC.host:IsShown()) then return end
    local state = Tab.ReadState(now)
    if state then PaintState(state) end
end

-- The clap: waves, flash and jolt (motion on), and the ledger the combat read falls back on.
function Tab.OnCast(spellID, now)
    if IsSecret(spellID) or not IS_RANK[spellID] then return end
    TC.lastCast = now or Now()
    local key = TC.key
    if key and TC.host and TC.host:IsShown() and Motion() then
        for _, wave in ipairs(key.fsWaves) do
            if wave.group then
                wave.group:Stop()
                wave.group:Play()
            end
        end
        if key.fsFlashGroup then key.fsFlashGroup:Stop() key.fsFlashGroup:Play() end
        if key.fsJolt then key.fsJolt:Stop() key.fsJolt:Play() end
    end
    UpdateCooldown()
    Tab.Paint(TC.lastCast)
end

function Tab.ShowTooltip(owner)
    if not (GameTooltip and TC.spellID) then return end
    GameTooltip:SetOwner(owner, "ANCHOR_TOP")
    if GameTooltip.SetSpellByID and pcall(GameTooltip.SetSpellByID, GameTooltip, TC.spellID) then
        GameTooltip:Show()
        return
    end
    GameTooltip:SetText("Thunder Clap")
    GameTooltip:Show()
end

-------------------------------------------------------------------------------
-- The seat
-------------------------------------------------------------------------------

function Tab.HostPoint()
    local shoulder = FS.ClassShoulder
    if shoulder and shoulder.HostPoint then
        local ok, point, rel, relPoint, x, y = pcall(shoulder.HostPoint, TC.KEY)
        if ok and point then return point, rel, relPoint, x, y end
    end
    return nil
end

local function ApplyVisibility()
    local host = TC.host
    if not host then return end
    local want = TC.seated and Tab.Shown() or false
    host:SetShown(want)
    if want then
        UpdateCooldown()
        Tab.Paint()
    else
        SetPing(false)
        TC.state = nil
    end
end
Tab.ApplyVisibility = ApplyVisibility

local function SeatHost()
    local host = TC.host
    local point, rel, relPoint, x, y = Tab.HostPoint()
    if not point then
        TC.seated = false
        ApplyVisibility()
        return
    end
    host:ClearAllPoints()
    host:SetPoint(point, rel, relPoint, x, y)
    local s = Scale()
    host:SetSize(50 * s, 49 * s)
    if rel.GetFrameLevel then host:SetFrameLevel(rel:GetFrameLevel() + 5) end
    TC.seated = true
    ApplyVisibility()
end

local function Sync()
    if not TC.built then return end
    if InCombatLockdown() then
        TC.pendingSync = true
        return
    end
    TC.pendingSync = false
    local ok, err = pcall(SeatHost)
    if ok then ok, err = pcall(LayoutKey) end
    if not ok then WarnOnce("thunderclap_sync", "Thunder Clap tab update failed (" .. tostring(err) .. ")") end
end
Tab.Sync = Sync

-- The known rank changed (a level, a trainer): new icon, and the shoulder comes or goes.
local function Relearn()
    local id = ResolveSpell()
    if id == TC.spellID then return end
    TC.spellID = id
    SetIcon()
    if FS.ClassShoulder and FS.ClassShoulder.Refresh then pcall(FS.ClassShoulder.Refresh) end
    ApplyVisibility()
end
Tab.Relearn = Relearn

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Build()
    TC.host = CreateFrame("Frame", "FSThunderClapTab", UIParent)
    TC.host:SetFrameStrata("LOW")
    TC.host:Hide()
    BuildKey()
    TC.built = true
    if FS.ModuleSwitch then FS.ModuleSwitch.MarkBuilt("m.class") end
end

-- A ticker child of the host (a hidden tab has no OnUpdate): fast while it cools, so the ready edge lands on time.
local function Tick(self, dt)
    self.fsElapsed = (self.fsElapsed or 0) + dt
    local every = TC.state == "cool" and TC.TICK_FAST or TC.TICK_SLOW
    if self.fsElapsed < every then return end
    self.fsElapsed = 0
    local ok, err = pcall(Tab.Paint)
    if not ok then WarnOnce("thunderclap_tick", "Thunder Clap tab repaint failed (" .. tostring(err) .. ")") end
end

local function OnEvent(_, event, unit, _, spellID)
    if event == "UNIT_SPELLCAST_SUCCEEDED" then
        if IsSecret(unit) or unit ~= "player" then return end
        Tab.OnCast(spellID)
    elseif event == "SPELL_UPDATE_COOLDOWN" then
        UpdateCooldown()
        Tab.Paint()
    elseif event == "SPELL_UPDATE_USABLE" or event == "UPDATE_SHAPESHIFT_FORM" or event == "UNIT_POWER_UPDATE" then
        Tab.Paint()
    elseif event == "SPELLS_CHANGED" or event == "PLAYER_LEVEL_UP" then
        Relearn()
    elseif event == "PLAYER_ENTERING_WORLD" then
        Relearn()
        UpdateCooldown()
        ApplyVisibility()
    elseif event == "PLAYER_REGEN_ENABLED" then
        if TC.pendingSync then Sync() end
        Tab.Paint()
    end
end

local function Apply()
    if not Tab.Applies() then return end
    if not (FS.Theme and FS.FrameHelpers and FS.Layout) then return end
    local ok, err = pcall(Build)
    if not ok then
        WarnOnce("thunderclap_build", "Thunder Clap tab failed to build (" .. tostring(err) .. ")")
        return
    end
    local events = CreateFrame("Frame")
    local function reg(event, unitOnly)
        local registered
        if unitOnly then registered = pcall(events.RegisterUnitEvent, events, event, "player") end
        if not registered then pcall(events.RegisterEvent, events, event) end
    end
    reg("UNIT_SPELLCAST_SUCCEEDED", true)
    reg("UNIT_POWER_UPDATE", true)
    for _, event in ipairs({ "SPELL_UPDATE_COOLDOWN", "SPELL_UPDATE_USABLE", "UPDATE_SHAPESHIFT_FORM", "SPELLS_CHANGED",
        "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD", "PLAYER_REGEN_ENABLED" }) do
        reg(event)
    end
    events:SetScript("OnEvent", OnEvent)
    local ticker = CreateFrame("Frame", "FSThunderClapTicker", TC.host)
    ticker:SetScript("OnUpdate", Tick)
    TC.ticker = ticker

    if FS.Config and FS.Config.OnChange then
        FS.Config.OnChange(SETTINGS.enabled.key, function()
            if FS.ClassShoulder and FS.ClassShoulder.Refresh then pcall(FS.ClassShoulder.Refresh) end
            ApplyVisibility()
        end)
        FS.Config.OnChange(SETTINGS.motion.key, function()
            TC.state = nil
            Tab.Paint()
        end)
    end
    if FS.Layout.OnRescale then FS.Layout.OnRescale(Sync) end
    if FS.ActionBars and FS.ActionBars.OnGeometry then FS.ActionBars.OnGeometry(Sync) end

    TC.spellID = ResolveSpell()
    SetIcon()
    if FS.ClassShoulder and FS.ClassShoulder.Refresh then
        local shouldered, why = pcall(FS.ClassShoulder.Refresh)
        if not shouldered then WarnOnce("thunderclap_shoulder", "class shoulder failed (" .. tostring(why) .. ")") end
    end
    Sync()
end

-- Built at PLAYER_LOGIN, in combat too: nothing here is protected, and the seat waits for regen inside Sync.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    -- Module power (m.class): off, this tab builds nothing and listens for nothing.
    local MS = FS.ModuleSwitch
    if MS and not MS.On("m.class") then return end
    Apply()
end)
