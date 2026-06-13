
#!/usr/bin/env python3
"""A股短线助手 - 四策略精选报告"""
import os, sys, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.strategy import get_strategy
from modules.hot_topics import get_hot_tracker
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

def gen():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 50)
    print("  A股短线助手 - 四套尾盘策略精选")
    print("=" * 50)
    s = get_strategy()
    print("")
    print("  [1] 分析市场情绪 & 扫描候选股...")
    r = s.get_top_picks(n=3, mode="eod")
    if r is None or not r.get("picks"):
        html = "<html><body><h1>None</h1></body></html>"
    else:
        picks, sentiment = r["picks"], r["sentiment"]
        concepts, danger = r["hot_concepts"], r.get("market_danger", False)
        print("  [2] 今日精选 " + str(len(picks)) + " 只")
        for i, p in enumerate(picks, 1):
            lv = p["levels"]
            print("    " + str(i) + ". [" + p["pattern_name"] + "] " + p["name"] + "(" + p["code"] + ")")
        print("  [3] 获取快讯...")
        from modules.hot_topics import get_hot_tracker as ght
        news = ght().get_eastmoney_news(top_n=15)
        html = build(picks, sentiment, concepts, news, danger)
    fpath = os.path.join(OUTPUT_DIR, "stock_report.html")
    with open(fpath, "w") as f:
        f.write(html)
    print("")
    print("报告已生成: " + fpath)

def build(picks, sentiment, concepts, news, danger):
    import json
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    pj = json.dumps(picks, ensure_ascii=False)
    sj = json.dumps(sentiment, ensure_ascii=False)
    cj = json.dumps(concepts, ensure_ascii=False)
    nj = json.dumps(news, ensure_ascii=False)
    md = "true" if danger else "false"
    # Build JS by injecting JSON data
    js_data = "var p=" + pj + ";var se=" + sj + ";var cc=" + cj + ";var nw=" + nj + ";var danger=" + md + ";"
    # JS rendering code - use a heredoc-style approach via separate assembly
    js_scripts = []
    # Helper: function to create JS string safely
    # Read JS from template file
    import os as _os
    _base = _os.path.dirname(_os.path.abspath(__file__))
    _js_path = _os.path.join(_base, 'template.js')
    if _os.path.exists(_js_path):
        with open(_js_path) as _f:
            js_code = _f.read()
    else:
        js_code = ''
    js = js_data + js_code
    # CSS
    css = ("*{margin:0;padding:0;box-sizing:border-box}"
          "body{font-family:-apple-system,\'PingFang SC\',\'Microsoft YaHei\',sans-serif;background:#0a0e1a;color:#d0d5e0;padding:16px}"
          "h1{font-size:18px;font-weight:700;background:linear-gradient(90deg,#f0b840,#f5923e);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}"
          ".time{font-size:12px;color:#718096}.card{background:#111827;border:1px solid #1e3050;border-radius:10px;padding:12px;margin-bottom:10px}"
          ".ct{font-size:14px;font-weight:600;color:#c8d0e0;margin-bottom:8px}"
          ".cr{display:flex;padding:3px 0;font-size:12px}.cr .idx{color:#4a5a70;width:20px}"
          ".pp{color:#f56565}.pn{color:#48bb78}.nt{font-size:11px;color:#4a5a70}.rise{color:#f56565}.fall{color:#48bb78}")
    html = ('<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\">'
            '<title>A股短线助手 - ' + now[:10] + '</title><style>' + css + '</style></head><body>'
            '<h1>A股短线助手 - 四套尾盘策略精选</h1>'
            '<div class=\"time\">' + now + ' | 基于多因子模型 · 仅供参考</div>'
            '<div id=\"wt\"></div><div id=\"mt\"></div><div id=\"safe\"></div>'
            '<div class=\"card\"><div class=\"ct\">🎯 今日策略精选</div><div id=\"pc\"></div></div>'
            '<div class=\"card\"><div class=\"ct\">🔥 热门板块</div><div id=\"cp\"></div></div>'
            '<div class=\"card\"><div class=\"ct\">📰 快讯</div><div id=\"nw\"></div></div>'
            '<div style=\"font-size:10px;color:#4a5a70;text-align:center;margin-top:12px;padding:8px;border-top:1px solid #1e3050\">'
            '免责声明：以上内容仅供参考，不构成投资建议。股市有风险，投资需谨慎。<br>'
            '每次刷新数据：python3 run.py</div>'
            '<script>' + js + '</script></body></html>')
    return html
if __name__ == "__main__":
    gen()
