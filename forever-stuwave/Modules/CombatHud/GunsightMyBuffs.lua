-- Forever STUwave: Gunsight "mybuffs" piece, a flank plate of up to four of the player's buffs outboard of the next cast tile, the time left under each and a cyan pip on a buff cast by a party or raid member.
-- It reads only the FS.PlayerAuras snapshot (plain values, frozen in combat), so in combat the time left is extrapolated from the stored expiry.
-- Tiles keep the snapshot's slot order; sorting by time left would shuffle them as the clocks tick.

local _, FS = ...

local Gunsight = FS.Gunsight
if type(Gunsight) ~= "table" or type(Gunsight.OnReady) ~= "function" then return end

local GunsightMyBuffs = {}
FS.GunsightMyBuffs = GunsightMyBuffs

local ui = Gunsight.ui
local IsSecret = FS.IsSecret or function() return false end

-- Mockup buffs() (gunsight-modules-concepts-v7): image px. TILE_DX / TILE_DY seat a tile from the plate's top left,
-- TEXT_DX is the time text's centre from the tile's left, PIP_DX / PIP_DY the pip's centre from the tile's top left.
local C = {
    X = 498, Y = 424, W = 164, H = 56, CHAMFER = 6,
    FILL = { 13 / 255, 6 / 255, 32 / 255, 0.7 }, STROKE_A = 0.75,
    MAX = 4, TILE = 24, PITCH = 38, TILE_DX = 10, TILE_DY = 6,
    TILE_FILL_A = 0.9, TILE_INSET = 2, ICON_CROP = 0.08,
    PIP_DX = 24, PIP_DY = 2, PIP_R = 3.2, PIP_RING = 1,
    TEXT_DX = 12, TEXT_Y = 46, TEXT_SIZE = 12, DESCENT = 0.22,
    TICK = 0.5, MIN_FONT = 6,
}
GunsightMyBuffs.C = C

local Theme = FS.Theme
local colors = {
    bg = { 13 / 255, 6 / 255, 32 / 255, 1 },
    cyan = (Theme and Theme.COLOR_POWER) or { 0.133, 0.878, 1, 1 },
    steel = (Theme and Theme.COLOR_STEEL) or { 0.5529, 0.5765, 0.651, 1 },
    white = { 0xf3 / 255, 0xfb / 255, 1, 1 },
}

local state = { plate = nil, body = nil, tiles = {}, fallbackAnchor = nil, warned = false }
local pipCache = setmetatable({}, { __mode = "k" })

local function Guard(fn, ...)
    local ok, err = pcall(fn, ...)
    if ok or state.warned then return end
    state.warned = true
    if FS.LogDegradeOnce then
        FS.LogDegradeOnce("gunsightmybuffs_update", "|cffff4488Forever STUwave|r: my buffs update failed: " .. tostring(err))
    end
end

local function FontSize()
    return math.max(C.MIN_FONT, math.floor(ui(C.TEXT_SIZE) + 0.5))
end

local function FormatTime(remaining)
    if remaining >= 3600 then return string.format("%dh", math.floor(remaining / 3600)) end
    if remaining >= 60 then return string.format("%dm", math.floor(remaining / 60)) end
    return string.format("%ds", math.floor(remaining))
end

-- True for a buff cast by a party or raid member other than the player. A missing, secret or odd source is no pip;
-- you can be raidN in a raid, so UnitIsUnit settles it. Cached per snapshot entry (entries are replaced, never mutated).
local function FromGroupMember(aura)
    local cached = pipCache[aura]
    if cached ~= nil then return cached end
    local unit = aura.sourceUnit
    local result = false
    if not IsSecret(unit) and type(unit) == "string" and (unit:find("^party%d+$") or unit:find("^raid%d+$")) then
        result = true
        if type(UnitIsUnit) == "function" then
            local same = UnitIsUnit(unit, "player")
            if not IsSecret(same) and same == true then result = false end
        end
    end
    pipCache[aura] = result
    return result
end

local function PaintTile(tile, aura, remaining)
    if tile.iconKey ~= aura.icon then
        tile.iconKey = aura.icon
        tile.icon:SetTexture(aura.icon)
    end
    local text = remaining and FormatTime(remaining) or ""
    if tile.text ~= text then
        tile.text = text
        tile.label:SetText(text)
    end
    tile.pip.dot:SetShown(FromGroupMember(aura))
    tile.pip.ring:SetShown(FromGroupMember(aura))
    tile.frame:Show()
end

-- Slot order, first four that have not run out. An expiry of 0 means no expiry.
local function Refresh()
    local body = state.body
    if not body then return end
    local auras = FS.PlayerAuras
    local snapshot = type(auras) == "table" and type(auras.Get) == "function" and auras.Get() or nil
    local list = type(snapshot) == "table" and snapshot.buffs or nil
    local shown = 0
    if type(list) == "table" then
        local now = GetTime()
        for i = 1, #list do
            local aura = list[i]
            local expires = aura.expirationTime
            local remaining
            if type(expires) == "number" and expires > 0 then remaining = expires - now end
            if remaining == nil or remaining > 0 then
                shown = shown + 1
                PaintTile(state.tiles[shown], aura, remaining)
                if shown == C.MAX then break end
            end
        end
    end
    for i = shown + 1, C.MAX do state.tiles[i].frame:Hide() end
    body:SetShown(shown > 0)
end

local function Layout()
    local body = state.body
    local k = ui(1)
    local fontSize = FontSize()
    for i, tile in ipairs(state.tiles) do
        local left = C.TILE_DX + (i - 1) * C.PITCH
        tile.frame:ClearAllPoints()
        tile.frame:SetPoint("TOPLEFT", body, "TOPLEFT", left * k, -C.TILE_DY * k)
        tile.frame:SetSize(C.TILE * k, C.TILE * k)
        tile.icon:ClearAllPoints()
        tile.icon:SetPoint("TOPLEFT", tile.frame, "TOPLEFT", C.TILE_INSET * k, -C.TILE_INSET * k)
        tile.icon:SetPoint("BOTTOMRIGHT", tile.frame, "BOTTOMRIGHT", -C.TILE_INSET * k, C.TILE_INSET * k)
        FS.Theme.ApplyMono(tile.label, fontSize, colors.white)
        tile.label:ClearAllPoints()
        tile.label:SetPoint("BOTTOM", body, "TOPLEFT", (left + C.TEXT_DX) * k, -(C.TEXT_Y + C.TEXT_SIZE * C.DESCENT) * k)
        tile.label:SetWidth(C.PITCH * k)
        for _, part in ipairs({ { tile.pip.ring, C.PIP_R + C.PIP_RING }, { tile.pip.dot, C.PIP_R } }) do
            part[1]:ClearAllPoints()
            part[1]:SetPoint("CENTER", tile.frame, "TOPLEFT", C.PIP_DX * k, -C.PIP_DY * k)
            part[1]:SetSize(2 * part[2] * k, 2 * part[2] * k)
        end
    end
end

local function BuildTile(body)
    local tile = {}
    local frame = CreateFrame("Frame", nil, body)
    Theme.AddCut2Texture(frame, Theme.SLICE_CUT2_FILL_TEXTURE,
        { colors.bg[1], colors.bg[2], colors.bg[3], C.TILE_FILL_A }, "BACKGROUND", 0)
    tile.icon = frame:CreateTexture(nil, "ARTWORK")
    tile.icon:SetTexCoord(C.ICON_CROP, 1 - C.ICON_CROP, C.ICON_CROP, 1 - C.ICON_CROP)
    Theme.AddCut2Texture(frame, Theme.SLICE_CUT2_OUTLINE_TEXTURE, colors.steel, "BORDER")
    local ring = frame:CreateTexture(nil, "OVERLAY", nil, 1)
    ring:SetColorTexture(colors.bg[1], colors.bg[2], colors.bg[3], 1)
    local dot = frame:CreateTexture(nil, "OVERLAY", nil, 2)
    dot:SetColorTexture(colors.cyan[1], colors.cyan[2], colors.cyan[3], 1)
    ring:Hide()
    dot:Hide()
    tile.pip = { ring = ring, dot = dot }
    tile.label = body:CreateFontString(nil, "OVERLAY")
    Theme.ApplyMono(tile.label, FontSize(), colors.white)
    tile.label:SetJustifyH("CENTER")
    tile.label:SetText("")
    frame:Hide()
    tile.frame = frame
    return tile
end

-- Gunsight's own "mybuffs" anchor when it has one, else a frame of the module's at the mockup's rect.
local function SeatFallback()
    local anchor = state.fallbackAnchor
    if not anchor then return end
    anchor:SetSize(ui(C.W), ui(C.H))
    Gunsight.Point(anchor, "TOPLEFT", C.X, C.Y)
end

local function Anchor()
    local anchor = Gunsight.anchors and Gunsight.anchors.mybuffs
    if anchor then return anchor end
    state.fallbackAnchor = CreateFrame("Frame", nil, Gunsight.root)
    SeatFallback()
    return state.fallbackAnchor
end

local function Build()
    if not Gunsight.IsEnabled() then return end
    local anchor = Anchor()
    GunsightMyBuffs.anchor = anchor
    local plate = CreateFrame("Frame", "ForeverSTUwaveGunsightMyBuffs", Gunsight.root)
    plate:SetPoint("TOPLEFT", anchor, "TOPLEFT", 0, 0)
    plate:SetPoint("BOTTOMRIGHT", anchor, "BOTTOMRIGHT", 0, 0)
    -- The body holds everything drawn, so an empty plate can hide without stopping the plate's own ticker.
    local body = CreateFrame("Frame", nil, plate)
    body:SetPoint("TOPLEFT", plate, "TOPLEFT", 0, 0)
    body:SetPoint("BOTTOMRIGHT", plate, "BOTTOMRIGHT", 0, 0)
    state.plate, state.body = plate, body
    GunsightMyBuffs.plate, GunsightMyBuffs.body = plate, body
    Theme.AddCut2Texture(body, Theme.SLICE_CUT2_FILL_TEXTURE, C.FILL, "BACKGROUND", 0)
    Theme.AddCut2Texture(body, Theme.SLICE_CUT2_OUTLINE_TEXTURE,
        { colors.cyan[1], colors.cyan[2], colors.cyan[3], C.STROKE_A }, "BORDER")
    for i = 1, C.MAX do state.tiles[i] = BuildTile(body) end
    GunsightMyBuffs.tiles = state.tiles
    body:Hide()
    Layout()

    local elapsed = 0
    plate:SetScript("OnUpdate", function(_, dt)
        elapsed = elapsed + dt
        if elapsed < C.TICK then return end
        elapsed = 0
        Guard(Refresh)
    end)

    local events = CreateFrame("Frame", nil, plate)
    if not pcall(events.RegisterUnitEvent, events, "UNIT_AURA", "player") then events:RegisterEvent("UNIT_AURA") end
    events:RegisterEvent("PLAYER_ENTERING_WORLD")
    events:RegisterEvent("PLAYER_REGEN_ENABLED")
    events:SetScript("OnEvent", function(_, event, unit)
        if event == "UNIT_AURA" and not IsSecret(unit) and type(unit) == "string" and unit ~= "player" then return end
        Guard(Refresh)
    end)

    Gunsight.RegisterPiece("mybuffs", { frame = plate, onShow = function() Guard(Refresh) end })
    Guard(Refresh)
    if FS.Layout and FS.Layout.OnRescale then
        FS.Layout.OnRescale(function()
            SeatFallback()
            Layout()
        end)
    end
end

GunsightMyBuffs.Refresh = function() Guard(Refresh) end

Gunsight.OnReady(function()
    local ok, err = pcall(Build)
    if not ok and FS.LogDegradeOnce then
        FS.LogDegradeOnce("gunsightmybuffs_build", "|cffff4488Forever STUwave|r: my buffs build failed: " .. tostring(err))
    end
end)
