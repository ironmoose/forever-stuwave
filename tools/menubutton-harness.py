#!/usr/bin/env python3
"""The Forever STUwave plate under the Game Menu (Modules/Config/MenuButton.lua) against the real Lua.

  * nothing is built until the menu first shows, and a second show builds nothing more;
  * the plate is our own button parented to GameMenuFrame and docked under its bottom edge, full width;
  * it is skinned as the cyan STUwave text button, titled in the display font, with the emblem on the left;
  * a click closes the menu and opens the config window;
  * the menu's own buttons are never touched.

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
__frames, __opened, __hidden, __skins, __sounds = {}, 0, 0, {}, 0
local Obj = {}; Obj.__index = Obj
function New(kind, parent, name)
    local o = setmetatable({ kind = kind, parent = parent, name = name, points = {}, scripts = {}, hooks = {}, shown = true }, Obj)
    __frames[#__frames + 1] = o
    return o
end
function Obj:SetPoint(...) self.points[#self.points + 1] = { ... } end
function Obj:ClearAllPoints() self.points = {} end
function Obj:SetHeight(h) self.h = h end
function Obj:SetSize(w, h) self.w, self.h = w, h end
function Obj:SetText(t) self.text = t end
function Obj:GetText() return self.text end
function Obj:RegisterForClicks(...) self.clicks = { ... } end
function Obj:SetScript(n, fn) self.scripts[n] = fn end
function Obj:HookScript(n, fn) self.hooks[n] = self.hooks[n] or {}; table.insert(self.hooks[n], fn) end
function Obj:IsShown() return self.shown end
function Obj:Hide() self.shown = false end
function Obj:Show() self.shown = true; for _, fn in ipairs(self.hooks.OnShow or {}) do fn(self) end end
function Obj:SetNormalFontObject(f) self.normalFont = f end
function Obj:SetHighlightFontObject(f) self.highlightFont = f end
function Obj:SetDisabledFontObject(f) self.disabledFont = f end
function Obj:CreateTexture(_, layer) local t = New("Texture", self); t.layer = layer; return t end
function Obj:SetTexture(p) self.tex = p end
function Obj:SetTextureFilter(f) self.filter = f end
function Obj:GetFontString() if not self.fs then self.fs = New("FontString", self) end return self.fs end
function Obj:SetFont(path, size, flags) self.font = { path, size, flags }; return true end
function Obj:SetShadowColor(...) self.shadow = { ... } end
function Obj:SetShadowOffset(...) self.shadowOffset = { ... } end
function CreateFrame(kind, name, parent) local f = New(kind, parent, name); if name then _G[name] = f end return f end
function CreateFont(name) local f = New("Font", nil, name); _G[name] = f; return f end
function HideUIPanel(f) __hidden = __hidden + 1; f:Hide() end
function PlaySound() __sounds = __sounds + 1 end
SOUNDKIT = { IG_MAINMENU_OPTION = 1 }
STANDARD_TEXT_FONT = "Fonts\\FRIZQT__.TTF"
GameMenuFrame = New("Frame", nil, "GameMenuFrame"); GameMenuFrame.shown = false
GameMenuButtonLogout = New("Button", GameMenuFrame, "GameMenuButtonLogout")
FS = {
    Theme = { FONT_ORBITRON = "Interface\\AddOns\\forever-stuwave\\Media\\Fonts\\FSDisplay-Bold.ttf" },
    ConfigWindow = { Open = function() __opened = __opened + 1 end },
    ButtonSkins = { SkinTextButton = function(b, opts) __skins[#__skins + 1] = { b = b, opts = opts } end },
    LogDegradeOnce = function(k, m) error("logged " .. k .. ": " .. tostring(m)) end,
}
"""

CHECKS = r"""
local function check(ok, msg) if not ok then error(msg, 2) end end
check(_G.ForeverSTUwaveMenuButton == nil, "nothing is built before the menu shows")
GameMenuFrame:Show()
local b = _G.ForeverSTUwaveMenuButton
check(b ~= nil and b.parent == GameMenuFrame, "the plate is ours, on the menu")
GameMenuFrame:Show()
local buttons = 0
for _, f in ipairs(__frames) do if f.kind == "Button" and f.name == "ForeverSTUwaveMenuButton" then buttons = buttons + 1 end end
check(buttons == 1 and #__skins == 1, "a second show builds nothing more")
local p1, p2 = b.points[1], b.points[2]
check(p1[1] == "TOPLEFT" and p1[2] == GameMenuFrame and p1[3] == "BOTTOMLEFT" and p1[5] < 0, "docked under the menu's left edge")
check(p2[1] == "TOPRIGHT" and p2[2] == GameMenuFrame and p2[3] == "BOTTOMRIGHT", "and its right edge")
check(__skins[1].b == b and __skins[1].opts.accent == "cyan", "skinned as the cyan STUwave text button")
check(b.text == "FOREVER STUWAVE", "titled")
local f = b.normalFont
check(f and f == b.highlightFont and f == b.disabledFont, "one font object for every state")
check(f.font[1]:find("FSDisplay", 1, true) ~= nil, "in the display font")
check(f.shadow[1] == 1 and f.shadowOffset[1] == 1, "with the pink drop shadow")
local icon
for _, t in ipairs(__frames) do if t.kind == "Texture" and t.parent == b then icon = t end end
check(icon and icon.tex:find("addon_icon", 1, true), "the emblem")
check(icon.points[1][1] == "LEFT", "on the left")
check(b.fs.points[1][4] > 0, "the title sits right of centre, clear of the emblem")
b.scripts.OnClick(b, "LeftButton")
check(__hidden == 1 and not GameMenuFrame.shown, "a click closes the menu")
check(__opened == 1 and __sounds == 1, "and opens the config window")
check(next(GameMenuButtonLogout.points) == nil and GameMenuButtonLogout.parent == GameMenuFrame, "the menu's own buttons are untouched")
return "ok"
"""


def main() -> int:
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STUBS)
    loader = lua.eval("function(src) local f = assert((loadstring or load)(src, '@MenuButton.lua')); f('forever-stuwave', FS) end")
    try:
        loader(SRC)
        lua.execute(CHECKS)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL  {e}")
        print("0/1 checks passed")
        return 1
    print("ok    the_menu_plate_docks_skins_and_opens_the_config")
    print("1/1 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
