# Data Source Expansion Plan

Version: 0.1
Date: 2026-06-15
Status: Draft

## Goal

实现沪深主板股票的全量数据覆盖，用于候选池评估筛选。

目标股票池：

- 上证主板 A 股。
- 深证主板 A 股。

剔除：

- ST。
- *ST。
- S*ST。
- 创业板。
- 科创板。
- 北交所。
- B 股。
- 退市整理或已退市股票。

## Current Situation

当前看板已经支持多层数据源：

1. 上交所、深交所公开股票列表。
2. 同花顺沪深行情列表试采。
3. 东方财富直连沪深 A 股快照。
4. 本地股票池缓存。
5. 新浪批量行情兜底。
6. 新浪焦点样本兜底。
7. 上一次成功快照兜底。
8. AKShare 全 A 股快照（保留为备用实验源，不参与默认刷新）。

当前问题：

- AKShare 的 `stock_zh_a_spot_em` 底层仍依赖东方财富节点。
- 东方财富公开接口偶尔会在分页时断连。
- 同花顺网页可正常打开，但行情列表接口存在 401/空表限流，不能假设网页登录后就有稳定 API。
- 新浪兜底源当前只是重点方向样本，不是全沪深主板。
- 当前已加入本地股票池缓存：每次成功采集到的沪深主板股票会沉淀到 `work/cache/stock_universe.csv`。
- 已新增交易所公开列表同步：`work/scripts/sync_exchange_universe.py`，用于自动扩容本地股票池。
- 网络完全不可用时，系统会沿用上一次成功快照，避免看板空白。

因此，当前系统具备全量采集能力框架，但公开免费接口的稳定性不足。

## Recommended Provider Layers

### Layer 1: Stable Full-Market Provider

推荐接入：

- Tushare Pro。
- 其他付费或稳定行情 API。

用途：

- 获取股票基础列表。
- 获取日线行情。
- 获取成交额、换手率、涨跌幅等标准字段。
- 作为全沪深主板覆盖的主数据源。

优点：

- 稳定性更高。
- 字段更标准。
- 适合每天固定刷新。

注意：

- 需要 Token。
- Token 不能提交到 GitHub。
- 应放在本地 `.env` 或系统环境变量。

### Layer 1.5: Exchange Official Stock List

用途：

- 从上交所主板 A 股、深交所 A 股列表同步股票基础池。
- 本地剔除 ST、创业板、科创板、北交所、B 股。
- 优先用于扩大 `work/cache/stock_universe.csv`。

已支持脚本：

- `work/scripts/sync_exchange_universe.py`

限制：

- 主要解决“股票代码/名称/行业”基础池，不直接解决实时行情。
- 深交所列表可能包含创业板，需本地代码前缀和板块二次过滤。
- 交易所网页接口如果临时不可用，刷新流程会跳过，不影响看板。

### Layer 2: 同花顺 Quote Page

用途：

- 试采沪深行情列表。
- 辅助验证网页端行情是否可访问。
- 后续可配合用户手动导出的板块/概念数据。

限制：

- 目前测试结果：Chrome 中同花顺行情中心可打开，但自动读取页面内容容易超时。
- 公网页面表格偶尔可返回，但连续翻页会出现 401 或空表。
- 不读取、不保存登录 cookie、账号或密码；不进入交易、资金、委托页面。
- 不建议把网页登录视为稳定 API。

### Layer 3: Eastmoney Direct

用途：

- 不依赖第三方 Python 包。
- 直接分页获取沪深 A 股快照。

限制：

- 分页接口有时会断连或返回 502。
- 需要本地缓存和断点续抓。
- 当前脚本已支持：后续页失败时，如果已获取到足够行数，可使用局部快照，避免直接退回窄样本。

### Layer 4: Sina/Tencent Quote Fallback

用途：

- 针对已有股票代码列表批量补行情。
- 做临时兜底。
- 优先使用本地股票池 `work/cache/stock_universe.csv`。

限制：

- 必须先有股票代码列表。
- 新浪/Tencent 适合补行情，不适合作为股票池发现源。
- 如果本地股票池还很小，覆盖范围仍有限。

### Layer 4.5: Existing Snapshot Fallback

用途：

- 所有网络源失败时，沿用 `latest_market_data.csv`。
- 保证看板刷新不会因为网络异常而变空。

限制：

- 数据不是最新行情，只能作为“保底显示”。
- 看板应继续显示实际数据源和交易日期，避免误判为实时刷新。

### Layer 5: 同花顺 Manual Export

用途：

- 作为人工确认和补充数据源。
- 从同花顺客户端导出沪深主板股票列表、板块排行、自选股、行情表或条件选股结果。
- 导出的 CSV/Excel 放入 `01_原始资料/market_data/manual_exports`，再由系统标准化。
- 已支持脚本：`work/scripts/import_ths_export.py`。

安全边界：

- 不接收、不保存同花顺账号密码。
- 不把交易账号、资金、持仓、委托、成交记录写入公开仓库。
- 不建议自动登录或模拟操作交易软件抓取数据。
- 如果需要使用同花顺数据，优先由用户本人登录客户端后手动导出文件。

可用价值：

- 同花顺的板块、概念和个股分类通常对短线题材识别很有帮助。
- 可以补足公开接口中概念字段不足的问题。
- 可以作为“主题标签”和“股票池清单”的人工权威来源之一。

限制：

- 没有公开稳定 API 时，自动化程度有限。
- 手动导出数据字段可能不固定；当前脚本已兼容常见的代码、名称、行业、概念表头。
- 若使用界面自动化，稳定性和合规风险都不如正式 API。

## Target Architecture

建议拆成两张数据表：

### Stock Universe

保存全量股票池：

```text
stock_code
stock_name
market
board
is_st
is_active
industry
concepts
updated_at
data_source
```

### Daily Quote

保存每日行情：

```text
trade_date
stock_code
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
data_source
captured_at
```

筛选流程：

1. 更新股票池。
2. 剔除 ST、创业板、科创板、北交所、B 股。
3. 获取每日行情。
4. 主题匹配。
5. 策略匹配。
6. 分入重点关注、观察候补、题材异动记录。

## Implementation Roadmap

### Step 1: Full-Market Public Provider

已开始：

- `fetch_latest_demo_data.py` 优先尝试同花顺行情列表。
- `serve_dashboard.py` 刷新前会先尝试 `sync_exchange_universe.py` 扩容官方股票池。
- 失败后尝试东方财富直连。
- 成功采集到的主板股票会更新本地股票池缓存。
- 再失败时优先使用本地股票池批量补新浪行情。
- 本地股票池不可用时回退到新浪焦点样本。
- 网络完全不可用时沿用上一次成功快照。
- AKShare 暂不参与默认刷新，避免第三方库在网络不稳时长时间卡住。

下一步：

- 为东方财富分页增加本地缓存。
- 把接口状态显示在看板顶部。
- 增加同花顺手动导出导入模板，用作概念/题材补充源。
- 当本地股票池超过 1500-3000 支后，优先用本地股票池 + 批量行情更新作为默认兜底；低于 3000 行的自动行情快照不应直接视作接近全量。

### Step 2: Stable Token Provider

推荐：

- 接入 Tushare Pro。

需要用户提供：

- Tushare Token。
- 是否允许保存到本地 `.env`。

安全要求：

- `.env` 必须被 `.gitignore` 排除。
- Token 不显示在看板和日志里。

### Step 3: Quote Fallback

在已有股票池基础上：

- 用 Tencent 或 Sina 批量补实时行情。
- 每批 50-100 只。
- 失败批次重试。

这样即使主行情源异常，也能用本地股票池继续补行情。

## Dashboard Display

看板应显示以下口径：

- 原始采集数：本次数据源返回的原始股票数量。
- 有效主板：剔除 ST、创业板、科创板等后的股票数量。
- 候选数：被分入重点关注、观察候补、题材异动记录的数量。
- 数据源状态：AKShare、Eastmoney、Sina、Tushare 中实际使用了哪个。

## Decision

短期：

- 继续使用同花顺试采 + 东方财富直连 + 新浪兜底。
- 持续积累本地股票池缓存。
- 将看板明确标注当前数据源覆盖范围。

中期：

- 接入 Tushare 或其他稳定 API，实现全沪深主板每日覆盖。
- 增加同花顺导出文件导入模板，用作主题/概念补充源。

长期：

- 建立本地股票池缓存和每日行情库，减少对单一公开接口的依赖。
