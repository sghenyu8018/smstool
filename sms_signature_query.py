"""
短信签名查询模块
提供可扩展的短信签名查询功能，便于后期调整和扩展其他功能
"""
import asyncio
import re
from datetime import datetime
from typing import Dict, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

# 页面配置
SIGN_QUERY_URL = "https://alicom-ops.alibaba-inc.com/dysms/dysms_sa/analyze_search/sign"

# 页面元素选择器配置（便于后期调整）
SELECTORS = {
    'partner_id': '#PartnerId',  # 客户PID输入框
    'sign_name': '#SignName',    # 签名名称输入框
    'table_row': 'tr.dumbo-antd-0-1-18-table-row',  # 表格行
    'work_order_primary': 'div.break-all',  # 工单号（优先选择器）
    'work_order_fallback': 'td.dumbo-antd-0-1-18-table-cell',  # 工单号（备选选择器）

    # 工单号主选择器，优先尝试；通常页面主要结果区域、文本内容为工单号
    # "div.break-all" 通常用于展示内容较长、需要自动换行的工单号
    # 'div.break-all' 是页面上用于展示工单号的主要元素，其 CSS 类 'break-all' 使文本内容自动换行，通常包含工单号字符串
    # 'work_order_primary' 是页面上主要用于展示工单号的元素，其 CSS 选择器 'div.break-all' 表示：查找所有 class 属性包含 'break-all' 的 <div> 元素。
    # 这里的 "break-all" 是该元素的 CSS 类名（class），用于定义样式，也方便自动化工具精确定位。
    'work_order_primary': 'div.break-all',

    # 工单号备选选择器，若主选择器无法提取到，则作为备选使用
    # "td.dumbo-antd-0-1-18-table-cell" 可能因UI框架升级更改，需要随时调整
    'work_order_fallback': 'td.dumbo-antd-0-1-18-table-cell',
}


async def query_sms_signature(
    page: Page,
    pid: Optional[str] = None,
    sign_name: Optional[str] = None,
    timeout: int = 30000
) -> Dict[str, any]:
    """
    查询短信签名并获取工单号
    
    Args:
        page: Playwright Page 对象（需要已登录的会话）
        pid: 客户PID（如果不提供，则从环境变量 SMS_PID 读取）
        sign_name: 签名名称（如果不提供，则从环境变量 SMS_SIGN_NAME 读取）
        timeout: 操作超时时间（毫秒），默认30秒
        
    Returns:
        Dict: 查询结果字典，包含以下字段：
            - success (bool): 是否查询成功
            - work_order_id (Optional[str]): 工单号（成功时返回，选择修改时间最新的）
            - error (Optional[str]): 错误信息（失败时返回）
            - all_work_orders (Optional[List]): 所有找到的工单号列表（如果有多行）
            - total_count (Optional[int]): 工单号总数
            
    Example:
        >>> result = await query_sms_signature(page, "100000103722927", "国能e购")
        >>> if result['success']:
        ...     print(f"工单号：{result['work_order_id']}")
        ... else:
        ...     print(f"查询失败：{result['error']}")
    """
    # 如果未提供pid或sign_name，从环境变量读取
    if not pid or not sign_name:
        try:
            from config import SMS_PID, SMS_SIGN_NAME
            
            if not pid:
                pid = SMS_PID
            if not sign_name:
                sign_name = SMS_SIGN_NAME
            
            if not pid or not sign_name:
                return {
                    'success': False,
                    'work_order_id': None,
                    'error': '客户PID和签名名称未提供，请在函数参数中传入或在环境变量中配置 SMS_PID 和 SMS_SIGN_NAME'
                }
        except ImportError:
            if not pid or not sign_name:
                return {
                    'success': False,
                    'work_order_id': None,
                    'error': '客户PID和签名名称未提供，且无法从环境变量读取'
                }
    try:
        # 1. 导航到查询页面
        print(f"正在访问查询页面: {SIGN_QUERY_URL}")
        await page.goto(SIGN_QUERY_URL, timeout=timeout, wait_until='networkidle')
        
        # 2. 等待页面加载完成，确保输入框可见
        await page.wait_for_selector(SELECTORS['partner_id'], timeout=timeout, state='visible')
        
        # 3. 填写客户PID
        print(f"正在填写客户PID: {pid}")
        await page.fill(SELECTORS['partner_id'], pid)
        await asyncio.sleep(0.5)  # 模拟人类操作，等待一下
        
        # 4. 填写签名名称
        print(f"正在填写签名名称: {sign_name}")
        await page.fill(SELECTORS['sign_name'], sign_name)
        await asyncio.sleep(0.5)  # 模拟人类操作
        
        # 5. 触发查询（如果页面有查询按钮，可以点击；否则等待自动查询）
        # 检查是否有查询按钮，如果有则点击
        try:
            query_button = await page.query_selector('button:has-text("查 询"), button:has-text("搜 索")')
            if query_button:
                await query_button.click()
                print("已点击查询按钮")
        except Exception:
            # 如果没有查询按钮，可能输入后自动触发查询
            pass
        
        # 6. 等待查询结果加载
        print("等待查询结果...")
        await asyncio.sleep(2)  # 等待查询完成
        
        # 7. 提取工单号（支持多行，根据修改时间选择最新的）
        work_order_id = None
        work_order_data = []
        
        try:
            # 方法1: 优先尝试从表格中提取多行数据
            print("尝试从表格中提取工单号...")
            table_rows = await page.query_selector_all(
                f"{SELECTORS['table_row']}:not([aria-hidden='true'])"
            )
            
            if table_rows and len(table_rows) > 0:
                print(f"找到 {len(table_rows)} 行数据")
                
                for idx, row in enumerate(table_rows):
                    try:
                        # 获取第一列（工单号）
                        first_cell = await row.query_selector('td.dumbo-antd-0-1-18-table-cell:nth-child(1)')
                        # 获取第三列（修改时间）
                        third_cell = await row.query_selector('td.dumbo-antd-0-1-18-table-cell:nth-child(3)')
                        
                        if first_cell and third_cell:
                            work_order_text = await first_cell.inner_text()
                            modify_time_text = await third_cell.inner_text()
                            
                            extracted_id = _extract_work_order_id(work_order_text)
                            modify_time = modify_time_text.strip()
                            
                            if extracted_id and modify_time:
                                work_order_data.append({
                                    'work_order_id': extracted_id,
                                    'modify_time': modify_time,
                                    'row_index': idx
                                })
                                print(f"  行 {idx+1}: 工单号={extracted_id}, 修改时间={modify_time}")
                    except Exception as e:
                        print(f"  处理第 {idx+1} 行时出错: {e}")
                        continue
                
                # 根据修改时间选择最新的工单号
                if work_order_data:
                    # 按修改时间排序（最新的在前）
                    work_order_data.sort(
                        key=lambda x: _parse_datetime(x['modify_time']),
                        reverse=True
                    )
                    
                    work_order_id = work_order_data[0]['work_order_id']
                    latest_time = work_order_data[0]['modify_time']
                    print(f"选择修改时间最新的工单号: {work_order_id} (修改时间: {latest_time})")
                    
                    if len(work_order_data) > 1:
                        print(f"共找到 {len(work_order_data)} 个工单号，已选择最新的")
            
        except Exception as e:
            print(f"从表格提取失败: {e}")
        
        # 方法2: 如果表格方法失败，尝试原来的方法（兼容旧逻辑）
        if not work_order_id:
            print("表格方法未找到工单号，尝试备选方法...")
            try:
                # 优先检查 div.break-all（可能不在表格中）
                primary_element = await page.wait_for_selector(
                    SELECTORS['work_order_primary'],
                    timeout=3000,
                    state='visible'
                )
                
                if primary_element:
                    work_order_text = await primary_element.inner_text()
                    work_order_id = _extract_work_order_id(work_order_text)
                    
                    if work_order_id:
                        print(f"从 div.break-all 提取到工单号: {work_order_id}")
                        
            except PlaywrightTimeoutError:
                # 如果找不到 div.break-all，尝试备选方案
                print("未找到 div.break-all，尝试其他方法...")
                
                try:
                    # 备选方案：检查 td.dumbo-antd-0-1-18-table-cell
                    fallback_elements = await page.query_selector_all(SELECTORS['work_order_fallback'])
                    
                    if fallback_elements:
                        # 遍历所有匹配的元素，找到包含数字的工单号
                        for element in fallback_elements:
                            text = await element.inner_text()
                            extracted_id = _extract_work_order_id(text)
                            if extracted_id:
                                work_order_id = extracted_id
                                print(f"从 td.dumbo-antd-0-1-18-table-cell 提取到工单号: {work_order_id}")
                                break
                                
                except Exception as e:
                    print(f"备选选择器也未能找到工单号: {e}")
        
        # 检查是否成功提取到工单号
        if work_order_id:
            result = {
                'success': True,
                'work_order_id': work_order_id,
                'error': None
            }
            
            # 如果有多行数据，也返回所有数据供参考
            if work_order_data:
                result['all_work_orders'] = work_order_data
                result['total_count'] = len(work_order_data)
            
            return result
        else:
            return {
                'success': False,
                'work_order_id': None,
                'error': '未能从页面中提取到工单号，请检查查询条件和页面结构'
            }
            
    except PlaywrightTimeoutError as e:
        error_msg = f"操作超时（超过 {timeout/1000} 秒）: {str(e)}"
        print(f"错误: {error_msg}")
        return {
            'success': False,
            'work_order_id': None,
            'error': error_msg
        }
    except Exception as e:
        error_msg = f"查询过程中发生错误: {str(e)}"
        print(f"错误: {error_msg}")
        return {
            'success': False,
            'work_order_id': None,
            'error': error_msg
        }


def _extract_work_order_id(text: str) -> Optional[str]:
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


def _parse_datetime(date_str: str) -> datetime:
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


# 扩展接口：可以方便地添加其他查询功能
class SMSQueryBase:
    """
    短信查询基类，便于扩展其他查询功能
    子类可以实现不同的查询方法
    """
    
    def __init__(self, page: Page):
        """
        初始化查询对象
        
        Args:
            page: Playwright Page 对象
        """
        self.page = page
        self.selectors = SELECTORS.copy()
    
    async def query(self, *args, **kwargs) -> Dict[str, any]:
        """
        执行查询（子类需要实现）
        
        Returns:
            Dict: 查询结果
        """
        raise NotImplementedError("子类必须实现 query 方法")
    
    def update_selectors(self, **kwargs):
        """
        更新选择器配置，便于后期调整
        
        Args:
            **kwargs: 选择器键值对
        """
        self.selectors.update(kwargs)


if __name__ == '__main__':
    """
    示例：使用短信签名查询功能
    """
    import asyncio
    from login_module import create_playwright_session
    
    async def main():
        # 创建已登录的会话
        print("正在创建浏览器会话...")
        playwright, browser, context, page = await create_playwright_session(headless=False)
        print("浏览器会话已创建")
        
        try:
            # 执行查询（如果不传参数，会从环境变量读取）
            result = await query_sms_signature(page=page)
            
            # 处理结果
            if result['success']:
                print(f"\n[OK] 查询成功！")
                print(f"工单号（最新）: {result['work_order_id']}")
                
                # 如果有多行数据，显示所有工单号
                if 'all_work_orders' in result and result['all_work_orders']:
                    print(f"\n共找到 {result['total_count']} 个工单号:")
                    for i, wo in enumerate(result['all_work_orders'], 1):
                        print(f"  {i}. 工单号: {wo['work_order_id']}, 修改时间: {wo['modify_time']}")
            else:
                print(f"\n[FAIL] 查询失败: {result['error']}")
                
        finally:
            # 清理资源
            print("\n正在关闭浏览器...")
            await context.close()
            await browser.close()
            await playwright.stop()
            print("已关闭浏览器")
    
    # 运行示例
    asyncio.run(main())