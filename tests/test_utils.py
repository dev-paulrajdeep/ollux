"""Utility helpers."""

from ollux.utils import looks_like_model_name, strip_ansi


def test_strip_ansi_csi():
    assert strip_ansi("\x1b[1;31mX\x1b[0m") == "X"


def test_model_heuristic_rejects_spaces():
    assert not looks_like_model_name("a b")
