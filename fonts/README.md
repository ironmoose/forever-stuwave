# Bundled fonts

These font files retain their own SIL Open Font License 1.1. The project's MIT license does not change their licenses.

| File | Source | License file | Modification |
| --- | --- | --- | --- |
| `Orbitron-VF.ttf` | [Google Fonts: Orbitron](https://github.com/google/fonts/tree/main/ofl/orbitron), The Orbitron Project Authors | [OFL-Orbitron.txt](OFL-Orbitron.txt) | Original binary, renamed on disk. Reserved Font Name: Orbitron. |
| `FSDisplay-Bold.ttf` | Static weight 700 instance derived from the bundled Orbitron font | [OFL-Orbitron.txt](OFL-Orbitron.txt) | Modified font, renamed to **FS Display** to respect Orbitron's Reserved Font Name. |
| `MononokiNerdFontMono-Bold.ttf` | [Nerd Fonts](https://github.com/ryanoasis/nerd-fonts), patched from [Mononoki](https://github.com/madmalik/mononoki) by Matthias Tellen | [OFL-Mononoki.txt](OFL-Mononoki.txt) | Nerd Fonts' patched redistribution, with additional glyphs; not patched by this project. Reserved Font Name in the source license: mononoki. |
| `ShareTechMono-Regular.ttf` | [Google Fonts: Share Tech Mono](https://github.com/google/fonts/tree/main/ofl/sharetechmono), Carrois Type Design / Ralph du Carrois | [OFL-ShareTechMono.txt](OFL-ShareTechMono.txt) | Unmodified binary. Reserved Font Name: Share. |

WoW's font renderer needs a static font for the display face. The development script [`make_display_font.py`](make_display_font.py) pins Orbitron's weight axis and gives the resulting family the name FS Display. That modified font continues under OFL 1.1 and credits Orbitron in its description metadata.

The README masthead uses vector outlines from FS Display and Share Tech Mono; it requires no remote font loading.
