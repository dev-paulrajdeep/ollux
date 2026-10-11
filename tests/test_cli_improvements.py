from ollux.config import Config
from ollux.cli import _handle_slash
import argparse

def test_handle_history():
    messages = [
        {"role": "system", "content": "you are an AI"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"}
    ]
    cfg = Config()
    # just checking it doesn't crash and returns True
    cont, _, _, _, _, msgs = _handle_slash("/history", client=None, cfg=cfg, model="m", math_mode="unicode", raw_mode=False, render_on=True, messages=messages, args=argparse.Namespace())
    assert cont
    assert msgs == messages

def test_handle_export(tmp_path):
    out = tmp_path / "out.md"
    messages = [
        {"role": "system", "content": "you are an AI"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"}
    ]
    cfg = Config()
    args = argparse.Namespace(force=False)
    cont, _, _, _, _, msgs = _handle_slash(f"/export {out}", client=None, cfg=cfg, model="m", math_mode="unicode", raw_mode=False, render_on=True, messages=messages, args=args)
    assert cont

    saved = out.read_text(encoding="utf-8")
    assert "### User" in saved
    assert "hello" in saved
    assert "### Assistant" in saved
    assert "hi" in saved

if __name__ == "__main__":
    import pytest
    pytest.main(["test_cli_improvements.py"])
