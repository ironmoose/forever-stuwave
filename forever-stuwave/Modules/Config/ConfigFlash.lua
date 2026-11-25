-- Forever STUwave: the hover flash on the thing a setting changes
-- Pointing at a row in /fsconfig for 150 ms outlines the frame on screen that the setting changes (the frames come from
-- ConfigTargets.lua, looked up when the row is hovered): the outline pulses twice for 1.1 s each, then holds, with a corner
-- bracket on each corner; leaving the row removes it. A setting whose frame has a seat but is not showing right now (a
-- target frame with no target, the party in no group, the Gunsight's target side) gets a PREVIEW where there is a safe one
-- to reuse: a plain insecure copy built from the Style tab's sample frames (or the Edit Mode raid preview) shown at the seat
-- while the row is hovered, then hidden again, never in combat. Where there is none the outline is drawn dimmed with a short
-- caption saying why it is empty ("Shows with a target"). A setting with no seat at all draws nothing, and its ? tip says
-- so. The overlays are plain insecure frames on UIParent, placed from the target's rect and never parented
-- to or anchored on it, so the flash works in combat. The look is the prototype's .flash (mockups/config-window-2026-11-25.html).
-- The "Flash frames on hover" switch (config.flash) is in Profiles > Window; off, nothing here runs.
-- Harness: tools/configflash-harness.py.

local _, FS = ...

local CW = FS.ConfigWindow
local I, UI, S, C = CW.I, CW.UI, CW.Spec, CW.C
local Theme = FS.Theme
local Config = FS.Config

local F = {}
CW.Flash = F

F.KEY = "config.flash"
F.DELAY = 0.15            -- the pointer rests on a row this long before anything is drawn
F.PULSE = 1.1             -- one pulse of the outline, in seconds
F.PULSES = 2              -- then it holds
-- The prototype's keyframes `fl` as { share of one pulse, opacity }; ease in out between them.
F.ENVELOPE = { { 0, 0 }, { 0.4, 1 }, { 0.7, 0.35 }, { 1, 1 } }
F.MAX = 12                -- overlays one row can draw (a raid grid is one frame; this is a cap, not a need)

local REFRESH = 0.05      -- while a flash is up its rects are read again this often, so it follows a frame being resized
local ARM = 2             -- thickness of a corner bracket arm
local GLOW_SIZE, GLOW_ALPHA = 12, 0.5   -- the prototype's box-shadow: 0 0 12px at half strength
local NOT_SHOWN = "Not on screen right now."
local DIM = 0.45              -- a dimmed outline's share of the pulse
local CAP_PAD, CAP_H = 6, 16  -- the caption plate: side padding and height, whole pixels
local PARTY_ROWS = 4          -- sample rows stacked in the party preview

if Config and Config.RegisterDefault then Config.RegisterDefault(F.KEY, true) end

function F.Enabled()
    return not Config or Config.Get(F.KEY) ~= false
end

-------------------------------------------------------------------------------
-- The pulse
-------------------------------------------------------------------------------

local function Smooth(u)
    return u * u * (3 - 2 * u)
end

-- The outline's opacity `t` seconds after the flash began: the keyframes twice, each eased, then held at the last one.
function F.Envelope(t)
    t = tonumber(t) or 0
    if t < 0 then t = 0 end
    local keys = F.ENVELOPE
    if t >= F.PULSE * F.PULSES then return keys[#keys][2] end
    local u = (t % F.PULSE) / F.PULSE
    for i = 2, #keys do
        if u <= keys[i][1] then
            local a, b = keys[i - 1], keys[i]
            local f = (u - a[1]) / (b[1] - a[1])
            return a[2] + (b[2] - a[2]) * Smooth(f)
        end
    end
    return keys[#keys][2]
end

-------------------------------------------------------------------------------
-- Overlays: a pool, one per target on screen
-------------------------------------------------------------------------------

local pool = {}
function F.Overlays() return pool end

-- The outline and glow live on `fsPulse` (its alpha is the pulse); the corner brackets stay on the overlay itself, solid.
local function NewOverlay()
    local o = CreateFrame("Frame", nil, UIParent)
    o:SetFrameStrata("FULLSCREEN_DIALOG")
    o:EnableMouse(false)
    o:Hide()
    local pulse = CreateFrame("Frame", nil, o)
    pulse:SetAllPoints(o)
    pulse:EnableMouse(false)
    o.fsPulse = pulse
    o.fsEdges = I.Outline(pulse, C.cyan, 0.8)
    if Theme and type(Theme.AddOuterGlow) == "function" then
        Theme.AddOuterGlow(pulse, C.cyan[1], C.cyan[2], C.cyan[3], GLOW_SIZE, GLOW_ALPHA, 0)
    end
    o.fsBrackets = {}
    for _, corner in ipairs({ "TOPLEFT", "TOPRIGHT", "BOTTOMLEFT", "BOTTOMRIGHT" }) do
        for arm = 1, 2 do
            local t = o:CreateTexture(nil, "OVERLAY")
            t:SetColorTexture(C.cyan[1], C.cyan[2], C.cyan[3], 1)
            if arm == 1 then t:SetSize(S.FLASH_CORNER, ARM) else t:SetSize(ARM, S.FLASH_CORNER) end
            t:SetPoint(corner, o, corner, 0, 0)
            o.fsBrackets[#o.fsBrackets + 1] = t
        end
    end
    -- The caption of a dimmed outline: a plate and one line of small text, centred
    o.fsCapBg = o:CreateTexture(nil, "ARTWORK")
    o.fsCapBg:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], 0.8)
    o.fsCapBg:Hide()
    o.fsCaption = o:CreateFontString(nil, "OVERLAY")
    Theme.ApplyMono(o.fsCaption, S.SMALL, C.text)
    o.fsCaption:SetWordWrap(false)
    o.fsCaption:Hide()
    return o
end

local function Whole(v) return math.floor(v + 0.5) end

-- Tints the outline and brackets: the flash cyan, or the muted tone when dimmed.
local function Tone(o, color, bracketAlpha)
    for _, e in ipairs(o.fsEdges or {}) do e:SetColorTexture(color[1], color[2], color[3], 0.8) end
    for _, t in ipairs(o.fsBrackets) do
        t:SetColorTexture(color[1], color[2], color[3], 1)
        t:SetAlpha(bracketAlpha)
    end
end

-- Puts an overlay in its look: live (today's outline, no caption) or dim with `reason` as the caption.
local function SetLook(o, dim, reason)
    local key = dim and ("dim:" .. tostring(reason)) or "live"
    o.fsDim = dim and true or false
    if o.fsLook == key then return end
    o.fsLook = key
    if not dim then
        Tone(o, C.cyan, 1)
        o.fsCapBg:Hide()
        o.fsCaption:Hide()
        return
    end
    Tone(o, C.muted, 0.6)
    local text = type(reason) == "string" and reason ~= "" and reason or "Hidden right now"
    local cap = o.fsCaption
    cap:SetText(text)
    local width = cap.GetStringWidth and cap:GetStringWidth() or 0
    if type(width) ~= "number" or width <= 0 then width = #text * 6 end
    local plate = Whole(width) + 2 * CAP_PAD
    local ow, oh = o:GetWidth() or plate, o:GetHeight() or CAP_H
    if type(ow) ~= "number" or ow <= 0 then ow = plate end
    if type(oh) ~= "number" or oh <= 0 then oh = CAP_H end
    plate = math.min(plate, Whole(ow))
    local x, y = math.floor((ow - plate) / 2), math.floor((oh - CAP_H) / 2)
    o.fsCapBg:ClearAllPoints()
    o.fsCapBg:SetPoint("TOPLEFT", o, "TOPLEFT", x, -y)
    o.fsCapBg:SetSize(plate, CAP_H)
    cap:ClearAllPoints()
    cap:SetPoint("CENTER", o.fsCapBg, "CENTER", 0, 0)
    cap:SetWidth(plate)
    o.fsCapBg:Show()
    cap:Show()
end

-- The overlay covers the target's rect pushed out by FLASH_OUT on every side, anchored on UIParent alone.
local function Place(o, rect)
    local out = S.FLASH_OUT
    o:ClearAllPoints()
    o:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", rect.left - out, rect.bottom - out)
    o:SetSize(rect.width + 2 * out, rect.height + 2 * out)
end

-------------------------------------------------------------------------------
-- Previews: a sample of a frame that is not showing, at its seat, while its row is hovered
-------------------------------------------------------------------------------
-- Built from what the Style tabs already draw (FS.UnitFrames.NewPreview, PartyFrames.NewStylePreview,
-- PetFrame.NewStylePreview: plain insecure frames, no unit, no event) inside a host frame on UIParent, scaled so the sample
-- is the size of the real frame's seat and anchored at its top left. The raid uses the Edit Mode preview (RaidFrames
-- Preview.Show / Hide, which only fades the real grid by alpha). Nothing here touches a secure frame, and nothing is
-- built or shown in combat. A key with no maker (cast bars, the Gunsight, class tabs, nameplates, alerts) has no sample
-- and gets the dimmed outline with its caption instead.

local ghosts = {}
F.ghosts = ghosts
local raidByUs = false

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() == true
end

local MAKERS = {}
F.MAKERS = MAKERS

for _, key in ipairs({ "player", "target", "focus", "boss" }) do
    MAKERS[key] = function(host)
        local uf = FS.UnitFrames
        if not (uf and uf.NewPreview) then return nil end
        local f = uf.NewPreview(host, key)
        return { frame = f, restyle = f.Restyle }
    end
end

MAKERS.petcontainer = function(host)
    local pet = FS.PetFrame
    if not (pet and pet.NewStylePreview) then return nil end
    local pv = pet.NewStylePreview(host)
    if type(pv) ~= "table" or not pv.frame then return nil end
    return { frame = pv.frame, restyle = pv.Restyle }
end

MAKERS.party = function(host)
    local party = FS.PartyFrames
    if not (party and party.NewStylePreview) then return nil end
    local stack = CreateFrame("Frame", nil, host)
    local rows = {}
    for i = 1, PARTY_ROWS do
        local pv = party.NewStylePreview(stack)
        if type(pv) ~= "table" or not pv.frame then return nil end
        rows[i] = pv
    end
    local function Restyle()
        local y, w = 0, 0
        for _, pv in ipairs(rows) do
            if pv.Restyle then pv.Restyle() end
            local h = pv.frame:GetHeight() or 0
            pv.frame:ClearAllPoints()
            pv.frame:SetPoint("TOPLEFT", stack, "TOPLEFT", 0, -y)
            y = y + h + 2
            w = math.max(w, pv.frame:GetWidth() or 0)
        end
        stack:SetSize(math.max(w, 1), math.max(y - 2, 1))
    end
    return { frame = stack, restyle = Restyle }
end

local function Plain(v)
    if FS.IsSecret and FS.IsSecret(v) then return nil end
    if type(v) ~= "number" or v ~= v then return nil end
    return v
end

-- The Edit Mode raid preview, shown for this hover only (left alone when the editor already has it up).
local function ShowRaid()
    local raid = FS.RaidFrames
    local pv = raid and raid.Preview
    if not (type(pv) == "table" and type(pv.Show) == "function" and type(pv.Rect) == "function"
        and type(pv.IsShown) == "function") then return nil end
    if pv.IsShown() ~= true then
        if pv.Show() ~= true then return nil end
        raidByUs = true
    end
    local l, t, w, h = pv.Rect()
    l, t, w, h = Plain(l), Plain(t), Plain(w), Plain(h)
    if not (l and t and w and h and w > 0 and h > 0) then return nil end
    return { left = l, bottom = t - h, width = w, height = h }, "raid"
end

local function HideRaid()
    if not raidByUs then return end
    raidByUs = false
    local raid = FS.RaidFrames
    local pv = raid and raid.Preview
    if type(pv) == "table" and type(pv.Hide) == "function" then pcall(pv.Hide) end
end

-- The Gunsight's target side: the real pieces draw at their own seats once the shared gate reads "has a target" (Theme.lua,
-- FS.SetTargetPreview), with sample readings in the info box. Non secure gates only; refused in combat.
local gunsightByUs = false
local function ShowGunsightTarget(rect)
    if type(FS.SetTargetPreview) ~= "function" then return nil end
    if not gunsightByUs then
        if FS.SetTargetPreview(true) ~= true then return nil end
        gunsightByUs = true
    end
    return rect, "gs.target"
end

local function HideGunsightTarget()
    if not gunsightByUs then return end
    gunsightByUs = false
    if type(FS.SetTargetPreview) == "function" then pcall(FS.SetTargetPreview, false) end
end

-- Shows the sample for a hidden rect and answers the rect it fills (and its key), or nil when there is none to show.
local function ShowGhost(rect)
    local key = rect.preview
    if not key or InCombat() then return nil end
    if key == "raid" then return ShowRaid() end
    if key == "gs.target" then return ShowGunsightTarget(rect) end
    local maker = MAKERS[key]
    if not maker then return nil end
    local g = ghosts[key]
    if g and g.failed then return nil end
    if not g then
        local host = CreateFrame("Frame", nil, UIParent)
        host:SetFrameStrata("HIGH")
        host:EnableMouse(false)
        host:Hide()
        local ok, made = pcall(maker, host)
        if not (ok and type(made) == "table" and made.frame) then
            host:Hide()
            ghosts[key] = { failed = true }
            return nil
        end
        g = { host = host, made = made, up = false }
        ghosts[key] = g
    end
    if not g.up then
        if g.made.restyle then pcall(g.made.restyle) end
        g.made.frame:Show()
    end
    local w, h = Plain(g.made.frame:GetWidth()), Plain(g.made.frame:GetHeight())
    if not (w and h and w > 0 and h > 0) then return nil end
    local scale = rect.width / w
    if scale < 0.25 then scale = 0.25 elseif scale > 4 then scale = 4 end
    local top = rect.bottom + rect.height
    g.host:SetScale(scale)
    g.host:SetSize(w, h)
    g.host:ClearAllPoints()
    g.host:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", rect.left / scale, top / scale)
    g.host:Show()
    g.up = true
    return { left = rect.left, bottom = top - h * scale, width = w * scale, height = h * scale }, key
end

-- Hides every sample that was not used this pass (`used` is the set of keys that were), or all of them when `used` is nil.
local function SweepGhosts(used)
    for key, g in pairs(ghosts) do
        if g.up and not (used and used[key]) then
            g.up = false
            g.host:Hide()
        end
    end
    if raidByUs and not (used and used.raid) then HideRaid() end
    if gunsightByUs and not (used and used["gs.target"]) then HideGunsightTarget() end
end

-- Draws the samples again with the settings as they are now (a setting changed while its row is hovered).
function F.Restyle()
    for _, g in pairs(ghosts) do
        if g.up and g.made.restyle then pcall(g.made.restyle) end
    end
end

-------------------------------------------------------------------------------
-- The hovered row
-------------------------------------------------------------------------------

local state = { entry = nil, live = false, waited = 0, t = 0, acc = 0, hidden = false }
F.state = state

local driver = CreateFrame("Frame", nil, UIParent)
F.driver = driver

-- The rects of a row's frames that are on screen now; nil when the row has no target (or the map is not there).
local function Rects(entry)
    local targets = CW.Targets
    if type(targets) ~= "table" or type(targets.Seats) ~= "function" then return nil end
    local ok, rects = pcall(targets.Seats, entry)
    if ok and type(rects) == "table" then return rects end
    return nil
end

-- The row's ? tip is where "Not on screen right now." goes: ConfigBuilders computes the tip text (I.RefreshTip), and this
-- adds the line while the row is the hovered one and its frame is missing. A row with no tip of its own gets a ? for it.
local baseRefreshTip = I.RefreshTip
function I.RefreshTip(row)
    local entry = row and row.fsEntry
    if not (entry and entry.opts) then return end
    local say = state.hidden and entry == state.entry
    if say and not row.fsHelp and row.fsLabel then
        local icon = UI.HelpIcon(row, "")
        icon:SetPoint("LEFT", row.fsLabel, "RIGHT", S.Q_GAP, 0)
        icon:Hide()
        row.fsHelp = icon
    end
    baseRefreshTip(row)
    local icon = row.fsHelp
    if say and icon then
        local own = icon.fsTip
        icon.fsTip = (type(own) == "string" and own ~= "") and (own .. "\n" .. NOT_SHOWN) or NOT_SHOWN
        icon:Show()
    end
end

local function SetHidden(hidden)
    if state.hidden == hidden then return end
    state.hidden = hidden
    local row = state.entry and state.entry.row
    if row then I.RefreshTip(row) end
end

local function Paint()
    local alpha = F.Envelope(state.t)
    for _, o in ipairs(pool) do
        if o:IsShown() then o.fsPulse:SetAlpha(o.fsDim and alpha * DIM or alpha) end
    end
end

local function Draw(rects)
    local n = math.min(#rects, F.MAX)
    local used = {}
    for i = 1, n do
        local o = pool[i]
        if not o then
            o = NewOverlay()
            pool[i] = o
        end
        local rect, dim = rects[i], false
        if rect.hidden then
            local seat, key = ShowGhost(rect)
            if seat then
                rect, used[key] = seat, true
            else
                dim = true
            end
        end
        Place(o, rect)
        SetLook(o, dim, rects[i].reason)
        if not o:IsShown() then
            o.fsPulse:SetAlpha(dim and F.Envelope(state.t) * DIM or F.Envelope(state.t))
            o:Show()
        end
    end
    SweepGhosts(used)
    for i = n + 1, #pool do
        if pool[i]:IsShown() then pool[i]:Hide() end
    end
end

local function Refresh()
    local rects = Rects(state.entry) or {}
    Draw(rects)
    SetHidden(#rects == 0)
end

local function GoLive(over)
    state.live, state.t, state.acc = true, over, 0
    Refresh()
    Paint()
end

local function Tick(_, dt)
    if not state.entry then
        driver:SetScript("OnUpdate", nil)
        return
    end
    if not state.live then
        state.waited = state.waited + dt
        if state.waited >= F.DELAY then GoLive(state.waited - F.DELAY) end
        return
    end
    state.t = state.t + dt
    state.acc = state.acc + dt
    if state.acc >= REFRESH then
        state.acc = 0
        Refresh()
    end
    Paint()
end

-- Removes every overlay and forgets the row; its ? tip goes back to what the builder computed.
function F.Clear()
    local entry, wasHidden = state.entry, state.hidden
    state.entry, state.live, state.hidden = nil, false, false
    state.waited, state.t, state.acc = 0, 0, 0
    driver:SetScript("OnUpdate", nil)
    for _, o in ipairs(pool) do
        if o:IsShown() then o:Hide() end
    end
    SweepGhosts(nil)
    if wasHidden and entry and entry.row then I.RefreshTip(entry.row) end
end

-- A row was pointed at: nothing is drawn yet; the wait starts. A row with no target, or the switch off, does nothing.
local function Begin(entry)
    F.Clear()
    if not F.Enabled() then return false end
    local rects = Rects(entry)
    if not rects then return false end
    state.entry = entry
    SetHidden(#rects == 0)
    driver:SetScript("OnUpdate", Tick)
    return true
end

function F.Start(entry)
    Begin(entry)
end

-- The same without the wait (the harness, and any caller that wants the flash now).
function F.Show(entry)
    if Begin(entry) then GoLive(0) end
end

CW.On("change", function() if state.entry then F.Restyle() end end)
CW.On("rowEnter", F.Start)
CW.On("rowLeave", F.Clear)
CW.On("hide", F.Clear)
CW.On("select", F.Clear)
-- Combat starts: every sample goes down now (they are plain frames, but nothing of this runs in a fight).
local combatWatch = CreateFrame("Frame", nil, UIParent)
pcall(combatWatch.RegisterEvent, combatWatch, "PLAYER_REGEN_DISABLED")
combatWatch:SetScript("OnEvent", function() SweepGhosts(nil); if F.ClearAlerts then F.ClearAlerts() end end)
F.combatWatch = combatWatch

if Config and Config.OnChange then
    Config.OnChange(F.KEY, function()
        if not F.Enabled() then F.Clear() end
    end)
end


-------------------------------------------------------------------------------
-- Alert previews: an alert the config controls, drawn with sample data while its rows are in use
-------------------------------------------------------------------------------
-- An alert (the warrior and druid pop up alerts today) registers { id, label, api, match, sound }: `api()` answers the module's
-- Preview table { Show() -> true when this call put it up, Hide(), Restyle() }, `match(entry)` says which rows belong to it
-- (its switches and the shared scale row), and `sound` (optional) is a function that plays one soft sound. The preview is up
-- while a matching row is pointed at, and STAYS up while its slider is dragged or its number box has the keyboard, even with
-- the pointer off the row; the section's Test button keeps it up until it is clicked again, the section folds or hides, the
-- page changes, the window closes or combat starts. Restyle runs on every setting change, so a scale moves it live. The previews are
-- silent; a Test click plays the alert's one soft sound when it has one and its own sound switch is on (none of today's alerts
-- has a sound, so none plays). Never started in combat.

local alertDefs = {}
F.alertDefs = alertDefs
local alertState = {}
F.alertState = alertState
local alertDriver = CreateFrame("Frame", nil, UIParent)
F.alertDriver = alertDriver

function F.RegisterAlert(def)
    if type(def) ~= "table" or type(def.id) ~= "string" then return false end
    alertDefs[def.id] = def
    alertState[def.id] = alertState[def.id] or { up = false }
    return true
end

local function AlertApi(def)
    if type(def.api) ~= "function" then return nil end
    local ok, api = pcall(def.api)
    if ok and type(api) == "table" and type(api.Show) == "function" and type(api.Hide) == "function" then return api end
    return nil
end

-- True while the pointer is off a slider row but the slider is still in use: its thumb is held, or its box has the keyboard.
local function InUse(entry)
    local row = entry and entry.row
    if not row then return false end
    local track, edit = row.fsTrack, row.fsEdit
    if track and track.fsDragging == true then return true end
    if edit and type(edit.HasFocus) == "function" and edit:HasFocus() then return true end
    return false
end

local AlertTick

local function SyncAlerts()
    local any = false
    for id, def in pairs(alertDefs) do
        local st = alertState[id]
        local wanted = st.hover ~= nil or st.test == true
        if wanted and not InCombat() then
            any = true
            if not st.up then
                local api = AlertApi(def)
                if api and api.Show() == true then st.up = true end
            end
        elseif st.up then
            local api = AlertApi(def)
            if api then pcall(api.Hide) end
            st.up = false
            if wanted then any = true end
        end
        if st.hover ~= nil or st.test == true then any = true end
    end
    alertDriver:SetScript("OnUpdate", any and AlertTick or nil)
end

local function PaintTest(id)
    local st = alertState[id]
    local b = st and st.button
    if b and b.Relabel then b.Relabel(st.test and "Stop" or "Test") end
end

AlertTick = function(_, dt)
    alertDriver.acc = (alertDriver.acc or 0) + dt
    if alertDriver.acc < 0.1 then return end
    alertDriver.acc = 0
    for id, st in pairs(alertState) do
        if st.hover and st.leaving and not InUse(st.hover) then st.hover, st.leaving = nil, nil end
        if st.test and st.header and type(st.header.IsVisible) == "function" and not st.header:IsVisible() then
            st.test = false
            PaintTest(id)
        end
    end
    SyncAlerts()
end

-- Every alert down: the window closed, the page changed, a fight began.
function F.ClearAlerts()
    for id, st in pairs(alertState) do
        st.hover, st.leaving = nil, nil
        if st.test then st.test = false; PaintTest(id) end
    end
    SyncAlerts()
end

local function AlertsOnEnter(entry)
    for id, def in pairs(alertDefs) do
        local ok, hit = pcall(def.match, entry)
        if ok and hit == true then
            alertState[id].hover, alertState[id].leaving = entry, nil
        end
    end
    SyncAlerts()
end

local function AlertsOnLeave(entry)
    for _, st in pairs(alertState) do
        if st.hover == entry then
            if InUse(entry) then st.leaving = true else st.hover, st.leaving = nil, nil end
        end
    end
    SyncAlerts()
end

-- A Test button for an alert in a section header (UI.SectionButton). Clicking keeps the preview up; clicking again takes it down.
function F.AddTest(sec, id)
    local def = alertDefs[id]
    if not (def and sec and sec.header and UI.SectionButton) then return nil end
    local st = alertState[id]
    local b = UI.SectionButton(sec, {
        text = "Test",
        tip = "Shows this alert on screen with sample values until you press it again, change the page or close the window. "
            .. "Move the scale while it is up to tune it.",
        onClick = function()
            if InCombat() and not st.test then return end
            st.test = not st.test
            PaintTest(id)
            if st.test and type(def.sound) == "function" then pcall(def.sound) end
            SyncAlerts()
        end,
    })
    st.button, st.header = b, sec.header
    PaintTest(id)
    return b
end

-- Which alert the shared scale row stands for: the player's own class when it has one, else the warrior's.
local function ScaleOwner()
    local DC = FS.DruidClearcasting
    if DC and DC.Applies and DC.Applies() then return "druid" end
    return "warrior"
end

F.ScaleOwner = ScaleOwner

local function ScaleKey()
    return FS.GunsightAreas and FS.GunsightAreas.ALERT_SCALE_KEY
end

local function Starts(key, prefix)
    return type(key) == "string" and key:sub(1, #prefix) == prefix
end

F.RegisterAlert({
    id = "warrior", label = "Warrior power-up alerts",
    api = function() return FS.WarriorPowerUps and FS.WarriorPowerUps.Preview end,
    match = function(entry)
        return Starts(entry.key, "gunsight.warrior.powerup") or (entry.key == ScaleKey() and ScaleOwner() == "warrior")
    end,
})
F.RegisterAlert({
    id = "druid", label = "Druid alerts",
    api = function() return FS.DruidClearcasting and FS.DruidClearcasting.Preview end,
    match = function(entry)
        return Starts(entry.key, "gunsight.druid.clearcasting") or (entry.key == ScaleKey() and ScaleOwner() == "druid")
    end,
})

CW.On("rowEnter", AlertsOnEnter)
CW.On("rowLeave", AlertsOnLeave)
CW.On("hide", F.ClearAlerts)
CW.On("select", F.ClearAlerts)
CW.On("change", function() for id, st in pairs(alertState) do
    if st.up then local api = AlertApi(alertDefs[id]); if api and api.Restyle then pcall(api.Restyle) end end
end end)

-------------------------------------------------------------------------------
-- The switch
-------------------------------------------------------------------------------

CW.ExtendTab("profiles", "p", { title = "Window" }, function(content)
    UI.Toggle(content, {
        label = "Flash frames on hover", key = F.KEY,
        tip = "Pointing at a setting outlines the frame on screen that it changes, for as long as you point at it. "
            .. "A setting whose frame is not on screen says so in its ? tip.",
    })
end, 900)
