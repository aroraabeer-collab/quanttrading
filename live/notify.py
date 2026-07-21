"""macOS desktop notifications for the live daemon (no dependencies).

Used to tell the human when to act — place a condor, or close one. A `Deduper`
keeps the daemon from re-firing the same banner every poll: an alert only repeats
if its content changes or enough time has passed.
"""
from __future__ import annotations

import subprocess
import time


def _escape(s: str) -> str:
    """Escape a string for embedding inside an AppleScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def notify(title: str, message: str, sound: str | None = "Glass") -> bool:
    """Show a macOS notification banner. Returns False if it couldn't be shown."""
    script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
    if sound:
        script += f' sound name "{_escape(sound)}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True,
                       capture_output=True, timeout=10)
        return True
    except Exception:  # noqa: BLE001 — never let a failed banner kill the daemon
        return False


class Deduper:
    """Suppresses repeat notifications.

    A notification fires when its ``key`` differs from the last one, or when
    ``repeat_after`` seconds have elapsed since the same key last fired.
    """

    def __init__(self, repeat_after: float = 1800.0) -> None:
        self.repeat_after = repeat_after
        self._last_key: str | None = None
        self._last_at: float = 0.0

    def should_fire(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if key != self._last_key or (now - self._last_at) >= self.repeat_after:
            self._last_key, self._last_at = key, now
            return True
        return False

    def reset(self) -> None:
        self._last_key, self._last_at = None, 0.0
