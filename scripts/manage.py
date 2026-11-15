#!/usr/bin/env python3
"""Local application lifecycle. Never removes or recreates the database."""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
STATE = RUNTIME / "processes.json"


def command_for(pid):
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True
    )
    return result.stdout.strip()


def owned(pid):
    return str(ROOT) in command_for(pid)


def state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def stop():
    for name, pid in state().items():
        if owned(pid):
            os.killpg(pid, signal.SIGTERM)
            print(f"{name}: stopped")
    STATE.unlink(missing_ok=True)


def available(port):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def health(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def start():
    current = state()
    if current and all(owned(pid) for pid in current.values()) and len(current) == 2:
        print("Already running: http://127.0.0.1:8765/")
        return
    if any(owned(pid) for pid in current.values()):
        raise SystemExit("Only one service is running. Use restart to repair the pair.")
    for port in (8765, 8766):
        if not available(port):
            raise SystemExit(
                f"Port {port} is already used; no existing process was stopped."
            )
    python = ROOT / ".venv" / "bin" / "python"
    vite = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    node = shutil.which("node")
    if (
        not python.exists()
        or not vite.exists()
        or not node
        or not (ROOT / "frontend" / "dist" / "index.html").exists()
    ):
        raise SystemExit("Run scripts/setup.sh first.")
    RUNTIME.mkdir(exist_ok=True)
    commands = {
        "backend": [
            str(python),
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(ROOT / "backend"),
            "--host",
            "127.0.0.1",
            "--port",
            "8766",
        ],
        "frontend": [
            node,
            str(vite),
            "preview",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--strictPort",
        ],
    }
    processes = {}
    try:
        for name, command in commands.items():
            with (RUNTIME / f"{name}.log").open("ab") as log:
                p = subprocess.Popen(
                    command,
                    cwd=ROOT / "frontend" if name == "frontend" else ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
                processes[name] = p.pid
            STATE.write_text(json.dumps(processes))
        for _ in range(40):
            if health("http://127.0.0.1:8766/api/health") and health(
                "http://127.0.0.1:8765/"
            ):
                print(
                    "Started: http://127.0.0.1:8765/\nAPI docs: http://127.0.0.1:8766/docs"
                )
                return
            time.sleep(0.25)
        raise RuntimeError(
            "Startup failed. Check .runtime/backend.log and .runtime/frontend.log."
        )
    except Exception:
        stop()
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["start", "stop", "restart", "status"])
    cmd = parser.parse_args().command
    if cmd == "stop":
        stop()
    elif cmd == "restart":
        stop()
        time.sleep(0.5)
        start()
    elif cmd == "start":
        start()
    else:
        for name, pid in state().items():
            print(f"{name}: {'running' if owned(pid) else 'stopped'} (pid {pid})")
        print(
            "Application:",
            "ready" if health("http://127.0.0.1:8765/api/health") else "unavailable",
        )


if __name__ == "__main__":
    main()
