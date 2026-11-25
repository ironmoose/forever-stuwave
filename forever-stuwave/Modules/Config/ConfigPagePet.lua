-- Forever STUwave: Config page, Pet bar
-- Style tab: the preview (the pet panel drawn by PetFrame.lua, PetCastBar.lua and PetDock.lua) with the pet kind picker
-- in its header, the cast bar plate rows (PetCastBar.lua), then the shared style blocks (ConfigPageBars.lua) for the pet
-- frame. Width and the bar heights are the dock's while the bar sits beside the Console, so those rows grey with a
-- reason then. Hunter tab: the happiness dot. Warlock tab: a note.

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI
local Config = FS.Config

local KINDS = {
    { value = "hunter", text = "Hunter pet" },
    { value = "demon", text = "Warlock demon" },
}

-- The shared rows the pet frame applies (PetFrame.lua ApplyStyle). The glow rows are the rest of the shared set: the pet
-- dock draws its own edge, so they stay greyed.
local APPLIED = { "w", "fh", "alpha", "bgAlpha", "hpStyle", "hpH", "hpFmt", "hpTs", "hpTa", "hpTx",
    "mpStyle", "mpH", "mpFmt", "mpTs", "mpTa", "mpTx", "name", "nameSize", "nameX", "level", "levelSize", "levelX" }

-- The rows the Console dock sizes while the pet bar sits beside it.
local DOCK_SIZED = { "bars.w", "bars.fh", "bars.hpH", "bars.mpH" }

local TIPS = {
    kind = "Same frame for every pet. What changes: the power rail colour (focus brown for hunter pets, mana blue for demons), "
        .. "the happiness dot on hunter pets, and whether the cast bar ever has a cast to show.",
    cast = "The plate right of the health and mana. Between casts it shows a faint empty row, as today.",
    show = "Always is today: a faint empty row between casts. While casting hides it between casts. Auto hides it for pets "
        .. "with no cast time spells (hunter pets) and keeps it for demons.",
    free = "Wider stretches the health and mana across the room the cast bar leaves. That only happens when the cast bar is "
        .. "gone for good: switched off, or a hunter pet with Show on While casting or Auto. A demon that casts keeps its "
        .. "room. Leave the gap keeps the width as it is.",
    happy = "A dot on the name row: green happy, yellow content, red unhappy. An unhappy pet does less damage.",
}
-- The first line of the ? tip while the row is greyed.
local DOCK_REASON = "The pet bar sits beside the Console, which sets its size. Without the Console it floats and this applies."

local Bars = FS.ConfigBars
if Bars and Bars.WIRED then
    local wired = Bars.WIRED.pet or {}
    Bars.WIRED.pet = wired
    for _, suffix in ipairs(APPLIED) do wired[suffix] = true end
end

-- Greys the dock sized rows while the pet bar is docked. The shared builder gave each row an enabled() (the applied list
-- above); this one asks the dock first and leaves the rest to it.
local function LockWhileDocked()
    for _, key in ipairs(DOCK_SIZED) do
        local entry = CW.RowByKey(key, "pet")
        local opts = entry and entry.opts
        if opts then
            local shared = opts.enabled
            opts.enabled = function()
                local pet = FS.PetFrame
                if pet and pet.IsDocked and pet.IsDocked() then
                    opts.reason = DOCK_REASON
                    return false
                end
                if shared then return shared() end
                return true
            end
        end
    end
end

-- The preview: the pet panel drawn by the real pet frame code.
if Bars and Bars.RegisterFrame then
    Bars.RegisterFrame({
        key = "pet", label = "Pet",
        preview = function(stage)
            local pet = FS.PetFrame
            if not (pet and pet.NewStylePreview) then return nil end
            return pet.NewStylePreview(stage)
        end,
    })
end

CW.RegisterCategory({
    key = "pet", label = "Pet bar", group = "FRAMES", order = 4,
    tabs = {
        { key = "style", label = "Style", build = function(content)
            local Bars = FS.ConfigBars
            if not Bars then return end
            Bars.BuildStyleTab(content, {
                page = "pet", tab = "style", frames = { "pet" },
                previewTip = "The pet bar as it is drawn with the settings below, for the kind of pet picked here. Pointing at a setting turns that feature on here for a moment.",
                -- which pet the preview shows, in the preview header
                header = function(band)
                    local buttons, prev = {}, nil
                    for index = #KINDS, 1, -1 do
                        local kind = KINDS[index]
                        local b = Bars.PickerButton(band, kind.text)
                        if prev then b:SetPoint("RIGHT", prev, "LEFT", -CW.Spec.SEG_GAP, 0) else b:SetPoint("TOPRIGHT", band, "TOPRIGHT", 0, -2) end
                        b:SetScript("OnClick", function() Config.Set("pet.previewKind", kind.value); CW.RefreshAll() end)
                        buttons[kind.value] = b
                        prev = b
                    end
                    local label = CW.I.Label(band, "Pet", CW.Spec.TEXT, CW.C.muted)
                    label:SetPoint("RIGHT", prev, "LEFT", -CW.Spec.CTL_GAP, 0)
                    CW.I.Track(function()
                        for value, b in pairs(buttons) do Bars.MarkPicker(b, Config.Get("pet.previewKind") == value) end
                    end)
                    local tip = UI.HelpIcon(band, TIPS.kind)
                    tip:SetPoint("RIGHT", label, "LEFT", -CW.Spec.Q_GAP, 0)
                end,
                before = function(body)
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
            LockWhileDocked()
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
