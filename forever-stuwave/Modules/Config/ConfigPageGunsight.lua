-- Forever STUwave: Config page, Gunsight HUD
-- Three tabs: Pieces (the master switch and the pieces), Target side (areas, tags, the target box bars) and Player side.
-- The class module rows moved to the Class modules page. Keys are today's real ones (Gunsight.PieceConfigKey and the
-- module SETTINGS tables); a module that is absent just leaves its group out.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local Config = FS.Config

local PIECE_ORDER = { "you", "tgt", "dot", "prc", "buff", "shard" }
local PIECE_LABELS = {
    you = "Your cast bar", tgt = "Target cast bar", dot = "Target side areas",
    shard = "Soul shards", prc = "Proc posts", buff = "Buff reminders",
}
local AREA_LABELS = {
    debuffsH = "Target Debuffs Horizontal", debuffsV = "Target Debuffs Vertical", class = "Class Module", empty = "Empty",
}
local MASTER_LABEL = "Gunsight HUD"

local function AreaItems()
    local items = {}
    for i, id in ipairs(FS.Gunsight.AREA_IDS) do items[i] = { value = id, text = AREA_LABELS[id] } end
    return items
end

local function AreaDropdown(content, label, which)
    local Gunsight = FS.Gunsight
    UI.Dropdown(content, {
        label = label,
        get = function() return Gunsight.GetArea(which) end,
        text = function(id) return AREA_LABELS[id] end,
        items = AreaItems,
        set = function(id) Gunsight.SetArea(which, id) end,
        regKey = "gunsight.area." .. which,
    })
end

local CLASS_ICON_TIP = "Shows the target's class icon in a corner tile on the target box when the target is a player. "
    .. "Nothing is drawn for creatures, or when the game hides the class during combat."

local tabs = {
    { key = "pieces", label = "Pieces", build = function(content)
        local Gunsight = FS.Gunsight
        if not (Gunsight and Gunsight.PIECES) then return end
        UI.Section(content, { title = "Gunsight" })
        UI.Toggle(content, {
            label = MASTER_LABEL, key = Gunsight.CONFIG_ENABLED, master = true, reload = Gunsight.NeedsReload,
            tip = "Master switch for the whole HUD. Off hands the cast bars back to the standard ones at once. "
                .. "A Gunsight that was off at login, or the classic combat HUD, needs /reload.",
        })
        UI.Section(content, { title = "Pieces", two = true })
        local known = {}
        for _, key in ipairs(Gunsight.PIECES) do known[key] = true end
        for _, key in ipairs(PIECE_ORDER) do
            if known[key] then
                UI.Toggle(content, {
                    label = PIECE_LABELS[key], key = Gunsight.PieceConfigKey(key),
                    needs = Gunsight.CONFIG_ENABLED, nl = MASTER_LABEL,
                })
            end
        end
    end },
    { key = "target", label = "Target side", build = function(content)
        local Gunsight = FS.Gunsight
        if not (Gunsight and Gunsight.PIECES) then return end
        UI.Section(content, {
            title = "Target side",
            tip = "Target debuffs shows only the debuffs you applied. Class Module shows your class's own resource: soul shards, seals, combo points.",
        })
        AreaDropdown(content, "Upper area", "upper")
        AreaDropdown(content, "Lower area", "lower")
        local Dots = FS.GunsightDots
        if Dots and Dots.SETTINGS and Dots.SETTINGS.keepFallen then
            UI.Toggle(content, {
                label = "Keep fallen-off debuffs as a reapply reminder", key = Dots.SETTINGS.keepFallen.key,
                tip = "When a debuff you applied runs out on your target during a fight, its row or chip stays with a red outline "
                    .. "as a reminder to apply it again. It clears when you reapply it, change target, or the fight ends.",
            })
        end
        local Tags = FS.GunsightTags
        if Tags and Tags.SETTINGS then
            local T = Tags.SETTINGS
            UI.Section(content, { title = "Target box tags", tip = "Small tags on the target info box.", two = true })
            for _, tag in ipairs({
                { "Level and rank", "level" }, { "Player class icon", "classIcon", CLASS_ICON_TIP },
                { "Health percent", "health" }, { "Target of target", "tot" },
            }) do
                local setting = T[tag[2]]
                if setting and setting.key then UI.Toggle(content, { label = tag[1], key = setting.key, tip = tag[3] }) end
            end
        end
        local Boxes = FS.GunsightBoxes
        if Boxes and Boxes.SETTINGS then
            local B = Boxes.SETTINGS
            UI.Section(content, { title = "Target health and resource" })
            UI.Slider(content, {
                label = "Health bar height", key = B.hpHeight.key, min = B.hpHeight.min, max = B.hpHeight.max,
                step = B.hpHeight.step, fmt = "%d px",
            })
            UI.Slider(content, {
                label = "Resource bar height", key = B.powerHeight.key, min = B.powerHeight.min, max = B.powerHeight.max,
                step = B.powerHeight.step, fmt = "%d px",
            })
            UI.Slider(content, {
                label = "Bar width", key = B.width.key, min = B.width.min, max = B.width.max, step = B.width.step,
                fmt = "%d%%", tip = "Percent of the target name width.",
            })
            UI.Toggle(content, { label = "Show numbers", key = B.numbers.key })
            UI.Segmented(content, {
                label = "Number format", key = B.numberFormat.key, options = Boxes.NUMBER_FORMATS, sub = true,
                needs = B.numbers.key, nl = "Show numbers",
                enabled = function() return Config.Get(B.numbers.key) == true end,
            })
        end
    end },
    { key = "player", label = "Player side", build = function(content)
        local Gunsight = FS.Gunsight
        if not (Gunsight and Gunsight.PIECES) then return end
        -- My buffs is deferred to the next release behind FS.Features.myBuffs (set in GunsightMyBuffs.lua); off, it has no row.
        local myBuffs = FS.Features and FS.Features.myBuffs == true
        UI.Section(content, {
            title = "Player side",
            tip = myBuffs and "My buffs is the plate left of the next cast tile. Next cast is the tile for your next spell."
                or "Next cast is the tile for your next spell.",
        })
        if myBuffs then UI.Toggle(content, { label = "My buffs", key = Gunsight.PieceConfigKey("mybuffs") }) end
        UI.Toggle(content, { label = "Next cast", key = Gunsight.PieceConfigKey("next") })
    end },
}

CW.RegisterCategory({ key = "gunsight", label = "Gunsight HUD", group = "SCREEN", order = 1, tabs = tabs })
