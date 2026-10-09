"""Shared Lua for the harnesses that check a spell tooltip on an icon.

The real tooltip helpers (HoverOnly, SetTipSpell, SpellIDForName, SpellCacheEpoch, AttachSpellTooltip,
RefreshSpellTooltip, ReleaseSpellTip, ReleaseGatedTips, ShowAuraTooltip) are
loaded from Core/FrameHelpers.lua into a throwaway namespace and copied onto the harness's own FS.FrameHelpers
stub, so a case drives the real code: hover(frame) runs the OnEnter hooks, tip() reads what GameTooltip was told.

Harness frame mocks need three things: Frame:HookScript storing into self.hooks[name], and the two
SetMouseMotionEnabled / SetMouseClickEnabled setters (HOOK_MOCK below adds them to a mock frame class).
"""

from pathlib import Path

HELPERS = Path(__file__).resolve().parent.parent / "forever-stuwave" / "Core" / "FrameHelpers.lua"

# Frame-class additions, for a harness whose frame class is a table named `Frame` (pass its name to .format).
HOOK_MOCK = r"""
function {cls}:HookScript(name, fn)
    self.hooks = self.hooks or {{}}
    self.hooks[name] = self.hooks[name] or {{}}
    table.insert(self.hooks[name], fn)
end
function {cls}:SetMouseMotionEnabled(on) self.motion = on and true or false end
function {cls}:SetMouseClickEnabled(on) self.click = on and true or false end
"""

LUA = r"""
-- GameTooltip as the spell tooltip uses it; setOwner counts every SetOwner (a double hook would show twice).
AURAS_READABLE = false
GameTooltip = { setOwner = 0 }
function GameTooltip:Reset() self.owner, self.shown, self.spellID, self.text, self.lines = nil, false, nil, nil, {} end
function GameTooltip:SetOwner(o) self:Reset(); self.owner = o; self.setOwner = self.setOwner + 1 end
function GameTooltip:GetOwner() return self.owner end
function GameTooltip:SetText(t) self.text = t end
function GameTooltip:AddLine(t) self.lines[#self.lines + 1] = t end
function GameTooltip:Show() self.shown = true end
function GameTooltip:Hide() self.shown = false; self.owner = nil end
function GameTooltip:SetSpellByID(id) self.spellID = id; self.shown = true end
GameTooltip:Reset()

function tipReset() GameTooltip:Reset(); GameTooltip.setOwner = 0 end
function tip() return GameTooltip.shown and GameTooltip or nil end

-- Loads the real helpers and copies the tooltip family onto FS.FrameHelpers (a table the harness already has).
function loadSpellTips(src)
    local X = { Theme = {}, IsSecret = FS.IsSecret or function() return false end,
        AurasReadable = function() return AURAS_READABLE end }
    local nFrames = FRAMES and #FRAMES or 0
    assert(loadstring(src, "@Core/FrameHelpers.lua"))("forever-stuwave", X)
    -- (the event frame is made lazily, on the first name lookup, so it can show up in a harness's FRAMES then)
    if FRAMES then for i = #FRAMES, nFrames + 1, -1 do FRAMES[i] = nil end end
    FS.FrameHelpers = FS.FrameHelpers or {}
    for _, k in ipairs({ "HoverOnly", "SetTipSpell", "SpellIDForName", "SpellCacheEpoch", "AttachSpellTooltip",
            "RefreshSpellTooltip", "ReleaseSpellTip", "ReleaseGatedTips", "ShowAuraTooltip" }) do
        FS.FrameHelpers[k] = X.FrameHelpers[k]
    end
    tipReset()
end

local function runHooks(f, name)
    if f.scripts and f.scripts[name] then f.scripts[name](f) end
    for _, fn in ipairs(f.hooks and f.hooks[name] or {}) do fn(f) end
end
function hover(f) runHooks(f, "OnEnter") end
function unhover(f) runHooks(f, "OnLeave") end
function hoverOnly(f) return f.motion == true and f.click == false end
"""
