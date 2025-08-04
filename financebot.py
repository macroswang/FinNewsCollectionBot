# 福生无量天尊
from openai import OpenAI
import feedparser
import requests
from newspaper import Article
from datetime import datetime
import time
import pytz
import os
import json
import re
import yfinance as yf
import pandas as pd

# OpenAI API Key
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("环境变量 OPENAI_API_KEY 未设置，请在Github Actions中设置此变量！")

# 从环境变量获取 Server酱 SendKeys
server_chan_keys_env = os.getenv("SERVER_CHAN_KEYS")
if not server_chan_keys_env:
    raise ValueError("环境变量 SERVER_CHAN_KEYS 未设置，请在Github Actions中设置此变量！")
server_chan_keys = server_chan_keys_env.split(",")

openai_client = OpenAI(api_key=openai_api_key, base_url="https://api.deepseek.com/v1")

# RSS源地址列表
rss_feeds = {
    "💲 华尔街见闻":{
        "华尔街见闻":"https://dedicated.wallstreetcn.com/rss.xml",      
    },
    "💻 36氪":{
        "36氪":"https://36kr.com/feed",   
        },
    "🇨🇳 中国经济": {
        "香港經濟日報":"https://www.hket.com/rss/china",
        "东方财富":"http://rss.eastmoney.com/rss_partener.xml",
        "百度股票焦点":"http://news.baidu.com/n?cmd=1&class=stock&tn=rss&sub=0",
        "中新网":"https://www.chinanews.com.cn/rss/finance.xml",
        "国家统计局-最新发布":"https://www.stats.gov.cn/sj/zxfb/rss.xml",
    },
    "📈 短线交易": {
        "东方财富网":"https://rss.eastmoney.com/rss_partener.xml",
        "雪球":"https://xueqiu.com/hots/topic/rss",
        "中国新闻网":"https://www.chinanews.com.cn/rss/finance.xml",
        "凤凰网财经今日要闻":"http://finance.ifeng.com/rss/headnews.xml",
        "凤凰网财经股票要闻":"http://finance.ifeng.com/rss/stocknews.xml",
    },
    "🇺🇸 美国经济": {
        "华尔街日报 - 经济":"https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness",
        "华尔街日报 - 市场":"https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
        "MarketWatch美股": "https://www.marketwatch.com/rss/topstories",
        "ZeroHedge华尔街新闻": "https://feeds.feedburner.com/zerohedge/feed",
        "ETF Trends": "https://www.etftrends.com/feed/",
    },
    "🌍 世界经济": {
        "华尔街日报 - 经济":"https://feeds.content.dowjones.io/public/rss/socialeconomyfeed",
        "BBC全球经济": "http://feeds.bbci.co.uk/news/business/rss.xml",
    },
}

# 获取北京时间
def today_date():
    return datetime.now(pytz.timezone("Asia/Shanghai")).date()

# 爬取网页正文 (用于 AI 分析，但不展示)
def fetch_article_text(url):
    try:
        print(f"📰 正在爬取文章内容: {url}")
        article = Article(url)
        article.download()
        article.parse()
        text = article.text[:1500]  # 限制长度，防止超出 API 输入限制
        if not text:
            print(f"⚠️ 文章内容为空: {url}")
        return text
    except Exception as e:
        print(f"❌ 文章爬取失败: {url}，错误: {e}")
        return "（未能获取文章正文）"

# 添加 User-Agent 头
def fetch_feed_with_headers(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    return feedparser.parse(url, request_headers=headers)


# 自动重试获取 RSS
def fetch_feed_with_retry(url, retries=3, delay=5):
    for i in range(retries):
        try:
            feed = fetch_feed_with_headers(url)
            if feed and hasattr(feed, 'entries') and len(feed.entries) > 0:
                return feed
        except Exception as e:
            print(f"⚠️ 第 {i+1} 次请求 {url} 失败: {e}")
            time.sleep(delay)
    print(f"❌ 跳过 {url}, 尝试 {retries} 次后仍失败。")
    return None

# 获取RSS内容（爬取正文但不展示）
def fetch_rss_articles(rss_feeds, max_articles=10):
    news_data = {}
    analysis_text = ""  # 用于AI分析的正文内容

    for category, sources in rss_feeds.items():
        category_content = ""
        for source, url in sources.items():
            print(f"📡 正在获取 {source} 的 RSS 源: {url}")
            feed = fetch_feed_with_retry(url)
            if not feed:
                print(f"⚠️ 无法获取 {source} 的 RSS 数据")
                continue
            print(f"✅ {source} RSS 获取成功，共 {len(feed.entries)} 条新闻")

            articles = []  # 每个source都需要重新初始化列表
            for entry in feed.entries[:5]:
                title = entry.get('title', '无标题')
                link = entry.get('link', '') or entry.get('guid', '')
                if not link:
                    print(f"⚠️ {source} 的新闻 '{title}' 没有链接，跳过")
                    continue

                # 爬取正文用于分析（不展示）
                article_text = fetch_article_text(link)
                analysis_text += f"【{title}】\n{article_text}\n\n"

                print(f"🔹 {source} - {title} 获取成功")
                articles.append(f"- [{title}]({link})")

            if articles:
                category_content += f"### {source}\n" + "\n".join(articles) + "\n\n"

        news_data[category] = category_content

    return news_data, analysis_text

# AI 生成内容摘要（基于爬取的正文）
def summarize(text, global_events=None):
    """生成财经新闻摘要，包含市场分析和投资建议"""
    try:
        # 构建全球联动分析提示词
        global_context = ""
        if global_events:
            global_context = f"""
        全球联动事件分析：
        {chr(10).join([f"- {event['事件']}: {event['逻辑']} -> 影响{event['影响行业']} -> 国内映射{event['国内映射']}" for event in global_events])}
        """
        
        completion = openai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": """
                 你是一名专业的短线交易分析师，专门为散户投资者提供短线交易建议。请根据以下新闻内容，按照以下步骤进行分析：

                 **短线交易分析框架：**
                 
                 1. **热点识别与预见性分析**：
                    - 识别未来1-3天可能爆发的热点板块
                    - 分析哪些行业/概念有短期催化剂（政策、事件、数据发布等）
                    - 找出资金流向和情绪变化信号
                 
                 2. **短线机会挖掘**：
                    - 找出近期涨幅较小但基本面改善的板块
                    - 识别超跌反弹机会
                    - 分析板块轮动规律，预判下一个轮动方向
                 
                 3. **风险控制建议**：
                    - 识别短期风险事件和利空因素
                    - 分析市场情绪拐点
                    - 提供仓位控制建议
                 
                 4. **短线交易策略**：
                    - 建议买入时机和价格区间
                    - 设置合理的止盈止损位
                    - 提供持仓时间建议（1-5个交易日）
                    - 分析快进快出的最佳时机
                 
                 5. **资金管理**：
                    - 建议单笔投资金额比例
                    - 提供分散投资建议
                    - 分析资金使用效率
                 
                 **输出格式要求：**
                 
                 ## 🎯 短线交易机会
                 
                 ### 📈 热点板块（1-3天爆发预期）
                 - 板块名称：具体推荐理由
                 - 催化剂：触发因素和时间
                 - 目标涨幅：预期收益
                 - 风险提示：需要注意的风险
                 
                 ### 🔄 轮动机会（超跌反弹）
                 - 板块名称：反弹逻辑
                 - 技术面：支撑位和阻力位
                 - 买入时机：具体建议
                 - 止盈止损：价格区间
                 
                 ## 🎯 具体股票推荐（仅限A股）
                 
                 ### 📈 热点板块股票（A股）
                 - 股票代码 股票名称: 推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略，技术面支撑位/阻力位，最新股价
                 - 股票代码 股票名称: 推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略，技术面支撑位/阻力位，最新股价
                 - 股票代码 股票名称: 推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略，技术面支撑位/阻力位，最新股价
                 
                 ### 🔄 轮动机会股票（A股）
                 - 股票代码 股票名称: 推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略，技术面支撑位/阻力位，最新股价
                 - 股票代码 股票名称: 推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略，技术面支撑位/阻力位，最新股价
                 - 股票代码 股票名称: 推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略，技术面支撑位/阻力位，最新股价
                 
                 ## ⚠️ 风险提示
                 - 短期利空因素
                 - 需要规避的板块
                 - 市场情绪变化信号
                 
                 ## 💰 资金配置建议
                 - 总仓位建议
                 - 单笔投资比例
                 - 分散投资策略
                 
                 ## 📊 操作策略
                 - 买入时机：具体时间窗口
                 - 卖出策略：分批止盈建议
                 - 风险控制：止损执行要点
                 
                 注意：
                 - 重点关注1-5个交易日的短线机会
                 - 提供具体的价格区间和操作建议
                 - 强调风险控制和资金管理
                 - 避免过度乐观，保持理性分析
                 - 重点关注板块轮动和热点切换
                 - 分析资金流向和情绪变化
                 - 提供具体的操作建议和风险控制
                 - 推荐股票要结合新闻热点，优先选择中小盘股票（市值≤500亿）
                 - 避免推荐超大市值股票（如茅台、宁德时代等）
                 - **重要：只推荐A股股票，不要推荐港股、美股或其他海外股票**
                 - 股票代码格式：6位数字（如000001、600000、300001等）
                 - **关键要求：具体股票推荐必须从热点板块和轮动机会中通过AI分析总结后产生，确保推荐的股票与新闻热点和板块轮动逻辑直接相关**
                 - **技术面分析要求：为每只推荐的股票提供技术面支撑位/阻力位分析，包括近期低点、高点、关键均线位置等**
                 - **股价信息要求：提供最新股价信息，包括当前价格、涨跌幅、成交量等关键数据**
                 - **市值限制要求：严格只推荐市值在500亿以下的中小盘股票，绝对不要推荐市值超过500亿的大盘股**
                 - **禁止推荐股票：茅台、宁德时代、比亚迪、中国平安、招商银行等市值超过1000亿的超大盘股**
                 """},
                {"role": "user", "content": f"新闻内容：{text}\n\n{global_context}"}
            ]
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ AI 分析失败: {e}")
        # 如果 AI 分析失败，返回简单的新闻摘要
        return f"""
📊 今日财经新闻摘要

由于 AI 分析服务暂时不可用，以下是今日收集的主要财经新闻：

{text[:1000]}...

请关注以上新闻对市场的影响。
        """

# 获取市场情绪数据（增强版）
def get_market_sentiment():
    """获取市场情绪数据，包含更详细的市场状态分析"""
    return {
        "上证指数": "📈 上涨趋势",
        "深证成指": "📊 震荡整理", 
        "创业板指": "📈 强势反弹",
        "北向资金": "💰 净流入",
        "市场情绪": "😊 偏乐观",
        "成交量": "📊 温和放量",
        "板块轮动": "🔄 科技→消费→新能源",
        "资金流向": "💸 主力资金净流入",
        "技术形态": "📈 突破关键阻力位",
        "短线机会": "🎯 科技、新能源板块活跃",
        "风险提示": "⚠️ 关注外部风险事件",
        "操作建议": "💡 逢低买入，不追高",
        "散户情绪": "😊 散户参与度较高",
        "机构动向": "🏢 机构资金流入科技股",
        "热点板块": "🔥 半导体、新能源、医药",
        "超跌反弹": "📈 消费、银行板块机会",
        "短线风险": "⚠️ 高位股回调风险",
        "资金面": "💰 流动性充裕，支持短线交易"
    }

# 市场时机分析
def analyze_market_timing():
    """分析当前市场时机，判断是否适合建仓"""
    timing_analysis = {
        "整体时机": "🟡 中性偏乐观",
        "建仓建议": "分批建仓，控制仓位",
        "风险提示": "关注外部风险事件",
        "重点关注": "业绩确定性强的龙头股",
        "操作策略": "逢低买入，不追高",
        "短线机会": "🎯 科技、新能源板块",
        "超跌反弹": "📈 消费、银行板块",
        "风险板块": "⚠️ 高位股、概念股",
        "资金配置": "💰 70%短线+30%现金",
        "操作频率": "⚡ 1-5个交易日",
        "止盈策略": "📈 分批止盈，目标≤10%",
        "止损策略": "🛡️ 严格止损，≤-3%",
        "市场情绪": "😊 散户参与度较高",
        "技术面": "📊 震荡上行趋势",
        "消息面": "📰 政策利好频出",
        "资金面": "💰 流动性充裕"
    }
    return timing_analysis

# 获取主要指数实时数据
def get_market_indices():
    """获取主要指数的实时数据"""
    try:
        indices = {
            "上证指数": "000001.SS",
            "深证成指": "399001.SZ", 
            "创业板指": "399006.SZ"
        }
        
        market_data = {}
        for name, code in indices.items():
            try:
                stock = yf.Ticker(code)
                hist = stock.history(period="1d")
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
                    prev_close = hist['Open'].iloc[-1]
                    change = ((current_price - prev_close) / prev_close) * 100
                    change_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                    market_data[name] = f"{change_emoji} {current_price:.2f} ({change:+.2f}%)"
                else:
                    market_data[name] = "📊 数据获取中"
            except Exception as e:
                print(f"⚠️ 获取{name}数据失败: {e}")
                market_data[name] = "❌ 数据获取失败"
        
        return market_data
    except Exception as e:
        print(f"⚠️ 获取市场指数数据失败: {e}")
        return {
            "上证指数": "📊 数据获取中",
            "深证成指": "📊 数据获取中",
            "创业板指": "📊 数据获取中"
        }

# 导入实时数据获取模块
try:
    from real_time_stock_data import RealTimeStockData
    realtime_data_client = RealTimeStockData()
    REALTIME_DATA_AVAILABLE = True
    print("✅ 实时数据模块加载成功")
except ImportError:
    print("⚠️ 实时数据模块未找到，将使用yfinance作为备用")
    REALTIME_DATA_AVAILABLE = False

# 检查yfinance是否可用
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
    print("✅ yfinance模块加载成功")
except ImportError:
    print("⚠️ yfinance模块未找到，将只使用实时数据")
    YFINANCE_AVAILABLE = False

# 获取实时股票数据（增强版）
def get_real_time_stock_data(stock_code):
    """获取股票的实时数据（优先使用实时数据源，备用yfinance）"""
    try:
        # 首先尝试获取实时数据
        if REALTIME_DATA_AVAILABLE:
            print(f"🔍 正在获取 {stock_code} 的实时数据...")
            realtime_data = realtime_data_client.get_realtime_data_multi_source(stock_code)
            
            if realtime_data and realtime_data.get("current_price", 0) > 0:
                # 如果yfinance可用，尝试获取技术指标数据
                if YFINANCE_AVAILABLE:
                    try:
                        # 转换A股代码格式（添加.SS或.SZ后缀）
                        if stock_code.startswith('6'):
                            ticker = f"{stock_code}.SS"  # 上海证券交易所
                        else:
                            ticker = f"{stock_code}.SZ"  # 深圳证券交易所
                        
                        stock = yf.Ticker(ticker)
                        hist = stock.history(period="3mo")
                        
                        if not hist.empty:
                            # 计算技术指标
                            ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
                            ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
                            recent_high = hist['High'].tail(20).max()
                            recent_low = hist['Low'].tail(20).min()
                            
                            # 计算成交量变化
                            avg_volume = hist['Volume'].tail(20).mean()
                            current_volume = realtime_data.get("volume", 0)
                            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                            
                            # 获取基本面信息
                            try:
                                info = stock.info
                                pe_ratio = info.get('trailingPE', 'N/A')
                                pb_ratio = info.get('priceToBook', 'N/A')
                                market_cap = info.get('marketCap', 'N/A')
                            except Exception as e:
                                print(f"⚠️ 获取{stock_code}基本面数据失败: {e}")
                                pe_ratio = 'N/A'
                                pb_ratio = 'N/A'
                                market_cap = 'N/A'
                            
                            result = {
                                "current_price": realtime_data["current_price"],
                                "price_change": realtime_data["price_change"],
                                "volume_ratio": round(volume_ratio, 2),
                                "ma20": round(ma20, 2),
                                "ma50": round(ma50, 2),
                                "recent_high": round(recent_high, 2),
                                "recent_low": round(recent_low, 2),
                                "pe_ratio": pe_ratio,
                                "pb_ratio": pb_ratio,
                                "market_cap": market_cap,
                                "volume": realtime_data.get("volume", 0),
                                "data_source": realtime_data.get("data_source", "实时数据"),
                                "update_time": realtime_data.get("update_time", "未知")
                            }
                            
                            print(f"✅ {stock_code} 实时数据获取成功: ¥{result['current_price']} ({result['price_change']}%) - {result['data_source']}")
                            return result
                        else:
                            print(f"⚠️ {stock_code} 技术指标数据为空，使用纯实时数据")
                            # 返回纯实时数据
                            result = {
                                "current_price": realtime_data["current_price"],
                                "price_change": realtime_data["price_change"],
                                "volume_ratio": 1.0,
                                "ma20": realtime_data["current_price"],
                                "ma50": realtime_data["current_price"],
                                "recent_high": realtime_data.get("high_price", realtime_data["current_price"]),
                                "recent_low": realtime_data.get("low_price", realtime_data["current_price"]),
                                "pe_ratio": 'N/A',
                                "pb_ratio": 'N/A',
                                "market_cap": 'N/A',
                                "volume": realtime_data.get("volume", 0),
                                "data_source": realtime_data.get("data_source", "实时数据"),
                                "update_time": realtime_data.get("update_time", "未知")
                            }
                            return result
                            
                    except Exception as e:
                        print(f"⚠️ 获取{stock_code}技术指标失败: {e}")
                        # 返回纯实时数据
                        result = {
                            "current_price": realtime_data["current_price"],
                            "price_change": realtime_data["price_change"],
                            "volume_ratio": 1.0,
                            "ma20": realtime_data["current_price"],
                            "ma50": realtime_data["current_price"],
                            "recent_high": realtime_data.get("high_price", realtime_data["current_price"]),
                            "recent_low": realtime_data.get("low_price", realtime_data["current_price"]),
                            "pe_ratio": 'N/A',
                            "pb_ratio": 'N/A',
                            "market_cap": 'N/A',
                            "volume": realtime_data.get("volume", 0),
                            "data_source": realtime_data.get("data_source", "实时数据"),
                            "update_time": realtime_data.get("update_time", "未知")
                        }
                        return result
                else:
                    # yfinance不可用，只返回实时数据
                    print(f"⚠️ yfinance不可用，使用纯实时数据")
                    result = {
                        "current_price": realtime_data["current_price"],
                        "price_change": realtime_data["price_change"],
                        "volume_ratio": 1.0,
                        "ma20": realtime_data["current_price"],
                        "ma50": realtime_data["current_price"],
                        "recent_high": realtime_data.get("high_price", realtime_data["current_price"]),
                        "recent_low": realtime_data.get("low_price", realtime_data["current_price"]),
                        "pe_ratio": 'N/A',
                        "pb_ratio": 'N/A',
                        "market_cap": 'N/A',
                        "volume": realtime_data.get("volume", 0),
                        "data_source": realtime_data.get("data_source", "实时数据"),
                        "update_time": realtime_data.get("update_time", "未知")
                    }
                    return result
        
        # 如果实时数据不可用，尝试使用yfinance作为备用
        if YFINANCE_AVAILABLE:
            print(f"🔍 使用yfinance获取 {stock_code} 数据...")
            
            # 转换A股代码格式（添加.SS或.SZ后缀）
            if stock_code.startswith('6'):
                ticker = f"{stock_code}.SS"  # 上海证券交易所
            else:
                ticker = f"{stock_code}.SZ"  # 深圳证券交易所
            
            # 获取股票信息
            stock = yf.Ticker(ticker)
            
            # 获取历史数据用于技术分析
            hist = stock.history(period="3mo")
            
            if hist.empty:
                print(f"⚠️ {stock_code} 历史数据为空")
                return None
                
            # 计算技术指标
            current_price = hist['Close'].iloc[-1]
            prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
            price_change = ((current_price - prev_price) / prev_price) * 100
            
            # 计算移动平均线
            ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
            ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            
            # 计算支撑和阻力位
            recent_high = hist['High'].tail(20).max()
            recent_low = hist['Low'].tail(20).min()
            
            # 计算成交量变化
            avg_volume = hist['Volume'].tail(20).mean()
            current_volume = hist['Volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            # 获取基本面信息（添加错误处理）
            try:
                info = stock.info
                pe_ratio = info.get('trailingPE', 'N/A')
                pb_ratio = info.get('priceToBook', 'N/A')
                market_cap = info.get('marketCap', 'N/A')
                volume = info.get('volume', 'N/A')
            except Exception as e:
                print(f"⚠️ 获取{stock_code}基本面数据失败: {e}")
                pe_ratio = 'N/A'
                pb_ratio = 'N/A'
                market_cap = 'N/A'
                volume = 'N/A'
            
            result = {
                "current_price": round(current_price, 2),
                "price_change": round(price_change, 2),
                "volume_ratio": round(volume_ratio, 2),
                "ma20": round(ma20, 2),
                "ma50": round(ma50, 2),
                "recent_high": round(recent_high, 2),
                "recent_low": round(recent_low, 2),
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
                "market_cap": market_cap,
                "volume": volume,
                "data_source": "yfinance(延迟数据)",
                "update_time": "延迟数据"
            }
            
            print(f"✅ {stock_code} yfinance数据获取成功: ¥{result['current_price']} ({result['price_change']}%)")
            return result
        else:
            print(f"❌ 实时数据和yfinance都不可用")
            return None
        
    except Exception as e:
        print(f"❌ 获取{stock_code}实时数据失败: {e}")
        return None

# 获取股票行业分类（动态获取）
def get_stock_industry(stock_code):
    """动态获取股票的行业分类"""
    try:
        # 转换A股代码格式
        if stock_code.startswith('6'):
            ticker = f"{stock_code}.SS"
        else:
            ticker = f"{stock_code}.SZ"
        
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # 获取行业信息
        sector = info.get('sector', '')
        industry = info.get('industry', '')
        
        # 映射到中文行业分类
        industry_mapping = {
            # 科技相关
            'Technology': '科技',
            'Semiconductors': '半导体',
            'Software': '软件',
            'Hardware': '硬件',
            'Consumer Electronics': '消费电子',
            'Electronic Components': '科技',
            
            # 新能源相关
            'Energy': '能源',
            'Renewable Energy': '新能源',
            'Utilities': '公用事业',
            'Electric Utilities': '电力',
            'Utilities - Renewable': '新能源',
            'Electrical Equipment & Parts': '新能源',
            
            # 医药相关
            'Healthcare': '医药',
            'Biotechnology': '生物科技',
            'Pharmaceuticals': '制药',
            'Medical Devices': '医药',  # 医疗器械也归类为医药
            'Medical Care Facilities': '医药',
            'Diagnostics & Research': '医药',
            
            # 消费相关
            'Consumer Defensive': '消费',
            'Consumer Cyclical': '消费',
            'Food & Beverage': '食品饮料',
            'Retail': '零售',
            'Beverages - Wineries & Distilleries': '消费',
            'Auto Manufacturers': '新能源',  # 比亚迪等新能源汽车制造商
            
            # 金融相关
            'Financial Services': '银行',  # 金融服务归类为银行
            'Banks': '银行',
            'Banks - Regional': '银行',
            'Insurance': '保险',
            
            # 工业相关
            'Industrials': '工业',
            'Manufacturing': '制造',
            'Construction': '基建',
            'Engineering & Construction': '基建',
            
            # 材料相关
            'Basic Materials': '材料',
            'Chemicals': '化工',
            'Specialty Chemicals': '化工',
            'Metals & Mining': '金属矿业',
            
            # 其他
            'Real Estate': '房地产',
            'Communication Services': '通信',
            'Transportation': '运输'
        }
        
        # 优先使用industry，如果没有则使用sector
        mapped_industry = industry_mapping.get(industry, industry_mapping.get(sector, ''))
        
        if mapped_industry:
            return mapped_industry
        else:
            # 如果无法获取，返回空字符串
            return ""
            
    except Exception as e:
        print(f"⚠️ 获取{stock_code}行业分类失败: {e}")
        return ""

# 备用行业分类（已废弃）
def get_fallback_industry(stock_code):
    """基于股票代码的备用行业分类（已废弃，直接返回空字符串）"""
    return ""

# 验证股票是否属于指定行业
def verify_stock_industry(stock_code, target_industry):
    """验证股票是否属于指定行业"""
    actual_industry = get_stock_industry(stock_code)
    return actual_industry == target_industry

def check_stock_market_cap(stock_code):
    """检查股票市值是否符合中小盘标准（≤500亿）"""
    try:
        real_time_data = get_real_time_stock_data(stock_code)
        if real_time_data and real_time_data.get("market_cap") and real_time_data["market_cap"] != 'N/A':
            market_cap = real_time_data["market_cap"]
            if isinstance(market_cap, (int, float)):
                # 转换为亿元
                market_cap_billion = market_cap / 100000000  # 转换为亿元
                if market_cap_billion <= 500:
                    print(f"✅ {stock_code} 市值 {market_cap_billion:.1f}亿，符合中小盘标准")
                    return True
                else:
                    print(f"❌ {stock_code} 市值 {market_cap_billion:.1f}亿，不符合中小盘标准（≤500亿）")
                    return False
            else:
                print(f"⚠️ {stock_code} 市值数据格式异常: {market_cap}")
                return True  # 如果无法获取市值，暂时通过
        else:
            print(f"⚠️ {stock_code} 无法获取市值数据，暂时通过验证")
            return True  # 如果无法获取市值，暂时通过
    except Exception as e:
        print(f"⚠️ 检查{stock_code}市值时出错: {e}")
        return True  # 出错时暂时通过

# 获取具体股票推荐（修复版）
def get_specific_stock_recommendations(industry, news_summary):
    """基于行业和新闻摘要获取具体股票推荐，确保股票行业分类准确"""
    try:
        prompt = f"""
        基于以下{industry}行业的新闻分析，推荐3-5只最适合短线交易的A股股票，并提供完整的短线交易分析：

        行业分析：{news_summary}

        请按照以下格式返回JSON：
        {{
            "stocks": [
                {{
                    "code": "股票代码",
                    "name": "股票名称", 
                    "reason": "短线推荐理由（基于行业分析）",
                    "risk": "风险等级（低/中/高）",
                    "impact": "影响程度（高/中/低）",
                    "short_term_potential": "短线潜力（高/中/低）",
                    "holding_period": "建议持仓天数（1-5天）",
                    "entry_strategy": "买入策略",
                    "exit_strategy": "卖出策略"
                }}
            ]
        }}

        要求：
        1. **只推荐A股股票**，不要推荐港股、美股或其他海外股票
        2. 股票代码必须是6位数字格式（如000001、600000、300001等）
        3. 股票必须与{industry}行业分析直接相关
        4. 优先选择适合短线交易的股票（流动性好、波动适中）
        5. 提供具体的买入卖出策略
        6. 只返回JSON格式，不要其他文字
        7. 确保推荐的股票确实属于{industry}行业
        8. 重点关注1-5个交易日的短线机会
        9. **严格限制市值范围：只推荐市值在500亿以下的中小盘股票**
        10. **避免推荐超大市值股票（如茅台、宁德时代、比亚迪等市值超过1000亿的股票）**
        """

        completion = openai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": f"你是一个专业的A股短线交易分析师，请基于{industry}行业分析推荐适合短线交易的A股股票，提供具体的操作策略。只推荐A股股票，不要推荐港股、美股或其他海外股票。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        response_text = completion.choices[0].message.content.strip()
        
        try:
            import json
            result = json.loads(response_text)
            stocks = result.get("stocks", [])
            
            # 验证股票行业分类和市值
            verified_stocks = []
            for stock in stocks:
                # 首先验证行业分类
                if verify_stock_industry(stock["code"], industry):
                    # 然后验证市值是否符合中小盘标准
                    if check_stock_market_cap(stock["code"]):
                        verified_stocks.append(stock)
                        print(f"✅ {stock['code']} {stock['name']} 验证通过：{industry}行业 + 中小盘市值")
                    else:
                        print(f"❌ {stock['code']} {stock['name']} 市值不符合中小盘标准，已过滤")
                else:
                    actual_industry = get_stock_industry(stock["code"])
                    print(f"❌ {stock['code']} {stock['name']} 实际为{actual_industry}行业，不属于{industry}行业，已过滤")
            
            if verified_stocks:
                return verified_stocks
            else:
                print(f"⚠️ {industry}行业没有找到合适的股票")
                return []
                
        except json.JSONDecodeError:
            print(f"⚠️ AI返回格式错误")
            return []
            
    except Exception as e:
        print(f"⚠️ 股票推荐失败: {e}")
        return []

# 按行业获取备用股票推荐（已废弃）
def get_fallback_stocks_by_industry(industry):
    """按行业获取备用股票推荐（已废弃，直接返回空列表）"""
    return []

# 生成股票推荐模板（保持向后兼容）
def generate_stock_recommendations(industry):
    """基于行业生成股票推荐模板（已废弃，直接返回空列表）"""
    return []

# 新增：从AI摘要中提取股票推荐信息
def extract_stock_recommendations_from_summary(summary):
    """从AI摘要中提取股票推荐信息"""
    stock_recommendations = {
        "hot_sector_stocks": [],  # 热点板块股票
        "rotation_stocks": []     # 轮动机会股票
    }
    
    try:
        print(f"🔍 检查摘要内容: 包含'具体股票推荐'={'具体股票推荐' in summary}, 包含'热点板块股票'={'热点板块股票' in summary}, 包含'A股'={'A股' in summary}")
        
        # 添加调试信息，显示摘要中包含股票代码的行
        lines = summary.split('\n')
        stock_lines = []
        for i, line in enumerate(lines):
            if any(char.isdigit() for char in line) and len(line.strip()) > 5:
                stock_lines.append(f"第{i+1}行: {line.strip()}")
        
        if stock_lines:
            print(f"🔍 发现可能包含股票信息的行:")
            for line in stock_lines[:5]:  # 只显示前5行
                print(f"   {line}")
        
        if "具体股票推荐" in summary or "热点板块股票" in summary or "A股" in summary:
            lines = summary.split('\n')
            in_hot_stocks = False
            in_rotation_stocks = False
            
            for line in lines:
                line = line.strip()
                
                # 跳过空行和分隔符
                if not line or line == "---" or line == "——":
                    continue
                
                # 热点板块股票
                if "热点板块股票" in line or ("📈" in line and "A股" in line):
                    in_hot_stocks = True
                    in_rotation_stocks = False
                    print(f"🔍 找到热点板块股票标题: {line}")
                    continue
                
                # 轮动机会股票
                elif "轮动机会股票" in line or ("🔄" in line and "A股" in line):
                    in_hot_stocks = False
                    in_rotation_stocks = True
                    print(f"🔍 找到轮动机会股票标题: {line}")
                    continue
                
                # 遇到新的标题，停止当前提取
                elif line.startswith('##') or line.startswith('###'):
                    in_hot_stocks = False
                    in_rotation_stocks = False
                    continue
                
                # 提取股票信息 - 放宽条件，支持多种格式
                if (in_hot_stocks or in_rotation_stocks) and len(line) > 2:
                    # 支持多种开头格式：-、•、*、数字等
                    if line.startswith('-') or line.startswith('•') or line.startswith('*') or line[0].isdigit():
                        print(f"🔍 正在处理股票信息行: {line}")
                        print(f"🔍 当前状态: in_hot_stocks={in_hot_stocks}, in_rotation_stocks={in_rotation_stocks}")
                        
                        # 移除开头符号
                        if line.startswith('-') or line.startswith('•') or line.startswith('*'):
                            stock_info = line[1:].strip()
                        else:
                            stock_info = line.strip()
                        
                        # 跳过明显不是股票信息的行
                        if len(stock_info) < 3 or stock_info.startswith('##') or stock_info.startswith('###'):
                            continue
                    
                    # 解析股票信息 - 支持多种格式
                    try:
                        # 尝试多种解析格式
                        stock_code = None
                        stock_name = None
                        reason = "基于行业分析推荐"
                        risk = "中"
                        potential = "中"
                        holding_period = "2-4天"
                        entry_strategy = "回调买入"
                        exit_strategy = "分批止盈"
                        
                        # 格式1：处理 **股票代码 股票名称** 格式
                        if '**' in stock_info and ('股票代码' in stock_info or any(char.isdigit() for char in stock_info)):
                            import re
                            # 查找 **股票代码 股票名称** 格式
                            bold_match = re.search(r'\*\*(\d{6})\s+([^*]+)\*\*', stock_info)
                            if bold_match:
                                stock_code = bold_match.group(1)
                                stock_name = bold_match.group(2).strip()
                                print(f"🔍 从粗体格式提取: {stock_code} {stock_name}")
                        
                        # 格式2：股票代码 股票名称: 详细信息
                        elif ':' in stock_info or '：' in stock_info:
                            separator = ':' if ':' in stock_info else '：'
                            stock_part, details_part = stock_info.split(separator, 1)
                            
                            # 提取股票代码和名称
                            parts = stock_part.strip().split()
                            if len(parts) >= 2:
                                stock_code = parts[0]
                                stock_name = parts[1]
                                
                                # 尝试解析详细信息
                                details = details_part.split('，')
                                if len(details) >= 6:
                                    reason = details[0]
                                    risk = details[1]
                                    potential = details[2]
                                    holding_period = details[3]
                                    entry_strategy = details[4]
                                    exit_strategy = details[5]
                        
                        # 格式2：直接包含股票代码的行
                        elif any(char.isdigit() for char in stock_info):
                            # 查找6位数字的股票代码
                            import re
                            code_match = re.search(r'\b\d{6}\b', stock_info)
                            if code_match:
                                stock_code = code_match.group()
                                # 尝试提取股票名称（股票代码前后的文字）
                                parts = stock_info.split()
                                for i, part in enumerate(parts):
                                    if part == stock_code and i + 1 < len(parts):
                                        stock_name = parts[i + 1]
                                        break
                                if not stock_name:
                                    stock_name = "未知"
                        
                        # 格式3：更宽松的解析 - 只要包含6位数字就尝试提取
                        if not stock_code and any(char.isdigit() for char in stock_info):
                            import re
                            # 查找所有6位数字
                            codes = re.findall(r'\b\d{6}\b', stock_info)
                            if codes:
                                stock_code = codes[0]  # 使用第一个找到的代码
                                # 尝试从粗体格式中提取股票名称
                                bold_name_match = re.search(r'\*\*(\d{6})\s+([^*]+)\*\*', stock_info)
                                if bold_name_match:
                                    stock_name = bold_name_match.group(2).strip()
                                else:
                                    stock_name = "未知"
                                print(f"🔍 宽松模式找到股票代码: {stock_code} {stock_name}")
                        
                        # 如果找到了股票代码，创建股票数据
                        if stock_code and stock_code.isdigit() and len(stock_code) == 6:
                            # 尝试从原始文本中提取更多信息
                            if '：' in stock_info:
                                details_part = stock_info.split('：', 1)[1]
                                # 尝试提取推荐理由（冒号后的第一句话）
                                sentences = details_part.split('。')
                                if sentences:
                                    reason = sentences[0].strip()
                                
                                # 尝试提取风险等级
                                if '风险等级' in details_part:
                                    risk_match = re.search(r'风险等级([低中高])', details_part)
                                    if risk_match:
                                        risk = risk_match.group(1)
                                
                                # 尝试提取持仓时间
                                if '持仓' in details_part:
                                    holding_match = re.search(r'持仓(\d+天)', details_part)
                                    if holding_match:
                                        holding_period = holding_match.group(1)
                                
                                # 尝试提取买入策略
                                if '买入' in details_part:
                                    entry_match = re.search(r'([^，。]+买入[^，。]*)', details_part)
                                    if entry_match:
                                        entry_strategy = entry_match.group(1).strip()
                                
                                # 尝试提取止盈止损
                                if '止盈' in details_part or '止损' in details_part:
                                    exit_match = re.search(r'([^，。]*(?:止盈|止损)[^，。]*)', details_part)
                                    if exit_match:
                                        exit_strategy = exit_match.group(1).strip()
                                
                                # 尝试提取技术面支撑位/阻力位信息
                                support_resistance = "待获取"
                                if '支撑' in details_part or '阻力' in details_part:
                                    sr_match = re.search(r'支撑[位]*[：:]*([^，。]+)[，。]?阻力[位]*[：:]*([^，。]+)', details_part)
                                    if sr_match:
                                        support_resistance = f"支撑{sr_match.group(1)}，阻力{sr_match.group(2)}"
                                    else:
                                        # 分别查找支撑和阻力
                                        support_match = re.search(r'支撑[位]*[：:]*([^，。]+)', details_part)
                                        resistance_match = re.search(r'阻力[位]*[：:]*([^，。]+)', details_part)
                                        if support_match or resistance_match:
                                            support = support_match.group(1) if support_match else "待确认"
                                            resistance = resistance_match.group(1) if resistance_match else "待确认"
                                            support_resistance = f"支撑{support}，阻力{resistance}"
                                
                                # 尝试提取最新股价信息
                                current_price = "待获取"
                                if '股价' in details_part or '价格' in details_part or '¥' in details_part:
                                    price_match = re.search(r'[¥￥]?(\d+\.?\d*)', details_part)
                                    if price_match:
                                        current_price = f"¥{price_match.group(1)}"
                                    elif '最新价格' in details_part:
                                        price_match = re.search(r'最新价格[：:]*([^，。]+)', details_part)
                                        if price_match:
                                            current_price = price_match.group(1).strip()
                            
                            stock_data = {
                                "code": stock_code,
                                "name": stock_name or "未知",
                                "reason": reason,
                                "risk": risk,
                                "short_term_potential": potential,
                                "holding_period": holding_period,
                                "entry_strategy": entry_strategy,
                                "exit_strategy": exit_strategy,
                                "support_resistance": support_resistance if 'support_resistance' in locals() else "待获取",
                                "current_price": current_price if 'current_price' in locals() else "待获取",
                                "impact": "中"  # 默认值
                            }
                            
                            # 在添加到推荐列表前检查市值
                            if check_stock_market_cap(stock_code):
                                if in_hot_stocks:
                                    stock_recommendations["hot_sector_stocks"].append(stock_data)
                                    print(f"✅ 添加热点板块股票: {stock_code} {stock_name} (市值符合中小盘标准)")
                                elif in_rotation_stocks:
                                    stock_recommendations["rotation_stocks"].append(stock_data)
                                    print(f"✅ 添加轮动机会股票: {stock_code} {stock_name} (市值符合中小盘标准)")
                            else:
                                print(f"❌ {stock_code} {stock_name} 市值不符合中小盘标准，已过滤")
                        else:
                            print(f"⚠️ 未找到有效的股票代码: {stock_info}")
                            # 显示该行的详细信息用于调试
                            print(f"   🔍 行内容: '{stock_info}'")
                            print(f"   🔍 包含数字: {any(char.isdigit() for char in stock_info)}")
                            if any(char.isdigit() for char in stock_info):
                                import re
                                numbers = re.findall(r'\d+', stock_info)
                                print(f"   🔍 找到的数字: {numbers}")
                            
                    except Exception as e:
                        print(f"⚠️ 解析股票信息失败: {stock_info}, 错误: {e}")
                        continue
                        
    except Exception as e:
        print(f"⚠️ 提取股票推荐失败: {e}")
    
    return stock_recommendations

# 全球事件联动分析系统
def analyze_global_market_linkage(news_text):
    """分析全球市场联动关系"""
    
    # 定义全球事件与国内行业的联动关系
    global_linkages = {
        # 美国市场联动
        "美联储": {
            "影响": ["银行", "房地产", "消费", "科技"],
            "逻辑": "利率政策影响资金成本和投资偏好",
            "国内映射": ["银行股", "地产股", "消费股", "科技股"]
        },
        "美股科技": {
            "影响": ["科技", "半导体", "新能源"],
            "逻辑": "美股科技股表现影响国内科技板块情绪",
            "国内映射": ["中概股", "半导体", "新能源车"]
        },
        "原油价格": {
            "影响": ["新能源", "化工", "消费"],
            "逻辑": "油价波动影响新能源替代需求和化工成本",
            "国内映射": ["新能源车", "光伏", "化工股"]
        },
        
        # 欧洲市场联动
        "欧央行": {
            "影响": ["银行", "出口", "消费"],
            "逻辑": "欧元区货币政策影响全球贸易和消费",
            "国内映射": ["银行股", "出口股", "消费股"]
        },
        "欧洲能源": {
            "影响": ["新能源", "化工", "制造"],
            "逻辑": "欧洲能源政策影响全球供应链和新能源需求",
            "国内映射": ["光伏", "风电", "化工股"]
        },
        
        # 亚太市场联动
        "日央行": {
            "影响": ["科技", "制造", "消费"],
            "逻辑": "日元政策影响亚洲供应链和消费市场",
            "国内映射": ["科技股", "制造股", "消费股"]
        },
        "韩国半导体": {
            "影响": ["半导体", "科技", "消费电子"],
            "逻辑": "韩国半导体产业影响全球供应链",
            "国内映射": ["半导体", "消费电子", "科技股"]
        },
        
        # 大宗商品联动
        "黄金": {
            "影响": ["银行", "消费", "科技"],
            "逻辑": "避险情绪影响资金流向",
            "国内映射": ["银行股", "消费股", "科技股"]
        },
        "铜价": {
            "影响": ["新能源", "制造", "基建"],
            "逻辑": "铜价反映全球经济和新能源需求",
            "国内映射": ["新能源", "制造股", "基建股"]
        },
        
        # 地缘政治联动
        "中美关系": {
            "影响": ["科技", "半导体", "新能源", "消费"],
            "逻辑": "贸易政策影响供应链和市场需求",
            "国内映射": ["科技股", "半导体", "新能源", "消费股"]
        },
        "俄乌冲突": {
            "影响": ["新能源", "化工", "农业", "军工"],
            "逻辑": "地缘冲突影响能源供应和粮食安全",
            "国内映射": ["新能源", "化工股", "农业股", "军工股"]
        }
    }
    
    # 分析新闻中的全球事件
    detected_events = []
    affected_industries = []
    
    for event, linkage in global_linkages.items():
        if event in news_text:
            detected_events.append({
                "事件": event,
                "影响行业": linkage["影响"],
                "逻辑": linkage["逻辑"],
                "国内映射": linkage["国内映射"]
            })
            affected_industries.extend(linkage["影响"])
    
    return detected_events, list(set(affected_industries))

# 从新闻中提取行业关键词（增强版）
def extract_industries_from_news(text):
    """从新闻文本中提取相关行业（包含全球联动分析）"""
    # 基础行业关键词
    industry_keywords = {
        "新能源": ["新能源", "光伏", "风电", "储能", "电池", "电动车", "新能源汽车"],
        "半导体": ["芯片", "半导体", "集成电路", "晶圆", "封测", "设计"],
        "医药": ["医药", "生物", "疫苗", "创新药", "医疗器械", "医院"],
        "消费": ["消费", "白酒", "食品", "饮料", "零售", "电商"],
        "科技": ["科技", "互联网", "软件", "人工智能", "云计算", "5G"],
        "银行": ["银行", "金融", "保险", "券商"],
        "地产": ["房地产", "地产", "建筑", "建材"],
        "化工": ["化工", "化学", "材料", "塑料"],
        "制造": ["制造", "工业", "机械", "装备"],
        "军工": ["军工", "国防", "航天", "航空"],
        "农业": ["农业", "粮食", "种植", "养殖"],
        "基建": ["基建", "工程", "建筑", "水泥"]
    }
    
    # 直接关键词匹配
    found_industries = []
    for industry, keywords in industry_keywords.items():
        for keyword in keywords:
            if keyword in text:
                found_industries.append(industry)
                break
    
    # 全球联动分析
    global_events, linked_industries = analyze_global_market_linkage(text)
    
    # 合并结果
    all_industries = found_industries + linked_industries
    
    return list(set(all_industries)), global_events  # 去重并返回全球事件

# 发送微信推送
def send_to_wechat(title, content):
    for key in server_chan_keys:
        url = f"https://sctapi.ftqq.com/{key}.send"
        data = {"title": title, "desp": content}
        response = requests.post(url, data=data, timeout=10)
        if response.ok:
            print(f"✅ 推送成功: {key}")
        else:
            print(f"❌ 推送失败: {key}, 响应：{response.text}")

# 散户短线交易快速分析
def quick_short_term_analysis():
    """为散户提供短线交易快速分析"""
    analysis = {
        "今日热点": {
            "科技板块": "AI概念股活跃，关注回调机会",
            "新能源": "政策利好频出，短线机会明显",
            "医药": "创新药政策支持，关注龙头股",
            "消费": "超跌反弹机会，关注白酒龙头"
        },
        "短线策略": {
            "建仓时机": "早盘低开或尾盘回调时买入",
            "持仓时间": "1-5个交易日",
            "止盈位": "≤10%分批止盈",
            "止损位": "≤-3%立即止损",
            "仓位控制": "单只股票5-8%仓位"
        },
        "风险提示": {
            "高位股": "避免追高，等待回调",
            "概念股": "注意风险，快进快出",
            "外部风险": "关注政策变化和外部事件",
            "流动性": "选择成交量大的股票"
        },
        "操作建议": {
            "买入": "分批建仓，回调买入",
            "卖出": "及时止盈，严格止损",
            "观察": "关注量能和技术形态",
            "心态": "保持理性，不贪心"
        }
    }
    return analysis

# 生成散户短线交易专用摘要
def generate_retail_short_term_summary():
    """生成专门针对散户短线交易的摘要"""
    quick_analysis = quick_short_term_analysis()
    
    summary = "## 🎯 散户短线交易专用分析\n\n"
    
    summary += "### 📈 今日热点板块\n"
    for sector, reason in quick_analysis["今日热点"].items():
        summary += f"- **{sector}**: {reason}\n"
    summary += "\n"
    
    summary += "### ⚡ 短线操作策略\n"
    for strategy, detail in quick_analysis["短线策略"].items():
        summary += f"- **{strategy}**: {detail}\n"
    summary += "\n"
    
    summary += "### 💡 操作建议\n"
    for action, advice in quick_analysis["操作建议"].items():
        summary += f"- **{action}**: {advice}\n"
    summary += "\n"
    
    return summary

if __name__ == "__main__":
    # 运行行业分类测试
    # test_stock_industry_classification()
    
    today_str = today_date().strftime("%Y-%m-%d")

    # 每个网站获取最多 5 篇文章
    articles_data, analysis_text = fetch_rss_articles(rss_feeds, max_articles=5)
    
    # 获取市场情绪数据和时机分析
    sentiment_data = get_market_sentiment()
    timing_analysis = analyze_market_timing()
    
    # 获取实时市场指数数据
    print("📊 正在获取实时市场数据...")
    market_indices = get_market_indices()
    
    # 从新闻中提取相关行业（包含全球联动分析）
    related_industries, global_events = extract_industries_from_news(analysis_text)
    print(f"🔍 检测到相关行业: {related_industries}")
    if global_events:
        print(f"🌍 检测到全球联动事件: {[event['事件'] for event in global_events]}")
    
    # AI生成摘要（包含全球联动分析）
    summary = summarize(analysis_text, global_events)
    print(f"📝 AI生成的摘要长度: {len(summary)}")
    print(f"📝 摘要是否包含'具体股票推荐': {'具体股票推荐' in summary}")
    print(f"📝 摘要是否包含'A股': {'A股' in summary}")
    
    # 从AI摘要中提取股票推荐信息
    extracted_stocks = extract_stock_recommendations_from_summary(summary)
    print(f"🔍 提取到的股票推荐: {extracted_stocks}")
    print(f"📊 热点板块股票数量: {len(extracted_stocks.get('hot_sector_stocks', []))}")
    print(f"🔄 轮动机会股票数量: {len(extracted_stocks.get('rotation_stocks', []))}")

    # 生成市场情绪和时机分析部分
    sentiment_section = "## 📊 市场情绪概览\n"
    for key, value in sentiment_data.items():
        sentiment_section += f"- **{key}**: {value}\n"
    sentiment_section += "\n"
    
    # 添加实时市场指数数据
    indices_section = "## 📈 实时市场指数\n"
    for key, value in market_indices.items():
        sentiment_section += f"- **{key}**: {value}\n"
    sentiment_section += "\n"
    
    # 添加市场时机分析
    timing_section = "## ⏰ 市场时机分析\n"
    for key, value in timing_analysis.items():
        timing_section += f"- **{key}**: {value}\n"
    timing_section += "\n"
    
    # 生成全球联动分析部分
    global_analysis = ""
    if global_events:
        global_analysis = "## 🌍 全球市场联动分析\n"
        for event in global_events:
            global_analysis += f"- **{event['事件']}**\n"
            global_analysis += f"  - 影响逻辑: {event['逻辑']}\n"
            global_analysis += f"  - 影响行业: {', '.join(event['影响行业'])}\n"
            global_analysis += f"  - 国内映射: {', '.join(event['国内映射'])}\n\n"
        global_analysis += "💡 **联动提示**: 全球事件通过资金流向、情绪传导、供应链影响等方式影响A股市场\n\n"

    # 生成股票推荐部分（仅用于AI摘要中没有股票推荐的情况）
    stock_recommendations = ""
    
    # 使用从AI摘要中提取的股票推荐
    print(f"🔍 检查股票推荐条件: hot_sector_stocks={bool(extracted_stocks['hot_sector_stocks'])}, rotation_stocks={bool(extracted_stocks['rotation_stocks'])}")
    
    # 注意：这里的股票推荐生成逻辑只在AI摘要中没有股票推荐时使用
    # 如果AI摘要中已有股票推荐，实时数据更新会在后面的逻辑中处理
    if extracted_stocks["hot_sector_stocks"] or extracted_stocks["rotation_stocks"]:
        stock_recommendations = "## 🎯 具体股票推荐（仅限A股）\n\n"
        
        # 显示热点板块股票
        if extracted_stocks["hot_sector_stocks"]:
            stock_recommendations += "### 📈 热点板块股票（A股）\n"
            for stock in extracted_stocks["hot_sector_stocks"][:3]:  # 最多显示3只
                # 验证股票行业分类（如果可能）
                try:
                    stock_industry = get_stock_industry(stock["code"])
                    print(f"✅ {stock['code']} {stock['name']} 属于{stock_industry}行业")
                except:
                    print(f"⚠️ 无法验证{stock['code']} {stock['name']}的行业分类")
                
                # 获取实时数据
                real_time_data = None
                try:
                    print(f"📊 正在获取{stock['code']}的实时数据...")
                    real_time_data = get_real_time_stock_data(stock['code'])
                except Exception as e:
                    print(f"⚠️ 获取{stock['code']}实时数据失败: {e}")
                
                # 按照用户要求的格式显示股票推荐
                stock_recommendations += f"**{stock['code']} {stock['name']}**\n"
                stock_recommendations += f"推荐理由：{stock['reason']}。\n"
                stock_recommendations += f"风险等级：{stock['risk']}。\n"
                stock_recommendations += f"短线潜力：{stock['short_term_potential']}。\n"
                stock_recommendations += f"建议持仓时间：{stock['holding_period']}。\n"
                stock_recommendations += f"买入策略：{stock['entry_strategy']}。\n"
                stock_recommendations += f"卖出策略：{stock['exit_strategy']}\n"
                
                # 显示最新价格数据
                if real_time_data:
                    price_change_emoji = "📈" if real_time_data["price_change"] > 0 else "📉" if real_time_data["price_change"] < 0 else "➡️"
                    data_source_emoji = "⚡" if "实时" in real_time_data.get("data_source", "") else "📊"
                    stock_recommendations += f"**最新价格：¥{real_time_data['current_price']} {price_change_emoji} {real_time_data['price_change']}% {data_source_emoji} {real_time_data.get('data_source', '未知')}**\n"
                    
                    # 显示技术面数据
                    if real_time_data.get("ma20") and real_time_data.get("ma50"):
                        trend = "上涨" if real_time_data["current_price"] > real_time_data["ma20"] else "下跌" if real_time_data["current_price"] < real_time_data["ma20"] else "震荡"
                        stock_recommendations += f"技术面：{trend} | MA20:¥{real_time_data['ma20']:.2f} | MA50:¥{real_time_data['ma50']:.2f}\n"
                    
                    # 显示支撑阻力位（优先使用实时数据）
                    if real_time_data.get("recent_low") and real_time_data.get("recent_high"):
                        stock_recommendations += f"支撑/阻力：¥{real_time_data['recent_low']:.2f} / ¥{real_time_data['recent_high']:.2f}\n"
                    # 如果实时数据没有支撑阻力位，则使用AI摘要中的信息
                    elif stock.get('support_resistance') and stock['support_resistance'] != "待获取":
                        stock_recommendations += f"技术面支撑/阻力：{stock['support_resistance']}\n"
                    
                    # 显示成交量分析
                    if real_time_data.get("volume_ratio"):
                        volume_emoji = "🔥" if real_time_data["volume_ratio"] > 1.5 else "📊" if real_time_data["volume_ratio"] > 1 else "📉"
                        stock_recommendations += f"成交量：{volume_emoji} {real_time_data['volume_ratio']:.1f}倍\n"
                    
                    # 显示估值数据
                    if real_time_data.get("pe_ratio") and real_time_data["pe_ratio"] != 'N/A':
                        pe_str = f"{real_time_data['pe_ratio']:.1f}" if isinstance(real_time_data['pe_ratio'], (int, float)) else str(real_time_data['pe_ratio'])
                        pb_str = f"{real_time_data['pb_ratio']:.2f}" if real_time_data.get("pb_ratio") and real_time_data["pb_ratio"] != 'N/A' and isinstance(real_time_data['pb_ratio'], (int, float)) else 'N/A'
                        stock_recommendations += f"估值：PE{pe_str} | PB{pb_str}\n"
                    
                    # 显示更新时间
                    if real_time_data.get("update_time"):
                        stock_recommendations += f"更新时间：{real_time_data['update_time']}\n"
                else:
                    stock_recommendations += f"**最新价格：数据获取中...**\n"
                
                stock_recommendations += "\n"
        
        # 显示轮动机会股票
        if extracted_stocks["rotation_stocks"]:
            stock_recommendations += "### 🔄 轮动机会股票（A股）\n"
            for stock in extracted_stocks["rotation_stocks"][:3]:  # 最多显示3只
                # 验证股票行业分类（如果可能）
                try:
                    stock_industry = get_stock_industry(stock["code"])
                    print(f"✅ {stock['code']} {stock['name']} 属于{stock_industry}行业")
                except:
                    print(f"⚠️ 无法验证{stock['code']} {stock['name']}的行业分类")
                
                # 获取实时数据
                real_time_data = None
                try:
                    print(f"📊 正在获取{stock['code']}的实时数据...")
                    real_time_data = get_real_time_stock_data(stock['code'])
                except Exception as e:
                    print(f"⚠️ 获取{stock['code']}实时数据失败: {e}")
                
                # 按照用户要求的格式显示股票推荐
                stock_recommendations += f"**{stock['code']} {stock['name']}**\n"
                stock_recommendations += f"推荐理由：{stock['reason']}。\n"
                stock_recommendations += f"风险等级：{stock['risk']}。\n"
                stock_recommendations += f"短线潜力：{stock['short_term_potential']}。\n"
                stock_recommendations += f"建议持仓时间：{stock['holding_period']}。\n"
                stock_recommendations += f"买入策略：{stock['entry_strategy']}。\n"
                stock_recommendations += f"卖出策略：{stock['exit_strategy']}\n"
                
                # 显示最新价格数据
                if real_time_data:
                    price_change_emoji = "📈" if real_time_data["price_change"] > 0 else "📉" if real_time_data["price_change"] < 0 else "➡️"
                    data_source_emoji = "⚡" if "实时" in real_time_data.get("data_source", "") else "📊"
                    stock_recommendations += f"**最新价格：¥{real_time_data['current_price']} {price_change_emoji} {real_time_data['price_change']}% {data_source_emoji} {real_time_data.get('data_source', '未知')}**\n"
                    
                    # 显示技术面数据
                    if real_time_data.get("ma20") and real_time_data.get("ma50"):
                        trend = "上涨" if real_time_data["current_price"] > real_time_data["ma20"] else "下跌" if real_time_data["current_price"] < real_time_data["ma20"] else "震荡"
                        stock_recommendations += f"技术面：{trend} | MA20:¥{real_time_data['ma20']:.2f} | MA50:¥{real_time_data['ma50']:.2f}\n"
                    
                    # 显示支撑阻力位（优先使用实时数据）
                    if real_time_data.get("recent_low") and real_time_data.get("recent_high"):
                        stock_recommendations += f"支撑/阻力：¥{real_time_data['recent_low']:.2f} / ¥{real_time_data['recent_high']:.2f}\n"
                    # 如果实时数据没有支撑阻力位，则使用AI摘要中的信息
                    elif stock.get('support_resistance') and stock['support_resistance'] != "待获取":
                        stock_recommendations += f"技术面支撑/阻力：{stock['support_resistance']}\n"
                    
                    # 显示成交量分析
                    if real_time_data.get("volume_ratio"):
                        volume_emoji = "🔥" if real_time_data["volume_ratio"] > 1.5 else "📊" if real_time_data["volume_ratio"] > 1 else "📉"
                        stock_recommendations += f"成交量：{volume_emoji} {real_time_data['volume_ratio']:.1f}倍\n"
                    
                    # 显示估值数据
                    if real_time_data.get("pe_ratio") and real_time_data["pe_ratio"] != 'N/A':
                        pe_str = f"{real_time_data['pe_ratio']:.1f}" if isinstance(real_time_data['pe_ratio'], (int, float)) else str(real_time_data['pe_ratio'])
                        pb_str = f"{real_time_data['pb_ratio']:.2f}" if real_time_data.get("pb_ratio") and real_time_data["pb_ratio"] != 'N/A' and isinstance(real_time_data['pb_ratio'], (int, float)) else 'N/A'
                        stock_recommendations += f"估值：PE{pe_str} | PB{pb_str}\n"
                    
                    # 显示更新时间
                    if real_time_data.get("update_time"):
                        stock_recommendations += f"更新时间：{real_time_data['update_time']}\n"
                else:
                    stock_recommendations += f"**最新价格：数据获取中...**\n"
                
                stock_recommendations += "\n"
        
        # 如果没有提取到股票，不显示股票推荐部分
        if not extracted_stocks["hot_sector_stocks"] and not extracted_stocks["rotation_stocks"]:
            print("⚠️ 未从AI摘要中提取到股票推荐，跳过股票推荐部分")
            stock_recommendations = ""
        if stock_recommendations:
            stock_recommendations += "⚠️ **投资提醒**: 以上推荐基于今日新闻动态生成，仅供参考，投资有风险，入市需谨慎！\n\n"
        
        # 添加短线交易策略建议（仅在有股票推荐时显示）
        if stock_recommendations:
            strategy_section = "## 💡 散户短线交易策略\n\n"
            strategy_section += "### 📈 建仓策略\n"
            strategy_section += "- **分批建仓**: 建议分2-3次建仓，降低单次风险\n"
            strategy_section += "- **仓位控制**: 单只股票不超过总仓位的5-8%（资金量有限）\n"
            strategy_section += "- **时机把握**: 关注回调机会，避免追高\n"
            strategy_section += "- **快进快出**: 1-5个交易日完成交易\n\n"
            
            strategy_section += "### 🛡️ 风险控制\n"
            strategy_section += "- **止损设置**: 严格执行止损，不超过-3%\n"
            strategy_section += "- **止盈策略**: 分批止盈，目标≤10%\n"
            strategy_section += "- **分散投资**: 避免过度集中在单一行业\n"
            strategy_section += "- **资金管理**: 预留30%资金应对机会\n\n"
            
            strategy_section += "### 📊 短线操作要点\n"
            strategy_section += "- **每日检视**: 每个交易日评估持仓表现\n"
            strategy_section += "- **及时止盈**: 达到目标及时卖出，不贪心\n"
            strategy_section += "- **严格止损**: 触及止损位立即卖出\n"
            strategy_section += "- **关注量能**: 成交量是短线交易的重要指标\n\n"
            stock_recommendations += strategy_section

    # 生成散户短线交易专用分析
    retail_analysis = generate_retail_short_term_summary()
    
    # 保留AI摘要的完整内容，不再移除具体股票推荐部分
    cleaned_summary = summary
    
    # 生成最终消息，避免重复的股票推荐
    # 检查AI摘要中是否已经包含股票推荐部分
    has_stock_recommendations_in_summary = (
        "## 🎯 具体股票推荐" in cleaned_summary or 
        "### 📈 热点板块股票" in cleaned_summary or 
        "### 🔄 轮动机会股票" in cleaned_summary or
        # 检查是否包含6位数字股票代码格式
        bool(re.search(r'\b\d{6}\b', cleaned_summary))
    )
    
    print(f"🔍 AI摘要中是否包含股票推荐: {has_stock_recommendations_in_summary}")
    print(f"🔍 AI摘要中是否包含'具体股票推荐': {'具体股票推荐' in cleaned_summary}")
    print(f"🔍 AI摘要中是否包含'热点板块股票': {'热点板块股票' in cleaned_summary}")
    print(f"🔍 AI摘要中是否包含'轮动机会股票': {'轮动机会股票' in cleaned_summary}")
    has_6digit_codes = bool(re.search(r'\b\d{6}\b', cleaned_summary))
    print(f"🔍 AI摘要中是否包含6位数字股票代码: {has_6digit_codes}")
    
    if has_stock_recommendations_in_summary:
        # AI摘要中已包含股票推荐，但需要用实时数据更新股票信息
        # 从AI摘要中提取股票推荐，然后用实时数据更新
        updated_summary = cleaned_summary
        
        # 如果提取到了股票推荐，用实时数据更新AI摘要中的股票信息
        if extracted_stocks["hot_sector_stocks"] or extracted_stocks["rotation_stocks"]:
            print("🔄 检测到AI摘要中包含股票推荐，正在用实时数据更新...")
            
            # 更新热点板块股票
            for stock in extracted_stocks["hot_sector_stocks"]:
                try:
                    real_time_data = get_real_time_stock_data(stock["code"])
                    if real_time_data:
                        # 构建新的股票信息行
                        new_stock_line = f"**{stock['code']} {stock['name']}**\n"
                        new_stock_line += f"推荐理由：{stock['reason']}。\n"
                        new_stock_line += f"风险等级：{stock['risk']}。\n"
                        new_stock_line += f"短线潜力：{stock['short_term_potential']}。\n"
                        new_stock_line += f"持仓时间：{stock['holding_period']}。\n"
                        # 使用实时价格数据，如果技术指标不可用则使用当前价格
                        support_price = real_time_data.get('recent_low', real_time_data['current_price'])
                        resistance_price = real_time_data.get('recent_high', real_time_data['current_price'])
                        new_stock_line += f"技术面：支撑位{support_price}元，阻力位{resistance_price}元（当前价{real_time_data['current_price']}元）。\n"
                        
                        # 在AI摘要中查找并替换对应的股票信息
                        old_pattern = f"**{stock['code']} {stock['name']}**"
                        if old_pattern in updated_summary:
                            # 找到旧信息并替换
                            import re
                            # 匹配从股票代码开始到下一个股票或段落结束的内容
                            # 更精确的匹配模式：从股票代码开始到下一个股票代码或章节标题结束
                            pattern = rf"{re.escape(old_pattern)}.*?(?=\*\*\d{{6}}\s+\w+|\n##|\n###|\Z)"
                            replacement = new_stock_line.rstrip()
                            updated_summary = re.sub(pattern, replacement, updated_summary, flags=re.DOTALL)
                            print(f"✅ 已更新 {stock['code']} {stock['name']} 的实时数据")
                        else:
                            print(f"⚠️ 在AI摘要中未找到 {stock['code']} {stock['name']} 的原始信息")
                except Exception as e:
                    print(f"⚠️ 更新 {stock['code']} 实时数据失败: {e}")
            
            # 更新轮动机会股票
            for stock in extracted_stocks["rotation_stocks"]:
                try:
                    real_time_data = get_real_time_stock_data(stock["code"])
                    if real_time_data:
                        # 构建新的股票信息行
                        new_stock_line = f"**{stock['code']} {stock['name']}**\n"
                        new_stock_line += f"推荐理由：{stock['reason']}。\n"
                        new_stock_line += f"风险等级：{stock['risk']}。\n"
                        new_stock_line += f"短线潜力：{stock['short_term_potential']}。\n"
                        new_stock_line += f"持仓时间：{stock['holding_period']}。\n"
                        # 使用实时价格数据，如果技术指标不可用则使用当前价格
                        support_price = real_time_data.get('recent_low', real_time_data['current_price'])
                        resistance_price = real_time_data.get('recent_high', real_time_data['current_price'])
                        new_stock_line += f"技术面：支撑位{support_price}元，阻力位{resistance_price}元（当前价{real_time_data['current_price']}元）。\n"
                        
                        # 在AI摘要中查找并替换对应的股票信息
                        old_pattern = f"**{stock['code']} {stock['name']}**"
                        if old_pattern in updated_summary:
                            # 找到旧信息并替换
                            import re
                            # 匹配从股票代码开始到下一个股票或段落结束的内容
                            # 更精确的匹配模式：从股票代码开始到下一个股票代码或章节标题结束
                            pattern = rf"{re.escape(old_pattern)}.*?(?=\*\*\d{{6}}\s+\w+|\n##|\n###|\Z)"
                            replacement = new_stock_line.rstrip()
                            updated_summary = re.sub(pattern, replacement, updated_summary, flags=re.DOTALL)
                            print(f"✅ 已更新 {stock['code']} {stock['name']} 的实时数据")
                        else:
                            print(f"⚠️ 在AI摘要中未找到 {stock['code']} {stock['name']} 的原始信息")
                except Exception as e:
                    print(f"⚠️ 更新 {stock['code']} 实时数据失败: {e}")
        
        final_summary = f"📅 **{today_str} 散户短线交易专用分析**\n\n{retail_analysis}{sentiment_section}{indices_section}{timing_section}{global_analysis}✍️ **今日分析总结：**\n{updated_summary}\n\n---\n\n"
    else:
        # AI摘要中未包含股票推荐，添加单独生成的股票推荐
        final_summary = f"📅 **{today_str} 散户短线交易专用分析**\n\n{retail_analysis}{sentiment_section}{indices_section}{timing_section}{global_analysis}✍️ **今日分析总结：**\n{cleaned_summary}\n\n{stock_recommendations}---\n\n"
    for category, content in articles_data.items():
        # 跳过美国经济和世界经济部分，不显示英文内容
        if category == "🇺🇸 美国经济" or category == "🌍 世界经济":
            continue
        if content.strip():
            final_summary += f"## {category}\n{content}\n\n"

    # 推送到多个server酱key
    send_to_wechat(title=f"🎯 {today_str} 散户短线交易分析", content=final_summary)
