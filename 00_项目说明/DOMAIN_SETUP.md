# alexsheng666.com 域名接入步骤

当前目标：先把实时行情接口切到专属域名 `quote.alexsheng666.com`，主看板链接暂时继续使用 GitHub Pages 固定链接。这样风险最小，也能先解决手机端 `workers.dev` 不稳定的问题。

## 推荐架构

- 看板页面：继续使用 `https://alexsheng666-bit.github.io/codex-A/outputs/stock_report.html`
- 实时行情接口：使用 `https://quote.alexsheng666.com/quotes?codes=002185`
- 备用行情接口：继续保留 `https://codex-a-refresh.alexsheng666.workers.dev`

## 为什么先只做 quote 子域名

`alexsheng666.com` 目前只完成认证，还没有 DNS 解析。Cloudflare Worker 的自定义域名需要这个域名先成为 Cloudflare 中的可用 Zone。Worker Custom Domain 会由 Cloudflare 创建 DNS 记录和证书。

## 操作步骤

1. 打开 Cloudflare，添加站点：`alexsheng666.com`。
2. 选择免费套餐即可。
3. Cloudflare 会给出 2 条 Nameserver。
4. 回到阿里云域名控制台，把 `alexsheng666.com` 的 DNS 服务器改成 Cloudflare 给出的 2 条 Nameserver。
5. 等待 Cloudflare 显示站点 Active。通常几分钟到数小时，极端情况可到 24 小时。
6. 进入 Cloudflare Workers & Pages，打开 Worker：`codex-a-refresh`。
7. 进入 Settings -> Domains & Routes -> Add -> Custom Domain。
8. 填入：`quote.alexsheng666.com`。
9. 等证书状态变为 Active 后，在浏览器打开测试：

```text
https://quote.alexsheng666.com/quotes?codes=002185
```

看到 JSON 并且包含 `ok: true` 后，再切换项目配置。

## 切换项目行情入口

把 `work/cloud/quote_endpoints.txt` 改成：

```text
https://quote.alexsheng666.com
https://codex-a-refresh.alexsheng666.workers.dev
```

然后重新生成并发布看板。这样页面会优先走专属域名，如果专属域名异常，会自动退回 Worker 原地址。

## Worker 来源配置

`wrangler.toml` 已准备：

```toml
ALLOWED_ORIGINS = "https://alexsheng666-bit.github.io,https://alexsheng666.com,https://www.alexsheng666.com"
```

这表示当前 GitHub Pages 页面、未来根域名页面、未来 www 页面都可以调用 Worker。
