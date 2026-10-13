-- Forever STUwave: Gunsight target side areas (the dot piece) and the module registry that fills them.
--
-- Two host frames, upper and lower, hang off the dot piece frame at the areaU and areaL rects.
-- Modules register under "debuffsH", "debuffsV", "class" or "classSoon" (the class module is chosen by class token)
-- and are built on first use. "classSoon" is the fallback for "class": the area shows it when the player's class has
-- no class module, so a class that later registers one stops showing it with no further change. A Target Debuffs
-- host follows FS.TargetTakesDots. VISIBILITY RULE: everything in these areas sits on the target side, so with no target
-- it is hidden like the target box and cast bar. A class module (and the coming soon plate) follows FS.HasTarget: the
-- host hides, and the module's onHide / onShow fire on that edge so it stops and restarts its events and OnUpdate (a
-- hidden host alone would leave them running). FS.HasTarget reads a secret or unreadable answer as "has one". A Target
-- Debuffs host hides on FS.TargetTakesDots with no hook, so the Hud ledger keeps running. A module that needs more
-- (a combo module also wants a hostile target) gates itself inside its own frame. No module is exempt; there is no
-- showWithoutTarget opt-in because no module has recorded approval to show with no target.

local _, FS = ...

local Gunsight = FS.Gunsight
if not (Gunsight and Gunsight.G and Gunsight.RegisterPiece and Gunsight.GetArea and Gunsight.OnReady) then return end

FS.GunsightAreas = FS.GunsightAreas or {}
local Areas = FS.GunsightAreas

local G = Gunsight.G
local ui, Point = Gunsight.ui, Gunsight.Point

local PREFIX = "|cffff4488Forever STUwave|r: gunsight areas: "
local MODULE_IDS = { debuffsH = true, debuffsV = true, class = true, classSoon = true }
local GATED = { debuffsH = true, debuffsV = true }     -- hidden while FS.TargetTakesDots() is false
local NEEDS_TARGET = { class = true, classSoon = true }  -- hidden while FS.HasTarget() is false; onShow / onHide fire on the edge
local AREA_NAMES = { "upper", "lower" }

local records = {}        -- id -> record, for debuffsH, debuffsV and classSoon
local classRecords = {}   -- one record per class spec
local hosts = {}          -- area -> host frame (nil until built)
local rects = {}          -- area -> { x, y, w, h } in image px, one table reused for every seat call
local hostOn = {}         -- area -> whether the host is shown
local occupant = {}       -- area -> the record shown there
local changedCallbacks = {}
local pieceFrame, built, lastSnapshot, classToken

local function LogOnce(key, msg)
    if FS.LogDegradeOnce then pcall(FS.LogDegradeOnce, "gunsight_areas_" .. key, PREFIX .. tostring(msg)) end
end

local function Safe(key, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok then LogOnce(key, key .. " failed: " .. tostring(err)) end
    return ok
end

local function ClassToken()
    if classToken then return classToken end
    if type(UnitClass) ~= "function" then return nil end
    local ok, _, token = pcall(UnitClass, "player")
    if ok and not (FS.IsSecret and FS.IsSecret(token)) and type(token) == "string" and token ~= "" then
        classToken = token
    end
    return classToken
end

local function HasClass(record, token)
    for _, c in ipairs(record.classes) do
        if c == token then return true end
    end
    return false
end

-- The record that answers for a module id: the registered one, or for "class" the spec listing the player's class.
local function RecordFor(id)
    if id == "class" then
        local token = ClassToken()
        if not token then return nil end
        for _, record in ipairs(classRecords) do
            if HasClass(record, token) then return record end
        end
        return nil
    end
    return records[id]
end

-- The record an area set to this module id draws: RecordFor, or for "class" with a readable class token that no
-- class spec lists, the classSoon fallback. AreaOf deliberately skips the fallback (it answers "is a real module shown").
local function RecordToShow(id)
    local record = RecordFor(id)
    if record or id ~= "class" or not ClassToken() then return record end
    return records.classSoon
end

local function AllRecords()
    local list = {}
    for _, record in pairs(records) do list[#list + 1] = record end
    for _, record in ipairs(classRecords) do list[#list + 1] = record end
    return list
end

local function TakesTarget()
    if type(FS.TargetTakesDots) ~= "function" then return true end
    local ok, want = pcall(FS.TargetTakesDots)
    return not ok or want ~= false
end

-- FS.HasTarget reads a secret or unreadable UnitExists as "has one", so a guess never hides the plate.
local function HasTarget()
    if type(FS.HasTarget) ~= "function" then return true end
    local ok, has = pcall(FS.HasTarget)
    return not ok or has ~= false
end

local function SeatHost(area)
    local rect = rects[area]
    Point(hosts[area], "TOPLEFT", rect.x, rect.y)
    hosts[area]:SetSize(ui(rect.w), ui(rect.h))
end

local function SeatRecord(record)
    local seat = record.spec.seat
    if seat and record.shown then Safe("seat " .. record.id, seat, rects[record.shown]) end
end

local function SeatAll()
    for _, area in ipairs(AREA_NAMES) do SeatHost(area) end
    for _, record in ipairs(AllRecords()) do SeatRecord(record) end
end

-- A target gated record's onShow / onHide follow the host (record.live), not the area: they fire when the host comes up
-- or goes down, so a module with no target is stopped. Everything else fires them as it takes or leaves an area.
local function RunHook(record, name, area)
    local hook = record.spec[name]
    if hook then Safe(name .. " " .. record.id, hook, area) end
end

-- Runs on every target health event, so it allocates nothing (until a hook fires). Returns true when a target gated
-- record went up or down, so a listener that depends on "is the module on screen right now" can re-render.
local function ApplyHosts()
    local flipped = false
    for _, area in ipairs(AREA_NAMES) do
        local record = occupant[area]
        local want = record ~= nil and (not GATED[record.id] or TakesTarget()) and (not NEEDS_TARGET[record.id] or HasTarget())
        if hostOn[area] ~= want then
            hostOn[area] = want
            if want then hosts[area]:Show() else hosts[area]:Hide() end
        end
        if record and NEEDS_TARGET[record.id] and record.live ~= want then
            record.live = want
            flipped = true
            RunHook(record, want and "onShow" or "onHide", area)
        end
    end
    return flipped
end

local function HideRecord(record)
    local area = record.shown
    if not area then return end
    record.shown = nil
    occupant[area] = nil
    if not NEEDS_TARGET[record.id] or record.live then RunHook(record, "onHide", area) end
    record.live = nil
    if record.frame then record.frame:Hide() end
end

local function ShowRecord(record, area)
    if not record.frame then
        if record.failed then return end
        local ok, frame = pcall(record.spec.build, hosts[area])
        if not (ok and type(frame) == "table") then
            record.failed = true
            LogOnce("build " .. record.id, "build " .. record.id .. " failed: " .. tostring(ok and "no frame returned" or frame))
            return
        end
        record.frame = frame
    end
    if record.frame:GetParent() ~= hosts[area] then record.frame:SetParent(hosts[area]) end
    record.shown = area
    occupant[area] = record
    SeatRecord(record)
    record.frame:Show()
    -- a target gated record starts from ApplyHosts, once its host is up
    if NEEDS_TARGET[record.id] then record.live = false else RunHook(record, "onShow", area) end
end

-- Which module id each area shows. The lower area yields when both name one family (one frame per module).
local function Wanted()
    local upper, lower = Gunsight.GetArea("upper"), Gunsight.GetArea("lower")
    local family = Gunsight.AreaFamily(lower)
    if family and family == Gunsight.AreaFamily(upper) then lower = nil end
    return { upper = upper, lower = lower }
end

local function Snapshot()
    local upper, lower = occupant.upper, occupant.lower
    return (upper and upper.id or "") .. "/" .. (lower and lower.id or "")
end

local function Refresh(force)
    if not built then return end
    local want = {}
    if Gunsight.IsPieceOn("dot") then
        local wanted = Wanted()
        for _, area in ipairs(AREA_NAMES) do
            local record = wanted[area] and RecordToShow(wanted[area])
            if record then want[record] = area end
        end
    end
    local list = AllRecords()
    for _, record in ipairs(list) do
        if record.shown and record.shown ~= want[record] then HideRecord(record) end
    end
    for _, record in ipairs(list) do
        if want[record] and record.shown ~= want[record] then ShowRecord(record, want[record]) end
    end
    local flipped = ApplyHosts()
    local snapshot = Snapshot()
    if force or flipped or snapshot ~= lastSnapshot then
        lastSnapshot = snapshot
        for _, fn in ipairs(changedCallbacks) do Safe("OnAreaChanged callback", fn) end
    end
end

-- spec = { build = function(host) return frame end, seat = function(rect), onShow = function(area),
-- onHide = function(area), classes = { "PALADIN" } }; classes is required for "class" only. "classSoon" takes the
-- same spec without classes.
function Areas.RegisterModule(id, spec)
    if not MODULE_IDS[id] then
        LogOnce("badid " .. tostring(id), "RegisterModule: unknown module id " .. tostring(id))
        return false
    end
    if type(spec) ~= "table" or type(spec.build) ~= "function" then
        LogOnce("badspec " .. id, "RegisterModule(" .. id .. "): a spec needs a build function")
        return false
    end
    local record = { id = id, spec = spec }
    if id == "class" then
        if type(spec.classes) ~= "table" or #spec.classes == 0 then
            LogOnce("badclasses", "RegisterModule(class): a spec needs a classes list")
            return false
        end
        record.classes = spec.classes
        for i = #classRecords, 1, -1 do
            local old = classRecords[i]
            for _, c in ipairs(spec.classes) do
                if HasClass(old, c) then
                    HideRecord(old)
                    table.remove(classRecords, i)
                    break
                end
            end
        end
        classRecords[#classRecords + 1] = record
    else
        if records[id] then HideRecord(records[id]) end
        records[id] = record
    end
    Refresh(false)
    return true
end

-- "upper", "lower", or nil when the module is not shown (not in an area, the dot piece off, or no spec for
-- this class). A host hidden for want of a target still reports its area, unless live is true: then the answer is nil
-- while the host is hidden, for a caller that draws something else when the module is not on screen.
function Areas.AreaOf(id, live)
    if not MODULE_IDS[id] then return nil end
    local record = RecordFor(id)
    local area = record and record.shown or nil
    if live and area and not hostOn[area] then return nil end
    return area
end

-- fn() runs after an area assignment, a registration, the dot piece, or a class host's target gate changes what an area shows.
function Areas.OnAreaChanged(fn)
    if type(fn) == "function" then changedCallbacks[#changedCallbacks + 1] = fn end
end

function Areas.Host(area)
    return hosts[area]
end

Gunsight.OnAreaChanged(function() Refresh(true) end)

-- A gate edge of a class host tells the listeners; Refresh does the same itself, so it calls ApplyHosts directly.
local function OnTargetEvent()
    if ApplyHosts() then
        for _, fn in ipairs(changedCallbacks) do Safe("OnAreaChanged callback", fn) end
    end
end

local function BuildFrames()
    pieceFrame = CreateFrame("Frame", "ForeverSTUwaveGunsightTargetSide", Gunsight.root)
    pieceFrame:SetSize(1, 1)
    pieceFrame:SetPoint("CENTER", Gunsight.root, "CENTER", 0, 0)
    local names = { upper = "ForeverSTUwaveGunsightAreaUpper", lower = "ForeverSTUwaveGunsightAreaLower" }
    rects.upper = { x = G.AREA.x, y = G.AREA.upperY, w = G.AREA.w, h = G.AREA.h }
    rects.lower = { x = G.AREA.x, y = G.AREA.lowerY, w = G.AREA.w, h = G.AREA.h }
    for _, area in ipairs(AREA_NAMES) do
        hosts[area] = CreateFrame("Frame", names[area], pieceFrame)
        hosts[area]:Hide()
        hostOn[area] = false
    end
    local events = CreateFrame("Frame", nil, pieceFrame)
    events:RegisterEvent("PLAYER_TARGET_CHANGED")
    events:RegisterEvent("PLAYER_ENTERING_WORLD")
    events:SetScript("OnEvent", OnTargetEvent)
    local unitEvents = CreateFrame("Frame", nil, pieceFrame)
    for _, name in ipairs({ "UNIT_HEALTH", "UNIT_FLAGS", "UNIT_FACTION" }) do
        if unitEvents.RegisterUnitEvent then pcall(unitEvents.RegisterUnitEvent, unitEvents, name, "target") end
    end
    unitEvents:SetScript("OnEvent", OnTargetEvent)
end

local function Build()
    if built or not Gunsight.IsEnabled() then return end
    if not Safe("build", BuildFrames) then return end
    Areas.frame = pieceFrame
    built = true
    SeatAll()
    if FS.Layout and FS.Layout.OnRescale then FS.Layout.OnRescale(SeatAll) end
    local function onPiece() Refresh(false) end
    Gunsight.RegisterPiece("dot", { frame = pieceFrame, onShow = onPiece, onHide = onPiece })
    Refresh(false)
end

Gunsight.OnReady(Build)
