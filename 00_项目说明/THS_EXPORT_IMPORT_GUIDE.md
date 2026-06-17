# Tonghuashun Export Import Guide

Version: 0.1
Date: 2026-06-15
Status: Draft

## Purpose

把同花顺手动导出的股票列表、行业、概念数据导入本地股票池缓存。

导入结果写入：

`work/cache/stock_universe.csv`

该缓存用于后续刷新失败时的批量行情补充，也用于逐步扩大沪深主板评估范围。

## Where To Put Files

将同花顺导出的 CSV 或 Excel 文件放入：

`01_原始资料/market_data/manual_exports`

该目录内容已加入 `.gitignore`，真实导出文件不会被提交到 GitHub。

## Supported Columns

脚本会自动识别常见表头。

必需：

- `代码`、`股票代码`、`证券代码`
- `名称`、`股票名称`、`证券名称`、`股票简称`

可选：

- `行业`、`所属行业`、`细分行业`、`同花顺行业`
- `概念`、`所属概念`、`概念题材`、`题材`、`概念板块`、`所属板块`

## Filter Rules

导入时自动保留：

- 上证主板。
- 深证主板。

自动剔除：

- ST、*ST、退市整理。
- 创业板。
- 科创板。
- 北交所。
- B 股。

## Run

导入默认文件夹内所有 CSV/Excel：

```bash
python3 work/scripts/import_ths_export.py
```

导入指定文件：

```bash
python3 work/scripts/import_ths_export.py \
  --input 01_原始资料/market_data/manual_exports/同花顺导出.csv
```

只测试不写入：

```bash
python3 work/scripts/import_ths_export.py \
  --input 01_原始资料/market_data/manual_exports/同花顺导出.csv \
  --dry-run
```

## Recommended Export Scope

优先从同花顺导出：

- 沪深 A 股列表。
- 行业分类。
- 概念板块。
- 自选主题池。

## Coverage Expansion Checklist

第一优先级：股票池全量列表。

建议导出范围：

- 沪深 A 股。
- 或沪深主板。
- 不需要只导出自选股。

建议字段：

- 代码。
- 名称。
- 行业。
- 概念、题材或所属板块。

导入后判断：

- 少于 1500 支：覆盖偏窄。
- 1500-2499 支：基本可用。
- 3000 支以上：接近全量。

如果第一次导入后仍然只有几百支，通常说明导出的不是全市场列表，而是当前页面、当前板块或自选股列表。

第二优先级：主题/概念补充。

建议额外导出：

- 半导体概念成分股。
- PCB 概念成分股。
- 商业航天概念成分股。
- 电力板块成分股。
- 科技、AI、算力、通信相关板块成分股。

这些文件可以和全市场列表一起放进 `manual_exports`，脚本会合并到同一个股票池缓存。

不需要导出：

- 交易账号。
- 持仓。
- 委托。
- 成交。
- 资金流水。

本项目不接收、不保存同花顺账号密码。
