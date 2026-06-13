#!/usr/bin/env python3
"""持仓编辑工具"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules.portfolio import load_portfolio, save_portfolio

def main():
    holdings = load_portfolio()
    print("持仓管理器 (最多3支)")
    print("=" * 40)
    
    while True:
        print(f"\n当前持仓: {len(holdings)}/3 支")
        for i, h in enumerate(holdings, 1):
            print(f"  {i}. {h['code']} 买入价:{h['buy_price']} 数量:{h.get('quantity',h.get('qty',0))}")
        print()
        print("1. 添加持仓")
        print("2. 删除持仓")
        print("3. 清空所有")
        print("4. 保存并退出")
        
        choice = input("\n请选择 (1-4): ").strip()
        
        if choice == "1":
            if len(holdings) >= 3:
                print("已达上限(3支)，请先删除")
                continue
            code = input("股票代码 (如 600519): ").strip()
            try:
                price = float(input("买入价格: ").strip())
                qty = int(input("买入数量(股): ").strip())
                holdings.append({"code": code, "buy_price": price, "quantity": qty})
                print(f"已添加: {code}")
            except:
                print("输入格式错误")
        
        elif choice == "2":
            if not holdings:
                print("暂无持仓")
                continue
            idx = input(f"删除第几支 (1-{len(holdings)}): ").strip()
            try:
                i = int(idx) - 1
                if 0 <= i < len(holdings):
                    removed = holdings.pop(i)
                    print(f"已删除: {removed['code']}")
            except:
                print("输入错误")
        
        elif choice == "3":
            confirm = input("确认清空所有持仓? (y/n): ").strip().lower()
            if confirm == "y":
                holdings = []
                print("已清空")
        
        elif choice == "4":
            save_portfolio(holdings)
            print(f"已保存 {len(holdings)} 支持仓")
            break

if __name__ == "__main__":
    main()
