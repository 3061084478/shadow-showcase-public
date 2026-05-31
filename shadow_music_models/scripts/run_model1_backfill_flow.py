from __future__ import annotations

import os
import sys

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.scripts.export_playlist_unknowns_for_chatgpt import main as export_unknowns_main


if __name__ == "__main__":
    raise SystemExit(export_unknowns_main(sys.argv[1:]))
