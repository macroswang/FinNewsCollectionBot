#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import time
from datetime import datetime, timedelta

class EastMoneyAPI:
    """东方财富API接口"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://quote.eastmoney.com/',
            'Accept': 'application/json, text/plain, */*',
        })
    
    def get_stock_info(self, stock_code):
        """获取股票基本信息"""
        try:
            if stock_code.startswith('6'):
                market = '1'
                full_code = f"1.{stock_code}"
            else:
                market = '0'
                full_code = f"0.{stock_code}"
            
            url = "http://push2.eastmoney.com/api/qt/stock/get"
            params = {
                'secid': f"{market}.{stock_code}",
                'fields': 'f57,f58,f162,f167,f127,f116,f117,f168,f169,f170,f46,f44,f51,f2,f3,f4,f5,f6,f15,f16,f17,f18,f45',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
                'fltt': '2',
                'invt': '2',
                '_': int(time.time() * 1000)
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('rc') == 0 and data.get('data'):
                stock_data = data['data']
                
                # 处理价格数据（东方财富的价格数据需要除以100）
                current_price = stock_data.get('f2', 0) / 100 if stock_data.get('f2', 0) > 0 else 0
                price_change = stock_data.get('f4', 0) / 100
                price_change_pct = stock_data.get('f3', 0) / 100
                
                # 处理市值数据（使用f45字段，总市值，单位：万元）
                market_cap_raw = stock_data.get('f45', 0)
                if isinstance(market_cap_raw, str):
                    try:
                        market_cap_raw = float(market_cap_raw)
                    except:
                        market_cap_raw = 0
                
                # 转换为元（万元 * 10000）
                market_cap = market_cap_raw * 10000 if market_cap_raw > 0 else 0
                
                return {
                    'name': stock_data.get('f58', ''),
                    'current_price': current_price,
                    'price_change': price_change,
                    'price_change_pct': price_change_pct,
                    'volume': stock_data.get('f5', 0),
                    'turnover': stock_data.get('f6', 0),
                    'market_cap': market_cap,
                    'pe_ratio': stock_data.get('f162', 0) / 100 if stock_data.get('f162', 0) > 0 else 'N/A',
                    'high': stock_data.get('f15', 0) / 100 if stock_data.get('f15', 0) > 0 else 0,
                    'low': stock_data.get('f16', 0) / 100 if stock_data.get('f16', 0) > 0 else 0,
                    'open': stock_data.get('f17', 0) / 100 if stock_data.get('f17', 0) > 0 else 0,
                    'prev_close': stock_data.get('f18', 0) / 100 if stock_data.get('f18', 0) > 0 else 0,
                }
            else:
                print(f"❌ 获取{stock_code}基本信息失败")
                return None
                
        except Exception as e:
            print(f"❌ 获取{stock_code}基本信息异常: {e}")
            return None
    
    def get_stock_history(self, stock_code, days=60):
        """获取股票历史数据"""
        try:
            if stock_code.startswith('6'):
                market = '1'
            else:
                market = '0'
            
            url = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
            params = {
                'secid': f"{market}.{stock_code}",
                'fields1': 'f1,f2,f3,f4,f5,f6',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
                'klt': '101',
                'fqt': '1',
                'beg': '0',
                'end': '20500101',
                'smplmt': str(days),
                'lmt': str(days),
                '_': int(time.time() * 1000)
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('rc') == 0 and data.get('data') and data['data'].get('klines'):
                klines = data['data']['klines']
                history_data = []
                
                for line in klines:
                    parts = line.split(',')
                    if len(parts) >= 7:
                        history_data.append({
                            'date': parts[0],
                            'open': float(parts[1]),
                            'close': float(parts[2]),
                            'high': float(parts[3]),
                            'low': float(parts[4]),
                            'volume': float(parts[5]),
                            'turnover': float(parts[6])
                        })
                
                return history_data
            else:
                print(f"❌ 获取{stock_code}历史数据失败")
                return None
                
        except Exception as e:
            print(f"❌ 获取{stock_code}历史数据异常: {e}")
            return None
    
    def check_st_stock(self, stock_code):
        """检查是否为ST股票"""
        try:
            stock_info = self.get_stock_info(stock_code)
            if stock_info and stock_info.get('name'):
                stock_name = stock_info['name']
                if 'ST' in stock_name.upper() or '*ST' in stock_name.upper():
                    print(f"❌ {stock_code} 为ST股票: {stock_name}")
                    return True
            return False
        except Exception as e:
            print(f"❌ 检查{stock_code} ST状态异常: {e}")
            return False
    
    def check_delisted_stock(self, stock_code):
        """检查是否为退市股票"""
        try:
            stock_info = self.get_stock_info(stock_code)
            if not stock_info:
                print(f"❌ {stock_code} 无法获取数据，可能已退市")
                return True
            
            # 检查是否有交易数据（非交易时间成交量可能为0，但历史数据应该存在）
            if stock_info.get('volume', 0) == 0:
                # 检查历史数据来判断是否真的退市
                history = self.get_stock_history(stock_code, days=5)
                if not history:
                    print(f"❌ {stock_code} 无历史数据，可能已退市")
                    return True
                else:
                    # 有历史数据但当前无成交量，可能是非交易时间
                    print(f"⚠️ {stock_code} 当前无成交量，可能是非交易时间")
                    return False
            
            return False
        except Exception as e:
            print(f"❌ 检查{stock_code}退市状态异常: {e}")
            return False
    
    def get_market_indices(self):
        """获取主要指数数据"""
        try:
            indices = {
                "上证指数": "000001",
                "深证成指": "399001", 
                "创业板指": "399006"
            }
            
            market_data = {}
            for name, code in indices.items():
                try:
                    stock_info = self.get_stock_info(code)
                    if stock_info:
                        current_price = stock_info.get('current_price', 0)
                        # 确保current_price是数字类型
                        if isinstance(current_price, (int, float)) and current_price > 0:
                            price_change_pct = stock_info.get('price_change_pct', 0)
                            emoji = "📈" if price_change_pct > 0 else "📉" if price_change_pct < 0 else "➡️"
                            market_data[name] = f"{emoji} {current_price:.2f} ({price_change_pct:+.2f}%)"
                        else:
                            market_data[name] = "📊 数据获取中"
                    else:
                        market_data[name] = "📊 数据获取中"
                except Exception as e:
                    print(f"❌ 获取{code}指数数据异常: {e}")
                    market_data[name] = "❌ 数据获取失败"
            
            return market_data
        except Exception as e:
            print(f"❌ 获取市场指数异常: {e}")
            return {"市场数据": "❌ 获取失败"}

# 创建全局实例
eastmoney_api = EastMoneyAPI() 