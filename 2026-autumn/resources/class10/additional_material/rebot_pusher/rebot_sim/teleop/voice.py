"""Spoken prompts for data collection (the operator cannot watch the screen while holding the tool).

Uses speech-dispatcher (``spd-say``, English voice ``en`` via espeak-ng on Ubuntu); falls back to the
terminal bell when it is not available.
"""

from __future__ import annotations

import shutil
import subprocess
import sys


class Voice:
    def __init__(self, enabled: bool = True, lang: str = "en", rate: int = 20) -> None:
        self.enabled = enabled and shutil.which("spd-say") is not None
        self.lang, self.rate = lang, rate
        if enabled and not self.enabled:
            print("! spd-say (speech-dispatcher) not found: the prompts use the terminal bell")

    def say(self, text: str) -> None:
        if not self.enabled:
            sys.stdout.write("\a")
            sys.stdout.flush()
            return
        subprocess.Popen(["spd-say", "-l", self.lang, "-r", str(self.rate), text],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
