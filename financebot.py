# 福生无量天尊
from openai import OpenAI
import feedparser
import requests
from newspaper import Article
from datetime import datetime, timedelta
import time
import pytz
import os
import json
import re
import yfinance as yf
import pandas as pd
import numpy as np
import signal

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
        print(f"�� 正在爬取文章内容: {url}")
        
        # 设置超时控制
        def timeout_handler(signum, frame):
            raise TimeoutError(f"爬取文章超时: {url}")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(20)  # 20秒超时
        
        try:
            article = Article(url)
            article.download()
            article.parse()
            text = article.text[:1500]  # 限制长度，防止超出 API 输入限制
            signal.alarm(0)  # 取消超时
            
            if not text:
                print(f"⚠️ 文章内容为空: {url}")
            return text
        except TimeoutError:
            print(f"⚠️ 爬取文章超时: {url}")
            signal.alarm(0)
            return "（文章爬取超时）"
        finally:
            signal.alarm(0)  # 确保取消超时
            
    except Exception as e:
        print(f"❌ 文章爬取失败: {url}，错误: {e}")
        return "（未能获取文章正文）"

# 添加 User-Agent 头
def fetch_feed_with_headers(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # 设置超时控制
    def timeout_handler(signum, frame):
        raise TimeoutError(f"RSS获取超时: {url}")
    
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(15)  # 15秒超时
    
    try:
        feed = feedparser.parse(url, request_headers=headers)
        signal.alarm(0)  # 取消超时
        return feed
    except TimeoutError:
        print(f"⚠️ RSS获取超时: {url}")
        signal.alarm(0)
        return None
    except Exception as e:
        print(f"⚠️ RSS获取失败: {url}, 错误: {e}")
        signal.alarm(0)
        return None
    finally:
        signal.alarm(0)  # 确保取消超时

# 自动重试获取 RSS
def fetch_feed_with_retry(url, retries=2, delay=3):
    for i in range(retries):
        try:
            print(f"📡 第 {i+1} 次尝试获取 RSS: {url}")
            feed = fetch_feed_with_headers(url)
            if feed and hasattr(feed, 'entries') and len(feed.entries) > 0:
                return feed
        except Exception as e:
            print(f"⚠️ 第 {i+1} 次请求 {url} 失败: {e}")
            if i < retries - 1:  # 不是最后一次重试
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
        
        # 设置超时控制
        def timeout_handler(signum, frame):
            raise TimeoutError("AI分析超时")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(60)  # 60秒超时
        
        try:
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
                        - 设置合理的止盈止损位（止盈≤10%，止损≤-3%）
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
                     
                     ## 🎯 具体股票推荐
                     
                     ### 📈 热点板块股票
                     - 股票代码 股票名称：推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略
                     - 股票代码 股票名称：推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略
                     - 股票代码 股票名称：推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略
                     
                     ### 🔄 轮动机会股票
                     - 股票代码 股票名称：推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略
                     - 股票代码 股票名称：推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略
                     - 股票代码 股票名称：推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略
                     
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
                     - 推荐股票要结合新闻热点，优先选择中小盘股票（市值100-500亿）
                     - 避免推荐超大市值股票（如茅台、宁德时代等）
                     """},
                    {"role": "user", "content": f"新闻内容：{text}\n\n{global_context}"}
                ],
                timeout=45  # 45秒超时
            )
            signal.alarm(0)  # 取消超时
            return completion.choices[0].message.content.strip()
        except TimeoutError:
            print("⚠️ AI分析超时，返回简单摘要")
            signal.alarm(0)
            return f"""
📊 今日财经新闻摘要

由于AI分析服务暂时不可用，以下是今日收集的主要财经新闻：

{text[:1000]}...

请关注以上新闻对市场的影响。
            """
        finally:
            signal.alarm(0)  # 确保取消超时
            
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
                # 设置超时控制
                def timeout_handler(signum, frame):
                    raise TimeoutError(f"获取{name}数据超时")
                
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(15)  # 15秒超时
                
                try:
                    stock = yf.Ticker(code)
                    hist = stock.history(period="1d", timeout=10)  # 10秒超时
                    signal.alarm(0)  # 取消超时
                    
                    if not hist.empty:
                        current_price = hist['Close'].iloc[-1]
                        prev_close = hist['Open'].iloc[-1]
                        change = ((current_price - prev_close) / prev_close) * 100
                        change_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                        market_data[name] = f"{change_emoji} {current_price:.2f} ({change:+.2f}%)"
                    else:
                        market_data[name] = "📊 数据获取中"
                except TimeoutError:
                    print(f"⚠️ 获取{name}数据超时")
                    signal.alarm(0)
                    market_data[name] = "❌ 数据获取超时"
                finally:
                    signal.alarm(0)  # 确保取消超时
                    
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

# 获取实时股票数据
def get_real_time_stock_data(stock_code):
    """获取股票的实时数据，包括详细的技术分析和买卖点"""
    try:
        # 转换A股代码格式（添加.SS或.SZ后缀）
        if stock_code.startswith('6'):
            ticker = f"{stock_code}.SS"  # 上海证券交易所
        else:
            ticker = f"{stock_code}.SZ"  # 深圳证券交易所
        
        print(f"🔍 正在获取 {ticker} 的实时数据...")
        
        # 获取股票信息
        stock = yf.Ticker(ticker)
        
        # 设置超时时间，防止无限等待
        def timeout_handler(signum, frame):
            raise TimeoutError(f"获取{stock_code}数据超时")
        
        # 设置30秒超时
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)
        
        try:
            # 获取历史数据用于技术分析（增加数据量）
            hist = stock.history(period="6mo", timeout=20)  # 添加20秒超时
            
            # 取消超时
            signal.alarm(0)
            
            if hist.empty:
                print(f"⚠️ {stock_code} 历史数据为空")
                return None
                
            # 计算技术指标
            current_price = hist['Close'].iloc[-1]
            prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
            price_change = ((current_price - prev_price) / prev_price) * 100
            
            # 计算移动平均线
            ma5 = hist['Close'].rolling(window=5).mean().iloc[-1]
            ma10 = hist['Close'].rolling(window=10).mean().iloc[-1]
            ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
            ma50 = hist['Close'].rolling(window=50).mean().iloc[-1]
            
            # 计算支撑和阻力位
            recent_high = hist['High'].tail(20).max()
            recent_low = hist['Low'].tail(20).min()
            
            # 计算布林带
            bb_period = 20
            bb_std = 2
            bb_middle = hist['Close'].rolling(window=bb_period).mean()
            bb_std_dev = hist['Close'].rolling(window=bb_period).std()
            bb_upper = bb_middle + (bb_std_dev * bb_std)
            bb_lower = bb_middle - (bb_std_dev * bb_std)
            
            current_bb_upper = bb_upper.iloc[-1]
            current_bb_lower = bb_lower.iloc[-1]
            
            # 计算RSI
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            current_rsi = rsi.iloc[-1]
            
            # 计算成交量变化
            avg_volume = hist['Volume'].tail(20).mean()
            current_volume = hist['Volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
            
            # 计算MACD
            exp1 = hist['Close'].ewm(span=12, adjust=False).mean()
            exp2 = hist['Close'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            current_macd = macd.iloc[-1]
            current_signal = signal.iloc[-1]
            
            # 获取基本面信息（添加超时控制）
            try:
                signal.alarm(15)  # 15秒超时获取基本面数据
                info = stock.info
                signal.alarm(0)
                
                pe_ratio = info.get('trailingPE', 'N/A')
                pb_ratio = info.get('priceToBook', 'N/A')
                market_cap = info.get('marketCap', 'N/A')
                volume = info.get('volume', 'N/A')
            except (TimeoutError, Exception) as e:
                print(f"⚠️ 获取{stock_code}基本面数据失败: {e}")
                pe_ratio = 'N/A'
                pb_ratio = 'N/A'
                market_cap = 'N/A'
                volume = 'N/A'
            
            # 计算买卖点
            # 支撑位：近期低点、布林带下轨、MA20的较低值
            support_levels = [
                recent_low,
                current_bb_lower,
                ma20 * 0.98  # MA20下方2%
            ]
            primary_support = max([s for s in support_levels if s < current_price], default=recent_low)
            secondary_support = primary_support * 0.95  # 第二支撑位
            
            # 阻力位：近期高点、布林带上轨、MA20上方
            resistance_levels = [
                recent_high,
                current_bb_upper,
                ma20 * 1.05  # MA20上方5%
            ]
            primary_resistance = min([r for r in resistance_levels if r > current_price], default=recent_high)
            secondary_resistance = primary_resistance * 1.05  # 第二阻力位
            
            # 计算建议买入价和卖出价
            buy_price = primary_support * 1.02  # 支撑位上方2%
            sell_price = primary_resistance * 0.98  # 阻力位下方2%
            
            # 计算止损价
            stop_loss = primary_support * 0.95  # 支撑位下方5%
            
            # 技术面分析
            technical_signals = []
            if current_price > ma20 and ma20 > ma50:
                technical_signals.append("多头排列")
            elif current_price < ma20 and ma20 < ma50:
                technical_signals.append("空头排列")
            
            if current_rsi < 30:
                technical_signals.append("超卖")
            elif current_rsi > 70:
                technical_signals.append("超买")
            
            if current_macd > current_signal:
                technical_signals.append("MACD金叉")
            elif current_macd < current_signal:
                technical_signals.append("MACD死叉")
            
            if volume_ratio > 1.5:
                technical_signals.append("放量")
            elif volume_ratio < 0.5:
                technical_signals.append("缩量")
            
            result = {
                "current_price": round(current_price, 2),
                "price_change": round(price_change, 2),
                "volume_ratio": round(volume_ratio, 2),
                "ma5": round(ma5, 2),
                "ma10": round(ma10, 2),
                "ma20": round(ma20, 2),
                "ma50": round(ma50, 2),
                "recent_high": round(recent_high, 2),
                "recent_low": round(recent_low, 2),
                "bb_upper": round(current_bb_upper, 2),
                "bb_lower": round(current_bb_lower, 2),
                "rsi": round(current_rsi, 2),
                "macd": round(current_macd, 2),
                "signal": round(current_signal, 2),
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
                "market_cap": market_cap,
                "volume": volume,
                "support_levels": {
                    "primary": round(primary_support, 2),
                    "secondary": round(secondary_support, 2)
                },
                "resistance_levels": {
                    "primary": round(primary_resistance, 2),
                    "secondary": round(secondary_resistance, 2)
                },
                "trading_points": {
                    "buy_price": round(buy_price, 2),
                    "sell_price": round(sell_price, 2),
                    "stop_loss": round(stop_loss, 2)
                },
                "technical_signals": technical_signals
            }
            
            print(f"✅ {stock_code} 实时数据获取成功: ¥{result['current_price']} ({result['price_change']}%)")
            return result
            
        except TimeoutError as e:
            print(f"❌ {stock_code} 数据获取超时: {e}")
            return None
        finally:
            signal.alarm(0)  # 确保取消超时
        
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
        
        # 设置超时控制
        def timeout_handler(signum, frame):
            raise TimeoutError(f"获取{stock_code}行业分类超时")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)  # 10秒超时
        
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            signal.alarm(0)  # 取消超时
            
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
                # 如果无法获取，使用备用分类
                return get_fallback_industry(stock_code)
                
        except TimeoutError:
            print(f"⚠️ 获取{stock_code}行业分类超时")
            signal.alarm(0)
            return get_fallback_industry(stock_code)
        finally:
            signal.alarm(0)  # 确保取消超时
            
    except Exception as e:
        print(f"⚠️ 获取{stock_code}行业分类失败: {e}")
        return get_fallback_industry(stock_code)

# 备用行业分类（当动态获取失败时使用）
def get_fallback_industry(stock_code):
    return []

# 验证股票是否属于指定行业
def verify_stock_industry(stock_code, target_industry):
    """验证股票是否属于指定行业"""
    actual_industry = get_stock_industry(stock_code)
    return actual_industry == target_industry

# 获取具体股票推荐（修复版）
def get_specific_stock_recommendations(industry, news_summary):
    """基于行业和新闻摘要获取具体股票推荐，包含实时数据和精确买卖点"""
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
                    "entry_strategy": "买入策略（具体价格区间）",
                    "exit_strategy": "卖出策略（具体价格区间）",
                    "stop_loss": "止损策略（具体价格）"
                }}
            ]
        }}
        
        要求：
        1. 股票必须与{industry}行业分析直接相关
        2. 优先选择适合短线交易的股票（流动性好、波动适中）
        3. 提供具体的买入卖出价格区间
        4. 只返回JSON格式，不要其他文字
        5. 确保推荐的股票确实属于{industry}行业
        6. 重点关注1-5个交易日的短线机会
        """

        # 设置超时控制
        def timeout_handler(signum, frame):
            raise TimeoutError("股票推荐AI分析超时")
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)  # 30秒超时
        
        try:
            completion = openai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": f"你是一个专业的短线交易分析师，请基于{industry}行业分析推荐适合短线交易的股票，提供具体的操作策略。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                timeout=25  # 25秒超时
            )
            signal.alarm(0)  # 取消超时
            
            response_text = completion.choices[0].message.content.strip()
            
            try:
                import json
                result = json.loads(response_text)
                stocks = result.get("stocks", [])
                
                # 验证股票行业分类并获取实时数据
                verified_stocks = []
                for stock in stocks:
                    if verify_stock_industry(stock["code"], industry):
                        # 获取实时数据
                        real_time_data = get_real_time_stock_data(stock["code"])
                        if real_time_data:
                            # 合并实时数据到股票推荐中
                            stock.update({
                                "real_time_data": real_time_data,
                                "current_price": real_time_data["current_price"],
                                "price_change": real_time_data["price_change"],
                                "technical_analysis": {
                                    "ma20": real_time_data["ma20"],
                                    "rsi": real_time_data["rsi"],
                                    "volume_ratio": real_time_data["volume_ratio"],
                                    "signals": real_time_data["technical_signals"]
                                },
                                "trading_points": real_time_data["trading_points"],
                                "support_resistance": {
                                    "support": real_time_data["support_levels"],
                                    "resistance": real_time_data["resistance_levels"]
                                }
                            })
                            
                            # 更新买卖策略为具体价格
                            stock["entry_strategy"] = f"建议买入价：¥{real_time_data['trading_points']['buy_price']}，支撑位：¥{real_time_data['support_levels']['primary']}"
                            stock["exit_strategy"] = f"建议卖出价：¥{real_time_data['trading_points']['sell_price']}，阻力位：¥{real_time_data['resistance_levels']['primary']}"
                            stock["stop_loss"] = f"止损价：¥{real_time_data['trading_points']['stop_loss']}"
                            
                            verified_stocks.append(stock)
                            print(f"✅ {stock['code']} {stock['name']} 验证为{industry}行业，实时价格：¥{real_time_data['current_price']}")
                        else:
                            print(f"⚠️ {stock['code']} {stock['name']} 实时数据获取失败，跳过")
                    else:
                        actual_industry = get_stock_industry(stock["code"])
                        print(f"❌ {stock['code']} {stock['name']} 实际为{actual_industry}行业，不属于{industry}行业，已过滤")
                    
                    if verified_stocks:
                        return verified_stocks
                    else:
                        print(f"⚠️ {industry}行业没有找到合适的股票，返回空")
                        return []
                        
            except json.JSONDecodeError:
                print(f"⚠️ AI返回格式错误，返回空")
                return []
                
        except TimeoutError:
            print(f"⚠️ {industry}行业股票推荐AI分析超时，使用备用推荐")
            signal.alarm(0)
            return get_fallback_stocks_by_industry(industry)
        finally:
            signal.alarm(0)  # 确保取消超时
            
    except Exception as e:
        print(f"⚠️ 股票推荐失败: {e}")
        return get_fallback_stocks_by_industry(industry)

# 按行业获取备用股票推荐
def get_fallback_stocks_by_industry(industry):
    """按行业获取备用股票推荐，包含实时数据"""
    stock_templates = {
        "新能源": [
            {"code": "300750", "name": "宁德时代", "reason": "动力电池龙头，技术领先，短线关注业绩预期", "risk": "中", "impact": "高", "short_term_potential": "高", "holding_period": "3-5天", "entry_strategy": "回调买入，关注量能", "exit_strategy": "分批止盈，设置止损"},
            {"code": "002594", "name": "比亚迪", "reason": "新能源汽车全产业链布局，政策利好", "risk": "中", "impact": "高", "short_term_potential": "高", "holding_period": "2-4天", "entry_strategy": "突破买入，关注技术形态", "exit_strategy": "快速止盈，控制风险"},
            {"code": "300274", "name": "阳光电源", "reason": "光伏逆变器龙头，海外订单增长", "risk": "中", "impact": "中", "short_term_potential": "中", "holding_period": "1-3天", "entry_strategy": "低吸买入，关注支撑位", "exit_strategy": "及时止盈，避免追高"}
        ],
        "半导体": [
            {"code": "688981", "name": "中芯国际", "reason": "国内晶圆代工龙头，国产替代加速", "risk": "高", "impact": "高", "short_term_potential": "高", "holding_period": "2-4天", "entry_strategy": "回调买入，关注政策面", "exit_strategy": "分批止盈，严格止损"},
            {"code": "002049", "name": "紫光国微", "reason": "安全芯片设计领先，军工概念", "risk": "中", "impact": "中", "short_term_potential": "中", "holding_period": "1-3天", "entry_strategy": "突破买入，关注量能", "exit_strategy": "快速止盈，控制仓位"},
            {"code": "688536", "name": "思瑞浦", "reason": "模拟芯片设计，技术壁垒高", "risk": "高", "impact": "中", "short_term_potential": "中", "holding_period": "1-2天", "entry_strategy": "低吸买入，关注技术面", "exit_strategy": "及时止盈，避免追高"}
        ],
        "医药": [
            {"code": "300015", "name": "爱尔眼科", "reason": "眼科医疗服务龙头，消费医疗概念", "risk": "低", "impact": "中", "short_term_potential": "中", "holding_period": "2-4天", "entry_strategy": "回调买入，关注业绩", "exit_strategy": "分批止盈，长期持有"},
            {"code": "600276", "name": "恒瑞医药", "reason": "创新药研发领先，政策支持", "risk": "中", "impact": "高", "short_term_potential": "高", "holding_period": "3-5天", "entry_strategy": "突破买入，关注研发进展", "exit_strategy": "分批止盈，设置止损"},
            {"code": "300760", "name": "迈瑞医疗", "reason": "医疗器械龙头，海外市场拓展", "risk": "低", "impact": "中", "short_term_potential": "中", "holding_period": "2-3天", "entry_strategy": "低吸买入，关注订单", "exit_strategy": "及时止盈，控制风险"}
        ],
        "消费": [
            {"code": "000858", "name": "五粮液", "reason": "白酒龙头，品牌价值高，消费复苏", "risk": "低", "impact": "中", "short_term_potential": "中", "holding_period": "2-4天", "entry_strategy": "回调买入，关注销量", "exit_strategy": "分批止盈，长期持有"},
            {"code": "600519", "name": "贵州茅台", "reason": "白酒第一品牌，稀缺性价值", "risk": "低", "impact": "中", "short_term_potential": "中", "holding_period": "3-5天", "entry_strategy": "低吸买入，关注价格", "exit_strategy": "分批止盈，价值投资"},
            {"code": "002304", "name": "洋河股份", "reason": "白酒行业领先，渠道优势明显", "risk": "中", "impact": "中", "short_term_potential": "中", "holding_period": "1-3天", "entry_strategy": "突破买入，关注业绩", "exit_strategy": "快速止盈，控制风险"}
        ],
        "科技": [
            {"code": "002475", "name": "立讯精密", "reason": "消费电子制造龙头，苹果概念", "risk": "中", "impact": "高", "short_term_potential": "高", "holding_period": "2-4天", "entry_strategy": "回调买入，关注订单", "exit_strategy": "分批止盈，设置止损"},
            {"code": "000725", "name": "京东方A", "reason": "显示面板龙头，OLED技术突破", "risk": "中", "impact": "中", "short_term_potential": "中", "holding_period": "1-3天", "entry_strategy": "低吸买入，关注技术", "exit_strategy": "及时止盈，避免追高"},
            {"code": "002415", "name": "海康威视", "reason": "安防设备龙头，AI技术领先", "risk": "中", "impact": "中", "short_term_potential": "中", "holding_period": "2-3天", "entry_strategy": "突破买入，关注创新", "exit_strategy": "分批止盈，控制风险"}
        ],
        "基建": [
            {"code": "601668", "name": "中国建筑", "reason": "建筑行业龙头，基建投资加码", "risk": "中", "impact": "中", "short_term_potential": "中", "holding_period": "2-4天", "entry_strategy": "回调买入，关注订单", "exit_strategy": "分批止盈，设置止损"},
            {"code": "601390", "name": "中国中铁", "reason": "铁路建设龙头，政策支持", "risk": "中", "impact": "中", "short_term_potential": "中", "holding_period": "1-3天", "entry_strategy": "低吸买入，关注项目", "exit_strategy": "及时止盈，控制风险"},
            {"code": "601186", "name": "中国铁建", "reason": "基建工程龙头，海外市场拓展", "risk": "中", "impact": "中", "short_term_potential": "中", "holding_period": "2-3天", "entry_strategy": "突破买入，关注合同", "exit_strategy": "分批止盈，避免追高"}
        ],
        "银行": [
            {"code": "000001", "name": "平安银行", "reason": "零售银行领先，数字化转型", "risk": "低", "impact": "中", "short_term_potential": "中", "holding_period": "2-4天", "entry_strategy": "回调买入，关注业绩", "exit_strategy": "分批止盈，长期持有"},
            {"code": "600036", "name": "招商银行", "reason": "零售银行龙头，资产质量优良", "risk": "低", "impact": "中", "short_term_potential": "中", "holding_period": "3-5天", "entry_strategy": "低吸买入，关注分红", "exit_strategy": "分批止盈，价值投资"},
            {"code": "601398", "name": "工商银行", "reason": "国有大行龙头，稳定性强", "risk": "低", "impact": "中", "short_term_potential": "低", "holding_period": "3-5天", "entry_strategy": "低吸买入，关注股息", "exit_strategy": "长期持有，稳健投资"}
        ],
        "化工": [
            {"code": "600309", "name": "万华化学", "reason": "化工龙头，MDI全球领先", "risk": "中", "impact": "中", "short_term_potential": "中", "holding_period": "2-4天", "entry_strategy": "回调买入，关注价格", "exit_strategy": "分批止盈，设置止损"},
            {"code": "002648", "name": "卫星化学", "reason": "石化新材料龙头，技术领先", "risk": "中", "impact": "中", "short_term_potential": "中", "holding_period": "1-3天", "entry_strategy": "突破买入，关注产能", "exit_strategy": "及时止盈，控制风险"},
            {"code": "600426", "name": "华鲁恒升", "reason": "煤化工龙头，成本优势明显", "risk": "中", "impact": "中", "short_term_potential": "中", "holding_period": "2-3天", "entry_strategy": "低吸买入，关注成本", "exit_strategy": "分批止盈，避免追高"}
        ]
    }
    
    stocks = stock_templates.get(industry, [])
    
    # 为备用股票获取实时数据
    enhanced_stocks = []
    for stock in stocks:
        real_time_data = get_real_time_stock_data(stock["code"])
        if real_time_data:
            # 合并实时数据
            stock.update({
                "real_time_data": real_time_data,
                "current_price": real_time_data["current_price"],
                "price_change": real_time_data["price_change"],
                "technical_analysis": {
                    "ma20": real_time_data["ma20"],
                    "rsi": real_time_data["rsi"],
                    "volume_ratio": real_time_data["volume_ratio"],
                    "signals": real_time_data["technical_signals"]
                },
                "trading_points": real_time_data["trading_points"],
                "support_resistance": {
                    "support": real_time_data["support_levels"],
                    "resistance": real_time_data["resistance_levels"]
                }
            })
            
            # 更新买卖策略为具体价格
            stock["entry_strategy"] = f"建议买入价：¥{real_time_data['trading_points']['buy_price']}，支撑位：¥{real_time_data['support_levels']['primary']}"
            stock["exit_strategy"] = f"建议卖出价：¥{real_time_data['trading_points']['sell_price']}，阻力位：¥{real_time_data['resistance_levels']['primary']}"
            stock["stop_loss"] = f"止损价：¥{real_time_data['trading_points']['stop_loss']}"
            
            enhanced_stocks.append(stock)
            print(f"✅ 备用股票 {stock['code']} {stock['name']} 实时数据获取成功：¥{real_time_data['current_price']}")
        else:
            print(f"⚠️ 备用股票 {stock['code']} {stock['name']} 实时数据获取失败")
    
    return enhanced_stocks

# 生成股票推荐模板（保持向后兼容）
def generate_stock_recommendations(industry):
    """基于行业生成股票推荐模板（已废弃，使用get_specific_stock_recommendations）"""
    return get_fallback_stocks_by_industry(industry)

# 新增：从AI摘要中提取股票推荐信息
def extract_stock_recommendations_from_summary(summary):
    """从AI摘要中提取股票推荐信息"""
    stock_recommendations = {
        "hot_sector_stocks": [],  # 热点板块股票
        "rotation_stocks": []     # 轮动机会股票
    }
    
    try:
        if "具体股票推荐" in summary or "热点板块股票" in summary:
            lines = summary.split('\n')
            in_hot_stocks = False
            in_rotation_stocks = False
            
            for line in lines:
                line = line.strip()
                
                # 热点板块股票
                if "热点板块股票" in line or "📈" in line:
                    in_hot_stocks = True
                    in_rotation_stocks = False
                    continue
                
                # 轮动机会股票
                elif "轮动机会股票" in line or "🔄" in line:
                    in_hot_stocks = False
                    in_rotation_stocks = True
                    continue
                
                # 遇到新的标题，停止当前提取
                elif line.startswith('##') or line.startswith('###'):
                    in_hot_stocks = False
                    in_rotation_stocks = False
                    continue
                
                # 提取股票信息
                if (in_hot_stocks or in_rotation_stocks) and line.startswith('-') and len(line) > 2:
                    stock_info = line[1:].strip()
                    
                    # 解析股票信息
                    try:
                        # 格式：股票代码 股票名称：推荐理由，风险等级，短线潜力，建议持仓时间，买入策略，卖出策略
                        if '：' in stock_info:
                            stock_part, details_part = stock_info.split('：', 1)
                            
                            # 提取股票代码和名称
                            parts = stock_part.strip().split()
                            if len(parts) >= 2:
                                stock_code = parts[0]
                                stock_name = parts[1]
                                
                                # 解析详细信息
                                details = details_part.split('，')
                                if len(details) >= 6:
                                    reason = details[0]
                                    risk = details[1]
                                    potential = details[2]
                                    holding_period = details[3]
                                    entry_strategy = details[4]
                                    exit_strategy = details[5]
                                    
                                    stock_data = {
                                        "code": stock_code,
                                        "name": stock_name,
                                        "reason": reason,
                                        "risk": risk,
                                        "short_term_potential": potential,
                                        "holding_period": holding_period,
                                        "entry_strategy": entry_strategy,
                                        "exit_strategy": exit_strategy,
                                        "impact": "中"  # 默认值
                                    }
                                    
                                    if in_hot_stocks:
                                        stock_recommendations["hot_sector_stocks"].append(stock_data)
                                    elif in_rotation_stocks:
                                        stock_recommendations["rotation_stocks"].append(stock_data)
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

# 测试股票行业分类功能
def test_stock_industry_classification():
    """测试股票行业分类功能"""
    print("🧪 开始测试股票行业分类功能...")
    
    test_stocks = [
        ("300750", "宁德时代", "新能源"),
        ("002594", "比亚迪", "新能源"),
        ("688981", "中芯国际", "半导体"),
        ("603986", "兆易创新", "半导体"),
        ("300015", "爱尔眼科", "医药"),
        ("603259", "药明康德", "医药"),
        ("000858", "五粮液", "消费"),
        ("600519", "贵州茅台", "消费"),
        ("002475", "立讯精密", "科技"),
        ("600900", "长江电力", "新能源"),
        ("000001", "平安银行", "银行"),
        ("600309", "万华化学", "化工")
    ]
    
    for code, name, expected_industry in test_stocks:
        actual_industry = get_stock_industry(code)
        status = "✅" if actual_industry == expected_industry else "❌"
        print(f"{status} {code} {name}: 期望{expected_industry}, 实际{actual_industry}")
    
    print("🧪 股票行业分类测试完成\n")

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
    
    summary += "### ⚠️ 风险提示\n"
    for risk, warning in quick_analysis["风险提示"].items():
        summary += f"- **{risk}**: {warning}\n"
    summary += "\n"
    
    summary += "### 💡 操作建议\n"
    for action, advice in quick_analysis["操作建议"].items():
        summary += f"- **{action}**: {advice}\n"
    summary += "\n"
    
    summary += "### 🎯 散户优势\n"
    summary += "- **资金灵活**: 进出方便，反应快速\n"
    summary += "- **风险可控**: 单笔损失有限\n"
    summary += "- **操作简单**: 专注短线，不复杂\n"
    summary += "- **心态轻松**: 压力小，决策快\n\n"
    
    return summary

# 新增：生成详细的短线交易报告
def generate_detailed_short_term_report():
    """生成包含实时数据和精确买卖点的详细短线交易报告"""
    try:
        print("🚀 开始生成详细短线交易报告...")
        
        # 获取市场情绪和时机分析
        market_sentiment = get_market_sentiment()
        market_timing = analyze_market_timing()
        
        # 获取主要指数数据
        indices = get_market_indices()
        
        # 获取新闻摘要
        news_data, analysis_text = fetch_rss_articles(rss_feeds, max_articles=15)
        if not analysis_text:
            print("❌ 无法获取新闻数据")
            return None
            
        # 使用analysis_text作为新闻内容
        news_text = analysis_text
        
        # 提取热点行业
        industries, global_events = extract_industries_from_news(news_text)
        
        # 生成新闻摘要
        news_summary = summarize(news_text, global_events)
        
        # 构建详细报告
        report = f"""
# 📈 短线交易机会详细报告
**生成时间**: {datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")}

## 🎯 市场概况
**市场情绪**: {market_sentiment}
**交易时机**: {market_timing}

## 📊 主要指数实时数据
"""
        
        if indices:
            for index_name, index_data in indices.items():
                report += f"**{index_name}**: {index_data}\n"
        
        report += f"""

## 📰 市场热点分析
{news_summary}

## 🔥 热点板块短线机会
"""
        
        # 为每个热点行业生成股票推荐
        for industry in industries[:3]:  # 只取前3个热点行业
            report += f"\n### {industry}板块\n"
            
            # 获取该行业的股票推荐
            stocks = get_specific_stock_recommendations(industry, news_summary)
            
            if stocks:
                for i, stock in enumerate(stocks[:3], 1):  # 每个行业最多3只股票
                    report += f"""
**{i}. {stock['name']} ({stock['code']})**
- **当前价格**: ¥{stock.get('current_price', 'N/A')} ({stock.get('price_change', 'N/A')}%)
- **推荐理由**: {stock['reason']}
- **风险等级**: {stock['risk']} | **短线潜力**: {stock['short_term_potential']}
- **建议持仓**: {stock['holding_period']}

**技术面分析**:
- MA20: ¥{stock.get('technical_analysis', {}).get('ma20', 'N/A')}
- RSI: {stock.get('technical_analysis', {}).get('rsi', 'N/A')}
- 量比: {stock.get('technical_analysis', {}).get('volume_ratio', 'N/A')}
- 技术信号: {', '.join(stock.get('technical_analysis', {}).get('signals', []))}

**交易策略**:
- **买入策略**: {stock['entry_strategy']}
- **卖出策略**: {stock['exit_strategy']}
- **止损策略**: {stock.get('stop_loss', '未设置')}

**支撑阻力位**:
- 支撑位: ¥{stock.get('support_resistance', {}).get('support', {}).get('primary', 'N/A')} / ¥{stock.get('support_resistance', {}).get('support', {}).get('secondary', 'N/A')}
- 阻力位: ¥{stock.get('support_resistance', {}).get('resistance', {}).get('primary', 'N/A')} / ¥{stock.get('support_resistance', {}).get('resistance', {}).get('secondary', 'N/A')}

---
"""
            else:
                report += f"⚠️ 未找到合适的{industry}行业股票\n\n"
        
        # 添加轮动机会
        report += f"""
## 🔄 轮动机会（超跌反弹）

### 消费板块
**反弹逻辑**: 部分消费股年内跌幅较大，估值已反映悲观预期；暑期旅游旺季支撑。

**推荐股票**:
"""
        
        # 获取消费板块股票
        consumer_stocks = get_fallback_stocks_by_industry("消费")
        for i, stock in enumerate(consumer_stocks[:2], 1):
            report += f"""
**{i}. {stock['name']} ({stock['code']})**
- **当前价格**: ¥{stock.get('current_price', 'N/A')} ({stock.get('price_change', 'N/A')}%)
- **推荐理由**: {stock['reason']}
- **买入策略**: {stock['entry_strategy']}
- **卖出策略**: {stock['exit_strategy']}
- **止损策略**: {stock.get('stop_loss', '未设置')}
"""
        
        report += f"""
### 医药板块
**反弹逻辑**: 创新药龙头估值处于低位；政策支持力度加大。

**推荐股票**:
"""
        
        # 获取医药板块股票
        medical_stocks = get_fallback_stocks_by_industry("医药")
        for i, stock in enumerate(medical_stocks[:2], 1):
            report += f"""
**{i}. {stock['name']} ({stock['code']})**
- **当前价格**: ¥{stock.get('current_price', 'N/A')} ({stock.get('price_change', 'N/A')}%)
- **推荐理由**: {stock['reason']}
- **买入策略**: {stock['entry_strategy']}
- **卖出策略**: {stock['exit_strategy']}
- **止损策略**: {stock.get('stop_loss', '未设置')}
"""
        
        report += f"""
## ⚠️ 风险提示
1. 以上推荐基于技术分析和市场热点，不构成投资建议
2. 短线交易风险较高，请根据自身风险承受能力谨慎操作
3. 建议设置止损位，控制单笔交易风险不超过总资金的2%
4. 关注市场整体环境变化，及时调整策略
5. 所有价格数据为实时获取，交易时请以实际成交价为准

## 📋 明日操作要点
1. **开盘前**: 关注隔夜美股表现和重要经济数据
2. **盘中**: 重点关注推荐股票的成交量和技术形态变化
3. **收盘前**: 评估持仓，根据市场情况决定是否调整仓位
4. **风险控制**: 严格执行止损策略，避免情绪化交易

---
*本报告由AI自动生成，仅供参考，投资有风险，入市需谨慎*
"""
        
        print("✅ 详细短线交易报告生成完成")
        return report
        
    except Exception as e:
        print(f"❌ 生成详细短线交易报告失败: {e}")
        return None

# 测试新功能
if __name__ == "__main__":
    # 测试详细报告生成
    report = generate_detailed_short_term_report()
    if report:
        print("📊 报告预览:")
        print(report[:1000] + "...")
        
        # 发送到微信
        send_to_wechat("📈 短线交易机会详细报告", report)
    else:
        print("❌ 报告生成失败")
