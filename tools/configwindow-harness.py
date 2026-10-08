#!/usr/bin/env python3
"""Runs the real ConfigWindow.lua, Config.lua and Gunsight.lua headless to pin the /fsconfig window.

The window is a plain themed frame with a category nav and a content well. These checks pin:

  * categories register, sort by order and may register after the window is built; a page builds
    once, lazily, the first time it is shown; the window keeps one fixed size on every page;
  * the window is non-secure, opens in combat, closes on Escape and /fsconfig toggles it;
  * the Unit Frames toggles write FS.Config and follow external changes and profile switches;
  * the Gunsight HUD page lists the author's piece labels, writes gunsight.* settings, and /fsgun
    shows the same state; the legacy ForeverSTUwaveDB.gunsight values migrate once into the
    active profile and a profile switch moves the live pieces;
  * the Profiles page calls the Config API (switch, new, copy, rename, delete, reset), asks before
    anything destructive, and keeps Delete off for Default and the active profile;
  * read-only Config disables every control; no player-facing string says "tape"; explanations
    live in ? tooltips, never inline; no Blizzard Settings panel or StaticPopup is used.

Theme is a recording stub and the frames are a mock. This is NOT the real client.

    python3 tools/configwindow-harness.py

Exit 0 = every check passed.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
# CONFIGWINDOW_LUA points the harness at a mutant copy (a check must fail on a broken one).
WINDOW_FILE = Path(os.environ.get("CONFIGWINDOW_LUA", ADDON / "Modules/Config/ConfigWindow.lua"))
CONFIG_FILE = ADDON / "Core/Config.lua"
GUNSIGHT_FILE = ADDON / "Modules/CombatHud/Gunsight.lua"
TOC_FILE = ADDON / "forever-stuwave.toc"

MOCK = r"""
ALL = {}            -- every frame and region, in creation order
__printed = {}
__errors = {}
__combat = false
UISpecialFrames = {}
SlashCmdList = {}
TOOLTIP = { text = nil, owner = nil, shown = false, history = {} }

local noop = function() end
local Obj = {}
Obj.__index = function(self, k)
    local m = Obj[k]
    if m ~= nil then return m end
    -- Unknown widget METHODS (capitalised) do nothing; unknown fields stay nil.
    if type(k) == "string" and k:match("^%u") then return noop end
end

local function new(kind, name, parent)
    local o = setmetatable({
        kind = kind, name = name, parent = parent, points = {}, w = 0, h = 0, shown = true, alpha = 1,
        scripts = {}, events = {}, enabled = true, mouse = false, level = 1, strata = "MEDIUM",
    }, Obj)
    if parent and parent.level then o.level = parent.level + 1 end
    ALL[#ALL + 1] = o
    if name then _G[name] = o end
    return o
end

function CreateFrame(kind, name, parent)
    local f = new(kind, name, parent or UIParent)
    f.isFrame = true
    f.protected = false
    return f
end
function Obj:CreateTexture(name, layer, template, sub)
    local t = new("Texture", name, self); t.layer, t.sub = layer, sub; return t
end
function Obj:CreateFontString(name, layer, template)
    local s = new("FontString", name, self)
    s.hasFont = type(template) == "string"
    return s
end
function Obj:SetFont(path, size, flags) self.hasFont = true; self.fontPath = path; self.fontSize = size; return true end
function Obj:GetFont() return self.fontPath, self.fontSize end
function Obj:SetFontObject() self.hasFont = true end
function Obj:SetText(t)
    if (self.kind == "FontString") and not self.hasFont then error("Font not set", 2) end
    self.text = t == nil and "" or tostring(t)
end
function Obj:GetText() return self.text or "" end
function Obj:SetFormattedText(fmt, ...) self:SetText(string.format(fmt, ...)) end
function Obj:GetStringWidth() return #(self.text or "") * 6 end
function Obj:SetTextColor(r, g, b, a) self.textColor = { r, g, b, a } end
function Obj:SetVertexColor(r, g, b, a) self.color = { r, g, b, a } end
function Obj:SetColorTexture(r, g, b, a) self.color = { r, g, b, a } end
BLOCKED = {}   -- protected-frame actions attempted in combat
local function blockedAction(self, what)
    if self.protected == true and __combat then
        BLOCKED[#BLOCKED + 1] = what
        error("ADDON_ACTION_BLOCKED " .. what, 3)
    end
end
function Obj:Show() blockedAction(self, "Show"); self.shown = true; if self.scripts.OnShow then self.scripts.OnShow(self) end end
function Obj:Hide()
    blockedAction(self, "Hide")
    local was = self.shown
    self.shown = false
    if was and self.scripts.OnHide then self.scripts.OnHide(self) end
end
function Obj:SetShown(v) if v then self:Show() else self:Hide() end end
function Obj:IsShown() return self.shown end
function Obj:IsVisible()
    local o = self
    while o do
        if not o.shown then return false end
        o = o.parent
    end
    return true
end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:SetWidth(w) self.w = w end
function Obj:SetHeight(h) self.h = h end
function Obj:GetWidth() return self.w end
function Obj:GetHeight() return self.h end
function Obj:SetPoint(point, rel, relPoint, x, y)
    if type(rel) == "number" then x, y, rel, relPoint = rel, relPoint, nil, nil end
    self.points[#self.points + 1] = { point = point, rel = rel or self.parent, relPoint = relPoint or point, x = x or 0, y = y or 0 }
end
function Obj:ClearAllPoints() self.points = {} end
function Obj:SetAllPoints(rel) self.points = { { point = "ALL", rel = rel or self.parent, x = 0, y = 0 } } end
function Obj:GetParent() return self.parent end
function Obj:SetAlpha(a) self.alpha = a end
function Obj:GetAlpha() return self.alpha end
function Obj:SetScript(k, fn) self.scripts[k] = fn end
function Obj:GetScript(k) return self.scripts[k] end
function Obj:HookScript(k, fn)
    local old = self.scripts[k]
    self.scripts[k] = old and function(...) old(...); fn(...) end or fn
end
function Obj:RegisterEvent(e) self.events[e] = true end
function Obj:UnregisterEvent(e) self.events[e] = nil end
function Obj:EnableMouse(v) blockedAction(self, "EnableMouse"); self.mouse = v and true or false end
function Obj:EnableKeyboard(v) self.keyboard = v and true or false end
function Obj:SetPropagateKeyboardInput(v) self.propagate = v end
function Obj:Enable() self.enabled = true end
function Obj:Disable() self.enabled = false end
function Obj:IsEnabled() return self.enabled end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:GetFrameLevel() return self.level end
function Obj:SetFrameStrata(s) self.strata = s end
function Obj:GetFrameStrata() return self.strata end
function Obj:IsProtected() return self.protected == true end
local function ghost()
    return setmetatable({}, { __index = function() return function() return ghost() end end })
end
function Obj:CreateAnimationGroup() return ghost() end
function Obj:SetFocus() self.focused = true end
function Obj:ClearFocus() self.focused = false end
function Obj:HasFocus() return self.focused == true end

UIParent = new("Frame", "UIParent", nil)
UIParent.isFrame = true
UIParent.w, UIParent.h = 2560, 1440

GameTooltip = new("Frame", "GameTooltip", UIParent)
GameTooltip.isFrame = true
function GameTooltip:SetOwner(owner) TOOLTIP.owner = owner; TOOLTIP.text = nil end
function GameTooltip:GetOwner() return TOOLTIP.owner end
function GameTooltip:SetText(text) TOOLTIP.text = text; TOOLTIP.history[#TOOLTIP.history + 1] = text end
function GameTooltip:AddLine(text) TOOLTIP.history[#TOOLTIP.history + 1] = text end
function GameTooltip:Show() TOOLTIP.shown = true end
function GameTooltip:Hide() TOOLTIP.shown = false; TOOLTIP.text = nil end

function InCombatLockdown() return __combat end
function print(...) local t = {}; for i = 1, select("#", ...) do t[#t + 1] = tostring((select(i, ...))) end; __printed[#__printed + 1] = table.concat(t, " ") end
function geterrorhandler() return function(err) __errors[#__errors + 1] = tostring(err) end end
__guid = "Player-1-AAAA"
function UnitGUID() return __guid end
function UnitName() return "Bob" end
function GetRealmName() return "Realm" end
function GetAddOnMetadata(addon, field) if field == "Version" then return "0.1.0-alpha.1" end end

function Fire(event, ...)
    local list = {}
    for _, f in ipairs(ALL) do
        if f.events[event] and f.scripts.OnEvent then list[#list + 1] = f end
    end
    for _, f in ipairs(list) do f.scripts.OnEvent(f, event, ...) end
end
"""

SESSION = r"""
function(configSrc, gunsightSrc, windowSrc, opts)
    opts = opts or {}
    ALL, __printed, __errors, __combat, BLOCKED = {}, {}, {}, false, {}
    ALL[1], ALL[2] = UIParent, GameTooltip
    UIParent.shown = true
    UISpecialFrames = {}
    TOOLTIP.text, TOOLTIP.owner, TOOLTIP.shown, TOOLTIP.history = nil, nil, false, {}
    for k in pairs(SlashCmdList) do SlashCmdList[k] = nil end
    ForeverSTUwaveDB = opts.db
    FS = {}
    FS.LogDegradeOnce = function() end
    FS.Layout = {
        OnRescale = function() end, Scale = function() return 1 end, UseStore = function() end,
        ReseatAll = function() end,
        ForwardError = function(err) __errors[#__errors + 1] = tostring(err) end,
    }
    local line = { 0.227, 0.129, 0.408, 1 }
    local Theme = {
        COLOR_BG = { 0.102, 0.063, 0.145, 0.8 }, COLOR_BORDER = { 0.659, 0.333, 0.969, 1 },
        COLOR_BAR_TRACK = { 0.039, 0.016, 0.086, 1 }, COLOR_BAR_BORDER = line,
        COLOR_HEALTH = { 1, 0.18, 0.592, 1 }, COLOR_POWER = { 0.133, 0.878, 1, 1 },
        COLOR_MUTED = { 0.616, 0.577, 0.769, 1 }, COLOR_CARET_HEALTH = { 0.224, 1, 0.078, 1 },
        FONT_MONO = "mono.ttf", FONT_ORBITRON = "display.ttf", FILL_CORNER_TEXTURE = "fill_corner.tga",
        PANEL_HEADER_H = 18, SKINNED = {},
    }
    function Theme.ApplyMono(fs, size, color) fs:SetFont("mono.ttf", size, ""); fs.themeColor = color end
    function Theme.ApplyFontGeneric(fs, path, size, color) fs:SetFont(path, size, ""); fs.themeColor = color end
    function Theme.SkinPanel(frame, o) Theme.SKINNED[frame] = o or {}; return {} end
    function Theme.SkinButton(button, o)
        local glow = button:CreateTexture(nil, "OVERLAY")
        local ring = button:CreateTexture(nil, "OVERLAY")
        local c = o and o.borderColor
        if c then ring:SetVertexColor(c[1], c[2], c[3], 1); glow:SetVertexColor(c[1], c[2], c[3], o.glowAlpha or 0.35) end
        button.fsSkin = { glow = glow, border = { ring = ring }, opts = o }
        return button.fsSkin
    end
    function Theme.AddCutSliceFill(panel, color, radius)
        local t = panel:CreateTexture(nil, "BACKGROUND")
        t:SetVertexColor(color[1], color[2], color[3], color[4] or 1)
        t.cut = radius
        return t
    end
    FS.Theme = Theme
    if opts.noConfig ~= true then
        assert(load(configSrc, "@Config.lua"))("forever-stuwave", FS)
    end
    if opts.noGunsight ~= true then
        assert(load(gunsightSrc, "@Gunsight.lua"))("forever-stuwave", FS)
    end
    if opts.preWindow then opts.preWindow() end
    assert(load(windowSrc, "@ConfigWindow.lua"))("forever-stuwave", FS)
    if opts.beforeLogin then opts.beforeLogin() end
    if opts.noLogin ~= true then
        Fire("ADDON_LOADED", "forever-stuwave")
        Fire("PLAYER_LOGIN")
    end
end
"""

CHECKS = r"""
local T = {}
local function eq(a, b, msg)
    if a ~= b then error((msg or "mismatch") .. ": got " .. tostring(a) .. ", want " .. tostring(b), 2) end
end
local function yes(v, msg) if not v then error(msg or "expected true", 2) end end
local function no(v, msg) if v then error(msg or "expected false", 2) end end

local function boot(opts)
    __session(__configSrc, __gunsightSrc, __windowSrc, opts)
    return FS.ConfigWindow
end

-- Visible FontStrings under a root (the whole addon world when no root is given).
local function under(root, o)
    while o do
        if o == root then return true end
        o = o.parent
    end
    return false
end
local function texts(root)
    local list = {}
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and (root == nil or under(root, o)) then
            list[#list + 1] = o:GetText()
        end
    end
    return list
end
local function findText(text, root, plain)
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and (root == nil or under(root, o)) then
            local t = o:GetText()
            if t == text or (plain and t:find(text, 1, true)) then return o end
        end
    end
end
local function owner(fs, field)
    local o = fs.parent
    while o do
        if (field == nil and o.scripts.OnClick) or (field and o[field]) then return o end
        o = o.parent
    end
end
local function click(text, root)
    local fs = findText(text, root)
    if not fs then error("no visible text '" .. text .. "'", 2) end
    local b = owner(fs)
    if not b then error("no clickable owner for '" .. text .. "'", 2) end
    if not b.enabled then return false end
    b.scripts.OnClick(b, "LeftButton")
    return true
end
local function row(label)
    for _, o in ipairs(ALL) do
        if o.kind == "FontString" and o:IsVisible() and o:GetText() == label then
            local r = owner(o, "control")
            if r then return r end
        end
    end
end
-- Presses the toggle (or button) of a labelled row, the way a click would; false when it is disabled.
local function press(label)
    local b = row(label).control
    if not b.enabled then return false end
    b.scripts.OnClick(b, "LeftButton")
    return true
end
local function win() return _G.ForeverSTUwaveConfig end
local function dialog() return assert(_G.ForeverSTUwaveConfigDialog, "the dialog was never built") end
local function menu() return assert(_G.ForeverSTUwaveConfigMenu, "the menu was never built") end
local function editBox()
    for _, o in ipairs(ALL) do if o.kind == "EditBox" and o:IsVisible() then return o end end
end
local function hasText(root, needle)
    for _, t in ipairs(texts(root)) do if t:find(needle, 1, true) then return true end end
    return false
end
local function count(t) local n = 0; for _ in pairs(t) do n = n + 1 end; return n end
local function keys(list) local out = {}; for _, c in ipairs(list) do out[#out + 1] = c.key end; return table.concat(out, ",") end
local function reload(opts)       -- a relog over the same saved variable
    opts = opts or {}
    opts.db = ForeverSTUwaveDB
    return boot(opts)
end

-------------------------------------------------------------------------------
-- Categories
-------------------------------------------------------------------------------

function T.categories_register_sorted_by_order()
    local W = boot()
    eq(keys(W.Categories()), "unitframes,gunsight,profiles")
    local c = W.Categories()
    eq(c[1].label, "Unit Frames"); eq(c[1].order, 1)
    eq(c[2].label, "Gunsight HUD"); eq(c[2].order, 2)
    eq(c[3].label, "Profiles"); eq(c[3].order, 9)
end

function T.register_before_the_window_is_built_sorts_in()
    local W = boot()
    yes(W.RegisterCategory({ key = "layout", label = "Layout", order = 3, build = function() end }))
    eq(keys(W.Categories()), "unitframes,gunsight,layout,profiles")
    W.Open()
    local nav = {}
    for _, o in ipairs(ALL) do if o.fsCategory and o:IsVisible() then nav[#nav + 1] = o.fsCategory end end
    eq(table.concat(nav, ","), "unitframes,gunsight,layout,profiles", "nav entries in order")
end

function T.register_after_the_window_is_built_adds_a_nav_entry()
    local W = boot()
    W.Open()
    yes(win() ~= nil, "built")
    yes(W.RegisterCategory({ key = "layout", label = "Layout", order = 3, build = function() end }))
    local fs = findText("Layout", win())
    yes(fs, "nav entry for the late category")
    local button = owner(fs, "fsCategory")
    eq(button.fsCategory, "layout")
    eq(button.fsNumber:GetText(), "03")
    local p = findText("Profiles", win())
    eq(owner(p, "fsCategory").fsNumber:GetText(), "04", "Profiles renumbered after the late entry")
end

function T.a_page_builds_once_and_only_when_first_shown()
    local W = boot()
    local built = 0
    W.RegisterCategory({ key = "layout", label = "Layout", order = 3, build = function(content)
        built = built + 1
        yes(content and content.isFrame, "build gets a content frame")
    end })
    W.Open()
    eq(built, 0, "not built while another page is shown")
    W.Open("layout")
    eq(built, 1)
    W.Open("profiles")
    W.Open("layout")
    W.Close(); W.Open("layout")
    eq(built, 1, "built once")
end

function T.a_throwing_page_build_does_not_kill_the_window()
    local W = boot()
    W.RegisterCategory({ key = "bad", label = "Bad", order = 4, build = function() error("boom") end })
    W.Open("bad")
    yes(W.IsShown(), "window still open")
    yes(#__errors >= 1, "the error was forwarded")
    W.Open("gunsight")
    yes(row("Your cast bar"), "other pages still work")
end

function T.register_rejects_bad_specs_and_replaces_a_repeated_key()
    local W = boot()
    no(W.RegisterCategory(nil)); no(W.RegisterCategory({})); no(W.RegisterCategory({ key = "x" }))
    no(W.RegisterCategory({ key = "x", label = "X", build = "nope" }))
    eq(#W.Categories(), 3)
    W.RegisterCategory({ key = "layout", label = "Layout", order = 3, build = function() end })
    W.RegisterCategory({ key = "layout", label = "Layout 2", order = 3, build = function() end })
    eq(#W.Categories(), 4, "a repeated key replaces")
    eq(W.Categories()[3].label, "Layout 2")
end

function T.equal_orders_sort_by_key()
    local W = boot()
    W.RegisterCategory({ key = "b", label = "B", order = 5, build = function() end })
    W.RegisterCategory({ key = "a", label = "A", order = 5, build = function() end })
    eq(keys(W.Categories()), "unitframes,gunsight,a,b,profiles")
end

-------------------------------------------------------------------------------
-- The window
-------------------------------------------------------------------------------

function T.open_close_toggle_and_escape()
    local W = boot()
    no(W.IsShown())
    W.Toggle(); yes(W.IsShown()); yes(win():IsShown())
    W.Toggle(); no(W.IsShown())
    W.Open(); yes(W.IsShown())
    W.Close(); no(W.IsShown())
    local found = false
    for _, n in ipairs(UISpecialFrames) do if n == "ForeverSTUwaveConfig" then found = true end end
    yes(found, "Escape closes it through UISpecialFrames")
    local count = 0
    W.Open(); W.Close(); W.Open()
    for _, n in ipairs(UISpecialFrames) do if n == "ForeverSTUwaveConfig" then count = count + 1 end end
    eq(count, 1, "registered once")
end

function T.the_window_is_a_plain_movable_non_secure_frame()
    local W = boot()
    W.Open()
    local f = win()
    eq(f.kind, "Frame"); eq(f.parent, UIParent); no(f:IsProtected())
    eq(f.strata, "DIALOG")
    yes(f.mouse, "mouse enabled so it can be dragged")
    yes(FS.Theme.SKINNED[f], "skinned with Theme.SkinPanel")
    eq(FS.Theme.SKINNED[f].title, "config")
    eq(FS.Theme.SKINNED[f].strip, false, "no Blizzard chrome to strip on our own frame")
end

function T.the_window_keeps_one_fixed_size_on_every_page()
    local W = boot()
    W.Open("unitframes")
    local w, h = win():GetWidth(), win():GetHeight()
    eq(w, 780); eq(h, 560)
    for _, key in ipairs({ "gunsight", "profiles", "unitframes" }) do
        W.Open(key)
        eq(win():GetWidth(), w, key .. " width"); eq(win():GetHeight(), h, key .. " height")
    end
end

local function protectedPiece()
    local frame = CreateFrame("Frame", nil, FS.Gunsight.root)
    frame.protected = true
    FS.Gunsight.RegisterPiece("party", { frame = frame })
    return frame
end

function T.the_window_opens_in_combat_and_a_toggle_only_fades_a_protected_piece()
    local W = boot()
    local frame = protectedPiece()
    __combat = true
    W.Open("gunsight")
    yes(W.IsShown())
    yes(press("Party frames"))
    eq(FS.Gunsight.IsPieceOn("party"), false)
    eq(frame:GetAlpha(), 0, "alpha only in combat")
    yes(frame:IsShown(), "no Hide on a protected frame in combat")
    eq(#BLOCKED, 0, "no blocked action was attempted")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED")
    no(frame:IsShown(), "the real hide waits for the end of combat")
end

function T.a_profile_switch_in_combat_defers_a_protected_piece()
    local W = boot()
    local frame = protectedPiece()
    FS.Config.NewProfile("Raid")
    FS.Config.SetActiveProfile("Raid")
    FS.Config.Set("gunsight.pieces.party", false)
    FS.Config.SetActiveProfile("Default")
    W.Open("gunsight")
    yes(frame:IsShown())
    __combat = true
    yes(FS.Config.SetActiveProfile("Raid"))
    eq(FS.Gunsight.IsPieceOn("party"), false)
    eq(frame:GetAlpha(), 0, "alpha only in combat")
    yes(frame:IsShown(), "still shown until combat ends")
    eq(#BLOCKED, 0)
    no(row("Party frames").control.fsChecked, "the toggle follows at once")
    __combat = false
    Fire("PLAYER_REGEN_ENABLED")
    no(frame:IsShown())
end

function T.slash_fsconfig_toggles_and_can_pick_a_page()
    local W = boot()
    eq(SLASH_FSCONFIG1, "/fsconfig")
    yes(type(SlashCmdList.FSCONFIG) == "function")
    SlashCmdList.FSCONFIG("")
    yes(W.IsShown())
    SlashCmdList.FSCONFIG("")
    no(W.IsShown())
    SlashCmdList.FSCONFIG("profiles")
    yes(W.IsShown())
    yes(findText("Profile in use", win()), "opened on the Profiles page")
    SlashCmdList.FSCONFIG("gunsight hud")
    yes(findText("Your cast bar", win()), "label match, spaces allowed")
end

function T.chrome_title_subtitle_footer_and_close()
    local W = boot()
    W.Open()
    local f = win()
    yes(findText("FOREVER |cffff2e97STU|rWAVE", f), "title with STU in pink")
    yes(hasText(f, "0.1.0-alpha.1"), "version from the toc")
    yes(hasText(f, "/fsconfig"), "slash in the subtitle and footer")
    yes(findText("Changes apply instantly", f))
    yes(findText("open with", f))
    yes(findText("// settings", f))
    local x = findText("X", f)
    yes(x, "close X")
    click("X", f)
    no(W.IsShown(), "the X closes the window")
end

function T.the_nav_numbers_follow_order_and_selection_follows_open()
    local W = boot()
    W.Open("gunsight")
    local nav = owner(findText("Gunsight HUD", win()), "fsCategory")
    eq(nav.fsNumber:GetText(), "02")
    yes(nav.fsSelected, "selected entry flagged")
    no(owner(findText("Unit Frames", win()), "fsCategory").fsSelected == true)
    yes(hasText(win(), "GUNSIGHT HUD"), "category label top right")
    click("Profiles", win())
    yes(findText("Profile in use", win()), "clicking a nav entry opens it")
    yes(hasText(win(), "PROFILES"))
end

function T.the_first_open_shows_the_lowest_order_page_and_a_reopen_keeps_the_last_one()
    local W = boot()
    W.Open()
    yes(findText("Hide player frame", win()), "first page is Unit Frames")
    W.Open("gunsight")
    W.Close()
    W.Open()
    yes(row("Your cast bar"), "a plain reopen returns to the page that was showing")
    no(findText("Hide player frame", win()), "the Unit Frames page is hidden")
end

-------------------------------------------------------------------------------
-- Unit Frames
-------------------------------------------------------------------------------

local function unitFramesDefaults()
    FS.Config.RegisterDefault("unitFrames.hidePlayer", false)
    FS.Config.RegisterDefault("unitFrames.hideTarget", false)
end

function T.unit_frames_toggles_write_config_and_follow_changes()
    local W = boot({ preWindow = unitFramesDefaults })
    W.Open("unitframes")
    local r = row("Hide player frame")
    no(r.control.fsChecked)
    press("Hide player frame")
    eq(FS.Config.Get("unitFrames.hidePlayer"), true)
    yes(r.control.fsChecked)
    eq(FS.Config.Get("unitFrames.hideTarget"), false, "the other key is untouched")
    FS.Config.Set("unitFrames.hidePlayer", false)
    no(r.control.fsChecked, "an external change shows")
    press("Hide target frame")
    eq(FS.Config.Get("unitFrames.hideTarget"), true)
end

function T.the_toggle_states_show_on_and_off()
    local W = boot({ preWindow = unitFramesDefaults })
    W.Open("unitframes")
    eq(#texts(row("Hide player frame")), 2, "label and state, nothing else on a row")
    local r = row("Hide player frame")
    yes(findText("OFF", r))
    FS.Config.Set("unitFrames.hidePlayer", true)
    yes(findText("ON", r))
end

function T.no_page_has_inline_help_text()
    local W = boot({ preWindow = unitFramesDefaults })
    for _, key in ipairs({ "unitframes", "gunsight", "profiles" }) do
        W.Open(key)
        local page
        for _, o in ipairs(ALL) do
            if o.kind == "Frame" and o:IsVisible() and o.points[1] and o.points[1].point == "ALL" and o.parent and o.parent.parent and o.parent.parent.parent == win() then page = o end
        end
        yes(page, key .. ": the page frame was found")
        local seen = 0
        for _, t in ipairs(texts(page)) do
            seen = seen + 1
            yes(#t <= 40, key .. ": inline text too long: " .. t)
            yes(not t:find("[^.]%.$"), key .. ": a sentence is inline: " .. t)
        end
        yes(seen >= 3, key .. ": page texts were collected")
    end
    W.Open("unitframes")
    yes(hasText(win(), "PLAYER AND TARGET"))
end

function T.the_unit_frames_header_explains_itself_in_a_tooltip()
    local W = boot({ preWindow = unitFramesDefaults })
    W.Open("unitframes")
    local icon
    for _, o in ipairs(ALL) do if o.fsTip and o:IsVisible() then icon = o end end
    yes(icon, "a ? icon on the header")
    icon.scripts.OnEnter(icon)
    eq(TOOLTIP.text, "Hidden frames stay click-through and invisible.")
    eq(TOOLTIP.owner, icon)
    yes(TOOLTIP.shown)
    icon.scripts.OnLeave(icon)
    no(TOOLTIP.shown)
end

function T.a_profile_switch_updates_every_control()
    local W = boot({ preWindow = unitFramesDefaults })
    W.Open("unitframes")
    local r = row("Hide player frame")
    FS.Config.NewProfile("Raid")
    FS.Config.Set("unitFrames.hidePlayer", true)       -- on Default
    yes(r.control.fsChecked)
    yes(FS.Config.SetActiveProfile("Raid"))
    no(r.control.fsChecked, "Raid has the default")
    FS.Config.SetActiveProfile("Default")
    yes(r.control.fsChecked)
end

-------------------------------------------------------------------------------
-- Gunsight HUD
-------------------------------------------------------------------------------

local PIECE_LABELS = {
    you = "Your cast bar", tgt = "Target cast bar", next = "Next cast tile", dot = "DoT time axis",
    shard = "Soul shards", prc = "Proc posts", buff = "Buff reminders", party = "Party frames",
}

function T.every_gunsight_piece_has_a_label_and_a_row()
    local W = boot()
    W.Open("gunsight")
    eq(#FS.Gunsight.PIECES, 8)
    for _, key in ipairs(FS.Gunsight.PIECES) do
        yes(PIECE_LABELS[key], "no label for piece " .. key)
        yes(row(PIECE_LABELS[key]), "no row for " .. key)
    end
    yes(row("Gunsight HUD"), "master toggle")
    yes(hasText(win(), "PIECES"), "section header")
end

function T.gunsight_page_has_no_numbers_sliders_or_aura_rows()
    local W = boot()
    W.Open("gunsight")
    local page = row("Gunsight HUD").parent
    local seen = {}
    for _, t in ipairs(texts(page)) do seen[#seen + 1] = t end
    for _, t in ipairs(seen) do
        yes(not t:lower():find("height") and not t:lower():find("width") and not t:lower():find("aura"), "unbuilt setting shown: " .. t)
    end
end

function T.gunsight_toggles_write_config_and_drive_the_live_piece()
    local W = boot()
    W.Open("gunsight")
    local seen = {}
    FS.Gunsight.OnPieceChanged(function(key, on) seen[#seen + 1] = key .. "=" .. tostring(on) end)
    yes(FS.Gunsight.IsPieceOn("you"))
    press("Your cast bar")
    eq(FS.Config.Get("gunsight.pieces.you"), false)
    eq(FS.Gunsight.IsPieceOn("you"), false)
    eq(table.concat(seen, ","), "you=false")
    yes(not row("Your cast bar").control.fsChecked)
    press("Your cast bar")
    eq(FS.Config.Get("gunsight.pieces.you"), true)
    eq(FS.Gunsight.IsPieceOn("you"), true)
    yes(row("Your cast bar").control.fsChecked)
end

function T.the_master_toggle_writes_config_and_waits_for_a_reload()
    local W = boot()
    W.Open("gunsight")
    yes(row("Gunsight HUD").control.fsChecked)
    press("Gunsight HUD")
    eq(FS.Config.Get("gunsight.enabled"), false)
    eq(FS.Gunsight.IsEnabled(), true, "the HUD is built for this session, so the switch applies after /reload")
    local W2 = reload()
    eq(FS.Gunsight.IsEnabled(), false, "after the reload")
    W2.Open("gunsight")
    no(row("Gunsight HUD").control.fsChecked)
end

function T.the_master_toggle_explains_the_reload_in_a_tooltip()
    local W = boot()
    W.Open("gunsight")
    local r = row("Gunsight HUD")
    local icon
    for _, o in ipairs(ALL) do if o.fsTip and o.parent == r then icon = o end end
    yes(icon, "? icon on the master row")
    icon.scripts.OnEnter(icon)
    yes(TOOLTIP.text:find("/reload", 1, true), "tooltip names the reload")
end

function T.a_profile_switch_moves_the_live_pieces_and_the_toggles()
    local W = boot()
    W.Open("gunsight")
    FS.Config.NewProfile("Raid")
    FS.Config.SetActiveProfile("Raid")
    FS.Config.Set("gunsight.pieces.buff", false)
    eq(FS.Gunsight.IsPieceOn("buff"), false)
    FS.Config.SetActiveProfile("Default")
    eq(FS.Gunsight.IsPieceOn("buff"), true, "Default still has it on")
    yes(row("Buff reminders").control.fsChecked)
    FS.Config.SetActiveProfile("Raid")
    eq(FS.Gunsight.IsPieceOn("buff"), false)
    no(row("Buff reminders").control.fsChecked)
end

function T.a_registered_piece_follows_a_profile_switch()
    local W = boot()
    local frame = CreateFrame("Frame", nil, FS.Gunsight.root)
    FS.Gunsight.RegisterPiece("dot", { frame = frame })
    yes(frame:IsShown())
    FS.Config.NewProfile("Raid")
    FS.Config.SetActiveProfile("Raid")
    FS.Config.Set("gunsight.pieces.dot", false)
    FS.Config.SetActiveProfile("Default")
    FS.Config.SetActiveProfile("Raid")
    eq(FS.Gunsight.IsPieceOn("dot"), false)
end

local function legacyDb(extra)
    local db = { gunsight = { enabled = false, pieces = { buff = false, you = "yes", bogus = true, tgt = true }, seat = { dx = 3, dy = 4 } } }
    for k, v in pairs(extra or {}) do db[k] = v end
    return db
end

function T.legacy_gunsight_values_migrate_into_the_active_profile_once()
    boot({ db = legacyDb() })
    local settings = ForeverSTUwaveDB.profiles.Default.settings
    eq(settings["gunsight.enabled"], false)
    eq(settings["gunsight.pieces.buff"], false)
    eq(settings["gunsight.pieces.you"], nil, "a non boolean value is ignored")
    eq(settings["gunsight.pieces.tgt"], nil, "a default value pins nothing")
    eq(settings["gunsight.pieces.bogus"], nil, "an unknown key is dropped")
    eq(ForeverSTUwaveDB.gunsight.enabled, nil, "legacy enabled removed")
    eq(ForeverSTUwaveDB.gunsight.pieces, nil, "legacy pieces removed")
    eq(ForeverSTUwaveDB.gunsight.seat.dx, 3, "seat stays where it was")
    eq(FS.Gunsight.IsEnabled(), false)
    eq(FS.Gunsight.IsPieceOn("buff"), false)
    eq(FS.Gunsight.IsPieceOn("you"), true)
    -- the user changes it back; the next load must not re-import anything
    FS.Config.Set("gunsight.pieces.buff", true)
    reload()
    eq(FS.Gunsight.IsPieceOn("buff"), true, "no second migration")
    eq(ForeverSTUwaveDB.gunsight.seat.dy, 4)
end

function T.migration_lands_in_the_profile_this_character_uses()
    local db = legacyDb({
        profiles = { Default = { settings = {}, layout = { v = 1, frames = {} } }, Raid = { settings = {}, layout = { v = 1, frames = {} } } },
        profileKeys = { ["Player-1-AAAA"] = "Raid" }, profilesVersion = 1,
    })
    boot({ db = db })
    eq(FS.Config.ActiveProfile(), "Raid")
    eq(db.profiles.Raid.settings["gunsight.pieces.buff"], false)
    eq(db.profiles.Default.settings["gunsight.pieces.buff"], nil, "Default untouched")
end

function T.migration_is_skipped_when_config_is_read_only_and_keeps_the_legacy_values()
    local db = legacyDb({ profilesVersion = 99 })
    boot({ db = db })
    yes(FS.Config.IsReadOnly())
    eq(db.gunsight.enabled, false, "legacy values kept for a later session")
    eq(db.gunsight.pieces.buff, false)
    eq(FS.Gunsight.IsEnabled(), true, "defaults in read-only")
end

function T.a_fresh_install_writes_no_gunsight_legacy_tables()
    boot({ db = {} })
    eq(ForeverSTUwaveDB.gunsight == nil or ForeverSTUwaveDB.gunsight.enabled == nil, true)
    eq(ForeverSTUwaveDB.gunsight == nil or ForeverSTUwaveDB.gunsight.pieces == nil, true)
end

function T.fsgun_and_the_window_show_the_same_state()
    local W = boot()
    W.Open("gunsight")
    local slash = SlashCmdList.FSGUN
    slash("piece shard off")
    eq(FS.Config.Get("gunsight.pieces.shard"), false, "/fsgun writes through FS.Config")
    no(row("Soul shards").control.fsChecked, "the window follows /fsgun")
    press("Soul shards")
    eq(FS.Gunsight.IsPieceOn("shard"), true, "/fsgun sees the window's change")
    __printed = {}
    slash("")
    local status = table.concat(__printed, "\n")
    yes(status:find("shard on", 1, true), "status reads the same state: " .. status)
    slash("off")
    eq(FS.Config.Get("gunsight.enabled"), false)
    no(row("Gunsight HUD").control.fsChecked)
    yes(table.concat(__printed, "\n"):lower():find("reload", 1, true), "off still says a reload is needed")
    slash("on")
    eq(FS.Config.Get("gunsight.enabled"), true)
    yes(row("Gunsight HUD").control.fsChecked)
end

function T.fsgun_reports_a_read_only_config()
    boot({ db = "junk" })
    __printed = {}
    SlashCmdList.FSGUN("piece shard off")
    yes(table.concat(__printed, " "):lower():find("read-only", 1, true), "read-only is said")
    eq(FS.Gunsight.IsPieceOn("shard"), true)
end

-------------------------------------------------------------------------------
-- Profiles
-------------------------------------------------------------------------------

local function profilesPage()
    local W = boot()
    W.Open("profiles")
    return W
end

function T.profiles_page_shows_the_active_profile_and_this_character()
    profilesPage()
    yes(findText("Profile in use", win()))
    yes(findText("Default", win()), "dropdown shows the active profile")
    yes(hasText(win(), "This character: "), "character line")
    yes(hasText(win(), "Bob-Realm"), "character label")
    for _, label in ipairs({ "New profile", "Copy from...", "Rename", "Delete", "Reset profile" }) do
        yes(findText(label, win()), "button " .. label)
    end
    yes(hasText(win(), "ACTIVE PROFILE") and hasText(win(), "MANAGE"))
end

function T.the_character_label_is_name_and_realm()
    boot({ db = { profileLabels = { ["Player-1-AAAA"] = "Old-Name" } } })
    FS.ConfigWindow.Open("profiles")
    yes(hasText(win(), "Bob-Realm"), "Config refreshes the label at login")
end

function T.the_dropdown_lists_profiles_and_switching_calls_set_active_profile()
    profilesPage()
    FS.Config.NewProfile("Raid")
    FS.Config.NewProfile("Alts")
    local dd = owner(findText("Default", win()))
    dd.scripts.OnClick(dd)
    yes(menu() and menu():IsVisible(), "menu opens")
    local items = {}
    for _, t in ipairs(texts(menu())) do items[#items + 1] = t end
    eq(table.concat(items, ","), "Default,Alts,Raid", "ListProfiles order")
    click("Raid", menu())
    eq(FS.Config.ActiveProfile(), "Raid")
    no(menu():IsVisible(), "menu closes on a pick")
    yes(findText("Raid", win()), "dropdown shows the new profile")
end

function T.new_profile_asks_for_a_name_creates_and_switches()
    profilesPage()
    click("New profile", win())
    yes(dialog() and dialog():IsVisible(), "prompt opens")
    local box = editBox()
    yes(box, "edit box")
    box:SetText("Raid")
    click("OK", dialog())
    yes(not dialog():IsVisible(), "prompt closes")
    local list = FS.Config.ListProfiles()
    eq(table.concat(list, ","), "Default,Raid")
    eq(FS.Config.ActiveProfile(), "Raid")
end

function T.a_bad_profile_name_shows_the_reason_and_keeps_the_prompt_open()
    profilesPage()
    FS.Config.NewProfile("Raid")
    click("New profile", win())
    editBox():SetText("raid")
    click("OK", dialog())
    yes(dialog():IsVisible(), "still open")
    yes(hasText(dialog(), "exists"), "reason shown")
    editBox():SetText("   ")
    click("OK", dialog())
    yes(hasText(dialog(), "empty"))
    click("Cancel", dialog())
    no(dialog():IsVisible())
    eq(#FS.Config.ListProfiles(), 2)
end

function T.enter_accepts_and_escape_cancels_the_prompt()
    profilesPage()
    click("New profile", win())
    local box = editBox()
    box:SetText("Raid")
    box.scripts.OnEnterPressed(box)
    eq(FS.Config.ActiveProfile(), "Raid")
    click("Rename", win())
    box = editBox()
    box.scripts.OnEscapePressed(box)
    no(dialog():IsVisible())
    eq(FS.Config.ActiveProfile(), "Raid")
    yes(win():IsShown(), "escape in the prompt does not close the window")
end

function T.rename_is_off_for_default_and_renames_the_active_profile()
    profilesPage()
    no(click("Rename", win()), "disabled on Default")
    FS.Config.NewProfile("Raid")
    FS.Config.SetActiveProfile("Raid")
    FS.ConfigWindow.RefreshAll()
    yes(click("Rename", win()))
    local box = editBox()
    eq(box:GetText(), "Raid", "prefilled with the current name")
    box:SetText("Mythic")
    click("OK", dialog())
    eq(FS.Config.ActiveProfile(), "Mythic")
    yes(findText("Mythic", win()))
end

function T.copy_from_lists_other_profiles_asks_and_copies()
    profilesPage()
    FS.Config.RegisterDefault("test.value", 1)
    FS.Config.NewProfile("Raid")
    FS.Config.SetActiveProfile("Raid")
    FS.Config.Set("test.value", 7)
    FS.Config.SetActiveProfile("Default")
    click("Copy from...", win())
    local items = texts(menu())
    eq(table.concat(items, ","), "Raid", "the active profile is not offered")
    click("Raid", menu())
    yes(dialog():IsVisible(), "asks first")
    eq(FS.Config.Get("test.value"), 1, "nothing copied yet")
    click("Confirm", dialog())
    eq(FS.Config.Get("test.value"), 7, "copied into the active profile")
    eq(FS.Config.ActiveProfile(), "Default")
end

function T.copy_from_is_off_when_there_is_nothing_to_copy()
    profilesPage()
    no(click("Copy from...", win()))
end

function T.delete_is_off_for_default_and_the_active_profile()
    profilesPage()
    no(click("Delete", win()), "only Default exists")
    FS.Config.NewProfile("Raid")
    FS.ConfigWindow.RefreshAll()
    yes(owner(findText("Delete", win())).enabled, "Raid can be deleted from Default")
    FS.Config.SetActiveProfile("Raid")
    FS.ConfigWindow.RefreshAll()
    no(owner(findText("Delete", win())).enabled, "Raid is active, Default cannot go")
end

function T.delete_offers_only_deletable_profiles_and_confirms()
    profilesPage()
    FS.Config.NewProfile("Raid")
    FS.Config.NewProfile("Alts")
    FS.Config.SetActiveProfile("Alts")
    FS.ConfigWindow.RefreshAll()
    click("Delete", win())
    eq(table.concat(texts(menu()), ","), "Raid", "not Default, not the active Alts")
    click("Raid", menu())
    yes(dialog():IsVisible(), "confirm first")
    click("Cancel", dialog())
    eq(table.concat(FS.Config.ListProfiles(), ","), "Default,Alts,Raid", "cancel deletes nothing")
    click("Delete", win()); click("Raid", menu())
    click("Confirm", dialog())
    eq(table.concat(FS.Config.ListProfiles(), ","), "Default,Alts")
end

function T.reset_profile_asks_then_resets()
    profilesPage()
    FS.Config.RegisterDefault("test.value", 1)
    FS.Config.Set("test.value", 5)
    click("Reset profile", win())
    yes(dialog():IsVisible(), "confirm first")
    eq(FS.Config.Get("test.value"), 5, "unchanged until confirmed")
    click("Cancel", dialog())
    eq(FS.Config.Get("test.value"), 5)
    click("Reset profile", win())
    click("Confirm", dialog())
    eq(FS.Config.Get("test.value"), 1)
end

function T.the_destructive_buttons_use_the_warning_skin()
    profilesPage()
    local del, reset = owner(findText("Delete", win())), owner(findText("Reset profile", win()))
    local pink, violet = FS.Theme.COLOR_HEALTH, FS.Theme.COLOR_BORDER
    local function ringIs(b, c) local r = b.fsSkin.border.ring.color; return r[1] == c[1] and r[2] == c[2] and r[3] == c[3] end
    local function textIs(b, c) return b.fsLabel.themeColor == c end
    yes(ringIs(del, pink) and ringIs(reset, pink), "the ring is pink")
    yes(textIs(del, pink) and textIs(reset, pink), "the label is pink")
    local rename = owner(findText("Rename", win()))
    yes(ringIs(rename, violet), "a plain button keeps the violet ring")
    yes(textIs(rename, FS.Theme.COLOR_POWER), "and the cyan label")
end

function T.profiles_headers_and_rows_carry_their_tooltips()
    profilesPage()
    local tips = {}
    for _, o in ipairs(ALL) do if o.fsTip and o:IsVisible() then tips[#tips + 1] = o.fsTip end end
    local all = table.concat(tips, "\n")
    yes(all:find("A profile holds layout positions and every setting in this window. Bug reports and logs stay account-wide.", 1, true), "active profile tip")
    yes(all:find("Default and the active profile cannot be deleted.", 1, true), "delete tip")
    yes(all:find("Cannot be undone.", 1, true), "reset tip")
end

-------------------------------------------------------------------------------
-- Read only
-------------------------------------------------------------------------------

function T.read_only_config_disables_every_control_and_says_why()
    local W = boot({ db = "junk", preWindow = unitFramesDefaults })
    W.Open("unitframes")
    local r = row("Hide player frame")
    no(r.control.enabled, "toggle disabled")
    press("Hide player frame")
    eq(FS.Config.Get("unitFrames.hidePlayer"), false)
    local icon
    for _, o in ipairs(ALL) do if o.fsReadOnlyIcon and o:IsVisible() then icon = o end end
    yes(icon, "a ? shows while read-only")
    icon.scripts.OnEnter(icon)
    yes(TOOLTIP.text:lower():find("read-only", 1, true))
    W.Open("profiles")
    no(owner(findText("New profile", win())).enabled, "profile buttons disabled")
    W.Open("gunsight")
    no(row("Gunsight HUD").control.enabled)
end

function T.the_read_only_icon_is_hidden_when_settings_are_writable()
    local W = boot({ preWindow = unitFramesDefaults })
    W.Open("unitframes")
    for _, o in ipairs(ALL) do if o.fsReadOnlyIcon then no(o:IsVisible(), "icon hidden") end end
end

-------------------------------------------------------------------------------
-- Extensibility
-------------------------------------------------------------------------------

function T.builders_auto_stack_and_bind_keys_or_get_set()
    local W = boot()
    FS.Config.RegisterDefault("demo.flag", false)
    FS.Config.RegisterDefault("demo.mode", "b")
    local store, confirmed, fired = false, 0, 0
    local frames = {}
    W.RegisterCategory({ key = "demo", label = "Demo", order = 3, build = function(content)
        local UI = W.UI
        frames.header = UI.Header(content, "Edit mode", "tip text")
        frames.keyed = UI.Toggle(content, { label = "Keyed", key = "demo.flag", tip = "why" })
        frames.manual = UI.Toggle(content, { label = "Manual", get = function() return store end, set = function(v) store = v end })
        frames.seg = UI.Segmented(content, { label = "Mode", key = "demo.mode", options = {
            { value = "a", text = "Alpha" }, { value = "b", text = "Beta" } } })
        frames.btn = UI.Button(content, { text = "Fire", onClick = function() fired = fired + 1 end })
        frames.big = UI.Button(content, { text = "EDIT", big = true, onClick = function() end })
        frames.warn = UI.Button(content, { text = "Wipe", warn = true, confirm = "Really?", onClick = function() confirmed = confirmed + 1 end })
        frames.custom = CreateFrame("Frame", nil, content)
        frames.custom:SetSize(100, 20)
        UI.Stack(content, frames.custom)
    end })
    W.Open("demo")
    local last = -1
    for _, name in ipairs({ "header", "keyed", "manual", "seg", "btn", "big", "warn", "custom" }) do
        local f = frames[name]
        yes(f, name .. " returned its frame")
        local p = f.points[1]
        yes(p, name .. " is anchored")
        local y = -p.y
        yes(y > last, name .. " stacks below the previous (" .. y .. " <= " .. last .. ")")
        last = y
    end
    -- key binding
    press("Keyed")
    eq(FS.Config.Get("demo.flag"), true)
    -- get/set binding
    press("Manual")
    eq(store, true)
    store = false
    W.RefreshAll()
    no(frames.manual.control.fsChecked, "get/set controls re-read on RefreshAll")
    -- segmented
    click("Alpha", win())
    eq(FS.Config.Get("demo.mode"), "a")
    FS.Config.Set("demo.mode", "b")
    yes(frames.seg.control.fsValue == "b", "segmented follows the key")
    -- plain and confirmed buttons
    click("Fire", win())
    eq(fired, 1)
    click("Wipe", win())
    eq(confirmed, 0, "confirm first")
    yes(dialog():IsVisible() and hasText(dialog(), "Really?"))
    click("Confirm", dialog())
    eq(confirmed, 1)
    click("Wipe", win()); click("Cancel", dialog())
    eq(confirmed, 1, "cancel does not fire")
end

function T.ui_confirm_runs_the_callback_only_on_accept()
    local W = boot()
    W.Open()
    local n = 0
    W.UI.Confirm("Sure?", function() n = n + 1 end)
    yes(hasText(dialog(), "Sure?"))
    click("Cancel", dialog()); eq(n, 0)
    W.UI.Confirm("Sure?", function() n = n + 1 end)
    click("Confirm", dialog()); eq(n, 1)
    no(dialog():IsVisible())
end

function T.closing_the_window_closes_its_popups()
    local W = boot()
    W.Open("profiles")
    FS.Config.NewProfile("Raid")
    click("New profile", win())
    yes(dialog():IsVisible())
    W.Close()
    no(dialog():IsVisible())
end

function T.refresh_on_open_picks_up_changes_made_while_closed()
    local W = boot({ preWindow = unitFramesDefaults })
    W.Open("unitframes")
    W.Close()
    FS.Config.Set("unitFrames.hideTarget", true)
    W.Open("unitframes")
    yes(row("Hide target frame").control.fsChecked)
end

-------------------------------------------------------------------------------
-- Text rules
-------------------------------------------------------------------------------

function T.no_player_facing_string_says_tape()
    local W = boot({ preWindow = unitFramesDefaults })
    W.RegisterCategory({ key = "layout", label = "Layout", order = 3, build = function() end })
    local seen = {}
    for _, key in ipairs({ "unitframes", "gunsight", "layout", "profiles" }) do
        W.Open(key)
        for _, t in ipairs(texts(win())) do seen[#seen + 1] = t end
        for _, o in ipairs(ALL) do
            if o.fsTip and o:IsVisible() then
                o.scripts.OnEnter(o)
                seen[#seen + 1] = TOOLTIP.text
                o.scripts.OnLeave(o)
            end
        end
    end
    yes(#seen > 20, "collected the strings")
    for _, t in ipairs(seen) do no(t:lower():find("tape", 1, true), "tape in: " .. t) end
end

-------------------------------------------------------------------------------
-- Review fixes
-------------------------------------------------------------------------------

function T.migration_keeps_values_the_profile_already_pins()
    local db = legacyDb({
        profiles = { Default = { settings = { ["gunsight.pieces.buff"] = true }, layout = { v = 1, frames = {} } } },
        profileKeys = {}, profilesVersion = 1,
    })
    boot({ db = db })
    local settings = db.profiles.Default.settings
    eq(settings["gunsight.pieces.buff"], true, "the profile's own value survives the legacy copy")
    eq(FS.Gunsight.IsPieceOn("buff"), true)
    eq(settings["gunsight.enabled"], false, "an unpinned key still migrates")
    eq(db.gunsight.enabled, nil, "legacy enabled is cleared")
    eq(db.gunsight.pieces, nil, "legacy pieces are cleared")
    eq(db.gunsight.seat.dx, 3, "seat stays")
end

function T.closing_hides_our_tooltip_but_not_one_that_belongs_to_another_frame()
    local W = boot({ preWindow = unitFramesDefaults })
    W.Open("unitframes")
    local icon
    for _, o in ipairs(ALL) do if o.fsTip and o:IsVisible() then icon = o end end
    icon.scripts.OnEnter(icon)
    yes(TOOLTIP.shown)
    W.Close()
    no(TOOLTIP.shown, "a tooltip owned by a window control goes with the window")
    local other = CreateFrame("Frame", nil, UIParent)
    GameTooltip:SetOwner(other)
    GameTooltip:Show()
    W.Open("unitframes")
    W.Close()
    yes(TOOLTIP.shown, "another frame's tooltip is left alone")
end

function T.a_hidden_window_does_not_refresh_its_controls()
    local W = boot()
    local reads = 0
    W.RegisterCategory({ key = "demo", label = "Demo", order = 3, build = function(content)
        W.UI.Toggle(content, { label = "Counted", get = function() reads = reads + 1; return false end, set = function() end })
    end })
    W.Open("demo")
    local shown = reads
    yes(shown >= 1)
    W.Close()
    FS.Config.NewProfile("Raid")
    FS.Config.SetActiveProfile("Raid")
    FS.Config.Set("gunsight.pieces.buff", false)
    W.RefreshAll()
    eq(reads, shown, "no control was read while the window was hidden")
    W.Open("demo")
    yes(reads > shown, "opening refreshes")
end

function T.a_refused_or_failing_write_is_reported()
    local W = boot({ preWindow = unitFramesDefaults })
    W.Open("unitframes")
    local realSet = FS.Config.Set
    FS.Config.Set = function() return false end
    __printed = {}
    press("Hide player frame")
    yes(table.concat(__printed, " "):find("read-only", 1, true), "a refused Set is said in chat")
    FS.Config.Set = function() error("boom") end
    __printed = {}
    press("Hide player frame")
    yes(table.concat(__printed, " "):lower():find("could not be changed", 1, true), "a throwing Set is said too")
    yes(#__errors >= 1, "and forwarded")
    FS.Config.Set = realSet
    W.RegisterCategory({ key = "demo", label = "Demo", order = 3, build = function(content)
        W.UI.Toggle(content, { label = "Manual", get = function() return false end, set = function() error("bad set") end })
    end })
    W.Open("demo")
    __printed = {}
    press("Manual")
    yes(table.concat(__printed, " "):lower():find("could not be changed", 1, true), "a throwing set() is said")
end

function T.a_disabled_button_does_not_hover_tint()
    profilesPage()
    local rename = owner(findText("Rename", win()))
    no(rename.enabled, "Rename is off on Default")
    local before = rename.fsFill.color
    local r, g, b = before[1], before[2], before[3]
    rename.scripts.OnEnter(rename)
    local after = rename.fsFill.color
    yes(after[1] == r and after[2] == g and after[3] == b, "no tint while disabled")
    local new = owner(findText("New profile", win()))
    local nr = new.fsFill.color[1]
    new.scripts.OnEnter(new)
    yes(new.fsFill.color[1] ~= nr, "an enabled button does tint")
    new.scripts.OnLeave(new)
    eq(new.fsFill.color[1], nr, "and clears on leave")
end

function T.re_registering_a_built_key_updates_the_label_but_never_rebuilds()
    local W = boot()
    local first, second = 0, 0
    W.RegisterCategory({ key = "demo", label = "Demo", order = 3, build = function() first = first + 1 end })
    W.Open("demo")
    W.RegisterCategory({ key = "demo", label = "Demo 2", order = 3, build = function() second = second + 1 end })
    W.Open("gunsight"); W.Open("demo")
    eq(first, 1); eq(second, 0, "first build wins")
    yes(findText("Demo 2", win()), "the nav shows the new label")
end

function T.the_nav_footer_lists_the_slash_commands()
    local W = boot()
    W.Open()
    yes(findText("/fsgun  /fsedit  /fsbug", win()))
end

function T.escape_closes_only_the_dialog_or_the_menu_not_the_window()
    profilesPage()
    FS.Config.NewProfile("Raid")
    FS.ConfigWindow.RefreshAll()
    click("New profile", win())
    local overlay = dialog().parent
    yes(overlay.keyboard, "the dialog listens for keys while it is up")
    overlay.scripts.OnKeyDown(overlay, "A")
    eq(overlay.propagate, true, "other keys reach the game")
    yes(dialog():IsVisible())
    overlay.scripts.OnKeyDown(overlay, "ESCAPE")
    eq(overlay.propagate, false, "Escape is consumed")
    no(dialog():IsVisible())
    no(overlay.keyboard, "keyboard capture is off once it closes")
    yes(win():IsShown(), "the window stays")
    click("Copy from...", win())
    local catcher = menu().parent
    yes(catcher.keyboard)
    catcher.scripts.OnKeyDown(catcher, "ESCAPE")
    eq(catcher.propagate, false)
    no(menu():IsVisible())
    no(catcher.keyboard)
    yes(win():IsShown(), "the window stays")
end

function T.open_close_and_profile_switches_leak_nothing()
    local registered = 0
    local W = boot({ preWindow = function()
        unitFramesDefaults()
        local orig = FS.Config.OnAnyChange
        FS.Config.OnAnyChange = function(fn) registered = registered + 1; return orig(fn) end
    end })
    eq(registered, 1, "one OnAnyChange registration")
    for _, key in ipairs({ "gunsight", "profiles", "unitframes" }) do W.Open(key) end
    W.Close()
    local frames = #ALL
    W.Open(); W.Close(); W.Open("gunsight")
    FS.Config.NewProfile("Raid")
    FS.Config.SetActiveProfile("Raid")
    FS.Config.SetActiveProfile("Default")
    FS.Config.Set("unitFrames.hidePlayer", true)
    W.RefreshAll()
    eq(#ALL, frames, "no frame or region was created")
    eq(registered, 1, "no extra registration")
end

__checks = T
"""


def boot() -> "LuaRuntime":
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute(MOCK)
    lua.globals().__session = lua.eval(SESSION)
    lua.globals().__configSrc = CONFIG_FILE.read_text(encoding="utf-8")
    lua.globals().__gunsightSrc = GUNSIGHT_FILE.read_text(encoding="utf-8")
    lua.globals().__windowSrc = WINDOW_FILE.read_text(encoding="utf-8") if WINDOW_FILE.exists() else "error('ConfigWindow.lua is missing')"
    lua.execute(CHECKS)
    return lua


def source_checks() -> list[tuple[str, str | None]]:
    """Text and API rules read straight from the files."""
    out: list[tuple[str, str | None]] = []
    src = WINDOW_FILE.read_text(encoding="utf-8") if WINDOW_FILE.exists() else ""
    out.append(("source_exists", None if src else f"{WINDOW_FILE} does not exist"))
    out.append(("source_never_says_tape", "the word 'tape' appears in ConfigWindow.lua" if re.search("tape", src, re.I) else None))
    banned = [r"\bSettings\.", r"RegisterCanvasLayoutCategory", r"StaticPopup", r"InterfaceOptions", r"\u2014"]
    hits = [p for p in banned if re.search(p, src)]
    out.append(("source_uses_no_blizzard_settings_or_static_popup_and_no_em_dash",
                f"banned pattern(s): {hits}" if hits else None))
    toc = [ln.strip() for ln in TOC_FILE.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("##")]
    want = "Modules/Config/ConfigWindow.lua"
    problems = []
    if want not in toc:
        problems.append(f"{want} is not in the .toc")
    else:
        at = toc.index(want)
        for dep in ("Core/Theme.lua", "Core/Config.lua", "Modules/CombatHud/Gunsight.lua", "Modules/UnitFrames/UnitFrames.lua"):
            if dep not in toc or toc.index(dep) > at:
                problems.append(f"{want} must load after {dep}")
        for later in ("Modules/Layout/LayoutEdit.lua", "Core/LayoutEdit.lua"):
            if later in toc and toc.index(later) < at:
                problems.append(f"{later} registers a category, so it must load after {want}")
    out.append(("toc_order", "; ".join(problems) or None))
    return out


# Checks that provoke an error on purpose; every other check must forward none.
EXPECTS_ERRORS = {"a_throwing_page_build_does_not_kill_the_window", "a_refused_or_failing_write_is_reported"}


def main() -> int:
    names = sorted(k for k in boot().eval("__checks").keys())
    failed = 0
    for name in names:
        # A fresh client per check: the saved variable, frames and callbacks must not leak.
        try:
            lua = boot()
            lua.eval("__checks")[name]()
            leaked = [] if name in EXPECTS_ERRORS else list(lua.eval("__errors").values())
            if leaked:
                raise LuaError(f"errors were forwarded to the error handler: {leaked}")
            print(f"ok    {name}")
        except LuaError as err:
            failed += 1
            print(f"FAIL  {name}: {err}")
    total = len(names)
    for name, problem in source_checks():
        total += 1
        if problem:
            failed += 1
            print(f"FAIL  {name}: {problem}")
        else:
            print(f"ok    {name}")
    print(f"{total - failed}/{total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
