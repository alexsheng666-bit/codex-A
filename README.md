# A股短线助手

本项目用于沉淀和开发「A股短线助手」相关的产品规划、资料、代码、交付物和复盘。

## Project Folder

正式项目目录：

`/Users/alexsheng/Documents/Codex/Workspace/projects/P002_A股短线助手`

## GitHub Repository

`https://github.com/alexsheng666-bit/codex-A`

## Folder Guide

- `00_项目说明`: 项目目标、范围、决策和会议记录。
- `01_原始资料`: 用户提供或外部收集的原始资料。
- `02_过程稿`: 草稿、方案、产品设计和中间版本。
- `03_交付物`: 最终交付文件。
- `04_复盘`: 项目复盘与可复用经验。
- `assets`: 图片、图标、截图和媒体素材。
- `work`: 脚本、实验文件和临时分析结果。
- `archive`: 暂时不用但需要保留的历史文件。

## Important Note

本项目涉及金融市场信息时，应把输出定位为辅助分析和信息整理，不构成投资建议。涉及实时行情、交易规则、合规或风险判断时，需要以最新可靠来源为准。

## Daily Use

1. 如有同花顺导出文件，放入 `01_原始资料/market_data/manual_exports`。
2. 启动前想先检查：双击 `1_启动前自检.command`。
3. 日常查看优先打开固定 Pages 链接。
4. 想手动更新线上网页：双击 `8_刷新并发布到固定链接.command`。
5. 只想把已有看板发布出去：双击 `7_发布到GitHub Pages.command`。
6. 想自动运行：双击 `5_安装自动运行.command`。
7. 想关闭自动运行：双击 `6_关闭自动运行.command`。
8. 本地临时查看才需要双击 `2_启动看板.command` 或 `3_刷新并启动看板.command`。
9. 不用本地看板时：双击 `4_关闭看板服务.command`。
10. 重点看“数据新鲜度”“本次来源”“股票池缓存”“覆盖状态”“重点关注/观察候补/题材异动记录”。

需要快速检查当前数据状态：

```bash
python3 work/scripts/status_check.py
```

日常调参入口：

`work/rules/strategy_rules.json`

其中 `screening.pool_caps` 控制重点关注、观察候补、题材异动记录的展示上限；`screening.theme_keywords` 控制电力、科技、商业航天、半导体、PCB 等重点主题的识别关键词。

采集脚本和筛选脚本都会读取这份配置，因此主题关键词只需要在这里维护一份。

当前策略采用“三层逻辑”：先用盘前主题确定观察方向，再用盘中板块、量能、分时承接做验证，14:50 生成尾盘第一版推荐；14:55 用最新价格、成交量、换手率等数据二次校验第一版推荐，生成最终推荐并交给模拟盘执行。看板左侧会展示这套流程，每只候选股卡片里也会显示“盘前 / 盘中 / 尾盘”的当前状态。

交易执行前会先通过“数据新鲜度闸门”：用于执行自动卖出或 14:55 模拟买入的行情快照必须是当天数据，且距离当前时间不超过 10 分钟；否则只更新看板和账户估值，不执行新增交易。A 池尾盘买入还会进行实时二次确认，要求价格、成交量、成交额、换手率、量比等字段齐全后才允许下单。

模拟账户说明：系统从 `2026-06-16` 开始记录纸面交易账户，初始本金 1,000,000 元。每天 14:55 之后，按当日“重点关注”股票平均分配账户余额模拟买入；严格遵守 A 股 T+1，今天尾盘买入的股票当天不会卖出，最早只能在下一交易日卖出。下一交易日刷新时，系统会先按卖出纪律结算上一轮持仓，盈亏滚入下一轮本金。同一天重复刷新不会重复买入。本功能只用于策略复盘和资金曲线观察，不构成真实交易指令。

模拟卖出纪律：由于当前数据源主要是日线/快照数据，卖出节点采用规则近似记录：低开超过 -1.5% 按 9:35 防守卖出；触发防守止损按止损点卖出；触发第一止盈按第一止盈点卖出；没有触发止盈止损时按“10:30 未走强/当日快照价”近似退出。后续接入真实分钟级数据后，可升级为更精确的分时卖点。

模拟账户输出：

- `work/paper_trading/account_state.json`
- `work/paper_trading/trade_ledger.csv`
- `work/paper_trading/positions_latest.csv`
- `work/paper_trading/trade_gate_latest.json`
- `work/paper_trading/paper_trading_report.md`

修改配置前建议先备份：

```bash
python3 work/scripts/backup_strategy_rules.py
```

查看或恢复备份：

```bash
python3 work/scripts/restore_strategy_rules.py
```

调参说明：

`00_项目说明/STRATEGY_CONFIG_GUIDE.md`

## First Runnable Prototype

CSV 样例：

`01_原始资料/market_data/raw_csv/sample_market_data.csv`

筛选脚本：

`work/scripts/screen_candidates.py`

运行示例：

```bash
python3 work/scripts/screen_candidates.py \
  --input 01_原始资料/market_data/raw_csv/sample_market_data.csv \
  --output-csv work/normalized_data/candidates_sample.csv \
  --report work/reports/candidates_sample.md \
  --report-html work/reports/candidates_sample.html
```

输出：

- `work/normalized_data/candidates_sample.csv`
- `work/reports/candidates_sample.md`
- `work/reports/candidates_sample.html`

## Local Dashboard

采集最近交易日全沪深主板数据：

```bash
python3 work/scripts/fetch_latest_demo_data.py \
  --output 01_原始资料/market_data/raw_csv/latest_market_data.csv
```

说明：默认先尝试同花顺沪深行情列表，再尝试东方财富沪深快照；成功获取到的主板股票会沉淀到 `work/cache/stock_universe.csv`。若公开接口不可用，会优先用本地股票池批量补行情，再回退到新浪重点方向样本；如果网络完全不可用，则沿用上一次成功快照，避免看板空白。刷新日志会显示本次实际使用的数据源。

数据源扩展计划：

`00_项目说明/DATA_SOURCE_EXPANSION_PLAN.md`

自动扩容股票池：

```bash
python3 work/scripts/sync_exchange_universe.py
```

该脚本会尝试使用上交所、深交所公开股票列表扩容本地股票池；点击看板“刷新数据”时也会自动尝试执行。

导入同花顺手动导出的股票列表、行业和概念：

```bash
python3 work/scripts/import_ths_export.py
```

导入后看 `Coverage` 输出：少于 1500 支是覆盖偏窄，1500 支以上基本可用，2500 支以上接近全量。

导出文件放入：

`01_原始资料/market_data/manual_exports`

导入说明：

`00_项目说明/THS_EXPORT_IMPORT_GUIDE.md`

看板右上角点击“刷新数据”时，会先自动导入该文件夹中的同花顺导出文件；没有文件时会跳过，不影响刷新。

生成最新候选池：

```bash
python3 work/scripts/screen_candidates.py \
  --input 01_原始资料/market_data/raw_csv/latest_market_data.csv \
  --output-csv work/normalized_data/candidates_latest.csv \
  --report work/reports/candidates_latest.md \
  --report-html work/reports/candidates_latest.html
```

构建正式看板：

```bash
python3 work/scripts/build_dashboard.py \
  --input work/normalized_data/candidates_latest.csv \
  --output dashboard/index.html
```

启动本地服务：

```bash
python3 work/scripts/serve_dashboard.py --host 127.0.0.1 --port 8765 --auto-port
```

macOS 上也可以双击：

`1_启动前自检.command`

`2_启动看板.command`

`3_刷新并启动看板.command`

`4_关闭看板服务.command`

`5_安装自动运行.command`

`6_关闭自动运行.command`

`7_发布到GitHub Pages.command`

`8_刷新并发布到固定链接.command`

`1_启动前自检.command` 只做启动前自检，不刷新数据、不启动服务。

`2_启动看板.command` 使用局域网模式启动，适合同一 Wi-Fi 下的手机或其他电脑访问。

`3_刷新并启动看板.command` 会先刷新数据，再启动本地看板。

`8_刷新并发布到固定链接.command` 会先刷新数据，再发布到固定 GitHub Pages 链接，不启动本地看板服务。

访问：

`http://127.0.0.1:8765/`

看板右上角的“刷新数据”按钮会重新采集最近交易日演示数据、生成候选池并重建看板。

窗口说明：自检窗口跑完可以关闭；启动看板窗口需要保留，关闭窗口通常会停止服务；不用看板时双击 `4_关闭看板服务.command`。

自动运行说明：双击 `5_安装自动运行.command` 后，不再启动本地看板服务；周一至周五按交易节奏自动刷新并尝试发布到 GitHub Pages：9:32、10:30、11:25、13:30、14:15、14:35、14:45、14:50、14:55、15:10、16:10。双击 `6_关闭自动运行.command` 可取消。自动刷新需要电脑开机并联网。

锁屏和外出访问：电脑锁屏不影响后台服务；电脑睡眠、关机或断网会影响访问。外出访问不建议直接暴露公网端口，推荐使用 Tailscale 或 Cloudflare Tunnel。

固定 GitHub Pages 链接：

`https://alexsheng666-bit.github.io/codex-A/outputs/stock_report.html`

启动排查：

- 如果提示端口被占用，脚本会自动尝试 `8766`、`8767` 等后续端口，请按窗口里的实际地址访问。
- 如果提示系统不允许监听端口，请在 macOS 弹窗中允许 Python 接收网络连接。
- 如果只在本机看，用 `--host 127.0.0.1`；如果同一 Wi-Fi 下手机或其他电脑也要看，用 `--host 0.0.0.0`。
- 如果只是临时查看，不能刷新数据时，也可以直接双击 `dashboard/index.html` 打开静态看板。

外出查看建议优先使用 Tailscale，详见：

`00_项目说明/LOCAL_DEPLOYMENT_PLAN.md`
