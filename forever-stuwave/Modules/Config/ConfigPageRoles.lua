-- Forever STUwave: Config page, Roles
-- Registered with four tab shells (Tank, Healer, Melee, Ranged); the roles ticket (C3) fills them.

local _, FS = ...

local CW = FS.ConfigWindow

CW.RegisterCategory({
    key = "role", label = "Roles", group = "GENERAL", order = 1,
    tabs = {
        { key = "tank", label = "Tank", build = function() end },
        { key = "healer", label = "Healer", build = function() end },
        { key = "melee", label = "Melee", build = function() end },
        { key = "ranged", label = "Ranged", build = function() end },
    },
})
