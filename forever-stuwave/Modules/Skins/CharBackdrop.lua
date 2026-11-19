-- Forever STUwave: the character window backdrop
-- A looping pixel-art scene in the model well behind the character (Aurora Night: tools/assets/charbg/scenes/c_aurora.js,
-- baked by tools/assets/charbg/bake.mjs into one flipbook sheet and the generated manifest CharBgArt.lua).
--
--   * One texture of ours on the well frame Character.lua builds (FS.CharacterSkin.state.well), between the well's ink fill
--     (BACKGROUND) and its ring (BORDER 1). The well sits a level under the model scene, so the model draws over it. It is
--     inset INSET physical px inside the plate, which clears the cut corners.
--   * Shown at a whole number scale (every scene pixel the same size on screen): the smallest integer scale that covers the
--     well, centred across, the overflow cropped with texcoords. The crop keeps the bottom, so the ground stays under the feet.
--     NEAREST filtering keeps the pixels crisp.
--   * One driver frame of ours, a child of the well, steps the texture at FPS while the paper doll is on screen; a hidden page
--     stops it with no extra code. A tick only adds the elapsed time and, when the cell changes, calls SetTexCoord with numbers
--     worked out at layout: nothing is allocated per tick.
--   * Setting character.backdrop: "animated" (default), "still" (one frame, the driver stopped), "off" (texture cleared so the
--     sheet can unload). ForeverSTUwaveDB.reducedMotion turns animated into still.
--
-- Skin only: our own texture and frame, run from our own Character.lua well layout hook. No stock frame is touched.

local _, FS = ...

local Art, Char, Config, Kit = FS.CharBgArt, FS.CharacterSkin, FS.Config, FS.ControlKit
if not (Art and Char and Char.state and Config and Kit) then return end

local M = {}
FS.CharBackdrop = M

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local INSET = 5
local W, H, CW, CH, COLS, SHEET, FRAMES, FPS = Art.W, Art.H, Art.CW, Art.CH, Art.COLS, Art.SHEET, Art.FRAMES, Art.FPS
local STILL_FRAME = 0
local STEP = 1 / FPS

M.SETTING = {
    key = "character.backdrop", default = "animated", label = "Character background",
    tip = "A painted scene behind your character in the character window. Animated loops it, Still shows one frame, Off draws "
        .. "nothing and frees the art. Reduced motion shows it still.",
}
M.STYLES = { "animated", "still", "off" }
M.STYLE_TEXT = { animated = "Animated", still = "Still", off = "Off" }
Config.RegisterDefault(M.SETTING.key, M.SETTING.default)

local CELL_U, CELL_V = {}, {}
for f = 0, FRAMES - 1 do
    CELL_U[f] = ((f % COLS) * CW + 1) / SHEET
    CELL_V[f] = (math.floor(f / COLS) * CH + 1) / SHEET
end

local rec = { on = false }
M.rec = rec
local frame = 0
local driver

function M.Mode()
    local mode = Config.Get(M.SETTING.key)
    if mode ~= "still" and mode ~= "off" then mode = "animated" end
    if mode == "animated" and type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.reducedMotion == true then mode = "still" end
    return mode
end

local function Show(f)
    local u, v = CELL_U[f], CELL_V[f]
    rec.tex:SetTexCoord(u + rec.u0, u + rec.u1, v + rec.v0, v + rec.v1)
end

local function Tick(_, elapsed)
    driver.acc = driver.acc + elapsed
    if driver.acc < STEP then return end
    local k = math.floor(driver.acc / STEP)
    driver.acc = driver.acc - k * STEP
    frame = (frame + k) % FRAMES
    if rec.on then Show(frame) end
end

local function Clear()
    if not rec.tex then return end
    rec.tex:Hide()
    if rec.file then rec.tex:SetTexture(nil) end
    rec.file, rec.on, rec.w, rec.h = nil, false, nil, nil
end

local function SeatTexture(well, mode)
    if not rec.tex then
        rec.tex = well.frame:CreateTexture(nil, "BORDER", nil, -1)
        Kit.Snap(rec.tex)
    end
    if mode == "off" then return Clear() end
    local pw, ph = well.wpx, well.hpx
    if type(pw) ~= "number" or type(ph) ~= "number" then return Clear() end
    local iw, ih = pw - 2 * INSET, ph - 2 * INSET
    if iw < 8 or ih < 8 then return Clear() end
    if rec.file ~= Art.sheet then
        local ok = pcall(rec.tex.SetTexture, rec.tex, MEDIA .. Art.sheet .. ".tga", "CLAMP", "CLAMP", "NEAREST")
        if not ok then return Clear() end
        rec.file = Art.sheet
    end
    if rec.w ~= iw or rec.h ~= ih then
        rec.w, rec.h = iw, ih
        local s = math.max(1, math.ceil(math.max(iw / W, ih / H)))
        local vw, vh = iw / s, ih / s
        local x0, y0 = (W - vw) / 2, H - vh
        rec.u0, rec.u1 = x0 / SHEET, (x0 + vw) / SHEET
        rec.v0, rec.v1 = y0 / SHEET, (y0 + vh) / SHEET
        rec.scale = s
        Kit.Place(rec.tex, well.frame, INSET, INSET, iw, ih)
    end
    rec.on = true
    Show(mode == "animated" and frame or STILL_FRAME)
    rec.tex:Show()
end

-- Seats the texture in the well and starts or stops the driver. Run after Character.lua lays out the well, and on a setting change.
function M.Seat()
    local well = Char.state.well
    if not (well and well.frame) then return end
    local mode = M.Mode()
    SeatTexture(well, mode)
    if not driver then
        driver = CreateFrame("Frame", nil, well.frame)
        driver.acc = 0
        driver:SetScript("OnHide", function(self) self.acc = 0 end)
    end
    if mode == "animated" and rec.on then
        if driver:GetScript("OnUpdate") ~= Tick then driver:SetScript("OnUpdate", Tick) end
    else
        driver:SetScript("OnUpdate", nil)
        driver.acc = 0
    end
end

local function SafeSeat()
    local ok, err = pcall(M.Seat)
    if not ok and FS.LogDegradeOnce then
        FS.LogDegradeOnce("charbackdrop:seat", "|cffff4488Forever STUwave|r: character background failed: " .. tostring(err))
    end
end

-- Character.lua calls this at the end of every well layout.
local prior = Char.OnWellLayout
Char.OnWellLayout = function(w)
    if prior then pcall(prior, w) end
    SafeSeat()
end
Config.OnChange(M.SETTING.key, SafeSeat)
SafeSeat()
