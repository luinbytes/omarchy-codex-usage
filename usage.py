#!/usr/bin/env python3
"""Codex and Cursor/Grok usage for the Omarchy Shell widget."""

import json
import math
import os
import queue
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

APP_NAME = "codex-quickshell-usage"
CURSOR_USAGE_URL = "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage"


def env_int(name, default, minimum=0, maximum=10_000):
    try:
        return max(minimum, min(maximum, int(os.environ.get(name, default))))
    except ValueError:
        return default


def number(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def rounded(value):
    return int(math.copysign(math.floor(abs(value) + 0.5), value))


def percent(value):
    value = number(value)
    return None if value is None else max(0, min(100, rounded(value)))


def window_label(window):
    seconds = number(window.get("limit_window_seconds"), 0)
    if seconds <= 6 * 60 * 60:
        return "5h"
    if seconds <= 8 * 24 * 60 * 60:
        return "weekly"
    return f"{round(seconds / 86400)}d"


def duration_text(seconds):
    seconds = max(0, int(seconds))
    if seconds == 0:
        return "now"
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def pace(window, used, now):
    duration = number(window.get("limit_window_seconds"), 0)
    if duration <= 0:
        return None

    used = max(0.0, min(100.0, number(used, 0)))
    reset = number(window.get("reset_at"))
    elapsed = (
        used / 100 if reset is None else (duration - max(0, reset - now)) / duration
    )
    elapsed = max(0.001, min(0.999, elapsed))
    remaining = 100 - used
    margin = remaining - 100 * (1 - elapsed)

    if margin > 4:
        state, status, glyph = "ahead", "under pace", "▲"
    elif margin < -4:
        state, status, glyph = "behind", "over pace", "▼"
    else:
        state, status, glyph = "onpace", "on pace", "●"
    if remaining <= 0.5:
        status, glyph = "spent", "■"
    elif remaining >= 99.5:
        status, glyph = "full", "◆"

    slope = (remaining - 100) / elapsed
    show_projection = slope < -0.01
    projection_elapsed = 1.0
    projected_remaining = remaining
    runs_out = False
    if show_projection:
        runout = elapsed + remaining / -slope
        if runout <= 1:
            projection_elapsed, projected_remaining, runs_out = runout, 0.0, True
        else:
            projected_remaining = max(0.0, remaining + slope * (1 - elapsed))

    effective_reset = (
        reset if reset is not None and reset > now else now + (1 - elapsed) * duration
    )
    return {
        "used": used,
        "status": status,
        "glyph": glyph,
        "pace_state": state,
        "margin": margin,
        "elapsed": elapsed,
        "projection_elapsed": projection_elapsed,
        "projected": 100 - projected_remaining,
        "show_projection": show_projection,
        "runs_out": runs_out,
        "effective_reset": effective_reset,
    }


def request_rate_limits(timeout=None):
    timeout = timeout or env_int("CODEX_QUICKSHELL_TIMEOUT", 12, 1, 60)
    codex = os.environ.get("CODEX_BIN") or shutil.which("codex")
    if not codex:
        bundled = Path("/usr/lib/chatgpt/resources/codex")
        if bundled.is_file() and os.access(bundled, os.X_OK):
            codex = str(bundled)
        else:
            raise RuntimeError("Codex executable not found; set CODEX_BIN")
    process = subprocess.Popen(
        [codex, "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    messages = queue.Queue()
    threading.Thread(
        target=lambda: [messages.put(json.loads(line)) for line in process.stdout],
        daemon=True,
    ).start()

    def send(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def receive(request_id):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Codex app-server did not respond")
            try:
                message = messages.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError("Codex app-server did not respond") from error
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(
                    message["error"].get("message", "Codex app-server error")
                )
            return message["result"]

    try:
        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": APP_NAME, "version": "1"}},
            }
        )
        receive(1)
        send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read"})
        return receive(2)
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()


def cursor_access_token():
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    database = config / "Cursor/User/globalStorage/state.vscdb"
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT value FROM ItemTable WHERE key = 'cursorAuth/accessToken'"
        ).fetchone()
    finally:
        connection.close()
    if not row or not str(row[0]).strip():
        raise RuntimeError("Cursor is not signed in")
    return str(row[0])


def request_cursor_usage(timeout=None):
    timeout = timeout or env_int("GROK_USAGE_TIMEOUT", 12, 1, 60)
    request = urllib.request.Request(
        CURSOR_USAGE_URL,
        data=b"{}",
        headers={
            "Authorization": f"Bearer {cursor_access_token()}",
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.URLError as error:
        raise RuntimeError("Cursor usage did not respond") from error
    if not isinstance(payload, dict):
        raise RuntimeError("Cursor usage response was not an object")
    return payload


def epoch_seconds(value):
    value = number(value)
    if value is None:
        return None
    return value / 1000 if value > 1e12 else value


def windows_from_cursor(payload):
    plan = payload.get("planUsage") if isinstance(payload, dict) else None
    if not isinstance(plan, dict):
        return []
    used = percent(plan.get("totalPercentUsed"))
    start = epoch_seconds(payload.get("billingCycleStart"))
    end = epoch_seconds(payload.get("billingCycleEnd"))
    if used is None or start is None or end is None or end <= start:
        return []
    windows = [
        {
            "used_percent": used,
            "limit_window_seconds": end - start,
            "reset_at": end,
        }
    ]
    return windows


def normalize_windows(result):
    by_id = result.get("rateLimitsByLimitId") or {}
    snapshot = by_id.get("codex") if isinstance(by_id, dict) else None
    if not snapshot or not any(snapshot.get(key) for key in ("primary", "secondary")):
        snapshot = result.get("rateLimits") or {}

    windows = []
    for key in ("primary", "secondary"):
        source = snapshot.get(key)
        if not isinstance(source, dict):
            continue
        minutes = number(source.get("windowDurationMins"), 0)
        used = percent(source.get("usedPercent"))
        if used is None or minutes <= 0:
            continue
        window = {"used_percent": used, "limit_window_seconds": minutes * 60}
        if number(source.get("resetsAt")) is not None:
            window["reset_at"] = number(source["resetsAt"])
        windows.append(window)
    return windows


def fetch_windows():
    return normalize_windows(request_rate_limits())


def select_windows(windows):
    valid = [
        window
        for window in windows
        if percent(window.get("used_percent")) is not None
        and number(window.get("limit_window_seconds"), 0) > 0
    ]
    if not valid:
        return None, None
    session = next((window for window in valid if window_label(window) == "5h"), None)
    weekly = next(
        (window for window in valid if window_label(window) == "weekly"), None
    )
    weekly = weekly or max(
        valid, key=lambda window: number(window.get("limit_window_seconds"), 0)
    )
    return (None if session is weekly else session), weekly


def derive_state(windows, now=None):
    now = time.time() if now is None else now
    session, weekly = select_windows(windows)
    if weekly is None:
        return None
    pacing = pace(weekly, number(weekly.get("used_percent"), 0), now)
    if pacing is None:
        return None
    reset = pacing["effective_reset"]
    seconds = max(0, int(reset - now))
    days, remainder = divmod(seconds, 86400)
    relative = f"{days}d {remainder // 3600}h" if days else duration_text(seconds)
    return {
        **pacing,
        "session_used": None
        if session is None
        else percent(session.get("used_percent")),
        "weekly_reset_at": number(weekly.get("reset_at")),
        "session_reset_at": None if session is None else number(session.get("reset_at")),
        "reset": f"{relative}  ·  {datetime.fromtimestamp(reset, UTC).astimezone().strftime('%a %H:%M')}",
    }


def quickshell_output(windows, now=None):
    state = derive_state(windows, now)
    if state is None:
        return {"available": False, "remaining": None}
    return {
        "available": True,
        "remaining": 100 - percent(state["used"]),
        "session_used": state["session_used"],
        "weekly_reset_at": state["weekly_reset_at"],
        "session_reset_at": state["session_reset_at"],
        "used": state["used"],
        "status": state["status"],
        "glyph": state["glyph"],
        "pace_state": state["pace_state"],
        "margin": abs(rounded(state["margin"])),
        "elapsed": state["elapsed"],
        "projection_elapsed": state["projection_elapsed"],
        "projected": state["projected"],
        "show_projection": state["show_projection"],
        "reset": state["reset"],
        "segments": burn_segments(state["used"], state["elapsed"]),
    }


def burn_segments(used, elapsed, periods=7):
    burn_rate = used / elapsed if elapsed > 0.001 else 0
    ideal = 100 / periods
    segments = []
    for index in range(periods):
        start, end = index / periods, (index + 1) / periods
        if end <= elapsed:
            width, alpha, consumed = 1.0, 0.17, burn_rate * (end - start)
        elif start < elapsed:
            width = (elapsed - start) / (end - start)
            alpha, consumed = 0.13, burn_rate * (elapsed - start)
        else:
            segments.append((1.0, 1.0, None))
            continue
        segments.append((width, consumed / ideal, alpha))
    return segments


def self_test():
    payload = {
        "rateLimits": {"primary": None, "secondary": None},
        "rateLimitsByLimitId": {
            "codex": {
                "primary": {
                    "usedPercent": 20,
                    "windowDurationMins": 300,
                    "resetsAt": 13167,
                },
                "secondary": {
                    "usedPercent": 15,
                    "windowDurationMins": 10080,
                    "resetsAt": 441531,
                },
            }
        },
    }
    windows = normalize_windows(payload)
    assert len(windows) == 2 and windows[0]["limit_window_seconds"] == 18000
    state = derive_state(windows, now=27)
    assert state["status"] == "under pace" and abs(rounded(state["margin"])) == 12
    assert state["session_used"] == 20 and round(state["projected"]) == 56
    quickshell = quickshell_output(windows, now=27)
    assert quickshell["remaining"] == 85 and len(quickshell["segments"]) == 7
    assert normalize_windows({"rateLimits": {"primary": None, "secondary": None}}) == []
    runout = pace({"limit_window_seconds": 100, "reset_at": 100}, 70, 50)
    assert runout["runs_out"] and abs(runout["projection_elapsed"] - 5 / 7) < 1e-9
    segments = burn_segments(50, 0.5)
    assert len(segments) == 7 and segments[0][2] == 0.17 and segments[3][2] == 0.13
    assert segments[4][2] is None
    assert rounded(0.5) == 1 and rounded(-0.5) == -1
    from contextlib import redirect_stderr
    from io import StringIO
    from unittest.mock import patch

    cursor_payload = {
        "planUsage": {"totalPercentUsed": 81, "apiPercentUsed": 20},
        "billingCycleStart": 1700000000000,
        "billingCycleEnd": 1702592000000,
    }
    cursor_windows = windows_from_cursor(cursor_payload)
    assert len(cursor_windows) == 1
    assert quickshell_output(cursor_windows)["session_used"] is None
    assert windows_from_cursor({}) == []
    with patch(__name__ + ".request_rate_limits", return_value=payload), patch(
        __name__ + ".request_cursor_usage", return_value=cursor_payload
    ):
        output = fetch_usage()
        assert output["remaining"] == 85 and output["grok"]["remaining"] == 19
    with redirect_stderr(StringIO()), patch(
        __name__ + ".request_rate_limits", side_effect=TimeoutError("unavailable")
    ), patch(__name__ + ".request_cursor_usage", return_value=cursor_payload):
        output = fetch_usage()
        assert not output["available"] and output["grok"]["remaining"] == 19
    with redirect_stderr(StringIO()), patch(
        __name__ + ".request_rate_limits", return_value=payload
    ), patch(__name__ + ".request_cursor_usage", side_effect=sqlite3.OperationalError("unavailable")):
        output = fetch_usage()
        assert output["remaining"] == 85 and not output["grok"]["available"]
    print(f"{APP_NAME} self-test: ok")


def fetch_provider(provider):
    try:
        windows = (fetch_windows() if provider == "codex"
                   else windows_from_cursor(request_cursor_usage()))
        return quickshell_output(windows)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(f"{APP_NAME}: {provider} refresh failed ({type(error).__name__})", file=sys.stderr)
        return quickshell_output([])


def fetch_usage():
    with ThreadPoolExecutor(max_workers=2) as executor:
        codex = executor.submit(fetch_provider, "codex")
        grok = executor.submit(fetch_provider, "grok")
        return {**codex.result(), "grok": grok.result()}


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        print(json.dumps(fetch_usage()))
