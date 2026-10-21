#!/usr/bin/env python3
"""Exercise the REAL HeldArt.lua and ButtonSkins.lua (with the real Theme.lua) against a small client mock.

HeldArt keeps Blizzard's button art invisible: it zeroes a region's alpha and re-zeroes it when anything writes
alpha again (SetAlpha cannot be undone by the atlas and texture swaps Blizzard runs on every state change, which
is why the art is held rather than cleared). ButtonSkins draws the STUwave close button and text buttons on
top of whatever Blizzard button it is given, without ever touching its scripts, attributes or click path.

The mock models what these modules rely on, not the whole client: regions and frames that record what they were
asked to do, Button state textures and font objects, HookScript/hooksecurefunc post-hooks that run after the
original, SetEnabled firing OnEnable/OnDisable, and the combat lockdown flag. It is NOT the real client; a
green run here says nothing about what the game draws.

    python3 tools/buttonskins-harness.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

ADDON = Path(__file__).resolve().parent.parent / "forever-stuwave"
THEME_SRC = (ADDON / "Core/Theme.lua").read_text(encoding="utf-8")

def read_module(name: str) -> str:
    """A module's source, or "" while it does not exist yet (the cases then fail with a clear message, not a crash)."""
    path = ADDON / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


HELDART_SRC = read_module("Core/HeldArt.lua")
BUTTONSKINS_SRC = read_module("Core/ButtonSkins.lua")
PANELSKINS_SRC = read_module("Core/PanelSkins.lua")
POPUPS_SRC = read_module("Modules/Skins/Popups.lua")
PANELS_SRC = read_module("Modules/Skins/Panels.lua")

MOCK = r"""
COMBAT = false
function InCombatLockdown() return COMBAT end

-- hooksecurefunc(tbl, name, fn): the real one swaps tbl[name] for a wrapper that runs the original, then fn with the
-- same arguments. HOOKS counts installs per function name so a case can pin "one hook, not one per call".
HOOKS = {}
function hooksecurefunc(tbl, name, fn)
    local orig = tbl[name]
    if type(orig) ~= "function" then error("hooksecurefunc: " .. tostring(name) .. " is not a function") end
    HOOKS[name] = (HOOKS[name] or 0) + 1
    tbl[name] = function(...)
        local r = orig(...)
        fn(...)
        return r
    end
end

-- Objects ---------------------------------------------------------------------------------------------------------
local Obj = {}
Obj.__index = Obj

local function new(kind, parent)
    local o = setmetatable({ kind = kind, parent = parent, points = {}, shown = true, alpha = 1, w = 0, h = 0,
        regions = {}, children = {}, scripts = {}, hooks = {}, level = 1, enabled = true }, Obj)
    return o
end

function Obj:GetObjectType() return self.kind end
function Obj:GetParent() return self.parent end
function Obj:SetAlpha(a) self.alpha = a end
function Obj:GetAlpha() return self.alpha end
function Obj:Show() if not self.shown then self.shown = true; self:Fire("OnShow") end end
function Obj:Hide() if self.shown then self.shown = false; self:Fire("OnHide") end end
function Obj:SetShown(v) if v then self:Show() else self:Hide() end end
function Obj:IsShown() return self.shown end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:SetWidth(w) self.w = w end
function Obj:SetHeight(h) self.h = h end
function Obj:GetWidth() return self.w end
function Obj:GetHeight() return self.h end
function Obj:SetPoint(p, rel, rp, x, y)
    if type(rel) == "number" then rel, rp, x, y = nil, nil, rel, rp end
    self.points[p] = { rel = rel or self.parent, rp = rp or p, x = x or 0, y = y or 0 }
end
function Obj:ClearAllPoints() self.points = {} end
function Obj:SetAllPoints(rel) self.allPoints = rel or self.parent end
function Obj:GetEffectiveScale() return self.scale or 1 end
function Obj:SetFrameLevel(l) self.level = l end
function Obj:GetFrameLevel() return self.level end
function Obj:IsProtected() return self.protected == true end
function Obj:GetName() return self.name end
function Obj:SetHitRectInsets(l, r, t, b) self.hit = { l, r, t, b } end
function Obj:RegisterForClicks() end
function Obj:EnableMouse() end
function Obj:IsMouseOver() return self.mouseOver == true end
function Obj:RegisterEvent() end
function Obj:UnregisterEvent() end
function Obj:RegisterUnitEvent() end
function Obj:SetClipsChildren() end

-- Textures
function Obj:SetTexture(p) self.texture = p; self.atlas = nil end
function Obj:SetAtlas(a) self.atlas = a; self.texture = nil end
function Obj:SetColorTexture(r, g, b, a) self.color = { r, g, b, a } end
function Obj:SetVertexColor(r, g, b, a) self.tint = { r, g, b, a } end
function Obj:SetTexCoord(...) self.texcoord = { ... } end
function Obj:SetBlendMode(m) self.blend = m end
function Obj:SetDrawLayer(l, s) self.layer, self.sublevel = l, s end
function Obj:SetSnapToPixelGrid(v) self.snap = v end
function Obj:SetTexelSnappingBias(v) self.bias = v end
function Obj:SetTextureSliceMargins(l, r, t, b) self.slice = { l, r, t, b } end
function Obj:SetTextureSliceMode(m) self.sliceMode = m end
function Obj:SetDesaturated() end
function Obj:SetHorizTile() end
function Obj:SetVertTile() end

-- Font strings
function Obj:SetFont(path, size, flags) self.font = { path, size, flags }; return true end
function Obj:GetFont() return self.font and self.font[1] or "font", self.font and self.font[2] or 10, "" end
function Obj:SetText(t) self.text = t end
function Obj:GetText() return self.text end
function Obj:SetTextColor(r, g, b, a) self.textColor = { r, g, b, a } end
function Obj:SetShadowColor(r, g, b, a) self.shadow = { r, g, b, a } end
function Obj:SetShadowOffset() end
function Obj:SetJustifyH() end

-- Frames
function Obj:CreateTexture(_, layer, _, sub)
    local t = new("Texture", self)
    t.layer, t.sublevel = layer, sub
    self.regions[#self.regions + 1] = t
    return t
end
function Obj:CreateFontString(_, layer)
    local t = new("FontString", self)
    t.layer = layer
    self.regions[#self.regions + 1] = t
    return t
end
function Obj:GetRegions() return unpack(self.regions) end

local SCRIPTS = { OnEnter = true, OnLeave = true, OnMouseDown = true, OnMouseUp = true, OnShow = true, OnHide = true,
    OnClick = true, OnEnable = true, OnDisable = true }
function Obj:SetScript(name, fn) self.scripts[name] = fn end
function Obj:GetScript(name) return self.scripts[name] end
function Obj:HookScript(name, fn)
    if not SCRIPTS[name] then error("Frame:HookScript(): " .. tostring(name) .. " is not a valid script type") end
    self.hooks[name] = self.hooks[name] or {}
    table.insert(self.hooks[name], fn)
end
-- Fire: the primary handler, then every HookScript hook, the way the engine runs a script.
function Obj:Fire(name, ...)
    local fn = self.scripts[name]
    if fn then fn(self, ...) end
    for _, h in ipairs(self.hooks[name] or {}) do h(self, ...) end
end

-- Buttons: state textures are created on first ask, the way the engine does when a template declares them.
local STATE = { Normal = "normalTexture", Pushed = "pushedTexture", Highlight = "highlightTexture", Disabled = "disabledTexture" }
for kind, field in pairs(STATE) do
    Obj["Get" .. kind .. "Texture"] = function(self)
        if not self.art or not self.art[kind] then return nil end
        if not self[field] then
            self[field] = new("Texture", self)
            self[field].stateTexture = kind
            self.regions[#self.regions + 1] = self[field]
        end
        return self[field]
    end
    Obj["Set" .. kind .. "Texture"] = function(self, tex)
        -- a SetNormalTexture with a path builds a FRESH state region, like MoneyFrame_Update does
        self.art = self.art or {}
        self.art[kind] = true
        self[field] = nil
        local t = self["Get" .. kind .. "Texture"](self)
        t:SetTexture(tex)
    end
    Obj["Set" .. kind .. "Atlas"] = function(self, atlas)
        self.art = self.art or {}
        self.art[kind] = true
        local t = self["Get" .. kind .. "Texture"](self)
        t:SetAtlas(atlas)
    end
    Obj["Set" .. kind .. "FontObject"] = function(self, obj) self["font" .. kind] = obj end
    Obj["Get" .. kind .. "FontObject"] = function(self) return self["font" .. kind] end
end
function Obj:GetFontString() return self.fontString end
function Obj:SetText(t) self.text = t end
function Obj:IsEnabled() return self.enabled end
function Obj:Enable() if not self.enabled then self.enabled = true; self:Fire("OnEnable") end end
function Obj:Disable() if self.enabled then self.enabled = false; self:Fire("OnDisable") end end
function Obj:SetEnabled(v) if v then self:Enable() else self:Disable() end end
function Obj:SetMotionScriptsWhileDisabled() end

-- A Blizzard-style button: its own state textures, the three slice regions, and a label.
function NewButton(parent, opts)
    opts = opts or {}
    local b = new("Button", parent)
    if parent then parent.children[#parent.children + 1] = b end
    b.w, b.h = opts.w or 24, opts.h or 24
    b.protected = opts.protected
    if opts.slices then
        for _, key in ipairs({ "Left", "Middle", "Right" }) do
            local t = b:CreateTexture(nil, "BACKGROUND")
            t:SetAtlas("stock-" .. key)
            b[key] = t
        end
    end
    b.art = {}
    for _, kind in ipairs(opts.states or {}) do b["Set" .. kind .. "Atlas"](b, "stock-" .. kind) end
    if opts.text ~= nil then
        local fs = b:CreateFontString(nil, "OVERLAY")
        fs:SetText(opts.text)
        b.fontString = fs
        b.text = opts.text
    end
    return b
end

ALL_WATCHERS = {}
function CreateFrame(kind, name, parent)
    local f = new(kind or "Frame", parent)
    ALL_WATCHERS[#ALL_WATCHERS + 1] = f
    if parent then parent.children[#parent.children + 1] = f end
    if name then f.name = name; _G[name] = f end
    return f
end
UIParent = CreateFrame("Frame", "UIParent")

local fontObjects = {}
FONT_OBJECTS = fontObjects
function CreateFont(name)
    local o = setmetatable({ fontName = name }, Obj)
    fontObjects[#fontObjects + 1] = o
    if name then _G[name] = o end
    return o
end

Enum = { UITextureSliceMode = { Stretched = 1 } }
PPU = 1                         -- physical pixels per UI unit; a case sets it before the skin runs
FS = { LogDegradeOnce = function() end }
FS.FrameHelpers = { PixelsPerUnit = function() return PPU end }
assert(loadstring(THEME_SRC, "@Theme.lua"))("forever-stuwave", FS)
Theme = FS.Theme

function LoadHeldArt()
    assert(HELDART_SRC ~= "", "Core/HeldArt.lua does not exist yet")
    assert(loadstring(HELDART_SRC, "@HeldArt.lua"))("forever-stuwave", FS)
    return FS.HeldArt
end
function LoadButtonSkins()
    assert(BUTTONSKINS_SRC ~= "", "Core/ButtonSkins.lua does not exist yet")
    LoadHeldArt()
    assert(loadstring(BUTTONSKINS_SRC, "@ButtonSkins.lua"))("forever-stuwave", FS)
    return FS.ButtonSkins
end

-- The skin parts of a button, failing with its name when it was not skinned.
function Skinned(button, what)
    local p = FS.ButtonSkins.Parts(button)
    assert(p, what .. " was not skinned")
    return p
end

function Near(a, b, eps) return math.abs(a - b) <= (eps or 1e-6) end

-- The Game Menu as Blizzard builds it: Border and Header child frames, a button pool whose buttons are the real
-- templated Buttons, and an InitButtons that a case replaces to add buttons the way AddButton does.
SlashCmdList = {}
LOG_OUT, EXIT_GAME, RETURN_TO_GAME, OPTIONS_MENU = "Log Out", "Exit Game", "Return to Game", "Options"
function MakeGameMenu()
    local menu = CreateFrame("Frame", "GameMenuFrame")
    menu.w, menu.h = 260, 420
    menu.Border = CreateFrame("Frame", nil, menu)
    menu.Header = CreateFrame("Frame", nil, menu)
    menu.active = {}
    menu.buttonPool = { EnumerateActive = function() return pairs(menu.active) end }
    function menu:Add(text, opts)
        opts = opts or {}
        local b = NewButton(menu, { w = 200, h = 36, slices = true, states = { "Highlight" }, text = text })
        b.enabled = not opts.disabled
        menu.active[b] = true
        return b
    end
    menu.InitButtons = function() end
    return menu
end
function LoadPanels()
    LoadButtonSkins()
    assert(PANELSKINS_SRC ~= "" and PANELS_SRC ~= "", "PanelSkins.lua / Panels.lua missing")
    assert(loadstring(PANELSKINS_SRC, "@PanelSkins.lua"))("forever-stuwave", FS)
    assert(loadstring(PANELS_SRC, "@Panels.lua"))("forever-stuwave", FS)
end
-- A stock Blizzard text button: UIPanelButtonTemplate's three slices, the stock hover glow and a label.
function StockText(parent, text, w, h)
    return NewButton(parent, { w = w or 96, h = h or 22, slices = true, states = { "Highlight" }, text = text })
end
function LoadPopups()
    LoadButtonSkins()
    assert(PANELSKINS_SRC ~= "" and POPUPS_SRC ~= "", "PanelSkins.lua / Popups.lua missing")
    assert(loadstring(PANELSKINS_SRC, "@PanelSkins.lua"))("forever-stuwave", FS)
    assert(loadstring(POPUPS_SRC, "@Popups.lua"))("forever-stuwave", FS)
end

-- A panel frame with a stock Blizzard icon-only close button (24 x 24, four state textures), as
-- UIPanelCloseButtonDefaultAnchors builds it. Returns frame, button.
function StockX(frame_name)
    local frame = CreateFrame("Frame", frame_name)
    frame.w, frame.h = 400, 300
    local b = NewButton(frame, { states = { "Normal", "Pushed", "Highlight", "Disabled" } })
    b.points.TOPRIGHT = { rel = frame, rp = "TOPRIGHT", x = 1, y = 0 }
    return frame, b
end

function Mix(a, b, t) return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t } end
function SameRgb(c, want, eps)
    return c and Near(c[1], want[1], eps or 1e-4) and Near(c[2], want[2], eps or 1e-4) and Near(c[3], want[3], eps or 1e-4)
end
-- A glyph cell's pixel position in the button (x right, y down), from its TOPLEFT anchor and the pixels per unit.
function CellPx(t)
    local p = t.points.TOPLEFT
    return math.floor(p.x * PPU + 0.5), math.floor(-p.y * PPU + 0.5)
end
function CellSet(parts)
    local set, n = {}, 0
    for _, t in ipairs(parts.glyph) do
        if t.shown then
            local x, y = CellPx(t)
            set[x .. "," .. y] = true
            n = n + 1
        end
    end
    return set, n
end
"""

CASES: list[tuple[str, str]] = []


def case(name: str, body: str) -> None:
    CASES.append((name, body))


# ---------------------------------------------------------------------------
# HeldArt: Blizzard art kept invisible
# ---------------------------------------------------------------------------

case("hold_zeroes_alpha_now_and_again_when_another_writer_raises_it", """
    local H = LoadHeldArt()
    local tex = new_texture()
    tex:SetAlpha(0.8)
    H.Hold(tex)
    assert(tex.alpha == 0, "held at once: " .. tex.alpha)
    tex:SetAlpha(1)
    assert(tex.alpha == 0, "a later alpha write must be re-zeroed: " .. tex.alpha)
""")

case("hold_installs_one_hook_per_region_however_often_it_is_called", """
    local H = LoadHeldArt()
    local tex = new_texture()
    H.Hold(tex); H.Hold(tex); H.Hold(tex)
    assert(HOOKS.SetAlpha == 1, "SetAlpha hooks: " .. tostring(HOOKS.SetAlpha))
""")

case("hold_does_not_recurse_through_its_own_zero_write", """
    local H = LoadHeldArt()
    local tex = new_texture()
    local writes = 0
    local base = tex.SetAlpha
    tex.SetAlpha = function(self, a) writes = writes + 1; base(self, a) end
    H.Hold(tex)
    writes = 0
    tex:SetAlpha(1)
    assert(writes == 2, "the other writer's call plus our one zero write, got " .. writes)
""")

case("hold_ignores_nil_and_anything_that_is_not_a_texture", """
    local H = LoadHeldArt()
    H.Hold(nil)
    H.Hold(7)
    local fs = new_fontstring()
    H.Hold(fs)
    assert(fs.alpha == 1, "a FontString is not art: " .. fs.alpha)
    assert(HOOKS.SetAlpha == nil, "no hook for non-textures")
""")

case("hold_normal_texture_reaches_the_parentkey_and_whatever_the_getter_returns_now", """
    local H = LoadHeldArt()
    local b = NewButton(nil, { states = { "Normal" } })
    local keyed = new_texture()
    b.NormalTexture = keyed
    H.HoldNormal(b)
    assert(keyed.alpha == 0, "the NormalTexture key is held")
    assert(b:GetNormalTexture().alpha == 0, "the getter's region is held")
""")

case("hold_button_holds_slice_regions_and_all_four_state_textures", """
    local H = LoadHeldArt()
    local b = NewButton(nil, { slices = true, states = { "Normal", "Pushed", "Highlight", "Disabled" }, text = "Close" })
    H.HoldButton(b)
    for _, key in ipairs({ "Left", "Middle", "Right" }) do assert(b[key].alpha == 0, key .. " held") end
    for _, kind in ipairs({ "Normal", "Pushed", "Highlight", "Disabled" }) do
        assert(b["Get" .. kind .. "Texture"](b).alpha == 0, kind .. " held")
    end
    assert(b.fontString.alpha == 1, "the label is not art")
""")

case("hold_button_leaves_the_regions_it_is_told_to_keep", """
    local H = LoadHeldArt()
    local b = NewButton(nil, { slices = true })
    local ours = b:CreateTexture(nil, "OVERLAY")
    H.HoldButton(b, { [ours] = true })
    assert(ours.alpha == 1, "a kept region stays visible: " .. ours.alpha)
    assert(b.Left.alpha == 0, "the stock art is still held")
""")

case("hold_button_holds_a_state_texture_blizzard_builds_afterwards", """
    local H = LoadHeldArt()
    local b = NewButton(nil, { states = { "Normal" } })
    H.HoldButton(b)
    b:SetNormalTexture("Interface\\\\Buttons\\\\fresh")
    assert(b:GetNormalTexture().alpha == 0, "a fresh normal texture is held by the setter hook")
    b:SetHighlightAtlas("stock-highlight")
    assert(b:GetHighlightTexture().alpha == 0, "a highlight atlas set later is held too")
""")

case("hold_button_does_not_error_on_a_table_that_is_not_a_frame", """
    local H = LoadHeldArt()
    H.HoldButton({})
    H.HoldButton(nil)
    H.HoldNormal({})
""")

# ---------------------------------------------------------------------------
# The close button (the X)
# ---------------------------------------------------------------------------

case("x_button_hides_the_stock_art_and_keeps_it_hidden", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b)
    for _, kind in ipairs({ "Normal", "Pushed", "Highlight", "Disabled" }) do
        local t = b["Get" .. kind .. "Texture"](b)
        assert(t.alpha == 0, kind .. " state texture is held hidden")
        t:SetAlpha(1)
        assert(t.alpha == 0, kind .. " stays hidden when Blizzard re-asserts it")
        t:SetAtlas("RedButton-Exit")
        assert(t.alpha == 0, kind .. " stays hidden across an atlas swap")
    end
""")

case("x_button_is_a_14_unit_plate_seated_top_right_minus_5_minus_3_with_a_roomier_hit_rect", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b, { anchor = frame })
    assert(b.w == 14 and b.h == 14, "plate " .. b.w .. " x " .. b.h)
    local p = b.points.TOPRIGHT
    assert(p and p.rel == frame and p.rp == "TOPRIGHT" and p.x == -5 and p.y == -3,
        "seat " .. tostring(p and p.x) .. "," .. tostring(p and p.y))
    local n = 0
    for _ in pairs(b.points) do n = n + 1 end
    assert(n == 1, "exactly one anchor, the stock TOPRIGHT +1,0 is gone: " .. n)
    assert(b.hit and b.hit[1] == -3 and b.hit[2] == -3 and b.hit[3] == -2 and b.hit[4] == -3, "hit insets")
""")

case("x_button_seats_to_its_parent_when_no_anchor_frame_is_given", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b)
    assert(b.points.TOPRIGHT.rel == frame, "the button's parent")
""")

case("x_button_plate_is_an_even_pixel_count_and_its_offsets_are_whole_pixels", """
    PPU = 1.2   -- the player's display: effective scale 0.64 at 1440p
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b, { anchor = frame })
    -- 14 units = 16.8 px, rounded up to the next even count, 18 px = 15 units
    assert(Near(b.w, 15) and Near(b.h, 15), "plate " .. b.w)
    local p = b.points.TOPRIGHT
    assert(Near(p.x, -5) and Near(p.y, -4 / 1.2), "offsets are 6 px and 4 px: " .. p.x .. "," .. p.y)
""")

case("x_glyph_is_a_six_by_six_pixel_x_centred_in_the_plate", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b)
    local parts = B.Parts(b)
    local set, n = CellSet(parts)
    assert(n == 12, "twelve one pixel squares: " .. n)
    -- margin (14 - 6) / 2 = 4 on every side; two diagonals of a 6 x 6 square
    for k = 0, 5 do
        assert(set[(4 + k) .. "," .. (4 + k)], "main diagonal " .. k)
        assert(set[(4 + 5 - k) .. "," .. (4 + k)], "anti diagonal " .. k)
    end
    for _, t in ipairs(parts.glyph) do assert(Near(t.w, 1) and Near(t.h, 1), "a pixel is one unit at 1 px per unit") end
""")

case("x_glyph_stays_six_physical_pixels_and_centred_when_a_unit_is_1_2_pixels", """
    PPU = 1.2
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b)
    local parts = B.Parts(b)
    local set, n = CellSet(parts)
    assert(n == 12, "twelve cells: " .. n)
    -- an 18 px plate: margin (18 - 6) / 2 = 6
    for k = 0, 5 do
        assert(set[(6 + k) .. "," .. (6 + k)], "main diagonal " .. k)
        assert(set[(6 + 5 - k) .. "," .. (6 + k)], "anti diagonal " .. k)
    end
    for _, t in ipairs(parts.glyph) do assert(Near(t.w, 1 / 1.2), "one pixel is 1/1.2 unit: " .. t.w) end
""")

case("x_glyph_cells_snap_to_the_pixel_grid_with_no_texel_bias", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b)
    for i, t in ipairs(B.Parts(b).glyph) do
        assert(t.snap == true and t.bias == 0, "cell " .. i .. " snaps with bias 0")
    end
""")

case("x_button_rests_as_ink_with_a_pink_ring_halo_and_glyph", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b)
    local parts = B.Parts(b)
    assert(SameRgb(parts.face.tint, Theme.COLOR_BUTTON_INK), "face is ink")
    assert(SameRgb(parts.ring.tint, Theme.COLOR_HEALTH) and Near(parts.ring.tint[4], 0.70), "ring pink at .70")
    assert(SameRgb(parts.halo.tint, Theme.COLOR_HEALTH) and Near(parts.halo.tint[4], 0.35), "halo pink at .35")
    assert(SameRgb(parts.glyph[1].color, Theme.COLOR_HEALTH) and Near(parts.glyph[1].color[4], 1), "glyph pink")
    assert(parts.disc.shown == false or Near(parts.disc.tint[4], 0), "no glyph glow at rest")
""")

case("x_button_hover_stays_pink_washes_the_face_and_lights_the_ring_halo_and_glyph", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b)
    local parts = B.Parts(b)
    b:Fire("OnEnter")
    assert(SameRgb(parts.face.tint, Mix(Theme.COLOR_BUTTON_INK, Theme.COLOR_HEALTH, 0.16)), "face + 16% pink")
    assert(Near(parts.ring.tint[4], 1.0) and Near(parts.halo.tint[4], 0.70), "ring 1.0, halo .70")
    assert(SameRgb(parts.glyph[1].color, Mix(Theme.COLOR_HEALTH, { 1, 1, 1 }, 0.12)), "glyph lifts toward white by 12%")
    assert(parts.disc.shown and SameRgb(parts.disc.tint, Theme.COLOR_HEALTH) and Near(parts.disc.tint[4], 0.45), "glow disc .45")
    b:Fire("OnLeave")
    assert(SameRgb(parts.face.tint, Theme.COLOR_BUTTON_INK) and Near(parts.ring.tint[4], 0.70), "back to rest on leave")
""")

case("x_button_pressed_goes_further_than_hover_and_releases_back_to_hover", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b)
    local parts = B.Parts(b)
    b:Fire("OnEnter")
    b:Fire("OnMouseDown")
    assert(SameRgb(parts.face.tint, Mix(Theme.COLOR_BUTTON_INK, Theme.COLOR_HEALTH, 0.32)), "face + 32% pink")
    assert(Near(parts.ring.tint[4], 1.0) and Near(parts.halo.tint[4], 0.50), "ring 1.0, halo .50")
    assert(SameRgb(parts.glyph[1].color, Mix(Theme.COLOR_HEALTH, { 1, 1, 1 }, 0.40)), "glyph +40% white")
    assert(Near(parts.disc.tint[4], 0.30), "glow .30")
    b:Fire("OnMouseUp")
    assert(SameRgb(parts.face.tint, Mix(Theme.COLOR_BUTTON_INK, Theme.COLOR_HEALTH, 0.16)), "released: hover again")
""")

case("x_button_disabled_dims_every_piece_to_four_tenths_and_ignores_the_mouse", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b)
    local parts = B.Parts(b)
    b:Disable()
    assert(Near(parts.ring.tint[4], 0.70 * 0.4) and Near(parts.halo.tint[4], 0), "ring dimmed, halo off")
    assert(Near(parts.face.tint[4], 0.4), "face alpha .4: " .. tostring(parts.face.tint[4]))
    assert(Near(parts.glyph[1].color[4], 0.4), "glyph alpha .4")
    b:Fire("OnEnter"); b:Fire("OnMouseDown")
    assert(SameRgb(parts.face.tint, Theme.COLOR_BUTTON_INK), "a disabled button takes no hover or press wash")
    b:Enable()
    assert(Near(parts.face.tint[4], 1) and Near(parts.ring.tint[4], 1.0 * 1), "enabled again, still hovered: lit")
""")

case("x_button_never_touches_scripts_attributes_or_the_enabled_state", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    local click = function() end
    b.scripts.OnClick = click
    local calls = 0
    for _, m in ipairs({ "SetScript", "SetEnabled", "Enable", "Disable", "SetAttribute", "SetText" }) do
        b[m] = function() calls = calls + 1 end
    end
    B.SkinCloseButton(b)
    assert(calls == 0, "skin wrote through " .. calls .. " forbidden setters")
    assert(b.scripts.OnClick == click, "the click handler is untouched")
""")

case("x_button_on_a_protected_frame_in_combat_gets_chrome_but_no_geometry", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    b.protected = true
    COMBAT = true
    local geometry = 0
    for _, m in ipairs({ "SetSize", "SetWidth", "SetHeight", "SetPoint", "ClearAllPoints", "SetHitRectInsets" }) do
        local base = b[m]
        b[m] = function(self, ...) geometry = geometry + 1; return base(self, ...) end
    end
    B.SkinCloseButton(b)
    assert(geometry == 0, "geometry writes in combat: " .. geometry)
    assert(B.Parts(b) and #B.Parts(b).glyph == 12, "the chrome was still built")
    assert(b:GetNormalTexture().alpha == 0, "the stock art is still held")
    COMBAT = false
    b:Fire("OnShow")
    assert(b.w == 14, "seated once combat ends and the button is shown")
""")

case("x_button_is_reseated_on_show_when_the_pixel_scale_changed", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b)
    assert(b.w == 14, "14 units at 1 px per unit")
    PPU = 1.2
    b:Fire("OnShow")
    assert(Near(b.w, 15), "18 px plate at 1.2 px per unit: " .. b.w)
    local set, n = CellSet(B.Parts(b))
    assert(n == 12 and set["6,6"] and set["11,6"], "glyph re-seated on the larger plate")
""")

case("x_skin_is_idempotent", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    B.SkinCloseButton(b)
    local regions, hooks = #b.regions, 0
    for _, list in pairs(b.hooks) do hooks = hooks + #list end
    B.SkinCloseButton(b)
    local hooks2 = 0
    for _, list in pairs(b.hooks) do hooks2 = hooks2 + #list end
    assert(#b.regions == regions, "no second set of textures: " .. regions .. " -> " .. #b.regions)
    assert(hooks2 == hooks, "no second set of script hooks")
""")

case("x_button_keeps_a_ring_and_glow_an_earlier_skin_button_call_drew", """
    local B = LoadButtonSkins()
    local frame, b = StockX()
    Theme.SkinButton(b)                    -- the old Popups path
    local earlier = b.fsSkin.border.ring
    B.SkinCloseButton(b)
    assert(earlier.alpha == 1, "the earlier ring is not held hidden")
    assert(B.Parts(b).ring == earlier, "and it is the ring the states paint")
""")

case("new_close_button_builds_a_plain_button_with_the_x_and_the_click_handler", """
    local B = LoadButtonSkins()
    local parent = CreateFrame("Frame")
    local clicked = 0
    local b = B.NewCloseButton(parent, function() clicked = clicked + 1 end)
    assert(b:GetParent() == parent and b:GetObjectType() == "Button", "a button of the parent")
    assert(b.points.TOPRIGHT.rel == parent and b.points.TOPRIGHT.x == -5 and b.points.TOPRIGHT.y == -3, "seat")
    assert(#B.Parts(b).glyph == 12, "the X")
    b.scripts.OnClick(b)
    assert(clicked == 1, "click handler runs")
""")

# ---------------------------------------------------------------------------
# Which button of a panel is the X
# ---------------------------------------------------------------------------

case("resolve_finds_the_close_panel_button_the_close_button_the_border_frame_one_and_the_global", """
    local B = LoadButtonSkins()
    local frame = CreateFrame("Frame", "ResolvePanel")
    local a = NewButton(frame, {})
    local c = NewButton(frame, { text = "Close" })
    local border = CreateFrame("Frame", nil, frame)
    local d = NewButton(border, {})
    local e = NewButton(frame, {})
    frame.ClosePanelButton, frame.CloseButton, frame.BorderFrame = a, c, { CloseButton = d }
    _G.ResolvePanelCloseButton = e
    local found = B.ResolveCloseButtons(frame)
    local by = {}
    for _, f in ipairs(found) do by[f.button] = f.kind end
    assert(#found == 4, "four buttons: " .. #found)
    assert(by[a] == "x" and by[d] == "x" and by[e] == "x", "icon-only buttons are X buttons")
    assert(by[c] == "text", "a button with a label is a text button")
""")

case("resolve_lists_a_button_reachable_two_ways_once_and_ignores_what_is_not_a_button", """
    local B = LoadButtonSkins()
    local frame = CreateFrame("Frame", "DupPanel")
    local a = NewButton(frame, {})
    frame.ClosePanelButton, frame.CloseButton = a, a
    _G.DupPanelCloseButton = a
    assert(#B.ResolveCloseButtons(frame) == 1, "once")
    frame.ClosePanelButton, frame.CloseButton, _G.DupPanelCloseButton = "oops", {}, 7
    assert(#B.ResolveCloseButtons(frame) == 0, "strings, plain tables and numbers are not buttons")
    assert(#B.ResolveCloseButtons(nil) == 0, "nil frame")
""")

case("resolve_treats_a_button_whose_label_is_only_in_its_font_string_as_a_text_button", """
    local B = LoadButtonSkins()
    local frame = CreateFrame("Frame")
    local b = NewButton(frame, { text = "Close" })
    b.text = nil                    -- GetText answers nothing; the font string has the label
    frame.CloseButton = b
    assert(B.ResolveCloseButtons(frame)[1].kind == "text", "the font string's text counts")
""")

case("theme_skin_panel_skins_the_x_through_the_forwarder", """
    local B = LoadButtonSkins()
    local frame = CreateFrame("Frame", "PanelWithX")
    frame.w, frame.h = 300, 200
    local x = NewButton(frame, { states = { "Normal", "Pushed", "Highlight", "Disabled" } })
    frame.ClosePanelButton = x
    Theme.SkinPanel(frame, { title = "demo" })
    assert(B.Parts(x), "SkinPanel reaches the close button")
""")

case("theme_skin_close_button_is_a_no_op_until_button_skins_is_loaded", """
    local frame = CreateFrame("Frame")
    Theme.SkinCloseButton(frame)
    Theme.SkinCloseButton(nil)
""")


# ---------------------------------------------------------------------------
# The text button
# ---------------------------------------------------------------------------

case("text_button_hides_the_stock_slices_and_state_art_and_keeps_the_label", """
    local B = LoadButtonSkins()
    local b = NewButton(nil, { w = 96, h = 22, slices = true, states = { "Highlight" }, text = "Close" })
    B.SkinTextButton(b)
    for _, key in ipairs({ "Left", "Middle", "Right" }) do
        assert(b[key].alpha == 0, key .. " held hidden")
        b[key]:SetAtlas("stock-" .. key .. "-Pressed")
        b[key]:SetAlpha(1)
        assert(b[key].alpha == 0, key .. " stays hidden when Blizzard swaps and re-shows it")
    end
    assert(b:GetHighlightTexture().alpha == 0, "the stock hover glow is held hidden")
    assert(b.fontString.alpha == 1, "the label is not art")
""")

case("text_button_rests_as_ink_with_a_violet_ring_halo_and_cyan_label_by_default", """
    local B = LoadButtonSkins()
    local b = NewButton(nil, { w = 96, h = 22, slices = true, text = "Close" })
    local p = B.SkinTextButton(b)
    assert(SameRgb(p.face.tint, Theme.COLOR_BUTTON_INK), "face is ink")
    assert(SameRgb(p.ring.tint, Theme.COLOR_BORDER) and Near(p.ring.tint[4], 0.70), "ring violet at .70")
    assert(SameRgb(p.halo.tint, Theme.COLOR_BORDER) and Near(p.halo.tint[4], 0.35), "halo violet at .35")
    assert(SameRgb(b.fontString.textColor, Theme.COLOR_POWER) and Near(b.fontString.textColor[4], 1), "label cyan")
""")

case("text_button_accents_set_the_ring_and_the_label", """
    local B = LoadButtonSkins()
    local function skin(accent)
        local b = NewButton(nil, { w = 96, h = 22, slices = true, text = "Go" })
        return B.SkinTextButton(b, { accent = accent }), b
    end
    local cp, cb = skin("cyan")
    assert(SameRgb(cp.ring.tint, Theme.COLOR_POWER) and SameRgb(cb.fontString.textColor, Theme.COLOR_POWER), "cyan ring and label")
    local pp, pb = skin("pink")
    assert(SameRgb(pp.ring.tint, Theme.COLOR_HEALTH) and SameRgb(pb.fontString.textColor, Theme.COLOR_HEALTH), "pink ring and label")
    local vp, vb = skin("nonsense")
    assert(SameRgb(vp.ring.tint, Theme.COLOR_BORDER), "an unknown accent is violet")
""")

case("text_button_hover_washes_the_face_toward_its_ring_colour_and_lifts_the_label", """
    local B = LoadButtonSkins()
    local b = NewButton(nil, { w = 96, h = 22, slices = true, text = "Close" })
    local p = B.SkinTextButton(b)
    b:Fire("OnEnter")
    assert(SameRgb(p.face.tint, Mix(Theme.COLOR_BUTTON_INK, Theme.COLOR_BORDER, 0.16)), "face + 16% violet")
    assert(Near(p.ring.tint[4], 1.0) and Near(p.halo.tint[4], 0.70), "ring 1.0, halo .70")
    assert(SameRgb(b.fontString.textColor, Mix(Theme.COLOR_POWER, { 1, 1, 1 }, 0.12)), "label +12% white")
    b:Fire("OnLeave")
    assert(SameRgb(p.face.tint, Theme.COLOR_BUTTON_INK) and SameRgb(b.fontString.textColor, Theme.COLOR_POWER), "rest on leave")
""")

case("text_button_pressed_and_disabled", """
    local B = LoadButtonSkins()
    local b = NewButton(nil, { w = 96, h = 22, slices = true, text = "Close" })
    local p = B.SkinTextButton(b)
    b:Fire("OnEnter"); b:Fire("OnMouseDown")
    assert(SameRgb(p.face.tint, Mix(Theme.COLOR_BUTTON_INK, Theme.COLOR_BORDER, 0.32)), "face + 32%")
    assert(Near(p.halo.tint[4], 0.50), "halo .50")
    assert(SameRgb(b.fontString.textColor, Mix(Theme.COLOR_POWER, { 1, 1, 1 }, 0.40)), "label +40% white")
    b:Fire("OnMouseUp")
    assert(SameRgb(b.fontString.textColor, Mix(Theme.COLOR_POWER, { 1, 1, 1 }, 0.12)), "released over the button: the hover label")
    b:Fire("OnLeave")
    b:Disable()
    assert(Near(p.ring.tint[4], 0.70 * 0.4) and Near(p.halo.tint[4], 0) and Near(p.face.tint[4], 0.4), "dimmed to .4, halo off")
    assert(Near(b.fontString.textColor[4], 0.4), "label alpha .4")
    b:Fire("OnEnter"); b:Fire("OnMouseDown")
    assert(SameRgb(p.face.tint, Theme.COLOR_BUTTON_INK), "a disabled button takes no hover or press")
""")

case("text_button_label_font_objects_are_ours_mono_and_sized_by_the_button_height", """
    local B = LoadButtonSkins()
    local small = NewButton(nil, { w = 96, h = 22, slices = true, text = "Close" })
    local big = NewButton(nil, { w = 204, h = 36, slices = true, text = "Options" })
    B.SkinTextButton(small); B.SkinTextButton(big)
    local function look(b, kind)
        local o = b["font" .. kind]
        assert(o, kind .. " font object set")
        return o
    end
    for _, kind in ipairs({ "Normal", "Highlight", "Disabled" }) do
        local o = look(small, kind)
        assert(o.font and o.font[1] == Theme.FONT_MONO and o.font[2] == 11, kind .. " is 11 pt mono")
        assert(look(big, kind).font[2] == 13, kind .. " is 13 pt on a 36 unit button")
    end
    assert(SameRgb(look(small, "Normal").textColor, Theme.COLOR_POWER), "normal: the label colour")
    assert(SameRgb(look(small, "Highlight").textColor, Mix(Theme.COLOR_POWER, { 1, 1, 1 }, 0.12)), "highlight: lifted")
    assert(Near(look(small, "Disabled").textColor[4], 0.4), "disabled: alpha .4")
    assert(look(small, "Normal").shadow == nil or look(small, "Normal").shadow[4] == 0, "no shadow")
""")

case("text_button_chamfer_follows_the_button_height", """
    local B = LoadButtonSkins()
    for _, h in ipairs({ 22, 36, 16 }) do
        local b = NewButton(nil, { w = 96, h = h, slices = true, text = "x" })
        local p = B.SkinTextButton(b)
        local ring = Theme.Cut2ButtonSet(Theme.CutSize(h))
        assert(p.ring.texture == ring, "height " .. h .. " ring " .. tostring(p.ring.texture))
    end
""")

case("text_button_never_touches_scripts_attributes_enabled_state_text_or_geometry", """
    local B = LoadButtonSkins()
    local b = NewButton(nil, { w = 96, h = 22, slices = true, text = "Log Out" })
    local click = function() end
    b.scripts.OnClick = click
    local calls = {}
    for _, m in ipairs({ "SetScript", "SetEnabled", "Enable", "Disable", "SetAttribute", "SetText", "SetSize", "SetWidth",
            "SetHeight", "SetPoint", "ClearAllPoints", "SetHitRectInsets", "SetParent", "Show", "Hide" }) do
        b[m] = function() calls[#calls + 1] = m end
    end
    B.SkinTextButton(b)
    B.SkinTextButton(b, { accent = "pink" })
    assert(#calls == 0, "forbidden writes: " .. table.concat(calls, ","))
    assert(b.scripts.OnClick == click, "the click handler is untouched")
    assert(b.text == "Log Out", "the label text is untouched")
""")

case("text_button_in_combat_on_a_protected_button_is_still_skinned_without_error", """
    local B = LoadButtonSkins()
    local b = NewButton(nil, { w = 96, h = 22, slices = true, text = "Options", protected = true })
    COMBAT = true
    local p = B.SkinTextButton(b)
    assert(p and p.face and p.ring, "chrome built")
    assert(b.Left.alpha == 0, "art held")
""")

case("text_button_skin_is_idempotent_and_a_new_accent_restyles_it_in_place", """
    local B = LoadButtonSkins()
    local b = NewButton(nil, { w = 96, h = 22, slices = true, text = "Close" })
    local p = B.SkinTextButton(b)
    local regions, hooks = #b.regions, 0
    for _, list in pairs(b.hooks) do hooks = hooks + #list end
    local again = B.SkinTextButton(b, { accent = "pink" })
    local hooks2 = 0
    for _, list in pairs(b.hooks) do hooks2 = hooks2 + #list end
    assert(again == p, "same pieces")
    assert(#b.regions == regions and hooks2 == hooks, "no second set of textures or hooks")
    assert(SameRgb(p.ring.tint, Theme.COLOR_HEALTH) and SameRgb(b.fontString.textColor, Theme.COLOR_HEALTH), "now pink")
    assert(SameRgb(b.fontNormal.textColor, Theme.COLOR_HEALTH), "the font objects follow the accent")
""")

case("text_button_without_a_label_or_not_a_button_is_handled", """
    local B = LoadButtonSkins()
    local b = NewButton(nil, { w = 40, h = 22, slices = true })
    assert(B.SkinTextButton(b), "an unlabelled button still gets its plate")
    assert(B.SkinTextButton(nil) == nil and B.SkinTextButton({}) == nil and B.SkinTextButton(7) == nil, "non-buttons")
""")

case("theme_skin_close_button_skins_the_panels_x_and_its_close_text_button_apart", """
    local B = LoadButtonSkins()
    local frame = CreateFrame("Frame", "SettingsLike")
    local x = NewButton(frame, { states = { "Normal", "Pushed", "Highlight", "Disabled" } })
    local text = NewButton(frame, { w = 96, h = 22, slices = true, states = { "Highlight" }, text = "Close" })
    frame.ClosePanelButton, frame.CloseButton = x, text
    Theme.SkinCloseButton(frame)
    assert(B.Parts(x) and #B.Parts(x).glyph == 12, "the real X got the pink X")
    local tp = B.Parts(text)
    assert(tp and #tp.glyph == 0, "the Close text button is a text button, with no X on the word")
    assert(text.Left.alpha == 0, "and its stock red art is gone")
""")


# ---------------------------------------------------------------------------
# The Game Menu
# ---------------------------------------------------------------------------

case("game_menu_hides_blizzards_gold_border_and_header_plate", """
    local menu = MakeGameMenu()
    LoadPopups()
    assert(not menu.Border.shown, "the gold inner border (an opaque dark fill) is hidden")
    assert(not menu.Header.shown, "the gold header plate and its Game Menu text are hidden")
""")

case("game_menu_gets_a_stuwave_menu_title_band_thirty_units_tall", """
    local menu = MakeGameMenu()
    LoadPopups()
    assert(menu.fsPanelTitle and menu.fsPanelTitle.text == "stuwave://menu", "title: " .. tostring(menu.fsPanelTitle and menu.fsPanelTitle.text))
    local band
    for _, t in ipairs(menu.regions) do if t.color and t.h == 30 then band = t end end
    assert(band, "a 30 unit band fills the padding Blizzard keeps for the header")
""")

case("game_menu_buttons_are_text_buttons_cyan_for_return_pink_for_log_out_and_exit_violet_for_the_rest", """
    local menu = MakeGameMenu()
    local options = menu:Add(OPTIONS_MENU)
    local logout, quit = menu:Add(LOG_OUT), menu:Add(EXIT_GAME)
    local back = menu:Add(RETURN_TO_GAME)
    LoadPopups()
    local B = FS.ButtonSkins
    assert(B.Parts(options).accent == "violet", "Options violet")
    assert(B.Parts(logout).accent == "pink" and B.Parts(quit).accent == "pink", "Log Out and Exit Game pink")
    assert(B.Parts(back).accent == "cyan", "Return to Game cyan")
    for _, b in ipairs({ options, logout, quit, back }) do
        assert(b.Left.alpha == 0 and b.Middle.alpha == 0 and b.Right.alpha == 0, "stock red art held on " .. b.text)
    end
""")

case("game_menu_skins_buttons_blizzard_adds_later_and_re_accents_a_recycled_one", """
    local menu = MakeGameMenu()
    local first = menu:Add(OPTIONS_MENU)
    local late
    -- what Blizzard's InitButtons does on every show: the pool hands the same button a new label and a new one appears
    menu.InitButtons = function(self)
        first.text = EXIT_GAME
        first.fontString:SetText(EXIT_GAME)
        if not late then late = self:Add(RETURN_TO_GAME) end
    end
    LoadPopups()
    local B = FS.ButtonSkins
    assert(B.Parts(first).accent == "violet", "skinned as Options first")
    menu:InitButtons()
    assert(B.Parts(late) and B.Parts(late).accent == "cyan", "the new button was skinned by the InitButtons hook")
    assert(B.Parts(first).accent == "pink", "the recycled button took the new label's accent")
    local regions = #first.regions
    menu:InitButtons()
    assert(#first.regions == regions, "no second set of textures on a recycled button")
""")

case("game_menu_buttons_keep_their_scripts_attributes_anchors_and_text", """
    local menu = MakeGameMenu()
    local logout = menu:Add(LOG_OUT)
    local click = function() end
    logout.scripts.OnClick = click
    local calls = {}
    for _, m in ipairs({ "SetScript", "SetAttribute", "SetEnabled", "SetText", "SetPoint", "ClearAllPoints", "SetSize", "SetWidth", "SetHeight" }) do
        logout[m] = function() calls[#calls + 1] = m end
    end
    LoadPopups()
    assert(#calls == 0, "the Game Menu skin wrote through: " .. table.concat(calls, ","))
    assert(logout.scripts.OnClick == click and logout.text == LOG_OUT, "click handler and label untouched")
""")

case("game_menu_falls_back_to_the_named_menu_buttons_when_there_is_no_button_pool", """
    local menu = MakeGameMenu()
    menu.buttonPool = nil
    local logout = NewButton(menu, { w = 200, h = 24, slices = true, text = "Log Out" })
    _G.GameMenuButtonLogout = logout
    local cont = NewButton(menu, { w = 200, h = 24, slices = true, text = "Return to Game" })
    _G.GameMenuButtonContinue = cont
    LoadPopups()
    local B = FS.ButtonSkins
    assert(B.Parts(logout).accent == "pink" and B.Parts(cont).accent == "cyan", "by name: Log Out pink, Continue cyan")
""")


# ---------------------------------------------------------------------------
# Wiring: dialogs and panels
# ---------------------------------------------------------------------------

case("static_popup_buttons_are_text_buttons_and_its_close_is_the_pink_x", """
    local pop = CreateFrame("Frame", "StaticPopup1")
    pop.w, pop.h = 320, 140
    local accept, cancel = StockText(pop, "Accept", 128, 32), StockText(pop, "Cancel", 128, 32)
    _G.StaticPopup1Button1, _G.StaticPopup1Button2 = accept, cancel
    local x = NewButton(pop, { states = { "Normal", "Pushed", "Highlight", "Disabled" } })
    _G.StaticPopup1CloseButton = x
    LoadPopups()
    assert(Skinned(accept, "Accept").accent == "violet" and Skinned(cancel, "Cancel").accent == "violet", "Accept and Cancel are violet text buttons")
    assert(accept.Left.alpha == 0 and cancel.Middle.alpha == 0, "stock red art held")
    assert(#Skinned(x, "the popup X").glyph == 12, "the popup's X is the pink X")
""")

case("settings_panel_x_close_apply_and_defaults_are_each_the_right_kind_of_button", """
    local panel = CreateFrame("Frame", "SettingsPanel")
    panel.w, panel.h = 920, 724
    local x = NewButton(panel, { states = { "Normal", "Pushed", "Highlight", "Disabled" } })
    local close, apply = StockText(panel, "Close"), StockText(panel, "Apply")
    local defaults = StockText(panel, "Defaults")
    panel.ClosePanelButton, panel.CloseButton, panel.ApplyButton = x, close, apply
    panel.Container = { SettingsList = { Header = { DefaultsButton = defaults } } }
    LoadPanels()
    assert(#Skinned(x, "ClosePanelButton").glyph == 12, "the real X, ClosePanelButton, is the pink X")
    local c = Skinned(close, "the bottom Close")
    assert(#c.glyph == 0 and c.accent == "violet", "the bottom Close is a text button with no X on it")
    assert(Skinned(apply, "Apply").accent == "violet", "Apply is a violet text button")
    assert(Skinned(defaults, "Defaults").accent == "pink", "Defaults, which resets everything, is pink")
    for _, b in ipairs({ close, apply, defaults }) do assert(b.Left.alpha == 0, "stock red art held on " .. b.text) end
""")

case("settings_panel_buttons_that_are_not_there_yet_are_skipped_and_picked_up_on_a_later_scan", """
    local panel = CreateFrame("Frame", "SettingsPanel")
    panel.w, panel.h = 920, 724
    LoadPanels()                                     -- no Apply, no Defaults yet
    local apply = StockText(panel, "Apply")
    panel.ApplyButton = apply
    -- a later scan (ADDON_LOADED) runs the same pass again
    for _, w in ipairs(ALL_WATCHERS) do if w.scripts.OnEvent then w.scripts.OnEvent(w, "PLAYER_ENTERING_WORLD") end end
    Skinned(apply, "Apply (picked up by the next scan)")
""")

case("gossip_goodbye_and_trainer_train_are_text_buttons", """
    local gossip = CreateFrame("Frame", "GossipFrame")
    gossip.GreetingPanel = { GoodbyeButton = StockText(gossip, "Goodbye", 128, 22) }
    local train = StockText(CreateFrame("Frame", "ClassTrainerFrame"), "Train", 80, 22)
    _G.ClassTrainerTrainButton = train
    LoadPanels()
    assert(Skinned(gossip.GreetingPanel.GoodbyeButton, "Goodbye").accent == "violet", "Goodbye is violet")
    assert(Skinned(train, "Train").accent == "violet", "Train is violet")
    assert(train.Left.alpha == 0, "stock art held")
""")


MOCK_HELPERS = r"""
function new_texture() return CreateFrame("Frame"):CreateTexture(nil, "BACKGROUND") end
function new_fontstring() return CreateFrame("Frame"):CreateFontString(nil, "OVERLAY") end
"""


def run_case(name: str, body: str) -> str | None:
    """Return None on pass, or the failure text."""
    rt = LuaRuntime(unpack_returned_tuples=False)
    g = rt.globals()
    g.THEME_SRC = THEME_SRC
    g.HELDART_SRC = HELDART_SRC
    g.BUTTONSKINS_SRC = BUTTONSKINS_SRC
    g.PANELSKINS_SRC = PANELSKINS_SRC
    g.POPUPS_SRC = POPUPS_SRC
    g.PANELS_SRC = PANELS_SRC
    try:
        rt.execute(MOCK)
        rt.execute(MOCK_HELPERS)
        rt.execute("local function main()\n" + body + "\nend\nmain()")
    except (LuaError, AssertionError) as exc:
        return str(exc)
    return None


def main() -> int:
    failures = 0
    for name, body in CASES:
        err = run_case(name, body)
        if err is None:
            print(f"ok    {name}")
        else:
            failures += 1
            print(f"FAIL  {name}: {err}")
    print(f"{len(CASES) - failures}/{len(CASES)} checks passed")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
