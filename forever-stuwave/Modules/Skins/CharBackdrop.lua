-- Forever STUwave: the character window backdrop
-- A looping pixel-art scene in the model well behind the character: the talent spec background (TalentBgArt.lua, the same
-- sheets the talent trees show) of the tree with the most points spent, ties to the leftmost tree. With no points spent, or a
-- class with no sheets, Aurora Night (tools/assets/charbg/scenes/c_aurora.js, baked by tools/assets/charbg/bake.mjs into one
-- flipbook sheet and the generated manifest CharBgArt.lua).
--
--   * Points per tree come from the trait system (C_ClassTalents.GetActiveConfigID -> C_Traits.GetConfigInfo -> GetTreeNodes ->
--     GetNodeInfo), which this client uses for all three trees in ONE trait tree. The trees are told apart by node column:
--     the distinct posX values are split at their two widest gaps. Read on login and on talent events, not per frame.
--   * One texture of ours on the well frame Character.lua builds (FS.CharacterSkin.state.well), between the well's ink fill
--     (BACKGROUND) and its ring (BORDER 1). The well sits a level under the model scene, so the model draws over it. It is
--     inset INSET physical px inside the plate, which clears the cut corners.
--   * Shown at a whole number scale (every scene pixel the same size on screen): the smallest integer scale that covers the
--     well, centred across, the overflow cropped with texcoords. Aurora's crop keeps the bottom, so the ground stays under the
--     feet; a talent scene is centred both ways, as on the talent page.
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
local STILL_FRAME = 0
-- Both families bake 24 frames at 8 fps in 6 columns; only the cell size differs.
local FRAMES, FPS, COLS, SHEET = Art.FRAMES, Art.FPS, Art.COLS, Art.SHEET
local STEP = 1 / FPS

-- One art record per family: its frame size, cell pitch, the top left texel of each cell as texcoords, and the crop anchor.
local function Family(a, bottom)
    local fam = { W = a.W, H = a.H, bottom = bottom, u = {}, v = {} }
    for f = 0, FRAMES - 1 do
        fam.u[f] = ((f % COLS) * a.CW + 1) / SHEET
        fam.v[f] = (math.floor(f / COLS) * a.CH + 1) / SHEET
    end
    return fam
end
local AURORA = Family(Art, true)
local TALENT = FS.TalentBgArt and FS.TalentBgArt.FRAMES == FRAMES and FS.TalentBgArt.COLS == COLS
    and FS.TalentBgArt.SHEET == SHEET and Family(FS.TalentBgArt, false) or nil

M.SETTING = {
    key = "character.backdrop", default = "animated", label = "Character background",
    tip = "A painted scene behind your character in the character window: the background of your talent tree with the most "
        .. "points, or a night sky before you spend any. Animated loops it, Still shows one frame, Off draws nothing and frees "
        .. "the art. Reduced motion shows it still.",
}
M.STYLES = { "animated", "still", "off" }
M.STYLE_TEXT = { animated = "Animated", still = "Still", off = "Off" }
Config.RegisterDefault(M.SETTING.key, M.SETTING.default)

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
    local fam = rec.fam
    local u, v = fam.u[f], fam.v[f]
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
    rec.file, rec.fam, rec.on, rec.w, rec.h = nil, nil, false, nil, nil
end

-- Points spent per tree, left to right, from the trait system; nil when it cannot be read. Pure reads, no secrets involved.
local function Call(fn, ...)
    if type(fn) ~= "function" then return nil end
    local ok, a = pcall(fn, ...)
    if ok then return a end
end

function M.TreePoints()
    local CT, T = _G.C_ClassTalents, _G.C_Traits
    if type(CT) ~= "table" or type(T) ~= "table" then return nil end
    local cfg = Call(CT.GetActiveConfigID)
    local info = type(cfg) == "number" and Call(T.GetConfigInfo, cfg)
    local trees = type(info) == "table" and info.treeIDs
    if type(trees) ~= "table" then return nil end
    local nodes = {}
    for _, treeId in ipairs(trees) do
        local ids = Call(T.GetTreeNodes, treeId)
        if type(ids) == "table" then
            for _, id in ipairs(ids) do
                local n = Call(T.GetNodeInfo, cfg, id)
                if type(n) == "table" and type(n.posX) == "number" then
                    local rank = n.activeRank or n.currentRank or n.ranksPurchased or 0
                    nodes[#nodes + 1] = { x = n.posX, rank = type(rank) == "number" and rank or 0 }
                end
            end
        end
    end
    -- distinct columns, then the two widest gaps between neighbours split them into three trees
    local xs, seen = {}, {}
    for _, n in ipairs(nodes) do
        if not seen[n.x] then seen[n.x] = true; xs[#xs + 1] = n.x end
    end
    if #xs < 3 then return nil end
    table.sort(xs)
    local gaps = {}
    for i = 1, #xs - 1 do gaps[i] = { d = xs[i + 1] - xs[i], at = xs[i] } end
    table.sort(gaps, function(a, b) if a.d ~= b.d then return a.d > b.d end return a.at < b.at end)
    local c1, c2 = math.min(gaps[1].at, gaps[2].at), math.max(gaps[1].at, gaps[2].at)
    local pts = { 0, 0, 0 }
    for _, n in ipairs(nodes) do
        local t = n.x <= c1 and 1 or (n.x <= c2 and 2 or 3)
        pts[t] = pts[t] + n.rank
    end
    return pts
end

-- The tree with the most points (ties to the leftmost), or nil with none spent.
local function TopTree()
    local pts = M.TreePoints()
    if not pts then return nil end
    local best, top = 0, nil
    for i = 1, 3 do
        if pts[i] > best then best, top = pts[i], i end
    end
    return top
end

-- The sheet and its family: the top tree's talent scene, else Aurora.
function M.Pick()
    local top = TALENT and TopTree()
    if top then
        local _, token = UnitClass("player")
        local sheets = type(token) == "string" and FS.TalentBgArt.sheets[token]
        local name = sheets and sheets[top]
        if type(name) == "string" then return name, TALENT end
    end
    return Art.sheet, AURORA
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
    local name, fam = M.Pick()
    if rec.file ~= name then
        local ok = pcall(rec.tex.SetTexture, rec.tex, MEDIA .. name .. ".tga", "CLAMP", "CLAMP", "NEAREST")
        if not ok then return Clear() end
        rec.file, rec.w, rec.h = name, nil, nil
    end
    rec.fam = fam
    if rec.w ~= iw or rec.h ~= ih then
        rec.w, rec.h = iw, ih
        local W, H = fam.W, fam.H
        local s = math.max(1, math.ceil(math.max(iw / W, ih / H)))
        local vw, vh = iw / s, ih / s
        local x0, y0 = (W - vw) / 2, fam.bottom and H - vh or (H - vh) / 2
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
-- A talent change can move the top tree. The texture is set only when the sheet changes.
local listener = CreateFrame("Frame")
for _, event in ipairs({ "PLAYER_ENTERING_WORLD", "TRAIT_CONFIG_UPDATED", "PLAYER_TALENT_UPDATE", "CHARACTER_POINTS_CHANGED" }) do
    pcall(listener.RegisterEvent, listener, event)
end
listener:SetScript("OnEvent", SafeSeat)
SafeSeat()
