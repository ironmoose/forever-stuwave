#!/usr/bin/env python3
"""/fsperf (Modules/Diagnostics/Hitch.lua) against the real Lua with a scripted clock and CPU counters.

  * with profiling off it turns it on and asks for a /reload, and turns it off again when the sample ends;
  * per frame CPU is the difference of the cumulative counters, and a slow frame keeps its top addons;
  * a heap that shrank in a slow frame is counted;
  * the sample ends on time, removes its OnUpdate and saves ForeverSTUwaveDB.hitch sorted by CPU in slow frames.

    python3 tools/hitch-harness.py

Exit 0 = every check passed.
"""
from __future__ import annotations

import sys
from pathlib import Path

from lupa import LuaRuntime

HERE = Path(__file__).resolve().parent
SRC = (HERE.parent / "forever-stuwave/Modules/Diagnostics/Hitch.lua").read_text(encoding="utf-8")

STUBS = r"""
__now, __cvar, __cpu, __heap, __said = 100, "0", { A = 0, B = 0 }, 1000, {}
function GetTime() return __now end
function GetCVar() return __cvar end
function SetCVar(_, v) __cvar = v; return true end
function UpdateAddOnCPUUsage() end
function GetAddOnCPUUsage(n) return __cpu[n] end
function GetUnitSpeed() return __speed end
__speed = 7
function date() return "now" end
local realgc = collectgarbage
function collectgarbage(op) if op == "count" then return __heap end return realgc(op) end
C_AddOns = {
    GetNumAddOns = function() return 3 end,
    GetAddOnInfo = function(i) return ({ "A", "B", "Off" })[i] end,
    IsAddOnLoaded = function(n) return n ~= "Off" end,
}
DEFAULT_CHAT_FRAME = { AddMessage = function(_, m) __said[#__said + 1] = m end }
SlashCmdList = {}
function CreateFrame()
    return { scripts = {}, SetScript = function(self, n, fn) self.scripts[n] = fn end,
        RegisterAllEvents = function(self) self.all = true end, UnregisterAllEvents = function(self) self.all = false end }
end
__fa = { GetDebugName = function() return "TrackerEvents" end, GetScript = function(_, n) return n == "OnEvent" or nil end }
__fb = { GetDebugName = function() return "Quiet" end, GetScript = function() return nil end }
__fcpu = { [__fa] = 10, [__fb] = 5 }
function EnumerateFrames(f) if f == nil then return __fa elseif f == __fa then return __fb end return nil end
function GetFrameCPUUsage(f) return __fcpu[f] end
FS = { IsSecret = function(v) return v == "SECRET" end }
"""

CHECKS = r"""
local function check(ok, msg) if not ok then error(msg, 2) end end
local H = FS.Hitch
SlashCmdList.FSPERF("")
check(H.run == nil and __cvar == "1" and __said[1]:find("/reload, then /fsperf", 1, true), "turns profiling on and asks for a reload")
SlashCmdList.FSPERF("10")
check(H.run and #H.run.names == 2, "samples the loaded addons only")
local f = H.frame.scripts.OnUpdate
local function frame(dt, a, b, heap)
    __now = __now + dt; __cpu.A = __cpu.A + a; __cpu.B = __cpu.B + b; __heap = heap or __heap
    f(H.frame, dt)
end
frame(0.008, 1, 1); frame(0.008, 1, 1); frame(0.008, 1, 1)
H.events.scripts.OnEvent(H.events, "BAG_UPDATE"); H.events.scripts.OnEvent(H.events, "BAG_UPDATE")
H.events.scripts.OnEvent(H.events, "UNIT_AURA")
frame(0.120, 30, 2, 400)               -- a hitch with a heap drop, A to blame
frame(0.008, 1, 1, 410)
check(H.run.slowCount == 1 and H.run.slowWithGc == 1, "one slow frame, with a heap drop")
check(#H.run.spikes == 2 and H.run.spikes[1]:find("A 30.00 ms", 1, true), "spikes kept with their time: " .. tostring(H.run.spikes[1]))
check(H.run.spikes[1]:find(": BAG_UPDATE x2, UNIT_AURA", 1, true) and H.run.slow[1].events == "BAG_UPDATE x2, UNIT_AURA", "with the events of that frame")
check(H.events.all, "listening to every event while sampling")
local row = H.run.slow[1]
check(row[1] == "A 30.00" and row[2] == "B 2.00" and row.gc, "the slow frame names A first: " .. tostring(row[1]))
__fcpu[__fa] = 200                      -- the tracker's handler did the work
frame(10, 0, 0)
check(H.run == nil and H.frame.scripts.OnUpdate == nil, "ends on time and removes its OnUpdate")
check(not H.events.all and H.events.scripts.OnEvent == nil, "and stops listening")
local saved = ForeverSTUwaveDB.hitch
check(#saved.frameCpu == 1 and saved.frameCpu[1]:find("190.0 ms TrackerEvents OnEvent", 1, true), "names the busy frame: " .. tostring(saved.frameCpu[1]))
check(saved.addons[1].name == "A" and saved.addons[1].slowMs == 30, "saved, sorted by CPU in slow frames")
check(saved.worstMs >= 119 and saved.moving == saved.frames, "worst frame and moving frames counted")
check(__said[#__said]:find("most CPU in slow frames: A", 1, true) and __said[#__said]:find("/fsbug", 1, true), "summed up in chat")
check(__cvar == "0" and not ForeverSTUwaveDB.hitchProfileOn, "profiling it turned on goes off again")
__speed = "SECRET"
__cvar = "1"
SlashCmdList.FSPERF("5")
local f2 = H.frame.scripts.OnUpdate
__now = __now + 0.01; f2(H.frame, 0.01)
check(H.run.frames == 1 and H.run.moving == 0, "a secret speed is never compared and counts as not moving")
return "ok"
"""


def main() -> int:
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STUBS)
    loader = lua.eval("function(src) local f = assert((loadstring or load)(src, '@Hitch.lua')); f('forever-stuwave', FS) end")
    try:
        loader(SRC)
        lua.execute(CHECKS)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL  {e}")
        print("0/1 checks passed")
        return 1
    print("ok    the_sampler_blames_the_addon_that_spiked_in_slow_frames")
    print("1/1 checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
