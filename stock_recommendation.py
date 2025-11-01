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
        current_price = realtime_data.get("current_price", 0)
        if current_price and current_price > 0:
            self.current_price = f"{current_price:.2f}"
            
            # 基于实时价格更新买入/卖出策略
            self._update_strategies_with_realtime_price(current_price, realtime_data)
        
        # 更新技术面数据
        if realtime_data.get("recent_low") and realtime_data.get("recent_high"):
            support = realtime_data.get("recent_low", 0)
            resistance = realtime_data.get("recent_high", 0)
            if support > 0 and resistance > 0:
                self.support_resistance = f"支撑位{support:.2f}元，阻力位{resistance:.2f}元"
    
    def _update_strategies_with_realtime_price(self, current_price: float, realtime_data: Dict):
        """基于实时价格更新买入/卖出策略"""
        # 计算回调买入价位（回调3-8%）
        buy_price_low = current_price * 0.92  # 回调8%
        buy_price_high = current_price * 0.97  # 回调3%
        
        # 计算止盈价位（目标涨幅5-10%）
        sell_price_low = current_price * 1.05  # 涨幅5%
        sell_price_high = current_price * 1.10  # 涨幅10%
        
        # 获取支撑位和阻力位
        support = realtime_data.get("recent_low", buy_price_low)
        resistance = realtime_data.get("recent_high", sell_price_high)
        ma20 = realtime_data.get("ma20")
        
        # 更新买入策略
        if "回调" in self.entry_strategy or "买入" in self.entry_strategy:
            # 如果有支撑位，使用支撑位作为买入参考
            if support and support < current_price:
                entry_price = max(support, buy_price_low)
                self.entry_strategy = f"回调至{entry_price:.2f}元附近分批买入"
            elif ma20 and ma20 < current_price:
                # 使用20日均线作为买入参考
                self.entry_strategy = f"回调至{ma20:.2f}元（20日均线）附近分批买入"
            else:
                self.entry_strategy = f"回调至{buy_price_low:.2f}-{buy_price_high:.2f}元区间分批买入"
        else:
            # 如果原策略中没有价格信息，添加实时价格参考
            if current_price > 0:
                self.entry_strategy = f"当前价{current_price:.2f}元，回调至{buy_price_low:.2f}-{buy_price_high:.2f}元分批买入"
        
        # 更新卖出策略
        if "止盈" in self.exit_strategy or "卖出" in self.exit_strategy:
            # 如果有阻力位，使用阻力位作为卖出参考
            if resistance and resistance > current_price:
                exit_price = min(resistance, sell_price_high)
                self.exit_strategy = f"{exit_price:.2f}元附近分批止盈"
            else:
                self.exit_strategy = f"{sell_price_low:.2f}-{sell_price_high:.2f}元分批止盈"
        else:
            # 如果原策略中没有价格信息，添加实时价格参考
            if current_price > 0:
                self.exit_strategy = f"{sell_price_low:.2f}-{sell_price_high:.2f}元分批止盈（目标涨幅5-10%）"
    
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
        current_stock_lines = []  # 收集当前股票的多行信息
        current_stock_code = None
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # 检测章节标题
            category_flag = self._detect_category(line)
            if category_flag == "hot":
                in_hot_stocks = True
                in_rotation_stocks = False
                # 处理之前收集的股票信息
                if current_stock_code:
                    stock = self._parse_multi_line_stock(current_stock_lines, in_hot_stocks, current_stock_code)
                    if stock:
                        self._add_stock_to_recommendations(stock, stock_recommendations, in_hot_stocks, in_rotation_stocks)
                current_stock_lines = []
                current_stock_code = None
                continue
            elif category_flag == "rotation":
                in_hot_stocks = False
                in_rotation_stocks = True
                # 处理之前收集的股票信息
                if current_stock_code:
                    stock = self._parse_multi_line_stock(current_stock_lines, in_hot_stocks, current_stock_code)
                    if stock:
                        self._add_stock_to_recommendations(stock, stock_recommendations, in_hot_stocks, in_rotation_stocks)
                current_stock_lines = []
                current_stock_code = None
                continue
            elif category_flag == "other":
                # 处理之前收集的股票信息
                if current_stock_code:
                    stock = self._parse_multi_line_stock(current_stock_lines, in_hot_stocks, current_stock_code)
                    if stock:
                        self._add_stock_to_recommendations(stock, stock_recommendations, in_hot_stocks, in_rotation_stocks)
                current_stock_lines = []
                current_stock_code = None
                in_hot_stocks = False
                in_rotation_stocks = False
                continue
            
            # 检查是否是新股票的开始（粗体格式：**代码 名称**）
            if (in_hot_stocks or in_rotation_stocks):
                # 检查是否是股票标题行（可能没有**标记，只有代码和名称）
                stock_code_match = re.search(r'\*\*(\d{6})\s+([^*]+)\*\*', line)
                if not stock_code_match:
                    # 尝试匹配不带**的格式
                    stock_code_match = re.search(r'^(\d{6})\s+(\S+)', line)
                
                if stock_code_match:
                    # 处理之前收集的股票信息
                    if current_stock_code:
                        stock = self._parse_multi_line_stock(current_stock_lines, in_hot_stocks, current_stock_code)
                        if stock:
                            self._add_stock_to_recommendations(stock, stock_recommendations, in_hot_stocks, in_rotation_stocks)
                    # 开始新股票
                    current_stock_code = stock_code_match.group(1)
                    current_stock_lines = [line]
                elif current_stock_code:
                    # 继续收集当前股票的信息（直到遇到下一个股票或章节结束）
                    # 检查是否是下一个股票的标题
                    next_stock_match = re.search(r'^(\d{6})\s+\S+', line)
                    if next_stock_match and next_stock_match.group(1) != current_stock_code:
                        # 发现新股票，先处理当前股票
                        stock = self._parse_multi_line_stock(current_stock_lines, in_hot_stocks, current_stock_code)
                        if stock:
                            self._add_stock_to_recommendations(stock, stock_recommendations, in_hot_stocks, in_rotation_stocks)
                        # 开始新股票
                        current_stock_code = next_stock_match.group(1)
                        current_stock_lines = [line]
                    else:
                        # 继续收集当前股票的信息
                        current_stock_lines.append(line)
                elif self._is_stock_line(line):
                    # 单行格式的股票
                    stock = self._parse_stock_line(line, in_hot_stocks)
                    if stock:
                        self._add_stock_to_recommendations(stock, stock_recommendations, in_hot_stocks, in_rotation_stocks)
        
        # 处理最后收集的股票信息
        if current_stock_code:
            stock = self._parse_multi_line_stock(current_stock_lines, in_hot_stocks, current_stock_code)
            if stock:
                self._add_stock_to_recommendations(stock, stock_recommendations, in_hot_stocks, in_rotation_stocks)
        
        return stock_recommendations
    
    def _parse_multi_line_stock(self, lines: List[str], is_hot_sector: bool, stock_code: str) -> Optional[StockRecommendation]:
        """
        解析多行格式的股票信息
        :param lines: 股票信息的行列表
        :param is_hot_sector: 是否属于热点板块
        :param stock_code: 股票代码（已从标题行提取）
        :return: StockRecommendation 对象
        """
        try:
            # 合并所有行为一个字符串用于解析
            combined_text = '\n'.join(lines)
            
            # 提取股票名称（支持多种格式）
            stock_name = "未知"
            first_line = lines[0] if lines else ""
            # 尝试匹配 **代码 名称** 格式
            name_match = re.search(rf'\*\*{re.escape(stock_code)}\s+([^*]+)\*\*', first_line)
            if name_match:
                stock_name = name_match.group(1).strip()
            else:
                # 尝试匹配不带**的格式：代码 名称
                name_match = re.search(rf'{re.escape(stock_code)}\s+(\S+)', first_line)
                if name_match:
                    stock_name = name_match.group(1).strip()
            
            # 确定分类
            category = StockCategory.HOT_SECTOR if is_hot_sector else StockCategory.ROTATION
            
            # 创建股票对象
            stock = StockRecommendation(
                code=stock_code,
                name=stock_name,
                category=category
            )
            
            # 解析详细信息（从合并的文本中提取）
            self._parse_detailed_format(combined_text, stock)
            
            # 调试输出
            if not stock.reason or len(stock.reason.strip()) == 0:
                print(f"  ⚠️ {stock_code} {stock_name} 推荐理由提取失败")
                print(f"  原始文本:\n{combined_text[:500]}")
                # 尝试手动查找推荐理由
                if '- **推荐理由**：' in combined_text:
                    reason_start = combined_text.find('- **推荐理由**：') + len('- **推荐理由**：')
                    reason_end = combined_text.find('\n- **风险等级', reason_start)
                    if reason_end == -1:
                        reason_end = combined_text.find('\n\n', reason_start)
                    if reason_end == -1:
                        reason_end = len(combined_text)
                    stock.reason = combined_text[reason_start:reason_end].strip()
                    print(f"  ✅ 手动提取到推荐理由: {stock.reason[:100]}...")
            
            return stock
            
        except Exception as e:
            print(f"⚠️ 解析多行股票信息失败: {stock_code}, 错误: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _add_stock_to_recommendations(self, stock: StockRecommendation, stock_recommendations: Dict, 
                                     in_hot_stocks: bool, in_rotation_stocks: bool):
        """添加股票到推荐列表（包含验证逻辑）"""
        if not stock or not stock.validate()[0]:
            return
        
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
            # 显示被过滤的推荐理由，便于调试
            reason_preview = stock.reason[:80] if stock.reason else "(无推荐理由)"
            print(f"⚠️ {stock.code} {stock.name} 推荐理由未明确引用新闻内容，已过滤")
            print(f"   推荐理由预览: {reason_preview}...")
    
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
        # 提取推荐理由（支持跨行和换行，匹配更多格式）
        # 优先匹配 "- **推荐理由**：内容" 格式，内容可能跨多行
        patterns = [
            # 模式1：- **推荐理由**：内容（直到下一个字段或空行，支持换行）
            r'[-*•]?\s*\*\*推荐理由[：:]\*\*\s*(.+?)(?=\n\s*[-*•]?\s*\*\*(?:风险等级|短线潜力|建议持仓|买入策略|卖出策略|技术面)|\n\n|\n\s*[-*•]\s*\*\*风险等级|$)',
            # 模式2：推荐理由**：内容（不带前面的-）
            r'\*\*推荐理由[：:]\*\*\s*(.+?)(?=\n\s*[-*•]?\s*\*\*(?:风险等级|短线潜力|建议持仓|买入策略|卖出策略|技术面)|\n\n|$)',
            # 模式3：- **推荐理由：内容（**只包推荐理由）
            r'[-*•]?\s*\*\*推荐理由[：:]\s*(.+?)(?=\n\s*[-*•]?\s*\*\*(?:风险等级|短线潜力|建议持仓|买入策略|卖出策略|技术面)|\n\n|$)',
            # 模式4：推荐理由：内容（不带**，但要匹配换行后的内容）
            r'推荐理由[：:]\s*(.+?)(?=\n\s*[-*•]?\s*\*?\*?风险等级|\n\s*[-*•]?\s*\*?\*?短线潜力|\n\s*[-*•]?\s*\*?\*?建议持仓|\n\s*[-*•]?\s*\*?\*?买入策略|\n\s*[-*•]?\s*\*?\*?卖出策略|\n\s*[-*•]?\s*\*?\*?技术面|\n\n|$)',
            # 模式5：单行格式（最后尝试）
            r'推荐理由[：:]([^\n]+)',
        ]
        
        for i, pattern in enumerate(patterns):
            reason_match = re.search(pattern, line, re.DOTALL | re.MULTILINE)
            if reason_match:
                stock.reason = reason_match.group(1).strip()
                # 清理可能的换行和多余空格，但保留中文句号
                stock.reason = ' '.join(stock.reason.split())
                # 移除开头可能的换行和空格
                stock.reason = stock.reason.lstrip()
                print(f"  ✅ 使用模式{i+1}提取到推荐理由: {stock.reason[:80]}...")
                break
        
        # 如果所有模式都失败，尝试更简单的方法
        if not stock.reason or len(stock.reason.strip()) == 0:
            # 直接查找"- **推荐理由**："并提取到下一个字段
            if '- **推荐理由**：' in line or '- **推荐理由**:' in line:
                start_markers = ['- **推荐理由**：', '- **推荐理由**:', '**推荐理由**：', '**推荐理由**:']
                for marker in start_markers:
                    if marker in line:
                        start_pos = line.find(marker) + len(marker)
                        # 找到下一个字段的开始
                        end_markers = ['\n- **风险等级', '\n- **短线潜力', '\n- **建议持仓', '\n- **买入策略', '\n- **卖出策略', '\n- **技术面', '\n\n']
                        end_pos = len(line)
                        for em in end_markers:
                            pos = line.find(em, start_pos)
                            if pos != -1 and pos < end_pos:
                                end_pos = pos
                        stock.reason = line[start_pos:end_pos].strip()
                        if stock.reason:
                            stock.reason = ' '.join(stock.reason.split())
                            print(f"  ✅ 使用备用方法提取到推荐理由: {stock.reason[:80]}...")
                            break
        
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
        
        if not stock.reason or len(stock.reason.strip()) == 0:
            # 如果没有推荐理由，认为无效
            return False
        
        reason = stock.reason.lower()
        
        # 检查推荐理由中是否包含新闻引用关键词（扩展关键词列表）
        news_keywords = [
            "新闻中提到", "新闻中报道", "新闻显示", "新闻称", "新闻指出",
            "根据新闻", "基于新闻", "新闻内容", "报道称", "消息称",
            "公告", "政策", "事件", "业绩", "数据", "会议", "决议",
            "发布", "出台", "宣布", "披露", "公布", "显示", "表明",
            "财报", "季报", "年报", "公告", "通知", "决定"
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
            # 提取推荐理由中的主要名词和关键词（2-6字的词）
            keywords = re.findall(r'[\u4e00-\u9fa5]{2,6}', reason)
            # 过滤常见无意义词
            stop_words = {'该股', '作为', '存在', '具有', '处于', '属于', '通过', '可以', '能够', '应该', '可能'}
            keywords = [kw for kw in keywords if kw not in stop_words and len(kw) >= 2]
            
            # 检查是否有关键词在新闻中出现（至少一个关键词匹配）
            news_lower = self.news_content.lower()
            matched_keywords = [kw for kw in keywords[:10] if kw in news_lower]  # 只检查前10个关键词
            
            if matched_keywords:
                print(f"  ✅ {stock.code} 推荐理由与新闻内容匹配（关键词：{matched_keywords[:3]}）")
                return True
            elif has_news_reference:
                # 有新闻引用关键词但关键词未匹配，可能是跨行提取的问题，给予通过
                print(f"  ✅ {stock.code} 包含新闻引用关键词，通过验证")
                return True
        
        # 如果既没有新闻引用关键词，也没有匹配的关键词，但推荐理由较长且包含具体信息，可以放宽验证
        if len(reason) > 40 and not has_news_reference:
            # 检查是否包含具体的事件、公司、行业等信息
            specific_info_keywords = ['公司', '企业', '行业', '板块', '股票', '市场', '交易', '投资']
            if any(kw in reason for kw in specific_info_keywords):
                print(f"  ℹ️ {stock.code} 推荐理由较长且包含具体信息，放宽验证通过")
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
        if not stocks:
            print("⚠️ 没有股票需要更新实时数据")
            return []
        
        print(f"📊 开始批量更新 {len(stocks)} 只股票的实时数据...")
        updated_stocks = []
        for stock in stocks:
            updated_stock = self.update_single_stock(stock)
            if updated_stock:
                updated_stocks.append(updated_stock)
        
        print(f"✅ 批量更新完成，成功更新 {len(updated_stocks)}/{len(stocks)} 只股票")
        return updated_stocks
    
    def update_single_stock(self, stock: StockRecommendation) -> Optional[StockRecommendation]:
        """
        更新单个股票信息
        :param stock: 股票推荐对象
        :return: 更新后的股票推荐对象
        """
        try:
            print(f"🔄 正在更新 {stock.code} {stock.name} 的实时数据...")
            realtime_data = self.data_fetcher.fetch_stock_data(stock.code)
            if realtime_data:
                stock.update_with_realtime_data(realtime_data)
                if stock.real_time_data and stock.real_time_data.get("current_price"):
                    price = stock.real_time_data["current_price"]
                    change = stock.real_time_data.get("price_change", 0)
                    print(f"✅ {stock.code} {stock.name} 实时数据更新成功: ¥{price:.2f} ({change:+.2f}%)")
                return stock
            else:
                print(f"⚠️ {stock.code} {stock.name} 实时数据获取失败")
        except Exception as e:
            print(f"⚠️ 更新{stock.code} {stock.name}失败: {e}")
        return stock
    
    def update_summary_with_realtime_data(
        self, 
        summary: str, 
        stocks: List[StockRecommendation],
        check_market_cap_func=None
    ) -> str:
        """
        在AI摘要中用实时数据更新股票信息
        :param summary: 原始摘要
        :param stocks: 股票推荐列表（已更新实时数据）
        :param check_market_cap_func: 市值检查函数（可选，用于过滤大市值股票）
        :return: 更新后的摘要
        """
        updated_summary = summary
        
        for stock in stocks:
            # 如果提供了市值检查函数，只更新通过市值检查的股票，并从摘要中移除大市值股票
            if check_market_cap_func and not check_market_cap_func(stock.code):
                print(f"⚠️ {stock.code} {stock.name} 市值不符合标准，从摘要中移除大市值股票推荐")
                # 从摘要中移除该股票的所有内容
                old_patterns = [
                    f"**{stock.code} {stock.name}**",
                    f"{stock.code} {stock.name}",
                    f"**{stock.code}**",
                ]
                for old_pattern in old_patterns:
                    if old_pattern in updated_summary:
                        # 匹配从股票标题到下一个股票或章节结束的所有内容并删除
                        pattern = rf"{re.escape(old_pattern)}.*?(?=\*\*\d{{6}}\s+\w+|\n##\s+|\n###\s+|\Z)"
                        updated_summary = re.sub(pattern, "", updated_summary, flags=re.DOTALL)
                        print(f"  ✅ 已从摘要中移除 {stock.code} {stock.name}（市值过大）")
                        break
                continue
                
            if stock.real_time_data:
                new_stock_block = self._generate_stock_block(stock)
                
                # 在摘要中查找并替换（支持多种格式）
                old_patterns = [
                    f"**{stock.code} {stock.name}**",  # **代码 名称**
                    f"{stock.code} {stock.name}",       # 代码 名称（不带**）
                    f"**{stock.code}**",                # **代码**
                ]
                
                replaced = False
                for old_pattern in old_patterns:
                    if old_pattern in updated_summary:
                        price = stock.real_time_data.get('current_price', 0)
                        change = stock.real_time_data.get('price_change', 0)
                        data_source = stock.real_time_data.get('data_source', 'N/A')
                        
                        # 匹配从股票标题到下一个股票或章节结束的所有内容
                        pattern = rf"{re.escape(old_pattern)}.*?(?=\*\*\d{{6}}\s+\w+|\n##\s+|\n###\s+|\Z)"
                        updated_summary = re.sub(
                            pattern, 
                            new_stock_block.rstrip(), 
                            updated_summary, 
                            flags=re.DOTALL
                        )
                        print(f"✅ 已更新 {stock.code} {stock.name} 的实时数据: ¥{price:.2f} ({change:+.2f}%) - {data_source}")
                        print(f"   📈 买入策略: {stock.entry_strategy}")
                        print(f"   📉 卖出策略: {stock.exit_strategy}")
                        replaced = True
                        break
                
                if not replaced:
                    print(f"⚠️ {stock.code} {stock.name} 在摘要中未找到匹配的模式，无法更新")
            else:
                print(f"⚠️ {stock.code} {stock.name} 没有实时数据，跳过更新")
        
        return updated_summary
    
    def _generate_stock_block(self, stock: StockRecommendation) -> str:
        """生成股票信息块（用于更新AI摘要）- 纯文本格式，无markdown"""
        block = f"{stock.code} {stock.name}\n\n"
        
        # 实时价格（最优先显示，放在第一位）
        if stock.real_time_data and stock.real_time_data.get('current_price', 0) > 0:
            price = stock.real_time_data.get('current_price', 0)
            change = stock.real_time_data.get('price_change', 0)
            emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else "待获取"
            data_source = stock.real_time_data.get('data_source', '实时数据')
            source_emoji = "⚡" if "实时" in data_source else "📊"
            block += f"💰 当前股价：{emoji} ¥{price:.2f} ({change_str}) {source_emoji} {data_source}\n\n"
        else:
            block += f"💰 当前股价：⚠️ 实时数据获取中...\n\n"
        
        # 推荐理由（包含市值）
        reason = stock.reason
        if stock.get_market_cap_str() and '市值' not in reason:
            reason += stock.get_market_cap_str()
        block += f"推荐理由：{reason}\n\n"
        
        # 其他信息
        block += f"风险等级：{stock.risk}\n\n"
        block += f"短线潜力：{stock.short_term_potential}\n\n"
        block += f"建议持仓时间：{stock.holding_period}\n\n"
        
        # 买入/卖出策略（已基于实时价格更新）
        block += f"买入策略：{stock.entry_strategy}\n\n"
        block += f"卖出策略：{stock.exit_strategy}\n\n"
        
        # 技术面（基于实时数据）
        if stock.real_time_data:
            current_price = stock.real_time_data.get('current_price', 0)
            support = stock.real_time_data.get('recent_low', 0)
            resistance = stock.real_time_data.get('recent_high', 0)
            ma20 = stock.real_time_data.get('ma20')
            ma50 = stock.real_time_data.get('ma50')
            
            ma20_info = f"，20日均线{ma20:.2f}元" if ma20 else ""
            ma50_info = f"，50日均线{ma50:.2f}元" if ma50 else ""
            
            if support > 0 and resistance > 0:
                block += f"技术面：支撑位{support:.2f}元{ma20_info}{ma50_info}，阻力位{resistance:.2f}元\n\n"
            elif current_price > 0:
                block += f"技术面：当前价{current_price:.2f}元{ma20_info}{ma50_info}，技术指标待计算\n\n"
            else:
                block += f"技术面：{stock.support_resistance}\n\n"
        else:
            block += f"技术面：{stock.support_resistance}\n\n"
        
        # 成交量信息
        if stock.real_time_data and stock.real_time_data.get("volume_ratio"):
            volume_ratio = stock.real_time_data.get("volume_ratio", 1)
            volume_emoji = "🔥" if volume_ratio > 1.5 else "📊" if volume_ratio > 1 else "📉"
            block += f"成交量：{volume_emoji} 较20日均量 {volume_ratio:.1f}倍\n\n"
        
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
        print("🔍 开始从AI摘要中提取股票推荐...")
        extracted = self.extractor.extract_from_summary(summary)
        
        all_stocks = extracted["all_stocks_in_summary"]
        print(f"📋 提取到 {len(all_stocks)} 只股票需要更新实时数据")
        
        # 2. 更新所有股票的实时数据
        if all_stocks:
            updated_stocks = self.updater.update_stocks(all_stocks)
            # 更新提取结果中的股票列表（包括热点板块和轮动机会）
            extracted["all_stocks_in_summary"] = updated_stocks
            
            # 同时更新热点板块和轮动机会的股票列表
            hot_stocks_codes = {s.code for s in extracted["hot_sector_stocks"]}
            rotation_stocks_codes = {s.code for s in extracted["rotation_stocks"]}
            
            updated_hot = [s for s in updated_stocks if s.code in hot_stocks_codes]
            updated_rotation = [s for s in updated_stocks if s.code in rotation_stocks_codes]
            
            extracted["hot_sector_stocks"] = updated_hot
            extracted["rotation_stocks"] = updated_rotation
        else:
            updated_stocks = []
            print("⚠️ 没有提取到需要更新的股票")
        
        # 3. 用实时数据更新摘要（只更新通过市值检查的股票）
        updated_summary = self.updater.update_summary_with_realtime_data(
            summary, 
            updated_stocks,
            check_market_cap_func=self.extractor.check_market_cap
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
