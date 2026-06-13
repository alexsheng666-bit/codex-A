"""
A股热点短线助手 - Web 服务 (使用waitress)
"""

from flask import Flask, render_template, jsonify
from modules.strategy import get_strategy
from modules.hot_topics import get_hot_tracker
from modules.data_fetcher import get_data_fetcher
from datetime import datetime

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/overview')
def api_overview():
    strategy = get_strategy()
    overview = strategy.get_market_overview()
    return jsonify({
        'success': True,
        'data': overview,
        'time': datetime.now().strftime('%H:%M:%S')
    })


@app.route('/api/hot_concepts')
def api_hot_concepts():
    tracker = get_hot_tracker()
    concepts = tracker.get_hot_concepts(top_n=20)
    return jsonify({
        'success': True,
        'data': concepts,
        'time': datetime.now().strftime('%H:%M:%S')
    })


@app.route('/api/signals')
def api_signals():
    strategy = get_strategy()
    try:
        signals = strategy.get_today_signals()
        if signals is not None and not signals.empty:
            data = signals.to_dict('records')
        else:
            data = []
        return jsonify({
            'success': True,
            'data': data,
            'time': datetime.now().strftime('%H:%M:%S')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'time': datetime.now().strftime('%H:%M:%S')
        })


@app.route('/api/news')
def api_news():
    tracker = get_hot_tracker()
    news = tracker.get_eastmoney_news(top_n=20)
    return jsonify({
        'success': True,
        'data': news,
        'time': datetime.now().strftime('%H:%M:%S')
    })


if __name__ == '__main__':
    from waitress import serve
    print("=" * 55)
    print("  A股热点短线助手")
    print("  运行地址: http://127.0.0.1:5000")
    print("  按 Ctrl+C 停止")
    print("=" * 55)
    serve(app, host='127.0.0.1', port=5000)
