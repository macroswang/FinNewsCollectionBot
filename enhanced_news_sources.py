"""
增强的新闻数据源模块
提供多种方式获取最新财经资讯
"""

import feedparser
import requests
from typing import Dict, List, Optional
from datetime import datetime
import time
import json
from newspaper import Article


class EnhancedNewsSources:
    """增强的新闻数据源管理器"""
    
    def __init__(self):
        """初始化，定义所有可用的新闻源"""
        self.rss_feeds = self._init_rss_feeds()
        self.api_sources = self._init_api_sources()
    
    def _init_rss_feeds(self) -> Dict:
        """初始化RSS源配置（大幅扩展）"""
        return {
            "💲 主流财经媒体": {
                "华尔街见闻": "https://dedicated.wallstreetcn.com/rss.xml",
                "36氪": "https://36kr.com/feed",
                "财新网": "https://www.caixin.com/rss/all.xml",
                "第一财经": "https://www.yicai.com/rss.xml",
                "财经杂志": "https://www.caijing.com.cn/rss.xml",
                "21世纪经济报道": "https://www.21jingji.com/rss.xml",
                "经济观察网": "https://www.eeo.com.cn/rss.xml",
                "界面新闻": "https://www.jiemian.com/rss.xml",
                "每日经济新闻": "https://www.nbd.com.cn/rss.xml",
                "证券时报": "https://www.stcn.com/rss.xml",
                "上海证券报": "https://www.cnstock.com/rss.xml",
                "中国证券报": "https://www.cs.com.cn/rss.xml",
            },
            "📈 股票交易平台": {
                "东方财富": "http://rss.eastmoney.com/rss_partener.xml",
                "东方财富-股票": "http://rss.eastmoney.com/rss_stock.xml",
                "东方财富-财经": "http://rss.eastmoney.com/rss_finance.xml",
                "雪球": "https://xueqiu.com/hots/topic/rss",
                "同花顺": "https://www.10jqka.com.cn/rss.xml",
                "和讯财经": "https://www.hexun.com/rss.xml",
                "金融界": "https://www.jrj.com.cn/rss.xml",
            },
            "🇨🇳 官方及权威媒体": {
                "新华财经": "https://www.xinhuanet.com/fortune/rss.xml",
                "中新网财经": "https://www.chinanews.com.cn/rss/finance.xml",
                "人民网财经": "http://finance.people.com.cn/rss.xml",
                "央视财经": "https://www.cctv.com/rss/finance.xml",
                "国家统计局": "https://www.stats.gov.cn/sj/zxfb/rss.xml",
                "证监会": "http://www.csrc.gov.cn/pub/newsite/rss.xml",
                "央行": "http://www.pbc.gov.cn/rss.xml",
            },
            "📰 综合财经媒体": {
                "新浪财经": "https://finance.sina.com.cn/rss.xml",
                "腾讯财经": "https://finance.qq.com/rss.xml",
                "网易财经": "https://money.163.com/rss.xml",
                "搜狐财经": "https://business.sohu.com/rss.xml",
                "凤凰财经": "http://finance.ifeng.com/rss/headnews.xml",
                "凤凰财经-股票": "http://finance.ifeng.com/rss/stocknews.xml",
                "凤凰财经-基金": "http://finance.ifeng.com/rss/fundnews.xml",
                "百度财经": "http://news.baidu.com/n?cmd=1&class=stock&tn=rss&sub=0",
            },
            "🌏 国际财经": {
                "路透中文": "https://cn.reuters.com/rssFeed/chinaNews",
                "路透财经": "https://cn.reuters.com/rssFeed/mostViewed",
                "FT中文网": "https://www.ftchinese.com/rss.xml",
                "华尔街日报中文": "https://cn.wsj.com/rss.xml",
                "彭博中文": "https://www.bloomberg.com/feeds/china.rss",
                "香港经济日报": "https://www.hket.com/rss/china",
                "香港01财经": "https://www.hk01.com/rss/finance.xml",
            },
            "🇺🇸 美国财经": {
                "华尔街日报-经济": "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness",
                "华尔街日报-市场": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
                "MarketWatch": "https://www.marketwatch.com/rss/topstories",
                "CNBC": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
                "ZeroHedge": "https://feeds.feedburner.com/zerohedge/feed",
                "ETF Trends": "https://www.etftrends.com/feed/",
                "Yahoo Finance": "https://finance.yahoo.com/rss/",
                "Bloomberg": "https://www.bloomberg.com/feeds/markets.rss",
            },
            "🌍 全球财经": {
                "BBC Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
                "Financial Times": "https://www.ft.com/rss/home",
                "The Economist": "https://www.economist.com/rss",
                "Reuters Business": "https://www.reuters.com/rssFeed/businessNews",
            },
            "💎 行业专业媒体": {
                "证券日报": "https://www.zqrb.cn/rss.xml",
                "投资界": "https://www.pedaily.cn/rss.xml",
                "投资快报": "https://www.9ifund.com/rss.xml",
                "格隆汇": "https://www.gelonghui.com/rss.xml",
            },
        }
    
    def _init_api_sources(self) -> Dict:
        """初始化API数据源配置"""
        return {
            "聚合数据-财经新闻": {
                "url": "https://api.juheapi.com/japi/toh",
                "requires_key": True,
                "key_env": "JUHE_API_KEY",
            },
            "天行数据-财经新闻": {
                "url": "https://api.tianapi.com/generalnews/index",
                "requires_key": True,
                "key_env": "TIANAPI_KEY",
            },
        }
    
    def fetch_rss_feed(self, url: str, retries: int = 3, delay: int = 2) -> Optional[feedparser.FeedParserDict]:
        """获取RSS源数据（带重试）"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        for i in range(retries):
            try:
                feed = feedparser.parse(url, request_headers=headers)
                if feed and hasattr(feed, 'entries') and len(feed.entries) > 0:
                    return feed
            except Exception as e:
                print(f"⚠️ 第 {i+1} 次请求 {url} 失败: {e}")
                if i < retries - 1:
                    time.sleep(delay)
        
        return None
    
    def fetch_article_content(self, url: str, max_length: int = 2000) -> str:
        """爬取文章正文内容"""
        try:
            article = Article(url)
            article.download()
            article.parse()
            text = article.text[:max_length] if article.text else ""
            return text if text else "（未能获取文章正文）"
        except Exception as e:
            print(f"⚠️ 文章爬取失败: {url}, 错误: {e}")
            return "（未能获取文章正文）"
    
    def get_all_news(self, max_articles_per_source: int = 5) -> tuple:
        """
        获取所有新闻源的内容
        :param max_articles_per_source: 每个源最多获取的文章数
        :return: (news_data字典, analysis_text用于AI分析的文本)
        """
        news_data = {}
        analysis_text = ""
        successful_sources = 0
        total_articles = 0
        
        print(f"📡 开始获取新闻，共 {sum(len(sources) for sources in self.rss_feeds.values())} 个RSS源...")
        
        for category, sources in self.rss_feeds.items():
            category_content = ""
            category_articles = 0
            
            for source_name, url in sources.items():
                feed = self.fetch_rss_feed(url)
                
                if not feed:
                    # print(f"❌ {source_name} 获取失败")
                    continue
                
                # print(f"✅ {source_name} 获取成功，共 {len(feed.entries)} 条")
                successful_sources += 1
                articles = []
                
                # 按时间排序，取最新的文章
                sorted_entries = sorted(
                    feed.entries,
                    key=lambda x: getattr(x, 'published_parsed', (2000, 1, 1, 0, 0, 0, 0, 0, 0)),
                    reverse=True
                )
                
                for entry in sorted_entries[:max_articles_per_source]:
                    title = entry.get('title', '无标题')
                    link = entry.get('link', '') or entry.get('guid', '')
                    
                    if not link:
                        continue
                    
                    # 爬取正文用于AI分析
                    article_text = self.fetch_article_content(link)
                    if article_text and article_text != "（未能获取文章正文）":
                        analysis_text += f"【{source_name} - {title}】\n{article_text}\n\n"
                        category_articles += 1
                        total_articles += 1
                    
                    articles.append(f"- [{title}]({link})")
                
                if articles:
                    category_content += f"### {source_name}\n" + "\n".join(articles) + "\n\n"
            
            if category_content:
                news_data[category] = category_content
                print(f"✅ {category} 获取完成，共 {category_articles} 篇文章")
        
        print(f"\n📊 新闻获取统计:")
        print(f"  ✅ 成功源: {successful_sources}/{sum(len(sources) for sources in self.rss_feeds.values())}")
        print(f"  📰 总文章数: {total_articles}")
        print(f"  📝 AI分析文本长度: {len(analysis_text)} 字符")
        
        return news_data, analysis_text
    
    def get_stock_specific_news(self, stock_code: str, max_articles: int = 10) -> List[Dict]:
        """
        获取特定股票的新闻（通过搜索）
        :param stock_code: 股票代码
        :param max_articles: 最多返回的文章数
        :return: 新闻列表
        """
        # 这个方法可以通过API或搜索实现
        # 暂时返回空，后续可以接入股票新闻API
        return []
    
    def get_recent_hot_stocks_from_news(self, analysis_text: str, top_n: int = 10) -> List[str]:
        """
        从新闻文本中提取最常提到的股票代码
        :param analysis_text: 新闻文本
        :param top_n: 返回前N只
        :return: 股票代码列表
        """
        import re
        # 提取6位股票代码
        stock_codes = re.findall(r'\b([036]\d{5})\b', analysis_text)
        
        # 统计出现频率
        from collections import Counter
        code_counts = Counter(stock_codes)
        
        # 返回出现频率最高的股票代码
        return [code for code, _ in code_counts.most_common(top_n)]
    
    def filter_duplicate_articles(self, articles: List[Dict]) -> List[Dict]:
        """
        过滤重复的文章（基于标题相似度）
        :param articles: 文章列表
        :return: 去重后的文章列表
        """
        seen_titles = set()
        unique_articles = []
        
        for article in articles:
            title = article.get('title', '').lower().strip()
            # 简单的去重：检查标题是否已存在
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_articles.append(article)
        
        return unique_articles


class NewsSourceConfig:
    """新闻源配置管理器（可从配置文件加载）"""
    
    @staticmethod
    def load_from_file(filepath: str = "news_sources.json") -> Dict:
        """从JSON文件加载新闻源配置"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ 配置文件 {filepath} 不存在，使用默认配置")
            return {}
    
    @staticmethod
    def save_to_file(config: Dict, filepath: str = "news_sources.json"):
        """保存新闻源配置到JSON文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)


# 便捷函数
def get_enhanced_news_sources() -> EnhancedNewsSources:
    """获取增强的新闻源实例"""
    return EnhancedNewsSources()


# 使用示例
if __name__ == "__main__":
    sources = EnhancedNewsSources()
    news_data, analysis_text = sources.get_all_news(max_articles_per_source=3)
    
    print(f"\n获取到的新闻数据:")
    for category, content in news_data.items():
        print(f"\n{category}:")
        print(content[:200] + "..." if len(content) > 200 else content)
