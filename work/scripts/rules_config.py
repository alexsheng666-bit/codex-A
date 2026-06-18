#!/usr/bin/env python3
"""Shared strategy rule configuration helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = ROOT / "work" / "rules" / "strategy_rules.json"
DEFAULT_POOL_CAPS = {"A": 5, "B": 10, "C": 20}
DEFAULT_DEFENSE_MODE = {
    "allow_empty_recommendations": True,
    "empty_when_no_a_pool": True,
    "min_a_score": 85,
    "min_b_score": 60,
    "min_c_score": 45,
    "max_severe_risk_count": 1,
    "description": "底层防御：行情特别差、风险巨大或没有合适股票时，可以不推或少推，空仓优先。",
}
DEFAULT_THEME_KEYWORDS = {
    "电力": ["电力", "火电", "水电", "核电", "风电", "光伏发电", "绿电", "电网", "储能", "虚拟电厂", "特高压"],
    "科技": ["科技", "软件", "信息技术", "人工智能", "AI", "算力", "数据中心", "云计算", "通信", "服务器", "信创", "网络安全", "机器人", "消费电子"],
    "商业航天": ["商业航天", "卫星", "卫星互联网", "火箭", "航天", "北斗导航", "空天信息", "遥感", "导航", "低轨卫星"],
    "半导体": ["半导体", "芯片", "集成电路", "晶圆", "封测", "光刻", "EDA", "存储芯片", "功率半导体", "第三代半导体", "先进封装"],
    "PCB": ["PCB", "印制电路板", "覆铜板", "CCL", "HDI", "载板", "IC 载板", "高速板", "高频板"],
}
DEFAULT_WORKFLOW = {
    "name": "盘前主题 → 盘中验证 → 尾盘执行",
    "premarket_theme_layer": {
        "purpose": "先确定当天值得观察的方向，只作为优先级加权，不直接构成买点。",
        "inputs": ["海外行业映射", "产业新闻催化", "A股本地强势板块", "重点主题关键词"],
        "pass_rule": "命中重点主题，或后续接入的盘前主线池。",
    },
    "intraday_validation_layer": {
        "purpose": "确认主题不是只停留在消息层，而是真的有A股量价和分时承接。",
        "checks": ["板块联动", "量比放大", "分时强于均价线", "涨幅不过热", "收盘位置强", "尾盘没有跳水"],
        "pass_rule": "至少出现量能、分时、板块或形态中的两类确认信号。",
    },
    "tail_execution_layer": {
        "purpose": "14:50生成第一版尾盘推荐；14:55用最新价格、成交量、换手率等数据二次校验，并把最终推荐交给模拟盘买入策略。",
        "buy_window": "14:55",
        "preferred_time": "14:55",
        "pass_rule": "必须命中S1/S2/S3/S4之一，并且没有严重风险。",
    },
}


def relative_path(path: Path, root: Path = ROOT) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _read_rules(path: Path) -> Tuple[Dict[str, object], List[str]]:
    if not path.exists():
        return {}, ["规则文件不存在，已使用默认配置"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as error:
        return {}, [f"规则文件 JSON 格式错误：第 {error.lineno} 行第 {error.colno} 列"]


def load_rules(path: Path = DEFAULT_RULES, strict: bool = False) -> Dict[str, object]:
    rules, warnings = _read_rules(path)
    if strict and path.exists() and warnings:
        raise SystemExit(f"规则配置 JSON 格式错误：{path}。")
    return rules


def screening_from_rules(rules: Dict[str, object], path: Path = DEFAULT_RULES, warnings: Optional[List[str]] = None) -> Dict[str, object]:
    warning_items = list(warnings or [])
    caps = dict(DEFAULT_POOL_CAPS)

    screening = rules.get("screening", {}) if isinstance(rules, dict) else {}
    if isinstance(screening, dict):
        configured_caps = screening.get("pool_caps", {})
        if isinstance(configured_caps, dict):
            for pool in ("A", "B", "C"):
                try:
                    raw_value = configured_caps.get(pool, caps[pool])
                    value = int(raw_value)
                    if value < 0:
                        warning_items.append(f"{pool} 池上限不能为负数，已按 0 处理")
                    caps[pool] = max(0, value)
                except (TypeError, ValueError):
                    warning_items.append(f"{pool} 池上限不是有效整数，已使用默认值 {caps[pool]}")

        defense_mode = dict(DEFAULT_DEFENSE_MODE)
        configured_defense = screening.get("defense_mode", {})
        if isinstance(configured_defense, dict):
            for key, value in configured_defense.items():
                if key in {"allow_empty_recommendations", "empty_when_no_a_pool"}:
                    defense_mode[key] = bool(value)
                elif key in {"min_a_score", "min_b_score", "min_c_score", "max_severe_risk_count"}:
                    try:
                        defense_mode[key] = float(value)
                    except (TypeError, ValueError):
                        warning_items.append(f"底层防御参数 {key} 不是有效数字，已使用默认值")
                elif key == "description":
                    defense_mode[key] = str(value)
        elif configured_defense:
            warning_items.append("defense_mode 配置不是有效对象")

        replace_themes = bool(screening.get("replace_theme_keywords", False))
        theme_keywords = {} if replace_themes else {
            theme: list(keywords) for theme, keywords in DEFAULT_THEME_KEYWORDS.items()
        }
        configured_themes = screening.get("theme_keywords", {})
        if isinstance(configured_themes, dict):
            for theme, keywords in configured_themes.items():
                if not isinstance(theme, str) or not theme.strip():
                    continue
                if isinstance(keywords, list):
                    clean_keywords = [str(keyword).strip() for keyword in keywords if str(keyword).strip()]
                    if clean_keywords:
                        theme_keywords[theme.strip()] = clean_keywords
        else:
            warning_items.append("重点主题配置不是有效对象")
    else:
        warning_items.append("缺少 screening 配置段")
        theme_keywords = {theme: list(keywords) for theme, keywords in DEFAULT_THEME_KEYWORDS.items()}
        defense_mode = dict(DEFAULT_DEFENSE_MODE)

    theme_names = list(theme_keywords.keys())
    if not theme_names:
        warning_items.append("重点主题为空，请检查 theme_keywords")

    workflow = rules.get("workflow", {}) if isinstance(rules, dict) else {}
    if not isinstance(workflow, dict):
        warning_items.append("workflow 配置不是有效对象，已使用默认流程")
        workflow = {}
    merged_workflow = dict(DEFAULT_WORKFLOW)
    for key, value in workflow.items():
        if isinstance(value, dict) and isinstance(merged_workflow.get(key), dict):
            merged = dict(merged_workflow[key])
            merged.update(value)
            merged_workflow[key] = merged
        elif value:
            merged_workflow[key] = value

    return {
        "rules_path": relative_path(path),
        "status": "正常" if not warning_items else "需检查",
        "warnings": warning_items,
        "pool_caps": caps,
        "theme_keywords": theme_keywords,
        "theme_names": theme_names,
        "workflow": merged_workflow,
        "defense_mode": defense_mode,
    }


def screening_config(path: Path = DEFAULT_RULES) -> Dict[str, object]:
    rules, warnings = _read_rules(path)
    return screening_from_rules(rules, path=path, warnings=warnings)
