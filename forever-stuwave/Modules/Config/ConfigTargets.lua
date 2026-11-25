-- Forever STUwave: which frame each setting points at
-- The target map behind the hover flash (ConfigFlash.lua): a row in /fsconfig answers "which frame on screen does this
-- change?". A row finds its frames by, in this order, its own `target` (a provider name, a function or a frame), the
-- longest key prefix in KEYS, then its page in PAGE_TARGETS. A provider is a function run when the row is hovered; it
-- answers a list of frames (or nothing when its module or frame is missing). CW.Targets.Resolve(entry) turns that into
-- rects in UIParent units for the frames that are on screen now, and nil when the row has no target at all.
-- Nothing here writes, shows, hides or anchors anything: a frame is only asked IsVisible, GetEffectiveAlpha and GetRect,
-- inside a pcall, so a protected frame in combat, a secret number or a frame with no rect yet is skipped, never an error.
-- CW.Targets.Seats(entry) also answers the frames that have a seat but are not showing (a hidden frame, alpha 0, a piece
-- that is off, a target side with no target): those rects carry `hidden = true`, a short `reason` ("Shows with a target")
-- and the `preview` key the flash can build a sample for. Resolve answers only what is showing.
-- A frame whose module is off this session (Core/ModuleSwitch.lua) or that was handed back to the game was never built, so it
-- has no frame to ask: its seat is worked out from the layout entry alone (OFF below) and answered the same way, hidden, with
-- the reason "Module is off" and the sample key, so the hover still has something to show.
-- Harness: tools/configflash-harness.py.

local _, FS = ...

local CW = FS.ConfigWindow
local Config = FS.Config

local T = {}
CW.Targets = T

-------------------------------------------------------------------------------
-- Reading a frame
-------------------------------------------------------------------------------

-- A finite plain number, or nil (a secret value is never compared).
local function Num(v)
    if FS.IsSecret and FS.IsSecret(v) then return nil end
    if type(v) ~= "number" or v ~= v or v <= -1e9 or v >= 1e9 then return nil end
    return v
end

T.GENERIC_REASON = "Hidden right now"

-- A frame's rect in UIParent units, whether or not it is showing; nil with no readable rect.
local function Measure(frame)
    local l, b, w, h = frame:GetRect()
    l, b, w, h = Num(l), Num(b), Num(w), Num(h)
    if not (l and b and w and h and w > 0 and h > 0) then return nil end
    -- GetRect is in the frame's own scale; the overlay sits on UIParent
    local scale, parentScale = 1, 1
    if type(frame.GetEffectiveScale) == "function" then scale = Num(frame:GetEffectiveScale()) or 1 end
    if UIParent and type(UIParent.GetEffectiveScale) == "function" then parentScale = Num(UIParent:GetEffectiveScale()) or 1 end
    if scale <= 0 or parentScale <= 0 then return nil end
    local k = scale / parentScale
    return { left = l * k, bottom = b * k, width = w * k, height = h * k }
end

-- True when our own frame is faded out (alpha 0). A secret or missing answer reads as not faded.
local function Faded(frame)
    local get = frame.GetEffectiveAlpha or frame.GetAlpha
    if type(get) ~= "function" then return false end
    local a = Num(get(frame))
    return a ~= nil and a <= 0
end

-- A plain table with the four fields as a rect; `place` keeps what a layout seat adds (its anchor point and the spot of it,
-- and the scale a sample is drawn at), which the flash uses to seat a sample the way the real frame is seated.
local function PlainRect(t, place)
    local l, b, w, h = Num(t.left), Num(t.bottom), Num(t.width), Num(t.height)
    if not (l and b and w and h and w > 0 and h > 0) then return nil end
    local r = { left = l, bottom = b, width = w, height = h }
    if place and type(t.point) == "string" then
        local ax, ay = Num(t.ax), Num(t.ay)
        if ax and ay then r.point, r.ax, r.ay = t.point, ax, ay end
    end
    return r
end

-- One thing a provider answered, as a rect { left, bottom, width, height } in UIParent units. A frame that is showing gives
-- the plain rect. A frame that has a rect but is not showing (hidden, faded out, or held down by `hidden`) gives the same
-- rect with `hidden = true`, `reason` and `preview` (what the provider says about why and what could stand in for it).
-- A provider may answer a wrapper { seat = frame, reason, preview, hidden, sample, fallback, scale } to say those itself.
-- `sample` (a key like `preview`) is for a frame that IS showing but may be empty (a Gunsight area with no debuffs of yours): the
-- flash puts the sample in it for the hover. `fallback` (a rect, or a function answering one) stands in for the rect of a frame
-- that is hidden and has never been laid out, so the client has none to give; a frame that is showing never takes it. `seat` may
-- itself be a plain rect (a frame that was never built, seated from the layout); `scale` is then the scale its sample is drawn at.
-- A plain table with the four fields is taken as it is (the quest tracker answers its own rect).
local function Read(thing, ctx)
    if type(thing) ~= "table" then return nil end
    local ok, rect = pcall(function()
        local frame, reason, preview, forced, sample, fallback, scale = thing, nil, nil, false, nil, nil, nil
        if thing.seat ~= nil then
            frame, reason, preview, forced, sample = thing.seat, thing.reason, thing.preview, thing.hidden == true, thing.sample
            fallback, scale = thing.fallback, Num(thing.scale)
        end
        if type(frame) ~= "table" then return nil end
        local r, hidden = nil, forced
        if type(frame.GetRect) ~= "function" then
            r = PlainRect(frame, scale ~= nil)
            if r and scale then r.scale = scale end
        else
            r = Measure(frame)
            if not hidden and type(frame.IsVisible) == "function" and frame:IsVisible() ~= true then hidden = true end
            if not hidden and Faded(frame) then hidden = true end
            if not r and hidden and fallback ~= nil then
                if type(fallback) == "function" then fallback = fallback() end
                if type(fallback) == "table" then r = PlainRect(fallback, false) end
            end
        end
        if not r then return nil end
        if hidden then
            r.hidden = true
            r.reason = reason or (ctx and ctx.reason) or T.GENERIC_REASON
            r.preview = preview or (ctx and ctx.preview) or nil
        elseif type(sample) == "string" then
            r.sample = sample
        end
        return r
    end)
    if ok then return rect end
    return nil
end

-------------------------------------------------------------------------------
-- Finding frames
-------------------------------------------------------------------------------

-- Why a seated frame is not showing, by layout id; the id is also the key of its preview (ConfigFlash.lua).
local SEAT_REASONS = {
    target = "Shows with a target", tcast = "Shows with a target",
    party = "Shows in a group", petcontainer = "Shows with a pet",
    pcast = "Shows while casting",
    warriorpowerup = "Shows on a proc", druidclearcasting = "Shows on a proc",
}
local SEAT_PREVIEWS = { player = true, target = true, focus = true, boss = true, party = true, petcontainer = true }

-- A frame that is off, or was never built: its seat from the layout entry alone. FS.Layout[id] holds the seat (the layout
-- editor writes a saved move into it in place), so the rect is what FS.Layout.Apply would have given the frame: x and y in design
-- px times the layout scale, or in plain UI units for an `unscaled` entry; the entry's `point` sits at `relPoint` of UIParent.
-- Answers { left, bottom, width, height } in UIParent units, the entry's anchor point with its spot (point, ax, ay) and the
-- scale it was worked out at (scale); nil without a usable entry or a UIParent that has a size.
local function Fractions(point)
    return point:find("LEFT") and 0 or point:find("RIGHT") and 1 or 0.5, point:find("BOTTOM") and 0 or point:find("TOP") and 1 or 0.5
end

local function SeatRect(id)
    local L = type(id) == "string" and FS.Layout and FS.Layout[id]
    if type(L) ~= "table" or type(L.point) ~= "string" or type(L.relPoint) ~= "string" then return nil end
    local x, y, w, h = Num(L.x), Num(L.y), Num(L.w), Num(L.h)
    if not (x and y and w and h and w > 0 and h > 0) then return nil end
    local pw = UIParent and type(UIParent.GetWidth) == "function" and Num(UIParent:GetWidth())
    local ph = UIParent and type(UIParent.GetHeight) == "function" and Num(UIParent:GetHeight())
    if not (pw and ph and pw > 0 and ph > 0) then return nil end
    local scale = 1
    if L.unscaled ~= true and type(FS.Layout.Scale) == "function" then scale = Num(FS.Layout.Scale()) or 1 end
    if scale <= 0 then return nil end
    local rx, ry = Fractions(L.relPoint)
    local ax, ay = pw * rx + x * scale, ph * ry + y * scale
    local fx, fy = Fractions(L.point)
    local width, height = w * scale, h * scale
    return { left = ax - width * fx, bottom = ay - height * fy, width = width, height = height,
        point = L.point, ax = ax, ay = ay, scale = scale }
end

T.OFF_REASON = "Module is off"
T.PENDING_REASON = "Off until a Reload UI"
T.GAME_REASON = "Uses the game's frame"
T.SWITCH_REASON = "Turned off"

-- The seat of the raid grid is the one of the size the Raid page's layout size shows (RaidFrames.Preview.SeatId).
local function RaidSeatId()
    local raid = FS.RaidFrames
    local pv = type(raid) == "table" and raid.Preview
    if type(pv) == "table" and type(pv.SeatId) == "function" then
        local ok, id = pcall(pv.SeatId)
        if ok and type(id) == "string" then return id end
    end
    return "raid10"
end

-- The frames a power switch (or a "STUwave frame" switch) can leave unbuilt, by the id their provider seats them under:
-- `module` the Core/ModuleSwitch.lua key that builds it, `use` the unit frame the Unit Frames page can hand back to the game,
-- `layout` the Layout.lua entry it sits at (the id itself when none is named; a function for the raid, whose seat follows a
-- size), `preview` the key of the sample the flash can build (none: the dimmed outline says why), and `draw` what the sample is
-- drawn in: "ui" the UI units the frame is built in (the unit frames, the raid grid, already scaled), "design" the design px of
-- the pet panel (times the layout scale), none the party stack, fitted to the width of the seat as the real container's is.
local OFF = {
    player = { module = "m.uf", use = "player", preview = "player", draw = "ui" },
    target = { module = "m.uf", use = "target", preview = "target", draw = "ui" },
    focus = { module = "m.uf", use = "focus", preview = "focus", draw = "ui" },
    boss = { module = "m.uf", use = "boss", preview = "boss", draw = "ui" },
    party = { module = "m.party", preview = "party" },
    petcontainer = { module = "m.pet", preview = "petcontainer", draw = "design" },
    raid = { module = "m.raid", layout = RaidSeatId, preview = "raid.sample", draw = "ui" },
    grid = { module = "m.ab" },
    databar = { module = "m.data" },
}
T.OFF_SEATS = OFF

-- Why a frame has none built this session, or nil when nothing says so: its module is off in this session (and the store
-- says off, or says on and waits for a Reload UI), or the Unit Frames page handed the frame back to the game.
local function OffReason(spec)
    local MS = FS.ModuleSwitch
    if spec.module and type(MS) == "table" and type(MS.On) == "function" and MS.On(spec.module) == false then
        local wanted = type(MS.Wanted) == "function" and MS.Wanted(spec.module) == true
        return wanted and T.PENDING_REASON or T.OFF_REASON
    end
    local UF = FS.UnitFrames
    if spec.use and type(UF) == "table" and type(UF.Built) == "function" and UF.Built(spec.use) == false then
        return T.GAME_REASON
    end
    return nil
end

-- The answer for a frame that was never built, as a wrapper Read understands; nil when it is built (or may yet be) or the
-- layout has no seat for it.
local function OffSeat(id)
    local spec = OFF[id]
    if not spec then return nil end
    local reason = OffReason(spec)
    if not reason then return nil end
    local layout = spec.layout
    if type(layout) == "function" then layout = layout() end
    local rect = SeatRect(layout or id)
    if not rect then return nil end
    local scale = spec.draw == "ui" and 1 or spec.draw == "design" and rect.scale or nil
    return { { seat = rect, hidden = true, reason = reason, preview = spec.preview, scale = scale } }
end

-- Frames that can be hidden by a switch of their own: when it is off that, not the group or the target, is why they are empty.
local function Setting(key, want)
    local Config = FS.Config
    if not (Config and Config.Get) then return false end
    local ok, v = pcall(Config.Get, key)
    return ok and v == want
end

local SEAT_SWITCH = {
    player = function() return Setting("unitFrames.hidePlayer", true) end,
    target = function() return Setting("unitFrames.hideTarget", true) end,
    focus = function() return Setting("unitFrames.showFocus", false) end,
    boss = function() return Setting("unitFrames.showBoss", false) end,
    party = function()
        local party = FS.PartyFrames
        return type(party) == "table" and type(party.IsShown) == "function" and party.IsShown() == false
    end,
}

-- The frame a layout id is seated on (FS.Layout._applied), a shown one when there are several. A frame that was never built
-- (its module is off) answers its layout seat instead (OffSeat); nothing when there is neither.
local function Seat(id)
    return function()
        local applied = FS.Layout and FS.Layout._applied
        local found
        if type(applied) == "table" then
            for frame, info in pairs(applied) do
                if type(info) == "table" and info.id == id and info.parent == nil then
                    local ok, shown = pcall(frame.IsShown, frame)
                    if ok and shown == true then found = frame; break end
                    found = found or frame
                end
            end
        end
        if not found then return OffSeat(id) end
        local reason = SEAT_REASONS[id]
        local switch = SEAT_SWITCH[id]
        if switch then
            local ok, off = pcall(switch)
            if ok and off == true then reason = T.SWITCH_REASON end
        end
        return { { seat = found, reason = reason, preview = SEAT_PREVIEWS[id] and id or nil,
            fallback = function() return SeatRect(id) end } }
    end
end

-- A global frame by name, looked up when asked (a module that is absent or builds later answers nothing, then the frame).
local function Named(name, reason, preview)
    return function()
        local frame = _G[name]
        if type(frame) == "table" then
            if reason or preview then return { { seat = frame, reason = reason, preview = preview } } end
            return { frame }
        end
        return nil
    end
end

-- Every answer of these providers, in order.
local function All(...)
    local list = { ... }
    return function()
        local out = {}
        for _, provider in ipairs(list) do
            local got = provider()
            if type(got) == "table" then
                for _, frame in ipairs(got) do out[#out + 1] = frame end
            end
        end
        return out
    end
end

-- The first provider that answers something.
local function First(...)
    local list = { ... }
    return function()
        for _, provider in ipairs(list) do
            local got = provider()
            if type(got) == "table" and #got > 0 then return got end
        end
        return nil
    end
end

-- Gunsight anchor frames by name. `piece` (optional) is the piece switch that must be on for them to be drawn; the HUD must
-- be up at all. The anchors are plain frames that stay "shown" with their piece faded out, so the switches are asked here,
-- and the target side only shows while there is a target. An anchor that is not drawn is still answered, marked hidden with
-- the reason, so the flash can say why it is empty.
local TARGET_SIDE = { tapeR = true, boxR = true, areaU = true, areaL = true }
-- The two target side areas: what each holds is `gunsight.target.upper` / `.lower`, and the sample the flash puts in one is
-- keyed `gs.upper` / `gs.lower` (GunsightAreas.Preview). An area set to Empty has nothing to sample.
local AREA_OF = { areaU = "upper", areaL = "lower" }

local function AreaIsEmpty(area)
    local G = FS.Gunsight
    if type(G) ~= "table" or type(G.GetArea) ~= "function" then return false end
    local ok, id = pcall(G.GetArea, area)
    return ok and id == "empty"
end

local function HasTarget()
    if type(FS.HasTarget) ~= "function" then return true end
    local ok, has = pcall(FS.HasTarget)
    return not ok or has ~= false
end

local function Anchors(piece, ...)
    local names = { ... }
    return function()
        local G = FS.Gunsight
        if type(G) ~= "table" or type(G.anchors) ~= "table" then return nil end
        local reason
        if type(G.IsActive) == "function" then
            local ok, active = pcall(G.IsActive)
            if ok and active ~= true then reason = "Turned off" end
        end
        if not reason and piece and type(G.IsPieceOn) == "function" then
            local ok, on = pcall(G.IsPieceOn, piece)
            if ok and on == false then reason = "Turned off" end
        end
        local noTarget = not reason and not HasTarget()
        local out = {}
        for _, name in ipairs(names) do
            local frame = G.anchors[name]
            local area = AREA_OF[name]
            if frame then
                if reason then
                    out[#out + 1] = { seat = frame, hidden = true, reason = reason }
                elseif area and AreaIsEmpty(area) then
                    out[#out + 1] = { seat = frame, hidden = true, reason = "Set to Empty" }
                elseif noTarget and TARGET_SIDE[name] then
                    out[#out + 1] = { seat = frame, hidden = true, reason = "Shows with a target",
                        preview = area and ("gs." .. area) or "gs.target" }
                elseif area then
                    out[#out + 1] = { seat = frame, sample = "gs." .. area }
                else
                    out[#out + 1] = frame
                end
            end
        end
        return out
    end
end

-------------------------------------------------------------------------------
-- Providers
-------------------------------------------------------------------------------

local P = {}
T.PROVIDERS = P

-- Unit frames, party, raid, pet dock
P.player = Seat("player")
P.target = Seat("target")
P.focus = Seat("focus")
P.boss = Seat("boss")
P.party = First(Seat("party"), Named("ForeverSTUwavePartyContainer", "Shows in a group", "party"))
P.raid = First(Named("ForeverSTUwaveRaidContainer", "Shows in a raid", "raid"), function() return OffSeat("raid") end)
P.pet = First(Seat("petcontainer"), Named("FSPetContainer", "Shows with a pet", "petcontainer"))

-- The Style tabs of the Unit Frames page share their rows between the four unit frames: the picker says which one.
local STYLE_FRAMES = { player = true, target = true, focus = true, boss = true }
function P.bars()
    local picked = Config and Config.Get and Config.Get("bars.module")
    if not STYLE_FRAMES[picked] then picked = "player" end
    return P[picked]()
end

-- Cast bars: the standalone bars (Stack A) and the Gunsight's own, whichever is up
P.pcast = Seat("pcast")
P.tcast = Seat("tcast")
P.castbars = All(Seat("pcast"), Seat("tcast"), Anchors(nil, "tapeL", "tapeR"))

-- The nameplate of the unit you are targeting: our plate root on it
function P.plate()
    local frames = FS.framesByUnit
    if type(frames) ~= "table" or type(UnitIsUnit) ~= "function" then return nil end
    for unit, root in pairs(frames) do
        local ok, is = pcall(UnitIsUnit, unit, "target")
        if ok and not (FS.IsSecret and FS.IsSecret(is)) and is == true then return { root } end
    end
    return nil
end

-- Gunsight HUD pieces
P["gs.hud"] = Anchors(nil, "tapeL", "tapeR", "boxL", "boxR")
P["gs.you"] = Anchors("you", "tapeL")
P["gs.tgt"] = Anchors("tgt", "tapeR")
P["gs.next"] = Anchors("next", "next")
P["gs.shards"] = Anchors("shard", "shards")
P["gs.buff"] = Anchors("buff", "buff")
P["gs.procs"] = Anchors("prc", "procL", "procR")
P["gs.mybuffs"] = Anchors("mybuffs", "mybuffs")
P["gs.areas"] = Anchors("dot", "areaU", "areaL")
P["gs.upper"] = Anchors(nil, "areaU")
P["gs.lower"] = Anchors(nil, "areaL")
P["gs.boxR"] = Anchors(nil, "boxR")

-- The class module is whichever target side area the area dropdowns gave it.
P["gs.class"] = function()
    local G = FS.Gunsight
    if type(G) ~= "table" or type(G.GetArea) ~= "function" then return nil end
    local out = {}
    for _, area in ipairs({ { "upper", "areaU" }, { "lower", "areaL" } }) do
        local ok, id = pcall(G.GetArea, area[1])
        if ok and id == "class" then
            local got = Anchors(nil, area[2])()
            if got then out[#out + 1] = got[1] end
        end
    end
    return out
end

P.warriorpowerup = First(Seat("warriorpowerup"), Named("ForeverSTUwaveWarriorPowerUps"))
P.druidclearcasting = First(Seat("druidclearcasting"), Named("ForeverSTUwaveDruidClearcasting"))

-- Class tabs on the Console's shoulder: each is a named host frame
P.regen = Named("FSFiveSecondTab")
P.ammo = Named("FSAmmoTab")
P.bufftab = Named("FSBuffTab")
P.thunderclap = Named("FSThunderClapTab")
P.totem1 = Named("FSTotemButton7")
P.totem2 = Named("FSTotemButton8")
P.totems = All(P.totem1, P.totem2)
P.forms = Named("FSShapeshiftTab")
P.callpet = Named("FSCallPetTab")
P.portals = Named("FSPortalsTab")
P.conjure = Named("FSConjureTab")
P.poisons = Named("FSPoisonsTab")
P.demons = Named("FSDemonTab")
P.classtabs = All(P.regen, P.ammo, P.bufftab, P.thunderclap, P.forms, P.callpet, P.portals, P.conjure, P.poisons, P.demons)

-- Screen pieces
P.console = Named("FSConsole")
P.grid = First(Named("FSActionGrid"), function() return OffSeat("grid") end)
P.micro = Named("ForeverSTUwaveMicroBar")
P.buffs = All(First(Seat("buffs"), Named("ForeverSTUwaveBuffsContainer")), First(Seat("debuffs"), Named("ForeverSTUwaveDebuffsContainer")))
P.databar = First(Named("ForeverSTUwaveDataBar"), function() return OffSeat("databar") end)
P.minimap = First(Named("Minimap"), Seat("minimap"))
P.chat = First(Seat("chat"), Named("ChatFrame1"))
P.professions = First(Seat("professions"), Named("ForeverSTUwaveProfessions"))
P.character = Named("CharacterFrame")
P.talents = First(Named("PlayerTalentFrame"), Named("TalentFrame"))
P.damagemeter = Named("DamageMeter")

-- The quest tracker answers its own rect (left, top, width, height in UIParent units), the way the layout editor reads it.
function P.tracker()
    local seat = FS.TrackerSeat
    if type(seat) == "table" and type(seat.Rect) == "function" then
        local ok, left, top, width, height = pcall(seat.Rect)
        left, top, width, height = Num(left), Num(top), Num(width), Num(height)
        if ok and left and top and width and height then
            return { { left = left, bottom = top - height, width = width, height = height } }
        end
        return nil
    end
    return Named("ObjectiveTrackerFrame")()
end

-- Bags are only on screen while one is open
function P.bags()
    local out = {}
    for i = 1, 13 do
        local frame = _G["ContainerFrame" .. i]
        if type(frame) == "table" then out[#out + 1] = frame end
    end
    local combined = _G.ContainerFrameCombinedBags
    if type(combined) == "table" then out[#out + 1] = combined end
    return out
end

-------------------------------------------------------------------------------
-- The map: key prefixes, then pages
-------------------------------------------------------------------------------

-- { key prefix, provider }. The longest prefix that starts the row's key wins.
local KEYS = {
    { "unitFrames.hidePlayer", "player" }, { "unitFrames.hideTarget", "target" },
    { "unitFrames.showFocus", "focus" }, { "unitFrames.showBoss", "boss" },
    { "unitFrames.usePlayer", "player" }, { "unitFrames.useTarget", "target" },
    { "unitFrames.useFocus", "focus" }, { "unitFrames.useBoss", "boss" },
    { "professions.shown", "professions" }, { "character.backdrop", "character" }, { "talents.backdrop", "talents" },
    { "skins.damageMeterRows", "damagemeter" },
    { "actionbars.grid", "grid" }, { "icons.microstyle", "micro" }, { "icons.spellstyle", "classtabs" },
    { "nameplates.", "plate" },
    { "fivesecond.", "regen" }, { "ammotab.", "ammo" }, { "thunderclap.", "thunderclap" }, { "buffs.combatstate", "bufftab" },
    { "totems.dialPlate", "totems" }, { "totems.dial", "totem1" }, { "totems.gnarly", "totem2" },
    { "tabs.druid.", "forms" }, { "tabs.hunter.", "callpet" }, { "tabs.mage.conjure", "conjure" },
    { "tabs.mage.", "portals" }, { "tabs.rogue.", "poisons" }, { "tabs.warlock.", "demons" },
    { "gunsight.enabled", "gs.hud" },
    { "gunsight.pieces.you", "gs.you" }, { "gunsight.pieces.tgt", "gs.tgt" }, { "gunsight.pieces.next", "gs.next" },
    { "gunsight.pieces.shard", "gs.shards" }, { "gunsight.pieces.buff", "gs.buff" }, { "gunsight.pieces.prc", "gs.procs" },
    { "gunsight.pieces.mybuffs", "gs.mybuffs" }, { "gunsight.pieces.dot", "gs.areas" },
    { "gunsight.area.upper", "gs.upper" }, { "gunsight.area.lower", "gs.lower" },
    { "gunsight.tags.", "gs.boxR" }, { "gunsight.targetBars.", "gs.boxR" }, { "gunsight.target.keepfallen", "gs.areas" },
    { "gunsight.classModule.", "gs.class" }, { "gunsight.warlock.", "gs.class" }, { "gunsight.priest.", "gs.class" },
    { "gunsight.hunter.", "gs.class" },
    { "gunsight.warrior.powerup", "warriorpowerup" }, { "gunsight.druid.clearcasting", "druidclearcasting" },
    { "chat.", "chat" }, { "minimap.", "minimap" }, { "tracker.", "tracker" },
}
table.sort(KEYS, function(a, b)
    if #a[1] ~= #b[1] then return #a[1] > #b[1] end
    return a[1] < b[1]
end)

-- Rows of these pages that no key rule names stand for the page's frame. The style rows of the other lanes (bars.*,
-- plates.*, databar.*) land here, so they follow their page without this file knowing their keys.
local PAGE_TARGETS = {
    unit = "bars", party = "party", raid = "raid", pet = "pet", cast = "castbars", plates = "plate", ab = "console",
    auras = "buffs", bags = "bags", mini = "minimap", chat = "chat", track = "tracker", data = "databar",
}

-- The key prefixes and the pages this map knows (the harness checks each against the addon).
function T.Prefixes()
    local out = {}
    for i, rule in ipairs(KEYS) do out[i] = rule[1] end
    return out
end

function T.Pages()
    local out = {}
    for page in pairs(PAGE_TARGETS) do out[#out + 1] = page end
    table.sort(out)
    return out
end

local function Starts(key, prefix)
    return type(key) == "string" and key:sub(1, #prefix) == prefix
end

-- The provider names and functions for a row, or nil when the row changes no frame.
local function Pick(entry)
    if type(entry) ~= "table" then return nil end
    local own = entry.target
    if type(own) == "string" and P[own] then return { own }, { P[own] } end
    if type(own) == "function" then return { "custom" }, { own } end
    if type(own) == "table" then return { "custom" }, { function() return { own } end } end
    for _, rule in ipairs(KEYS) do
        if Starts(entry.key, rule[1]) or Starts(entry.cfgKey, rule[1]) then return { rule[2] }, { P[rule[2]] } end
    end
    local page = PAGE_TARGETS[entry.page]
    if page and P[page] then return { page }, { P[page] } end
    return nil
end

-- The provider names a row maps to (nil for a row that changes no frame).
function T.Providers(entry)
    local names = Pick(entry)
    return names
end

-- Switches that are the row's own: a row whose key is one of these (or ends in .enabled) and is off gives "Turned off".
local OWN_SWITCH = { ["unitFrames.showFocus"] = true, ["unitFrames.showBoss"] = true }
local function OwnSwitchOff(entry)
    local key = entry.key
    if type(key) ~= "string" or not (OWN_SWITCH[key] or key:sub(-8) == ".enabled") then return false end
    if not (Config and Config.Get) then return false end
    local ok, v = pcall(Config.Get, key)
    return ok and v == false
end

-- Every frame of a row that has a seat, as rects { left, bottom, width, height } in UIParent units: the ones on screen now
-- plain, the ones that are not carry hidden = true, reason (short, shown to the player) and preview (a key, or nil). nil:
-- the row has no target. An empty list: it has one and none of it has a seat to draw at.
function T.Seats(entry)
    local names, fns = Pick(entry)
    if not fns then return nil end
    local off = OwnSwitchOff(entry)
    local out = {}
    for i, fn in ipairs(fns) do
        local ok, list = pcall(fn, entry)
        if ok and type(list) == "table" then
            if list[1] == nil and (type(list.GetRect) == "function" or list.left ~= nil or list.seat ~= nil) then list = { list } end
            for _, thing in ipairs(list) do
                local rect = Read(thing, { reason = nil, preview = nil, name = names[i] })
                if rect then
                    if off then rect.hidden, rect.reason, rect.preview = true, "Turned off", nil end
                    out[#out + 1] = rect
                end
            end
        end
    end
    return out
end

-- The frames of a row that are on screen now. nil: the row has no target. An empty list: it has one and nothing of it is
-- on screen right now.
function T.Resolve(entry)
    local seats = T.Seats(entry)
    if not seats then return nil end
    local out = {}
    for _, rect in ipairs(seats) do
        if not rect.hidden then out[#out + 1] = rect end
    end
    return out
end
