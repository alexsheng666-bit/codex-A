# GitHub Pages 云端刷新说明

GitHub Pages 是静态网页，不能直接运行本项目里的 Python 采集脚本。

当前云端方案分两层：

1. GitHub Actions 自动刷新
   - 已新增 `.github/workflows/cloud-refresh-dashboard.yml`
   - 周一至周五按交易节奏自动运行
   - 也支持在 GitHub Actions 页面手动运行
   - 双击 `8_刷新并发布到固定链接.command` 时，会同时发布网页和云端自动刷新所需程序

2. GitHub Pages 按钮触发刷新
   - 需要一个 Cloudflare Worker 做安全中转
   - Worker 保存 GitHub token
   - 页面按钮只调用 Worker，不暴露 token

Worker 代码：

`work/cloud/github_pages_refresh_worker.js`

这个 Worker 同时负责两件事：

- `POST /`：触发 GitHub Actions 云端刷新看板。
- `GET /quotes?codes=600601,002185`：给固定链接页面提供重点关注股票实时价，用于 15 秒价格刷新和止盈止损提醒。

如果本地更新了 `work/cloud/github_pages_refresh_worker.js`，需要回到 Cloudflare Worker 的 `Edit code` 重新粘贴并 `Deploy`，线上实时价功能才会同步生效。

一次性配置步骤：

1. 打开 Cloudflare，进入 Workers & Pages，新建 Worker。
2. 把 `work/cloud/github_pages_refresh_worker.js` 里的全部代码复制进去并部署。
3. 在 Worker 设置里添加下面 4 个变量。
4. 复制 Worker 的公开访问地址，通常类似：
   `https://codex-a-refresh.xxxxx.workers.dev`
5. 回到项目文件夹，双击 `9_配置固定链接刷新按钮.command`。
6. 粘贴 Worker 地址并按回车，脚本会重新生成并发布看板。

Worker 变量：

- `GITHUB_TOKEN`: GitHub fine-grained token，需要当前仓库 Contents 读写、Actions 读写权限
- `GITHUB_OWNER`: `alexsheng666-bit`
- `GITHUB_REPO`: `codex-A`
- `ALLOWED_ORIGIN`: `https://alexsheng666-bit.github.io`

部署 Worker 后，把 Worker 的公开地址写入：

`work/cloud/refresh_endpoint.txt`

然后重新发布看板。此后固定链接里的“刷新数据”按钮会触发云端 GitHub Actions 刷新。
