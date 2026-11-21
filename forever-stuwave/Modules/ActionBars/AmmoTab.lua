-- Forever STUwave: the ammo tab (look B, LED COUNTER, with the BROADHEAD arrow, of the design mockups ammo-tab-2026-11-20 and
-- ammo-tab-led-arrow-2026-11-20)
--
-- A 2 x 1 shoulder on the Console's top edge (92.8 x 49 design px) that always shows how many arrows or bullets are left.
-- ClassShoulder.lua seats it like the mana regen module: 16 design px right of the last shoulder that stands, or at the first
-- seat (36) when none does. DISPLAY ONLY: plain frames, no secure button, no binding, no click action (the mouse is on for the
-- tooltip alone).
--
-- Who: a Warrior, Hunter or Rogue (Forever's SkillLineAbility gives Bows, Crossbows and Guns to class mask 13) while the ranged
-- slot holds a bow, crossbow or gun. A wand, a thrown weapon, a relic or nothing there stands no tab and the Console's top
-- line closes.
--
-- The count is FS.HunterState's (Ammo, AmmoKind): GetItemCount of the item in the ammo slot, the read the Hunter scope's low
-- ammo warning uses, so the two never disagree. It is plain (in combat too on the Priest probe; UNVERIFIED on a Hunter).
-- Nothing in the ammo slot is 0.
--
-- The face: led_well.tga as the readout well (the mana regen module's plate) with its cut ring, four tall seven segment cells
-- and a fifth cell with the broadhead arrow (bow, crossbow) or the bullet (gun), all from led_ammo.tga, one texture per
-- segment at n physical pixels a texel (never scaled fractionally), unlit segments drawn faint; a soft copy from
-- led_ammo_glow.tga under each lit one. Positions past the number's own digits stay unlit; 0 reads 0000. Under the readout a
-- ten segment gauge drains from the right against the FULL MARK: the biggest count since the count last went up (a restock
-- or a new stack). The client has no quiver capacity to read, so the mark is ours and resets at login.
--
-- States: PLENTY (cyan digits and gauge, violet ring), LOW at or under the warn count (`gunsight.hunter.ammowarn`, default
-- 60, the scope's setting; amber digits, gauge, ring and underline), OUT at 0 (pink, and the readout blinks twice when it
-- gets there). `ammotab.lowwarn` off keeps the cyan look whatever the count; `ammotab.motion` off drops the blink.
--
-- Combat: nothing here is protected, so painting runs in combat; the host's anchor onto the Console and a shoulder that
-- comes or goes wait for PLAYER_REGEN_ENABLED (ClassShoulder.Refresh parks itself in combat). Loads after ThunderClapTab.lua,
-- before ConfigWindow.lua (which reads SETTINGS); HunterState.lua loads later and is asked for at PLAYER_LOGIN.
-- tools/ammotab-harness.py pins it against a mock. New TGAs need a full client restart.

local _, FS = ...

local Tab = {}
FS.AmmoTab = Tab

local IsSecret = FS.IsSecret
local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"

local AT = {
    KEY = "ammo",
    CLASSES = { WARRIOR = true, HUNTER = true, ROGUE = true },
    HOST_W = 92.8, HOST_H = 49,
    HERO = { x = 6, y = 6, w = 81, h = 38 },       -- the readout well, the 2 x 1 key block
    LED_CX = 46.5, LED_CY = 20,                    -- the readout's centre, design px from the host's top left
    LED_W = 66, PITCH = 12, GLYPH_X = 57,          -- texels: four digits on a 12 pitch, the glyph cell at 57
    CELL_W = 9, CELL_H = 18, SLOT_W = 16, SLOT_H = 32, ATLAS_W = 128, ATLAS_H = 64,
    GLOW_PAD = 2, GLOW_W = 13, GLOW_H = 22,
    ARROW_SLOT = 7, BULLET_SLOT = 8,
    ROOM_H = 28,                                   -- design px above the gauge the readout may fill (y 6..34)
    GAUGE_N = 10, GAUGE_X = 11, GAUGE_PITCH = 7, GAUGE_SEG_W = 6, GAUGE_Y = 35, GAUGE_H = 4, GAUGE_GLOW_PAD = 1,
    UL = { x = 11, y = 47, w = 71, h = 1 },
    GHOST = { 0x22 / 255, 0x16 / 255, 0x3e / 255 },  -- #22163e an unlit segment
    GAUGE_OFF = { 0x1e / 255, 0x12 / 255, 0x38 / 255 },  -- #1e1238 an empty gauge segment
    GLOW_LIT = 0.5, GLOW_GAUGE = 0.6,
    RING_PLENTY = 0.6, HALO_PLENTY = 0.25, HALO_WARN = 0.55,
    BLINK_ON = 0.45, BLINK_OFF = 0.45, BLINK_LOW = 0.25, BLINKS = 2,
    MAX = 9999,
    host = nil, built = false, seated = false, pendingSync = false,
    count = nil, kind = nil, full = nil, state = nil, sig = nil,
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
        tip = "Turns the tab amber when you are down to the low ammo count and pink when you are out. Off keeps it cyan.",
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

-- The count and kind from HunterState; the full mark follows: any rise (a restock, a new stack) sets it to the count, a new
-- weapon kind too. A count of nil (no weapon that fires ammo, unreadable) leaves the mark alone.
function Tab.Read()
    local data = Data()
    local n = data and data.Ammo() or nil
    if IsSecret(n) or type(n) ~= "number" then n = nil end
    local kind = data and data.AmmoKind and data.AmmoKind() or nil
    if kind ~= "bullet" then kind = n and "arrow" or nil end
    if n then
        n = math.max(0, math.floor(n))
        if AT.full == nil or AT.count == nil or n > AT.count or kind ~= AT.kind then AT.full = n end
        if n > AT.full then AT.full = n end
    end
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

-- The grid: px UI units a physical pixel, n physical pixels a texel (a whole number, the nearest to a design px that still fits
-- the readout over the gauge and inside the well).
local function SeatGrid()
    local s = Scale()
    local FH = FS.FrameHelpers
    local px = FH and FH.PixelUnit and FH.PixelUnit(AT.host) or s
    AT.s, AT.px = s, px
    local ratio = s / px
    local fitH = math.floor(AT.ROOM_H * ratio / AT.CELL_H)
    local fitW = math.floor((AT.HERO.w - 3) * ratio / AT.LED_W)
    AT.n = math.max(1, math.min(math.floor(ratio + 0.5), fitH, fitW))
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
-- The LED art
-------------------------------------------------------------------------------

local SEGMENT_ORDER = { "a", "b", "c", "d", "e", "f", "g" }
Tab.SEGMENT_ORDER = SEGMENT_ORDER
local DIGIT_TEXT = {
    ["0"] = "abcdef", ["1"] = "bc", ["2"] = "abged", ["3"] = "abgcd", ["4"] = "fgbc",
    ["5"] = "afgcd", ["6"] = "afgedc", ["7"] = "abc", ["8"] = "abcdefg", ["9"] = "abcdfg",
}
Tab.DIGIT_TEXT = DIGIT_TEXT
local DIGIT = {}
for ch, text in pairs(DIGIT_TEXT) do
    local lit = {}
    for n, name in ipairs(SEGMENT_ORDER) do
        if text:find(name, 1, true) then lit[n] = true end
    end
    DIGIT[ch] = lit
end

local function SlotCoords(slot, w, h)
    local ox, oy = (slot % 8) * AT.SLOT_W, math.floor(slot / 8) * AT.SLOT_H
    return ox / AT.ATLAS_W, (ox + w) / AT.ATLAS_W, oy / AT.ATLAS_H, (oy + h) / AT.ATLAS_H
end

-- One piece of a cell: the hard texture and its soft copy under it.
local function NewPiece(frame, slot)
    local gl = Crisp(frame:CreateTexture(nil, "ARTWORK", nil, 0))
    gl:SetTexture(MEDIA .. "led_ammo_glow.tga")
    gl:SetBlendMode("ADD")
    gl:SetTexCoord(SlotCoords(slot, AT.GLOW_W, AT.GLOW_H))
    gl:SetVertexColor(1, 1, 1, 0)
    local tex = Crisp(frame:CreateTexture(nil, "ARTWORK", nil, 1))
    tex:SetTexture(MEDIA .. "led_ammo.tga")
    tex:SetTexCoord(SlotCoords(slot, AT.CELL_W, AT.CELL_H))
    return { tex = tex, gl = gl }
end

local function NewCell(parent, slots)
    local frame = CreateFrame("Frame", nil, parent)
    frame:EnableMouse(false)
    frame:SetFrameLevel(parent:GetFrameLevel() + 1)
    local cell = { frame = frame, pieces = {} }
    for i, slot in ipairs(slots) do cell.pieces[i] = NewPiece(frame, slot) end
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
    T.SkinCutButton(hero, { borderColor = T.COLOR_BORDER, glowAlpha = AT.HALO_PLENTY })
    Crisp(hero.fsPlate)
    if hero.fsSkin and hero.fsSkin.border and hero.fsSkin.border.ring then Crisp(hero.fsSkin.border.ring) end
    AT.shine = Flat(hero, "BACKGROUND", -7)
    AT.shine:SetVertexColor(1, 1, 1, 0.08)
    AT.hero = hero

    local body = CreateFrame("Frame", "FSAmmoTabReadout", host)
    body:EnableMouse(false)
    body:SetFrameLevel(hero:GetFrameLevel() + 3)
    AT.body = body
    local segs = {}
    for n = 1, #SEGMENT_ORDER do segs[n] = n - 1 end
    AT.digits = {}
    for i = 1, 4 do AT.digits[i] = NewCell(body, segs) end
    AT.glyph = NewCell(body, { AT.ARROW_SLOT, AT.BULLET_SLOT })

    local gauge = { seg = {}, gl = {} }
    for i = 1, AT.GAUGE_N do
        local gl = Crisp(body:CreateTexture(nil, "ARTWORK", nil, -1))
        gl:SetTexture(MEDIA .. "led_glow.tga")
        gl:SetBlendMode("ADD")
        gl:SetVertexColor(1, 1, 1, 0)
        gauge.gl[i] = gl
        gauge.seg[i] = Flat(body, "ARTWORK", 0)
    end
    AT.gauge = gauge

    AT.underline = Flat(host, "OVERLAY", 0)

    -- the blink: the readout's alpha held on, low, on, low (BLINKS times), then back to 1
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

    host:SetScript("OnEnter", function(self) Tab.ShowTooltip(self) end)
    host:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
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
    local U = AT.UL
    Place(AT.underline, U.x, U.y, U.w, U.h)
    for i = 1, AT.GAUGE_N do
        local x = AT.GAUGE_X + (i - 1) * AT.GAUGE_PITCH
        Place(AT.gauge.seg[i], x, AT.GAUGE_Y, AT.GAUGE_SEG_W, AT.GAUGE_H)
        local gp = AT.GAUGE_GLOW_PAD
        Place(AT.gauge.gl[i], x - gp, AT.GAUGE_Y - gp, AT.GAUGE_SEG_W + 2 * gp, AT.GAUGE_H + 2 * gp)
    end
    local left = PixelsOf(AT.LED_CX) - math.floor(AT.LED_W * n / 2)
    local top = PixelsOf(AT.LED_CY) - math.floor(AT.CELL_H * n / 2)
    local gm = AT.GLOW_PAD * n
    local function seat(cell, x)
        PlacePx(cell.frame, x, top, AT.CELL_W * n, AT.CELL_H * n)
        for _, piece in ipairs(cell.pieces) do
            piece.tex:ClearAllPoints()
            piece.tex:SetAllPoints(cell.frame)
            piece.gl:ClearAllPoints()
            piece.gl:SetPoint("TOPLEFT", cell.frame, "TOPLEFT", -gm * px, gm * px)
            piece.gl:SetSize(AT.GLOW_W * n * px, AT.GLOW_H * n * px)
        end
    end
    for i, cell in ipairs(AT.digits) do seat(cell, left + (i - 1) * AT.PITCH * n) end
    seat(AT.glyph, left + AT.GLYPH_X * n)
    AT.sig = nil
end

-------------------------------------------------------------------------------
-- Painting (texture writes only)
-------------------------------------------------------------------------------

local function Color(name, fallback)
    local theme = FS.Theme
    return (theme and theme[name]) or fallback
end

local LOOKS = {
    plenty = { lit = "COLOR_POWER", ring = "COLOR_BORDER", ringA = AT.RING_PLENTY, halo = AT.HALO_PLENTY, ul = "COLOR_BORDER" },
    low = { lit = "COLOR_AMBER", ring = "COLOR_AMBER", ringA = 1, halo = AT.HALO_WARN, ul = "COLOR_AMBER" },
    out = { lit = "COLOR_HEALTH", ring = "COLOR_HEALTH", ringA = 1, halo = AT.HALO_WARN, ul = "COLOR_HEALTH" },
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

-- How many of the ten gauge segments are lit: the count over the full mark, rounded up (one is lit while any is left).
function Tab.GaugeLit(n, full)
    if type(n) ~= "number" or n <= 0 then return 0 end
    if type(full) ~= "number" or full <= 0 then return AT.GAUGE_N end
    return math.max(1, math.min(AT.GAUGE_N, math.ceil(n / full * AT.GAUGE_N - 1e-9)))
end

local function PaintPiece(piece, on, c)
    if on then
        piece.tex:SetVertexColor(c[1], c[2], c[3], 1)
        piece.gl:SetVertexColor(c[1], c[2], c[3], AT.GLOW_LIT)
    else
        local g = AT.GHOST
        piece.tex:SetVertexColor(g[1], g[2], g[3], 1)
        piece.gl:SetVertexColor(c[1], c[2], c[3], 0)
    end
end

function Tab.Paint()
    if not (AT.host and AT.host:IsShown()) then return end
    local n, kind = AT.count, AT.kind
    local state = Tab.StateOf(n)
    if not state then return end
    local sig = state .. ":" .. n .. ":" .. tostring(AT.full) .. ":" .. tostring(kind)
    local was = AT.state
    AT.state = state
    if sig == AT.sig then return end
    AT.sig = sig
    local look = LOOKS[state]
    local c = Color(look.lit, { 1, 1, 1, 1 })
    local chars = Tab.Digits(n)
    for i, cell in ipairs(AT.digits) do
        local lit = chars[i] and DIGIT[chars[i]]
        for k, piece in ipairs(cell.pieces) do PaintPiece(piece, lit and lit[k], c) end
    end
    local arrow = kind ~= "bullet"
    local a, b = AT.glyph.pieces[1], AT.glyph.pieces[2]
    PaintPiece(a, true, c)
    PaintPiece(b, true, c)
    a.tex:SetShown(arrow)
    a.gl:SetShown(arrow)
    b.tex:SetShown(not arrow)
    b.gl:SetShown(not arrow)
    local on = Tab.GaugeLit(n, AT.full)
    local off = AT.GAUGE_OFF
    for i = 1, AT.GAUGE_N do
        if i <= on then
            AT.gauge.seg[i]:SetVertexColor(c[1], c[2], c[3], 1)
            AT.gauge.gl[i]:SetVertexColor(c[1], c[2], c[3], AT.GLOW_GAUGE)
        else
            AT.gauge.seg[i]:SetVertexColor(off[1], off[2], off[3], 1)
            AT.gauge.gl[i]:SetVertexColor(c[1], c[2], c[3], 0)
        end
    end
    local ring = Color(look.ring, c)
    local skin = AT.hero.fsSkin
    if skin and skin.border and skin.border.ring then skin.border.ring:SetVertexColor(ring[1], ring[2], ring[3], look.ringA) end
    if skin and skin.glow then skin.glow:SetVertexColor(ring[1], ring[2], ring[3], look.halo) end
    local ul = Color(look.ul, ring)
    AT.underline:SetVertexColor(ul[1], ul[2], ul[3], 0.9)
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
