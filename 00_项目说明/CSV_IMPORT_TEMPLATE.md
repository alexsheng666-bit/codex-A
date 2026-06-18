# CSV Import Template

Version: 0.1
Date: 2026-06-15
Status: Draft

## Purpose

本文件定义第一版 CSV 导入字段。第一版筛选脚本读取 CSV 后，会完成：

- 沪深主板股票池过滤。
- ST、*ST、创业板、科创板、北交所、B 股、退市整理过滤。
- 重点主题标签识别。
- 四种策略的初步规则匹配。
- A/B/C 候选池分层。
- 生成标准化 CSV、卡片式 Markdown 报告和静态 HTML 报告。

样例文件：

`01_原始资料/market_data/raw_csv/sample_market_data.csv`

筛选脚本：

`work/scripts/screen_candidates.py`

## Required Fields

第一版必填字段：

| Field | Meaning |
| --- | --- |
| `trade_date` | 交易日期，格式 `YYYY-MM-DD` |
| `stock_code` | 股票代码，6 位字符串 |
| `stock_name` | 股票名称 |
| `board` | 板块，例如 `沪主板`、`深主板`、`创业板` |
| `market` | 市场，例如 `SH`、`SZ` |
| `industry` | 行业 |
| `concepts` | 概念，多个概念用分号分隔 |
| `open` | 开盘价 |
| `high` | 最高价 |
| `low` | 最低价 |
| `close` | 收盘价 |
| `pre_close` | 前收盘价 |
| `pct_change` | 当日涨跌幅，百分数 |
| `turnover_amount` | 成交额，单位建议统一为元 |
| `turnover_rate` | 换手率，百分数 |
| `volume` | 成交量 |
| `volume_ratio` | 量比 |

## Signal Fields

这些字段用于策略识别。没有分钟线数据时，可先由人工或行情软件导出后补充。

| Field | Meaning |
| --- | --- |
| `tail_rise_pct` | 尾盘涨幅或尾盘推升幅度 |
| `tail_volume_ratio` | 尾盘量能相对强度 |
| `close_position_pct` | 收盘位置，`close / high * 100` 的近似值 |
| `above_vwap_most_day` | 分时是否大部分时间在均价线上方，`是/否` |
| `stepwise_rise_after_1430` | 14:30 后是否阶梯式推升，`是/否` |
| `break_intraday_high` | 是否突破当日高点，`是/否` |
| `break_key_resistance` | 是否突破关键压力位，`是/否` |
| `tail_pullback_holds` | 突破后回踩是否不破，`是/否` |
| `ma5` | 5 日均线 |
| `ma10` | 10 日均线 |
| `ma20` | 20 日均线 |
| `ma_alignment_up` | 均线是否多头向上，`是/否` |
| `pullback_to_ma10_or_ma20` | 是否回踩 10 日或 20 日均线，`是/否` |
| `close_above_ma5` | 收盘是否站上 5 日线，`是/否` |
| `recent_volume_rank_low` | 是否近 5-10 日地量，`是/否` |
| `close_gt_open` | 收盘价是否大于开盘价，`是/否` |
| `kdj_low_turn_up` | KDJ 是否低位拐头，`是/否` |
| `rsi_low_turn_up` | RSI 是否低位拐头，`是/否` |
| `theme_limit_up_count` | 所属主题当日涨停数量 |
| `theme_rank` | 所属主题强度排名，1 为最强 |
| `theme_tail_reflow` | 主题尾盘是否回流，`是/否` |
| `theme_leader_auction` | 次日龙头竞价，可填 `高开`、`低开`、`平开` |

## Output Fields

筛选脚本会新增：

| Field | Meaning |
| --- | --- |
| `universe` | `沪主板`、`深主板` 或空 |
| `universe_eligible` | 是否符合股票池 |
| `exclude_reason` | 剔除原因 |
| `theme_tags` | 命中的重点主题 |
| `is_focus_theme` | 是否命中重点主题 |
| `matched_strategies` | 命中的策略 |
| `primary_strategy` | 主策略 |
| `pool_level` | A/B/C |
| `entry_reasons` | 入池原因 |
| `risk_tags` | 风险标签 |
| `next_day_valid_if` | 次日逻辑成立条件 |
| `next_day_weak_if` | 次日逻辑减弱条件 |
| `next_day_remove_if` | 次日取消关注条件 |

## Run Command

```bash
python3 work/scripts/screen_candidates.py \
  --input 01_原始资料/market_data/raw_csv/sample_market_data.csv \
  --output-csv work/normalized_data/candidates_sample.csv \
  --report work/reports/candidates_sample.md \
  --report-html work/reports/candidates_sample.html
```

输出文件：

- `work/normalized_data/candidates_sample.csv`: 标准化候选池数据。
- `work/reports/candidates_sample.md`: 卡片式文本报告，适合快速查看和版本管理。
- `work/reports/candidates_sample.html`: 可在浏览器打开的视觉报告，更适合盘后复盘。

## Notes

- 第一版规则是辅助筛选，不做买卖建议。
- CSV 字段可以逐步完善，脚本会尽量兼容缺失的可选字段。
- 真正实盘前，应先用历史样本做复盘统计。
