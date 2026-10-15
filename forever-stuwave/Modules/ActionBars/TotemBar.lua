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
--       ACTION mode: the multi-cast bar exists (HasMultiCastActionBar, else Call of the Elements known: below
--       that there are no slots, so nothing is attempted and nothing is warned), is usable
--       (C_ActionBar.GetMultiCastBarIndex answers a plain number and GetMultiCastTotemSpells lists totems for the
--       slot) AND the element's multi-cast slot plainly holds one of its totems (GetActionInfo reads it back).
--       type1 = "action" on that slot's action id: the native MultiCastActionButton's own CalculateAction() when the
--       frame exists (Wrath orders those buttons by SHAMAN_TOTEM_PRIORITIES, Earth first, so button n is not totem
--       slot n), else the formula (bar - 1) * 12 + (set - 1) * 4 + slot, set 1. The slot holds the pick, so a pick
--       needs no attribute write, and the native Call of the Elements drops the same set. An empty or foreign slot
--       is filled with the pick ONLY at the native button's id; a formula id is adopted when it already holds one of
--       the element's totems and is never written to, and a slot that holds a totem of another element is a mapping
--       error (SPELL mode, no write, one chat line).
--       SPELL mode: anything else, including every moment a multi-cast slot does not (yet) hold a totem of the
--       element. type1 = "spell" with the picked totem's localized NAME, written out of combat, so a pick made in
--       combat waits for PLAYER_REGEN_ENABLED. An element whose slot never took a SetMultiCastSpell pick (or whose
--       call raised twice) stays in SPELL mode until a learn event (PLAYER_LEVEL_UP, or a changed set of known
--       totems or bar at a sync) allows one fresh try (TB.spellOnly).
--     Which one is live is a question to the client at sync time (every call pcall'd and secret-guarded); neither
--     the action id formula nor the behaviour of SetMultiCastSpell is verified in game.
--   * SetMultiCastSpell is treated as PROTECTED (the secure action table has a "multispell" type): a blocked call
--     from addon code goes through the global error handler (ADDON_ACTION_BLOCKED), which pcall cannot catch, and
--     is not a silent no-op. So it is NEVER called in combat; a pick made in combat is queued and sent at
--     PLAYER_REGEN_ENABLED. Out of combat a call counts as landed only when GetActionInfo reads the pick back
--     from the slot (SendPick); a pick that has not shown in the slot a second later, or whose call raised twice, is
--     abandoned and its element falls back to SPELL mode. The button icon and tooltip always show what the slot (or the spell attribute)
--     will really drop, never a pick that did not land.
--   * SHIFT-RIGHT CLICK on an element dismisses ALL totems: shift-type2 = macro on the element button, whose macro
--     text clicks FSTotemDestroy1..4, four hidden secure buttons (SecureActionButtonTemplate, type destroytotem,
--     totem-slot 1..4) that carry no other attribute but useOnKeyDown = false (see Build). They are built with the tab and written once, out of combat.
--     Modifier prefixes are read from the keys held (SecureButton_GetModifierPrefix), so the held Shift looks
--     for shift-prefixed attributes on those buttons and falls back to the bare totem-slot. Not checked in game:
--     that /click reaches buttons whose host is the (shown) tab and that the C side answers a bare attribute
--     under Shift.
--   * SET DROP is Call of the Elements (66842), with Call of the Ancestors (66843) on shift once known. RECALL is
--     Totemic Recall (36936). Both are plain type "spell" and locked until known.
--   * LOCKED: an element with no known totem, and a Set drop or Recall not yet learned, carry NO castable
--     attribute, show the dotted mold and their unlock level, and dim by alpha. They are never hidden: Show and
--     Hide on a secure button are refused in combat.
--   * PICKING: a hover PIECE on each element button (TotemPiece.lua: a square cap piece over the button, up only while
--     the cursor is over the button or the piece, or while the picker for that element is open; the tab outline grows a
--     bump around it; the click area is the piece, 38 x 13 design px, 0 px into the button face; its chevron points down
--     while the picker is open), or an Alt-click, opens a plain frame (not secure, parented
--     to UIParent; nothing secure is its child or anchor target) that holds the known totems as an ICON ONLY flyout: a
--     column of 32 px tiles growing out of the tab's bump (TotemPiece.lua draws the chimney around it), the real spell
--     tooltip to the right of the hovered tile, the current pick marked. A click stores the
--     pick per character (ForeverSTUwaveDB.totemPicks[guid]) and, in action mode, calls SetMultiCastSpell out of
--     combat (queued for regen in combat). The saved pick is written ONLY by an explicit user pick or by adopting
--     what a slot already held, never for the default (the first known totem). Any Alt-modified click carries an
--     empty type1 (alt-, alt-shift-, alt-ctrl-, alt-ctrl-shift-) so it never also drops the totem.
--   * SWEEPS: every button carries the GCD swipe (spell cooldown duration object), element buttons also the live
--     totem sweep (GetTotemInfo times when plain and non zero, else the GetTotemDuration object; a plain zero answer is
--     "unknown" (it is what a standing totem can read in combat), so the sweep is cleared only when no totem
--     stands; left alone when nothing is readable).
--   * No `.bar` field and no attribute that makes a button borrow its parent's (the "use parent" family) is ever
--     set on a button: Blizzard's SecureButton_GetModifiedAttribute reads both during a secure click, and an addon
--     written value there taints the click. Every button carries explicit attributes (action / spell / totem-slot).
--   * SetAttribute, Show, Hide, SetPoint and SetSize on a secure button (or its host) are refused in combat.
--     Everything that does any of them runs out of combat only; combat sets `pendingSync` and
--     PLAYER_REGEN_ENABLED replays it. Textures, swipes and the picker follow in combat; SetMultiCastSpell waits for regen.
--   * USABILITY: the same feedback as the main bars (ActionBars.lua UpdateUsable, colours Theme.COLOR_OOM and
--     Theme.COLOR_UNUSABLE): out of mana tints blue, otherwise unusable tints grey, usable is the plain look. An
--     ELEMENT button tints its spell icon only (the crown and the underline keep the element colour); the set drop
--     and recall buttons, whose face is the glyph, tint the glyph (the dark plate behind it is left alone). The
--     source is IsUsableAction on the multi-cast slot in ACTION mode and C_Spell.IsSpellUsable (else IsUsableSpell)
--     on the current pick in SPELL mode. An answer that is secret, missing or raised leaves the tint as it was.
--     A locked button is plain. Event driven (SPELL_UPDATE_USABLE, ACTIONBAR_UPDATE_USABLE, the combat edges, a
--     sync, a new pick): texture writes only, legal in combat, a write only when the state changed.
--   * SEAT: TotemBar.HostPoint / TotemBar.SlotPoint, answered by the class shoulder while it stands, with the
--     same fallback as SealBar (above the stance bar's seat).
--
--   * CELLS: TotemPresets.lua adds up to two more buttons after the six, FSTotemButton7 (Preset 1) and 8
--     (Preset 2), through TotemBar.AddCell at its own load, before the tab builds. A cell def carries `cell = true`
--     and `enabled()`; the tab is 6 + (cells that are enabled) columns wide (TotemBar.Cols, which ClassShoulder.lua
--     reads for the shoulder's width), the cells stand after the six in order, a cell that is off hides. TotemDial.lua
--     styles and paints them; this file only seats, shows, hides and asks them for their attributes in Sync (out of
--     combat). Without those two files the tab is the six stock buttons it always was.
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
    GLYPH_ALPHA = 0.95,         -- the pole crown / face glyph (StyleButton, and the usability tint restores it)
    LOCKED_ALPHA = 0.4,
    MC_SET = 1,                 -- the multi-cast page Call of the Elements drops
    MAX_ENTRIES = 6,            -- picker tiles (an element holds at most 5 totems by level 30)
    -- the icon flyout (mockups/totem-picker-arrow-2026-10-13.html concept A, open state of
    -- mockups/totem-picker-arrow-v3-2026-10-13.html V1; the harness reads those numbers back out of the v3 file):
    -- 32 px tiles in a column on the button's own axis, bottom up, a 3 px gap, 3 px to each wall, 5 px over the last
    -- tile, the cut 4 seat of the tab's buttons. The first tile sits ABOVE = 4 px over the piece top, so the column's
    -- bottom is RISE = piece top (SEAM 2 + BAR 11) + ABOVE over the button top, which is the bump top the chimney's
    -- walls rise out of (TotemPiece.lua draws the chimney).
    FLYOUT = { TILE = 32, GAP = 3, PAD = 3, TOP_PAD = 5, CUT = 4, ABOVE = 4, RISE = 17, TIP_GAP = 5 },
    -- the arrow's hit area is the hover piece itself (TotemPiece.lua, mockups/totem-picker-arrow-v3-2026-10-13.html):
    -- the button's width, the 11 px bar plus the 2 px seam under it, standing on the button top with ARROW_INTO = 0 px
    -- inside the face (the piece's wedge tip under the button top is art only, never clickable). Its top is 7 px over
    -- the tab's top rail, which grows a bump around it while it is up.
    ARROW_W = 38, ARROW_H = 13, ARROW_INTO = 0,
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
    -- the totems of each element up to level 30, in the default pick order, as { rank 1 spell id, English name }.
    -- The id is the identity (the localized name of that id is what is shown and written to a spell attribute, and
    -- looking that name up finds the highest rank the player knows); the English name is only the display
    -- fallback for an id the client cannot name. The ids are the Classic rank 1 ids; the multi-cast API's own
    -- lists carry whatever ids Forever uses.
    TOTEMS = {
        fire = { { 3599, "Searing Totem" }, { 8181, "Frost Resistance Totem" }, { 8190, "Magma Totem" },
            { 8227, "Flametongue Totem" } },
        earth = { { 8071, "Stoneskin Totem" }, { 2484, "Earthbind Totem" }, { 5730, "Stoneclaw Totem" },
            { 8075, "Strength of Earth Totem" }, { 8143, "Tremor Totem" } },
        water = { { 5394, "Healing Stream Totem" }, { 8166, "Poison Cleansing Totem" },
            { 5675, "Mana Spring Totem" }, { 8184, "Fire Resistance Totem" } },
        air = { { 8177, "Grounding Totem" }, { 10595, "Nature Resistance Totem" } },
    },
    CALL_ID = 66842,            -- Call of the Elements: the spell that brings the multi-cast bar
    -- Alt-modified left clicks: an empty type1 (ATTRIBUTE_NOOP) for each, so they open the picker without
    -- dropping. Blizzard's SecureTemplates builds the modifier prefix only in the order alt-ctrl-shift-.
    ALT_NOOPS = { "alt-type1", "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1" },
    SETTLE = 1.0,               -- seconds a SetMultiCastSpell call gets to show in the slot before it is given up
    MAX_ATTEMPTS = 2,           -- SetMultiCastSpell calls that may raise before the element falls back to SPELL mode
    -- every attribute this tab writes, cleared together when a button locks
    ATTRS = { "type", "spell", "type1", "action1", "spell1", "type2", "totem-slot2", "alt-type1",
        "alt-shift-type1", "alt-ctrl-type1", "alt-ctrl-shift-type1", "shift-type1", "shift-spell1",
        "shift-type2", "shift-macrotext2" },
    -- Shift-right click on an element dismisses every totem: a macro that clicks four hidden secure buttons
    -- (FSTotemDestroy1..4, type destroytotem, totem-slot 1..4). /click presses LeftButton, the buttons carry no
    -- modifier-prefixed attribute and the bare totem-slot answers whatever modifier is held.
    DESTROY_ALL = "/click FSTotemDestroy1\n/click FSTotemDestroy2\n/click FSTotemDestroy3\n/click FSTotemDestroy4",
    EVENTS = { "SPELLS_CHANGED", "LEARNED_SPELL_IN_SKILL_LINE", "PLAYER_LEVEL_UP", "PLAYER_ENTERING_WORLD" },
    -- state-only events: texture and Cooldown writes, legal in combat
    LIVE_EVENTS = { "SPELL_UPDATE_COOLDOWN", "PLAYER_TOTEM_UPDATE", "ACTIONBAR_SLOT_CHANGED",
        "SPELL_UPDATE_USABLE", "ACTIONBAR_UPDATE_USABLE", "PLAYER_REGEN_DISABLED" },
    -- not on every client; asked with a pcall
    OPTIONAL_EVENTS = { "UPDATE_MULTI_CAST_ACTIONBAR" },
    host = nil,
    list = {},          -- the six buttons, by index
    byKey = {},         -- and by key
    destroy = {},       -- the four hidden dismiss buttons, by totem slot
    cells = {},         -- the cell defs TotemPresets.lua added (also appended to BUTTONS), in order
    picker = nil,
    pending = {},       -- key -> { id, sent, at, ignore }: a multi-cast pick not in the slot yet (sent = the call ran,
                        -- at = when; ignore = slot contents that are not a native change)
    ownFill = {},       -- key -> spell id the tab itself put in an empty slot (a default, not an adopted choice)
    fills = {},         -- key -> { tag, sent, at }: a fill of an empty or foreign slot that has not shown up yet
    attempts = {},      -- key -> SetMultiCastSpell calls that raised since the last one that ran
    spellOnly = {},     -- key -> true: this element's slot never took a pick; SPELL mode until a learn event
    signature = nil,    -- what the player knew at the last sync (totems, multi-cast bar): a change allows a new try
    needsResync = false,
    verifyQueued = false,
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
local ATTRIBUTE_NOOP = ""      -- Blizzard's ATTRIBUTE_NOOP: a click type that does nothing

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

-- Shared with the other class tabs (FrameHelpers.lua).
local PlainValue = FS.FrameHelpers.PlainValue

-------------------------------------------------------------------------------
-- Spells
-------------------------------------------------------------------------------

-- Spell lookups shared with the other class tabs (FrameHelpers.lua): ResolveSpell(name) -> id, icon (the highest
-- rank the player knows), SpellById(id) -> name, icon, IsKnownSpellId(id, fallback) (SealBar's rule).
local ResolveSpell = FS.FrameHelpers.ResolveSpell
local SpellById = FS.FrameHelpers.SpellById
local IsKnownSpellId = FS.FrameHelpers.IsKnownSpellId

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

-- The action id Blizzard's own multi-cast button reports for a totem slot, or nil when it cannot be told. Wrath
-- orders MultiCastActionButton1..4 by SHAMAN_TOTEM_PRIORITIES (Earth first), so the button for totem slot `slot` is
-- the one at that slot's position in the priorities, not button `slot`. The frame's own CalculateAction() answers
-- the id; the formula above is only the fallback when there is no such frame.
local function NativeActionId(slot)
    local priorities = _G.SHAMAN_TOTEM_PRIORITIES
    if type(priorities) ~= "table" or IsSecret(priorities) then return nil end
    local index
    for i = 1, 8 do
        local entry = priorities[i]
        if entry == nil or IsSecret(entry) then break end
        if entry == slot then
            index = i
            break
        end
    end
    if not index then return nil end
    local widget = _G["MultiCastActionButton" .. index]
    if type(widget) ~= "table" or IsSecret(widget) or type(widget.CalculateAction) ~= "function" then return nil end
    local ok, got = pcall(widget.CalculateAction, widget)
    got = ok and PlainValue(got, "number") or nil
    if got and got >= 1 and got == math.floor(got) then return got end
    return nil
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

-- The known totems of an element from the spellbook, in the table's order. Each static entry is a rank 1 id: its
-- localized name (the display name, and the spell attribute) is looked up for the highest rank the player knows, and
-- the entry is known when either that rank or the static id is. With no spellbook API at all, only a name that
-- resolves counts.
local function BookTotems(def)
    local out = {}
    for _, totem in ipairs(TB.TOTEMS[def.key] or {}) do
        local baseId, englishName = totem[1], totem[2]
        local name, icon = SpellById(baseId)
        local topId, topIcon
        if name then topId, topIcon = ResolveSpell(name) end
        local id
        if topId and IsKnownSpellId(topId, true) then
            id = topId
        elseif IsKnownSpellId(baseId, false) then
            id = baseId
        end
        if id then
            local shown, shownIcon = SpellById(id)
            out[#out + 1] = { id = id, name = shown or name or englishName,
                icon = shownIcon or icon or topIcon }
        end
    end
    return out
end

-- true when the client's multi-cast bar exists: HasMultiCastActionBar answers a plain flag, else Call of the Elements
-- is known (it is what brings the bar). Below that the slots do not exist, so no fill is ever attempted.
local function MultiCastBarActive()
    if HasMultiCastActionBar then
        local ok, has = pcall(HasMultiCastActionBar)
        if ok and not IsSecret(has) then
            if type(has) == "boolean" then return has end
            if type(has) == "number" then return has ~= 0 end
        end
    end
    return IsKnownSpellId(TB.CALL_ID, false)
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

-- Seconds from GetTime, or nil when the client has none.
local function Now()
    if not GetTime then return nil end
    local ok, t = pcall(GetTime)
    return ok and PlainValue(t, "number") or nil
end

-- true when a send made at `at` has had TB.SETTLE seconds to show up. Without a clock any later look counts.
local function Settled(at)
    local now = Now()
    if not (now and at) then return true end
    return now - at >= TB.SETTLE
end

-- Asks for one more sync a moment after a send that has not shown in the slot yet, so a pick that never lands is
-- noticed without waiting for some other event. Sync parks itself in combat.
local function ScheduleVerify()
    if TB.verifyQueued or not (C_Timer and C_Timer.After) then return end
    TB.verifyQueued = true
    C_Timer.After(TB.SETTLE + 0.1, function()
        TB.verifyQueued = false
        if TotemBar.Sync then TotemBar.Sync() end
    end)
end

-- SetMultiCastSpell(actionId, spellId), OUT OF COMBAT ONLY (it is a protected function: a blocked call is not
-- catchable by pcall, so it is never made in combat). Returns landed, called. `landed` is true only when the slot
-- reads back as the pick right now. `called` is true when the call ran without raising; the slot may still update a
-- moment later (ACTIONBAR_SLOT_CHANGED), so a call that did not land is judged again after TB.SETTLE seconds.
-- `raised` is true when the call was made and threw (not when it was refused for combat or a missing function).
local function SendPick(actionId, spellId)
    if not SetMultiCastSpell or InCombatLockdown() then return false, false, false end
    if not pcall(SetMultiCastSpell, actionId, spellId) then return false, false, true end
    local got, readable = ReadSlot(actionId)
    return readable and got == spellId, true, false
end

-- A SetMultiCastSpell call raised: the element's attempt count, and true once TB.MAX_ATTEMPTS is reached.
local function CountFailure(key)
    local n = (TB.attempts[key] or 0) + 1
    TB.attempts[key] = n
    return n >= TB.MAX_ATTEMPTS
end

-- The multi-cast slot is no good for this element (it did not take a pick, or the call keeps raising): SPELL mode
-- until a learn event allows a fresh try. The saved pick stays; the spell attribute follows it at the next sync.
local function GiveUp(key, title, why)
    TB.pending[key], TB.fills[key], TB.ownFill[key], TB.attempts[key] = nil, nil, nil, nil
    TB.spellOnly[key] = true
    TB.needsResync = true
    WarnOnce("totembar_pick_" .. key, title .. " totem: " .. why .. ", using the spell instead")
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

-- The known totems of an element for SPELL mode: the spellbook's, else the multi-cast API's, named (a spell
-- attribute needs the totem's name).
local function SpellList(def, multi)
    local list = BookTotems(def)
    if #list == 0 and multi then list = multi end
    local named = {}
    for _, entry in ipairs(list) do
        if entry.name ~= "" then named[#named + 1] = entry end
    end
    return named
end

-- true when a spell id is a totem of ANOTHER element: in that element's multi-cast list, or in the static table.
-- A slot that holds one means the slot mapping is wrong for this element.
local function HoldsOtherElement(def, held)
    for _, other in ipairs(TB.BUTTONS) do
        if other.slot and other.key ~= def.key then
            if EntryById(MultiCastTotems(other.slot) or {}, held) then return true end
            for _, totem in ipairs(TB.TOTEMS[other.key] or {}) do
                if totem[1] == held then return true end
            end
        end
    end
    return false
end

-- What an element button should be right now: { list, mode, actionId, pick, landed, adopted, mapError }. `mode` is
-- nil when no totem of the element is known (the button locks). Reads only; writes nothing.
--   ACTION mode needs the multi-cast bar to exist (MultiCastBarActive) and a readable multi-cast slot. `landed` is
--   true when the slot holds one of the element's totems (that is `pick`, and `adopted` says it was there already);
--   false when the slot is empty or holds something else, and then `pick` is the totem to fill it with. A fill is
--   offered ONLY for an action id the native multi-cast button reported: an id from the formula can name another
--   element's slot, so it may be adopted but never written. A slot that holds a totem of ANOTHER element is a
--   mapping error (`mapError`): SPELL mode, no write.
--   SPELL mode: the saved pick, else the first known totem.
-- `forceSpell` skips ACTION mode (the caller found the slot unusable).
local function Evaluate(def, forceSpell)
    local multi = MultiCastTotems(def.slot)
    local bar = multi and not forceSpell and not TB.spellOnly[def.key] and MultiCastBar() or nil
    if bar and not MultiCastBarActive() then bar = nil end
    local mapError = false
    if bar then
        local native = NativeActionId(def.slot)
        local actionId = native or ActionId(bar, def.slot)
        local held, readable = ReadSlot(actionId)
        if readable then
            local entry = held and EntryById(multi, held)
            if entry then
                return { list = multi, mode = "action", actionId = actionId, pick = entry, landed = true, adopted = true }
            end
            if held and HoldsOtherElement(def, held) then
                mapError = true
            elseif native then
                local pick = Matching(multi, ReadPick(def.key)) or multi[1]
                return { list = multi, mode = "action", actionId = actionId, pick = pick, landed = false }
            end
        end
    end
    local list = SpellList(def, multi)
    if #list == 0 then return { list = list, mapError = mapError } end
    return { list = list, mode = "spell", pick = Matching(list, ReadPick(def.key)) or list[1], mapError = mapError }
end

-------------------------------------------------------------------------------
-- Buttons
-------------------------------------------------------------------------------

local UpdateHotkey = FS.FrameHelpers.UpdateButtonHotkey
local AnchorTooltip = FS.FrameHelpers.AnchorTooltip

local function ShowTooltip(self)
    local tip = GameTooltip
    local def = self.fsDef
    if not (tip and def) then return end
    if def.cell then
        if FS.TotemDial and FS.TotemDial.Tooltip then FS.TotemDial.Tooltip(self) end
        return
    end
    AnchorTooltip(self)
    local c = self.fsColor
    if self.fsLocked then
        tip:AddLine(def.title .. (def.slot and " totem" or ""), c[1], c[2], c[3])
        tip:AddLine("Opens at level " .. def.unlock .. ".", 0.62, 0.58, 0.77)
    elseif def.slot then
        local pick = self.fsPick
        local name = pick and pick.name ~= "" and pick.name or (def.title .. " totem")
        tip:AddLine(def.title .. " totem: " .. name, c[1], c[2], c[3])
        tip:AddLine("Left click: drop " .. name .. ". Right click: dismiss. Shift-right click: dismiss all. Alt-click or arrow: change totem.",
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

-- The hover piece (a plain Button on the element button) opens the picker; Alt-click on the button does too.
local function OnArrowClick(self)
    TotemBar.TogglePicker(self.fsKey)
end

-- true while the picker is open for this element's button
local function PickerOpenFor(button)
    local picker = TB.picker
    return picker ~= nil and picker:IsShown() and picker.fsKey == button.fsKey
end

-- The piece's look: lit while the cursor is on it or its picker is open, the chevron down while the picker is open.
-- Texture writes on the plain arrow only, legal in combat.
local function RefreshPiece(button)
    local arrow = button.fsArrow
    if not arrow then return end
    local open = PickerOpenFor(button)
    FS.TotemPiece.SetLook(arrow, arrow.fsOver or open, open)
end

-- The piece is up only while the cursor is over its element button or over the piece itself (like Blizzard's own
-- flyout arrow), or while the picker for it is open. IsMouseOver is the cursor's position against each frame's rect,
-- so crossing from the button onto the piece (the button's OnLeave fires first) never drops it. The arrow is a plain
-- frame: Show and Hide on it are legal in combat even though its parent is a secure button.
local function ShowArrow(button)
    local arrow = button.fsArrow
    if arrow and not button.fsLocked then arrow:Show() end
end

local function HideArrowIfAway(button)
    local arrow = button.fsArrow
    if not (arrow and arrow:IsShown()) or PickerOpenFor(button) then return end
    if not (button:IsMouseOver() or arrow:IsMouseOver()) then arrow:Hide() end
end

-- The piece comes up with the bump around it; both go together. OnShow also fires for a picker opened without the
-- cursor (a key press), which shows the piece in its open state.
local function OnArrowShow(self)
    FS.TotemPiece.SetBump(self.fsButton.fsCol, true)
    RefreshPiece(self.fsButton)
end

-- One bump stands at a time, so a hover over another element moves the open picker's bump away. When that hover
-- ends the open picker's piece is still up and gets its bump back.
local function RestoreOpenPickerBump(except)
    local picker = TB.picker
    local owner = picker and picker:IsShown() and picker.fsOwner or nil
    if owner and owner ~= except and owner.fsArrow and owner.fsArrow:IsShown() then
        FS.TotemPiece.SetBump(owner.fsCol, true)
    end
end

local function OnArrowHide(self)
    self.fsOver = false
    RefreshPiece(self.fsButton)
    FS.TotemPiece.SetBump(self.fsButton.fsCol, false)
    RestoreOpenPickerBump(self.fsButton)
end

local function OnArrowEnter(self)
    self.fsOver = true
    RefreshPiece(self.fsButton)
end

local function OnArrowLeave(self)
    self.fsOver = false
    RefreshPiece(self.fsButton)
    HideArrowIfAway(self.fsButton)
end

local function OnButtonEnter(self)
    ShowArrow(self)
end

local function OnButtonLeave(self)
    HideArrowIfAway(self)
end

local function OnButtonHide(self)
    if self.fsArrow then self.fsArrow:Hide() end
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
        button:HookScript("OnEnter", OnButtonEnter)
        button:HookScript("OnLeave", OnButtonLeave)
        button:HookScript("OnHide", OnButtonHide)
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
    local textHost = FS.FrameHelpers.SeatButtonText(button, button.HotKey)
    local top = button.totemCooldown or button.cooldown
    if textHost.GetFrameLevel and top.GetFrameLevel and top:GetFrameLevel() >= textHost:GetFrameLevel() then
        textHost:SetFrameLevel(top:GetFrameLevel() + 1)
    end
    FS.FrameHelpers.SeatButtonHotkey(button, textHost)

    -- the pole crown: a small badge on an element button, the whole face glyph on the set and recall buttons
    if def.glyph and not button.fsGlyph then
        local glyph = textHost:CreateTexture(nil, "OVERLAY", nil, 2)
        glyph:SetTexture(MEDIA .. def.glyph .. ".tga")
        glyph:SetVertexColor(button.fsColor[1], button.fsColor[2], button.fsColor[3], TB.GLYPH_ALPHA)
        button.fsGlyph = glyph
    end
    if button.fsGlyph then
        button.fsGlyph:ClearAllPoints()
        if def.slot then
            button.fsGlyph:SetSize(13 * scale, 13 * scale)
            button.fsGlyph:SetPoint("BOTTOMLEFT", button, "BOTTOMLEFT", 4 * scale, 6 * scale)
        else
            button.fsGlyph:SetSize(26 * scale, 26 * scale)
            button.fsGlyph:SetPoint("CENTER", button, "CENTER", 0, 0)
        end
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

    -- a locked button: the dotted mold and its unlock level (a cell is never locked)
    if def.unlock and not button.fsMold then
        local mold = button:CreateTexture(nil, "ARTWORK", nil, 1)
        mold:SetTexture(MEDIA .. "totem_mold.tga")
        local m = FS.Theme.COLOR_MUTED or { 0.62, 0.58, 0.77, 1 }
        mold:SetVertexColor(m[1], m[2], m[3], 0.9)
        mold:SetAllPoints(button)
        mold:Hide()
        button.fsMold = mold
    end
    if def.unlock and not button.fsLockText then
        local text = textHost:CreateFontString(nil, "OVERLAY")
        FS.Theme.ApplyMono(text, 11, FS.Theme.COLOR_MUTED or FS.Theme.COLOR_TEXT_WHITE)
        text:SetPoint("CENTER", button, "CENTER", 0, 0)
        text:SetText("L" .. def.unlock)
        text:Hide()
        button.fsLockText = text
    end

    -- the hover piece: a plain Button, so a click on it never reaches the secure action underneath. The Button is
    -- the HIT AREA and it is exactly the piece's bar and seam: 38 x 13 design px standing on the button top, 0 px
    -- inside the face, so everything on the face (drop, dismiss, shift and its tooltip) stays the button's. The art
    -- (TotemPiece.lua) is regions of this Button and hangs a little past its rect: the wedge tip under the button top
    -- and a glow, none of it clickable.
    -- (without TotemPiece.lua, which is not required to load, the tab builds with no piece: the picker still opens
    -- by key and Alt-click)
    if def.slot and FS.TotemPiece and not button.fsArrow then
        local arrow = CreateFrame("Button", nil, button)
        arrow.fsKey = def.key
        arrow.fsButton = button
        arrow:RegisterForClicks("LeftButtonUp")
        FS.TotemPiece.Attach(arrow, button.fsColor)
        arrow:SetScript("OnClick", OnArrowClick)
        arrow:SetScript("OnEnter", OnArrowEnter)
        arrow:SetScript("OnLeave", OnArrowLeave)
        arrow:SetScript("OnShow", OnArrowShow)
        arrow:SetScript("OnHide", OnArrowHide)
        -- a missed OnLeave (the cursor warped, the frame hidden under it) must not leave the piece standing
        arrow:SetScript("OnUpdate", function(self) HideArrowIfAway(self.fsButton) end)
        arrow:Hide()
        button.fsArrow = arrow
    end
    if button.fsArrow then
        local arrow = button.fsArrow
        arrow:SetSize(TB.ARROW_W * scale, TB.ARROW_H * scale)
        arrow:ClearAllPoints()
        arrow:SetPoint("BOTTOMLEFT", button, "TOPLEFT", 0, -TB.ARROW_INTO * scale)
        arrow:SetFrameLevel(textHost:GetFrameLevel() + 1)
        if FS.TotemPiece then FS.TotemPiece.Seat(arrow, scale) end
    end

    -- a cell (TotemDial.lua) wears its own face on this chrome
    if def.cell and FS.TotemDial and FS.TotemDial.StyleCell then FS.TotemDial.StyleCell(button, textHost, scale) end
end

local function BuildButton(host, def, index)
    local button = CreateFrame("Button", "FSTotemButton" .. index, host, "SecureActionButtonTemplate")
    button.fsKey = def.key
    button.fsDef = def
    button.fsCol = index
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

-- The live totem sweep. A plain false from GetTotemInfo is "no totem" and clears the sweep first. Otherwise its start
-- and duration when both are plain and non zero; a plain zero answer is NOT "no totem" (a standing totem can read
-- true, "", 0, 0, 0 in combat), so the GetTotemDuration object is asked next (a secret answer is checked before
-- anything else is done with it). With GetTotemInfo unreadable the sweep is cleared only when the duration object
-- is plainly nil. Anything else leaves the sweep as it was.
local function UpdateTotemSweep(button)
    local sweep, slot = button.totemCooldown, button.fsDef.slot
    if not (sweep and slot) then return end
    if button.fsLocked then
        sweep:Clear()
        sweep:Hide()
        return
    end
    local have
    if GetTotemInfo then
        local ok, haveTotem, _, start, duration = pcall(GetTotemInfo, slot)
        if ok then
            have = PlainValue(haveTotem, "boolean")
            if have == false then
                -- GetTotemInfo plainly says no totem stands: nothing a duration object says can override that
                sweep:Clear()
                sweep:Hide()
                return
            end
            start, duration = PlainValue(start, "number"), PlainValue(duration, "number")
            if start and duration and start > 0 and duration > 0 then
                sweep:SetCooldown(start, duration)
                sweep:Show()
                return
            end
        end
    end
    local objNil = false
    if GetTotemDuration then
        local ok, obj = pcall(GetTotemDuration, slot)
        if ok and not IsSecret(obj) then
            if obj == nil then
                objNil = true
            else
                sweep:SetCooldownFromDurationObject(obj)
                sweep:Show()
                return
            end
        end
    end
    if have == true then return end
    if objNil then
        sweep:Clear()
        sweep:Hide()
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
-- Usability (texture writes: legal in combat)
-------------------------------------------------------------------------------

local ActionUsability = FS.FrameHelpers.ActionUsability
local SpellUsability = FS.FrameHelpers.SpellUsability
local UsabilityColor = FS.FrameHelpers.UsabilityColor

-- Paints a usability state ("oom", "unusable", anything else is plain) when it differs from the one painted. An
-- element button tints its spell icon; the set drop and recall buttons wear their glyph as the face, so the glyph
-- takes the tint colour instead (their element colour comes back with the plain state).
local function PaintUsable(button, state)
    if button.fsTint == state then return end
    local c = UsabilityColor(state)
    if button.fsDef.slot then
        if not button.icon then return end
        button.fsTint = state
        if c then button.icon:SetVertexColor(c[1], c[2], c[3]) else button.icon:SetVertexColor(1, 1, 1) end
    else
        local glyph = button.fsGlyph
        if not glyph then return end
        button.fsTint = state
        local from = c or button.fsColor
        glyph:SetVertexColor(from[1], from[2], from[3], TB.GLYPH_ALPHA)
    end
end

-- Reads one button's usability from where it casts: the multi-cast slot in ACTION mode, the spell otherwise. An
-- answer that cannot be told (nil: secret, missing, raised) leaves the painted state alone. A locked button is plain.
local function UpdateUsable(button)
    if button.fsLocked then
        PaintUsable(button, nil)
        return
    end
    local state
    if button.fsMode == "action" and button.fsActionId then
        state = ActionUsability(button.fsActionId)
    elseif button.fsSpellID then
        state = SpellUsability(button.fsSpellID)
    end
    if state then PaintUsable(button, state) end
end

local function UpdateAllUsable()
    for _, button in ipairs(TB.list) do UpdateUsable(button) end
end
TotemBar.UpdateUsable = UpdateAllUsable

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
        button.fsArrow:Hide()
    end
    UpdateCooldown(button)
    UpdateTotemSweep(button)
    PaintUsable(button, nil)
end

local function Unlock(button)
    button.fsLocked = false
    button:SetAlpha(1)
    button.fsMold:Hide()
    button.fsLockText:Hide()
    if button.fsUnderline then button.fsUnderline:Show() end
    if button.fsArrow then
        button.fsArrow:EnableMouse(true)
        -- up only if the cursor is already on the button when it unlocks
        if button:IsMouseOver() then button.fsArrow:Show() end
    end
end

-- Shows the picked totem on an element button: its icon and the id its swipe follows. Texture state.
local function ShowPick(button, pick)
    button.fsPick = pick
    button.fsSpellID = pick and pick.id or nil
    if pick and pick.icon then
        FS.FrameHelpers.SetSpellIcon(button.icon, pick.icon)
        button.icon:Show()
    elseif pick then
        button.icon:Show()
    end
    UpdateCooldown(button)
    UpdateUsable(button)
end

-- An empty or foreign multi-cast slot (one the native multi-cast button named) gets the pick once per (slot, pick).
-- The slot is then judged by what it reads back: a fill that shows up (now, or on ACTIONBAR_SLOT_CHANGED within
-- TB.SETTLE seconds) makes the element ACTION mode; until then the button is SPELL mode, so it never points at an
-- empty slot. A fill that has not shown after TB.SETTLE seconds is given up and the element stays SPELL mode until a
-- learn event; so does one whose call keeps raising (TB.MAX_ATTEMPTS). The fill is marked sent BEFORE the call, so
-- an event the call raises synchronously cannot send it again, and the pick is marked as the tab's own default as
-- soon as the call runs, so a slot that updates late is not saved as the user's choice. Out of combat only.
local function Settle(def, st)
    local key = def.key
    local tag = tostring(st.actionId) .. ":" .. tostring(st.pick.id)
    local rec = TB.fills[key]
    if rec and rec.tag == tag and rec.sent then
        if Settled(rec.at) then
            GiveUp(key, def.title, "the multi-cast slot did not take the pick")
        else
            ScheduleVerify()
        end
        return Evaluate(def, true)
    end
    rec = { tag = tag, sent = true, at = Now() }
    TB.fills[key] = rec
    local landed, called, raised = SendPick(st.actionId, st.pick.id)
    if not called then rec.sent, rec.at = nil, nil end
    if called then
        TB.attempts[key] = nil
        TB.ownFill[key] = st.pick.id
    elseif raised then
        if CountFailure(key) then
            GiveUp(key, def.title, "the multi-cast call keeps failing")
        else
            ScheduleVerify()
        end
        return Evaluate(def, true)
    end
    if landed then
        TB.fills[key] = nil
        local now = Evaluate(def)
        if now.landed then
            now.adopted = false      -- our own fill, not something the slot already held
            return now
        end
    end
    if called then ScheduleVerify() end
    return Evaluate(def, true)
end

-- Listeners told, after an element button's castable attributes were settled (written, kept or stripped by Lock), which
-- button it was: GunsightShamanDrop.lua copies type1 / action1 / spell1 onto its pole click catchers so a click on a pole
-- casts exactly what this button casts. Called from ApplyElement only, which runs out of combat only (Sync), so a listener
-- may write secure attributes. A listener that throws is skipped and named once in chat.
local attributeListeners = {}
function TotemBar.OnAttributes(fn)
    if type(fn) ~= "function" then return end
    for i = 1, #attributeListeners do if attributeListeners[i] == fn then return end end
    attributeListeners[#attributeListeners + 1] = fn
end

local function AnnounceAttributes(button)
    for i = 1, #attributeListeners do
        local ok, err = pcall(attributeListeners[i], button)
        if not ok then WarnOnce("totembar_listener", "an attribute listener failed (" .. tostring(err) .. ")") end
    end
end

-- An element button from its evaluated state. Out of combat only (attributes).
local function ApplyElement(button, def)
    local st = Evaluate(def)
    if st.mode == "action" and not st.landed then
        st = Settle(def, st)
    else
        TB.fills[def.key] = nil      -- landed, or no longer in play: nothing to wait for
    end
    if st.mapError then
        WarnOnce("totembar_map_" .. def.key, def.title .. " totem: the multi-cast slot holds another element's "
            .. "totem, using the spell instead")
    end
    if not st.pick then
        Lock(button)
        AnnounceAttributes(button)
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
        button:SetAttribute("shift-type2", "macro")
        button:SetAttribute("shift-macrotext2", TB.DESTROY_ALL)
        -- Alt-click opens the picker; an empty type means it does not also drop the totem
        for _, name in ipairs(TB.ALT_NOOPS) do button:SetAttribute(name, ATTRIBUTE_NOOP) end
        button.fsAttrKey = key
    end
    -- the saved pick follows the slot only when the slot already held the totem (not for our own default fill)
    if st.adopted and not TB.pending[def.key] and TB.ownFill[def.key] ~= pick.id then
        WritePick(def.key, pick)
        TB.ownFill[def.key] = nil
    end
    ShowPick(button, pick)
    AnnounceAttributes(button)
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
    UpdateUsable(button)
end

-- A pick the native bar made (or one we sent) moved the multi-cast slot: show it. Texture state and a saved
-- variable write, so it may run in combat. Never touches an attribute, except through a parked Sync: an element
-- waiting on a fill is re-judged once its slot changes. A queued pick of ours is dropped when the slot shows a
-- totem that is neither the pick nor something the slot held when it was queued (the native bar changed it).
local function RefreshPicks()
    for _, button in ipairs(TB.list) do
        if button.fsMode == "action" and button.fsList and not button.fsLocked then
            local held = ReadSlot(button.fsActionId)
            local entry = held and EntryById(button.fsList, held)
            local queued = TB.pending[button.fsKey]
            if queued then
                if entry and entry.id == queued.id then
                    TB.pending[button.fsKey] = nil
                    ShowPick(button, entry)
                elseif entry and not (queued.ignore and queued.ignore[entry.id]) then
                    -- the native bar chose another totem since this pick was queued: that is the newer choice, and
                    -- resending ours at regen would overwrite it
                    TB.pending[button.fsKey] = nil
                    TB.ownFill[button.fsKey] = nil
                    WritePick(button.fsKey, entry)
                    ShowPick(button, entry)
                end
            elseif entry and (not button.fsPick or entry.id ~= button.fsPick.id) then
                TB.ownFill[button.fsKey] = nil
                WritePick(button.fsKey, entry)
                ShowPick(button, entry)
            end
        end
    end
    if next(TB.fills) ~= nil and TotemBar.Sync then TotemBar.Sync() end
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

local function CellOn(def)
    if not def.enabled then return true end
    local ok, on = pcall(def.enabled)
    return ok and on == true
end

-- The columns the tab stands on: the six stock buttons and one more for each cell that is on.
function TotemBar.Cols()
    local cols = TB.COLS
    for _, def in ipairs(TB.cells) do
        if CellOn(def) then cols = cols + 1 end
    end
    return cols
end

local function SeatButtons()
    local s = Scale()
    local cols = TotemBar.Cols()
    TB.host:SetSize((2 * TB.PAD + cols * TB.BTN + (cols - 1) * TB.GAP) * s, (TB.PT + TB.BTN + TB.PB) * s)
    for _, button in ipairs(TB.list) do StyleButton(button, TB.BTN * s, s) end
end

local function ApplyButtons()
    local cellCol = TB.COLS
    for i, button in ipairs(TB.list) do
        local def = button.fsDef
        if def.cell then
            -- the cells stand after the six, in order, and a cell that is off hides (Show and Hide are out of combat)
            if CellOn(def) then
                cellCol = cellCol + 1
                button:ClearAllPoints()
                button:SetPoint(TotemBar.SlotPoint(cellCol))
                if FS.TotemDial and FS.TotemDial.ApplyCell then FS.TotemDial.ApplyCell(button, def) end
                UpdateHotkey(button)
                button:Show()
            else
                button:Hide()
            end
        else
            button:ClearAllPoints()
            button:SetPoint(TotemBar.SlotPoint(i))
            if def.slot then ApplyElement(button, def) else ApplyFixed(button, def) end
            UpdateHotkey(button)
            PaintRing(button)
            UpdateTotemSweep(button)
            button:Show()
        end
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

-- Sends the multi-cast picks queued in combat and judges the ones sent but not seen in the slot yet. Out of combat
-- only (SendPick refuses combat). A pick whose slot reads it back is done; one sent more than TB.SETTLE seconds ago
-- that never showed is abandoned and its element falls back to SPELL mode (needsResync), and so is one whose call
-- raised TB.MAX_ATTEMPTS times. The saved pick stays either way.
local function ReplayPicks()
    for key, rec in pairs(TB.pending) do
        local button = TB.byKey[key]
        if not (button and button.fsMode == "action" and button.fsActionId and button.fsList) then
            TB.pending[key] = nil
        else
            local held, readable = ReadSlot(button.fsActionId)
            local entry = EntryById(button.fsList, rec.id)
            if readable and held == rec.id then
                TB.pending[key] = nil
                if entry then ShowPick(button, entry) end
            elseif rec.sent and Settled(rec.at) then
                GiveUp(key, button.fsDef.title, "the multi-cast slot did not take the pick")
            elseif rec.sent then
                ScheduleVerify()
            else
                rec.sent, rec.at = true, Now()
                local landed, called, raised = SendPick(button.fsActionId, rec.id)
                if landed then
                    TB.pending[key] = nil
                    TB.attempts[key] = nil
                    if entry then ShowPick(button, entry) end
                elseif called then
                    TB.attempts[key] = nil
                    ScheduleVerify()
                else
                    rec.sent, rec.at = nil, nil
                    if raised then
                        if CountFailure(key) then
                            GiveUp(key, button.fsDef.title, "the multi-cast call keeps failing")
                        else
                            ScheduleVerify()
                        end
                    end
                end
            end
        end
    end
end

-- What the player knows that decides the modes: the bar's existence and every totem the spellbook or the multi-cast
-- lists name. A change between two syncs is a learn event.
local function KnownSignature()
    local parts = { MultiCastBarActive() and "bar" or "nobar" }
    for _, def in ipairs(TB.BUTTONS) do
        if def.slot then
            local ids = {}
            for _, entry in ipairs(BookTotems(def)) do ids[#ids + 1] = tostring(entry.id) end
            for _, entry in ipairs(MultiCastTotems(def.slot) or {}) do ids[#ids + 1] = "m" .. tostring(entry.id) end
            parts[#parts + 1] = def.key .. "=" .. table.concat(ids, ",")
        end
    end
    return table.concat(parts, ";")
end

-- A learn event (a level, or a changed set of known totems or bar): every element that gave up on its multi-cast
-- slot, and every fill still waiting, gets one fresh try.
local function ForgetFailures()
    TB.spellOnly, TB.fills, TB.attempts = {}, {}, {}
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
    TB.needsResync = false
    local okSig, signature = pcall(KnownSignature)
    if okSig then
        if TB.signature ~= nil and TB.signature ~= signature then ForgetFailures() end
        TB.signature = signature
    end
    for _, step in ipairs({ ReplayPicks, SeatButtons, ApplyButtons, SeatHost }) do
        local ok, err = pcall(step)
        if not ok then WarnOnce("totembar_sync", "totem tab update failed (" .. tostring(err) .. ")") end
    end
    TB.needsResync = false
    if FS.TotemDial and FS.TotemDial.Refresh then
        local ok, err = pcall(FS.TotemDial.Refresh)
        if not ok then WarnOnce("totembar_dial", "totem preset cells failed to paint (" .. tostring(err) .. ")") end
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
TotemBar.FLYOUT = TB.FLYOUT

-- A tile's look: the border violet at rest, the element colour on hover (and a glow), the element colour a little
-- dimmer plus an underline on the current pick. Texture writes only.
local function PaintTile(tile)
    local skin, c = tile.fsSkin, tile.fsColor
    if not (skin and c) then return end
    local v = (FS.Theme and FS.Theme.COLOR_BORDER) or { 0.659, 0.333, 0.969, 1 }
    local ring, glow = skin.border and skin.border.ring, skin.glow
    if tile.fsHover then
        if ring then ring:SetVertexColor(c[1], c[2], c[3], 1) end
        if glow then glow:SetVertexColor(c[1], c[2], c[3], 0.55) end
    elseif tile.fsCurrent then
        if ring then ring:SetVertexColor(c[1], c[2], c[3], 0.75) end
        if glow then glow:SetVertexColor(c[1], c[2], c[3], 0) end
    else
        if ring then ring:SetVertexColor(v[1], v[2], v[3], 0.35) end
        if glow then glow:SetVertexColor(c[1], c[2], c[3], 0) end
    end
    if tile.fsUnderline then tile.fsUnderline:SetShown(tile.fsCurrent and true or false) end
end

-- The pick is made after the picker has closed: a throw inside Pick must never leave the list standing with
-- nothing done.
local function EntryClick(self)
    local picker = TB.picker
    local key, id = picker and picker.fsKey, self.fsSpellID
    if not (key and id) then return end
    ClosePicker()
    TotemBar.Pick(key, id)
end

local function EntryEnter(self)
    self.fsHover = true
    PaintTile(self)
    local tip = GameTooltip
    if not (tip and self.fsSpellID and tip.SetSpellByID) then return end
    tip:SetOwner(self, "ANCHOR_NONE")
    tip:ClearAllPoints()
    tip:SetPoint("LEFT", self, "RIGHT", TB.FLYOUT.TIP_GAP * Scale(), 0)
    tip:SetSpellByID(self.fsSpellID)
    tip:Show()
end

local function EntryLeave(self)
    self.fsHover = false
    PaintTile(self)
    HideTooltip()
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

-- One tile: a plain Button wearing the tab buttons' chrome at the cut 4 (plate, ring, glow, the icon seated in the
-- cut), no text, an underline for the current pick.
local function BuildTile(picker)
    local f = TB.FLYOUT
    local tile = CreateFrame("Button", nil, picker)
    tile:RegisterForClicks("LeftButtonUp")
    tile:SetSize(f.TILE, f.TILE)
    local icon = tile:CreateTexture(nil, "ARTWORK")
    icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    tile.icon = icon
    FS.Theme.SkinButton(tile, { cut = true, chamfer = f.CUT, glowAlpha = 0 })
    FS.FrameHelpers.SeatAuraTile(tile)
    local line = tile:CreateTexture(nil, "OVERLAY", nil, 2)
    line:SetColorTexture(1, 1, 1, 0.95)
    line:Hide()
    tile.fsUnderline = line
    tile:SetScript("OnClick", EntryClick)
    tile:SetScript("OnEnter", EntryEnter)
    tile:SetScript("OnLeave", EntryLeave)
    return tile
end

local function BuildPicker()
    if TB.picker then return TB.picker end
    local picker = CreateFrame("Frame", "FSTotemPicker", UIParent)
    picker:SetFrameStrata("DIALOG")
    picker:EnableMouse(true)
    picker:Hide()
    picker.fsEntries = {}
    for i = 1, TB.MAX_ENTRIES do
        picker.fsEntries[i] = BuildTile(picker)
    end
    picker:SetScript("OnShow", function(self)
        self.fsIdle = 0
        self:SetScript("OnUpdate", PickerIdle)
        -- the owner's piece lights and its chevron points down
        if self.fsOwner then RefreshPiece(self.fsOwner) end
    end)
    picker:SetScript("OnHide", function(self)
        self:SetScript("OnUpdate", nil)
        local owner = self.fsOwner
        self.fsOwner, self.fsKey = nil, nil
        -- the chimney goes with the picker, and the tooltip of a tile the cursor was on
        if FS.TotemPiece and FS.TotemPiece.SetFlyout then FS.TotemPiece.SetFlyout() end
        for _, tile in ipairs(self.fsEntries) do
            if tile.fsHover then
                tile.fsHover = false
                PaintTile(tile)
                HideTooltip()
            end
        end
        -- the owner's piece points up again and goes if the cursor is away
        if owner then
            RefreshPiece(owner)
            HideArrowIfAway(owner)
        end
    end)
    if type(_G.UISpecialFrames) == "table" then table.insert(_G.UISpecialFrames, "FSTotemPicker") end
    TB.picker = picker
    return picker
end

function TotemBar.Picker()
    return TB.picker
end

-- Opens the flyout above an element button with that element's known totems. Plain frames only, so it is legal
-- in combat. A locked element has nothing to list.
function TotemBar.OpenPicker(key)
    local button = TB.byKey[key]
    if not (button and button.fsDef.slot) or not TB.built then return end
    local st = Evaluate(button.fsDef)
    if #st.list == 0 then return end
    local picker = BuildPicker()
    local s = Scale()
    local f = TB.FLYOUT
    local current = st.pick
    local n = math.min(#st.list, TB.MAX_ENTRIES)
    local height = n * f.TILE + (n - 1) * f.GAP + f.TOP_PAD
    local c = button.fsColor
    picker:SetSize((TB.ARROW_W) * s, height * s)
    for i, tile in ipairs(picker.fsEntries) do
        tile:ClearAllPoints()
        local item = st.list[i]
        if item and i <= n then
            tile:SetSize(f.TILE * s, f.TILE * s)
            tile:SetPoint("BOTTOMLEFT", picker, "BOTTOMLEFT", f.PAD * s, (i - 1) * (f.TILE + f.GAP) * s)
            tile.fsSpellID = item.id
            tile.fsColor = c
            tile.fsHover = false
            tile.fsCurrent = current ~= nil and item.id == current.id
            if item.icon then FS.FrameHelpers.SetSpellIcon(tile.icon, item.icon) end
            tile.fsUnderline:SetColorTexture(c[1], c[2], c[3], 0.95)
            tile.fsUnderline:ClearAllPoints()
            tile.fsUnderline:SetPoint("BOTTOMLEFT", tile, "BOTTOMLEFT", 5 * s, 2 * s)
            tile.fsUnderline:SetPoint("BOTTOMRIGHT", tile, "BOTTOMRIGHT", -5 * s, 2 * s)
            tile.fsUnderline:SetHeight(2 * s)
            PaintTile(tile)
            tile:Show()
        else
            tile.fsSpellID = nil
            tile.fsHover = false
            tile:Hide()
        end
    end
    picker:ClearAllPoints()
    picker:SetPoint("BOTTOMLEFT", button, "TOPLEFT", 0, f.RISE * s)
    local previous = picker:IsShown() and picker.fsOwner or nil
    picker.fsOwner, picker.fsKey = button, key
    picker.fsIdle = 0
    -- the piece of the element that had the picker goes back to its hover look, this one's comes up in its open one
    if previous and previous ~= button then
        RefreshPiece(previous)
        HideArrowIfAway(previous)
    end
    ShowArrow(button)
    RefreshPiece(button)
    if FS.TotemPiece and FS.TotemPiece.SetFlyout then FS.TotemPiece.SetFlyout(button.fsCol, height) end
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
-- out of combat; in combat it is queued for regen, and the button keeps showing what the slot holds until the slot
-- reads the pick back. Spell mode rewrites the spell attribute, which waits for regen in combat.
function TotemBar.Pick(key, spellId)
    local button = TB.byKey[key]
    if not (button and button.fsDef.slot and type(spellId) == "number") then return end
    TB.pickSerial = (TB.pickSerial or 0) + 1       -- the set 2 watch drops its window on any pick (PickSerial)
    local entry = button.fsList and EntryById(button.fsList, spellId)
    if not entry then
        local name, icon = SpellById(spellId)
        entry = { id = spellId, name = name or "", icon = icon }
    end
    WritePick(key, entry)
    TB.ownFill[key] = nil       -- an explicit pick is the user's, never the tab's default
    if button.fsMode == "action" and button.fsActionId then
        local previous = TB.pending[key]
        TB.pending[key], TB.attempts[key] = nil, nil
        -- what the slot may still read while this pick is on its way: the totem shown now, the one queued before it
        local ignore = {}
        if button.fsPick then ignore[button.fsPick.id] = true end
        if previous then ignore[previous.id] = true end
        local rec = { id = spellId, ignore = ignore }
        TB.pending[key] = rec
        if InCombatLockdown() then return end
        rec.sent, rec.at = true, Now()
        local landed, called, raised = SendPick(button.fsActionId, spellId)
        if landed then
            TB.pending[key] = nil
            ShowPick(button, entry)
        elseif called then
            ScheduleVerify()
        else
            rec.sent, rec.at = nil, nil
            if raised then
                -- queued for one more try (the next sync, or regen); ReplayPicks gives up on a second failure
                CountFailure(key)
                ScheduleVerify()
            end
        end
    else
        Sync()
    end
end

-------------------------------------------------------------------------------
-- Cells and what the preset code reads (TotemPresets.lua, TotemDial.lua)
-------------------------------------------------------------------------------

-- Adds a cell button after the existing ones. Only before the tab builds (the buttons are built once and their
-- order is the saved keybind order): a late call is refused. A def is { key, title, color, label, enabled = function() }.
function TotemBar.AddCell(def)
    if TB.built or type(def) ~= "table" or type(def.key) ~= "string" or TB.byKey[def.key] then return false end
    for _, other in ipairs(TB.cells) do
        if other.key == def.key then return false end
    end
    def.cell = true
    TB.cells[#TB.cells + 1] = def
    TB.BUTTONS[#TB.BUTTONS + 1] = def
    _G["BINDING_NAME_CLICK FSTotemButton" .. #TB.BUTTONS .. ":LeftButton"] = def.label
    return true
end

function TotemBar.Button(key)
    return TB.byKey[key]
end

-- The cell defs added so far, in order.
function TotemBar.Cells()
    return TB.cells
end

-- The element's totems the player knows right now, as { id (the rank the player knows), name, icon } entries (the
-- picker's own list), or an empty list. Reads only.
function TotemBar.KnownList(key)
    local button = TB.byKey[key]
    if not (button and button.fsDef.slot) then return {} end
    local ok, st = pcall(Evaluate, button.fsDef)
    return ok and st and st.list or {}
end

-- What the element's button casts now: { id, name, icon } or nil.
function TotemBar.CurrentPick(key)
    local button = TB.byKey[key]
    return button and button.fsPick or nil
end

-- The rank 1 totem table of an element: { id, English name } entries in the default order.
function TotemBar.Static(key)
    return TB.TOTEMS[key]
end

TotemBar.ELEMENTS = { "fire", "earth", "water", "air" }

-- The multi-cast helpers the preset code uses for the second set (TotemPresets.lua SyncSet2). Same functions the tab
-- itself uses, so the set 1 rules (out of combat only, read back, pcall) hold for it too.
TotemBar.MC = {
    Bar = MultiCastBar, Active = MultiCastBarActive, ReadSlot = ReadSlot, SendPick = SendPick,
    NativeActionId = NativeActionId, ActionId = ActionId, SET = TB.MC_SET, ANCESTORS_ID = 66843,
    -- the clock and the re-look the picks use: Now() (seconds or nil), Settled(at) (a send made at `at` has had
    -- TB.SETTLE seconds), ScheduleVerify() (one more Sync a moment after a send that has not shown yet)
    Now = Now, Settled = Settled, ScheduleVerify = ScheduleVerify,
    -- a set 1 pick of the element is still on its way / the element uses its spell instead of its slot
    Pending = function(key) return TB.pending[key] ~= nil end,
    -- counts every TotemBar.Pick (the tab's picker and the presets both go through it)
    PickSerial = function() return TB.pickSerial or 0 end,
    SpellOnly = function(key) return TB.spellOnly[key] == true end,
}

local function Build()
    TB.host = CreateFrame("Frame", "FSTotemBar", UIParent)
    TB.host:SetFrameStrata("LOW")
    TB.host:Hide()
    -- the four hidden buttons Shift-right click clicks: type and totem-slot, nothing else, written once here
    -- (out of combat: Build never runs in combat), no mouse, 1 x 1, no regions
    for slot = 1, 4 do
        if not TB.destroy[slot] then
            local hidden = CreateFrame("Button", "FSTotemDestroy" .. slot, TB.host, "SecureActionButtonTemplate")
            hidden:RegisterForClicks("AnyUp", "AnyDown")
            hidden:SetSize(1, 1)
            hidden:SetPoint("BOTTOMLEFT", TB.host, "BOTTOMLEFT", 0, 0)
            hidden:EnableMouse(false)
            hidden:SetAttribute("type", "destroytotem")
            hidden:SetAttribute("totem-slot", slot)
            -- a macro /click sends down=false, and with the ActionButtonUseKeyDown CVar on
            -- SecureActionButton_OnClick would ignore that up-click (clickAction = down and useOnKeyDown, or not
            -- down and not useOnKeyDown). False here makes the up-click the one that counts, whatever the CVar says.
            hidden:SetAttribute("useOnKeyDown", false)
            TB.destroy[slot] = hidden
        end
    end
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
        UpdateAllUsable()
        -- the preset cells start their steps over and read the known totems again before the sync below
        if FS.TotemPresets and FS.TotemPresets.CombatEnded then
            local ok, err = pcall(FS.TotemPresets.CombatEnded)
            if not ok then WarnOnce("totembar_presets", "the totem presets could not start over (" .. tostring(err) .. ")") end
        end
        if TB.pendingSync then
            Sync()
        else
            local ok = pcall(ReplayPicks)
            if not ok then WarnOnce("totembar_replay", "totem tab could not resend a pick") end
            if TB.needsResync then Sync() end
        end
    elseif event == "UPDATE_BINDINGS" then
        UpdateAllHotkeys()
    elseif event == "SPELL_UPDATE_USABLE" or event == "ACTIONBAR_UPDATE_USABLE" or event == "PLAYER_REGEN_DISABLED" then
        UpdateAllUsable()
    elseif event == "SPELL_UPDATE_COOLDOWN" then
        UpdateAllCooldowns()
    elseif event == "PLAYER_TOTEM_UPDATE" then
        UpdateAllSweeps()
    elseif event == "ACTIONBAR_SLOT_CHANGED" or event == "UPDATE_MULTI_CAST_ACTIONBAR" then
        RefreshPicks()
    elseif event == "PLAYER_LEVEL_UP" then
        ForgetFailures()
        Sync()
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
    FS.FrameHelpers.RegisterEvents(events, TB.EVENTS)
    events:RegisterEvent("PLAYER_REGEN_ENABLED")
    events:RegisterEvent("UPDATE_BINDINGS")
    FS.FrameHelpers.RegisterEvents(events, TB.LIVE_EVENTS)
    FS.FrameHelpers.RegisterEvents(events, TB.OPTIONAL_EVENTS)
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
