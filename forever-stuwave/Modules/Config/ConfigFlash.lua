-- Forever STUwave: the hover flash on the thing a setting changes
-- Pointing at a row in /fsconfig for 150 ms outlines the frame on screen that the setting changes (the frames come from
-- ConfigTargets.lua, looked up when the row is hovered): the outline pulses twice for 1.1 s each, then holds, with a corner
-- bracket on each corner; leaving the row removes it. A setting whose frame is not on screen right now draws nothing, and
-- its ? tip says so. The overlays are plain insecure frames on UIParent, placed from the target's rect and never parented
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
    return o
end

-- The overlay covers the target's rect pushed out by FLASH_OUT on every side, anchored on UIParent alone.
local function Place(o, rect)
    local out = S.FLASH_OUT
    o:ClearAllPoints()
    o:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", rect.left - out, rect.bottom - out)
    o:SetSize(rect.width + 2 * out, rect.height + 2 * out)
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
    if type(targets) ~= "table" or type(targets.Resolve) ~= "function" then return nil end
    local ok, rects = pcall(targets.Resolve, entry)
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
        if o:IsShown() then o.fsPulse:SetAlpha(alpha) end
    end
end

local function Draw(rects)
    local n = math.min(#rects, F.MAX)
    for i = 1, n do
        local o = pool[i]
        if not o then
            o = NewOverlay()
            pool[i] = o
        end
        Place(o, rects[i])
        if not o:IsShown() then
            o.fsPulse:SetAlpha(F.Envelope(state.t))
            o:Show()
        end
    end
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

CW.On("rowEnter", F.Start)
CW.On("rowLeave", F.Clear)
CW.On("hide", F.Clear)
CW.On("select", F.Clear)
if Config and Config.OnChange then
    Config.OnChange(F.KEY, function()
        if not F.Enabled() then F.Clear() end
    end)
end

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
