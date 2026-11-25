#!/usr/bin/env python3
"""The Forever STUwave button in the Game Menu (Modules/Config/MenuButton.lua) against the real Lua.

  * it is our own button, a child of the menu, built on the first open and placed again on every open;
  * its layoutIndex puts it right above AddOns (else Log Out), carrying that row's section gap;
  * it is the cyan STUwave text button in the display font, with the emblem on the left; a face that did not
    take is logged (font objects' SetFont returns nothing, so it is read back);
  * a click closes the menu and opens the config window; the menu's own rows are never anchored or scripted.

    python3 tools/menubutton-harness.py

Exit 0 = every check passed. Rendering still needs an in-game look.
"""
from __future__ import annotations

import sys
from pathlib import Path

from lupa import LuaRuntime

HERE = Path(__file__).resolve().parent
SRC = (HERE.parent / "forever-stuwave/Modules/Config/MenuButton.lua").read_text(encoding="utf-8")

STUBS = r"""
__frames, __opened, __hidden, __skins, __sounds, __dirty = {}, 0, 0, {}, 0, 0
local Obj = {}; Obj.__index = Obj
function New(kind, parent, name)
    local o = setmetatable({ kind = kind, parent = parent, name = name, points = {}, scripts = {}, hooks = {}, shown = true }, Obj)
    __frames[#__frames + 1] = o
    return o
end
function Obj:SetPoint(...) self.points[#self.points + 1] = { ... } end
function Obj:ClearAllPoints() self.points = {} end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:GetSize() return self.w, self.h end
function Obj:SetText(t) self.text = t end
function Obj:GetText() return self.text end
function Obj:RegisterForClicks(...) self.clicks = { ... } end
function Obj:SetScript(n, fn) self.scripts[n] = fn; self.scriptWrites = (self.scriptWrites or 0) + 1 end
function Obj:IsShown() return self.shown end
function Obj:Hide() self.shown = false end
function Obj:Show() self.shown = true end
function Obj:SetNormalFontObject(f) self.normalFont = f end
function Obj:SetHighlightFontObject(f) self.highlightFont = f end
function Obj:SetDisabledFontObject(f) self.disabledFont = f end
function Obj:CreateTexture(_, layer) local t = New("Texture", self); t.layer = layer; return t end
function Obj:SetTexture(p) self.tex = p end
function Obj:SetFont(path, size, flags) if __fontOk then self.font = { path, size, flags } end end
function Obj:GetFont() return self.font and self.font[1] end
function Obj:SetShadowColor(...) self.shadow = { ... } end
function Obj:SetShadowOffset(...) self.shadowOffset = { ... } end
function CreateFrame(kind, name, parent) local f = New(kind, parent, name); if name then _G[name] = f end return f end
function CreateFont(name) local f = New("Font", nil, name); _G[name] = f; return f end
function HideUIPanel(f) __hidden = __hidden + 1; f:Hide() end
function PlaySound() __sounds = __sounds + 1 end
function hooksecurefunc(t, k, fn) local orig = t[k]; t[k] = function(...) local r = orig(...); fn(...); return r end end
__fontOk = true
SOUNDKIT = { IG_MAINMENU_OPTION = 1 }
STANDARD_TEXT_FONT = "Fonts\\FRIZQT__.TTF"
ADDONS = "AddOns"
GameMenuFrame = New("Frame", nil, "GameMenuFrame"); GameMenuFrame.shown = false
local rows = {}
GameMenuFrame.buttonPool = { EnumerateActive = function() local i = 0; return function() i = i + 1; return rows[i] end end }
function GameMenuFrame:GetLogoutText() return "Log Out" end
function GameMenuFrame:MarkDirty() __dirty = __dirty + 1 end
__withAddOns = true
function GameMenuFrame:InitButtons()
    for k in pairs(rows) do rows[k] = nil end
    local list = { { "Options" }, { "Shop" }, { "AddOns", 20 }, { "Edit Mode" }, { "Log Out", 20 }, { "Exit Game" } }
    for i, r in ipairs(list) do
        if __withAddOns or r[1] ~= "AddOns" then
            local b = New("Button", self); b.text, b.layoutIndex, b.topPadding, b.w, b.h = r[1], i, r[2], 200, 30
            rows[#rows + 1] = b
        end
    end
end
function Row(text) for _, b in ipairs(rows) do if b.text == text then return b end end end
FS = {
    Theme = { FONT_ORBITRON = "Interface\\AddOns\\forever-stuwave\\Media\\Fonts\\FSDisplay-Bold.ttf" },
    ConfigWindow = { Open = function() __opened = __opened + 1 end },
    ButtonSkins = { SkinTextButton = function(b, opts) __skins[#__skins + 1] = { b = b, opts = opts } end },
    LogDegradeOnce = function(k, m) error("logged " .. k .. ": " .. tostring(m)) end,
}
"""

CHECKS = r"""
local function check(ok, msg) if not ok then error(msg, 2) end end
check(_G.ForeverSTUwaveMenuButton == nil, "nothing is built before the menu opens")
GameMenuFrame:InitButtons()
local b = _G.ForeverSTUwaveMenuButton
check(b ~= nil and b.parent == GameMenuFrame and b.shown, "our own button, a child of the menu")
local addons = Row("AddOns")
check(b.layoutIndex == addons.layoutIndex - 0.5, "laid out right above AddOns")
check(b.topPadding == 20 and addons.topPadding == nil, "the section gap moves above ours")
check(b.w == 200 and b.h == 30 and __dirty == 1, "the rows' size, and the menu lays out again")
GameMenuFrame:InitButtons()
local n = 0
for _, f in ipairs(__frames) do if f.name == "ForeverSTUwaveMenuButton" then n = n + 1 end end
check(n == 1 and #__skins == 1, "a second open builds nothing more")
check(b.layoutIndex == Row("AddOns").layoutIndex - 0.5, "and places it again")
check(__skins[1].b == b and __skins[1].opts.accent == "cyan", "skinned as the cyan STUwave text button")
local f = b.normalFont
check(f and f == b.highlightFont and f == b.disabledFont, "one font object for every state")
check(f.font[1]:find("FSDisplay", 1, true) ~= nil, "in the display font")
check(f.shadow[1] == 1 and f.shadowOffset[1] == 1, "with the pink drop shadow")
local icon
for _, t in ipairs(__frames) do if t.kind == "Texture" and t.parent == b then icon = t end end
check(icon and icon.tex:find("addon_icon", 1, true) and icon.points[1][1] == "LEFT", "the emblem on the left")
for _, r in ipairs({ Row("Options"), Row("Log Out") }) do
    check(next(r.points) == nil and not r.scriptWrites, "the menu's own rows are not anchored or scripted")
end
__withAddOns = false
GameMenuFrame:InitButtons()
check(b.layoutIndex == Row("Log Out").layoutIndex - 0.5 and b.shown, "without AddOns it sits above Log Out")
GameMenuFrame.shown = true
b.scripts.OnClick(b, "LeftButton")
check(__hidden == 1 and not GameMenuFrame.shown and __opened == 1, "a click closes the menu and opens the config")
return "ok"
"""

FONT_FAIL = r"""
__fontOk = false
GameMenuFrame:InitButtons()
"""


def main() -> int:
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STUBS)
    loader = lua.eval("function(src) local f = assert((loadstring or load)(src, '@MenuButton.lua')); f('forever-stuwave', FS) end")
    try:
        loader(SRC)
        lua.execute(CHECKS)
        bad = LuaRuntime(unpack_returned_tuples=True)
        bad.execute(STUBS)
        bad.execute("FS.LogDegradeOnce = function(k, m) __logged = k end")
        bad.eval("function(src) local f = assert((loadstring or load)(src, '@MenuButton.lua')); f('forever-stuwave', FS) end")(SRC)
        bad.execute(FONT_FAIL)
        assert bad.eval("__logged") == "menubutton_font", "a face that did not take is logged"
    except Exception as e:  # noqa: BLE001
        print(f"FAIL  {e}")
        print("0/1 checks passed")
        return 1
    print("ok    the_menu_button_sits_above_addons_and_opens_the_config")
    print("1/1 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
