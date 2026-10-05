-- Forever Synthwave: Gunsight cast info boxes (the boxes of pieces "you" and "tgt").
--
-- The two info boxes of the Gunsight HUD (mockups/gunsight-hud-v2-2026-10-02/
-- gunsight-hud-v2-2026-10-02.html, infoBox and castIcon, drawn by drawYour on BOXL and drawTarget on
-- BOXR): a 114 x 56 chamfered plate above each tape with a small caps header, two lines of text and a
-- 28 square spell icon tile on its inner side.
--
--   yours   header the character name (cyan, YOU as the fallback); line 1 the spell name (white, 14 image px,
--           shrunk to fit), line 2 the timer "0.9 / 2.5" (cyan, 18); the icon tile to the RIGHT of the
--           box; the channel tick counter "n/T" / "CUT" in the header row at the box's right end (not in
--           the mockup: the mockup has no counter, this is where the Stack A tab's counter now lives)
--   target  header TARGET; line 1 the unit name (white while it casts, muted between casts, 14),
--           a divider, line 2 the spell name (18); the icon tile to the LEFT of the box, only while
--           a cast is live; NO timer (target cast timing is secret, the mockup draws none). The box
--           edge, header, line 2, divider and tile edge are pink while the cast can be kicked and
--           steel while it cannot (flag through SetAlphaFromBoolean, see below)
--
-- NO STATE MACHINE HERE. CastBars.lua owns every cast rule. A box exposes the MEMBERS its bar table
-- needs (box.members = { icon, timer, tabName, tabTicks }) and GunsightTape.lua puts them into the
-- bar table it hands to FS.CastBars.SetView, so CastBars keeps writing through its existing paths
-- (S.icon:SetTexture, S.tabName:SetText, S.timer:SetFormattedText / SetText, S.tabTicks) and this file
-- reads no cast data, runs no OnUpdate and listens to one event pair (the target's unit name).
-- Three of the four members are small sink objects with the FontString / Texture methods CastBars
-- calls; a write that is a PLAIN empty string means "idle" (CastBars's GoIdle), anything else "live":
--   tabName   forwards to the FontString(s), shrinks plain text that is wider than the box, never
--             measures a secret (a fixed smaller size and a fixed width instead: the text clips),
--             and flips line 1's colour between live (white) and muted
--   timer     forwards, and at idle blanks line 2 (no "0.0 / total"); the target's is a null sink
--   icon      forwards, dims the player's tile at idle and hides the target's
-- A secret (spell name, unit name, flag, texture) only ever reaches SetText / SetTexture /
-- SetAlphaFromBoolean: it is type-checked (legal) and never compared, concatenated, measured or
-- upper-cased. The flag colouring needs no member of its own: the box adds its two colour frames
-- (box.fb.pink / box.fb.steel) to the lists the tape's shield stand-in drives.
--
-- VISIBILITY. YOUR box exists only while you cast: it is built hidden, a plain empty write through the name
-- sink (CastBars' GoIdle) hides the WHOLE box (plate, header, both lines, tile, tick counter), any other
-- name write shows it (a secret name included: the decision is the write path, a secret is never read), and
-- the INTERRUPTED look shows it and keeps it up until the next write clears it. THE TARGET's box is shown
-- only while the player has a target (FS.HasTarget, Theme.lua: a secret or unreadable UnitExists keeps it
-- shown), re-read on PLAYER_TARGET_CHANGED and PLAYER_ENTERING_WORLD; its cast state is untouched, only the
-- visuals hide. Both rules are Show/Hide of the box frame (a plain addon frame, never protected, no secure
-- child), legal in combat, and a rescale never calls Show. The piece toggles are independent: they fade the
-- tape piece frame above the box.
--
-- HEADER. Yours reads the character's name, `UnitName("player")` upper-cased and shrunk to fit the header
-- width (the box minus C.HEAD_RESERVE kept for the tick counter), falling back to YOU for nil, "Unknown", an
-- empty string or a secret; refreshed on PLAYER_LOGIN / PLAYER_ENTERING_WORLD because the name is not always
-- ready at build. The target's header stays TARGET.
--
-- AT REST (when a box is shown but idle: the target's only): the plate and steel edge, the unit's name muted,
-- no spell and no tile.
--
-- STRUCTURE (one build per box, Layout re-seats and re-sizes on FS.Layout.OnRescale, nothing is created
-- again): box.frame (child of the tape's piece frame, so the `you` / `tgt` piece toggles fade it;
-- filling anchors.boxL / boxR) holds the plate, line 1, the tick counter, one TONE frame per colour
-- (edge stroke, header, line 2, the target's divider) and the icon TILE (plate, icon, one tile-tone
-- frame per colour with the tile edge). A tone is a frame so SetAlphaFromBoolean lands on a frame, as
-- it already does for the tape's own layers. Plain frames only, nothing protected.
--
-- UNVERIFIED IN GAME (needs an eyeball): the text baselines (C.DESCENT is an estimate of the font's
-- descent, as GunsightFrame's LABEL_DESCENT), line 2's clip for a secret name (the text is cut at
-- the width, or overflows if the client does not clip), the chamfer (baked 6, the mockup 8 image px),
-- the box edge without the mockup's glow halo, the tick counter in the header row, the "0.9 / 2.5"
-- timer with its muted " / total" (CastBars' colour escape; the mockup colours the whole line), and
-- the target's idle look, the INTERRUPTED red and flicker timing against the mockup's (the box edge snaps to red
-- where the mockup eases over .22 s; the timer's muted " / total" stays muted).
--
-- INTERRUPTED. CastBars calls bar.onVerdict(bar, "interrupt") (pcall'd, view bars only) after it froze the
-- readout; members.onVerdict shows the mockup's outage look: plain "INTERRUPTED" on line one in red, a
-- third (red) tone frame in place of the pink / steel / cyan one (box edge, header, line 2, divider, tile
-- edge; NOT in the box.fb lists the flag drives), the player's icon dimmed and gray, and the box alpha
-- flickering through ONE Alpha AnimationGroup (no OnUpdate). ANY later write through the name / timer
-- sinks (GoIdle, the next cast; the target's timer is a null sink, so only its name sink) drops it and
-- stops the flicker. A success has no look in the box (the
-- mockup's hold only pops the timer's colour), so CastBars sends no "succeed".
--
-- FONTS. Every FontString gets its font (ApplyMono at the base size) at creation: SetText on one without
-- a font throws "Font not set", which would land in pcall(BuildBox) and silently drop the box.

local _, FS = ...

local Gunsight = FS.Gunsight
if type(Gunsight) ~= "table" or type(Gunsight.OnReady) ~= "function" then return end

local GunsightBoxes = {}
FS.GunsightBoxes = GunsightBoxes

local G = Gunsight.G
local ui = Gunsight.ui
local NAME = "ForeverSynthwaveGunsightBox_"
local IsSecret = FS.IsSecret or function() return false end

-------------------------------------------------------------------------------
-- Constants (mockup name in the comment; gunsightboxes-harness.py re-reads every one from the HTML)
-------------------------------------------------------------------------------

local C = {
    CHAMFER = 8,                                     -- chamfer(b.x, b.y, b.w, b.h, 8) (the baked cut is 6)
    FILL = { 13 / 255, 6 / 255, 32 / 255, 0.85 * 0.82 },  -- rgba(13,6,32,.85) under A(.82)
    STROKE_A = 1,                                    -- A(a), a = 1
    PAD = 7,                                         -- text x = b.x + 7, wmax = b.w - 14
    L1_SIZE = 14, L1_Y = 23,                         -- fs = o.fs1 || 14, text(l1, b.x + 7, b.y + 23, ...)
    L2_SIZE = 18, L2_Y = 45,                         -- f2 = 18, text(l2, b.x + 7, b.y + 45, ...)
    DIV_Y = 29, DIV_A = 0.4,                         -- hline(b.y + 29, b.x + 7, b.x + b.w - 7, ..., .4 * a)
    HEAD_SIZE = 11, HEAD_DY = 14, HEAD_A = 0.9,      -- header(s, x, BOX.y - 14, col, .9), text size 11
    HEAD_RESERVE = 26,                               -- image px kept at the header's right end for the tick
                                                     -- counter (not in the mockup)
    CI = 28, CIC = 5, CIG = 6,                       -- castIcon: tile size, chamfer, gap to the box
    CI_FILL_A = 0.9 * 0.85, CI_STROKE_A = 0.9,       -- A(.85 * a) rgba(13,6,32,.9); A(.9 * a) stroke
    ICON_CROP = 0.08,                                -- ICON_CROP, per side
    IDLE_ICON_A = 0.45,                              -- (idle ? .45 : 1) * flick
    DESCENT = 0.22,                                  -- em from a baseline to the bottom of its line (estimate)
    SECRET_L2_SIZE = 14,                             -- line 2's image px for a secret name (never measured)
    MIN_FONT = 6,                                    -- smallest size a fit may pick
    -- INTERRUPTED look (drawYour, st.mode == 'outage'): the flicker steps of the box alpha, 0.05 s each
    -- ((st.tau - .2) / .35 * 7 over [.5, 1, .35, .85, .3, .7, .45]) after a 0.2 s delay, then back to 1.
    FLICK_DELAY = 0.2, FLICK_STEP = 0.05,
    FLICK = { 0.5, 1, 0.35, 0.85, 0.3, 0.7, 0.45 },
}
GunsightBoxes.C = C

local BG = { 13 / 255, 6 / 255, 32 / 255, 1 }          -- --bg #0d0620
local colors = {
    cyan = (FS.Theme and FS.Theme.COLOR_POWER) or { 0.133, 0.878, 1, 1 },        -- --cyan #22e0ff
    pink = (FS.Theme and FS.Theme.COLOR_HEALTH) or { 1, 0.18, 0.592, 1 },        -- --pink #ff2e97
    steel = (FS.Theme and FS.Theme.COLOR_STEEL) or { 0.5529, 0.5765, 0.651, 1 }, -- --steel #8d93a6
    red = (FS.Theme and FS.Theme.COLOR_RED) or { 1, 0.2314, 0.3059, 1 },         -- --red #ff3b4e (K.red)
    white = { 0xf3 / 255, 0xfb / 255, 1, 1 },                                    -- --white #f3fbff
    muted = { 0x9d / 255, 0x93 / 255, 0xc4 / 255, 1 },                           -- --muted #9d93c4
    bg = BG,
}
GunsightBoxes.colors = colors

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

local function HasMethod(obj, name)
    return obj ~= nil and type(obj[name]) == "function"
end

local function FillParent(frame, parent)
    frame:SetPoint("TOPLEFT", parent, "TOPLEFT", 0, 0)
    frame:SetPoint("BOTTOMRIGHT", parent, "BOTTOMRIGHT", 0, 0)
end

local function Crisp(tex)
    if tex.SetSnapToPixelGrid then pcall(tex.SetSnapToPixelGrid, tex, true) end
    if tex.SetTexelSnappingBias then pcall(tex.SetTexelSnappingBias, tex, 0) end
end

local function Paint(fs, color)
    fs:SetTextColor(color[1], color[2], color[3], color[4] or 1)
end

local function FontSize(imagePx)
    return math.max(C.MIN_FONT, math.floor(ui(imagePx) + 0.5))
end

-- Colour with a different alpha, for a texture's vertex colour.
local function WithAlpha(color, a)
    return { color[1], color[2], color[3], a }
end

-- A plain, non-secret empty string: the only write that means "idle". Never compares a secret.
local function IsPlainEmpty(v)
    if IsSecret(v) then return false end
    return v == nil or v == ""
end

-------------------------------------------------------------------------------
-- Text lines: one or two FontStrings (one per colour) that carry the same text and fit together
-------------------------------------------------------------------------------

-- line = { fonts, baseImg / secretImg (image px), wmax (UI units), size (applied), text (last PLAIN
-- text or nil), secretNow (the text now shown is a secret), colors (one per FontString) }
local function NewLine(fonts, baseImg, secretImg)
    return { fonts = fonts, baseImg = baseImg, secretImg = secretImg, colors = {}, size = nil, text = nil, secretNow = false }
end

local function ApplySize(line, size)
    if line.size == size then return end
    line.size = size
    for i, fs in ipairs(line.fonts) do
        FS.Theme.ApplyMono(fs, size, line.colors[i] or colors.white)
        Paint(fs, line.colors[i] or colors.white)
    end
end

local function SetLineColor(line, i, color)
    line.colors[i] = color
    Paint(line.fonts[i], color)
end

-- Picks the size for the text now in the line's FontStrings. A plain string is measured (at the
-- size it is drawn at, scaled back to the base) and shrunk to fit wmax; a secret is NEVER measured
-- (GetStringWidth on a secret is not allowed) and gets the fixed smaller size, its width fixed so it
-- clips instead of overflowing.
local function FitLine(line, text)
    local base = FontSize(line.baseImg)
    local size = base
    line.secretNow = false
    if IsSecret(text) then
        line.text = nil
        line.secretNow = true
        if line.secretImg then size = FontSize(line.secretImg) end
    elseif type(text) == "string" and text ~= "" then
        line.text = text
        local fs = line.fonts[1]
        local ok, w = pcall(fs.GetStringWidth, fs)
        if ok and type(w) == "number" and not IsSecret(w) and w > 0 and line.size and line.size > 0 then
            local atBase = w * base / line.size
            if atBase > line.wmax then
                size = math.max(C.MIN_FONT, math.floor(base * line.wmax / atBase))
            end
        end
    else
        line.text = nil
    end
    ApplySize(line, size)
end

-- A rescale re-runs the fit for the text the line holds (a secret keeps its fixed size).
local function RefitLine(line)
    if line.secretNow then
        ApplySize(line, FontSize(line.secretImg or line.baseImg))
    else
        FitLine(line, line.text or "")
    end
end

-- Writes `text` into every FontString of the line (errors propagate like a plain FontString's) and fits.
local function WriteLine(line, text)
    for _, fs in ipairs(line.fonts) do fs:SetText(text) end
    FitLine(line, text)
end

-------------------------------------------------------------------------------
-- Build pieces
-------------------------------------------------------------------------------

local function SolidTexture(parent, color, alpha, layer)
    local tex = parent:CreateTexture(nil, layer or "ARTWORK")
    tex:SetColorTexture(color[1], color[2], color[3], alpha or color[4] or 1)
    Crisp(tex)
    return tex
end

-- A FontString with its font already set: the client throws "Font not set" for SetText on one that has
-- none, and the throw would land in pcall(BuildBox) and silently drop the box. Every FontString this file
-- makes gets the mono font at its base size here, before anything is written to it.
local function NewFont(parent, imagePx, color)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    FS.Theme.ApplyMono(fs, FontSize(imagePx), color or colors.white)
    fs:SetJustifyH("LEFT")
    if HasMethod(fs, "SetJustifyV") then fs:SetJustifyV("BOTTOM") end
    fs:SetWordWrap(false)
    if HasMethod(fs, "SetMaxLines") then fs:SetMaxLines(1) end
    if HasMethod(fs, "SetNonSpaceWrap") then fs:SetNonSpaceWrap(false) end
    fs:SetText("")
    return fs
end

-- The state of a box's two looks. Colour flips only on a real change.
local function SetNameLive(box, live)
    if box.nameLive == live then return end
    box.nameLive = live
    SetLineColor(box.lineOne, 1, live and colors.white or colors.muted)
end

local function SetTimerLive(box, live)
    if box.timerLive == live then return end
    box.timerLive = live
    SetLineColor(box.lineTwo, 1, live and colors.cyan or colors.muted)
end

local function SetTileLive(box, live)
    if box.isTarget then
        box.tile:SetShown(live)
    else
        box.tile:SetAlpha(live and 1 or C.IDLE_ICON_A)
        -- the mockup's idle tile is a gray flag as well as dimmed
        if HasMethod(box.icon, "SetDesaturated") then box.icon:SetDesaturated(not live) end
    end
end

-- Show / Hide of the whole box. The box frame is a plain child of the tape piece frame: legal in combat.
local function SetBoxShown(box, on)
    if box.retired then return end
    box.frame:SetShown(on and true or false)
end

-- The target's box follows the target alone.
local function RefreshTargetShown(box)
    SetBoxShown(box, FS.HasTarget())
end

-------------------------------------------------------------------------------
-- Your header: the character's name
-------------------------------------------------------------------------------

-- The player's name when it is real: nil for a missing name, an empty string, "Unknown" (the client's
-- placeholder very early on) and a secret (never inspected past IsSecret).
local function ReadPlayerName()
    if type(UnitName) ~= "function" then return nil end
    local name = UnitName("player")
    if IsSecret(name) or type(name) ~= "string" or name == "" then return nil end
    if name == "Unknown" or name == _G.UNKNOWNOBJECT then return nil end
    return name
end

local function RefreshPlayerName(box)
    if box.retired or box.isTarget or not box.headLine then return end
    local name = ReadPlayerName()
    WriteLine(box.headLine, name and name:upper() or "YOU")
end

-------------------------------------------------------------------------------
-- The target's unit name (line 1): the only thing a box reads itself
-------------------------------------------------------------------------------

local function ReadTargetName()
    local exists = UnitExists and UnitExists("target")
    if not IsSecret(exists) and not exists then return "" end
    local name
    if type(FS.GetFullUnitName) == "function" then
        name = FS.GetFullUnitName("target")
    elseif UnitName then
        name = UnitName("target")
    end
    return name
end

-- Skipped while the INTERRUPTED look is up (it owns line one); ClearVerdict refreshes the name after.
local function RefreshTargetName(box)
    if box.retired or box.verdict then return end
    local name = ReadTargetName()
    if IsSecret(name) then
        WriteLine(box.lineOne, name)                 -- SetText only; never upper-cased
    elseif type(name) == "string" then
        WriteLine(box.lineOne, name:upper())
    else
        WriteLine(box.lineOne, "")
    end
end

-- Takes the unit-name listener down: events unregistered and the handler dropped. Shared by every path that
-- abandons a box (a failing build step, a failing rescale registration, Retire), so none of them can leave
-- one live. Safe on a box that never had one.
local function Unlisten(box)
    local events = box.events
    if not events then return end
    events:UnregisterAllEvents()
    events:SetScript("OnEvent", nil)
end

-------------------------------------------------------------------------------
-- The INTERRUPTED look (mockup drawYour, outage): plain "INTERRUPTED" on line one, the box edge, header,
-- line 2 and tile edge in red (a third tone frame, NOT in the pink / steel lists the interruptible flag
-- drives), the box alpha flickering through one Alpha AnimationGroup. CastBars tells the box through the
-- bar table's onVerdict; a later write through the name sink (GoIdle, the next cast) drops it, and for YOUR box
-- through the timer sink too (the target's timer is a null sink, see BuildMembers).
-------------------------------------------------------------------------------

local function ClearVerdict(box)
    if not box.verdict then return end
    box.verdict = false
    if box.flicker then box.flicker:Stop() end
    for key, tone in pairs(box.tones) do tone:SetShown(key ~= "red") end
    for key, tone in pairs(box.tileTones) do tone:SetShown(key ~= "red") end
    SetLineColor(box.lineOne, 1, box.nameLive and colors.white or colors.muted)
    if box.isTarget then RefreshTargetName(box) end      -- line one is the unit name again
end

local function ShowVerdict(box)
    if box.retired then return end                       -- a stale bar table can still call the hook
    box.verdict = true
    if not box.isTarget then SetBoxShown(box, true) end   -- the look is shown even over a hidden idle box
    for key, tone in pairs(box.tones) do tone:SetShown(key == "red") end
    for key, tone in pairs(box.tileTones) do tone:SetShown(key == "red") end
    WriteLine(box.lineOne, "INTERRUPTED")
    SetLineColor(box.lineOne, 1, colors.red)
    if not box.isTarget then SetTileLive(box, false) end  -- the mockup dims the icon of an interrupted cast
    if box.flicker then
        box.flicker:Stop()
        box.flicker:Play()
    end
end

-- The members CastBars writes to (see the header).
local function BuildMembers(box)
    local members = {}

    -- tabName: line 1 for yours, line 2 (both colour copies) for the target.
    local nameLine = box.isTarget and box.lineTwo or box.lineOne
    local name = {}
    function name.SetText(_, text)
        if box.retired then return end                   -- a stale bar table can still write the sink
        ClearVerdict(box)
        WriteLine(nameLine, text)                        -- at rest (a plain "") the line is blank, no stale spell
        SetNameLive(box, not IsPlainEmpty(text))
        -- Yours: the idle write hides the whole box, any other write (a secret name too) shows it.
        if not box.isTarget then SetBoxShown(box, not IsPlainEmpty(text)) end
    end
    function name.GetStringWidth()
        return nameLine.fonts[1]:GetStringWidth()
    end
    members.tabName = name

    -- timer: yours is the line 2 FontString, the target's goes nowhere.
    local timer = {}
    if box.isTarget then
        -- A true null sink. It does not clear the INTERRUPTED look: every path that writes the timer
        -- (GoIdle, the next cast's start) writes the name sink in the same call, and that one clears it.
        function timer.SetText() end
        function timer.SetFormattedText() end
    else
        -- Line 2 has one FontString per colour (the base and the red copy): every one carries the text.
        local fonts = box.lineTwo.fonts
        function timer.SetText(_, text)
            if box.retired then return end               -- a stale bar table can still write the sink
            ClearVerdict(box)
            if IsPlainEmpty(text) then
                for _, fs in ipairs(fonts) do fs:SetText("") end   -- at rest the timer line is blank
                SetTimerLive(box, false)
            else
                for _, fs in ipairs(fonts) do fs:SetText(text) end
                SetTimerLive(box, true)
            end
        end
        function timer.SetFormattedText(_, fmt, ...)
            if box.retired then return end               -- a stale bar table can still write the sink
            ClearVerdict(box)
            for _, fs in ipairs(fonts) do fs:SetFormattedText(fmt, ...) end
            SetTimerLive(box, true)
        end
    end
    members.timer = timer

    -- icon: forwards to the texture; a nil texture is the idle write (type() is legal on a secret).
    local icon = {}
    function icon.SetTexture(_, tex)
        if box.retired then return end                   -- a stale bar table can still write the sink
        box.icon:SetTexture(tex)
        SetTileLive(box, type(tex) ~= "nil")
    end
    members.icon = icon

    members.tabTicks = box.ticks

    -- CastBars calls this (pcall'd) with "interrupt" after it froze the readout. Only the interrupt has a
    -- look in the mockup's box; a success has none, so CastBars never sends one.
    function members.onVerdict(_, kind)
        if kind == "interrupt" then ShowVerdict(box) end
    end
    return members
end

-- One colour's frame of the box: edge, header, line 2 and (target) the divider.
local function BuildTone(box, key, color)
    local Theme = FS.Theme
    local tone = CreateFrame("Frame", nil, box.frame)
    FillParent(tone, box.frame)
    box.tones[key] = tone
    box.stroke[key] = Theme.AddCut2Texture(tone, Theme.SLICE_CUT2_OUTLINE_TEXTURE, WithAlpha(color, C.STROKE_A), "BORDER")
    local head = tone:CreateFontString(nil, "OVERLAY")
    FS.Theme.ApplyMono(head, FontSize(C.HEAD_SIZE), color)       -- a font before the first SetText
    head:SetText(box.isTarget and "TARGET" or "YOU")
    head:SetAlpha(C.HEAD_A)
    box.head[key] = head
    box.headFonts[#box.headFonts + 1] = head
    local l2 = NewFont(tone, C.L2_SIZE, color)
    box.l2[key] = l2
    if box.isTarget then
        box.divider[key] = SolidTexture(tone, color, C.DIV_A)
    end
    if key == "red" then tone:Hide() end                         -- only while INTERRUPTED shows
    return tone
end

-- The tile's own colour frame: its edge.
local function BuildTileTone(box, key, color)
    local Theme = FS.Theme
    local tone = CreateFrame("Frame", nil, box.tile)
    FillParent(tone, box.tile)
    box.tileTones[key] = tone
    Theme.AddCut2Texture(tone, Theme.SLICE_CUT2_OUTLINE_TEXTURE, WithAlpha(color, C.CI_STROKE_A), "BORDER")
    if key == "red" then tone:Hide() end
    return tone
end

-------------------------------------------------------------------------------
-- Layout (build and every rescale: re-seats and re-sizes, creates nothing)
-------------------------------------------------------------------------------

local function SeatBottom(fs, point, rel, relPoint, x, y)
    fs:ClearAllPoints()
    fs:SetPoint(point, rel, relPoint, x, y)
end

local function Layout(box)
    local k = ui(1)
    local g = box.geom
    local frame = box.frame
    local wmax = (g.w - 2 * C.PAD) * k
    local left = not box.isTarget

    -- Line 1 and line 2: baseline at the mockup's y, left at the padding.
    box.lineOne.wmax, box.lineTwo.wmax = wmax, wmax
    box.l1:SetWidth(wmax)
    SeatBottom(box.l1, "BOTTOMLEFT", frame, "TOPLEFT", C.PAD * k, -(C.L1_Y + C.L1_SIZE * C.DESCENT) * k)
    for _, fs in pairs(box.l2) do
        fs:SetWidth(wmax)
        SeatBottom(fs, "BOTTOMLEFT", frame, "TOPLEFT", C.PAD * k, -(C.L2_Y + C.L2_SIZE * C.DESCENT) * k)
    end

    -- Header row: the name of the side at the box's outer end, the tick counter at the other.
    local headY = (C.HEAD_DY - C.HEAD_SIZE * C.DESCENT) * k
    local headSize = FontSize(C.HEAD_SIZE)
    for key, fs in pairs(box.head) do
        -- Yours is sized and fitted through box.headLine below (the name varies); the target's is fixed text.
        if not box.headLine then FS.Theme.ApplyMono(fs, headSize, box.toneColors[key]) end
        if left then
            SeatBottom(fs, "BOTTOMLEFT", frame, "TOPLEFT", 0, headY)
        else
            SeatBottom(fs, "BOTTOMRIGHT", frame, "TOPRIGHT", 0, headY)
        end
    end
    FS.Theme.ApplyMono(box.ticks, headSize, colors.white)
    if left then
        SeatBottom(box.ticks, "BOTTOMRIGHT", frame, "TOPRIGHT", 0, headY)
    else
        SeatBottom(box.ticks, "BOTTOMLEFT", frame, "TOPLEFT", 0, headY)
    end

    -- Target divider: one line, padded.
    for _, d in pairs(box.divider) do
        d:ClearAllPoints()
        d:SetPoint("TOPLEFT", frame, "TOPLEFT", C.PAD * k, -C.DIV_Y * k)
        d:SetSize((g.w - 2 * C.PAD) * k, k)
    end

    -- Icon tile: on the box's inner side, centred on its height.
    local tile = box.tile
    tile:ClearAllPoints()
    local y = -((g.h - C.CI) / 2) * k
    if left then
        tile:SetPoint("TOPLEFT", frame, "TOPRIGHT", C.CIG * k, y)
    else
        tile:SetPoint("TOPRIGHT", frame, "TOPLEFT", -C.CIG * k, y)
    end
    tile:SetSize(C.CI * k, C.CI * k)
    local ins = math.max(1, math.ceil(C.CIC / 2)) * k
    box.icon:ClearAllPoints()
    box.icon:SetPoint("TOPLEFT", tile, "TOPLEFT", ins, -ins)
    box.icon:SetPoint("BOTTOMRIGHT", tile, "BOTTOMRIGHT", -ins, ins)

    -- Type sizes: the line fits run again for the text they hold; the line colours survive.
    -- (Yours line 2 is the timer, whose numbers may be secret: it never holds a plain text, so it keeps
    -- line 2's size.)
    -- The fonts go back to the new base size first, so the fit measures the text at the base size (a plain
    -- name that no longer fits after a rescale shrinks again at once, and one that now fits grows back at
    -- once, not at its next write). line.size always holds the size last applied, so ApplySize's early
    -- return only skips a font that is already there.
    if box.headLine then box.headLine.wmax = (g.w - C.HEAD_RESERVE) * k end
    for _, line in ipairs({ box.lineOne, box.lineTwo, box.headLine }) do
        ApplySize(line, FontSize(line.baseImg))
        RefitLine(line)
    end
end

-------------------------------------------------------------------------------
-- Build
-------------------------------------------------------------------------------

-- The flicker: a delay at alpha 1, then the mockup's seven steps as flat Alpha animations in order, one
-- group on the box frame (no OnUpdate). The group ends back at the frame's own alpha, the mockup's flick 1.
-- nil when the client has no animation groups (the red look then shows without the flicker).
local function BuildFlicker(frame)
    if not HasMethod(frame, "CreateAnimationGroup") then return nil end
    local group = frame:CreateAnimationGroup()
    local order = 0
    local function step(alpha, seconds)
        order = order + 1
        local a = group:CreateAnimation("Alpha")
        a:SetOrder(order)
        a:SetDuration(seconds)
        a:SetFromAlpha(alpha)
        a:SetToAlpha(alpha)
    end
    step(1, C.FLICK_DELAY)
    for _, alpha in ipairs(C.FLICK) do step(alpha, C.FLICK_STEP) end
    return group
end

local function BuildBox(spec)
    local Theme = FS.Theme
    local isTarget = spec.isTarget and true or false
    local box = {
        key = spec.key, anchor = spec.anchor, isTarget = isTarget,
        geom = isTarget and G.BOXR or G.BOXL,
        tones = {}, tileTones = {}, stroke = {}, head = {}, l2 = {}, divider = {},
        toneColors = {}, fb = { pink = {}, steel = {} }, headFonts = {},
    }

    local frame = CreateFrame("Frame", NAME .. spec.key, spec.parent)
    box.frame = frame
    FillParent(frame, spec.anchor)
    spec.built[#spec.built + 1] = frame

    -- Plate and line 1 (shared by the colours).
    Theme.AddCut2Texture(frame, Theme.SLICE_CUT2_FILL_TEXTURE, C.FILL, "BACKGROUND", 0)
    box.l1 = NewFont(frame, C.L1_SIZE, colors.muted)
    box.ticks = frame:CreateFontString(nil, "OVERLAY")
    FS.Theme.ApplyMono(box.ticks, FontSize(C.HEAD_SIZE), colors.white)
    box.ticks:SetText("")
    box.ticks:Hide()

    -- The icon tile (shared plate and icon, then one edge frame per colour).
    local tile = CreateFrame("Frame", nil, frame)
    box.tile = tile
    Theme.AddCut2Texture(tile, Theme.SLICE_CUT2_FILL_TEXTURE, WithAlpha(BG, C.CI_FILL_A), "BACKGROUND", 0)
    box.icon = tile:CreateTexture(nil, "ARTWORK")
    box.icon:SetTexCoord(C.ICON_CROP, 1 - C.ICON_CROP, C.ICON_CROP, 1 - C.ICON_CROP)

    -- The colour frames.
    local tones = isTarget and { { "pink", colors.pink }, { "steel", colors.steel }, { "red", colors.red } }
        or { { "base", colors.cyan }, { "red", colors.red } }
    for _, t in ipairs(tones) do
        local key, color = t[1], t[2]
        box.toneColors[key] = color
        local tone = BuildTone(box, key, color)
        local tileTone = BuildTileTone(box, key, color)
        if key == "pink" or key == "steel" then
            local list = box.fb[key]
            list[#list + 1] = tone
            list[#list + 1] = tileTone
        end
    end

    -- Lines. Line 1 has one FontString; line 2 one per colour. A line's colours: line 1 muted until
    -- a cast, line 2 in its colour (the player's timer flips between cyan and muted).
    box.lineOne = NewLine({ box.l1 }, C.L1_SIZE)
    box.lineOne.colors[1] = colors.muted
    local twoFonts, i = {}, 0
    for _, t in ipairs(tones) do
        i = i + 1
        twoFonts[i] = box.l2[t[1]]
    end
    box.lineTwo = NewLine(twoFonts, C.L2_SIZE, isTarget and C.SECRET_L2_SIZE or nil)
    i = 0
    for _, t in ipairs(tones) do
        i = i + 1
        box.lineTwo.colors[i] = (t[1] == "red" and colors.red) or (isTarget and t[2] or colors.muted)
    end
    box.nameLive, box.timerLive = false, false
    if not isTarget then
        -- Yours: the header is the character's name, fitted like the other plain text (one FontString per tone).
        box.headLine = NewLine(box.headFonts, C.HEAD_SIZE)
        local i2 = 0
        for _, t in ipairs(tones) do
            i2 = i2 + 1
            box.headLine.colors[i2] = t[2]
        end
    end
    box.flicker = BuildFlicker(frame)

    box.members = BuildMembers(box)
    box.regions = {
        icon = box.icon, ticks = box.ticks,
        name = isTarget and box.l2.pink or box.l1,
        timer = (not isTarget) and box.l2.base or nil,
    }

    -- Rest look: the target has no tile between casts, yours a dimmed empty one.
    SetTileLive(box, false)
    Layout(box)

    if isTarget then
        RefreshTargetName(box)
        RefreshTargetShown(box)
    else
        RefreshPlayerName(box)
        frame:Hide()                                 -- yours exists only while a cast is live
    end

    -- The unit-name listener is the second to last step: a build that throws earlier never leaves it live on a box
    -- that was hidden, and one that fails inside this step unregisters what it had registered. (A box that built
    -- whole and is dropped later by its caller goes through GunsightBoxes.Retire.)
    local events = CreateFrame("Frame", nil, frame)
    box.events = events
    local okEvents, errEvents = pcall(function()
        if isTarget then
            events:RegisterEvent("PLAYER_TARGET_CHANGED")
            events:RegisterEvent("PLAYER_ENTERING_WORLD")        -- as the tape, the dots and the horizon re-read it
            if not pcall(events.RegisterUnitEvent, events, "UNIT_NAME_UPDATE", "target") then
                events:RegisterEvent("UNIT_NAME_UPDATE")
            end
            events:SetScript("OnEvent", function()
                RefreshTargetName(box)
                RefreshTargetShown(box)
            end)
        else
            -- the character name is not always ready at build
            events:RegisterEvent("PLAYER_LOGIN")
            events:RegisterEvent("PLAYER_ENTERING_WORLD")
            events:SetScript("OnEvent", function() RefreshPlayerName(box) end)
        end
    end)
    if not okEvents then
        Unlisten(box)
        error(errEvents, 0)
    end

    -- The rescale callback is the LAST step, so a box dropped by a failure above never keeps a Layout
    -- callback (a registered callback cannot be removed). If registering itself throws, the listener
    -- goes down with the box. A box retired later keeps the callback but it does nothing (box.retired).
    if FS.Layout and FS.Layout.OnRescale then
        local okRescale, errRescale = pcall(FS.Layout.OnRescale, function()
            if not box.retired then Layout(box) end
        end)
        if not okRescale then
            Unlisten(box)
            error(errRescale, 0)
        end
    end
    return box
end

-- Takes a built box out of service for a caller that drops it after Build returned (GunsightTape, when a later
-- build step fails): hidden, the unit-name listener down, the flicker stopped, and the rescale callback (which
-- Layout.OnRescale cannot unregister) turned into a no-op by the retired flag. Idempotent, never throws.
function GunsightBoxes.Retire(box)
    if type(box) ~= "table" or box.retired then return end
    box.retired = true
    pcall(Unlisten, box)
    if box.flicker then pcall(box.flicker.Stop, box.flicker) end
    if box.frame then pcall(box.frame.Hide, box.frame) end
end

-- Builds one box. spec = { key, parent (the tape's piece frame), anchor (boxL / boxR), isTarget }.
-- Returns the box, or nil and a reason (whatever was built is hidden; nothing is registered).
function GunsightBoxes.Build(spec)
    if type(spec) ~= "table" or not spec.parent or not spec.anchor or not spec.key then
        return nil, "bad spec"
    end
    spec = { key = spec.key, parent = spec.parent, anchor = spec.anchor, isTarget = spec.isTarget, built = {} }
    local ok, box = pcall(BuildBox, spec)
    if ok then return box end
    for _, frame in ipairs(spec.built) do frame:Hide() end
    return nil, tostring(box)
end
