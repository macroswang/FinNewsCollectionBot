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

# 检测是否为英文内容
def is_english_content(text):
    """检测文本是否为英文内容"""
    if not text:
        return False
    
    # 统计英文字符和中文字符
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    
    # 如果英文字符数量明显多于中文字符，则认为是英文内容
    return english_chars > chinese_chars * 2

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

                # 检测是否为英文内容，如果是则跳过展示
                if is_english_content(title):
                    print(f"🔹 {source} - {title} 获取成功（英文内容，仅用于分析）")
                    continue

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
                 你是一名专业的财经新闻分析师，请根据以下新闻内容和全球市场联动分析，按照以下步骤完成任务：
                 
                 **分析步骤：**
                 1. 提取新闻中涉及的主要行业和主题，找出近1天涨幅最高的3个行业或主题，以及近3天涨幅较高且此前2周表现平淡的3个行业/主题。
                 2. 针对每个热点，输出：
                    - 催化剂：分析近期上涨的可能原因（政策、数据、事件、情绪等）
                    - 复盘：梳理过去3个月该行业/主题的核心逻辑、关键动态与阶段性走势
                    - 展望：判断该热点是短期炒作还是有持续行情潜力
                 
                 **全球联动分析：**
                 3. 分析全球事件对国内市场的联动影响：
                    - 资金流向影响
                    - 情绪传导机制
                    - 供应链影响
                    - 政策传导效应
                 
                 **投资建议：**
                 4. 基于以上分析，提供投资建议：
                    - 重点关注行业和板块
                    - 风险提示和注意事项
                    - 投资策略建议
                 
                 5. 将以上分析整合为一篇1500字以内的财经热点摘要，包含：
                    - 市场热点分析
                    - 全球联动影响
                    - 投资建议和风险提示
                    
                 注意：分析要结合国内外市场联动逻辑，避免无根据的推荐。
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
        "技术形态": "📈 突破关键阻力位"
    }

# 市场时机分析
def analyze_market_timing():
    """分析当前市场时机，判断是否适合建仓"""
    timing_analysis = {
        "整体时机": "🟡 中性偏乐观",
        "建仓建议": "分批建仓，控制仓位",
        "风险提示": "关注外部风险事件",
        "重点关注": "业绩确定性强的龙头股",
        "操作策略": "逢低买入，不追高"
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

# 获取实时股票数据
def get_real_time_stock_data(stock_code):
    """获取股票的实时数据"""
    try:
        # 转换A股代码格式（添加.SS或.SZ后缀）
        if stock_code.startswith('6'):
            ticker = f"{stock_code}.SS"  # 上海证券交易所
        else:
            ticker = f"{stock_code}.SZ"  # 深圳证券交易所
        
        print(f"🔍 正在获取 {ticker} 的数据...")
        
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
            "volume": volume
        }
        
        print(f"✅ {stock_code} 数据获取成功: ¥{result['current_price']} ({result['price_change']}%)")
        return result
        
    except Exception as e:
        print(f"❌ 获取{stock_code}实时数据失败: {e}")
        return None

# 获取具体股票推荐（增强版）
def get_specific_stock_recommendations(industry, news_summary):
    """基于行业和新闻摘要获取具体股票推荐，包含实时基本面、技术面和买卖点分析"""
    try:
        # 根据行业提供具体的股票推荐指导
        industry_guidance = {
            "银行": "推荐银行板块龙头股，如工商银行、建设银行、农业银行、中国银行等",
            "消费": "推荐消费板块龙头股，如贵州茅台、五粮液、海天味业、伊利股份等",
            "科技": "推荐科技板块龙头股，如腾讯、阿里巴巴、百度、美团等",
            "新能源": "推荐新能源板块龙头股，如宁德时代、比亚迪、隆基绿能、阳光电源等",
            "医药": "推荐医药板块龙头股，如恒瑞医药、迈瑞医疗、爱尔眼科、药明康德等",
            "军工": "推荐军工板块龙头股，如中航沈飞、中航西飞、航天电子、中国重工等",
            "半导体": "推荐半导体板块龙头股，如中芯国际、韦尔股份、北方华创、紫光国微等",
            "房地产": "推荐房地产板块龙头股，如万科A、保利发展、招商蛇口、金地集团等",
            "化工": "推荐化工板块龙头股，如万华化学、恒力石化、荣盛石化、桐昆股份等",
            "汽车": "推荐汽车板块龙头股，如上汽集团、比亚迪、长城汽车、长安汽车等"
        }
        
        guidance = industry_guidance.get(industry, f"推荐{industry}板块的龙头股票")
        
        prompt = f"""
        基于以下{industry}行业的新闻分析，推荐3-5只最相关的A股股票：

        行业分析：{news_summary}
        
        推荐要求：
        {guidance}
        
        请严格按照以下格式返回JSON：
        {{
            "stocks": [
                {{
                    "code": "股票代码",
                    "name": "股票名称", 
                    "reason": "推荐理由（必须与{industry}行业直接相关）",
                    "risk": "风险等级（低/中/高）",
                    "impact": "影响程度（高/中/低）"
                }}
            ]
        }}

        严格要求：
        1. 股票必须严格属于{industry}行业，不能跨行业推荐
        2. 推荐理由必须与{industry}行业直接相关
        3. 只返回JSON格式，不要其他文字
        4. 确保股票代码和名称准确
        """

        completion = openai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": f"你是一个专业的股票分析师，专门负责{industry}行业的股票推荐。请严格按照行业分类推荐股票，确保推荐的股票确实属于{industry}行业。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        
        response_text = completion.choices[0].message.content.strip()
        
        try:
            import json
            result = json.loads(response_text)
            stocks = result.get("stocks", [])
            
            # 验证股票是否属于该行业
            validated_stocks = []
            for stock in stocks:
                # 简单的行业验证逻辑
                if industry == "银行" and "银行" in stock.get("name", ""):
                    validated_stocks.append(stock)
                elif industry == "消费" and any(keyword in stock.get("name", "") for keyword in ["茅台", "五粮液", "海天", "伊利", "美的", "格力"]):
                    validated_stocks.append(stock)
                elif industry == "军工" and any(keyword in stock.get("name", "") for keyword in ["航空", "航天", "军工", "沈飞", "西飞"]):
                    validated_stocks.append(stock)
                elif industry == "新能源" and any(keyword in stock.get("name", "") for keyword in ["宁德", "比亚迪", "隆基", "阳光", "新能源"]):
                    validated_stocks.append(stock)
                elif industry == "医药" and any(keyword in stock.get("name", "") for keyword in ["医药", "医疗", "恒瑞", "迈瑞", "爱尔"]):
                    validated_stocks.append(stock)
                elif industry == "科技" and any(keyword in stock.get("name", "") for keyword in ["科技", "软件", "互联网", "腾讯", "阿里"]):
                    validated_stocks.append(stock)
                elif industry == "半导体" and any(keyword in stock.get("name", "") for keyword in ["半导体", "芯片", "中芯", "韦尔", "北方"]):
                    validated_stocks.append(stock)
                elif industry == "房地产" and any(keyword in stock.get("name", "") for keyword in ["万科", "保利", "招商", "金地", "房地产"]):
                    validated_stocks.append(stock)
                elif industry == "化工" and any(keyword in stock.get("name", "") for keyword in ["化工", "化学", "石化", "万华", "恒力"]):
                    validated_stocks.append(stock)
                elif industry == "汽车" and any(keyword in stock.get("name", "") for keyword in ["汽车", "上汽", "比亚迪", "长城", "长安"]):
                    validated_stocks.append(stock)
                else:
                    # 对于其他行业，如果推荐理由包含行业关键词，则接受
                    if industry in stock.get("reason", ""):
                        validated_stocks.append(stock)
            
            return validated_stocks
            
        except json.JSONDecodeError:
            print(f"⚠️ AI返回格式错误，返回空列表")
            return []
            
    except Exception as e:
        print(f"⚠️ 股票推荐失败: {e}")
        return []



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


if __name__ == "__main__":
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

    # 生成股票推荐部分
    stock_recommendations = ""
    if related_industries:
        stock_recommendations = "## 🎯 A股投资机会\n\n"
        used_stocks = set()  # 用于去重的股票代码集合
        
        for industry in related_industries[:3]:  # 最多推荐3个行业
            print(f"🤖 正在为{industry}行业生成股票推荐...")
            stocks = get_specific_stock_recommendations(industry, summary)
            if stocks:
                stock_recommendations += f"### 📈 {industry}板块\n"
                industry_stock_count = 0  # 每个行业的股票计数
                
                for stock in stocks:
                    # 检查是否已经推荐过这只股票
                    stock_code = stock.get('code', '')
                    if stock_code in used_stocks:
                        print(f"⚠️ 跳过重复股票: {stock_code} {stock.get('name', '')}")
                        continue
                    
                    # 检查是否达到每个行业的最大推荐数量
                    if industry_stock_count >= 3:
                        break
                    
                    used_stocks.add(stock_code)  # 添加到已使用集合
                    industry_stock_count += 1
                    
                    risk_emoji = {"低": "🟢", "中": "🟡", "高": "🔴"}.get(stock["risk"], "⚪")
                    impact_emoji = {"高": "🔥", "中": "⚡", "低": "💡"}.get(stock.get("impact", "中"), "💡")
                    stock_recommendations += f"- **{stock['code']} {stock['name']}** {risk_emoji} {impact_emoji}\n"
                    stock_recommendations += f"  - 推荐理由: {stock['reason']}\n"
                    stock_recommendations += f"  - 风险等级: {stock['risk']}\n"
                    if stock.get("impact"):
                        stock_recommendations += f"  - 影响程度: {stock['impact']}\n"
                    
                    # 获取实时数据
                    try:
                        print(f"📊 正在获取{stock['code']}的实时数据...")
                        real_time_data = get_real_time_stock_data(stock['code'])
                        
                        if real_time_data:
                            # 实时价格和涨跌幅
                            price_change_emoji = "📈" if real_time_data["price_change"] > 0 else "📉" if real_time_data["price_change"] < 0 else "➡️"
                            stock_recommendations += f"  - **实时价格**: ¥{real_time_data['current_price']} {price_change_emoji} {real_time_data['price_change']}%\n"
                            
                            # 基本面数据
                            if real_time_data["pe_ratio"] != 'N/A' and real_time_data["pe_ratio"] is not None:
                                pe_str = f"{real_time_data['pe_ratio']:.1f}" if isinstance(real_time_data['pe_ratio'], (int, float)) else str(real_time_data['pe_ratio'])
                                pb_str = f"{real_time_data['pb_ratio']:.2f}" if real_time_data['pb_ratio'] != 'N/A' and real_time_data['pb_ratio'] is not None and isinstance(real_time_data['pb_ratio'], (int, float)) else 'N/A'
                                stock_recommendations += f"  - **估值**: PE{pe_str} | PB{pb_str}\n"
                            
                            # 技术面分析
                            trend = "上涨" if real_time_data["current_price"] > real_time_data["ma20"] else "下跌" if real_time_data["current_price"] < real_time_data["ma20"] else "震荡"
                            stock_recommendations += f"  - **技术面**: {trend} | MA20:¥{real_time_data['ma20']:.2f} | MA50:¥{real_time_data['ma50']:.2f}\n"
                            
                            # 支撑阻力位
                            stock_recommendations += f"  - **支撑/阻力**: ¥{real_time_data['recent_low']:.2f} / ¥{real_time_data['recent_high']:.2f}\n"
                            
                            # 成交量分析
                            volume_emoji = "🔥" if real_time_data["volume_ratio"] > 1.5 else "📊" if real_time_data["volume_ratio"] > 1 else "📉"
                            stock_recommendations += f"  - **成交量**: {volume_emoji} {real_time_data['volume_ratio']:.1f}倍\n"
                            
                            # 交易建议（基于实时数据）
                            entry_price = real_time_data["current_price"] * 0.95  # 建议在现价5%以下买入
                            stop_loss = real_time_data["current_price"] * 0.92    # 止损设在现价8%以下
                            target_price = real_time_data["current_price"] * 1.15  # 目标价设在现价15%以上
                            
                            stock_recommendations += f"  - **买入建议**: ¥{entry_price:.2f}以下\n"
                            stock_recommendations += f"  - **止损位**: ¥{stop_loss:.2f}\n"
                            stock_recommendations += f"  - **目标价**: ¥{target_price:.2f}\n"
                        else:
                            stock_recommendations += f"  - **数据获取失败**，请手动查询\n"
                    except Exception as e:
                        print(f"⚠️ 处理{stock['code']}数据时出错: {e}")
                        stock_recommendations += f"  - **数据处理错误**，请手动查询\n"
                    
                    stock_recommendations += "\n"
        stock_recommendations += "⚠️ **投资提醒**: 以上推荐基于今日新闻动态生成，仅供参考，投资有风险，入市需谨慎！\n\n"
        
        # 添加投资策略建议
        strategy_section = "## 💡 投资策略建议\n\n"
        strategy_section += "### 📈 建仓策略\n"
        strategy_section += "- **分批建仓**: 建议分3-5次逐步建仓，降低单次风险\n"
        strategy_section += "- **仓位控制**: 单只股票不超过总仓位的10-15%\n"
        strategy_section += "- **时机把握**: 关注回调机会，避免追高\n\n"
        
        strategy_section += "### 🛡️ 风险控制\n"
        strategy_section += "- **止损设置**: 严格执行止损，一般不超过-8%\n"
        strategy_section += "- **止盈策略**: 分批止盈，锁定部分利润\n"
        strategy_section += "- **分散投资**: 避免过度集中在单一行业\n\n"
        
        strategy_section += "### 📊 持仓管理\n"
        strategy_section += "- **定期检视**: 每周评估持仓表现\n"
        strategy_section += "- **动态调整**: 根据市场变化调整仓位\n"
        strategy_section += "- **长期思维**: 优质股票可长期持有\n\n"
        
        stock_recommendations += strategy_section

    # 生成仅展示标题和链接的最终消息
    final_summary = f"📅 **{today_str} 财经新闻摘要**\n\n{sentiment_section}{indices_section}{timing_section}{global_analysis}✍️ **今日分析总结：**\n{summary}\n\n{stock_recommendations}---\n\n"
    for category, content in articles_data.items():
        if content.strip():
            final_summary += f"## {category}\n{content}\n\n"

    # 推送到多个server酱key
    send_to_wechat(title=f"📌 {today_str} 财经新闻摘要", content=final_summary)
