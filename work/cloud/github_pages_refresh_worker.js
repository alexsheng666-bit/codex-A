// Cloudflare Worker: trigger GitHub Actions refresh from GitHub Pages and proxy live quotes.
//
// Required Worker environment variables:
// - GITHUB_TOKEN: fine-grained token with repository Contents read/write and Actions read/write
// - GITHUB_OWNER: alexsheng666-bit
// - GITHUB_REPO: codex-A
// - ALLOWED_ORIGIN: https://alexsheng666-bit.github.io

function corsHeaders(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "https://alexsheng666-bit.github.io",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  };
}

function sinaSymbol(code) {
  const clean = String(code || "").replace(/\D/g, "").padStart(6, "0").slice(-6);
  if (!clean) return "";
  return clean.startsWith("6") ? `sh${clean}` : `sz${clean}`;
}

function eastmoneySecid(code) {
  const clean = String(code || "").replace(/\D/g, "").padStart(6, "0").slice(-6);
  if (!clean) return "";
  return clean.startsWith("6") ? `1.${clean}` : `0.${clean}`;
}

function parseSinaQuotes(text) {
  const quotes = {};
  const pattern = /var hq_str_(s[hz]\d{6})="([^"]*)";/g;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    const symbol = match[1];
    const code = symbol.slice(2);
    const fields = match[2].split(",");
    if (fields.length < 32 || !fields[0]) continue;
    const preClose = Number(fields[2] || 0);
    const price = Number(fields[3] || 0);
    const high = Number(fields[4] || 0);
    const low = Number(fields[5] || 0);
    quotes[code] = {
      code,
      symbol,
      name: fields[0],
      open: Number(fields[1] || 0),
      pre_close: preClose,
      price,
      high,
      low,
      volume: Number(fields[8] || 0),
      amount: Number(fields[9] || 0),
      time: `${fields[30] || ""} ${fields[31] || ""}`.trim(),
      pct_change: preClose ? Number(((price - preClose) / preClose * 100).toFixed(2)) : 0,
    };
  }
  return quotes;
}

function parseEastmoneyQuotes(payload) {
  const quotes = {};
  const rows = payload?.data?.diff || [];
  for (const row of rows) {
    const code = String(row.f12 || "").padStart(6, "0");
    const price = Number(row.f2 || 0);
    const preClose = Number(row.f18 || 0);
    if (!code || !price) continue;
    quotes[code] = {
      code,
      symbol: eastmoneySecid(code),
      name: row.f14 || "",
      open: Number(row.f17 || 0),
      pre_close: preClose,
      price,
      high: Number(row.f15 || 0),
      low: Number(row.f16 || 0),
      volume: Number(row.f5 || 0),
      amount: Number(row.f6 || 0),
      time: new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }),
      pct_change: row.f3 !== undefined ? Number(row.f3 || 0) : (preClose ? Number(((price - preClose) / preClose * 100).toFixed(2)) : 0),
    };
  }
  return quotes;
}

async function fetchSinaQuotes(symbols) {
  const quoteUrl = `https://hq.sinajs.cn/list=${symbols.join(",")}`;
  const response = await fetch(quoteUrl, {
    headers: {
      "Referer": "https://finance.sina.com.cn/",
      "User-Agent": "Mozilla/5.0",
    },
  });
  if (!response.ok) throw new Error("Sina quote fetch failed.");
  return parseSinaQuotes(await response.text());
}

async function fetchEastmoneyQuotes(secids) {
  const fields = "f12,f14,f2,f3,f5,f6,f15,f16,f17,f18";
  const quoteUrl = `https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=${fields}&secids=${secids.join(",")}`;
  const response = await fetch(quoteUrl, {
    headers: {
      "Referer": "https://quote.eastmoney.com/",
      "User-Agent": "Mozilla/5.0",
    },
  });
  if (!response.ok) throw new Error("Eastmoney quote fetch failed.");
  return parseEastmoneyQuotes(await response.json());
}

async function handleQuotes(request, env) {
  const url = new URL(request.url);
  const codes = (url.searchParams.get("codes") || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 30);
  const symbols = codes.map(sinaSymbol).filter(Boolean);
  if (!symbols.length) {
    return new Response(JSON.stringify({ ok: false, message: "Missing codes." }), {
      status: 400,
      headers: corsHeaders(env),
    });
  }
  const secids = codes.map(eastmoneySecid).filter(Boolean);
  const sources = [];
  const errors = [];
  let quotes = {};
  try {
    quotes = await fetchSinaQuotes(symbols);
    sources.push("sina");
  } catch (error) {
    errors.push(String(error.message || error));
  }
  const missingSecids = codes
    .filter((code) => !quotes[String(code).replace(/\D/g, "").padStart(6, "0").slice(-6)])
    .map(eastmoneySecid)
    .filter(Boolean);
  if (missingSecids.length || !sources.length) {
    try {
      quotes = { ...quotes, ...(await fetchEastmoneyQuotes(missingSecids.length ? missingSecids : secids)) };
      sources.push("eastmoney");
    } catch (error) {
      errors.push(String(error.message || error));
    }
  }
  if (!Object.keys(quotes).length) {
    return new Response(JSON.stringify({ ok: false, message: "Quote fetch failed." }), {
      status: 502,
      headers: corsHeaders(env),
    });
  }
  return new Response(
    JSON.stringify({
      ok: true,
      source: sources.join("+") || "unknown",
      updated_at: new Date().toISOString(),
      quotes,
      warnings: errors,
    }),
    { status: 200, headers: corsHeaders(env) },
  );
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(env) });
    }
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/quotes") {
      return handleQuotes(request, env);
    }
    if (request.method !== "POST") {
      return new Response(JSON.stringify({ ok: false, message: "Only POST is allowed." }), {
        status: 405,
        headers: corsHeaders(env),
      });
    }

    const owner = env.GITHUB_OWNER || "alexsheng666-bit";
    const repo = env.GITHUB_REPO || "codex-A";
    const token = env.GITHUB_TOKEN;
    if (!token) {
      return new Response(JSON.stringify({ ok: false, message: "Worker missing GITHUB_TOKEN." }), {
        status: 500,
        headers: corsHeaders(env),
      });
    }

    const response = await fetch(`https://api.github.com/repos/${owner}/${repo}/dispatches`, {
      method: "POST",
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
        "User-Agent": "codex-a-dashboard-refresh",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        event_type: "dashboard-refresh",
        client_payload: { source: "github-pages-button", requested_at: new Date().toISOString() },
      }),
    });

    if (!response.ok) {
      const detail = await response.text();
      return new Response(JSON.stringify({ ok: false, message: "GitHub trigger failed.", detail }), {
        status: 502,
        headers: corsHeaders(env),
      });
    }

    return new Response(
      JSON.stringify({
        ok: true,
        message: "云端刷新已启动，通常 1-3 分钟后固定链接会更新。",
      }),
      { status: 200, headers: corsHeaders(env) },
    );
  },
};
