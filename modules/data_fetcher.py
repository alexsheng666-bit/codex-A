"""
A股数据获取模块
使用东方财富push2标准接口获取实时行情和板块数据
"""

import requests
import pandas as pd
import time
from datetime import datetime, timedelta


class DataFetcher:
    """数据获取器"""

    EASTMONEY_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.eastmoney.com/',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.EASTMONEY_HEADERS)
        self._spot_cache = None
        self._spot_cache_time = None

    def get_all_stocks_spot(self, force_refresh=False):
        """获取全市场实时行情（缓存60秒）"""
        now = time.time()
        if not force_refresh and self._spot_cache is not None and now - self._spot_cache_time < 60:
            return self._spot_cache
        try:
            url = 'https://push2.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': '1',
                'pz': '1000',
                'po': '1',
                'np': '1',
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': '2',
                'invt': '2',
                'fid': 'f50',
                'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048',
                'fields': 'f2,f3,f4,f6,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f37,f38,f40,f41,f45,f46,f50,f57,f58,f62,f115,f128,f136,f140,f141,f152,f292',
                '_': int(time.time() * 1000),
            }
            resp = self.session.get(url, params=params, timeout=15)
            data = resp.json()
            rows = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    rows.append({
                        'code': str(item.get('f12', '')),
                        'name': str(item.get('f14', '')),
                        'price': float(item.get('f2', 0)),
                        'change_pct': float(item.get('f3', 0)),
                        'change_amount': float(item.get('f4', 0)),
                        'volume': float(item.get('f6', 0)),
                        'amount': float(item.get('f50', 0) or 0),
                        'high': float(item.get('f15', 0)),
                        'low': float(item.get('f16', 0)),
                        'open': float(item.get('f17', 0)),
                        'prev_close': float(item.get('f18', 0) or 0),
                        'turnover': float(item.get('f8', 0) or 0),
                        'pe': float(item.get('f9', 0) or 0),
                        'pb': float(item.get('f23', 0) or 0),
                        'amplitude': round((float(item.get('f15', 0)) - float(item.get('f16', 0))) / max(float(item.get('f18', 0) or item.get('f2', 1)), 1) * 100, 2),
                        'total_mv': float(item.get('f20', 0) or 0),
                        'vol_ratio': float(item.get('f10', 0) or 0),
                        'avg_price': float(item.get('f45', 0) or 0),
                        'ma_60': float(item.get('f57', 0) or 0),
                        'avg_turnover_30d': float(item.get('f62', 0) or 0),
                        'nav_per_share': float(item.get('f115', 0) or 0),
                        'status': int(item.get('f152', 0)),
                        'board_count': int(item.get('f292', 0)),
                    })
            if rows:
                df = pd.DataFrame(rows)
                self._spot_cache = df
                self._spot_cache_time = now
                return df
            return None
        except Exception as e:
            print(f"[data_fetcher] 获取全市场行情失败: {e}")
            return self._spot_cache


    def get_hot_boards(self):
        """获取热门板块"""
        result = {'concept': None, 'industry': None}
        try:
            url = 'https://push2.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': '1', 'pz': '20', 'po': '1', 'np': '1',
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': '2', 'invt': '2', 'fid': 'f50',
                'fs': 'm:90+t:3', 'fields': 'f2,f3,f4,f8,f12,f14,f20',
            }
            resp = self.session.get(url, params=params, timeout=15)
            data = resp.json()
            items = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    items.append({
                        'code': item.get('f12', ''),
                        'name': item.get('f14', ''),
                        'change_pct': item.get('f3', 0),
                    })
            result['concept'] = pd.DataFrame(items) if items else None
        except Exception as e:
            print(f"[data_fetcher] 获取概念板块失败: {e}")
        return result

    def get_board_stocks(self, board_code):
        """获取板块内的成分股"""
        try:
            url = 'https://push2.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': '1', 'pz': '100', 'po': '1', 'np': '1',
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': '2', 'invt': '2', 'fid': 'f50',
                'fs': f'b:{board_code}+f:!50',
                'fields': 'f2,f3,f4,f12,f14',
            }
            resp = self.session.get(url, params=params, timeout=15)
            data = resp.json()
            rows = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    rows.append({
                        'code': str(item.get('f12', '')),
                        'name': str(item.get('f14', '')),
                        'price': float(item.get('f2', 0)),
                        'change_pct': float(item.get('f3', 0)),
                    })
            return pd.DataFrame(rows) if rows else None
        except Exception as e:
            print(f"[data_fetcher] 获取板块成分股失败: {e}")
            return None


    def get_sina_history(self, code, days=30):
        """从新浪财经获取个股历史K线数据"""
        try:
            if code.startswith('6') or code.startswith('9'):
                symbol = 'sh' + code
            else:
                symbol = 'sz' + code
            url = 'https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData'
            params = {'symbol': symbol, 'scale': '240', 'ma': 'no', 'datalen': str(days)}
            resp = self.session.get(url, params=params, timeout=15)
            if resp.text.startswith('['):
                import json as _json
                data = _json.loads(resp.text)
                if data and len(data) >= 5:
                    closes = [float(d['close']) for d in data]
                    highs = [float(d['high']) for d in data]
                    lows = [float(d['low']) for d in data]
                    volumes = [float(d['volume']) for d in data]
                    opens = [float(d['open']) for d in data]
                    
                    def _ma(arr, n):
                        if len(arr) >= n:
                            return sum(arr[-n:]) / n
                        return None
                    
                    def _kdj(closes, highs, lows):
                        n = min(9, len(closes))
                        if n < 5:
                            return None, None, None
                        low_n = min(lows[-n:])
                        high_n = max(highs[-n:])
                        if high_n == low_n:
                            return 50, 50, 50
                        rsv = (closes[-1] - low_n) / (high_n - low_n) * 100
                        k = min(max(rsv, 0), 100)
                        d = k * 2 / 3 + 33.33
                        j = 3 * k - 2 * d
                        return round(k, 1), round(d, 1), round(j, 1)
                    
                    result = {
                        'ma5': _ma(closes, 5),
                        'ma10': _ma(closes, 10),
                        'ma20': _ma(closes, 20),
                        'ma60': _ma(closes, 60),
                        'close': closes[-1] if closes else None,
                        'closes': closes,
                        'volumes': volumes,
                        'opens': opens,
                        'highs': highs,
                        'lows': lows,
                    }
                    k, d, j = _kdj(closes, highs, lows)
                    result['kdj_k'] = k
                    result['kdj_d'] = d
                    result['kdj_j'] = j
                    
                    # 判断均线状态
                    if result['ma5'] and result['ma10'] and result['ma20']:
                        if result['ma5'] > result['ma10'] > result['ma20']:
                            result['ma_trend'] = 'bullish'
                        elif result['ma5'] < result['ma10'] < result['ma20']:
                            result['ma_trend'] = 'bearish'
                        else:
                            result['ma_trend'] = 'mixed'
                    return result
            return None
        except:
            return None

    def get_stocks_by_codes(self, codes_list):
        """按股票代码批量获取实时行情"""
        if not codes_list:
            return None
        secids = []
        for c in codes_list:
            if c.startswith(('6','9')):
                secids.append('1.' + c)
            else:
                secids.append('0.' + c)
        try:
            url = 'https://push2.eastmoney.com/api/qt/ulist.np/get'
            params = {
                'fltt': '2',
                'secids': ','.join(secids),
                'fields': 'f2,f3,f4,f6,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f37,f38,f40,f41,f45,f46,f50,f57,f115,f152,f292',
                '_': 0,
            }
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get('data') and data['data'].get('diff'):
                rows = []
                for item in data['data']['diff']:
                    rows.append(self._parse_item(item))
                return pd.DataFrame(rows) if rows else None
            return None
        except Exception as e:
            print(f"[data_fetcher] 按代码获取行情失败: {e}")
            return None

    def _parse_item(self, item):
        return {
            'code': str(item.get('f12', '')),
            'name': str(item.get('f14', '')),
            'price': float(item.get('f2', 0)),
            'change_pct': float(item.get('f3', 0)),
            'change_amount': float(item.get('f4', 0)),
            'volume': float(item.get('f6', 0)),
            'amount': float(item.get('f50', 0) or 0),
            'high': float(item.get('f15', 0)),
            'low': float(item.get('f16', 0)),
            'open': float(item.get('f17', 0)),
            'prev_close': float(item.get('f18', 0) or 0),
            'turnover': float(item.get('f8', 0) or 0),
            'pe': float(item.get('f9', 0) or 0),
            'pb': float(item.get('f23', 0) or 0),
            'amplitude': round((float(item.get('f15', 0)) - float(item.get('f16', 0)))
                               / max(float(item.get('f18', 0) or item.get('f2', 1)), 1) * 100, 2),
            'total_mv': float(item.get('f20', 0) or 0),
            'vol_ratio': float(item.get('f10', 0) or 0),
            'avg_price': float(item.get('f45', 0) or 0),
            'ma_60': float(item.get('f57', 0) or 0),
            'nav_per_share': float(item.get('f115', 0) or 0),
            'status': int(item.get('f152', 0)),
            'board_count': int(item.get('f292', 0)),
        }

_instance = None
def get_data_fetcher():
    global _instance
    if _instance is None:
        _instance = DataFetcher()
    return _instance
