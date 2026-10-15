"""Mutation checks for tools/private-name-gate.py: every pattern must fire on its sample and
must be the only thing catching it. Samples are assembled from pieces so this file passes the gate."""

import importlib.util
from pathlib import Path

import pytest

GATE_PATH = Path(__file__).resolve().parent / "private-name-gate.py"
spec = importlib.util.spec_from_file_location("private_name_gate", GATE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

NAME = "Park" + "er"
SAMPLES = {
    "personal name": [NAME, NAME.lower() + "'s call", "tells_" + NAME.lower() + "_what", NAME.upper() + " PICK"],
    "legal first name": ["Pa" + "ul", "by pa" + "ul."],
    "mail account": ["air" + "ete@example.org"],
    "local user name": ["kh" + "ildrak"],
    "home directory": ["/ho" + "me/someone/project"],
    "mail domain": ["someone@gma" + "il.com"],
    "windows user path": ["C:" + "\\Us" + "ers\\someone", "c:" + "\\\\us" + "ers\\\\x"],
}
NEAR_MISSES = {
    "personal name": ["s" + "park" + "ers", NAME.lower() + "s", "Park", "sports park"],
    "legal first name": ["Pa" + "ulina", "sp" + "aul" + "ding", "Pa"],
    "mail account": ["air" + "plane"],
    "local user name": ["khil"],
    "home directory": ["homepage", "/home"],
    "mail domain": ["gma" + "il" + "com", "gmailer.com"],
    "windows user path": ["C:" + "\\Prog" + "ram Files"],
}


def labels_hit(text: str, skip: str | None = None) -> set[str]:
    return {label for label, rx in gate.FORBIDDEN.items() if label != skip and rx.search(text)}


def test_every_pattern_has_samples():
    assert set(SAMPLES) == set(gate.FORBIDDEN) == set(NEAR_MISSES)


@pytest.mark.parametrize("label", sorted(SAMPLES))
def test_each_pattern_fires_on_its_samples_and_nothing_else_catches_them(label):
    for sample in SAMPLES[label]:
        assert label in labels_hit(sample), sample
        # Mutation: with this pattern removed the sample goes undetected, so the pattern is load-bearing.
        assert not labels_hit(sample, skip=label), sample


@pytest.mark.parametrize("label", sorted(NEAR_MISSES))
def test_each_pattern_ignores_its_near_misses(label):
    for sample in NEAR_MISSES[label]:
        assert not labels_hit(sample), sample


def test_the_gate_reports_content_and_file_name_hits_and_passes_a_clean_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    (tmp_path / "clean.lua").write_text("-- the player's call\n")
    assert gate.main() == 0
    (tmp_path / "note.md").write_text("fine\nby " + NAME + "\n")
    (tmp_path / (NAME.lower() + ".txt")).write_text("fine\n")
    (tmp_path / "blob.bin").write_bytes(b"\0" + NAME.encode())
    hits = [hit for path in gate.candidate_files() if path.is_file() for hit in gate.find_hits(path)]
    assert len(hits) == 2
    assert any(hit.startswith("note.md:2:") for hit in hits)
    assert any(hit.endswith("file name") for hit in hits)
