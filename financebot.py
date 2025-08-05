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
from eastmoney_api import eastmoney_api
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
        # 使用东方财富API获取股票信息
        stock_info = eastmoney_api.get_stock_info(stock_code)
        if not stock_info:
            print(f"❌ 获取{stock_code}数据失败")
            return None
            
        current_price = stock_info['current_price']
        price_change_pct = stock_info['price_change_pct']
        
        # 获取历史数据计算技术指标
        history_data = eastmoney_api.get_stock_history(stock_code, days=60)
        if history_data and len(history_data) >= 20:
            # 计算MA20
            closes = [item['close'] for item in history_data[-20:]]
            ma20 = sum(closes) / len(closes)
            
            # 计算近期高低点
            highs = [item['high'] for item in history_data[-20:]]
            lows = [item['low'] for item in history_data[-20:]]
            recent_high = max(highs)
            recent_low = min(lows)
        else:
            ma20 = current_price
            recent_high = current_price
            recent_low = current_price
        
        return {
            "current_price": round(current_price, 2),
            "price_change": round(price_change_pct, 2),
            "ma20": round(ma20, 2),
            "recent_high": round(recent_high, 2),
            "recent_low": round(recent_low, 2),
            "pe_ratio": stock_info.get('pe_ratio', 'N/A'),
            "market_cap": stock_info.get('market_cap', 0)
        }
        
    except Exception as e:
        print(f"❌ 获取{stock_code}数据失败: {e}")
        return None

def check_market_cap(stock_code, max_cap_billion=500):
    """检查股票市值是否符合中小盘标准"""
    try:
        stock_info = eastmoney_api.get_stock_info(stock_code)
        if stock_info and stock_info.get('market_cap'):
            market_cap_billion = stock_info["market_cap"] / 100000000  # 转换为亿元
            if market_cap_billion > max_cap_billion:
                print(f"❌ {stock_code} 市值超标 ({market_cap_billion:.1f}亿 > {max_cap_billion}亿)，已过滤")
                return False
            return True
        # 无法获取市值数据时，可能是网络问题，默认通过
        print(f"⚠️ {stock_code} 无法获取市值数据，可能是网络问题，默认通过")
        return True
    except Exception as e:
        print(f"⚠️ {stock_code} 市值检查异常: {e}，默认通过")
        return True  # 异常时默认通过

def is_st_or_delisted_stock(stock_code):
    """检查股票是否为ST股票或退市股票"""
    try:
        # 使用东方财富API检查ST状态
        if eastmoney_api.check_st_stock(stock_code):
            return True
        
        # 检查是否为退市股票
        if eastmoney_api.check_delisted_stock(stock_code):
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
- 板块名称：推荐理由，催化剂，目标涨幅，买入时机，止盈止损

### 🔄 轮动机会（超跌反弹）  
- 板块名称：反弹逻辑，技术支撑，买入时机，止盈止损

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

**关键约束条件：**
- 只推荐A股（6位数字代码）
- 分析资金流向和情绪变化
- 重点关注板块轮动和热点切换
- 优先选择适合短线交易的股票（流动性好、波动适中）
- 优先推荐中小盘股票（市值≤500亿）
- 严禁推荐ST股票、*ST股票或退市、科创版和北交所股票
- 只推荐正常交易的主板、中小板、创业板股票
- 提供具体操作建议，1-5个交易日操作周期

**重要：买入价格约束**
- 推荐的买入价格必须在当前股价的±10%范围内
- 支撑位/买入点必须是近期（1-5个交易日）可能触及的价格
- 不能推荐需要等待股价大幅下跌才能介入的股票
- 买入策略应该是：当前价附近、回调5-10%时、突破某阻力位等近期可操作的时机
- 如果股票当前价格不适合短线介入，则不要推荐该股票

**买入时机描述示例：**
正确：当前价附近分批建仓、回调3-5%时加仓、突破20日线时追入
错误：跌至XX元（远低于当前价）时介入、等待大幅回调后买入
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

def validate_buy_price_reasonableness(stock_line, current_price):
    """验证买入价格的合理性"""
    try:
        # 提取买入价格相关的文本
        price_patterns = [
            r'(\d+\.?\d*)元[附近买入|买入|介入]',  # XX元买入/介入
            r'[回调至|跌至|支撑位](\d+\.?\d*)元',  # 回调至XX元
            r'(\d+\.?\d*)[元]?[附近|左右|上下]',   # XX元附近
            r'支撑[位]?[：:]?(\d+\.?\d*)',       # 支撑位XX
        ]
        
        buy_prices = []
        for pattern in price_patterns:
            matches = re.findall(pattern, stock_line)
            for match in matches:
                try:
                    price = float(match)
                    if 1 <= price <= 1000:  # 合理的股价范围
                        buy_prices.append(price)
                except ValueError:
                    continue
        
        if not buy_prices:
            # 如果没有找到具体价格，检查是否有明显不合理的描述
            unreasonable_phrases = [
                r'跌至\d+元', r'等待.*回调', r'大幅下跌', 
                r'深度回调', r'等.*跌破', r'破位.*买入'
            ]
            for phrase in unreasonable_phrases:
                if re.search(phrase, stock_line):
                    print(f"❌ 发现不合理买入描述: {phrase}")
                    return False
            return True  # 没有具体价格但也没有不合理描述，暂时通过
        
        # 检查价格合理性
        for buy_price in buy_prices:
            price_diff_percent = abs(buy_price - current_price) / current_price * 100
            if price_diff_percent > 15:  # 超过15%认为不合理
                print(f"❌ 买入价格 {buy_price}元 与当前价格 {current_price}元 差距过大: {price_diff_percent:.1f}%")
                return False
            elif buy_price < current_price * 0.85:  # 低于当前价85%认为不合理
                print(f"❌ 买入价格 {buy_price}元 过低，当前价格 {current_price}元")
                return False
                
        return True
        
    except Exception as e:
        print(f"⚠️ 价格合理性验证失败: {e}")
        return True  # 验证失败时默认通过

def update_stock_data_in_text(text):
    """更新文本中股票的实时数据并验证推荐合理性"""
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
            current_price = data['current_price']
            
            # 查找该股票的推荐行
            stock_line_pattern = rf'- {code}[^-\n]*(?:\n(?!\s*-)[^\n]*)*'
            stock_line_match = re.search(stock_line_pattern, updated_text, re.MULTILINE)
            
            if stock_line_match:
                stock_line = stock_line_match.group(0)
                
                # 验证买入价格合理性
                if not validate_buy_price_reasonableness(stock_line, current_price):
                    print(f"❌ {code} 买入价格不合理，已过滤")
                    # 从文本中移除这个股票代码的推荐
                    updated_text = updated_text.replace(stock_line, '')
                    continue
            
            # 在股票代码后添加实时价格信息
            price_emoji = "📈" if data["price_change"] > 0 else "📉" if data["price_change"] < 0 else "➡️"
            price_info = f"（当前价：¥{current_price} {price_emoji}{data['price_change']}%）"
            
            # 替换文本中的股票代码，添加价格信息
            pattern = rf'\b{code}\b(?!\s*（当前价：)'  # 避免重复添加
            replacement = f"{code}{price_info}"
            updated_text = re.sub(pattern, replacement, updated_text)
            
            print(f"✅ 已更新 {code} 实时数据，买入价格合理")
        else:
            print(f"❌ {code} 无法获取实时数据，已过滤")
            # 从文本中移除这个股票代码的推荐
            pattern = rf'- {code}[^\n]*\n?'
            updated_text = re.sub(pattern, '', updated_text)
    
    # 清理空的推荐部分
    updated_text = clean_empty_sections(updated_text)
    
    return updated_text

def clean_empty_sections(text):
    """清理空的推荐部分"""
    lines = text.split('\n')
    cleaned_lines = []
    skip_next_empty = False
    
    for i, line in enumerate(lines):
        # 如果是子标题行（### 开头）
        if line.startswith('### '):
            # 检查后面是否有实际的推荐内容
            has_content = False
            for j in range(i + 1, len(lines)):
                if lines[j].startswith('### ') or lines[j].startswith('## '):
                    break
                if lines[j].strip() and lines[j].startswith('- '):
                    has_content = True
                    break
            
            if has_content:
                cleaned_lines.append(line)
            else:
                skip_next_empty = True
        # 如果是主标题行（## 开头）
        elif line.startswith('## '):
            cleaned_lines.append(line)
            skip_next_empty = False
        # 如果是空行且前面的部分被跳过了
        elif not line.strip() and skip_next_empty:
            skip_next_empty = False
            continue
        else:
            cleaned_lines.append(line)
            skip_next_empty = False
    
    return '\n'.join(cleaned_lines)

def get_market_indices():
    """获取主要指数数据"""
    try:
        return eastmoney_api.get_market_indices()
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