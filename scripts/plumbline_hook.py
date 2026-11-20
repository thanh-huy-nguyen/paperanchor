#!/usr/bin/env python3
"""Hook entry point used by hooks/hooks.json: `plumbline_hook.py start|pre|post|stop` with the event on stdin."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plumbline.hook import main  # noqa: E402

main()
