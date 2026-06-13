"""
热点题材追踪模块
从东方财富等抓取当日热门话题、新闻、板块轮动信息
"""

import requests
import json
import time
import re
from datetime import datetime


class HotTopicTracker:
    """热点追踪器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.eastmoney.com/',
        })
        self._cache = {}
        self._cache_time = {}

    def _cached(self, key, ttl=120):
        if key in self._cache and time.time() - self._cache_time.get(key, 0) < ttl:
            return self._cache[key]
        return None

    def _set_cache(self, key, value):
        self._cache[key] = value
        self._cache_time[key] = time.time()

    def get_eastmoney_news(self, top_n=15):
        """获取东方财富快讯头条"""
        cached = self._cached('em_news', ttl=180)
        if cached:
            return cached[:top_n]
        try:
            url = 'https://push2.eastmoney.com/api/qt/ulist.np/get'
            params = {
                'fltt': '2',
                'secids': '1.000001,0.399001,0.399006,1.000688',
                'fields': 'f2,f3,f4,f12,f14',
                '_': int(time.time() * 1000)
            }
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            items = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    items.append({
                        'code': item.get('f12', ''),
                        'name': item.get('f14', ''),
                        'price': item.get('f2', 0),
                        'change_pct': item.get('f3', 0),
                    })
            news = self._fetch_fast_news(limit=top_n)
            if news:
                items = news + items
            self._set_cache('em_news', items)
            return items[:top_n]
        except Exception as e:
            print(f"[hot_topics] 东方财富接口失败: {e}")
            return self._cache.get('em_news', [])[:top_n]

    def _fetch_fast_news(self, limit=10):
        """抓取东方财富快讯"""
        try:
            url = 'https://push2ex.eastmoney.com/getStockNews'
            params = {'pageindex': '0', 'pagesize': str(limit), '_': int(time.time() * 1000)}
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            items = []
            if data.get('data') and data['data'].get('list'):
                for item in data['data']['list']:
                    items.append({
                        'title': item.get('title', ''),
                        'content': item.get('digest', item.get('content', '')),
                        'time': item.get('showtime', ''),
                        'type': 'news',
                    })
            return items
        except:
            return []

    def get_hot_concepts(self, top_n=15):
        """获取东方财富热门概念板块排名"""
        cached = self._cached('hot_concepts', ttl=120)
        if cached:
            return cached[:top_n]
        try:
            url = 'https://push2.eastmoney.com/api/qt/clist/get'
            params = {
                'pn': '1', 'pz': str(top_n), 'po': '1', 'np': '1',
                'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                'fltt': '2', 'invt': '2', 'fid': 'f3',
                'fs': 'm:90+t:3',
                'fields': 'f12,f14,f2,f3,f4,f8,f20',
                '_': int(time.time() * 1000)
            }
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            items = []
            if data.get('data') and data['data'].get('diff'):
                for item in data['data']['diff']:
                    items.append({
                        'code': item.get('f12', ''),
                        'name': item.get('f14', ''),
                        'price': item.get('f2', 0),
                        'change_pct': item.get('f3', 0),
                        'up_count': item.get('f20', 0),
                    })
            self._set_cache('hot_concepts', items)
            return items[:top_n]
        except Exception as e:
            print(f"[hot_topics] 获取热门概念失败: {e}")
            return self._cache.get('hot_concepts', [])[:top_n]

    def get_today_hot_keywords(self):
        """获取今日热门关键词"""
        news = self.get_eastmoney_news(top_n=30)
        hot_concepts = self.get_hot_concepts(top_n=10)
        keywords = set()
        for c in hot_concepts:
            name = c.get('name', '')
            if name and c.get('change_pct', 0) > 2:
                keywords.add(name)
        for n in news:
            title = n.get('title', '') or n.get('content', '') or ''
            patterns = [
                r'(.{2,8})概念', r'(.{2,8})板块', r'(.{2,8})利好',
                r'(.{2,8})大涨', r'(.{2,8})爆发', r'(.{2,8})政策',
            ]
            for p in patterns:
                match = re.search(p, title)
                if match:
                    kw = match.group(1).strip()
                    if len(kw) >= 2:
                        keywords.add(kw)
        return list(keywords)[:20]


_instance = None
def get_hot_tracker():
    global _instance
    if _instance is None:
        _instance = HotTopicTracker()
    return _instance
