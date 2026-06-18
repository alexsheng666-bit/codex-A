# Strategy Rule Table

Version: 0.1
Date: 2026-06-15
Status: Draft

## Purpose

本文件把 `TRADING_STRATEGY_PLAN.md` 中的文字策略整理为规则表，方便后续转成程序筛选逻辑。

规则表只用于辅助研究、候选池生成和复盘，不构成投资建议。

## Global Rules

| Rule | Value |
| --- | --- |
| 股票池 | 上证主板 + 深证主板 |
| 硬排除 | ST、*ST、创业板、科创板、北交所、B 股、退市整理 |
| 买入窗口 | 14:50-14:57 |
| 优先确认时间 | 14:52 左右 |
| 次日卖出窗口 | 9:30-10:30 |
| 单票仓位 | 总资金 10%-15% 以内 |
| 硬止损 | 买入价下方 -2% 到 -3% |
| 大盘风控 | 大盘当日跌幅超过 -1.5% 时降低仓位或空仓 |
| 禁止动作 | 尾盘 90 度急拉追高、涨幅超过 6%-7% 后继续追尾盘 |

## Strategy Summary

| Strategy ID | Strategy Name | Preferred Pool | Style | Main Edge |
| --- | --- | --- | --- | --- |
| S1 | 攻击型尾盘突破 | A | 进攻 | 尾盘放量突破带来的次日情绪溢价 |
| S2 | 均线回踩支撑尾盘企稳 | B | 稳健 | 趋势回踩后的低风险延续 |
| S3 | 主线热点尾盘回流抢筹 | A/B | 情绪 | 主线板块延续带来的板块溢价 |
| S4 | 地量底部首阳尾盘收稳 | C/B | 左侧 | 抛压衰竭后的修复预期 |

## S1: 攻击型尾盘突破

| Field | Rule |
| --- | --- |
| `strategy_id` | `S1` |
| `strategy_type` | `tail_breakout` |
| `pool_level` | A |
| `entry_conditions` | 14:30 后阶梯式推升；突破当日高点或关键压力位；收盘价大于等于最高价 95%；尾盘 30 分钟放量；量比大于 1.2-1.5；分时多数时间在均价线上方 |
| `buy_condition` | 突破确认后回踩不破，14:52 左右低吸 |
| `exclude_conditions` | 尾盘直线急拉；当日涨幅超过 6%-7% 后追高；量价背离；大盘暴跌仍强做 |
| `sell_plan` | 次日高开 0.5%-2% 且量能跟上，冲高 1.5%-3% 分批止盈 |
| `danger_exit` | 高开超过 3% 后第一波涨不动；低开跌破 -1.5%；9:35 前无法修复 |
| `stop_loss` | -2% 到 -3% |
| `risk_tags` | 高位追涨、冲高回落、放量滞涨、尾盘诱多 |

## S2: 均线回踩支撑尾盘企稳

| Field | Rule |
| --- | --- |
| `strategy_id` | `S2` |
| `strategy_type` | `ma_pullback_support` |
| `pool_level` | B |
| `entry_conditions` | 5 日线大于 10 日线，10 日线大于 20 日线；均线向上发散；盘中回踩 10 日或 20 日线附近获得支撑；尾盘缩量企稳收阳；收盘价站回 5 日线上方；换手率 3%-8% |
| `buy_condition` | 14:50 左右确认支撑有效，股价拐头向上 |
| `exclude_conditions` | 跌破关键均线无法收回；趋势均线走平或拐头向下；换手过低或过热 |
| `sell_plan` | 次日目标 1.5%-3%，见好就收 |
| `danger_exit` | 次日跌破买入当天收盘价支撑位 |
| `stop_loss` | -2% 到 -3% |
| `risk_tags` | 趋势转弱、缩量无承接、支撑失效 |

## S3: 主线热点尾盘回流抢筹

| Field | Rule |
| --- | --- |
| `strategy_id` | `S3` |
| `strategy_type` | `theme_reflow` |
| `pool_level` | A/B |
| `entry_conditions` | 当日最强板块由涨幅榜和涨停数量双重验证；板块涨停数量大于等于 3 只；个股涨幅 3%-5%；量比大于 1.5；分时全天在均价线上方；最后 10 分钟放量翘尾 |
| `buy_condition` | 14:52-14:56 确认板块没有整体跳水，个股翘尾持续 |
| `exclude_conditions` | 龙头或强势股涨幅超过 7%；板块尾盘跳水；龙头竞价弱；情绪退潮 |
| `sell_plan` | 次日 9:25 看板块龙头竞价，龙头高开则等冲高 |
| `danger_exit` | 龙头低开；板块不延续；个股开盘弱于板块 |
| `stop_loss` | -2% 到 -3% |
| `risk_tags` | 情绪退潮、板块未延续、跟风弱化 |

## S4: 地量底部首阳尾盘收稳

| Field | Rule |
| --- | --- |
| `strategy_id` | `S4` |
| `strategy_type` | `low_volume_first_positive` |
| `pool_level` | C/B |
| `entry_conditions` | 前期明显下跌或横盘阴跌；成交量创近 5-10 日地量；不是零成交僵尸股；尾盘温和收阳；收盘价大于开盘价；最好站上短期均线；KDJ 或 RSI 低位拐头 |
| `buy_condition` | 尾盘确认阳线成形且不再回落 |
| `exclude_conditions` | 流动性太差；下跌趋势未止；无量假阳；基本面或公告风险 |
| `sell_plan` | 可给 1-2 天验证；若做一日一夜，目标约 2% |
| `danger_exit` | 次日继续缩量下跌；跌破首阳低点；没有资金承接 |
| `stop_loss` | -2% 到 -3% |
| `risk_tags` | 左侧试错、修复失败、流动性不足 |

## Review Metrics

每笔观察或交易至少记录：

| Field | Purpose |
| --- | --- |
| `strategy_id` | 识别使用哪种打法 |
| `pool_level` | 记录 A/B/C 池 |
| `entry_time` | 检查是否符合 14:50-14:57 |
| `entry_price` | 计算止损和收益 |
| `planned_stop_loss` | 交易前纪律 |
| `next_day_open` | 观察隔夜反馈 |
| `next_day_high` | 统计可兑现空间 |
| `next_day_low` | 统计最大回撤 |
| `exit_time` | 检查是否按 9:30-10:30 处理 |
| `exit_price` | 计算实际收益 |
| `return_pct` | 统计策略效果 |
| `mistake_tag` | 记录失败原因 |
| `review_note` | 沉淀复盘经验 |

## Implementation Notes

- 第一版先用规则标签，不急着做综合评分。
- 筛选程序应先执行硬排除，再判断策略命中。
- 同一只股票可以命中多个策略，但报告中要标记主策略。
- 大盘环境和板块状态应作为交易开关，而不是事后说明。
- 每次输出都必须保留数据来源和采集时间。
