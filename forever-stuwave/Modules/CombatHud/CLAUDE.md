# CombatHud

The combat HUD: HudSpells -> HudProfiles -> HudLogic decide what to show, CombatHud and the Gunsight* files draw it.

## Patterns
- `HudLogic.lua`'s OnUpdate runs whenever a profile exists (Reconcile and Prune run with zero subscribers; only the state build is gated on subscribers). An unchanged tick's addon-side allocation should be zero: it builds into a reused scratch, reads each spell cooldown once, and compares a flat buffer. `hud-harness.py` measures it (`idle_tick_addon_side_allocation_*`), under LuaJIT with jit.off: indicative only, the client runs PUC 5.1 and still allocates its own API result tables.
- `Hud.GetState()` always returns a fresh, caller-owned state. Only `Hud.Tick` builds in the scratch.

## Dependencies
- Depends on: `FS.HudSpells`, `FS.HudProfiles`
- Depended on by: CombatHud.lua, GunsightSeals.lua (also `GetJudgement` and `GetSeals`), GunsightDots.lua, GunsightFrame.lua
