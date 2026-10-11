import time
from ollux.utils import Spinner
import sys

def test_spinner(capsys):
    with Spinner("Test", delay=0.01) as spinner:
        time.sleep(0.05)
    # The spinner writes to stderr and uses carriage returns, so we can't easily capture the exact sequence cleanly with capsys in a fast unit test,
    # but we can ensure it starts and stops without error.
    assert not spinner.running

if __name__ == "__main__":
    import pytest
    pytest.main(["test_spinner.py"])
