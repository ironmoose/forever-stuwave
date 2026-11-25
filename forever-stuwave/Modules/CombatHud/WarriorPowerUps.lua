-- Forever STUwave: the Warrior power-up alerts (design mockup "Gunsight Warrior: proc alerts v2", 2026-11-17).
--
-- WHAT IT IS. When a reactive Warrior spell lights up (Overpower after a dodge, Revenge after a block or parry, Victory Rush after
-- a kill) a big pixel alert plays above the character, between the rails, with a drain bar under its title:
--   * OVERPOWER: a bearded double axe chops into a rotating rune circle (16 Elder Futhark runes), the rune cut title slides together.
--   * REVENGE: a cackling Viking skull on a round shield, its jaw drops on each cackle, little round shields flank the title.
--   * VICTORY RUSH: crossed flaming bearded axes on a red sunburst, a clang, a green heal, the title bumps on each clang.
-- The drain bar runs the window's length (the real remaining time) and turns amber for the last 1.5 s. A cast of the spell plays the
-- cast exit (0.6 s), a window that runs out unused plays the expiry exit (0.7 s). Only one alert shows at a time: the shown window
-- with the least time left. No knotwork under the titles.
--
-- THE ART IS BAKED, NOT DRAWN. tools/assets/generate_warrior_powerups.py ports the mockup's canvas code and plays every 30 Hz frame
-- into a display list of sprites (WarriorPowerUpArt.lua, warrior_powerups_N.tga). This file only replays those lists: a spell has
-- the sequences enter, held (the idle loop), amber (the loop in amber), cast and exp; a sequence's first frame is a snapshot and
-- the rest are deltas, so a tick touches only the slots that changed. Slots are back to front; slot n lives on child frame
-- ceil(n / 64) at draw layer and sublevel (n - 1) % 64, so the whole stack keeps the baked order. The drain bar's fill is three
-- baked one texel slots (the spell's `fill`) that this file stretches to the width the remaining time gives. Overpower is exact;
-- Revenge (1.8 s) and Victory Rush (2.4 s) loop seamlessly, their periods retuned to whole loops (see the generator's RETUNE note).
--
-- DATA. FS.WarriorWindows (WarriorWindows.lua): Subscribe, Get, Remaining, Shown, Tick, ORDER. Nothing is detected here. A window
-- that is open but held back (Victory Rush above 90 percent health) is not shown, so no alert; this file then polls Windows.Tick
-- every POLL s until it is shown or closes. `Gunsight.IsActive()` false hides every alert. A Warrior only: other classes build
-- nothing, so the layout editor shows no handle for them.
--
-- FRAME. A plain frame on UIParent (never a secure one, so Show and Hide are legal in combat), seated by FS.Layout as
-- `warriorpowerup` (movable in /fsedit, which shows the Overpower held frame as a static preview). One OnUpdate on a driver frame,
-- only while an alert plays (30 Hz) or a held back window waits (POLL); nothing allocates per tick.
-- UNVERIFIED in game: the NEAREST filter, the layering of 174 textures, the position over the character, every window event.

local _, FS = ...

local PU = {}
FS.WarriorPowerUps = PU

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FRAME_S = 1 / 30          -- the baked frames' clock
local MAX_DT = 0.1              -- a hitch never fast forwards the animation
local POLL = 0.2                -- s between checks while a window waits behind the health gate
local EXIT_GRACE = 1.0          -- a cast or an expiry plays its exit when the alert was up this recently
local PREVIEW_FRAME = 34        -- the layout editor's static frame: Overpower held at 1.6 s, as the mockup's strip shows it
local PREVIEW_REM = 0.7         -- ... with the drain bar at 70 percent
local LAYERS = { "BACKGROUND", "BORDER", "ARTWORK", "OVERLAY" }
local PER_FRAME = 64            -- textures per child frame: 4 layers x 16 sublevels

PU.SETTING = {
    key = "gunsight.warrior.powerups", default = true, label = "Power-up alerts",
    tip = "A big alert above your character when Overpower, Revenge or Victory Rush lights up, with a bar that drains over the "
        .. "window. A cast and a window that runs out each play a short exit. Move it with /fsedit.",
}
PU.SPELLS = {
    overpower = { key = "gunsight.warrior.powerup.overpower", default = true, label = "Overpower" },
    revenge = { key = "gunsight.warrior.powerup.revenge", default = true, label = "Revenge" },
    victoryrush = { key = "gunsight.warrior.powerup.victoryrush", default = true, label = "Victory Rush" },
}
PU.ORDER = { "overpower", "revenge", "victoryrush" }
PU.LAYOUT_ID = "warriorpowerup"

if FS.Config and FS.Config.RegisterDefault then
    FS.Config.RegisterDefault(PU.SETTING.key, PU.SETTING.default)
    for _, key in ipairs(PU.ORDER) do FS.Config.RegisterDefault(PU.SPELLS[key].key, PU.SPELLS[key].default) end
end

local IsSecret = FS.IsSecret or function() return false end

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "warriorpowerups_" .. key, "|cffff4488Forever STUwave|r: warrior power-up alerts: " .. tostring(msg))
    end
end

-------------------------------------------------------------------------------
-- State. Everything the tick touches is a number or an existing table: nothing allocates per tick.
-------------------------------------------------------------------------------

local Art, Windows
local ART_SPELLS                  -- Art.SPELL
local maxSlots = 0
local built = false
local root, driver
local children = {}               -- child frames, back to front
local tex = {}                    -- slot -> texture
local want, wantX, wantY = {}, {}, {}           -- what the list says: sprite id (0 hides), x, y in sprite px
local shSprite, shX, shY, shW, shAtlas = {}, {}, {}, {}, {}  -- what the texture shows now (sprite 0 = hidden)
local slotParent = {}             -- slot -> its child frame
local ATLAS_PATH = {}
local UL, UR, UT, UB, SW, SH, SA = {}, {}, {}, {}, {}, {}, {}   -- per sprite: texcoords, size in sprite px, atlas
local unit = 1                    -- UI units per sprite px (the layout scale and the alert scale folded in)
local offX, offY = 0, 0           -- UI units the alert scale moves every texture so the art grows about its canvas middle

local cfgMaster = true
local cfgSpell = { overpower = true, revenge = true, victoryrush = true }

local curKey, curSpell, curSeq, curFrames, curIdx, curAcc, curRem
local lastShown = { overpower = -100, revenge = -100, victoryrush = -100 }   -- GetTime() of the last live paint
local lastRem = { overpower = 0, revenge = 0, victoryrush = 0 }
local waitAcc = 0
local driving = false
local previewing = false
local inited = false
local subscribed = false
local sync                         -- forward

-------------------------------------------------------------------------------
-- Class, switches
-------------------------------------------------------------------------------

function PU.Applies()
    if type(UnitClass) ~= "function" then return false end
    local ok, _, token = pcall(UnitClass, "player")
    return ok and not IsSecret(token) and token == "WARRIOR"
end

local function ReadConfig()
    local C = FS.Config
    if not (C and C.Get) then return end
    local v = C.Get(PU.SETTING.key)
    cfgMaster = v ~= false
    for _, key in ipairs(PU.ORDER) do
        v = C.Get(PU.SPELLS[key].key)
        cfgSpell[key] = v ~= false
    end
end

local function GunsightUp()
    local G = FS.Gunsight
    return type(G) == "table" and type(G.IsActive) == "function" and G.IsActive() == true
end

local function Enabled(key)
    return cfgMaster and cfgSpell[key] == true and GunsightUp()
end

-------------------------------------------------------------------------------
-- The frame
-------------------------------------------------------------------------------

local function SetTex(t, path)
    local ok = pcall(t.SetTexture, t, path, "CLAMP", "CLAMP", "NEAREST")
    if not ok then t:SetTexture(path) end
end

-- The Class modules page's Alert scale (Areas.AlertScale, 0.5 to 2): anything that is not a finite number above 0 reads as 1,
-- and so does a client where the Gunsight areas are absent.
local function AlertScale()
    local A = FS.GunsightAreas
    local v = A and A.AlertScale and A.AlertScale()
    if type(v) == "number" and v > 0 and v - v == 0 then return v end
    return 1
end

-- The canvas is the frame's own size (GW x GH sprite px), so the art scales about its middle and the alert keeps its seat: at 1
-- both offsets are 0 and every position and size is what it was.
local function Rescale()
    local base = Art.SPX * ((FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1)
    local scale = AlertScale()
    unit = base * scale
    offX, offY = Art.GW * base * (1 - scale) / 2, Art.GH * base * (1 - scale) / 2
    for slot = 1, maxSlots do shX[slot], shY[slot], shW[slot] = nil, nil, nil end
end

local function BuildTextures()
    for a = 1, #Art.ATLAS do ATLAS_PATH[a] = MEDIA .. Art.ATLAS[a].file .. ".tga" end
    for id = 1, #Art.SPRITE do
        local sp = Art.SPRITE[id]
        local atlas = Art.ATLAS[sp[1]]
        SA[id], SW[id], SH[id] = sp[1], sp[4], sp[5]
        UL[id], UR[id] = sp[2] / atlas.w, (sp[2] + sp[4]) / atlas.w
        UT[id], UB[id] = sp[3] / atlas.h, (sp[3] + sp[5]) / atlas.h
    end
    local frames = math.floor((maxSlots + PER_FRAME - 1) / PER_FRAME)
    local base = root:GetFrameLevel()
    for c = 1, frames do
        local f = CreateFrame("Frame", nil, root)
        f:SetAllPoints(root)
        f:SetFrameLevel(base + c)
        f:EnableMouse(false)
        children[c] = f
    end
    for s = 1, maxSlots do
        local z = s - 1
        local c = math.floor(z / PER_FRAME) + 1
        local w = z % PER_FRAME
        local t = children[c]:CreateTexture(nil, LAYERS[math.floor(w / 16) + 1], nil, w % 16 - 8)
        t:Hide()
        tex[s], slotParent[s] = t, children[c]
        want[s], wantX[s], wantY[s] = 0, 0, 0
        shSprite[s], shAtlas[s] = 0, 0
    end
end

local function Build()
    if built then return true end
    if not (Art and Art.SPELL and Art.SPRITE and Art.ATLAS) then return false end
    local ok, err = pcall(function()
        for _, spell in pairs(Art.SPELL) do
            if spell.slots > maxSlots then maxSlots = spell.slots end
        end
        root = CreateFrame("Frame", "ForeverSTUwaveWarriorPowerUps", UIParent)
        root:SetFrameStrata("MEDIUM")
        root:SetFrameLevel(20)
        root:EnableMouse(false)
        if FS.Layout and FS.Layout.Apply then FS.Layout.Apply(root, PU.LAYOUT_ID) end
        root:Hide()
        BuildTextures()
        Rescale()
        built = true
    end)
    if not ok then
        LogOnce("build", err)
        if root then root:Hide() end
        return false
    end
    return true
end

-- Writes what the lists say onto the textures; only what changed is touched.
local function Commit()
    local fa, fz = 0, -1
    if curSpell then fa, fz = curSpell.fill[1], curSpell.fill[3] end
    for s = 1, maxSlots do
        local sp = want[s]
        local fw
        if sp ~= 0 and s >= fa and s <= fz then
            local win = curSpell.win
            local frac = curRem / win
            if frac > 1 then frac = 1 elseif frac < 0 then frac = 0 end
            fw = math.floor(frac * Art.BAR_FILL + 0.5)
            if fw <= 0 then sp = 0 end
        end
        local t = tex[s]
        if sp == 0 then
            if shSprite[s] ~= 0 then
                t:Hide()
                shSprite[s] = 0
            end
        else
            local w = fw or SW[sp]
            local fresh = shSprite[s] == 0
            if shSprite[s] ~= sp then
                if shAtlas[s] ~= SA[sp] then
                    SetTex(t, ATLAS_PATH[SA[sp]])
                    shAtlas[s] = SA[sp]
                end
                t:SetTexCoord(UL[sp], UR[sp], UT[sp], UB[sp])
                shSprite[s] = sp
                shW[s] = nil
            end
            if shW[s] ~= w then
                t:SetSize(w * unit, SH[sp] * unit)
                shW[s] = w
            end
            if fresh or shX[s] ~= wantX[s] or shY[s] ~= wantY[s] then
                t:ClearAllPoints()
                t:SetPoint("TOPLEFT", slotParent[s], "TOPLEFT", wantX[s] * unit + offX, -wantY[s] * unit - offY)
                shX[s], shY[s] = wantX[s], wantY[s]
            end
            if fresh then t:Show() end
        end
    end
end

-- A new layout scale or alert scale: seat the textures again, and repaint the alert that is showing
local function Reseat()
    if not built then return end
    Rescale()
    if curKey or previewing then Commit() end
end

-------------------------------------------------------------------------------
-- Replaying the lists
-------------------------------------------------------------------------------

local function ApplyList(list)
    for k = 1, #list, 4 do
        local s = list[k]
        want[s], wantX[s], wantY[s] = list[k + 1], list[k + 2], list[k + 3]
    end
end

local function Snapshot(list)
    for s = 1, maxSlots do want[s] = 0 end
    ApplyList(list)
end

-- The state of frame n of a sequence: its snapshot, then the deltas up to n.
local function Reach(frames, n)
    Snapshot(frames[1])
    for i = 2, n do ApplyList(frames[i]) end
end

local function Stop()
    curKey, curSeq, curFrames = nil, nil, nil
    for s = 1, maxSlots do want[s] = 0 end
    if built then
        Commit()
        root:Hide()
    end
    curSpell = nil
end

local function StartSeq(key, seq, idx, rem)
    curKey, curSpell, curSeq = key, ART_SPELLS[key], seq
    curFrames = curSpell.seqs[seq]
    curIdx, curAcc, curRem = idx, 0, rem
    Reach(curFrames, idx)
    root:Show()
    Commit()
end

local function Finish()
    Stop()
    sync(GetTime())
end

-- One baked frame forward: the next delta, or the end of the sequence (enter -> held, a loop wraps, an exit finishes).
local function Step()
    if curIdx < #curFrames then
        curIdx = curIdx + 1
        ApplyList(curFrames[curIdx])
        return
    end
    local seq = curSeq
    if seq == "cast" or seq == "exp" then
        Finish()
    elseif seq == "enter" then
        StartSeq(curKey, curRem <= Art.AMBER and "amber" or "held", 1, curRem)
    else
        curIdx = 1
        Snapshot(curFrames[1])
    end
end

local function PlayExit(kind, key, now)
    if not (built and not previewing and Enabled(key) and ART_SPELLS[key]) then return end
    if curKey ~= key and now - lastShown[key] > EXIT_GRACE then return end
    StartSeq(key, kind, 1, lastRem[key])
    sync(now)
end

-------------------------------------------------------------------------------
-- Which alert, and the driver
-------------------------------------------------------------------------------

-- The enabled, shown window with the least time left; second result: some enabled window is open but held back.
local function Desired(now)
    local best, bestLeft, held
    local order = Windows.ORDER
    for i = 1, #order do
        local key = order[i]
        if cfgMaster and cfgSpell[key] and ART_SPELLS[key] then
            if Windows.Shown(key, now) then
                local left = Windows.Remaining(key, now)
                if left and (not bestLeft or left < bestLeft) then best, bestLeft = key, left end
            else
                local st = Windows.Get(key)
                if st and st.known and st.open then held = true end
            end
        end
    end
    return best, held
end

local function Tick(_, elapsed)
    if elapsed > MAX_DT then elapsed = MAX_DT end
    local now = GetTime()
    if Windows.Tick then Windows.Tick(now) end
    if not curKey then
        waitAcc = waitAcc + elapsed
        if waitAcc >= POLL then
            waitAcc = 0
            sync(now)
        end
        return
    end
    local seq = curSeq
    if seq == "cast" or seq == "exp" then
        curAcc = curAcc + elapsed
        while curAcc >= FRAME_S and curKey do
            curAcc = curAcc - FRAME_S
            Step()
        end
        if curKey then Commit() end
        return
    end
    sync(now)
    if not curKey or curSeq == "cast" or curSeq == "exp" then return end
    curAcc = curAcc + elapsed
    while curAcc >= FRAME_S and curKey do
        curAcc = curAcc - FRAME_S
        Step()
    end
    if curKey then Commit() end
end

local function UpdateDriver(waiting)
    local want = curKey ~= nil or waiting == true
    if want == driving then return end
    driving = want
    driver:SetScript("OnUpdate", want and Tick or nil)
    waitAcc = 0
end

-- Decide what shows now: start, switch or stop the live alert. An exit in progress plays out first.
sync = function(now)
    if not (built and driver) or previewing then return end
    local seq = curSeq
    if seq == "cast" or seq == "exp" then
        UpdateDriver(false)
        return
    end
    local key, held
    if GunsightUp() then key, held = Desired(now) end
    if not key then
        if curKey then Stop() end
        UpdateDriver(held)
        return
    end
    local rem = Windows.Remaining(key, now)
    if key ~= curKey then
        lastShown[key], lastRem[key] = now, rem or 0
        StartSeq(key, "enter", 1, rem or 0)
        UpdateDriver(false)
        return
    end
    lastShown[key] = now
    if rem then
        curRem, lastRem[key] = rem, rem
    end
    if curSeq == "held" and curRem <= Art.AMBER then
        local idx = curSpell.amberStart == curSpell.heldStart and curIdx or 1
        StartSeq(key, "amber", idx, curRem)
    end
    UpdateDriver(false)
end

-------------------------------------------------------------------------------
-- Window events
-------------------------------------------------------------------------------

local function OnWindowChange(key, reason)
    if not built then return end
    local now = GetTime()
    if reason == "cast" or reason == "expire" then
        local st = Windows.Get(key)
        if st and st.shownAtClose then PlayExit(reason == "cast" and "cast" or "exp", key, now) end
        sync(now)
        return
    end
    if reason == "change" and curKey == key and (curSeq == "enter" or curSeq == "held" or curSeq == "amber") then
        local rem = Windows.Remaining(key, now) or 0
        lastShown[key], lastRem[key] = now, rem
        StartSeq(key, "enter", 1, rem)
        return
    end
    sync(now)
end

-------------------------------------------------------------------------------
-- The layout editor's preview
-------------------------------------------------------------------------------

local function ShowPreview()
    if not Build() then return end
    Stop()
    previewing = true
    curKey, curSpell, curSeq = "overpower", ART_SPELLS.overpower, "held"
    curFrames = curSpell.seqs.held
    curRem = curSpell.win * PREVIEW_REM
    Reach(curFrames, PREVIEW_FRAME)
    root:Show()
    Commit()
    curKey = nil
    UpdateDriver(false)
end

local function EndPreview()
    if not previewing then return end
    previewing = false
    Stop()
    sync(GetTime())
end

local function OnEditChanged(editing)
    if not built then return end
    if editing then ShowPreview() else EndPreview() end
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

function PU.Init()
    if inited then return true end
    if not PU.Applies() then return false end
    Art, Windows = FS.WarriorPowerUpArt, FS.WarriorWindows
    if not (Art and Windows and Windows.Get and Windows.Shown and Windows.Remaining and Windows.Subscribe and Windows.ORDER) then
        LogOnce("deps", "FS.WarriorWindows or the baked art is missing, the alerts are off")
        return false
    end
    ART_SPELLS = Art.SPELL
    if not Build() then return false end
    inited = true
    ReadConfig()
    driver = CreateFrame("Frame")
    if FS.Layout and FS.Layout.OnRescale then FS.Layout.OnRescale(Reseat) end
    if FS.Config and FS.Config.OnChange then
        local function Changed() ReadConfig(); sync(GetTime()) end
        FS.Config.OnChange(PU.SETTING.key, Changed)
        for _, key in ipairs(PU.ORDER) do FS.Config.OnChange(PU.SPELLS[key].key, Changed) end
        if FS.GunsightAreas and FS.GunsightAreas.ALERT_SCALE_KEY then FS.Config.OnChange(FS.GunsightAreas.ALERT_SCALE_KEY, Reseat) end
    end
    if FS.Gunsight and FS.Gunsight.OnActiveChanged then
        FS.Gunsight.OnActiveChanged(function() sync(GetTime()) end)
    end
    if FS.Gunsight and FS.Gunsight.OnReady then
        FS.Gunsight.OnReady(function() sync(GetTime()) end)
    end
    if FS.LayoutEdit and FS.LayoutEdit.OnEditChanged then
        FS.LayoutEdit.OnEditChanged(OnEditChanged)
        if FS.LayoutEdit.IsEditing and FS.LayoutEdit.IsEditing() then ShowPreview() end
    end
    if Windows.Start then Windows.Start() end
    if not subscribed then
        subscribed = true
        Windows.Subscribe(OnWindowChange)
    end
    sync(GetTime())
    return true
end

local boot = CreateFrame("Frame")
boot:RegisterEvent("PLAYER_LOGIN")
boot:SetScript("OnEvent", function(self)
    self:UnregisterAllEvents()
    local ok, err = pcall(PU.Init)
    if not ok then LogOnce("init", err) end
end)

-- for the harness
PU._Tick = Tick
PU._driver = function() return driver end
PU._root = function() return root end
PU._sync = function(now) return sync(now) end
PU._state = function() return curKey, curSeq, curIdx, previewing end
