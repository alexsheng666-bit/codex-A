#!/usr/bin/env python3
"""A股短线助手 - 盘中实时信号看板"""
import os, sys, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.strategy import get_strategy
from modules.hot_topics import get_hot_tracker
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

def gen():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 50)
    print("  A股盘中实时信号")
    print("=" * 50)
    s = get_strategy()
    print("\n  获取盘中数据...")
    r = s.get_top_picks(n=10, mode="intraday")
    if r is None or not r.get("picks"):
        html = "<html><body><h1>暂无信号</h1></body></html>"
    else:
        picks, sentiment = r["picks"], r["sentiment"]
        concepts, danger = r["hot_concepts"], r.get("market_danger", False)
        print("  [盘中] 信号数: " + str(len(picks)))
        tracker = get_hot_tracker()
        news = tracker.get_eastmoney_news(top_n=15)
        html = build_html(picks, sentiment, concepts, news, danger)
    fpath = os.path.join(OUTPUT_DIR, "intraday_report.html")
    with open(fpath, "w") as f:
        f.write(html)
    print("\n盘中报告已生成: " + fpath)

def build_html(picks, sentiment, concepts, news, danger):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    pj = json.dumps(picks, ensure_ascii=False)
    sj = json.dumps(sentiment, ensure_ascii=False)
    cj = json.dumps(concepts, ensure_ascii=False)
    nj = json.dumps(news, ensure_ascii=False)
    md = "true" if danger else "false"
    
    # Read template
    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template_intraday.js")
    if os.path.exists(tpl_path):
        with open(tpl_path) as f:
            js_code = f.read()
    else:
        js_code = ""
    
    js = "var now='" + now + "';var p=" + pj + ";var se=" + sj + ";var cc=" + cj + ";var nw=" + nj + ";var danger=" + md + ";\n" + js_code
    
    css = ("*{margin:0;padding:0;box-sizing:border-box}"
           "body{font-family:-apple-system,\"PingFang SC\",\"Microsoft YaHei\",sans-serif;background:#0a0e1a;color:#d0d5e0;padding:14px}"
           "h1{font-size:16px;font-weight:700;background:linear-gradient(90deg,#f0b840,#f5923e);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}"
           ".card{background:#111827;border:1px solid #1e3050;border-radius:8px;padding:10px;margin-bottom:8px}"
           ".ct{font-size:13px;font-weight:600;color:#c8d0e0;margin-bottom:6px}"
           ".cr{display:flex;padding:2px 0;font-size:12px}.cr .idx{color:#4a5a70;width:18px}"
           ".pp{color:#f56565}.pn{color:#48bb78}.rise{color:#f56565}.fall{color:#48bb78}")
    
    html = ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">'
            '<title>A股盘中实时 - ' + now[:10] + '</title><style>' + css + '</style></head><body>'
            '<h1>A股盘中实时信号</h1>'
            '<div id="market-status" style="font-size:13px;margin:4px 0"></div>'
            '<div id="mood-text" style="margin:4px 0"></div>'
            '<div id="safe"></div>'
            '<div class="card"><div class="ct">实时信号</div><div id="pc"></div></div>'
            '<div class="card"><div class="ct">热门板块</div><div id="cp"></div></div>'
            '<div style="font-size:10px;color:#4a5a70;text-align:center;margin-top:10px;padding:6px;border-top:1px solid #1e3050">'
            '盘中数据 | 刷新数据: python3 run_intraday.py</div>'
            '<script>' + js + '</script></body></html>')
    return html

if __name__ == "__main__":
    gen()
