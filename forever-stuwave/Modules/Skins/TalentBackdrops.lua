-- Forever STUwave: talent spec backgrounds
-- A looping pixel-art scene behind each talent tree, one per spec (the approved mockup
-- mockups/talent-spec-backgrounds-2026-11-15.html; the scenes are tools/assets/talentbg/scenes/*.js, baked by bake.mjs into one
-- flipbook sheet per spec and the generated manifest TalentBgArt.lua).
--
--   * Each of the three tree panels Talents.lua builds (FS.TalentsSkin.state.cols[i], left to right) gets one texture of ours on
--     the panel's own frame, between the panel's ink fill (BACKGROUND) and its ring (BORDER 1), so below the talent buttons and
--     arrows (children of the ButtonsParent, a level up). It is inset INSET physical px inside the plate, which clears the cut
--     corners, so nothing is baked for them.
--   * The picture is shown at a whole number scale (every scene pixel the same size on screen): the smallest integer scale that
--     covers the panel, centred, the overflow cropped with texcoords. NEAREST filtering keeps the pixels crisp.
--   * The sheet is the player's class token and the tree index. The inspect view of another player draws nothing.
--   * One driver frame of ours, a child of the talents frame, steps all three textures together at FPS while the talent page is
--     on screen; a hidden page stops it with no extra code. A tick only adds the elapsed time, and when the cell changes calls
--     SetTexCoord on each texture with numbers worked out when the panels were laid out: nothing is allocated per tick.
--   * Setting talents.backdrop: "animated" (default), "still" (one frame, the driver stopped), "off" (textures cleared so the
--     sheets can unload). ForeverSTUwaveDB.reducedMotion turns animated into still.
--
-- Skin only: our own textures and frames, a post-hook on our own FS.TalentsSkin.Layout. No stock frame is touched.

local _, FS = ...

local Art, Tal, Config, Kit = FS.TalentBgArt, FS.TalentsSkin, FS.Config, FS.ControlKit
if not (Art and Tal and Tal.state and Config and Kit) then return end

local M = {}
FS.TalentBackdrops = M

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local INSET = 4
local W, H, CW, CH, COLS, SHEET, FRAMES, FPS = Art.W, Art.H, Art.CW, Art.CH, Art.COLS, Art.SHEET, Art.FRAMES, Art.FPS
local STILL_FRAME = 0
local STEP = 1 / FPS

M.SETTING = {
    key = "talents.backdrop", default = "animated", label = "Talent backgrounds",
    tip = "A painted scene behind each talent tree, one per spec. Animated loops it, Still shows one frame, Off draws nothing "
        .. "and frees the art. Reduced motion shows it still.",
}
M.STYLES = { "animated", "still", "off" }
M.STYLE_TEXT = { animated = "Animated", still = "Still", off = "Off" }
Config.RegisterDefault(M.SETTING.key, M.SETTING.default)

-- the top left texel of each frame's cell, as texcoords
local CELL_U, CELL_V = {}, {}
for f = 0, FRAMES - 1 do
    CELL_U[f] = ((f % COLS) * CW + 1) / SHEET
    CELL_V[f] = (math.floor(f / COLS) * CH + 1) / SHEET
end

local recs = {}
M.recs = recs
local frame = 0
local driver

function M.Mode()
    local mode = Config.Get(M.SETTING.key)
    if mode ~= "still" and mode ~= "off" then mode = "animated" end
    if mode == "animated" and type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.reducedMotion == true then mode = "still" end
    return mode
end

local function Show(rec, f)
    local u, v = CELL_U[f], CELL_V[f]
    rec.tex:SetTexCoord(u + rec.u0, u + rec.u1, v + rec.v0, v + rec.v1)
end

local function Tick(_, elapsed)
    driver.acc = driver.acc + elapsed
    if driver.acc < STEP then return end
    local k = math.floor(driver.acc / STEP)
    driver.acc = driver.acc - k * STEP
    frame = (frame + k) % FRAMES
    for i = 1, #recs do
        local rec = recs[i]
        if rec.on then Show(rec, frame) end
    end
end

local function Driver(tf)
    if driver then return driver end
    driver = CreateFrame("Frame", nil, tf)
    driver.acc = 0
    driver:SetScript("OnHide", function(self) self.acc = 0 end)
    return driver
end

local function Inspecting(tf)
    local fn = tf.IsInspecting
    if type(fn) ~= "function" then return false end
    local ok, v = pcall(fn, tf)
    return ok and v == true
end

local function ClassSheets()
    local _, token = UnitClass("player")
    return type(token) == "string" and Art.sheets[token] or nil
end

local function Clear(rec)
    if not rec.tex then return end
    rec.tex:Hide()
    if rec.file then rec.tex:SetTexture(nil) end
    rec.file, rec.on, rec.w, rec.h = nil, false, nil, nil
end

-- Seats tree i's texture on its panel: the sheet, the whole number scale, the centred crop.
local function SeatOne(i, col, sheets, mode)
    local rec = recs[i]
    if not rec then
        rec = { tex = col.frame:CreateTexture(nil, "BORDER", nil, -1), on = false }
        Kit.Snap(rec.tex)
        recs[i] = rec
    end
    local name = sheets and sheets[i]
    if mode == "off" or type(name) ~= "string" then return Clear(rec) end
    local pw, ph = Kit.SizePx(col.frame)
    if not pw then return Clear(rec) end
    local iw, ih = pw - 2 * INSET, ph - 2 * INSET
    if iw < 8 or ih < 8 then return Clear(rec) end
    if rec.file ~= name then
        local ok = pcall(rec.tex.SetTexture, rec.tex, MEDIA .. name .. ".tga", "CLAMP", "CLAMP", "NEAREST")
        if not ok then return Clear(rec) end
        rec.file = name
    end
    if rec.w ~= iw or rec.h ~= ih then
        rec.w, rec.h = iw, ih
        local s = math.max(1, math.ceil(math.max(iw / W, ih / H)))
        local vw, vh = iw / s, ih / s
        local x0, y0 = (W - vw) / 2, (H - vh) / 2
        rec.u0, rec.u1 = x0 / SHEET, (x0 + vw) / SHEET
        rec.v0, rec.v1 = y0 / SHEET, (y0 + vh) / SHEET
        rec.scale = s
        Kit.Place(rec.tex, col.frame, INSET, INSET, iw, ih)
    end
    rec.on = true
    Show(rec, mode == "animated" and frame or STILL_FRAME)
    rec.tex:Show()
end

-- Lays out every panel's texture and starts or stops the driver. Run after Talents.lua lays out its panels, and on a setting change.
function M.Seat()
    local S = Tal.state
    local tf = S.tf
    if not tf then return end
    local mode = M.Mode()
    local sheets = not Inspecting(tf) and ClassSheets() or nil
    local cols = S.cols or {}
    for i = 1, math.max(#cols, #recs) do
        local col = cols[i]
        if col and col.frame then SeatOne(i, col, sheets, mode)
        elseif recs[i] then Clear(recs[i]) end
    end
    local any = false
    for i = 1, #recs do any = any or recs[i].on end
    local d = Driver(tf)
    if mode == "animated" and any then
        if d:GetScript("OnUpdate") ~= Tick then d:SetScript("OnUpdate", Tick) end
    else
        d:SetScript("OnUpdate", nil)
        d.acc = 0
    end
end

local function SafeSeat()
    local ok, err = pcall(M.Seat)
    if not ok and FS.LogDegradeOnce then
        FS.LogDegradeOnce("talentbackdrops:seat", "|cffff4488Forever STUwave|r: talent backgrounds failed: " .. tostring(err))
    end
end

hooksecurefunc(Tal, "Layout", SafeSeat)
Config.OnChange(M.SETTING.key, SafeSeat)
