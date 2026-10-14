-- Forever STUwave: Shaman totem presets (data and rules)
--
-- Concept C of mockups/totem-presets-2026-10-14.html. A PRESET is a name (up to 8 letters), up to one totem per element
-- (stored as the rank 1 spell id, the identity TotemBar.lua keeps for every totem) and a DROP ORDER. Up to P.MAX
-- presets per character, saved in ForeverSTUwaveDB.totemPresets[guid] = { list = { preset... }, active = n }.
-- An element a preset leaves out keeps its current pick (switching never clears a button) and is skipped by the step.
--
--   * The active preset is the DIAL's (cell 7 of the totem tab, TotemDial.lua). Switching to one picks each of its
--     totems on the element buttons through TotemBar.Pick, the same call the icon picker makes, so the buttons, the
--     native multi-cast set (SET DROP) and the Gunsight poles follow at once. A pick never made twice: an element that
--     already casts the totem is left alone.
--   * Switching changes secure attributes and the multi-cast slots, so it is OUT OF COMBAT ONLY. A switch picked in
--     combat is QUEUED (P.pending, shown by the dial) and applied at PLAYER_REGEN_ENABLED by OnRegen. Editing a preset
--     (create, rename, fill, reorder, delete) is out of combat too and is refused in combat.
--   * The slot past the last preset is a NEW slot while there is room (the dial shows a "+"): selecting it changes
--     nothing, and Shift click on the dial makes a preset there as a copy of the four buttons.
--   * STEP: a click on the dial drops the next totem of the active preset. The script behind the click is a cast
--     sequence over the totems the player knows (`/castsequence reset=combat/N totem1, totem2, ...`, N = P.STEP_IDLE),
--     written to the dial as a secure attribute out of combat (TotemDial.lua ApplyCell); it restarts when combat ends
--     and after P.STEP_IDLE seconds without a press. The progress the dial draws is OUR record, advanced by
--     UNIT_SPELLCAST_SUCCEEDED for the next totem of the sequence (OnCast) and reset the same two ways (ResetSteps,
--     Expire); a stun or a failed cast can leave the game's step off by one from ours until the restart.
--   * LEVELS: an element's totem the character does not know is LOCKED: it shows as a dashed grey arc and a "(level N)"
--     line, the step skips it, and a preset that has only locked totems steps nothing.
--
--   * GNARLY: the second cell (FSTotemButton8, pink) steps ONE preset that never changes with the dial: the character's
--     GNARLY preset (store.gnarly, picked in the settings or by USE AS GNARLY PRESET in the editor). Its script is
--     written out of combat like the dial's and is not touched by a switch, so it is armed in combat whatever the dial
--     is waiting on. It keeps its own step record, attributed to the cell whose press came just before a cast.
--   * SET 2: the GNARLY preset's totems are also written into the native multi-cast set 2 (Call of the Ancestors, level
--     30) so that spell drops them. SyncSet2 is defensive: out of combat only, only for an element whose set 1 slot is
--     proven to map (the native button agrees with the formula, or the slot holds that element's totem), one attempt per
--     element and spell per session, read back, and the set 1 slots are read before and after: a set 1 slot that
--     changed is restored and set 2 is given up for the session. No chat line; the state line carries the result.
--
-- State line: ForeverSTUwaveDB.totemPresetState.line (on disk after a /reload) names the live unknowns: what each cell's
-- script attribute reads back as, how many presses and matching casts it has seen, the preset queue and the set 2
-- result. Neutral words.
--
-- UNVERIFIED in game: that a cast sequence run from a secure button casts totems here and advances only on a cast, that
-- it accepts reset=combat/N, the SOUNDKIT names of the cues, the UNIT_SPELLCAST_SUCCEEDED spell id being plain, and
-- that SetMultiCastSpell on set 2 (action ids 4 past set 1) lands and leaves set 1 alone.
--
-- Loads after TotemBar.lua (it adds the cells to the tab at load) and before TotemDial.lua.

local _, FS = ...

local PS = {}
FS.TotemPresets = PS

local P = {
    MAX = 4,                    -- presets per character
    NAME_MAX = 8,               -- letters in a name
    STEP_IDLE = 6,              -- seconds without a press before the step starts over
    APPLIED_FLASH = 1.6,        -- seconds the changed buttons stay marked after a switch
    PRESS_FLASH = 0.25,         -- seconds the GNARLY cell flashes after a press
    PRESS_WINDOW = 2,           -- seconds after a press in which a matching cast is counted as that press's drop
    SET2_STEP = 4,              -- action ids from a set 1 slot to the same slot of set 2
    SET2_ATTEMPTS = 3,          -- sends of one spell to one set 2 slot (each after TB.SETTLE seconds without it showing)
    ELEMENTS = { "fire", "earth", "water", "air" },
    DEFAULT_ORDER = { "earth", "fire", "water", "air" },    -- the order a new preset gets
    -- the character level each totem opens at (ForeverDB), by rank 1 spell id; an element's own opening level is the floor
    LEVEL = {
        [8071] = 4, [2484] = 6, [5730] = 8, [8075] = 10, [8143] = 18,
        [3599] = 10, [8181] = 24, [8190] = 26, [8227] = 28,
        [5394] = 20, [8166] = 22, [5675] = 26, [8184] = 28,
        [8177] = 30, [10595] = 30,
    },
    ELEMENT_LEVEL = { fire = 10, earth = 4, water = 20, air = 30 },
    -- SOUNDKIT names of the cues; a client without one plays nothing
    SOUND = { waiting = "IG_MAINMENU_OPTION_CHECKBOX_OFF", applied = "IG_MAINMENU_OPTION_CHECKBOX_ON",
        press = "IG_ABILITY_ICON_DROP" },
    warned = {},
}
PS.P = P

-- Settings, read by the config window; each is explained by its `tip` (a ? icon), never by a helper line.
local SETTINGS = {
    dial = {
        key = "totems.dial", default = true, label = "Preset dial",
        tip = "A cell on the totem tab that holds your active totem preset. Click drops the next totem of it, one per "
            .. "press. Shift click edits it, and so does a keybind that includes Shift. Off hides it.",
    },
    dialPlate = {
        key = "totems.dialPlate", default = true, label = "Name plate",
        tip = "Shows the preset's name on a small plate above the dial.",
    },
    dialRight = {
        key = "totems.dialRight", default = true, label = "Cycle with right click",
        tip = "Right click on the dial switches to the next preset. In combat the switch waits until combat ends.",
    },
    dialWheel = {
        key = "totems.dialWheel", default = true, label = "Cycle with mouse wheel",
        tip = "Scrolling over the dial switches to the next or previous preset. In combat the switch waits until combat ends.",
    },
    waitPulse = {
        key = "totems.waitPulse", default = true, label = "Waiting pulse",
        tip = "The dial pulses amber while a switch made in combat waits for combat to end.",
    },
    waitSound = {
        key = "totems.waitSound", default = false, label = "Waiting sound",
        tip = "Plays a short sound when a switch is made in combat and has to wait.",
    },
    appliedFlash = {
        key = "totems.appliedFlash", default = true, label = "Applied flash",
        tip = "Marks the totem buttons that changed for a moment when a preset switch applies.",
    },
    appliedSound = {
        key = "totems.appliedSound", default = false, label = "Applied sound",
        tip = "Plays a short sound when a preset switch applies.",
    },
    gnarly = {
        key = "totems.gnarly", default = true, label = "GNARLY button",
        tip = "Adds a second cell that always drops the preset you choose, one totem per press. It is never switched, "
            .. "so it works in combat. It starts over after combat ends or a short pause. Shift click edits its preset, "
            .. "and so does a keybind that includes Shift (which drops no totem, so avoid Shift in its keybind).",
    },
    gnarlyFlash = {
        key = "totems.gnarlyFlash", default = true, label = "Press flash",
        tip = "The GNARLY cell flashes for a moment each time you press it.",
    },
    gnarlySound = {
        key = "totems.gnarlySound", default = false, label = "Press sound",
        tip = "Plays a short sound each time you press the GNARLY cell.",
    },
    gnarlySet2 = {
        key = "totems.gnarlySet2", default = true, label = "Also on Call of the Ancestors",
        tip = "Puts the GNARLY preset's totems on the Call of the Ancestors set (level 30), so that spell drops them too. "
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
-- Listeners (the dial repaints, the cues play)
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

-- A preset as the file may hold it, made plain and consistent: only known ids, an order of exactly the elements with a
-- totem (kept in order, the rest appended), a name that is never empty. A broken entry becomes nil.
local function Sanitize(entry)
    if type(entry) ~= "table" then return nil end
    local preset = { name = CleanName(entry.name), picks = {}, order = {} }
    if preset.name == "" then preset.name = "NEW" end
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

local memory                -- the store of a session that cannot write the database
local clean = {}            -- the character keys whose saved table has been sanitised this session

-- The character's store { list, active } and whether it is the saved one. A database that is not a table, a
-- read-only Config, or a character key that cannot be read yet (never saved under a made up one) leaves the presets in
-- memory: readable, never written to disk (every edit is refused there, so the memory store only ever holds a slot).
local function Store()
    local db = _G.ForeverSTUwaveDB
    local key = CharKey()
    if type(db) ~= "table" or ConfigReadOnly() or not key then
        memory = memory or { list = {}, active = 1 }
        return memory, false
    end
    if type(db.totemPresets) ~= "table" then db.totemPresets = {} end
    local store = db.totemPresets[key]
    if type(store) ~= "table" then
        store = { list = {}, active = 1 }
        db.totemPresets[key] = store
    end
    if not clean[key] or clean[key] ~= store then
        local list = {}
        for _, entry in ipairs(type(store.list) == "table" and store.list or {}) do
            local preset = Sanitize(entry)
            if preset and #list < P.MAX then list[#list + 1] = preset end
        end
        store.list = list
        if type(store.active) ~= "number" or store.active < 1 or store.active > #list + 1 then store.active = 1 end
        if type(store.gnarly) ~= "number" or not list[store.gnarly] then store.gnarly = nil end
        clean[key] = store
    end
    return store, true
end

function PS.Count()
    return #Store().list
end

function PS.Get(index)
    return Store().list[index]
end

function PS.Writable()
    local _, saved = Store()
    return saved
end

-- Slots the dial turns through: every preset and, while there is room, one NEW slot after them.
function PS.SlotCount()
    local n = PS.Count()
    return n + (n < P.MAX and 1 or 0)
end

-- true when slot `index` is the NEW slot (past the last preset)
function PS.IsNew(index)
    return index > PS.Count()
end

function PS.Active()
    local store = Store()
    local index = store.active
    if index > PS.SlotCount() then index = 1 end
    return index
end

function PS.Pending()
    return P.pending
end

-- The preset the dial shows: the one at the active slot, nil for the NEW slot.
function PS.ActivePreset()
    return PS.Get(PS.Active())
end

function PS.Gnarly()
    return Store().gnarly
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
-- sync (Dial.Refresh), a learn event, regen. The dial repaints ten times a second while a switch waits and every paint
-- asks for each preset totem, so an uncached spellbook scan per ask would run dozens of times a second.
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
    local tb = TotemBar()
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
-- Cues
-------------------------------------------------------------------------------

local function Play(name)
    local kit = _G.SOUNDKIT
    local id = type(kit) == "table" and kit[name]
    if type(id) == "number" and PlaySound then pcall(PlaySound, id) end
end

-------------------------------------------------------------------------------
-- Switching
-------------------------------------------------------------------------------

-- The element buttons that will change when preset `index` applies: { element... }.
function PS.WouldChange(index)
    local out = {}
    local preset = PS.Get(index)
    if not preset then return out end
    local tb = TotemBar()
    for _, element in ipairs(P.ELEMENTS) do
        local entry = PS.Entry(element, preset.picks[element])
        if entry and entry.known then
            local current = tb.CurrentPick(element)
            if not (current and current.id == entry.id) then out[#out + 1] = element end
        end
    end
    return out
end

-- Applies slot `index` out of combat: every totem of the preset the character knows is picked on its element button
-- unless the button already casts it. The slot becomes the saved active one. Returns the elements that changed.
local function ApplySlot(index)
    local changed = PS.WouldChange(index)
    local tb = TotemBar()
    local preset = PS.Get(index)
    for _, element in ipairs(changed) do
        local entry = PS.Entry(element, preset.picks[element])
        tb.Pick(element, entry.id)
    end
    Save(function(store) store.active = index end)
    if tb.Sync then tb.Sync() end
    return changed
end

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

-- Switches the dial to slot `index`. In combat the switch is queued and the dial shows it as pending.
function PS.Select(index)
    local slots = PS.SlotCount()
    if type(index) ~= "number" or index < 1 or index > slots then return false end
    if InCombat() then
        if index == PS.Active() then
            P.pending = nil
        elseif P.pending ~= index then
            P.pending = index
            if Setting(SETTINGS.waitSound) then Play(P.SOUND.waiting) end
        end
        Notify("pending", P.pending)
        return "queued"
    end
    P.pending = nil
    local changed = ApplySlot(index)
    P.applied = { at = Now(), elements = changed }
    if #changed > 0 and Setting(SETTINGS.appliedSound) then Play(P.SOUND.applied) end
    PS.ResetSteps()
    Notify("applied", changed)
    return "applied"
end

-- The next (dir 1) or previous (dir -1) slot, from the pending one when a switch is waiting.
function PS.Cycle(dir)
    local slots = PS.SlotCount()
    local from = P.pending or PS.Active()
    local index = ((from - 1 + (dir or 1)) % slots) + 1
    return PS.Select(index)
end

-- At PLAYER_REGEN_ENABLED: the queued switch applies, and every step starts over.
function PS.OnRegen()
    PS.InvalidateKnown()
    PS.ResetSteps()
    local index = P.pending
    if index then
        P.pending = nil
        if index <= PS.SlotCount() then
            local changed = ApplySlot(index)
            P.applied = { at = Now(), elements = changed }
            if #changed > 0 and Setting(SETTINGS.appliedSound) then Play(P.SOUND.applied) end
            Notify("applied", changed)
            return
        end
    end
    Notify("regen")
end

-- The active preset changed under the dial (an edit): its totems are picked again (changed ones only).
local function Reapply()
    if InCombat() then return end
    local index = PS.Active()
    if PS.IsNew(index) then
        local tb = TotemBar()
        if tb and tb.Sync then tb.Sync() end
        return
    end
    ApplySlot(index)
end

-------------------------------------------------------------------------------
-- Editing (out of combat only)
-------------------------------------------------------------------------------

-- An edit of preset `index` reached the buttons that carry it: the dial's active one is picked again, and the GNARLY
-- cell's script is written again when it steps this preset.
local function AfterEdit(index)
    if index == PS.Active() then
        Reapply()
    elseif index == PS.Gnarly() then
        local tb = TotemBar()
        if tb and tb.Sync and not InCombat() then tb.Sync() end
    end
end

-- Makes a preset in the NEW slot as a copy of what the four element buttons cast. Returns its index, or nil and why.
function PS.Create()
    local why = Refusal()
    if why then return nil, why end
    if PS.Count() >= P.MAX then return nil, "there is no room for another preset" end
    local tb = TotemBar()
    local preset = { name = "NEW", picks = {}, order = {} }
    for _, element in ipairs(P.ELEMENTS) do
        local current = tb and tb.CurrentPick(element)
        local base = current and PS.BaseOf(element, current)
        if base then preset.picks[element] = base end
    end
    for _, element in ipairs(P.DEFAULT_ORDER) do
        if preset.picks[element] then preset.order[#preset.order + 1] = element end
    end
    local index
    Save(function(store)
        store.list[#store.list + 1] = preset
        index = #store.list
        store.active = index
    end)
    PS.ResetSteps()
    Reapply()
    Notify("edited", index)
    return index
end

-- Is there room for another preset (the cap is P.MAX)?
function PS.HasRoom()
    return PS.Count() < P.MAX
end

-- Shift click on an unset GNARLY: makes an EMPTY preset, ties it as the GNARLY preset and returns its index (nil and
-- why when it cannot). The dial's active slot is not changed: when the dial sat on the NEW slot it stays on the NEW slot
-- that follows the new preset (or, with none left, on the first preset, as PS.Active clamps it anyway). Nothing is
-- applied to the buttons: the player's picks and the set 1 slots stay as they are.
function PS.CreateGnarly()
    local why = Refusal()
    if why then return nil, why end
    if not PS.HasRoom() then return nil, "there is no room for another preset" end
    local wasNew = PS.IsNew(PS.Active())
    local index
    Save(function(store)
        store.list[#store.list + 1] = { name = "NEW", picks = {}, order = {} }
        index = #store.list
        store.gnarly = index
        if wasNew then store.active = index < P.MAX and index + 1 or 1 end
    end)
    PS.ResetSteps("gnarly")                   -- the dial's step record is not touched
    local tb = TotemBar()
    if tb and tb.Sync then tb.Sync() end
    Notify("edited", index)
    return index
end

function PS.Rename(index, text)
    local why = Refusal()
    if why then return false, why end
    local preset = PS.Get(index)
    local name = CleanName(text)
    if not preset or name == "" then return false, "a name needs a letter" end
    Save(function() preset.name = name end)
    Notify("edited", index)
    return true
end

-- Puts `base` (a rank 1 id, or nil to leave the element out) on the preset. A new totem joins the end of the order.
function PS.SetTotem(index, element, base)
    local why = Refusal()
    if why then return false, why end
    local preset = PS.Get(index)
    if not preset or not IsBaseId(element, base or BaseIds(element)[1]) then return false, "no such totem" end
    Save(function()
        preset.picks[element] = base
        local at
        for i, e in ipairs(preset.order) do
            if e == element then at = i end
        end
        if base and not at then preset.order[#preset.order + 1] = element end
        if not base and at then table.remove(preset.order, at) end
    end)
    PS.ResetSteps()
    AfterEdit(index)
    Notify("edited", index)
    return true
end

-- Moves an element up (-1) or down (1) in the drop order.
function PS.Move(index, element, delta)
    local why = Refusal()
    if why then return false, why end
    local preset = PS.Get(index)
    if not preset then return false, "no such preset" end
    local at
    for i, e in ipairs(preset.order) do
        if e == element then at = i end
    end
    local to = at and at + delta
    if not to or to < 1 or to > #preset.order then return false, "it cannot move that way" end
    Save(function() preset.order[at], preset.order[to] = preset.order[to], preset.order[at] end)
    PS.ResetSteps()
    AfterEdit(index)
    Notify("edited", index)
    return true
end

function PS.Delete(index)
    local why = Refusal()
    if why then return false, why end
    if not PS.Get(index) then return false, "no such preset" end
    Save(function(store)
        table.remove(store.list, index)
        if store.active > index then store.active = store.active - 1 end
        if store.gnarly == index then store.gnarly = nil elseif store.gnarly and store.gnarly > index then store.gnarly = store.gnarly - 1 end
        if store.active > #store.list + (#store.list < P.MAX and 1 or 0) then store.active = 1 end
    end)
    P.pending = nil
    PS.ResetSteps()
    Reapply()
    Notify("edited", index)
    return true
end

-- The settings dropdown's entries for the GNARLY preset: { value, text } with 0 for none, and the name of a value.
function PS.GnarlyChoices()
    local out = { { value = 0, text = "None" } }
    for i = 1, PS.Count() do out[#out + 1] = { value = i, text = i .. " " .. PS.Get(i).name } end
    return out
end

function PS.GnarlyName(value)
    local preset = value and value ~= 0 and PS.Get(value) or nil
    return preset and (value .. " " .. preset.name) or "None"
end

-- Ties the GNARLY cell to preset `index` (nil unties it). Out of combat only: its script is a secure attribute.
function PS.SetGnarly(index)
    local why = Refusal()
    if why then return false, why end
    if index ~= nil and not PS.Get(index) then return false, "no such preset" end
    Save(function(store) store.gnarly = index end)
    PS.ResetSteps()
    local tb = TotemBar()
    if tb and tb.Sync then tb.Sync() end
    Notify("edited", index)
    return true
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

-- The preset a cell steps: the dial's is the active one (nil on the NEW slot), the GNARLY cell's is its own.
function PS.CellPreset(cell)
    if cell == "dial" then return PS.ActivePreset() end
    if cell == "gnarly" then
        local index = PS.Gnarly()
        return index and PS.Get(index) or nil
    end
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
    if cell == "gnarly" and Setting(SETTINGS.gnarlySound) then Play(P.SOUND.press) end
    Notify("step", cell)
end

-- Seconds since the cell was last pressed, or nil when it never was.
function PS.PressAge(cell)
    local t = steps[cell]
    local now = Now()
    if not (t and t.pressAt and now) then return nil end
    return now - t.pressAt
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

-- The idle restart: a started sequence with no press or drop for STEP_IDLE seconds starts over. Called from the dial's
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
-- The native multi-cast set 2 (Call of the Ancestors) carries the GNARLY preset
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

-- Does the active preset want the totem `held` on the element's set 1 button (a change to it is a pick, not a bleed)?
local function WantedOnSet1(element, held)
    local active = PS.Get(PS.Active())
    local entry = active and PS.Entry(element, active.picks[element])
    return entry ~= nil and entry.id == held
end

-- A set 2 write can reach set 1 a moment after it returns (the slot updates when the game gets to it). For the
-- window after a send (until the pass that judges it), a set 1 slot that reads other than it did before the send AND
-- reads the spell that was sent to its set 2 twin is that bleed, unless the active preset wants that totem there (then
-- it is counted unproven, never restored). Any pick through the tab (a preset switch or the picker) ends the window. The tab's own picks cannot say: it adopts whatever
-- its slot holds as the pick, so a comparison with the pick sees nothing. Returns the work item and the old spell.
local function Set1Bled(mc, work, window)
    local legit = 0
    for _, w in ipairs(work) do
        local was = window.before[w.id1]          -- false: the slot was empty
        local rec = set2.sent[w.id2]
        local now, readable = mc.ReadSlot(w.id1)
        if was ~= nil and readable and now ~= (was or nil) and rec and now == rec.spell then
            if WantedOnSet1(w.element, now) then
                legit = legit + 1                 -- the dial's preset wants this totem there: not a bleed
            else
                return w, was or nil, legit
            end
        end
    end
    return nil, nil, legit
end

-- Writes the GNARLY preset's known totems into set 2. Out of combat only. A slot that does not read the wanted spell
-- is sent it again once TB.SETTLE seconds have passed since the last send (at most P.SET2_ATTEMPTS sends of one spell
-- to one slot), and a send that did not show at once schedules a re-look, as the picks do. A slot is written only when
-- it reads back and holds nothing or a totem of its element; anything else is left alone and counted unproven.
function PS.SyncSet2()
    if InCombat() or set2.state == "dead" then return end
    local tb = TotemBar()
    local mc = tb and tb.MC
    local preset = Setting(SETTINGS.gnarly) and Setting(SETTINGS.gnarlySet2) and PS.CellPreset("gnarly") or nil
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
    local legit = 0
    if window and window.serial ~= (mc.PickSerial and mc.PickSerial() or 0) then
        set2.window, window = nil, nil
    end
    if window then
        set2.check = "window"
        local bled, was
        bled, was, legit = Set1Bled(mc, work, window)
        if legit > 0 then set2.window, window = nil, nil end
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
    set2.unproven = unproven + legit
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
    local parts = { "presets=" .. PS.Count(), "active=" .. PS.Active(), "pending=" .. tostring(P.pending) }
    for _, cell in ipairs({ "dial", "gnarly" }) do
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
        .. (set2.why and (" (" .. set2.why .. ")") or "") .. (set2.unproven > 0 and (" unproven=" .. set2.unproven) or "")
        .. " set1Intact=" .. tostring(set2.set1Intact) .. " set1Check=" .. set2.check
    local line = table.concat(parts, " | ")
    if line == lastLine and type(db.totemPresetState) == "table" then return end
    lastLine = line
    db.totemPresetState = { line = line, active = PS.Active(), pending = P.pending }
end

function PS.SaveState()
    if not pcall(Write) then WarnOnce("totempresets_state", "the preset state line could not be saved") end
end

-------------------------------------------------------------------------------
-- Who has it
-------------------------------------------------------------------------------

-- true for a Shaman whose totem tab is up (the config window shows the group then)
function PS.Applies()
    local tb = TotemBar()
    return tb ~= nil and tb.OwnsShoulder ~= nil and tb.OwnsShoulder() == true
end

-- The cell defs the tab adds after its six buttons. The dial is cell 7; its `enabled` is the setting.
local function Register()
    local tb = TotemBar()
    if not (tb and tb.AddCell) then return end
    tb.AddCell({
        key = "dial", title = "Preset dial", color = "22e0ff", label = "Totem preset dial",
        enabled = function() return Setting(SETTINGS.dial) end,
    })
    tb.AddCell({
        key = "gnarly", title = "GNARLY", color = "ff2e97", label = "Totem GNARLY preset", hot = true,
        enabled = function() return Setting(SETTINGS.gnarly) end,
    })
end
Register()
