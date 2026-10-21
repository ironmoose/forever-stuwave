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
function Obj:SetShadowColor() end
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

function CreateFrame(kind, name, parent)
    local f = new("Frame", parent)
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

function Near(a, b, eps) return math.abs(a - b) <= (eps or 1e-6) end
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
