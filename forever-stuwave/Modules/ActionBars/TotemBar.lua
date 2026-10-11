-- Forever STUwave: Shaman totem tab
--
-- A Shaman shoulder on the Console chassis (ClassShoulder.lua, 6 columns x 1 row, 264 x 49 design px), built the
-- way SealBar.lua builds the Paladin's: plain SecureActionButtonTemplate buttons on a separate protected host,
-- attributes written directly from Lua out of combat, no secure snippet, no state driver (they do not run on this
-- client). Ghost Wolf stays on the stance bar: this tab never takes forms away from it.
--
--   * SIX buttons, FSTotemButton1..6, built ONCE, in a fixed order that is the saved keybind order (append
--     only): 1 Fire, 2 Earth, 3 Water, 4 Air, 5 Set drop, 6 Recall. CLICK FSTotemButtonN:LeftButton is declared
--     in Bindings.xml and Quick Keybind mode binds it.
--   * An ELEMENT button shows the picked totem's own spell icon, an element coloured underline and the element's
--     pole crown (mockups/gunsight-class-module-shaman-2026-10-08.html, Concept A) as a small badge. Right click
--     dismisses the totem through the secure "destroytotem" type (type2, totem-slot2 = the element's totem slot:
--     FIRE 1, EARTH 2, WATER 3, AIR 4). LEFT click drops the picked totem, in one of two modes decided at sync
--     time, per element:
--       ACTION mode: the multi-cast bar is usable (C_ActionBar.GetMultiCastBarIndex answers a plain number and
--       GetMultiCastTotemSpells lists totems for the slot). type1 = "action" on the multi-cast action id
--       (bar - 1) * 12 + (set - 1) * 4 + slot, set 1. The slot holds the pick, so a pick made in combat
--       (SetMultiCastSpell) needs no attribute write, and the native Call of the Elements drops the same set.
--       SPELL mode: anything else. type1 = "spell" with the picked totem's NAME, written out of combat, so a
--       pick made in combat waits for PLAYER_REGEN_ENABLED.
--     Which one is live is a question to the client at sync time (every call pcall'd and secret-guarded); neither
--     the action id formula nor the combat behaviour of SetMultiCastSpell is verified in game.
--   * SET DROP is Call of the Elements (66842), with Call of the Ancestors (66843) on shift once known. RECALL is
--     Totemic Recall (36936). Both are plain type "spell" and locked until known.
--   * LOCKED: an element with no known totem, and a Set drop or Recall not yet learned, carry NO castable
--     attribute, show the dotted mold and their unlock level, and dim by alpha. They are never hidden: Show and
--     Hide on a secure button are refused in combat.
--   * PICKING: a small arrow tab on each element button, or an Alt-click, opens a plain frame (not secure, parented
--     to UIParent; nothing secure is its child or anchor target) listing the known totems. A click stores the
--     pick per character (ForeverSTUwaveDB.totemPicks[guid]) and, in action mode, calls SetMultiCastSpell. A pick
--     the client did not take (a protected call from tainted code in combat is dropped, not raised) is kept and
--     sent again at regen. The default pick is the first known totem. An Alt-click carries an empty alt-type1 so
--     it never also drops the totem.
--   * SWEEPS: every button carries the GCD swipe (spell cooldown duration object), element buttons also the live
--     totem sweep (GetTotemInfo times when plain, else the GetTotemDuration object, else left alone when secret).
--   * No `.bar` field and no attribute that makes a button borrow its parent's (the "use parent" family) is ever
--     set on a button: Blizzard's SecureButton_GetModifiedAttribute reads both during a secure click, and an addon
--     written value there taints the click. Every button carries explicit attributes (action / spell / totem-slot).
--   * SetAttribute, Show, Hide, SetPoint and SetSize on a secure button (or its host) are refused in combat.
--     Everything that does any of them runs out of combat only; combat sets `pendingSync` and
--     PLAYER_REGEN_ENABLED replays it. Textures, swipes, the picker and a SetMultiCastSpell pick follow in combat.
--   * SEAT: TotemBar.HostPoint / TotemBar.SlotPoint, answered by the class shoulder while it stands, with the
--     same fallback as SealBar (above the stance bar's seat).
--
-- Design reference only: ShamanForever (GPL-3) was read for what a totem bar does, no code was taken from it.
-- Loads after SealBar.lua. Nothing here is verified in game.

local _, FS = ...

local TotemBar = {}
FS.TotemBar = TotemBar

local MEDIA = "Interface\\AddOns\\forever-stuwave\\Media\\Textures\\"

local TB = {
    CLASS = "SHAMAN",
    -- the Paladin block's numbers (ClassShoulder.lua); this block is 6 x 1
    BTN = 38, GAP = 4.8, PAD = 6, PT = 6, PB = 5, COLS = 6,
    BORDER_ALPHA = 0.35,
    LOCKED_ALPHA = 0.4,
    MC_SET = 1,                 -- the multi-cast page Call of the Elements drops
    MAX_ENTRIES = 6,            -- picker rows (an element holds at most 5 totems by level 30)
    ENTRY_W = 168, ENTRY_H = 24, PICKER_PAD = 4, PICKER_RISE = 8,
    PICKER_IDLE = 0.6,          -- seconds with the mouse away before the picker closes itself
    -- Append only, never reorder: the index is the saved keybind.
    BUTTONS = {
        { key = "fire", title = "Fire", slot = 1, color = "ff5a3c", unlock = 10, glyph = "totem_fire",
          label = "Fire totem" },
        { key = "earth", title = "Earth", slot = 2, color = "a8e063", unlock = 4, glyph = "totem_earth",
          label = "Earth totem" },
        { key = "water", title = "Water", slot = 3, color = "4aa8ff", unlock = 20, glyph = "totem_water",
          label = "Water totem" },
        { key = "air", title = "Air", slot = 4, color = "e2d4ff", unlock = 30, glyph = "totem_air",
          label = "Air totem" },
        { key = "set", title = "Set drop", color = "22e0ff", unlock = 20, glyph = "totem_set",
          label = "Totem set drop",
          spells = { { 66842, "Call of the Elements" }, { 66843, "Call of the Ancestors" } } },
        { key = "recall", title = "Recall", color = "ffb648", unlock = 20, glyph = "totem_recall",
          label = "Totemic Recall", spells = { { 36936, "Totemic Recall" } } },
    },
    -- the totems of each element up to level 30, by English spell name (the first known one is the default
    -- pick); used when the multi-cast API does not list them
    TOTEMS = {
        fire = { "Searing Totem", "Frost Resistance Totem", "Magma Totem", "Flametongue Totem" },
        earth = { "Stoneskin Totem", "Earthbind Totem", "Stoneclaw Totem", "Strength of Earth Totem",
            "Tremor Totem" },
        water = { "Healing Stream Totem", "Poison Cleansing Totem", "Mana Spring Totem", "Fire Resistance Totem" },
        air = { "Grounding Totem", "Nature Resistance Totem" },
    },
    -- every attribute this tab writes, cleared together when a button locks
    ATTRS = { "type", "spell", "type1", "action1", "spell1", "type2", "totem-slot2", "alt-type1",
        "shift-type1", "shift-spell1" },
    EVENTS = { "SPELLS_CHANGED", "LEARNED_SPELL_IN_TAB", "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD" },
    -- state-only events: texture and Cooldown writes, legal in combat
    LIVE_EVENTS = { "SPELL_UPDATE_COOLDOWN", "PLAYER_TOTEM_UPDATE", "ACTIONBAR_SLOT_CHANGED" },
    -- not on every client; asked with a pcall
    OPTIONAL_EVENTS = { "UPDATE_MULTI_CAST_ACTIONBAR" },
    host = nil,
    list = {},          -- the six buttons, by index
    byKey = {},         -- and by key
    picker = nil,
    pending = {},       -- key -> spell id: a multi-cast pick the client has not taken yet
    built = false,
    owns = false,
    pendingSync = false,
    warned = {},
}

-- Binding labels for the commands Bindings.xml names; the client reads these globals for the key binding
-- screen, and for every class. BINDING_HEADER_FOREVERSTUWAVE is SealBar's.
for i, def in ipairs(TB.BUTTONS) do
    _G["BINDING_NAME_CLICK FSTotemButton" .. i .. ":LeftButton"] = def.label
end

local IsSecret = FS.IsSecret

local function Hex(hex)
    return {
        tonumber(hex:sub(1, 2), 16) / 255, tonumber(hex:sub(3, 4), 16) / 255,
        tonumber(hex:sub(5, 6), 16) / 255,
    }
end

local function Scale()
    return (FS.Layout and FS.Layout.Scale and FS.Layout.Scale()) or 1
end

-- One chat line per distinct problem, once per session (LogDegradeOnce does not dedupe).
local function WarnOnce(key, text)
    if TB.warned[key] then return end
    TB.warned[key] = true
    FS.LogDegradeOnce(key, "|cffff4488Forever STUwave|r: " .. text)
end

local function IsShaman()
    local ok, _, token = pcall(UnitClass, "player")
    if not ok or IsSecret(token) then return false end
    return token == TB.CLASS
end

-- A value only when it is plain (not secret) and of the wanted type, else nil.
local function PlainValue(v, kind)
    if IsSecret(v) or v == nil or type(v) ~= kind then return nil end
    return v
end

-------------------------------------------------------------------------------
-- Spells
-------------------------------------------------------------------------------

-- spellID, iconID of a spell by name, plain values only; nil when the name does not resolve.
local function ResolveSpell(name)
    local modern = C_Spell and C_Spell.GetSpellInfo
    if modern then
        local ok, info = pcall(modern, name)
        if ok and not IsSecret(info) and type(info) == "table" then
            return PlainValue(info.spellID, "number"), PlainValue(info.iconID, "number")
        end
        return nil
    end
    if GetSpellInfo then
        local ok, _, _, icon, _, _, _, id = pcall(GetSpellInfo, name)
        if ok then return PlainValue(id, "number"), PlainValue(icon, "number") end
    end
    return nil
end

-- name, iconID of a spell by id, plain values only.
local function SpellById(id)
    local modern = C_Spell and C_Spell.GetSpellInfo
    if modern then
        local ok, info = pcall(modern, id)
        if ok and not IsSecret(info) and type(info) == "table" then
            return PlainValue(info.name, "string"), PlainValue(info.iconID, "number")
        end
        return nil
    end
    if GetSpellInfo then
        local ok, name, _, icon = pcall(GetSpellInfo, id)
        if ok then return PlainValue(name, "string"), PlainValue(icon, "number") end
    end
    return nil
end

-- true when the player knows this spell id, asking every spellbook API the client has (SealBar's
-- IsKnownSpellId). An API that raises or answers secret counts as "no" and is asked again at the next event.
-- With none of them present the id already resolved, which in this spellbook API means known.
local function IsKnownSpellId(id)
    local fns = { IsPlayerSpell, IsSpellKnown, C_SpellBook and C_SpellBook.IsSpellKnown }
    local asked = false
    for i = 1, 3 do
        local fn = fns[i]
        if fn then
            asked = true
            local ok, answer = pcall(fn, id)
            if ok and not IsSecret(answer) and answer then return true end
        end
    end
    return not asked
end

-------------------------------------------------------------------------------
-- The multi-cast bar (ACTION mode) and the known totems
-------------------------------------------------------------------------------

-- The multi-cast page, or nil when the bar is not usable (no API, it raised, it answered secret or nonsense).
local function MultiCastBar()
    local api = C_ActionBar and C_ActionBar.GetMultiCastBarIndex
    if not (api and GetMultiCastTotemSpells and SetMultiCastSpell) then return nil end
    local ok, bar = pcall(api)
    bar = ok and PlainValue(bar, "number") or nil
    if bar and bar >= 1 then return bar end
    return nil
end

-- The action id of an element's multi-cast slot: (bar - 1) * 12 + (set - 1) * 4 + slot.
local function ActionId(bar, slot)
    return (bar - 1) * 12 + (TB.MC_SET - 1) * 4 + slot
end

-- The known totems the multi-cast API lists for a totem slot, as entries { id, name, icon }; nil when it lists
-- none or any answer is unreadable.
local function MultiCastTotems(slot)
    if not GetMultiCastTotemSpells then return nil end
    local ok, packed = pcall(function() return { GetMultiCastTotemSpells(slot) } end)
    if not ok or type(packed) ~= "table" then return nil end
    local out = {}
    for i = 1, #packed do
        local id = packed[i]
        if IsSecret(id) then return nil end
        if type(id) == "number" and id > 0 then
            local name, icon = SpellById(id)
            out[#out + 1] = { id = id, name = name or "", icon = icon }
        end
    end
    if #out == 0 then return nil end
    return out
end

-- The known totems of an element from the spellbook, in the table's order.
local function BookTotems(def)
    local out = {}
    for _, name in ipairs(TB.TOTEMS[def.key] or {}) do
        local id, icon = ResolveSpell(name)
        if id and IsKnownSpellId(id) then out[#out + 1] = { id = id, name = name, icon = icon } end
    end
    return out
end

-- What the slot holds: (spell id or nil, readable). Readable and nil means the slot is plainly empty.
local function ReadSlot(actionId)
    if not GetActionInfo then return nil, false end
    local ok, kind, id = pcall(GetActionInfo, actionId)
    if not ok or IsSecret(kind) or IsSecret(id) then return nil, false end
    if kind == nil then return nil, true end
    if kind == "spell" and type(id) == "number" then return id, true end
    return nil, false
end

-- true when a SetMultiCastSpell call took. A protected call from tainted code in combat is dropped by the
-- client without an error, so the slot is read back; an unreadable slot counts as taken only out of combat.
local function SendPick(actionId, spellId)
    if not SetMultiCastSpell then return false end
    if not pcall(SetMultiCastSpell, actionId, spellId) then return false end
    local got, readable = ReadSlot(actionId)
    if readable and got == spellId then return true end
    return not InCombatLockdown()
end

-------------------------------------------------------------------------------
-- The saved pick, per character
-------------------------------------------------------------------------------

local function CharKey()
    if UnitGUID then
        local ok, guid = pcall(UnitGUID, "player")
        if ok and not IsSecret(guid) and type(guid) == "string" and guid ~= "" then return guid end
    end
    return "player"
end

-- { id, name } or nil
local function ReadPick(key)
    local db = _G.ForeverSTUwaveDB
    local all = type(db) == "table" and db.totemPicks
    local mine = type(all) == "table" and all[CharKey()]
    local pick = type(mine) == "table" and mine[key]
    if type(pick) == "table" then return pick end
end

local function WritePick(key, entry)
    if type(_G.ForeverSTUwaveDB) ~= "table" then _G.ForeverSTUwaveDB = {} end
    local db = _G.ForeverSTUwaveDB
    if type(db.totemPicks) ~= "table" then db.totemPicks = {} end
    local char = CharKey()
    if type(db.totemPicks[char]) ~= "table" then db.totemPicks[char] = {} end
    db.totemPicks[char][key] = { id = entry.id, name = entry.name }
end

local function Matching(list, stored)
    if type(stored) ~= "table" then return nil end
    for _, entry in ipairs(list) do
        if stored.id ~= nil and entry.id == stored.id then return entry end
    end
    for _, entry in ipairs(list) do
        if type(stored.name) == "string" and stored.name ~= "" and entry.name == stored.name then return entry end
    end
end

local function EntryById(list, id)
    for _, entry in ipairs(list) do
        if entry.id == id then return entry end
    end
end

-------------------------------------------------------------------------------
-- One element's state
-------------------------------------------------------------------------------

-- What an element button should be right now: { list, mode, actionId, pick }. `mode` is nil when no totem of the
-- element is known (the button locks). Reads only; writes nothing.
local function Evaluate(def)
    local multi = MultiCastTotems(def.slot)
    local bar = multi and MultiCastBar()
    local list, mode, actionId
    if bar then
        list, mode, actionId = multi, "action", ActionId(bar, def.slot)
    else
        list = BookTotems(def)
        if #list == 0 and multi then list = multi end
        mode = "spell"
        -- a spell attribute needs the totem's name
        local named = {}
        for _, entry in ipairs(list) do
            if entry.name ~= "" then named[#named + 1] = entry end
        end
        list = named
    end
    if #list == 0 then return { list = list } end
    local pick
    local queued = TB.pending[def.key]
    if queued then pick = EntryById(list, queued) end
    if not pick and mode == "action" then
        local held = ReadSlot(actionId)
        if held then pick = EntryById(list, held) end
    end
    pick = pick or Matching(list, ReadPick(def.key)) or list[1]
    return { list = list, mode = mode, actionId = actionId, pick = pick }
end

-------------------------------------------------------------------------------
-- Buttons
-------------------------------------------------------------------------------

local function UpdateHotkey(button)
    local hotkey = button.HotKey
    if not hotkey then return end
    local key = GetBindingKey(button.fsCommand)
    local text = FS.FrameHelpers.FormatBindingText(key)
    if text == "" then
        hotkey:SetText("")
        hotkey:Hide()
        if button.fsHotkeyPlate then button.fsHotkeyPlate:Hide() end
        return
    end
    hotkey:SetText(text)
    hotkey:Show()
    if button.fsHotkeyPlate then button.fsHotkeyPlate:Show() end
end

local function AnchorTooltip(owner)
    local tip = GameTooltip
    if _G.GameTooltip_SetDefaultAnchor then
        _G.GameTooltip_SetDefaultAnchor(tip, owner)
    else
        tip:SetOwner(owner, "ANCHOR_TOP")
    end
end

local function ShowTooltip(self)
    local tip = GameTooltip
    local def = self.fsDef
    if not (tip and def) then return end
    AnchorTooltip(self)
    local c = self.fsColor
    if self.fsLocked then
        tip:AddLine(def.title .. (def.slot and " totem" or ""), c[1], c[2], c[3])
        tip:AddLine("Opens at level " .. def.unlock .. ".", 0.62, 0.58, 0.77)
    elseif def.slot then
        local pick = self.fsPick
        local name = pick and pick.name ~= "" and pick.name or (def.title .. " totem")
        tip:AddLine(def.title .. " totem: " .. name, c[1], c[2], c[3])
        tip:AddLine("Left click: drop " .. name .. ". Right click: dismiss. Alt-click or arrow: change totem.",
            1, 1, 1, true)
    else
        if self.fsSpellID and tip.SetSpellByID then
            tip:SetSpellByID(self.fsSpellID)
        else
            tip:AddLine(def.title, c[1], c[2], c[3])
        end
        if self.fsShiftName then tip:AddLine("Shift-click: " .. self.fsShiftName, 0.62, 0.58, 0.77) end
    end
    tip:Show()
end

local function HideTooltip()
    GameTooltip:Hide()
end

-- Paints the border and glow from the button's tint; texture writes only.
local function PaintRing(button)
    local skin, color = button.fsSkin, button.fsColor
    if not (skin and color) then return end
    if skin.border and skin.border.ring then skin.border.ring:SetVertexColor(color[1], color[2], color[3], 1) end
    if skin.glow then skin.glow:SetVertexColor(color[1], color[2], color[3], TB.BORDER_ALPHA) end
end

-- The arrow tab (a plain Button on the element button) opens the picker; Alt-click on the button does too.
local function OnArrowClick(self)
    TotemBar.TogglePicker(self.fsKey)
end

local function OnButtonClick(self, mouseButton, down)
    if down or mouseButton ~= "LeftButton" or not self.fsDef.slot then return end
    if IsAltKeyDown and IsAltKeyDown() then TotemBar.TogglePicker(self.fsKey) end
end

-- Runs once per button, from Build and again on every re-seat. Everything that creates a region, hook or frame
-- is guarded so a throw partway is finished by the next Build.
local function StyleButton(button, size, scale)
    local def = button.fsDef
    button:SetSize(size, size)

    if not button.fsPlate then
        button.fsPlate = FS.Theme.AddCut2Texture(
            button, FS.Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)
    end
    FS.Theme.SkinCutButton(button, { borderColor = FS.Theme.COLOR_POWER, glowAlpha = TB.BORDER_ALPHA })

    if not button.fsHooked then
        button.fsHooked = true
        button:HookScript("OnEnter", ShowTooltip)
        button:HookScript("OnLeave", HideTooltip)
        button:HookScript("OnClick", OnButtonClick)
    end

    if not button.icon then
        local icon = button:CreateTexture(nil, "ARTWORK")
        icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        button.icon = icon
    end
    FS.FrameHelpers.SeatCutIcon(button)

    -- the GCD swipe: a full-icon Cooldown (black .64, no edge or bling), built once
    if not button.cooldown then
        button.cooldown = CreateFrame("Cooldown", nil, button, "CooldownFrameTemplate")
    end
    FS.FrameHelpers.SeatButtonCooldown(button)

    -- the live totem sweep: the element's colour over the face, the remaining time lit
    if def.slot and not button.totemCooldown then
        local sweep = CreateFrame("Cooldown", nil, button, "CooldownFrameTemplate")
        sweep:SetAllPoints(button.icon)
        if sweep.SetDrawEdge then sweep:SetDrawEdge(false) end
        if sweep.SetDrawBling then sweep:SetDrawBling(false) end
        if sweep.SetHideCountdownNumbers then sweep:SetHideCountdownNumbers(true) end
        if sweep.SetReverse then sweep:SetReverse(true) end
        if sweep.SetSwipeColor then sweep:SetSwipeColor(button.fsColor[1], button.fsColor[2], button.fsColor[3], 0.4) end
        button.totemCooldown = sweep
    end
    if button.cooldown.SetHideCountdownNumbers then button.cooldown:SetHideCountdownNumbers(true) end

    if not button.HotKey then
        button.HotKey = button:CreateFontString(nil, "OVERLAY")
    end
    local hotkey = button.HotKey
    local textHost = FS.FrameHelpers.SeatButtonText(button, hotkey)
    local top = button.totemCooldown or button.cooldown
    if textHost.GetFrameLevel and top.GetFrameLevel and top:GetFrameLevel() >= textHost:GetFrameLevel() then
        textHost:SetFrameLevel(top:GetFrameLevel() + 1)
    end
    hotkey:ClearAllPoints()
    hotkey:SetWidth(0)
    hotkey:SetPoint("TOPRIGHT", button, "TOPRIGHT", -3, -2)
    hotkey:SetJustifyH("RIGHT")
    hotkey:SetDrawLayer("OVERLAY", 4)
    FS.Theme.ApplyMono(hotkey, 10, FS.Theme.COLOR_TEXT_WHITE)

    if not button.fsHotkeyPlate then
        local plate = textHost:CreateTexture(nil, "OVERLAY", nil, 3)
        plate:SetColorTexture(0.024, 0.012, 0.071, 0.78)
        plate:SetPoint("TOPLEFT", hotkey, "TOPLEFT", -3, 2)
        plate:SetPoint("BOTTOMRIGHT", hotkey, "BOTTOMRIGHT", 3, -2)
        plate:Hide()
        button.fsHotkeyPlate = plate
    end

    -- the pole crown: a small badge on an element button, the whole face glyph on the set and recall buttons
    if not button.fsGlyph then
        local glyph = textHost:CreateTexture(nil, "OVERLAY", nil, 2)
        glyph:SetTexture(MEDIA .. def.glyph .. ".tga")
        glyph:SetVertexColor(button.fsColor[1], button.fsColor[2], button.fsColor[3], 0.95)
        button.fsGlyph = glyph
    end
    button.fsGlyph:ClearAllPoints()
    if def.slot then
        button.fsGlyph:SetSize(13 * scale, 13 * scale)
        button.fsGlyph:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", 4 * scale, 6 * scale)
    else
        button.fsGlyph:SetSize(26 * scale, 26 * scale)
        button.fsGlyph:SetPoint("CENTER", button, "CENTER", 0, 0)
    end

    -- the element underline
    if def.slot and not button.fsUnderline then
        local line = textHost:CreateTexture(nil, "OVERLAY", nil, 2)
        line:SetColorTexture(button.fsColor[1], button.fsColor[2], button.fsColor[3], 1)
        button.fsUnderline = line
    end
    if button.fsUnderline then
        button.fsUnderline:ClearAllPoints()
        button.fsUnderline:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", 4 * scale, 3 * scale)
        button.fsUnderline:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", -7 * scale, 3 * scale)
        button.fsUnderline:SetHeight(2 * scale)
    end

    -- a locked button: the dotted mold and its unlock level
    if not button.fsMold then
        local mold = button:CreateTexture(nil, "ARTWORK", nil, 1)
        mold:SetTexture(MEDIA .. "totem_mold.tga")
        local m = FS.Theme.COLOR_MUTED or { 0.62, 0.58, 0.77, 1 }
        mold:SetVertexColor(m[1], m[2], m[3], 0.9)
        mold:SetAllPoints(button)
        mold:Hide()
        button.fsMold = mold
    end
    if not button.fsLockText then
        local text = textHost:CreateFontString(nil, "OVERLAY")
        FS.Theme.ApplyMono(text, 11, FS.Theme.COLOR_MUTED or FS.Theme.COLOR_TEXT_WHITE)
        text:SetPoint("CENTER", button, "CENTER", 0, 0)
        text:SetText("L" .. def.unlock)
        text:Hide()
        button.fsLockText = text
    end

    -- the arrow tab: a plain Button, so a click on it never reaches the secure action underneath
    if def.slot and not button.fsArrow then
        local arrow = CreateFrame("Button", nil, button)
        arrow.fsKey = def.key
        arrow:RegisterForClicks("LeftButtonUp")
        local tex = arrow:CreateTexture(nil, "OVERLAY")
        tex:SetTexture(MEDIA .. "cast_chevron_up_fill.tga")
        tex:SetVertexColor(button.fsColor[1], button.fsColor[2], button.fsColor[3], 0.85)
        tex:SetAllPoints(arrow)
        arrow.fsTex = tex
        arrow:SetScript("OnClick", OnArrowClick)
        arrow:SetScript("OnEnter", function(self) self.fsTex:SetAlpha(1) end)
        arrow:SetScript("OnLeave", function(self) self.fsTex:SetAlpha(0.85) end)
        button.fsArrow = arrow
    end
    if button.fsArrow then
        button.fsArrow:SetSize(16 * scale, 8 * scale)
        button.fsArrow:ClearAllPoints()
        button.fsArrow:SetPoint("BOTTOM", button, "TOP", 0, -1 * scale)
        button.fsArrow:SetFrameLevel(textHost:GetFrameLevel() + 1)
    end
end

local function BuildButton(host, def, index)
    local button = CreateFrame("Button", "FSTotemButton" .. index, host, "SecureActionButtonTemplate")
    button.fsKey = def.key
    button.fsDef = def
    button.fsColor = Hex(def.color)
    button.fsCommand = "CLICK FSTotemButton" .. index .. ":LeftButton"
    button:RegisterForClicks("AnyUp", "AnyDown")
    FS.FrameHelpers.AttachQuickKeybind(button, button.fsCommand)
    return button
end

-------------------------------------------------------------------------------
-- Swipes (texture and Cooldown writes: legal in combat)
-------------------------------------------------------------------------------

-- The GCD swipe: the spell's cooldown as the duration object when the client has it, else the legacy start and
-- duration, read only when both are plain.
local function UpdateCooldown(button)
    local cooldown = button.cooldown
    if not cooldown then return end
    local id = button.fsSpellID
    if not id or button.fsLocked then
        cooldown:Clear()
        cooldown:Hide()
        return
    end
    local modern = C_Spell and C_Spell.GetSpellCooldownDuration
    if modern then
        local ok, obj = pcall(modern, id)
        if ok and not IsSecret(obj) and obj ~= nil then
            cooldown:SetCooldownFromDurationObject(obj)
        else
            cooldown:Clear()
        end
        cooldown:Show()
        return
    end
    local start, duration, enabled
    if C_Spell and C_Spell.GetSpellCooldown then
        local ok, info = pcall(C_Spell.GetSpellCooldown, id)
        if ok and type(info) == "table" and not IsSecret(info) then
            start, duration, enabled = info.startTime, info.duration, info.isEnabled
        end
    elseif GetSpellCooldown then
        local ok, s, d, e = pcall(GetSpellCooldown, id)
        if ok then start, duration, enabled = s, d, e end
    end
    if IsSecret(start) or IsSecret(duration) or IsSecret(enabled) then
        cooldown:Hide()
        return
    end
    if type(start) == "number" and type(duration) == "number" and duration > 0
        and enabled ~= false and enabled ~= 0 then
        cooldown:SetCooldown(start, duration)
        cooldown:Show()
    else
        cooldown:Clear()
        cooldown:Hide()
    end
end

-- The live totem sweep: GetTotemInfo's start and duration when both are plain, else the duration object, else
-- the sweep is left as it was (a secret answer in combat).
local function UpdateTotemSweep(button)
    local sweep, slot = button.totemCooldown, button.fsDef.slot
    if not (sweep and slot) then return end
    if button.fsLocked then
        sweep:Clear()
        sweep:Hide()
        return
    end
    if GetTotemInfo then
        local ok, _, _, start, duration = pcall(GetTotemInfo, slot)
        start, duration = ok and PlainValue(start, "number"), ok and PlainValue(duration, "number")
        if start and duration then
            if duration > 0 and start > 0 then
                sweep:SetCooldown(start, duration)
                sweep:Show()
            else
                sweep:Clear()
                sweep:Hide()
            end
            return
        end
    end
    if GetTotemDuration then
        local ok, obj = pcall(GetTotemDuration, slot)
        if ok and obj ~= nil and not IsSecret(obj) then
            sweep:SetCooldownFromDurationObject(obj)
            sweep:Show()
        end
    end
end

local function UpdateAllCooldowns()
    for _, button in ipairs(TB.list) do UpdateCooldown(button) end
end

local function UpdateAllSweeps()
    for _, button in ipairs(TB.list) do UpdateTotemSweep(button) end
end

local function UpdateAllHotkeys()
    for _, button in ipairs(TB.list) do
        if button:IsShown() then UpdateHotkey(button) end
    end
end

-------------------------------------------------------------------------------
-- Applying a state to a button
-------------------------------------------------------------------------------

-- Dims and strips a button that has nothing to cast: no castable attribute, the mold and the unlock level.
-- Attribute writes happen out of combat only (the caller); the rest is texture state.
local function Lock(button)
    if button.fsAttrKey ~= nil then
        for _, name in ipairs(TB.ATTRS) do button:SetAttribute(name, nil) end
        button.fsAttrKey = nil
    end
    button.fsLocked = true
    button.fsMode, button.fsPick, button.fsList, button.fsActionId = nil, nil, nil, nil
    button.fsSpellID, button.fsShiftName = nil, nil
    button:SetAlpha(TB.LOCKED_ALPHA)
    button.icon:Hide()
    button.fsMold:Show()
    button.fsLockText:Show()
    if button.fsUnderline then button.fsUnderline:Hide() end
    if button.fsArrow then
        button.fsArrow:EnableMouse(false)
        button.fsArrow:SetAlpha(0)
    end
    UpdateCooldown(button)
    UpdateTotemSweep(button)
end

local function Unlock(button)
    button.fsLocked = false
    button:SetAlpha(1)
    button.fsMold:Hide()
    button.fsLockText:Hide()
    if button.fsUnderline then button.fsUnderline:Show() end
    if button.fsArrow then
        button.fsArrow:EnableMouse(true)
        button.fsArrow:SetAlpha(1)
    end
end

-- Shows the picked totem on an element button: its icon and the id its swipe follows. Texture state.
local function ShowPick(button, pick)
    button.fsPick = pick
    button.fsSpellID = pick and pick.id or nil
    if pick and pick.icon then
        button.icon:SetTexture(pick.icon)
        button.icon:Show()
    elseif pick then
        button.icon:Show()
    end
    UpdateCooldown(button)
end

-- An element button from its evaluated state. Out of combat only (attributes).
local function ApplyElement(button, def)
    local st = Evaluate(def)
    if not st.pick then
        Lock(button)
        return
    end
    Unlock(button)
    local mode, pick = st.mode, st.pick
    button.fsMode, button.fsList, button.fsActionId = mode, st.list, st.actionId
    local key = mode .. "|" .. (mode == "action" and tostring(st.actionId) or pick.name) .. "|" .. def.slot
    if button.fsAttrKey ~= key then
        button:SetAttribute("type1", mode == "action" and "action" or "spell")
        button:SetAttribute("action1", mode == "action" and st.actionId or nil)
        button:SetAttribute("spell1", mode == "spell" and pick.name or nil)
        button:SetAttribute("type2", "destroytotem")
        button:SetAttribute("totem-slot2", def.slot)
        -- Alt-click opens the picker; an empty type means it does not also drop the totem
        button:SetAttribute("alt-type1", "")
        button.fsAttrKey = key
    end
    -- the multi-cast slot holds the pick: an empty one is filled with it, one the native bar filled is adopted
    if mode == "action" then
        local held, readable = ReadSlot(st.actionId)
        local fillKey = st.actionId .. ":" .. pick.id
        if readable and held == nil and button.fsFillKey ~= fillKey then
            if SendPick(st.actionId, pick.id) then button.fsFillKey = fillKey end
        end
    end
    WritePick(def.key, pick)
    ShowPick(button, pick)
end

-- Set drop and Recall: a plain spell button, locked until the first of its spells is known.
local function ApplyFixed(button, def)
    local names = {}
    for i, spell in ipairs(def.spells) do
        local id, fallback = spell[1], spell[2]
        if IsKnownSpellId(id) then
            names[i] = { id = id, name = SpellById(id) or fallback }
        end
    end
    local primary = names[1]
    if not primary then
        Lock(button)
        return
    end
    Unlock(button)
    local second = names[2]
    local key = primary.name .. "|" .. (second and second.name or "")
    if button.fsAttrKey ~= key then
        button:SetAttribute("type", "spell")
        button:SetAttribute("spell", primary.name)
        button:SetAttribute("shift-type1", second and "spell" or nil)
        button:SetAttribute("shift-spell1", second and second.name or nil)
        button.fsAttrKey = key
    end
    button.fsSpellID = primary.id
    button.fsShiftName = second and second.name or nil
    -- the glyph is the face; the icon is a dark plate behind it
    button.icon:SetColorTexture(0.04, 0.02, 0.09, 0.9)
    button.icon:Show()
    UpdateCooldown(button)
end

-- A pick the native bar made (or one we sent) moved the multi-cast slot: show it. Texture state and a saved
-- variable write, so it may run in combat. Never touches an attribute.
local function RefreshPicks()
    for _, button in ipairs(TB.list) do
        if button.fsMode == "action" and button.fsList and not button.fsLocked and not TB.pending[button.fsKey] then
            local held = ReadSlot(button.fsActionId)
            local entry = held and EntryById(button.fsList, held)
            if entry and entry ~= button.fsPick and (not button.fsPick or entry.id ~= button.fsPick.id) then
                WritePick(button.fsKey, entry)
                ShowPick(button, entry)
            end
        end
    end
end

-------------------------------------------------------------------------------
-- The seat
-------------------------------------------------------------------------------

local function ConsoleApi()
    local console = FS.Console
    if type(console) == "table" and type(console.IsDrawn) == "function" then return console end
end

-- Where the host stands: the SetPoint arguments, or nil for no seat (the host then hides). While the class
-- shoulder is up it supplies the seat; without it the host sits on the Console chassis top edge, or just above the
-- stance bar's seat with the Console not drawn, with the one time line SealBar logs for a missing Console.
function TotemBar.HostPoint()
    local shoulder = FS.ClassShoulder
    if shoulder and shoulder.HostPoint then
        local ok, point, rel, relPoint, x, y = pcall(shoulder.HostPoint)
        if ok and point then return point, rel, relPoint, x, y end
    end
    local s = Scale()
    local console = ConsoleApi()
    if console then
        if console.IsDrawn() and console.root then
            return "BOTTOMLEFT", console.root, "TOPLEFT", 36 * s, 0
        end
    else
        WarnOnce("totembar_noconsole", "no Console, the totem tab sits above the stance bar's seat")
    end
    local stance = _G.FSStanceBar
    if stance then return "BOTTOMLEFT", stance, "TOPLEFT", 0, 4 * s end
    return nil
end

-- Where button `col` (1..6) stands on the host.
function TotemBar.SlotPoint(col)
    local shoulder = FS.ClassShoulder
    if shoulder and shoulder.SlotPoint then
        local ok, point, rel, relPoint, x, y = pcall(shoulder.SlotPoint, TB.host, 1, col)
        if ok and point then return point, rel, relPoint, x, y end
    end
    local s, pitch = Scale(), TB.BTN + TB.GAP
    return "BOTTOMLEFT", TB.host, "BOTTOMLEFT", (TB.PAD + (col - 1) * pitch) * s, TB.PB * s
end

local function SeatButtons()
    local s = Scale()
    TB.host:SetSize((2 * TB.PAD + TB.COLS * TB.BTN + (TB.COLS - 1) * TB.GAP) * s, (TB.PT + TB.BTN + TB.PB) * s)
    for _, button in ipairs(TB.list) do StyleButton(button, TB.BTN * s, s) end
end

local function ApplyButtons()
    for i, button in ipairs(TB.list) do
        button:ClearAllPoints()
        button:SetPoint(TotemBar.SlotPoint(i))
        local def = button.fsDef
        if def.slot then ApplyElement(button, def) else ApplyFixed(button, def) end
        UpdateHotkey(button)
        PaintRing(button)
        UpdateTotemSweep(button)
        button:Show()
    end
end

local function SeatHost()
    local host = TB.host
    local point, rel, relPoint, x, y = TotemBar.HostPoint()
    if not point then
        host:Hide()
        return
    end
    host:ClearAllPoints()
    host:SetPoint(point, rel, relPoint, x, y)
    if rel.GetFrameLevel then host:SetFrameLevel(rel:GetFrameLevel() + 5) end
    host:Show()
end

-- Sends the multi-cast picks the client has not taken yet. Out of combat it is the retry; a pick the slot reads
-- back as taken is dropped from the queue.
local function ReplayPicks()
    for key, id in pairs(TB.pending) do
        local button = TB.byKey[key]
        if button and button.fsActionId then
            if SendPick(button.fsActionId, id) then TB.pending[key] = nil end
        else
            TB.pending[key] = nil
        end
    end
end

-- Every protected step in one place; combat parks it for PLAYER_REGEN_ENABLED. Each step is its own pcall so one
-- failure cannot stop the next.
local function Sync()
    if not TB.built then return end
    if InCombatLockdown() then
        TB.pendingSync = true
        return
    end
    TB.pendingSync = false
    for _, step in ipairs({ ReplayPicks, SeatButtons, ApplyButtons, SeatHost }) do
        local ok, err = pcall(step)
        if not ok then WarnOnce("totembar_sync", "totem tab update failed (" .. tostring(err) .. ")") end
    end
end
TotemBar.Sync = Sync

-- true once this tab is built for a Shaman: ClassShoulder.lua then stands the Shaman block.
function TotemBar.OwnsShoulder()
    return TB.owns
end

-------------------------------------------------------------------------------
-- The picker (plain frames: nothing secure is a child of it or anchored to it)
-------------------------------------------------------------------------------

local function ClosePicker()
    local picker = TB.picker
    if picker and picker:IsShown() then picker:Hide() end
end
TotemBar.ClosePicker = ClosePicker

local function EntryClick(self)
    local picker = TB.picker
    if not (picker and picker.fsKey and self.fsSpellID) then return end
    TotemBar.Pick(picker.fsKey, self.fsSpellID)
    ClosePicker()
end

local function EntryEnter(self)
    local tip = GameTooltip
    if not (tip and self.fsSpellID and tip.SetSpellByID) then return end
    tip:SetOwner(self, "ANCHOR_RIGHT")
    tip:SetSpellByID(self.fsSpellID)
    tip:Show()
end

-- Closes the picker once the mouse has been off it and its element for PICKER_IDLE seconds.
local function PickerIdle(self, elapsed)
    local owner = self.fsOwner
    local over = self:IsMouseOver() or (owner and (owner:IsMouseOver()
        or (owner.fsArrow and owner.fsArrow:IsMouseOver())))
    if over then
        self.fsIdle = 0
        return
    end
    self.fsIdle = (self.fsIdle or 0) + (elapsed or 0)
    if self.fsIdle >= TB.PICKER_IDLE then self:Hide() end
end

local function BuildPicker()
    if TB.picker then return TB.picker end
    local picker = CreateFrame("Frame", "FSTotemPicker", UIParent)
    picker:SetFrameStrata("DIALOG")
    picker:EnableMouse(true)
    picker:Hide()
    local fill = picker:CreateTexture(nil, "BACKGROUND")
    fill:SetColorTexture(0.024, 0.012, 0.071, 0.94)
    fill:SetAllPoints(picker)
    local line = picker:CreateTexture(nil, "BORDER")
    line:SetColorTexture(1, 1, 1, 0.9)
    line:SetPoint("TOPLEFT", picker, "TOPLEFT", 0, 0)
    line:SetPoint("TOPRIGHT", picker, "TOPRIGHT", 0, 0)
    line:SetHeight(2)
    picker.fsLine = line
    picker.fsEntries = {}
    for i = 1, TB.MAX_ENTRIES do
        local entry = CreateFrame("Button", nil, picker)
        entry:RegisterForClicks("LeftButtonUp")
        local icon = entry:CreateTexture(nil, "ARTWORK")
        icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
        entry.fsIcon = icon
        local label = entry:CreateFontString(nil, "OVERLAY")
        FS.Theme.ApplyMono(label, 11, FS.Theme.COLOR_TEXT_WHITE)
        label:SetJustifyH("LEFT")
        entry.fsLabel = label
        local mark = entry:CreateTexture(nil, "BACKGROUND")
        mark:SetColorTexture(1, 1, 1, 0.16)
        mark:SetAllPoints(entry)
        mark:Hide()
        entry.fsMark = mark
        entry:SetScript("OnClick", EntryClick)
        entry:SetScript("OnEnter", EntryEnter)
        entry:SetScript("OnLeave", HideTooltip)
        picker.fsEntries[i] = entry
    end
    picker:SetScript("OnShow", function(self)
        self.fsIdle = 0
        self:SetScript("OnUpdate", PickerIdle)
    end)
    picker:SetScript("OnHide", function(self)
        self:SetScript("OnUpdate", nil)
        self.fsOwner, self.fsKey = nil, nil
    end)
    if type(_G.UISpecialFrames) == "table" then table.insert(_G.UISpecialFrames, "FSTotemPicker") end
    TB.picker = picker
    return picker
end

function TotemBar.Picker()
    return TB.picker
end

-- Opens the picker above an element button with that element's known totems. Plain frames only, so it is legal
-- in combat. A locked element has nothing to list.
function TotemBar.OpenPicker(key)
    local button = TB.byKey[key]
    if not (button and button.fsDef.slot) or not TB.built then return end
    local st = Evaluate(button.fsDef)
    if #st.list == 0 then return end
    local picker = BuildPicker()
    local s = Scale()
    local current = st.pick
    local n = math.min(#st.list, TB.MAX_ENTRIES)
    local c = button.fsColor
    picker.fsLine:SetColorTexture(c[1], c[2], c[3], 0.9)
    picker:SetSize((TB.ENTRY_W + 2 * TB.PICKER_PAD) * s, (n * TB.ENTRY_H + 2 * TB.PICKER_PAD + 2) * s)
    for i, entry in ipairs(picker.fsEntries) do
        entry:ClearAllPoints()
        local item = st.list[i]
        if item and i <= n then
            entry:SetSize(TB.ENTRY_W * s, TB.ENTRY_H * s)
            entry:SetPoint("BOTTOMLEFT", picker, "BOTTOMLEFT", TB.PICKER_PAD * s,
                (TB.PICKER_PAD + (i - 1) * TB.ENTRY_H) * s)
            entry.fsSpellID = item.id
            entry.fsIcon:SetSize((TB.ENTRY_H - 4) * s, (TB.ENTRY_H - 4) * s)
            entry.fsIcon:ClearAllPoints()
            entry.fsIcon:SetPoint("LEFT", entry, "LEFT", 2 * s, 0)
            if item.icon then entry.fsIcon:SetTexture(item.icon) end
            entry.fsLabel:ClearAllPoints()
            entry.fsLabel:SetPoint("LEFT", entry.fsIcon, "RIGHT", 6 * s, 0)
            entry.fsLabel:SetText(item.name)
            entry.fsMark:SetShown(current ~= nil and item.id == current.id)
            entry:Show()
        else
            entry.fsSpellID = nil
            entry:Hide()
        end
    end
    picker:ClearAllPoints()
    picker:SetPoint("BOTTOM", button, "TOP", 0, TB.PICKER_RISE * s)
    picker.fsOwner, picker.fsKey = button, key
    picker.fsIdle = 0
    picker:Show()
end

function TotemBar.TogglePicker(key)
    local picker = TB.picker
    if picker and picker:IsShown() and picker.fsKey == key then
        ClosePicker()
    else
        TotemBar.OpenPicker(key)
    end
end

-- Stores the pick for the character and makes the element drop it. Action mode sends it to the multi-cast slot
-- at once (kept for regen when the client did not take it); spell mode rewrites the spell attribute, which waits
-- for regen in combat.
function TotemBar.Pick(key, spellId)
    local button = TB.byKey[key]
    if not (button and button.fsDef.slot and type(spellId) == "number") then return end
    local entry = button.fsList and EntryById(button.fsList, spellId)
    if not entry then
        local name, icon = SpellById(spellId)
        entry = { id = spellId, name = name or "", icon = icon }
    end
    WritePick(key, entry)
    if button.fsMode == "action" and button.fsActionId then
        TB.pending[key] = nil
        if not SendPick(button.fsActionId, spellId) then TB.pending[key] = spellId end
        ShowPick(button, entry)
    else
        Sync()
    end
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Build()
    TB.host = CreateFrame("Frame", "FSTotemBar", UIParent)
    TB.host:SetFrameStrata("LOW")
    TB.host:Hide()
    for i, def in ipairs(TB.BUTTONS) do
        local button = TB.list[i]
        if not button then
            button = BuildButton(TB.host, def, i)
            TB.list[i] = button
            TB.byKey[def.key] = button
        end
        button:Hide()
    end
    TB.built = true
end

local function OnEvent(_, event)
    if event == "PLAYER_REGEN_ENABLED" then
        if TB.pendingSync then
            Sync()
        else
            local ok = pcall(ReplayPicks)
            if not ok then WarnOnce("totembar_replay", "totem tab could not resend a pick") end
        end
    elseif event == "UPDATE_BINDINGS" then
        UpdateAllHotkeys()
    elseif event == "SPELL_UPDATE_COOLDOWN" then
        UpdateAllCooldowns()
    elseif event == "PLAYER_TOTEM_UPDATE" then
        UpdateAllSweeps()
    elseif event == "ACTIONBAR_SLOT_CHANGED" or event == "UPDATE_MULTI_CAST_ACTIONBAR" then
        RefreshPicks()
    else
        Sync()
    end
end

local function Apply()
    if not IsShaman() then return end
    if not (FS.Theme and FS.FrameHelpers and FS.Layout) then return end

    local ok, err = pcall(Build)
    if not ok then
        print("|cff22e0ffForever STUwave|r: totem tab failed to build (" .. tostring(err) .. ")")
        return
    end

    local events = CreateFrame("Frame")
    for _, event in ipairs(TB.EVENTS) do pcall(events.RegisterEvent, events, event) end
    events:RegisterEvent("PLAYER_REGEN_ENABLED")
    events:RegisterEvent("UPDATE_BINDINGS")
    for _, event in ipairs(TB.LIVE_EVENTS) do pcall(events.RegisterEvent, events, event) end
    for _, event in ipairs(TB.OPTIONAL_EVENTS) do pcall(events.RegisterEvent, events, event) end
    events:SetScript("OnEvent", OnEvent)

    if FS.Layout.OnRescale then FS.Layout.OnRescale(Sync) end
    if FS.ActionBars and FS.ActionBars.OnGeometry then FS.ActionBars.OnGeometry(Sync) end
    FS.FrameHelpers.OnQuickKeybindChanged(UpdateAllHotkeys)

    -- The shoulder builds only for a bar that owns it, and its seat must exist before the first Sync seats the
    -- host and the buttons on it. The stance bar keeps Ghost Wolf: nothing here asks for the forms.
    TB.owns = true
    if FS.ClassShoulder and FS.ClassShoulder.Refresh then
        local shouldered, why = pcall(FS.ClassShoulder.Refresh)
        if not shouldered then WarnOnce("totembar_shoulder", "class shoulder failed (" .. tostring(why) .. ")") end
    end

    Sync()
end

-- Deferred to PLAYER_LOGIN with an InCombatLockdown fallback to PLAYER_REGEN_ENABLED, like SealBar.lua's loader.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    if InCombatLockdown() then
        self:RegisterEvent("PLAYER_REGEN_ENABLED")
        self:SetScript("OnEvent", function(inner)
            inner:UnregisterEvent("PLAYER_REGEN_ENABLED")
            Apply()
        end)
        return
    end
    Apply()
end)
