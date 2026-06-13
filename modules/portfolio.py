
"""持仓管理模块"""
import os, json, requests

PORTFOLIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.json")

def load_portfolio():
    """读取持仓"""
    if not os.path.exists(PORTFOLIO_FILE):
        return []
    with open(PORTFOLIO_FILE) as f:
        return json.load(f)

def save_portfolio(holdings):
    """保存持仓"""
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(holdings, f, ensure_ascii=False, indent=2)

def fetch_prices(holdings):
    """获取当前价格"""
    if not holdings:
        return []
    codes = [h["code"] for h in holdings]
    secids = []
    for c in codes:
        if c.startswith(("6","9")):
            secids.append("1." + c)
        else:
            secids.append("0." + c)
    try:
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        params = {
            "fltt": "2", "secids": ",".join(secids),
            "fields": "f12,f14,f2,f3",
            "_": 0,
        }
        resp = requests.get(url, params=params, timeout=10,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.eastmoney.com/"})
        data = resp.json()
        prices = {}
        if data.get("data") and data["data"].get("diff"):
            for item in data["data"]["diff"]:
                code = str(item.get("f12", ""))
                prices[code] = {
                    "name": str(item.get("f14", "")),
                    "price": float(item.get("f2", 0)),
                    "change_pct": float(item.get("f3", 0)),
                }
        # Map prices to holdings
        results = []
        for h in holdings:
            code = h["code"]
            info = prices.get(code, {})
            buy_price = float(h["buy_price"])
            qty = int(h.get("quantity", h.get("qty", 0)))
            current_price = info.get("price", 0)
            cost = buy_price * qty
            current_value = current_price * qty
            pl = current_value - cost
            pl_pct = (current_price - buy_price) / buy_price * 100 if buy_price > 0 else 0
            results.append({
                "code": code,
                "name": info.get("name", code),
                "buy_price": buy_price,
                "quantity": qty,
                "current_price": current_price,
                "change_pct": info.get("change_pct", 0),
                "cost": round(cost, 2),
                "current_value": round(current_value, 2),
                "pl": round(pl, 2),
                "pl_pct": round(pl_pct, 2),
            })
        return results
    except Exception as e:
        print(f"[portfolio] 获取持仓价格失败: {e}")
        return []
