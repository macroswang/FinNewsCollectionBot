# 实时股票数据获取模块
import requests
import json
import time
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, Optional, List
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RealTimeStockData:
    """实时股票数据获取类"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
    def get_eastmoney_realtime_data(self, stock_code: str) -> Optional[Dict]:
        """从东方财富获取实时数据"""
        try:
            # 东方财富实时数据API
            if stock_code.startswith('6'):
                market = '1'  # 上海
            else:
                market = '0'  # 深圳
                
            url = f"http://push2.eastmoney.com/api/qt/stock/get"
            params = {
                'secid': f'{market}.{stock_code}',
                'fields': 'f43,f57,f58,f169,f170,f46,f44,f51,f168,f47,f164,f163,f116,f60,f45,f52,f50,f48,f167,f117,f71,f161,f49,f530,f135,f136,f137,f138,f139,f141,f142,f144,f145,f147,f148,f140,f143,f146,f149,f55,f62,f162,f92,f173,f104,f105,f84,f85,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f107,f111,f86,f177,f78,f110,f262,f263,f264,f267,f268,f250,f251,f252,f253,f254,f255,f256,f257,f258,f266,f269,f270,f271,f273,f274,f275,f127,f199,f128,f193,f196,f194,f195,f197,f80,f280,f281,f282,f284,f285,f286,f287,f292,f293,f181,f294,f295,f279,f288'
            }
            
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('rc') == 0 and data.get('data'):
                    stock_data = data['data']
                    
                    # 解析数据字段
                    current_price = stock_data.get('f43', 0) / 100  # 当前价格
                    prev_close = stock_data.get('f60', 0) / 100    # 昨收价
                    open_price = stock_data.get('f46', 0) / 100    # 开盘价
                    high_price = stock_data.get('f44', 0) / 100    # 最高价
                    low_price = stock_data.get('f45', 0) / 100     # 最低价
                    volume = stock_data.get('f47', 0)              # 成交量
                    amount = stock_data.get('f48', 0) / 10000      # 成交额(万元)
                    
                    # 计算涨跌幅
                    if prev_close > 0:
                        price_change = ((current_price - prev_close) / prev_close) * 100
                    else:
                        price_change = 0
                    
                    return {
                        "current_price": round(current_price, 2),
                        "prev_close": round(prev_close, 2),
                        "open_price": round(open_price, 2),
                        "high_price": round(high_price, 2),
                        "low_price": round(low_price, 2),
                        "price_change": round(price_change, 2),
                        "volume": volume,
                        "amount": round(amount, 2),
                        "data_source": "东方财富",
                        "update_time": datetime.now().strftime("%H:%M:%S")
                    }
                    
        except Exception as e:
            logger.error(f"东方财富数据获取失败 {stock_code}: {e}")
            
        return None
    
    def get_sina_realtime_data(self, stock_code: str) -> Optional[Dict]:
        """从新浪财经获取实时数据"""
        try:
            # 新浪财经实时数据API
            if stock_code.startswith('6'):
                sina_code = f"sh{stock_code}"
            else:
                sina_code = f"sz{stock_code}"
                
            url = f"http://hq.sinajs.cn/list={sina_code}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                text = response.text
                # 解析新浪数据格式：var hq_str_sh601318="中国平安,82.50,82.51,82.45,82.80,82.20,82.45,82.46,1234567890,123456789,100,82.45,200,82.44,300,82.43,400,82.42,500,82.41,100,82.46,200,82.47,300,82.48,400,82.49,500,82.50,2023-12-01,15:00:00,00,D|0|0";
                if 'var hq_str_' in text and '=' in text:
                    data_part = text.split('=')[1].strip('"').split(',')
                    if len(data_part) > 30:
                        stock_name = data_part[0]
                        open_price = float(data_part[1])
                        prev_close = float(data_part[2])
                        current_price = float(data_part[3])
                        high_price = float(data_part[4])
                        low_price = float(data_part[5])
                        volume = int(data_part[8])
                        amount = float(data_part[9]) / 10000  # 转换为万元
                        
                        # 计算涨跌幅
                        if prev_close > 0:
                            price_change = ((current_price - prev_close) / prev_close) * 100
                        else:
                            price_change = 0
                        
                        return {
                            "current_price": round(current_price, 2),
                            "prev_close": round(prev_close, 2),
                            "open_price": round(open_price, 2),
                            "high_price": round(high_price, 2),
                            "low_price": round(low_price, 2),
                            "price_change": round(price_change, 2),
                            "volume": volume,
                            "amount": round(amount, 2),
                            "data_source": "新浪财经",
                            "update_time": datetime.now().strftime("%H:%M:%S")
                        }
                        
        except Exception as e:
            logger.error(f"新浪财经数据获取失败 {stock_code}: {e}")
            
        return None
    
    def get_tencent_realtime_data(self, stock_code: str) -> Optional[Dict]:
        """从腾讯财经获取实时数据"""
        try:
            # 腾讯财经实时数据API
            if stock_code.startswith('6'):
                qq_code = f"sh{stock_code}"
            else:
                qq_code = f"sz{stock_code}"
                
            url = f"http://qt.gtimg.cn/q={qq_code}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                text = response.text
                # 解析腾讯数据格式：v_sz000001="51~平安银行~000001~12.34~12.35~12.36~1234567~123456~1111111~12.34~100~12.33~200~12.32~300~12.31~400~12.30~500~12.35~100~12.36~200~12.37~300~12.38~400~12.39~500~20231201~15:00:00~00~";
                if 'v_' in text and '=' in text:
                    data_part = text.split('=')[1].strip('"').split('~')
                    if len(data_part) > 30:
                        stock_name = data_part[1]
                        current_price = float(data_part[3])
                        prev_close = float(data_part[4])
                        open_price = float(data_part[5])
                        volume = int(data_part[6])
                        amount = float(data_part[37]) / 10000  # 转换为万元
                        
                        # 计算涨跌幅
                        if prev_close > 0:
                            price_change = ((current_price - prev_close) / prev_close) * 100
                        else:
                            price_change = 0
                        
                        return {
                            "current_price": round(current_price, 2),
                            "prev_close": round(prev_close, 2),
                            "open_price": round(open_price, 2),
                            "price_change": round(price_change, 2),
                            "volume": volume,
                            "amount": round(amount, 2),
                            "data_source": "腾讯财经",
                            "update_time": datetime.now().strftime("%H:%M:%S")
                        }
                        
        except Exception as e:
            logger.error(f"腾讯财经数据获取失败 {stock_code}: {e}")
            
        return None
    
    def get_realtime_data_multi_source(self, stock_code: str) -> Optional[Dict]:
        """多数据源获取实时数据，优先选择最快响应的数据源"""
        data_sources = [
            ("东方财富", self.get_eastmoney_realtime_data),
            ("新浪财经", self.get_sina_realtime_data),
            ("腾讯财经", self.get_tencent_realtime_data)
        ]
        
        for source_name, data_func in data_sources:
            try:
                logger.info(f"正在从{source_name}获取{stock_code}数据...")
                data = data_func(stock_code)
                if data and data.get("current_price", 0) > 0:
                    logger.info(f"✅ 从{source_name}成功获取{stock_code}数据: ¥{data['current_price']}")
                    return data
            except Exception as e:
                logger.warning(f"⚠️ {source_name}获取{stock_code}数据失败: {e}")
                continue
        
        logger.error(f"❌ 所有数据源都无法获取{stock_code}的实时数据")
        return None
    
    def get_batch_realtime_data(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """批量获取多只股票的实时数据"""
        results = {}
        
        for stock_code in stock_codes:
            try:
                data = self.get_realtime_data_multi_source(stock_code)
                if data:
                    results[stock_code] = data
                else:
                    results[stock_code] = {"error": "数据获取失败"}
                    
                # 添加延迟避免请求过于频繁
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"批量获取{stock_code}数据失败: {e}")
                results[stock_code] = {"error": str(e)}
        
        return results

# 使用示例
if __name__ == "__main__":
    # 测试实时数据获取
    stock_data = RealTimeStockData()
    
    # 测试单只股票
    test_stocks = ["000001", "600036", "300750"]  # 平安银行、招商银行、宁德时代
    
    print("🧪 测试实时股票数据获取...")
    for stock_code in test_stocks:
        print(f"\n📊 获取 {stock_code} 实时数据:")
        data = stock_data.get_realtime_data_multi_source(stock_code)
        if data:
            print(f"  当前价格: ¥{data['current_price']}")
            print(f"  涨跌幅: {data['price_change']}%")
            print(f"  成交量: {data['volume']}")
            print(f"  数据源: {data['data_source']}")
            print(f"  更新时间: {data['update_time']}")
        else:
            print("  ❌ 数据获取失败")
    
    # 测试批量获取
    print(f"\n📦 批量获取 {len(test_stocks)} 只股票数据:")
    batch_data = stock_data.get_batch_realtime_data(test_stocks)
    for code, data in batch_data.items():
        if "error" not in data:
            print(f"  {code}: ¥{data['current_price']} ({data['price_change']}%) - {data['data_source']}")
        else:
            print(f"  {code}: {data['error']}") 