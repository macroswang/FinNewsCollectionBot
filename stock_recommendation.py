"""
股票推荐机制重构模块

提供模块化、清晰的股票推荐功能
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class StockCategory(Enum):
    """股票分类"""
    HOT_SECTOR = "hot_sector"  # 热点板块
    ROTATION = "rotation"  # 轮动机会


@dataclass
class StockRecommendation:
    """股票推荐数据模型"""
    code: str
    name: str
    category: StockCategory
    reason: str = ""
    risk: str = "中"
    short_term_potential: str = "中"
    holding_period: str = "2-4天"
    entry_strategy: str = "回调买入"
    exit_strategy: str = "分批止盈"
    support_resistance: str = "待获取"
    current_price: str = "待获取"
    market_cap: Optional[float] = None  # 市值（亿元）
    real_time_data: Optional[Dict] = None  # 实时数据
    
    def update_with_realtime_data(self, realtime_data: Dict):
        """使用实时数据更新股票信息"""
        self.real_time_data = realtime_data
        
        # 更新市值
        if realtime_data.get("market_cap") and realtime_data["market_cap"] != 'N/A':
            market_cap = realtime_data["market_cap"]
            if isinstance(market_cap, (int, float)):
                self.market_cap = market_cap / 100000000  # 转换为亿元
        
        # 更新当前价格
        if realtime_data.get("current_price"):
            self.current_price = f"{realtime_data['current_price']:.2f}"
    
    def get_market_cap_str(self) -> str:
        """获取市值字符串"""
        if self.market_cap:
            return f"，市值约{self.market_cap:.0f}亿"
        return ""
    
    def validate(self) -> Tuple[bool, str]:
        """验证股票推荐数据的有效性"""
        if not self.code or len(self.code) != 6 or not self.code.isdigit():
            return False, "股票代码格式不正确"
        if not self.name or self.name == "未知":
            return False, "股票名称缺失"
        return True, ""


class StockDataFetcher:
    """股票数据获取器"""
    
    def __init__(self, get_realtime_data_func):
        """
        初始化
        :param get_realtime_data_func: 获取实时数据的函数
        """
        self.get_realtime_data = get_realtime_data_func
    
    def fetch_stock_data(self, stock_code: str) -> Optional[Dict]:
        """
        获取股票实时数据
        :param stock_code: 股票代码
        :return: 实时数据字典
        """
        try:
            print(f"📊 正在获取{stock_code}的实时数据...")
            data = self.get_realtime_data(stock_code)
            if data:
                print(f"✅ {stock_code} 数据获取成功")
            return data
        except Exception as e:
            print(f"⚠️ 获取{stock_code}实时数据失败: {e}")
            return None
    
    def fetch_multiple_stocks(self, stock_codes: List[str]) -> Dict[str, Dict]:
        """
        批量获取多只股票的数据
        :param stock_codes: 股票代码列表
        :return: {股票代码: 数据} 字典
        """
        results = {}
        for code in stock_codes:
            data = self.fetch_stock_data(code)
            if data:
                results[code] = data
        return results


class StockRecommendationExtractor:
    """股票推荐提取器 - 从AI摘要中提取股票信息"""
    
    def __init__(self, check_market_cap_func, news_content=None):
        """
        初始化
        :param check_market_cap_func: 检查市值的函数
        :param news_content: 原始新闻内容（用于验证推荐理由是否基于新闻）
        """
        self.check_market_cap = check_market_cap_func
        self.news_content = news_content or ""
    
    def extract_from_summary(self, summary: str) -> Dict[str, List[StockRecommendation]]:
        """
        从AI摘要中提取股票推荐信息
        :param summary: AI生成的摘要
        :return: {"hot_sector_stocks": [...], "rotation_stocks": [...], "all_stocks_in_summary": [...]}
        """
        stock_recommendations = {
            "hot_sector_stocks": [],
            "rotation_stocks": [],
            "all_stocks_in_summary": []
        }
        
        if not self._has_stock_recommendations(summary):
            return stock_recommendations
        
        lines = summary.split('\n')
        in_hot_stocks = False
        in_rotation_stocks = False
        
        for line in lines:
            line = line.strip()
            
            # 检测章节标题
            category_flag = self._detect_category(line)
            if category_flag == "hot":
                in_hot_stocks = True
                in_rotation_stocks = False
                continue
            elif category_flag == "rotation":
                in_hot_stocks = False
                in_rotation_stocks = True
                continue
            elif category_flag == "other":
                in_hot_stocks = False
                in_rotation_stocks = False
                continue
            
            # 提取股票信息
            if (in_hot_stocks or in_rotation_stocks) and self._is_stock_line(line):
                stock = self._parse_stock_line(line, in_hot_stocks)
                if stock and stock.validate()[0]:
                    # 验证推荐理由是否基于新闻内容
                    if self._verify_recommendation_based_on_news(stock):
                        stock_recommendations["all_stocks_in_summary"].append(stock)
                        
                        # 检查市值，决定是否添加到推荐列表
                        if self.check_market_cap(stock.code):
                            if in_hot_stocks:
                                stock_recommendations["hot_sector_stocks"].append(stock)
                            elif in_rotation_stocks:
                                stock_recommendations["rotation_stocks"].append(stock)
                        else:
                            print(f"❌ {stock.code} {stock.name} 市值不符合中小盘标准，已过滤")
                    else:
                        print(f"⚠️ {stock.code} {stock.name} 推荐理由未明确引用新闻内容，已过滤")
        
        return stock_recommendations
    
    def _has_stock_recommendations(self, summary: str) -> bool:
        """检查摘要中是否包含股票推荐"""
        return (
            "具体股票推荐" in summary or
            "热点板块股票" in summary or
            "轮动机会股票" in summary or
            "A股" in summary or
            bool(re.search(r'\b\d{6}\b', summary))
        )
    
    def _detect_category(self, line: str) -> Optional[str]:
        """检测行是否属于某个股票分类章节"""
        if "热点板块股票" in line or ("📈" in line and "A股" in line):
            return "hot"
        elif "轮动机会股票" in line or ("🔄" in line and "A股" in line):
            return "rotation"
        elif line.startswith('##') or line.startswith('###'):
            return "other"
        return None
    
    def _is_stock_line(self, line: str) -> bool:
        """判断是否可能是股票信息行"""
        if not line or len(line) < 3:
            return False
        
        # 包含6位数字股票代码，或者以特定符号开头
        has_stock_code = bool(re.search(r'\b\d{6}\b', line))
        starts_with_symbol = line.startswith('-') or line.startswith('•') or line.startswith('*')
        
        return has_stock_code or starts_with_symbol
    
    def _parse_stock_line(self, line: str, is_hot_sector: bool) -> Optional[StockRecommendation]:
        """
        解析股票信息行
        :param line: 股票信息行
        :param is_hot_sector: 是否属于热点板块
        :return: StockRecommendation 对象
        """
        try:
            # 移除开头符号
            clean_line = line.lstrip('-•*').strip()
            
            # 提取股票代码
            code_match = re.search(r'\b(\d{6})\b', clean_line)
            if not code_match:
                return None
            
            stock_code = code_match.group(1)
            
            # 提取股票名称
            stock_name = self._extract_stock_name(clean_line, stock_code)
            
            # 确定分类
            category = StockCategory.HOT_SECTOR if is_hot_sector else StockCategory.ROTATION
            
            # 提取详细信息
            stock = StockRecommendation(
                code=stock_code,
                name=stock_name,
                category=category
            )
            
            # 解析推荐理由格式
            if '推荐理由：' in clean_line or '推荐理由:' in clean_line:
                self._parse_detailed_format(clean_line, stock)
            else:
                self._parse_simple_format(clean_line, stock)
            
            return stock
            
        except Exception as e:
            print(f"⚠️ 解析股票信息失败: {line}, 错误: {e}")
            return None
    
    def _extract_stock_name(self, line: str, stock_code: str) -> str:
        """提取股票名称"""
        # 尝试从粗体格式中提取
        bold_match = re.search(rf'\*\*{re.escape(stock_code)}\s+([^*]+)\*\*', line)
        if bold_match:
            return bold_match.group(1).strip()
        
        # 尝试从代码后的文字中提取
        name_match = re.search(rf'{re.escape(stock_code)}\s+([^\s：:，,。]+)', line)
        if name_match:
            return name_match.group(1).strip()
        
        return "未知"
    
    def _parse_detailed_format(self, line: str, stock: StockRecommendation):
        """解析详细格式的股票信息（包含推荐理由、风险等级等）"""
        # 提取推荐理由
        reason_match = re.search(r'推荐理由[：:]([^。]+)', line)
        if reason_match:
            stock.reason = reason_match.group(1).strip()
        
        # 提取风险等级
        risk_match = re.search(r'风险等级[：:]([^。]+)', line)
        if risk_match:
            stock.risk = risk_match.group(1).strip()
        
        # 提取短线潜力
        potential_match = re.search(r'短线潜力[：:]([^。]+)', line)
        if potential_match:
            stock.short_term_potential = potential_match.group(1).strip()
        
        # 提取持仓时间
        holding_match = re.search(r'(?:建议)?持仓时间[：:]([^。]+)', line)
        if holding_match:
            stock.holding_period = holding_match.group(1).strip()
        
        # 提取买入策略
        entry_match = re.search(r'买入策略[：:]([^。]+)', line)
        if entry_match:
            stock.entry_strategy = entry_match.group(1).strip()
        
        # 提取卖出策略
        exit_match = re.search(r'卖出策略[：:]([^。]+)', line)
        if exit_match:
            stock.exit_strategy = exit_match.group(1).strip()
        
        # 提取技术面信息
        tech_match = re.search(r'技术面[：:]([^。]+)', line)
        if tech_match:
            stock.support_resistance = tech_match.group(1).strip()
        
        # 提取市值信息（如果存在）
        market_cap_match = re.search(r'市值约?(\d+(?:\.\d+)?)亿', line)
        if market_cap_match:
            try:
                stock.market_cap = float(market_cap_match.group(1))
            except:
                pass
    
    def _parse_simple_format(self, line: str, stock: StockRecommendation):
        """解析简单格式的股票信息"""
        # 如果包含冒号，尝试解析冒号后的内容
        if '：' in line or ':' in line:
            separator = '：' if '：' in line else ':'
            parts = line.split(separator, 1)
            if len(parts) > 1:
                details = parts[1].strip()
                # 尝试从详细信息中提取
                self._parse_detailed_format(details, stock)
    
    def _verify_recommendation_based_on_news(self, stock: StockRecommendation) -> bool:
        """
        验证推荐理由是否基于新闻内容
        :param stock: 股票推荐对象
        :return: True表示推荐理由有效（基于新闻），False表示无效
        """
        if not self.news_content:
            # 如果没有提供新闻内容，无法验证，默认通过
            return True
        
        reason = stock.reason.lower()
        
        # 检查推荐理由中是否包含新闻引用关键词
        news_keywords = [
            "新闻中提到", "新闻中报道", "新闻显示", "新闻称", "新闻指出",
            "根据新闻", "基于新闻", "新闻内容", "报道称", "消息称",
            "公告", "政策", "事件", "业绩", "数据", "会议", "决议"
        ]
        
        has_news_reference = any(keyword in reason for keyword in news_keywords)
        
        # 如果推荐理由中没有明确引用新闻，检查是否只是通用描述
        if not has_news_reference:
            # 检查是否是通用的、非新闻相关的描述
            generic_phrases = [
                "龙头", "基本面", "长期看好", "行业领先", "技术先进",
                "市场份额", "竞争优势", "财务稳健"  # 这些可能是训练数据中的通用知识
            ]
            
            # 如果推荐理由只包含通用描述，没有新闻相关关键词，认为无效
            if any(phrase in reason for phrase in generic_phrases) and len(reason) < 30:
                print(f"  ⚠️ 推荐理由疑似使用通用知识：{stock.reason[:50]}...")
                return False
        
        # 进一步验证：检查推荐理由中的关键词是否在新闻中出现
        if self.news_content and len(reason) > 0:
            # 提取推荐理由中的关键词（去除常见词）
            import re
            # 提取推荐理由中的主要名词和关键词
            keywords = re.findall(r'[\u4e00-\u9fa5]{2,}', reason)
            
            # 检查是否有关键词在新闻中出现（至少一个关键词匹配）
            news_lower = self.news_content.lower()
            matched_keywords = [kw for kw in keywords if kw in news_lower]
            
            if matched_keywords:
                print(f"  ✅ 推荐理由与新闻内容匹配（关键词：{matched_keywords[:3]}）")
                return True
            elif has_news_reference:
                # 有新闻引用关键词但关键词未匹配，可能是跨行提取的问题，给予通过
                return True
        
        return has_news_reference


class StockRecommendationUpdater:
    """股票推荐更新器 - 使用实时数据更新股票信息"""
    
    def __init__(self, data_fetcher: StockDataFetcher):
        """
        初始化
        :param data_fetcher: 数据获取器
        """
        self.data_fetcher = data_fetcher
    
    def update_stocks(self, stocks: List[StockRecommendation]) -> List[StockRecommendation]:
        """
        批量更新股票信息
        :param stocks: 股票推荐列表
        :return: 更新后的股票推荐列表
        """
        updated_stocks = []
        for stock in stocks:
            updated_stock = self.update_single_stock(stock)
            if updated_stock:
                updated_stocks.append(updated_stock)
        return updated_stocks
    
    def update_single_stock(self, stock: StockRecommendation) -> Optional[StockRecommendation]:
        """
        更新单个股票信息
        :param stock: 股票推荐对象
        :return: 更新后的股票推荐对象
        """
        try:
            realtime_data = self.data_fetcher.fetch_stock_data(stock.code)
            if realtime_data:
                stock.update_with_realtime_data(realtime_data)
                return stock
        except Exception as e:
            print(f"⚠️ 更新{stock.code}失败: {e}")
        return stock
    
    def update_summary_with_realtime_data(
        self, 
        summary: str, 
        stocks: List[StockRecommendation]
    ) -> str:
        """
        在AI摘要中用实时数据更新股票信息
        :param summary: 原始摘要
        :param stocks: 股票推荐列表（已更新实时数据）
        :return: 更新后的摘要
        """
        updated_summary = summary
        
        for stock in stocks:
            if stock.real_time_data:
                new_stock_block = self._generate_stock_block(stock)
                
                # 在摘要中查找并替换
                old_pattern = f"**{stock.code} {stock.name}**"
                if old_pattern in updated_summary:
                    pattern = rf"{re.escape(old_pattern)}.*?(?=\*\*\d{{6}}\s+\w+|\n##|\n###|\Z)"
                    updated_summary = re.sub(
                        pattern, 
                        new_stock_block.rstrip(), 
                        updated_summary, 
                        flags=re.DOTALL
                    )
                    print(f"✅ 已更新 {stock.code} {stock.name} 的实时数据")
        
        return updated_summary
    
    def _generate_stock_block(self, stock: StockRecommendation) -> str:
        """生成股票信息块（用于更新AI摘要）"""
        block = f"**{stock.code} {stock.name}**\n\n"
        
        # 推荐理由（包含市值）
        reason = stock.reason
        if stock.get_market_cap_str() and '市值' not in reason:
            reason += stock.get_market_cap_str()
        block += f"- **推荐理由**：{reason}\n\n"
        
        # 其他信息
        block += f"- **风险等级**：{stock.risk}\n\n"
        block += f"- **短线潜力**：{stock.short_term_potential}\n\n"
        block += f"- **建议持仓时间**：{stock.holding_period}\n\n"
        block += f"- **买入策略**：{stock.entry_strategy}\n\n"
        block += f"- **卖出策略**：{stock.exit_strategy}\n\n"
        
        # 技术面
        if stock.real_time_data:
            support = stock.real_time_data.get('recent_low', stock.real_time_data.get('current_price', 0))
            resistance = stock.real_time_data.get('recent_high', stock.real_time_data.get('current_price', 0))
            ma20 = stock.real_time_data.get('ma20')
            ma20_info = f"（20日均线{ma20:.2f}元）" if ma20 else ""
            block += f"- **技术面**：支撑位{support:.2f}元{ma20_info}，阻力位{resistance:.2f}元（前高）\n\n"
        
        # 当前数据
        if stock.real_time_data:
            price = stock.real_time_data.get('current_price', 0)
            change = stock.real_time_data.get('price_change', 0)
            emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "待获取"
            
            volume_info = ""
            volume_ratio = stock.real_time_data.get("volume_ratio", 1)
            if volume_ratio > 1.5:
                volume_info = "，成交量放大"
            elif volume_ratio > 1:
                volume_info = "，成交量略有增加"
            else:
                volume_info = "，成交量萎缩"
            
            block += f"- **当前数据**：约{price:.2f}元{emoji}，近期涨幅{change_str}{volume_info}\n"
        
        return block


class StockRecommendationFormatter:
    """股票推荐格式化器 - 负责格式化输出"""
    
    @staticmethod
    def format_stock_recommendation(stock: StockRecommendation) -> str:
        """格式化单个股票推荐"""
        output = f"**{stock.code} {stock.name}**\n"
        output += f"推荐理由：{stock.reason}{stock.get_market_cap_str()}。\n"
        output += f"风险等级：{stock.risk}。\n"
        output += f"短线潜力：{stock.short_term_potential}。\n"
        output += f"建议持仓时间：{stock.holding_period}。\n"
        output += f"买入策略：{stock.entry_strategy}。\n"
        output += f"卖出策略：{stock.exit_strategy}\n"
        
        # 添加实时数据（优先显示）
        if stock.real_time_data:
            output += "\n" + StockRecommendationFormatter._format_realtime_data(stock.real_time_data)
        else:
            output += "\n⚠️ **实时数据获取中...**\n"
        
        return output + "\n"
    
    @staticmethod
    def _format_realtime_data(data: Dict) -> str:
        """格式化实时数据"""
        output = "**📊 实时数据（A股）**\n"
        
        # 价格和涨跌幅
        price = data.get('current_price', 0)
        change = data.get('price_change', 0)
        emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
        source_emoji = "⚡" if "实时" in data.get("data_source", "") else "📊"
        update_time = data.get('update_time', '实时')
        
        output += f"- **当前股价**：¥{price:.2f} {emoji} {change:+.2f}% {source_emoji} {data.get('data_source', '实时数据')}\n"
        if update_time and update_time != '未知' and update_time != '实时':
            output += f"- **数据时间**：{update_time}\n"
        
        # 技术面
        if data.get("ma20") and data.get("ma50"):
            trend = "上涨" if price > data["ma20"] else "下跌" if price < data["ma20"] else "震荡"
            trend_emoji = "📈" if trend == "上涨" else "📉" if trend == "下跌" else "➡️"
            output += f"- **技术面**：{trend_emoji} {trend} | MA20: ¥{data['ma20']:.2f} | MA50: ¥{data['ma50']:.2f}\n"
        
        # 支撑阻力位
        if data.get("recent_low") and data.get("recent_high"):
            output += f"- **支撑/阻力**：¥{data['recent_low']:.2f} / ¥{data['recent_high']:.2f}\n"
        
        # 成交量
        if data.get("volume_ratio"):
            volume_emoji = "🔥" if data["volume_ratio"] > 1.5 else "📊" if data["volume_ratio"] > 1 else "📉"
            output += f"- **成交量**：{volume_emoji} {data['volume_ratio']:.1f}倍（较20日均量）\n"
        
        # 估值
        if data.get("pe_ratio") and data["pe_ratio"] != 'N/A':
            pe_str = f"{data['pe_ratio']:.1f}" if isinstance(data['pe_ratio'], (int, float)) else str(data['pe_ratio'])
            pb_str = f"{data['pb_ratio']:.2f}" if data.get("pb_ratio") and data["pb_ratio"] != 'N/A' and isinstance(data['pb_ratio'], (int, float)) else 'N/A'
            output += f"- **估值指标**：PE {pe_str} | PB {pb_str}\n"
        
        # 市值（如果有）
        if data.get("market_cap") and data["market_cap"] != 'N/A':
            market_cap_billion = data["market_cap"] / 100000000 if isinstance(data["market_cap"], (int, float)) else 0
            if market_cap_billion > 0:
                output += f"- **市值**：约{market_cap_billion:.0f}亿元\n"
        
        return output
    
    @staticmethod
    def format_stock_section(
        category_name: str,
        stocks: List[StockRecommendation],
        max_count: int = 3
    ) -> str:
        """格式化股票推荐分类部分"""
        if not stocks:
            return ""
        
        output = f"### {category_name}\n"
        for stock in stocks[:max_count]:
            output += StockRecommendationFormatter.format_stock_recommendation(stock)
        
        return output + "\n"


class StockRecommendationManager:
    """股票推荐管理器 - 主协调器"""
    
    def __init__(
        self,
        get_realtime_data_func,
        check_market_cap_func,
        get_stock_industry_func=None,
        news_content=None
    ):
        """
        初始化
        :param get_realtime_data_func: 获取实时数据的函数
        :param check_market_cap_func: 检查市值的函数
        :param get_stock_industry_func: 获取股票行业的函数（可选）
        :param news_content: 原始新闻内容（用于验证推荐是否基于新闻）
        """
        self.data_fetcher = StockDataFetcher(get_realtime_data_func)
        self.extractor = StockRecommendationExtractor(check_market_cap_func, news_content)
        self.updater = StockRecommendationUpdater(self.data_fetcher)
        self.formatter = StockRecommendationFormatter()
        self.get_stock_industry = get_stock_industry_func
    
    def process_summary(self, summary: str) -> Tuple[str, Dict[str, List[StockRecommendation]]]:
        """
        处理AI摘要，提取、更新股票推荐
        :param summary: AI生成的摘要
        :return: (更新后的摘要, 提取的股票推荐字典)
        """
        # 1. 提取股票推荐
        extracted = self.extractor.extract_from_summary(summary)
        
        # 2. 更新所有股票的实时数据
        all_stocks = extracted["all_stocks_in_summary"]
        updated_stocks = self.updater.update_stocks(all_stocks)
        
        # 更新提取结果中的股票列表
        extracted["all_stocks_in_summary"] = updated_stocks
        
        # 3. 用实时数据更新摘要
        updated_summary = self.updater.update_summary_with_realtime_data(
            summary, 
            updated_stocks
        )
        
        return updated_summary, extracted
    
    def generate_stock_recommendations_section(
        self,
        extracted: Dict[str, List[StockRecommendation]]
    ) -> str:
        """
        生成股票推荐部分（用于AI摘要中没有股票推荐的情况）
        :param extracted: 提取的股票推荐字典
        :return: 格式化的股票推荐文本
        """
        if not extracted["hot_sector_stocks"] and not extracted["rotation_stocks"]:
            return ""
        
        output = "## 🎯 具体股票推荐（仅限A股）\n\n"
        
        # 更新热点板块股票和轮动机会股票的实时数据
        hot_stocks = self.updater.update_stocks(extracted["hot_sector_stocks"])
        rotation_stocks = self.updater.update_stocks(extracted["rotation_stocks"])
        
        # 验证行业分类（可选）
        if self.get_stock_industry:
            for stock in hot_stocks + rotation_stocks:
                try:
                    industry = self.get_stock_industry(stock.code)
                    print(f"✅ {stock.code} {stock.name} 属于{industry}行业")
                except:
                    pass
        
        # 格式化输出
        if hot_stocks:
            output += self.formatter.format_stock_section(
                "📈 热点板块股票（A股）",
                hot_stocks
            )
        
        if rotation_stocks:
            output += self.formatter.format_stock_section(
                "🔄 轮动机会股票（A股）",
                rotation_stocks
            )
        
        if output:
            output += "⚠️ **投资提醒**: 以上推荐基于今日新闻动态生成，仅供参考，投资有风险，入市需谨慎！\n\n"
            output += self._generate_strategy_section()
        
        return output
    
    @staticmethod
    def _generate_strategy_section() -> str:
        """生成交易策略部分"""
        section = "## 💡 散户短线交易策略\n\n"
        section += "### 📈 建仓策略\n"
        section += "- **分批建仓**: 建议分2-3次建仓，降低单次风险\n"
        section += "- **仓位控制**: 单只股票不超过总仓位的5-8%（资金量有限）\n"
        section += "- **时机把握**: 关注回调机会，避免追高\n"
        section += "- **快进快出**: 1-5个交易日完成交易\n\n"
        
        section += "### 🛡️ 风险控制\n"
        section += "- **止损设置**: 严格执行止损，不超过-3%\n"
        section += "- **止盈策略**: 分批止盈，目标≤10%\n"
        section += "- **分散投资**: 避免过度集中在单一行业\n"
        section += "- **资金管理**: 预留30%资金应对机会\n\n"
        
        section += "### 📊 短线操作要点\n"
        section += "- **每日检视**: 每个交易日评估持仓表现\n"
        section += "- **及时止盈**: 达到目标及时卖出，不贪心\n"
        section += "- **严格止损**: 触及止损位立即卖出\n"
        section += "- **关注量能**: 成交量是短线交易的重要指标\n\n"
        
        return section
