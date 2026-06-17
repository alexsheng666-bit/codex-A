# A股短线助手 Data Source Plan

Version: 0.1
Date: 2026-06-15
Status: Draft

## Recommendation

第一版采用“CSV 优先 + AKShare 自动化适配器 + Tushare 后续增强”的路线。

这样做的原因：

- CSV 最稳，适合先把候选池、筛选规则、风险标签和复盘流程跑通。
- AKShare 覆盖 A 股实时行情、历史行情、涨停池、板块、龙虎榜等数据，适合做第一版自动化数据接入。
- Tushare 更适合后续作为相对稳定的数据服务接入，但通常需要账号、Token 和权限管理，不应作为第一天的阻塞项。

## Source Review

### CSV Import

定位：第一版默认输入。

优点：

- 不依赖外部接口稳定性。
- 可以从行情软件、网页、表格或手工整理中导出。
- 便于调试字段、筛选规则和复盘逻辑。
- 不涉及 API Key 和账号权限。

缺点：

- 需要手动导入。
- 数据格式可能不统一。
- 不适合长期自动化。

结论：

第一版必须支持 CSV 导入，作为所有自动接口失败时的兜底方案。

### AKShare

定位：第一版自动化接入的首选候选。

当前公开文档显示：

- AKShare 是基于 Python 的财经数据接口库，覆盖股票、基金、指数、期货等数据。
- AKShare 文档提示其采集公开数据源，主要用于学术研究，并提示商业风险。
- `stock_zh_a_spot_em` 可获取沪深京 A 股实时行情，包含代码、名称、最新价、涨跌幅、成交额、量比、换手率、市值等字段。
- `stock_zh_a_hist` 可获取沪深京 A 股历史日频数据，包含开盘、收盘、最高、最低、成交量、成交额、涨跌幅、换手率等字段。
- `stock_zt_pool_em` 可获取近期涨停股池，包含涨跌幅、成交额、换手率、封板资金、首次封板时间、炸板次数、连板数、所属行业等字段。

优点：

- Python 接入成本低。
- 字段覆盖较适合短线候选池。
- 能支持涨停池、板块、历史行情等短线常用维度。
- 适合本地工具和研究型项目快速验证。

缺点：

- 依赖公开网页或公开源，接口可能因目标网站变化而失效。
- 不应默认用于商业化或高频稳定服务。
- 需要定期更新依赖和关注接口变化。
- 数据准确性需要抽样核验。

结论：

第一版可以把 AKShare 作为自动化采集适配器，但必须保留 CSV 兜底，并在输出中记录数据来源和采集时间。

### Tushare

定位：第二阶段增强数据源。

当前公开首页显示：

- Tushare 提供多类数据，并支持 Python SDK、Restful HTTP 调用等接入方式。
- 它更适合作为需要权限、Token、稳定接口和长期数据管理的后续方案。

优点：

- 数据服务平台定位更明确。
- 适合后续本地落库、历史数据补全和标准化字段。
- 适合当项目从个人工具进入更稳定的研究系统阶段。

缺点：

- 需要账号、Token 和权限确认。
- 部分数据可能有积分、套餐或访问限制。
- 不适合作为第一版启动阻塞项。

结论：

第一版不强依赖 Tushare。等候选池流程稳定后，再评估是否接入。

## Version 1 Data Strategy

### Universe Filter

第一版股票池范围：

- 上证主板 A 股。
- 深证主板 A 股。

第一版剔除范围：

- ST、*ST、S*ST 等风险警示股票。
- 创业板。
- 科创板。
- 北交所。
- B 股。
- 退市整理或已退市股票。

代码前缀粗筛：

- 纳入：`600`、`601`、`603`、`605`、`000`、`001`、`002`、`003`。
- 排除：`300`、`301`、`688`、`8`、`4`、`9` 等非目标范围。

注意：代码前缀只允许用于交易所/主板范围过滤；禁止凭股票名称、股票简称或代码直接猜测行业/板块。行业标签必须来自可信数据源，或先联网核对最新主营业务构成后按申万一级行业匹配。

### Focus Themes

第一版重点关注：

- 电力股。
- 科技股。
- 商业航天。
- 半导体。
- PCB 概念。

数据标准化时应生成 `theme_tags` 字段，用于记录命中的主题标签。

### Phase 1: Manual Reliable Input

目标：让产品逻辑先跑通。

输入方式：

- 用户上传 CSV。
- 或把行情数据放入 `01_原始资料`。
- 系统读取、校验、标准化字段。

产出：

- 标准化行情表。
- 候选池表。
- 次日观察清单。
- 复盘记录。

### Phase 2: AKShare Adapter

目标：减少手工导入。

优先接入：

- 全市场实时/收盘行情。
- 个股历史日频行情。
- 涨停股池。
- 行业或概念板块行情。

注意：

- 每次采集保存原始数据快照。
- 每次输出记录数据来源、采集时间和接口名称。
- 如果接口失败，回退到 CSV 导入。

### Phase 3: Stable Data Service

目标：提升长期稳定性。

候选方向：

- Tushare Pro。
- 付费行情服务。
- 自建本地数据仓库。

前提：

- 已明确第一版字段模型。
- 已有稳定候选池规则。
- 已确认是否需要长期历史数据和更完整基本面数据。

## Standard Data Folder

建议在项目内使用以下数据目录：

```text
01_原始资料/
  market_data/
    raw_csv/
    akshare_snapshots/
    tushare_snapshots/
work/
  normalized_data/
  reports/
```

说明：

- `01_原始资料/market_data/raw_csv`: 用户导入的原始 CSV。
- `01_原始资料/market_data/akshare_snapshots`: AKShare 原始采集结果。
- `01_原始资料/market_data/tushare_snapshots`: Tushare 原始采集结果。
- `work/normalized_data`: 清洗后的标准数据。
- `work/reports`: 候选池、观察清单、复盘报告等中间输出。

## Standard Fields

第一版标准字段：

```text
trade_date
stock_code
stock_name
board
market
industry
concepts
theme_tags
is_focus_theme
is_st
universe_eligible
open
high
low
close
pre_close
pct_change
turnover_amount
turnover_rate
volume
volume_ratio
amplitude
market_cap
float_market_cap
limit_up_status
first_limit_up_time
last_limit_up_time
limit_up_break_count
consecutive_limit_up_count
pool_level
entry_reasons
risk_tags
next_day_valid_if
next_day_weak_if
next_day_remove_if
review_status
data_source
captured_at
```

字段原则：

- 所有股票代码统一为 6 位字符串。
- 所有金额字段统一记录单位。
- 所有百分比字段统一记录为百分数数值，例如 `10.0` 表示 10%。
- 所有日期字段统一为 `YYYY-MM-DD`。
- 所有采集结果都保留 `data_source` 和 `captured_at`。

## Data Quality Checks

导入或采集后必须检查：

- 股票代码是否为空或格式异常。
- 股票名称是否为空。
- 涨跌幅、换手率、量比是否存在异常值。
- 成交额是否为 0 或缺失。
- 当日数据是否真的属于目标交易日。
- 同一交易日同一股票是否重复。
- 涨停池数据是否只覆盖近期日期。
- 采集时间是否在收盘后，避免把盘中数据误当盘后数据。

## Fallback Rules

如果自动采集失败：

1. 使用最近一次成功快照，但必须标记为历史快照。
2. 允许用户上传 CSV 覆盖当天数据。
3. 候选池报告中显示数据来源异常。
4. 不输出带确定性语气的结论。

## Sources Checked

- AKShare 项目概览：`https://akshare.akfamily.xyz/introduction.html`
- AKShare 股票数据文档：`https://akshare.akfamily.xyz/data/stock/stock.html`
- Tushare 首页：`https://tushare.pro/`

## Decision

第一版正式决策：

- 默认输入：CSV。
- 自动化候选：AKShare。
- 后续增强：Tushare 或其他稳定数据服务。
- 所有数据输出必须记录来源和采集时间。
- 所有结论只作为辅助分析，不构成投资建议。
