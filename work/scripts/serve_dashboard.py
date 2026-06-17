#!/usr/bin/env python3
"""Serve the local dashboard over HTTP."""

from __future__ import annotations

import argparse
import csv
import errno
import functools
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DASHBOARD_DIR = ROOT / "dashboard"
CANDIDATES_CSV = ROOT / "work" / "normalized_data" / "candidates_latest.csv"
UNIVERSE_CACHE = ROOT / "work" / "cache" / "stock_universe.csv"
NEXT_DAY_REVIEW_CSV = ROOT / "work" / "review" / "next_day_review_latest.csv"
REFRESH_LOCK = threading.Lock()


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/refresh":
            self.send_error(404, "Not found")
            return
        self.handle_refresh()

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/api/health":
            self.write_json(
                200,
                {
                    "ok": True,
                    "project": str(ROOT),
                    "message": "A股短线助手看板服务运行中",
                },
            )
            return
        super().do_GET()

    def handle_refresh(self) -> None:
        if not REFRESH_LOCK.acquire(blocking=False):
            self.write_json(409, {"ok": False, "message": "刷新任务正在执行，请稍后。"})
            return
        try:
            result = refresh_dashboard()
            self.write_json(200 if result["ok"] else 500, result)
        finally:
            REFRESH_LOCK.release()

    def write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_step(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        return subprocess.CompletedProcess(
            args=[sys.executable, *args],
            returncode=124,
            stdout=error.stdout or "",
            stderr=f"Step timeout after {timeout}s",
        )


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return sum(1 for _ in csv.DictReader(file))


def candidate_summary(path: Path) -> dict:
    if not path.exists():
        return {"total_rows": 0, "raw_candidate_count": 0, "candidate_rows": 0}
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    raw_count = sum(
        1
        for row in rows
        if row.get("pool_raw_level") in {"A", "B", "C"} or row.get("pool_level") in {"A", "B", "C"}
    )
    final_count = sum(1 for row in rows if row.get("pool_level") in {"A", "B", "C"})
    return {"total_rows": len(rows), "raw_candidate_count": raw_count, "candidate_rows": final_count}


def source_label(source: str) -> str:
    labels = {
        "Tonghuashun": "同花顺行情列表",
        "Eastmoney": "东方财富行情快照",
        "SinaUniverse": "本地股票池 + 新浪行情",
        "SinaFocus": "新浪重点样本",
        "ExistingSnapshot": "上一次成功快照",
        "AKShare": "AKShare 行情快照",
    }
    return labels.get(source, source or "未知来源")


def summarize_refresh(logs: list[dict]) -> dict:
    fetch_log = next((log for log in logs if "fetch_latest_demo_data.py" in log.get("command", "")), {})
    candidates = candidate_summary(CANDIDATES_CSV)
    cache_rows = count_csv_rows(UNIVERSE_CACHE)
    review_rows = count_csv_rows(NEXT_DAY_REVIEW_CSV)
    stdout = fetch_log.get("stdout", "")
    source = ""
    trade_date = ""
    rows = ""
    fallback_markers = []
    for line in stdout.splitlines():
        if line.startswith("Source:"):
            source = line.split(":", 1)[1].strip()
        elif line.startswith("Latest trade date inferred:"):
            trade_date = line.split(":", 1)[1].strip()
        elif line.startswith("Rows:"):
            rows = line.split(":", 1)[1].strip()
        elif "falling back" in line or "using existing latest snapshot" in line:
            fallback_markers.append(line.strip())
    return {
        "source": source_label(source),
        "source_code": source or "unknown",
        "trade_date": trade_date,
        "rows": int(rows) if rows.isdigit() else rows,
        **candidates,
        "universe_cache": cache_rows,
        "review_rows": review_rows,
        "fallback": bool(fallback_markers),
        "fallback_note": fallback_markers[-1] if fallback_markers else "",
    }


def refresh_dashboard() -> dict:
    steps = [
        {"args": ["work/scripts/sync_exchange_universe.py", "--allow-fail"], "optional": True, "timeout": 45},
        {"args": ["work/scripts/import_ths_export.py", "--allow-empty"], "optional": True, "timeout": 60},
        {
            "args": [
                "work/scripts/fetch_latest_demo_data.py",
                "--output",
                "01_原始资料/market_data/raw_csv/latest_market_data.csv",
            ],
            "timeout": 240,
        },
        {
            "args": [
                "work/scripts/enrich_market_signals.py",
                "--input",
                "01_原始资料/market_data/raw_csv/latest_market_data.csv",
                "--output",
                "01_原始资料/market_data/raw_csv/latest_market_data.csv",
            ],
        },
        {
            "args": [
                "work/scripts/screen_candidates.py",
                "--input",
                "01_原始资料/market_data/raw_csv/latest_market_data.csv",
                "--output-csv",
                "work/normalized_data/candidates_latest.csv",
                "--report",
                "work/reports/candidates_latest.md",
                "--report-html",
                "work/reports/candidates_latest.html",
            ],
        },
        {
            "args": [
                "work/scripts/update_theme_signals.py",
                "--candidates",
                "work/normalized_data/candidates_latest.csv",
                "--output",
                "work/theme_signals/theme_signals_latest.csv",
            ],
            "optional": True,
            "timeout": 180,
        },
        {
            "args": [
                "work/scripts/screen_candidates.py",
                "--input",
                "01_原始资料/market_data/raw_csv/latest_market_data.csv",
                "--output-csv",
                "work/normalized_data/candidates_latest.csv",
                "--report",
                "work/reports/candidates_latest.md",
                "--report-html",
                "work/reports/candidates_latest.html",
            ],
        },
        {
            "args": [
                "work/scripts/review_next_day.py",
                "--candidates",
                "work/normalized_data/candidates_latest.csv",
                "--market",
                "01_原始资料/market_data/raw_csv/latest_market_data.csv",
                "--output",
                "work/review/next_day_review_latest.csv",
                "--report",
                "work/review/next_day_review_latest.md",
            ],
        },
        {
            "args": [
                "work/scripts/update_paper_trading.py",
                "--candidates",
                "work/normalized_data/candidates_latest.csv",
                "--market",
                "01_原始资料/market_data/raw_csv/latest_market_data.csv",
            ],
        },
        {
            "args": [
                "work/scripts/build_dashboard.py",
                "--input",
                "work/normalized_data/candidates_latest.csv",
                "--output",
                "dashboard/index.html",
            ],
        },
    ]
    logs = []
    for step in steps:
        args = step["args"]
        completed = run_step(args, timeout=step.get("timeout", 120))
        logs.append(
            {
                "command": " ".join(args),
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
        )
        if completed.returncode != 0:
            if step.get("optional"):
                continue
            return {"ok": False, "message": "刷新失败。", "logs": logs, "summary": summarize_refresh(logs)}
    return {"ok": True, "message": "数据已刷新。", "logs": logs, "summary": summarize_refresh(logs)}


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def existing_dashboard_server(start_port: int, end_port: int = 8785) -> dict:
    for port in range(start_port, end_port + 1):
        try:
            request = Request(f"http://127.0.0.1:{port}/api/health", headers={"X-Dashboard-Healthcheck": "1"})
            with urlopen(request, timeout=0.35) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("project") == str(ROOT):
                return {"port": port, "payload": payload}
        except Exception:
            pass
        try:
            with urlopen(f"http://127.0.0.1:{port}/", timeout=0.35) as response:
                text = response.read(4096).decode("utf-8", errors="ignore")
            if "A股短线助手" in text and "dashboard-data" in text:
                return {"port": port, "payload": {"legacy": True}}
        except Exception:
            continue
    return {}


def permission_message(host: str) -> str:
    lines = [
        "启动失败：系统没有允许这个本地服务监听端口。",
    ]
    if host == "0.0.0.0":
        lines.extend(
            [
                "当前是局域网访问模式，首次启动时 macOS 可能会询问是否允许 Python 接收网络连接，请选择“允许”。",
                "如果只是本机查看，可以运行：python3 work/scripts/serve_dashboard.py --host 127.0.0.1 --port 8765 --auto-port",
            ]
        )
    else:
        lines.extend(
            [
                "当前已经是仅本机访问模式，仍被拦截时，请在 macOS 的网络权限弹窗中允许 Python，或直接双击 start_dashboard.command 在日常环境中启动。",
                "在 Codex 受限环境里测试服务端口时，也可能出现这个提示；这不代表看板文件或数据生成失败。",
            ]
        )
    return "\n".join(lines)


def create_server(host: str, port: int, handler: object) -> http.server.ThreadingHTTPServer:
    try:
        return http.server.ThreadingHTTPServer((host, port), handler)
    except PermissionError as error:
        raise SystemExit(permission_message(host)) from error
    except OSError as error:
        if getattr(error, "errno", None) in {errno.EACCES, errno.EPERM}:
            raise SystemExit(permission_message(host)) from error
        if getattr(error, "errno", None) == errno.EADDRINUSE:
            raise SystemExit(f"启动失败：端口 {port} 已被占用。可加 --auto-port 自动换端口。") from error
        raise


def create_server_with_port(host: str, preferred_port: int, auto_port: bool, handler: object) -> tuple[int, http.server.ThreadingHTTPServer]:
    candidate_ports = range(preferred_port, preferred_port + 20) if auto_port else [preferred_port]
    occupied_ports = []
    for port in candidate_ports:
        try:
            return port, create_server(host, port, handler)
        except SystemExit as error:
            message = str(error)
            if "已被占用" in message and auto_port:
                occupied_ports.append(port)
                continue
            raise
    used = "、".join(str(port) for port in occupied_ports) or f"{preferred_port}-{preferred_port + 19}"
    raise SystemExit(f"启动失败：端口 {used} 已被占用，请关闭占用程序后重试。")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve dashboard locally.")
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 for LAN access")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--auto-port", action="store_true", help="Use the next available port if the preferred one is busy")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DASHBOARD_DIR)
    parser.add_argument("--reuse-existing", action="store_true", help="Reuse an existing dashboard server if one is already running")
    args = parser.parse_args()

    if not args.dir.exists():
        raise SystemExit(f"Dashboard directory not found: {args.dir}")

    if args.reuse_existing:
        existing = existing_dashboard_server(args.port)
        if existing:
            port = existing["port"]
            print("A股短线助手看板已经在运行")
            print(f"Project: {ROOT}")
            print(f"Local:   http://127.0.0.1:{port}/")
            if args.host == "0.0.0.0":
                print(f"LAN:     http://{local_ip()}:{port}/")
            print("无需重复启动。若要关闭，请双击 4_关闭看板服务.command。")
            return

    handler = functools.partial(NoCacheHandler, directory=str(args.dir))
    port, server = create_server_with_port(args.host, args.port, args.auto_port, handler)

    print("A股短线助手看板已启动")
    print(f"Project: {ROOT}")
    print(f"Local:   http://127.0.0.1:{port}/")
    if args.host == "0.0.0.0":
        print(f"LAN:     http://{local_ip()}:{port}/")
        print("同一 Wi-Fi 下的手机或电脑可以打开 LAN 地址。外出访问建议使用 Tailscale。")
    else:
        print("当前为仅本机访问模式。如需同一 Wi-Fi 访问，请使用 --host 0.0.0.0。")
    if os.environ.get("CODEX_SANDBOX"):
        print("提示：当前可能在受限环境中运行；双击 start_dashboard.command 更接近日常使用环境。")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
