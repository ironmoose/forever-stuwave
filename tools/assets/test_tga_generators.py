"""Check generated texture bytes against independent size and geometry expectations.

Generators run as subprocesses with an isolated output directory; committed runtime assets stay untouched.
Run with `uv run python -m pytest tools/assets/test_tga_generators.py -v`.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

GENERATOR_DIR = Path(__file__).resolve().parent
REPO = GENERATOR_DIR.parent.parent
MEDIA_DIR = REPO / "forever-stuwave" / "Media" / "Textures"
GENERATOR_PATHS = sorted(GENERATOR_DIR.glob("generate_*.py"))

TGA_HEADER_SIZE = 18

# Independent oracle: intended (width, height) per generator, not derived
# from the generator's own constants (see module docstring).
# test_generator_writes_valid_tga asserts every discovered generate_*.py stem
# has an entry here.
#
# A generator stem maps to either:
#   - one (width, height), when it writes a single .tga sharing its own name
#     (generate_scanline.py -> scanline.tga), or
#   - a dict {output_stem: (width, height), ...}, when it writes one or more
#     .tga files under a DIFFERENT name than the generator's own stem, or
#     more than one .tga file (e.g. generate_slice_chrome.py -> slice_fill,
#     slice_button, slice_border, slice_glow).
EXPECTED_DIMS: dict[str, tuple[int, int] | dict[str, tuple[int, int]]] = {
    "anti_corner": (64, 64),
    "border_corner": (64, 64),
    "border_rail": (4, 128),
    # generate_cell_glow.py's own SIZE constant says 64x64, but it writes
    # cell_slant_glow.tga, not cell_glow.tga -- a deliberate name mismatch
    # (see the generator's own docstring: it is the glow for cell_slant's
    # pip shape, not a shape of its own).
    "cell_glow": {"cell_slant_glow": (64, 64)},
    "cast_chevron": {
        "cast_chevron_fill": (64, 64),
        "cast_chevron_outline": (64, 64),
        "cast_chevron_glow": (128, 128),
        "cast_chevron_burst": (128, 128),
        "cast_chevron_strip": (32, 16),
    },
    # generate_cast_chevron_up.py: the shallow UP chevron of the vertical cast tapes
    # (Gunsight HUD). 64x32 box (2:1), glow/burst canvases 128x64 with the box
    # centred, strip a 32x16 vertical tile.
    "cast_chevron_up": {
        "cast_chevron_up_fill": (64, 32),
        "cast_chevron_up_outline": (64, 32),
        "cast_chevron_up_glow": (128, 64),
        "cast_chevron_up_burst": (128, 64),
        "cast_chevron_up_strip": (32, 16),
        "cast_chevron_up_cap": (64, 32),
    },
    # generate_hud_key_glyphs.py: the eight HUD toggle key glyphs.
    "hud_key_glyphs": {
        f"glyph_hud_{name}": (32, 32)
        for name in ("chev", "play", "diamond", "shield", "cross", "clock", "bolt", "group")
    },
    # generate_hud_key_ring.py: sixteen arc segments of the toggle key ring.
    "hud_key_ring": {f"hud_key_ring_{i:02d}": (128, 64) for i in range(16)},
    # generate_console_chrome.py: Console panel chassis (cut 14) and the 45 degree tab foot.
    "console_chrome": {
        "console_fill_c14": (64, 64),
        "console_outline_c14": (64, 64),
        "console_glow_c14": (64, 64),
        "console_tab_foot": (128, 128),
    },
    "cell_slant": (32, 32),
    "deck_chrome": {
        "deck_divider": (32, 32),
        "deck_led": (32, 8),
        # Same dims as cell_slant.tga, which the micro keys reuse for the fill.
        "deck_key_slant_outline": (32, 32),
    },
    "deck_glyphs": {
        name: (32, 32)
        for name in (
            "glyph_character", "glyph_professions", "glyph_spellbook",
            "glyph_talents", "glyph_legacy", "glyph_questlog", "glyph_guild",
            "glyph_lfd", "glyph_collections", "glyph_help", "glyph_store",
            "glyph_mainmenu", "glyph_achievement", "glyph_ej", "glyph_pvp",
            "glyph_socials", "glyph_worldmap", "glyph_housing",
        )
    },
    # generate_cut_corner_outline.py writes the four-corner chamfered nine-slice
    # pair (slice_cut_outline, slice_cut_fill) and the two-corner (top-left +
    # bottom-right) set the action bars use (slice_cut2_outline/fill/button/glow
    # nine-slices, plus the 64x64 mask_cut2_square icon/swipe mask), not a file
    # named after its own stem.
    "cut_corner_outline": {
        "slice_cut_outline": (32, 32),
        "slice_cut_fill": (32, 32),
        "slice_cut2_outline": (32, 32),
        "slice_cut2_fill": (32, 32),
        "slice_cut2_button": (32, 32),
        "slice_cut2_glow": (32, 32),
        "mask_cut2_square": (64, 64),
    },
    # generate_cut_pieces.py: the cut-corner (chamfer) replacements for the rounded
    # chrome. Composed pieces are 16x16 canvases (the piece sits top-left at native
    # texels), the nine-slice sets and the corner glow are 32x32. Chamfer set
    # {2, 3, 4, 6}; every shape is two-corner (TL + BR). c=6 two-corner slices
    # already exist (cut_corner_outline), so only slice_cut2_border_c6 is new there.
    "cut_pieces": {
        **{f"fill_cut_c{c}": (16, 16) for c in (2, 3, 4, 6)},
        **{f"anti_cut_c{c}": (16, 16) for c in (2, 3, 4, 6)},
        **{f"anti_cut_br_c{c}": (16, 16) for c in (2, 3, 4, 6)},
        **{f"border_cut_c{c}_t1": (16, 16) for c in (2, 3, 4, 6)},
        "border_cut_c6_t2": (16, 16),
        "glow_corner_cut": (32, 32),
        **{f"slice_cut2_border_c{c}": (32, 32) for c in (2, 3, 4, 6)},
        **{f"slice_cut2_{kind}_c{c}": (32, 32)
           for kind in ("outline", "glow", "button", "fill") for c in (2, 3, 4)},
        **{f"slice_cut2_erase_c{c}": (32, 32) for c in (4, 6)},
    },
    "fill_corner": (64, 64),
    "glow_corner": (128, 128),
    "glow_corner_round": (128, 128),
    "glow_edge": (128, 128),
    "glow_round": (128, 128),
    # No SIZE/WIDTH/HEIGHT module constant -- see generate_grid.py's own
    # docstring on why 2048x256 (a power-of-two disk size) encodes a
    # 2560x183 on-screen shape.
    "grid": (2048, 256),
    "hatch": (16, 16),
    "hud_diamond": (32, 32),
    # generate_hud_shard.py: the line art soul shard of the Gunsight HUD. The glyph box is 10 x 18
    # addon units; the line, fill and facet canvases are 16 x 32 units (64x128 texels), the square
    # glow canvas 40 units (64x64 texels).
    "hud_shard": {
        "hud_shard_line": (64, 128),
        "hud_shard_fill": (64, 128),
        "hud_shard_facet": (64, 128),
        "hud_shard_glow": (64, 64),
    },
    # generate_hud_tile.py writes the square tile and its two-corner cut twin.
    "hud_tile": {"hud_tile": (64, 64), "hud_tile_cut2": (64, 64)},
    "icon_chrome": {"icon_chat": (32, 32), "icon_channel": (32, 32)},
    "icon_jump": (32, 32),
    "icon_social": (32, 32),
    "icon_window": {"icon_minimize": (32, 32), "icon_maximize": (32, 32)},
    "mask_minimap": (64, 64),
    # 64x32, not the naive 37x32 equilateral-content size -- the canvas is
    # padded out to the next power of two (WoW silently refuses to render a
    # non-power-of-two file texture, same trap generate_grid.py's own
    # docstring documents); the actual 37-texel-wide triangle content is
    # cropped out of that padding at render time via SetTexCoord on the Lua
    # side. See generate_pet_cast_triangle.py's own module docstring.
    "pet_cast_triangle": (64, 32),
    # generate_pet_dock_flare.py: the docked pet panel's flare stroke and halo, two 128 canvases
    # with the piece at the top-left (CLAUDE.md, PetDock.lua).
    "pet_dock_flare": {
        "pet_dock_flare_line": (128, 128),
        "pet_dock_flare_glow": (128, 128),
    },
    # generate_pet_slot_ring.py: sixteen arc segments of the pet slot ring.
    "pet_slot_ring": {f"pet_slot_ring_{i:02d}": (128, 128) for i in range(16)},
    "scanline": (4, 4),
    "scanline_rgb": (4, 4),
    # generate_seal_glyphs.py: the seven Paladin seal sigils, 64x64 (1 texel = 1 mockup image px).
    "seal_glyphs": {
        f"seal_glyph_{name}": (64, 64)
        for name in ("righteousness", "crusader", "fury", "command", "light", "wisdom", "justice")
    },
    # generate_seal_lens.py: the Seal Chamber lens ring and its three turning arcs, 128x128
    # (1.2 texels per mockup image px).
    "seal_lens": {"seal_lens": (128, 128), "seal_arcs": (128, 128)},
    # generate_seal_ring.py: the Judgement ring with its baked halo, 256x256 (1.2 texels per mockup
    # image px: the halo reaches 70.2 texels from the centre, past the lens' 128 canvas).
    "seal_ring": (256, 256),
    "scroll_rail": (32, 32),
    # generate_shoulder_glow.py: the three pieces of the Paladin shoulder's halo that console_glow_c14
    # cannot draw (top left cut 6, vertex and foot, concave corner), one 64 canvas.
    "shoulder_glow": (64, 64),
    "slice_chrome": {
        "slice_fill": (32, 32),
        "slice_button": (32, 32),
        "slice_border": (32, 32),
        "slice_glow": (32, 32),
    },
    "tab_plate": {"tab_plate": (32, 32), "tab_edge": (32, 32)},
    "tab_slant": {
        "tab_slant": (32, 32),
        "tab_slant_glow": (32, 32),
        "tab_mid_glow": (32, 32),
        "tab_mid_raster": (32, 32),
        "tab_slant_raster": (32, 32),
    },
}


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _generator_needs_numpy(generator_path: Path) -> bool:
    """True if this generator's source imports numpy.

    generate_grid.py is currently the only generator with a numpy dependency
    (see its own docstring), but this check is deliberately generic rather
    than hardcoded to that filename, so a future numpy-dependent generator
    gets the same clean skip instead of a raw traceback when numpy is
    missing from the environment.
    """
    return "import numpy" in generator_path.read_text(encoding="utf-8")


def _run_generator(generator_path: Path, work_dir: Path) -> None:
    """Copy a generator script into an isolated directory and run it there.

    The output override keeps generated files away from committed runtime assets.
    """
    script_copy = work_dir / generator_path.name
    shutil.copyfile(generator_path, script_copy)
    result = subprocess.run(
        [sys.executable, script_copy.name],
        cwd=work_dir,
        env={**os.environ, "FS_ASSET_OUTPUT_DIR": str(work_dir)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"{generator_path.name} exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


@pytest.mark.parametrize("generator_path", GENERATOR_PATHS, ids=lambda p: p.stem)
def test_generator_writes_valid_tga(generator_path: Path, tmp_path: Path) -> None:
    stem = generator_path.stem.removeprefix("generate_")
    assert stem in EXPECTED_DIMS, (
        f"no hardcoded oracle entry for new generator '{stem}'; add one to "
        "EXPECTED_DIMS instead of trusting the module's own constants"
    )
    dims_entry = EXPECTED_DIMS[stem]
    expected_outputs = dims_entry if isinstance(dims_entry, dict) else {stem: dims_entry}

    if _generator_needs_numpy(generator_path) and importlib.util.find_spec("numpy") is None:
        pytest.skip(f"numpy not installed; {generator_path.name} needs it")

    _run_generator(generator_path, tmp_path)

    actual_stems = {p.stem for p in tmp_path.glob("*.tga")}
    expected_stems = set(expected_outputs)
    assert actual_stems == expected_stems, (
        f"{generator_path.name} wrote a different .tga file set than expected "
        f"-- unexpected: {sorted(actual_stems - expected_stems)}, "
        f"missing: {sorted(expected_stems - actual_stems)}"
    )

    for output_stem, (expected_width, expected_height) in expected_outputs.items():
        out_path = tmp_path / f"{output_stem}.tga"
        assert out_path.exists(), (
            f"{generator_path.name} did not write {output_stem}.tga "
            f"(wrote: {sorted(p.name for p in tmp_path.glob('*.tga'))})"
        )
        data = out_path.read_bytes()

        assert data[2] == 2, f"{output_stem}.tga byte[2] must be 2 (uncompressed truecolor)"

        width, height = struct.unpack_from("<HH", data, 12)

        # WoW silently refuses to render a file texture whose dimensions
        # aren't powers of two -- generate_grid.py's own docstring documents
        # exactly this trap (a 2048x146 first attempt drew nothing in game).
        assert _is_power_of_two(width) and _is_power_of_two(height), (
            f"{output_stem}.tga is {width}x{height}: WoW will silently fail "
            "to render a non-power-of-two texture"
        )

        assert (width, height) == (expected_width, expected_height), (
            f"{generator_path.name}'s actual written {output_stem}.tga "
            f"({width}x{height}) has drifted from the expected "
            f"({expected_width}x{expected_height})"
        )

        assert data[16] == 32, f"{output_stem}.tga byte[16] must be 32 bits per pixel"
        assert data[17] == 0x28, (
            f"{output_stem}.tga byte[17] must be 0x28 (top-left origin, 8 alpha bits)"
        )

        pixel_payload = data[TGA_HEADER_SIZE:]
        expected_payload_len = expected_width * expected_height * 4
        assert len(pixel_payload) == expected_payload_len
        assert len(data) == TGA_HEADER_SIZE + expected_payload_len


# ---------------------------------------------------------------------------
# generate_cut_corner_outline.py: corner sets
#
# The generator draws a chamfered plate. The four-corner pair
# (slice_cut_outline / slice_cut_fill) is committed and consumed by BagBar, so
# it must not change when the two-corner set (TL + BR cut, TR + BL square) is
# added. The geometry below is hardcoded here, not read from the generator:
# 32px nine-slice textures, 64px mask, chamfer 6 texels (Theme.SLICE_CUT_MARGIN)
# and a 4 texel glow pad (Theme.SLICE_GLOW_PAD).
# ---------------------------------------------------------------------------

CUT_GENERATOR = GENERATOR_DIR / "generate_cut_corner_outline.py"
CUT_SIZE = 32
GLOW_PAD = 4


@pytest.fixture(scope="module")
def cut_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("cut_corner")
    _run_generator(CUT_GENERATOR, work)
    return work


def _alpha_at(path: Path, x: int, y: int) -> int:
    data = path.read_bytes()
    width, _ = struct.unpack_from("<HH", data, 12)
    return data[TGA_HEADER_SIZE + (y * width + x) * 4 + 3]


@pytest.mark.parametrize("name", ["slice_cut_outline", "slice_cut_fill"])
def test_four_corner_outputs_unchanged(cut_outputs: Path, name: str) -> None:
    regenerated = (cut_outputs / f"{name}.tga").read_bytes()
    assert regenerated == (MEDIA_DIR / f"{name}.tga").read_bytes()


def test_four_corner_fill_still_cuts_all_four_corners(cut_outputs: Path) -> None:
    last = CUT_SIZE - 1
    fill = cut_outputs / "slice_cut_fill.tga"
    for x, y in ((0, 0), (last, 0), (0, last), (last, last)):
        assert _alpha_at(fill, x, y) == 0, (x, y)


@pytest.mark.parametrize("name", ["slice_cut2_fill", "slice_cut2_button"])
def test_cut2_fill_cuts_top_left_and_bottom_right_only(cut_outputs: Path, name: str) -> None:
    last = CUT_SIZE - 1
    path = cut_outputs / f"{name}.tga"
    assert _alpha_at(path, 0, 0) == 0, "top-left must be cut"
    assert _alpha_at(path, last, last) == 0, "bottom-right must be cut"
    assert _alpha_at(path, last, 0) == 255, "top-right must stay square"
    assert _alpha_at(path, 0, last) == 255, "bottom-left must stay square"
    assert _alpha_at(path, CUT_SIZE // 2, CUT_SIZE // 2) == 255


def test_cut2_outline_cuts_top_left_and_bottom_right_only(cut_outputs: Path) -> None:
    last = CUT_SIZE - 1
    path = cut_outputs / "slice_cut2_outline.tga"
    assert _alpha_at(path, 0, 0) == 0
    assert _alpha_at(path, last, last) == 0
    # The square corners carry the stroke right to the corner pixel.
    assert _alpha_at(path, last, 0) == 255
    assert _alpha_at(path, 0, last) == 255
    # Hollow interior, solid stroke along the straight runs.
    assert _alpha_at(path, CUT_SIZE // 2, CUT_SIZE // 2) == 0
    assert _alpha_at(path, CUT_SIZE // 2, 0) == 255


def test_cut2_outline_stroke_is_unbroken_along_the_cut(cut_outputs: Path) -> None:
    # Walk the top-left diagonal: every anti-diagonal of the corner slice
    # (x + y == d) must hold some stroke, or the chamfer reads as a gap.
    path = cut_outputs / "slice_cut2_outline.tga"
    for d in range(6, 9):
        assert max(_alpha_at(path, x, d - x) for x in range(d + 1)) > 128, d


def test_mask_cut2_square_cuts_top_left_and_bottom_right_only(cut_outputs: Path) -> None:
    path = cut_outputs / "mask_cut2_square.tga"
    data = path.read_bytes()
    blue = set(data[TGA_HEADER_SIZE + i] for i in range(0, 64 * 64 * 4, 4))
    assert blue == {255}, "RGB must be white"
    last = 63
    assert _alpha_at(path, 0, 0) == 0
    assert _alpha_at(path, last, last) == 0
    assert _alpha_at(path, last, 0) == 255
    assert _alpha_at(path, 0, last) == 255
    assert _alpha_at(path, 32, 32) == 255


def test_glow_cut2_follows_the_chamfer_on_top_left_and_bottom_right(cut_outputs: Path) -> None:
    path = cut_outputs / "slice_cut2_glow.tga"
    last = CUT_SIZE - 1
    near = GLOW_PAD + 2
    # Where a square corner would have been, the cut leaves a lit gap at TL/BR...
    assert _alpha_at(path, near, near) > 128
    assert _alpha_at(path, last - near, last - near) > 128
    # ...while the square TR/BL corners are inside the shape, hence hollow.
    assert _alpha_at(path, last - near, near) == 0
    assert _alpha_at(path, near, last - near) == 0
    # Hollow inside, near dark at the texture edge, lit just outside a straight run.
    assert _alpha_at(path, CUT_SIZE // 2, CUT_SIZE // 2) == 0
    assert _alpha_at(path, CUT_SIZE // 2, 0) < 16
    assert _alpha_at(path, CUT_SIZE // 2, GLOW_PAD - 1) > 128


# ---------------------------------------------------------------------------
# generate_cast_chevron.py: cast bar chevron textures
#
# Geometry is hardcoded here, not read from the generator: the chevron fills a
# 64x64 box (45 degree arms, notch at the vertical middle), the glow and burst
# canvases are 128x128 with that box centred (32 texel pad), and the strip is a
# 32x16 tile holding 2 chevrons at a 16 texel pitch. Prototype:
# mockups/castbar-v2-chevrons-locked-2026-10-01.html (segsChev).
# ---------------------------------------------------------------------------

CHEVRON_GENERATOR = GENERATOR_DIR / "generate_cast_chevron.py"
CHEVRON_BOX = 64
CHEVRON_PAD = 32
STRIP_W = 32
STRIP_PITCH = 16


@pytest.fixture(scope="module")
def chevron_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("cast_chevron")
    _run_generator(CHEVRON_GENERATOR, work)
    return work


def test_chevron_fill_has_white_rgb_solid_tip_and_open_notch(chevron_outputs: Path) -> None:
    path = chevron_outputs / "cast_chevron_fill.tga"
    data = path.read_bytes()
    blue = set(data[TGA_HEADER_SIZE + i] for i in range(0, CHEVRON_BOX * CHEVRON_BOX * 4, 4))
    assert blue == {255}
    mid = CHEVRON_BOX // 2
    assert _alpha_at(path, CHEVRON_BOX - 4, mid) == 255, "tip must be opaque"
    assert _alpha_at(path, 8, mid) == 0, "notch must be transparent"
    assert _alpha_at(path, 8, 2) == 255, "top arm must be solid"
    assert _alpha_at(path, 0, mid) == 0, "left edge at mid height is the notch"


def test_chevron_outline_is_hollow_inside_with_stroke_on_the_tip(chevron_outputs: Path) -> None:
    path = chevron_outputs / "cast_chevron_outline.tga"
    mid = CHEVRON_BOX // 2
    assert _alpha_at(path, CHEVRON_BOX - 4, mid) == 255, "stroke must carry to the tip"
    assert _alpha_at(path, 48, mid) == 0, "interior must be hollow"
    assert _alpha_at(path, 8, mid) == 0, "notch must be transparent"


@pytest.mark.parametrize("name", ["cast_chevron_glow", "cast_chevron_burst"])
def test_chevron_glow_canvases_reach_past_the_chevron_box(chevron_outputs: Path, name: str) -> None:
    path = chevron_outputs / f"{name}.tga"
    mid = CHEVRON_BOX  # centre of the 128 canvas
    # Soft halo lit outside the box (a plain outline texture has nothing there)
    # and fading out before the canvas edge.
    assert _alpha_at(path, CHEVRON_PAD + 16, CHEVRON_PAD - 4) > 0, "lit just above the top arm"
    assert _alpha_at(path, 0, mid) < 8
    assert _alpha_at(path, mid, 0) < 8


def test_chevron_burst_is_solid_in_the_chevron_and_glow_is_not(chevron_outputs: Path) -> None:
    mid = CHEVRON_BOX
    solid_px = (CHEVRON_PAD + CHEVRON_BOX - 8, mid)
    assert _alpha_at(chevron_outputs / "cast_chevron_burst.tga", *solid_px) == 255
    assert _alpha_at(chevron_outputs / "cast_chevron_glow.tga", *solid_px) < 255


def test_chevron_strip_tiles_seamlessly(chevron_outputs: Path) -> None:
    path = chevron_outputs / "cast_chevron_strip.tga"
    data = path.read_bytes()
    w, h = struct.unpack_from("<HH", data, 12)
    assert (w, h) == (STRIP_W, 16)

    def column(x: int) -> bytes:
        return b"".join(
            data[TGA_HEADER_SIZE + (y * w + x) * 4:TGA_HEADER_SIZE + (y * w + x) * 4 + 4]
            for y in range(h)
        )

    # Two chevrons per tile: the pattern repeats every STRIP_PITCH columns, so
    # the column after the last (the first of the next tile) is the one that
    # follows column STRIP_PITCH - 1 inside the tile.
    for x in range(w):
        assert column(x) == column((x + STRIP_PITCH) % w), x
    assert column(0) == column(STRIP_PITCH)
    assert column(w - 1) == column(STRIP_PITCH - 1)
    assert any(data[TGA_HEADER_SIZE + i + 3] == 0 for i in range(0, w * h * 4, 4)), "needs gaps"
    assert any(data[TGA_HEADER_SIZE + i + 3] == 255 for i in range(0, w * h * 4, 4)), "needs shape"

# ---------------------------------------------------------------------------
# generate_cut_pieces.py: cut-corner (chamfer) pieces and nine-slice sets
#
# Everything below is hardcoded from the design, not read from the generator.
# Composed pieces: 16x16 canvas, the c x c piece sits top-left at native texels
# (callers SetTexCoord(0, c/16, 0, c/16)), and the canvas keeps going as the
# plate it is a corner of, so bilinear filtering at the region edge samples the
# straight run rather than a transparent border. Nine-slice sets: 32x32, slice
# margin == the baked chamfer (glow: GLOW_PAD + chamfer).
# ---------------------------------------------------------------------------

PIECES_GENERATOR = GENERATOR_DIR / "generate_cut_pieces.py"
PIECE_N = 16
SLICE_N = 32
CHAMFERS = (2, 3, 4, 6)
EXTRA_CHAMFERS = (2, 3, 4)
ANTI_INSET = 2.0 - 2 ** 0.5   # leg = c - ANTI_INSET at inset 1 (c - 0.586)


@pytest.fixture(scope="module")
def piece_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("cut_pieces")
    _run_generator(PIECES_GENERATOR, work)
    return work


def _tri_area(s: float) -> float:
    """Area of {u + v < s} inside the unit square."""
    if s <= 0:
        return 0.0
    if s <= 1:
        return s * s / 2
    if s <= 2:
        return 1 - (2 - s) ** 2 / 2
    return 1.0


def _alpha_grid(path: Path) -> list[list[int]]:
    data = path.read_bytes()
    width, height = struct.unpack_from("<HH", data, 12)
    return [
        [data[TGA_HEADER_SIZE + (y * width + x) * 4 + 3] for x in range(width)]
        for y in range(height)
    ]


@pytest.mark.parametrize("c", CHAMFERS)
def test_fill_cut_is_the_triangle_x_plus_y_at_least_c(piece_outputs: Path, c: int) -> None:
    grid = _alpha_grid(piece_outputs / f"fill_cut_c{c}.tga")
    for y in range(PIECE_N):
        for x in range(PIECE_N):
            expected = 255 * (1 - _tri_area(c - x - y))
            assert abs(grid[y][x] - expected) <= 4, (c, x, y, grid[y][x], expected)
    # Spot the contract in plain numbers: solid at x+y>=c, clear well outside.
    assert grid[0][c] == 255 and grid[c][0] == 255
    assert grid[0][0] == 0


@pytest.mark.parametrize("c", CHAMFERS)
def test_anti_cut_is_the_erase_triangle_with_the_fractional_leg(
    piece_outputs: Path, c: int
) -> None:
    leg = c - ANTI_INSET
    grid = _alpha_grid(piece_outputs / f"anti_cut_c{c}.tga")
    for y in range(PIECE_N):
        for x in range(PIECE_N):
            expected = 255 * _tri_area(leg - x - y)
            assert abs(grid[y][x] - expected) <= 4, (c, x, y, grid[y][x], expected)
    assert grid[0][0] > 200, "the very corner is erased"
    assert grid[0][c] == 0 and grid[c - 1][1] == 0, "x+y>=c is untouched"
    # The leg is fractional: the c-1 anti-diagonal is a partial sliver, not 0 or 255.
    assert 0 < grid[0][c - 1] < 64


@pytest.mark.parametrize("c", CHAMFERS)
def test_anti_cut_is_the_complement_of_fill_cut_inside_the_inset(
    piece_outputs: Path, c: int
) -> None:
    fill = _alpha_grid(piece_outputs / f"fill_cut_c{c}.tga")
    anti = _alpha_grid(piece_outputs / f"anti_cut_c{c}.tga")
    for y in range(PIECE_N):
        for x in range(PIECE_N):
            if x + y + 2 <= c - ANTI_INSET:
                assert anti[y][x] == 255 and fill[y][x] == 0


BORDER_PIECES = [(c, 1) for c in CHAMFERS] + [(6, 2)]


@pytest.mark.parametrize("c,t", BORDER_PIECES)
def test_border_cut_diagonal_stroke_is_unbroken_and_as_wide_as_the_straight_run(
        piece_outputs: Path, c: int, t: int) -> None:
    grid = _alpha_grid(piece_outputs / f"border_cut_c{c}_t{t}.tga")
    # Every anti-diagonal across the stroke band holds stroke (no gap in the cut).
    for d in range(c, c + t + 1):
        along = [grid[d - x][x] for x in range(0, d + 1) if d - x < PIECE_N]
        assert max(along) > 128, (c, t, d)
    # Nothing outside the cut, hollow inside, straight strokes carry to the canvas edge.
    for d in range(0, c - 1):
        assert all(grid[d - x][x] == 0 for x in range(d + 1)), (c, t, d)
    assert grid[PIECE_N - 1][PIECE_N - 1] == 0
    assert all(grid[y][PIECE_N - 1] == 255 for y in range(0, t))      # top run
    assert all(grid[PIECE_N - 1][x] == 255 for x in range(0, t))      # left run
    # Same width on the diagonal as on the straight runs: a column that only crosses
    # the diagonal holds t*sqrt(2) texels of stroke (vertical extent of a 45 degree band).
    for x in range(math.ceil(t * 2 ** 0.5), c - 1):
        total = sum(grid[y][x] for y in range(PIECE_N)) / 255
        assert abs(total - t * 2 ** 0.5) < 0.15, (c, t, x, total)
    # The cut must not bleed into the run it hands over to: past the chamfer the
    # stroke is exactly t texels (rails start at c, so a leak would double-line).
    for x in range(c, PIECE_N):
        assert all(grid[y][x] == 0 for y in range(t, PIECE_N)), (c, t, x)
        assert grid[t - 1][x] == 255


@pytest.mark.parametrize("c", EXTRA_CHAMFERS)
def test_cut2_extra_sets_cut_top_left_and_bottom_right_only(piece_outputs: Path, c: int) -> None:
    last = SLICE_N - 1
    for kind in ("fill", "button"):
        grid = _alpha_grid(piece_outputs / f"slice_cut2_{kind}_c{c}.tga")
        assert (grid[0][0], grid[last][last]) == (0, 0), (kind, c)
        assert (grid[0][last], grid[last][0]) == (255, 255), (kind, c)
        assert grid[16][16] == 255
    outline = _alpha_grid(piece_outputs / f"slice_cut2_outline_c{c}.tga")
    assert (outline[0][0], outline[last][last]) == (0, 0)
    assert (outline[0][last], outline[last][0]) == (255, 255)
    assert outline[16][16] == 0 and outline[0][16] == 255
    for d in range(c, c + 2):
        assert max(outline[d - x][x] for x in range(d + 1)) > 128, (c, d)
    # TL + BR cut means the shape is symmetric under transpose.
    for kind in ("fill", "outline", "button", "glow"):
        grid = _alpha_grid(piece_outputs / f"slice_cut2_{kind}_c{c}.tga")
        assert all(
            grid[y][x] == grid[x][y] for y in range(SLICE_N) for x in range(SLICE_N)
        ), (kind, c)
    glow = _alpha_grid(piece_outputs / f"slice_cut2_glow_c{c}.tga")
    near = GLOW_PAD + 1
    assert glow[16][16] == 0, "hollow inside"
    # The last diagonal texel whose centre is outside the cut (cut line u + v = 2 * GLOW_PAD + c).
    k = math.ceil((2 * GLOW_PAD - 1 + c) / 2) - 1
    assert glow[k][k] > 64, "lit where the cut leaves a gap"
    assert (
        glow[near][last - near] == 0 and glow[last - near][near] == 0
    ), "square corners stay hollow"


def _assert_nine_slice_uniform(grid: list[list[int]], margin: int, label: str) -> None:
    """The stretched slices (edges, centre) must be constant along their stretch
    direction, or the nine-slice smears a corner artefact across the whole edge."""
    lo, hi = margin, SLICE_N - margin
    for y in range(SLICE_N):
        row = grid[y]
        if y < lo or y >= hi:
            assert len({row[x] for x in range(lo, hi)}) == 1, (label, "horizontal slice", y)
    for x in range(SLICE_N):
        if x < lo or x >= hi:
            assert len({grid[y][x] for y in range(lo, hi)}) == 1, (label, "vertical slice", x)


@pytest.mark.parametrize("c", CHAMFERS)
def test_cut2_border_is_a_two_corner_unit_stroke(piece_outputs: Path, c: int) -> None:
    last = SLICE_N - 1
    border = _alpha_grid(piece_outputs / f"slice_cut2_border_c{c}.tga")
    assert (border[0][0], border[last][last]) == (0, 0), "TL and BR are cut"
    assert (border[0][last], border[last][0]) == (255, 255), "TR and BL stay square"
    assert border[16][16] == 0 and border[0][16] == 255 and border[16][0] == 255
    assert all(border[y][x] == border[x][y] for y in range(SLICE_N) for x in range(SLICE_N))
    for d in range(c, c + 2):
        assert max(border[d - x][x] for x in range(d + 1)) > 128, (c, d)
    # 1.0 stroke on the straight runs, nothing leaking inward past the chamfer.
    assert all(border[1][x] == 0 for x in range(c, SLICE_N - 1)), c
    assert all(border[0][x] == 255 for x in range(c, SLICE_N))
    _assert_nine_slice_uniform(border, c, "border")


@pytest.mark.parametrize("c", EXTRA_CHAMFERS)
def test_cut2_extra_slice_margins_equal_the_baked_chamfer(piece_outputs: Path, c: int) -> None:
    for kind in ("fill", "button", "outline"):
        _assert_nine_slice_uniform(
            _alpha_grid(piece_outputs / f"slice_cut2_{kind}_c{c}.tga"), c, kind)
    _assert_nine_slice_uniform(
        _alpha_grid(piece_outputs / f"slice_cut2_glow_c{c}.tga"), GLOW_PAD + c, "glow")


# The fill erase for a nine-sliced stroke (slice_cut2_erase_c{4,6}): a nine-slice whose only opaque
# texels are a wedge in each cut corner, drawn over the SAME rect, at the SAME slice margin, as the
# stroke it sits inside (c6: the nameplate's slice_cut2_border_c6 over the plate root; c4: the party
# pet column's slice_cut2_outline_c4 ring over its box). The engine slices both from one rect at one
# margin, so the wedge's hypotenuse stays the same distance from the stroke's diagonal in screen
# pixels at ANY scale; the wedge is baked H = c + 1.25 texels from the corner, 0.164 inside the
# stroke's inner edge (c + sqrt 2). Expected numbers are derived here, not read from the generator.
ERASE_CHAMFERS = (4, 6)
ERASE_RING = {4: "slice_cut2_outline_c4", 6: "slice_cut2_border_c6"}   # the committed stroke per chamfer
ERASE_TOLERANCE = 0.15                      # texels on H
ERASE_MAX_INNER_GAP = 0.2                   # texels; a 1.2 px texel then leaves under 0.25 px


def _wedge_area(h: float, c: int) -> float:
    """Area of x + y < h clipped to the c x c corner slice."""
    return h * h / 2 - max(h - c, 0) ** 2


def _erase_hypotenuse(grid: list[list[int]], corner: str, c: int) -> float:
    """The cut line x + y = H of one corner's wedge, solved from its measured area."""
    area = 0.0
    for y in range(c):
        for x in range(c):
            tx, ty = (x, y) if corner == "tl" else (SLICE_N - 1 - x, SLICE_N - 1 - y)
            area += grid[ty][tx] / 255
    lo, hi = 0.0, 12.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _wedge_area(mid, c) < area else (lo, mid)
    return (lo + hi) / 2


@pytest.mark.parametrize("c", ERASE_CHAMFERS)
def test_cut2_erase_is_one_wedge_per_cut_corner_and_nothing_else(piece_outputs: Path, c: int) -> None:
    grid = _alpha_grid(piece_outputs / f"slice_cut2_erase_c{c}.tga")
    last = SLICE_N - 1
    assert grid[0][0] == 255 and grid[last][last] == 255, "both cut corners are erased at the tip"
    assert grid[0][last] == 0 and grid[last][0] == 0, "square corners stay clear"
    assert grid[16][16] == 0, "centre is clear"
    # Nothing outside the two corner slices (margin c), so the stretched edges are empty.
    for y in range(SLICE_N):
        for x in range(SLICE_N):
            if not ((x < c and y < c) or (x >= SLICE_N - c and y >= SLICE_N - c)):
                assert grid[y][x] == 0, (x, y)
    # The BR wedge mirrors the TL one.
    assert all(grid[y][x] == grid[last - y][last - x] for y in range(c) for x in range(c))
    _assert_nine_slice_uniform(grid, c, "erase")


@pytest.mark.parametrize("corner", ("tl", "br"))
@pytest.mark.parametrize("c", ERASE_CHAMFERS)
def test_cut2_erase_hypotenuse_is_baked_inside_the_stroke_inner_edge(
    piece_outputs: Path, c: int, corner: str
) -> None:
    h = _erase_hypotenuse(_alpha_grid(piece_outputs / f"slice_cut2_erase_c{c}.tga"), corner, c)
    assert abs(h - (c + 1.25)) <= ERASE_TOLERANCE, (c, corner, round(h, 3))
    # The supported window, stated once: at or past the stroke's outer cut line (nothing of the
    # fill shows outside the violet line) and not past its inner edge (no dark sliver between
    # the stroke and the fill), and close enough to that edge that the gap stays sub-pixel.
    inner = c + 2 ** 0.5
    assert c <= h <= inner, (c, corner, round(h, 3))
    assert inner - h <= ERASE_MAX_INNER_GAP, (c, corner, round(inner - h, 3))


@pytest.mark.parametrize("c", ERASE_CHAMFERS)
def test_cut2_erase_covers_the_committed_stroke_it_sits_inside(piece_outputs: Path, c: int) -> None:
    """Cross-check against the committed ring: every stroked texel of a cut corner whose centre lies
    well inside the stroke band is also erased, so the stroke never sits over an uncovered fill."""
    ring = _alpha_grid(MEDIA_DIR / f"{ERASE_RING[c]}.tga")
    erase = _alpha_grid(piece_outputs / f"slice_cut2_erase_c{c}.tga")
    for y in range(c):
        for x in range(c):
            if ring[y][x] > 0 and x + y + 1 < c + 2 ** 0.5 - 0.5:
                assert erase[y][x] > 0, (c, x, y)


def test_c6_erase_stays_byte_identical_to_the_committed_file(piece_outputs: Path) -> None:
    """The nameplate's c6 erase must not move when the generator learns a second chamfer."""
    assert (piece_outputs / "slice_cut2_erase_c6.tga").read_bytes() == (
        MEDIA_DIR / "slice_cut2_erase_c6.tga").read_bytes()


def test_c4_fill_slice_corners_equal_the_unit_sized_fill_pieces_at_one_texel_per_unit(
    piece_outputs: Path,
) -> None:
    """The party pet box fill is slice_cut2_fill_c4 at margin 4 instead of flat rects plus
    fill_cut_c4 triangles (AddRoundedFill). At one texel per unit the two must be the same pixels:
    each cut corner cell of the slice equals the 4 x 4 piece (TL as baked, BR flipped both ways),
    and everything else is opaque, as the flat rects are."""
    c = 4
    piece = _alpha_grid(piece_outputs / f"fill_cut_c{c}.tga")
    grid = _alpha_grid(piece_outputs / f"slice_cut2_fill_c{c}.tga")
    last = SLICE_N - 1
    for y in range(c):
        for x in range(c):
            assert grid[y][x] == piece[y][x], ("TL", x, y)
            assert grid[last - y][last - x] == piece[y][x], ("BR", x, y)
    for y in range(SLICE_N):
        for x in range(SLICE_N):
            in_tl = x < c and y < c
            in_br = x >= SLICE_N - c and y >= SLICE_N - c
            if not (in_tl or in_br):
                assert grid[y][x] == 255, (x, y)


@pytest.mark.parametrize("c", CHAMFERS)
def test_anti_cut_br_is_anti_cut_flipped_both_ways(piece_outputs: Path, c: int) -> None:
    """The gated mid-plate wedge: a StatusBar fill shows its file unflipped, so the
    BOTTOM-RIGHT erase triangle is baked into the file instead of sampled with flipped
    texcoords (SetTexCoord on a StatusBar fill is not reliable)."""
    anti = _alpha_grid(piece_outputs / f"anti_cut_c{c}.tga")
    br = _alpha_grid(piece_outputs / f"anti_cut_br_c{c}.tga")
    last = PIECE_N - 1
    for y in range(PIECE_N):
        for x in range(PIECE_N):
            assert abs(br[y][x] - anti[last - y][last - x]) <= 1, (c, x, y)
    assert br[last][last] > 200 and br[0][0] == 0


def test_cut2_button_extra_sizes_bake_the_action_button_gradient(piece_outputs: Path) -> None:
    # Same #241640 -> #160c2b top-to-bottom gradient as slice_cut2_button (c=6).
    for c in EXTRA_CHAMFERS:
        data = (piece_outputs / f"slice_cut2_button_c{c}.tga").read_bytes()

        def rgb(y: int) -> tuple[int, int, int]:
            off = TGA_HEADER_SIZE + (y * SLICE_N + 16) * 4
            return data[off + 2], data[off + 1], data[off]

        assert rgb(0) == (0x24, 0x16, 0x40), c
        assert rgb(SLICE_N - 1) == (0x16, 0x0C, 0x2B), c


def test_glow_corner_cut_halos_the_cut_and_matches_the_straight_strip(piece_outputs: Path) -> None:
    # 6:8 chamfer:glow, baked on a 32 canvas: the panel corner box is 14 display px.
    grid = _alpha_grid(piece_outputs / "glow_corner_cut.tga")
    last = SLICE_N - 1
    assert all(
        grid[y][x] == grid[x][y] for y in range(SLICE_N) for x in range(SLICE_N)
    ), "symmetric"
    assert grid[last][last] == 0, "hollow inside the plate"
    assert grid[0][0] < 8, "faded out at the far corner"
    assert grid[24][24] > 200, "peaks right outside the cut"
    assert grid[24][24] >= grid[20][20] >= grid[16][16] >= grid[10][10], "falls off outward"
    # Where the straight run begins (panel y = 0, box x = c) the strip peaks, so the
    # piece must too, or the halo steps at the join.
    assert grid[18][last] > 235 and grid[last][18] > 235


HUD_GENERATOR = GENERATOR_DIR / "generate_hud_tile.py"


@pytest.fixture(scope="module")
def hud_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("hud_tile")
    _run_generator(HUD_GENERATOR, work)
    return work


def _bgra_at(path: Path, x: int, y: int) -> tuple[int, int, int, int]:
    data = path.read_bytes()
    width, _ = struct.unpack_from("<HH", data, 12)
    off = TGA_HEADER_SIZE + (y * width + x) * 4
    return data[off], data[off + 1], data[off + 2], data[off + 3]


def test_hud_tile_unchanged_and_cut2_twin_shares_its_gradient(hud_outputs: Path) -> None:
    assert (hud_outputs / "hud_tile.tga").read_bytes() == (MEDIA_DIR / "hud_tile.tga").read_bytes()
    generated = (hud_outputs / "hud_tile_cut2.tga").read_bytes()
    assert generated == (MEDIA_DIR / "hud_tile_cut2.tga").read_bytes()
    plain, cut = hud_outputs / "hud_tile.tga", hud_outputs / "hud_tile_cut2.tga"
    last = 63
    assert _bgra_at(cut, 0, 0)[3] == 0 and _bgra_at(cut, last, last)[3] == 0
    assert _bgra_at(cut, last, 0)[3] == 255 and _bgra_at(cut, 0, last)[3] == 255
    assert _bgra_at(cut, 32, 32)[3] == 255
    # RGB is the same 135 degree gradient everywhere the tile is solid.
    for x, y in ((last, 0), (0, last), (32, 32), (40, 12), (12, 40)):
        assert _bgra_at(cut, x, y) == _bgra_at(plain, x, y), (x, y)
    # The chamfer is a fraction of the tile (it is stretched over 24 to 56 px tiles):
    # 6 px on the 36 px tile = 1/6 of it = ~10.7 of 64 texels.
    assert _bgra_at(cut, 10, 0)[3] < 255 and _bgra_at(cut, 12, 0)[3] == 255
    assert _bgra_at(cut, 0, 10)[3] < 255 and _bgra_at(cut, 0, 12)[3] == 255


def test_existing_cut_corner_and_round_textures_are_untouched(tmp_path: Path) -> None:
    # The cut2 set the action bars consume (c=6) is pinned beside the four-corner pair.
    _run_generator(CUT_GENERATOR, tmp_path)
    for name in ("slice_cut2_outline", "slice_cut2_fill", "slice_cut2_button",
                 "slice_cut2_glow", "mask_cut2_square"):
        generated = (tmp_path / f"{name}.tga").read_bytes()
        assert generated == (MEDIA_DIR / f"{name}.tga").read_bytes(), name


def test_committed_cut_pieces_match_the_generator(piece_outputs: Path) -> None:
    # Guards a stale commit: every generated piece is checked in byte for byte.
    for out in sorted(piece_outputs.glob("*.tga")):
        assert out.read_bytes() == (MEDIA_DIR / out.name).read_bytes(), out.name


def test_cut_pieces_never_overwrite_a_pre_existing_texture(piece_outputs: Path) -> None:
    protected = {
        "slice_cut_outline", "slice_cut_fill", "slice_cut2_outline", "slice_cut2_fill",
        "slice_cut2_button", "slice_cut2_glow", "mask_cut2_square", "fill_corner",
        "anti_corner", "border_corner", "glow_corner_round", "mask_minimap", "hud_tile",
        "slice_fill", "slice_button", "slice_border", "slice_glow",
    }
    assert not protected & {p.stem for p in piece_outputs.glob("*.tga")}



# ---------------------------------------------------------------------------
# mask_minimap: 64px map-face mask, chamfer 6/250 of the side (about 1.5 texels),
# top-left and bottom-right cut, top-right and bottom-left square.
# ---------------------------------------------------------------------------

MINIMAP_GENERATOR = GENERATOR_DIR / "generate_mask_minimap.py"


def test_mask_minimap_cuts_top_left_and_bottom_right_only(tmp_path: Path) -> None:
    _run_generator(MINIMAP_GENERATOR, tmp_path)
    path = tmp_path / "mask_minimap.tga"
    last = 63
    # The chamfer is only ~1.5 texels, so the corner texel is mostly (not fully) clear.
    assert _alpha_at(path, 0, 0) < 64, "top-left must be cut"
    assert _alpha_at(path, last, last) < 64, "bottom-right must be cut"
    assert _alpha_at(path, last, 0) == 255, "top-right must stay square"
    assert _alpha_at(path, 0, last) == 255, "bottom-left must stay square"
    assert _alpha_at(path, 32, 32) == 255
    for x, y in ((32, 0), (32, last), (0, 32), (last, 32)):
        assert _alpha_at(path, x, y) == 255, (x, y)


# ---------------------------------------------------------------------------
# Gunsight HUD textures (mockups/gunsight-hud-v2-2026-10-02): vertical cast tape
# chevron, toggle key glyphs and ring arcs, Console chassis chrome.
#
# Every number below is hardcoded from the mockup, never read from a generator.
# ---------------------------------------------------------------------------

def _rgba_grid(path: Path) -> list[list[tuple[int, int, int, int]]]:
    data = path.read_bytes()
    width, height = struct.unpack_from("<HH", data, 12)
    out = []
    for y in range(height):
        row = []
        for x in range(width):
            o = TGA_HEADER_SIZE + (y * width + x) * 4
            row.append((data[o + 2], data[o + 1], data[o], data[o + 3]))
        out.append(row)
    return out


def _is_white(path: Path) -> bool:
    return all(px[:3] == (255, 255, 255) for row in _rgba_grid(path) for px in row)


def _seg_dist(px: float, py: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(px - a[0], py - a[1])
    t = ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def _poly_dist(px: float, py: float, pts: list[tuple[float, float]], closed: bool = True) -> float:
    n = len(pts) if closed else len(pts) - 1
    return min(_seg_dist(px, py, pts[i], pts[(i + 1) % len(pts)]) for i in range(n))


def _poly_inside(px: float, py: float, pts: list[tuple[float, float]]) -> bool:
    inside = False
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % len(pts)]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


# --- vertical cast tape chevron --------------------------------------------

CHEVRON_UP_GENERATOR = GENERATOR_DIR / "generate_cast_chevron_up.py"
UP_W, UP_H = 64, 32          # fill / outline box (2:1, hw 14 tape chevron: 28 x 13.5)
UP_PAD_X, UP_PAD_Y = 32, 16  # glow and burst canvases are 128x64, box centred
# Tape chevron: depth d 8, thickness t 5.5 over a 13.5 high box (drawTape).
UP_FILL_D = 8.0 / 13.5
# Caret chevron: depth 9, thickness 7 over 16 (chevPath(cx, tipY - 1, hw + 3, d + 1, 7)).
UP_CARET_D = 9.0 / 16.0


def _up_poly(w: float, h: float, d_frac: float, ox: float = 0.0, oy: float = 0.0):
    d = d_frac * h
    return [(ox + w / 2, oy), (ox + w, oy + d), (ox + w, oy + h),
            (ox + w / 2, oy + (h - d)), (ox, oy + h), (ox, oy + d)]


@pytest.fixture(scope="module")
def chevron_up_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("cast_chevron_up")
    _run_generator(CHEVRON_UP_GENERATOR, work)
    return work


@pytest.mark.parametrize("name", ["fill", "outline", "glow", "burst", "strip", "cap"])
def test_chevron_up_textures_are_white_with_shape_in_alpha(
        chevron_up_outputs: Path, name: str) -> None:
    path = chevron_up_outputs / f"cast_chevron_up_{name}.tga"
    assert _is_white(path)
    alphas = [px[3] for row in _rgba_grid(path) for px in row]
    # A blurred halo never quite reaches full alpha; the crisp shapes do.
    assert max(alphas) >= (150 if name == "glow" else 255) and min(alphas) == 0


@pytest.mark.parametrize("name", ["fill", "outline", "glow", "burst", "cap"])
def test_chevron_up_is_mirror_symmetric(chevron_up_outputs: Path, name: str) -> None:
    grid = _alpha_grid(chevron_up_outputs / f"cast_chevron_up_{name}.tga")
    w = len(grid[0])
    for y, row in enumerate(grid):
        for x in range(w):
            assert abs(row[x] - row[w - 1 - x]) <= 2, (name, x, y)


def test_chevron_up_fill_points_up_with_an_open_notch_below(chevron_up_outputs: Path) -> None:
    path = chevron_up_outputs / "cast_chevron_up_fill.tga"
    assert _alpha_at(path, 32, 6) >= 250, "the band under the tip is solid"
    assert _alpha_at(path, 32, 24) == 0, "below the notch is open"
    assert _alpha_at(path, 3, 28) == 255, "the arm foot is solid"
    assert _alpha_at(path, 3, 10) == 0, "above the arm is empty (the tip is the top)"
    # Same polygon as drawTape's chevPath, normalised into the 64x32 box.
    poly = _up_poly(UP_W, UP_H, UP_FILL_D)
    for y in range(UP_H):
        for x in range(UP_W):
            if _poly_dist(x + 0.5, y + 0.5, poly) < 0.9:
                continue
            want = 255 if _poly_inside(x + 0.5, y + 0.5, poly) else 0
            assert abs(_alpha_at(path, x, y) - want) <= 4, (x, y)


def test_chevron_up_outline_is_a_hollow_caret(chevron_up_outputs: Path) -> None:
    path = chevron_up_outputs / "cast_chevron_up_outline.tga"
    assert _alpha_at(path, 32, 1) >= 250, "the stroke carries to the tip"
    assert _alpha_at(path, 32, 7) <= 8, "the band interior is hollow"
    assert _alpha_at(path, 32, 24) == 0, "below the notch is open"
    poly = _up_poly(UP_W, UP_H, UP_CARET_D)
    # Stroke lives inside the polygon and never leaves it.
    for y in range(UP_H):
        for x in range(UP_W):
            if not _poly_inside(x + 0.5, y + 0.5, poly) and _poly_dist(x + 0.5, y + 0.5, poly) > 0.9:
                assert _alpha_at(path, x, y) == 0, (x, y)


# The cap is the caret's roof (same tip, same arm ends) filled solid down to CAP_APEX rows under the
# tip: the lit fill under the caret ends 9.2 caret units under the tip, and the cap hides that cut.
UP_CAP_ROOF_END = UP_CARET_D * UP_H     # row of the arm ends: the roof falls this far over half the box
UP_CAP_APEX = 23                        # rows under the tip where the cap's lower edge crosses the centre
UP_CAP_CUT_ROW = 18.4                   # the lit fill's flat top: 9.2 of the caret's 16 units (two rows a unit) under the tip
UP_LIT_W, UP_CARET_W = 20.0, 26.0       # image px: the lit chevron inside the caret box


def _roof_row(x: float) -> float:
    return UP_CAP_ROOF_END * abs(x - UP_W / 2) / (UP_W / 2)


def test_chevron_up_cap_follows_the_caret_roof_and_never_rises_above_it(
        chevron_up_outputs: Path) -> None:
    path = chevron_up_outputs / "cast_chevron_up_cap.tga"
    assert _alpha_at(path, 32, 1) >= 250, "solid to the tip"
    assert _alpha_at(path, 3, 3) == 0, "above the arm is empty"
    for y in range(UP_H):
        for x in range(UP_W):
            if y + 0.5 < _roof_row(x + 0.5) - 0.9:
                assert _alpha_at(path, x, y) == 0, ("above the roof", x, y)
            if _roof_row(x + 0.5) + 0.9 < y + 0.5 < min(UP_H, UP_CAP_APEX + _roof_row(x + 0.5)) - 0.9:
                assert _alpha_at(path, x, y) >= 250, ("inside the band", x, y)
    assert _alpha_at(path, 32, UP_CAP_APEX + 2) == 0, "open under the lower edge at the centre"


def test_chevron_up_cap_covers_the_lit_fills_flat_top_across_the_lit_column(
        chevron_up_outputs: Path) -> None:
    path = chevron_up_outputs / "cast_chevron_up_cap.tga"
    # The lit chevron is 20 image px wide inside the caret's 26, centred: texel columns 7.38 .. 56.62, so
    # columns 7 .. 56 (edge columns included). Every row within 2 caret units (4 rows) of the cut must be
    # solid in each, whole rows only: 15 .. 22.
    edge = (UP_W - UP_W * UP_LIT_W / UP_CARET_W) / 2
    first, last = int(edge), int(UP_W - edge)
    assert (first, last) == (7, 56)
    top, bottom = math.ceil(UP_CAP_CUT_ROW - 4), math.floor(UP_CAP_CUT_ROW + 4)
    assert (top, bottom) == (15, 22) and bottom + 1 <= UP_CAP_APEX
    for x in range(first, last + 1):
        for y in range(top, bottom + 1):
            assert _alpha_at(path, x, y) >= 250, (x, y)


@pytest.mark.parametrize("name", ["glow", "burst"])
def test_chevron_up_glow_canvases_reach_past_the_box(chevron_up_outputs: Path, name: str) -> None:
    path = chevron_up_outputs / f"cast_chevron_up_{name}.tga"
    assert _alpha_at(path, UP_PAD_X + UP_W // 2, UP_PAD_Y - 3) > 0, "lit just above the tip"
    assert _alpha_at(path, 0, 0) < 8 and _alpha_at(path, 64, 0) < 8
    assert _alpha_at(path, 0, 63) < 8 and _alpha_at(path, 127, 32) < 8


def test_chevron_up_burst_is_solid_in_the_chevron_and_glow_is_not(
        chevron_up_outputs: Path) -> None:
    px = (UP_PAD_X + UP_W // 2, UP_PAD_Y + 6)
    assert _alpha_at(chevron_up_outputs / "cast_chevron_up_burst.tga", *px) == 255
    assert _alpha_at(chevron_up_outputs / "cast_chevron_up_glow.tga", *px) < 255


def test_chevron_up_strip_is_one_chevron_per_tile_and_wraps_vertically(
        chevron_up_outputs: Path) -> None:
    path = chevron_up_outputs / "cast_chevron_up_strip.tga"
    pitch, width = 16.0, 32.0
    d, t = pitch * 8.0 / 12.2, pitch * 5.5 / 12.2   # mockup d, t over its 12.2 pitch
    polys = [
        [(ox + width / 2, oy), (ox + width, oy + d), (ox + width, oy + d + t),
         (ox + width / 2, oy + t), (ox, oy + d + t), (ox, oy + d)]
        for ox, oy in ((0.0, -pitch), (0.0, 0.0), (0.0, pitch))
    ]
    seen_in = seen_out = 0
    for y in range(16):
        for x in range(32):
            cx, cy = x + 0.5, y + 0.5
            if min(_poly_dist(cx, cy, p) for p in polys) < 0.9:
                continue
            inside = any(_poly_inside(cx, cy, p) for p in polys)
            seen_in += inside
            seen_out += not inside
            assert abs(_alpha_at(path, x, y) - (255 if inside else 0)) <= 4, (x, y)
    assert seen_in > 100 and seen_out > 100


# --- toggle key glyphs ------------------------------------------------------

GLYPH_HUD_NAMES = ("chev", "play", "diamond", "shield", "cross", "clock", "bolt", "group")
GLYPH_HUD_GENERATOR = GENERATOR_DIR / "generate_hud_key_glyphs.py"


@pytest.fixture(scope="module")
def hud_glyph_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("hud_key_glyphs")
    _run_generator(GLYPH_HUD_GENERATOR, work)
    return work


def test_hud_key_glyph_count_is_eight(hud_glyph_outputs: Path) -> None:
    assert len(list(hud_glyph_outputs.glob("*.tga"))) == 8
    assert {p.stem for p in hud_glyph_outputs.glob("*.tga")} == {
        f"glyph_hud_{n}" for n in GLYPH_HUD_NAMES}


@pytest.mark.parametrize("name", GLYPH_HUD_NAMES)
def test_hud_key_glyph_is_white_ink_on_transparent_with_padding(
        hud_glyph_outputs: Path, name: str) -> None:
    path = hud_glyph_outputs / f"glyph_hud_{name}.tga"
    assert _is_white(path)
    grid = _alpha_grid(path)
    flat = [a for row in grid for a in row]
    assert max(flat) == 255, "crisp ink"
    assert min(flat) == 0
    assert 0.04 < sum(1 for a in flat if a > 0) / len(flat) < 0.6, "a line icon, not blank or filled"
    # The 16 unit viewBox maps onto 32 texels and every stroke (half width 1.6 texels)
    # ends inside it, so the outermost texels hold at most a thin tail, never a clipped edge.
    edge = grid[0] + grid[-1] + [row[0] for row in grid] + [row[-1] for row in grid]
    assert max(edge) <= 170


@pytest.mark.parametrize("name,horizontal,vertical", [
    ("cross", True, True), ("diamond", True, False),
])
def test_hud_key_glyph_symmetry(
        hud_glyph_outputs: Path, name: str, horizontal: bool, vertical: bool) -> None:
    grid = _alpha_grid(hud_glyph_outputs / f"glyph_hud_{name}.tga")
    for y in range(32):
        for x in range(32):
            if horizontal:
                assert abs(grid[y][x] - grid[y][31 - x]) <= 24, (name, x, y)
            if vertical:
                assert abs(grid[y][x] - grid[31 - y][x]) <= 24, (name, x, y)


def test_hud_key_chev_second_line_is_baked_at_its_stroke_opacity(hud_glyph_outputs: Path) -> None:
    # GLY.chev: first path full strength, second path stroke-opacity .55.
    path = hud_glyph_outputs / "glyph_hud_chev.tga"
    assert _alpha_at(path, 11, 14) == 255
    assert abs(_alpha_at(path, 11, 23) - round(0.55 * 255)) <= 2


def test_hud_key_cross_dot_is_filled_and_ring_is_hollow(hud_glyph_outputs: Path) -> None:
    path = hud_glyph_outputs / "glyph_hud_cross.tga"
    assert _alpha_at(path, 15, 15) == 255 and _alpha_at(path, 16, 16) == 255, "centre dot"
    assert _alpha_at(path, 12, 12) == 0, "inside the ring, off the dot and ticks"
    assert _alpha_at(path, 16, 7) == 255, "the ring's top"


# --- toggle key ring arcs ---------------------------------------------------

RING_GENERATOR = GENERATOR_DIR / "generate_hud_key_ring.py"
RING_N = 16
RING_CANVAS = (128, 64)
RING_KEY = (34.0, 26.0)
RING_PAD = 4.0   # design units of room round the 34 x 26 key for the glow
_RING_INS, _RING_C = 1.8, 6.0
_RING_CP = _RING_C - 0.586 * _RING_INS
# buildRing's polygon, from the top middle, clockwise.
RING_PTS = [
    (17.0, _RING_INS), (34.0 - _RING_INS, _RING_INS),
    (34.0 - _RING_INS, 26.0 - _RING_CP - _RING_INS),
    (34.0 - _RING_CP - _RING_INS, 26.0 - _RING_INS), (_RING_INS, 26.0 - _RING_INS),
    (_RING_INS, _RING_CP + _RING_INS), (_RING_CP + _RING_INS, _RING_INS),
]


def _ring_at(f: float) -> tuple[float, float]:
    """The ring centreline at perimeter fraction f (0 = top middle, clockwise)."""
    segs = [(RING_PTS[i], RING_PTS[(i + 1) % len(RING_PTS)]) for i in range(len(RING_PTS))]
    lens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs]
    d = (f % 1.0) * sum(lens)
    for (a, b), n in zip(segs, lens):
        if d <= n:
            return a[0] + (b[0] - a[0]) * d / n, a[1] + (b[1] - a[1]) * d / n
        d -= n
    return RING_PTS[0]


def _ring_texel(kx: float, ky: float) -> tuple[int, int]:
    return (int((kx + RING_PAD) * RING_CANVAS[0] / (RING_KEY[0] + 2 * RING_PAD)),
            int((ky + RING_PAD) * RING_CANVAS[1] / (RING_KEY[1] + 2 * RING_PAD)))


@pytest.fixture(scope="module")
def ring_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("hud_key_ring")
    _run_generator(RING_GENERATOR, work)
    return work


def test_ring_has_sixteen_distinct_nonempty_white_arcs(ring_outputs: Path) -> None:
    files = sorted(ring_outputs.glob("hud_key_ring_*.tga"))
    assert [p.stem for p in files] == [f"hud_key_ring_{i:02d}" for i in range(RING_N)]
    assert len({p.read_bytes() for p in files}) == RING_N
    for p in files:
        assert _is_white(p)
        assert max(a for row in _alpha_grid(p) for a in row) == 255, p.name


def test_ring_arcs_run_clockwise_from_the_top_middle(ring_outputs: Path) -> None:
    grids = [_alpha_grid(ring_outputs / f"hud_key_ring_{i:02d}.tga") for i in range(RING_N)]
    for i in range(RING_N):
        x, y = _ring_texel(*_ring_at((i + 0.5) / RING_N))
        assert grids[i][y][x] >= 250, f"arc {i} lit at its own midpoint"
        for j in range(RING_N):
            if j != i:
                assert grids[j][y][x] <= 64, f"arc {j} must stay off arc {i}'s midpoint"


def test_ring_arcs_together_cover_the_whole_ring(ring_outputs: Path) -> None:
    grids = [_alpha_grid(ring_outputs / f"hud_key_ring_{i:02d}.tga") for i in range(RING_N)]
    for k in range(512):
        x, y = _ring_texel(*_ring_at(k / 512))
        assert max(g[y][x] for g in grids) >= 250, f"gap in the ring at fraction {k}/512"


def test_ring_stroke_is_crisp_with_a_soft_glow_edge_and_room_to_fade(ring_outputs: Path) -> None:
    grid = _alpha_grid(ring_outputs / "hud_key_ring_00.tga")  # arc 0 covers x 17..23 on the top run
    kx = 20.0
    cx, cy = _ring_texel(kx, _RING_INS)
    assert grid[cy][cx] == 255
    gx, gy = _ring_texel(kx, _RING_INS - 1.5)
    assert 10 < grid[gy][gx] < 200, "glow edge sits between crisp and nothing"
    assert grid[0][cx] < 8, "faded out before the canvas edge"
    ix, iy = _ring_texel(kx, 13.0)
    assert grid[iy][ix] == 0, "nothing in the middle of the key"
    # The stroke is 1.4 units thick: the solid run across it is about 1.4 * (64 / 34) texels.
    solid = sum(1 for y in range(64) if grid[y][cx] >= 250)
    assert 1 <= solid <= 4


def test_committed_ring_and_glyphs_match_their_generators(
        ring_outputs: Path, hud_glyph_outputs: Path, chevron_up_outputs: Path) -> None:
    for out_dir in (ring_outputs, hud_glyph_outputs, chevron_up_outputs):
        for out in sorted(out_dir.glob("*.tga")):
            assert out.read_bytes() == (MEDIA_DIR / out.name).read_bytes(), out.name


# --- Console panel chrome ---------------------------------------------------

CONSOLE_GENERATOR = GENERATOR_DIR / "generate_console_chrome.py"
CN_CHAMFER = 14
CN_PAD = 11
# cnBake halo: HALO = [[width, alpha]...] stroke widths over a 0.9 core stroke, alpha x gk 1.7
# x the .7 overall alpha, image px to design px x 1.28.
CN_HALO = [(1.5, 0.26), (3.2, 0.17), (5.0, 0.10), (7.0, 0.055)]


def _console_glow_alpha(dist: float) -> float:
    keep = 1.0
    for w, a in CN_HALO:
        if dist <= (w + 0.45) * 1.28:
            keep *= 1.0 - min(1.0, a * 1.7 * 0.7)
    return 1.0 - keep


@pytest.fixture(scope="module")
def console_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("console_chrome")
    _run_generator(CONSOLE_GENERATOR, work)
    return work


def test_console_fill_cuts_top_left_and_bottom_right_by_14(console_outputs: Path) -> None:
    path = console_outputs / "console_fill_c14.tga"
    assert _is_white(path)
    assert _alpha_at(path, 5, 5) == 0 and _alpha_at(path, 58, 58) == 0
    assert _alpha_at(path, 63, 0) == 255 and _alpha_at(path, 0, 63) == 255
    assert _alpha_at(path, 20, 0) == 255 and _alpha_at(path, 0, 20) == 255
    assert _alpha_at(path, 32, 32) == 255
    # The cut leg is 14: x + y < 14 is clear, x + y > 15 is solid, along the whole diagonal.
    for k in range(1, 13):
        assert _alpha_at(path, k, 12 - k) == 0, k
        assert _alpha_at(path, k, 16 - k) == 255, k


def test_console_outline_is_a_one_texel_two_corner_stroke(console_outputs: Path) -> None:
    path = console_outputs / "console_outline_c14.tga"
    assert _is_white(path)
    assert _alpha_at(path, 32, 0) == 255 and _alpha_at(path, 0, 32) == 255
    assert _alpha_at(path, 63, 32) == 255 and _alpha_at(path, 32, 63) == 255
    assert _alpha_at(path, 32, 32) == 0, "hollow"
    assert _alpha_at(path, 63, 0) == 255 and _alpha_at(path, 0, 63) == 255, "square corners"
    grid = _alpha_grid(path)
    # The diagonal stroke is as thick as the straight run (1 texel, 1.41 measured down a column).
    for x in range(1, 13):
        column = sum(grid[y][x] for y in range(0, 16)) / 255
        assert 1.2 <= column <= 1.6, (x, column)


def test_console_glow_is_the_mockup_halo_outside_the_cut_chassis_only(
        console_outputs: Path) -> None:
    path = console_outputs / "console_glow_c14.tga"
    assert _is_white(path)
    lo, hi = CN_PAD, 64 - CN_PAD
    poly = [(lo, lo + CN_CHAMFER), (lo + CN_CHAMFER, lo), (hi, lo), (hi, hi - CN_CHAMFER),
            (hi - CN_CHAMFER, hi), (lo, hi)]
    assert _alpha_at(path, 32, 32) == 0, "hollow inside the chassis"
    checked = 0
    for y in range(64):
        for x in range(64):
            cx, cy = x + 0.5, y + 0.5
            dist = _poly_dist(cx, cy, poly)
            if dist < 0.8:
                continue  # a texel straddling the outline is anti-aliased
            if _poly_inside(cx, cy, poly):
                assert _alpha_at(path, x, y) == 0, ("inside", x, y)
                continue
            steps = [(w + 0.45) * 1.28 for w, _ in CN_HALO]
            if min(abs(dist - s) for s in steps) < 0.8:
                continue  # an anti-aliased step boundary
            assert abs(_alpha_at(path, x, y) - 255 * _console_glow_alpha(dist)) <= 6, (x, y)
            checked += 1
    assert checked > 1000
    # Faded out before the canvas edge, so a nine-slice has no hard cutoff.
    assert all(_alpha_at(path, x, 0) == 0 and _alpha_at(path, 0, x) == 0 for x in range(64))
    assert all(_alpha_at(path, x, 63) == 0 and _alpha_at(path, 63, x) == 0 for x in range(64))


# The tab foot canvas covers 59.2 x 49.2 design units: a 39.2 high tab foot (CN_TH) plus a
# halo pad of 10 left and above, and a 10 unit stub of the top edge so the corner joins.
FOOT_W, FOOT_H, FOOT_PAD, FOOT_TH = 59.2, 49.2, 10.0, 39.2


def _foot_design(x: int, y: int) -> tuple[float, float]:
    return (x + 0.5) * FOOT_W / 128, (y + 0.5) * FOOT_H / 128


def test_console_tab_foot_runs_at_45_degrees_with_halo_outside_only(
        console_outputs: Path) -> None:
    path = console_outputs / "console_tab_foot.tga"
    assert _is_white(path)
    grid = _alpha_grid(path)
    # Core pixels (the halo never exceeds 0.6) sit on x + y = FOOT_PAD * 2 + FOOT_TH in design units.
    rows_with_core = 0
    for y in range(128):
        sums = [sum(_foot_design(x, y)) for x in range(128)
                if grid[y][x] >= 230 and _foot_design(x, y)[0] < FOOT_PAD + FOOT_TH - 2]
        if sums:
            rows_with_core += 1
            assert abs(sum(sums) / len(sums) - (2 * FOOT_PAD + FOOT_TH)) < 0.9, y
    assert rows_with_core > 70, "the whole diagonal is stroked"
    # The top edge stub continues the line to the right of the corner.
    top = [x for x in range(128) if grid[int(FOOT_PAD * 128 / FOOT_H)][x] >= 230]
    assert top and max(top) == 127
    poly = [(FOOT_PAD, FOOT_H), (FOOT_PAD + FOOT_TH, FOOT_PAD), (FOOT_W, FOOT_PAD), (FOOT_W, FOOT_H)]
    for y in range(128):
        for x in range(128):
            dx, dy = _foot_design(x, y)
            if _poly_inside(dx, dy, poly) and _poly_dist(dx, dy, poly[:3], closed=False) > 1.2:
                assert grid[y][x] == 0, ("halo leaked inside the tab", x, y)
    # Outside the tab the halo follows the mockup profile at a perpendicular offset of 3.
    ox, oy = _foot_design(0, 0)
    nx = 30.0 - 3 / math.sqrt(2)
    ny = (2 * FOOT_PAD + FOOT_TH) - 30.0 - 3 / math.sqrt(2)
    tx, ty = int(nx * 128 / FOOT_W), int(ny * 128 / FOOT_H)
    want = 255 * _console_glow_alpha(3.0)
    assert abs(grid[ty][tx] - want) <= 14, (grid[ty][tx], want)


def test_console_textures_do_not_overwrite_existing_ones(console_outputs: Path) -> None:
    protected = {"slice_cut2_outline", "slice_cut2_fill", "slice_cut2_glow",
                 "tab_slant", "slice_cut2_border_c6", "slice_cut2_glow_c4"}
    assert not protected & {p.stem for p in console_outputs.glob("*.tga")}


def test_committed_console_textures_match_the_generator(console_outputs: Path) -> None:
    for out in sorted(console_outputs.glob("*.tga")):
        assert out.read_bytes() == (MEDIA_DIR / out.name).read_bytes(), out.name


# --- Paladin shoulder halo ---------------------------------------------------
#
# Every number is hardcoded from the mockup (HALO, CN_GK, A(.7), LS_C 6, LS_F 10) and from the
# Console's own committed glow texture, never read from the generator. The shoulder is haloed in the
# mockup by the SAME stepped profile as the chassis; console_glow_c14.tga draws the straight runs and
# the square corner, shoulder_glow.tga the places it cannot.

SHOULDER_GLOW_GENERATOR = GENERATOR_DIR / "generate_shoulder_glow.py"
SG_PIECES = {"TL": (2, 2, 17, 17), "FLARE": (26, 2, 15, 22), "BL": (48, 2, 11, 11)}  # x, y, w, h
SG_MARGIN = 2
SG_PAD = 11           # texels from the Console glow's edge to its outline
SG_CUT = 6.0          # LS_C
SG_FLARE = 10.0       # LS_F
SG_ABOVE = 12.0       # side shown above the foot's vertex
SG_FAR = 60.0
SG_STROKE_OFF = 0.5 * math.sqrt(2.0) - 0.5   # the 1 px foot stroke's outer edge, above its centreline vertex


@pytest.fixture(scope="module")
def shoulder_glow_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("shoulder_glow")
    _run_generator(SHOULDER_GLOW_GENERATOR, work)
    return work


def _shoulder_piece_paths() -> dict[str, tuple[list, list]]:
    """name -> (outline path, closing points that make it a region), piece-local texels, y down."""
    g, c, f = float(SG_PAD), SG_CUT, SG_FLARE
    return {
        "TL": ([(g, g + SG_FAR), (g, g + c), (g + c, g), (g + SG_FAR, g)], [(g + SG_FAR, g + SG_FAR)]),
        "FLARE": ([(0.0, -SG_FAR), (0.0, SG_ABOVE - SG_STROKE_OFF), (f + SG_STROKE_OFF, SG_ABOVE + f),
                   (SG_FAR, SG_ABOVE + f)], [(SG_FAR, SG_FAR), (-SG_FAR, SG_FAR), (-SG_FAR, -SG_FAR)]),
        "BL": ([(-SG_FAR, g), (g, g), (g, -SG_FAR)], [(SG_FAR, -SG_FAR), (SG_FAR, SG_FAR), (-SG_FAR, SG_FAR)]),
    }


def _oracle_texel(path: list, closing: list, x0: int, y0: int) -> float:
    """The mockup's halo around the outline, averaged over the 1 x 1 texel at (x0, y0) on a 4 x 4 grid (the
    sub-sample grid the Console's own bake uses), 0 inside the shape."""
    shape = path + closing
    total = 0.0
    for sy in range(4):
        for sx in range(4):
            px, py = x0 + (sx + 0.5) / 4, y0 + (sy + 0.5) / 4
            if not _poly_inside(px, py, shape):
                total += _console_glow_alpha(_poly_dist(px, py, path, closed=False))
    return total / 16


def test_shoulder_glow_is_white_and_lights_only_its_three_pieces(shoulder_glow_outputs: Path) -> None:
    path = shoulder_glow_outputs / "shoulder_glow.tga"
    assert _is_white(path)
    grid = _alpha_grid(path)
    lit = set()
    for x, y, w, h in SG_PIECES.values():
        for j in range(y - SG_MARGIN, y + h + SG_MARGIN):
            for i in range(x - SG_MARGIN, x + w + SG_MARGIN):
                lit.add((i, j))
    for j in range(64):
        for i in range(64):
            if (i, j) not in lit:
                assert grid[j][i] == 0, (i, j)
    # the pieces do not touch: their margins stay apart, so the filter never reads a neighbour
    boxes = [(x - SG_MARGIN, y - SG_MARGIN, x + w + SG_MARGIN, y + h + SG_MARGIN) for x, y, w, h in SG_PIECES.values()]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)


@pytest.mark.parametrize("name", sorted(SG_PIECES))
def test_shoulder_glow_piece_is_the_mockup_halo_around_its_outline(
        shoulder_glow_outputs: Path, name: str) -> None:
    grid = _alpha_grid(shoulder_glow_outputs / "shoulder_glow.tga")
    x, y, w, h = SG_PIECES[name]
    path, closing = _shoulder_piece_paths()[name]
    worst = 0.0
    for j in range(-SG_MARGIN, h + SG_MARGIN):
        for i in range(-SG_MARGIN, w + SG_MARGIN):
            want = 255 * _oracle_texel(path, closing, i, j)
            got = grid[y + j][x + i]
            worst = max(worst, abs(got - want))
            assert abs(got - want) <= 2, (name, i, j, got, want)
    assert worst <= 2


def test_shoulder_glow_straight_texels_equal_the_consoles_own(shoulder_glow_outputs: Path,
                                                              console_outputs: Path) -> None:
    """The profile is not just like the Console's, it IS the Console's texel for texel wherever the outline is
    a straight run: the flare piece's side above the vertex against the glow's right edge, the corner piece's
    left arm and top arm against its left and top edges."""
    sg = _alpha_grid(shoulder_glow_outputs / "shoulder_glow.tga")
    cg = _alpha_grid(console_outputs / "console_glow_c14.tga")
    fx, fy, _, _ = SG_PIECES["FLARE"]
    bx, by, _, _ = SG_PIECES["BL"]
    for k in range(SG_PAD):
        for row in range(3):          # three rows of the side, far above the vertex at row 11.8
            assert abs(sg[fy + row][fx + k] - cg[32][53 + k]) <= 2, ("right edge", k, row)
        assert abs(sg[by][bx + k] - cg[32][k]) <= 2, ("left edge", k)
        assert abs(sg[by + k][bx] - cg[k][32]) <= 2, ("top edge", k)
    assert cg[32][53] > 120 and cg[32][53] == max(cg[32][53 + k] for k in range(SG_PAD)), "the peak is at the edge"


def test_shoulder_glow_cut_corner_is_a_45_degree_cut_of_6(shoulder_glow_outputs: Path) -> None:
    sg = _alpha_grid(shoulder_glow_outputs / "shoulder_glow.tga")
    x, y, _, _ = SG_PIECES["TL"]
    g = SG_PAD
    # inside the block, below the cut x + y = 6 (art), nothing; just outside it the peak profile
    for k in range(1, 5):
        assert sg[y + g + k][x + g + 6 - k + 2] == 0, ("inside the shoulder", k)
        assert sg[y + g + k][x + g + 6 - k - 2] > 120, ("just outside the cut", k)


def test_shoulder_glow_pieces_agree_with_petdock_lua() -> None:
    """PetDock.C.SHOULDER_GLOW carries the same rects, the canvas and the pad as this file."""
    text = (REPO / "forever-stuwave" / "Modules/Pet/PetDock.lua").read_text(encoding="utf-8")
    block = re.search(r"SHOULDER_GLOW = \{(.*?)\n    \},", text, re.S)
    assert block, "PetDock.C.SHOULDER_GLOW is gone"
    body = block.group(1)
    for key, want in (("CANVAS", 64), ("PAD", SG_PAD), ("ABOVE", int(SG_ABOVE))):
        assert re.search(rf"\b{key} = {want},", body), key
    for key, rect in (("TL", "TL"), ("FLARE", "FLARE"), ("BL", "BL")):
        nums = tuple(int(n) for n in re.search(rf"\b{key} = \{{ ([\d, ]+) \}}", body).group(1).split(","))
        assert nums == SG_PIECES[rect], (key, nums)


def test_committed_shoulder_glow_matches_the_generator(shoulder_glow_outputs: Path) -> None:
    out = shoulder_glow_outputs / "shoulder_glow.tga"
    assert out.read_bytes() == (MEDIA_DIR / "shoulder_glow.tga").read_bytes()


def test_shoulder_glow_does_not_overwrite_existing_textures(shoulder_glow_outputs: Path) -> None:
    assert {p.stem for p in shoulder_glow_outputs.glob("*.tga")} == {"shoulder_glow"}


# --- Seal Chamber: the seven seal sigils and the lens -----------------------
#
# Every number is hardcoded from drawSealChamber / GLYPH / LW in
# mockups/gunsight-hud-v2-2026-10-02/, never read from a generator. The glyph paths are NOT
# copied here: the test runs the mockup's own GLYPH source under node, flattens what it records
# and checks the baked alpha against it, so a wrong or swapped glyph fails.

SEAL_MOCKUP = (REPO / "mockups" / "gunsight-hud-v2-2026-10-02"
               / "gunsight-hud-v2-2026-10-02.html")
SEAL_GLYPH_GENERATOR = GENERATOR_DIR / "generate_seal_glyphs.py"
SEAL_LENS_GENERATOR = GENERATOR_DIR / "generate_seal_lens.py"
SEAL_RING_GENERATOR = GENERATOR_DIR / "generate_seal_ring.py"
SEAL_IDS = ("righteousness", "crusader", "fury", "command", "light", "wisdom", "justice")

SC_GR = 50.0                       # lens radius, mockup image px
SEAL_LW = 1.3 * 2000.0 / 1400.0    # LW: 1.3 screen px at the 1400 px preview of the 2000 px canvas
GLYPH_SIDE = 64
GLYPH_UNIT = SC_GR * 0.56          # strokeGlyph(..., SC_GR * .56, ...) at 1 texel per image px
GLYPH_STROKE = 1.6 * SEAL_LW       # strokeGlyph(..., LW * 1.6)
LENS_SIDE = 128
LENS_K = 1.2                       # texels per image px
LENS_R = SC_GR * LENS_K
LENS_INNER_R = (SC_GR - 14.0) * LENS_K
LENS_RING_ALPHA, LENS_INNER_ALPHA = 0.28, 0.18
ARC_SPAN = 0.62
RING_SIDE = 256
RING_HALO = ((1.5, 0.26), (3.2, 0.17), (5.0, 0.10), (7.0, 0.055))   # the mockup's HALO table: (reach, alpha)
RING_STROKE = 1.6 * SEAL_LW        # the Judgement ring's stroke, LW * 1.6

_GLYPH_RECORDER_JS = r"""
const src = require('fs').readFileSync(0, 'utf8');
const GLYPH = new Function('Math', src + '\nreturn GLYPH;')(Math);
const out = {};
for (const id of Object.keys(GLYPH)) {
  const ops = [];
  const g = {};
  for (const op of ['m', 'l', 'q', 'b', 'c', 'z']) {
    g[op] = (...a) => { ops.push([op, ...a]); };
  }
  GLYPH[id](g);
  out[id] = ops;
}
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def mockup_glyph_ops() -> dict[str, list[list]]:
    """The mockup's GLYPH table, run under node and recorded as m/l/q/b/c/z calls."""
    if shutil.which("node") is None:
        message = ("node is required to compare seal glyphs against the mockup; "
                   "set FS_SKIP_NODE=1 to skip")
        if os.environ.get("FS_SKIP_NODE") == "1":
            pytest.skip(message)
        pytest.fail(message)
    html = SEAL_MOCKUP.read_text(encoding="utf-8")
    match = re.search(r"var GLYPH=\{.*?\n\};", html, re.S)
    assert match, "the mockup no longer has a `var GLYPH={ ... };` block"
    result = subprocess.run(
        ["node", "-e", _GLYPH_RECORDER_JS],
        input=match.group(0), capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _flatten_glyph(ops: list[list]) -> list[list[tuple[float, float]]]:
    """Polylines in texel space for one glyph, curves cut into 64 steps, circles into 128."""
    def tex(x: float, y: float) -> tuple[float, float]:
        return (GLYPH_SIDE / 2 + x * GLYPH_UNIT, GLYPH_SIDE / 2 + y * GLYPH_UNIT)

    lines: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    start = pt = (0.0, 0.0)
    for op, *a in ops:
        if op == "m":
            start = pt = tex(a[0], a[1])
            cur = [pt]
            lines.append(cur)
        elif op == "l":
            pt = tex(a[0], a[1])
            cur.append(pt)
        elif op == "q":
            p1, p2 = tex(a[0], a[1]), tex(a[2], a[3])
            for i in range(1, 65):
                t = i / 64
                u = 1 - t
                cur.append((u * u * pt[0] + 2 * u * t * p1[0] + t * t * p2[0],
                            u * u * pt[1] + 2 * u * t * p1[1] + t * t * p2[1]))
            pt = p2
        elif op == "b":
            p1, p2, p3 = tex(a[0], a[1]), tex(a[2], a[3]), tex(a[4], a[5])
            for i in range(1, 65):
                t = i / 64
                u = 1 - t
                cur.append((u ** 3 * pt[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0]
                            + t ** 3 * p3[0],
                            u ** 3 * pt[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1]
                            + t ** 3 * p3[1]))
            pt = p3
        elif op == "c":
            cx, cy = tex(a[0], a[1])
            r = a[2] * GLYPH_UNIT
            cur = [(cx + r * math.cos(2 * math.pi * i / 128), cy + r * math.sin(2 * math.pi * i / 128))
                   for i in range(129)]
            start = cur[0]
            pt = cur[-1]
            lines.append(cur)
        elif op == "z":
            cur.append(start)
            pt = start
    return lines


def _glyph_violations(grid: list[list[int]], lines: list[list[tuple[float, float]]]) -> int:
    """How many places the baked alpha disagrees with the stroked path.

    Points on the path's centre line must be solid (the stroke is 2.97 texels, wider than the
    1.41 texel diagonal of the pixel that holds the point); pixels whose centre is more than a
    texel clear of the stroke edge must be empty; pixels whose centre is well inside the stroke
    must be solid.
    """
    half = GLYPH_STROKE / 2
    bad = 0
    for pts in lines:
        for a, b in zip(pts, pts[1:]):
            steps = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 1.5))
            for i in range(steps + 1):
                x = a[0] + (b[0] - a[0]) * i / steps
                y = a[1] + (b[1] - a[1]) * i / steps
                if grid[int(y)][int(x)] < 240:
                    bad += 1
    for y in range(GLYPH_SIDE):
        for x in range(GLYPH_SIDE):
            d = min(_poly_dist(x + 0.5, y + 0.5, pts, closed=False) for pts in lines)
            if d > half + 1.0 and grid[y][x] != 0:
                bad += 1
            elif d < half - 0.8 and grid[y][x] < 250:
                bad += 1
    return bad


@pytest.fixture(scope="module")
def seal_glyph_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("seal_glyphs")
    _run_generator(SEAL_GLYPH_GENERATOR, work)
    return work


@pytest.fixture(scope="module")
def seal_lens_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("seal_lens")
    _run_generator(SEAL_LENS_GENERATOR, work)
    return work


@pytest.fixture(scope="module")
def seal_ring_outputs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    work = tmp_path_factory.mktemp("seal_ring")
    _run_generator(SEAL_RING_GENERATOR, work)
    return work


def test_mockup_has_exactly_the_seven_seal_glyphs(mockup_glyph_ops: dict) -> None:
    assert set(mockup_glyph_ops) == set(SEAL_IDS)


@pytest.mark.parametrize("name", SEAL_IDS)
def test_seal_glyph_is_white_antialiased_alpha_with_room_at_the_edge(
        seal_glyph_outputs: Path, name: str) -> None:
    path = seal_glyph_outputs / f"seal_glyph_{name}.tga"
    assert _is_white(path)
    grid = _alpha_grid(path)
    flat = [a for row in grid for a in row]
    assert max(flat) == 255, "crisp ink"
    assert min(flat) == 0
    assert any(0 < a < 255 for a in flat), "anti-aliased"
    assert 0.03 < sum(1 for a in flat if a > 0) / len(flat) < 0.5, "line art, not blank or filled"
    # The widest glyph extent is 1.02 units (scales, eye): 28.6 texels + half the stroke = 30.1,
    # inside the 32 texel half canvas, so the outermost ring of texels is empty.
    edge = grid[0] + grid[-1] + [row[0] for row in grid] + [row[-1] for row in grid]
    assert max(edge) == 0


@pytest.mark.parametrize("name", SEAL_IDS)
def test_seal_glyph_covers_the_mockup_path_and_nothing_else(
        seal_glyph_outputs: Path, mockup_glyph_ops: dict, name: str) -> None:
    grid = _alpha_grid(seal_glyph_outputs / f"seal_glyph_{name}.tga")
    assert _glyph_violations(grid, _flatten_glyph(mockup_glyph_ops[name])) == 0


def test_seal_glyph_check_rejects_a_swapped_glyph(
        seal_glyph_outputs: Path, mockup_glyph_ops: dict) -> None:
    # Guard the guard: the next glyph's path must NOT validate against this glyph's bake.
    for i, name in enumerate(SEAL_IDS):
        other = SEAL_IDS[(i + 1) % len(SEAL_IDS)]
        grid = _alpha_grid(seal_glyph_outputs / f"seal_glyph_{name}.tga")
        violations = _glyph_violations(grid, _flatten_glyph(mockup_glyph_ops[other]))
        assert violations > 50, (name, other, violations)


def test_seal_glyph_stroke_is_the_mockup_line_width_times_1_6(seal_glyph_outputs: Path) -> None:
    # The scales' stem (x = 0, y -.78 to .8) is the only ink in the middle columns of a row
    # a little above the origin; the row's coverage summed over those columns is its width.
    grid = _alpha_grid(seal_glyph_outputs / "seal_glyph_righteousness.tga")
    row = grid[27]
    width = sum(row[26:38]) / 255
    assert abs(width - GLYPH_STROKE) < 0.15, (width, GLYPH_STROKE)


def test_seal_glyph_origin_is_the_canvas_centre_for_scales_and_eye(
        seal_glyph_outputs: Path) -> None:
    # Checks only the scales and the eye glyphs, not the other five. The scales' stem is centred
    # on the origin column (both texels either side are solid), and the eye's iris ring
    # (r .3 = 8.4 texels) is symmetric about the origin with a gap between it and the pupil
    # ring (r .1 = 2.8 texels, ink to 4.3).
    scales = _alpha_grid(seal_glyph_outputs / "seal_glyph_righteousness.tga")
    assert scales[27][31] == 255 and scales[27][32] == 255
    eye = _alpha_grid(seal_glyph_outputs / "seal_glyph_wisdom.tga")
    assert eye[32][40] == 255 and eye[32][23] == 255, "iris ring either side of the origin"
    assert eye[32][37] == 0 and eye[32][26] == 0, "gap between the pupil and iris rings"


def _lens_alpha_at(grid: list[list[int]], radius: float, angle: float) -> int:
    x = LENS_SIDE / 2 + radius * math.cos(angle)
    y = LENS_SIDE / 2 + radius * math.sin(angle)
    return grid[int(y)][int(x)]


def test_seal_lens_and_arcs_are_white_alpha_only(seal_lens_outputs: Path) -> None:
    for name in ("seal_lens", "seal_arcs"):
        path = seal_lens_outputs / f"{name}.tga"
        assert _is_white(path), name
        flat = [a for row in _alpha_grid(path) for a in row]
        assert max(flat) > 0 and any(0 < a < 255 for a in flat), name
        assert _alpha_grid(path)[64][64] == 0, "empty centre for the glyph"


def test_seal_lens_has_36_ticks_with_every_third_long(seal_lens_outputs: Path) -> None:
    grid = _alpha_grid(seal_lens_outputs / "seal_lens.tga")
    step = math.pi / 18
    # 56.6 texels (47.2 image px): inside both the long (52.2 to 58.8) and the short (55.8 to
    # 58.8) ticks, and a pixel's reach clear of the outer ring's inner edge at 58.9.
    r_both = 56.6
    # SC_GR - 5 image px: inside the long ticks only.
    r_long = (SC_GR - 5.0) * LENS_K
    for i in range(36):
        f = i * step
        assert _lens_alpha_at(grid, r_both, f) > 40, f"tick {i} missing"
        assert _lens_alpha_at(grid, r_both, f + step / 2) == 0, f"stray ink between ticks {i}"
        if i % 3 == 0:
            assert _lens_alpha_at(grid, r_long, f) > 40, f"tick {i} should be long"
        else:
            assert _lens_alpha_at(grid, r_long, f) == 0, f"tick {i} should be short"


def test_seal_lens_rings_sit_at_the_mockup_radii_and_alphas(seal_lens_outputs: Path) -> None:
    grid = _alpha_grid(seal_lens_outputs / "seal_lens.tga")
    step = math.pi / 18
    for i in range(36):
        f = i * step + step / 2   # between ticks
        assert abs(_lens_alpha_at(grid, LENS_R, f) - LENS_RING_ALPHA * 255) <= 6, i
        assert abs(_lens_alpha_at(grid, LENS_INNER_R, f) - LENS_INNER_ALPHA * 255) <= 6, i
        assert _lens_alpha_at(grid, LENS_R + 3.5, f) == 0
        assert _lens_alpha_at(grid, LENS_INNER_R - 6, f) == 0
        assert _lens_alpha_at(grid, 48.0, f) == 0, "between the inner ring and the ticks"


def test_seal_arcs_are_three_butt_ended_arcs_on_the_outer_ring(seal_lens_outputs: Path) -> None:
    grid = _alpha_grid(seal_lens_outputs / "seal_arcs.tga")
    n = 720
    lit = [_lens_alpha_at(grid, LENS_R, 2 * math.pi * i / n) >= 250 for i in range(n)]
    # Runs of lit samples round the ring, wrapping at the seam.
    runs = []
    for i in range(n):
        if lit[i] and not lit[i - 1]:
            j = i
            while lit[(j + 1) % n]:
                j += 1
            runs.append((i, j - i + 1))
    assert len(runs) == 3, runs
    for k, (first, length) in enumerate(sorted(runs)):
        start = 2 * math.pi * first / n
        assert abs(start - k * 2 * math.pi / 3) < 0.04, (k, start)
        assert abs(length * 2 * math.pi / n - ARC_SPAN) < 0.05, (k, length)
    for f in (0.3, 2.4, 4.5):
        assert _lens_alpha_at(grid, LENS_R - 5, f) == 0 and _lens_alpha_at(grid, LENS_R + 3.5, f) == 0
    assert _lens_alpha_at(grid, LENS_R, 1.0) == 0, "gap between the arcs"


def _ring_alpha_at(grid: list[list[int]], radius: float, angle: float) -> int:
    x = RING_SIDE / 2 + radius * math.cos(angle)
    y = RING_SIDE / 2 + radius * math.sin(angle)
    return grid[int(y)][int(x)]


def _ring_expected(dist_img_px: float) -> float:
    """The mockup's glow(col, 1) then the core stroke, composited with "over", at a distance in image px from the
    ring's centre line (alpha 1 = the A(1) the Lua side then scales)."""
    if dist_img_px <= RING_STROKE / 2:
        return 1.0
    keep = 1.0
    for reach, a in RING_HALO:
        if dist_img_px <= RING_STROKE / 2 + reach:
            keep *= 1.0 - a
    return 1.0 - keep


def test_seal_ring_is_white_alpha_only_with_an_empty_centre(seal_ring_outputs: Path) -> None:
    path = seal_ring_outputs / "seal_ring.tga"
    assert _is_white(path)
    grid = _alpha_grid(path)
    flat = [a for row in grid for a in row]
    assert max(flat) == 255 and any(0 < a < 255 for a in flat)
    assert grid[128][128] == 0 and grid[100][100] == 0, "the lens sits inside the ring"


def test_seal_ring_is_a_full_circle_at_the_lens_radius(seal_ring_outputs: Path) -> None:
    grid = _alpha_grid(seal_ring_outputs / "seal_ring.tga")
    n = 720
    for i in range(n):
        f = 2 * math.pi * i / n
        assert _ring_alpha_at(grid, LENS_R, f) >= 250, f"gap in the ring at {f:.3f} rad"
        assert _ring_alpha_at(grid, LENS_R - 12, f) == 0, "ink inside the ring"
        assert _ring_alpha_at(grid, LENS_R + 12, f) == 0, "ink past the halo"


def test_seal_ring_stroke_is_lw_times_one_point_six(seal_ring_outputs: Path) -> None:
    grid = _alpha_grid(seal_ring_outputs / "seal_ring.tga")
    # Along +x from the centre: count the texels whose alpha is 255 (the core). The core is
    # RING_STROKE * LENS_K texels wide (3.57), so 3 or 4 whole texels are solid.
    row = grid[128]
    core = sum(1 for x in range(128, RING_SIDE) if row[x] == 255)
    assert core in (2, 3, 4), core


def test_seal_ring_carries_the_mockups_glow_halo(seal_ring_outputs: Path) -> None:
    grid = _alpha_grid(seal_ring_outputs / "seal_ring.tga")
    edges = [RING_STROKE / 2] + [RING_STROKE / 2 + reach for reach, _ in RING_HALO]
    checked = {0.0: 0}
    for y in range(RING_SIDE):
        for x in range(RING_SIDE):
            d = abs(math.hypot(x + 0.5 - RING_SIDE / 2, y + 0.5 - RING_SIDE / 2) - LENS_R) / LENS_K
            # a texel's anti-aliasing blends across its own footprint (0.71 texel to a corner), so leave the
            # texels that sit that close to a band edge to the supersampler
            if any(abs(d - e) < 0.75 for e in edges):
                continue
            want = _ring_expected(d) * 255
            assert abs(grid[y][x] - want) <= 3, (x, y, d, grid[y][x], want)
            if d > 0:
                checked[0.0] += 1
    assert checked[0.0] > 3000, "the sweep must reach every band"
    # the bands themselves: the halo falls off monotonically outward, then stops
    steps = [_ring_expected(RING_STROKE / 2 + r) for r in (0.1, 1.9, 3.5, 5.5, 7.5)]
    assert steps[0] > steps[1] > steps[2] > steps[3] > 0 == steps[4]


def test_seal_ring_total_ink_matches_the_mockups_stroke_and_halo(seal_ring_outputs: Path) -> None:
    # The area under the whole ring (core and halo) in texel^2 against the mockup's profile integrated
    # round the circle: a thinner or fatter stroke, or a missing halo layer, moves it by several percent.
    grid = _alpha_grid(seal_ring_outputs / "seal_ring.tga")
    got = sum(a for row in grid for a in row) / 255.0
    steps = 4000
    reach = RING_STROKE / 2 + 7.0 + 0.5
    want = 0.0
    for i in range(steps):
        d = -reach + 2 * reach * (i + 0.5) / steps          # signed image px from the centre line
        r_tex = LENS_R + d * LENS_K
        want += _ring_expected(abs(d)) * 2 * math.pi * r_tex * (2 * reach / steps * LENS_K)
    assert abs(got - want) / want < 0.01, (got, want)


def test_seal_ring_halo_fits_the_canvas(seal_ring_outputs: Path) -> None:
    grid = _alpha_grid(seal_ring_outputs / "seal_ring.tga")
    edge = [grid[0][i] + grid[RING_SIDE - 1][i] + grid[i][0] + grid[i][RING_SIDE - 1] for i in range(RING_SIDE)]
    assert max(edge) == 0, "the halo touches the canvas edge, so it would be clipped"
    # the outermost halo texel sits (stroke / 2 + 7) image px past the centre line
    reach = LENS_R + (RING_STROKE / 2 + 7.0) * LENS_K
    assert reach < RING_SIDE / 2
    assert _ring_alpha_at(grid, reach - 1.0, 0.3) > 0


def test_committed_seal_textures_match_their_generators(
        seal_glyph_outputs: Path, seal_lens_outputs: Path, seal_ring_outputs: Path) -> None:
    for out_dir in (seal_glyph_outputs, seal_lens_outputs, seal_ring_outputs):
        for out in sorted(out_dir.glob("*.tga")):
            assert out.read_bytes() == (MEDIA_DIR / out.name).read_bytes(), out.name


if __name__ == "__main__":
    sys.exit(pytest.main([str(Path(__file__).resolve()), "-v"]))
