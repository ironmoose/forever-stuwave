# Chat

The chat terminal: the game's own chat windows, tabs and edit boxes reseated and skinned inside one container frame, the term bar and tab strip drawn over them, the line format (channel tags, class coloured names, line tint). Every file shares the `FS.Chat` table (`ChatCore.lua` creates it; each file assigns its own fields).

## Key Files
- `ChatCore.lua` -- `FS.Chat`, the shared constants and state, `Chat.ModuleOff()`, `Chat.BuildTerminal()` (the full screen container `ForeverSTUwaveChatTerminal`, `FS.chatTerminal`), `Chat.SeatTerminalChrome`, `Chat.WrapAddMessage`.
- `ChatTabs.lua` -- the tab strip and `Chat.ApplyDockState`, the Blizzard tab hide, the selection hooks. `ChatEditBox.lua`, `ChatTermBar.lua` -- functions only (no file scope effect).
- `ChatWindowState.lua` -- the window size settings (`chat.w`, `chat.h`), the seat of ChatFrame1, the Edit Mode re-seat hook, minimise and maximise.
- `ChatFrameSkin.lua` -- font size, background opacity (`chat.bgAlpha`), `Chat.SkinChatFrame`.
- `ChatSlashCommands.lua` -- `/fschat`, the cycle key function, late window skinning and `Apply()`, the one build of the module.
- `ChatFormat.lua` -- the line format and the line tint; `FS.ChatFormat`, `/fschatfmt`. Loads last.
- `Skins/ChatSettings.lua` (another folder) skins the game's chat settings window and belongs to this module.

## Module power
The Chat switch (`m.chat`, `Core/ModuleSwitch.lua`; the store, the gate API and the shape of every gate are in `Modules/Config/CLAUDE.md` "Module power") gates this folder. Off, the game's own chat is left exactly as the game made it: nothing is reparented, resized, hidden, hooked, wrapped or filtered, no frame is made and no event is listened for. Every table and function stays defined and answers empty or does nothing, so the Chat page, the layout editor and the console key can ask without an error.
- Start: `ChatSlashCommands.lua` `Start()` (the font watcher and `Apply()`, deferred to PLAYER_REGEN_ENABLED in a fight) and `MS.MarkBuilt("m.chat")` at the end of `Apply()`; `ChatCore.lua` makes the terminal, `ChatFrameSkin.lua` its background watcher and `ChatFormat.lua` its login and colour watcher, each from `MS.WhenOn("m.chat", ...)`. `Apply()` moved from file scope to ADDON_LOADED, where the switch is known.
- The guard is `Chat.ModuleOff()` (true only from ADDON_LOADED on, with the switch off). It sits on every entry point another file can reach: `Chat.SeatPrimaryChat`, `ReassertPrimaryChat`, `ApplyWindowState`, `ToggleWindowState`, the size callback `ApplySize`, `ForeverSTUwave_CycleChatTab`, `/fschat`, `/fschatfmt` and `FS.ChatFormat.Enable`. `Chat.ApplyDockState`, `SeatTerminalChrome`, `ApplyAllFontSizes` and `ApplyBackground` need none: with no terminal and no skinned window they find nothing to do. `Chat.windowState` stays `normal` while off (`ToggleWindowState` does not write it).
- Registrations that stay at file scope on purpose: the `chat.w` and `chat.h` callbacks (their order against the layout editor's own callback on the same keys decides whether the re-seat runs; the guard is inside `ApplySize`), the defaults, and the line tint callbacks (they loop over an empty table while off).
- The saved window state (`chatWindowState`) is read when the files load (`Chat.pendingWindowState`, as before the gate), not at ADDON_LOADED. The saved variables are not readable when the files load on the live client, so a minimised or maximised window comes back normal after a reload, as it always did; reading the saved table in `Apply()` would start restoring it, which is a change to ask for, not a side effect of the gate.
- Dependents: `ConsoleKeys.lua` does not draw the chat key while off and ignores a click on it (`ChatModuleOff()`), the layout editor has no chat handle (`MODULE_OF.chat`), `Skins/ChatSettings.lua` skins only with Window skins and Chat both on, `Skins/Professions.lua` reads `Chat.PlaceTermBarTooltip` (a plain function, defined while off).
- `tools/moduleswitch-harness.py` (B5d rows): chat off alone, in a fight, with the data bar off, plus every way in (the API, the slash commands, a size write, the layout editor and the console key).
