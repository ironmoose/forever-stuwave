#!/usr/bin/env python3
"""Runs the real Modules/Skins/HudAlerts.lua (and the zone text part of HudText.lua) headless against mock HUD frames.

Pinned: the mirror timers (MirrorTimerContainer.mirrorTimers) hold the stock bar, border and text box art, wear a cut plate and
27 cells that follow the stock bar value, take a kind colour, go pink under ten seconds with the last lit cells blinking, and the
setting turns that off; the loot, money and recipe toasts hold their stock backgrounds, wear a plate, an icon ring and a fuse
that burns down with the stock out animation delay (paused while the stock code pauses it), toasts of other systems stay stock;
the vehicle exit key holds its art and repaints on hover, press and disable, and is built after combat when it first shows up
in combat; the zone text takes the territory colour after every SetZoneText. No script or attribute is written on a Blizzard
widget (the engine throws), and no Blizzard frame is moved. Run `python3 tools/hudalerts-harness.py [--png debug/hudalerts]`.
The mock is NOT the real client.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from charskin_support import Harness  # noqa: E402

BLIZZARD = r"""
local blz, tex, fstring = BLZ.blz, BLZ.tex, BLZ.fstring
local function atex(parent, name, layer, atlas, w, h)
    local t = tex(parent, name, layer)
    t.atlas = atlas
    t.GetAtlas = function(self) return self.atlas end
    t.SetAtlas = function(self, a) self.atlas = a end
    if w then t.w, t.h = w, h end
    return t
end

NOW = 100
function GetTime() return NOW end
-- one frame of the shared animation ticker (the Kit makes one hidden frame with one OnUpdate)
function Tick(dt)
    NOW = NOW + dt
    for _, o in ipairs(ALL) do
        if o.scripts.OnUpdate and not o.blizz then o.scripts.OnUpdate(o, dt) end
    end
end

local function statusbar(parent, w, h, x, y)
    local sb = blz("StatusBar", nil, parent, w, h, "TOP", x, y)
    sb.min, sb.max, sb.value = 0, 1, 0
    function sb:SetMinMaxValues(a, b) self.min, self.max = a, b end
    function sb:GetMinMaxValues() return self.min, self.max end
    function sb:SetValue(v) self.value = v end
    function sb:GetValue() return self.value end
    function sb:SetStatusBarTexture() end
    sb.fill = tex(sb, nil, "ARTWORK")
    return sb
end

-- AlertFrames.lua, reduced to what the skin hooks
function AlertFrame_PlayOutAnimation(frame, delay) frame.outDelay = delay or 1; frame.paused = false end
function AlertFrame_PauseOutAnimation(frame) frame.paused = true end
function AlertFrame_ResumeOutAnimation(frame) AlertFrame_PlayOutAnimation(frame, 1) end
function AlertFrame_ShowNewAlert(frame) frame:Show(); AlertFrame_PlayOutAnimation(frame, frame.duration or 4) end
LootAlertSystem, MoneyWonAlertSystem, NewRecipeLearnedAlertSystem, HonorAwardedAlertSystem = {}, {}, {}, {}

local GOLD, WHITE, GREEN = { 1, 0.82, 0, 1 }, { 1, 1, 1, 1 }, { 0.12, 1, 0, 1 }

-- LootWonAlertFrameTemplate: 276 x 96, the item button inside it
function MakeLoot(x, y, name, rollValue)
    local f = blz("Frame", nil, UIParent, 276, 96, "TOPLEFT", x, y)
    f.shown = false
    f.queue = LootAlertSystem
    f.Background = atex(f, nil, "BACKGROUND", "LootToast", 276, 96)
    f.PvPBackground = atex(f, nil, "BACKGROUND", "loottoast-bg-alliance", 276, 96)
    f.RatedPvPBackground = atex(f, nil, "BACKGROUND", "pvprated-loottoast-bg-alliance", 276, 96)
    f.BGAtlas = atex(f, nil, "BACKGROUND", nil, 276, 96)
    local li = blz("Button", nil, f, 52, 52, "TOPLEFT", 22, -23)
    f.lootItem = li
    li.Icon = tex(li, nil, "BORDER"); li.Icon.path = "Interface\\Icons\\inv_staff_01"; li.Icon.w, li.Icon.h = 52, 52
    li.IconBorder = atex(li, nil, "ARTWORK", "loottoast-itemborder-green", 64, 64)
    li.IconOverlay = tex(li, nil, "ARTWORK")
    li.ItemBurst = tex(li, nil, "OVERLAY")
    li.Count = fstring(li, nil, "", 12, WHITE)
    f.Label = fstring(f, nil, "You won:", 12, GOLD)
    f.Label.w, f.Label.h = 167, 16
    f.Label.points[1] = { point = "TOPLEFT", rel = li, relPoint = "TOPRIGHT", x = 7, y = 0 }
    f.ItemName = fstring(f, nil, name or "Gnarled Ash Staff", 14, WHITE)
    f.ItemName.w, f.ItemName.h = 167, 33
    f.ItemName.points[1] = { point = "TOPLEFT", rel = li, relPoint = "TOPRIGHT", x = 10, y = -19 }
    f.RollTypeIcon = tex(f, nil, "ARTWORK"); f.RollTypeIcon.w, f.RollTypeIcon.h = 22, 22
    f.RollTypeIcon.points[1] = { point = "TOPRIGHT", rel = f, relPoint = "TOPRIGHT", x = -20, y = -18 }
    f.RollValue = fstring(f, nil, rollValue or "", 12, GREEN)
    f.RollValue.points[1] = { point = "RIGHT", rel = f.RollTypeIcon, relPoint = "LEFT", x = -3, y = 2 }
    f.glow = atex(f, nil, "OVERLAY", "loottoast-glow", 286, 109)
    f.shine = tex(f, nil, "OVERLAY")
    return f
end

-- MoneyWonAlertFrameTemplate: 249 x 71
function MakeMoney(x, y)
    local f = blz("Frame", nil, UIParent, 249, 71, "TOPLEFT", x, y)
    f.shown = false
    f.queue = MoneyWonAlertSystem
    f.Background = tex(f, nil, "BACKGROUND")
    f.Icon = tex(f, nil, "BORDER"); f.Icon.path = "Interface\\Icons\\INV_Misc_Coin_02"; f.Icon.w, f.Icon.h = 38, 38
    f.Icon.points[1] = { point = "LEFT", rel = f, relPoint = "LEFT", x = 16, y = 0 }
    f.IconBorder = tex(f, nil, "ARTWORK"); f.IconBorder.w, f.IconBorder.h = 45, 45
    f.IconBorder.points[1] = { point = "CENTER", rel = f.Icon, relPoint = "CENTER", x = 0, y = 0 }
    f.Label = fstring(f, nil, "Money Won", 12, GOLD)
    f.Label.points[1] = { point = "TOPLEFT", rel = f.IconBorder, relPoint = "TOPRIGHT", x = 7, y = -1 }
    f.Amount = fstring(f, nil, "4g 12s", 16, WHITE)
    f.Amount.points[1] = { point = "BOTTOMLEFT", rel = f.IconBorder, relPoint = "BOTTOMRIGHT", x = 10, y = 7 }
    return f
end

-- NewRecipeLearnedAlertFrameTemplate: 312 x 89
function MakeRecipe(x, y)
    local f = blz("Frame", nil, UIParent, 312, 89, "TOPLEFT", x, y)
    f.shown = false
    f.queue = NewRecipeLearnedAlertSystem
    atex(f, nil, "BACKGROUND", "recipetoast-bg", 312, 89)
    f.Icon = tex(f, nil, "BACKGROUND"); f.Icon.sub = -1; f.Icon.path = "Interface\\Icons\\inv_misc_bandage_01"; f.Icon.w, f.Icon.h = 64, 64
    f.Icon.points[1] = { point = "LEFT", rel = f, relPoint = "LEFT", x = 18, y = 0 }
    f.Title = fstring(f, nil, "Recipe Learned", 12, WHITE)
    f.Title.points[1] = { point = "TOP", rel = f, relPoint = "TOP", x = 31, y = -15 }
    f.Name = fstring(f, nil, "Linen Bandage", 14, GOLD)
    f.Name.points = { { point = "TOPLEFT", rel = f, relPoint = "TOPLEFT", x = 98, y = -34 },
        { point = "BOTTOMRIGHT", rel = f, relPoint = "BOTTOMRIGHT", x = -32, y = 17 } }
    f.Name.justify = "CENTER"
    f.glow = atex(f, nil, "OVERLAY", "UI-Achievement-Alert-Glow", 400, 171)
    f.shine = atex(f, nil, "OVERLAY", "UI-Achievement-Alert-Glow", 67, 82)
    return f
end

-- the achievement toast, which the skin leaves alone
function MakeAchievement(x, y)
    local f = blz("Frame", nil, UIParent, 300, 101, "TOPLEFT", x, y)
    f.shown = false
    f.Background = atex(f, nil, "BACKGROUND", "ui-achievement-alert-background", 300, 101)
    f.Unlocked = fstring(f, nil, "Achievement unlocked", 10, GOLD)
    f.Name = fstring(f, nil, "Explore Mulgore", 12, WHITE)
    f.Icon = blz("Frame", nil, f, 78, 75, "TOPLEFT", -4, -15)
    return f
end

function MakeVehicle(x, y)
    local b = blz("Button", "MainMenuBarVehicleLeaveButton", UIParent, 32, 32, "TOPLEFT", x or 40, y or -40)
    b.normalTex = tex(b, nil, "ARTWORK")
    b.pushedTex = tex(b, nil, "ARTWORK")
    b.highlightTex = tex(b, nil, "HIGHLIGHT")
    b.Highlight = b.highlightTex
    b.scripts.OnClick = function() end
    b.scripts.OnEnter = function() end
    b.scripts.OnLeave = function() end
    return b
end

PVPTYPE = nil
C_PvP = { GetZonePVPInfo = function() return PVPTYPE, false, "" end }
function SetZoneText(showZone)
    local c = { 1.0, 0.9294, 0.7607 }
    if PVPTYPE == "friendly" then c = { 0.1, 1.0, 0.1 }
    elseif PVPTYPE == "hostile" or PVPTYPE == "combat" or PVPTYPE == "arena" then c = { 1.0, 0.1, 0.1 }
    elseif PVPTYPE == "contested" then c = { 1.0, 0.7, 0 }
    elseif PVPTYPE == "sanctuary" then c = { 0.41, 0.8, 0.94 } end
    for _, n in ipairs({ "ZoneTextString", "SubZoneTextString", "PVPInfoTextString", "PVPArenaTextString" }) do _G[n]:SetTextColor(c[1], c[2], c[3]) end
end

local build = BuildBlizzard
function BuildBlizzard()
    for k in pairs(_G) do
        if type(k) == "string" and (k:find("^Character") or k:find("^PaperDoll") or k:find("^Reputation") or k:find("^Token")
            or k:find("^Skills") or k:find("^PVPRank") or k:find("^Statistics")) then _G[k] = nil end
    end
    -- the mirror timers, as Blizzard_MirrorTimer builds them: a container, three timers of 206 x 32 with a 195 x 13 bar
    local cont = blz("Frame", "MirrorTimerContainer", UIParent, 1, 1, "TOPLEFT", 40, -40)
    cont.mirrorTimers = {}
    for i = 1, 3 do
        local t = blz("Frame", nil, cont, 206, 32, "TOPLEFT", 0, -(i - 1) * 40)
        t.shown = false
        t.StatusBar = statusbar(t, 195, 13, 0, -2)
        t.TextBorder = atex(t, nil, "BACKGROUND", "ui-castingbar-textbox", 195, 27)
        atex(t, nil, "BACKGROUND", "ui-castingbar-background", 197, 15)
        t.Border = atex(t, nil, "OVERLAY", "ui-castingbar-frame", 199, 17)
        t.Text = fstring(t, nil, "", 10, WHITE)
        t.Text.points[1] = { point = "TOP", rel = t.StatusBar, relPoint = "BOTTOM", x = 0, y = 0 }
        t.Text.justify = "CENTER"
        function t:Setup(timer, value, maxvalue, paused, label)
            self.timer = timer
            self.StatusBar:SetMinMaxValues(0, maxvalue / 1000)
            self.StatusBar:SetValue(value / 1000)
            self.Text:SetText(label)
            self:Show()
        end
        function t:Clear() self.timer = nil; self:Hide() end
        cont.mirrorTimers[i] = t
    end
    -- the zone text
    for i, n in ipairs({ "ZoneTextString", "SubZoneTextString", "PVPInfoTextString", "PVPArenaTextString" }) do
        local f = fstring(UIParent, n, i == 1 and "Mulgore" or (i == 2 and "Bloodhoof Village" or ""), 24, WHITE)
        f.points[1] = { point = "TOPLEFT", rel = UIParent, relPoint = "TOPLEFT", x = 600, y = -40 - i * 30 }
    end
    ZonePVPType = nil
    PVPTYPE = nil
end
"""

H = Harness({"HudText": "Modules/Skins/HudText.lua", "HudAlerts": "Modules/Skins/HudAlerts.lua"}, BLIZZARD)
case = H.case

LIT = """
local function lit(t)
    local n = 0
    local unlit = FS.Theme.COLOR_CTRL_CELL
    for _, c in ipairs(FS.HudAlerts.state.mirror[t].cells) do
        if c.color and (math.abs(c.color[1] - unlit[1]) > 0.001 or math.abs(c.color[2] - unlit[2]) > 0.001) then n = n + 1 end
    end
    return n
end
"""

case("mirror timers: the stock bar, border and text box art are held and a plate with 27 cells is built on each timer", LIT + """
    local timers = MirrorTimerContainer.mirrorTimers
    for i = 1, 3 do
        local t = timers[i]
        local m = FS.HudAlerts.state.mirror[t]
        assert(m, 'timer ' .. i .. ' not skinned')
        assert(#m.cells == 27, 'cells: ' .. #m.cells)
        assert(t.Border.alpha == 0 and t.TextBorder.alpha == 0, 'border art kept')
        assert(t.StatusBar.alpha == 0, 'bar fill kept')
        assert(t.Text.fontPath ~= 'stock.ttf', 'label not mono')
        assert(t.shown == false, 'a stock frame was shown')
    end
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("mirror timers: the bar value lights the cells, a kind picks the colour, a cleared timer is left alone", LIT + """
    local t = MirrorTimerContainer.mirrorTimers[1]
    t:Setup('BREATH', 41000, 60000, false, 'Breath')
    assert(lit(t) == 19, 'breath cells: ' .. lit(t))
    t.StatusBar:SetValue(30)
    assert(lit(t) == 14, 'half: ' .. lit(t))
    local m = FS.HudAlerts.state.mirror[t]
    local cyan = FS.Theme.COLOR_POWER
    assert(m.cells[1].color[2] == cyan[2] and m.cells[1].color[3] == cyan[3], 'breath is not cyan')
    local t2 = MirrorTimerContainer.mirrorTimers[2]
    t2:Setup('EXHAUSTION', 18000, 60000, false, 'Fatigue')
    local amber = FS.Theme.COLOR_AMBER
    assert(FS.HudAlerts.state.mirror[t2].cells[1].color[2] == amber[2], 'fatigue is not amber')
    local t3 = MirrorTimerContainer.mirrorTimers[3]
    t3:Setup('FEIGNDEATH', 290000, 360000, false, 'Feign Death')
    local violet = FS.Theme.COLOR_BORDER
    assert(FS.HudAlerts.state.mirror[t3].cells[1].color[3] == violet[3], 'feign death is not violet')
    t:Clear()
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("mirror timers: under ten seconds the cells go pink and the last three lit cells blink, the setting turns it off", LIT + """
    local t = MirrorTimerContainer.mirrorTimers[1]
    t:Setup('BREATH', 41000, 60000, false, 'Breath')
    t.StatusBar:SetValue(7)
    local m = FS.HudAlerts.state.mirror[t]
    local pink = FS.Theme.COLOR_HEALTH
    assert(m.low, 'not low')
    assert(m.cells[1].color[2] == pink[2], 'low cells not pink')
    assert(FS.ControlKit.IsAnimating(t, 'low'), 'no blink running')
    local seen = {}
    for i = 1, 10 do
        Tick(0.1)
        local a = m.cells[m.lit].color[4]
        seen[a] = true
    end
    local n = 0
    for _ in pairs(seen) do n = n + 1 end
    assert(n >= 2, 'the last lit cell never changed alpha')
    assert(m.cells[1].color[4] == 1, 'the first cell blinked')
    -- back above ten seconds: stops, cyan again
    t.StatusBar:SetValue(40)
    assert(not m.low and not FS.ControlKit.IsAnimating(t, 'low'), 'still blinking')
    assert(m.cells[1].color[2] ~= pink[2], 'still pink')
    -- the setting off: low never blinks and the colour stays the kind colour
    FS.Config = { Get = function(k) if k == 'hud.mirror.low' then return false end end }
    t.StatusBar:SetValue(5)
    assert(m.cells[1].color[2] ~= pink[2], 'pink with the setting off')
    assert(not FS.ControlKit.IsAnimating(t, 'low'), 'blinking with the setting off')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("toasts: a loot toast holds its stock backgrounds, keeps the icon, and wears a plate, a ring and a fuse", """
    local f = MakeLoot(40, -40, 'Gnarled Ash Staff', '87')
    local before = #f.points
    AlertFrame_ShowNewAlert(f)
    local S = FS.HudAlerts.state
    local rec = S.toast[f]
    assert(rec and rec.kind == 'loot', 'not skinned as loot')
    assert(f.Background.alpha == 0 and f.PvPBackground.alpha == 0 and f.RatedPvPBackground.alpha == 0 and f.BGAtlas.alpha == 0, 'background kept')
    assert(f.glow.alpha == 0 and f.shine.alpha == 0, 'glow kept')
    assert(f.lootItem.IconBorder.alpha == 0 and f.lootItem.ItemBurst.alpha == 0, 'item border art kept')
    assert(f.lootItem.Icon.alpha == 1, 'the item icon was held')
    assert(f.RollTypeIcon.alpha == 1, 'the roll icon was held')
    assert(f.ItemName.fontPath ~= 'stock.ttf' and f.Label.fontPath ~= 'stock.ttf', 'text not mono')
    assert(rec.plate and rec.ring and rec.track and rec.fill, 'parts missing')
    assert(#f.points == before and f.points[1].x == 40 and f.points[1].y == -40, 'a stock frame was moved')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("toasts: money and recipe toasts are skinned, an achievement toast and a toast of another system stay stock", """
    local m, r, a = MakeMoney(40, -40), MakeRecipe(40, -140), MakeAchievement(40, -240)
    local honor = MakeMoney(40, -340)
    honor.queue = HonorAwardedAlertSystem
    for _, f in ipairs({ m, r, a, honor }) do AlertFrame_ShowNewAlert(f) end
    local S = FS.HudAlerts.state
    assert(S.toast[m] and S.toast[m].kind == 'money', 'money not skinned')
    assert(S.toast[r] and S.toast[r].kind == 'recipe', 'recipe not skinned')
    assert(m.Background.alpha == 0 and m.IconBorder.alpha == 0 and m.Icon.alpha == 1, 'money art')
    assert(r.Icon.alpha == 1 and r.glow.alpha == 0, 'recipe art')
    assert(not S.toast[a], 'the achievement toast was skinned')
    assert(a.Background.alpha == 1, 'its art was held')
    assert(not S.toast[honor], 'a toast of another system was skinned')
    assert(honor.Background.alpha == 1, 'honor art was held')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("toasts: the fuse burns down over the stock hold time, freezes while paused and restarts for the one second after", """
    local f = MakeMoney(40, -40)
    NOW = 100
    AlertFrame_ShowNewAlert(f)
    local S = FS.HudAlerts.state
    local rec = S.toast[f]
    assert(rec.fuseW and rec.fuseW > 20, 'no fuse width')
    assert(FS.ControlKit.IsAnimating(f, 'fuse'), 'no fuse animation')
    Tick(0.1)
    local full = rec.fuseNow
    assert(full >= rec.fuseW * 0.95, 'not full at the start: ' .. tostring(full) .. ' of ' .. rec.fuseW)
    Tick(1.9)
    local half = rec.fuseNow
    assert(math.abs(half - rec.fuseW * 0.5) <= 2, 'half way: ' .. tostring(half) .. ' of ' .. rec.fuseW)
    AlertFrame_PauseOutAnimation(f)
    Tick(1.0)
    Tick(1.0)
    assert(math.abs(rec.fuseNow - half) <= 2, 'moved while paused')
    AlertFrame_ResumeOutAnimation(f)
    Tick(0.01)
    assert(rec.fuseNow >= rec.fuseW * 0.95, 'resume did not restart: ' .. tostring(rec.fuseNow))
    Tick(0.5)
    assert(math.abs(rec.fuseNow - rec.fuseW * 0.5) <= 3, 'one second hold, half way: ' .. tostring(rec.fuseNow))
    Tick(0.6)
    assert(rec.fuseNow == 0, 'not burnt out: ' .. tostring(rec.fuseNow))
    assert(not rec.fill:IsShown(), 'fill still shown at zero')
    assert(not FS.ControlKit.IsAnimating(f, 'fuse'), 'fuse animation did not stop')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("toasts: the fuse and the flash have a setting each", """
    FS.Config = { Get = function(k) if k == 'hud.alerts.fuse' or k == 'hud.alerts.act' then return false end end }
    local f = MakeLoot(40, -40)
    AlertFrame_ShowNewAlert(f)
    local rec = FS.HudAlerts.state.toast[f]
    assert(not rec.track:IsShown() and not rec.fill:IsShown(), 'fuse shown with the setting off')
    assert(not FS.ControlKit.IsAnimating(f, 'fuse'), 'fuse animating with the setting off')
    assert(not FS.ControlKit.IsAnimating(f, 'flash'), 'flash running with the setting off')
    assert(rec.ring.vertex, 'ring not painted')
    FS.Config = { Get = function() return true end }
    local g = MakeLoot(40, -140)
    AlertFrame_ShowNewAlert(g)
    assert(FS.ControlKit.IsAnimating(g, 'flash'), 'no flash with the setting on')
    local r0 = FS.HudAlerts.state.toast[g].ring.vertex[1]
    Tick(0.1); Tick(0.4); Tick(0.4)
    assert(not FS.ControlKit.IsAnimating(g, 'flash'), 'flash did not end')
    local blue = FS.Theme.COLOR_TOTEM.water
    assert(math.abs(FS.HudAlerts.state.toast[g].ring.vertex[1] - blue[1]) < 0.01, 'ring did not settle on the kind colour')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("toasts: a pooled toast shown again restarts its fuse and does not build a second plate", """
    local f = MakeRecipe(40, -40)
    AlertFrame_ShowNewAlert(f)
    local rec = FS.HudAlerts.state.toast[f]
    local objects = ObjCount()
    Tick(3.5)
    f:Hide()
    AlertFrame_ShowNewAlert(f)
    assert(ObjCount() == objects, 'objects grew: ' .. ObjCount() - objects)
    assert(FS.HudAlerts.state.toast[f] == rec, 'rebuilt')
    Tick(0.05)
    assert(rec.fuseNow >= rec.fuseW * 0.95, 'fuse not restarted: ' .. tostring(rec.fuseNow))
""")

case("toasts: a pixel scale change seats the plate and the fuse again", """
    local f = MakeLoot(40, -40)
    AlertFrame_ShowNewAlert(f)
    local rec = FS.HudAlerts.state.toast[f]
    local w1 = rec.fuseW
    PPU = 1.5
    FS.ControlKit.Reseat()
    assert(rec.fuseW > w1, 'fuse width did not follow the scale: ' .. w1 .. ' -> ' .. rec.fuseW)
    local l, t, r, b = Px(rec.plate.ring, f)
    assert(math.abs(l - 10 * 1.5) <= 1 and math.abs(t - 12 * 1.5) <= 1, 'plate inset after reseat: ' .. l .. ',' .. t)
""")

case("vehicle exit: the stock art is held, the key repaints on hover, press and disable, no script or attribute is written", """
    local b = MakeVehicle()
    Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
    local S = FS.HudAlerts.state
    local v = S.vehicle[b]
    assert(v, 'not skinned')
    assert(b.normalTex.alpha == 0 and b.pushedTex.alpha == 0 and b.highlightTex.alpha == 0, 'stock art kept')
    local pink, cyan = FS.Theme.COLOR_HEALTH, FS.Theme.COLOR_POWER
    assert(v.plate.ring.vertex[1] == pink[1] and v.plate.ring.vertex[3] == pink[3], 'idle edge not pink')
    b:RunScript('OnEnter')
    assert(v.plate.ring.vertex[1] == cyan[1] and v.plate.ring.vertex[2] == cyan[2], 'hover edge not cyan')
    b:RunScript('OnLeave')
    assert(v.plate.ring.vertex[1] == pink[1], 'edge not pink after leave')
    b:Disable()
    assert(v.plate.ring.vertex[1] < 0.5, 'disabled edge not dim')
    b:Enable()
    assert(b.scripts.OnClick, 'click lost')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

case("mirror timers: the cells sit inside the plate with equal side margins, clear of the label row", """
    local t = MirrorTimerContainer.mirrorTimers[1]
    local m = FS.HudAlerts.state.mirror[t]
    local pl, pt, pr, pb = Px(m.plate.ring, t)
    local c1l, c1t, c1r, c1b = Px(m.cells[1], t)
    local cnl, cnt, cnr, cnb = Px(m.cells[27], t)
    assert(math.abs((c1l - pl) - (pr - cnr)) <= 1, 'side margins: ' .. (c1l - pl) .. ' vs ' .. (pr - cnr))
    assert(c1l - pl >= 8, 'cells too close to the plate edge: ' .. (c1l - pl))
    assert(c1t > pt + 2 and c1b < pb - 2, 'cells outside the plate')
    t:Setup('BREATH', 41000, 60000, false, 'Breath')
    local tl, tt, tr, tb = Px(t.Text, t)
    assert(tt >= c1b - 1, 'label overlaps the cells: ' .. tt .. ' vs ' .. c1b)
    for i = 2, 27 do
        local l, _, r = Px(m.cells[i], t)
        local pl2, _, pr2 = Px(m.cells[i - 1], t)
        assert(Near(l - pr2, 2, 0.01), 'gap between cells ' .. i - 1 .. ' and ' .. i .. ': ' .. (l - pr2))
    end
""")

case("toasts: the ring, the fuse and the texts lie inside the plate for every kind", """
    local frames = { loot = MakeLoot(40, -40, 'Gnarled Ash Staff', '87'), money = MakeMoney(40, -150), recipe = MakeRecipe(40, -240) }
    for kind, f in pairs(frames) do
        AlertFrame_ShowNewAlert(f)
        local rec = FS.HudAlerts.state.toast[f]
        local pl, pt, pr, pb = Px(rec.plate.ring, f)
        local rl, rt, rr, rb = Px(rec.ring, f)
        assert(rl >= pl + 2 and rt >= pt + 2 and rb <= pb - 2, kind .. ' ring touches the plate: ' .. rl - pl .. ',' .. rt - pt .. ',' .. pb - rb)
        local fl, ft, fr, fb = Px(rec.track, f)
        assert(fl >= pl + 6 and fr <= pr - 6 and fb <= pb - 2 and ft >= pt, kind .. ' fuse outside: ' .. fl - pl .. ',' .. pr - fr .. ',' .. pb - fb)
        assert(fl >= rr + 3, kind .. ' fuse starts under the icon ring: ' .. fl .. ' vs ' .. rr)
        local names = kind == 'loot' and { f.Label, f.ItemName } or kind == 'money' and { f.Label, f.Amount } or { f.Title, f.Name }
        for _, fs in ipairs(names) do
            local l, t, r, b = Px(fs, f)
            assert(r <= pr - 4 and l >= rr and t >= pt and b <= fb, kind .. ' text out of place: l=' .. l .. ' r=' .. r .. ' t=' .. t .. ' b=' .. b .. ' fuse=' .. fb)
        end
        assert(fb < pb, kind .. ' fuse below the plate')
    end
""")

case("vehicle exit: the glyph is centred in the key and the hazard bands lie inside the plate clear of the cut corners", """
    local b = MakeVehicle()
    Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
    local v = FS.HudAlerts.state.vehicle[b]
    local W, H = FS.ControlKit.SizePx(b)
    local gl, gt, gr, gb = Px(v.glyph, b)
    assert(Near((gl + gr) / 2, W / 2, 0.51) and Near((gt + gb) / 2, H / 2, 0.51), 'glyph off centre: ' .. (gl + gr) / 2 .. ',' .. (gt + gb) / 2 .. ' in ' .. W .. 'x' .. H)
    local tl, tt, tr, tb = Px(v.top, b)
    local bl, bt, br, bb = Px(v.bottom, b)
    assert(tl >= 3 and tr <= W - 3 + 0.01 and tt >= 2, 'top band outside: ' .. tl .. ',' .. tr .. ',' .. tt)
    assert(bl >= 2 and br <= W - 3 + 0.01 and bb <= H - 2 + 0.01, 'bottom band outside: ' .. bl .. ',' .. br .. ',' .. bb)
    b:RunScript('OnMouseDown')
    local pl, pt = Px(v.glyph, b)
    assert(pl > gl and pt < gt, 'glyph did not launch up and right while held')
    b:RunScript('OnMouseUp')
    local rl, rt = Px(v.glyph, b)
    assert(Near(rl, gl) and Near(rt, gt), 'glyph did not come back')
""")

case("vehicle exit: a key that appears in combat is built when combat ends", """
    __combat = true
    local b = MakeVehicle()
    Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
    assert(not FS.HudAlerts.state.vehicle[b], 'built in combat')
    __combat = false
    Fire('PLAYER_REGEN_ENABLED'); FlushTimers()
    assert(FS.HudAlerts.state.vehicle[b], 'not built after combat')
""")

case("zone text: every SetZoneText takes the territory colour", """
    local cyan, pink, amber = FS.Theme.COLOR_POWER, FS.Theme.COLOR_HEALTH, FS.Theme.COLOR_AMBER
    local function colour(name) local c = _G[name].textColor; return c[1], c[2], c[3] end
    local function is(name, want, what)
        local r, g, b = colour(name)
        assert(math.abs(r - want[1]) < 0.01 and math.abs(g - want[2]) < 0.01 and math.abs(b - want[3]) < 0.01, what .. ': ' .. r .. ',' .. g .. ',' .. b)
    end
    PVPTYPE = 'friendly'; SetZoneText(true)
    is('ZoneTextString', cyan, 'friendly zone'); is('SubZoneTextString', cyan, 'friendly subzone'); is('PVPInfoTextString', cyan, 'friendly pvp line')
    PVPTYPE = 'hostile'; SetZoneText(true)
    is('ZoneTextString', pink, 'hostile zone'); is('SubZoneTextString', pink, 'hostile subzone')
    PVPTYPE = 'contested'; SetZoneText(true)
    is('ZoneTextString', amber, 'contested zone'); is('PVPInfoTextString', amber, 'contested pvp line')
    PVPTYPE = 'sanctuary'; SetZoneText(true)
    is('ZoneTextString', cyan, 'sanctuary zone')
    PVPTYPE = nil; SetZoneText(true)
    is('ZoneTextString', cyan, 'no territory zone'); is('SubZoneTextString', cyan, 'no territory subzone')
    assert(ZoneTextString.fontPath ~= 'stock.ttf', 'zone text not mono')
    assert(#DEGRADED == 0, table.concat(DEGRADED, '\\n'))
""")

SCENES = {
    "mirror": """
        local t1, t2, t3 = MirrorTimerContainer.mirrorTimers[1], MirrorTimerContainer.mirrorTimers[2], MirrorTimerContainer.mirrorTimers[3]
        t1:Setup('BREATH', 41000, 60000, false, 'Breath')
        t2:Setup('EXHAUSTION', 18000, 60000, false, 'Fatigue')
        t3:Setup('FEIGNDEATH', 290000, 360000, false, 'Feign Death')
        FlushTimers()
        return DumpOps({ MirrorTimerContainer })
    """,
    "mirror-low": """
        local t1, t2 = MirrorTimerContainer.mirrorTimers[1], MirrorTimerContainer.mirrorTimers[2]
        t1:Setup('BREATH', 7000, 60000, false, 'Breath')
        t2:Setup('EXHAUSTION', 3000, 60000, false, 'Fatigue')
        FlushTimers()
        return DumpOps({ MirrorTimerContainer })
    """,
    "toasts": """
        local l, m, r = MakeLoot(40, -40, 'Gnarled Ash Staff', '87'), MakeMoney(40, -150), MakeRecipe(40, -240)
        NOW = 100
        for _, f in ipairs({ l, m, r }) do AlertFrame_ShowNewAlert(f) end
        Tick(2.0)
        FlushTimers()
        return DumpOps({ l, m, r })
    """,
    "vehicle": """
        local b = MakeVehicle(40, -40)
        Fire('PLAYER_ENTERING_WORLD'); FlushTimers()
        return DumpOps({ b })
    """,
}

if __name__ == "__main__":
    raise SystemExit(H.main("HUD alerts", SCENES))
