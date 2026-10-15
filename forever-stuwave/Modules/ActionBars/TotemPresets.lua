-- Forever STUwave: Shaman totem presets (data and rules)
--
-- Design: the two preset mockup. A PRESET is a name (up to 8 letters), up to one totem per element
-- (stored as the rank 1 spell id, the identity TotemBar.lua keeps for every totem) and a DROP ORDER. A character has
-- exactly TWO preset slots, Preset 1 and Preset 2, each with an OUTLINE COLOUR picked from P.COLORS (cyan, pink, violet,
-- amber, green, red, white), saved in ForeverSTUwaveDB.totemPresets[guid] =
--     { slots = { [1] = preset|nil, [2] = preset|nil }, colors = { n1, n2 }, retired = { preset... } }
-- The colour belongs to the cell, not to the preset: clearing a preset keeps it, and a bad or missing colour reads as the
-- slot's default (cyan for Preset 1, pink for Preset 2).
--
--   * Each slot has a cell on the totem tab (FSTotemButton7 for Preset 1, FSTotemButton8 for Preset 2; TotemDial.lua draws
--     them). A click drops the next totem of that slot's preset and nothing is ever switched: both cells are secure buttons
--     whose script is written out of combat from the tab's Sync (TotemDial.lua ApplyCell), so a press works in combat.
--     Editing a preset (fill, reorder, rename, colour, CLEAR) is out of combat only and is refused in combat. An unset slot
--     is a dim cell that does nothing when pressed; Shift click on it makes the preset from the four totem buttons.
--   * STEP: the script behind the click is a cast sequence over the totems the player knows (`/castsequence
--     reset=combat/N totem1, totem2, ...`, N = P.STEP_IDLE); it restarts when combat ends and after P.STEP_IDLE seconds
--     without a press. The progress a cell draws is OUR record, advanced by UNIT_SPELLCAST_SUCCEEDED for the next totem of
--     the sequence (OnCast) and reset the same two ways (ResetSteps, Expire); a stun or a failed cast can leave the game's
--     step off by one from ours until the restart.
--   * LEVELS: an element's totem the character does not know is LOCKED: it shows as a dashed grey arc and a "(level N)"
--     line, the step skips it, and a preset that has only locked totems steps nothing.
--   * SET 2: Preset 2's totems are also written into the native multi-cast set 2 (Call of the Ancestors, level 30) so that
--     spell drops them. SyncSet2 is defensive: out of combat only, only for an element whose set 1 slot is proven to map
--     (the native button agrees with the formula, or the slot holds that element's totem), one attempt per element and
--     spell per session, read back, and the set 1 slots are read before and after: a set 1 slot that changed is restored
--     and set 2 is given up for the session. No chat line; the state line carries the result.
--   * MIGRATION: a file written by the build with the dial (a list of up to four presets, an active index and a GNARLY tie)
--     moves into the two slots once, when the character's store is first read: Preset 1 is the active preset (the first
--     one when the dial rested on the empty slot), Preset 2 is the GNARLY preset when it is a different one, else the first
--     other preset in list order, else unset. Colours start as cyan and pink, as the cells looked before. Presets past two
--     go to `retired` in the same table, unseen, never deleted. A file that already has `slots` is never migrated.
--
-- State line: ForeverSTUwaveDB.totemPresetState.line (on disk after a /reload) names the live unknowns: what each cell's
-- script attribute reads back as, how many presses and matching casts it has seen, and the set 2 result. Neutral words.
--
-- UNVERIFIED in game: that a cast sequence run from a secure button casts totems here and advances only on a cast, that
-- it accepts reset=combat/N, the UNIT_SPELLCAST_SUCCEEDED spell id being plain, and that SetMultiCastSpell on set 2
-- (action ids 4 past set 1) lands and leaves set 1 alone.
--
-- Loads after TotemBar.lua (it adds the cells to the tab at load) and before TotemDial.lua.

local _, FS = ...

local PS = {}
FS.TotemPresets = PS

local function Rgb(hex)
    return { tonumber(hex:sub(1, 2), 16) / 255, tonumber(hex:sub(3, 4), 16) / 255, tonumber(hex:sub(5, 6), 16) / 255, 1 }
end

local P = {
    SLOTS = 2,                  -- preset slots per character
    NAME_MAX = 8,               -- letters in a name ("PRESET 2" fits)
    STEP_IDLE = 6,              -- seconds without a press before the step starts over
    PRESS_WINDOW = 2,           -- seconds after a press in which a matching cast is counted as that press's drop
    SET2_STEP = 4,              -- action ids from a set 1 slot to the same slot of set 2
    SET2_ATTEMPTS = 3,          -- sends of one spell to one set 2 slot (each after TB.SETTLE seconds without it showing)
    ELEMENTS = { "fire", "earth", "water", "air" },
    DEFAULT_ORDER = { "earth", "fire", "water", "air" },    -- the order a new preset gets
    -- the outline colours a cell can wear, in the order the editor's swatches stand; a slot saves the index
    COLORS = {
        { key = "cyan", hex = "22e0ff" }, { key = "pink", hex = "ff2e97" }, { key = "violet", hex = "a855f7" },
        { key = "amber", hex = "ffb648" }, { key = "green", hex = "39ff14" }, { key = "red", hex = "ff3b4e" },
        { key = "white", hex = "f3fbff" },
    },
    DEFAULT_COLOR = { 1, 2 },   -- Preset 1 cyan, Preset 2 pink
    CELL = { preset1 = 1, preset2 = 2 },        -- cell key -> slot
    -- the character level each totem opens at (ForeverDB), by rank 1 spell id; an element's own opening level is the floor
    LEVEL = {
        [8071] = 4, [2484] = 6, [5730] = 8, [8075] = 10, [8143] = 18,
        [3599] = 10, [8181] = 24, [8190] = 26, [8227] = 28,
        [5394] = 20, [8166] = 22, [5675] = 26, [8184] = 28,
        [8177] = 30, [10595] = 30,
    },
    ELEMENT_LEVEL = { fire = 10, earth = 4, water = 20, air = 30 },
    warned = {},
}
for _, color in ipairs(P.COLORS) do color.rgb = Rgb(color.hex) end
PS.P = P

-- Settings, read by the config window; each is explained by its `tip` (a ? icon), never by a helper line. The keys are
-- the ones players already saved (the cells were the dial and GNARLY before).
local SETTINGS = {
    preset1 = {
        key = "totems.dial", default = true, label = "Preset 1",
        tip = "A cell on the totem tab that drops the totems of Preset 1, one per press. It works in combat and starts over "
            .. "after combat ends or a short pause. Shift click edits it, and so does a keybind that includes Shift (which "
            .. "drops no totem, so avoid Shift in its keybind). Off hides it.",
    },
    preset2 = {
        key = "totems.gnarly", default = true, label = "Preset 2",
        tip = "A second cell that drops the totems of Preset 2, one per press. It works in combat and starts over after "
            .. "combat ends or a short pause. Shift click edits it, and so does a keybind that includes Shift (which drops "
            .. "no totem, so avoid Shift in its keybind). Off hides it.",
    },
    plate = {
        key = "totems.dialPlate", default = true, label = "Name plates",
        tip = "Shows each preset's name on a small plate above its cell.",
    },
    set2 = {
        key = "totems.gnarlySet2", default = true, label = "Also on Call of the Ancestors",
        tip = "Puts Preset 2's totems on the Call of the Ancestors set (level 30), so that spell drops them too. "
            .. "Only changes that set, only out of combat. Turning this off leaves set 2 as it is.",
    },
}
PS.SETTINGS = SETTINGS
if FS.Config and FS.Config.RegisterDefault then
    for _, def in pairs(SETTINGS) do FS.Config.RegisterDefault(def.key, def.default) end
end

local function Setting(def)
    local config = FS.Config
    if config and config.Get then
        local value = config.Get(def.key)
        if type(value) == "boolean" then return value end
    end
    return def.default
end
PS.Setting = Setting

local IsSecret = FS.IsSecret

-- One chat line per distinct problem, once per session (LogDegradeOnce does not dedupe).
local function WarnOnce(key, text)
    if P.warned[key] then return end
    P.warned[key] = true
    if FS.LogDegradeOnce then FS.LogDegradeOnce(key, "|cffff4488Forever STUwave|r: " .. text) end
end

local function TotemBar()
    return FS.TotemBar
end

local function SpellById(id)
    local helpers = FS.FrameHelpers
    if helpers and helpers.SpellById then return helpers.SpellById(id) end
end

local function Now()
    if not GetTime then return nil end
    local ok, t = pcall(GetTime)
    if ok and not IsSecret(t) and type(t) == "number" then return t end
end

local function InCombat()
    return InCombatLockdown and InCombatLockdown() and true or false
end

-------------------------------------------------------------------------------
-- Listeners (the cells repaint)
-------------------------------------------------------------------------------

local listeners = {}
function PS.OnEvent(fn)
    if type(fn) == "function" then listeners[#listeners + 1] = fn end
end

local function Notify(what, ...)
    for i = 1, #listeners do
        local ok, err = pcall(listeners[i], what, ...)
        if not ok then WarnOnce("totempresets_listener", "a preset listener failed (" .. tostring(err) .. ")") end
    end
end

-------------------------------------------------------------------------------
-- The saved presets, per character
-------------------------------------------------------------------------------

local function CharKey()
    if UnitGUID then
        local ok, guid = pcall(UnitGUID, "player")
        if ok and not IsSecret(guid) and type(guid) == "string" and guid ~= "" then return guid end
    end
    return nil          -- not readable yet: no key to save under (Store keeps the presets in memory meanwhile)
end

local function ConfigReadOnly()
    local config = FS.Config
    return config and type(config.IsReadOnly) == "function" and config.IsReadOnly() or false
end

-- The rank 1 spell ids of an element, in the default order.
local function BaseIds(element)
    local out = {}
    local tb = TotemBar()
    for _, totem in ipairs(tb and tb.Static and tb.Static(element) or {}) do out[#out + 1] = totem[1] end
    return out
end

local function IsBaseId(element, id)
    for _, base in ipairs(BaseIds(element)) do
        if base == id then return true end
    end
    return false
end

local function CleanName(text)
    text = tostring(text or ""):gsub("[^%a%d ]", ""):gsub("^%s+", ""):gsub("%s+$", "")
    if #text > P.NAME_MAX then text = text:sub(1, P.NAME_MAX) end
    return text:upper()
end
PS.CleanName = CleanName


local function DefaultName(slot)
    return slot and ("PRESET " .. slot) or "NEW"
end

-- A preset as the file may hold it, made plain and consistent: only known ids, an order of exactly the elements with a
-- totem (kept in order, the rest appended), a name that is never empty (PRESET n for slot n). A broken entry becomes nil.
local function Sanitize(entry, slot)
    if type(entry) ~= "table" then return nil end
    local preset = { name = CleanName(entry.name), picks = {}, order = {} }
    if preset.name == "" then preset.name = DefaultName(slot) end
    if type(entry.picks) == "table" then
        for _, element in ipairs(P.ELEMENTS) do
            local id = entry.picks[element]
            if type(id) == "number" and IsBaseId(element, id) then preset.picks[element] = id end
        end
    end
    local seen = {}
    if type(entry.order) == "table" then
        for _, element in ipairs(entry.order) do
            if preset.picks[element] and not seen[element] then
                seen[element] = true
                preset.order[#preset.order + 1] = element
            end
        end
    end
    for _, element in ipairs(P.ELEMENTS) do
        if preset.picks[element] and not seen[element] then preset.order[#preset.order + 1] = element end
    end
    return preset
end

-- A colour index as the file may hold it: a whole number in range, else the slot's default.
local function CleanColor(value, slot)
    if type(value) == "number" and value == math.floor(value) and value >= 1 and value <= #P.COLORS then return value end
    return P.DEFAULT_COLOR[slot]
end

local function EmptyStore()
    return { slots = {}, colors = { P.DEFAULT_COLOR[1], P.DEFAULT_COLOR[2] }, retired = {} }
end

-- Moves a file written by the build with the dial (store.list, store.active, store.gnarly) into the two slots; see the
-- header for the rule. The presets that find no slot go to store.retired in list order.
local function Migrate(store)
    local list = {}
    for _, entry in ipairs(type(store.list) == "table" and store.list or {}) do
        local preset = Sanitize(entry)
        if preset then list[#list + 1] = preset end
    end
    local first = type(store.active) == "number" and list[store.active] and store.active or (list[1] and 1 or nil)
    local second
    if type(store.gnarly) == "number" and list[store.gnarly] and store.gnarly ~= first then
        second = store.gnarly
    else
        for i = 1, #list do
            if i ~= first then
                second = i
                break
            end
        end
    end
    local out = EmptyStore()
    out.slots[1] = first and list[first] or nil
    out.slots[2] = second and list[second] or nil
    for i, preset in ipairs(list) do
        if i ~= first and i ~= second then out.retired[#out.retired + 1] = preset end
    end
    store.slots, store.colors, store.retired = out.slots, out.colors, out.retired
    store.list, store.active, store.gnarly = nil, nil, nil
end

local memory                -- the store of a session that cannot write the database
local clean = {}            -- the character keys whose saved table has been read this session: key -> the table

-- The character's store { slots, colors, retired } and whether it is the saved one. A database that is not a table, a
-- read-only Config, or a character key that cannot be read yet (never saved under a made up one) leaves the presets in
-- memory: readable, never written to disk (every edit is refused there, so the memory store only ever holds a slot).
local function Store()
    local db = _G.ForeverSTUwaveDB
    local key = CharKey()
    if type(db) ~= "table" or ConfigReadOnly() or not key then
        memory = memory or EmptyStore()
        return memory, false
    end
    if type(db.totemPresets) ~= "table" then db.totemPresets = {} end
    local store = db.totemPresets[key]
    if type(store) ~= "table" then
        store = EmptyStore()
        db.totemPresets[key] = store
    end
    if not clean[key] or clean[key] ~= store then
        if type(store.slots) ~= "table" then Migrate(store) end
        local slots = {}
        for slot = 1, P.SLOTS do slots[slot] = Sanitize(store.slots[slot], slot) end
        store.slots = slots
        local colors = type(store.colors) == "table" and store.colors or {}
        store.colors = { CleanColor(colors[1], 1), CleanColor(colors[2], 2) }
        local retired = {}
        for _, entry in ipairs(type(store.retired) == "table" and store.retired or {}) do
            local preset = Sanitize(entry)
            if preset then retired[#retired + 1] = preset end
        end
        store.retired = retired
        clean[key] = store
    end
    return store, true
end

local function ValidSlot(slot)
    return slot == 1 or slot == 2
end

-- The preset in a slot (1 or 2), or nil when the slot is unset.
function PS.Get(slot)
    if not ValidSlot(slot) then return nil end
    return Store().slots[slot]
end

function PS.Writable()
    local _, saved = Store()
    return saved
end

-- The slot a cell key stands for (1 or 2), or nil.
function PS.SlotOf(cell)
    return P.CELL[cell]
end

-- The colour index of a slot (a whole number into P.COLORS); a bad value reads as the slot's default.
function PS.Color(slot)
    if not ValidSlot(slot) then return nil end
    return CleanColor(Store().colors[slot], slot)
end

-- The colour of a slot as { r, g, b, 1 }.
function PS.ColorRgb(slot)
    local index = PS.Color(slot)
    return index and P.COLORS[index].rgb or nil
end

-- true when a slot has nothing to clear: no preset, or one with no totem that still carries its default name.
function PS.IsEmpty(slot)
    local preset = PS.Get(slot)
    if not preset then return true end
    return next(preset.picks) == nil and preset.name == DefaultName(slot)
end

local entriesCache = {}      -- preset table -> its PS.Entries; dropped with the known lists and on every save

local function Save(fn)
    local store, saved = Store()
    fn(store)
    entriesCache = {}
    return saved
end

-------------------------------------------------------------------------------
-- A totem of a preset, against what the character knows
-------------------------------------------------------------------------------

-- The totems of `element` the character knows (TotemBar.KnownList), kept until something that can change it happens: a
-- sync (Dial.Refresh), a learn event, regen. Every cell paint asks for each preset totem, so an uncached spellbook scan
-- per ask would run dozens of times a second.
local knownCache = {}
function PS.InvalidateKnown()
    knownCache = {}
    entriesCache = {}
end

function PS.Known(element)
    local list = knownCache[element]
    if list then return list end
    local tb = TotemBar()
    list = tb and tb.KnownList and tb.KnownList(element) or {}
    if tb and tb.KnownList then knownCache[element] = list end
    return list
end

-- { element, base, name, id, icon, known, level } for the preset's totem of `element` (nil when it has none). `id` and
-- `icon` are the rank the character knows (the id TotemBar.Pick takes); known is false for a totem not learned yet.
function PS.Entry(element, base)
    if not base then return nil end
    local name, icon = SpellById(base)
    if not name then
        for _, totem in ipairs((TotemBar() and TotemBar().Static and TotemBar().Static(element)) or {}) do
            if totem[1] == base then name = totem[2] end
        end
    end
    local entry = { element = element, base = base, name = name or "", icon = icon, known = false,
        level = math.max(P.LEVEL[base] or 0, P.ELEMENT_LEVEL[element] or 0) }
    for _, item in ipairs(PS.Known(element)) do
        if item.name ~= "" and item.name == entry.name then
            entry.known, entry.id, entry.icon = true, item.id, item.icon or icon
            break
        end
    end
    return entry
end

-- The rank 1 id of a known totem entry ({ id, name, icon } from KnownList), or nil.
function PS.BaseOf(element, item)
    local tb = TotemBar()
    for _, totem in ipairs(tb and tb.Static and tb.Static(element) or {}) do
        local name = SpellById(totem[1])
        if totem[1] == item.id or (name and item.name ~= "" and name == item.name) then return totem[1] end
    end
end

-- The preset's totems in drop order: { entry... }, every one of them (locked ones carry known = false).
function PS.Entries(preset)
    if not preset then return {} end
    local out = entriesCache[preset]
    if out then return out end
    out = {}
    for _, element in ipairs(preset.order) do
        local entry = PS.Entry(element, preset.picks[element])
        if entry then out[#out + 1] = entry end
    end
    entriesCache[preset] = out
    return out
end

-- The totems a step drops: the known ones, in drop order.
function PS.Steps(preset)
    local out = {}
    for _, entry in ipairs(PS.Entries(preset)) do
        if entry.known then out[#out + 1] = entry end
    end
    return out
end

-- The script text behind a click, or nil when there is nothing to drop. One totem is a plain cast; more are a cast
-- sequence that restarts when combat ends and after STEP_IDLE seconds.
function PS.StepText(preset)
    local steps = PS.Steps(preset)
    if #steps == 0 then return nil end
    if #steps == 1 then return "/cast " .. steps[1].name end
    local names = {}
    for i, entry in ipairs(steps) do names[i] = entry.name end
    return "/castsequence reset=combat/" .. P.STEP_IDLE .. " " .. table.concat(names, ", ")
end

-------------------------------------------------------------------------------
-- Editing (out of combat only)
-------------------------------------------------------------------------------

-- One refusal reason for an edit, or nil when it may go ahead.
local function Refusal()
    if InCombat() then return "editing waits for combat to end" end
    if not PS.Writable() then
        -- a character key that is only unreadable for now (the database and Config are fine) passes by itself
        if CharKey() == nil and type(_G.ForeverSTUwaveDB) == "table" and not ConfigReadOnly() then
            return "presets will be editable in a moment"
        end
        return "the presets cannot be saved this session"
    end
end
PS.Refusal = Refusal

-- An edit of slot `slot` reached the secure script of its cell: the tab writes it again (out of combat, as edits are).
local function AfterEdit()
    local tb = TotemBar()
    if tb and tb.Sync and not InCombat() then tb.Sync() end
end

-- The step record of a slot's cell starts over (an edit changed what its script drops).
local function ResetSlot(slot)
    PS.ResetSteps("preset" .. slot)
end

-- Makes slot `slot` as a copy of what the four element buttons cast, named PRESET n. Returns the slot, or nil and why (nothing is made when the buttons give no totem).
function PS.Create(slot)
    local why = Refusal()
    if why then return nil, why end
    if not ValidSlot(slot) then return nil, "no such preset" end
    if PS.Get(slot) then return nil, "that preset is already made" end
    local tb = TotemBar()
    local preset = { name = DefaultName(slot), picks = {}, order = {} }
    for _, element in ipairs(P.ELEMENTS) do
        local current = tb and tb.CurrentPick(element)
        local base = current and PS.BaseOf(element, current)
        if base then preset.picks[element] = base end
    end
    for _, element in ipairs(P.DEFAULT_ORDER) do
        if preset.picks[element] then preset.order[#preset.order + 1] = element end
    end
    if #preset.order == 0 then return nil, "no totems to copy" end
    Save(function(store) store.slots[slot] = preset end)
    ResetSlot(slot)
    AfterEdit()
    Notify("edited", slot)
    return slot
end

-- Renames a preset. A name typed on an unset slot makes an empty preset that holds it.
function PS.Rename(slot, text)
    local why = Refusal()
    if why then return false, why end
    if not ValidSlot(slot) then return false, "no such preset" end
    local name = CleanName(text)
    if name == "" then return false, "a name needs a letter" end
    Save(function(store)
        local preset = store.slots[slot]
        if preset then
            preset.name = name
        else
            store.slots[slot] = { name = name, picks = {}, order = {} }
        end
    end)
    Notify("edited", slot)
    return true
end

-- Puts `base` (a rank 1 id, or nil to leave the element out) on the preset. A new totem joins the end of the order. The
-- first totem on an unset slot makes the preset, named PRESET n until a name is typed.
function PS.SetTotem(slot, element, base)
    local why = Refusal()
    if why then return false, why end
    if not ValidSlot(slot) then return false, "no such preset" end
    if not IsBaseId(element, base or BaseIds(element)[1]) then return false, "no such totem" end
    if base == nil and not PS.Get(slot) then return true end
    Save(function(store)
        local preset = store.slots[slot]
        if not preset then
            preset = { name = DefaultName(slot), picks = {}, order = {} }
            store.slots[slot] = preset
        end
        preset.picks[element] = base
        local at
        for i, e in ipairs(preset.order) do
            if e == element then at = i end
        end
        if base and not at then preset.order[#preset.order + 1] = element end
        if not base and at then table.remove(preset.order, at) end
    end)
    ResetSlot(slot)
    AfterEdit()
    Notify("edited", slot)
    return true
end

-- Moves an element up (-1) or down (1) in the drop order.
function PS.Move(slot, element, delta)
    local why = Refusal()
    if why then return false, why end
    local preset = PS.Get(slot)
    if not preset then return false, "no such preset" end
    local at
    for i, e in ipairs(preset.order) do
        if e == element then at = i end
    end
    local to = at and at + delta
    if not to or to < 1 or to > #preset.order then return false, "it cannot move that way" end
    Save(function() preset.order[at], preset.order[to] = preset.order[to], preset.order[at] end)
    ResetSlot(slot)
    AfterEdit()
    Notify("edited", slot)
    return true
end

-- Empties a slot: the totems and the name go, the outline colour stays. An empty slot has nothing to clear.
function PS.Clear(slot)
    local why = Refusal()
    if why then return false, why end
    if not ValidSlot(slot) then return false, "no such preset" end
    if PS.IsEmpty(slot) then return false, "there is nothing to clear" end
    Save(function(store) store.slots[slot] = nil end)
    ResetSlot(slot)
    AfterEdit()
    Notify("edited", slot)
    return true
end

-- Chooses the outline colour of a slot (an index into P.COLORS). Kept when the preset is cleared.
function PS.SetColor(slot, index)
    local why = Refusal()
    if why then return false, why end
    if not ValidSlot(slot) then return false, "no such preset" end
    if CleanColor(index, 0) == nil then return false, "no such colour" end
    Save(function(store) store.colors[slot] = index end)
    Notify("edited", slot)
    return true
end

-- At PLAYER_REGEN_ENABLED: the known totems are read again and every step starts over.
function PS.CombatEnded()
    PS.InvalidateKnown()
    PS.ResetSteps()
    Notify("regen")
end

-------------------------------------------------------------------------------
-- The step: our record of how far the sequence has got
-------------------------------------------------------------------------------

local steps = {}        -- cell key -> { k = totems dropped, at = time of the last press or drop, presses, matched }

local function Track(cell)
    local t = steps[cell]
    if not t then
        t = { k = 0, presses = 0, matched = 0 }
        steps[cell] = t
    end
    return t
end

-- The preset a cell steps: the one in its own slot (nil when the slot is unset).
function PS.CellPreset(cell)
    return PS.Get(P.CELL[cell])
end

-- (done, total) for a cell: how many totems of its sequence have dropped, and how many it has.
function PS.Progress(cell)
    local t = Track(cell)
    local preset = PS.CellPreset(cell)
    local n = #PS.Steps(preset)
    local k = t.k
    if k > n then k = 0 end
    return k, n
end

-- A press on a cell's click.
function PS.NotePress(cell)
    local t = Track(cell)
    t.presses = t.presses + 1
    t.pressAt = Now()
    t.at = t.pressAt
    Notify("step", cell)
end

-- UNIT_SPELLCAST_SUCCEEDED for the player: a totem the sequence was waiting for counts as the next step done, for the
-- cell whose press came just before it (the game advances a sequence only when its own button runs it). A finished
-- sequence starts over at the next drop, as the game's does.
function PS.OnCast(spellId)
    if IsSecret(spellId) then
        P.castIdsSecret = true
        return
    end
    if type(spellId) ~= "number" then return end
    local name = SpellById(spellId)
    if not name then return end
    local now = Now()
    local best, bestAt
    for cell, t in pairs(steps) do
        local list = PS.Steps(PS.CellPreset(cell))
        if #list > 0 and t.pressAt and now and now - t.pressAt <= P.PRESS_WINDOW then
            local from = t.k >= #list and 0 or t.k
            local want = list[from + 1]
            if want and want.name == name and (not bestAt or t.pressAt >= bestAt) then
                best, bestAt = cell, t.pressAt
            end
        end
    end
    if not best then return end
    local t, list = steps[best], PS.Steps(PS.CellPreset(best))
    if t.k >= #list then t.k = 0 end
    t.k = t.k + 1
    t.matched = t.matched + 1
    t.at = now
    t.pressAt = nil
    t.lastName = name
    Notify("step", best)
end

-- Starts the step records over: every cell's, or only `only`'s (a cell key).
function PS.ResetSteps(only)
    local any = false
    for cell, t in pairs(steps) do
        if only == nil or cell == only then
            if t.k ~= 0 then any = true end
            t.k, t.at, t.pressAt = 0, nil, nil
        end
    end
    if any then Notify("step") end
end

-- The idle restart: a started sequence with no press or drop for STEP_IDLE seconds starts over. Called from the cells'
-- ticker; true when anything restarted.
function PS.Expire()
    local now = Now()
    if not now then return false end
    local any = false
    for _, t in pairs(steps) do
        if t.k > 0 and t.at and now - t.at >= P.STEP_IDLE then
            t.k, t.at = 0, nil
            any = true
        end
    end
    if any then Notify("step") end
    return any
end

function PS.Tracker(cell)
    return Track(cell)
end


-------------------------------------------------------------------------------
-- The native multi-cast set 2 (Call of the Ancestors) carries Preset 2
-------------------------------------------------------------------------------

-- state: nil (never looked), "off" (setting off, no preset or nothing to write), "wait" (no bar, set not known or in
-- combat), "ok" (every wanted slot reads back), "partial" (some did not land), "dead" (given up for the session, with
-- `why`). set1Intact: false once a set 1 slot was seen to change under a set 2 write. sent: per set 2 action id, the
-- spell last sent, when, and how many times. check: which set 1 check the last pass ran ("none", "bracket" = set 1
-- read before and after a write, "window" = set 1 against its reading before the sends not judged yet, or both).
-- window: { at, before = { set 1 action id -> spell or false } } while a send is not judged. unproven: wanted
-- slots that could not be judged (unreadable, or holding something that is not a totem of the element).
local set2 = { sent = {}, results = {}, set1Intact = true, wrote = false, check = "none", unproven = 0 }
PS.Set2 = set2

local function Dead(why)
    set2.state, set2.why = "dead", why
end

local function KnowsAncestors(mc)
    local helpers = FS.FrameHelpers
    return helpers and helpers.IsKnownSpellId and helpers.IsKnownSpellId(mc.ANCESTORS_ID, false) or false
end

-- Does the set 1 slot of `element` map as the formula says? The native button agrees with the formula, or (no native
-- button) the slot holds one of the element's own totems.
local function Set1Maps(tb, mc, element, slot, id1)
    local native = mc.NativeActionId(slot)
    if native ~= nil then return native == id1 end
    local held, readable = mc.ReadSlot(id1)
    if not (readable and held) then return false end
    for _, item in ipairs(tb.KnownList(element)) do
        if item.id == held then return true end
    end
    return false
end

-- Does the spell id `held` name a totem of `element` (a known rank or the rank 1 id, or one of the same name)?
local function IsElementTotem(tb, element, held)
    local name = SpellById(held)
    local function same(id, itemName)
        return id == held or (name and itemName ~= "" and itemName == name)
    end
    for _, item in ipairs(PS.Known(element)) do
        if same(item.id, item.name) then return true end
    end
    for _, totem in ipairs(tb.Static and tb.Static(element) or {}) do
        if same(totem[1], SpellById(totem[1]) or "") then return true end
    end
    return false
end

-- A set 2 write can reach set 1 a moment after it returns (the slot updates when the game gets to it). For the
-- window after a send (until the pass that judges it), a set 1 slot that reads other than it did before the send AND
-- reads the spell that was sent to its set 2 twin is that bleed. Any pick through the tab (the picker) ends the window.
-- Returns the work item and the old spell of the slot that bled.
local function Set1Bled(mc, work, window)
    for _, w in ipairs(work) do
        local was = window.before[w.id1]          -- false: the slot was empty
        local rec = set2.sent[w.id2]
        local now, readable = mc.ReadSlot(w.id1)
        if was ~= nil and readable and now ~= (was or nil) and rec and now == rec.spell then
            return w, was or nil
        end
    end
    return nil, nil
end

-- Writes Preset 2's known totems into set 2. Out of combat only. A slot that does not read the wanted spell
-- is sent it again once TB.SETTLE seconds have passed since the last send (at most P.SET2_ATTEMPTS sends of one spell
-- to one slot), and a send that did not show at once schedules a re-look, as the picks do. A slot is written only when
-- it reads back and holds nothing or a totem of its element; anything else is left alone and counted unproven.
function PS.SyncSet2()
    if InCombat() or set2.state == "dead" then return end
    local tb = TotemBar()
    local mc = tb and tb.MC
    local preset = Setting(SETTINGS.preset2) and Setting(SETTINGS.set2) and PS.CellPreset("preset2") or nil
    if not (mc and preset) then
        set2.state = "off"
        return
    end
    local bar = mc.Bar()
    if not (bar and mc.Active() and KnowsAncestors(mc)) then
        set2.state = "wait"
        return
    end
    local work = {}
    for _, entry in ipairs(PS.Steps(preset)) do
        local button = tb.Button(entry.element)
        local slot = button and button.fsDef and button.fsDef.slot
        if slot then
            local id1 = mc.ActionId(bar, slot)
            work[#work + 1] = { element = entry.element, spell = entry.id, slot = slot, id1 = id1,
                id2 = id1 + P.SET2_STEP }
        end
    end
    -- the mapping must be proven for every element before anything is written
    for _, w in ipairs(work) do
        if not Set1Maps(tb, mc, w.element, w.slot, w.id1) then
            Dead("set 1 slot of " .. w.element .. " does not map")
            return
        end
    end
    local before = {}
    for _, w in ipairs(work) do
        local held, readable = mc.ReadSlot(w.id1)
        if not readable then
            set2.state = "wait"      -- set 1 cannot be read, so it could not be proven untouched: write nothing
            return
        end
        before[w.id1] = held
    end
    -- later passes, while a send is not judged yet: set 1 against what it read before the send (the bracket below
    -- only sees one pass)
    set2.check = "none"
    local window = set2.window
    if window and window.serial ~= (mc.PickSerial and mc.PickSerial() or 0) then
        set2.window, window = nil, nil
    end
    if window then
        set2.check = "window"
        local bled, was = Set1Bled(mc, work, window)
        if bled then
            set2.set1Intact = false
            if was then mc.SendPick(bled.id1, was) end
            Dead("a set 1 slot changed after a set 2 write")
            if tb.Sync then tb.Sync() end
            return
        end
        if window and mc.Settled(window.at) then set2.window = nil end
    end
    local wrote, unproven = false, 0
    for _, w in ipairs(work) do
        local held, readable = mc.ReadSlot(w.id2)
        if not readable or (held ~= nil and held ~= w.spell and not IsElementTotem(tb, w.element, held)) then
            unproven = unproven + 1
            set2.results[w.id2] = "unproven"
        elseif held == w.spell then
            set2.results[w.id2] = "landed"
        else
            local rec = set2.sent[w.id2]
            if not rec or rec.spell ~= w.spell then
                rec = { spell = w.spell, n = 0 }
                set2.sent[w.id2] = rec
            end
            if rec.n >= P.SET2_ATTEMPTS then
                set2.results[w.id2] = "gave up"
            elseif rec.n == 0 or mc.Settled(rec.at) then
                rec.n, rec.at = rec.n + 1, mc.Now()
                local landed = mc.SendPick(w.id2, w.spell)
                wrote = true
                set2.results[w.id2] = landed and "landed" or "sent"
                if not landed then mc.ScheduleVerify() end
            end                         -- else the last send is still settling: its re-look is already scheduled
        end
    end
    set2.unproven = unproven
    if wrote then
        set2.wrote = true
        set2.check = set2.check == "window" and "window+bracket" or "bracket"
        local win = set2.window or { before = {} }
        win.at = mc.Now()
        win.serial = mc.PickSerial and mc.PickSerial() or 0
        for id1, held in pairs(before) do
            if win.before[id1] == nil then win.before[id1] = held or false end
        end
        set2.window = win
        -- set 1 must read exactly as before
        for _, w in ipairs(work) do
            local now = select(1, mc.ReadSlot(w.id1))
            if now ~= before[w.id1] then
                set2.set1Intact = false
                if before[w.id1] then mc.SendPick(w.id1, before[w.id1]) end
                Dead("a set 1 slot changed under a set 2 write")
            end
        end
    end
    if set2.state == "dead" then
        if tb.Sync then tb.Sync() end
        return
    end
    local landed, total = 0, 0
    for _, w in ipairs(work) do
        total = total + 1
        local held, readable = mc.ReadSlot(w.id2)
        if readable and held == w.spell then landed = landed + 1 end
    end
    set2.landed, set2.total = landed, total
    set2.state = (total == 0 and "off") or (landed == total and "ok") or "partial"
    if wrote then Notify("set2") end
end

-------------------------------------------------------------------------------
-- The state line for the live test
-------------------------------------------------------------------------------

local lastLine

-- ForeverSTUwaveDB.totemPresetState.line, rewritten when it changes. Never creates or replaces the database and never
-- writes to a read-only Config's, and a database that refuses the write cannot make the caller throw.
local function Write()
    local db = _G.ForeverSTUwaveDB
    if type(db) ~= "table" or ConfigReadOnly() then return end
    local parts = { "presets=" .. ((PS.Get(1) and 1 or 0) + (PS.Get(2) and 1 or 0)), "colors=" .. PS.Color(1) .. "," .. PS.Color(2) }
    for _, cell in ipairs({ "preset1", "preset2" }) do
        local t = Track(cell)
        local button = TotemBar() and TotemBar().Button and TotemBar().Button(cell)
        local kind, len = "none", 0
        if button and button.GetAttribute then
            local ok, type1 = pcall(button.GetAttribute, button, "type1")
            local okText, text = pcall(button.GetAttribute, button, "macrotext1")
            if ok and type(type1) == "string" then kind = type1 end
            if okText and type(text) == "string" then len = #text end
        end
        local k, n = PS.Progress(cell)
        parts[#parts + 1] = string.format("%s type1=%s script=%d step=%d/%d presses=%d casts=%d", cell, kind, len, k, n,
            t.presses, t.matched)
    end
    if P.castIdsSecret then parts[#parts + 1] = "castids=secret" end
    local state = set2.state or "unseen"
    parts[#parts + 1] = "set2=" .. state .. (set2.total and (" " .. set2.landed .. "/" .. set2.total) or "")
        .. (set2.why and (" (" .. tostring(set2.why) .. ")") or "")
        .. ((set2.unproven or 0) > 0 and (" unproven=" .. tostring(set2.unproven)) or "")
        .. " set1Intact=" .. tostring(set2.set1Intact) .. " set1Check=" .. tostring(set2.check)
    local line = table.concat(parts, " | ")
    if line == lastLine and type(db.totemPresetState) == "table" then return end
    lastLine = line
    db.totemPresetState = { line = line }
end

function PS.SaveState()
    local ok, err = pcall(Write)
    if not ok and not P.warned.totempresets_state then
        P.warned.totempresets_state = true
        if FS.LogQuiet then FS.LogQuiet("totempresets_state", "the preset state line could not be saved: " .. tostring(err)) end
    end
end


-------------------------------------------------------------------------------
-- Who has it
-------------------------------------------------------------------------------

-- true for a Shaman whose totem tab is up (the config window shows the group then)
function PS.Applies()
    local tb = TotemBar()
    return tb ~= nil and tb.OwnsShoulder ~= nil and tb.OwnsShoulder() == true
end

-- The cell defs the tab adds after its six buttons: Preset 1 is cell 7, Preset 2 cell 8; each `enabled` is its setting.
-- The def's colour is only the first look before a cell paints: a cell wears the outline colour of its slot.
local function Register()
    local tb = TotemBar()
    if not (tb and tb.AddCell) then return end
    tb.AddCell({
        key = "preset1", title = "Preset 1", color = "22e0ff", label = "Totem preset 1",
        enabled = function() return Setting(SETTINGS.preset1) end,
    })
    tb.AddCell({
        key = "preset2", title = "Preset 2", color = "ff2e97", label = "Totem preset 2",
        enabled = function() return Setting(SETTINGS.preset2) end,
    })
end
Register()
