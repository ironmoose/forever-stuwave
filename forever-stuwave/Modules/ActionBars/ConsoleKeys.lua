-- Forever STUwave: Console keys
--
-- The eight keys on the Console's shoulder tab (the locked design in
-- the design mockup: DECK_DEFS, GLY, keySvg,
-- the `.cdeck.bm` key rules and the Rings block). Each key toggles ONE switch: a Gunsight piece, or for the party
-- key the party frames' own switch, which does not depend on the Gunsight HUD (DEFS order is the slot order when
-- every key shows; the pitch is one even gap, there are no group gaps):
--
--   key 1  you    Your Cast      cyan    glyph_hud_chev       key 6  dot    Target side    violet  clock
--   key 2  next   Next Cast      gold    play                 key 7  prc    Procs          amber   bolt
--   key 3  shard  Soul Shards    violet  diamond              key 8  party  Party Frame    green   group
--   key 4  buff   Buff Reminder  pink    shield
--   key 5  tgt    Target Cast    pink    cross
--
-- HIDING. A key shows only when its piece has something to draw for the class profile
-- (FS.Hud.GetProfile(), HudProfiles.lua data), read from the same fields the piece reads:
--   shard  profile.resource.shards          (CombatHud draws the shard row only then)
--   prc    a profile.procs entry with a side (GunsightFrame draws a rung only for a proc with a side)
--   next   profile.rotation not empty       (HudLogic's next cast comes from the rotation)
--   buff   profile.selfBuffs not empty      (the buff reminder tile comes from the self buffs)
--   you, tgt, dot, party                    never read the profile: always shown
--          (the dot key switches both target side areas, Target debuffs and the class module, and Target debuffs
--          applies to every class, so it shows even for a class with no HUD profile)
-- TOOLTIP. The dot key names its slot from the profile: a profile `dotLabel = { n, d }` (HudProfiles.lua, the
-- Paladin's "Target side" text naming the Seal module) replaces the key's title and description, each field on its own, and a missing or
-- non string field keeps the default Target side text. It is read from the profile every time the tooltip is built
-- (ConsoleKeys.Label), so it follows the profile as it resolves, like the shown set.
--
-- No profile (a class with no HUD) hides the four profile keys (shard, prc, next, buff). Hiding is VISUAL ONLY:
-- the key is Hidden, the key's on/off setting is never touched (nothing is set) and the
-- hidden key still follows its switch's change notice. The shown keys take consecutive slots (the Console's
-- KeyRect(slot)) at the even pitch, and `Console.SetKeyCount(n)` sizes the shoulder tab for the shown
-- count. The count is the number of keys actually drawn, whatever hid the rest. The party key is always drawn
-- (see KeyDrawn), so with the Gunsight HUD off (disabled at login, or switched off live) the tab is ONE key wide
-- with the party key in slot 0, at the tab's full height; the tab would go away only at zero drawn keys, which
-- cannot happen once the keys are built.
-- The profile is resolved by HudLogic at load or PLAYER_LOGIN, before the Gunsight's OnReady
-- builds these keys; HudLogic has no profile-change hook (a class never changes), so the visibility is
-- recomputed at every hook this file already has (the Console's geometry callback, a rescale,
-- PLAYER_REGEN_ENABLED) plus PLAYER_ENTERING_WORLD, and applied only when the shown set changed.
--
-- PLAIN BUTTONS, NOT SECURE. They only call Switch.Set: FS.Gunsight.SetPiece, which itself fades a piece and
-- uses alpha only for a protected frame in combat, or FS.PartyFrames.SetShown, which keeps the same combat
-- rule for the party frames' secure rows, so a click works in combat. Click only: there
-- are no keybinds and no number in the tooltip. They hang off `FS.Console.tab` (a plain frame that
-- shows and hides with the Console, so /fsconsole off hides the keys with it) and are seated from
-- `FS.Console.KeyRect(index, scale)`, never from a copy of the tab geometry: a change to the tab
-- moves the keys. There are deliberately NO coloured annunciator ticks under the tab's top edge
-- (the mockup's CN_TICK rects were dropped by design): on and off show in the ring, the glyph and
-- its LED underline inside the key.
--
-- LOOK (the Bar-matched `.cdeck.bm` key). Everything inside the key is drawn on a child frame scaled
-- by FS.Layout.Scale(), so one unit is one design px and the baked cut-corner textures land at their
-- native size (the same idiom as Console.art). Cut-corner button plate, a 1 texel cyan edge (alpha
-- .45 off, .95 lit), a cyan halo (.18 off, .34 lit, pink .7 on hover, pink .5 while pressed), a pink
-- wash on hover (.15, .3 pressed), the glyph (#5a5070 off, the key colour 88% toward white lit, plus
-- an ADD copy at .5 lit) and a 20 x 2 LED underline that is lit only when on.
--
-- RING. media/hud_key_ring_00..15.tga are the sixteen arcs of the key's inset outline. The ring is
-- invisible at rest. Turning a key ON ignites the arcs (FS.ChevronCastBar.Fx: makeFlicker / segLook,
-- the exact cast bar ignite, in the key's colour); turning it OFF runs the 1.0 s power outage
-- (brownout, stutter, cut, fade) while the key keeps its lit look, then the key goes dark. After the
-- last animated frame the ring eases out over 0.4 s. The port of `ringUpdate`, one OnUpdate on one
-- driver frame that exists only while some ring is live.
--
-- STATE. The switch owns it, and Switch (below) is the one place that knows which switch a key has: IsOn,
-- Set and OnChanged. Every key but party is a Gunsight piece (IsPieceOn, SetPiece, OnPieceChanged), so
-- `/fsgun piece <key> on|off` moves those keys too. The party key is FS.PartyFrames (IsShown, SetShown,
-- OnShownChanged): the party frames are no Gunsight piece, they show and hide themselves from their saved
-- value whether the Gunsight HUD is built or not, so this file registers nothing with the Gunsight for them
-- and a change to that value from anywhere (a profile switch) moves the key. A key reads IsOn at OnReady
-- and then follows OnChanged. A change made while the key is not visible, or with
-- ForeverSTUwaveDB.reducedMotion == true (nothing in the addon sets it yet), snaps with no ring.
--
-- WHAT EXISTS IS READ ONCE, THE SWITCH IS LIVE. All eight keys are built once the Gunsight has said what it built
-- (Gunsight.OnReady) and the Console has a tab. Whether the HUD keys are DRAWN is captured at login: a Gunsight
-- that was off then draws only the party key, and `/fsgun on` afterwards draws no HUD key until a reload. A
-- Gunsight that was on follows Gunsight.OnActiveChanged, because the keys live on Console.tab and not under the
-- Gunsight root, so hiding the root does not hide them. Inactive: each HUD key is hidden at once (plain frames,
-- so also in combat) and no HUD key is drawn, so the tab narrows to the party key (at regen in combat, with the
-- other re-seats). Active again: the layout is re-seated for the shown set (a key the last layout still drew shows
-- at once, which only happens for an off and on inside one fight). The tab resize and any re-seat wait for
-- PLAYER_REGEN_ENABLED in combat like every other re-seat here. The
-- party key is no part of this: the master switch never touches it or the party frames it switches.
--
-- SCALE AND COMBAT. Built once. Re-seated (visibility, slots, positions, sizes, art scale, and the
-- tab's size, or its absence, through Console.SetKeyCount) from the Console's geometry callback,
-- FS.Layout.OnRescale and the visibility hooks above, outside combat only (the tab hangs off the protected action stack's
-- anchor chain, and Console.SetKeyCount refuses in combat); a re-seat asked for in combat runs at
-- PLAYER_REGEN_ENABLED, all of it in one pass so the tab and the keys never disagree.

local _, FS = ...

local ConsoleKeys = {}
FS.ConsoleKeys = ConsoleKeys

local Console = FS.Console
local Theme = FS.Theme

local function Degrade(key, msg)
    if FS.LogDegradeOnce then
        FS.LogDegradeOnce("consolekeys_" .. key, "|cffff4488Forever STUwave|r: console keys " .. key .. ": " .. tostring(msg))
    end
end

if not (Console and Console.KeyRect and Console.KEY and Console.SetKeyCount and FS.ActionBars and FS.ActionBars.OnGeometry
        and FS.Gunsight and FS.Gunsight.OnReady and FS.Gunsight.OnPieceChanged and FS.Gunsight.OnActiveChanged
        and FS.PartyFrames and FS.PartyFrames.IsShown and FS.PartyFrames.SetShown and FS.PartyFrames.OnShownChanged
        and Theme and Theme.AddSliceTexture and Theme.ApplyNineSlice) then
    Degrade("load", "needs Console.lua, ActionBars.lua, Gunsight.lua, PartyFrames.lua and Theme.lua first, no keys")
    return
end

local Gunsight = FS.Gunsight
local PartyFrames = FS.PartyFrames

-- Where a key's on/off state lives (see STATE above). The party key is the party frames' own switch, every other key
-- a Gunsight piece. Calls go through the Gunsight table at call time, so nothing here caches a function.
local Switch = {}
function Switch.IsOn(piece)
    if piece == "party" then return PartyFrames.IsShown() end
    return Gunsight.IsPieceOn(piece)
end
function Switch.Set(piece, on)
    if piece == "party" then return PartyFrames.SetShown(on) end
    return Gunsight.SetPiece(piece, on)
end
-- fn(piece, on) runs after a key's state changed, however it was changed.
function Switch.OnChanged(fn)
    Gunsight.OnPieceChanged(fn)
    PartyFrames.OnShownChanged(function(on) fn("party", on) end)
end

-------------------------------------------------------------------------------
-- Constants (the mockup's: DECK_DEFS, kpts, keySvg, the .cdeck.bm rules, Rings)
-------------------------------------------------------------------------------

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"
local RING_N = 16
local RING_W, RING_H = 42, 34            -- design units the ring textures cover (key + 4 pad each side)
local KEY_W, KEY_H = 34, 26
local GLYPH_X, GLYPH_Y, GLYPH_S = 10.6, 4.1, 12.8   -- translate(10.6 4.1) scale(.8) of the 16 box
local GLYPH_GLOW_SCALE = 1.35            -- the ADD copy (.kgg: a wider, blurred stroke) drawn a little larger
local LED_X, LED_Y, LED_W, LED_H = 4, 19, 20, 2
local HIT_V = 6                          -- hit area grows 6 up and down: 146.15% of the key height
local TIP_GAP = 10                       -- design px between key and tooltip
local RING_FADE_MS = 400                 -- the ring eases out this long after the last animated frame

-- The mockup's colour tokens (:root), 0 to 1.
local function Hex(r, g, b) return { r / 255, g / 255, b / 255 } end
local COLORS = {
    cyan = Hex(0x22, 0xe0, 0xff), gold = Hex(0xff, 0xd2, 0x3f), violet = Hex(0xa8, 0x55, 0xf7),
    pink = Hex(0xff, 0x2e, 0x97), amber = Hex(0xff, 0xb6, 0x48), green = Hex(0x39, 0xff, 0x14),
}
local WHITE = Hex(0xf3, 0xfb, 0xff)
local GLYPH_OFF = Hex(0x5a, 0x50, 0x70)
local MUTED = Hex(0x9d, 0x93, 0xc4)

-- DECK_DEFS: piece key, name, description, colour, glyph file. Order = key order (index 0 to 7).
local DEFS = {
    { key = "you", n = "Your Cast", d = "Your cast bar and timer box", c = "cyan", g = "chev" },
    { key = "next", n = "Next Cast", d = "Profile's next spell, gold on proc", c = "gold", g = "play" },
    { key = "shard", n = "Soul Shards", d = "Held shards under your cast bar", c = "violet", g = "diamond" },
    { key = "buff", n = "Buff Reminder", d = "Missing self buff tile", c = "pink", g = "shield" },
    { key = "tgt", n = "Target Cast", d = "Target cast bar, kick and lock state", c = "pink", g = "cross" },
    { key = "dot", n = "Target side", d = "Target debuffs and class module beside the target cast bar", c = "violet", g = "clock" },
    { key = "prc", n = "Procs", d = "Proc and cooldown posts", c = "amber", g = "bolt" },
    { key = "party", n = "Party Frame", d = "Show or hide the party frame", c = "green", g = "group" },
}
ConsoleKeys.DEFS = DEFS
ConsoleKeys.COLORS = COLORS

-------------------------------------------------------------------------------
-- Which keys have something to show (see HIDING above)
-------------------------------------------------------------------------------

local function Filled(t) return type(t) == "table" and next(t) ~= nil end

local function HasDrawnProc(p)
    if type(p.procs) ~= "table" then return false end
    for _, spec in pairs(p.procs) do
        if type(spec) == "table" and spec.side ~= nil then return true end
    end
    return false
end

-- piece key -> function(profile) (profile is a table). A key with no rule always shows.
local NEEDS = {
    shard = function(p) return type(p.resource) == "table" and p.resource.shards ~= nil and p.resource.shards ~= false end,
    prc = HasDrawnProc,
    next = function(p) return Filled(p.rotation) end,
    buff = function(p) return Filled(p.selfBuffs) end,
}

-- True when the key for `piece` has something to show for `profile` (nil: no profile).
function ConsoleKeys.KeyShown(piece, profile)
    local need = NEEDS[piece]
    if not need then return true end
    if type(profile) ~= "table" then return false end
    return need(profile) and true or false
end

local function Profile()
    local Hud = FS.Hud
    if type(Hud) ~= "table" or type(Hud.GetProfile) ~= "function" then return nil end
    local ok, p = pcall(Hud.GetProfile)
    if ok and type(p) == "table" then return p end
    return nil
end

local function Text(v) return type(v) == "string" and v ~= "" and v or nil end

-- Title and description of the key for `piece` under `profile`. Only the dot key reads the profile: its
-- `dotLabel` fields replace the DEFS text one by one. Plain strings only (a profile is addon data).
function ConsoleKeys.Label(piece, profile)
    for _, def in ipairs(DEFS) do
        if def.key == piece then
            local label = piece == "dot" and type(profile) == "table" and type(profile.dotLabel) == "table"
                and profile.dotLabel or nil
            if not label then return def.n, def.d end
            return Text(label.n) or def.n, Text(label.d) or def.d
        end
    end
end

-------------------------------------------------------------------------------
-- State
-------------------------------------------------------------------------------

local keys = {}          -- index (1 to 8) -> key record
local byPiece = {}       -- piece key -> key record
local host               -- plain frame under the tab that holds every key
local built = false
local pendingSeat = false
local seatedSig            -- shown-set signature of the last applied layout ("1" shown, "0" hidden, per DEFS)
local shownCount = 0
local inactive = false       -- the Gunsight is switched off (or waiting to come back): the HUD keys are hidden
local gunsightReady = false  -- the Gunsight's OnReady has run: its state at login is final
local loginEnabled = false   -- Gunsight.IsEnabled() as of login, never re-read (see WHAT EXISTS IS READ ONCE)

local function Scale()
    if FS.Layout and FS.Layout.Scale then return FS.Layout.Scale() end
    return 1
end

local function Now() return GetTime() * 1000 end

local function ReducedMotion()
    return type(ForeverSTUwaveDB) == "table" and ForeverSTUwaveDB.reducedMotion == true
end

local function GetFx()
    return FS.ChevronCastBar and FS.ChevronCastBar.Fx
end

local function Mix(a, b, t)
    return a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t
end

-------------------------------------------------------------------------------
-- Static look (`.cdeck.bm .dkey`)
-------------------------------------------------------------------------------

-- Precedence in the mockup: pressed > hover > lit > rest (the hover and pressed rules come after the
-- lit rule at the same specificity). `lit` is on, or the outage that holds the on look.
local function Look(k)
    local lit = k.phase ~= "off"
    local ga, gr, gg, gb   -- halo
    if k.down then
        gr, gg, gb, ga = COLORS.pink[1], COLORS.pink[2], COLORS.pink[3], 0.5
    elseif k.hover then
        gr, gg, gb, ga = COLORS.pink[1], COLORS.pink[2], COLORS.pink[3], 0.7
    else
        gr, gg, gb, ga = COLORS.cyan[1], COLORS.cyan[2], COLORS.cyan[3], lit and 0.34 or 0.18
    end
    k.glow:SetVertexColor(gr, gg, gb, ga)
    k.edge:SetVertexColor(COLORS.cyan[1], COLORS.cyan[2], COLORS.cyan[3], lit and 0.95 or 0.45)
    local wash = k.down and 0.3 or (k.hover and 0.15 or 0)
    k.wash:SetVertexColor(COLORS.pink[1], COLORS.pink[2], COLORS.pink[3], wash)
    local c = k.color
    if lit then
        local r, g, b = Mix(c, WHITE, 0.12)   -- color-mix(c 88%, white)
        k.glyph:SetVertexColor(r, g, b, 1)
        k.glyphGlow:SetVertexColor(r, g, b, 0.5)
        k.led:SetVertexColor(c[1], c[2], c[3], 1)
    else
        k.glyph:SetVertexColor(GLYPH_OFF[1], GLYPH_OFF[2], GLYPH_OFF[3], 1)
        k.glyphGlow:SetVertexColor(GLYPH_OFF[1], GLYPH_OFF[2], GLYPH_OFF[3], 0)
        k.led:SetVertexColor(c[1], c[2], c[3], 0)
    end
end

-------------------------------------------------------------------------------
-- Ring animation (the mockup's ringUpdate, on the shared Fx motion)
-------------------------------------------------------------------------------

local driver
local driverRunning = false
local active = {}        -- key record -> true while its ring is live

local function SetRingShown(k, shown)
    if k.ringShown == shown then return end
    k.ringShown = shown
    if shown then k.ring:Show() else k.ring:Hide() end
end

local function ResetSegs(k, litSince)
    for i = 1, RING_N do k.segs[i].litSince = litSince end
end

-- One frame of one ring. Returns true while the ring still needs frames.
local function RingUpdate(k, Fx, now)
    local anim, intr = false, nil
    local lit = k.phase ~= "off"
    if k.phase == "outage" then
        local uT = (now - k.t0) / Fx.INTR_MS
        if uT >= 1 then
            k.phase = "off"
            lit = false
            Look(k)
        else
            if uT < 0 then uT = 0 end
            intr = Fx.phaseOf(uT)
            anim = true
        end
    end
    local ctx = k.ctx
    local ip = Fx.intrParams(intr)
    ctx.lit, ctx.snap, ctx.intr, ctx.ip = lit, false, intr, ip
    ctx.level, ctx.fadeLit, ctx.extent = ip.level, 1, 1
    local ign = false
    for i = 1, RING_N do
        local look = Fx.segLook(k.pal, k.segs[i], now, ctx)
        if look.anim then anim = true; ign = true end
        if look.alpha > 0 then
            k.lr[i], k.lg[i], k.lb[i], k.la[i] = look.r, look.g, look.b, look.alpha
        else
            k.lr[i], k.lg[i], k.lb[i], k.la[i] = k.color[1], k.color[2], k.color[3], 0
        end
    end
    if intr or ign then k.rT = now end
    local u = 1 - (now - k.rT) / RING_FADE_MS
    if u < 0 then u = 0 elseif u > 1 then u = 1 end
    local ro = Fx.ease(u)
    SetRingShown(k, ro > 0)
    if ro > 0 then
        for i = 1, RING_N do
            -- the unlit arcs are the faint ring under the lit ones (stroke .14), the lit ones draw over it
            local a = k.la[i]
            if a < 0.14 then a = 0.14 end
            k.arcs[i]:SetVertexColor(k.lr[i], k.lg[i], k.lb[i], a * ro)
        end
    end
    -- the fade is still owed while ro > 0 and nothing animates
    if ro > 0 and (ro < 1 or not (intr or ign)) then anim = true end
    return anim
end

local function Tick()
    local Fx = GetFx()
    local now = Now()
    for k in pairs(active) do
        if not Fx or not RingUpdate(k, Fx, now) then
            active[k] = nil
            if not Fx then
                SetRingShown(k, false)
                if k.phase == "outage" then k.phase = "off"; Look(k) end
            end
        end
    end
    if next(active) == nil then
        driverRunning = false
        driver:SetScript("OnUpdate", nil)
    end
end

local function Activate(k)
    active[k] = true
    if not driverRunning then
        driverRunning = true
        driver:SetScript("OnUpdate", Tick)
    end
end

-- Puts key `k` into the on or off state. A visible key animates (ring ignite, outage); a hidden one,
-- reduced motion or a missing Fx snaps.
local function SetState(k, on, instant)
    local Fx = GetFx()
    local wanted = k.phase == "on"
    if instant or not Fx or ReducedMotion() or not k.btn:IsVisible() then
        k.phase = on and "on" or "off"
        ResetSegs(k, -1e9)
        active[k] = nil
        SetRingShown(k, false)
        k.rT = -1e9
        Look(k)
        return
    end
    if wanted == on then return end
    local now = Now()
    if on then
        k.phase = "on"
        ResetSegs(k, false)
    else
        k.phase = "outage"
    end
    k.t0 = now
    Look(k)
    Activate(k)
end

-------------------------------------------------------------------------------
-- Tooltip (Deck skin comes from Tooltip.lua; the lines are the mockup's name and description)
-------------------------------------------------------------------------------

local function ShowTip(k)
    local ok, err = pcall(function()
        local on = Switch.IsOn(k.key)
        local s = Scale()
        GameTooltip:SetOwner(k.btn, "ANCHOR_NONE")
        GameTooltip:ClearAllPoints()
        local slot = k.slot or (k.index - 1)
        -- The tab ends at the Console's right edge, so the last key's tooltip always opens leftward (a lone key
        -- is slot 0 and the last).
        if slot < 3 and slot < shownCount - 1 then
            GameTooltip:SetPoint("BOTTOMLEFT", k.btn, "TOPLEFT", 0, TIP_GAP * s)
        elseif slot >= shownCount - 2 then
            GameTooltip:SetPoint("BOTTOMRIGHT", k.btn, "TOPRIGHT", 0, TIP_GAP * s)
        else
            GameTooltip:SetPoint("BOTTOM", k.btn, "TOP", 0, TIP_GAP * s)
        end
        local sc = on and COLORS.cyan or MUTED
        local name, desc = ConsoleKeys.Label(k.key, Profile())
        GameTooltip:AddDoubleLine(name, on and "ON" or "OFF", 1, 1, 1, sc[1], sc[2], sc[3])
        GameTooltip:AddLine(desc, MUTED[1], MUTED[2], MUTED[3], true)
        GameTooltip:Show()
    end)
    if not ok then Degrade("tooltip", err) end
end

local function HideTip(k)
    if GameTooltip and GameTooltip.GetOwner and GameTooltip:GetOwner() == k.btn then GameTooltip:Hide() end
end

-------------------------------------------------------------------------------
-- Build and seat
-------------------------------------------------------------------------------

local function Cut2(art, path, layer, sub, inset, margin)
    local t = Theme.AddSliceTexture(art, path, nil, layer, sub, inset)
    Theme.ApplyNineSlice(t, margin)
    return t
end

local function BuildKey(i, def)
    local Fx = GetFx()
    local color = COLORS[def.c]
    local k = {
        index = i, def = def, key = def.key, color = color, phase = "off", t0 = 0, rT = -1e9,
        arcs = {}, segs = {}, lr = {}, lg = {}, lb = {}, la = {}, ringShown = true,
    }
    local btn = CreateFrame("Button", "FSConsoleKey" .. def.key, host)
    btn:RegisterForClicks("LeftButtonUp")
    k.btn = btn

    local art = CreateFrame("Frame", nil, btn)
    art:EnableMouse(false)
    art:SetSize(KEY_W, KEY_H)
    art:SetPoint("TOPLEFT", btn, "TOPLEFT", 0, 0)
    k.art = art

    local media = Theme.SLICE_CUT2_GLOW_TEXTURE
    local margin = Theme.SLICE_CUT_MARGIN or 6
    k.glow = Cut2(art, media, "BACKGROUND", -2, -(Theme.SLICE_CUT2_GLOW_PAD or 4), Theme.SLICE_CUT2_GLOW_MARGIN or 10)
    k.body = Cut2(art, Theme.SLICE_CUT2_BUTTON_TEXTURE, "BACKGROUND", -1, 0, margin)
    k.body:SetVertexColor(1, 1, 1, 1)
    k.wash = Cut2(art, Theme.SLICE_CUT2_FILL_TEXTURE, "ARTWORK", -1, 0, margin)
    k.wash:SetBlendMode("ADD")
    k.edge = Cut2(art, Theme.SLICE_CUT2_OUTLINE_TEXTURE, "ARTWORK", 1, 0, margin)

    local path = MEDIA .. "glyph_hud_" .. def.g .. ".tga"
    k.glyphGlow = art:CreateTexture(nil, "ARTWORK", nil, 2)
    k.glyphGlow:SetTexture(path)
    k.glyphGlow:SetBlendMode("ADD")
    k.glyphGlow:SetSize(GLYPH_S * GLYPH_GLOW_SCALE, GLYPH_S * GLYPH_GLOW_SCALE)
    k.glyphGlow:SetPoint("CENTER", art, "TOPLEFT", GLYPH_X + GLYPH_S / 2, -(GLYPH_Y + GLYPH_S / 2))
    k.glyph = art:CreateTexture(nil, "ARTWORK", nil, 3)
    k.glyph:SetTexture(path)
    k.glyph:SetSize(GLYPH_S, GLYPH_S)
    k.glyph:SetPoint("TOPLEFT", art, "TOPLEFT", GLYPH_X, -GLYPH_Y)

    k.led = art:CreateTexture(nil, "ARTWORK", nil, 3)
    k.led:SetColorTexture(1, 1, 1, 1)
    k.led:SetSize(LED_W, LED_H)
    k.led:SetPoint("TOPLEFT", art, "TOPLEFT", LED_X, -LED_Y)

    -- the ring: sixteen arcs stacked on one anchor, centred on the key
    local ring = CreateFrame("Frame", nil, art)
    ring:EnableMouse(false)
    ring:SetAllPoints(art)
    k.ring = ring
    for n = 1, RING_N do
        local t = ring:CreateTexture(nil, "OVERLAY", nil, 1)
        t:SetTexture(MEDIA .. string.format("hud_key_ring_%02d.tga", n - 1))
        t:SetSize(RING_W, RING_H)
        t:SetPoint("CENTER", art, "TOPLEFT", KEY_W / 2, -KEY_H / 2)
        t:SetVertexColor(color[1], color[2], color[3], 0)
        k.arcs[n] = t
    end
    ring:Hide()
    k.ringShown = false

    if Fx then
        k.pal = Fx.MakePalette({ base = { color[1], color[2], color[3] } })
        k.ctx = Fx.NewContext()
        for n = 1, RING_N do
            local seg = Fx.NewSeg(9000 + (i - 1) * 977 + (n - 1) * 131)   -- the mockup's ring seeds
            seg.a = (n - 1) / RING_N
            seg.litSince = -1e9
            k.segs[n] = seg
        end
    end

    btn:SetScript("OnEnter", function() k.hover = true; Look(k); ShowTip(k) end)
    btn:SetScript("OnLeave", function() k.hover = false; k.down = false; Look(k); HideTip(k) end)
    btn:SetScript("OnMouseDown", function() k.down = true; Look(k) end)
    btn:SetScript("OnMouseUp", function() k.down = false; Look(k) end)
    btn:SetScript("OnHide", function() k.hover = false; k.down = false; Look(k); HideTip(k) end)
    btn:Hide()   -- ApplyLayout shows the keys that have something to show
    btn:SetScript("OnClick", function()
        Switch.Set(k.key, not Switch.IsOn(k.key))
        if k.hover then ShowTip(k) end   -- the ON / OFF word follows the click
    end)
    return k
end

-- The HUD keys belong to the Gunsight HUD; the party key is the party frames' own switch.
local function IsHudKey(piece) return piece ~= "party" end

-- True when the key for `piece` is drawn right now. The party key always is: the party frames do not depend on
-- the HUD, so its switch stays on the Console with the HUD off (never built, or switched off), where it is the
-- one key left. A HUD key is drawn when the Gunsight was on at login, is not inactive now, and has something to
-- show for the class. The Console's tab is sized for the number of keys this lets through; with the party key
-- always among them the tab never goes away.
local function KeyDrawn(piece, profile)
    if not IsHudKey(piece) then return true end
    return loginEnabled and not inactive and ConsoleKeys.KeyShown(piece, profile)
end

-- The drawn set under the current profile: "1" or "0" per DEFS entry.
local function ShownSignature()
    local p = Profile()
    local out = {}
    for i, def in ipairs(DEFS) do out[i] = KeyDrawn(def.key, p) and "1" or "0" end
    return table.concat(out)
end

-- Gives the drawn keys consecutive slots, sizes the Console's tab for them, then seats, shows and hides. Out of
-- combat only (Reseat checks). The hit areas grow half a gap to each side, so they tile the even pitch.
local function ApplyLayout()
    local sig = ShownSignature()
    local slot = 0
    for i, k in ipairs(keys) do
        k.shown = sig:sub(i, i) == "1"
        if k.shown then k.slot = slot; slot = slot + 1 else k.slot = nil end
    end
    shownCount = slot
    Console.SetKeyCount(slot)   -- the party key is always drawn, so never 0 (the Console would draw no tab)
    local s = Scale()
    local half = Console.KEY.GAP / 2
    for _, k in ipairs(keys) do
        if k.shown then
            local r = Console.KeyRect(k.slot, s)
            k.btn:ClearAllPoints()
            k.btn:SetPoint("TOPLEFT", Console.tab, "TOPLEFT", r.x, -r.y)
            k.btn:SetSize(r.w, r.h)
            k.art:SetScale(s)
            if k.btn.SetHitRectInsets then
                k.btn:SetHitRectInsets(-half * s, -half * s, -HIT_V * s, -HIT_V * s)
            end
            k.btn:Show()
        else
            k.btn:Hide()
        end
    end
    seatedSig = sig
end

local function Reseat()
    if not built then return end   -- until the keys exist (the Console's tab, the Gunsight's state) the Console keeps its count
    if InCombatLockdown() then
        pendingSeat = true
        return
    end
    pendingSeat = false
    local ok, err = pcall(ApplyLayout)
    if not ok then Degrade("seat", err) end
end

-- Re-reads the profile and applies a layout only when the shown set changed (or a re-seat is owed).
-- The cheap check the visibility hooks run.
local function Refresh()
    if not built then return end
    if pendingSeat or ShownSignature() ~= seatedSig then Reseat() end
end

-- Builds the keys once the Gunsight state is final AND the Console has made its tab. All eight are built whatever
-- the Gunsight is doing (the party key is wanted with the HUD off), and KeyDrawn decides which of them are drawn.
local function Ensure()
    if built or not gunsightReady or not Console.tab then return end
    local ok, err = pcall(function()
        host = CreateFrame("Frame", nil, Console.tab)
        host:SetAllPoints(Console.tab)
        host:EnableMouse(false)
        driver = CreateFrame("Frame")
        for i, def in ipairs(DEFS) do
            local k = BuildKey(i, def)
            keys[i] = k
            byPiece[def.key] = k
        end
        built = true
        Reseat()
        for _, k in ipairs(keys) do SetState(k, Switch.IsOn(k.key), true) end
    end)
    if not ok then
        Degrade("build", err)
        built = false
    end
end

-------------------------------------------------------------------------------
-- Wiring
-------------------------------------------------------------------------------

Switch.OnChanged(function(piece, on)
    local k = byPiece[piece]
    if k then SetState(k, on and true or false, false) end
end)

-- The master switch, live (see WHAT EXISTS IS READ ONCE, THE SWITCH IS LIVE). Only fires for a Gunsight that was built.
-- The HUD keys stand down at once (plain frames, so also in combat) and the layout catches up when it can; the
-- party key is left alone. Coming back, a key the last layout still drew shows again at once (a HUD that went off
-- in combat comes back in the same fight); after an off out of combat the Gunsight itself returns only at regen,
-- and the layout with it.
Gunsight.OnActiveChanged(function(active)
    inactive = not active
    if built then
        for _, k in ipairs(keys) do
            if IsHudKey(k.key) then
                if inactive then
                    k.btn:Hide()   -- its OnHide clears hover, press and the tooltip (no OnLeave comes for a hidden key)
                elseif k.shown then
                    k.btn:Show()
                end
            end
        end
        Reseat()
    end
end)

-- (The Console may already have drawn once with its default full count when this runs, because the geometry can
-- arrive before the Gunsight is ready. Both land in the one login event dispatch and the count changes below in
-- the same pass, so the default tab is replaced before anything is rendered. The count is not seeded earlier on
-- purpose: this is the moment Gunsight.IsEnabled() is final (before the Gunsight's init it reads its default,
-- true), and reading it sooner would depend on the order of two files' event handlers.)
Gunsight.OnReady(function()
    gunsightReady = true
    loginEnabled = Gunsight.IsEnabled() and true or false
    Ensure()
end)

-- The Console's own geometry callback runs first (it subscribed earlier), so the tab is seated.
FS.ActionBars.OnGeometry(function()
    Ensure()
    Reseat()
end)

if FS.Layout and FS.Layout.OnRescale then FS.Layout.OnRescale(Reseat) end

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:RegisterEvent("PLAYER_ENTERING_WORLD")
events:SetScript("OnEvent", function()
    Ensure()
    Refresh()
end)

-- Test and diagnostic surface.
ConsoleKeys.keys = keys
function ConsoleKeys.IsBuilt() return built end
function ConsoleKeys.ShownCount() return shownCount end
ConsoleKeys.Refresh = Refresh
function ConsoleKeys.IsAnimating() return driverRunning end
