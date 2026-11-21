-- Forever STUwave: the ammo tab (mockup ammo-tab-glyph-right-2026-11-20, look B: the count twice as tall, the glyph on
-- the right)
--
-- A 2 x 1 shoulder on the Console's top edge (92.8 x 49 design px) that always shows how many arrows or bullets are left.
-- ClassShoulder.lua seats it like the mana regen module: 16 design px right of the last shoulder that stands, or at the first
-- seat (36) when none does. DISPLAY ONLY: plain frames, no secure button, no binding, no click action (the mouse is on for the
-- tooltip and the hover ring alone).
--
-- Who: a Warrior, Hunter or Rogue (Forever's SkillLineAbility gives Bows, Crossbows and Guns to class mask 13) while the ranged
-- slot holds a bow, crossbow or gun. A wand, a thrown weapon, a relic or nothing there stands no tab and the Console's top
-- line closes.
--
-- The count is FS.HunterState's (Ammo, AmmoKind): the stack in the ammo slot (or the bags' count when that is more), the
-- read the Hunter scope's low ammo warning uses, so the two never disagree. Nothing in the ammo slot is 0.
--
-- The face is the mana regen module's style (FiveSecondTab.lua), so the two read as one family: one led_well.tga tile with its
-- cut ring filling the face, four fourteen segment cells with their unlit segments showing as a faint LED pattern, and the
-- ammo glyph on the right (an arrow for a bow or crossbow, a cartridge for a gun, lying level and pointing right, flat runs on
-- whole pixels, two texels a glyph pixel). The cells are the regen module's segments redrawn twice as tall
-- (led_segments_tall.tga, 11 x 22 texels, n physical pixels a texel, a soft copy from led_segment_glow_tall.tga under each
-- lit segment). Places before the number stay unlit; 0 reads 0000; 9999 at most.
--
-- States: PLENTY is the regen module's resting look (muted digits and glyph, violet ring, the face dimmed); LOW at or under
-- the warn count (`gunsight.hunter.ammowarn`, default 60, the scope's setting) lights amber like its countdown; OUT at 0
-- lights pink and the readout blinks twice when it gets there. `ammotab.lowwarn` off keeps the resting look whatever the
-- count; `ammotab.motion` off drops the blink. The ring turns cyan under the mouse, as the regen module's does.
--
-- Combat: nothing here is protected, so painting runs in combat; the host's anchor onto the Console and a shoulder that
-- comes or goes wait for PLAYER_REGEN_ENABLED (ClassShoulder.Refresh parks itself in combat). Loads after ThunderClapTab.lua,
-- before ConfigWindow.lua (which reads SETTINGS); HunterState.lua loads later and is asked for at PLAYER_LOGIN.
-- tools/ammotab-harness.py pins it against a mock. The tall LED art is a new texture, so a full client restart picks it up.

local _, FS = ...

local Tab = {}
FS.AmmoTab = Tab

local IsSecret = FS.IsSecret
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"

local AT = {
    KEY = "ammo",
    CLASSES = { WARRIOR = true, HUNTER = true, ROGUE = true },
    HOST_W = 92.8, HOST_H = 49,                     -- the mana regen module's block (FiveSecondTab.lua FT)
    HERO = { x = 6, y = 6, w = 81, h = 37 },        -- the one tile, filling the face (chamfer 6)
    CELL_W = 11, CELL_H = 22, SLOT = 32, ATLAS = 128, -- a cell of led_segments_tall.tga in texels, its slot, the atlas side
    PITCH = 13,                                     -- four cells on a 13 texel pitch: 4 x 11 + 3 x 2 = 50
    GLYPH_GAP = 3, GLYPH_W = 10, GLYPH_H = 7, GLYPH_SCALE = 2, -- the glyph right of the cells, two texels a glyph pixel
    READ_W = 73,                                    -- the cells, the gap and the glyph (50 + 3 + 20), centred on the tile
    SEG_GLOW_PAD = 2, SEG_GLOW_W = 15, SEG_GLOW_H = 26,
    IDLE_ALPHA = 0.72, WORD_IDLE = 0.55, GHOST_REST = 0.14, GHOST_LIT = 0.18, GLOW_STEADY = 0.5,
    -- the unlit segments show as a visible LED pattern behind the digits (playtest 2026-11-20: the regen module's 0.05 to 0.08
    -- ghost was too faint to see on the ammo tab), so they sit brighter than the regen module's
    RING_IDLE = 0.4, RING_WARN = 0.7, HOVER_GLOW = 0.6,
    BLINK_ON = 0.45, BLINK_OFF = 0.45, BLINK_LOW = 0.25, BLINKS = 2,
    MAX = 9999,
    host = nil, built = false, seated = false, pendingSync = false, hover = false,
    count = nil, kind = nil, state = nil, sig = nil,
    warned = {},
}
Tab.AT = AT

local SETTINGS = {
    enabled = {
        key = "ammotab.enabled", default = true, label = "Ammo tab",
        tip = "A tab on the Console that shows how many arrows or bullets you have left while you carry a bow, crossbow "
            .. "or gun. Off hides it.",
    },
    lowwarn = {
        key = "ammotab.lowwarn", default = true, label = "Low ammo colours",
        tip = "Turns the tab amber when you are down to the low ammo count and pink when you are out. Off keeps its resting look.",
    },
    motion = {
        key = "ammotab.motion", default = true, label = "Out of ammo blink",
        tip = "The count blinks twice when your last arrow or bullet is gone. Off keeps it still.",
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
    if AT.warned[key] then return end
    AT.warned[key] = true
    if FS.LogDegradeOnce then FS.LogDegradeOnce(key, "|cffff4488Forever STUwave|r: " .. text) end
end

local function PlayerClass()
    local ok, _, token = pcall(UnitClass, "player")
    if not ok or IsSecret(token) or type(token) ~= "string" then return nil end
    return token
end

local function Data()
    local state = FS.HunterState
    if type(state) == "table" and type(state.Ammo) == "function" then return state end
end

-------------------------------------------------------------------------------
-- Who gets it, and the count
-------------------------------------------------------------------------------

function Tab.Applies()
    return AT.CLASSES[PlayerClass() or ""] == true
end

-- The count and kind from HunterState; nil (no weapon that fires ammo, unreadable) is no tab.
function Tab.Read()
    local data = Data()
    local n = data and data.Ammo() or nil
    if IsSecret(n) or type(n) ~= "number" then n = nil end
    local kind = data and data.AmmoKind and data.AmmoKind() or nil
    if kind ~= "bullet" then kind = n and "arrow" or nil end
    if n then n = math.max(0, math.floor(n)) end
    AT.count, AT.kind = n, kind
    return n, kind
end

function Tab.Warn()
    local data = Data()
    local v = data and data.AmmoWarn and data.AmmoWarn()
    if type(v) ~= "number" or v < 0 then return 60 end
    return v
end

-- "plenty" | "low" | "out" for a count, nil for none.
function Tab.StateOf(n)
    if type(n) ~= "number" then return nil end
    if not Setting(SETTINGS.lowwarn) then return "plenty" end
    if n <= 0 then return "out" end
    local warn = Tab.Warn()
    if warn > 0 and n <= warn then return "low" end
    return "plenty"
end

function Tab.Shown()
    return Tab.Applies() and Setting(SETTINGS.enabled) and AT.count ~= nil
end

-- ClassShoulder.lua stands the block while this is true.
function Tab.OwnsShoulder()
    return AT.built and Tab.Shown() or false
end

-------------------------------------------------------------------------------
-- Pixels
-------------------------------------------------------------------------------

local function Crisp(tex)
    if tex.SetSnapToPixelGrid then pcall(tex.SetSnapToPixelGrid, tex, true) end
    if tex.SetTexelSnappingBias then pcall(tex.SetTexelSnappingBias, tex, 0) end
    return tex
end

local function Flat(parent, layer, sub)
    local tex = Crisp(parent:CreateTexture(nil, layer or "ARTWORK", nil, sub or 0))
    tex:SetColorTexture(1, 1, 1, 1)
    return tex
end

-- The grid, the mana regen module's: px UI units a physical pixel, n physical pixels a texel (a whole number, the nearest to a
-- design px that still leaves the ring clear of the cells and the readout inside the tile).
local function SeatGrid()
    local s = Scale()
    local FH = FS.FrameHelpers
    local px = FH and FH.PixelUnit and FH.PixelUnit(AT.host) or s
    AT.s, AT.px = s, px
    local ratio = s / px
    local fit = math.min(math.floor((AT.HERO.h * ratio - 2) / AT.CELL_H), math.floor((AT.HERO.w * ratio - 4) / AT.READ_W))
    AT.n = math.max(1, math.min(math.floor(ratio + 0.5), fit))
end

local function PixelsOf(d)
    return math.floor(d * AT.s / AT.px + 0.5)
end

function Tab.Place(region, x, y, w, h)
    local px = AT.px
    local l, t = PixelsOf(x), PixelsOf(y)
    local r, b = PixelsOf(x + w), PixelsOf(y + h)
    region:ClearAllPoints()
    region:SetPoint("TOPLEFT", AT.host, "TOPLEFT", l * px, -t * px)
    region:SetSize((r - l) * px, (b - t) * px)
end
local Place = Tab.Place

local function PlacePx(region, x, y, w, h)
    local px = AT.px
    region:ClearAllPoints()
    region:SetPoint("TOPLEFT", AT.host, "TOPLEFT", x * px, -y * px)
    region:SetSize(w * px, h * px)
end

-------------------------------------------------------------------------------
-- The LED art: the mana regen module's fourteen segment cells, twice as tall (led_segments_tall.tga)
-------------------------------------------------------------------------------

-- The atlas slot order (generate_led_segments_tall.py SEGMENT_ORDER, the regen module's): slot n is column n % 4, row n // 4
-- of 32 x 32 texels.
local SEGMENT_ORDER = { "a", "b", "c", "d", "e", "f", "g1", "g2", "i", "l", "h", "j", "k", "m" }
Tab.SEGMENT_ORDER = SEGMENT_ORDER
local DIGIT_TEXT = {
    ["0"] = "a b c d e f", ["1"] = "b c", ["2"] = "a b g1 g2 e d", ["3"] = "a b c d g1 g2", ["4"] = "f b g1 g2 c",
    ["5"] = "a f g1 g2 c d", ["6"] = "a f e d c g1 g2", ["7"] = "a b c", ["8"] = "a b c d e f g1 g2",
    ["9"] = "a b c d f g1 g2",
}
Tab.DIGIT_TEXT = DIGIT_TEXT
local DIGIT = {}
do
    local index = {}
    for n, name in ipairs(SEGMENT_ORDER) do index[name] = n end
    for ch, text in pairs(DIGIT_TEXT) do
        local lit = {}
        for name in text:gmatch("%S+") do lit[index[name]] = true end
        DIGIT[ch] = lit
    end
end

-- The glyph, lying level and pointing right: "#" lit, 10 x 7 glyph pixels.
local GLYPHS = {
    arrow = { "#.....#...", ".#....##..", "..#...###.", "##########", "..#...###.", ".#....##..", "#.....#..." },
    bullet = { "#.........", "#.#####...", "#.#######.", "#.########", "#.#######.", "#.#####...", "#........." },
}
Tab.GLYPHS = GLYPHS

-- Each glyph as runs { x, y, w } one texel tall.
local RUNS = {}
for kind, rows in pairs(GLYPHS) do
    local runs = {}
    for y, row in ipairs(rows) do
        local x = 1
        while x <= #row do
            if row:sub(x, x) == "#" then
                local w = 0
                while row:sub(x + w, x + w) == "#" do w = w + 1 end
                runs[#runs + 1] = { x - 1, y - 1, w }
                x = x + w
            else
                x = x + 1
            end
        end
    end
    RUNS[kind] = runs
end
Tab.RUNS = RUNS

local function NewCell(parent, level)
    local frame = CreateFrame("Frame", nil, parent)
    frame:EnableMouse(false)
    frame:SetFrameLevel(level)
    local cell = { frame = frame, seg = {}, gl = {} }
    for n = 1, #SEGMENT_ORDER do
        local l, t = ((n - 1) % 4) * 0.25, math.floor((n - 1) / 4) * 0.25
        local gl = Crisp(frame:CreateTexture(nil, "ARTWORK", nil, 0))
        gl:SetTexture(MEDIA .. "led_segment_glow_tall.tga")
        gl:SetBlendMode("ADD")
        gl:SetTexCoord(l, l + AT.SEG_GLOW_W / AT.ATLAS, t, t + AT.SEG_GLOW_H / AT.ATLAS)
        gl:SetVertexColor(1, 1, 1, 0)
        cell.gl[n] = gl
        local tex = Crisp(frame:CreateTexture(nil, "ARTWORK", nil, 1))
        tex:SetTexture(MEDIA .. "led_segments_tall.tga")
        tex:SetTexCoord(l, l + AT.CELL_W / AT.ATLAS, t, t + AT.CELL_H / AT.ATLAS)
        cell.seg[n] = tex
    end
    return cell
end

local function Build()
    local T = FS.Theme
    local host = CreateFrame("Frame", "FSAmmoTab", UIParent)
    host:SetFrameStrata("LOW")
    host:EnableMouse(true)
    host:Hide()
    AT.host = host

    local hero = CreateFrame("Frame", nil, host)
    hero:EnableMouse(false)
    hero.fsPlate = T.AddCut2Texture(hero, MEDIA .. "led_well.tga", { 1, 1, 1, 1 }, "BACKGROUND", -8)
    T.SkinCutButton(hero, { borderColor = T.COLOR_BORDER, glowAlpha = 0 })
    Crisp(hero.fsPlate)
    if hero.fsSkin and hero.fsSkin.border and hero.fsSkin.border.ring then Crisp(hero.fsSkin.border.ring) end
    AT.shine = Flat(hero, "BACKGROUND", -7)
    AT.shine:SetVertexColor(1, 1, 1, 0.08)
    AT.hero = hero

    -- the readout: the cells and the glyph (one frame, so the idle dimming and the blink are its alpha)
    local body = CreateFrame("Frame", "FSAmmoTabReadout", host)
    body:EnableMouse(false)
    body:SetFrameLevel(hero:GetFrameLevel() + 3)
    AT.body = body
    AT.digits = {}
    for i = 1, 4 do AT.digits[i] = NewCell(body, body:GetFrameLevel() + 1) end
    AT.glyph = {}
    for kind, runs in pairs(RUNS) do
        local set = {}
        for i = 1, #runs do set[i] = Flat(body, "OVERLAY", 1) end
        AT.glyph[kind] = set
    end

    -- the blink: the readout's alpha held low, on (BLINKS times)
    if body.CreateAnimationGroup then
        local group = body:CreateAnimationGroup()
        local order = 0
        local function hold(alpha, time)
            order = order + 1
            local a = group:CreateAnimation("Alpha")
            a:SetFromAlpha(alpha)
            a:SetToAlpha(alpha)
            a:SetDuration(time)
            a:SetOrder(order)
        end
        for _ = 1, AT.BLINKS do
            hold(AT.BLINK_LOW, AT.BLINK_OFF)
            hold(1, AT.BLINK_ON)
        end
        AT.blink = group
    end

    host:SetScript("OnEnter", function(self)
        AT.hover = true
        AT.sig = nil
        Tab.Paint()
        Tab.ShowTooltip(self)
    end)
    host:SetScript("OnLeave", function()
        AT.hover = false
        AT.sig = nil
        Tab.Paint()
        if GameTooltip then GameTooltip:Hide() end
    end)
    AT.built = true
end

-- Sizes and points only, on whole pixels; legal in combat (plain frames).
local function Layout()
    local s = Scale()
    SeatGrid()
    local px, n = AT.px, AT.n
    local H = AT.HERO
    AT.host:SetSize(AT.HOST_W * s, AT.HOST_H * s)
    Place(AT.hero, H.x, H.y, H.w, H.h)
    Place(AT.body, H.x, H.y, H.w, H.h)
    Place(AT.shine, H.x + 6, H.y + 1, H.w - 7, 1)

    -- the cells and the glyph, centred on the tile as one line, every number a whole count of physical pixels
    local left = PixelsOf(H.x + H.w / 2) - math.floor(AT.READ_W * n / 2)
    local mid = PixelsOf(H.y + H.h / 2)
    local top = mid - math.floor(AT.CELL_H * n / 2)
    local gm = AT.SEG_GLOW_PAD * n
    for i, cell in ipairs(AT.digits) do
        PlacePx(cell.frame, left + (i - 1) * AT.PITCH * n, top, AT.CELL_W * n, AT.CELL_H * n)
        for _, tex in ipairs(cell.seg) do
            tex:ClearAllPoints()
            tex:SetAllPoints(cell.frame)
        end
        for _, gl in ipairs(cell.gl) do
            gl:ClearAllPoints()
            gl:SetPoint("TOPLEFT", cell.frame, "TOPLEFT", -gm * px, gm * px)
            gl:SetSize(AT.SEG_GLOW_W * n * px, AT.SEG_GLOW_H * n * px)
        end
    end
    local k = AT.GLYPH_SCALE * n
    local gx = left + (3 * AT.PITCH + AT.CELL_W + AT.GLYPH_GAP) * n
    local gy = mid - math.floor(AT.GLYPH_H * k / 2)
    for kind, set in pairs(AT.glyph) do
        for i, run in ipairs(RUNS[kind]) do
            PlacePx(set[i], gx + run[1] * k, gy + run[2] * k, run[3] * k, k)
        end
    end
    AT.sig = nil
end

-------------------------------------------------------------------------------
-- Painting (texture and font writes only)
-------------------------------------------------------------------------------

local function Color(name, fallback)
    local theme = FS.Theme
    return (theme and theme[name]) or fallback
end

-- The resting look is the mana regen module's at rest (muted digits, violet ring, the face dimmed); low and out light up
-- like its countdown, in amber and pink.
local LOOKS = {
    plenty = { lit = "COLOR_MUTED", rest = true },
    low = { lit = "COLOR_AMBER" },
    out = { lit = "COLOR_HEALTH" },
}
Tab.LOOKS = LOOKS

-- The characters the four cells show: the number right aligned, the places before it unlit (nil), "0000" for none left.
function Tab.Digits(n)
    n = math.max(0, math.min(AT.MAX, math.floor(n)))
    if n == 0 then return { "0", "0", "0", "0" } end
    local text = tostring(n)
    local out = {}
    for i = 1, 4 do
        local k = i - (4 - #text)
        out[i] = k >= 1 and text:sub(k, k) or nil
    end
    return out
end

local function PaintCell(cell, ch, c, litA, ghostA, glow)
    local lit = ch and DIGIT[ch]
    for k = 1, #SEGMENT_ORDER do
        if lit and lit[k] then
            cell.seg[k]:SetVertexColor(c[1], c[2], c[3], litA)
            cell.gl[k]:SetVertexColor(c[1], c[2], c[3], glow * litA)
        else
            cell.seg[k]:SetVertexColor(c[1], c[2], c[3], ghostA)
            cell.gl[k]:SetVertexColor(c[1], c[2], c[3], 0)
        end
    end
end

function Tab.Paint()
    if not (AT.host and AT.host:IsShown()) then return end
    local n, kind = AT.count, AT.kind
    local state = Tab.StateOf(n)
    if not state then return end
    local sig = state .. ":" .. n .. ":" .. tostring(kind) .. ":" .. tostring(AT.hover)
    local was = AT.state
    AT.state = state
    if sig == AT.sig then return end
    AT.sig = sig
    local T = FS.Theme
    local look = LOOKS[state]
    local rest = look.rest and true or false
    local c = Color(look.lit, { 1, 1, 1, 1 })
    local violet, cyan = T.COLOR_BORDER, T.COLOR_POWER

    -- the readout and the glyph, in one colour
    local litA = rest and AT.WORD_IDLE or 1
    local ghostA = rest and AT.GHOST_REST or AT.GHOST_LIT
    local glow = rest and 0 or AT.GLOW_STEADY
    local chars = Tab.Digits(n)
    for i, cell in ipairs(AT.digits) do PaintCell(cell, chars[i], c, litA, ghostA, glow) end
    local which = kind == "bullet" and "bullet" or "arrow"
    for k, set in pairs(AT.glyph) do
        for _, run in ipairs(set) do
            run:SetShown(k == which)
            run:SetVertexColor(c[1], c[2], c[3], litA)
        end
    end
    AT.body:SetAlpha(rest and AT.IDLE_ALPHA or 1)

    -- the rim: violet at rest, the state's colour when low or out, cyan under the mouse
    local ring, ringA, glowA = rest and violet or c, rest and AT.RING_IDLE or AT.RING_WARN, 0
    if AT.hover then ring, ringA, glowA = cyan, 1, AT.HOVER_GLOW end
    local skin = AT.hero.fsSkin
    if skin and skin.border and skin.border.ring then skin.border.ring:SetVertexColor(ring[1], ring[2], ring[3], ringA) end
    if skin and skin.glow then skin.glow:SetVertexColor(ring[1], ring[2], ring[3], glowA) end

    if state == "out" and was ~= nil and was ~= "out" and Setting(SETTINGS.motion) and AT.blink then
        AT.blink:Stop()
        AT.blink:Play()
    elseif state ~= "out" and AT.blink and AT.blink:IsPlaying() then
        AT.blink:Stop()
    end
end

function Tab.ShowTooltip(owner)
    local tip = GameTooltip
    if not tip then return end
    tip:SetOwner(owner, "ANCHOR_TOP")
    local ok, id = false, nil
    if GetInventoryItemID then ok, id = pcall(GetInventoryItemID, "player", 0) end
    if ok and id and not IsSecret(id) and tip.SetInventoryItem and pcall(tip.SetInventoryItem, tip, "player", 0) then
        tip:Show()
        return
    end
    tip:SetText(AT.kind == "bullet" and "Bullets" or "Arrows")
    tip:AddLine("Nothing in the ammo slot.", 1, 1, 1, true)
    tip:Show()
end

-------------------------------------------------------------------------------
-- The seat
-------------------------------------------------------------------------------

function Tab.HostPoint()
    local shoulder = FS.ClassShoulder
    if shoulder and shoulder.HostPoint then
        local ok, point, rel, relPoint, x, y = pcall(shoulder.HostPoint, AT.KEY)
        if ok and point then return point, rel, relPoint, x, y end
    end
    return nil
end

local function ApplyVisibility()
    local host = AT.host
    if not host then return end
    local want = AT.seated and Tab.Shown() or false
    host:SetShown(want)
    if want then
        AT.sig = nil
        Tab.Paint()
    else
        AT.state = nil
        if AT.blink then AT.blink:Stop() end
        if GameTooltip and GameTooltip.GetOwner and GameTooltip:GetOwner() == host then GameTooltip:Hide() end
    end
end
Tab.ApplyVisibility = ApplyVisibility

local function SeatHost()
    local host = AT.host
    local point, rel, relPoint, x, y = Tab.HostPoint()
    if not point then
        AT.seated = false
        ApplyVisibility()
        return
    end
    host:ClearAllPoints()
    host:SetPoint(point, rel, relPoint, x, y)
    if rel.GetFrameLevel then host:SetFrameLevel(rel:GetFrameLevel() + 5) end
    AT.seated = true
    ApplyVisibility()
end

local function Sync()
    if not AT.built then return end
    local ok, err = pcall(Layout)
    if not ok then WarnOnce("ammotab_layout", "ammo tab layout failed (" .. tostring(err) .. ")") end
    if InCombatLockdown() then
        AT.pendingSync = true
        return
    end
    AT.pendingSync = false
    ok, err = pcall(SeatHost)
    if not ok then WarnOnce("ammotab_sync", "ammo tab update failed (" .. tostring(err) .. ")") end
end
Tab.Sync = Sync

-- A new count or kind: repaint, and when the tab comes or goes the shoulder follows (out of combat; in combat the shoulder
-- parks the request until regen).
local function OnData()
    local before = Tab.Shown()
    Tab.Read()
    if Tab.Shown() ~= before then
        if FS.ClassShoulder and FS.ClassShoulder.Refresh then pcall(FS.ClassShoulder.Refresh) end
        ApplyVisibility()
    else
        Tab.Paint()
    end
end
Tab.OnData = OnData

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Apply()
    if not Tab.Applies() then return end
    if not (FS.Theme and FS.FrameHelpers and FS.Layout) then return end
    local data = Data()
    if not data then
        WarnOnce("ammotab_nodata", "no ammo count to read, the ammo tab is not drawn")
        return
    end
    local ok, err = pcall(Build)
    if not ok then
        WarnOnce("ammotab_build", "ammo tab failed to build (" .. tostring(err) .. ")")
        return
    end
    if data.Start then pcall(data.Start) end
    if data.Subscribe then
        data.Subscribe(function(reason)
            if reason == "ammo" or reason == "change" then OnData() end
        end)
    end
    Tab.Read()
    local events = CreateFrame("Frame")
    events:RegisterEvent("PLAYER_REGEN_ENABLED")
    events:SetScript("OnEvent", function()
        if AT.pendingSync then Sync() end
    end)
    if FS.Config and FS.Config.OnChange then
        FS.Config.OnChange(SETTINGS.enabled.key, function()
            if FS.ClassShoulder and FS.ClassShoulder.Refresh then pcall(FS.ClassShoulder.Refresh) end
            ApplyVisibility()
        end)
        local function repaint()
            AT.sig = nil
            Tab.Paint()
        end
        FS.Config.OnChange(SETTINGS.lowwarn.key, repaint)
        FS.Config.OnChange("gunsight.hunter.ammowarn", repaint)
        FS.Config.OnChange(SETTINGS.motion.key, function()
            if not Setting(SETTINGS.motion) and AT.blink then AT.blink:Stop() end
        end)
    end
    if FS.Layout.OnRescale then FS.Layout.OnRescale(Sync) end
    if FS.ActionBars and FS.ActionBars.OnGeometry then FS.ActionBars.OnGeometry(Sync) end
    if FS.ClassShoulder and FS.ClassShoulder.Refresh then
        local shouldered, why = pcall(FS.ClassShoulder.Refresh)
        if not shouldered then WarnOnce("ammotab_shoulder", "class shoulder failed (" .. tostring(why) .. ")") end
    end
    Sync()
end

-- Built at PLAYER_LOGIN (HunterState.lua has loaded by then), in combat too: nothing here is protected, and the seat waits for
-- regen inside Sync.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    local ok, err = pcall(Apply)
    if not ok then WarnOnce("ammotab_apply", "ammo tab failed to start (" .. tostring(err) .. ")") end
end)
