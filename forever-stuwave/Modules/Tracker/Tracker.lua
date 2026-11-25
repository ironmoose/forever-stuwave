-- Forever STUwave: Tracker
-- UNVALIDATED in-game: no /fstack or visual check done yet.
--
-- THE MANIFEST SPINE (mockups/tracker-2026-11-12.html, Geometry A). The tracker is one cut panel behind the whole
-- container strip, with the approved stuwave://objectives band in the container's own 32 px header strip (the 38 px of
-- topModulePadding Blizzard reserves above the first module), a single collapse control (the band's pink minus), module
-- headers as quiet sub-heads (diamond, mono lowercase label, rule), and each quest a station on a spine: its marker is
-- the node, a 2 px spine runs down behind its rows, each objective is a tick off it, the spine charges cyan to the last
-- finished objective (amber when the quest is ready to turn in, dim pink when it failed), and the row washes on hover,
-- press and while it is the followed quest. Collapsed, the panel is exactly the 24 px bar "quests (n/40)" with one tick
-- per quest (amber when ready, pink when failed), an amber LED while any quest is ready, and a pink edge on hover; the
-- minus and plus are the same two bars. Expanding wipes a shutter off the panel.
--
-- Every piece is our own region or frame anchored to stock frames. Blizzard's frames get alpha holds, post-hooks and
-- reads only; no script, attribute, parent, size or layout field is written (topModulePadding and the module fields are
-- only read: they are what Blizzard's layout code reads, the classic tracker taint path). The stock NineSlice is held at
-- alpha 0 for good, since the container writes its alpha (SetBackgroundAlpha) and a stale full-height NineSlice was the
-- source of the leftover backdrop under a collapsed tracker.
--
-- LEFT OUT (computed or invented in the mockup, or a restyle of internals nobody has verified in game):
--   * the band's "3/9 done" chip and the module count chips (computed counts the stock tracker does not show);
--   * per-module accent colours (every module wears the one cyan);
--   * rails for rows that have no quest marker (achievements, scenario, bonus, profession recipes): their rows stay
--     stock, only their module header is the sub-head;
--   * the dashed pink spine of a failed quest (a solid dim pink one stands in), the spine's top-to-bottom charge on
--     expand, objective pips and counters, the progress-bar and timer-bar restyle, the item button corner masks, and
--     the distance and zone line;
--   * the stuwave://timers fuse lanes (QuestTimerFrame keeps its panel skin below);
--   * Geometry B (reclaiming 36 px by writing tracker fields; taint risk, needs approval).
--
-- Source citations below are all against
-- ~/workspaces/reference/wow-ui-source-live-12.1.0/Interface/AddOns/
-- Blizzard_ObjectiveTracker/ (retail 12.1.0), corroborated against the 16001
-- globals dump (~/workspaces/reference/wow-api-dump-16001/globals.txt) for
-- presence on THIS client. ElvUI's ObjectiveTracker skin
-- (~/workspaces/reference/ElvUI) was read for corroboration only, not cited
-- as a primary source.

local _, FS = ...

-- Module power (Core/ModuleSwitch.lua): the build at the end of this file (the panel, the sub-heads, the quest rows, the
-- quest timer skin and the size settings) runs only with the Quest tracker switch on. Off, Blizzard's objective tracker is
-- left exactly as the client draws it; FS.Tracker, its settings table and its size keys stay defined.
local MS = FS.ModuleSwitch

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local Theme = FS.Theme
local ApplyFontGeneric = Theme.ApplyFontGeneric
local ApplyMono = Theme.ApplyMono
local COLOR_POWER = Theme.COLOR_POWER -- cyan; header accent, matches Chat.lua's selected-tab tint
local Kit = FS.ControlKit -- animation, pixel and hold helpers; every use below checks for it

-- Muted line color for body text: light enough to read against the tracker's
-- dark backdrop without competing with the cyan header.
local COLOR_LINE_MUTED = { 0.827, 0.827, 0.878, 1 } -- ~#d3d3e0

local MODULE_RULE_ALPHA = 0.45

-------------------------------------------------------------------------------
-- Shared Font objects (unchanged from the first pass)
-------------------------------------------------------------------------------

-- No addon display font is exposed on FS.Theme (only FONT_MONO), so the
-- header keeps its current font file and only gets the cyan recolor;
-- ApplyFontGeneric's own SetFont result-check falls back to that same path if
-- the re-apply somehow fails. Module headers read through our own mono label now (see Module header chrome), so this
-- recolor only matters for whatever stock header text is ever shown; it also recolors the container header font, held
-- at alpha 0 behind the band.
local function StyleHeaderFont()
    local font = ObjectiveTrackerHeaderFont
    if not (font and font.SetFont and font.SetTextColor and font.GetFont) then return end

    local path, size, flags = font:GetFont()
    ApplyFontGeneric(font, path, size, COLOR_POWER, flags)
end

-- Line text switches to the addon's body/mono font (ApplyMono), muted color.
local function StyleLineFont()
    local font = ObjectiveTrackerLineFont
    if not (font and font.SetFont and font.SetTextColor and font.GetFont) then return end

    local _, size = font:GetFont()
    ApplyMono(font, size, COLOR_LINE_MUTED)
end

-------------------------------------------------------------------------------
-- Small helpers
-------------------------------------------------------------------------------

-- `units` of the mockup as UI units on whole physical pixels (at least one), and `n` physical pixels as UI units.
local function Whole(frame, units)
    local ppu = Kit and Kit.Ppu(frame) or 1
    return math.max(1, math.floor(units * ppu + 0.5)) / ppu
end

local function Phys(frame, n)
    return n / (Kit and Kit.Ppu(frame) or 1)
end

local function Snap(texture)
    if Kit and Kit.Snap then Kit.Snap(texture) end
end

-- A plain number, or nil: a secret is turned away before anything touches it, NaN after.
local function Number(value)
    if type(value) ~= "number" then return nil end
    if FS.IsSecret and FS.IsSecret(value) then return nil end
    if value ~= value then return nil end
    return value
end

local function Read(object, method)
    if type(object) ~= "table" or type(object[method]) ~= "function" then return nil end
    local ok, value = pcall(object[method], object)
    if not ok then return nil end
    return Number(value)
end

-- A post-hook's or HookScript's error is raised in Blizzard's own caller (the tracker's layout pass, a button's click
-- script), so a throw of ours would cut that short. It is caught and handed to the error handler instead.
local function Guard(fn)
    return function(...)
        local ok, err = pcall(fn, ...)
        if ok then return end
        local layout = FS.Layout
        if layout and layout.ForwardError then layout.ForwardError(err) end
    end
end

-- Holds a region at alpha 0: zeroed now, and zeroed again after any SetAlpha on it.
local function HoldZero(region)
    if type(region) ~= "table" or type(region.SetAlpha) ~= "function" or region.fsHeldZero then return end
    region.fsHeldZero = true
    region:SetAlpha(0)
    if type(hooksecurefunc) == "function" then
        local zeroing = false
        hooksecurefunc(region, "SetAlpha", function(self)
            if zeroing then return end
            zeroing = true
            self:SetAlpha(0)
            zeroing = false
        end)
    end
end

local function Lift(c, t)
    return { c[1] + (1 - c[1]) * t, c[2] + (1 - c[2]) * t, c[3] + (1 - c[3]) * t }
end

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local chrome = {} -- frame, header, nineSlice, backdrop, band, rule, label, button, glyph bars, ticks, led, shutter
local moduleRules = setmetatable({}, { __mode = "k" }) -- module header -> our cyan rule
local headerSkins = setmetatable({}, { __mode = "k" }) -- module header -> our diamond and label
local blockSkins = setmetatable({}, { __mode = "k" }) -- quest block -> our spine, fill, wash and scanline
local lineSkins = setmetatable({}, { __mode = "k" }) -- objective line -> our tick
local lineChecks = setmetatable({}, { __mode = "k" }) -- objective line -> our check, shown on a finished objective
local CHECK_TEX = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\ctl_tick.tga" -- the settings checkbox tick
local poiSkins = setmetatable({}, { __mode = "k" }) -- POI button -> our marker pieces (see Quest markers)
local MARKER_GAP = 8 -- panel edge to the quest markers

-- The collapsed bar's ticks and the rows' ticks: open (dim cyan), ready (amber), failed (pink). Built on first use.
local tickColors
local function TickColor(state)
    if not tickColors then
        local amber, pink = Theme.COLOR_AMBER, Theme.COLOR_HEALTH
        tickColors = {
            open = { COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.55 },
            ready = { amber[1], amber[2], amber[3], 1 },
            failed = { pink[1], pink[2], pink[3], 0.9 },
        }
    end
    return tickColors[state] or tickColors.open
end

local BAND_TEXT = "stuwave://objectives"
local BAND_MAX_H = 32 -- the container's own header strip
local BAND_GAP = 3 -- band bottom to the first module header
local BAR_PAD = 10 -- label (or LED) to the bar's right end
local GLYPH_INSET = 6 -- the collapse glyph from the band's left, as the chat's minimise sits
local LABEL_X = 26 -- label from the band's left, after the glyph (the chat's 46 less its second lamp)
local MAX_TICKS = 20 -- the bar draws one tick per quest, up to this many
local TICK_W, TICK_H, TICK_GAP = 3, 8, 1 -- physical pixels
local TICK_LEAD, LED_LEAD, LED_PX = 10, 6, 5
local SHUTTER_SECONDS, GLYPH_SECONDS = 0.22, 0.16

-- How far right of the container's left edge our panel can start: the stock layout leaves a wide empty margin left
-- of the quest markers (playtest 2026-11-05). Measured off the shown markers, never written into Blizzard's layout;
-- with no marker shown the panel keeps the container's edge.
local function LeftTrim(top)
    local okL, edge = pcall(top.GetLeft, top)
    if not okL or type(edge) ~= "number" then return 0 end
    local leftMost
    for button, m in pairs(poiSkins) do
        if type(m) == "table" and m.frame then
            local okV, visible = pcall(button.IsVisible, button)
            local okX, x = pcall(m.frame.GetLeft, m.frame)
            if okV and visible and okX and type(x) == "number" and (not leftMost or x < leftMost) then leftMost = x end
        end
    end
    if not leftMost then return 0 end
    return math.max(0, math.floor(leftMost - edge - MARKER_GAP))
end

-- How far our panel's left and right edges lie from `frame`'s (panel minus frame, units), nil where either rect is not
-- readable yet. Sub-heads, rules and washes are anchored to stock frames and offset by these, so they sit edge to edge
-- in the panel whatever left margin the stock layout leaves.
local function PanelEdges(frame)
    local panel = chrome.backdrop
    if not (panel and frame) then return nil, nil end
    local pl, pr = Read(panel, "GetLeft"), Read(panel, "GetRight")
    local fl, fr = Read(frame, "GetLeft"), Read(frame, "GetRight")
    return pl and fl and (pl - fl) or nil, pr and fr and (pr - fr) or nil
end

local MODULE_NAMES -- set below, with the module header skin
local RepaintHeaders, RepaintBlocks -- set below, with the module header and quest row skins

local function QuestCount()
    local q = C_QuestLog
    local n
    if q and type(q.GetNumQuestLogEntries) == "function" then
        local ok, _, quests = pcall(q.GetNumQuestLogEntries)
        if ok and type(quests) == "number" then n = quests end
    end
    if not n then return nil end
    local max
    if q and type(q.GetMaxNumQuestsCanAccept) == "function" then
        local ok, m = pcall(q.GetMaxNumQuestsCanAccept)
        if ok and type(m) == "number" and m > 0 then max = m end
    end
    if not max and type(_G.MAX_QUESTS) == "number" then max = _G.MAX_QUESTS end
    return n, max
end

local function CollapsedText()
    local ok, n, max = pcall(QuestCount)
    if not ok or not n then return "quests" end
    if max then return ("quests (%d/%d)"):format(n, max) end
    return ("quests (%d)"):format(n)
end

-- One state per quest in the log, in log order: "open", "ready" or "failed". Nil when the client will not list them.
local function QuestStates()
    local q = C_QuestLog
    if not (q and type(q.GetNumQuestLogEntries) == "function" and type(q.GetInfo) == "function") then return nil end
    local okN, total = pcall(q.GetNumQuestLogEntries)
    if not okN or type(total) ~= "number" then return nil end
    local states = {}
    for i = 1, total do
        local okI, info = pcall(q.GetInfo, i)
        local id = okI and type(info) == "table" and not info.isHeader and not info.isHidden and info.questID
        if type(id) == "number" then
            local state = "open"
            if type(q.IsFailed) == "function" then
                local ok, failed = pcall(q.IsFailed, id)
                if ok and failed == true then state = "failed" end
            end
            if state == "open" and type(q.IsComplete) == "function" then
                local ok, complete = pcall(q.IsComplete, id)
                if ok and complete == true then state = "ready" end
            end
            states[#states + 1] = state
        end
    end
    return states
end

local function SetBarHit(button, width)
    if not (button and button.SetHitRectInsets) then return end
    if not chrome.hit and button.GetHitRectInsets then
        chrome.hit = { button:GetHitRectInsets() }
    end
    if width then
        local bw = button:GetWidth() or 0
        button:SetHitRectInsets(-GLYPH_INSET, -(width - GLYPH_INSET - bw), -4, -4)
    elseif chrome.hit then
        button:SetHitRectInsets(chrome.hit[1], chrome.hit[2], chrome.hit[3], chrome.hit[4])
    end
end

-- The console's Quests key opens and closes the tracker, so while it is on screen a collapsed tracker draws nothing
-- at all (playtest 2026-11-05). Without the key the small collapsed bar stays, the only way back.
local function KeyCarriesIt()
    local key = _G.FSConsoleKeyquests
    return type(key) == "table" and type(key.IsVisible) == "function" and key:IsVisible() == true
end

-------------------------------------------------------------------------------
-- Container chrome: the panel, the band, the collapsed bar
-------------------------------------------------------------------------------

-- The collapse control's glyph: a minus is one bar, a plus adds the cross bar, so collapsing grows the vertical bar in
-- from nothing and expanding takes it out again (the mockup's two bars rotating, on rects that stay whole pixels).
local function SetGlyphProgress(p)
    local v = chrome.glyphV
    if not v then return end
    chrome.glyphP = p
    if p <= 0.001 then
        v:Hide()
    else
        v:SetSize(chrome.glyphThick, math.max(chrome.glyphThick, chrome.glyphLen * p))
        v:SetShown(not chrome.hidden)
    end
end

local function SetGlyph(collapsed, animate)
    local target = collapsed and 1 or 0
    local from = chrome.glyphP or target
    local button = chrome.button
    local visible = button and type(button.IsVisible) == "function" and button:IsVisible() == true
    if not (animate and Kit and visible and from ~= target) then
        if Kit and button then Kit.StopAnimate(button, "glyph") end
        SetGlyphProgress(target)
        return
    end
    Kit.Animate(button, "glyph", function(_, elapsed)
        local p = math.min(1, elapsed / GLYPH_SECONDS)
        SetGlyphProgress(from + (target - from) * Kit.Ease.outQuad(p))
        if p >= 1 then Kit.StopAnimate(button, "glyph") end
    end)
end

-- Rest and hover looks: the glyph at rest alpha or full, the bar's edge cyan or, collapsed and hovered, pink.
local GLYPH_ALPHA, GLYPH_ALPHA_HOVER = 0.85, 1.00 -- the chat term bar's title button values
local function PaintChrome()
    local pink = Theme.COLOR_HEALTH
    local hot = chrome.hover or chrome.pressed
    local g = chrome.pressed and Lift(pink, 0.35) or pink
    local alpha = hot and GLYPH_ALPHA_HOVER or GLYPH_ALPHA
    for _, bar in ipairs({ chrome.glyphH, chrome.glyphV }) do
        if bar then bar:SetColorTexture(g[1], g[2], g[3], alpha) end
    end
    if chrome.border then
        local edge = (chrome.collapsed and hot) and pink or COLOR_POWER
        chrome.border:SetVertexColor(edge[1], edge[2], edge[3], 1)
    end
end

-- Hidden: our panel off, the glyph off and Blizzard's button deaf to the mouse (a secure Click still works).
local function SetHidden(hidden)
    local backdrop, button = chrome.backdrop, chrome.button
    chrome.hidden = hidden
    if backdrop then backdrop:SetShown(not hidden) end
    if chrome.glyphH then chrome.glyphH:SetShown(not hidden) end
    if chrome.glyphV then chrome.glyphV:SetShown(not hidden and (chrome.glyphP or 0) > 0.001) end
    if button and button.EnableMouse then button:EnableMouse(not hidden) end
end

local function MakeTick(i)
    local backdrop = chrome.backdrop
    local t = backdrop:CreateTexture(nil, "OVERLAY")
    Snap(t)
    if i == 1 then
        t:SetPoint("LEFT", chrome.label, "RIGHT", TICK_LEAD, 0)
    else
        t:SetPoint("LEFT", chrome.ticks[i - 1], "RIGHT", Phys(backdrop, TICK_GAP), 0)
    end
    chrome.ticks[i] = t
    return t
end

-- The LED breathes while a quest is ready (the mockup's `pulse`), and rests lit otherwise unseen.
local function SetLed(ready)
    local led = chrome.led
    if not led then return end
    led:SetShown(ready)
    if not Kit then return end
    if ready then
        if not Kit.IsAnimating(chrome.backdrop, "led") then
            Kit.Animate(chrome.backdrop, "led", function(_, elapsed) led:SetAlpha(Kit.Pulse(elapsed, 1.6, 0.35)) end)
        end
    else
        Kit.StopAnimate(chrome.backdrop, "led")
        led:SetAlpha(1)
    end
end

-- The collapsed bar: label, one tick per quest, the LED, and the width that holds them. Returns that width.
local function LayoutBar(inset)
    local backdrop, label = chrome.backdrop, chrome.label
    label:SetText(CollapsedText())
    local states = QuestStates() or {}
    local n = math.min(#states, MAX_TICKS)
    local tickW, tickH, gap = Phys(backdrop, TICK_W), Phys(backdrop, TICK_H), Phys(backdrop, TICK_GAP)
    for i = 1, n do
        local t = chrome.ticks[i] or MakeTick(i)
        local c = TickColor(states[i])
        t:SetSize(tickW, tickH)
        t:SetColorTexture(c[1], c[2], c[3], c[4])
        t:Show()
    end
    for i = n + 1, #chrome.ticks do chrome.ticks[i]:Hide() end
    local ready = false
    for _, state in ipairs(states) do
        if state == "ready" then ready = true break end
    end
    local led = chrome.led
    local ledSize = Phys(backdrop, LED_PX)
    if led then
        led:ClearAllPoints()
        led:SetSize(ledSize, ledSize)
        led:SetPoint("LEFT", n > 0 and chrome.ticks[n] or label, "RIGHT", n > 0 and LED_LEAD or TICK_LEAD, 0)
    end
    SetLed(ready)
    local ticksW = n > 0 and (TICK_LEAD + n * tickW + (n - 1) * gap) or 0
    local ledW = ready and ((n > 0 and LED_LEAD or TICK_LEAD) + ledSize) or 0
    local labelW = label.GetStringWidth and label:GetStringWidth() or 0
    return math.ceil(inset + LABEL_X + labelW + ticksW + ledW + BAR_PAD + inset)
end

local function HideBarParts()
    for _, t in ipairs(chrome.ticks) do t:Hide() end
    SetLed(false)
end

local function Relayout()
    local frame, backdrop = chrome.frame, chrome.backdrop
    if not backdrop then return end
    SetHidden(chrome.collapsed and KeyCarriesIt())
    local top = chrome.nineSlice or frame
    local inset = Theme.PanelBandInset()
    backdrop:ClearAllPoints()
    if chrome.collapsed then
        local width = LayoutBar(inset)
        backdrop:SetPoint("TOPRIGHT", top, "TOPRIGHT", 0, 0)
        backdrop:SetSize(width, Theme.PANEL_HEADER_H + inset * 2)
        chrome.band:SetHeight(Theme.PANEL_HEADER_H)
        chrome.rule:Hide()
        SetBarHit(chrome.button, width)
    else
        -- the whole container strip; the band fills the 32 px the stock header strip reserves, less the panel inset
        -- and a small gap before the first module header. topModulePadding is only read.
        local pad = tonumber(frame.topModulePadding) or 0
        local bandH = math.max(Theme.PANEL_HEADER_H, math.min(BAND_MAX_H, math.floor(pad - inset - BAND_GAP)))
        backdrop:SetPoint("TOPLEFT", top, "TOPLEFT", LeftTrim(top), 0)
        backdrop:SetPoint("BOTTOMRIGHT", top, "BOTTOMRIGHT", 0, 0)
        chrome.label:SetText(BAND_TEXT)
        chrome.band:SetHeight(bandH)
        chrome.rule:Show()
        HideBarParts()
        SetBarHit(chrome.button, nil)
    end
    PaintChrome()
    if RepaintHeaders then RepaintHeaders() end
    if RepaintBlocks then RepaintBlocks() end
end

-- Expanding: a shutter of the panel's own fill covers the panel and recedes top to bottom behind a cyan scan edge. It
-- is our frame (mouse off), the only thing the wipe touches, and a bounded timer hides it if the animation never ends.
local function PlayShutter()
    local shutter, backdrop = chrome.shutter, chrome.backdrop
    if not (Kit and shutter and backdrop) then return end
    shutter:SetHeight(1)
    shutter:Show()
    Kit.Animate(shutter, "wipe", function(_, elapsed)
        local p = math.min(1, elapsed / SHUTTER_SECONDS)
        local full = Read(backdrop, "GetHeight") or 0
        local h = full * (1 - Kit.Ease.outQuad(p))
        if p >= 1 or h < 1 then
            shutter:Hide()
            Kit.StopAnimate(shutter, "wipe")
        else
            shutter:SetHeight(h)
        end
    end)
    if _G.C_Timer and _G.C_Timer.After then
        _G.C_Timer.After(SHUTTER_SECONDS + 0.4, function() shutter:Hide() end)
    end
end

local function ApplyCollapsed(collapsed)
    local was = chrome.collapsed
    chrome.collapsed = collapsed == true
    Relayout()
    SetGlyph(chrome.collapsed, was ~= nil and was ~= chrome.collapsed)
    PaintChrome()
    if was == true and not chrome.collapsed then PlayShutter() end
end

-- The container's own state is the truth: it is read after every layout pass as well as taken from the collapse hooks.
local function SyncCollapsed()
    local frame = chrome.frame
    if frame and type(frame.IsCollapsed) == "function" then
        local ok, value = pcall(frame.IsCollapsed, frame)
        if ok and type(value) == "boolean" and value ~= chrome.collapsed then
            ApplyCollapsed(value)
            return
        end
    end
    Relayout()
end

-- Keeps the count current; made with the chrome, so a file load builds no frame.
local function WatchQuestCount()
    if chrome.countEvents or type(CreateFrame) ~= "function" then return end
    local f = CreateFrame("Frame")
    for _, event in ipairs({ "QUEST_LOG_UPDATE", "QUEST_ACCEPTED", "QUEST_REMOVED" }) do
        pcall(f.RegisterEvent, f, event)
    end
    f:SetScript("OnEvent", Relayout)
    chrome.countEvents = f
end

-- The collapse button wears the chat's minimise control (playtest 2026-11-05): a flat pink glyph quiet at rest and full
-- on hover, at the left end of the band with the label after it. It is Blizzard's own button: its art is held at alpha
-- 0 and it is re-seated on our band; its click path is untouched. The glyph is two bars of ours drawn over it.
local GLYPH_SIZE, GLYPH_LEN, GLYPH_THICK = 16, 10, 2

local function SkinCollapseButton(header, band)
    local button = header and header.MinimizeButton
    if not (button and button.CreateTexture) then return end
    if FS.HeldArt then FS.HeldArt.HoldButton(button) end
    button:ClearAllPoints()
    button:SetSize(GLYPH_SIZE, GLYPH_SIZE)
    button:SetPoint("LEFT", band, "LEFT", GLYPH_INSET, 0)
    local len, thick = Whole(button, GLYPH_LEN), Whole(button, GLYPH_THICK)
    local pink = Theme.COLOR_HEALTH
    local h = button:CreateTexture(nil, "OVERLAY")
    h:SetColorTexture(pink[1], pink[2], pink[3], GLYPH_ALPHA)
    h:SetSize(len, thick)
    h:SetPoint("CENTER", button, "CENTER", 0, 0)
    Snap(h)
    local v = button:CreateTexture(nil, "OVERLAY")
    v:SetColorTexture(pink[1], pink[2], pink[3], GLYPH_ALPHA)
    v:SetSize(thick, len)
    v:SetPoint("CENTER", button, "CENTER", 0, 0)
    Snap(v)
    v:Hide()
    chrome.glyphH, chrome.glyphV, chrome.glyphLen, chrome.glyphThick = h, v, len, thick
    if button.HookScript then
        local function set(field, value)
            return Guard(function() chrome[field] = value; PaintChrome() end)
        end
        button:HookScript("OnEnter", set("hover", true))
        button:HookScript("OnLeave", Guard(function() chrome.hover, chrome.pressed = false, false; PaintChrome() end))
        button:HookScript("OnMouseDown", set("pressed", true))
        button:HookScript("OnMouseUp", set("pressed", false))
    end
    chrome.button = button
    if type(hooksecurefunc) == "function" and type(header.SetCollapsed) == "function" then
        hooksecurefunc(header, "SetCollapsed", Guard(function(_, nowCollapsed) ApplyCollapsed(nowCollapsed == true) end))
    end
end

-- Our backdrop follows the container's own NineSlice child: every container layout pass moves its BOTTOM to the last
-- module's bottom (Blizzard_ObjectiveTrackerContainer.lua:100) and its TOPLEFT/TOPRIGHT are fixed, so anchoring to it
-- tracks every resize with no hook. The container itself Shows/Hides with content, and our backdrop is its child, so
-- visibility cascades. Without a NineSlice the backdrop anchors to the container frame.
local function BuildContainerChrome()
    local frame = ObjectiveTrackerFrame
    if not (frame and frame.CreateTexture) then return end
    if frame.fsTrackerChromeBuilt then return end

    local header = frame.Header
    local nineSlice = frame.NineSlice
    local usingNineSlice = nineSlice and nineSlice.SetPoint and nineSlice.SetAlpha

    -- A new frame does not inherit its parent's LOW strata; set it, and sit at the container's own level (as its
    -- NineSlice does) so the header and modules draw above.
    local backdrop = CreateFrame("Frame", nil, frame)
    backdrop:SetFrameStrata(frame:GetFrameStrata())
    backdrop:SetFrameLevel(frame:GetFrameLevel())

    -- The same cut panel chrome every other STUwave panel wears.
    local fill, glow, border = Theme.AddPanelChrome(backdrop, { fillColor = Theme.COLOR_BG, accent = COLOR_POWER })
    chrome.fill, chrome.glow, chrome.border = fill, glow, border

    local inset = Theme.PanelBandInset()
    local band = backdrop:CreateTexture(nil, "ARTWORK")
    band:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.08)
    band:SetPoint("TOPLEFT", backdrop, "TOPLEFT", inset, -inset)
    band:SetPoint("TOPRIGHT", backdrop, "TOPRIGHT", -inset, -inset)
    band:SetHeight(Theme.PANEL_HEADER_H)

    local rule = backdrop:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 0.30)
    rule:SetPoint("TOPLEFT", band, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("TOPRIGHT", band, "BOTTOMRIGHT", 0, 0)
    rule:SetHeight(1)

    local label = backdrop:CreateFontString(nil, "OVERLAY")
    ApplyMono(label, 10, COLOR_POWER)
    label:SetPoint("LEFT", band, "LEFT", LABEL_X, 0)
    label:SetWordWrap(false)
    label:SetText(CollapsedText())

    -- the collapsed bar's LED, ticks are made on demand
    local led = backdrop:CreateTexture(nil, "OVERLAY")
    led:SetColorTexture(Theme.COLOR_AMBER[1], Theme.COLOR_AMBER[2], Theme.COLOR_AMBER[3], 1)
    Snap(led)
    led:Hide()

    -- the expand shutter: the panel's own fill over the stock rows, receding downward behind a cyan scan edge
    local shutter = CreateFrame("Frame", nil, backdrop)
    shutter:SetFrameStrata(frame:GetFrameStrata())
    shutter:SetFrameLevel(frame:GetFrameLevel() + 40)
    shutter:SetPoint("BOTTOMLEFT", backdrop, "BOTTOMLEFT", inset, inset)
    shutter:SetPoint("BOTTOMRIGHT", backdrop, "BOTTOMRIGHT", -inset, inset)
    shutter:SetHeight(1)
    if shutter.EnableMouse then shutter:EnableMouse(false) end
    local cover = shutter:CreateTexture(nil, "BACKGROUND")
    cover:SetAllPoints(shutter)
    cover:SetColorTexture(Theme.COLOR_BG[1], Theme.COLOR_BG[2], Theme.COLOR_BG[3], 1)
    local scan = shutter:CreateTexture(nil, "OVERLAY")
    scan:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1)
    scan:SetPoint("TOPLEFT", shutter, "TOPLEFT", 0, 0)
    scan:SetPoint("TOPRIGHT", shutter, "TOPRIGHT", 0, 0)
    scan:SetHeight(Phys(shutter, 2))
    Snap(scan)
    shutter:Hide()

    chrome.backdrop, chrome.frame, chrome.header, chrome.band, chrome.rule, chrome.label = backdrop, frame, header, band, rule, label
    chrome.led, chrome.shutter, chrome.ticks = led, shutter, {}
    chrome.nineSlice = usingNineSlice and nineSlice or nil

    if header then
        -- Stock header art and text held at alpha 0 (not Hidden), so Blizzard's own show state is untouched.
        if header.Background and header.Background.SetAlpha then header.Background:SetAlpha(0) end
        if header.Text and header.Text.SetAlpha then header.Text:SetAlpha(0) end
        SkinCollapseButton(header, band)
    end

    -- Held for good: the container writes this NineSlice's alpha (SetBackgroundAlpha) and its bottom is only moved
    -- while it has modules, so a collapsed tracker left the stock art at its old full height.
    if usingNineSlice then
        if Kit and Kit.HoldFrame then Kit.HoldFrame(nineSlice) else nineSlice:SetAlpha(0) end
    end
    backdrop:Show()

    local collapsed = false
    if type(frame.IsCollapsed) == "function" then
        local ok, value = pcall(frame.IsCollapsed, frame)
        collapsed = ok and value == true
    end
    -- After each layout pass: which modules and rows show can change (a new quest type, a recipe tracked), and the
    -- container's own collapsed state is read again.
    if type(hooksecurefunc) == "function" then
        if type(frame.Update) == "function" then hooksecurefunc(frame, "Update", Guard(SyncCollapsed)) end
        if type(frame.SetCollapsed) == "function" then
            hooksecurefunc(frame, "SetCollapsed", Guard(function(_, nowCollapsed) ApplyCollapsed(nowCollapsed == true) end))
        end
    end
    ApplyCollapsed(collapsed)
    WatchQuestCount()

    frame.fsTrackerChromeBuilt = true
end

-------------------------------------------------------------------------------
-- Module header chrome (Quests, Campaign, Achievements, Bonus, World Quest,
-- Scenario, Adventure, Monthly Activities, Initiative Tasks, UI Widget,
-- Professions Recipe)
-------------------------------------------------------------------------------

-- Every module frame is built from ObjectiveTrackerModuleTemplate
-- (Blizzard_ObjectiveTrackerModule.xml:71-97), whose Header child
-- (ObjectiveTrackerModuleHeaderTemplate, same file lines 11-69) is identical
-- across every module: a Background atlas texture, a Text FontString sharing
-- ObjectiveTrackerHeaderFont, and a MinimizeButton -- confirmed for ProfessionsRecipeTracker too
-- (Blizzard_ProfessionsRecipeTracker.xml:3, `inherits="ObjectiveTrackerModuleTemplate"`).
-- That shared template is why one loop below can treat all eleven module
-- names identically rather than special-casing any of them.
MODULE_NAMES = {
    "QuestObjectiveTracker",
    "CampaignQuestObjectiveTracker",
    "AchievementObjectiveTracker",
    "BonusObjectiveTracker",
    "WorldQuestObjectiveTracker",
    "ScenarioObjectiveTracker",
    "AdventureObjectiveTracker",
    "MonthlyActivitiesObjectiveTracker",
    "InitiativeTasksObjectiveTracker",
    "UIWidgetObjectiveTracker",
    "ProfessionsRecipeTracker",
}

-- A module header reads as a quiet sub-head: a pixel diamond, the module's own name in mono lowercase, and the cyan
-- rule under it edge to edge in the panel. The stock text is held at alpha 0 and our label follows its text, so the
-- name Blizzard sets (and changes: "Campaign", a scenario's title) is always what shows. The diamond is 11 rows of one
-- physical pixel (widths 1, 3 ... 11 ... 3, 1: odd, so every row centres on a pixel edge) in a small frame of ours.
local DIAMOND_PX = 11
local DIAMOND_X, LABEL_GAP = 9, 13 -- diamond from the panel's inner left edge (units), label after the diamond

-- The quest module's sub-head also carries the count, "quests (12/40)", the same text the collapsed bar shows
-- (playtest 2026-11-20: the open tracker never showed it). Other modules show their own name only.
local function SetSubHeadText(skin, text)
    if text ~= nil then skin.stockText = text end
    local name = type(skin.stockText) == "string" and skin.stockText:lower() or ""
    if skin.quests and name ~= "" then
        local ok, n, max = pcall(QuestCount)
        if ok and n then name = max and ("%s (%d/%d)"):format(name, n, max) or ("%s (%d)"):format(name, n) end
    end
    skin.label:SetText(name)
end

local function SkinSubHead(header)
    if headerSkins[header] or type(header.CreateFontString) ~= "function" then return end
    local holder = CreateFrame("Frame", nil, header)
    holder:SetSize(Phys(header, DIAMOND_PX), Phys(header, DIAMOND_PX))
    holder:SetPoint("LEFT", header, "LEFT", DIAMOND_X, 0)
    if holder.EnableMouse then holder:EnableMouse(false) end
    local skin = { holder = holder, diamond = {} }
    local mid = (DIAMOND_PX + 1) / 2
    for i = 1, DIAMOND_PX do
        local t = holder:CreateTexture(nil, "ARTWORK")
        t:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1)
        Snap(t)
        t:SetSize(Phys(header, DIAMOND_PX - 2 * math.abs(mid - i)), Phys(header, 1))
        t:SetPoint("CENTER", holder, "CENTER", 0, Phys(header, mid - i))
        skin.diamond[i] = t
    end
    local label = header:CreateFontString(nil, "OVERLAY")
    ApplyMono(label, 11, COLOR_POWER)
    label:SetPoint("LEFT", holder, "RIGHT", LABEL_GAP, 0)
    label:SetWordWrap(false)
    skin.label = label
    local questModule = _G.QuestObjectiveTracker
    skin.quests = type(questModule) == "table" and questModule.Header == header
    headerSkins[header] = skin
    local stock = header.Text
    if stock then
        HoldZero(stock)
        if type(stock.GetText) == "function" then SetSubHeadText(skin, stock:GetText()) end
        if type(hooksecurefunc) == "function" and type(stock.SetText) == "function" then
            pcall(hooksecurefunc, stock, "SetText", Guard(function(_, text) SetSubHeadText(skin, text) end))
        end
    end
end

-- Seats a header's sub-head and rule on the panel's current edges. Run after every layout pass.
local function RepaintHeader(header)
    local skin = headerSkins[header]
    if not skin or chrome.collapsed or not chrome.backdrop then return end
    if skin.quests then SetSubHeadText(skin, nil) end
    local inset = Theme.PanelBandInset()
    local dl, dr = PanelEdges(header)
    if dl then dl = math.min(0, math.max(-80, dl)) end
    skin.holder:ClearAllPoints()
    skin.holder:SetPoint("LEFT", header, "LEFT", (dl or 0) + DIAMOND_X, 0)
    local rule = moduleRules[header]
    if rule then
        rule:ClearAllPoints()
        rule:SetPoint("BOTTOMLEFT", header, "BOTTOMLEFT", dl and (dl + inset) or 0, 0)
        rule:SetPoint("BOTTOMRIGHT", header, "BOTTOMRIGHT", dr and (dr - inset) or 0, 0)
    end
end

RepaintHeaders = function()
    for _, name in ipairs(MODULE_NAMES) do
        local module = _G[name]
        if module and module.Header then RepaintHeader(module.Header) end
    end
end

-- Hides one module's stock header background art, adds a thin cyan rule under it and the sub-head over it.
-- Idempotent via header.fsModuleHeaderSkin; feature-detected per module (a global present but with no .Header, or a
-- .Header with no .Background, is skipped rather than erroring).
--
-- SetAtlas(nil) clears the texture itself rather than just alpha-hiding it:
-- ObjectiveTrackerModuleHeaderTemplate's own AddAnim animates Background's
-- alpha 0->1 (Blizzard_ObjectiveTrackerModule.xml:56-64, setToFinalAlpha="true"),
-- and PlayAddAnimation replays it from EndLayout on every empty-to-content
-- transition (Blizzard_ObjectiveTrackerModule.lua:210-211, 779-781) -- a new
-- quest, a new world quest, entering a scenario, all routine. A plain
-- SetAlpha(0) would just get overwritten back to 1 by that animation the
-- next time it plays. Clearing the atlas is flicker-free and permanent: no
-- retail Lua ever re-sets Background's atlas, and ElvUI's own tracker skin
-- does the same thing (ElvUI/Game/Mainline/Skins/ObjectiveTracker.lua:23,
-- `header.Background:SetAtlas(nil)`). The container Header's own Background
-- (BuildContainerChrome above) does NOT need this: ObjectiveTrackerContainerHeaderTemplate
-- has no AddAnim at all (Blizzard_ObjectiveTrackerContainer.xml:18-61) and
-- ObjectiveTrackerContainerHeaderMixin never re-sets it either, so a plain
-- SetAlpha(0) there is never undone.
local function StyleModuleHeader(moduleName)
    local module = _G[moduleName]
    if not module then return end

    local header = module.Header
    if not (header and header.CreateTexture) then return end
    if header.fsModuleHeaderSkin then return end

    if header.Background then
        if header.Background.SetAtlas then
            header.Background:SetAtlas(nil)
        elseif header.Background.SetTexture then
            header.Background:SetTexture(nil)
        end
    end

    local rule = header:CreateTexture(nil, "ARTWORK")
    rule:SetColorTexture(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], MODULE_RULE_ALPHA)
    rule:SetPoint("BOTTOMLEFT", header, "BOTTOMLEFT", 0, 0)
    rule:SetPoint("BOTTOMRIGHT", header, "BOTTOMRIGHT", 0, 0)
    rule:SetHeight(1)

    moduleRules[header] = rule
    SkinSubHead(header)

    -- One collapse control: the tracker's own. Each module's stock gold minus is hidden, and kept hidden: its header's
    -- add animation fades it back in, so an alpha of 0 did not hold (playtest 2026-11-05). Nothing in Blizzard's
    -- tracker code Shows it; the Show hook is a guard.
    local minimize = header.MinimizeButton
    if minimize and minimize.Hide then
        minimize:Hide()
        if type(hooksecurefunc) == "function" then hooksecurefunc(minimize, "Show", minimize.Hide) end
    end

    header.fsModuleHeaderSkin = true
end

local function StyleModuleHeaders()
    for _, name in ipairs(MODULE_NAMES) do
        StyleModuleHeader(name)
    end
end

-------------------------------------------------------------------------------
-- Quest markers (the POI buttons beside each quest title)
-------------------------------------------------------------------------------

-- Blizzard's gold "?" (ready to turn in) and "..." (in progress) discs, playtest 2026-11-05: still stock art. Each
-- marker gets a small cut plate of our own drawn over it, its Blizzard art held at alpha 0 (HeldArt), with the
-- shared button looks: hover lifts the ring and washes the face, pressed nudges the glyph a pixel, and the quest
-- being followed (selected) wears pink. A failed quest wears a pink X. The button, its click, its place and its pool
-- are Blizzard's; markers are found after each module layout by reading the module's block list. Textures and alpha
-- only, so safe in combat. The plate is the quest's station node on the spine (see Quest rows).
local MARKER_SIZE = 20 -- the POI button's own size
-- Pixel glyphs, drawn cell by cell on whole physical pixels so they sit dead centre (a font glyph's side bearing
-- and baseline put the "?" off centre, playtest 2026-11-05). Each cell is CELL_PX x CELL_PX pixels.
local CELL_PX = 2
local MARKER_GLYPHS = {
    ask  = { ".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.." },
    bang = { "#", "#", "#", "#", "#", ".", "#" },
    dots = { "#.#.#" },
    fail = { "#...#", ".#.#.", "..#..", ".#.#.", "#...#" },
}

local function IsFailedQuest(button)
    local q = C_QuestLog
    if not (q and type(q.IsFailed) == "function" and type(button.GetQuestID) == "function") then return false end
    local okI, id = pcall(button.GetQuestID, button)
    if not okI or type(id) ~= "number" then return false end
    local okF, failed = pcall(q.IsFailed, id)
    return okF and failed == true
end

local function MarkerKind(button)
    local styles = POIButtonUtil and POIButtonUtil.Style
    local ok, style = pcall(button.GetStyle, button)
    if not ok or not styles then return "dots" end
    if style == styles.QuestComplete then return "ask" end
    if IsFailedQuest(button) then return "fail" end
    if style == styles.QuestInProgress then return "dots" end
    if style == styles.QuestDisabled then return "none" end
    return "bang"
end

local PaintBlock -- set below, with the quest rows

local function PaintMarker(button)
    local m = poiSkins[button]
    if not m then return end
    local kind = MarkerKind(button)
    -- the plate lives beside the button (see SkinMarker), so it follows the button into whichever block the pool
    -- hands it to, and keeps to the button's own shown state
    local okP, parent = pcall(button.GetParent, button)
    if okP and parent and m.frame:GetParent() ~= parent then m.frame:SetParent(parent) end
    if okP and parent then m.block = parent end
    local okL, level = pcall(button.GetFrameLevel, button)
    if okL and type(level) == "number" then m.frame:SetFrameLevel(level + 1) end
    m.frame:SetShown(kind ~= "none" and not m.hidden)
    m.kind = kind
    local okSel, selected = pcall(button.IsSelected, button)
    selected = okSel and selected == true
    m.selected = selected
    if kind == "none" then
        if PaintBlock and m.block then PaintBlock(m.block) end
        return
    end
    local accent = (selected or kind == "fail") and Theme.COLOR_HEALTH or (kind == "ask" and Theme.COLOR_AMBER or COLOR_POWER)
    local hover, pressed = m.hover, m.pressed
    local wash = pressed and 0.40 or (hover and 0.25 or (selected and 0.15 or 0))
    local ink = Theme.COLOR_BUTTON_INK
    m.fill:SetVertexColor(ink[1] + (accent[1] - ink[1]) * wash, ink[2] + (accent[2] - ink[2]) * wash,
        ink[3] + (accent[3] - ink[3]) * wash, 1)
    m.ring:SetVertexColor(accent[1], accent[2], accent[3], (hover or pressed or selected) and 1 or 0.75)
    m.glow:SetVertexColor(accent[1], accent[2], accent[3], (hover or pressed) and 0.65 or (selected and 0.45 or 0.2))
    local g = (hover or pressed) and Lift(accent, 0.55) or accent
    local rows = MARKER_GLYPHS[kind]
    local okPx, es = false, nil
    if FS.FrameHelpers and FS.FrameHelpers.PixelsPerUnit then
        okPx, es = pcall(FS.FrameHelpers.PixelsPerUnit, m.frame)
    end
    if not okPx or type(es) ~= "number" or es <= 0 then es = 1 end
    local px = 1 / es
    local platePx = math.floor(MARKER_SIZE * es / 2 + 0.5) * 2 -- even, so the centre is a pixel edge
    m.frame:SetSize(platePx * px, platePx * px)
    local cell = kind == "dots" and CELL_PX + 1 or CELL_PX
    local gw, gh = #rows[1] * cell, #rows * cell
    local mx, my = math.floor((platePx - gw) / 2), math.floor((platePx - gh) / 2)
    local dx, dy = pressed and 1 or 0, pressed and 1 or 0
    local n = 0
    for r, row in ipairs(rows) do
        for c = 1, #row do
            if row:sub(c, c) == "#" then
                n = n + 1
                local t = m.cells[n]
                if not t then
                    t = m.frame:CreateTexture(nil, "OVERLAY")
                    if t.SetSnapToPixelGrid then pcall(t.SetSnapToPixelGrid, t, true) end
                    if t.SetTexelSnappingBias then pcall(t.SetTexelSnappingBias, t, 0) end
                    m.cells[n] = t
                end
                t:ClearAllPoints()
                t:SetSize(cell * px, cell * px)
                t:SetPoint("TOPLEFT", m.frame, "TOPLEFT", (mx + (c - 1) * cell + dx) * px, -(my + (r - 1) * cell + dy) * px)
                t:SetColorTexture(g[1], g[2], g[3], 1)
                t:Show()
            end
        end
    end
    for i = n + 1, #m.cells do m.cells[i]:Hide() end
    if PaintBlock and m.block then PaintBlock(m.block) end
end

local function SkinMarker(button)
    if poiSkins[button] or type(button) ~= "table" or type(button.CreateTexture) ~= "function" then return end
    if FS.HeldArt then FS.HeldArt.HoldButton(button) end
    -- Blizzard's art layer (Display) and its icon texture are each held at alpha 0. Holding the frame alone was not
    -- enough: the tracker's add animation brings a new quest's art layer back to full alpha without a SetAlpha call,
    -- so the stock icon showed through our plate (live probe 2026-11-06: Display alpha 1 on every newly accepted quest).
    local display = button.Display
    HoldZero(display)
    HoldZero(display and display.Icon)
    local anim = button.AddAnim
    if anim and anim.HookScript and display and display.SetAlpha then
        pcall(anim.HookScript, anim, "OnFinished", Guard(function() display:SetAlpha(0) end))
    end

    -- Our plate is NOT a child of the button: the same add animation scales the button 1.2x and back, and our sliced
    -- plate textures drew as a box many times the marker's size while it ran (screen capture 2026-11-06). Beside the
    -- button, centred on it, the animation cannot reach it.
    local okP, parent = pcall(button.GetParent, button)
    local f = CreateFrame("Frame", nil, okP and parent or button)
    f:SetSize(MARKER_SIZE, MARKER_SIZE)
    f:SetPoint("CENTER", button, "CENTER", 0, 0)
    if f.EnableMouse then f:EnableMouse(false) end
    local m = { frame = f, cells = {}, hover = false, pressed = false }
    m.glow = Theme.AddCut2Texture(f, Theme.SLICE_CUT2_GLOW_TEXTURE, COLOR_POWER, "BACKGROUND", 1,
        -Theme.SLICE_CUT2_GLOW_PAD)
    m.fill = Theme.AddCut2Texture(f, Theme.SLICE_CUT2_FILL_TEXTURE, Theme.COLOR_BUTTON_INK, "ARTWORK", 1)
    m.ring = Theme.AddCut2Texture(f, Theme.SLICE_CUT2_OUTLINE_TEXTURE, COLOR_POWER, "ARTWORK", 2)
    poiSkins[button] = m

    local function set(field, value)
        return Guard(function(self)
            local s = poiSkins[self]
            if s then s[field] = value; PaintMarker(self) end
        end)
    end
    if button.HookScript then
        button:HookScript("OnEnter", set("hover", true))
        button:HookScript("OnLeave", Guard(function(self)
            local s = poiSkins[self]
            if s then s.hover, s.pressed = false, false; PaintMarker(self) end
        end))
        button:HookScript("OnMouseDown", set("pressed", true))
        button:HookScript("OnMouseUp", set("pressed", false))
        button:HookScript("OnHide", Guard(function(self)
            local s = poiSkins[self]
            if s then s.hidden = true; s.frame:Hide() end
        end))
        button:HookScript("OnShow", Guard(function(self)
            local s = poiSkins[self]
            if s then s.hidden = false; PaintMarker(self) end
        end))
    end
    if type(hooksecurefunc) == "function" then
        local paint = Guard(PaintMarker)
        for _, method in ipairs({ "UpdateButtonStyle", "SetStyle", "SetSelected", "UpdateSelected" }) do
            if type(button[method]) == "function" then pcall(hooksecurefunc, button, method, paint) end
        end
    end
    PaintMarker(button)
end

-------------------------------------------------------------------------------
-- Quest rows: the spine, the ticks, the charge and the wash
-------------------------------------------------------------------------------

-- Each quest block that has a marker gets, as regions of ITS OWN frame (so they move, hide and pool with it), a 2 px
-- spine centred under the marker plate and running from just above the plate to the bottom of the block's last region,
-- a tick off the spine to every objective line (the stock dash is held at alpha 0 beside it), a charge in front of
-- the spine, and a wash behind the row. Every one of them is anchored to a stock frame (the header text, the last
-- region, the line) with the one offset that is the marker's own: Blizzard hangs the POI button TOPRIGHT of the header
-- text at (-7, +5), size 20 (Blizzard_ObjectiveTrackerQuestPOIBlock.lua:29), so its centre is 17 left of the text.
-- The charge runs to the last finished objective (a line whose text colour is the stock "Complete" colour), amber and
-- the whole spine when the quest is ready, none when it failed. Hover and press come from the header button's own
-- scripts through HookScript; the followed quest is the marker's selected state, with a scanline sweeping its wash.
local RAIL_CENTER = 17 -- spine centre left of the header text
local RAIL_STUB = 10 -- the spine starts this far above the header text: the module header's bottom, 5 above the plate
local RAIL_THICK = 2 -- units; whole pixels
local TICK_RUN = RAIL_CENTER - 3 -- tick from the spine centre to 3 short of the text
local TICK_ROW = 6 -- tick centre below the line's top: the first text row's middle
local FILL_DROP = 7 -- the charge ends this far below a finished line's top (the tick's lower edge)
local WASH_UP, WASH_DOWN = 5, 4 -- the wash above the header text (the plate top) and below the last region
local SCAN_SECONDS = 2.6

local WASH_ALPHA = { hover = 0.10, pressed = 0.18, followed = 0.16, followedHover = 0.22, followedPressed = 0.30 }

local function ObjectiveColor(name)
    local colors = _G.OBJECTIVE_TRACKER_COLOR
    return type(colors) == "table" and colors[name] or nil
end

local function LineIsDone(line)
    local text = type(line) == "table" and line.Text
    local style = type(text) == "table" and text.colorStyle
    return style ~= nil and style == ObjectiveColor("Complete")
end

local function SkinLine(line)
    local tick = lineSkins[line]
    if tick then return tick end
    if type(line) ~= "table" or type(line.CreateTexture) ~= "function" then return nil end
    tick = line:CreateTexture(nil, "OVERLAY")
    Snap(tick)
    tick:SetSize(Phys(line, 1), Phys(line, 1))
    lineSkins[line] = tick
    HoldZero(line.Dash)
    -- The stock green check on a finished objective (ObjectiveTrackerAnimLineTemplate's Icon, and the CheckGlow its
    -- CheckAnim flashes) sat over our tick and spine in Blizzard's art. Both are held hidden and our own check (the
    -- settings checkbox tick) stands in, painted per state in PaintBlock. CheckAnim drives the glow's alpha without
    -- SetAlpha, so both also get a vertex alpha of 0, which an Alpha animation only multiplies.
    for _, art in ipairs({ line.Icon, line.CheckGlow }) do
        HoldZero(art)
        if type(art) == "table" and type(art.SetVertexColor) == "function" then art:SetVertexColor(1, 1, 1, 0) end
    end
    local check = line:CreateTexture(nil, "OVERLAY")
    check:SetTexture(CHECK_TEX)
    Snap(check)
    check:Hide()
    lineChecks[line] = check
    return tick
end

local function SkinBlock(block)
    local r = blockSkins[block]
    if r then return r end
    if type(block) ~= "table" or type(block.CreateTexture) ~= "function" or type(block.HeaderText) ~= "table" then
        return nil
    end
    r = {}
    r.wash = block:CreateTexture(nil, "BACKGROUND", nil, -8)
    r.spine = block:CreateTexture(nil, "BACKGROUND", nil, -6)
    r.fill = block:CreateTexture(nil, "BACKGROUND", nil, -5)
    r.scan = block:CreateTexture(nil, "BACKGROUND", nil, -4)
    for _, t in ipairs({ r.wash, r.spine, r.fill, r.scan }) do Snap(t); t:Hide() end
    blockSkins[block] = r
    local button = block.HeaderButton
    if type(button) == "table" and type(button.HookScript) == "function" then
        local function set(field, value)
            return Guard(function() r[field] = value; PaintBlock(block) end)
        end
        button:HookScript("OnEnter", set("hover", true))
        button:HookScript("OnLeave", Guard(function() r.hover, r.pressed = false, false; PaintBlock(block) end))
        button:HookScript("OnMouseDown", set("pressed", true))
        button:HookScript("OnMouseUp", set("pressed", false))
    end
    if type(block.HookScript) == "function" then
        -- a pooled block comes back clean
        block:HookScript("OnHide", Guard(function() r.hover, r.pressed = false, false end))
    end
    return r
end

local function StopScan(block, r)
    if Kit then Kit.StopAnimate(block, "scan") end
    r.scan:Hide()
end

-- The followed quest's scanline: one pixel, sweeping the wash top to bottom every SCAN_SECONDS.
local function StartScan(block, r)
    r.scan:Show()
    if not Kit or Kit.IsAnimating(block, "scan") then return end
    Kit.Animate(block, "scan", function(_, elapsed)
        local h = Read(r.wash, "GetHeight") or 0
        local y = ((elapsed % SCAN_SECONDS) / SCAN_SECONDS) * math.max(0, h - Phys(block, 1))
        r.scan:ClearAllPoints()
        r.scan:SetPoint("TOPLEFT", r.wash, "TOPLEFT", 0, -y)
        r.scan:SetPoint("TOPRIGHT", r.wash, "TOPRIGHT", 0, -y)
    end)
end

local function HideRail(block, r)
    for _, t in ipairs({ r.wash, r.spine, r.fill }) do t:Hide() end
    StopScan(block, r)
    for _, line in pairs(type(block.usedLines) == "table" and block.usedLines or {}) do
        local tick = lineSkins[line]
        if tick then tick:Hide() end
        if lineChecks[line] then lineChecks[line]:Hide() end
    end
end

PaintBlock = function(block)
    local r = blockSkins[block]
    if not r then return end
    local poi = block.poiButton
    local m = poi and poiSkins[poi]
    local kind = m and m.kind
    local text = block.HeaderText
    if not (m and kind and kind ~= "none" and text) then
        HideRail(block, r)
        return
    end
    local ready, failed, followed = kind == "ask", kind == "fail", m.selected == true
    local accent = ready and Theme.COLOR_AMBER or (failed and Theme.COLOR_HEALTH or COLOR_POWER)
    local inset = Theme.PanelBandInset()
    local last = type(block.lastRegion) == "table" and block.lastRegion or text
    local width = Whole(block, RAIL_THICK)
    local x = -(RAIL_CENTER + width / 2)

    -- the spine: from above the plate to the bottom of the last region. The x of the bottom point is the header text's
    -- own left less the rail offset, corrected when the last region sits somewhere else (a bar placed with an offset).
    local lx, tx = Read(last, "GetLeft"), Read(text, "GetLeft")
    local correct = (last ~= text and lx and tx) and math.max(-30, math.min(30, tx - lx)) or 0
    r.spine:ClearAllPoints()
    r.spine:SetPoint("TOPLEFT", text, "TOPLEFT", x, RAIL_STUB)
    r.spine:SetPoint("BOTTOMLEFT", last, "BOTTOMLEFT", x + correct, 0)
    r.spine:SetWidth(width)
    local base = failed and Theme.COLOR_HEALTH or Theme.COLOR_BORDER
    r.spine:SetColorTexture(base[1], base[2], base[3], failed and 0.5 or 0.55)
    r.spine:Show()

    -- the ticks, and the last finished objective
    local doneLine, doneKey
    local lines = type(block.usedLines) == "table" and block.usedLines or {}
    for key, line in pairs(lines) do
        local tick = SkinLine(line)
        if tick then
            local done = LineIsDone(line)
            local c = (ready and TickColor("ready")) or (failed and TickColor("failed"))
                or (done and { COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], 1 }) or TickColor("open")
            tick:ClearAllPoints()
            tick:SetSize(TICK_RUN, Whole(line, RAIL_THICK))
            tick:SetPoint("RIGHT", line, "TOPLEFT", -3, -TICK_ROW)
            tick:SetColorTexture(c[1], c[2], c[3], c[4])
            tick:Show()
            -- the check sits in the stock dash's space (held invisible, still sized) on the tick's row, before the text,
            -- at the texture's own 16 physical pixels so its 2 px stroke stays crisp
            local check = lineChecks[line]
            if check and done and not failed then
                local cc = ready and TickColor("ready") or COLOR_POWER
                check:ClearAllPoints()
                check:SetSize(Phys(line, 16), Phys(line, 16))
                check:SetPoint("CENTER", line, "TOPLEFT", Whole(line, 5), -TICK_ROW)
                check:SetVertexColor(cc[1], cc[2], cc[3], 1)
                check:Show()
            elseif check then
                check:Hide()
            end
            if done and type(key) == "number" and (not doneKey or key > doneKey) then doneLine, doneKey = line, key end
        end
    end

    -- the charge
    r.fill:ClearAllPoints()
    r.fill:SetPoint("TOPLEFT", text, "TOPLEFT", x, RAIL_STUB)
    if ready then
        r.fill:SetPoint("BOTTOMLEFT", last, "BOTTOMLEFT", x + correct, 0)
    elseif doneLine and not failed then
        r.fill:SetPoint("BOTTOMLEFT", doneLine, "TOPLEFT", x, -FILL_DROP)
    end
    r.fill:SetWidth(width)
    if ready or (doneLine and not failed) then
        r.fill:SetColorTexture(accent[1], accent[2], accent[3], 1)
        r.fill:Show()
    else
        r.fill:Hide()
    end

    -- the wash: edge to edge in the panel, over the stock row
    local pink = Theme.COLOR_HEALTH
    local hot = r.hover or r.pressed
    local alpha, c
    if followed then
        alpha = r.pressed and WASH_ALPHA.followedPressed or (r.hover and WASH_ALPHA.followedHover or WASH_ALPHA.followed)
        c = pink
    elseif hot then
        alpha = r.pressed and WASH_ALPHA.pressed or WASH_ALPHA.hover
        c = COLOR_POWER
    end
    if alpha and chrome.backdrop then
        local dl = PanelEdges(block)
        local _, dr = PanelEdges(last)
        r.wash:ClearAllPoints()
        r.wash:SetPoint("TOPLEFT", text, "TOPLEFT", (dl or -RAIL_CENTER - 20) + inset, WASH_UP)
        r.wash:SetPoint("BOTTOMRIGHT", last, "BOTTOMRIGHT", (dr or 6) - inset, -WASH_DOWN)
        r.wash:SetColorTexture(c[1], c[2], c[3], alpha)
        r.wash:Show()
        r.scan:SetColorTexture(pink[1], pink[2], pink[3], 0.55)
        r.scan:SetHeight(Phys(block, 1))
        if followed then StartScan(block, r) else StopScan(block, r) end
    else
        r.wash:Hide()
        StopScan(block, r)
    end
end

RepaintBlocks = function()
    for block in pairs(blockSkins) do
        if type(block) == "table" then PaintBlock(block) end
    end
end

local function SkinModuleMarkers(module)
    local used = type(module) == "table" and module.usedBlocks
    if type(used) ~= "table" then return end
    for _, blocks in pairs(used) do
        if type(blocks) == "table" then
            for _, block in pairs(blocks) do
                local poi = type(block) == "table" and block.poiButton
                if poi then
                    SkinMarker(poi)
                    PaintMarker(poi)
                    if SkinBlock(block) then PaintBlock(block) end
                end
            end
        end
    end
end

local function WatchMarkers()
    if type(hooksecurefunc) ~= "function" then return end
    local seen = false
    for _, name in ipairs(MODULE_NAMES) do
        local module = _G[name]
        if module and not poiSkins[module] and type(module.EndLayout) == "function" then
            hooksecurefunc(module, "EndLayout", Guard(SkinModuleMarkers))
            poiSkins[module] = true
            SkinModuleMarkers(module)
            seen = true
        end
    end
    -- the plates just made move the panel's left edge
    if seen then Relayout() end
end

-------------------------------------------------------------------------------
-- Quest timers
-------------------------------------------------------------------------------

-- Blizzard_QuestTimer's QuestTimerFrame (Blizzard_QuestTimer.xml) is a BackdropTemplate dialog with a gold header on
-- the BACKGROUND strata, laid out by RightManagedFrameContainer into the gap the tracker leaves at its top. Our
-- backdrop sits on the tracker's LOW strata, so the stock timer drew behind it (playtest 2026-11-04). Skin and raise
-- only, never moved: the container owns its anchor, and ignoreFramePositionManager, the one way out, is a field its
-- layout code reads.

-- Puts the timer on the tracker's strata, above the tracker. The container's UpdateFrame reparents the timer, which
-- resets its level, so this runs again after every re-layout and show.
-- The 12.1 source names its lines QuestTimer1Text..QuestTimer25Text, but the 16001 globals dump has none of those
-- names, so the Forever build is not that file. The lines are found by shape instead: every font string on a child
-- frame of the timer. Run again on each show, so a line made after the skin is set too.
local function StyleQuestTimerLines(timer)
    local ok, children = pcall(function() return { timer:GetChildren() } end)
    if not ok then return end
    for _, child in ipairs(children) do
        if type(child) == "table" and child ~= timer.Header and child ~= timer.Border
            and type(child.GetRegions) == "function" then
            for _, region in ipairs({ child:GetRegions() }) do
                if region.GetObjectType and region:GetObjectType() == "FontString" then
                    ApplyMono(region, 10, COLOR_LINE_MUTED)
                end
            end
        end
    end
end

-- The 16001 timer draws its wood dialog from two child frames, Header (the "Quest Timers" plaque) and Border, plus its
-- backdrop (live recon 2026-11-05: QuestTimerFrame keys Header=Frame, Border=Frame, backdropInfo set). The region sweep in
-- SkinPanel reaches none of them, so they are hidden here, on every show, since Blizzard re-shows its own art.
local function HideStockTimerChrome(timer)
    for _, key in ipairs({ "Header", "Border" }) do
        local part = timer[key]
        if type(part) == "table" and part.Hide then pcall(part.Hide, part) end
    end
    if type(timer.ClearBackdrop) == "function" then pcall(timer.ClearBackdrop, timer) end
end

local function RaiseQuestTimer()
    local timer, tracker = QuestTimerFrame, ObjectiveTrackerFrame
    if timer then HideStockTimerChrome(timer) end
    if not (timer and timer.SetFrameStrata and tracker and tracker.GetFrameStrata) then return end
    timer:SetFrameStrata(tracker:GetFrameStrata())
    timer:SetFrameLevel(tracker:GetFrameLevel() + 10)
    StyleQuestTimerLines(timer)
end

local function SkinQuestTimer()
    local timer = QuestTimerFrame
    if not (timer and timer.GetRegions) then return end
    if not timer.fsQuestTimerSkin then
        Theme.SkinPanel(timer, { fillColor = Theme.COLOR_BG, borderColor = COLOR_POWER, title = "timers" })
        -- Blizzard's "Quest Timers" label; the band carries the title now
        for _, region in ipairs({ timer:GetRegions() }) do
            if region ~= timer.fsPanelTitle and region.GetObjectType and region:GetObjectType() == "FontString" then
                region:Hide()
            end
        end
        FS.PanelSkins.HookShowOnce(timer, "fsQuestTimerHook", RaiseQuestTimer)
        local container = RightManagedFrameContainer
        if container and type(container.UpdateFrame) == "function" then
            hooksecurefunc(container, "UpdateFrame", RaiseQuestTimer)
        end
        timer.fsQuestTimerSkin = true
    end
    RaiseQuestTimer()
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

-- Font objects, CreateTexture/CreateFrame calls, and SetAlpha are all
-- non-secure, so none of this is combat-illegal; deferred anyway for
-- consistency with the rest of the addon's Init pattern. Module frames
-- (QuestObjectiveTracker etc.) exist at file-load time regardless of whether
-- they have ever displayed content, so StyleModuleHeaders needs no
-- ADDON_LOADED/load-on-demand watch the way e.g. AuctionHouse.lua's panels do.
-------------------------------------------------------------------------------
-- Size settings (the Quest tracker page: Scale, Opacity, Background opacity)
-------------------------------------------------------------------------------

-- Opacity is the alpha of the whole container (the text too), Background opacity the alpha of our panel's fill alone (the stock
-- NineSlice stays held at 0), Scale the container's scale. All three leave the defaults (100, 100 and 80, which is COLOR_BG's own
-- alpha) untouched: nothing is written until a value moves off its default, and a value moved back is written once more. The
-- scale goes through the Base calls an Edit Mode system frame keeps (the override would run Blizzard's frame manager under our
-- taint) and re-pins every anchor the way that override does, so the corner the player placed stays put; Blizzard's own anchor
-- pass divides its offsets by the frame's scale, so a later re-seat agrees. A write to the scale waits for the end of combat.
--
-- Height is the game's own Edit Mode setting for the objective tracker (400 to 1000 by 10, the game's default 800; the
-- prototype's 120 to 800 is not something Edit Mode accepts), written into the active Edit Mode layout through TrackerSeat:
-- never a size on the tracker frame, which the file header rules out. The game only uses it once the tracker has been moved
-- off its default seat, so a height is written for a moved tracker only (a Seat.Move carries it along otherwise), out of
-- combat (held until PLAYER_REGEN_ENABLED), and not at all while the setting holds its default and was never changed: the
-- layout keeps whatever height Edit Mode gave it. Width stays locked: Edit Mode has no width setting for this tracker and its
-- width is fixed by its modules; the page says why.
FS.Tracker = FS.Tracker or {}
local SIZE = {
    w = { key = "tracker.w", min = 180, max = 500, step = 1, default = FS.Layout and FS.Layout.tracker and FS.Layout.tracker.w or 270 },
    h = { key = "tracker.h", min = 400, max = 1000, step = 10, default = 800 }, -- TrackerSeat.HEIGHT: what Edit Mode accepts
    scale = { key = "tracker.scale", min = 50, max = 200, step = 5, default = 100 },
    alpha = { key = "tracker.alpha", min = 10, max = 100, step = 5, default = 100 },
    bgAlpha = { key = "tracker.bgAlpha", min = 0, max = 100, step = 1, default = 80 }, -- COLOR_BG's alpha, in percent
}
FS.Tracker.SIZE = SIZE
FS.Tracker.SIZE_LOCKED = "The game's Edit Mode has a Height for the tracker but no Width, and this addon may not resize the game's tracker itself."

-- The setting held to its range; the default for anything that is not a plain number.
local function SizeValue(spec)
    local value
    if FS.Config and FS.Config.Get then
        local ok, stored = pcall(FS.Config.Get, spec.key)
        if ok then value = stored end
    end
    value = Number(value)
    if not value or value - value ~= 0 then return spec.default end
    return math.max(spec.min, math.min(spec.max, value))
end

local function ApplyBackground()
    local fill = chrome.fill
    if not (fill and fill.SetVertexColor) then return end
    local c = Theme.COLOR_BG
    local percent = SizeValue(SIZE.bgAlpha)
    fill:SetVertexColor(c[1], c[2], c[3], percent == SIZE.bgAlpha.default and c[4] or percent / 100)
end

local alphaWritten = false
local function ApplyOpacity()
    local frame = _G.ObjectiveTrackerFrame
    if not (frame and frame.SetAlpha) then return end
    local percent = SizeValue(SIZE.alpha)
    if percent == SIZE.alpha.default and not alphaWritten then return end
    alphaWritten = percent ~= SIZE.alpha.default
    frame:SetAlpha(percent / 100)
end

local scaleWritten, scalePending = false, false
local function ApplyScale()
    local frame = _G.ObjectiveTrackerFrame
    if not (frame and frame.GetScale) then return end
    local percent = SizeValue(SIZE.scale)
    if percent == SIZE.scale.default and not scaleWritten then return end
    if InCombatLockdown and InCombatLockdown() then
        scalePending = true
        return
    end
    scalePending = false
    local want = percent == SIZE.scale.default and 1 or percent / 100
    local old = Read(frame, "GetScale") or 1
    if old <= 0 or math.abs(old - want) < 1e-6 then return end
    local setScale = frame.SetScaleBase or frame.SetScale
    local setPoint = frame.SetPointBase or frame.SetPoint
    if type(setScale) ~= "function" or type(setPoint) ~= "function" or type(frame.GetPoint) ~= "function" then return end
    local anchors = {}
    for i = 1, Read(frame, "GetNumPoints") or 0 do
        local ok, point, rel, relPoint, x, y = pcall(frame.GetPoint, frame, i)
        x, y = Number(x), Number(y)
        if ok and point and x and y then anchors[#anchors + 1] = { point, rel, relPoint, x * old / want, y * old / want } end
    end
    setScale(frame, want)
    for _, a in ipairs(anchors) do setPoint(frame, a[1], a[2], a[3], a[4], a[5]) end
    scaleWritten = want ~= 1
    Relayout() -- the panel's whole-pixel pieces sit on the pixel scale the tracker has now
end

local function ApplySizeSettings()
    ApplyBackground()
    ApplyOpacity()
    ApplyScale()
end

-- The height the setting asks for, or nil while it holds its default (nothing stored: Edit Mode's own height stays).
-- TrackerSeat.Move asks for it too, so a move writes it in the same save.
function FS.Tracker.WantedHeight()
    local config = FS.Config
    if not (config and config.IsStored and config.IsStored(SIZE.h.key)) then return nil end
    return SizeValue(SIZE.h)
end

-- `forced` is the player's own change of the row (it writes even the default, putting 800 back); the login and layout events
-- write only a stored height. heightPending holds a write back from combat or from layouts that are not readable yet;
-- heightSynced says the login pass reached an answer, after which a layout the player saves in Edit Mode is theirs again.
local heightPending, heightForced, heightSynced = false, false, false
local function ApplyHeight(forced)
    local seat = FS.TrackerSeat
    if not (seat and seat.SetHeight) then return end
    local want = forced and SizeValue(SIZE.h) or FS.Tracker.WantedHeight()
    if not want then
        heightSynced = true
        return
    end
    local _, _, wait = seat.SetHeight(want)
    if wait then
        heightPending, heightForced = true, heightForced or forced == true
    else
        heightPending, heightForced, heightSynced = false, false, true
    end
end

if FS.Config and FS.Config.RegisterDefault then
    for _, spec in pairs(SIZE) do FS.Config.RegisterDefault(spec.key, spec.default) end
end

local function Apply()
    -- Built from the first step on: the tracker is ours now, and a later step that throws does not hand it back to Blizzard.
    if MS then MS.MarkBuilt("m.track") end
    StyleHeaderFont()
    StyleLineFont()
    BuildContainerChrome()
    ApplySizeSettings()
    StyleModuleHeaders()
    WatchMarkers()
    SkinQuestTimer()
    Relayout() -- the sub-heads, plates and rows made above sit on the panel's current edges
end

FS.PanelSkins.RegisterInspect("Tracker", {
    { name = "ObjectiveTrackerFrame", guard = "fsTrackerChromeBuilt" },
    { name = "QuestTimerFrame", guard = "fsQuestTimerSkin" },
})

-- Everything that listens or hooks starts here, only with the switch on.
local function Start()
    if FS.Config and FS.Config.OnChange then
        FS.Config.OnChange(SIZE.bgAlpha.key, Guard(ApplyBackground))
        FS.Config.OnChange(SIZE.alpha.key, Guard(ApplyOpacity))
        FS.Config.OnChange(SIZE.scale.key, Guard(ApplyScale))
        FS.Config.OnChange(SIZE.h.key, Guard(function() ApplyHeight(true) end))
    end

    -- The profile loads after the files run: apply what it holds at login, and a scale or height held back in combat when it
    -- ends. Edit Mode's layouts may not be readable at PLAYER_LOGIN, so the height asks again when they arrive (and on
    -- entering the world) until one pass has an answer.
    local sizeWatcher = CreateFrame("Frame")
    sizeWatcher:RegisterEvent("PLAYER_LOGIN")
    sizeWatcher:RegisterEvent("PLAYER_REGEN_ENABLED")
    sizeWatcher:RegisterEvent("PLAYER_ENTERING_WORLD")
    pcall(sizeWatcher.RegisterEvent, sizeWatcher, "EDIT_MODE_LAYOUTS_UPDATED")
    sizeWatcher:SetScript("OnEvent", Guard(function(_, event)
        if event == "PLAYER_REGEN_ENABLED" then
            if scalePending then ApplySizeSettings() end
            if heightPending then ApplyHeight(heightForced) end
        elseif event == "PLAYER_LOGIN" then
            ApplySizeSettings()
            ApplyHeight(false)
        elseif not heightSynced then
            ApplyHeight(false)
        end
    end))

    FS.PanelSkins.DeferCombat(Apply, "m.track")

    -- Blizzard_QuestTimer is its own addon and may load after this file.
    FS.PanelSkins.WatchAddonLoad(SkinQuestTimer, function(name) return name == "Blizzard_QuestTimer" end, "m.track")
end
if MS then MS.WhenOn("m.track", Start) else Start() end

-------------------------------------------------------------------------------
-- Left alone
-------------------------------------------------------------------------------
-- Progress bars, timer bars and quest item buttons keep their stock look (see the list in the file header). The item
-- buttons are SECURE and must never be touched at all; a row's stock lines, header text and click paths are never
-- re-anchored or scripted, only drawn beside and behind.

-- The visible panel (the STUwave backdrop), for the layout editor's handle. Nil until the chrome is built.
FS.Tracker = FS.Tracker or {}
function FS.Tracker.Panel()
    return chrome.backdrop
end

-- The console keys call this after they are seated, so a collapsed tracker hides or shows with its key.
function FS.Tracker.Refresh()
    Relayout()
end

-- The skin's own state, for the harness: chrome pieces, module sub-heads and rules, quest rows, objective ticks, markers.
FS.Tracker.state = {
    chrome = chrome, headers = headerSkins, rules = moduleRules, blocks = blockSkins, lines = lineSkins,
    markers = poiSkins,
}
