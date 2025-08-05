#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from eastmoney_api import eastmoney_api

def test_eastmoney_api():
    """测试东方财富API"""
    print("=== 测试东方财富API ===")
    
    # 测试股票
    test_stocks = ["002747", "000933", "000001", "000002"]
    
    for stock_code in test_stocks:
        print(f"\n--- 测试股票 {stock_code} ---")
        
        # 测试获取股票信息
        print("1. 获取股票基本信息:")
        stock_info = eastmoney_api.get_stock_info(stock_code)
        if stock_info:
            print(f"   股票名称: {stock_info.get('name', 'N/A')}")
            print(f"   当前价格: ¥{stock_info.get('current_price', 0):.2f}")
            print(f"   涨跌幅: {stock_info.get('price_change_pct', 0):.2f}%")
            print(f"   成交量: {stock_info.get('volume', 0):,.0f}")
            print(f"   市值: {stock_info.get('market_cap', 0)/100000000:.1f}亿")
            print(f"   市盈率: {stock_info.get('pe_ratio', 'N/A')}")
        else:
            print("   获取失败")
        
        # 测试ST检查
        print("2. ST股票检查:")
        is_st = eastmoney_api.check_st_stock(stock_code)
        print(f"   结果: {'是ST股票' if is_st else '正常股票'}")
        
        # 测试退市检查
        print("3. 退市检查:")
        is_delisted = eastmoney_api.check_delisted_stock(stock_code)
        print(f"   结果: {'已退市' if is_delisted else '正常交易'}")
        
        # 测试历史数据
        print("4. 历史数据:")
        history = eastmoney_api.get_stock_history(stock_code, days=5)
        if history:
            print(f"   获取到 {len(history)} 条历史数据")
            latest = history[-1]
            print(f"   最新日期: {latest['date']}")
            print(f"   最新收盘: ¥{latest['close']:.2f}")
        else:
            print("   获取失败")
    
    # 测试市场指数
    print("\n--- 测试市场指数 ---")
    indices = eastmoney_api.get_market_indices()
    for name, value in indices.items():
        print(f"{name}: {value}")

if __name__ == "__main__":
    test_eastmoney_api() 