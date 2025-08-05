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
    
    def is_trading_time(self):
        """判断当前是否为A股交易时间"""
        now = datetime.now()
        
        # 判断是否为工作日
        if now.weekday() >= 5:  # 周六、周日
            return False
        
        # 判断是否为交易时间
        # 上午：9:30-11:30
        # 下午：13:00-15:00
        current_time = now.time()
        morning_start = datetime.strptime('09:30:00', '%H:%M:%S').time()
        morning_end = datetime.strptime('11:30:00', '%H:%M:%S').time()
        afternoon_start = datetime.strptime('13:00:00', '%H:%M:%S').time()
        afternoon_end = datetime.strptime('15:00:00', '%H:%M:%S').time()
        
        return (morning_start <= current_time <= morning_end) or (afternoon_start <= current_time <= afternoon_end)
    
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
                
                # 获取前一日收盘价
                prev_close = stock_data.get('f18', 0) / 100 if stock_data.get('f18', 0) > 0 else 0
                
                # 处理价格数据（东方财富的价格数据需要除以100）
                current_price_raw = stock_data.get('f2', 0) / 100 if stock_data.get('f2', 0) > 0 else 0
                price_change = stock_data.get('f4', 0) / 100
                price_change_pct = stock_data.get('f3', 0) / 100
                
                # 在非交易时间，如果当前价格为0，使用前一日收盘价
                if current_price_raw == 0 and prev_close > 0:
                    current_price = prev_close
                    # 获取前一个交易日的涨跌幅
                    prev_day_change = self._get_prev_trading_day_change(stock_code)
                    if prev_day_change is not None:
                        price_change = prev_day_change['price_change']
                        price_change_pct = prev_day_change['price_change_pct']
                    else:
                        # 如果无法获取前一日数据，使用0
                        price_change = 0
                        price_change_pct = 0
                else:
                    current_price = current_price_raw
                
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
                    'prev_close': prev_close,
                    'is_trading_time': self.is_trading_time(),
                }
            else:
                print(f"❌ 获取{stock_code}基本信息失败")
                return None
                
        except Exception as e:
            print(f"❌ 获取{stock_code}基本信息异常: {e}")
            return None
    
    def _get_prev_trading_day_change(self, stock_code):
        """获取前一个交易日的涨跌幅数据"""
        try:
            # 获取最近2天的历史数据
            history_data = self.get_stock_history(stock_code, days=2)
            if history_data and len(history_data) >= 2:
                # 获取前一个交易日的收盘价和前一日的收盘价
                prev_close = history_data[-1]['close']  # 前一个交易日
                prev_prev_close = history_data[-2]['close']  # 前前一个交易日
                
                # 计算前一个交易日的涨跌幅
                price_change = prev_close - prev_prev_close
                price_change_pct = (price_change / prev_prev_close) * 100 if prev_prev_close > 0 else 0
                
                return {
                    'price_change': round(price_change, 2),
                    'price_change_pct': round(price_change_pct, 2)
                }
            return None
        except Exception as e:
            print(f"❌ 获取{stock_code}前一日涨跌幅异常: {e}")
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