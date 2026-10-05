-- Forever Synthwave: Gunsight HUD core (geometry root, anchor frames, piece registry).
--
-- The Gunsight HUD is the locked design in mockups/gunsight-hud-v2-2026-10-02/
-- gunsight-hud-v2-2026-10-02.html: two vertical tapes either side of your character, info boxes
-- above them, a next-cast tile, soul shards, buff reminders, a DoT time axis on the enemy side,
-- proc posts and one horizon hairline. Later lanes build the pieces; THIS file
-- owns where they sit and how they switch on and off, so no lane re-derives a coordinate.
--
-- GEOMETRY. The mockup canvas is 2000 x 1125 image px and the design space is 2560 x 1440
-- (FS.Layout.DESIGN_W/H), so design = image * 1.28, and UI units = design * FS.Layout.Scale().
-- The character centre (the mockup's CX, CY) is the ROOT ORIGIN: the root frame is 0 x 0 and sits
-- (CX - W/2, -(CY - H/2)) * 1.28 = (-6.4, -86.4) design px from UIParent CENTER (Y up), plus a
-- saved nudge (/fsgun seat). Every anchor frame is a child of the root, seated by mockup image
-- coordinates, never by a hand-converted number. Nothing is positioned at file load (UIParent is
-- only 768 tall then); PLAYER_LOGIN and the FS.Layout rescale hook seat everything.
--
-- PIECES. Keys you, next, shard, buff, tgt, dot, prc, party. RegisterPiece(key, {frame,
-- onShow, onHide}) hands a piece's frame to the registry; SetPiece(key, on, instant) fades it
-- (a 0.25 s Alpha AnimationGroup, never OnUpdate) and persists the state. State lives in
-- ForeverSynthwaveDB.gunsight and is applied to a piece when it registers, or at init for pieces
-- that registered before SavedVariables existed. A PROTECTED frame (the party frames) is never
-- Show/Hidden or EnableMouse'd in combat (ADDON_ACTION_BLOCKED fires even inside a pcall): alpha
-- only, the rest reconciled on PLAYER_REGEN_ENABLED.
--
-- Slash: /fsgun [on | off | seat <dx> <dy> | piece <key> on|off | debug]. Public surface (all
-- FS.Gunsight.*): ui, Point, root, anchors, G, RegisterPiece, SetPiece, IsPieceOn, OnPieceChanged,
-- OnReady, IsEnabled, SetSeat, Reseat.

local _, FS = ...

FS.Gunsight = FS.Gunsight or {}
local Gunsight = FS.Gunsight

-------------------------------------------------------------------------------
-- Constants (mockup name in the comment; gunsight-harness.py re-reads every one from the HTML)
-------------------------------------------------------------------------------

local GRID = 1.28                                   -- design px per image px (2560 / 2000)
local U = 1 / GRID                                  -- the mockup's U: addon units to image px

local W, H, CX, CY = 2000, 1125, 995, 630           -- W, H, CX, CY: canvas and character centre
local TOP, BOT, FR_T, FR_B = 508, 752, 500, 760     -- TOP, BOT (scale), FR_T, FR_B (tape frame)
local TL = { x0 = 796, x1 = 826 }                   -- TL: your tape
local TR = { x0 = 1164, x1 = 1194 }                 -- TR: target tape
local BOXL = { x = 724, y = 424, w = 114, h = 56 }  -- BOXL: your info box
local BOXR = { x = 1152, y = 424, w = 114, h = 56 } -- BOXR: target info box
local LBRK = 836                                    -- LBRK: left proc post x
local RBRK = 2 * CX - LBRK                          -- RBRK: right proc post x
local DOT_AX, DOT_END = 1239, 1387                  -- DOT_AX: DoT axis, DOT_END: lane end
local LANE = { 1283, 1312, 1341, 1370 }             -- LANE: DoT lane x
local NXT_S, NXT_PAD = 56, 10                       -- NXT.s, the gap left of BOXL (addon units)
local SH_SC, SH_W, SH_H, SH_G = 4, 10, 18, 4        -- SH_SC, SH_W, SH_H, SH_G (addon units)
local SH_DROP = 6                                   -- SH_Y = FR_B + 6*U (addon units)
local BUFF_S, BUFF_GAP = 24, 8                      -- drawBuff bs, and its 8*U drop under the shards
local HZ_PAD_L, HZ_PAD_R = 2, 12                    -- horizon: TL.x1 + 2 ... DOT_AX - 12
local PROC_BASE, PROC_GROW, PROC_TICK = 16, 54, 7   -- drawProc: half = 16 + q*54, tick 7 long

local PIECE_KEYS = { "you", "next", "shard", "buff", "tgt", "dot", "prc", "party" }
local FADE_SECONDS = 0.25
local PREFIX = "|cffff4488Forever STUwave|r: gunsight: "

Gunsight.G = {
    GRID = GRID, U = U, W = W, H = H, CX = CX, CY = CY,
    TOP = TOP, BOT = BOT, FR_T = FR_T, FR_B = FR_B, TL = TL, TR = TR, BOXL = BOXL, BOXR = BOXR,
    LBRK = LBRK, RBRK = RBRK, DOT_AX = DOT_AX, DOT_END = DOT_END, LANE = LANE,
    NXT_S = NXT_S, NXT_PAD = NXT_PAD, SH_SC = SH_SC, SH_W = SH_W, SH_H = SH_H, SH_G = SH_G,
    SH_DROP = SH_DROP, BUFF_S = BUFF_S, BUFF_GAP = BUFF_GAP, HZ_PAD_L = HZ_PAD_L, HZ_PAD_R = HZ_PAD_R,
    PROC_BASE = PROC_BASE, PROC_GROW = PROC_GROW, PROC_TICK = PROC_TICK,
}
Gunsight.PIECES = PIECE_KEYS

-- Anchor rects in image px, top-left origin: { name, x, y, w, h }. The comment says where the
-- mockup draws it.
local SH_Y = FR_B + SH_DROP * U
local SH_ROW_W = SH_SC * SH_W * U + (SH_SC - 1) * SH_G * U
local NXT_PX = NXT_S * U
local BUFF_PX = BUFF_S * U
local PROC_W = 2 * PROC_TICK
local PROC_H = 2 * (PROC_BASE + PROC_GROW)

local ANCHOR_SPECS = {
    { "tapeL", TL.x0, FR_T, TL.x1 - TL.x0, FR_B - FR_T },                         -- your tape frame
    { "tapeR", TR.x0, FR_T, TR.x1 - TR.x0, FR_B - FR_T },                         -- target tape frame
    { "boxL", BOXL.x, BOXL.y, BOXL.w, BOXL.h },                                   -- your info box
    { "boxR", BOXR.x, BOXR.y, BOXR.w, BOXR.h },                                   -- target info box
    { "dotAxis", DOT_AX, TOP, DOT_END - DOT_AX, BOT - TOP },                      -- DoT axis to lane end
    { "next", BOXL.x - NXT_PAD * U - NXT_PX, BOXL.y + (BOXL.h - NXT_PX) / 2, NXT_PX, NXT_PX }, -- NXT tile
    { "shards", TL.x1 - SH_ROW_W, SH_Y, SH_ROW_W, SH_H * U },                     -- shard row, right aligned to TL
    { "buff", (TL.x0 + TL.x1) / 2 - BUFF_PX / 2, SH_Y + SH_H * U + BUFF_GAP * U, BUFF_PX, BUFF_PX }, -- buff tile
    { "procL", LBRK - PROC_W / 2, CY - PROC_H / 2, PROC_W, PROC_H },              -- left proc post, horizon centred
    { "procR", RBRK - PROC_W / 2, CY - PROC_H / 2, PROC_W, PROC_H },              -- right proc post
    { "horizon", TL.x1 + HZ_PAD_L, CY, (DOT_AX - HZ_PAD_R) - (TL.x1 + HZ_PAD_L), 0 }, -- horizon hairline
}

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local pieces = {}              -- key -> { key, frame, onShow, onHide, group, anim, deferred }
local pieceState = {}          -- key -> boolean, the live truth (saved at init, defaults on)
local earlySaves = {}          -- SetPiece calls made before SavedVariables existed
local changedCallbacks = {}
local readyCallbacks = {}
local logged = {}
local seat = { dx = 0, dy = 0 }
local pendingSeat                -- a SetSeat made before Init; Init applies it over the saved seat
local enabled = true
local inited, loggedIn, ready, debugOn = false, false, false, false
local root
local anchors = {}
local outlines = {}

for _, key in ipairs(PIECE_KEYS) do pieceState[key] = true end

local function IsKnownKey(key)
    for _, k in ipairs(PIECE_KEYS) do
        if k == key then return true end
    end
    return false
end

-- A degrade is logged once per key, to chat and to ForeverSynthwaveDB.degradeLog.
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsight_" .. key, PREFIX .. tostring(msg))
    end
end

local function Say(msg)
    print(PREFIX .. msg)
end

-------------------------------------------------------------------------------
-- Geo
-------------------------------------------------------------------------------

local function Scale()
    if FS.Layout and FS.Layout.Scale then return FS.Layout.Scale() end
    return 1
end

-- Image px (the mockup's canvas) to UI units at the current scale.
function Gunsight.ui(imagePx)
    return imagePx * GRID * Scale()
end

-- Seats `frame` so its `point` sits at mockup image coordinate (imgX, imgY), relative to the root.
function Gunsight.Point(frame, point, imgX, imgY)
    local k = GRID * Scale()
    frame:ClearAllPoints()
    frame:SetPoint(point, root, "CENTER", (imgX - CX) * k, -(imgY - CY) * k)
end

-- The root is the character centre: design offset (-6.4, -86.4) from UIParent CENTER, Y up.
local ROOT_DX = (CX - W / 2) * GRID
local ROOT_DY = -(CY - H / 2) * GRID

root = CreateFrame("Frame", "ForeverSynthwaveGunsight", UIParent)
root:SetFrameStrata("MEDIUM")
-- 1 x 1, not 0 x 0: a 0 x 0 frame has no rect on this client (GetCenter is nil), so every frame
-- anchored to it had no rect and nothing drew (measured live 2026-10-03). Children anchor to the
-- root's CENTER, so a 1 x 1 root moves no seat.
root:SetSize(1, 1)
Gunsight.root = root

for _, spec in ipairs(ANCHOR_SPECS) do
    local frame = CreateFrame("Frame", "ForeverSynthwaveGunsight_" .. spec[1], root)
    frame.gunsightSpec = spec
    anchors[spec[1]] = frame
end
Gunsight.anchors = anchors

local function Reseat()
    if not loggedIn then return end
    local scale = Scale()
    root:ClearAllPoints()
    root:SetPoint("CENTER", UIParent, "CENTER", (ROOT_DX + seat.dx) * scale, (ROOT_DY + seat.dy) * scale)
    for _, frame in pairs(anchors) do
        local spec = frame.gunsightSpec
        frame:SetSize(Gunsight.ui(spec[4]), Gunsight.ui(spec[5]))
        Gunsight.Point(frame, "TOPLEFT", spec[2], spec[3])
    end
end
Gunsight.Reseat = Reseat

if FS.Layout and FS.Layout.OnRescale then FS.Layout.OnRescale(Reseat) end

-------------------------------------------------------------------------------
-- Saved settings
-------------------------------------------------------------------------------

local function IsFiniteNumber(v)
    return type(v) == "number" and v == v and v > -1e9 and v < 1e9
end

-- ForeverSynthwaveDB.gunsight = { enabled = true, pieces = { key = true ... }, seat = { dx, dy } }.
local function NormalizedDB()
    if type(ForeverSynthwaveDB) ~= "table" then ForeverSynthwaveDB = {} end
    local db = ForeverSynthwaveDB.gunsight
    if type(db) ~= "table" then
        db = {}
        ForeverSynthwaveDB.gunsight = db
    end
    db.enabled = db.enabled ~= false
    if type(db.pieces) ~= "table" then db.pieces = {} end
    for _, key in ipairs(PIECE_KEYS) do
        if type(db.pieces[key]) ~= "boolean" then db.pieces[key] = true end
    end
    if type(db.seat) ~= "table" then db.seat = {} end
    if not IsFiniteNumber(db.seat.dx) then db.seat.dx = 0 end
    if not IsFiniteNumber(db.seat.dy) then db.seat.dy = 0 end
    return db
end

-------------------------------------------------------------------------------
-- Piece registry
-------------------------------------------------------------------------------

local function IsProtectedFrame(frame)
    if not frame.IsProtected then return false end
    local ok, value = pcall(frame.IsProtected, frame)
    return ok and value == true
end

local function RunHook(piece, name)
    local fn = piece[name]
    if not fn then return end
    local ok, err = pcall(fn, piece.key)
    if not ok then LogOnce("hook_" .. piece.key .. "_" .. name, piece.key .. " " .. name .. " failed: " .. tostring(err)) end
end

-- Puts the frame itself into the on or off look. In combat a protected frame gets ALPHA ONLY:
-- Show, Hide and EnableMouse are all blocked under lockdown (and raise ADDON_ACTION_BLOCKED even
-- inside a pcall), so `deferred` marks it for the PLAYER_REGEN_ENABLED pass, which does the real
-- Show/Hide. Mouse is never toggled: a hidden frame takes no mouse, and the invisible frame left
-- shown in combat stays clickable until the reconcile (that was already so, the old in combat
-- EnableMouse was blocked).
local function ApplyFrame(piece, on)
    local frame = piece.frame
    if piece.group then piece.group:Stop() end
    if IsProtectedFrame(frame) and InCombatLockdown() then
        frame:SetAlpha(on and 1 or 0)
        piece.deferred = true
        return
    end
    piece.deferred = false
    if on then
        frame:SetAlpha(1)
        frame:Show()
    else
        frame:Hide()
        frame:SetAlpha(0)
    end
end

-- The fade group is built once per piece. Its OnFinished lands the frame in the piece's CURRENT
-- state, so an interrupted fade or a flip mid fade can never strand it half way.
local function FadeGroup(piece)
    if piece.group then return piece.group, piece.anim end
    local group = piece.frame:CreateAnimationGroup()
    local anim = group:CreateAnimation("Alpha")
    anim:SetDuration(FADE_SECONDS)
    if anim.SetSmoothing then anim:SetSmoothing("IN_OUT") end
    if group.SetToFinalAlpha then group:SetToFinalAlpha(true) end
    group:SetScript("OnFinished", function()
        ApplyFrame(piece, pieceState[piece.key] == true)
    end)
    piece.group, piece.anim = group, anim
    return group, anim
end

-- Fades from wherever the frame is now (a flip mid fade does not snap first). An animation group
-- never plays on a frame that is not VISIBLE (IsVisible, which counts every ancestor; IsShown is
-- only the frame's own flag), so OnFinished would never fire and the frame would be stranded:
-- under a hidden ancestor the frame snaps to the final state instead.
local function Fade(piece, on)
    local frame = piece.frame
    if piece.group then piece.group:Stop() end
    local from = frame:IsShown() and frame:GetAlpha() or 0
    if on then
        if not frame:IsShown() then
            frame:SetAlpha(0)
            frame:Show()
        end
    end
    if not frame:IsVisible() then
        ApplyFrame(piece, on)
        return
    end
    local group, anim = FadeGroup(piece)
    anim:SetFromAlpha(from)
    anim:SetToAlpha(on and 1 or 0)
    group:Play()
end

local function ApplyAndHook(piece, on, instant)
    if instant or not piece.frame:IsVisible() and not on then
        ApplyFrame(piece, on)
    elseif IsProtectedFrame(piece.frame) and InCombatLockdown() then
        ApplyFrame(piece, on)
    else
        Fade(piece, on)
    end
    RunHook(piece, on and "onShow" or "onHide")
end

function Gunsight.IsPieceOn(key)
    return pieceState[key] == true
end

function Gunsight.RegisterPiece(key, spec)
    if not IsKnownKey(key) then
        LogOnce("badkey_" .. tostring(key), "RegisterPiece: unknown piece key " .. tostring(key))
        return false
    end
    if type(spec) ~= "table" or type(spec.frame) ~= "table" then
        LogOnce("badspec_" .. key, "RegisterPiece(" .. key .. "): a spec needs a frame")
        return false
    end
    local old = pieces[key]
    if old and old.group then old.group:Stop() end
    local piece = { key = key, frame = spec.frame, onShow = spec.onShow, onHide = spec.onHide }
    pieces[key] = piece
    -- Before init the saved state does not exist yet; Init applies it to everything registered.
    if inited then
        local on = pieceState[key] == true
        ApplyFrame(piece, on)
        RunHook(piece, on and "onShow" or "onHide")
    end
    return piece
end

local function Notify(key, on)
    for _, fn in ipairs(changedCallbacks) do
        local ok, err = pcall(fn, key, on)
        if not ok then LogOnce("changed_callback", "an OnPieceChanged callback failed: " .. tostring(err)) end
    end
end

function Gunsight.SetPiece(key, on, instant)
    if not IsKnownKey(key) then return false end
    on = on and true or false
    local changed = pieceState[key] ~= on
    pieceState[key] = on
    if inited then
        ForeverSynthwaveDB.gunsight.pieces[key] = on
    else
        earlySaves[key] = on
    end
    if not changed then return true end
    local piece = pieces[key]
    if piece and inited then ApplyAndHook(piece, on, instant) end
    Notify(key, on)
    return true
end

-- OnPieceChanged fires only for a change made after init (SetPiece). The state Init restores from
-- SavedVariables is NOT announced: a listener reads IsPieceOn(key) inside its OnReady callback for
-- the initial state, then follows OnPieceChanged from there.
function Gunsight.OnPieceChanged(fn)
    if type(fn) == "function" then changedCallbacks[#changedCallbacks + 1] = fn end
end

-- OnReady runs once, at PLAYER_LOGIN after Init (at once if that already happened). That is the
-- moment IsPieceOn(key) is final for every key, including pieces saved off.
function Gunsight.OnReady(fn)
    if type(fn) ~= "function" then return end
    if ready then
        local ok, err = pcall(fn)
        if not ok then LogOnce("ready_callback", "an OnReady callback failed: " .. tostring(err)) end
    else
        readyCallbacks[#readyCallbacks + 1] = fn
    end
end

function Gunsight.IsEnabled()
    return enabled
end

function Gunsight.SetSeat(dx, dy)
    if not IsFiniteNumber(dx) or not IsFiniteNumber(dy) then return false end
    seat.dx, seat.dy = dx, dy
    if inited then
        local saved = ForeverSynthwaveDB.gunsight.seat
        saved.dx, saved.dy = dx, dy
    else
        pendingSeat = { dx = dx, dy = dy }
    end
    Reseat()
    return true
end

local function Init()
    if inited then return end
    local db = NormalizedDB()
    for key, on in pairs(earlySaves) do db.pieces[key] = on end
    earlySaves = {}
    enabled = db.enabled
    seat.dx, seat.dy = db.seat.dx, db.seat.dy
    if pendingSeat then
        seat.dx, seat.dy = pendingSeat.dx, pendingSeat.dy
        db.seat.dx, db.seat.dy = seat.dx, seat.dy
        pendingSeat = nil
    end
    for _, key in ipairs(PIECE_KEYS) do pieceState[key] = db.pieces[key] end
    inited = true
    for _, key in ipairs(PIECE_KEYS) do
        local piece = pieces[key]
        if piece then
            ApplyFrame(piece, pieceState[key])
            RunHook(piece, pieceState[key] and "onShow" or "onHide")
        end
    end
end

-- Out of combat again: finish whatever a protected frame could not do under lockdown.
local function Reconcile()
    for _, key in ipairs(PIECE_KEYS) do
        local piece = pieces[key]
        if piece and piece.deferred then ApplyFrame(piece, pieceState[key] == true) end
    end
end

-------------------------------------------------------------------------------
-- Debug outlines
-------------------------------------------------------------------------------

local DEBUG_COLORS = {
    { 1, 0.18, 0.59 }, { 0.13, 0.88, 1 }, { 0.66, 0.33, 0.97 }, { 1, 0.82, 0.25 }, { 0.22, 1, 0.08 }, { 1, 0.71, 0.28 },
}

local function BuildOutline(name, frame, color)
    local edges = {}
    local function edge(p1, p2, horizontal)
        local t = frame:CreateTexture(nil, "OVERLAY")
        t:SetColorTexture(color[1], color[2], color[3], 1)
        t:SetPoint(p1, frame, p1)
        t:SetPoint(p2, frame, p2)
        if horizontal then t:SetHeight(1) else t:SetWidth(1) end
        edges[#edges + 1] = t
    end
    edge("TOPLEFT", "TOPRIGHT", true)
    edge("BOTTOMLEFT", "BOTTOMRIGHT", true)
    edge("TOPLEFT", "BOTTOMLEFT", false)
    edge("TOPRIGHT", "BOTTOMRIGHT", false)
    local label
    local ok, made = pcall(frame.CreateFontString, frame, nil, "OVERLAY", "GameFontNormalSmall")
    if ok and made then
        label = made
        label:SetPoint("BOTTOMLEFT", frame, "TOPLEFT", 0, 2)
        label:SetText(name)
        label:SetTextColor(color[1], color[2], color[3], 1)
        edges[#edges + 1] = label
    end
    return edges
end

local function SetDebug(on)
    debugOn = on
    local i = 0
    for _, spec in ipairs(ANCHOR_SPECS) do
        i = i + 1
        local name = spec[1]
        if on and not outlines[name] then
            outlines[name] = BuildOutline(name, anchors[name], DEBUG_COLORS[(i - 1) % #DEBUG_COLORS + 1])
        end
        for _, region in ipairs(outlines[name] or {}) do
            if on then region:Show() else region:Hide() end
        end
    end
end

-------------------------------------------------------------------------------
-- Events and the slash command
-------------------------------------------------------------------------------

local events = CreateFrame("Frame")
events:RegisterEvent("ADDON_LOADED")
events:RegisterEvent("PLAYER_LOGIN")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:SetScript("OnEvent", function(_, event, arg1)
    if event == "ADDON_LOADED" then
        if arg1 == "ForeverSynthwave" then Init() end
    elseif event == "PLAYER_LOGIN" then
        Init()
        loggedIn = true
        Reseat()
        if not ready then
            ready = true
            local list = readyCallbacks
            readyCallbacks = {}
            for _, fn in ipairs(list) do
                local ok, err = pcall(fn)
                if not ok then LogOnce("ready_callback", "an OnReady callback failed: " .. tostring(err)) end
            end
        end
    elseif event == "PLAYER_REGEN_ENABLED" then
        Reconcile()
    end
end)

local function PrintStatus()
    local parts = {}
    for _, key in ipairs(PIECE_KEYS) do
        parts[#parts + 1] = key .. " " .. (pieceState[key] and "on" or "off")
    end
    Say((enabled and "enabled" or "disabled") .. ", seat " .. seat.dx .. ", " .. seat.dy .. " (design px), debug "
        .. (debugOn and "on" or "off"))
    Say("pieces: " .. table.concat(parts, ", "))
    Say("/fsgun on | off | seat <dx> <dy> | piece <key> on|off | debug")
end

local function SetEnabled(on)
    enabled = on
    if inited then ForeverSynthwaveDB.gunsight.enabled = on end
    Say((on and "enabled" or "disabled") .. "; /reload for it to take effect.")
end

SLASH_FSGUN1 = "/fsgun"
SlashCmdList["FSGUN"] = function(msg)
    local cmd, a, b = string.match(string.lower(tostring(msg or "")), "^%s*(%S*)%s*(%S*)%s*(%S*)")
    if cmd == "" then
        PrintStatus()
    elseif cmd == "on" then
        SetEnabled(true)
    elseif cmd == "off" then
        SetEnabled(false)
    elseif cmd == "seat" then
        if Gunsight.SetSeat(tonumber(a), tonumber(b)) then
            Say("seat " .. seat.dx .. ", " .. seat.dy .. " (design px, Y up).")
        else
            Say("usage: /fsgun seat <dx> <dy>  (numbers, design px, Y up)")
        end
    elseif cmd == "piece" then
        if not IsKnownKey(a) then
            Say("unknown piece '" .. a .. "'; keys: " .. table.concat(PIECE_KEYS, ", "))
        elseif b ~= "on" and b ~= "off" then
            Say("usage: /fsgun piece <key> on|off")
        else
            Gunsight.SetPiece(a, b == "on")
            Say(a .. " " .. b .. ".")
        end
    elseif cmd == "debug" then
        SetDebug(not debugOn)
        Say("debug outlines " .. (debugOn and "on" or "off") .. ".")
    else
        Say("/fsgun on | off | seat <dx> <dy> | piece <key> on|off | debug")
    end
end
