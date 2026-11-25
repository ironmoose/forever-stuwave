-- Forever STUwave: the STAY RAD sample alert, a placeholder pop up in the Warrior Overpower alert's own 8 bit style.
--
-- WHAT IT IS. A pixel alert with the Overpower alert's frame, lettering and sequences (a rune circle that draws itself, a synthwave sun
-- that slams down in the class emblem's place, the STAY RAD title slashed in, a drain bar under it), for the classes that have no pop up
-- alert yet. It NEVER shows in play: nothing here reads the game, listens for an event or runs by itself. The config window shows it
-- as the sample of the Alert scale row (ConfigFlash.lua asks FS.PlaceholderAlert.Preview), so the scale can be tuned on a class that has
-- nothing else to look at.
--
-- THE PREVIEW (Preview.Show / Hide / Restyle / IsShown) plays like a fight, on the real clock, the way the Warrior alert's does: the
-- baked enter animation, then the held look while the drain bar empties over the whole 5 s window (amber for its last 1.5 s, as in
-- play), the baked exit when it runs dry, a PREVIEW_GAP of nothing, again. Out of combat only (Show refuses in a fight and a tick in a
-- fight takes it down), and the loop stops the moment it is hidden. The window is Overpower's, so its art is not looped: the held and
-- amber sequences stay on their last frame until the next one starts.
--
-- THE ART IS BAKED, NOT DRAWN. tools/assets/generate_placeholder_alert.py ports the Overpower alert's code (generate_warrior_powerups.py)
-- and plays every 30 Hz frame into a display list of sprites (PlaceholderAlertArt.lua, placeholder_alert_N.tga). This file only replays
-- those lists, the way WarriorPowerUps.lua does: a sequence's first frame is a snapshot and the rest are deltas, slot n lives on child
-- frame ceil(n / 64) at draw layer and sublevel (n - 1) % 64 so the whole stack keeps the baked back to front order, and the drain bar's
-- fill is three baked one texel slots that this file stretches to the width the remaining time gives.
--
-- FRAME. A plain frame on UIParent (never a secure one) built on the first Show and never before, so a class that never opens the
-- preview pays nothing. It takes the Warrior alert's seat, `warriorpowerup`, placed WITH a parent (FS.Layout.Apply's third argument),
-- which follows that seat's moves and rescales but is never listed by /fsedit or the hover outline as a second piece. The Alert scale
-- (FS.GunsightAreas.AlertScale) grows the art about the middle of its canvas, as it does the Warrior and Druid alerts.
-- UNVERIFIED in game: the NEAREST filter on the atlas and the position over the character.

local _, FS = ...

local PA = {}
FS.PlaceholderAlert = PA

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FRAME_S = 1 / 30          -- the baked frames' clock
local MAX_DT = 0.1              -- a hitch never fast forwards the animation
local PREVIEW_GAP = 0.6         -- s of nothing between two plays
local LAYERS = { "BACKGROUND", "BORDER", "ARTWORK", "OVERLAY" }
local PER_FRAME = 64            -- textures per child frame: 4 layers x 16 sublevels
local SPELL = "stayrad"

PA.LAYOUT_ID = "warriorpowerup"  -- the Warrior alert's seat

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "placeholderalert_" .. key, "|cffff4488Forever STUwave|r: sample alert: " .. tostring(msg))
    end
end

-------------------------------------------------------------------------------
-- State. Everything the tick touches is a number or an existing table: nothing allocates per tick.
-------------------------------------------------------------------------------

local Art, SP
local maxSlots = 0
local built = false
local root
local children = {}               -- child frames, back to front
local tex = {}                    -- slot -> texture
local want, wantX, wantY = {}, {}, {}           -- what the list says: sprite id (0 hides), x, y in sprite px
local shSprite, shX, shY, shW, shAtlas = {}, {}, {}, {}, {}  -- what the texture shows now (sprite 0 = hidden)
local slotParent = {}             -- slot -> its child frame
local ATLAS_PATH = {}
local UL, UR, UT, UB, SW, SH, SA = {}, {}, {}, {}, {}, {}, {}   -- per sprite: texcoords, size in sprite px, atlas
local unit = 1                    -- UI units per sprite px (the layout scale and the alert scale folded in)
local offX, offY = 0, 0           -- UI units the alert scale moves every texture so the art grows about its canvas middle

local curSeq, curFrames, curIdx, curAcc, curRem
local previewing = false
local loop = { phase = nil, t = 0 }
local loopFrame
local rescaleHooked = false

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

-- The canvas is the frame's own size (GW x GH sprite px), so the art scales about its middle and keeps its seat: at 1 both
-- offsets are 0 and every position and size is what the lists say.
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

-- Writes what the lists say onto the textures; only what changed is touched.
local function Commit()
    local fa, fz = SP.fill[1], SP.fill[3]
    for s = 1, maxSlots do
        local sp = want[s]
        local fw
        if sp ~= 0 and s >= fa and s <= fz then
            local frac = curRem / SP.win
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
    if previewing then Commit() end
end

local function Build()
    if built then return true end
    Art = Art or FS.PlaceholderAlertArt
    if not (Art and Art.SPELL and Art.SPRITE and Art.ATLAS and Art.SPELL[SPELL]) then return false end
    SP = Art.SPELL[SPELL]
    local ok, err = pcall(function()
        maxSlots = SP.slots
        root = CreateFrame("Frame", "ForeverSTUwavePlaceholderAlert", UIParent)
        root:SetFrameStrata("MEDIUM")
        root:SetFrameLevel(20)
        root:EnableMouse(false)
        if FS.Layout and FS.Layout.Apply then FS.Layout.Apply(root, PA.LAYOUT_ID, UIParent) end
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
    if FS.Layout and FS.Layout.OnRescale and not rescaleHooked then
        rescaleHooked = true
        FS.Layout.OnRescale(Reseat)
    end
    return true
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
    curSeq, curFrames = nil, nil
    for s = 1, maxSlots do want[s] = 0 end
    if built then
        Commit()
        root:Hide()
    end
end

local function StartSeq(seq, idx, rem)
    curSeq = seq
    curFrames = SP.seqs[seq]
    curIdx, curAcc, curRem = idx, 0, rem
    Reach(curFrames, idx)
    root:Show()
    Commit()
end

-- One baked frame forward: the next delta, or the end of the sequence (enter -> held or amber, an exit finishes). The held and
-- amber lists are not loops: at their end the last frame stays until the clock starts the next sequence.
local function Step()
    if curIdx < #curFrames then
        curIdx = curIdx + 1
        ApplyList(curFrames[curIdx])
        return
    end
    if curSeq == "exp" then
        Stop()
    elseif curSeq == "enter" then
        StartSeq(curRem <= Art.AMBER and "amber" or "held", 1, curRem)
    end
end

-------------------------------------------------------------------------------
-- The preview loop
-------------------------------------------------------------------------------

local function LoopBegin()
    loop.phase, loop.t = "enter", 0
    StartSeq("enter", 1, SP.win)
end

local function InCombat()
    return type(InCombatLockdown) == "function" and InCombatLockdown() == true
end

local function LoopTick(_, dt)
    if not (previewing and built and loop.phase) then
        loopFrame:SetScript("OnUpdate", nil)
        loop.phase = nil
        return
    end
    if InCombat() then
        PA.Preview.Hide()
        return
    end
    if dt > MAX_DT then dt = MAX_DT end
    if loop.phase == "gap" then
        loop.t = loop.t + dt
        if loop.t >= PREVIEW_GAP then LoopBegin() end
        return
    end
    if loop.phase ~= "exit" and curRem then
        curRem = curRem - dt
        if curRem <= 0 then
            curRem = 0
            loop.phase = "exit"
            StartSeq("exp", 1, 0)
        elseif curSeq == "held" and curRem <= Art.AMBER then
            StartSeq("amber", 1, curRem)
        end
    end
    curAcc = curAcc + dt
    while curAcc >= FRAME_S and curSeq do
        curAcc = curAcc - FRAME_S
        Step()
    end
    if curSeq then Commit() end
    if loop.phase == "exit" and not curSeq then
        loop.phase, loop.t = "gap", 0
    elseif loop.phase == "enter" and curSeq ~= "enter" then
        loop.phase = "hold"
    end
end

local function LoopStop()
    loop.phase = nil
    if loopFrame then loopFrame:SetScript("OnUpdate", nil) end
end

-------------------------------------------------------------------------------
-- The config window's preview (ConfigFlash.lua)
-------------------------------------------------------------------------------

-- Show answers true when this call put it up (false: it is already up, it is a fight, or the art cannot be built).
PA.Preview = {}
function PA.Preview.IsShown() return previewing end
function PA.Preview.Show()
    if previewing or InCombat() then return false end
    if not Build() then return false end
    Stop()
    previewing = true
    loopFrame = loopFrame or CreateFrame("Frame")
    LoopBegin()
    loopFrame:SetScript("OnUpdate", LoopTick)
    return true
end
function PA.Preview.Hide()
    LoopStop()
    if previewing then
        previewing = false
        Stop()
    end
end
function PA.Preview.Restyle()
    if previewing and built then pcall(Reseat) end
end
function PA.Preview.Phase() return loop.phase end
function PA.Preview.Driver() return loopFrame end

-- for the harness
PA._root = function() return root end
PA._state = function() return curSeq, curIdx, previewing end
