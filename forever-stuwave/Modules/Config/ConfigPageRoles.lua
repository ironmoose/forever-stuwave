-- Forever STUwave: Config page, Roles
-- Four tabs (Tank, Healer, Melee, Ranged). Every tab carries the same pinned "Your role" bar: Auto (your group role, else your
-- talents, else your class) or a hand pick, with what Auto chose beside the label. A section is tagged YOUR ROLE (cyan) when
-- it belongs to the role in use and "<ROLE> ONLY" (amber) when it belongs to another; the rows of another role stay
-- editable, they act once that role is the one in use. The tab of the role in use carries a small cyan arrow.
-- The settings live in Core/Role.lua (FS.Role.SETTINGS), the plate side in Modules/Nameplates/PlateThreat.lua.
-- Left out of the page when the role module is absent; the swatch rows when the plate threat module is.

local _, FS = ...

local CW = FS.ConfigWindow
local UI, I, C, S = CW.UI, CW.I, CW.C, CW.Spec
local Theme = FS.Theme

local BAR_H = 24            -- the pinned bar: the segmented control is S.SEG_H tall
local ARROW_GAP = 2         -- tab label to the arrow (the arrow sits in the tab's right padding)

-- The prototype's words (mockups/proto-src-2026-11-25/proto-pages.js, page "role").
local TIP_ROLE = "Auto uses your group role when one is set, else your talents: most points in Enhancement makes you Melee. "
    .. "Pick one to override it, for example when you heal a dungeon. Settings of the other roles wait until you switch. "
    .. "Saved per character."
local TIP_PLATES = "Colours the health bar by who the mob is hitting."
local TIP_THREAT = "Aggro % = your share of the mob's threat, 100 means it is on you. Lead = how far ahead of the next player you are."
local TIP_LOST = "Flashes the plate when a mob you had turns to someone else."
local TIP_HEALTH = "Missing = how much health they are down."
local TIP_WARN = "Before you pull the mob off the tank."

local function Ready()
    local Role = FS.Role
    return Role ~= nil and Role.SETTINGS ~= nil and Role.PICKS ~= nil and FS.Config ~= nil
end

local function RoleNow()
    return FS.Role and (FS.Role.Current())
end

-------------------------------------------------------------------------------
-- The pinned role bar
-------------------------------------------------------------------------------

local barRegistered = false

-- "Your role" is one row for search whichever tab was built first; the others only draw.
local function ForgetEntry(entry)
    for index, item in ipairs(I.registry) do
        if item == entry then
            table.remove(I.registry, index)
            return
        end
    end
end

-- The band on top of the tab: the label and its ? on the left (with what Auto chose in cyan), the five picks on the right.
-- The control is a real UI.Segmented built into the tab and then taken out of the flow and seated in the band, so the
-- registry, the refresh and the ? tip are the ones every row has.
local function RoleBar(content)
    local Role = FS.Role
    local band = UI.Band(content, BAR_H)
    if not band then return end
    local options = {}
    for _, pick in ipairs(Role.PICKS) do
        options[#options + 1] = { value = pick, text = pick == "auto" and "Auto" or Role.TEXT[pick] }
    end
    local row = UI.Segmented(content, {
        label = "Your role", regKey = "role", options = options, nodot = true, height = BAR_H, size = S.SMALL,
        tip = TIP_ROLE, get = Role.Pick, set = Role.SetPick,
    })
    local owner = I.FlowOwner(content)
    local flow = owner and owner.fsFlow
    if flow and row.fsItem then
        for index = #flow, 1, -1 do
            if flow[index] == row.fsItem then
                table.remove(flow, index)
                break
            end
        end
        row.fsItem.y = 0
    end
    if barRegistered then
        if row.fsEntry then ForgetEntry(row.fsEntry) end
    else
        barRegistered = true
    end
    row:SetParent(band)
    row:ClearAllPoints()
    row:SetPoint("TOPLEFT", band, "TOPLEFT", 0, 0)
    row:SetPoint("TOPRIGHT", band, "TOPRIGHT", 0, 0)
    row:Show()
    row.fsLabel:SetText("YOUR ROLE")
    Theme.ApplyMono(row.fsLabel, S.SMALL, C.muted)
    local summary = I.Label(row, "", S.SMALL, C.cyan)
    summary:SetPoint("LEFT", row.fsHelp or row.fsLabel, "RIGHT", 8, 0)
    I.Track(function()
        summary:SetText(Role.Summary() or "")
        if row.fsHelp then row.fsHelp.fsTip = TIP_ROLE .. "\n" .. Role.Why() end
    end)
end

-------------------------------------------------------------------------------
-- Sections and rows
-------------------------------------------------------------------------------

-- A section of one role: its title, and the tag of the header (YOUR ROLE when it is the role in use, else "<ROLE> ONLY").
local function RoleSection(content, title, role, tip)
    local sec = UI.Section(content, { title = title, tip = tip })
    I.Track(function()
        local mine = RoleNow() == role
        sec.SetMeta(mine and "YOUR ROLE" or (FS.Role.TEXT[role]:upper() .. " ONLY"))
        Theme.ApplyMono(sec.meta, S.SMALL, mine and C.cyan or C.amber)
    end)
    return sec
end

local function Switch(content, key, label, extra)
    if not FS.Role.SETTINGS[key] then return end
    local o = { label = label, key = key }
    for name, value in pairs(extra or {}) do o[name] = value end
    UI.Toggle(content, o)
end

local function Choice(content, key, label, extra)
    local def = FS.Role.SETTINGS[key]
    if not def then return end
    local o = { label = label, key = key, options = def.options }
    for name, value in pairs(extra or {}) do o[name] = value end
    UI.Segmented(content, o)
end

local function Sub(key, label)
    return { sub = true, needs = key, nl = label }
end

local function Colours(content, role, key, label)
    local threat = FS.PlateThreat
    local swatches = threat and threat.SWATCHES and threat.SWATCHES[role]
    if not swatches then return end
    UI.Swatch(content, { label = "Colours", sub = true, colors = swatches, needs = key, nl = label })
end

local function Warn(content, role)
    local s = FS.Role.SETTINGS
    local warn, pct = role .. ".warn", role .. ".pct"
    Switch(content, warn, "Warn near the tank", { tip = TIP_WARN })
    local def = s[pct]
    if def then
        UI.Slider(content, { label = "Warn at", key = pct, min = def.min, max = def.max, step = def.step, fmt = "%d%%",
            sub = true, needs = warn, nl = "Warn near the tank" })
    end
    Switch(content, role .. ".aggro", "Aggro colours")
    Colours(content, role, role .. ".aggro", "Aggro colours")
end

local BUILD = {}

function BUILD.tank(content)
    RoleSection(content, "Aggro on plates", "tank", TIP_PLATES)
    Switch(content, "tank.aggro", "Aggro colours")
    Colours(content, "tank", "tank.aggro", "Aggro colours")
    Choice(content, "tank.threat", "Threat text", { tip = TIP_THREAT })
    RoleSection(content, "Alerts", "tank")
    Switch(content, "tank.lost", "Lost aggro", { tip = TIP_LOST })
    Switch(content, "tank.lost.snd", "Sound", Sub("tank.lost", "Lost aggro"))
end

function BUILD.healer(content)
    RoleSection(content, "Party frames", "healer")
    Switch(content, "heal.incoming", "Incoming heals")
    Switch(content, "heal.range", "Fade out of range")
    Switch(content, "heal.dispel", "Highlight what I can dispel")
    -- The party frames show the percent today; the missing amount is not drawn yet, so the row says so instead of doing nothing
    Choice(content, "heal.hp", "Health text", { tip = TIP_HEALTH, enabled = function() return false end,
        reason = "Not applied yet: the party frames show the percent for now." })
    RoleSection(content, "Alerts", "healer")
    Switch(content, "heal.aggro", "A mob turns to me")
    Switch(content, "heal.aggro.snd", "Sound", Sub("heal.aggro", "A mob turns to me"))
end

function BUILD.melee(content)
    RoleSection(content, "Threat", "melee")
    Warn(content, "melee")
    RoleSection(content, "Range", "melee")
    Switch(content, "melee.range", "Dim target out of melee range")
end

function BUILD.ranged(content)
    RoleSection(content, "Threat", "ranged")
    Warn(content, "ranged")
    RoleSection(content, "Range", "ranged")
    Switch(content, "ranged.range", "Dim target out of spell range")
end

local function Tab(key)
    return function(content)
        if not Ready() then return end
        RoleBar(content)
        BUILD[key](content)
    end
end

-------------------------------------------------------------------------------
-- The arrow on the tab of the role in use
-------------------------------------------------------------------------------

-- The strip is built the first time the page is selected, so this runs with every refresh and finds it then.
local function PaintArrows()
    local strips = I.ui and I.ui.strips
    local strip = strips and strips.role
    if not strip then return end
    local role = RoleNow()
    for _, button in ipairs(strip.fsButtons or {}) do
        if not button.fsRoleArrow and button.fsLabel then
            local arrow = I.Label(button, "<", S.TEXT, C.cyan)
            arrow:SetPoint("LEFT", button.fsLabel, "RIGHT", ARROW_GAP, 0)
            button.fsRoleArrow = arrow
        end
        if button.fsRoleArrow then button.fsRoleArrow:SetShown(role ~= nil and button.fsTabKey == role) end
    end
end

I.Track(PaintArrows)
if FS.Role and FS.Role.OnChange then
    FS.Role.OnChange(function()
        if CW.RefreshAll then CW.RefreshAll() end
    end)
end

CW.RegisterCategory({
    key = "role", label = "Roles", group = "GENERAL", order = 1,
    tabs = {
        { key = "tank", label = "Tank", build = Tab("tank") },
        { key = "healer", label = "Healer", build = Tab("healer") },
        { key = "melee", label = "Melee", build = Tab("melee") },
        { key = "ranged", label = "Ranged", build = Tab("ranged") },
    },
})
