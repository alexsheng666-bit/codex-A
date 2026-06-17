# Local Deployment Plan

Version: 0.1
Date: 2026-06-15
Status: Draft

## Goal

把「A股短线助手」做成可以本地部署、远程查看的个人看板。

第一版采用静态看板：

- 输入：候选池 CSV。
- 构建：`work/scripts/build_dashboard.py`。
- 输出：`dashboard/index.html`。
- 本地服务：`work/scripts/serve_dashboard.py`。

## Local Build

查看当前数据和看板状态：

```bash
python3 work/scripts/status_check.py
```

调整入池上限和重点主题：

```text
00_项目说明/STRATEGY_CONFIG_GUIDE.md
```

先生成候选池数据：

```bash
python3 work/scripts/screen_candidates.py \
  --input 01_原始资料/market_data/raw_csv/sample_market_data.csv \
  --output-csv work/normalized_data/candidates_sample.csv \
  --report work/reports/candidates_sample.md \
  --report-html work/reports/candidates_sample.html
```

再构建看板：

```bash
python3 work/scripts/build_dashboard.py \
  --input work/normalized_data/candidates_sample.csv \
  --output dashboard/index.html
```

## Local Access

启动本地服务：

```bash
python3 work/scripts/serve_dashboard.py --host 127.0.0.1 --port 8765 --auto-port
```

macOS 双击启动：

```text
1_启动前自检.command
2_启动看板.command
3_刷新并启动看板.command
4_关闭看板服务.command
5_安装自动运行.command
6_关闭自动运行.command
7_发布到GitHub Pages.command
```

启动前自检用 `1_启动前自检.command`：只检查看板文件、数据日期、候选数量、端口和 macOS 网络权限状态，不刷新数据、不启动服务。

快速查看用 `2_启动看板.command`：直接生成当前看板并启动本地服务，不主动联网刷新。

先更新再查看用：

```text
3_刷新并启动看板.command
```

这个脚本会先执行一次完整刷新，再启动看板。网络较慢或公开行情源不稳定时，启动会更慢，但打开后数据口径更接近最新。

不用看板时，双击：

```text
4_关闭看板服务.command
```

窗口说明：自检窗口跑完可以关闭；启动看板窗口需要保留，关闭窗口通常会停止服务；不想看到窗口时可以最小化到 Dock。

## Automatic Run

如果希望不每天手动双击启动，可以安装自动运行：

```text
5_安装自动运行.command
```

安装后：

- 登录电脑后自动启动看板服务。
- 周一至周五按交易节奏自动刷新：9:32、10:30、11:25、13:30、14:15、14:35、14:45、14:52、14:57、15:10、16:10。
- 14:15 进入午后预选，14:35 进入尾盘候选，14:52 为准推荐，14:57 为 15:00 前最终推荐和模拟盘执行窗口。
- 每次刷新成功后会尝试发布到 GitHub Pages。
- 服务在后台运行，不需要保留 Terminal 窗口。
- 自动刷新需要电脑开机并联网；电脑睡眠时可能会错过当次刷新。

如果不想继续自动启动或自动刷新，双击：

```text
6_关闭自动运行.command
```

这只会关闭自动运行配置，不会删除你的数据和看板文件。

手动发布固定网页：

```text
7_发布到GitHub Pages.command
```

固定访问链接：

```text
https://alexsheng666-bit.github.io/codex-A/outputs/stock_report.html
```

双击脚本默认使用局域网模式：

```bash
python3 work/scripts/serve_dashboard.py --host 0.0.0.0 --port 8765 --auto-port
```

本机访问：

```text
http://127.0.0.1:8765/
```

## LAN Access

如果只想在同一 Wi-Fi 或局域网内访问：

```bash
python3 work/scripts/serve_dashboard.py --host 0.0.0.0 --port 8765 --auto-port
```

然后用手机或其他电脑访问脚本输出的 LAN 地址。默认优先使用 `8765` 端口；如果端口已被占用，会自动尝试 `8766`、`8767` 等后续端口，并在窗口里打印最终地址。

注意：

- 只在可信网络中使用 LAN 模式。
- 第一次启动时，macOS 可能提示是否允许 Python 接收网络连接，需要允许后局域网设备才能访问。
- 局域网地址通常形如 `http://192.168.x.x:8765/`。
- 如果脚本显示的端口不是 `8765`，请按窗口里的实际地址访问。
- 不要把交易账号、API Key、Token 或敏感资产信息写入看板。

## Startup Troubleshooting

如果启动窗口提示“端口已被占用”：

```bash
python3 work/scripts/serve_dashboard.py --host 127.0.0.1 --port 8765 --auto-port
```

脚本会自动尝试 `8766`、`8767` 等后续端口，按窗口打印的地址打开即可。

如果启动窗口提示“系统没有允许这个本地服务监听端口”：

1. 看 macOS 是否弹出网络权限提示，如有请选择“允许”。
2. 只在本机查看时，使用 `--host 127.0.0.1`。
3. 局域网访问时，使用 `--host 0.0.0.0`，并确保电脑和访问设备在同一 Wi-Fi。
4. 如果是在 Codex 内部测试服务端口出现该提示，优先双击 `2_启动看板.command` 在日常环境中启动。

如果只是临时查看、不需要点击“刷新数据”，可以直接双击：

```text
dashboard/index.html
```

静态打开能看当前候选池，但刷新按钮需要本地服务运行后才可用。

## Remote Access Options

### Option 1: Tailscale

适合只给自己的设备访问。

优点：

- 安全性高。
- 不需要暴露公网 IP。
- 适合个人工具。

使用方式：

1. 在电脑和手机上安装 Tailscale。
2. 电脑启动看板服务，建议使用 `--host 0.0.0.0`。
3. 手机通过 Tailscale 分配的电脑地址访问启动窗口里显示的端口。

推荐日常用法：

```text
http://你的电脑Tailscale地址:启动窗口显示的端口/
```

如果 Tailscale 开启 MagicDNS，也可以用电脑名访问。

### Option 2: Cloudflare Tunnel

适合需要一个稳定外部链接，但又不想暴露家庭公网 IP。

优点：

- 稳定。
- 可以绑定域名。
- 不需要路由器端口转发。

注意：

- 建议加访问控制。
- 不建议公开裸奔访问。

### Option 3: GitHub Pages

适合发布静态报告。

优点：

- 简单。
- 免费。
- 适合展示非敏感数据。

缺点：

- 如果仓库公开，策略和候选池可能被公开。
- 不适合包含个人交易计划或敏感数据。

## Recommended Path

推荐路线：

1. 先双击 `4_关闭看板服务.command` 清理重复手动服务。
2. 再双击 `5_安装自动运行.command`，让看板后台自动启动、工作日多节点自动刷新。
3. 同一 Wi-Fi 下用 LAN 地址访问。
4. 外出访问用 Tailscale。
5. 后续如果需要固定链接，再考虑 Cloudflare Tunnel。
6. GitHub Pages 用于固定链接访问；注意仓库公开时，候选池和策略输出也可能被公开。
