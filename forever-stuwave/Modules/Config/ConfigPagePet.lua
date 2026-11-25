-- Forever STUwave: Config page, Pet bar
-- Style tab: which pet the preview shows, the cast bar plate (PetCastBar.lua), then the shared style blocks
-- (ConfigPageBars.lua) for the pet frame. Hunter tab: the happiness dot. Warlock tab: a note.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local Config = FS.Config

local TIPS = {
    kind = "Same frame for every pet. What changes: the power rail colour (focus brown for hunter pets, mana blue for demons), "
        .. "the happiness dot on hunter pets, and whether the cast bar ever has a cast to show.",
    cast = "The plate right of the health and mana. Between casts it shows a faint empty row, as today.",
    show = "Always is today: a faint empty row between casts. While casting hides it between casts. Auto hides it for pets "
        .. "with no cast time spells (hunter pets) and keeps it for demons.",
    free = "Wider stretches the health and mana across the space the cast bar used.",
    happy = "A dot on the name row: green happy, yellow content, red unhappy. An unhappy pet does less damage.",
}

CW.RegisterCategory({
    key = "pet", label = "Pet bar", group = "FRAMES", order = 4,
    tabs = {
        { key = "style", label = "Style", build = function(content)
            local Bars = FS.ConfigBars
            if not Bars then return end
            Bars.BuildStyleTab(content, {
                page = "pet", tab = "style", frames = { "pet" },
                previewTip = "The pet bar as it is drawn with the settings below.",
                before = function(body)
                    UI.Section(body, { title = "Pet" })
                    UI.Segmented(body, { label = "Preview", key = "pet.previewKind", tip = TIPS.kind,
                        options = { { value = "hunter", text = "Hunter pet" }, { value = "demon", text = "Warlock demon" } } })
                    UI.Section(body, { title = "Cast bar", tip = TIPS.cast })
                    UI.Toggle(body, { label = "Cast bar", key = "pet.cast" })
                    UI.Segmented(body, { label = "Show", key = "pet.castShow", sub = true, needs = "pet.cast", nl = "Cast bar", tip = TIPS.show,
                        options = { { value = "always", text = "Always" }, { value = "casting", text = "While casting" }, { value = "auto", text = "Auto" } } })
                    UI.Segmented(body, { label = "When hidden", key = "pet.castFree", sub = true, tip = TIPS.free,
                        when = function() return Config.Get("pet.cast") ~= true or Config.Get("pet.castShow") ~= "always" end,
                        options = { { value = "wider", text = "Wider health and mana" }, { value = "gap", text = "Leave the gap" } } })
                    UI.Toggle(body, { label = "Spell icon", key = "pet.castIcon", sub = true, needs = "pet.cast", nl = "Cast bar" })
                    UI.Toggle(body, { label = "Spell name", key = "pet.castName", sub = true, needs = "pet.cast", nl = "Cast bar" })
                    UI.Toggle(body, { label = "Timer", key = "pet.castTimer", sub = true, needs = "pet.cast", nl = "Cast bar" })
                end,
            })
        end },
        { key = "hunter", label = "Hunter", build = function(content)
            UI.Section(content, { title = "Hunter pet" })
            UI.Toggle(content, { label = "Happiness dot", key = "pet.happy", tip = TIPS.happy })
            UI.Swatch(content, { label = "Colours", sub = true, needs = "pet.happy", nl = "Happiness dot",
                colors = { { { 0, 0.659, 0.110 }, "happy" }, { { 1, 0.824, 0.247 }, "content" }, { { 1, 0.231, 0.306 }, "unhappy" } } })
            UI.Note(content, { text = "Hunter pets use focus, so the power rail is brown, as today." })
        end },
        { key = "warlock", label = "Warlock", build = function(content)
            UI.Section(content, { title = "Demon" })
            UI.Note(content, { text = "Demons use mana, so the power rail is blue. Demon cues are under Class modules, Warlock." })
        end },
    },
})
