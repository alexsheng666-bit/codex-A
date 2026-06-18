#!/usr/bin/env python3
"""Stop dashboard servers started from this project."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]


def dashboard_port(port: int) -> bool:
    try:
        request = Request(f"http://127.0.0.1:{port}/api/health", headers={"X-Dashboard-Healthcheck": "1"})
        with urlopen(request, timeout=0.35) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("project") == str(ROOT):
            return True
    except Exception:
        pass
    try:
        with urlopen(f"http://127.0.0.1:{port}/", timeout=0.35) as response:
            text = response.read(4096).decode("utf-8", errors="ignore")
        return "A股短线助手" in text and "dashboard-data" in text
    except Exception:
        return False


def pids_on_port(port: int) -> list[int]:
    completed = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    pids: list[int] = []
    for line in completed.stdout.splitlines():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            continue
    return sorted(set(pids))


def main() -> None:
    parser = argparse.ArgumentParser(description="Stop local dashboard servers.")
    parser.add_argument("--start-port", type=int, default=8765)
    parser.add_argument("--end-port", type=int, default=8785)
    args = parser.parse_args()

    stopped: list[tuple[int, int]] = []
    for port in range(args.start_port, args.end_port + 1):
        if not dashboard_port(port):
            continue
        for pid in pids_on_port(port):
            try:
                os.kill(pid, signal.SIGTERM)
                stopped.append((port, pid))
            except OSError as error:
                print(f"端口 {port} 的进程 {pid} 关闭失败：{error}")

    if stopped:
        print("已关闭以下看板服务：")
        for port, pid in stopped:
            print(f"- 端口 {port}，进程 {pid}")
    else:
        print("没有发现需要关闭的 A股短线助手看板服务。")


if __name__ == "__main__":
    main()
