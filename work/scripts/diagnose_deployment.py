#!/usr/bin/env python3
"""Diagnose local dashboard deployment readiness."""

from __future__ import annotations

import argparse
import errno
import http.server
import json
from pathlib import Path
from typing import Dict, List

from serve_dashboard import local_ip
from status_check import DASHBOARD, build_status


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PORT = 8765


def check_bind(host: str, port: int) -> Dict[str, object]:
    try:
        server = http.server.ThreadingHTTPServer((host, port), http.server.SimpleHTTPRequestHandler)
        server.server_close()
        return {"host": host, "port": port, "status": "ok", "message": "可以启动"}
    except PermissionError:
        return {"host": host, "port": port, "status": "permission", "message": "系统权限拦截"}
    except OSError as error:
        code = getattr(error, "errno", None)
        if code == errno.EADDRINUSE:
            return {"host": host, "port": port, "status": "occupied", "message": "端口已被占用"}
        if code in {errno.EACCES, errno.EPERM}:
            return {"host": host, "port": port, "status": "permission", "message": "系统权限拦截"}
        return {"host": host, "port": port, "status": "error", "message": str(error)}


def first_available_local_port(start_port: int) -> int:
    for port in range(start_port, start_port + 20):
        result = check_bind("127.0.0.1", port)
        if result["status"] == "ok":
            return port
    return 0


def build_diagnosis(port: int) -> Dict[str, object]:
    status = build_status()
    local_check = check_bind("127.0.0.1", port)
    lan_check = check_bind("0.0.0.0", port)
    suggested_port = port if local_check["status"] == "ok" else first_available_local_port(port)
    actions: List[str] = []

    if not status["dashboard_exists"]:
        actions.append("看板文件缺失：先运行 python3 work/scripts/build_dashboard.py --input work/normalized_data/candidates_latest.csv --output dashboard/index.html")
    if status["raw_rows"] == 0 or status["candidate_rows"] == 0:
        actions.append("数据为空：先双击 start_dashboard_refresh.command 或运行 python3 work/scripts/refresh_dashboard_data.py")
    if status["freshness_status"] in {"可能过期", "无数据日期", "日期异常"}:
        actions.append(f"数据需要确认：{status['freshness_note']}")
    if local_check["status"] == "permission":
        actions.append("本机服务被系统权限拦截：请在 macOS 弹窗中允许 Python 接收网络连接，或双击 start_dashboard.command 在日常环境中启动")
    elif local_check["status"] == "occupied":
        actions.append("8765 端口被占用：启动时使用 --auto-port，或按自检建议端口访问")
    elif local_check["status"] == "ok":
        actions.append(f"本机可用：启动后访问 http://127.0.0.1:{port}/")

    if lan_check["status"] == "ok":
        actions.append(f"同一 Wi-Fi 可用：启动局域网模式后访问 http://{local_ip()}:{port}/")
    elif lan_check["status"] == "permission":
        actions.append("局域网访问需要 macOS 允许 Python 接收网络连接")

    return {
        "project": str(ROOT),
        "dashboard": str(DASHBOARD),
        "dashboard_exists": status["dashboard_exists"],
        "trade_date": status["trade_date"],
        "freshness_status": status["freshness_status"],
        "raw_rows": status["raw_rows"],
        "candidate_rows": status["candidate_rows"],
        "coverage_status": status["coverage_status"],
        "universe_cache_rows": status["universe_cache_rows"],
        "local_check": local_check,
        "lan_check": lan_check,
        "suggested_port": suggested_port,
        "actions": actions,
    }


def print_text(result: Dict[str, object]) -> None:
    print("A股短线助手部署自检")
    print("-" * 32)
    print(f"项目目录: {result['project']}")
    print(f"看板文件: {'已生成' if result['dashboard_exists'] else '缺失'}")
    print(f"最近交易日: {result['trade_date'] or '-'} ({result['freshness_status']})")
    print(f"原始采集: {result['raw_rows']} 行")
    print(f"最终候选: {result['candidate_rows']} 只")
    print(f"股票池缓存: {result['universe_cache_rows']} 支 ({result['coverage_status']})")
    local = result["local_check"]
    lan = result["lan_check"]
    print(f"本机访问检查: {local['message']} ({local['host']}:{local['port']})")
    print(f"局域网访问检查: {lan['message']} ({lan['host']}:{lan['port']})")
    if result["suggested_port"]:
        print(f"建议端口: {result['suggested_port']}")
    print()
    print("下一步建议")
    for index, action in enumerate(result["actions"], start=1):
        print(f"{index}. {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose local dashboard deployment readiness.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = build_diagnosis(args.port)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text(result)


if __name__ == "__main__":
    main()
