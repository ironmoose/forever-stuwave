-- Forever STUwave: Config page, Unit Frames (Player, Target, Focus and Boss)
-- Frames tab: the four Show switches. The Style tab shell is filled by the Style ticket (C1).

local _, FS = ...

local CW = FS.ConfigWindow
local UI = CW.UI

CW.RegisterCategory({
    key = "unit", label = "Unit Frames", group = "FRAMES", order = 1,
    tabs = {
        { key = "frames", label = "Frames", build = function(content)
            -- Which frames this addon draws at all. Off hands that one frame back to the game's own, and leaves the rest of
            -- Unit frames, party, raid and the HUD running. Read when the frames are built, so it takes a reload.
            UI.Section(content, { title = "STUwave frames",
                tip = "Off gives that frame back to the game's own. The other frames keep the STUwave look." })
            local UF = FS.UnitFrames
            for _, f in ipairs({ { "player", "Player" }, { "target", "Target" }, { "focus", "Focus" }, { "boss", "Boss" } }) do
                local frame, name = f[1], f[2]
                local key = UF and UF.USE_KEYS and UF.USE_KEYS[frame]
                if key then
                    UI.Toggle(content, { label = "STUwave " .. name:lower() .. " frame" .. (frame == "boss" and "s" or ""), key = key,
                        reload = function()
                            local built = UF.Built and UF.Built(frame)
                            if built == nil then return nil end
                            if built ~= (FS.Config.Get(key) ~= false) then return "Reload to swap frames" end
                            return nil
                        end })
                end
            end
            UI.Section(content, { title = "Frames", tip = "A frame that is off stays click-through and invisible." })
            -- The saved keys hold a hide flag (unitFrames.hidePlayer / hideTarget): the row shows and writes the inverse,
            -- so a player who hid a frame before still sees its switch off.
            UI.Toggle(content, { label = "Show player frame", key = "unitFrames.hidePlayer", inverted = true })
            UI.Toggle(content, { label = "Show target frame", key = "unitFrames.hideTarget", inverted = true })
            UI.Toggle(content, { label = "Show focus frame", key = "unitFrames.showFocus" })
            UI.Toggle(content, { label = "Show boss frames", key = "unitFrames.showBoss" })
        end },
        { key = "bars", label = "Style", build = function(content)
            local bars = FS.ConfigBars
            if bars then bars.BuildStyleTab(content, { page = "unit", tab = "bars", frames = { "player", "target", "focus", "boss" } }) end
        end },
    },
})
