(function(){
// 市场情绪
var m=se.mood||'震荡';
var mc={'强势':'#48bb78','偏多':'#63b3ed','震荡':'#ecc94b','偏弱':'#f56565','弱势':'#e53e3e'}[m]||'#ecc94b';
var mt=document.getElementById('mt');
if(mt){
  var dg=danger?'<span style="color:#e53e3e;font-weight:700"> ⚠️ 大盘风险偏高，建议空仓观望</span>':'';
  mt.innerHTML='<span style="font-size:15px">市场情绪: <strong style="color:'+mc+'">'+m+'</strong> | '+se.rise_count+'涨/'+se.fall_count+'跌 | 涨停'+se.limit_up+'只</span>'+dg;
}
var safe=document.getElementById('safe');
if(safe){
  safe.innerHTML=danger
    ?'<div style="background:#2a1010;border:1px solid #4a2020;border-radius:8px;padding:10px;margin:8px 0;color:#f56565;font-size:13px">⚠️ 今日大盘风险较高（跌停'+se.limit_down+'只），建议以观望为主，严格控制仓位</div>'
    :'<div style="background:#0f1929;border:1px solid #1a2840;border-radius:8px;padding:10px;margin:8px 0;font-size:12px;color:#718096">💡 买入窗口: 14:50~14:57 | 仓位: 单只≤10%~15% | 卖出: 次日9:30~10:30 | 止损: -2%~-3%</div>';
}
// 推荐股票
var ph='';
var pstyles={
  1:{icon:'🚀',color:'#f0b840',bg:'linear-gradient(135deg,#1a2810,#2a3820)'},
  2:{icon:'📊',color:'#63b3ed',bg:'linear-gradient(135deg,#1a2840,#1a3860)'},
  3:{icon:'🔥',color:'#f56565',bg:'linear-gradient(135deg,#2a2020,#3a2830)'},
  4:{icon:'🌱',color:'#48bb78',bg:'linear-gradient(135deg,#102020,#103030)'},
};
for(var i=0;i<p.length;i++){
  var s=p[i];var lv=s.levels;var ps=pstyles[s.pattern_id]||pstyles[1];
  ph+='<div style="background:'+ps.bg+';border:1px solid '+ps.color+';border-radius:10px;padding:14px;margin-bottom:10px">';
  ph+='<div style="font-size:12px;color:'+ps.color+';margin-bottom:4px">'+ps.icon+' '+s.pattern_name+'</div>';
  ph+='<div style="font-size:16px;font-weight:700;color:#e0e5f0">'+s.name+' <span style="font-size:12px;color:#718096;font-weight:400">'+s.code+'</span>';
  ph+=' <span style="font-size:12px;color:#8899b0;font-weight:400">评分'+s.score+'/100</span></div>';
  ph+='<div style="font-size:12px;color:#a0b0c8;margin:4px 0"><strong>'+s.reasons+'</strong></div>';
  ph+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;background:#0a0e1a;border-radius:8px;padding:10px;margin:6px 0">';
  ph+='<div><div style="font-size:10px;color:#48bb78">📌 买入</div><div style="font-weight:700">'+lv.buy_point+'</div></div>';
  ph+='<div><div style="font-size:10px;color:#63b3ed">🎯 目标</div><div style="font-weight:700">'+lv.target+' (+'+lv.target_pct+'%)</div></div>';
  ph+='<div><div style="font-size:10px;color:#f56565">⛔ 止损</div><div style="font-weight:700">'+lv.stop_loss+' (-'+lv.stop_pct+'%)</div></div>';
  ph+='<div><div style="font-size:10px;color:#ecc94b">💰 现价</div><div style="font-weight:700">'+s.price.toFixed(2)+'<span class="'+(s.change_pct>=0?'rise':'fall')+'" style="margin-left:4px">'+(s.change_pct>=0?'+':'')+s.change_pct.toFixed(2)+'%</span></div></div>';
  ph+='</div>';
  ph+='<div style="font-size:11px;color:#f56565">⚠️ '+s.risks+'</div>';
  ph+='<div style="font-size:11px;color:#ecc94b;margin-top:2px">💡 '+s.sell_guide+'</div>';
  ph+='</div>';
}
document.getElementById('pc').innerHTML=ph||'<div style="text-align:center;padding:30px;color:#4a5a70">暂无符合策略的股票</div>';
// 热门板块
document.getElementById('cp').innerHTML=cc.map(function(c,i){
  var p=c.change_pct||0;
  return '<div class="cr"><span class="idx">'+(i+1)+'</span><span style="flex:1">'+c.name+'</span><span class="'+(p>=0?'pp':'pn')+'">'+(p>=0?'+':'')+p.toFixed(2)+'%</span></div>';
}).join('')||'';
// 快讯
document.getElementById('nw').innerHTML=nw.map(function(n){
  var t=n.title||n.content||'';
  var tm=n.time||'';
  return (tm?'<div class="nt">'+tm+'</div>':'')+'<div>'+t+'</div>';
}).join('')||'';
// 周末提醒
var d=new Date();var w=d.getDay();
if(w===0||w===6){
  var wt=document.getElementById('wt');
  if(wt) wt.innerHTML='<div style="background:#1a2840;border-radius:6px;padding:6px;font-size:12px;color:#ecc94b;margin:6px 0">📅 今日非交易日，数据为最近交易日</div>';
}
})();
