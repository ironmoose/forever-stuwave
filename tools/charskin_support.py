"""Shared mock for the Character, Reputation, Currency, Spellbook, Talents and Inspect skin harnesses.

The widget engine (real anchor solver, hooksecurefunc, SetScript / SetAttribute that throw on a Blizzard widget) and the
measuring and render-op helpers are lifted from mailskin-harness.py, so every harness reads rectangles in physical pixels
the same way. This file adds the Lua that loads the real addon files, a stock CharacterFrame built from the 16001 globals
dump names (and the retail 12.1.0 Blizzard_UIPanels_Game source for the structure behind them), the API mocks the skins read,
and a PNG renderer. The mock is NOT the real client.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

try:
    from lupa.luajit21 import LuaError, LuaRuntime
except ImportError:
    sys.exit("lupa is missing; see parse-gate.py for the venv recipe.")

HERE = Path(__file__).resolve().parent
ADDON = HERE.parent / "forever-stuwave"
FONT = ADDON / "Media/Fonts/MononokiNerdFontMono-Bold.ttf"

_spec = importlib.util.spec_from_file_location("mailskin_harness", HERE / "mailskin-harness.py")
_mail = importlib.util.module_from_spec(_spec)
sys.modules["mailskin_harness"] = _mail
_spec.loader.exec_module(_mail)

_MOCK = _mail.MOCK
_BLIZ = _MOCK.index("-------------------------------------------------------------------------------\n-- Blizzard's mailbox")
_MEAS = _MOCK.index("-------------------------------------------------------------------------------\n-- Measuring")
ENGINE = _MOCK[:_BLIZ]
MEASURE = _MOCK[_MEAS:]

CORE = ["Core/Theme.lua", "Core/Layout.lua", "Core/HeldArt.lua", "Core/PanelSkins.lua", "Core/ControlKit.lua",
        "Core/ItemSlotSkins.lua", "Core/TabSkins.lua"]


def read(path: str) -> str:
    return (ADDON / path).read_text(encoding="utf-8")


GLUE = r"""
SlashCmdList = SlashCmdList or {}
UISpecialFrames = {}
GameTooltip = GameTooltip or nil
function GetTime() return 100 end

local function blz(kind, name, parent, w, h, point, x, y)
    local o = adopt(parent, new(kind, name, parent, true))
    o.w, o.h = w or 0, h or 0
    o.points[1] = { point = point or "TOPLEFT", rel = parent, relPoint = point or "TOPLEFT", x = x or 0, y = y or 0 }
    return o
end
local function tex(parent, name, layer)
    local t = adopt(parent, new("Texture", name, parent, true))
    t.layer = layer or "BACKGROUND"
    t.path = "Interface\\stock\\art"
    return t
end
local function fstring(parent, name, text, size, color)
    local f = adopt(parent, new("FontString", name, parent, true))
    f.fontPath, f.size, f.text = "stock.ttf", size or 12, text or ""
    f.textColor = color or { 1, 0.82, 0, 1 }
    f.points[1] = { point = "TOPLEFT", rel = parent, relPoint = "TOPLEFT", x = 0, y = 0 }
    function f:SetTextColor(r, g, b, a) self.textColor = { r, g, b, a or 1 } end
    return f
end
BLZ = { blz = blz, tex = tex, fstring = fstring }

function Load(files)
    FS = { LogDegradeOnce = function(key, msg) DEGRADED[#DEGRADED + 1] = key .. " :: " .. tostring(msg) end }
    FS.IsSecret = function(v) return type(v) == "table" and v.__secret == true end
    FS.FrameHelpers = { PixelsPerUnit = function() return PPU end }
    for _, name in ipairs(files) do
        local chunk, err = load(SOURCES[name], "=" .. name)
        if not chunk then error(err) end
        chunk("forever-stuwave", FS)
    end
    return FS
end
function Reset()
    for i = #ALL, 2, -1 do ALL[i] = nil end
    TIMERS = {}
    DEGRADED = {}
    __combat = false
    PPU = 1.2
    UIParent.children, UIParent.regions = {}, {}
    BuildBlizzard()
end
function Secret() return { __secret = true } end
"""

# ---------------------------------------------------------------------------------------------------------------------
# A stock CharacterFrame (ButtonFrameTemplate, Tab1..3, the paper doll slots, the stats pane) with the three sub frames.
# ---------------------------------------------------------------------------------------------------------------------
CHARACTER_LUA = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring

SLOTS = { "Head", "Neck", "Shoulder", "Back", "Chest", "Shirt", "Tabard", "Wrist", "Hands", "Waist", "Legs", "Feet",
          "Finger0", "Finger1", "Trinket0", "Trinket1", "MainHand", "SecondaryHand", "Ranged" }
SLOT_IDS = { Head = 1, Neck = 2, Shoulder = 3, Shirt = 4, Chest = 5, Waist = 6, Legs = 7, Feet = 8, Wrist = 9, Hands = 10,
    Finger0 = 11, Finger1 = 12, Trinket0 = 13, Trinket1 = 14, Back = 15, MainHand = 16, SecondaryHand = 17, Ranged = 18, Tabard = 19 }
-- slot id -> { quality, durability current, max }
GEAR = {
    [1] = { 3, 72, 100 }, [2] = { 2 }, [3] = { 4, 34, 100 }, [15] = { 2, 100, 100 }, [5] = { 3, 12, 100 }, [4] = { 1 },
    [9] = { 1, 100, 100 }, [10] = { 2, 100, 100 }, [6] = { 3, 100, 100 }, [7] = { 2, 0, 100 }, [8] = { 5, 100, 100 },
    [11] = { 3 }, [12] = { 2 }, [13] = { 4 }, [16] = { 3, 45, 100 }, [17] = { 1, 100, 100 },
}
REPAIR = { [1] = 5200, [3] = 14100, [5] = 3300, [7] = 4200, [16] = 1200 }
function GetInventoryItemQuality(unit, id) local g = GEAR[id]; return g and g[1] end
function GetInventoryItemTexture(unit, id) return GEAR[id] and "Interface\\Icons\\inv_" .. id or nil end
function GetInventoryItemDurability(id) local g = GEAR[id]; if g and g[2] then return g[2], g[3] end end
function GetAverageItemLevel() return 14.4, 14.2, 14.2 end
C_TooltipInfo = { GetInventoryItem = function(unit, id) return { repairCost = REPAIR[id] } end }

function BuildBlizzard()
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^Character") or k:find("^PaperDoll") or k:find("^Reputation") or k:find("^Token")) then _G[k] = nil end
    end
    local win = blz("Frame", "CharacterFrame", UIParent, 540, 480)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 250, y = -100 }
    win.shown = false
    win.Bg = tex(win, nil, "BACKGROUND")
    win.NineSlice = blz("Frame", nil, win, 540, 480)
    win.TitleContainer = blz("Frame", nil, win, 400, 24)
    tex(win, "CharacterFramePortrait", "ARTWORK")
    fstring(win, "CharacterFrameTitleText", "Stu")
    win.Inset = blz("Frame", nil, win, 330, 380)
    win.Inset.Bg = tex(win.Inset, nil, "BACKGROUND")
    win.InsetRight = blz("Frame", nil, win, 190, 380)
    win.InsetRight.points[1] = { point = "TOPLEFT", rel = win, relPoint = "TOPLEFT", x = 340, y = -62 }
    local close = blz("Button", "CharacterFrameCloseButton", win, 24, 24, "TOPRIGHT")
    tex(close, nil, "BACKGROUND")
    win.CloseButton = close
    fstring(win, "CharacterLevelText", "Level 12 Tauren Shaman", 12, { 1, 1, 1, 1 })
    tex(win, "CharacterLevelTextBackground", "BACKGROUND")
    for _, n in ipairs({ "TopLeft", "TopRight", "BotLeft", "BotRight" }) do tex(win, "CharacterModelFrameBackground" .. n, "BACKGROUND") end

    local pd = blz("Frame", "PaperDollFrame", win, 540, 480)
    pd.id = 1
    pd.Bg = tex(pd, nil, "BACKGROUND")
    local rep = blz("Frame", "ReputationFrame", win, 540, 480); rep.shown = false; rep.id = 2
    local tok = blz("Frame", "TokenFrame", win, 540, 480); tok.shown = false; tok.id = 3
    local pages = { pd, rep, tok }
    local function select(i)
        for j, f in ipairs(pages) do if j == i then f:Show() else f:Hide() end end
    end
    for i = 1, 3 do
        local tab = blz("Button", "CharacterFrameTab" .. i, win, 90, 32, "BOTTOMLEFT", 11 + (i - 1) * 91, 2)
        tab.Left, tab.Middle, tab.Right = tex(tab, nil, "BACKGROUND"), tex(tab, nil, "BACKGROUND"), tex(tab, nil, "BACKGROUND")
        tab.fs = fstring(tab, "CharacterFrameTab" .. i .. "Text", ({ "Character", "Rep", "Currency" })[i])
        tab.scripts.OnClick = function() select(i) end
        if i == 3 then tab.shown = true end
    end
    CharacterFrameTab3.shown = true
    ToggleCharacter = function(name, onlyShow) for i, f in ipairs(pages) do if f:GetName() == name then select(i) end end end

    local function slot(name, x, y)
        local b = blz("Button", "Character" .. name .. "Slot", pd, 37, 37, "TOPLEFT", x, y)
        b.id = SLOT_IDS[name]
        b.NormalTexture = tex(b, "Character" .. name .. "SlotNormalTexture", "ARTWORK")
        b.icon = tex(b, "Character" .. name .. "SlotIconTexture", "BORDER")
        b.icon.path = GEAR[b.id] and ("Interface\\Icons\\inv_" .. b.id) or "Interface\\PaperDoll\\UI-PaperDoll-Slot-" .. name
        b.IconBorder = tex(b, nil, "OVERLAY")
        b.Count = fstring(b, "Character" .. name .. "SlotCount", "", 12)
        b.pushedTex = tex(b, nil, "HIGHLIGHT")
        b.GetID = function(self) return self.id end
        return b
    end
    local left = { "Head", "Neck", "Shoulder", "Back", "Chest", "Shirt", "Tabard", "Wrist" }
    local right = { "Hands", "Waist", "Legs", "Feet", "Finger0", "Finger1", "Trinket0", "Trinket1" }
    for i, n in ipairs(left) do slot(n, 14, -(70 + (i - 1) * 41)) end
    for i, n in ipairs(right) do slot(n, 290, -(70 + (i - 1) * 41)) end
    slot("MainHand", 110, -410); slot("SecondaryHand", 150, -410); slot("Ranged", 190, -410)

    local pane = blz("Frame", "CharacterStatsPane", pd, 190, 380, "TOPLEFT", 342, -64)
    pane.ClassBackground = tex(pane, nil, "BACKGROUND")
    pane.ItemLevelFrame = blz("Frame", nil, pane, 187, 29)
    pane.ItemLevelFrame.Value = fstring(pane.ItemLevelFrame, nil, "14", 15, { 1, 1, 1, 1 })
    local y = 40
    local function category(title)
        local f = blz("Frame", nil, pane, 197, 40, "TOPLEFT", 0, -y)
        tex(f, nil, "BACKGROUND")
        f.Title = fstring(f, nil, title, 12, { 1, 1, 1, 1 })
        y = y + 34
    end
    local function stat(label, value)
        local f = blz("Frame", nil, pane, 187, 15, "TOPLEFT", 0, -y)
        f.Background = tex(f, nil, "BACKGROUND")
        f.Label = fstring(f, nil, label, 11, { 1, 0.82, 0, 1 })
        f.Value = fstring(f, nil, value, 11, { 1, 1, 1, 1 })
        f.Value.points[1] = { point = "RIGHT", rel = f, relPoint = "RIGHT", x = -8, y = 0 }
        f.Value.justify = "RIGHT"
        f.Label.points[1] = { point = "LEFT", rel = f, relPoint = "LEFT", x = 11, y = 0 }
        f.scripts.OnEnter = function() end
        y = y + 20
    end
    category("Attributes")
    for _, s in ipairs({ { "Strength", "74" }, { "Agility", "41" }, { "Stamina", "63" }, { "Intellect", "52" }, { "Spirit", "58" } }) do stat(s[1], s[2]) end
    category("Enhancements")
    for _, s in ipairs({ { "Attack Power", "122" }, { "Crit", "5.2%" }, { "Haste", "2.1%" } }) do stat(s[1], s[2]) end
    PaperDollFrame_UpdateStats = function() end
    pd:Show()
    win.fsOnShowHooks = nil
end

CLASS_SOURCES = { "Theme", "Layout", "HeldArt", "PanelSkins", "ControlKit", "ItemSlotSkins", "TabSkins" }
"""

LOAD_ALL = "local FS = Load({ 'Theme', 'Layout', 'HeldArt', 'PanelSkins', 'ControlKit', 'ItemSlotSkins', 'TabSkins' %s })"


class Harness:
    def __init__(self, extra: dict[str, str], blizzard_lua: str = "", sources_extra: dict[str, str] | None = None):
        self.sources = {Path(p).stem: read(p) for p in CORE}
        for name, path in extra.items():
            self.sources[name] = read(path)
        self.extra_names = list(extra)
        self.blizzard_lua = blizzard_lua
        self.cases: list[tuple[str, str]] = []

    def case(self, name: str, body: str) -> None:
        self.cases.append((name, body))

    def runtime(self):
        rt = LuaRuntime(unpack_returned_tuples=False)
        rt.globals()["SOURCES_PY"] = rt.table_from(self.sources)
        rt.execute("SOURCES = SOURCES_PY")
        # one chunk: the engine's locals (new, adopt, ALL, TIMERS) are shared by everything after it
        rt.execute("\n".join([ENGINE, GLUE, CHARACTER_LUA, self.blizzard_lua, MEASURE, "BuildBlizzard()"]))
        return rt

    def load_line(self) -> str:
        extra = "".join(f", '{n}'" for n in self.extra_names)
        return LOAD_ALL % extra

    def run_case(self, body: str):
        rt = self.runtime()
        try:
            rt.execute(self.load_line() + "\nlocal function main()\n" + body + "\nend\nreturn main()")
        except LuaError as exc:
            return str(exc)
        return None

    def main(self, label: str, scenes: dict[str, str]) -> int:
        png = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None
        failures = 0
        for name, body in self.cases:
            err = self.run_case(body)
            if err is None:
                print(f"ok    {name}")
            else:
                failures += 1
                print(f"FAIL  {name}: {err}")
        print(f"{len(self.cases) - failures}/{len(self.cases)} {label} checks passed")
        if png:
            self.render(png, scenes)
        return int(failures > 0)

    def render(self, prefix: str, scenes: dict[str, str]) -> None:
        from PIL import Image, ImageDraw, ImageFont

        for scene, code in scenes.items():
            rt = self.runtime()
            ops = rt.execute(self.load_line() + "\nlocal function main()\n" + code + "\nend\nreturn main()")
            flat = []
            for i in range(1, len(ops) + 1):
                op = ops[i]
                flat.append({k: (dict((j, v[j]) for j in range(1, len(v) + 1)) if hasattr(v, "__len__") and not isinstance(v, str) else v)
                             for k, v in dict(op.items()).items()})
            xs = [o["l"] for o in flat] + [o["r"] for o in flat]
            ys = [o["t"] for o in flat] + [o["b"] for o in flat]
            pad = 24
            ox, oy = min(xs) - pad, min(ys) - pad
            W, H = int(max(xs) - ox + pad), int(max(ys) - oy + pad)
            img = Image.new("RGBA", (W, H), (11, 6, 24, 255))
            fonts: dict[int, ImageFont.FreeTypeFont] = {}
            for op in flat:
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                d = ImageDraw.Draw(layer)
                rgba = op["rgba"]
                col = tuple(int(max(0, min(1, rgba[k])) * 255 + 0.5) for k in (1, 2, 3)) + (int(max(0, min(1, rgba[4])) * 255 + 0.5),)
                l, t, r, b = (round(op["l"] - ox), round(op["t"] - oy), round(op["r"] - ox), round(op["b"] - oy))
                kind = op["kind"]
                if kind == "text":
                    size = max(6, round(op["size"]))
                    font = fonts.setdefault(size, ImageFont.truetype(str(FONT), size))
                    text = re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", op["text"])
                    total = font.getlength(text)
                    x = l if op["justify"] == "LEFT" else (r - total if op["justify"] == "RIGHT" else (l + r) / 2 - total / 2)
                    d.text((x, (t + b) / 2), text, font=font, fill=col, anchor="lm")
                else:
                    c = max(0, min(int(op.get("c", 0)), (b - t) // 2))
                    pts = [(l + c, t), (r - 1, t), (r - 1, b - 1 - c), (r - 1 - c, b - 1), (l, b - 1), (l, t + c)]
                    if kind == "flat":
                        d.rectangle([l, t, r - 1, b - 1], fill=col)
                    elif kind == "fill":
                        d.polygon(pts, fill=col)
                    elif kind == "ring":
                        d.line(pts + [pts[0]], fill=col, width=1)
                img = Image.alpha_composite(img, layer)
            out = f"{prefix}-{scene}.png"
            img.convert("RGB").save(out)
            print("wrote", out)
