#!/usr/bin/env python3
"""Publish the generated dashboard to the GitHub Pages output path."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "dashboard" / "index.html"
OUTPUTS = ROOT / "outputs"
REPORT = OUTPUTS / "stock_report.html"
INDEX = OUTPUTS / "index.html"
METADATA = OUTPUTS / "publish_metadata.json"
NOJEKYLL = ROOT / ".nojekyll"
PUBLISH_PATHS = [
    "outputs/stock_report.html",
    "outputs/index.html",
    "outputs/publish_metadata.json",
    ".nojekyll",
]
CLOUD_SOURCE_PATHS = [
    "00_项目说明/CLOUD_REFRESH_SETUP.md",
    "work/cloud/github_pages_refresh_worker.js",
    "work/cloud/refresh_endpoint.txt",
    "work/cache/stock_universe.csv",
    "work/rules/strategy_rules.json",
    "work/scripts/build_dashboard.py",
    "work/scripts/enrich_market_signals.py",
    "work/scripts/fetch_latest_demo_data.py",
    "work/scripts/import_ths_export.py",
    "work/scripts/publish_github_pages.py",
    "work/scripts/refresh_dashboard_data.py",
    "work/scripts/review_next_day.py",
    "work/scripts/rules_config.py",
    "work/scripts/screen_candidates.py",
    "work/scripts/serve_dashboard.py",
    "work/scripts/status_check.py",
    "work/scripts/sync_exchange_universe.py",
    "work/scripts/update_paper_trading.py",
    "wrangler.toml",
    "10_部署Cloudflare Worker.command",
    ".github/workflows/cloud-refresh-dashboard.yml",
]
WORKFLOW_PATHS = {".github/workflows/cloud-refresh-dashboard.yml"}
SKIPPED_OPTIONAL_PATHS: list[str] = []


def rebase_in_progress() -> bool:
    return (ROOT / ".git" / "rebase-merge").exists() or (ROOT / ".git" / "rebase-apply").exists()


def git_auth_args(token_env: str = "") -> list[str]:
    token = os.environ.get(token_env, "").strip() if token_env else ""
    if not token:
        return []
    credential = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
    return [
        "-c",
        f"http.https://github.com/.extraheader=AUTHORIZATION: basic {credential}",
    ]


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        command = " ".join(["git", *args])
        raise SystemExit(
            f"Git 命令超时：{command}\n"
            "通常是终端连接 GitHub 太慢或网络被拦截。请稍后重试，或在发布窗口中输入 GitHub token 使用 API 发布。"
        ) from error
    if check and completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise SystemExit(message)
    return completed


def origin_repo() -> tuple[str, str]:
    remote = run_git(["remote", "get-url", "origin"]).stdout.strip()
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)(?:\.git)?$", remote)
    if not match:
        raise SystemExit(f"无法识别 GitHub 远程仓库地址：{remote}")
    return match.group(1), match.group(2)


def network_unreachable(output: str) -> bool:
    markers = [
        "Could not resolve host",
        "Couldn't connect to server",
        "Failed to connect to github.com",
        "Error in the HTTP2 framing layer",
        "Operation timed out",
        "Connection timed out",
        "Network is unreachable",
    ]
    return any(marker in output for marker in markers)


def github_request(url: str, token: str, method: str = "GET", payload: Optional[dict] = None) -> dict:
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"GitHub API 请求失败：HTTP {error.code}\n{body}") from error
    except URLError as error:
        raise SystemExit(f"GitHub API 网络连接失败：{error}") from error


def existing_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if (ROOT / path).exists()]


def publish_via_github_api(token_env: str, message: str, branch: str, paths: list[str]) -> None:
    token = os.environ.get(token_env, "").strip() if token_env else ""
    if not token:
        raise SystemExit("没有可用的 GitHub token，无法使用 API 发布。")

    owner, repo = origin_repo()
    base_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
    for path in paths:
        file_path = ROOT / path
        if not file_path.exists():
            raise SystemExit(f"待发布文件不存在：{path}")
        content = base64.b64encode(file_path.read_bytes()).decode("ascii")
        sha = None
        try:
            current = github_request(f"{base_url}/{path}?ref={branch}", token)
            sha = current.get("sha")
        except SystemExit as error:
            if "HTTP 404" not in str(error):
                raise
        payload = {
            "message": message,
            "content": content,
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        try:
            github_request(f"{base_url}/{path}", token, method="PUT", payload=payload)
        except SystemExit as error:
            text = str(error)
            if path in WORKFLOW_PATHS and ("HTTP 404" in text or "workflow" in text.lower()):
                SKIPPED_OPTIONAL_PATHS.append(path)
                print(f"跳过工作流文件：{path}")
                print("原因：当前 token 缺少 Workflows 写入权限；网页和普通程序文件已继续发布。")
                continue
            raise
        print(f"已通过 GitHub API 发布：{path}")


def push_with_rebase(branch: str, token_env: str = "", api_paths: list[str] | None = None) -> None:
    auth_args = git_auth_args(token_env)
    print(f"正在推送到 GitHub：origin/{branch} ...")
    first_push = run_git([*auth_args, "push", "origin", branch], check=False)
    if first_push.returncode == 0:
        return

    output = f"{first_push.stdout}\n{first_push.stderr}"
    if "fetch first" in output or "non-fast-forward" in output or "rejected" in output:
        if token_env:
            print("Git 推送遇到远端历史冲突，改用 GitHub API 发布必要文件...")
            publish_via_github_api(
                token_env,
                f"Update stock report {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                branch,
                api_paths or PUBLISH_PATHS,
            )
            return
        raise SystemExit(
            "Git 推送遇到远端历史冲突。请在发布窗口中输入 GitHub token，脚本会只更新 outputs 网页文件，不会合并或覆盖远端程序。"
        )
    if network_unreachable(output):
        raise SystemExit(
            "GitHub 网络连接失败：当前电脑终端无法连接 github.com:443。\n"
            "这不是 token 问题。请先确认浏览器能打开 github.com，或配置可用网络/代理后再发布。"
        )
    if "fetch first" not in output and "non-fast-forward" not in output and "rejected" not in output:
        raise SystemExit(first_push.stderr.strip() or first_push.stdout.strip() or "GitHub 推送失败。")


def dashboard_payload(html_text: str) -> Dict[str, object]:
    match = re.search(r'<script id="dashboard-data" type="application/json">(.*?)</script>', html_text)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def write_outputs() -> Dict[str, object]:
    if not DASHBOARD.exists():
        raise SystemExit("看板文件不存在，请先刷新或构建 dashboard/index.html。")

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    html_text = DASHBOARD.read_text(encoding="utf-8")
    payload = dashboard_payload(html_text)
    shutil.copyfile(DASHBOARD, REPORT)

    INDEX.write_text(
        """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url=stock_report.html">
  <title>A股短线助手</title>
</head>
<body>
  <p><a href="stock_report.html">打开 A股短线助手看板</a></p>
</body>
</html>
""",
        encoding="utf-8",
    )

    metadata = {
        "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": payload.get("trade_date", ""),
        "freshness_status": payload.get("freshness_status", ""),
        "candidate_count": payload.get("summary", {}).get("candidate_count", ""),
        "source": payload.get("primary_source", ""),
        "report": "outputs/stock_report.html",
    }
    METADATA.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    NOJEKYLL.write_text("", encoding="utf-8")
    return metadata


def commit_outputs(message: str, paths: list[str]) -> bool:
    run_git(["add", "-f", *paths])
    diff = run_git(["diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 0:
        print("GitHub Pages 输出没有变化，无需提交。")
        return False
    run_git(["commit", "-m", message])
    print("GitHub Pages 输出已提交。")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish dashboard output for GitHub Pages.")
    parser.add_argument("--commit", action="store_true", help="Commit outputs/ changes.")
    parser.add_argument("--push", action="store_true", help="Push current branch to origin after committing.")
    parser.add_argument("--message", default="", help="Commit message.")
    parser.add_argument("--token-env", default="", help="Environment variable containing a GitHub token for push.")
    parser.add_argument(
        "--publish-cloud-source",
        action="store_true",
        help="Also publish the source files required by GitHub Actions cloud refresh.",
    )
    args = parser.parse_args()

    if rebase_in_progress():
        raise SystemExit("Git 正在同步中途。请先双击 0_修复Git同步状态.command，然后再发布。")

    metadata = write_outputs()
    print(f"已生成 GitHub Pages 文件：{REPORT.relative_to(ROOT)}")
    print(f"固定链接路径：/outputs/stock_report.html")
    print(
        "发布摘要: "
        f"交易日 {metadata.get('trade_date') or '-'}"
        f" | 数据状态 {metadata.get('freshness_status') or '-'}"
        f" | 候选 {metadata.get('candidate_count') or '-'}"
    )

    publish_paths = list(PUBLISH_PATHS)
    if args.publish_cloud_source:
        publish_paths = existing_paths([*PUBLISH_PATHS, *CLOUD_SOURCE_PATHS])

    committed = False
    if args.commit or args.push:
        message = args.message or f"Update stock report {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        committed = commit_outputs(message, publish_paths)
    if args.push:
        branch = run_git(["branch", "--show-current"]).stdout.strip() or "main"
        if args.token_env:
            publish_via_github_api(args.token_env, message, branch, publish_paths)
            print(f"已通过 GitHub API 发布到：origin/{branch}")
            if SKIPPED_OPTIONAL_PATHS:
                print("提醒：固定网页已发布；云端定时刷新工作流文件未更新。若要更新工作流，请给 token 增加 Workflows 写入权限后再发布。")
        else:
            push_with_rebase(branch, args.token_env, publish_paths)
            print(f"已推送到 GitHub：origin/{branch}")
    elif committed:
        print("已提交但未推送；如需发布到线上，请执行 git push。")


if __name__ == "__main__":
    main()
