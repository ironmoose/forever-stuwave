-- Forever STUwave: the Druid Clearcasting alert (design mockup "Druid Clearcasting alert", 2026-11-17).
--
-- WHAT IT IS. When Omen of Clarity procs (Clearcasting, spell 16870: 15 s, the next damage or healing spell or offensive ability
-- costs nothing; Wrath does not spend it) a big pixel alert plays above the character, in the Warrior power-up alerts' seat and
-- flow: a seer's orb in an antler root cradle with the omen of the current form inside it (Bear: the roaring bear, FREE MAUL;
-- Cat: the roaring lion, FREE SHRED; caster and the other forms: the waxing moon and a star, FREE SPELL), the CLEARCASTING title
-- and a drain bar under it, amber for the last 3 s. Spending it plays the cast exit (the beast bursts out of the glass, the orb
-- shatters, a green ring; 0.6 s), letting it run out plays the expiry exit (the omen sinks into the mist and greys out; 0.7 s).
-- A form change while it is up plays the new form's entrance with the time that is left.
--
-- THE ART IS BAKED, NOT DRAWN. tools/assets/generate_druid_clearcasting.py ports the mockup's drawCC and plays every 30 Hz frame
-- into display lists (DruidClearcastingArt.lua, druid_clearcasting_N.tga); this file replays them exactly as WarriorPowerUps.lua
-- does (snapshot then deltas, slot n on child frame ceil(n / 64) at layer and sublevel (n - 1) % 64, the drain fill three
-- stretched 1 texel slots). The held loop is 6.8 s (two roars), retuned to whole periods by the generator.
--
-- DATA (this file; nothing here compares a secret):
--   * Out of combat, while FS.AurasReadable(): the player's aura (by spell id 16870, else by the name "Clearcasting") is the
--     truth, with its plain expiration time.
--   * In combat the aura is not readable, so the signal is the cost of a probe spell of the current form (Maul, Swipe; Shred,
--     Claw, Rake; Moonfire, Healing Touch, Rejuvenation, Starfire): a plain C_Spell.GetSpellPowerCost that reads 0 for a spell
--     whose plain cost out of combat was above 0 means the omen is up, a plain cost above 0 that it is not. The 15 s then run
--     from the moment the 0 was first seen (an estimate). A secret or missing cost says nothing and the state stands (it still
--     runs out by its clock). UNPROVEN LIVE: that the cost reads 0 under Clearcasting on this client.
--   * Closing: an own cast (UNIT_SPELLCAST_SUCCEEDED, not Wrath) within CAST_WINDOW before the omen goes means it was spent
--     (cast exit); an omen gone at the end of its time ran out (expiry exit); one gone early with no cast seen was spent too.
--   * The form is FS.DruidState.Form() (cat, bear, else the moon).
--   * Not learned = not drawn: with Omen of Clarity readably not known nothing is read, polled or drawn.
-- Reads happen on UNIT_AURA, the own casts, form, combat and spell events, and every POLL s in combat (a proc from a melee swing
-- raises no event of ours in combat besides UNIT_AURA, whose payload is not read).
--
-- FRAME. A plain frame on UIParent (`ForeverSTUwaveDruidClearcasting`, MEDIUM), seated by FS.Layout as `druidclearcasting`
-- (the Warrior alerts' seat), movable in /fsedit (a static bear held frame while the editor is on). `Gunsight.IsActive()` false
-- hides it. A Druid only: other classes build nothing. One OnUpdate on a driver frame, only while an alert plays (30 Hz) or in
-- combat with the omen known (POLL); nothing allocates per tick in this file.
-- UNVERIFIED in game: the cost signal, the aura id, the NEAREST filter on the 8 MB atlas, the layering of 83 textures, the seat.

local _, FS = ...

local CC = {}
FS.DruidClearcasting = CC

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local FRAME_S = 1 / 30
local MAX_DT = 0.1
local POLL = 0.2
local CAST_WINDOW = 0.6          -- s between an own cast and the omen going that count as "spent"
local END_SLACK = 0.6            -- an omen gone this close to its end ran out
local PREVIEW_FRAME = 60
local PREVIEW_REM = 0.7
local LAYERS = { "BACKGROUND", "BORDER", "ARTWORK", "OVERLAY" }
local PER_FRAME = 64

CC.SPELL_ID = 16870
CC.AURA_NAME = "Clearcasting"
CC.TALENT = "Omen of Clarity"
CC.SECONDS = 15
CC.TELLS = {
    bear = { "Maul", "Swipe" },
    cat = { "Shred", "Claw", "Rake" },
    moon = { "Moonfire", "Healing Touch", "Rejuvenation", "Starfire" },
}
CC.NOT_SPENT = { ["wrath"] = true }      -- casts that leave the omen up (Forever spell data: Wrath does not consume it)
CC.SETTING = {
    key = "gunsight.druid.clearcasting", default = true, label = "Clearcasting alert",
    tip = "A big alert above your character when Clearcasting procs: your next spell or ability is free. It shows the "
        .. "omen of your form (bear, lion, moon) and a bar that drains as it runs out. Move it with /fsedit.",
}
CC.LAYOUT_ID = "druidclearcasting"

if FS.Config and FS.Config.RegisterDefault then FS.Config.RegisterDefault(CC.SETTING.key, CC.SETTING.default) end

local IsSecret = FS.IsSecret or function() return false end

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "druidclearcasting_" .. key, "|cffff4488Forever STUwave|r: clearcasting alert: " .. tostring(msg))
    end
end

local function PlainOf(v, kind)
    if IsSecret(v) then return nil end
    if type(v) == kind then return v end
    return nil
end

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local Art, KINDS
local maxSlots = 0
local built = false
local root, driver, events
local children = {}
local tex = {}
local want, wantX, wantY = {}, {}, {}
local shSprite, shX, shY, shW, shAtlas = {}, {}, {}, {}, {}
local slotParent = {}
local ATLAS_PATH = {}
local UL, UR, UT, UB, SW, SH, SA = {}, {}, {}, {}, {}, {}, {}
local unit = 1                 -- UI units per sprite px (the layout scale and the alert scale folded in)
local offX, offY = 0, 0        -- UI units the alert scale moves every texture so the art grows about its canvas middle

local cfgOn = true
local curKind, curSpell, curSeq, curFrames, curIdx, curAcc, curRem
local waitAcc, readAcc = 0, 0
local driving = false
local previewing = false
local inited = false
local sync, Update                 -- forward

-- the omen: open, its end (GetTime() base), est (a guess from the cost), the kind it opened as
local omen = { open = false, expires = 0, est = false }
local castAt = -100
local learned = nil                -- Omen of Clarity: true, false, or nil when unreadable
local inCombat = false
local tellBase = {}               -- tell name -> its last plain cost above 0

-------------------------------------------------------------------------------
-- Class, switches
-------------------------------------------------------------------------------

function CC.Applies()
    if type(UnitClass) ~= "function" then return false end
    local ok, _, token = pcall(UnitClass, "player")
    return ok and not IsSecret(token) and token == "DRUID"
end

local function ReadConfig()
    local C = FS.Config
    if not (C and C.Get) then return end
    cfgOn = C.Get(CC.SETTING.key) ~= false
end

local function GunsightUp()
    local G = FS.Gunsight
    return type(G) == "table" and type(G.IsActive) == "function" and G.IsActive() == true
end

local function Kind()
    local DS = FS.DruidState
    local f = DS and DS.Form and DS.Form()
    if f == "cat" then return "cat" end
    if f == "bear" then return "bear" end
    return "moon"
end

local function Known(name)
    local FH = FS.FrameHelpers
    if not (FH and FH.ResolveSpell and FH.IsKnownSpellId) then return nil end
    local ok, id = pcall(FH.ResolveSpell, name)
    if not ok then return nil end
    if not id then return false end
    local ok2, k = pcall(FH.IsKnownSpellId, id, false)
    if not ok2 then return nil end
    return k and true or false
end

-------------------------------------------------------------------------------
-- Reading the omen
-------------------------------------------------------------------------------

local function Readable() return FS.AurasReadable and FS.AurasReadable() or false end

-- true, expires | false | nil (unreadable)
local function ReadAura()
    if not Readable() or not C_UnitAuras then return nil end
    local aura
    local byId = C_UnitAuras.GetPlayerAuraBySpellID
    if type(byId) == "function" then
        local ok, a = pcall(byId, CC.SPELL_ID)
        if ok and not IsSecret(a) and type(a) == "table" then aura = a end
    end
    if not aura then
        local byName = C_UnitAuras.GetAuraDataBySpellName
        if type(byName) ~= "function" then return nil end
        local ok, a = pcall(byName, "player", CC.AURA_NAME, "HELPFUL")
        if not ok or IsSecret(a) then return nil end
        if type(a) ~= "table" then return false end
        aura = a
    end
    local exp = PlainOf(aura.expirationTime, "number")
    return true, (exp and exp > 0) and exp or nil
end

-- the first plain cost of a spell, or nil
local function Cost(name)
    local fn = C_Spell and C_Spell.GetSpellPowerCost
    if type(fn) ~= "function" then return nil end
    local ok, costs = pcall(fn, name)
    if not ok or IsSecret(costs) or type(costs) ~= "table" then return nil end
    for i = 1, #costs do
        local c = costs[i]
        if type(c) == "table" and not IsSecret(c) then
            local v = PlainOf(c.cost, "number")
            if v ~= nil then return v end
        end
    end
    return nil
end

-- true (a probe that costs something reads 0), false (a probe reads its cost), nil (nothing plain)
local function CostSignal(kind)
    local list = CC.TELLS[kind]
    local seen = nil
    for i = 1, #list do
        local name = list[i]
        local v = Cost(name)
        if v ~= nil then
            if v > 0 then
                tellBase[name] = v
                seen = false
            elseif (tellBase[name] or 0) > 0 then
                return true
            end
        end
    end
    return seen
end

local function Close(now)
    local spent = (now - castAt) <= CAST_WINDOW or now < omen.expires - END_SLACK
    omen.open = false
    return spent and "cast" or "expire"
end

-- Reads the omen now; returns the change: "open", "change", "cast", "expire" or nil.
Update = function(now)
    if learned == false then
        if omen.open then omen.open = false; return "expire" end
        return nil
    end
    local up, exp, est
    local a, ae = ReadAura()
    if a ~= nil then
        up, exp, est = a, ae, false
        if a and not ae then exp, est = omen.open and omen.expires or now + CC.SECONDS, true end
        -- the probes' costs are plain out of combat: learn them while the omen is down
        if not a then CostSignal(Kind()) end
    else
        local c = CostSignal(Kind())
        if c == nil then
            if omen.open and now >= omen.expires then return Close(now) end
            return nil
        end
        up, est = c, true
        if c then exp = (omen.open and now < omen.expires) and omen.expires or now + CC.SECONDS end
    end
    if not up then
        if omen.open then return Close(now) end
        return nil
    end
    if not omen.open then
        omen.open, omen.expires, omen.est = true, exp, est
        return "open"
    end
    if omen.est and est and now >= omen.expires then
        omen.expires = now + CC.SECONDS              -- still free after its time: a new proc that was not seen
        return "change"
    end
    if not est and exp and math.abs(exp - omen.expires) > 0.5 then
        local renewed = exp > omen.expires + 0.5
        omen.expires, omen.est = exp, false
        return renewed and "change" or nil
    end
    omen.est = est and omen.est
    return nil
end

function CC.Remaining(now)
    if not omen.open then return nil end
    local left = omen.expires - now
    return left > 0 and left or 0
end

function CC.Open() return omen.open end

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
    if not (Art and Art.KIND and Art.SPRITE and Art.ATLAS) then return false end
    local ok, err = pcall(function()
        for _, kind in pairs(Art.KIND) do
            if kind.slots > maxSlots then maxSlots = kind.slots end
        end
        root = CreateFrame("Frame", "ForeverSTUwaveDruidClearcasting", UIParent)
        root:SetFrameStrata("MEDIUM")
        root:SetFrameLevel(20)
        root:EnableMouse(false)
        if FS.Layout and FS.Layout.Apply then FS.Layout.Apply(root, CC.LAYOUT_ID) end
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

local function Commit()
    local fa, fz = 0, -1
    if curSpell then fa, fz = curSpell.fill[1], curSpell.fill[3] end
    for s = 1, maxSlots do
        local sp = want[s]
        local fw
        if sp ~= 0 and s >= fa and s <= fz then
            local frac = curRem / Art.WIN
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
    if curKind or previewing then Commit() end
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

local function Reach(frames, n)
    Snapshot(frames[1])
    for i = 2, n do ApplyList(frames[i]) end
end

local function Stop()
    curKind, curSeq, curFrames = nil, nil, nil
    for s = 1, maxSlots do want[s] = 0 end
    if built then
        Commit()
        root:Hide()
    end
    curSpell = nil
end

local function StartSeq(kind, seq, idx, rem)
    curKind, curSpell, curSeq = kind, KINDS[kind], seq
    curFrames = curSpell.seqs[seq]
    curIdx, curAcc, curRem = idx, 0, rem
    Reach(curFrames, idx)
    root:Show()
    Commit()
end

local function Step()
    if curIdx < #curFrames then
        curIdx = curIdx + 1
        ApplyList(curFrames[curIdx])
        return
    end
    local seq = curSeq
    if seq == "cast" or seq == "exp" then
        Stop()
        sync(GetTime())
    elseif seq == "enter" then
        StartSeq(curKind, curRem <= Art.AMBER and "amber" or "held", 1, curRem)
    else
        curIdx = 1
        Snapshot(curFrames[1])
    end
end

local function Playing() return curSeq == "cast" or curSeq == "exp" end

-------------------------------------------------------------------------------
-- Driver
-------------------------------------------------------------------------------

local function Wanted()
    return omen.open and cfgOn and GunsightUp() and not previewing
end

local function Changed(change, now)
    if not change or not built or previewing then return end
    if change == "cast" or change == "expire" then
        if curKind and not Playing() then StartSeq(curKind, change == "cast" and "cast" or "exp", 1, curRem or 0) end
    elseif change == "change" and curKind and not Playing() then
        StartSeq(Kind(), "enter", 1, CC.Remaining(now) or 0)
    end
    sync(now)
end

local function Tick(_, elapsed)
    if elapsed > MAX_DT then elapsed = MAX_DT end
    local now = GetTime()
    readAcc = readAcc + elapsed
    if readAcc >= POLL or (omen.open and now >= omen.expires) then
        readAcc = 0
        Changed(Update(now), now)
    end
    if not curKind then return end
    if not Playing() then
        local rem = CC.Remaining(now)
        if rem then curRem = rem end
        if curSeq == "held" and curRem <= Art.AMBER then
            StartSeq(curKind, "amber", curSpell.amberStart == curSpell.heldStart and curIdx or 1, curRem)
        end
    end
    curAcc = curAcc + elapsed
    while curAcc >= FRAME_S and curKind do
        curAcc = curAcc - FRAME_S
        Step()
    end
    if curKind then Commit() end
end

local function UpdateDriver()
    local on = curKind ~= nil or (inCombat and learned ~= false and cfgOn)
    if on == driving then return end
    driving = on
    driver:SetScript("OnUpdate", on and Tick or nil)
    readAcc = 0
end

-- What shows now: start, switch form or stop. An exit in progress plays out first.
sync = function(now)
    if not (built and driver) or previewing then return end
    if Playing() then UpdateDriver() return end
    if not Wanted() then
        if curKind then Stop() end
        UpdateDriver()
        return
    end
    local kind = Kind()
    local rem = CC.Remaining(now) or 0
    if kind ~= curKind then
        StartSeq(kind, "enter", 1, rem)
    else
        curRem = rem
    end
    UpdateDriver()
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local function SpellName(id)
    if type(id) ~= "number" or IsSecret(id) then return nil end
    local fn = C_Spell and C_Spell.GetSpellName
    local ok, name = false, nil
    if type(fn) == "function" then ok, name = pcall(fn, id) end
    if not ok and type(GetSpellInfo) == "function" then ok, name = pcall(GetSpellInfo, id) end
    if not ok then return nil end
    return PlainOf(name, "string")
end

local function OnEvent(_, event, unitId, _, spellID)
    local now = GetTime()
    if event == "UNIT_SPELLCAST_SUCCEEDED" then
        local name = SpellName(spellID)
        if name and CC.NOT_SPENT[string.lower(name)] then return end
        castAt = now
        if C_Timer and C_Timer.After then
            C_Timer.After(0.1, function() Changed(Update(GetTime()), GetTime()) end)
        end
        return
    end
    if event == "PLAYER_REGEN_DISABLED" then
        inCombat = true
    elseif event == "PLAYER_REGEN_ENABLED" then
        inCombat = false
    elseif event == "SPELLS_CHANGED" or event == "PLAYER_ENTERING_WORLD" or event == "PLAYER_LEVEL_UP" then
        learned = Known(CC.TALENT)
    end
    Changed(Update(now), now)
    sync(now)
end

-------------------------------------------------------------------------------
-- The layout editor's preview
-------------------------------------------------------------------------------

local function ShowPreview()
    if not Build() then return end
    Stop()
    previewing = true
    curKind, curSpell, curSeq = "bear", KINDS.bear, "held"
    curFrames = curSpell.seqs.held
    curRem = Art.WIN * PREVIEW_REM
    Reach(curFrames, PREVIEW_FRAME)
    root:Show()
    Commit()
    curKind = nil
    UpdateDriver()
end

local function EndPreview()
    if not previewing then return end
    previewing = false
    Stop()
    sync(GetTime())
end


-- The preview plays like a fight: the baked enter animation, a hold of PREVIEW_HOLD seconds on the held loop, the baked exit,
-- a PREVIEW_GAP of nothing, again. Plain frames and the module's own sequences; it runs only while the preview is up.
local PREVIEW_HOLD, PREVIEW_GAP = 1.5, 0.6
local loop = { phase = nil, t = 0 }
local loopFrame

local function LoopBegin()
    loop.phase, loop.t = "enter", 0
    StartSeq("bear", "enter", 1, Art.WIN * PREVIEW_REM)
end

local function LoopTick(_, dt)
    if not (previewing and built and loop.phase) then
        loopFrame:SetScript("OnUpdate", nil)
        loop.phase = nil
        return
    end
    if dt > 0.1 then dt = 0.1 end
    if loop.phase == "gap" then
        loop.t = loop.t + dt
        if loop.t >= PREVIEW_GAP then LoopBegin() end
        return
    end
    curAcc = curAcc + dt
    while curAcc >= FRAME_S and curKind do
        curAcc = curAcc - FRAME_S
        Step()
    end
    if curKind then Commit() end
    if loop.phase == "enter" and curSeq ~= "enter" then
        loop.phase, loop.t = "hold", 0
    elseif loop.phase == "hold" then
        loop.t = loop.t + dt
        if loop.t >= PREVIEW_HOLD then
            loop.phase = "exit"
            StartSeq("bear", "exp", 1, curRem)
        end
    elseif loop.phase == "exit" and not curKind then
        loop.phase, loop.t = "gap", 0
    end
end

local function LoopStart()
    loopFrame = loopFrame or CreateFrame("Frame")
    LoopBegin()
    loopFrame:SetScript("OnUpdate", LoopTick)
end

local function LoopStop()
    loop.phase = nil
    if loopFrame then loopFrame:SetScript("OnUpdate", nil) end
end

-- The config window's preview (ConfigFlash.lua): the same still alert the layout editor shows, at its seat while a row of the
-- alert is pointed at or its Test button is on, whatever the class (the art is baked, nothing is read from the player). Out of
-- combat only. Show answers true when this call put it up (false: already up, or it cannot be built).
CC.Preview = {}
function CC.Preview.IsShown() return previewing end
function CC.Preview.Show()
    if previewing then return false end
    if type(InCombatLockdown) == "function" and InCombatLockdown() then return false end
    if not built then
        Art = Art or FS.DruidClearcastingArt
        if not (Art and Art.KIND) then return false end
        KINDS = KINDS or Art.KIND
    end
    if not Build() then return false end
    ShowPreview()
    if previewing then LoopStart() end
    return previewing
end
function CC.Preview.Hide()
    LoopStop()
    if previewing then EndPreview() end
end
function CC.Preview.Phase() return loop.phase end
function CC.Preview.Driver() return loopFrame end
function CC.Preview.Restyle()
    if previewing and built then pcall(Reseat) end
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local EVENTS = { "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "SPELLS_CHANGED", "PLAYER_ENTERING_WORLD", "PLAYER_LEVEL_UP",
    "UPDATE_SHAPESHIFT_FORM", "SPELL_UPDATE_USABLE" }

local function Register(f, event, ...)
    local FH = FS.FrameHelpers
    if FH and FH.RegisterEvent then return FH.RegisterEvent(f, event, ...) end
    if select("#", ...) > 0 then return pcall(f.RegisterUnitEvent, f, event, ...) end
    return pcall(f.RegisterEvent, f, event)
end

function CC.Init()
    if inited then return true end
    if not CC.Applies() then return false end
    Art = FS.DruidClearcastingArt
    if not (Art and Art.KIND) then
        LogOnce("deps", "the baked art is missing, the alert is off")
        return false
    end
    KINDS = Art.KIND
    if not Build() then return false end
    inited = true
    ReadConfig()
    learned = Known(CC.TALENT)
    inCombat = type(InCombatLockdown) == "function" and InCombatLockdown() and true or false
    driver = CreateFrame("Frame")
    events = CreateFrame("Frame")
    events:SetScript("OnEvent", function(...)
        local ok, err = pcall(OnEvent, ...)
        if not ok then LogOnce("event", err) end
    end)
    Register(events, "UNIT_SPELLCAST_SUCCEEDED", "player")
    Register(events, "UNIT_AURA", "player")
    for _, e in ipairs(EVENTS) do Register(events, e) end
    if FS.DruidState then
        if FS.DruidState.Start then FS.DruidState.Start() end
        if FS.DruidState.Subscribe then
            FS.DruidState.Subscribe(function(reason) if reason == "form" then sync(GetTime()) end end)
        end
    end
    if FS.Layout and FS.Layout.OnRescale then FS.Layout.OnRescale(Reseat) end
    if FS.Config and FS.Config.OnChange then
        FS.Config.OnChange(CC.SETTING.key, function() ReadConfig(); sync(GetTime()) end)
        if FS.GunsightAreas and FS.GunsightAreas.ALERT_SCALE_KEY then FS.Config.OnChange(FS.GunsightAreas.ALERT_SCALE_KEY, Reseat) end
    end
    if FS.Gunsight and FS.Gunsight.OnActiveChanged then FS.Gunsight.OnActiveChanged(function() sync(GetTime()) end) end
    if FS.Gunsight and FS.Gunsight.OnReady then FS.Gunsight.OnReady(function() sync(GetTime()) end) end
    if FS.OnAurasReadable then FS.OnAurasReadable(function() local now = GetTime(); Changed(Update(now), now) end) end
    if FS.LayoutEdit and FS.LayoutEdit.OnEditChanged then
        FS.LayoutEdit.OnEditChanged(function(editing)
            if not built then return end
            if editing then ShowPreview() else EndPreview() end
        end)
        if FS.LayoutEdit.IsEditing and FS.LayoutEdit.IsEditing() then ShowPreview() end
    end
    local now = GetTime()
    Update(now)
    sync(now)
    return true
end

local boot = CreateFrame("Frame")
boot:RegisterEvent("PLAYER_LOGIN")
boot:SetScript("OnEvent", function(self)
    self:UnregisterAllEvents()
    -- Module power (m.gs): the Gunsight HUD module off, this piece starts nothing.
    local MS = FS.ModuleSwitch
    if MS and not MS.On("m.gs") then return end
    local ok, err = pcall(CC.Init)
    if not ok then LogOnce("init", err) end
end)

-- for the harness
CC._Tick = Tick
CC._OnEvent = function(event, ...) return OnEvent(nil, event, ...) end
CC._driver = function() return driver end
CC._root = function() return root end
CC._sync = function(now) return sync(now) end
CC._state = function() return curKind, curSeq, curIdx, previewing, driving end
