-- Forever STUwave: Panel Skins
-- Shared machinery behind the FIRST PASS Blizzard-panel reskins (Panels,
-- Tooltip, Popups, Bags, Loot, AuctionHouse, Tracker): the combat-safe defer
-- wrapper, a loud-fail-once load guard, money-frame styling, the skin-once-
-- and-cache pattern tooltips/loot share, and a table-driven scan/skin/watch
-- driver for the panel registries. Loaded before every consumer (see .toc).

local _, FS = ...
FS.PanelSkins = FS.PanelSkins or {}
local PanelSkins = FS.PanelSkins

-------------------------------------------------------------------------------
-- Combat-safe defer
-------------------------------------------------------------------------------

-- Runs `fn` immediately, or once PLAYER_REGEN_ENABLED fires if the caller is
-- in combat. None of the panels this addon skins are secure, but every
-- consumer defers anyway for consistency with the rest of the addon's Init
-- pattern.
function PanelSkins.DeferCombat(fn)
    if InCombatLockdown() then
        local regen = CreateFrame("Frame")
        regen:RegisterEvent("PLAYER_REGEN_ENABLED")
        regen:SetScript("OnEvent", function(self)
            self:UnregisterEvent("PLAYER_REGEN_ENABLED")
            fn()
        end)
    else
        fn()
    end
end

-------------------------------------------------------------------------------
-- Loud-fail-once load guard
-------------------------------------------------------------------------------

-- Meant to be called ONCE at file scope (load time) by each consumer, not
-- per-call, so it never spams. Mirrors Theme.lua's warnedNoSliceMargins
-- degrade-and-warn shape (colored chat message, once per session) rather than
-- a raw assert/error, since a missing export should disable that one file's
-- reskin, not the whole addon.
function PanelSkins.RequireExport(export, label)
    if export then return true end

    local msg = ("|cffff4488Forever STUwave|r: %s"):format(label)
    FS.LogDegradeOnce("require:" .. label, msg)
    return false
end

-------------------------------------------------------------------------------
-- Theme (shared chrome + palette; see Theme.lua for signatures)
-------------------------------------------------------------------------------

local Theme = FS.Theme
local SkinPanel = Theme.SkinPanel
local StyleMoney = Theme.StyleMoney

-- Warns once, but does NOT abort the chunk: only SkinPanelCached actually
-- calls SkinPanel, and an early return here would also delete every
-- unrelated export below (TryStyleMoney, CreateSkinDriver, RegisterRecon,
-- ...) for every consumer, including ones like Tracker.lua that have no
-- SkinPanel dependency at all. SkinPanelCached carries its own direct guard.
PanelSkins.RequireExport(SkinPanel, "PanelSkins.lua panel-cache disabled: FS.Theme.SkinPanel missing")

-------------------------------------------------------------------------------
-- Money styling
-------------------------------------------------------------------------------

-- A MoneyFrameTemplate instance always sets `staticMoney` (even to false) and
-- always spawns a `<name>GoldButtonText` fontstring, so either is a reliable
-- fingerprint for "this is a real money frame" regardless of what it's named
-- or parented under.
local function LooksLikeMoneyFrame(candidate)
    if type(candidate) ~= "table" then return false end
    if candidate.staticMoney ~= nil then return true end

    local name = candidate.GetName and candidate:GetName()
    return name ~= nil and _G[name .. "GoldButtonText"] ~= nil
end

-- Locates a panel's MoneyFrame three ways, in order: the modern parentKey
-- attribute (`frame.MoneyFrame`), the legacy global-name-suffix convention
-- (`<FrameName>MoneyFrame`, used by the numbered ContainerFrameN/BankFrame),
-- and -- confirmed needed for ContainerFrameCombinedBags, whose `.MoneyFrame`
-- is nil on interface 16001 -- a scan of the frame's direct children for
-- anything that looks like a money frame. A miss on all three is a silent
-- no-op.
local function ResolveMoneyFrame(frame)
    if not frame then return nil end

    local money = frame.MoneyFrame
    if not money then
        local name = frame.GetName and frame:GetName()
        if name then
            money = _G[name .. "MoneyFrame"]
        end
    end

    if not money and frame.GetChildren then
        for _, child in ipairs({ frame:GetChildren() }) do
            if LooksLikeMoneyFrame(child) then
                money = child
                break
            end
        end
    end

    return money
end

function PanelSkins.TryStyleMoney(frame)
    if not StyleMoney or not frame then return end

    local money = ResolveMoneyFrame(frame)
    if money then
        StyleMoney(money)
    end
end

-------------------------------------------------------------------------------
-- Panel-skin-once-and-cache
-------------------------------------------------------------------------------

-- Creates the panel chrome once (guarded by frame.fsSkinCache) and re-shows
-- the stored regions on every call after that, so an OnShow hook can call
-- this repeatedly without stacking a new set of textures per show. Unifies
-- what used to be two identical functions (Tooltip.lua's SkinTooltip,
-- Loot.lua's SkinLootPanel) under one marker field name.
function PanelSkins.SkinPanelCached(frame, opts)
    if not frame or not SkinPanel then return end

    if not frame.fsSkinCache then
        frame.fsSkinCache = SkinPanel(frame, opts) or true
    end

    local chrome = frame.fsSkinCache
    if type(chrome) == "table" then
        for _, region in ipairs(chrome) do
            if region.Show then region:Show() end
        end
    end
end

-- Hooks OnShow exactly once per frame, guarded by a caller-supplied marker
-- field, so a re-apply handler never stacks a second hook on the same frame.
function PanelSkins.HookShowOnce(frame, guardField, handler)
    if not frame or frame[guardField] then return end
    if not frame.HookScript then return end

    frame:HookScript("OnShow", handler)
    frame[guardField] = true
end

-------------------------------------------------------------------------------
-- Registry + generic scan/skin/watch driver
-------------------------------------------------------------------------------

-- Generic Blizzard_* addon-loaded matcher: true for any loaded addon name
-- starting "Blizzard_". Used as the default ADDON_LOADED filter below.
local function MatchesBlizzardPrefix(loadedAddonName)
    return loadedAddonName ~= nil and loadedAddonName:find("^Blizzard_") ~= nil
end

-- Creates a watcher frame that calls `callback` on PLAYER_ENTERING_WORLD and
-- on ADDON_LOADED whenever `matches(loadedAddonName)` is true (default: any
-- Blizzard_* module -- pass an explicit-name matcher when a panel knows its
-- exact load-on-demand module, which is tighter; see AuctionHouse.lua).
function PanelSkins.WatchAddonLoad(callback, matches)
    matches = matches or MatchesBlizzardPrefix
    local watcher = CreateFrame("Frame")
    watcher:RegisterEvent("ADDON_LOADED")
    watcher:RegisterEvent("PLAYER_ENTERING_WORLD")
    watcher:SetScript("OnEvent", function(_, event, loadedAddonName)
        if event == "ADDON_LOADED" and not matches(loadedAddonName) then
            return
        end
        callback()
    end)
    return watcher
end

-- Generic scan/skin/watch driver for a registry of Blizzard panels that are
-- either present at login or load on demand. `config`:
--   entries      - list of registry entries; shape is caller-defined and
--                  passed straight through to skinEntry
--   skinEntry    - function(entry) called once per entry on every scan pass;
--                  responsible for its own frame lookup + fsXSkin idempotency
--                  guard, so a repeated scan is always a cheap no-op
--   afterScan    - optional function() called once after each full pass over
--                  entries (e.g. Panels.lua's LightenParchmentFonts retint)
--   matchesAddon - optional function(loadedAddonName) -> bool filter for the
--                  ADDON_LOADED watcher; defaults to the generic "^Blizzard_"
--                  prefix match
--   onWatch      - optional function() called instead of the scan itself on
--                  every watcher fire (Popups.lua uses this to also re-hook
--                  OnShow on newly-appeared frames); defaults to the scan
-- Returns the ScanAndSkin function and the watcher frame.
function PanelSkins.CreateSkinDriver(config)
    local entries = config.entries
    local skinEntry = config.skinEntry

    local function ScanAndSkin()
        for _, entry in ipairs(entries) do
            skinEntry(entry)
        end
        if config.afterScan then config.afterScan() end
    end

    local watcher = PanelSkins.WatchAddonLoad(config.onWatch or ScanAndSkin, config.matchesAddon)

    return ScanAndSkin, watcher
end

-------------------------------------------------------------------------------
-- Panel guts (content-child strip/hide/retint)
-------------------------------------------------------------------------------

-- FS.LogDegradeOnce does NOT dedupe by key itself (see ErrorLog.lua): every
-- caller keeps its own once-per-session guard. `loggedGutsPaths` is that
-- guard for `ResolveGutsPath`, module-level rather than per-call, since the
-- same path can be re-resolved across many ApplyGuts passes.
local loggedGutsPaths = {}

-- Resolves a plain global name, or a "Global.field[.field]" path where only
-- the first segment is an `_G` lookup and every later segment is a plain
-- table index (so "GossipFrame.GreetingPanel.ScrollBox" resolves as
-- `_G.GossipFrame.GreetingPanel.ScrollBox`, never `_G["A.B.C"]`). A path that
-- fails to resolve logs once via `FS.LogDegradeOnce` (guarded by
-- `loggedGutsPaths`, keyed on the path itself) unless `silent` is true, which
-- callers pass when "not resolved yet" is an expected, self-healing state
-- rather than a real miss (`ApplyGutsRows`' scrollBox resolution).
local function ResolveGutsPath(path, silent)
    local first, rest = path:match("^([^.]+)(%..+)$")
    local region = _G[first or path]
    if region and rest then
        for field in rest:gmatch("%.([^.]+)") do
            region = region and region[field]
        end
    end

    if not region and not silent and not loggedGutsPaths[path] then
        loggedGutsPaths[path] = true
        FS.LogDegradeOnce("guts-path:" .. path,
            ("|cffff4488Forever STUwave|r: panel-guts path not found: %s"):format(path))
    end
    return region
end

-- Strips leftover Blizzard chrome from named CONTENT children of an already-
-- skinned panel (e.g. ItemTextFrame's ItemTextScrollFrame), not just the
-- panel's own frame. Theme.StripBlizzardChrome is already idempotent and
-- self-reinstalls its own OnShow re-strip, so calling this again on an
-- already-stripped frame is a cheap no-op. `names` is a list of plain _G
-- frame names or "Frame.field" paths (`ResolveGutsPath`); a miss no-ops after
-- its one-time log.
function PanelSkins.StripNamed(names)
    for _, name in ipairs(names) do
        local frame = ResolveGutsPath(name)
        if frame then
            Theme.StripBlizzardChrome(frame)
        end
    end
end

-- Hides leftover Blizzard chrome Blizzard re-asserts per page/open (e.g.
-- ItemText's four corner materials, Mail's stationery backgrounds). `list`
-- entries: { name = <_G texture/frame name>, alpha0 = bool }. `alpha0` true
-- means Blizzard re-asserts full ALPHA (not visibility) on that object, so
-- SetAlpha(0) is reapplied every call with no hook needed; `alpha0` false
-- means Hide() once, then re-hidden by a SINGLE HookScript("OnShow") on the
-- object's own parent (guarded by `parent.fsGutsHideHooked` so a repeated
-- call never stacks a second hook) that re-hides every object this function
-- has ever hidden under that parent -- de-duped by `parent.fsGutsHiddenSet`
-- keyed on object identity, since ApplyGuts re-runs this on every re-scan
-- and a plain append would grow the list with the same objects each pass.
function PanelSkins.HideNamed(list)
    for _, entry in ipairs(list) do
        local obj = ResolveGutsPath(entry.name)
        if obj then
            if entry.alpha0 then
                if obj.SetAlpha then obj:SetAlpha(0) end
            elseif obj.Hide then
                obj:Hide()
                local parent = obj.GetParent and obj:GetParent()
                if parent and parent.HookScript then
                    parent.fsGutsHidden = parent.fsGutsHidden or {}
                    parent.fsGutsHiddenSet = parent.fsGutsHiddenSet or {}
                    local hidden = parent.fsGutsHidden
                    local hiddenSet = parent.fsGutsHiddenSet
                    if not hiddenSet[obj] then
                        hiddenSet[obj] = true
                        hidden[#hidden + 1] = obj
                    end
                    if not parent.fsGutsHideHooked then
                        parent.fsGutsHideHooked = true
                        parent:HookScript("OnShow", function()
                            for _, hiddenObj in ipairs(hidden) do
                                if hiddenObj.Hide then hiddenObj:Hide() end
                            end
                        end)
                    end
                end
            end
        end
    end
end

-- Retints a dark-on-parchment text region (a plain FontString, e.g.
-- ItemTextCurrentPage, or a SimpleHTML, e.g. ItemTextPageText) to `color`,
-- gated by `Theme.IsDarkText` the same way `Theme.LightenParchmentFonts`
-- gates shared font objects: only genuinely dark text is touched, and a
-- saturated state color (RED_FONT_COLOR's luma is ~0.31, under the plain
-- luma threshold, but its red channel is bright) is never mistaken for it,
-- since the hook below would otherwise re-assert mint over it forever.
-- `opts.simpleHTML` +
-- `opts.textTypes` (e.g. {"P","H1","H2","H3"}) read/write per-textType via
-- `region:GetTextColor(textType)`/`SetTextColor(textType, r,g,b)`, both
-- pcall'd since a SimpleHTML missing a given textType errors rather than
-- returning nil; a plain FontString instead reads/writes with no textType
-- argument. Installs ONE hooksecurefunc(region, "SetTextColor", ...) so
-- Blizzard's own repaint (a new book/letter page) is caught too, guarded by
-- `region.fsRetintHooked`; `region.fsRetintApplying` stops our own
-- SetTextColor call inside that hook from recursing into itself.
function PanelSkins.RetintDarkText(region, color, opts)
    if not region or not region.SetTextColor or not region.GetTextColor then return end
    opts = opts or {}
    color = color or Theme.COLOR_TEXT_PARCHMENT

    local function isDark(textType)
        local ok, r, g, b
        if opts.simpleHTML and textType then
            ok, r, g, b = pcall(region.GetTextColor, region, textType)
        else
            ok, r, g, b = pcall(region.GetTextColor, region)
        end
        return ok and r and Theme.IsDarkText(r, g, b)
    end

    local function apply()
        if region.fsRetintApplying then return end
        region.fsRetintApplying = true
        if opts.simpleHTML and opts.textTypes then
            for _, textType in ipairs(opts.textTypes) do
                if isDark(textType) then
                    pcall(region.SetTextColor, region, textType, color[1], color[2], color[3])
                end
            end
        elseif isDark() then
            pcall(region.SetTextColor, region, color[1], color[2], color[3])
        end
        region.fsRetintApplying = false
    end

    apply()

    if not region.fsRetintHooked then
        region.fsRetintHooked = true
        hooksecurefunc(region, "SetTextColor", apply)
    end
end

-- Rewrites a single dark |cffRRGGBB inline color code to `color`, gated by
-- `Theme.IsDarkText` exactly like RetintDarkText, so bright inline codes
-- (state colors: gray "used" gossip/trainer text, quest-complete gold, and
-- crucially a saturated RED_FONT_COLOR "can't learn"/"can't afford" warning,
-- whose luma alone reads as dark) pass through untouched. Returns nil (leave
-- as-is) when the code isn't dark. Channels are rounded, not truncated, so
-- the emitted code is the exact token hex (0.749 -> bf, not be).
local function RewriteInlineColorCode(hex, color)
    local r = tonumber(hex:sub(1, 2), 16) / 255
    local g = tonumber(hex:sub(3, 4), 16) / 255
    local b = tonumber(hex:sub(5, 6), 16) / 255
    if not Theme.IsDarkText(r, g, b) then return nil end

    return ("|cff%02x%02x%02x"):format(
        math.floor(color[1] * 255 + 0.5), math.floor(color[2] * 255 + 0.5), math.floor(color[3] * 255 + 0.5))
end

-- Rewrites every dark inline color code in `text` to `color`; returns nil
-- (not the unchanged string) when nothing needed rewriting, so callers can
-- skip the SetText round-trip entirely on an already-bright line.
local function RewriteInlineColorText(text, color)
    if not text then return nil end

    local changed = false
    local rewritten = text:gsub("|c[fF][fF](%x%x%x%x%x%x)", function(hex)
        local replacement = RewriteInlineColorCode(hex, color)
        if replacement then changed = true end
        return replacement -- nil/false leaves gsub's match text untouched
    end)
    return changed and rewritten or nil
end

-- FS.LogDegradeOnce does not dedupe by key (see ErrorLog.lua), so this is the
-- once-per-session guard for a failed rewrite SetText, shared by every target.
local loggedInlineRewriteError = false

-- Hooks SetText/SetFormattedText on `target` (a Button or FontString -- both
-- expose SetText; SetFormattedText is feature-detected since a FontString has
-- it but not every Button-like object is guaranteed to) to rewrite dark
-- inline |cffRRGGBB codes to `color` (default `Theme.COLOR_TEXT_PARCHMENT`).
-- Hooked once per target (`fsInlineRewriteHooked`); `fsInlineRewriteApplying`
-- guards against the hook's own re-entrant SetText call, the same
-- re-entrancy shape as `RetintDarkText`'s `fsRetintApplying`. Shared by
-- GossipFrame's row text and ClassTrainerFrame's row text, both of which
-- embed state color via inline code rather than SetTextColor.
--
-- The hooks only see FUTURE writes, but our row skin runs AFTER Blizzard's
-- initializer already set the text (a quest title row carries
-- `|cff000000%s|r`), so a freshly acquired row would stay black until its
-- frame was reused. Installing the hooks therefore also rewrites the text
-- the target holds right now (ElvUI's Gossip.lua does the same,
-- `Gossip_SetText(button, button:GetText())`).
function PanelSkins.HookInlineColorRewrite(target, color)
    if not target or target.fsInlineRewriteHooked then return end
    target.fsInlineRewriteHooked = true
    color = color or Theme.COLOR_TEXT_PARCHMENT

    -- The one entry for every text this hook sees (install-time current text,
    -- SetText, SetFormattedText): a non-string or secret value is skipped, never
    -- matched. The inner SetText is pcall'd so the Applying flag always clears;
    -- a failure degrades to one log line instead of throwing out of Blizzard's
    -- own SetText call and leaving this target stuck un-rewritten.
    local function rewriteNow(self, text)
        if type(text) ~= "string" or (FS.IsSecret and FS.IsSecret(text)) then return end

        local rewritten = RewriteInlineColorText(text, color)
        if not rewritten then return end

        self.fsInlineRewriteApplying = true
        local ok, err = pcall(self.SetText, self, rewritten)
        self.fsInlineRewriteApplying = false
        if not ok and not loggedInlineRewriteError then
            if FS.LogDegradeOnce then
                loggedInlineRewriteError = true
                FS.LogDegradeOnce("inline_rewrite",
                    ("|cffff4488Forever STUwave|r: inline colour rewrite SetText failed: %s"):format(tostring(err)))
            end
        end
    end

    hooksecurefunc(target, "SetText", function(self, text)
        if self.fsInlineRewriteApplying then return end
        rewriteNow(self, text)
    end)

    if target.SetFormattedText then
        hooksecurefunc(target, "SetFormattedText", function(self, format, ...)
            if self.fsInlineRewriteApplying then return end
            local ok, text = pcall(string.format, format, ...)
            if ok then rewriteNow(self, text) end
        end)
    end

    -- The text already on the target. GetText is feature-detected; rewriteNow
    -- skips a secret or non-string answer.
    if target.GetText then
        local ok, current = pcall(target.GetText, target)
        if ok then rewriteNow(target, current) end
    end
end

-- Resolves one retint entry's target region: `r.region`, if the caller
-- already has one (e.g. a dynamically-created FontString), wins outright.
-- Otherwise `r.name` goes through `ResolveGutsPath` (plain global or
-- "Frame.field" path).
local function ResolveGutsRegion(r)
    if r.region then return r.region end
    if not r.name then return nil end
    return ResolveGutsPath(r.name)
end

-- Wires a ScrollBox's rows into the guts pass: `rows` = { scrollBox = <path>,
-- perRow = fn(rowFrame) }. Every ApplyGuts pass runs `perRow` over whatever
-- rows are currently acquired (`scrollBox:ForEachFrame`, feature-detected --
-- ElvUI-verified, not in the client's own API dump since it's a Lua mixin
-- method, not a native widget method) AND, once per scrollBox, hooksecurefunc's
-- its `Update` method to re-run the same sweep whenever Blizzard repaints the
-- rows (a new dialog page). If the scrollBox itself hasn't resolved yet (the
-- owning panel isn't fully built at apply time), retries from `parent`'s own
-- OnShow instead of giving up, guarded via `parent.fsGutsRowsRetry`, a table
-- keyed by `rows.scrollBox` (the path string) rather than a single flag on
-- `parent` -- more than one `rows` entry can share the same `parent` (e.g.
-- AuctionHouse.lua's three item-list ScrollBoxes, none of which has its own
-- top-level global), and a single shared flag would let only the FIRST
-- unresolved entry ever re-arm its retry, silently starving the rest.
-- Resolved `silent` (the not-yet-built case is expected and self-healing, not
-- a real miss worth a degrade-log).
local function ApplyGutsRows(parent, rows)
    local scrollBox = ResolveGutsPath(rows.scrollBox, true)
    if not scrollBox then
        if parent.HookScript then
            parent.fsGutsRowsRetry = parent.fsGutsRowsRetry or {}
            if not parent.fsGutsRowsRetry[rows.scrollBox] then
                parent.fsGutsRowsRetry[rows.scrollBox] = true
                parent:HookScript("OnShow", function() ApplyGutsRows(parent, rows) end)
            end
        end
        return
    end

    local function SweepRows()
        if type(scrollBox.ForEachFrame) == "function"
            and type(scrollBox.GetView) == "function" and scrollBox:GetView() then
            scrollBox:ForEachFrame(rows.perRow)
        end
    end

    SweepRows()

    if not scrollBox.fsGutsRowsHooked and type(scrollBox.Update) == "function" then
        scrollBox.fsGutsRowsHooked = true
        hooksecurefunc(scrollBox, "Update", SweepRows)
    end
end

-- Applies strip/hide/retint/rows to a list of panel-guts specs; each entry:
--   parent = "<global frame name>"  -- entry skipped whole if not yet resolved
--   strip  = { <name>, ... }                            -> StripNamed
--   hide   = { { name = <name>, alpha0 = bool }, ... }   -> HideNamed
--   retint = { { name = <_G name or "Frame.field" path>, opts = {...} } |
--              { region = <resolved region>, opts = {...} }, ... } -> RetintDarkText
--   rows   = { scrollBox = <path>, perRow = fn }         -> ApplyGutsRows
-- Guarded by `parent.fsGutsApplied` so /fsrecon skins can read this back like
-- every other panel marker; the strip/hide/retint/rows helpers are each
-- independently idempotent, so re-running them on an already-applied parent
-- (e.g. Panels.lua's MAIL_INBOX_UPDATE re-scan) stays cheap and safe.
-- FS.LogDegradeOnce does NOT dedupe by key itself (see ErrorLog.lua and the
-- loggedGutsPaths guard above). loggedGutsEntryErrors is ApplyGuts' own
-- once-per-session guard so one failing entry logs once, not once per rescan.
-- Keyed by the `entry` table itself, NOT `entry.parent`: multiple spec entries
-- can share one parent global (AuctionHouse.lua's three ScrollBoxes all
-- resolve to AuctionHouseFrame), so keying by parent would let the first
-- entry's failure silently suppress a sibling entry's own independent
-- failure -- the same trap ApplyGutsRows' own `fsGutsRowsRetry` guard above
-- was keyed by scrollBox, not a single flag on parent, to avoid.
local loggedGutsEntryErrors = {}

function PanelSkins.ApplyGuts(spec)
    for _, entry in ipairs(spec) do
        local parent = _G[entry.parent]
        if parent then
            local ok, err = pcall(function()
                if entry.strip then PanelSkins.StripNamed(entry.strip) end
                if entry.hide then PanelSkins.HideNamed(entry.hide) end
                if entry.retint then
                    for _, r in ipairs(entry.retint) do
                        local region = ResolveGutsRegion(r)
                        if region then
                            PanelSkins.RetintDarkText(region, Theme.COLOR_TEXT_PARCHMENT, r.opts)
                        end
                    end
                end
                if entry.rows then ApplyGutsRows(parent, entry.rows) end
            end)
            if not ok and not loggedGutsEntryErrors[entry] then
                loggedGutsEntryErrors[entry] = true
                -- "guts-entry:" .. entry.parent is just a human-readable label for
                -- FS.LogDegradeOnce's own key string; the dedup above is the
                -- loggedGutsEntryErrors[entry] table-identity lookup, not this string.
                FS.LogDegradeOnce("guts-entry:" .. entry.parent,
                    ("|cffff4488Forever STUwave|r: panel-guts entry '%s' failed: %s"):format(entry.parent, tostring(err)))
            end
            parent.fsGutsApplied = true
        end
    end
end

-------------------------------------------------------------------------------
-- /fsrecon skins | pos <frame> readback commands
-------------------------------------------------------------------------------

-- Read-only recon registry: each reskin file registers the surfaces it owns
-- so /fsrecon skins can report which ones resolved (frame exists, idempotency
-- marker set) vs skipped (frame absent -- not yet loaded, load-on-demand) at
-- call time, without this file needing to know each consumer's frame list.
local reconGroups = {}

-- `entries` is a list of { name = <_G frame name>, guard = <marker field> }.
function PanelSkins.RegisterRecon(label, entries)
    reconGroups[#reconGroups + 1] = { label = label, entries = entries }
end

-- Convenience wrapper for the RegisterRecon(label, entries) call every
-- consumer used to build by hand: builds the { name, guard } entries list
-- from `list` (each element either a bare string, or a table whose
-- `nameField` key holds the frame name) and registers it under `label`.
function PanelSkins.RegisterReconFromList(label, list, guard, nameField)
    local entries = {}
    for _, x in ipairs(list) do
        entries[#entries+1] = { name = nameField and x[nameField] or x, guard = guard }
    end
    PanelSkins.RegisterRecon(label, entries)
end

-- A couple of obvious shorthands for /fsrecon pos; the identifier is always
-- tried verbatim against _G first (below), so any real global frame name
-- works untouched without needing an entry here.
local reconFrameAliases = {
    issuereporter = "PTR_IssueReporter",
    minimap = "Minimap",
}

-- Usage line shared by the plain "/fsrecon" call and any unrecognised
-- subcommand, so there is exactly one place naming all three.
local function PrintReconUsage()
    print("|cff22e0ffForever STUwave|r: /fsrecon skins | pos <frame> | threat [auto [N]|clear] | " ..
        "pet [auto [N]|clear] | probe [stop] | surname | minimap [paint|spill|clear] | microbags | plateauras [arm|off] | class | all -- panel-skin idempotency readback | " ..
        "frame position report | threat/role/reaction secret-value probe | pet Phase-0 probe | " ..
        "name-API surname probe | Minimap/MinimapCluster geometry probe | " ..
        "hidden native nameplate aura frame probe (not part of all; arm waits for combat, off disarms) | " ..
        "class spell, form and aura recon (out of combat; not part of all; /fsbug includes it) | all -- run every probe")
end

SLASH_FSRECON1 = "/fsrecon"
SlashCmdList["FSRECON"] = function(msg)
    if msg == "probe" then
        FS.Diagnostics.ArmAuraProbe()
        return
    end
    if msg == "probe stop" then
        FS.Diagnostics.StopAuraProbe()
        return
    end
    if msg == "threat" or msg:match("^threat%s") then
        -- The probe logic lives in Diagnostics.lua (FS.Diagnostics), not here:
        -- reached through the table at call time since that file loads AFTER
        -- this one, so a captured local would still be nil when this closure
        -- was built.
        local rest = msg:match("^threat%s*(.-)%s*$") or ""

        if rest == "" then
            FS.Diagnostics.RunThreatProbe()
            return
        end

        if rest == "clear" then
            FS.Diagnostics.ClearThreatRuns()
            return
        end

        -- Require a word boundary after "auto" so "threat automatic" (or any
        -- other word merely starting with it) falls through to the usage
        -- print instead of silently arming with the default N.
        if rest == "auto" or rest:match("^auto%s") then
            local autoArg = rest:match("^auto%s*(.-)%s*$")
            FS.Diagnostics.ArmThreatAuto(tonumber(autoArg))
            return
        end

        PrintReconUsage()
        return
    end

    if msg == "pet" or msg:match("^pet%s") then
        -- Same dispatch shape as the threat probe above: routed through
        -- FS.Diagnostics at call time since Diagnostics.lua loads after this
        -- file. See Diagnostics.lua's /fsrecon pet section for the probe
        -- logic itself.
        local rest = msg:match("^pet%s*(.-)%s*$") or ""

        if rest == "" then
            FS.Diagnostics.RunPetProbe()
            return
        end

        if rest == "clear" then
            FS.Diagnostics.ClearPetRuns()
            return
        end

        if rest == "auto" or rest:match("^auto%s") then
            local autoArg = rest:match("^auto%s*(.-)%s*$")
            FS.Diagnostics.ArmPetAuto(tonumber(autoArg))
            return
        end

        PrintReconUsage()
        return
    end

    if msg == "surname" or msg:match("^surname%s") then
        -- Routed through FS.Diagnostics at call time like threat/pet above,
        -- since Diagnostics.lua loads after this file. One-shot lookup, no
        -- auto/clear -- see Diagnostics.lua's /fsrecon surname section.
        FS.Diagnostics.RunSurnameProbe()
        return
    end

    if msg == "minimap" or msg:match("^minimap%s") then
        local rest = msg:match("^minimap%s*(.-)%s*$") or ""
        if rest == "" then
            FS.Diagnostics.RunMinimapProbe()
        elseif rest == "paint" or rest == "spill" or rest == "clear" or rest == "paintoff" then
            FS.Diagnostics.RunMinimapBounds(rest)
        else
            PrintReconUsage()
        end
        return
    end

    if msg == "microbags" then
        FS.Diagnostics.RunMicroBagsProbe()
        return
    end

    if msg == "plateauras" or msg == "plateauras arm" or msg == "plateauras off" then
        -- Read-only probe of Blizzard's own (hidden) nameplate aura frames;
        -- see Diagnostics.lua's /fsrecon plateauras section. `arm` waits for
        -- the first in-combat target UNIT_AURA so nothing is typed mid-fight;
        -- `off` disarms it. Not part of `all`.
        if msg == "plateauras" then
            FS.Diagnostics.RunPlateAurasProbe()
        elseif msg == "plateauras arm" then
            FS.Diagnostics.ArmPlateAuras()
        else
            FS.Diagnostics.DisarmPlateAuras()
        end
        return
    end

    if msg == "class" or msg:match("^class%s") then
        -- Class spell/form/aura recon for building class features; see Diagnostics.lua's
        -- /fsrecon class section. Not part of `all`: it reads auras, so it wants a quiet moment.
        FS.Diagnostics.RunClassRecon()
        return
    end

    if msg == "all" or msg:match("^all%s") then
        -- Runs every one-shot recon probe in one command and prints one
        -- combined confirmation line -- see Diagnostics.lua's /fsrecon all
        -- section.
        FS.Diagnostics.RunAllRecon()
        return
    end

    if msg == "pos" or msg:match("^pos%s") then
        -- Everything after "pos", trimmed -- the lazy capture plus the
        -- trailing %s*$ anchor eats leading/trailing whitespace in one match.
        local id = msg:match("^pos%s*(.-)%s*$") or ""
        if id == "" then
            print("|cff22e0ffForever STUwave|r: /fsrecon pos <FrameName> -- reports a frame's position")
            return
        end

        -- Verbatim global first (any real frame name works untouched), then
        -- the small alias table keyed by lowercase.
        local frame = _G[id] or _G[reconFrameAliases[id:lower()]]
        if type(frame) ~= "table" or type(frame.GetRect) ~= "function" then
            print(("|cffff4488Forever STUwave|r: /fsrecon pos -- frame '%s' not found or has no GetRect"):format(id))
            return
        end

        -- GetRect returns nil for all four if the frame has no resolved
        -- anchor point yet (e.g. created but never SetPoint'd/shown) --
        -- guard before any arithmetic/formatting touches l/b/w/h.
        local l, b, w, h = frame:GetRect()
        if not l then
            print(("|cffff4488Forever STUwave|r: /fsrecon pos -- frame '%s' has no resolved position " ..
                "(GetRect returned nil)"):format(id))
            return
        end

        local uw, uh, s = 0, 0, 0
        local xf, yf = 0, 0
        if UIParent then
            uw, uh = UIParent:GetWidth() or 0, UIParent:GetHeight() or 0
            s = UIParent:GetEffectiveScale() or 0
            if uw > 0 and uh > 0 then
                xf, yf = l / uw, b / uh
            end
        end

        -- A chat print scrolls away and never reaches a headless driver, so
        -- this also writes into ForeverSTUwaveDB -- same idiom as the
        -- skins readback below -- for fsdev.py to read after /fsreload.
        local line = ("|cff22e0ffstuwave://pos|r %s  BOTTOMLEFT x=%.1f y=%.1f  (size %.0fx%.0f)  " ..
            "frac x=%.4f y=%.4f  UIParent %.0fx%.0f @ %.3f"):format(
            id, l, b, w, h, xf, yf, uw, uh, s)
        print(line)

        ForeverSTUwaveDB = ForeverSTUwaveDB or {}
        ForeverSTUwaveDB.reconPos = line
        print("|cff22e0ffstuwave://recon|r  written to ForeverSTUwaveDB; /fsreload to flush it")
        return
    end

    if msg ~= "skins" then
        PrintReconUsage()
        return
    end

    ForeverSTUwaveDB = ForeverSTUwaveDB or {}

    -- A chat print scrolls away and never reaches a headless driver, so this
    -- also writes a compact readback into ForeverSTUwaveDB -- same idiom as
    -- Diagnostics.lua's /fsfont -> fontProbe -- for fsdev.py to read after
    -- /fsreload.
    local groupSummaries = {}
    local presentUnskinned = {}
    local skippedCount = 0

    print("|cff22e0ffForever STUwave|r: /fsrecon skins")
    for _, group in ipairs(reconGroups) do
        local resolved = 0
        for _, entry in ipairs(group.entries) do
            local frame = _G[entry.name]
            if frame and frame[entry.guard] then resolved = resolved + 1 end
        end
        print(("  %s: %d/%d resolved"):format(group.label, resolved, #group.entries))
        groupSummaries[#groupSummaries + 1] = ("%s %d/%d"):format(group.label, resolved, #group.entries)
        for _, entry in ipairs(group.entries) do
            local frame = _G[entry.name]
            local status
            if frame and frame[entry.guard] then
                status = "resolved"
            elseif frame then
                status = "present, unskinned"
                presentUnskinned[#presentUnskinned + 1] = ("%s/%s"):format(group.label, entry.name)
            else
                status = "skipped (not loaded)"
                skippedCount = skippedCount + 1
            end
            print(("    %-28s %s"):format(entry.name, status))
        end
    end

    local unskinnedText = "none present-unskinned"
    if #presentUnskinned > 0 then
        unskinnedText = "PRESENT-UNSKINNED: " .. table.concat(presentUnskinned, ", ")
    end
    ForeverSTUwaveDB.reconSkins = ("%s | %s | %d skipped (not loaded)"):format(
        table.concat(groupSummaries, " | "), unskinnedText, skippedCount)
    print("|cff22e0ffstuwave://recon|r  written to ForeverSTUwaveDB; /fsreload to flush it")
end
