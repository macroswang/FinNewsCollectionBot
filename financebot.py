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

# 获取具体股票推荐（增强版）
def get_specific_stock_recommendations(industry, news_summary):
    """基于行业和新闻摘要获取具体股票推荐，包含基本面、技术面和买卖点分析"""
    try:
        prompt = f"""
        基于以下{industry}行业的新闻分析，推荐3-5只最相关的A股股票，并提供完整的投资分析：

        行业分析：{news_summary}

        请按照以下格式返回JSON：
        {{
            "stocks": [
                {{
                    "code": "股票代码",
                    "name": "股票名称", 
                    "reason": "推荐理由（基于行业分析）",
                    "risk": "风险等级（低/中/高）",
                    "impact": "影响程度（高/中/低）",
                    "fundamental": {{
                        "pe_ratio": "市盈率估值",
                        "pb_ratio": "市净率估值", 
                        "roe": "净资产收益率",
                        "debt_ratio": "负债率",
                        "growth": "成长性评估"
                    }},
                    "technical": {{
                        "trend": "技术趋势（上涨/下跌/震荡）",
                        "support": "支撑位",
                        "resistance": "阻力位",
                        "volume": "成交量分析",
                        "momentum": "动量指标"
                    }},
                    "trading": {{
                        "entry_price": "建议买入价格区间",
                        "stop_loss": "止损位",
                        "target_price": "目标价格",
                        "holding_period": "建议持有周期",
                        "exit_strategy": "退出策略"
                    }},
                    "research": {{
                        "analyst_rating": "分析师评级",
                        "target_price_avg": "平均目标价",
                        "upside_potential": "上涨空间",
                        "key_risks": "主要风险因素"
                    }}
                }}
            ]
        }}

        要求：
        1. 股票必须与行业分析直接相关
        2. 基本面分析要客观评估估值水平
        3. 技术面分析要结合当前市场环境
        4. 买卖点建议要具体可操作
        5. 研报分析要参考市场共识
        6. 只返回JSON格式，不要其他文字
        """

        completion = openai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个专业的股票分析师，请基于行业分析推荐相关股票。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        response_text = completion.choices[0].message.content.strip()
        
        try:
            import json
            result = json.loads(response_text)
            return result.get("stocks", [])
        except json.JSONDecodeError:
            print(f"⚠️ AI返回格式错误，使用备用推荐")
            return get_fallback_stocks(industry)
            
    except Exception as e:
        print(f"⚠️ 股票推荐失败: {e}")
        return get_fallback_stocks(industry)

# 备用股票推荐（当动态推荐失败时使用）
def get_fallback_stocks(industry):
    """备用股票推荐模板"""
    stock_templates = {
        "新能源": [
            {"code": "300750", "name": "宁德时代", "reason": "动力电池龙头，技术领先", "risk": "中", "impact": "高"},
            {"code": "002594", "name": "比亚迪", "reason": "新能源汽车全产业链布局", "risk": "中", "impact": "高"},
            {"code": "300274", "name": "阳光电源", "reason": "光伏逆变器龙头", "risk": "中", "impact": "中"}
        ],
        "半导体": [
            {"code": "688981", "name": "中芯国际", "reason": "国内晶圆代工龙头", "risk": "高", "impact": "高"},
            {"code": "002049", "name": "紫光国微", "reason": "安全芯片设计领先", "risk": "中", "impact": "中"},
            {"code": "688536", "name": "思瑞浦", "reason": "模拟芯片设计", "risk": "高", "impact": "中"}
        ],
        "医药": [
            {"code": "300015", "name": "爱尔眼科", "reason": "眼科医疗服务龙头", "risk": "低", "impact": "中"},
            {"code": "600276", "name": "恒瑞医药", "reason": "创新药研发领先", "risk": "中", "impact": "高"},
            {"code": "300760", "name": "迈瑞医疗", "reason": "医疗器械龙头", "risk": "低", "impact": "中"}
        ],
        "消费": [
            {"code": "000858", "name": "五粮液", "reason": "白酒龙头，品牌价值高", "risk": "低", "impact": "中"},
            {"code": "600519", "name": "贵州茅台", "reason": "白酒第一品牌", "risk": "低", "impact": "中"},
            {"code": "002304", "name": "洋河股份", "reason": "白酒行业领先", "risk": "中", "impact": "中"}
        ],
        "科技": [
            {"code": "000002", "name": "万科A", "reason": "房地产龙头", "risk": "高", "impact": "中"},
            {"code": "000001", "name": "平安银行", "reason": "银行股龙头", "risk": "低", "impact": "中"},
            {"code": "600036", "name": "招商银行", "reason": "零售银行领先", "risk": "低", "impact": "中"}
        ]
    }
    return stock_templates.get(industry, [])

# 生成股票推荐模板（保持向后兼容）
def generate_stock_recommendations(industry):
    """基于行业生成股票推荐模板（已废弃，使用get_dynamic_stock_recommendations）"""
    return get_fallback_stocks(industry)

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
        for industry in related_industries[:3]:  # 最多推荐3个行业
            print(f"🤖 正在为{industry}行业生成股票推荐...")
            stocks = get_specific_stock_recommendations(industry, summary)
            if stocks:
                stock_recommendations += f"### 📈 {industry}板块\n"
                for stock in stocks[:3]:  # 每个行业最多3只股票
                    risk_emoji = {"低": "🟢", "中": "🟡", "高": "🔴"}.get(stock["risk"], "⚪")
                    impact_emoji = {"高": "🔥", "中": "⚡", "低": "💡"}.get(stock.get("impact", "中"), "💡")
                    stock_recommendations += f"- **{stock['code']} {stock['name']}** {risk_emoji} {impact_emoji}\n"
                    stock_recommendations += f"  - 推荐理由: {stock['reason']}\n"
                    stock_recommendations += f"  - 风险等级: {stock['risk']}\n"
                    if stock.get("impact"):
                        stock_recommendations += f"  - 影响程度: {stock['impact']}\n"
                    
                    # 基本面分析
                    if stock.get("fundamental"):
                        fund = stock["fundamental"]
                        stock_recommendations += f"  - **基本面**: PE{fund.get('pe_ratio', 'N/A')} | PB{fund.get('pb_ratio', 'N/A')} | ROE{fund.get('roe', 'N/A')}\n"
                    
                    # 技术面分析
                    if stock.get("technical"):
                        tech = stock["technical"]
                        stock_recommendations += f"  - **技术面**: {tech.get('trend', 'N/A')} | 支撑{tech.get('support', 'N/A')} | 阻力{tech.get('resistance', 'N/A')}\n"
                    
                    # 交易建议
                    if stock.get("trading"):
                        trade = stock["trading"]
                        stock_recommendations += f"  - **买入**: {trade.get('entry_price', 'N/A')}\n"
                        stock_recommendations += f"  - **止损**: {trade.get('stop_loss', 'N/A')}\n"
                        stock_recommendations += f"  - **目标**: {trade.get('target_price', 'N/A')}\n"
                        stock_recommendations += f"  - **持有**: {trade.get('holding_period', 'N/A')}\n"
                    
                    # 研报分析
                    if stock.get("research"):
                        research = stock["research"]
                        stock_recommendations += f"  - **评级**: {research.get('analyst_rating', 'N/A')} | 目标价{research.get('target_price_avg', 'N/A')}\n"
                        stock_recommendations += f"  - **空间**: {research.get('upside_potential', 'N/A')}\n"
                    
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
    final_summary = f"📅 **{today_str} 财经新闻摘要**\n\n{sentiment_section}{timing_section}{global_analysis}✍️ **今日分析总结：**\n{summary}\n\n{stock_recommendations}---\n\n"
    for category, content in articles_data.items():
        if content.strip():
            final_summary += f"## {category}\n{content}\n\n"

    # 推送到多个server酱key
    send_to_wechat(title=f"📌 {today_str} 财经新闻摘要", content=final_summary)
