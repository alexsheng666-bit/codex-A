#!/usr/bin/env python3
"""Screen A-share candidates from a CSV file.

This first version is intentionally rule-based and dependency-free. It is a
research and review aid, not investment advice.
"""

from __future__ import annotations

import argparse
import csv
import html
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from rules_config import DEFAULT_DEFENSE_MODE, DEFAULT_POOL_CAPS, DEFAULT_RULES, DEFAULT_THEME_KEYWORDS, load_rules, screening_from_rules


ROOT = Path(__file__).resolve().parents[2]
INCLUDE_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")
EXCLUDE_PREFIXES = ("300", "301", "688", "8", "4", "9")
POOL_CAPS = dict(DEFAULT_POOL_CAPS)
THEME_KEYWORDS = {theme: list(keywords) for theme, keywords in DEFAULT_THEME_KEYWORDS.items()}
DEFENSE_MODE = dict(DEFAULT_DEFENSE_MODE)
SEVERE_RISKS = {"接近涨停", "换手过热", "尾盘放量但收盘位置弱"}
THEME_SIGNAL_PATH = ROOT / "work" / "theme_signals" / "theme_signals_latest.csv"
THEME_SIGNAL_MAX_SCORE = 10.0
SOURCE_RELIABILITY_SCORES = {
    "official": 3.0,
    "policy": 3.0,
    "exchange": 3.0,
    "company": 2.7,
    "overseas_market": 2.4,
    "market": 2.2,
    "financial_media": 1.8,
    "media": 1.5,
    "self_media": 0.5,
    "rumor": 0.0,
}


def yes(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "是", "对"}


def num(row: Dict[str, str], key: str, default: float = 0.0) -> float:
    raw = str(row.get(key, "")).strip().replace(",", "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def normalize_code(code: str) -> str:
    digits = "".join(ch for ch in str(code or "").strip() if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else ""


def detect_universe(row: Dict[str, str], code: str) -> Tuple[bool, str, str]:
    name = str(row.get("stock_name", "")).strip().upper()
    board = str(row.get("board", "")).strip()

    if any(flag in name for flag in ("*ST", "S*ST", "ST")):
        return False, "", "ST_or_special_treatment"
    if "退" in str(row.get("stock_name", "")):
        return False, "", "delisting_or_delisted"
    if code.startswith(EXCLUDE_PREFIXES):
        return False, "", "excluded_code_prefix"
    if board in {"创业板", "科创板", "北交所", "B股", "退市整理"}:
        return False, "", f"excluded_board:{board}"
    if code.startswith(INCLUDE_PREFIXES):
        if code.startswith(("600", "601", "603", "605")):
            return True, "沪主板", ""
        return True, "深主板", ""
    if board in {"沪主板", "深主板"}:
        return True, board, ""
    return False, "", "not_main_board_universe"


TRUSTED_THEME_FIELDS = ("industry", "concepts", "theme_tags")


def trusted_theme_text(row: Dict[str, str]) -> str:
    return " ".join(str(row.get(key, "")) for key in TRUSTED_THEME_FIELDS).upper()


def detect_themes(row: Dict[str, str]) -> List[str]:
    text = trusted_theme_text(row)
    matched = []
    for theme, keywords in THEME_KEYWORDS.items():
        if any(keyword.upper() in text for keyword in keywords):
            matched.append(theme)
    return matched


def add_reason(reasons: List[str], condition: bool, text: str) -> None:
    if condition:
        reasons.append(text)


def add_risk(risks: List[str], condition: bool, text: str) -> None:
    if condition and text not in risks:
        risks.append(text)


def split_signal_items(value: str) -> List[str]:
    raw = str(value or "").replace("；", ";").replace("，", ",")
    items: List[str] = []
    for chunk in raw.split(";"):
        items.extend(part.strip() for part in chunk.split(",") if part.strip())
    return items


def load_theme_signals(path: Path = THEME_SIGNAL_PATH) -> Dict[str, List[Dict[str, str]]]:
    if not path.exists():
        return {}
    try:
        with path.open(newline="", encoding="utf-8-sig") as file:
            rows = [dict(row) for row in csv.DictReader(file)]
    except OSError:
        return {}

    signals: Dict[str, List[Dict[str, str]]] = {}
    for row in rows:
        themes = split_signal_items(row.get("theme") or row.get("themes") or row.get("theme_tags"))
        for theme in themes:
            signals.setdefault(theme, []).append(row)
    return signals


def bounded_score(value: object, default: float = 0.0, cap: float = THEME_SIGNAL_MAX_SCORE) -> float:
    try:
        score = float(str(value).strip())
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(cap, score))


def signal_freshness_score(signal: Dict[str, str], row: Dict[str, str]) -> float:
    raw_date = (signal.get("signal_date") or signal.get("date") or signal.get("published_at") or "").strip()
    trade_date = (row.get("trade_date") or "").strip()
    if not raw_date or not trade_date:
        return 0.5
    try:
        signal_day = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
        trade_day = datetime.strptime(trade_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return 0.5
    delta = (trade_day - signal_day).days
    if delta == 0:
        return 1.0
    if delta == 1:
        return 0.7
    if 2 <= delta <= 3:
        return 0.3
    return 0.0


def row_theme_relevance_score(signal: Dict[str, str], row: Dict[str, str], theme: str) -> float:
    score = 1.2 if theme in split_signal_items(row.get("theme_tags")) or theme in detect_themes(row) else 0.8
    keywords = split_signal_items(signal.get("keywords") or signal.get("related_keywords"))
    if keywords:
        text = trusted_theme_text(row)
        if any(keyword.upper() in text for keyword in keywords):
            score += 0.8
    else:
        score += 0.4
    return min(2.0, score)


def market_confirmation_score(row: Dict[str, str]) -> float:
    score = 0.0
    if num(row, "theme_limit_up_count") >= 3 or num(row, "real_theme_limit_up_count") >= 3:
        score += 1.0
    if num(row, "theme_rank", 99) <= 3:
        score += 0.7
    if 1.2 <= num(row, "volume_ratio") <= 3:
        score += 0.5
    if yes(row.get("theme_tail_reflow")):
        score += 0.5
    if above_vwap_signal(row):
        score += 0.3
    return min(3.0, score)


def signal_risk_penalty(signal: Dict[str, str], risks: List[str]) -> float:
    explicit = signal.get("risk_penalty") or signal.get("negative_score")
    if explicit not in (None, ""):
        return bounded_score(explicit, cap=1.0)
    risk_text = " ".join(str(signal.get(key, "")) for key in ("risk", "risk_tags", "note"))
    penalty = 0.0
    if any(word in risk_text for word in ("兑现", "高开低走", "炸板", "传闻", "辟谣", "弱关联")):
        penalty += 0.7
    if any(risk in SEVERE_RISKS for risk in risks):
        penalty += 0.3
    return min(1.0, penalty)


def theme_signal_score(
    row: Dict[str, str],
    themes: List[str],
    risks: List[str],
    signals_by_theme: Dict[str, List[Dict[str, str]]],
) -> Tuple[float, str]:
    if not themes:
        return 0.0, "未命中重点主题，不加消息辅助分"

    preset = row.get("theme_signal_score") or row.get("news_signal_score")
    if preset not in (None, ""):
        score = bounded_score(preset)
        detail = row.get("theme_signal_detail") or row.get("news_signal_detail") or "外部数据已给出消息辅助分"
        return score, detail

    best_score = 0.0
    best_detail = "暂无已接入的可靠消息源，消息辅助分为0"
    for theme in themes:
        for signal in signals_by_theme.get(theme, []):
            manual_score = signal.get("score") or signal.get("theme_signal_score")
            if manual_score not in (None, ""):
                score = bounded_score(manual_score)
            else:
                source_type = str(signal.get("source_type") or signal.get("source") or "").strip().lower()
                reliability = bounded_score(signal.get("reliability_score"), default=SOURCE_RELIABILITY_SCORES.get(source_type, 1.0), cap=3.0)
                relevance = bounded_score(signal.get("relevance_score"), default=row_theme_relevance_score(signal, row, theme), cap=2.0)
                confirmation = bounded_score(signal.get("market_confirm_score"), default=market_confirmation_score(row), cap=3.0)
                freshness = bounded_score(signal.get("freshness_score"), default=signal_freshness_score(signal, row), cap=1.0)
                penalty = signal_risk_penalty(signal, risks)
                score = max(0.0, reliability + relevance + confirmation + freshness - penalty)
            score = min(THEME_SIGNAL_MAX_SCORE, score)
            if score > best_score:
                title = signal.get("title") or signal.get("event") or signal.get("source_name") or "主题信号"
                best_score = score
                best_detail = f"{theme}：{title}"

    return round(best_score, 2), best_detail


def match_strategies(row: Dict[str, str], themes: List[str]) -> Tuple[List[str], List[str], List[str]]:
    matched: List[str] = []
    reasons: List[str] = []
    risks: List[str] = []

    pct_change = num(row, "pct_change")
    turnover_rate = num(row, "turnover_rate")
    volume_ratio = num(row, "volume_ratio")
    tail_volume_ratio = num(row, "tail_volume_ratio")
    close_position_pct = num(row, "close_position_pct")
    theme_limit_up_count = num(row, "theme_limit_up_count")
    theme_rank = num(row, "theme_rank", 99)
    ma5, ma10, ma20 = num(row, "ma5"), num(row, "ma10"), num(row, "ma20")
    close = num(row, "close")
    open_price = num(row, "open")

    add_risk(risks, pct_change >= 9.5, "接近涨停")
    add_risk(risks, turnover_rate > 12, "换手过热")
    add_risk(risks, turnover_rate < 1, "流动性不足")
    add_risk(risks, tail_volume_ratio > 2.5 and close_position_pct < 90, "尾盘放量但收盘位置弱")
    add_risk(risks, volume_ratio > 3 and pct_change < 2, "放量滞涨")
    add_risk(risks, pct_change > 6.5 and not high_gain_a_pool_gate_pass(row), "高涨幅A池确认不足")

    s1 = all(
        [
            yes(row.get("stepwise_rise_after_1430")),
            yes(row.get("break_intraday_high")) or yes(row.get("break_key_resistance")),
            close_position_pct >= 95,
            tail_volume_ratio >= 1.2 or volume_ratio >= 1.5,
            above_vwap_signal(row),
        ]
    )
    if s1:
        matched.append("S1")
        reasons.append("攻击型尾盘突破：尾盘阶梯推升、突破压力、收盘接近高位")

    s2 = all(
        [
            yes(row.get("ma_alignment_up")) or (ma5 > ma10 > ma20 > 0),
            yes(row.get("pullback_to_ma10_or_ma20")),
            yes(row.get("close_above_ma5")) or (close > ma5 > 0),
            3 <= turnover_rate <= 8,
        ]
    )
    if s2:
        matched.append("S2")
        reasons.append("均线回踩支撑：多头趋势中回踩企稳")

    s3 = all(
        [
            bool(themes),
            theme_limit_up_count >= 3,
            theme_rank <= 3,
            3 <= pct_change <= 5.5,
            volume_ratio >= 1.5,
            above_vwap_signal(row),
            yes(row.get("theme_tail_reflow")),
        ]
    )
    if s3:
        matched.append("S3")
        reasons.append("主线热点回流：主题强、板块涨停扩散、尾盘回流")

    s4 = all(
        [
            yes(row.get("recent_volume_rank_low")),
            yes(row.get("close_gt_open")) or close > open_price,
            yes(row.get("kdj_low_turn_up")) or yes(row.get("rsi_low_turn_up")),
            turnover_rate >= 1,
        ]
    )
    if s4:
        matched.append("S4")
        reasons.append("地量底部首阳：缩量后温和收阳并出现低位拐头")

    return matched, reasons, risks


def has_real_tail_volume_confirm(row: Dict[str, str]) -> bool:
    if yes(row.get("real_tail_volume_confirmed")) or yes(row.get("tail_volume_confirmed")):
        return True

    source = str(row.get("data_source", "")).lower()
    note = str(row.get("manual_note", ""))
    if "近似" in note or "日线" in note:
        return False

    minute_source_markers = ("minute", "1m", "5m", "intraday", "分时", "分钟")
    return any(marker in source or marker in note for marker in minute_source_markers)


def high_gain_a_pool_gate_pass(row: Dict[str, str]) -> bool:
    pct_change = num(row, "pct_change")
    if pct_change <= 6.5:
        return True
    return num(row, "real_theme_limit_up_count") >= 3 and has_real_tail_volume_confirm(row)


def above_vwap_signal(row: Dict[str, str]) -> bool:
    if row.get("vwap_signal_source"):
        return yes(row.get("above_intraday_vwap"))
    return yes(row.get("above_vwap_most_day"))


def choose_pool(themes: List[str], strategies: List[str], risks: List[str], row: Dict[str, str]) -> str:
    severe_risk_count = sum(risk in SEVERE_RISKS for risk in risks)
    theme_limit_up_count = num(row, "theme_limit_up_count")
    volume_ratio = num(row, "volume_ratio")

    if severe_risk_count >= 2:
        return "C"
    if ("S1" in strategies or "S3" in strategies) and themes and severe_risk_count == 0:
        if not high_gain_a_pool_gate_pass(row):
            return "B"
        return "A"
    if "S2" in strategies or ("S3" in strategies and severe_risk_count <= 1):
        return "B"
    if "S4" in strategies:
        return "C"
    if themes and theme_limit_up_count >= 3 and volume_ratio >= 1.2:
        return "B"
    if themes:
        return "C"
    return ""


def candidate_score(themes: List[str], strategies: List[str], risks: List[str], row: Dict[str, str]) -> float:
    pct_change = num(row, "pct_change")
    volume_ratio = num(row, "volume_ratio")
    turnover_rate = num(row, "turnover_rate")
    turnover_amount = num(row, "turnover_amount")
    close_position_pct = num(row, "close_position_pct")

    score = 0.0
    if themes:
        score += 25 + min(len(themes), 3) * 3
    if "S1" in strategies:
        score += 35
    if "S3" in strategies:
        score += 30
    if "S2" in strategies:
        score += 18
    if "S4" in strategies:
        score += 8

    if 2 <= pct_change < 9.5:
        score += min(15, pct_change * 2)
    elif pct_change >= 9.5:
        score -= 18
    elif pct_change < 0:
        score -= 10

    if 1.2 <= volume_ratio <= 3:
        score += min(10, volume_ratio * 3)
    elif volume_ratio > 3:
        score -= 5

    if 2 <= turnover_rate <= 10:
        score += 8
    elif turnover_rate < 1:
        score -= 10
    elif turnover_rate > 12:
        score -= 12

    if turnover_amount >= 1_000_000_000:
        score += 10
    elif turnover_amount >= 300_000_000:
        score += 6
    elif turnover_amount >= 100_000_000:
        score += 3
    elif turnover_amount and turnover_amount < 50_000_000:
        score -= 5

    if close_position_pct >= 98:
        score += 8
    elif close_position_pct >= 95:
        score += 5
    elif close_position_pct < 85:
        score -= 8

    for risk in risks:
        if risk in {"接近涨停", "换手过热", "尾盘放量但收盘位置弱"}:
            score -= 18
        elif risk == "流动性不足":
            score -= 8
        else:
            score -= 5
    return round(score, 2)


def score_reasons(themes: List[str], strategies: List[str], risks: List[str], row: Dict[str, str]) -> str:
    pct_change = num(row, "pct_change")
    volume_ratio = num(row, "volume_ratio")
    turnover_rate = num(row, "turnover_rate")
    turnover_amount = num(row, "turnover_amount")
    close_position_pct = num(row, "close_position_pct")
    reasons: List[str] = []

    if themes:
        reasons.append(f"命中主题：{';'.join(themes)}")
    if strategies:
        reasons.append(f"策略信号：{';'.join(strategies)}")
    if 2 <= pct_change < 9.5:
        reasons.append("涨幅处于短线可观察区间")
    elif pct_change >= 9.5:
        reasons.append("接近涨停扣分")
    elif pct_change < 0:
        reasons.append("当日下跌扣分")

    if 1.2 <= volume_ratio <= 3:
        reasons.append("量比温和放大")
    elif volume_ratio > 3:
        reasons.append("量比过高扣分")

    if 2 <= turnover_rate <= 10:
        reasons.append("换手处于活跃区间")
    elif turnover_rate < 1:
        reasons.append("换手偏低扣分")
    elif turnover_rate > 12:
        reasons.append("换手过热扣分")

    if turnover_amount >= 1_000_000_000:
        reasons.append("成交额超过10亿")
    elif turnover_amount >= 300_000_000:
        reasons.append("成交额超过3亿")
    elif turnover_amount >= 100_000_000:
        reasons.append("成交额超过1亿")
    elif turnover_amount and turnover_amount < 50_000_000:
        reasons.append("成交额偏低扣分")

    if close_position_pct >= 98:
        reasons.append("收盘接近全天高位")
    elif close_position_pct >= 95:
        reasons.append("收盘位置较强")
    elif close_position_pct < 85:
        reasons.append("收盘位置偏弱扣分")

    if risks:
        reasons.append(f"风险扣分：{';'.join(risks)}")
    else:
        reasons.append("暂无明显风险扣分")
    return "；".join(reasons)


def defense_min_score(pool: str) -> float:
    key = {"A": "min_a_score", "B": "min_b_score", "C": "min_c_score"}.get(pool)
    if not key:
        return 0.0
    try:
        return float(DEFENSE_MODE.get(key, 0))
    except (TypeError, ValueError):
        return 0.0


def apply_defense_gate(pool: str, score: float, risks: List[str]) -> Tuple[str, str]:
    if not pool:
        return "", ""
    severe_count = sum(risk in SEVERE_RISKS for risk in risks)
    max_severe = int(float(DEFENSE_MODE.get("max_severe_risk_count", 1)))
    if severe_count > max_severe:
        return "", f"底层防御：严重风险 {severe_count} 个，超过上限 {max_severe}，不推荐"
    min_score = defense_min_score(pool)
    if score < min_score:
        return "", f"底层防御：评分 {score} 低于{pool}池最低要求 {min_score:g}，不推荐"
    return pool, ""


def apply_empty_market_defense(rows: List[Dict[str, str]]) -> None:
    if not bool(DEFENSE_MODE.get("allow_empty_recommendations", True)):
        return
    if not bool(DEFENSE_MODE.get("empty_when_no_a_pool", True)):
        return
    if any(row.get("pool_level") == "A" for row in rows):
        return

    for row in rows:
        if row.get("pool_level") in {"B", "C"}:
            previous_pool = row.get("pool_level", "")
            note = f"底层防御：没有重点关注标的，行情或信号不足，{previous_pool}池候选改为后台记录，空仓等待"
            row["pool_cap_note"] = note
            row["pool_level"] = ""
            row["tail_execution_layer"] = "空仓等待"
            row["tail_execution_detail"] = "行情或信号不足，没有合适股票可以不推"
            row["workflow_summary"] = f"盘前主题：{row.get('premarket_layer', '')}；盘中验证：{row.get('intraday_layer', '')}；尾盘执行：空仓等待"
            row["buy_point"] = ""
            row["sell_point"] = ""
            row["stop_point"] = ""
            row["first_take_profit_point"] = ""
            row["strong_follow_rule"] = ""
            row["defensive_stop_point"] = ""
            row["moving_take_profit_rule"] = ""
            row["point_basis"] = ""
            row["next_day_valid_if"] = ""
            row["next_day_weak_if"] = ""
            row["next_day_remove_if"] = ""
            existing = row.get("risk_tags", "")
            row["risk_tags"] = f"{existing}；{note}" if existing else note


def workflow_assessment(
    row: Dict[str, str],
    themes: List[str],
    strategies: List[str],
    risks: List[str],
    pool: str,
) -> Dict[str, str]:
    pct_change = num(row, "pct_change")
    turnover_rate = num(row, "turnover_rate")
    volume_ratio = num(row, "volume_ratio")
    tail_volume_ratio = num(row, "tail_volume_ratio")
    close_position_pct = num(row, "close_position_pct")
    theme_limit_up_count = num(row, "theme_limit_up_count")
    theme_rank = num(row, "theme_rank", 99)

    severe_risk_count = sum(risk in SEVERE_RISKS for risk in risks)

    if themes:
        premarket_status = "通过"
        premarket_detail = f"命中重点主题：{';'.join(themes)}"
    else:
        premarket_status = "未命中"
        premarket_detail = "未命中当前重点主题，暂不进入主线优先级"

    validation_signals: List[str] = []
    if 1.2 <= volume_ratio <= 3 or tail_volume_ratio >= 1.2:
        validation_signals.append("量能承接")
    if above_vwap_signal(row):
        validation_signals.append("分时强于均价线")
    if theme_limit_up_count >= 3 or theme_rank <= 3:
        validation_signals.append("板块联动")
    if close_position_pct >= 95:
        validation_signals.append("收盘位置强")
    if strategies:
        validation_signals.append("形态命中")
    if 0 <= pct_change < 9.5 and turnover_rate <= 12:
        validation_signals.append("涨幅/换手未过热")
    if pct_change > 6.5:
        if high_gain_a_pool_gate_pass(row):
            validation_signals.append("高涨幅已通过A池确认")
        else:
            validation_signals.append("高涨幅需板块涨停和真实尾盘量确认")

    if not themes:
        intraday_status = "不足"
    elif severe_risk_count >= 2:
        intraday_status = "降级"
    elif len(validation_signals) >= 2:
        intraday_status = "通过"
    elif validation_signals:
        intraday_status = "待确认"
    else:
        intraday_status = "不足"
    intraday_detail = "；".join(validation_signals) if validation_signals else "等待板块、量能、分时承接确认"

    if pool == "A" and strategies and intraday_status == "通过" and severe_risk_count == 0:
        tail_status = "可尾盘观察"
        tail_detail = "14:50-14:57按命中策略验证，不追直线急拉"
    elif pool and strategies:
        tail_status = "等待确认"
        tail_detail = "有策略形态，但需先排除过热、跳水或承接不足"
    elif pool:
        tail_status = "题材记录"
        tail_detail = "仅作为题材异动或候补记录，暂不进入尾盘执行"
    else:
        tail_status = "不执行"
        tail_detail = "未进入候选池"

    return {
        "premarket_layer": premarket_status,
        "premarket_detail": premarket_detail,
        "intraday_layer": intraday_status,
        "intraday_detail": intraday_detail,
        "tail_execution_layer": tail_status,
        "tail_execution_detail": tail_detail,
        "workflow_summary": f"盘前主题：{premarket_status}；盘中验证：{intraday_status}；尾盘执行：{tail_status}",
    }


def format_price(value: float) -> str:
    if value <= 0:
        return ""
    return f"{value:.2f}"


def execution_points(pool: str, strategies: List[str], row: Dict[str, str]) -> Dict[str, str]:
    if pool != "A":
        return {
            "buy_point": "",
            "sell_point": "",
            "stop_point": "",
            "first_take_profit_point": "",
            "strong_follow_rule": "",
            "defensive_stop_point": "",
            "moving_take_profit_rule": "",
            "point_basis": "",
        }

    buy_price = num(row, "close")
    if buy_price <= 0:
        return {
            "buy_point": "",
            "sell_point": "",
            "stop_point": "",
            "first_take_profit_point": "",
            "strong_follow_rule": "",
            "defensive_stop_point": "",
            "moving_take_profit_rule": "",
            "point_basis": "缺少有效收盘价，暂不计算点位",
        }

    if "S1" in strategies:
        target_pct = 2.0
        stop_pct = 2.5
        basis = "S1尾盘突破：第一止盈+2.0%，防守止损-2.5%；强势票按移动止盈跟踪"
    elif "S3" in strategies:
        target_pct = 2.0
        stop_pct = 2.5
        basis = "S3主线回流：买入按尾盘参考价，止盈+2.0%，止损-2.5%"
    elif "S2" in strategies:
        target_pct = 1.8
        stop_pct = 2.3
        basis = "S2均线支撑：买入按尾盘参考价，止盈+1.8%，止损-2.3%"
    elif "S4" in strategies:
        target_pct = 2.0
        stop_pct = 2.5
        basis = "S4底部首阳：买入按尾盘参考价，止盈+2.0%，止损-2.5%"
    else:
        target_pct = 2.0
        stop_pct = 2.5
        basis = "重点关注：买入按尾盘参考价，止盈+2.0%，止损-2.5%"

    first_take_profit = format_price(buy_price * (1 + target_pct / 100))
    defensive_stop = format_price(buy_price * (1 - stop_pct / 100))
    return {
        "buy_point": format_price(buy_price),
        "sell_point": first_take_profit,
        "stop_point": defensive_stop,
        "first_take_profit_point": first_take_profit,
        "strong_follow_rule": "跌破分时均价线卖出",
        "defensive_stop_point": defensive_stop,
        "moving_take_profit_rule": "浮盈+1.5%止损上移到买入价；+2.5%上移到+1%；+4%后跌破分时均价线卖出",
        "point_basis": basis,
    }


def enforce_pool_caps(rows: List[Dict[str, str]]) -> None:
    for pool, cap in POOL_CAPS.items():
        pool_rows = [row for row in rows if row.get("pool_level") == pool]
        pool_rows.sort(
            key=lambda row: (
                num(row, "candidate_score"),
                num(row, "turnover_amount"),
                num(row, "pct_change"),
            ),
            reverse=True,
        )
        for index, row in enumerate(pool_rows, start=1):
            row["pool_rank"] = str(index)
            if index > cap:
                row["pool_cap_note"] = f"超过{pool}池每日上限{cap}只，保留为未入池记录"
                row["pool_level"] = ""
                row["tail_execution_layer"] = "未入池"
                row["tail_execution_detail"] = "超过当日池级上限，只保留为后台记录"
                row["workflow_summary"] = f"盘前主题：{row.get('premarket_layer', '')}；盘中验证：{row.get('intraday_layer', '')}；尾盘执行：未入池"
                row["buy_point"] = ""
                row["sell_point"] = ""
                row["stop_point"] = ""
                row["first_take_profit_point"] = ""
                row["strong_follow_rule"] = ""
                row["defensive_stop_point"] = ""
                row["moving_take_profit_rule"] = ""
                row["point_basis"] = ""
                row["next_day_valid_if"] = ""
                row["next_day_weak_if"] = ""
                row["next_day_remove_if"] = ""


def next_day_plan(pool: str, strategies: List[str]) -> Tuple[str, str, str]:
    if not pool:
        return "", "", ""
    return (
        "高开0.5%-3%且冲到第一止盈点，先卖50%；放量继续上攻则小仓跟踪",
        "平开或小幅高开，9:45前站不上分时均价线卖出；10:30前未走强退出或降到观察仓",
        "低开超-1.5%且9:35前不能修复卖出；高开超3%第一波拉不动优先卖出；板块龙头低开低走或个股跌破均价线且无量反抽也退出",
    )


def process_rows(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    output = []
    signals_by_theme = load_theme_signals()
    for row in rows:
        row = dict(row)
        code = normalize_code(row.get("stock_code", ""))
        row["stock_code"] = code
        eligible, universe, exclude_reason = detect_universe(row, code)
        themes = detect_themes(row) if eligible else []
        strategies, reasons, risks = match_strategies(row, themes) if eligible else ([], [], [])
        base_score = candidate_score(themes, strategies, risks, row) if eligible else 0
        raw_pool = choose_pool(themes, strategies, risks, row) if eligible else ""
        pool, defense_note = apply_defense_gate(raw_pool, base_score, risks) if eligible else ("", "")
        signal_score, signal_detail = theme_signal_score(row, themes, risks, signals_by_theme) if eligible else (0.0, "")
        score = round(base_score + signal_score, 2) if eligible else 0
        score_reason_text = score_reasons(themes, strategies, risks, row) if eligible else ""
        if eligible:
            score_reason_text = f"{score_reason_text}；消息辅助：+{signal_score:g}/10，{signal_detail}"
        workflow = workflow_assessment(row, themes, strategies, risks, pool) if eligible else {
            "premarket_layer": "",
            "premarket_detail": "",
            "intraday_layer": "",
            "intraday_detail": "",
            "tail_execution_layer": "",
            "tail_execution_detail": "",
            "workflow_summary": "",
        }
        if defense_note:
            risks.append(defense_note)
            reasons.append(defense_note)
            score_reason_text = f"{score_reason_text}；{defense_note}" if score_reason_text else defense_note
        if pool and not reasons:
            reasons.append(f"重点主题观察：命中{';'.join(themes)}，等待量价或板块延续确认")
        valid_if, weak_if, remove_if = next_day_plan(pool, strategies)
        points = execution_points(pool, strategies, row) if eligible else {
            "buy_point": "",
            "sell_point": "",
            "stop_point": "",
            "first_take_profit_point": "",
            "strong_follow_rule": "",
            "defensive_stop_point": "",
            "moving_take_profit_rule": "",
            "point_basis": "",
        }

        row.update(
            {
                "universe": universe,
                "universe_eligible": "是" if eligible else "否",
                "exclude_reason": exclude_reason,
                "theme_tags": ";".join(themes),
                "is_focus_theme": "是" if themes else "否",
                "matched_strategies": ";".join(strategies),
                "primary_strategy": strategies[0] if strategies else "",
                "base_candidate_score": base_score,
                "theme_signal_score": signal_score,
                "theme_signal_detail": signal_detail,
                "candidate_score": score,
                "score_reasons": score_reason_text,
                "pool_raw_level": raw_pool,
                "pool_rank": "",
                "pool_cap_note": "",
                "pool_level": pool,
                "entry_reasons": "；".join(reasons),
                "risk_tags": "；".join(risks) if risks else ("暂无明显风险标签" if pool else ""),
                **workflow,
                **points,
                "next_day_valid_if": valid_if,
                "next_day_weak_if": weak_if,
                "next_day_remove_if": remove_if,
                "data_source": row.get("data_source") or "csv",
                "captured_at": row.get("captured_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        output.append(row)
    apply_empty_market_defense(output)
    enforce_pool_caps(output)
    return output


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize_by_pool(rows: List[Dict[str, str]], pool: str) -> List[Dict[str, str]]:
    return [row for row in rows if row.get("pool_level") == pool]


def split_items(value: str) -> List[str]:
    raw = str(value or "").replace("；", ";")
    return [item.strip() for item in raw.split(";") if item.strip()]


def markdown_tags(value: str) -> str:
    items = split_items(value)
    return " ".join(f"`{item}`" for item in items) if items else "`无`"


def write_report(path: Path, rows: List[Dict[str, str]], source: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    eligible = [row for row in rows if row.get("universe_eligible") == "是"]
    excluded = [row for row in rows if row.get("universe_eligible") != "是"]
    lines = [
        "# Candidate Screening Report",
        "",
        f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Input: `{source}`",
        "",
        "本报告为规则筛选和复盘辅助，不构成投资建议。",
        "",
        "## Summary",
        "",
        f"- Total rows: {len(rows)}",
        f"- Eligible universe: {len(eligible)}",
        f"- Excluded: {len(excluded)}",
        f"- A pool: {len(summarize_by_pool(rows, 'A'))}",
        f"- B pool: {len(summarize_by_pool(rows, 'B'))}",
        f"- C pool: {len(summarize_by_pool(rows, 'C'))}",
        "",
    ]

    for pool, label in (("A", "重点关注"), ("B", "观察候补"), ("C", "题材异动记录")):
        pool_rows = summarize_by_pool(rows, pool)
        lines.extend([f"## {pool} 池：{label}", ""])
        if not pool_rows:
            lines.extend(["暂无候选。", ""])
            continue
        for index, row in enumerate(pool_rows, 1):
            lines.extend(
                [
                    f"### {index}. {row.get('stock_name', '')} `{row.get('stock_code', '')}`",
                    "",
                    f"- **主题**：{markdown_tags(row.get('theme_tags', ''))}",
                    f"- **策略**：{markdown_tags(row.get('matched_strategies', ''))}",
                    f"- **涨跌幅 / 量比 / 换手**：{row.get('pct_change', '')}% / {row.get('volume_ratio', '')} / {row.get('turnover_rate', '')}%",
                    f"- **评分**：总分 {row.get('candidate_score', '')} / 基础 {row.get('base_candidate_score', '')} / 消息辅助 +{row.get('theme_signal_score', '0')}/10（{row.get('theme_signal_detail', '')}）",
                    f"- **三层逻辑**：{row.get('workflow_summary', '') or '待补充'}",
                    f"- **规则点位**：买入 {row.get('buy_point', '') or '-'} / 第一止盈 {row.get('first_take_profit_point', '') or '-'} / 强势跟踪 {row.get('strong_follow_rule', '') or '-'} / 防守止损 {row.get('defensive_stop_point', '') or '-'}",
                    f"- **入选原因**：{row.get('entry_reasons', '') or '暂无'}",
                    f"- **风险标签**：{row.get('risk_tags', '') or '暂无'}",
                    f"- **次日成立**：{row.get('next_day_valid_if', '') or '待补充'}",
                    f"- **次日减弱**：{row.get('next_day_weak_if', '') or '待补充'}",
                    f"- **取消关注**：{row.get('next_day_remove_if', '') or '待补充'}",
                    "",
                ]
            )
        lines.append("")

    if excluded:
        lines.extend(["## Excluded", ""])
        lines.append("| Code | Name | Reason |")
        lines.append("| --- | --- | --- |")
        for row in excluded:
            lines.append(f"| {row.get('stock_code', '')} | {row.get('stock_name', '')} | {row.get('exclude_reason', '')} |")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def html_tag_list(value: str, class_name: str = "tag") -> str:
    items = split_items(value)
    if not items:
        return '<span class="tag muted">无</span>'
    return "".join(f'<span class="{class_name}">{esc(item)}</span>' for item in items)


def write_html_report(path: Path, rows: List[Dict[str, str]], source: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    eligible = [row for row in rows if row.get("universe_eligible") == "是"]
    excluded = [row for row in rows if row.get("universe_eligible") != "是"]
    pool_counts = {pool: len(summarize_by_pool(rows, pool)) for pool in ("A", "B", "C")}

    def metric(label: str, value: object, tone: str = "") -> str:
        return f'<div class="metric {tone}"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>'

    cards = []
    for pool, label in (("A", "重点关注"), ("B", "观察候补"), ("C", "题材异动记录")):
        pool_rows = summarize_by_pool(rows, pool)
        cards.append(f'<section class="pool-section pool-{pool.lower()}">')
        cards.append(
            f'<div class="section-title"><div><span class="pool-badge">{pool}</span>'
            f'<h2>{pool} 池 · {esc(label)}</h2></div><strong>{len(pool_rows)} 只</strong></div>'
        )
        if not pool_rows:
            cards.append('<div class="empty">暂无候选</div>')
            cards.append("</section>")
            continue
        cards.append('<div class="card-grid">')
        for row in pool_rows:
            risks = row.get("risk_tags", "")
            risk_class = "risk-ok" if "暂无明显风险" in risks else "risk-warn"
            cards.append(
                f'''
                <article class="candidate-card">
                  <div class="card-head">
                    <div>
                      <div class="code">{esc(row.get("stock_code"))}</div>
                      <h3>{esc(row.get("stock_name"))}</h3>
                    </div>
                    <div class="change">{esc(row.get("pct_change"))}%</div>
                  </div>
                  <div class="tags">{html_tag_list(row.get("theme_tags", ""))}{html_tag_list(row.get("matched_strategies", ""), "tag strategy")}</div>
                  <div class="numbers">
                    <span>量比 <strong>{esc(row.get("volume_ratio"))}</strong></span>
                    <span>换手 <strong>{esc(row.get("turnover_rate"))}%</strong></span>
                    <span>消息 <strong>+{esc(row.get("theme_signal_score") or "0")}/10</strong></span>
                  </div>
                  <div class="block">
                    <span class="label">三层逻辑</span>
                    <p>{esc(row.get("workflow_summary") or "待补充")}</p>
                  </div>
                  <div class="block">
                    <span class="label">规则点位</span>
                    <p>买入 {esc(row.get("buy_point") or "-")} / 第一止盈 {esc(row.get("first_take_profit_point") or "-")} / 强势跟踪 {esc(row.get("strong_follow_rule") or "-")} / 防守止损 {esc(row.get("defensive_stop_point") or "-")}</p>
                  </div>
                  <div class="block">
                    <span class="label">入选原因</span>
                    <p>{esc(row.get("entry_reasons") or "暂无")}</p>
                  </div>
                  <div class="block {risk_class}">
                    <span class="label">风险</span>
                    <p>{esc(risks or "暂无")}</p>
                  </div>
                  <div class="next-day">
                    <div><span>成立</span><p>{esc(row.get("next_day_valid_if") or "待补充")}</p></div>
                    <div><span>减弱</span><p>{esc(row.get("next_day_weak_if") or "待补充")}</p></div>
                    <div><span>取消</span><p>{esc(row.get("next_day_remove_if") or "待补充")}</p></div>
                  </div>
                </article>
                '''
            )
        cards.append("</div></section>")

    excluded_html = ""
    if excluded:
        items = "\n".join(
            f'<li><strong>{esc(row.get("stock_code"))} {esc(row.get("stock_name"))}</strong><span>{esc(row.get("exclude_reason"))}</span></li>'
            for row in excluded
        )
        excluded_html = f'<section class="excluded"><h2>已剔除</h2><ul>{items}</ul></section>'

    document = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A股短线助手候选池报告</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #18202a;
      --muted: #687385;
      --line: #dfe4ea;
      --red: #c93232;
      --green: #167a4b;
      --amber: #a86405;
      --blue: #2167a8;
      --teal: #0d766f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.5;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px 20px 48px; }}
    header {{ display: flex; justify-content: space-between; gap: 18px; align-items: flex-end; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 6px; font-size: 30px; letter-spacing: 0; }}
    h2, h3 {{ margin: 0; letter-spacing: 0; }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .notice {{ background: #fff7df; border: 1px solid #efd68b; color: #6f5000; padding: 10px 12px; border-radius: 8px; margin-bottom: 16px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; margin: 16px 0 24px; }}
    .metric {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; min-height: 74px; }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; }}
    .metric strong {{ display: block; margin-top: 6px; font-size: 25px; }}
    .metric.a strong {{ color: var(--red); }}
    .metric.b strong {{ color: var(--blue); }}
    .metric.c strong {{ color: var(--teal); }}
    .pool-section {{ margin-top: 22px; }}
    .section-title {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
    .section-title > div {{ display: flex; align-items: center; gap: 10px; }}
    .pool-badge {{ display: inline-flex; width: 36px; height: 36px; align-items: center; justify-content: center; border-radius: 8px; color: #fff; font-weight: 800; background: var(--red); }}
    .pool-b .pool-badge {{ background: var(--blue); }}
    .pool-c .pool-badge {{ background: var(--teal); }}
    .card-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .candidate-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }}
    .card-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: start; }}
    .code {{ color: var(--muted); font-size: 13px; }}
    .card-head h3 {{ font-size: 22px; }}
    .change {{ color: var(--red); font-size: 22px; font-weight: 800; white-space: nowrap; }}
    .tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }}
    .tag {{ border: 1px solid #ccd6e2; background: #f4f8fc; color: #24435f; border-radius: 999px; padding: 3px 8px; font-size: 12px; }}
    .tag.strategy {{ background: #fff1f1; color: #9d2525; border-color: #efc8c8; }}
    .tag.muted {{ color: var(--muted); background: #f2f3f5; }}
    .numbers {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }}
    .numbers span {{ background: #f7f8fa; border: 1px solid #edf0f3; border-radius: 8px; padding: 8px; color: var(--muted); font-size: 12px; }}
    .numbers strong {{ color: var(--ink); }}
    .block {{ border-left: 4px solid var(--blue); background: #f7fbff; padding: 10px 12px; border-radius: 6px; margin-top: 10px; }}
    .block.risk-ok {{ border-left-color: var(--green); background: #f3fbf6; }}
    .block.risk-warn {{ border-left-color: var(--amber); background: #fff8ee; }}
    .label, .next-day span {{ color: var(--muted); font-size: 12px; font-weight: 700; }}
    p {{ margin: 4px 0 0; }}
    .next-day {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }}
    .next-day div {{ background: #fafafa; border: 1px solid #edf0f3; border-radius: 8px; padding: 10px; }}
    .next-day p {{ font-size: 13px; }}
    .empty {{ background: var(--panel); border: 1px dashed #bdc5cf; color: var(--muted); border-radius: 8px; padding: 22px; }}
    .excluded {{ margin-top: 24px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }}
    .excluded ul {{ margin: 12px 0 0; padding: 0; list-style: none; }}
    .excluded li {{ display: flex; justify-content: space-between; gap: 12px; border-top: 1px solid #edf0f3; padding: 10px 0; }}
    .excluded li:first-child {{ border-top: 0; }}
    .excluded span {{ color: var(--muted); }}
    @media (max-width: 820px) {{
      header {{ display: block; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .card-grid, .next-day {{ grid-template-columns: 1fr; }}
      .numbers {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>A股短线助手候选池报告</h1>
        <div class="meta">生成时间：{esc(generated_at)} · 输入：{esc(source)}</div>
      </div>
    </header>
    <div class="notice">本报告为规则筛选和复盘辅助，不构成投资建议。重点看“入选原因、风险、次日条件”，不要只看池级。</div>
    <section class="metrics">
      {metric("总行数", len(rows))}
      {metric("有效股票池", len(eligible))}
      {metric("已剔除", len(excluded))}
      {metric("A 池", pool_counts["A"], "a")}
      {metric("B 池", pool_counts["B"], "b")}
      {metric("C 池", pool_counts["C"], "c")}
    </section>
    {''.join(cards)}
    {excluded_html}
  </main>
</body>
</html>
'''
    path.write_text(document, encoding="utf-8")


def apply_rules_config(rules: Dict[str, object]) -> None:
    global POOL_CAPS, THEME_KEYWORDS, DEFENSE_MODE
    config = screening_from_rules(rules)
    POOL_CAPS = dict(config["pool_caps"])
    THEME_KEYWORDS = {theme: list(keywords) for theme, keywords in config["theme_keywords"].items()}
    DEFENSE_MODE = dict(config.get("defense_mode", DEFAULT_DEFENSE_MODE))


def main() -> None:
    parser = argparse.ArgumentParser(description="Screen A-share short-term candidates from CSV.")
    parser.add_argument("--input", required=True, type=Path, help="Input CSV path")
    parser.add_argument("--output-csv", required=True, type=Path, help="Output normalized CSV path")
    parser.add_argument("--report", required=True, type=Path, help="Output Markdown report path")
    parser.add_argument("--report-html", type=Path, help="Output visual HTML report path")
    parser.add_argument("--rules", default=DEFAULT_RULES, type=Path, help="Rules JSON path")
    args = parser.parse_args()

    rules = load_rules(args.rules, strict=True)
    apply_rules_config(rules)
    with args.input.open("r", newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    processed = process_rows(rows)
    write_csv(args.output_csv, processed)
    write_report(args.report, processed, args.input)
    if args.report_html:
        write_html_report(args.report_html, processed, args.input)

    print(f"Processed {len(processed)} rows")
    print(f"Pool caps: A={POOL_CAPS['A']} B={POOL_CAPS['B']} C={POOL_CAPS['C']}")
    print("Themes: " + "，".join(THEME_KEYWORDS.keys()))
    print(f"Wrote CSV: {args.output_csv}")
    print(f"Wrote report: {args.report}")
    if args.report_html:
        print(f"Wrote HTML report: {args.report_html}")


if __name__ == "__main__":
    main()
