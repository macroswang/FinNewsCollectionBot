# 福生无量天尊 - 精简版财经机器人
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
from openai import OpenAI

# 环境变量配置
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("环境变量 OPENAI_API_KEY 未设置")

server_chan_keys_env = os.getenv("SERVER_CHAN_KEYS")
if not server_chan_keys_env:
    raise ValueError("环境变量 SERVER_CHAN_KEYS 未设置")
server_chan_keys = server_chan_keys_env.split(",")

openai_client = OpenAI(api_key=openai_api_key, base_url="https://api.deepseek.com/v1")

# 精简后的RSS源配置
rss_feeds = {
    "💲 财经要闻": {
        "华尔街见闻": "https://dedicated.wallstreetcn.com/rss.xml",
        "36氪": "https://36kr.com/feed",
        "东方财富": "http://rss.eastmoney.com/rss_partener.xml",
        "香港經濟日報":"https://www.hket.com/rss/china",
        "东方财富":"http://rss.eastmoney.com/rss_partener.xml",
        "百度股票焦点":"http://news.baidu.com/n?cmd=1&class=stock&tn=rss&sub=0",
        "中新网":"https://www.chinanews.com.cn/rss/finance.xml",
        "国家统计局-最新发布":"https://www.stats.gov.cn/sj/zxfb/rss.xml",
    },
    "📈 市场动态": {
        "雪球": "https://xueqiu.com/hots/topic/rss",
        "中新网财经": "https://www.chinanews.com.cn/rss/finance.xml",
        "凤凰财经": "http://finance.ifeng.com/rss/stocknews.xml",
        "华尔街日报 - 经济":"https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness",
        "华尔街日报 - 市场":"https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
        "MarketWatch美股": "https://www.marketwatch.com/rss/topstories",
        "ZeroHedge华尔街新闻": "https://feeds.feedburner.com/zerohedge/feed",
        "ETF Trends": "https://www.etftrends.com/feed/",
    }
}

def get_today_date():
    """获取北京时间日期"""
    return datetime.now(pytz.timezone("Asia/Shanghai")).date()

def fetch_article_content(url, max_length=1000):
    """爬取文章内容"""
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text[:max_length]
    except Exception as e:
        print(f"❌ 文章爬取失败: {url}, {e}")
        return ""

def fetch_rss_with_retry(url, retries=2):
    """获取RSS内容"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    for i in range(retries):
        try:
            feed = feedparser.parse(url, request_headers=headers)
            if feed and hasattr(feed, 'entries') and len(feed.entries) > 0:
                return feed
        except Exception as e:
            print(f"⚠️ RSS获取失败 {i+1}/{retries}: {e}")
            time.sleep(2)
    return None

def collect_news_data(rss_feeds, max_articles=3):
    """收集新闻数据"""
    news_data = {}
    analysis_text = ""

    for category, sources in rss_feeds.items():
        category_content = ""
        for source, url in sources.items():
            print(f"📡 获取 {source} RSS...")
            feed = fetch_rss_with_retry(url)
            if not feed:
                continue

            articles = []
            for entry in feed.entries[:max_articles]:
                title = entry.get('title', '无标题')
                link = entry.get('link', '')
                if not link:
                    continue

                # 获取文章正文用于AI分析
                content = fetch_article_content(link)
                if content:
                    analysis_text += f"【{title}】\n{content}\n\n"
                
                articles.append(f"- [{title}]({link})")

            if articles:
                category_content += f"### {source}\n" + "\n".join(articles) + "\n\n"

        news_data[category] = category_content

    return news_data, analysis_text

def get_real_time_stock_data(stock_code):
    """获取股票实时数据"""
    try:
        # 转换A股代码格式
        if stock_code.startswith('6'):
            ticker = f"{stock_code}.SS"
        else:
            ticker = f"{stock_code}.SZ"
        
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2mo")
        
        if hist.empty:
            return None
            
        current_price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
        price_change = ((current_price - prev_price) / prev_price) * 100
        
        # 计算技术指标
        ma20 = hist['Close'].rolling(window=20).mean().iloc[-1] if len(hist) >= 20 else current_price
        recent_high = hist['High'].tail(20).max()
        recent_low = hist['Low'].tail(20).min()
        
        # 获取基本面数据
        try:
            info = stock.info
            market_cap = info.get('marketCap', 0)
            pe_ratio = info.get('trailingPE', 'N/A')
        except:
            market_cap = 0
            pe_ratio = 'N/A'
        
        return {
            "current_price": round(current_price, 2),
            "price_change": round(price_change, 2),
            "ma20": round(ma20, 2),
            "recent_high": round(recent_high, 2),
            "recent_low": round(recent_low, 2),
            "pe_ratio": pe_ratio,
            "market_cap": market_cap
        }
        
    except Exception as e:
        print(f"❌ 获取{stock_code}数据失败: {e}")
        return None

def check_market_cap(stock_code, max_cap_billion=500):
    """检查股票市值是否符合中小盘标准"""
    try:
        data = get_real_time_stock_data(stock_code)
        if data and data.get("market_cap"):
            market_cap_billion = data["market_cap"] / 100000000  # 转换为亿元
            return market_cap_billion <= max_cap_billion
        return True  # 无法获取时默认通过
    except:
        return True

def is_st_or_delisted_stock(stock_code):
    """检查股票是否为ST股票或退市股票"""
    try:
        # 转换A股代码格式
        if stock_code.startswith('6'):
            ticker = f"{stock_code}.SS"
        else:
            ticker = f"{stock_code}.SZ"
        
        stock = yf.Ticker(ticker)
        
        # 尝试获取股票信息
        try:
            info = stock.info
            stock_name = info.get('longName', '') or info.get('shortName', '')
            
            # 检查股票名称是否包含ST标记
            if stock_name and ('ST' in stock_name.upper() or '*ST' in stock_name.upper()):
                print(f"❌ {stock_code} 为ST股票: {stock_name}")
                return True
                
        except Exception:
            # 无法获取股票信息，可能已退市
            pass
        
        # 检查是否能获取到近期交易数据
        try:
            hist = stock.history(period="5d")
            if hist.empty:
                print(f"❌ {stock_code} 无交易数据，可能已退市")
                return True
                
            # 检查最近是否有交易量
            recent_volume = hist['Volume'].tail(3).sum()
            if recent_volume == 0:
                print(f"❌ {stock_code} 近期无交易量，可能已停牌或退市")
                return True
                
        except Exception:
            print(f"❌ {stock_code} 数据获取异常，可能已退市")
            return True
            
        return False
        
    except Exception as e:
        print(f"❌ 检查{stock_code}异常: {e}")
        return True  # 异常时默认过滤掉

def generate_ai_analysis(news_text):
    """生成AI分析"""
    try:
        completion = openai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": """
你是专业的短线交易分析师。请根据新闻内容生成短线交易分析，包括：

1. 热点板块分析（1-3天爆发预期）
2. 轮动机会分析（超跌反弹）  
3. 具体股票推荐（仅限A股，市值≤500亿）
4. 风险提示和操作策略

格式要求：
## 🎯 短线交易机会

### 📈 热点板块（1-3天预期）
- 板块名称：推荐理由，催化剂，目标涨幅

### 🔄 轮动机会（超跌反弹）  
- 板块名称：反弹逻辑，技术支撑

## 🎯 具体股票推荐（A股）

### 📈 热点板块股票
- 股票代码 股票名称：推荐理由，风险等级，短线潜力，持仓时间，买入策略，技术支撑

### 🔄 轮动机会股票  
- 股票代码 股票名称：推荐理由，风险等级，短线潜力，持仓时间，买入策略，技术支撑

## ⚠️ 风险提示
- 主要风险因素
- 需要规避的板块

## 💰 操作策略
- 仓位控制建议
- 止盈止损策略

要求：
- 只推荐A股（6位数字代码）
- 优先推荐中小盘股票（市值≤500亿）
- 严禁推荐ST股票、*ST股票或退市、科创版和北交所股票
- 只推荐正常交易的主板、中小板、创业板股票
- 提供具体操作建议
- 1-5个交易日操作周期
                """},
                {"role": "user", "content": f"新闻内容：{news_text}"}
            ],
            temperature=0.3
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ AI分析失败: {e}")
        return f"## 📊 今日财经要闻\n\n{news_text[:800]}..."

def extract_stock_codes(text):
    """提取文本中的股票代码"""
    pattern = r'\b\d{6}\b'
    return re.findall(pattern, text)

def update_stock_data_in_text(text):
    """更新文本中股票的实时数据"""
    stock_codes = extract_stock_codes(text)
    updated_text = text
    
    for code in stock_codes:
        # 首先检查是否为ST股票或退市股票
        if is_st_or_delisted_stock(code):
            print(f"❌ {code} 为ST股票或已退市，已过滤")
            # 从文本中移除这个股票代码的推荐
            pattern = rf'- {code}[^\n]*\n?'
            updated_text = re.sub(pattern, '', updated_text)
            continue
            
        # 检查市值是否符合要求
        if not check_market_cap(code):
            print(f"❌ {code} 市值超标，已过滤")
            # 从文本中移除这个股票代码的推荐
            pattern = rf'- {code}[^\n]*\n?'
            updated_text = re.sub(pattern, '', updated_text)
            continue
            
        # 获取实时数据
        data = get_real_time_stock_data(code)
        if data:
            # 在股票代码后添加实时价格信息
            price_emoji = "📈" if data["price_change"] > 0 else "📉" if data["price_change"] < 0 else "➡️"
            price_info = f"（当前价：¥{data['current_price']} {price_emoji}{data['price_change']}%）"
            
            # 替换文本中的股票代码，添加价格信息
            pattern = rf'\b{code}\b(?!\s*（当前价：)'  # 避免重复添加
            replacement = f"{code}{price_info}"
            updated_text = re.sub(pattern, replacement, updated_text)
            
            print(f"✅ 已更新 {code} 实时数据")
    
    return updated_text

def get_market_indices():
    """获取主要指数数据"""
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
                    emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                    market_data[name] = f"{emoji} {current_price:.2f} ({change:+.2f}%)"
                else:
                    market_data[name] = "📊 数据获取中"
            except Exception:
                market_data[name] = "❌ 数据获取失败"
        
        return market_data
    except Exception:
        return {"市场数据": "❌ 获取失败"}

def send_wechat_notification(title, content):
    """发送微信推送"""
    for key in server_chan_keys:
        try:
            url = f"https://sctapi.ftqq.com/{key}.send"
            data = {"title": title, "desp": content}
            response = requests.post(url, data=data, timeout=10)
            if response.ok:
                print(f"✅ 推送成功: {key}")
            else:
                print(f"❌ 推送失败: {key}")
        except Exception as e:
            print(f"❌ 推送异常: {key}, {e}")

def main():
    """主函数"""
    today_str = get_today_date().strftime("%Y-%m-%d")
    print(f"📅 开始执行 {today_str} 财经分析")
    
    # 收集新闻数据
    print("📡 正在收集新闻数据...")
    news_data, analysis_text = collect_news_data(rss_feeds)
    
    if not analysis_text.strip():
        print("⚠️ 未获取到新闻内容")
        return
    
    # 获取市场指数
    print("📊 正在获取市场指数...")
    market_indices = get_market_indices()
    
    print("🔍 分析文本：", analysis_text)
    # 生成AI分析
    print("🤖 正在生成AI分析...")
    ai_analysis = generate_ai_analysis(analysis_text)
    
    print("🔍 AI分析内容结果：", ai_analysis)
    # 更新股票实时数据
    print("📈 正在更新股票实时数据...")
    updated_analysis = update_stock_data_in_text(ai_analysis)
    
    print("🔍 AI分析总结：", updated_analysis)
    # 构建最终消息
    indices_section = "## 📈 实时市场指数\n"
    for name, value in market_indices.items():
        indices_section += f"- **{name}**: {value}\n"
    indices_section += "\n"
    
    final_message = f"""📅 **{today_str} 散户短线交易分析**

{indices_section}

✍️ **AI分析总结：**
{updated_analysis}

---

"""
    
    # 添加新闻链接
    for category, content in news_data.items():
        if content.strip():
            final_message += f"## {category}\n{content}\n\n"
    
    # 发送推送
    print("📤 正在发送推送...")
    send_wechat_notification(
        title=f"🎯 {today_str} 短线交易分析", 
        content=final_message
    )
    
    print("✅ 分析完成")

if __name__ == "__main__":
    main()