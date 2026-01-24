"""
辅助函数模块
包含通用的工具函数
"""
import re
from datetime import datetime
from typing import Optional


def extract_work_order_id(text: str) -> Optional[str]:
    """
    从文本中提取工单号
    
    工单号通常是纯数字，可能包含在文本的其他部分中
    例如："20055094254<span>...</span>" 应该提取为 "20055094254"
    
    Args:
        text: 包含工单号的文本
        
    Returns:
        Optional[str]: 提取出的工单号，如果未找到则返回 None
    """
    if not text:
        return None
    
    # 去除空白字符
    text = text.strip()
    
    # 尝试提取纯数字（工单号通常是纯数字）
    # 匹配连续的数字
    match = re.search(r'\d+', text)
    if match:
        return match.group(0)
    
    return None


def parse_datetime(date_str: str) -> datetime:
    """
    解析日期时间字符串，用于排序
    
    Args:
        date_str: 日期时间字符串，格式如 "2025-12-15 21:28:23"
        
    Returns:
        datetime: 解析后的datetime对象，如果解析失败返回最小datetime
    """
    try:
        # 尝试解析格式: "YYYY-MM-DD HH:MM:SS"
        return datetime.strptime(date_str.strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError, TypeError):
        # 如果解析失败，返回最小datetime（用于排序）
        return datetime.min


async def extract_cell_text(cell) -> str:
    """
    从单元格中提取文本，优先从 table-m__split-container 中提取
    
    Args:
        cell: Playwright ElementHandle 对象
        
    Returns:
        str: 提取的文本内容
    """
    try:
        # 尝试从 table-m__split-container 中提取
        container = await cell.query_selector('div.table-m__split-container__67f567d5 span')
        if container:
            return await container.inner_text()
        # 如果没有找到，直接提取单元格文本
        return await cell.inner_text()
    except Exception:
        try:
            return await cell.inner_text()
        except Exception:
            return ''
