"""Start the API server and ARQ worker together for local development."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(sys.executable).resolve().parent
IS_WINDOWS = os.name == "nt"


def _script_path(name: str) -> str:
    suffix = ".exe" if IS_WINDOWS else ""
    path = SCRIPTS_DIR / f"{name}{suffix}"
    return str(path)


def _redis_target() -> tuple[str, int]:
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    parsed = urlparse(redis_url)
    return parsed.hostname or "127.0.0.1", parsed.port or 6379


def _warn_if_redis_unavailable() -> None:
    host, port = _redis_target()
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return
    except OSError:
        print(
            f"[dev] Warning: Redis is not reachable at {host}:{port}. "
            "AI queued tasks will wait until Redis is available.",
            flush=True,
        )


def _start_process(name: str, command: list[str]) -> subprocess.Popen:
    print(f"[dev] Starting {name}: {' '.join(command)}", flush=True)
    return subprocess.Popen(command, cwd=BACKEND_DIR)


def _stop_process(name: str, process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    print(f"[dev] Stopping {name}...", flush=True)
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run AgentChat FastAPI and ARQ worker in one terminal."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8000")
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()

    _warn_if_redis_unavailable()

    api_command = [
        _script_path("uvicorn"),
        "app.main:app",
        "--host",
        args.host,
        "--port",
        args.port,
    ]
    if not args.no_reload:
        api_command.append("--reload")

    worker_command = [
        _script_path("arq"),
        "app.services.task_worker.WorkerSettings",
    ]

    processes: list[tuple[str, subprocess.Popen]] = [
        ("api", _start_process("api", api_command)),
        ("worker", _start_process("worker", worker_command)),
    ]

    def handle_signal(signum, _frame) -> None:
        print(f"[dev] Received signal {signum}; shutting down...", flush=True)
        for process_name, process in reversed(processes):
            _stop_process(process_name, process)

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    try:
        while True:
            for process_name, process in processes:
                return_code = process.poll()
                if return_code is not None:
                    print(
                        f"[dev] {process_name} exited with code {return_code}; shutting down.",
                        flush=True,
                    )
                    for other_name, other_process in reversed(processes):
                        if other_name != process_name:
                            _stop_process(other_name, other_process)
                    return return_code
            signal.pause() if hasattr(signal, "pause") else _sleep()
    finally:
        for process_name, process in reversed(processes):
            _stop_process(process_name, process)


def _sleep() -> None:
    import time

    time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
