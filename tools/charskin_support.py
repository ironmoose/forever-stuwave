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
    function f:GetTextColor() return unpack(self.textColor) end
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
function Obj:GetLeft() local l = self:Rect(); return l end
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
        if type(k) == "string" and (k:find("^Character") or k:find("^PaperDoll") or k:find("^Reputation") or k:find("^Token")
            or k:find("^Skills") or k:find("^PVPRank") or k:find("^Statistics")) then _G[k] = nil end
    end
    local function atex(parent, name, layer, atlas, w, h)
        local t = tex(parent, name, layer)
        t.atlas = atlas
        t.GetAtlas = function(self) return self.atlas end
        t.SetAtlas = function(self, a) self.atlas = a end
        if w then t.w, t.h = w, h end
        return t
    end
    BLZ.atex = atex
    -- the 16001 window: 631 x 484, panes from 20 units under the top edge, no Inset / InsetRight, no CharacterFrameTab1..3
    local win = blz("Frame", "CharacterFrame", UIParent, 631, 484)
    win.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 250, y = -100 }
    win.shown = false
    win.Bg = tex(win, nil, "BACKGROUND")
    win.NineSlice = blz("Frame", nil, win, 631, 484)
    win.TitleContainer = blz("Frame", nil, win, 549, 20)
    tex(win, "CharacterFramePortrait", "ARTWORK")
    fstring(win, "CharacterFrameTitleText", "Stu")
    local close = blz("Button", "CharacterFrameCloseButton", win, 15, 15, "TOPRIGHT", -6, -4)
    tex(close, nil, "BACKGROUND")
    win.CloseButton = close
    tex(win, "CharacterLevelTextBackground", "BACKGROUND")

    local left = blz("Frame", "CharacterFrameLeftPaneHost", win, 398, 464, "TOPLEFT", 0, -20)
    win.LeftPaneHost = left
    atex(left, nil, "BACKGROUND", "UI-Character-Info-General-BG", 398, 464)
    local right = blz("Frame", "CharacterFrameRightPaneHost", win, 233, 464, "TOPLEFT", 398, -20)
    win.RightPaneHost = right
    atex(right, nil, "BACKGROUND", "UI-Character-Info-Stat-BG", 233, 464)
    right.StoneBg = atex(right, "CharacterFrameRightPaneHostStoneBg", "ARTWORK", "UI-Character-Info-Stat-StoneBG3", 233, 60)
    local div = blz("Frame", nil, right, 11, 463, "TOPLEFT", -5, 0)
    atex(div, nil, "OVERLAY", "common-framedivider", 11, 463)

    -- the six page tabs down the right edge
    local modeTabs = blz("Frame", "CharacterFrameModeTabs", win, 64, 384, "TOPLEFT", 624, -40)
    win.ModeTabs = modeTabs
    PAGE_FRAMES = { "PaperDollFrame", "ReputationFrame", "SkillsFrame", "PVPRankFrame", "TokenFrame", "StatisticsFrame" }
    local pages = {}
    local pd = blz("Frame", "PaperDollFrame", win, 631, 484)
    pd.id = 1
    pd.Bg = tex(pd, nil, "BACKGROUND")
    pages[1] = pd
    for i = 2, 6 do
        local f = blz("Frame", PAGE_FRAMES[i], win, 631, 484)
        f.shown = false
        pages[i] = f
    end
    local function select(i)
        for j, f in ipairs(pages) do if j == i then f:Show() else f:Hide() end end
        for j = 1, 6 do _G["CharacterFrameModeTab" .. j].SelectedTexture:SetShown(j == i) end
    end
    for i = 1, 6 do
        local tab = blz("Frame", "CharacterFrameModeTab" .. i, modeTabs, 55, 55, "TOPLEFT", 4, -(i - 1) * 62)
        tab.Background = atex(tab, nil, "BACKGROUND", "common-sidetab", 55, 60)
        tab.Icon = tex(tab, nil, "ARTWORK"); tab.Icon.w, tab.Icon.h = 50, 50
        tab.SelectedTexture = atex(tab, nil, "OVERLAY", "common-sidetab-selected", 55, 60)
        tab.SelectedTexture.shown = (i == 1)
        tab.TabGlow = atex(tab, nil, "OVERLAY", "common-sidetab-selected", 55, 60)
        tab.HighlightTexture = atex(tab, nil, "HIGHLIGHT", "common-sidetab-hover", 55, 60)
        tab.scripts.OnMouseUp = function() select(i) end
        tab.scripts.OnEnter = function() end
    end
    local toggle = blz("Button", "CharacterFrameRightPaneToggleButton", win, 28, 28, "TOPLEFT", 380, -3)
    win.RightPaneToggleButton = toggle
    tex(toggle, nil, "ARTWORK"); tex(toggle, nil, "ARTWORK"); tex(toggle, nil, "HIGHLIGHT")
    toggle.scripts.OnClick = function() end
    ToggleCharacter = function(name, onlyShow) for i, f in ipairs(pages) do if f:GetName() == name then select(i) end end end

    -- paper doll: top strip, level line, model with its buttons, sidebar tabs, slots
    local strip = blz("Frame", nil, pd, 398, 36, "TOPLEFT", 0, -20)
    pd.TopBackgroundStripHost = strip
    strip.TopBackgroundStrip = tex(strip, nil, "ARTWORK")
    strip.TopBackgroundStripBottomEdge = atex(strip, nil, "ARTWORK", "_UI-Frame-InnerTopTile", 398, 3)
    local info = blz("Frame", "PaperDollLevelInfo", pd, 220, 20, "TOPLEFT", 90, -28)
    fstring(info, "CharacterLevelText", "Level 22 Shaman", 12, { 1, 1, 1, 1 })
    local scene = blz("Frame", "CharacterModelScene", pd, 398, 428, "TOPLEFT", 0, -56)
    pd.CharacterModelScene = scene
    for _, n in ipairs({ "TopLeft", "TopRight", "BotLeft", "BotRight" }) do
        scene["Background" .. n] = tex(scene, "CharacterModelFrameBackground" .. n, "BACKGROUND")
    end
    scene.BackgroundOverlay = atex(scene, nil, "BORDER", "UI-Character-Info-RaceBG-Overlay", 398, 428)
    local control = blz("Frame", nil, scene, 132, 32, "BOTTOM", 0, 8)
    scene.ControlFrame = control
    for i, key in ipairs({ "zoomInButton", "zoomOutButton", "rotateLeftButton", "rotateRightButton", "resetButton" }) do
        local b = blz("Button", nil, control, 32, 32, "TOPLEFT", (i - 1) * 34, 0)
        b.Icon = atex(b, nil, "OVERLAY", "common-icon-zoomin", 16, 16)
        b.NormalTexture = atex(b, nil, "ARTWORK", "common-button-square-gray-up", 32, 32)
        b.PushedTexture = atex(b, nil, "ARTWORK", "common-button-square-gray-down", 32, 32)
        b.HighlightTexture = tex(b, nil, "HIGHLIGHT")
        b.GetNormalTexture = function(self) return self.NormalTexture end
        b.scripts.OnClick = function() end
        control[key] = b
    end
    local sidebar = blz("Frame", "PaperDollSidebarTabs", pd, 233, 85, "TOPLEFT", 398, -24)
    for i = 1, 3 do
        local b = blz("CheckButton", "PaperDollSidebarTab" .. i, sidebar, 42, 42, "TOPLEFT", 10 + (i - 1) * 46, 0)
        b.Icon = tex(b, nil, "BACKGROUND")
        atex(b, nil, "BORDER", "UI-Character-Info-StatTab", 42, 42)
        b.selTex = atex(b, nil, "OVERLAY", "UI-Character-Info-StatTab-Selected", 42, 42)
        b.selTex.shown = (i == 1)
        b.scripts.OnClick = function() end
        b.SetChecked = function(self, v) self.selTex:SetShown(v) end
    end
    pd.TitleManagerPane = blz("Frame", nil, pd, 233, 404, "TOPLEFT", 398, -100)
    pd.TitleManagerPane.shown = false
    pd.EquipmentManagerPane = blz("Frame", nil, pd, 233, 404, "TOPLEFT", 398, -100)
    pd.EquipmentManagerPane.shown = false

    local function slot(name, x, y)
        local b = blz("Button", "Character" .. name .. "Slot", pd, 37, 37, "TOPLEFT", x, y)
        b.id = SLOT_IDS[name]
        b.NormalTexture = tex(b, "Character" .. name .. "SlotNormalTexture", "ARTWORK")
        b.icon = tex(b, "Character" .. name .. "SlotIconTexture", "BORDER")
        b.icon.path = GEAR[b.id] and ("Interface\\Icons\\inv_" .. b.id) or "Interface\\PaperDoll\\UI-PaperDoll-Slot-" .. name
        b.IconBorder = tex(b, nil, "OVERLAY")
        b.Count = fstring(b, "Character" .. name .. "SlotCount", "", 12)
        -- the 16001 slot keeps its pressed art (a texture, hidden until a press) and its hover highlight as keyed regions
        b.PushedTexture = tex(b, nil, "ARTWORK")
        b.PushedTexture.shown = false
        b.HighlightTexture = tex(b, nil, "HIGHLIGHT")
        b.GetPushedTexture = function(self) return self.PushedTexture end
        b.GetHighlightTexture = function(self) return self.HighlightTexture end
        b.GetID = function(self) return self.id end
        -- the 16001 dump: the bronze ring is a BorderFrame child holding one UI-Character-Info-GearSlot texture, 55 x 55
        b.BorderFrame = blz("Frame", nil, b, 1, 1, "CENTER", 0, 0)
        b.BorderFrame.ring = tex(b.BorderFrame, nil, "BACKGROUND")
        return b
    end
    local lefts = { "Head", "Neck", "Shoulder", "Back", "Chest", "Shirt", "Tabard", "Wrist" }
    local rights = { "Hands", "Waist", "Legs", "Feet", "Finger0", "Finger1", "Trinket0", "Trinket1" }
    for i, n in ipairs(lefts) do slot(n, 14, -(70 + (i - 1) * 41)) end
    for i, n in ipairs(rights) do slot(n, 346, -(70 + (i - 1) * 41)) end
    slot("MainHand", 150, -420); slot("SecondaryHand", 190, -420); slot("Ranged", 230, -420)

    -- the stats: a ScrollBox of recycled rows (category headers and stat rows), the way 16001 builds them
    local pane = blz("Frame", "CharacterStatsPaneScrollBox", pd, 233, 404, "TOPLEFT", 398, -100)
    pane.Border = atex(pane, nil, "BORDER", "common-insideframe", 228, 403)
    atex(pane, nil, "BORDER", "UI-Character-Info-ScrollLine", 210, 7)
    pane.ClassBackground = atex(pane, nil, "BACKGROUND", "UI-Character-Info-Shaman-BG", 233, 383)
    local box = blz("Frame", nil, pane, 193, 366, "TOPLEFT", 10, -20)
    pane.ScrollBox = box
    box.ScrollTarget = blz("Frame", nil, box, 193, 1)
    box.rows = {}
    box.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
    box.Update = function() end
    local y = 0
    local function category(title)
        local f = blz("Frame", nil, box.ScrollTarget, 193, 40, "TOPLEFT", 0, -y)
        f.Background = atex(f, nil, "BACKGROUND", "UI-Character-Info-Title", 193, 40)
        f.Title = fstring(f, nil, title, 12, { 1, 1, 1, 1 })
        box.rows[#box.rows + 1] = f
        y = y + 40
    end
    local function stat(label, value)
        local f = blz("Frame", nil, box.ScrollTarget, 193, 23, "TOPLEFT", 0, -y)
        f.Background = atex(f, nil, "BACKGROUND", "UI-Character-Info-Line-Bounce2", 213, 23)
        f.Label = fstring(f, nil, label, 11, { 1, 0.82, 0, 1 })
        f.Value = fstring(f, nil, value, 11, { 1, 1, 1, 1 })
        f.Value.points[1] = { point = "RIGHT", rel = f, relPoint = "RIGHT", x = -8, y = 0 }
        f.Value.justify = "RIGHT"
        f.Label.points[1] = { point = "LEFT", rel = f, relPoint = "LEFT", x = 11, y = 0 }
        f.scripts.OnEnter = function() end
        box.rows[#box.rows + 1] = f
        y = y + 23
    end
    category("Attributes")
    for _, s in ipairs({ { "Strength", "74" }, { "Agility", "41" }, { "Stamina", "63" }, { "Intellect", "52" }, { "Spirit", "58" } }) do stat(s[1], s[2]) end
    category("Enhancements")
    for _, s in ipairs({ { "Attack Power", "122" }, { "Crit", "5.2%" }, { "Haste", "2.1%" } }) do stat(s[1], s[2]) end
    PaperDollFrame_UpdateStats = function() end

    -- the other pages: a ScrollBox with the long line overlays, a detail pane
    for _, i in ipairs({ 3, 6 }) do
        local pg = pages[i]
        pg.ScrollBox = blz("Frame", nil, pg, 363, 409, "TOPLEFT", 8, -40)
        pg.ScrollBox.rows = {}
        pg.ScrollBox.ForEachFrame = function(self, fn) for _, r in ipairs(self.rows) do fn(r) end end
        pg.ScrollBox.Update = function() end
        local ov = blz("Frame", nil, pg.ScrollBox, 1, 1)
        atex(ov, nil, "OVERLAY", "UI-Character-Info-ScrollLine-Long", 384, 8)
        local hdr = blz("Button", nil, pg.ScrollBox, 343, 26, "TOPLEFT", 0, 0)
        atex(hdr, nil, "BACKGROUND", "common-button-list-collapseExpand", 343, 26)
        hdr.StateIcon = atex(hdr, nil, "BORDER", "common-button-list-minus", 13, 4)
        hdr.Name = fstring(hdr, nil, "Header", 12)
        pg.ScrollBox.rows[1] = hdr
    end
    local sk = pages[3]
    sk.SkillDetailFrame = blz("Frame", nil, sk, 205, 436, "TOPLEFT", 400, -30)
    sk.SkillDetailFrame.Title = fstring(sk.SkillDetailFrame, nil, "Mining", 12)
    sk.SkillDetailFrame.Divider = atex(sk.SkillDetailFrame, nil, "BORDER", "UI-Character-Info-ScrollLine", 210, 7)
    sk.SkillDetailFrame.RankBar = blz("Frame", nil, sk.SkillDetailFrame, 180, 29, "TOPLEFT", 10, -80)
    atex(sk.SkillDetailFrame.RankBar, nil, "BACKGROUND", "common-stat-bar-BG", 180, 29)
    local pv = pages[4]
    pv.MainInfoFrame = blz("Frame", nil, pv, 398, 135, "TOPLEFT", 0, -20)
    atex(pv.MainInfoFrame, nil, "ARTWORK", "UI-Character-Info-Honor-LevelBG", 350, 62)
    pv.MainInfoFrame.badge = atex(pv.MainInfoFrame, nil, "ARTWORK", "UI-Character-Info-Honor-Icon-Horde", 75, 75)
    pv.DetailFrame = blz("Frame", nil, pv, 205, 436, "TOPLEFT", 400, -30)
    pv.DetailFrame.Title = fstring(pv.DetailFrame, nil, "Honor", 12)
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
                if r <= l or b <= t:
                    continue
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
