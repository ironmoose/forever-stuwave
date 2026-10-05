-- Forever STUwave: Action Bars
--
-- BUILD-CUSTOM. Our own SecureActionButtonTemplate buttons, with their
-- type/action attributes set DIRECTLY from Lua.
--
-- Why not LibActionButton, after vendoring it: secure snippet bodies do not
-- execute on this client. Measured 2026-09-20 with the probe in ErrorLog.lua --
-- both Execute() and RegisterStateDriver() return without error and NEITHER
-- side effect lands (see the ForeverSTUwaveProbe block in SavedVariables).
-- Blizzard's own UI is unaffected because its snippets compiled at load while
-- loadstring_untainted still existed and are cached in the closure factory;
-- anything an addon defines afterwards silently no-ops. LibActionButton assigns
-- type/action INSIDE its UpdateState snippet, so its buttons render but stay
-- permanently empty here. The library stays vendored for reference but is no
-- longer loaded by the .toc.
--
-- What DOES work, verified in game by clicking one: a SecureActionButtonTemplate
-- whose attributes are set from plain Lua. Click handling is C-side, so no
-- restricted closure is in the path at all.
--
-- The cost is paging. Without a secure state driver the page can only be
-- re-pointed OUT of combat, so a mid-fight stance dance will not re-page until
-- combat ends. Bars 2-6 are fixed slot ranges and are unaffected.
--
-- Layout is the mockup, not an approximation -- mockups/full-ui-layout.html,
-- role "actionbars":
--     .abstack  column, gap 5, padding 5
--     .abrow    3 rows, gap 6
--     .abbar    2 per row, 12 buttons, gap 3, padding 3, radius 5,
--               fill rgba(10,5,22,.32), border 1px rgba(168,85,247,.3)
--     .abbar.main   pink border + glow + "MAIN" tag
--     .sqbtn    square, radius 4, 1px cyan border, #241640 -> #160c2b gradient
--
-- Escape hatch: /fsbars blizz restores Blizzard's bars, /fsbars fs returns.

local _, FS = ...

-------------------------------------------------------------------------------
-- Theme
-------------------------------------------------------------------------------

local IsSecret = FS.IsSecret
local SkinCutButton = FS.Theme.SkinCutButton
local AddRoundedFill = FS.Theme.AddRoundedFill
local AddGradientBorder = FS.Theme.AddGradientBorder
local AddOuterGlow = FS.Theme.AddOuterGlow
local ApplyMono = FS.Theme.ApplyMono
local COLOR_POWER = FS.Theme.COLOR_POWER    -- #22e0ff, the mock's --elc here
local COLOR_TEXT_WHITE = FS.Theme.COLOR_TEXT_WHITE  -- keybind glyphs, over a dark plate
local COLOR_HEALTH = FS.Theme.COLOR_HEALTH  -- #ff2e97, the MAIN accent

-- Mockup CSS, kept as named constants so a planner re-export can be diffed
-- against them instead of reverse-engineered out of the code.
local STACK_PAD, STACK_GAP = 5, 5
local ROW_GAP = 6
local BAR_PAD = 3
-- Mockup gap is 3, but our glow throws 5-6px outward from every edge, so
-- neighbouring buttons were bleeding into each other. Widened on Parker's call
-- so each button's halo has room to fall off before the next one starts.
local BTN_GAP = 7
-- Header plate chamfer: 6 is a baked size (Theme.CUT_SIZES), so SnapCut keeps it as is;
-- only TOP-LEFT and BOTTOM-RIGHT are cut, matching the 2C buttons it holds.
local BAR_RADIUS = 6
local ROWS, BARS_PER_ROW, BUTTONS_PER_BAR = 3, 2, 12

local BAR_FILL = { 0.039, 0.020, 0.086, 0.32 }
local BAR_BORDER = { 0.659, 0.333, 0.969, 0.30 }
local MAIN_FILL = { 1, 0.180, 0.592, 0.08 }
-- The button background's #241640 -> #160c2b gradient now lives BAKED into
-- media/slice_cut2_button.tga (see media/generate_cut_corner_outline.py); change it there.

-- Blizzard's own feedback colors for unusable / out-of-mana / out-of-range.
local COLOR_UNUSABLE = { 0.4, 0.4, 0.4 }
local COLOR_OOM = { 0.5, 0.5, 1.0 }
local COLOR_OUT_OF_RANGE = { 0.8, 0.1, 0.1 }

-- Hover: magenta, matching the MAIN bar accent rather than default-UI gold.

-- Queued / toggled-on state (Heroic Strike awaiting its swing, Attack on, auto-repeat):
-- cyan, the same wash PetActionBar gives the current pet mode, plus the cut2 glow so it
-- reads at a glance mid-fight. Cyan because hover is magenta and the border is cyan.
local QUEUED_WASH_ALPHA = 0.4
local QUEUED_GLOW_ALPHA = 0.9
-- Pressed (key or mouse down): the hover pink, much stronger than the hover wash's 0.15.
local PRESSED_WASH_ALPHA = 0.6

-------------------------------------------------------------------------------
-- Bars
-------------------------------------------------------------------------------

-- Bar 1 is PAGED: its slots follow the current action page. The rest own a
-- fixed range. Blizzard container names all confirmed in the 16001 globals
-- dump -- note the main bar is MainActionBar here, not the older MainMenuBar.
-- `binding` is the prefix Blizzard's own keybinding names use for that bar, so
-- GetBindingKey(prefix .. index) finds the key the player actually bound. Taken
-- from the buttonTemplate/buttonType pairs in Blizzard_ActionBar's
-- MultiActionBars.xml rather than guessed -- and worth reading, because
-- MultiBarLeft is MULTIACTIONBAR*4* and MultiBarRight is *3*, which is the
-- reverse of the order the names suggest.
-- MultiBar5 does NOT sit at 73: slots 73-120 are action pages 7-10, the BONUS bars the
-- paged main bar flips to in Battle Stance, cat form, stealth and the like, so a bar 6
-- there mirrored the main bar. Blizzard seats it on MULTIBAR_5_ACTIONBAR_PAGE (13,
-- slots 145-156; Blizzard_ActionBar MultiActionBars.lua), and the first slot of page N is
-- (N - 1) * 12 + 1. The other four multibars are confirmed against Blizzard's own page
-- constants the same way (RIGHT 3 -> 25, LEFT 4 -> 37, BOTTOMRIGHT 5 -> 49, BOTTOMLEFT
-- 6 -> 61), so they stay literal. CombatHud.lua derives its copy the same way.
local MULTIBAR5_PAGE = type(MULTIBAR_5_ACTIONBAR_PAGE) == "number" and MULTIBAR_5_ACTIONBAR_PAGE or 13
local MULTIBAR5_FIRST_ACTION = (MULTIBAR5_PAGE - 1) * BUTTONS_PER_BAR + 1

local BARS = {
    { id = 1, paged = true, label = "MAIN", blizzard = "MainActionBar",     binding = "ACTIONBUTTON" },
    { id = 2, firstAction = 61, blizzard = "MultiBarBottomLeft",  binding = "MULTIACTIONBAR1BUTTON" },
    { id = 3, firstAction = 49, blizzard = "MultiBarBottomRight", binding = "MULTIACTIONBAR2BUTTON" },
    { id = 4, firstAction = 25, blizzard = "MultiBarRight",       binding = "MULTIACTIONBAR3BUTTON" },
    { id = 5, firstAction = 37, blizzard = "MultiBarLeft",        binding = "MULTIACTIONBAR4BUTTON" },
    { id = 6, firstAction = MULTIBAR5_FIRST_ACTION, blizzard = "MultiBar5",           binding = "MULTIACTIONBAR5BUTTON" },
}

local EXTRA_BLIZZARD_BARS = { "MultiBar6", "MultiBar7", "OverrideActionBar" }

-- The page the main bar should show. This is the insecure equivalent of what
-- Bartender4 resolves inside its _onstate-page snippet: a macro conditional
-- cannot tell which special surface is live, so ask directly. Order matters --
-- vehicle outranks override outranks temp-shapeshift outranks bonus.
local function CurrentPage()
    if HasVehicleActionBar and HasVehicleActionBar() then
        return GetVehicleBarIndex and GetVehicleBarIndex() or 12
    end
    if HasOverrideActionBar and HasOverrideActionBar() then
        return GetOverrideBarIndex and GetOverrideBarIndex() or 14
    end
    if HasTempShapeshiftActionBar and HasTempShapeshiftActionBar() then
        return GetTempShapeshiftBarIndex and GetTempShapeshiftBarIndex() or 13
    end
    if HasBonusActionBar and HasBonusActionBar() then
        return GetBonusBarIndex and GetBonusBarIndex() or 7
    end
    return (GetActionBarPage and GetActionBarPage()) or 1
end

-------------------------------------------------------------------------------
-- Console mode
--
-- Console.lua draws ONE chassis behind all 72 buttons (the Gunsight HUD's action
-- bar, mockups/gunsight-hud-v2-2026-10-02). While it is active the per-pill chrome
-- (fill, border, MAIN pink border and tag) is hidden and the gap between the left
-- and right halves grows from the 6 unit pill gap (7.2 design px) to SPINE_DESIGN
-- design px, for the centre spine. `/fsconsole off` (Console.lua) falls back to the
-- pill look.
--
-- ActionBars owns the geometry, Console.lua only reads it: `FS.ActionBars.geometry`
-- (UI units, stack-local, y down) and `FS.ActionBars.OnGeometry(fn)`, called after
-- every re-seat. Everything that touches the stack, the pills or the buttons waits
-- for PLAYER_REGEN_ENABLED when the player is in lockdown: the buttons are secure,
-- so the stack that parents them is protected implicitly. That is also why the
-- Console is NOT parented to the stack.
-------------------------------------------------------------------------------

local ActionBars = { SPINE_DESIGN = 20 }
FS.ActionBars = ActionBars

local consoleActive = false   -- what is applied right now
local pendingConsole          -- a SetConsoleActive made in combat, applied on regen
local pendingSeat = false     -- a rescale that arrived in combat
local usingFS = true          -- /fsbars: false while Blizzard's bars are back

-------------------------------------------------------------------------------
-- Geometry
-------------------------------------------------------------------------------

-- The widest stack (UI units) the Console may be drawn from, or nil when it cannot be
-- worked out (no Console art loaded, or a layout without a seat). The chassis is the button
-- field plus paddings and a halo (Console.EXTENT, design px) and the stack is centred on
-- the layout anchor, so the halo's left/right edges move with the stack width. They must stay
-- inside the action footprint and CHAT_CLEARANCE right of the chat terminal's outer edge
-- (FS.Layout.CHAT_CHROME_RIGHT, the live measurement): whichever bound is nearer wins, which
-- is the chat on the left. The right side then has room to spare because the stack is
-- centred, not the chassis.
local function ConsoleMaxStackW(layout, scale)
    local ext = FS.Console and FS.Console.EXTENT
    local L = FS.Layout
    if not (ext and L and L.CHAT_CHROME_RIGHT and L.CHAT_CLEARANCE and layout.x and layout.w) then return nil end
    local inset = (STACK_PAD + BAR_PAD) / scale           -- stack edge to field edge, design px
    local leftBound = math.max(layout.x - layout.w / 2, L.CHAT_CHROME_RIGHT + L.CHAT_CLEARANCE)
    local rightBound = layout.x + layout.w / 2
    local half = math.min(layout.x + inset - ext.left - leftBound,
        rightBound - layout.x + inset - ext.right)
    return 2 * half * scale
end

-- Solves the mockup's flex layout for real pixels. The mockup lets flex divide
-- the leftover space, so reproduce that rather than baking the 41px the planner
-- happened to land on -- a resized section then still fits.
local function ComputeGeometry(layout)
    -- scaledW, not w: FS.Layout.Apply sizes the stack in UI units, so the
    -- button solve has to happen in UI units too or the twelve buttons will
    -- not fit the bar they are put inside.
    local w = layout.scaledW or layout.w or 1089
    local rowW = w - STACK_PAD * 2
    local barW = (rowW - ROW_GAP * (BARS_PER_ROW - 1)) / BARS_PER_ROW
    local innerW = barW - BAR_PAD * 2
    local btnSize = math.floor((innerW - BTN_GAP * (BUTTONS_PER_BAR - 1)) / BUTTONS_PER_BAR)

    -- The button edge above was solved with the pill gap (ROW_GAP). With the Console on the
    -- spine is wider and the chassis draws outside the field, so the buttons are solved
    -- again in the narrower width the Console fits (ConsoleMaxStackW); never larger than
    -- the pill solve, so the Console off path below is untouched.
    local gap = ROW_GAP
    if consoleActive then
        local scale = FS.Layout and FS.Layout.Scale and FS.Layout.Scale() or 1
        gap = ActionBars.SPINE_DESIGN * scale
        local maxW = ConsoleMaxStackW(layout, scale)
        if maxW then
            local fitBar = (maxW - gap - STACK_PAD * 2) / BARS_PER_ROW - BAR_PAD * 2
            btnSize = math.min(btnSize,
                math.floor((fitBar - BTN_GAP * (BUTTONS_PER_BAR - 1)) / BUTTONS_PER_BAR))
        end
    end
    local barH = btnSize + BAR_PAD * 2

    -- Flooring the button edge leaves the row slightly narrower than the flex
    -- width, and the mockup absorbs that with justify-content:center. Centring
    -- it here still left a visible gap between the last button and the end of
    -- the pill, so instead SHRINK THE PILL to exactly fit its buttons: the
    -- content is the source of truth and every edge lines up.
    --
    -- The stack then has to hug the two bars too, or the same slack just moves
    -- up a level. Stack is anchored CENTER, so narrowing it keeps it centred on
    -- the layout anchor.
    local used = btnSize * BUTTONS_PER_BAR + BTN_GAP * (BUTTONS_PER_BAR - 1)
    barW = used + BAR_PAD * 2

    return {
        barW = barW,
        barH = barH,
        btnSize = btnSize,
        gap = gap,
        stackW = barW * BARS_PER_ROW + gap * (BARS_PER_ROW - 1) + STACK_PAD * 2,
        stackH = barH * ROWS + STACK_GAP * (ROWS - 1) + STACK_PAD * 2,
    }
end

-------------------------------------------------------------------------------
-- Blizzard bars
-------------------------------------------------------------------------------

local hiddenParent
local stashed = {}

local function HiddenParent()
    if not hiddenParent then
        hiddenParent = CreateFrame("Frame", nil, UIParent)
        hiddenParent:Hide()
    end
    return hiddenParent
end

-- Never in combat: EnableMouse on a secure stock button, and hiding a container
-- holding SECURE buttons, are protected while locked down, so the gate is
-- load-bearing, not defensive noise.
--
-- WHY "dim" IS THE DEFAULT (live bug, 2026-10-03): the old default "stash" did
-- `bar:SetParent(HiddenParent()); bar:Hide()`. On a Blizzard action bar, Hide is
-- NOT the C method: Edit Mode replaces the instance's Hide with HideOverride
-- (Blizzard_ActionBar/Shared/ActionBar.lua, SetupVisibilityFunctionOverrides), so
-- our call ran Blizzard's visibility and Edit Mode code, and the OnHide cascade
-- into every stock button (ActionBarActionButtonMixin:OnHide), all under OUR
-- taint. Blizzard's own hidden MultiBarBottomLeftButton2 then threw in combat:
--
--   Blizzard_ActionBar/Shared/ActionButton.lua:891: bad argument #1 to
--   'SetCooldown' ... Secret values are only allowed during untainted
--   execution for this argument.
--
-- That is Blizzard's code and Blizzard's button, failing because state it reads
-- was written under our taint. The only way to keep it out of that code is to
-- run none of it: the default now calls SetAlpha and EnableMouse only, which are
-- plain engine methods that fire no Blizzard script. No Hide, Show, SetParent,
-- SetScript or HookScript on a Blizzard bar or button, and no write to any
-- Blizzard table.
--
-- STOCK BUTTONS KEEP RUNNING, AND THAT IS FINE. They register no events of their
-- own: ActionBarButtonEventsFrame (and ActionBarActionEventsFrame) hold the
-- registrations and a `frames` list, and their OnEvent walks that list calling
-- each button's OnEvent (ActionButton.lua, ActionBarButtonEventsFrameMixin).
-- Unregistering the bar's or its children's events therefore never stopped them,
-- which is what an earlier version of this comment wrongly claimed. Running on
-- an invisible button is harmless as long as the run is UNTAINTED, so we leave
-- both dispatcher frames and their `frames` tables strictly alone: writing to
-- them from addon code taints them, and other Blizzard systems iterate them.
-- (An untainted run on the hidden button costs a little CPU per combat event;
-- the price of not being the thing that taints it.)
--
-- WHAT WE NO LONGER UNREGISTER: the bar's own events (the show-grid pair and
-- PLAYER_REGEN_*, which feed EditModeActionBarMixin:UpdateVisibility). Nothing
-- we rely on needs them gone: the bar is invisible by alpha whatever its
-- visibility logic decides, and with them left registered Blizzard's own state
-- stays coherent for Edit Mode and for /fsbars blizz, which the old
-- UnregisterAllEvents could not undo (RestoreBlizzardBar never re-registered).
--
-- THE BUTTONS ARE NOT THE BAR'S CHILDREN. An ActionBarMixin bar's children are
-- ActionBarButtonContainerN frames; each container holds one stock button, and
-- the bar keeps the same buttons in its read-only `actionButtons` table.
-- EnableMouse does not inherit, so sweeping only bar:GetChildren() leaves the 12
-- real buttons clickable at alpha 0 over ours. FrameHelpers.CollectActionBarFrames
-- walks containers, their buttons and `actionButtons` (read only, deduplicated).
-- The parent's alpha already cascades to every descendant.
--
-- "stash" (reparent to a hidden frame + Hide) stays selectable with
-- `/fstaint stash` as an explicit experiment, and a save that chose it keeps it.
-- It is the path that runs Blizzard's HideOverride, so expect the error above
-- back while it is on.
--
-- Keybinds are unaffected either way. A key bound to ACTIONBUTTON3 or
-- MULTIACTIONBAR1BUTTON3 never reaches OUR button: the binding body
-- (Bindings_Mists.xml) calls ActionButtonDown(3) / MultiActionButtonDown(
-- "MultiBarBottomLeft", 3), which look up BLIZZARD's button for that slot and
-- click it, regardless of its visibility or parent. Our button only mirrors the
-- binding as hotkey text. The real buttons stay present at alpha 0, which is why
-- mouse has to be disabled on each of them or they would silently eat clicks
-- aimed at our buttons underneath.
local HIDE_STRATEGY_DEFAULT = "dim"
local hideStrategy = HIDE_STRATEGY_DEFAULT

local function HideBlizzardBar(name)
    local bar = _G[name]
    if not bar or stashed[name] or InCombatLockdown() then return end

    local stash = {
        parent = bar:GetParent(),
        shown = bar:IsShown(),
        strategy = hideStrategy,
        alpha = bar:GetAlpha(),
    }
    stashed[name] = stash

    pcall(function()
        if hideStrategy == "dim" then
            stash.mouse = bar.IsMouseEnabled and bar:IsMouseEnabled()
            stash.children = {}
            bar:SetAlpha(0)
            if bar.EnableMouse then bar:EnableMouse(false) end
            for _, frame in ipairs(FS.FrameHelpers.CollectActionBarFrames(bar)) do
                pcall(function()
                    stash.children[#stash.children + 1] = {
                        frame = frame,
                        alpha = frame:GetAlpha(),
                        mouse = frame.IsMouseEnabled and frame:IsMouseEnabled(),
                    }
                    frame:SetAlpha(0)
                    if frame.EnableMouse then frame:EnableMouse(false) end
                end)
            end
        else
            bar:SetParent(HiddenParent())
            bar:Hide()
        end
    end)
end

local function RestoreBlizzardBar(name)
    local bar, stash = _G[name], stashed[name]
    if not bar or not stash or InCombatLockdown() then return end
    pcall(function()
        -- Undo whatever was actually APPLIED, not whatever is selected now --
        -- /fstaint can change the strategy between hide and restore.
        if stash.strategy == "dim" then
            bar:SetAlpha(stash.alpha or 1)
            if bar.EnableMouse and stash.mouse ~= nil then bar:EnableMouse(stash.mouse) end
            for _, saved in ipairs(stash.children or {}) do
                pcall(function()
                    saved.frame:SetAlpha(saved.alpha or 1)
                    if saved.frame.EnableMouse and saved.mouse ~= nil then
                        saved.frame:EnableMouse(saved.mouse)
                    end
                end)
            end
        else
            bar:SetParent(stash.parent or UIParent)
            if stash.shown then bar:Show() end
        end
    end)
    stashed[name] = nil
end

local function ForEachBlizzardBar(fn)
    for _, spec in ipairs(BARS) do
        if spec.blizzard then fn(spec.blizzard) end
    end
    for _, name in ipairs(EXTRA_BLIZZARD_BARS) do fn(name) end
end

-- Switch strategy live: restore everything with the OLD method, then re-hide
-- with the new one. No reload, so an A/B against the error log is two commands
-- rather than two sessions.
local function SetHideStrategy(which)
    if which ~= "stash" and which ~= "dim" then return false end
    if InCombatLockdown() then
        print("|cff22e0ffForever STUwave|r: not while in combat -- hiding secure "
            .. "frames is protected during lockdown.")
        return true
    end

    ForEachBlizzardBar(RestoreBlizzardBar)
    hideStrategy = which
    ForeverSTUwaveDB = ForeverSTUwaveDB or {}
    ForeverSTUwaveDB.barHideStrategy = which
    ForEachBlizzardBar(HideBlizzardBar)

    print(("|cff22e0ffForever STUwave|r: Blizzard bars hidden by |cffff2e97%s|r. "
        .. "Clear the error log (/fserr clear), play a few pulls, then compare.")
        :format(which))
    return true
end

SLASH_FSTAINT1 = "/fstaint"
SlashCmdList["FSTAINT"] = function(msg)
    msg = (msg or ""):lower():gsub("%s", "")
    if not SetHideStrategy(msg) then
        print("|cff22e0ffForever STUwave|r: /fstaint dim | stash   (currently "
            .. "|cffff2e97" .. hideStrategy .. "|r)")
        print("  |cffaaaaaadim|r    default. Leave them in place, SetAlpha(0) + mouse off "
            .. "on the bar, its containers and every stock button. Runs no Blizzard script.")
        print("  |cffaaaaaastash|r  experiment. Reparent + Hide, which runs Blizzard's "
            .. "HideOverride under our taint and can bring back the SetCooldown secret error.")
        print("  Measure with the error log; do not judge by feel.")
    end
end

-------------------------------------------------------------------------------
-- Button visuals
--
-- Without LibActionButton nothing paints these for us, so every piece of state
-- a button shows is driven here off the action APIs. All of them were confirmed
-- present in the 16001 globals dump before this was written.
-------------------------------------------------------------------------------

local allButtons = {}

local function UpdateIcon(button)
    local icon = button.icon
    if not icon then return end

    local texture = HasAction(button.action) and GetActionTexture(button.action) or nil
    if texture then
        icon:SetTexture(texture)
        icon:Show()
    else
        icon:Hide()
    end
end

-- 12.0 secret values. GetActionCount hands back a SECRET number once combat
-- starts, and `count > 1` is a comparison, which is illegal on one -- Parker
-- hit this the moment he pulled: 89 throws, all from this line.
--
-- The 12.0 answer is not to guard the comparison, it is to stop asking for a
-- number. C_ActionBar.GetActionDisplayCount returns what the engine wants
-- DISPLAYED -- already blank when a count should not show -- so it goes
-- straight to SetText with no comparison anywhere. LibActionButton-1.0 (in
-- libs/, which is how this was found) goes further and stubs GetActionCount
-- out entirely on this engine: "the remaining uses of GetActionCount can't
-- deal with secrets".
--
-- The legacy branch is kept for clients without C_ActionBar, and there the
-- last plain reading has to stand for the fight, since there is no legal way
-- to decide "blank or not" from a secret.
local GetActionDisplayCount = C_ActionBar and C_ActionBar.GetActionDisplayCount

local function UpdateCount(button)
    if not button.Count then return end

    if not HasAction(button.action) then
        button.Count:SetText("")
        return
    end

    if GetActionDisplayCount then
        button.Count:SetText(GetActionDisplayCount(button.action))
        return
    end

    local count = GetActionCount(button.action) or 0
    if IsSecret(count) then return end
    button.Count:SetText(count > 1 and count or "")
end

local GetActionCooldownDuration = C_ActionBar and C_ActionBar.GetActionCooldownDuration

local function UpdateCooldown(button)
    local cooldown = button.cooldown
    if not cooldown then return end
    -- SetCooldown is NOT on the secret whitelist, which I assumed it was. It
    -- refuses outright:
    --
    --   bad argument #1 to 'SetCooldown' ... Secret values are only allowed
    --   during untainted execution for this argument.
    --
    -- Read that wording carefully: the ARGUMENT is permitted, the CALLER is
    -- not. Everything an addon calls is tainted, so there is no way to reach
    -- the permitted path from here, and no amount of guarding start/duration
    -- gets the swipe back.
    --
    -- 12.0 supplies a different shape instead: ask for a DURATION OBJECT and
    -- hand that to the engine. The object is opaque -- we never look inside it
    -- -- which is the same bargain as every other secret-safe setter.
    -- C_ActionBar.GetActionCooldownDuration + Cooldown:SetCooldownFromDurationObject,
    -- exactly as LibActionButton-1.0 does it in libs/.
    if GetActionCooldownDuration and cooldown.SetCooldownFromDurationObject then
        local durationObject = GetActionCooldownDuration(button.action)
        if durationObject then
            cooldown:SetCooldownFromDurationObject(durationObject)
        elseif cooldown.Clear then
            cooldown:Clear()
        end
        cooldown:Show()
        return
    end

    -- Legacy clients only, where none of the values are secret to begin with.
    local start, duration, enable = GetActionCooldown(button.action)
    if not (start and duration) then return end
    if IsSecret(start) or IsSecret(duration) then return end

    cooldown:SetCooldown(start, duration)

    -- `enable == 0` is a comparison, illegal on a secret. An unreadable flag
    -- means show the cooldown, which is the state that matters.
    if not IsSecret(enable) and enable == 0 then
        cooldown:Hide()
    else
        cooldown:Show()
    end
end

-- Tints the ICON rather than the border: the border is our synthwave chrome and
-- recoloring it for a transient state would fight the theme.
local function UpdateUsable(button)
    local icon = button.icon
    if not icon or not HasAction(button.action) then return end

    local isUsable, notEnoughMana = IsUsableAction(button.action)
    local inRange = IsActionInRange(button.action)

    -- All three of these go SECRET in combat, and they are secret BOOLEANS,
    -- which are the strictest case in the 12.0 rules: a secret number can at
    -- least be truth-tested, a secret boolean cannot be touched at all. So the
    -- red/blue/grey tints below are simply unreachable mid-fight.
    --
    -- Range still gets feedback, because SetAlphaFromBoolean is the one
    -- sanctioned consumer of a secret boolean: out of range becomes a dim
    -- instead of a red wash. That is a deliberate visual difference between
    -- combat and out of combat, not a bug.
    local rangeSecret = IsSecret(inRange)
    if rangeSecret then
        if icon.SetAlphaFromBoolean then
            icon:SetAlphaFromBoolean(inRange, 1, 0.45)
        end
    else
        icon:SetAlpha(1)
    end

    if not rangeSecret and inRange == false then
        icon:SetVertexColor(COLOR_OUT_OF_RANGE[1], COLOR_OUT_OF_RANGE[2], COLOR_OUT_OF_RANGE[3])
    elseif not IsSecret(notEnoughMana) and notEnoughMana then
        icon:SetVertexColor(COLOR_OOM[1], COLOR_OOM[2], COLOR_OOM[3])
    elseif not IsSecret(isUsable) and not isUsable then
        icon:SetVertexColor(COLOR_UNUSABLE[1], COLOR_UNUSABLE[2], COLOR_UNUSABLE[3])
    else
        icon:SetVertexColor(1, 1, 1)
    end
end

-- Keybind text, top-right of the button.
--
-- Mirrors ActionBarActionButtonMixin:UpdateHotkeys: look up the binding by its
-- canonical name, fall back to a direct CLICK binding on the button itself
-- (which is how a player binds a key straight to a custom button). The shared
-- formatter shortens mouse labels and keeps Blizzard's keyboard/gamepad text.
--
-- None of these return secret values; bindings are player config, not combat
-- state.
local function UpdateHotkey(button)
    local hotkey = button.HotKey
    if not hotkey then return end

    local key
    if button.bindingAction then
        key = GetBindingKey(button.bindingAction)
    end
    if not key and button.GetName then
        key = GetBindingKey("CLICK " .. button:GetName() .. ":LeftButton")
    end

    local text = FS.FrameHelpers.FormatBindingText(key)
    if text == "" then
        hotkey:SetText("")
        hotkey:Hide()
        if button.fsHotkeyPlate then button.fsHotkeyPlate:Hide() end
        return
    end

    hotkey:SetText(text)
    hotkey:Show()
    -- The plate is anchored to the FontString, so it follows the text's size;
    -- it only needs showing and hiding alongside it.
    if button.fsHotkeyPlate then button.fsHotkeyPlate:Show() end
end

-- Key-press feedback. A key bound to ACTIONBUTTONn / MULTIACTIONBARnBUTTONn never reaches
-- OUR button: the binding body calls ActionButtonDown(n) / MultiActionButtonDown(bar, n),
-- which push and click Blizzard's own hidden twin (see the hide-strategy notes above).
-- So the cast worked and our button showed nothing: no press, no animation. Parker: "when
-- I am hitting my keybind I don't get ... the button on the action bar making any kind
-- of animation".
--
-- hooksecurefunc post-hooks on those four globals mirror the press onto our button with
-- SetButtonState, the same call Blizzard makes on its own, so the CheckButton's native
-- pushed texture (restyled in StyleButton) shows for the length of the press. A post-hook
-- runs insecure and after the original, so it cannot taint or block the cast, and
-- RegisterForClicks stays as it was. Which of ours is meant follows the BINDING name
-- (position on the bar), exactly like button.bindingAction. Feature-detected: a client
-- without any of the four just gets no press look.
--
-- Known gap: on a pet-battle style override bar Blizzard's ActionButtonDown returns early
-- for the pet buttons and our bar 1 button n would still be pushed. Cosmetic only.
local buttonsByBinding = {}
local bindingPrefixByBlizzardBar = {}
for _, spec in ipairs(BARS) do
    if spec.binding then bindingPrefixByBlizzardBar[spec.blizzard] = spec.binding end
end
local pressHooksInstalled = false

local function SetPressed(prefix, id, down)
    local button = prefix and id and buttonsByBinding[prefix .. id]
    if not (button and button.GetButtonState and button.SetButtonState) then return end
    local state = button:GetButtonState()
    if down and state == "NORMAL" then
        button:SetButtonState("PUSHED")
    elseif not down and state == "PUSHED" then
        button:SetButtonState("NORMAL")
    end
end

-- Blizzard's ActionButtonDown returns BEFORE pushing anything during a pet battle (its
-- CheckPetActionButtonEvent); mirror that guard on the press only. A release is always
-- honoured, so a press that began before the battle can still clear.
local function InPetBattle()
    local petBattles = _G.C_PetBattles
    if not (petBattles and petBattles.IsInBattle) then return false end
    local ok, inBattle = pcall(petBattles.IsInBattle)
    return ok and inBattle and true or false
end

-- A key release that never arrives (alt-tab away, binding changed mid-press, combat
-- state flipping under a held key) would leave a button PUSHED. There is no focus-loss
-- event to catch the alt-tab, so the state is re-pinned when combat ENDS or the bindings
-- change, which bounds how long a stuck look can last. Not on PLAYER_REGEN_DISABLED: that
-- would clear the very key that opened the fight and, falling through OnEvent, run a full
-- UpdateAll over all 72 buttons at the pull.
local function ReleaseAllPresses()
    for _, button in ipairs(allButtons) do
        if button.GetButtonState and button:GetButtonState() == "PUSHED"
            and not (button.IsMouseOver and button:IsMouseOver()) then
            button:SetButtonState("NORMAL")
        end
    end
end

local function InstallPressHooks()
    if pressHooksInstalled or type(hooksecurefunc) ~= "function" then return end
    pressHooksInstalled = true
    local mainPrefix
    for _, spec in ipairs(BARS) do
        if spec.paged then mainPrefix = spec.binding end
    end
    local function hook(name, fn)
        if type(_G[name]) == "function" then pcall(hooksecurefunc, name, fn) end
    end
    hook("ActionButtonDown", function(id)
        if not InPetBattle() then SetPressed(mainPrefix, id, true) end
    end)
    hook("ActionButtonUp", function(id) SetPressed(mainPrefix, id, false) end)
    hook("MultiActionButtonDown", function(barName, id)
        SetPressed(bindingPrefixByBlizzardBar[barName], id, true)
    end)
    hook("MultiActionButtonUp", function(barName, id)
        SetPressed(bindingPrefixByBlizzardBar[barName], id, false)
    end)
end

-- Queued / active state. Blizzard's ActionButton_UpdateState does
-- `SetChecked(IsCurrentAction(action) or IsAutoRepeatAction(action))`: a next-swing
-- ability (Heroic Strike, Cleave), a toggled-on Attack, an auto-repeat shot and a spell
-- waiting on a target click all read as "checked". Ours drew nothing, so there was no way
-- to see a queued Heroic Strike.
--
-- Our own wash + glow textures carry the look instead of the CheckButton's checked
-- state, for the same reason UpdateUsable cannot use Blizzard's tints: both APIs may hand
-- back a SECRET boolean in combat (not in secretAudit, which only probes unit APIs, so
-- assume they do), and SetChecked / `if flag then` cannot take one. SetAlphaFromBoolean
-- is the sanctioned consumer, so a secret answer is routed straight into the textures'
-- alpha. The CheckButton itself is pinned unchecked, so a click's own toggle never
-- leaves a stale state behind.
--
-- Two flags, two wash+glow pairs: IsCurrentAction drives fsQueuedWash/fsQueuedGlow and
-- IsAutoRepeatAction drives fsRepeatWash/fsRepeatGlow, each on its own. Two secret
-- booleans cannot be OR-ed in Lua, but ADD blending ORs the two pairs on screen, so an
-- Auto Shot or wand stays lit in combat even while IsCurrentAction is secret. (Both true
-- at once simply stacks the two washes a little brighter.)
local function SetQueuedPair(wash, glow, flag)
    if IsSecret(flag) then
        if wash.SetAlphaFromBoolean and glow.SetAlphaFromBoolean then
            wash:Show()
            glow:Show()
            wash:SetAlphaFromBoolean(flag, 1, 0)
            glow:SetAlphaFromBoolean(flag, 1, 0)
        else
            wash:Hide()   -- nothing legal to do with it: show nothing, not a guess
            glow:Hide()
        end
        return
    end
    local shown = flag and true or false
    wash:SetAlpha(1)    -- undo any alpha a secret flag left behind
    glow:SetAlpha(1)
    wash:SetShown(shown)
    glow:SetShown(shown)
end

local function UpdateState(button)
    if not button.fsQueuedWash then return end
    if button.SetChecked then button:SetChecked(false) end

    local slot = button.action
    SetQueuedPair(button.fsQueuedWash, button.fsQueuedGlow, IsCurrentAction and IsCurrentAction(slot))
    SetQueuedPair(button.fsRepeatWash, button.fsRepeatGlow, IsAutoRepeatAction and IsAutoRepeatAction(slot))
end

-------------------------------------------------------------------------------
-- Tooltip
--
-- Never had a working tooltip to begin with, not a regression: our buttons
-- inherit the bare "ActionButtonTemplate" global, which only mixes in
-- BaseActionButtonMixin. The tooltip wiring (ActionBarActionButtonMixin ->
-- GameTooltip:SetAction) lives in ActionBarButtonMixin, which belongs to the
-- FULLER ActionBarButtonTemplate Blizzard's own MultiBarBottomLeftButton1-and-
-- friends use -- not the template we build on. So there was nothing to lose.
--
-- SetAction is a Lua mixin method (GameTooltipMixin), not a C-side widget
-- method, so it can't be confirmed from a metatable dump -- feature-detected
-- the same way the rest of this file feature-detects action-bar APIs.
--
-- HookScript, matching the hover-glow registration below: nothing else has a
-- claim on OnEnter/OnLeave here, but HookScript costs nothing and keeps that
-- true if it ever changes.
-------------------------------------------------------------------------------

local HAS_TOOLTIP_SETACTION = type(GameTooltip) == "table" and type(GameTooltip.SetAction) == "function"
local warnedNoTooltipApi = false

local function ShowActionTooltip(self)
    if not HAS_TOOLTIP_SETACTION then
        if not warnedNoTooltipApi then
            warnedNoTooltipApi = true
            FS.LogDegradeOnce("actionbar_notooltipapi",
                "|cffff4488Forever STUwave|r: GameTooltip:SetAction unavailable, " ..
                "action bar tooltips disabled")
        end
        return
    end
    if not HasAction(self.action) then return end

    if _G.GameTooltip_SetDefaultAnchor then
        _G.GameTooltip_SetDefaultAnchor(GameTooltip, self)
    else
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    end
    GameTooltip:SetAction(self.action)
    GameTooltip:Show()
end

local function HideActionTooltip()
    GameTooltip:Hide()
end

-- Drag and drop: pick a spell up off a button, drop one onto it.
--
-- Our buttons are built from SecureActionButtonTemplate by hand, so they never
-- inherited ActionBarActionButtonMixin's drag handlers and there was simply
-- nothing listening -- the bars were not "locked", they were inert. Parker
-- found this trying to move a skill.
--
-- Plain insecure handlers are the right tool here, which is worth justifying
-- because LibActionButton does this with secure snippets and those do NOT
-- execute on this client (see the header of this file). It needs them because
-- it rewrites the button's own secure `type`/`action` ATTRIBUTES mid-drag for
-- its non-action button kinds. We never do that: a drag moves the contents of
-- an action SLOT, which is server state, and our attributes are untouched.
-- LibActionButton's own PickupAny helper calls PickupAction from plain Lua for
-- exactly this reason, so the API is not protected.
--
-- Mirrors ActionBarActionButtonMixin:OnDragStart, including the lock check --
-- with "Lock Action Bars" on, Blizzard requires the PICKUPACTION modifier
-- (shift by default), and silently ignoring that setting would be its own bug
-- report later.
-- Forward declaration: SetupDrag's handlers call UpdateButton, which is defined
-- below them. Without this they would capture a nil upvalue and the icon would
-- not refresh after a drag.
local UpdateButton

local function ActionBarsLocked()
    if Settings and Settings.GetValue then
        local ok, value = pcall(Settings.GetValue, "lockActionBars")
        if ok then return value and true or false end
    end
    if GetCVarBool then
        local ok, value = pcall(GetCVarBool, "lockActionBars")
        if ok then return value and true or false end
    end
    return false
end

local function SetupDrag(button)
    if not button.RegisterForDrag then return end
    button:RegisterForDrag("LeftButton", "RightButton")

    button:SetScript("OnDragStart", function(self)
        -- Attribute writes are illegal in combat and PickupAction touches the
        -- action bar state, so this stays out of lockdown entirely.
        if InCombatLockdown() then return end
        if ActionBarsLocked() and not IsModifiedClick("PICKUPACTION") then return end

        PickupAction(self.action)
        UpdateButton(self)
    end)

    button:SetScript("OnReceiveDrag", function(self)
        if InCombatLockdown() then return end
        PlaceAction(self.action)
        UpdateButton(self)
    end)
end

function UpdateButton(button)
    UpdateHotkey(button)
    UpdateIcon(button)
    UpdateCount(button)
    UpdateCooldown(button)
    UpdateUsable(button)
    UpdateState(button)
end

local function UpdateAll()
    for _, button in ipairs(allButtons) do
        UpdateButton(button)
    end
end

-- Hotkey text only: the cheap refresh Quick Keybind mode asks for after a
-- rebind, without redoing icon/cooldown/usable for all 72 buttons.
local function UpdateAllHotkeys()
    for _, button in ipairs(allButtons) do
        UpdateHotkey(button)
    end
end

-- Queued / active state only: the cheap refresh for the cast-intent events, which fire
-- on every swing and spell queue and change nothing else about a button.
local function UpdateAllState()
    for _, button in ipairs(allButtons) do
        UpdateState(button)
    end
end

-- Re-points the paged bar at the current page. Attribute writes are illegal in
-- combat, so a page change mid-fight is remembered and applied on regen -- the
-- one real cost of having no secure state driver.
local pendingPage = false

local function ApplyPage()
    local page = CurrentPage()
    for _, button in ipairs(allButtons) do
        if button.paged then
            local slot = (page - 1) * BUTTONS_PER_BAR + button.index
            if button.action ~= slot then
                button.action = slot
                button:SetAttribute("action", slot)
            end
        end
    end
    UpdateAll()
end

local function RequestPage()
    if InCombatLockdown() then
        pendingPage = true
        return
    end
    pendingPage = false
    ApplyPage()
end

-------------------------------------------------------------------------------
-- Button construction
-------------------------------------------------------------------------------

local function StyleButton(button, size)
    button:SetSize(size, size)

    -- Blank Blizzard's own button art FIRST, before ours goes on.
    --
    -- ActionButtonTemplate ships a full-size SQUARE slot texture at
    -- BACKGROUND/0 -- above our rounded fill at BACKGROUND/-8 -- so it poked
    -- past the rounded border as a dark nub at every corner. It is anonymous,
    -- found by dumping a live button's regions (29x30, layer BACKGROUND/0).
    --
    -- Blanking every Texture present at this moment rather than naming them:
    -- that set is exactly Blizzard's, since none of ours exists yet. The icon
    -- is spared because it carries the spell art, and the Count/HotKey strings
    -- are FontStrings, not Textures, so they are untouched. The highlight is
    -- re-textured further down.
    if button.GetRegions then
        for _, region in ipairs({ button:GetRegions() }) do
            if region ~= button.icon
                and region.GetObjectType and region:GetObjectType() == "Texture"
                and region.SetAlpha
            then
                region:SetAlpha(0)
            end
        end
    end

    -- CUT-CORNER background: ONE nine-sliced texture (slice_cut2_button.tga).
    --
    -- The button shape is the two-corner cut from the locked pet-slot design: top-left
    -- and bottom-right chamfered, top-right and bottom-left square (Theme SLICE_CUT2_*,
    -- media/generate_cut_corner_outline.py). It replaced the 4px rounded shape; the
    -- history below is why it is ONE nine-sliced texture, which still holds for a
    -- chamfer (the corner slice just holds a 45 degree cut instead of an arc).
    --
    -- Parker found the original cause -- the background was square behind a
    -- round border. The first fix rebuilt it the way Theme.AddRoundedFill
    -- builds a panel (centre + four edge strips + four corner quads), and that
    -- still showed corners, because at a 4px radius FILL_CORNER_TEXTURE's
    -- quarter-disc renders as a plain 4x4 SQUARE -- proved by painting those
    -- pieces bright red. Insetting the fill 1px hid it behind the border, but
    -- only moved the problem onto the border, which had the same seam.
    --
    -- Nine-slice ends the whole class of bug: the shape is in the texture, the
    -- engine emits the corners at native texel resolution, and there is no
    -- join to misalign. Nine regions become one.
    --
    -- The mockup's #241640 -> #160c2b vertical gradient is BAKED into the
    -- texture's RGB rather than applied with SetGradient: a gradient is a
    -- per-vertex effect and a nine-sliced texture is nine quads, so it would
    -- band at every slice boundary. Tinted white here to pass it through.
    FS.Theme.AddCut2Texture(
        button, FS.Theme.SLICE_CUT2_BUTTON_TEXTURE, { 1, 1, 1, 1 }, "BACKGROUND", -8)

    -- ActionButtonTemplate brings Blizzard's gold frame along. These are OUR
    -- buttons, so blanking it is not the taint case the old overlay worried
    -- about.
    if button.NormalTexture then button.NormalTexture:SetAlpha(0) end
    local normal = button.GetNormalTexture and button:GetNormalTexture()
    if normal then normal:SetAlpha(0) end

    -- Border and base glow in the cut shape. SkinCutButton is SkinButton with the cut2
    -- outline/glow textures passed in (see Theme.SkinCutButton for why it is not a
    -- hand-drawn border here); same color, same 0.35 glow alpha. The 1 texel stroke is
    -- baked into slice_cut2_outline.tga, the same weight the rounded border had.
    if SkinCutButton then
        SkinCutButton(button, {
            borderColor = COLOR_POWER,
            glowAlpha = 0.35,
        })
    end

    -- Blizzard's highlight texture is authored for a 36px action button and
    -- does not follow our smaller one, so it hung outside the edges as a gold
    -- halo. Replace it outright: a magenta additive wash sized to the button,
    -- plus a matching outer glow, so hover reads as part of the theme instead
    -- of default-UI gold.
    --
    -- The wash is the white cut2 fill shape (nine-sliced, ADD blend), not a flat
    -- rectangle, so its top-left and bottom-right corners follow the chamfer instead
    -- of tinting the corner the button does not have. The fill texture is used rather
    -- than the icon mask because the wash spans the whole button, one pixel wider than
    -- the icon the mask is anchored to.
    local highlight = button.GetHighlightTexture and button:GetHighlightTexture()
    if highlight then
        highlight:SetTexture(FS.Theme.SLICE_CUT2_FILL_TEXTURE)
        FS.Theme.ApplyNineSlice(highlight, FS.Theme.SLICE_CUT_MARGIN)
        highlight:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3])
        highlight:SetBlendMode("ADD")
        highlight:SetAlpha(0.15)
        highlight:ClearAllPoints()
        highlight:SetAllPoints(button)
    end

    -- Outer magenta glow: ONE nine-sliced texture.
    --
    -- This was four edge strips flush to the button's SQUARE edge, which is the
    -- construction the base glow already had to be rewritten out of -- and the
    -- rewrite never carried over here, so hovering brought the dark corner
    -- notch straight back. Parker: "the hover state for action bars has the
    -- broken corners still".
    --
    -- Strips cannot cover the area a rounded corner cuts away, at any size or
    -- alpha. A texture whose shape IS the button shape cannot leave that gap, so the
    -- glow is slice_cut2_glow.tga: the two-corner chamfer plus its halo.
    if not button.fsHoverGlow then
        local pad = FS.Theme.SLICE_CUT2_GLOW_PAD
        local glow = button:CreateTexture(nil, "OVERLAY", nil, 1)
        glow:SetTexture(FS.Theme.SLICE_CUT2_GLOW_TEXTURE)
        FS.Theme.ApplyNineSlice(glow, FS.Theme.SLICE_CUT2_GLOW_MARGIN)
        glow:SetPoint("TOPLEFT", button, "TOPLEFT", -pad, pad)
        glow:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", pad, -pad)
        glow:SetBlendMode("ADD")
        glow:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], 0.9)
        glow:Hide()
        button.fsHoverGlow = glow

        button:HookScript("OnEnter", function(self)
            if self.fsHoverGlow then self.fsHoverGlow:Show() end
        end)
        button:HookScript("OnLeave", function(self)
            if self.fsHoverGlow then self.fsHoverGlow:Hide() end
        end)
    end

    -- Pressed look, shown by the CheckButton itself while its state is PUSHED: a mouse press
    -- natively, a bound key through the ActionButtonDown hook (see InstallPressHooks). The
    -- template's own pushed art was blanked by the region sweep above (and is authored for
    -- 36px), so this is a bright pink wash, the hover color at full strength, the cut2 fill
    -- shape like every other wash here. Drawn at OVERLAY so it sits above the icon.
    local pushed = button.GetPushedTexture and button:GetPushedTexture()
    if not pushed and button.SetPushedTexture then
        pushed = button:CreateTexture(nil, "OVERLAY", nil, 3)
        button:SetPushedTexture(pushed)
    end
    if pushed then
        pushed:SetTexture(FS.Theme.SLICE_CUT2_FILL_TEXTURE)
        FS.Theme.ApplyNineSlice(pushed, FS.Theme.SLICE_CUT_MARGIN)
        pushed:SetVertexColor(COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], PRESSED_WASH_ALPHA)
        pushed:SetBlendMode("ADD")
        pushed:SetAlpha(1)   -- the sweep above zeroed the template's
        pushed:SetDrawLayer("OVERLAY", 3)
        pushed:ClearAllPoints()
        pushed:SetAllPoints(button)
    end

    -- Queued / active look (see UpdateState): a cyan wash over the whole face and a cyan
    -- cut2 glow around it, both hidden until the button's action is current or repeating.
    -- Built like the pet bar's checked wash and the hover glow above: nine-sliced cut2
    -- shapes, ADD blended, so the two chamfered-away corners stay dark.
    if not button.fsQueuedWash then
        local function queuedPair()
            local wash = button:CreateTexture(nil, "OVERLAY", nil, 2)
            wash:SetTexture(FS.Theme.SLICE_CUT2_FILL_TEXTURE)
            FS.Theme.ApplyNineSlice(wash, FS.Theme.SLICE_CUT_MARGIN)
            wash:SetVertexColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], QUEUED_WASH_ALPHA)
            wash:SetBlendMode("ADD")
            wash:SetAllPoints(button)
            wash:Hide()

            local pad = FS.Theme.SLICE_CUT2_GLOW_PAD
            local glow = button:CreateTexture(nil, "OVERLAY", nil, 1)
            glow:SetTexture(FS.Theme.SLICE_CUT2_GLOW_TEXTURE)
            FS.Theme.ApplyNineSlice(glow, FS.Theme.SLICE_CUT2_GLOW_MARGIN)
            glow:SetPoint("TOPLEFT", button, "TOPLEFT", -pad, pad)
            glow:SetPoint("BOTTOMRIGHT", button, "BOTTOMRIGHT", pad, -pad)
            glow:SetBlendMode("ADD")
            glow:SetVertexColor(COLOR_POWER[1], COLOR_POWER[2], COLOR_POWER[3], QUEUED_GLOW_ALPHA)
            glow:Hide()
            return wash, glow
        end
        button.fsQueuedWash, button.fsQueuedGlow = queuedPair()   -- IsCurrentAction
        button.fsRepeatWash, button.fsRepeatGlow = queuedPair()   -- IsAutoRepeatAction
    end

    -- A click flips a CheckButton to checked natively, and Blizzard's checked art would
    -- show until the next UpdateState. Blank the template's CheckedTexture (the region
    -- sweep above normally has, this makes it certain) and re-pin the check after each
    -- click half (AnyDown + AnyUp), like PetActionBar's SyncChecked. Insecure; the queued
    -- look is ours (UpdateState), never the CheckButton's.
    local checkedArt = button.GetCheckedTexture and button:GetCheckedTexture()
    if checkedArt then checkedArt:SetAlpha(0) end
    if not button.fsPostClickPinned then
        button.fsPostClickPinned = true   -- hooks stack: never add a second on a re-style
        button:HookScript("PostClick", function(self) self:SetChecked(false) end)
    end

    button:HookScript("OnEnter", ShowActionTooltip)
    button:HookScript("OnLeave", HideActionTooltip)

    -- Icon: seated by FrameHelpers.SeatCutIcon. The icon is a SQUARE texture, so its
    -- top-left and bottom-right corners would poke past the chamfered border as dark
    -- nubs. MaskTexture exists on this client but does not clip (see the Theme.lua note
    -- and FrameHelpers.SeatCutIcon), so the icon is always inset 3px, which puts its
    -- corners on the chamfer line under the border stroke. No mask is created.
    FS.FrameHelpers.SeatCutIcon(button)
    if button.icon then
        button.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    end

    -- The GCD / cooldown swipe. Re-seated onto the icon edge to edge, because
    -- the inherited template leaves it 3px inside the icon (4px inside our
    -- border), which Parker saw as "the GCD ... doesn't extend to the edge".
    -- Full rationale at FrameHelpers.SeatButtonCooldown.
    --
    -- Square swipe (no swipeTexture): the icon is square because masks don't clip here
    -- (see SeatCutIcon), so a cut swipe would leave undimmed icon corners.
    FS.FrameHelpers.SeatButtonCooldown(button)

    -- A swipe that now covers the whole face would also dim the keybind and the
    -- count if they were drawn under the cooldown's child frame. Which frame
    -- they must live on is decided by FrameHelpers.SeatButtonText (Blizzard's
    -- own TextOverlayContainer when this client's template has one above the
    -- cooldown, else a click-through host of ours; see there for what is known
    -- and what is unverified on 16001). Whichever it returns also hosts the
    -- hotkey plate below, so the plate stays above the swipe with the text.
    local textHost = FS.FrameHelpers.SeatButtonText(button, button.HotKey, button.Count)

    -- Seat the keybind in the top-right corner, inside the border. Blizzard's
    -- template anchors it for a 36px button and it hangs off ours otherwise.
    --
    -- Readability comes from a dark PLATE behind the glyphs, not from an
    -- outline or a shadow. Two reasons. ApplyMono deliberately sets neither --
    -- "no OUTLINE (renders unevenly on this font) and no shadow -- the user
    -- judged this cleanest in-game" -- and it runs after this, so a shadow set
    -- here is silently wiped anyway. That is exactly what had been happening:
    -- the keys were rendering as bare cyan on top of bright spell art with no
    -- separation at all, which is why Parker could not read them.
    --
    -- SetWidth(0) restores auto-sizing on a FontString, so the plate anchored
    -- to its edges hugs the text and stays tight on "1" as well as "SHIFT-F".
    if button.HotKey then
        local hotkey = button.HotKey
        hotkey:ClearAllPoints()
        hotkey:SetWidth(0)
        hotkey:SetPoint("TOPRIGHT", button, "TOPRIGHT", -3, -2)
        hotkey:SetJustifyH("RIGHT")
        hotkey:SetDrawLayer("OVERLAY", 4)

        if not button.fsHotkeyPlate then
            -- On the text host, not the button, so it stays above the swipe.
            local plate = textHost:CreateTexture(nil, "OVERLAY", nil, 3)
            plate:SetColorTexture(0.024, 0.012, 0.071, 0.78)
            plate:SetPoint("TOPLEFT", hotkey, "TOPLEFT", -3, 2)
            plate:SetPoint("BOTTOMRIGHT", hotkey, "BOTTOMRIGHT", 3, -2)
            plate:Hide()
            button.fsHotkeyPlate = plate
        end
    end

    if ApplyMono then
        -- A point larger than the count, and white rather than cyan: against a
        -- dark plate white is the most legible, and cyan-on-cyan-border was
        -- reading as decoration rather than as information.
        if button.HotKey then ApplyMono(button.HotKey, 10, COLOR_TEXT_WHITE) end
        if button.Count then ApplyMono(button.Count, 10) end
    end
    if button.Name then button.Name:SetAlpha(0) end
end

local function BuildBar(spec, geo, parent)
    local header = CreateFrame("Frame", "FSActionBar" .. spec.id, parent)
    header:SetSize(geo.barW, geo.barH)

    -- The pill's own chrome (fill, border, MAIN glow and tag) lives on ONE child
    -- frame so the Console can hide it with a single call. It sits at the header's
    -- own level, under the buttons (one level up), like the textures it replaces.
    local chrome = CreateFrame("Frame", nil, header)
    chrome:SetAllPoints(header)
    chrome:SetFrameLevel(header:GetFrameLevel())
    header.fsChrome = chrome

    if AddRoundedFill then
        AddRoundedFill(chrome, spec.paged and MAIN_FILL or BAR_FILL, BAR_RADIUS)
    end
    if AddGradientBorder then
        AddGradientBorder(chrome, spec.paged and COLOR_HEALTH or BAR_BORDER, 1, BAR_RADIUS)
    end
    if spec.paged and AddOuterGlow then
        AddOuterGlow(chrome, COLOR_HEALTH[1], COLOR_HEALTH[2], COLOR_HEALTH[3], 8, 0.45, BAR_RADIUS)
    end

    local buttons = {}
    local previous
    for i = 1, BUTTONS_PER_BAR do
        local button = CreateFrame(
            "CheckButton", ("FSActionButton%d_%d"):format(spec.id, i), header,
            "ActionButtonTemplate, SecureActionButtonTemplate"
        )

        button.index = i
        button.paged = spec.paged
        button.action = spec.paged
            and ((CurrentPage() - 1) * BUTTONS_PER_BAR + i)
            or (spec.firstAction + i - 1)

        -- The canonical binding name for this slot. Note it follows the BAR
        -- and the button's position on it, NOT button.action -- paging bar 1
        -- changes which spell a button fires, but "1" is still bound to the
        -- first button, so this must not be recomputed when the page flips.
        button.bindingAction = spec.binding and (spec.binding .. i) or nil

        SetupDrag(button)

        -- The whole design, in two lines. No snippet, no state driver: the
        -- client resolves these C-side on click. Verified in game 2026-09-20
        -- with a single test button before any of this was built.
        button:SetAttribute("type", "action")
        button:SetAttribute("action", button.action)

        -- Mouseover / self / focus casting. SecureButton_GetModifiedUnit (retail
        -- 12.1 SecureTemplates.lua) honours the enableMouseoverCast CVar and the
        -- MOUSEOVERCAST modifier only on a button carrying these attributes, and
        -- only Blizzard's own ActionBarActionButtonMixin:OnLoad sets them, so a
        -- button we build ourselves must. Build runs out of combat only (the
        -- loader below defers to PLAYER_REGEN_ENABLED), so the secure write is
        -- legal. Mouseover casting is inert while the CVar is off, but checkselfcast
        -- and checkfocuscast act on the player's own SELFCAST and FOCUSCAST
        -- modifiers regardless of it (Blizzard parity). /fsmouseover is the switch.
        button:SetAttribute("checkmouseovercast", true)
        button:SetAttribute("checkselfcast", true)
        button:SetAttribute("checkfocuscast", true)

        -- Free the PICKUP modifier from the secure handler, so holding it turns
        -- a press into a DRAG instead of a cast.
        --
        -- Parker: "if i am holding shift to move a spell on my bar it still
        -- tries to cast it" -- which finally explains the drag failure. With
        -- AnyDown registered the secure cast resolves on mouse-DOWN, before a
        -- drag can begin, so the modifier never gets a chance to matter.
        --
        -- The fix is NOT to drop AnyDown; I tried that and it killed
        -- click-to-cast on every bar. SecureActionButtonTemplate resolves
        -- modifier-prefixed attributes first, so "shift-type1" = "none" makes a
        -- modified press do nothing secure and leaves it available to the drag
        -- handler, while an unmodified click still casts exactly as before.
        --
        -- Read from GetModifiedClick rather than hardcoding shift: the modifier
        -- is a keybinding, and hardcoding it would break for anyone who has
        -- moved it -- and silently disable a modifier they DO use to cast.
        local pickupModifier = GetModifiedClick and GetModifiedClick("PICKUPACTION")
        if pickupModifier == "SHIFT" then
            button:SetAttribute("shift-type1", "none")
        elseif pickupModifier == "CTRL" then
            button:SetAttribute("ctrl-type1", "none")
        elseif pickupModifier == "ALT" then
            button:SetAttribute("alt-type1", "none")
        end
        -- BOTH, and do not "fix" this again.
        --
        -- I narrowed this to "AnyUp" on the theory that AnyDown consumed the
        -- press and prevented drags. That theory was wrong -- Blizzard's own
        -- action buttons register key-down and drag fine -- and narrowing it
        -- stopped click-to-cast working on EVERY bar. This exact pairing is
        -- the configuration Parker confirmed casting with in game.
        --
        -- Whatever is wrong with drag and drop, it is not this line.
        button:RegisterForClicks("AnyUp", "AnyDown")
        button:RegisterForDrag("LeftButton", "RightButton")

        button:ClearAllPoints()
        if previous then
            button:SetPoint("LEFT", previous, "RIGHT", BTN_GAP, 0)
        else
            button:SetPoint("LEFT", header, "LEFT", BAR_PAD, 0)
        end

        StyleButton(button, geo.btnSize)

        -- Take part in Blizzard's Quick Keybind mode under the canonical
        -- command, so hover + key or mouse button binds this button. See
        -- FrameHelpers' Quick Keybind section.
        if button.bindingAction then
            FS.FrameHelpers.AttachQuickKeybind(button, button.bindingAction)
        end

        if button.bindingAction then buttonsByBinding[button.bindingAction] = button end
        allButtons[#allButtons + 1] = button
        buttons[#buttons + 1] = button
        previous = button
    end

    if spec.label then
        local tag = chrome:CreateFontString(nil, "OVERLAY")
        if ApplyMono then ApplyMono(tag, 8, COLOR_HEALTH) end
        tag:SetText(spec.label)
        tag:SetPoint("BOTTOMLEFT", header, "TOPLEFT", 3, -2)
    end

    header.buttons = buttons
    return header
end

-------------------------------------------------------------------------------
-- Perspective grid backdrop
-------------------------------------------------------------------------------

-- Baked by media/generate_grid.py to the mockup's three-layer construction.
-- Seated at FS.Layout.grid -- the previous version used FS.Layout.action, which
-- squeezed a 2560x183 full-width floor into the 1089x178 action-bar box.
local gridFrame

local function EnsureGrid()
    if gridFrame or not (FS.Layout and FS.Layout.Apply and FS.Layout.grid) then return end
    gridFrame = CreateFrame("Frame", "FSActionGrid", UIParent)
    gridFrame:SetFrameStrata("BACKGROUND")
    gridFrame:EnableMouse(false)
    FS.Layout.Apply(gridFrame, "grid")

    -- The layout's 2560 design px scales to 2133 UI units, but the screen is
    -- 2151 wide -- so the floor stopped ~9 units short at each edge and you
    -- could see the world behind it. The grid is meant to be edge-to-edge, so
    -- take the width from UIParent and keep only the layout's height/anchor.
    local screenWidth = UIParent:GetWidth()
    if screenWidth and screenWidth > 0 then
        gridFrame:SetWidth(screenWidth)
    end

    local tex = gridFrame:CreateTexture(nil, "BACKGROUND")
    tex:SetTexture("Interface\\AddOns\\forever-stuwave\\Media\\Textures\\grid.tga")
    tex:SetAllPoints(gridFrame)
    gridFrame.fsTexture = tex
end

-------------------------------------------------------------------------------
-- Assembly
-------------------------------------------------------------------------------

local stack
local headers = {}
local geometryCallbacks = {}

-- One sizing pass over the whole stack, separated out because it has to run
-- AGAIN after any layout re-seat. FS.Layout.Apply resets a frame to the raw
-- layout size, so the pill-hugging widths computed here are otherwise undone
-- the moment the PLAYER_LOGIN watcher re-applies -- which is exactly why the
-- first attempt at this changed nothing on screen.
local function NotifyGeometry()
    if not ActionBars.geometry then return end
    for _, fn in ipairs(geometryCallbacks) do
        pcall(fn, ActionBars.geometry)
    end
end

-- Console.lua subscribes here. Called after every re-seat with the fresh
-- geometry, and at once when a seat already happened, so load order is free.
function ActionBars.OnGeometry(fn)
    geometryCallbacks[#geometryCallbacks + 1] = fn
    if ActionBars.geometry then pcall(fn, ActionBars.geometry) end
end

local function SeatAll(geo)
    if not stack then return end
    stack:SetSize(geo.stackW, geo.stackH)

    for _, header in ipairs(headers) do
        local index = header.fsIndex
        local row = math.floor((index - 1) / BARS_PER_ROW)
        local col = (index - 1) % BARS_PER_ROW

        header:SetSize(geo.barW, geo.barH)
        header:ClearAllPoints()
        header:SetPoint(
            "TOPLEFT", stack, "TOPLEFT",
            STACK_PAD + col * (geo.barW + geo.gap),
            -(STACK_PAD + row * (geo.barH + STACK_GAP))
        )
        if header.fsChrome then header.fsChrome:SetShown(not consoleActive) end

        for _, button in ipairs(header.buttons or {}) do
            button:SetSize(geo.btnSize, geo.btnSize)
        end
    end

    -- What the Console needs, in UI units from the stack's TOPLEFT, y down. The
    -- buttons sit BAR_PAD inside their pill on every side (barH = btnSize + 2 *
    -- BAR_PAD), the spine is the stack's centre.
    local halfX = { STACK_PAD, STACK_PAD + geo.barW + geo.gap }
    local fieldTop = STACK_PAD + (geo.barH - geo.btnSize) / 2
    local rowPitch = geo.barH + STACK_GAP
    ActionBars.geometry = {
        stack = stack,
        console = consoleActive,
        shown = usingFS,
        scale = FS.Layout and FS.Layout.Scale and FS.Layout.Scale() or 1,
        btnSize = geo.btnSize,
        btnPitch = geo.btnSize + BTN_GAP,
        btnX0 = BAR_PAD,
        barW = geo.barW,
        barH = geo.barH,
        gap = geo.gap,
        rowPitch = rowPitch,
        halfX = halfX,
        stackW = geo.stackW,
        stackH = geo.stackH,
        spineX = geo.stackW / 2,
        fieldLeft = halfX[1] + BAR_PAD,
        fieldRight = halfX[2] + geo.barW - BAR_PAD,
        fieldTop = fieldTop,
        fieldBottom = fieldTop + (ROWS - 1) * rowPitch + geo.btnSize,
    }
    NotifyGeometry()
end

-- Re-seat the whole stack from the layout, out of combat only. In lockdown the
-- request is remembered and PLAYER_REGEN_ENABLED replays it.
local function RequestSeat()
    local L = FS.Layout and FS.Layout.action
    if not (stack and L) then return false end
    if InCombatLockdown() then
        pendingSeat = true
        return false
    end
    pendingSeat = false
    SeatAll(ComputeGeometry(L))
    return true
end

-- Switches the Console look: pill chrome off and a wide spine, or the pill look.
-- Returns true when applied (or when there is no stack yet and the next build
-- will pick it up). Otherwise false plus the reason: "combat" (waits for regen) or
-- "unavailable" (no layout to seat from yet; the choice is held).
function ActionBars.SetConsoleActive(on)
    on = on and true or false
    if on == consoleActive then
        pendingConsole = nil
        return true
    end
    if not stack then
        consoleActive = on
        return true
    end
    if InCombatLockdown() then
        pendingConsole = on
        return false, "combat"
    end
    pendingConsole = nil
    consoleActive = on
    if RequestSeat() then return true end
    return false, "unavailable"
end

function ActionBars.IsConsoleActive()
    return consoleActive
end

local function BuildStack()
    if stack then return stack end
    local layout = FS.Layout and FS.Layout.action
    if not layout then return nil end

    local geo

    stack = CreateFrame("Frame", "FSActionBarStack", UIParent)
    local applied = FS.Layout.Apply(stack, "action")
    geo = ComputeGeometry(applied or layout)
    stack:SetSize(geo.stackW, geo.stackH)
    stack:SetFrameStrata("LOW")

    for index, spec in ipairs(BARS) do
        local header = BuildBar(spec, geo, stack)
        header.fsIndex = index
        headers[#headers + 1] = header
    end

    SeatAll(geo)
    return stack
end

-------------------------------------------------------------------------------
-- Events
-------------------------------------------------------------------------------

local events = CreateFrame("Frame")

local function OnEvent(_, event, arg1)
    if event == "PLAYER_REGEN_ENABLED" or event == "UPDATE_BINDINGS" then
        ReleaseAllPresses()
    end
    if event == "PLAYER_REGEN_ENABLED" then
        if pendingConsole ~= nil then
            consoleActive = pendingConsole
            pendingConsole = nil
            pendingSeat = true
        end
        if pendingSeat then RequestSeat() end
        if pendingPage then RequestPage() end
        UpdateAll()
    elseif event == "ACTIONBAR_SLOT_CHANGED" then
        -- arg1 is the changed slot, or 0 meaning "all of them".
        if arg1 and arg1 ~= 0 then
            for _, button in ipairs(allButtons) do
                if button.action == arg1 then UpdateButton(button) end
            end
        else
            UpdateAll()
        end
    elseif event == "ACTIONBAR_PAGE_CHANGED"
        or event == "UPDATE_BONUS_ACTIONBAR"
        or event == "UPDATE_VEHICLE_ACTIONBAR"
        or event == "UPDATE_OVERRIDE_ACTIONBAR"
        or event == "UPDATE_SHAPESHIFT_FORM" then
        RequestPage()
    elseif event == "CURRENT_SPELL_CAST_CHANGED"
        or event == "START_AUTOREPEAT_SPELL"
        or event == "STOP_AUTOREPEAT_SPELL"
        or event == "PLAYER_ENTER_COMBAT"
        or event == "PLAYER_LEAVE_COMBAT" then
        UpdateAllState()
    else
        UpdateAll()
    end
end

local function RegisterEvents()
    for _, event in ipairs({
        "PLAYER_ENTERING_WORLD",
        "PLAYER_REGEN_ENABLED",
        "ACTIONBAR_SLOT_CHANGED",
        "ACTIONBAR_UPDATE_COOLDOWN",
        "ACTIONBAR_UPDATE_USABLE",
        "ACTIONBAR_UPDATE_STATE",
        "ACTIONBAR_PAGE_CHANGED",
        "UPDATE_BONUS_ACTIONBAR",
        "UPDATE_VEHICLE_ACTIONBAR",
        "UPDATE_OVERRIDE_ACTIONBAR",
        "UPDATE_SHAPESHIFT_FORM",
        "SPELL_UPDATE_COOLDOWN",
        "SPELL_UPDATE_USABLE",
        "PLAYER_TARGET_CHANGED",
        -- Queued / active state (UpdateState): a queued next-swing ability, auto-attack
        -- and auto-repeat toggling. ACTIONBAR_UPDATE_STATE above is Blizzard's own
        -- trigger; these cover the intent changes it does not always raise.
        "CURRENT_SPELL_CAST_CHANGED",
        "START_AUTOREPEAT_SPELL",
        "STOP_AUTOREPEAT_SPELL",
        "PLAYER_ENTER_COMBAT",
        "PLAYER_LEAVE_COMBAT",
        -- Keybinds are player config, so they change on their own schedule --
        -- without this the text is only correct until the first time the
        -- bindings UI is used. Quick Keybind mode's SetBinding calls raise it
        -- too (stock buttons refresh their hotkeys from the same event); the
        -- mode's own RebindSuccess / close signals are wired in Apply as well.
        "UPDATE_BINDINGS",
    }) do
        -- Individually guarded: a name absent on this client should skip, not
        -- abort the whole registration and leave the bars static.
        pcall(events.RegisterEvent, events, event)
    end
    events:SetScript("OnEvent", OnEvent)
end

-------------------------------------------------------------------------------
-- Slash command (escape hatch)
-------------------------------------------------------------------------------

local function SetMode(mode)
    if InCombatLockdown() then
        print("|cff22e0ffForever STUwave|r: cannot switch action bars in combat.")
        return
    end

    if mode == "blizz" then
        if stack then stack:Hide() end
        if gridFrame then gridFrame:Hide() end
        ForEachBlizzardBar(RestoreBlizzardBar)
        usingFS = false
        if ActionBars.geometry then ActionBars.geometry.shown = false; NotifyGeometry() end
        print("|cff22e0ffForever STUwave|r: Blizzard action bars restored. /fsbars fs to switch back.")
    else
        ForEachBlizzardBar(HideBlizzardBar)
        if stack then stack:Show() end
        if gridFrame then gridFrame:Show() end
        usingFS = true
        if ActionBars.geometry then ActionBars.geometry.shown = true; NotifyGeometry() end
        print("|cff22e0ffForever STUwave|r: synthwave action bars active.")
    end
end

SLASH_FSBARS1 = "/fsbars"
SlashCmdList["FSBARS"] = function(msg)
    msg = (msg or ""):lower():gsub("%s", "")
    if msg == "blizz" or msg == "blizzard" or msg == "off" then
        SetMode("blizz")
    elseif msg == "fs" or msg == "on" then
        SetMode("fs")
    else
        print("|cff22e0ffForever STUwave|r: /fsbars blizz | /fsbars fs  (currently "
            .. (usingFS and "synthwave" or "Blizzard") .. ")")
    end
end

-------------------------------------------------------------------------------
-- Mouseover casting: /fsmouseover [on|off] [alt|ctrl|shift|none]
--
-- The buttons carry checkmouseovercast (see the build loop); whether it does
-- anything is two player settings Blizzard keeps: the enableMouseoverCast CVar
-- and the MOUSEOVERCAST modified-click key (NONE = always, else hold that key).
-- Both are what Blizzard's own settings UI writes (SetCVar, then
-- SetModifiedClick + SaveBindings; Blizzard_ClickBindingUI.lua). Off by default,
-- never forced on.
--
-- SetModifiedClick and SaveBindings are treated as protected in combat
-- (unverified; Blizzard calls them directly), so a modifier change in combat (or
-- one the client refuses) is held in pending and replayed on PLAYER_REGEN_ENABLED.
-- The CVar is not protected and applies at once.
-------------------------------------------------------------------------------

local Mouseover = {
    CVAR = "enableMouseoverCast",
    CLICK = "MOUSEOVERCAST",
    HINT = "Forever STUwave: mouseover casting is off. /fsmouseover on to cast on the "
        .. "unit under your mouse without changing target.",
    pending = nil,   -- modifier key waiting for the end of combat
}

local function MouseoverSay(text)
    print("|cff22e0ffForever STUwave|r: " .. text)
end

function Mouseover.IsOn()
    if not GetCVarBool then return false end
    local ok, on = pcall(GetCVarBool, Mouseover.CVAR)
    return ok and on and true or false
end

function Mouseover.Modifier()
    if not GetModifiedClick then return "NONE" end
    local ok, key = pcall(GetModifiedClick, Mouseover.CLICK)
    return (ok and type(key) == "string" and key ~= "") and key or "NONE"
end

-- Returns true when applied, false when the client refused it.
function Mouseover.WriteModifier(key)
    return pcall(function()
        SetModifiedClick(Mouseover.CLICK, key)
        SaveBindings(GetCurrentBindingSet())
    end)
end

function Mouseover.OnRegen(frame)
    frame:UnregisterEvent("PLAYER_REGEN_ENABLED")
    local key = Mouseover.pending
    Mouseover.pending = nil
    if key then Mouseover.SetModifier(key) end
end

function Mouseover.Defer(key, why)
    Mouseover.pending = key
    if not Mouseover.frame then
        Mouseover.frame = CreateFrame("Frame")
        Mouseover.frame:SetScript("OnEvent", Mouseover.OnRegen)
    end
    Mouseover.frame:RegisterEvent("PLAYER_REGEN_ENABLED")
    MouseoverSay(("%s; the %s modifier applies when combat ends."):format(why, key))
end

function Mouseover.SetModifier(key)
    if not (SetModifiedClick and SaveBindings and GetCurrentBindingSet) then
        MouseoverSay("this client has no way to set the mouseover modifier.")
        return
    end
    if InCombatLockdown() then
        Mouseover.Defer(key, "in combat")
    elseif Mouseover.WriteModifier(key) then
        Mouseover.pending = nil   -- a stale queued key must not replay over this one
        MouseoverSay("mouseover cast modifier set to |cffff2e97" .. key .. "|r.")
    else
        Mouseover.Defer(key, "the client refused the change")
    end
end

function Mouseover.Report()
    local key = Mouseover.Modifier()
    MouseoverSay(("mouseover casting is |cffff2e97%s|r, modifier |cffff2e97%s|r%s."):format(
        Mouseover.IsOn() and "on" or "off", key, key == "NONE" and " (always)" or " (hold it)"))
    MouseoverSay("/fsmouseover [on|off] [alt|ctrl|shift|none]")
end

local MOUSEOVER_KEYS = { alt = "ALT", ctrl = "CTRL", shift = "SHIFT", none = "NONE" }

SLASH_FSMOUSEOVER1 = "/fsmouseover"
SlashCmdList["FSMOUSEOVER"] = function(msg)
    local turn, key
    for word in (msg or ""):lower():gmatch("%S+") do
        if word == "on" or word == "off" then
            turn = word
        elseif MOUSEOVER_KEYS[word] then
            key = MOUSEOVER_KEYS[word]
        else
            -- One bad word cancels the whole command, so a typo never half-applies.
            Mouseover.Report()
            return
        end
    end
    if not turn and not key then
        Mouseover.Report()
        return
    end
    if turn then
        -- SetCVar returns a success bool and can refuse without throwing.
        local ok, set = pcall(SetCVar, Mouseover.CVAR, turn == "on" and "1" or "0")
        if ok and set ~= false then
            MouseoverSay("mouseover casting |cffff2e97" .. turn .. "|r.")
        else
            MouseoverSay("could not set the " .. Mouseover.CVAR .. " CVar.")
        end
    end
    if key then Mouseover.SetModifier(key) end
end

-- First login after this shipped: say once, if the CVar is off, that the feature
-- exists. The flag is stored whether or not the hint printed, so turning the CVar
-- off later does not bring the hint back.
function Mouseover.Hint()
    if type(ForeverSTUwaveDB) ~= "table" then ForeverSTUwaveDB = {} end
    if ForeverSTUwaveDB.mouseoverHintSeen then return end
    ForeverSTUwaveDB.mouseoverHintSeen = true
    if not Mouseover.IsOn() then print(Mouseover.HINT) end
end

-------------------------------------------------------------------------------
-- Init
-------------------------------------------------------------------------------

local function Apply()
    EnsureGrid()

    -- Build ours first, and only take Blizzard's away if that worked: a failure
    -- leaves the player with working stock bars rather than none.
    local ok, err = pcall(BuildStack)
    if not ok or not stack then
        print("|cff22e0ffForever STUwave|r: action bars failed to build ("
            .. tostring(err) .. "); Blizzard bars left in place.")
        return
    end

    -- Re-seating restores the raw layout size, so re-run our own sizing after
    -- the watcher has had its turn.
    if FS.Layout.OnRescale then
        FS.Layout.OnRescale(RequestSeat)
    end

    FS.FrameHelpers.OnQuickKeybindChanged(UpdateAllHotkeys)
    RegisterEvents()
    InstallPressHooks()
    ApplyPage()

    -- Restore an explicitly chosen hide strategy BEFORE the first hide, so a
    -- session picks up where the last one left off. Only /fstaint writes this
    -- key, so an unset value means "never chose" and gets the default (dim);
    -- a saved "stash" is an experiment someone opted into and is honoured.
    -- Account-wide store: the only one this client restores (see the .toc
    -- header).
    local savedStrategy = type(ForeverSTUwaveDB) == "table"
        and ForeverSTUwaveDB.barHideStrategy
    if savedStrategy == "stash" or savedStrategy == "dim" then
        hideStrategy = savedStrategy
    end

    ForEachBlizzardBar(HideBlizzardBar)
end

-- Deferred to PLAYER_LOGIN rather than run at file scope: UIParent is not fully
-- sized during addon load (768 tall there, 1200 by login on this client), and
-- the button edge is SOLVED from the stack width -- so building early bakes a
-- ~64%-scale layout that re-seating alone cannot undo.
local loader = CreateFrame("Frame")
loader:RegisterEvent("PLAYER_LOGIN")
loader:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")
    pcall(Mouseover.Hint)
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
