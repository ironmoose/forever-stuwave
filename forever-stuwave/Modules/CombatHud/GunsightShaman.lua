-- Forever STUwave: Gunsight Class Module for the Shaman, first slice: the IMBUE and SHIELD self reminder chips.
--
-- Registers the module "class" for SHAMAN with FS.GunsightAreas, which hosts it in the upper or lower area and calls
-- seat(rect) again on every rescale. This is Concept A, Totem Poles, of mockups/gunsight-class-module-shaman-2026-10-08.html
-- (poleMod, reminders and mchip): two 14 px chips in the footer of the area. The totem poles, the shock trace and the Fire
-- Nova ring are not drawn yet; they get their own sections below the chips. Offsets are image px from the area rect's
-- corner; gunsightshaman-harness.py parses them back out of the mockup.
--
-- IMBUE: weapon imbue and its time left. GetWeaponEnchantInfo gives the time in ms and (maybe) the enchant id of BOTH
-- hands, read every time. Imbues last 60 minutes, so the expiry is stored from every plain read and in combat, where
-- the read may be secret, the chip keeps counting down from it. The chip shows the enchanted hand with the LEAST time
-- left. Dual wield rule: when exactly one hand is enchanted and the other holds a weapon (not a shield or a held-in-off-
-- hand frill) and the Shaman knows an imbue, the chip is amber IMBUE until that hand has one too.
-- Which imbue it is: the enchant ids are NOT known on Forever (the Classic ids are listed in IMBUES only as a reference),
-- so an id names an imbue only after our own UNIT_SPELLCAST_SUCCEEDED confirmed it (a cast teaches the id it produced),
-- else the one imbue the Shaman knows, else IM.
-- SHIELD: Lightning Shield and its orb count, from the FS.PlayerAuras snapshot Buffs.lua keeps (plain values, frozen in
-- combat), so no aura API is read here. In combat the last live answer is an estimate (a "~" before the count) that
-- is believed for at most the shield's ten minutes. A Water Shield on the Shaman hides the chip (it is not missing).
-- A spell the Shaman has not learned draws no chip, so there is no nagging "missing".

local _, FS = ...

local Gunsight = FS.Gunsight
local Areas = FS.GunsightAreas
if not (Gunsight and Gunsight.ui and Gunsight.Point and Gunsight.G) then return end
if not (Areas and Areas.RegisterModule) then return end

local ui, Point = Gunsight.ui, Gunsight.Point

local M = {
    DY = 100,                                   -- the footer line, image px below the area rect's top
    DX = { imbue = 73, shield = 129 },          -- chip left edges, image px from the area rect's left
    CHIP = 14, CHAMFER = 3, GLOW_PAD = 3,       -- chip box, its cut corner, the glow's reach
    AB_PX = 9, AB_DX = 7, AB_BASE = 10.5,       -- the code inside the chip: centre x, baseline
    TXT_PX = 10, TXT_DX = 18, TXT_BASE = 10.5,  -- the time, orb count or word beside it: left edge, baseline
    UP_ALPHA = 0.85, GLOW_ALPHA = 0.35,
    TEXT_MID = 0.35,                            -- a line's centre sits this fraction of its size above the baseline
    TICK = 1,                                   -- seconds between reads: the 1 s tick is plenty for hour long imbues
    IMBUE_S = 3600, SHIELD_ORBS = 3,            -- a fresh imbue, a fresh Lightning Shield
    SHIELD_S = 600,                             -- Lightning Shield lasts ten minutes: no estimate is believed longer
    EXPIRING_S = 300,                           -- an imbue at five minutes or less turns to the expiring colour
    CAST_GRACE = 1.5, FRESH_S = 10,             -- seconds a cast stands before the weapon or the aura has caught up
    UPK = { 0xd9 / 255, 0xa5 / 255, 0x21 / 255 },       -- #d9a521 the chip gold
    FG = { 0xe9 / 255, 0xe2 / 255, 1 },                 -- #e9e2ff the soft foreground
    BG = { 13 / 255, 6 / 255, 32 / 255 },               -- #0d0620
    EXPIRING = { 0.925, 0.286, 0.600 },                 -- #EC4899, Buffs.lua's COLOR_BORDER_EXPIRING (aura time under two minutes)
    FILL_ON = 0.3, FILL_WARN = 0.22, FILL_HOLLOW_A = 0.7, STROKE_HOLLOW = 0.25,
}

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"

-- The four imbues, in the order they are learned. `base` is a rank id used only to read the spell's localized name.
-- The Classic era weapon enchant ids by rank, for reference only (NOT verified on Forever, so never used to name an
-- imbue; a cast teaches the real ones): Rockbiter 29 6 1 503 1663 683 1664, Flametongue 5 4 3 523 1665 1666,
-- Frostbrand 2 12 524 1667 1668, Windfury 283 284 525 1669 2636.
local IMBUES = {
    { code = "RB", name = "Rockbiter Weapon", base = 8017 },
    { code = "FT", name = "Flametongue Weapon", base = 8024 },
    { code = "FB", name = "Frostbrand Weapon", base = 8033 },
    { code = "WF", name = "Windfury Weapon", base = 8232 },
}
local SHIELD = { name = "Lightning Shield", base = 324 }
local WATER = { name = "Water Shield", base = 24398 }   -- hides the SHIELD chip; harmless where the spell does not exist
-- Item equip locations that are a weapon (a shield is INVTYPE_SHIELD, a held-in-off-hand frill INVTYPE_HOLDABLE).
local WEAPON_LOC = { INVTYPE_WEAPON = true, INVTYPE_WEAPONMAINHAND = true, INVTYPE_WEAPONOFFHAND = true, INVTYPE_2HWEAPON = true }

local logged = {}
local function LogOnce(key, msg)
    if logged[key] then return end
    logged[key] = true
    if FS.LogDegradeOnce then
        pcall(FS.LogDegradeOnce, "gunsightshaman_" .. key, "|cffff4488Forever STUwave|r: gunsight shaman module: " .. tostring(msg))
    end
end

local function IsSecret(v) return FS.IsSecret and FS.IsSecret(v) or false end
local function Theme() return FS.Theme end

local function PlainOf(v, kind)
    if IsSecret(v) or type(v) ~= kind then return nil end
    return v
end

local function PlayerClass()
    if type(UnitClass) ~= "function" then return nil end
    local ok, _, token = pcall(UnitClass, "player")
    if not ok or IsSecret(token) or type(token) ~= "string" then return nil end
    return token
end

-------------------------------------------------------------------------------
-- Spells: names, ranks, what the player has learned
-------------------------------------------------------------------------------

-- name, spellID of a spell given its name or id; plain values only.
local function SpellInfo(x)
    local modern = C_Spell and C_Spell.GetSpellInfo
    if modern then
        local ok, info = pcall(modern, x)
        if ok and not IsSecret(info) and type(info) == "table" then
            return PlainOf(info.name, "string"), PlainOf(info.spellID, "number")
        end
        return nil
    end
    if GetSpellInfo then
        local ok, name, _, _, _, _, _, id = pcall(GetSpellInfo, x)
        if ok then return PlainOf(name, "string"), PlainOf(id, "number") end
    end
    return nil
end

-- One spellbook API's answer: asked, yes. A missing API is not asked; one that raises or answers secret says no.
local function Ask(fn, id)
    if not fn then return false, false end
    local ok, answer = pcall(fn, id)
    return true, (ok and not IsSecret(answer) and answer) and true or false
end

-- true when the player knows this spell id, asking every spellbook API the client has (TotemBar's IsKnownSpellId); with
-- none present it is true. No table is built: this runs only when a negative answer is asked again.
local function IsKnownSpellId(id)
    local a1, y1 = Ask(IsPlayerSpell, id)
    local a2, y2 = Ask(IsSpellKnown, id)
    local a3, y3 = Ask(C_SpellBook and C_SpellBook.IsSpellKnown, id)
    if y1 or y2 or y3 then return true end
    return not (a1 or a2 or a3)
end

local nameById = {}
local function SpellNameById(id)
    local hit = nameById[id]
    if hit then return hit end
    local name = SpellInfo(id)
    if name then nameById[id] = name end
    return name
end

-- Whether a spell name is this definition's (English, or the client's own language through the rank id).
local function NameIs(name, def)
    if type(name) ~= "string" then return false end
    return name == def.name or name == SpellNameById(def.base)
end

local function SpellKnown(def)
    local _, id = SpellInfo(def.name)
    if id and IsKnownSpellId(id) then return true end
    return def.base ~= id and IsKnownSpellId(def.base) or false
end

-- Learned spells: an answer, yes or no, sticks until the spellbook changes (SPELLBOOK_EVENTS and each show drop it), so
-- an unlearned spell is not asked about at every tick.
local known = {}
local function RefreshKnown()
    for _, def in ipairs(IMBUES) do
        if known[def.code] == nil then known[def.code] = SpellKnown(def) end
    end
    if known.shield == nil then known.shield = SpellKnown(SHIELD) end
end

local function KnownImbues()
    local n, only = 0, nil
    for _, def in ipairs(IMBUES) do
        if known[def.code] then n = n + 1; only = def.code end
    end
    return n, only
end

local function BestKnownImbue()
    for i = #IMBUES, 1, -1 do
        if known[IMBUES[i].code] then return IMBUES[i].code end
    end
    return nil
end

-------------------------------------------------------------------------------
-- Imbue data
-------------------------------------------------------------------------------

local imbue = {
    present = nil,        -- true (an enchant is on a weapon), false (none), nil (never read)
    expiry = nil,         -- GetTime() when it falls off (the hand with the least time), from the last plain read or a cast
    code = nil,           -- the code of the enchant that is on now, when a cast or a taught id says so (not a guess)
    lastCode = nil,       -- the last code ever named, kept for the missing chip
    idMain = nil, idOff = nil,  -- the last plain enchant id of each hand
    cast = nil,           -- { code, prevMain, prevOff, at } of an imbue cast whose enchant id has not shown up yet
    learned = {},         -- enchant id -> code, taught by casts: the only thing that names an imbue by its id
    handMissing = false,  -- one hand is enchanted and the other holds a weapon with no enchant
    graceUntil = 0,       -- a cast stands against a "no enchant" read until then
}

local weaponLoc = {}      -- item id -> true when it is a weapon, false when it is not (shield, frill)

-- true when the item in this equipment slot is a weapon. Guarded: any refusal or secret answer says no.
local function HandHoldsWeapon(slot)
    if type(GetInventoryItemID) ~= "function" then return false end
    local ok, itemId = pcall(GetInventoryItemID, "player", slot)
    itemId = ok and PlainOf(itemId, "number") or nil
    if not itemId then return false end
    local isWeapon = weaponLoc[itemId]
    if isWeapon == nil then
        local info = (C_Item and C_Item.GetItemInfoInstant) or GetItemInfoInstant
        if type(info) ~= "function" then return false end
        local ok2, _, _, _, equipLoc = pcall(info, itemId)
        equipLoc = ok2 and PlainOf(equipLoc, "string") or nil
        if not equipLoc then return false end
        isWeapon = WEAPON_LOC[equipLoc] or false
        weaponLoc[itemId] = isWeapon
    end
    return isWeapon
end

-- Both hands, every time. "has", ms, pickId, mainId, offId, handMissing when an enchant is on a hand: ms and pickId are
-- those of the enchanted hand with the LEAST time left; handMissing when the other hand holds a weapon with none.
-- "none"; "unreadable" for a missing API, a throw or a secret answer (a secret flag is never tested, only IsSecret'd).
local function ReadWeapon()
    if type(GetWeaponEnchantInfo) ~= "function" then return "unreadable" end
    local ok, hasMain, msMain, _, idMain, hasOff, msOff, _, idOff = pcall(GetWeaponEnchantInfo)
    if not ok or IsSecret(hasMain) then return "unreadable" end
    local offSecret = IsSecret(hasOff)
    if not hasMain and offSecret then return "unreadable" end
    local mainOn = hasMain and true or false
    local offOn = (not offSecret and hasOff) and true or false
    if not (mainOn or offOn) then return "none" end
    local mMs, mId, oMs, oId
    if mainOn then mMs, mId = PlainOf(msMain, "number"), PlainOf(idMain, "number") end
    if offOn then oMs, oId = PlainOf(msOff, "number"), PlainOf(idOff, "number") end
    if mId and mId <= 0 then mId = nil end
    if oId and oId <= 0 then oId = nil end
    local ms, pick
    if mMs and oMs then
        if oMs < mMs then ms, pick = oMs, oId else ms, pick = mMs, mId end
    elseif mMs or oMs then
        if mMs then ms, pick = mMs, mId else ms, pick = oMs, oId end
    else
        pick = mId or oId
    end
    local missing = false
    if mainOn and not offOn and not offSecret then missing = HandHoldsWeapon(17)
    elseif offOn and not mainOn then missing = HandHoldsWeapon(16) end
    return "has", ms, pick, mId, oId, missing
end

-- Names the enchant that is on the weapon and says whether the weapon is still BEHIND a cast we made (it reports only
-- the enchants it had before, so its time is the old one's). A cast is believed until a hand shows an enchant id that
-- was not there before it: that id is taught as the cast's code (unless it is already known as a different imbue, which
-- then wins), or until the weapon never changed past FRESH_S (a recast of the same imbue). Two new ids at once cannot
-- be told apart and teach nothing. An id names an imbue only through `learned`; with no id readable the last name stays.
local function Identify(pick, mId, oId, now)
    local cast, behind = imbue.cast, false
    if cast then
        local newId, newCount = nil, 0
        if mId and mId ~= cast.prevMain and mId ~= cast.prevOff then newId, newCount = mId, newCount + 1 end
        if oId and oId ~= cast.prevMain and oId ~= cast.prevOff then newId, newCount = oId, newCount + 1 end
        if newCount == 1 then
            if not imbue.learned[newId] then imbue.learned[newId] = cast.code end
            imbue.cast = nil
        elseif newCount > 1 then
            imbue.cast = nil
        elseif (mId or oId) and now > cast.at + M.FRESH_S then
            imbue.cast = nil
        else
            behind = (mId or oId) ~= nil
        end
    end
    local code
    if imbue.cast then code = imbue.cast.code
    elseif pick then code = imbue.learned[pick]
    else code = imbue.code end
    imbue.code = code
    if code then imbue.lastCode = code end
    return behind
end

local function ReadImbue()
    local status, ms, pick, mId, oId, missing = ReadWeapon()
    local now = GetTime()
    if status == "has" then
        imbue.present = true
        imbue.graceUntil = 0
        local behind = Identify(pick, mId, oId, now)
        imbue.idMain, imbue.idOff = mId, oId
        -- a weapon still behind a cast reports the OLD enchants (their time, their missing hand): keep what the cast said
        if not behind then
            imbue.handMissing = missing
            if ms then imbue.expiry = now + ms / 1000 end
        end
    elseif status == "none" then
        if now < imbue.graceUntil then return end
        imbue.present, imbue.expiry, imbue.code, imbue.cast, imbue.handMissing = false, nil, nil, nil, false
        imbue.idMain, imbue.idOff = nil, nil
    end
end

local function OnImbueCast(def)
    local now = GetTime()
    imbue.present = true
    imbue.expiry = now + M.IMBUE_S
    imbue.graceUntil = now + M.CAST_GRACE
    imbue.code = def.code
    imbue.lastCode = def.code
    imbue.handMissing = false           -- the cast answers the reminder; the next read says whether it did
    imbue.cast = { code = def.code, prevMain = imbue.idMain, prevOff = imbue.idOff, at = now }
end

-------------------------------------------------------------------------------
-- Shield data
-------------------------------------------------------------------------------

local shield = {
    seen = nil,           -- the last live answer: "up", "missing" or nil (none yet)
    count = nil,          -- its orb count
    expiry = nil,         -- when it falls off, if the aura told
    readAt = nil,         -- GetTime() of the last live read that found it up (its ten minutes count from there)
    castAt = nil,         -- a cast the snapshot has not confirmed yet
    other = false,        -- the last live read found a Water Shield (the chip is not about to be missing)
    frozen = false,       -- the snapshot cannot refresh (combat)
    available = false,    -- FS.PlayerAuras exists
}

local function AuraIs(aura, def)
    if type(aura) ~= "table" then return false end
    if NameIs(aura.name, def) then return true end
    if aura.name == nil and type(aura.spellId) == "number" then return NameIs(SpellNameById(aura.spellId), def) end
    return false
end

local function ReadShield()
    local auras = FS.PlayerAuras
    if type(auras) ~= "table" or type(auras.Get) ~= "function" then
        shield.available = false
        return
    end
    shield.available = true
    local frozen = true
    if type(auras.IsFrozen) == "function" then
        local ok, answer = pcall(auras.IsFrozen)
        if ok and not IsSecret(answer) and answer == false then frozen = false end
    end
    shield.frozen = frozen
    if frozen then return end
    local ok, snap = pcall(auras.Get)
    local list = ok and type(snap) == "table" and snap.buffs or nil
    if type(list) ~= "table" then return end
    local now = GetTime()
    local other = false
    for i = 1, #list do
        local aura = list[i]
        if AuraIs(aura, SHIELD) then
            shield.seen = "up"
            shield.count = PlainOf(aura.count, "number")
            local expires = PlainOf(aura.expirationTime, "number")
            shield.expiry = expires and expires > 0 and expires or nil
            shield.readAt, shield.castAt, shield.other = now, nil, false
            return
        elseif AuraIs(aura, WATER) then
            other = true
        end
    end
    shield.other = other
    if shield.castAt and now < shield.castAt + M.CAST_GRACE then return end
    shield.seen, shield.count, shield.expiry, shield.readAt, shield.castAt = "missing", nil, nil, nil, nil
end

local function OnShieldCast()
    shield.castAt = GetTime()
end

-------------------------------------------------------------------------------
-- Chips
-------------------------------------------------------------------------------

local built, rect = false, nil
local frame, box, events
local chips = {}
local look                      -- mode -> colours, built once the theme exists
local elapsed = 0

local function Mix(a, b, t)
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
end

-- The mockup's mchip looks: on (quiet gold), warn (amber, a reminder), hollow (unknown) and, our one addition,
-- expiring (the aura row's expiring pink on the same chip as "on").
local function BuildLooks()
    local T = Theme()
    local white = T.COLOR_TEXT_WHITE
    local amber, muted = T.COLOR_AMBER, T.COLOR_MUTED
    local hollowStroke = Mix(muted, { 1, 1, 1 }, M.STROKE_HOLLOW)
    look = {
        on = { stroke = M.UPK, fill = Mix(M.BG, M.UPK, M.FILL_ON), fillA = 1, glow = true,
            code = white, text = M.FG, textA = M.UP_ALPHA },
        expiring = { stroke = M.EXPIRING, fill = Mix(M.BG, M.EXPIRING, M.FILL_ON), fillA = 1, glow = true,
            code = white, text = M.EXPIRING, textA = 1 },
        warn = { stroke = amber, fill = Mix(M.BG, amber, M.FILL_WARN), fillA = 1, glow = true,
            code = amber, text = amber, textA = 1 },
        hollow = { stroke = hollowStroke, fill = M.BG, fillA = M.FILL_HOLLOW_A, glow = false,
            code = hollowStroke, text = muted, textA = 1 },
    }
end

local function NewText(parent, justify)
    local fs = parent:CreateFontString(nil, "OVERLAY")
    fs:SetJustifyH(justify)
    return fs
end

-- The font is set (SetText on a FontString with none throws); the colour is kept for the next seat.
local function SetFont(fs, px, color)
    fs.fsColor = color
    Theme().ApplyMono(fs, ui(px), color)
end

local function BuildChip(key)
    local T = Theme()
    local ringPath, glowPath, c = MEDIA .. "slice_cut2_outline_c3.tga", MEDIA .. "slice_cut2_glow_c3.tga", M.CHAMFER
    if T.Cut2ButtonSet then
        local ok, ring, glow, used = pcall(T.Cut2ButtonSet, M.CHAMFER)
        if ok and type(ring) == "string" and type(glow) == "string" then ringPath, glowPath, c = ring, glow, used or c end
    end
    local chip = { key = key, frame = CreateFrame("Frame", nil, box) }
    chip.frame:SetAllPoints(box)
    chip.glow = chip.frame:CreateTexture(nil, "BACKGROUND", nil, 0)
    chip.glow:SetTexture(glowPath)
    T.ApplyNineSlice(chip.glow, (T.SLICE_CUT2_GLOW_PAD or 4) + c)
    chip.glow:SetBlendMode("ADD")
    chip.fill = chip.frame:CreateTexture(nil, "BACKGROUND", nil, 1)
    chip.fill:SetTexture(MEDIA .. "slice_cut2_fill_c" .. c .. ".tga")
    T.ApplyNineSlice(chip.fill, c)
    chip.ring = chip.frame:CreateTexture(nil, "ARTWORK", nil, 0)
    chip.ring:SetTexture(ringPath)
    T.ApplyNineSlice(chip.ring, c)
    chip.code = NewText(chip.frame, "CENTER")
    chip.word = NewText(chip.frame, "LEFT")
    SetFont(chip.code, M.AB_PX, T.COLOR_TEXT_WHITE)
    SetFont(chip.word, M.TXT_PX, T.COLOR_TEXT_WHITE)
    chip.frame:Hide()
    return chip
end

local function SeatChip(chip)
    if not rect then return end
    local x, y = rect.x + M.DX[chip.key], rect.y + M.DY
    local size, pad = ui(M.CHIP), M.GLOW_PAD
    for _, tex in ipairs({ chip.fill, chip.ring }) do
        Point(tex, "TOPLEFT", x, y)
        tex:SetSize(size, size)
    end
    Point(chip.glow, "TOPLEFT", x - pad, y - pad)
    chip.glow:SetSize(ui(M.CHIP + 2 * pad), ui(M.CHIP + 2 * pad))
    SetFont(chip.code, M.AB_PX, chip.code.fsColor)
    Point(chip.code, "CENTER", x + M.AB_DX, y + M.AB_BASE - M.TEXT_MID * M.AB_PX)
    SetFont(chip.word, M.TXT_PX, chip.word.fsColor)
    Point(chip.word, "LEFT", x + M.TXT_DX, y + M.TXT_BASE - M.TEXT_MID * M.TXT_PX)
end

-- Writes only what changed: this runs every second.
local function PaintChip(chip, on, mode, code, text)
    if chip.on ~= on then
        chip.on = on
        chip.frame:SetShown(on)
    end
    if not on then return end
    if chip.mode ~= mode then
        chip.mode = mode
        local l = look[mode]
        chip.fill:SetVertexColor(l.fill[1], l.fill[2], l.fill[3], l.fillA)
        chip.ring:SetVertexColor(l.stroke[1], l.stroke[2], l.stroke[3], 1)
        chip.glow:SetVertexColor(l.stroke[1], l.stroke[2], l.stroke[3], M.GLOW_ALPHA)
        chip.glow:SetShown(l.glow)
        chip.code.fsColor = { l.code[1], l.code[2], l.code[3], 1 }
        chip.code:SetTextColor(l.code[1], l.code[2], l.code[3], 1)
        chip.word.fsColor = { l.text[1], l.text[2], l.text[3], l.textA }
        chip.word:SetTextColor(l.text[1], l.text[2], l.text[3], l.textA)
    end
    if chip.codeText ~= code then
        chip.codeText = code
        chip.code:SetText(code)
    end
    if chip.wordText ~= text then
        chip.wordText = text
        chip.word:SetText(text)
    end
end

-- 52 minutes read "52m", under a minute "45s".
local function FormatTime(remaining)
    if remaining >= 60 then return string.format("%dm", math.floor(remaining / 60)) end
    return string.format("%ds", math.max(0, math.floor(remaining)))
end

local function PaintImbue(now)
    local chip = chips.imbue
    local nKnown, onlyKnown = KnownImbues()
    local present = imbue.present
    if not (nKnown > 0 or present == true) then
        PaintChip(chip, false)
        return
    end
    local code = imbue.code
    local mode, text
    if present == nil or (present == true and not imbue.expiry) then
        mode, text = "hollow", "?"
    else
        local remaining = present and imbue.expiry - now or 0
        if remaining <= 0 or (imbue.handMissing and nKnown > 0) then
            mode, text = "warn", "IMBUE"
        else
            mode = remaining <= M.EXPIRING_S and "expiring" or "on"
            text = FormatTime(remaining)
        end
    end
    if mode == "warn" or mode == "hollow" then
        code = code or imbue.lastCode or BestKnownImbue()
    elseif not code and nKnown == 1 then
        code = onlyKnown                    -- the one imbue the Shaman knows is the honest guess
    end
    PaintChip(chip, true, mode, code or "IM", text)
end

local function PaintShield(now)
    local chip = chips.shield
    if not known.shield then
        PaintChip(chip, false)
        return
    end
    local count = shield.count
    local up = shield.seen == "up"
    local estimate
    local at = shield.castAt
    if at and (now < at + M.CAST_GRACE or (shield.frozen and now < at + M.SHIELD_S)) then
        up, estimate, count = true, true, M.SHIELD_ORBS
    elseif shield.frozen and up then
        estimate = true
        local ends = shield.expiry or (shield.readAt and shield.readAt + M.SHIELD_S)
        if ends and ends <= now then up = false end
    end
    if not up and shield.other then          -- a Water Shield instead: nothing to remind about
        PaintChip(chip, false)
        return
    end
    local mode, text
    if not shield.available and shield.seen == nil then
        mode, text = "hollow", "?"
    elseif shield.seen == nil and not up then
        mode, text = "hollow", "?"
    elseif up then
        mode = "on"
        text = (count and count >= 1) and tostring(math.floor(count)) or "ON"
        if estimate and count and count >= 1 then text = "~" .. text end
    else
        mode, text = "warn", "SHIELD"
    end
    PaintChip(chip, true, mode, "LS", text)
end

local function Paint()
    if not built then return end
    local now = GetTime()
    PaintImbue(now)
    PaintShield(now)
end

local function Guard(fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok then LogOnce("update", err) end
end

local function RefreshAll()
    if not built then return end
    RefreshKnown()
    ReadImbue()
    ReadShield()
    Paint()
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local function OnCast(spellId)
    local id = PlainOf(spellId, "number")
    if not id then return end
    local name = SpellNameById(id)
    if not name then return end
    for _, def in ipairs(IMBUES) do
        if NameIs(name, def) then
            OnImbueCast(def)
            ReadImbue()
            Paint()
            return
        end
    end
    if NameIs(name, SHIELD) then
        OnShieldCast()
        Paint()
    end
end

local SPELLBOOK_EVENTS = {
    SPELLS_CHANGED = true, PLAYER_LEVEL_UP = true, LEARNED_SPELL_IN_SKILL_LINE = true, LEARNED_SPELL_IN_TAB = true,
}

local function OnEvent(_, event, unit, _, spellId)
    if (event == "UNIT_INVENTORY_CHANGED" or event == "UNIT_AURA" or event == "UNIT_SPELLCAST_SUCCEEDED")
        and not IsSecret(unit) and unit ~= "player" then
        return
    end
    if event == "UNIT_AURA" then
        ReadShield()
        Paint()
    elseif event == "UNIT_SPELLCAST_SUCCEEDED" then
        OnCast(spellId)
    elseif SPELLBOOK_EVENTS[event] then
        known = {}
        RefreshAll()
    else
        RefreshKnown()
        ReadImbue()
        Paint()
    end
end

local function SetEvents(on)
    -- optional: a refusal is not worth a chat line (the tick covers it)
    local function reg(event, unitOnly, optional)
        if on then
            local ok, err
            if unitOnly then
                ok, err = pcall(events.RegisterUnitEvent, events, event, "player")
            else
                ok, err = pcall(events.RegisterEvent, events, event)
            end
            if not ok and not optional then LogOnce("event_" .. event, event .. " cannot be registered on this client (" .. tostring(err) .. ")") end
        else
            pcall(events.UnregisterEvent, events, event)
        end
    end
    reg("UNIT_INVENTORY_CHANGED", true)
    reg("PLAYER_EQUIPMENT_CHANGED")
    reg("UNIT_AURA", true)
    reg("UNIT_SPELLCAST_SUCCEEDED", true)
    for event in pairs(SPELLBOOK_EVENTS) do reg(event, false, true) end
    events:SetScript("OnEvent", on and function(...) Guard(OnEvent, ...) end or nil)
end

-------------------------------------------------------------------------------
-- The module
-------------------------------------------------------------------------------

local function SeatAll()
    if not built then return end
    for _, chip in pairs(chips) do SeatChip(chip) end
end

local function Build(host)
    frame = CreateFrame("Frame", nil, host)
    frame:SetAllPoints(host)
    events = CreateFrame("Frame", nil, frame)
    built = false
    if PlayerClass() ~= "SHAMAN" then return frame end
    box = CreateFrame("Frame", nil, frame)
    box:SetAllPoints(frame)
    BuildLooks()
    chips.imbue, chips.shield = BuildChip("imbue"), BuildChip("shield")
    built = true
    SeatAll()
    return frame
end

local function Seat(r)
    if type(r) ~= "table" or type(r.x) ~= "number" or type(r.y) ~= "number" then return end
    rect = { x = r.x, y = r.y }
    local ok, err = pcall(SeatAll)
    if not ok then LogOnce("seat", err) end
end

local function OnShow()
    if not built then return end
    SetEvents(true)
    known = {}                              -- the spellbook may have changed while hidden
    elapsed = 0
    frame:SetScript("OnUpdate", function(_, dt)
        elapsed = elapsed + dt
        if elapsed < M.TICK then return end
        elapsed = 0
        Guard(RefreshAll)
    end)
    Guard(RefreshAll)
end

local function OnHide()
    if not built then return end
    SetEvents(false)
    frame:SetScript("OnUpdate", nil)
end

local ok, result = pcall(Areas.RegisterModule, "class", {
    classes = { "SHAMAN" },
    build = Build, seat = Seat, onShow = OnShow, onHide = OnHide,
})
if not ok or not result then LogOnce("register", "FS.GunsightAreas.RegisterModule refused the class module (" .. tostring(result) .. ")") end
