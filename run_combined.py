#!/usr/bin/env python3
"""A股短线助手 - 双看板+持仓 一键运行"""
import sys, os, json, shutil
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.strategy import get_strategy
from modules.hot_topics import get_hot_tracker
from modules.portfolio import load_portfolio, fetch_prices
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("A股短线助手 - 双看板+持仓")
    s = get_strategy()
    intra = (s.get_top_picks(n=5, mode="intraday") or {}).get("picks", [])
    eod = (s.get_top_picks(n=3, mode="eod") or {}).get("picks", [])
    sentiment = s.get_market_sentiment()
    concepts = get_hot_tracker().get_hot_concepts(top_n=12)
    news = get_hot_tracker().get_eastmoney_news(top_n=12)
    portfolio_data = fetch_prices(load_portfolio())
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    pj_intra = json.dumps(intra, ensure_ascii=False)
    pj_eod = json.dumps(eod, ensure_ascii=False)
    sj = json.dumps(sentiment, ensure_ascii=False)
    cj = json.dumps(concepts, ensure_ascii=False)
    nj = json.dumps(news, ensure_ascii=False)
    pf = json.dumps(portfolio_data, ensure_ascii=False)
    
    js = ("var pi="+pj_intra+";var pe="+pj_eod+";var se="+sj+";"
          "var cc="+cj+";var nw="+nj+";var pf="+pf+";var now='"+now_str+"';")
    js += """
(function(){
var h2=new Date();var hh2=h2.getHours();var mm2=h2.getMinutes();var isM=(hh2>=9&&hh2<15)||(hh2==9&&mm2>=30);
document.getElementById('ms').innerHTML=(isM?'<span style="color:#48bb78">\u25cf \u76d8\u4e2d</span>':'<span style="color:#f56565">\u25cf \u5df2\u6536\u76d8</span>')+' | '+now;
var m=se.mood||'\u9707\u8361';var mc={'\u5f3a\u52bf':'#48bb78','\u504f\u591a':'#63b3ed','\u9707\u8361':'#ecc94b','\u504f\u5f31':'#f56565','\u5f31\u52bf':'#e53e3e'}[m]||'#ecc94b';
document.getElementById('mt').innerHTML='\u60c5\u7eea: <strong style="color:'+mc+'">'+m+'</strong> | '+se.rise_count+'\u6da8/'+se.fall_count+'\u8dcc | \u6da8\u505c'+se.limit_up+'\u53ea';

var pfHtml='';
if(pf.length>0){
  pfHtml='<table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr style="color:#718096"><th>\u80a1\u7968</th><th>\u6210\u672c</th><th>\u73b0\u4ef7</th><th>\u76c8\u4e8f</th><th>\u6536\u76ca\u7387</th></tr></thead><tbody>';
  for(var i=0;i<pf.length;i++){
    var h=pf[i];var plCls=h.pl>=0?'rise':'fall';var plSign=h.pl>=0?'+':'';
    var pctCls=h.pl_pct>=0?'rise':'fall';var pctSign=h.pl_pct>=0?'+':'';
    pfHtml+='<tr><td><strong>'+h.name+'</strong><br><span style="color:#718096">'+h.code+'</span></td>'
      +'<td>'+h.buy_price+'</td>'
      +'<td class="'+(h.change_pct>=0?'rise':'fall')+'">'+h.current_price+'<br><span style="font-size:10px">'+(h.change_pct>=0?'+':'')+h.change_pct+'%</span></td>'
      +'<td class="'+plCls+'">'+plSign+Math.abs(h.pl).toFixed(0)+'</td>'
      +'<td class="'+pctCls+'">'+pctSign+h.pl_pct.toFixed(1)+'%</td></tr>';
  }
  pfHtml+='</tbody></table>';
  var totalPL=pf.reduce(function(a,b){return a+b.pl},0);
  var tCls=totalPL>=0?'rise':'fall';var tSign=totalPL>=0?'+':'';
  pfHtml+='<div style="font-size:13px;font-weight:700;margin-top:6px;text-align:right" class="'+tCls+'">\u603b\u76c8\u4e8f: '+tSign+Math.abs(totalPL).toFixed(0)+'</div>';
}else{
  pfHtml='<div style="text-align:center;padding:12px;color:#4a5a70">\u6682\u65e0\u6301\u4ed3<br><span style="font-size:11px">\u8fd0\u884c python3 edit_portfolio.py \u6dfb\u52a0</span></div>';
}
document.getElementById('pf').innerHTML=pfHtml;

function rp(picks,id){
  var h='';
  for(var i=0;i<picks.length;i++){
    var s=picks[i];var lv=s.levels;
    h+='<div style="background:#0f1929;border:1px solid #1a2840;border-radius:6px;padding:8px;margin-bottom:6px">'
      +'<div style="display:flex;justify-content:space-between"><span style="font-weight:600">'+s.name+'</span><span style="color:#8899b0;font-size:12px">'+s.code+'</span></div>'
      +'<div style="font-size:12px;color:#a0b0c8;margin:2px 0">'+s.reasons+'</div>'
      +'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;background:#0a0e1a;border-radius:4px;padding:6px;margin:4px 0">'
      +'<div><div style="font-size:10px;color:#48bb78">\u4e70\u5165</div><div style="font-weight:700;font-size:13px">'+lv.buy_point+'</div></div>'
      +'<div><div style="font-size:10px;color:#63b3ed">\u76ee\u6807</div><div style="font-weight:700;font-size:13px">'+lv.target+'<br><span style="font-size:10px;color:#63b3ed">+'+lv.target_pct+'%</span></div></div>'
      +'<div><div style="font-size:10px;color:#f56565">\u6b62\u635f</div><div style="font-weight:700;font-size:13px">'+lv.stop_loss+'<br><span style="font-size:10px;color:#f56565">-'+lv.stop_pct+'%</span></div></div>'
      +'</div><div style="font-size:10px;color:#f56565">\u26a0\ufe0f '+s.risks+'</div></div>';
  }
  document.getElementById(id).innerHTML=h||'<div style="text-align:center;padding:20px;color:#4a5a70">\u6682\u65e0\u4fe1\u53f7</div>';
}
rp(pi,'ip');rp(pe,'ep');
document.getElementById('cp').innerHTML=cc.map(function(c,i){var p=c.change_pct||0;return '<div style="display:flex;padding:2px 0;font-size:12px"><span style="color:#4a5a70;width:18px">'+(i+1)+'</span><span style="flex:1">'+c.name+'</span><span class="'+(p>=0?'pp':'pn')+'">'+(p>=0?'+':'')+p.toFixed(2)+'%</span></div>';}).join('')||'';
})();
"""
    css = ("*{margin:0;padding:0;box-sizing:border-box}"
           "body{font-family:-apple-system,\"PingFang SC\",\"Microsoft YaHei\",sans-serif;background:#0a0e1a;color:#d0d5e0;padding:10px}"
           "h1{font-size:15px;font-weight:700;background:linear-gradient(90deg,#f0b840,#f5923e);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}"
           ".layout{display:grid;grid-template-columns:1fr 1fr;gap:8px}"
           ".card{background:#111827;border:1px solid #1e3050;border-radius:8px;padding:8px;margin-bottom:6px}"
           ".ct{font-size:12px;font-weight:600;color:#c8d0e0;margin-bottom:4px}"
           ".pp{color:#f56565}.pn{color:#48bb78}.rise{color:#f56565}.fall{color:#48bb78}"
           "td{padding:3px 4px;vertical-align:middle}")
    
    html = ('<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\">'
            '<title>A股短线助手 ' + now_str[:10] + '</title><style>' + css + '</style></head><body>'
            '<div style=\"display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;margin-bottom:4px\">'
            '<h1>A股短线助手 - 双看板</h1><div id=\"ms\" style=\"font-size:11px;color:#718096\"></div></div>'
            '<div id=\"mt\" style=\"font-size:11px;margin-bottom:4px\"></div>'
            '<div class=\"card\"><div class=\"ct\">\u7bb1 \u6211\u7684\u6301\u4ed3</div><div id=\"pf\"></div></div>'
            '<div class=\"layout\">'
            '<div class=\"card\"><div class=\"ct\">\ud83d\udd34 \u76d8\u4e2d\u5b9e\u65f6\u4fe1\u53f7</div><div id=\"ip\"></div></div>'
            '<div class=\"card\"><div class=\"ct\">\ud83d\udcca \u5c3e\u76d8\u63a8\u8350</div><div id=\"ep\"></div></div>'
            '</div>'
            '<div class=\"card\"><div class=\"ct\">\ud83d\udd25 \u70ed\u95e8\u677f\u5757</div><div id=\"cp\"></div></div>'
            '<div style=\"font-size:10px;color:#4a5a70;text-align:center;margin-top:6px;padding:4px;border-top:1px solid #1e3050\">'
            '\u5237\u65b0\u6570\u636e: python3 run_combined.py</div>'
            '<script>' + js + '</script></body></html>')
    
    path = os.path.join(OUTPUT_DIR, "stock_report.html")
    with open(path, "w") as f:
        f.write(html)
    chat_out = "/Users/alexsheng/Documents/Codex/2026-06-13/new-chat/outputs/stock_report.html"
    import shutil
    shutil.copy2(path, chat_out)
    print("\u62a5\u544a\u5df2\u751f\u6210:", path)

if __name__ == "__main__":
    run()
