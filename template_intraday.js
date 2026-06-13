(function(){
var m=se.mood||'震荡';
var mc={'强势':'#48bb78','偏多':'#63b3ed','震荡':'#ecc94b','偏弱':'#f56565','弱势':'#e53e3e'}[m]||'#ecc94b';
// 市场状态
var h=new Date();var hh=h.getHours();var mm=h.getMinutes();var isMarket=(hh>=9&&hh<15)||(hh==9&&mm>=30);
var marketStatus=isMarket?'<span style="color:#48bb78">● 盘中交易中</span>':'<span style="color:#f56565">● 已收盘</span>';
document.getElementById('market-status').innerHTML=marketStatus+' <span style="color:#718096;font-size:12px">| 上次更新: '+now+'</span>';
// 情绪
document.getElementById('mood-text').innerHTML='<span style="font-size:14px">市场情绪: <strong style="color:'+mc+'">'+m+'</strong> | '+se.rise_count+'涨/'+se.fall_count+'跌 | 涨停'+se.limit_up+'只</span>';
document.getElementById('safe').innerHTML='<div style="background:#0f1929;border:1px solid #1a2840;border-radius:6px;padding:8px;font-size:12px;color:#718096">💡 盘中实时信号 | 建议每15-30分钟重新运行刷新数据 | 买入窗口: 14:50~14:57 | 仓位: 单只≤10%~15% | 止损: -2%~-3%</div>';
// 推荐
var ph='';
for(var i=0;i<p.length;i++){
  var s=p[i];var lv=s.levels;
  ph+='<div style="background:#111827;border:1px solid #1e3050;border-radius:8px;padding:12px;margin-bottom:8px">';
  ph+='<div style="display:flex;justify-content:space-between;align-items:center">';
  ph+='<div><span style="font-size:15px;font-weight:700;color:#e0e5f0">'+s.name+'</span> <span style="font-size:12px;color:#718096">'+s.code+'</span></div>';
  ph+='<div style="font-size:16px;font-weight:700" class="'+(s.change_pct>=0?'rise':'fall')+'">'+(s.change_pct>=0?'+':'')+s.change_pct.toFixed(2)+'%</div>';
  ph+='</div>';
  ph+='<div style="font-size:12px;color:#a0b0c8;margin:4px 0">'+s.reasons+'</div>';
  ph+='<div style="display:grid;grid-template-columns:3fr 2fr 2fr;gap:4px;background:#0a0e1a;border-radius:6px;padding:8px;margin:6px 0">';
  ph+='<div><div style="font-size:10px;color:#48bb78">📌 买入</div><div style="font-weight:700;font-size:15px;color:#c8d0e0">'+lv.buy_point+'</div></div>';
  ph+='<div><div style="font-size:10px;color:#63b3ed">🎯 目标</div><div style="font-weight:700;color:#c8d0e0">'+lv.target+'<br><span style="font-size:11px;color:#63b3ed">+'+lv.target_pct+'%</span></div></div>';
  ph+='<div><div style="font-size:10px;color:#f56565">⛔ 止损</div><div style="font-weight:700;color:#c8d0e0">'+lv.stop_loss+'<br><span style="font-size:11px;color:#f56565">-'+lv.stop_pct+'%</span></div></div>';
  ph+='</div>';
  ph+='<div style="font-size:11px;color:#f56565">⚠️ '+s.risks+'</div>';
  ph+='<div style="font-size:11px;color:#ecc94b">💡 '+s.sell_guide+'</div>';
  ph+='</div>';
}
document.getElementById('pc').innerHTML=ph||'<div style="text-align:center;padding:30px;color:#4a5a70">暂无实时信号</div>';
// 板块
document.getElementById('cp').innerHTML=cc.map(function(c,i){
  var p=c.change_pct||0;
  return '<div class="cr"><span class="idx">'+(i+1)+'</span><span style="flex:1">'+c.name+'</span><span class="'+(p>=0?'pp':'pn')+'">'+(p>=0?'+':'')+p.toFixed(2)+'%</span></div>';
}).join('')||'';
})();
