-- Forever STUwave: Questie compatibility
-- Questie draws a quest icon beside the target frame (QuestieNameplate.lua, GetTargetFrameIconFrame). It parents that
-- icon to Blizzard's TargetFrame unless it recognises another unit frame addon, and STUwave keeps Blizzard's TargetFrame
-- at alpha 0 (UnitFrames.lua, DimBlizzardFrame), so the icon would never be seen. After each target change this moves
-- Questie's icon onto ForeverSTUwaveTargetFrame, at Questie's own offsets from that frame's right edge.
--
-- Questie builds a fresh icon frame each time the previous one is dropped, and keeps no global handle to it, so it is
-- found among TargetFrame's children: an unnamed plain Frame carrying an `Icon` texture at Questie's frame level 11.
-- Adopted frames leave TargetFrame, so each is moved once. Plain frames only, nothing secure, legal in combat.

local _, FS = ...

local QC = {}
FS.QuestieCompat = QC

local QUESTIE_ICON_LEVEL = 11
local ABOVE_FRAME = 20

local function QuestieLoaded()
    local CA = _G.C_AddOns
    local isLoaded = CA and CA.IsAddOnLoaded or _G.IsAddOnLoaded
    if type(isLoaded) ~= "function" then return false end
    local ok, loaded = pcall(isLoaded, "Questie")
    return ok and loaded and true or false
end
QC.QuestieLoaded = QuestieLoaded

local function QuestieProfile()
    local q = _G.Questie
    local db = type(q) == "table" and q.db
    return type(db) == "table" and type(db.profile) == "table" and db.profile or nil
end
QC.Profile = QuestieProfile

local function IsQuestieIcon(child)
    return type(child) == "table" and child.GetObjectType and child:GetObjectType() == "Frame"
        and child:GetName() == nil and type(child.Icon) == "table" and child.Icon.SetTexture ~= nil
        and child:GetFrameLevel() == QUESTIE_ICON_LEVEL
end

local function Adopt()
    local ours, blizz = _G.ForeverSTUwaveTargetFrame, _G.TargetFrame
    if not (ours and blizz and blizz.GetChildren) then return end
    local profile = QuestieProfile()
    local x = profile and tonumber(profile.nameplateTargetFrameX) or -30
    local y = profile and tonumber(profile.nameplateTargetFrameY) or 25
    for _, child in ipairs({ blizz:GetChildren() }) do
        if IsQuestieIcon(child) then
            child:SetParent(ours)
            child:SetFrameStrata(ours:GetFrameStrata())
            child:SetFrameLevel(ours:GetFrameLevel() + ABOVE_FRAME)
            child:ClearAllPoints()
            child:SetPoint("RIGHT", ours, "RIGHT", x, y)
        end
    end
end
QC.Adopt = Adopt

local events = CreateFrame("Frame")
events:RegisterEvent("PLAYER_LOGIN")
events:SetScript("OnEvent", function(self, event)
    if event == "PLAYER_LOGIN" then
        if not QuestieLoaded() then
            self:UnregisterAllEvents()
            return
        end
        self:RegisterEvent("PLAYER_TARGET_CHANGED")
        self:RegisterEvent("QUEST_LOG_UPDATE")
        return
    end
    -- Questie draws on the same events; wait a frame so its icon exists before it is moved.
    if C_Timer and C_Timer.After then C_Timer.After(0, Adopt) else Adopt() end
end)
