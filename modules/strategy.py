"""
A股短线策略引擎 v2 - 四套实战打法
基于尾盘分析的攻防体系
"""

import os
import pandas as pd
import numpy as np
from .data_fetcher import get_data_fetcher
from .hot_topics import get_hot_tracker

COMMON_TOPICS = ['科技', '医药', '新能源', '汽车', '芯片', 'AI', '人工智能',
    '证券', '银行', '地产', '消费', '食品', '酒', '电力', '光伏', '锂电',
    '军工', '通信', '传媒', '游戏', '旅游', '黄金', '有色', '化工', '机械',
    '基建', '环保', '机器人', '低空经济', '数字经济', '算力', '数据要素',
    '跨境支付', '储能', '氢能', '半导体', '创新药', '电商', '物流', '航运']


def _is_valid_code(code):
    """检查是否可交易（排除创业板/科创板/北交所/B股）"""
    if code.startswith(('300','301')):
        return False
    if code.startswith('688'):
        return False
    if code.startswith(('8','900','920')):
        return False
    return True

def _hot_score(name, hot_names):
    """热点关联评分"""
    score, matched = 0, []
    for hn in hot_names:
        if len(hn) >= 2 and (hn in name or name in hn):
            score += 20
            matched.append(hn)
    for topic in COMMON_TOPICS:
        if topic in name:
            for hn in hot_names:
                if topic in hn or hn in topic:
                    score += 10
                    if topic not in matched:
                        matched.append(topic)
                    break
            if score > 0:
                break
    return min(score, 30), matched


def _sina_prefix(code):
    if code.startswith('6'):
        return 'sh' + code
    return 'sz' + code


class StrategyEngine:
    """策略引擎 - 四套尾盘打法"""

    def __init__(self):
        self.fetcher = get_data_fetcher()
        self.tracker = get_hot_tracker()
        self._load_sectors()
    
    def _load_sectors(self):
        """加载板块股票库"""
        import json as _json
        _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sector_stocks.json')
        self.sector_watchlist = {}  # code -> sector_name
        self.watchlist_codes = set()
        if os.path.exists(_p):
            with open(_p) as _f:
                data = _json.load(_f)
            for sector, stocks in data.items():
                for s in stocks:
                    code = str(s.get('code', ''))
                    if code:
                        self.sector_watchlist[code] = sector
                        self.watchlist_codes.add(code)

    def get_market_sentiment(self):
        spot = self.fetcher.get_all_stocks_spot()
        if spot is None or spot.empty:
            return {}
        rise = spot[spot['change_pct'] > 0]
        fall = spot[spot['change_pct'] < 0]
        rc, fc = len(rise), len(fall)
        ratio = rc / max(fc, 1)
        limit_up = spot[(spot['change_pct'] >= 9.5) & (abs(spot['price'] - spot['high']) / spot['price'] < 0.005)]
        limit_down = spot[(spot['change_pct'] <= -9.5) & (abs(spot['price'] - spot['low']) / spot['price'] < 0.005)]
        hott = spot[spot['turnover'] > 5]
        if ratio >= 2 and len(limit_up) >= 5:
            mood = '强势'
        elif ratio >= 1.2 and len(limit_up) >= 3:
            mood = '偏多'
        elif ratio >= 0.8:
            mood = '震荡'
        elif ratio >= 0.5:
            mood = '偏弱'
        else:
            mood = '弱势'
        return {
            'rise_count': rc, 'fall_count': fc, 'ratio': round(ratio, 2),
            'limit_up': len(limit_up), 'limit_down': len(limit_down),
            'high_turnover_pct': round(len(hott) / max(len(spot), 1) * 100, 1),
            'mood': mood,
        }

    def _calc_levels(self, price, high, low, amplitude, change_pct, pattern='breakout'):
        """根据打法和波动率计算买卖点位"""
        amp = max(abs(amplitude), 2) / 100.0

        if pattern == 'breakout':
            # 攻击型：进取一点，买在回踩位
            buy_low = round(max(low * 1.005, price * 0.985), 2)
            buy_high = round(price * 1.005, 2)
            target_pct = min(max(amp * 0.5, 0.025), 0.055)
            stop_pct = min(max(amp * 0.25, 0.02), 0.03)
        elif pattern == 'ma_support':
            # 均线回踩：保守，买在支撑位附近
            buy_low = round(price * 0.985, 2)
            buy_high = round(price * 1.002, 2)
            target_pct = min(max(amp * 0.4, 0.02), 0.035)
            stop_pct = min(max(amp * 0.2, 0.02), 0.025)
        elif pattern == 'hot_sector':
            # 热点回流：中等
            buy_low = round(price * 0.992, 2)
            buy_high = round(price * 1.008, 2)
            target_pct = min(max(amp * 0.45, 0.025), 0.05)
            stop_pct = min(max(amp * 0.22, 0.02), 0.028)
        else:  # bottom
            buy_low = round(price * 0.992, 2)
            buy_high = round(price * 1.005, 2)
            target_pct = min(max(amp * 0.35, 0.015), 0.03)
            stop_pct = min(max(amp * 0.2, 0.02), 0.025)

        target = round(price * (1 + target_pct), 2)
        stop_loss = round(price * (1 - stop_pct), 2)
        # 取中间偏低的单一点位作为买入点
        buy_point = round((buy_low + buy_high) / 2 * 0.998, 2)
        return {
            'buy_point': buy_point,
            'target': target,
            'target_pct': round(target_pct * 100, 1),
            'stop_loss': stop_loss,
            'stop_pct': round(stop_pct * 100, 1),
        }

    def get_top_picks(self, n=3, mode="eod"):
        """
        主入口：返回按策略分组的推荐股票
        Phase 1: 全市场扫描 + 初步评分
        Phase 2: 对候选股获取历史数据验证均线
        """
        spot = self.fetcher.get_all_stocks_spot()
        if spot is None or spot.empty:
            return None

        # 获取板块库股票的实时数据，合并到分析池
        if self.watchlist_codes:
            wl_codes = list(self.watchlist_codes)
            wl_data = self.fetcher.get_stocks_by_codes(wl_codes)
            if wl_data is not None and not wl_data.empty:
                # 标记板块归属
                wl_data['sector'] = wl_data['code'].apply(lambda c: self.sector_watchlist.get(str(c), ''))
                # 合并，优先保留主数据的更高行情（量更大）
                spot_codes = set(spot['code'].astype(str))
                new_stocks = wl_data[~wl_data['code'].isin(spot_codes)]
                if not new_stocks.empty:
                    spot = pd.concat([spot, new_stocks], ignore_index=True)
                    print(f"  [板块库] 补充 {len(new_stocks)} 只板块股, 总 {len(spot)} 只")

        tracker = get_hot_tracker()
        concepts = tracker.get_hot_concepts(top_n=15)
        keywords = tracker.get_today_hot_keywords()
        hot_names = [c['name'] for c in concepts] + keywords
        sentiment = self.get_market_sentiment()
        rf_ratio = sentiment.get('ratio', 1)

        # 识别热点板块
        hot_sectors = {}
        for c in concepts:
            if c.get('change_pct', 0) > 2:
                hot_sectors[c['name']] = c

        # 过滤并评分所有股票
        all_candidates = {1: [], 2: [], 3: [], 4: []}
        all_stocks_info = []

        for _, row in spot.iterrows():
            code = str(row.get('code', ''))
            name = str(row.get('name', ''))
            if not _is_valid_code(code) or 'ST' in name or '退' in name:
                continue

            price = float(row.get('price', 0))
            change_pct = float(row.get('change_pct', 0))
            turnover = float(row.get('turnover', 0))
            amount_yi = float(row.get('amount', 0)) / 1e8
            high = float(row.get('high', 0))
            low = float(row.get('low', 0))
            amplitude = float(row.get('amplitude', 0))
            vol_ratio = float(row.get('vol_ratio', 0) or 1)
            pe_val = float(row.get('pe', 0) or 0)
            avg_price = float(row.get('avg_price', 0) or 0)
            ma_60 = float(row.get('ma_60', 0) or 0)
            change_60d = 0  # removed - use ma_60 instead

            hs, matched = _hot_score(name, hot_names)
            price_near_high = price > 0 and high > 0 and price / high >= 0.92
            above_vwap = price > avg_price if avg_price > 0 else True

            # ---- Pattern 1: 攻击型尾盘突破 ----
            p1_score = 0
            if mode == "intraday":
                # 盘中模式：更宽松的阈值，更关注实时波动
                p1_ok = (vol_ratio > 0.8 and turnover > 1.0
                        and 1 < change_pct < 9.5 and above_vwap)
                p2_ok = (change_pct > 2 and price > ma_60 * 0.95
                        and vol_ratio > 0.5 and turnover > 0.5)
                p3_ok = (hs >= 5 and 1 < change_pct < 7
                        and vol_ratio > 0.8 and above_vwap)
                p4_ok = (vol_ratio < 0.8 and change_pct > -2 and change_pct < 4)
            else:
                p1_ok = (price_near_high and vol_ratio > 1.0 and turnover > 1.5
                        and 2 < change_pct < 9.5 and above_vwap)
                p2_ok = (price > ma_60 and -3 < change_pct < 4
                        and 1 < turnover < 10 and price > ma_60 * 0.95
                        and vol_ratio < 2.0)
                p3_ok = (hs >= 5 and 1 < change_pct < 7
                        and vol_ratio > 1.0 and turnover > 1.5 and above_vwap)
                p4_ok = (price < ma_60 and vol_ratio < 1.0
                        and -1 < change_pct < 5 and turnover < 10)
            
            if (p1_ok):
                p1_score = int(hs * 0.3 + min(change_pct / 9.5 * 40, 30)
                               + min(vol_ratio / 3 * 20, 15) + min(turnover / 10 * 10, 10))
                all_candidates[1].append({
                    'code': code, 'name': name, 'price': price,
                    'change_pct': round(change_pct, 2),
                    'turnover': round(turnover, 2),
                    'amount_yi': round(amount_yi, 2),
                    'vol_ratio': round(vol_ratio, 2),
                    'amplitude': round(amplitude, 2),
                    'high': high, 'low': low,
                    'p1_score': p1_score,
                    'matched_topics': matched,
                })

            # ---- Pattern 2: 均线回踩支撑 ----
            p2_score = 0
            if (price > ma_60 and -3 < change_pct < 4
                    and 1 < turnover < 10 and price > ma_60 * 0.95
                    and vol_ratio < 2.0):
                p2_score = int(min(max(price - ma_60, 0) / ma_60 * 50, 20)
                               + min(vol_ratio * 10, 10)
                               + (hs * 0.3))
                all_candidates[2].append({
                    'code': code, 'name': name, 'price': price,
                    'change_pct': round(change_pct, 2),
                    'turnover': round(turnover, 2),
                    'amount_yi': round(amount_yi, 2),
                    'vol_ratio': round(vol_ratio, 2),
                    'amplitude': round(amplitude, 2),
                    'high': high, 'low': low,
                    'p2_score': p2_score,
                    'matched_topics': matched,
                })

            # ---- Pattern 3: 主线热点回流 ----
            p3_score = 0
            if (hs >= 5 and 1 < change_pct < 7
                    and vol_ratio > 1.0 and turnover > 1.5
                    and above_vwap):
                p3_score = int(hs * 0.5 + min(vol_ratio / 3 * 20, 15)
                               + min(change_pct / 7 * 20, 15))
                all_candidates[3].append({
                    'code': code, 'name': name, 'price': price,
                    'change_pct': round(change_pct, 2),
                    'turnover': round(turnover, 2),
                    'amount_yi': round(amount_yi, 2),
                    'vol_ratio': round(vol_ratio, 2),
                    'amplitude': round(amplitude, 2),
                    'high': high, 'low': low,
                    'p3_score': p3_score,
                    'matched_topics': matched,
                })

            # ---- Pattern 4: 地量底部首阳 ----
            p4_score = 0
            if (price < ma_60 and vol_ratio < 1.0
                    and -1 < change_pct < 5 and turnover < 10
                    and price > 0):
                p4_score = int(min(max(ma_60 - price, 0) / ma_60 * 30, 15)
                               + min(max(1 - vol_ratio, 0) * 20, 15)
                               + (hs * 0.2))
                all_candidates[4].append({
                    'code': code, 'name': name, 'price': price,
                    'change_pct': round(change_pct, 2),
                    'turnover': round(turnover, 2),
                    'amount_yi': round(amount_yi, 2),
                    'vol_ratio': round(vol_ratio, 2),
                    'amplitude': round(amplitude, 2),
                    'high': high, 'low': low,
                    'p4_score': p4_score,
                    'matched_topics': matched,
                })

        # Phase 2: 简化的验证（去掉Sina历史数据依赖）
        pattern_names = {
            1: '攻击型尾盘突破', 2: '均线回踩支撑',
            3: '主线热点回流', 4: '地量底部首阳'
        }
        pattern_icons = {1: 'breakout', 2: 'ma_support', 3: 'hot_sector', 4: 'bottom'}
        final_picks = []

        for p_id in [1, 2, 3, 4]:
            candidates = all_candidates[p_id]
            if not candidates:
                continue
            sorted_c = sorted(candidates, key=lambda x: x.get(
                f'p{p_id}_score', 0), reverse=True)[:5]

            verified = []
            for c in sorted_c:
                score = c.get(f'p{p_id}_score', 0)
                if score < 20:
                    continue

                # 获取历史数据进行Phase 2验证
                hist = self.fetcher.get_sina_history(c['code'], days=30)
                ma_confirmed = True
                if hist and hist.get('ma5') and hist.get('ma10') and hist.get('ma20'):
                    ma5 = hist['ma5']
                    ma10 = hist['ma10']
                    ma20 = hist['ma20']
                    price = c['price']

                    if p_id == 2:  # 均线回踩：需要多头排列
                        if not (ma5 > ma10 > ma20):
                            ma_confirmed = False
                        # 价格应靠近MA10或MA20
                        if price > ma5 * 1.03:
                            ma_confirmed = False
                    elif p_id == 4:  # 底部：需要空头排列
                        if hist['ma_trend'] != 'bearish':
                            ma_confirmed = False
                    elif p_id == 1:  # 突破：至少不能是空头
                        if hist['ma_trend'] == 'bearish':
                            ma_confirmed = False
                elif hist is None:
                    # 如果拿不到历史数据，降低置信度但不完全排除
                    pass

                if ma_confirmed:
                    verified.append(c)

            # Final排名
            verified = sorted(verified, key=lambda x: x.get(
                f'p{p_id}_score', 0), reverse=True)

            for i, v in enumerate(verified):
                if i >= 2:  # 每个策略最多2只
                    break
                s = v
                levels = self._calc_levels(
                    s['price'], s.get('high', s['price']),
                    s.get('low', s['price'] * 0.98),
                    s.get('amplitude', 3), s['change_pct'],
                    pattern_icons[p_id])

                # 生成推荐理由
                reasons_parts = []
                if s.get('matched_topics'):
                    reasons_parts.append('热点:' + ';'.join(s['matched_topics'][:2]))
                if s['vol_ratio'] > 1.5:
                    reasons_parts.append('放量%.1f倍' % s['vol_ratio'])
                if s['change_pct'] > 5:
                    reasons_parts.append('强势')
                if p_id == 1:
                    reasons_parts.append('尾盘突破')
                elif p_id == 2:
                    reasons_parts.append('均线支撑')
                elif p_id == 3:
                    reasons_parts.append('热点回流')
                elif p_id == 4:
                    reasons_parts.append('地量企稳')

                risk = []
                if s['change_pct'] > 7:
                    risk.append('追高风险')
                if s['turnover'] > 10:
                    risk.append('换手过高')
                if s.get('amplitude', 0) > 8:
                    risk.append('波动大')
                if not risk:
                    risk.append('严格止损')

                # 买卖指南
                sell_guide = ''
                if p_id == 1:
                    sell_guide = '次日9:30-10:30冲高止盈; 高开>3%提防回落; 低开破-1.5%九点半前止损'
                elif p_id == 2:
                    sell_guide = '次日冲高+1.5%~+3%走人; 跌破买入日收盘价直接止损'
                elif p_id == 3:
                    sell_guide = '9:25看板块龙头竞价; 龙头高开持有, 低开竞价就走'
                else:
                    sell_guide = '可持有1-2天; 目标+2%见好就收; 跌破买入价出局'

                final_picks.append({
                    'code': s['code'],
                    'name': s['name'],
                    'price': s['price'],
                    'change_pct': s['change_pct'],
                    'score': s.get(f'p{p_id}_score', 0),
                    'pattern_id': p_id,
                    'pattern_name': pattern_names[p_id],
                    'matched_topics': s.get('matched_topics', []),
                    'reasons': '; '.join(reasons_parts),
                    'risks': '; '.join(risk),
                    'sell_guide': sell_guide,
                    'levels': levels,
                })

        # 兜底：如果推荐不足3支，用综合评分补足
        if len(final_picks) < 3 and not all_candidates.get('_all'):
            # 对剩余所有股票做一个简化评分
            backup_candidates = []
            for _, row in spot.iterrows():
                code2 = str(row.get('code', ''))
                name2 = str(row.get('name', ''))
                if not _is_valid_code(code2) or 'ST' in name2 or '退' in name2:
                    continue
                # 跳过已在推荐中的
                if any(p['code'] == code2 for p in final_picks):
                    continue
                
                p2 = float(row.get('price', 0))
                cp2 = float(row.get('change_pct', 0))
                to2 = float(row.get('turnover', 0))
                vr2 = float(row.get('vol_ratio', 0) or 1)
                amt2 = float(row.get('amount', 0)) / 1e8
                hs2, _ = _hot_score(name2, hot_names)
                
                # 综合评分：热点+涨幅+量比+换手率
                sector_bonus2 = 10 if code2 in self.watchlist_codes else 0
                total2 = hs2 + min(max(cp2, 0) / 10 * 25, 20) + min(vr2 / 2 * 15, 12) + min(to2 / 5 * 10, 8) + sector_bonus2
                if total2 >= 15:
                    lv2 = self._calc_levels(p2, float(row.get('high', p2)),
                                            float(row.get('low', p2 * 0.98)),
                                            abs(float(row.get('change_pct', 0))), cp2, 'ma_support')
                    backup_candidates.append({
                        'code': code2, 'name': name2, 'price': p2,
                        'change_pct': round(cp2, 2),
                        'score': int(total2),
                        'pattern_id': 2, 'pattern_name': '综合评分(备选)',
                        'matched_topics': [],
                        'reasons': '全市场扫描补充推荐',
                        'risks': '严格止损',
                        'sell_guide': '次日9:30-10:30冲高止盈; 跌破买入价出局',
                        'levels': lv2,
                    })
            
            backup_candidates.sort(key=lambda x: x['score'], reverse=True)
            for bc in backup_candidates:
                if len(final_picks) >= 3:
                    break
                final_picks.append(bc)
        
        # 增加大盘风险判断
        market_danger = sentiment.get('limit_down', 0) > 20 or sentiment.get('mood') in ['弱势']

        return {
            'picks': final_picks,
            'sentiment': sentiment,
            'hot_concepts': concepts[:10],
            'market_danger': market_danger,
        }

    def get_today_signals(self):
        picks = self.get_top_picks(n=30)
        if picks and picks['picks']:
            return pd.DataFrame(picks['picks'])
        return None

    def get_market_overview(self):
        return self.get_market_sentiment()


_instance = None
def get_strategy():
    global _instance
    if _instance is None:
        _instance = StrategyEngine()
    return _instance
