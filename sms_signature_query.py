"""
短信签名查询模块
提供可扩展的短信签名查询功能，便于后期调整和扩展其他功能
"""
import asyncio
import re
from typing import Dict, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

# 页面配置
SIGN_QUERY_URL = "https://alicom-ops.alibaba-inc.com/dysms/dysms_sa/analyze_search/sign"

# 页面元素选择器配置（便于后期调整）
SELECTORS = {
    'partner_id': '#PartnerId',  # 客户PID输入框
    'sign_name': '#SignName',    # 签名名称输入框
    'work_order_primary': 'div.break-all',  # 工单号（优先选择器）
    'work_order_fallback': 'td.dumbo-antd-0-1-18-table-cell',  # 工单号（备选选择器）
}


async def query_sms_signature(
    page: Page,
    pid: str,
    sign_name: str,
    timeout: int = 30000
) -> Dict[str, any]:
    """
    查询短信签名并获取工单号
    
    Args:
        page: Playwright Page 对象（需要已登录的会话）
        pid: 客户PID
        sign_name: 签名名称
        timeout: 操作超时时间（毫秒），默认30秒
        
    Returns:
        Dict: 查询结果字典，包含以下字段：
            - success (bool): 是否查询成功
            - work_order_id (Optional[str]): 工单号（成功时返回）
            - error (Optional[str]): 错误信息（失败时返回）
            
    Example:
        >>> result = await query_sms_signature(page, "100000103722927", "国能e购")
        >>> if result['success']:
        ...     print(f"工单号：{result['work_order_id']}")
        ... else:
        ...     print(f"查询失败：{result['error']}")
    """
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
            query_button = await page.query_selector('button:has-text("查询"), button:has-text("搜索")')
            if query_button:
                await query_button.click()
                print("已点击查询按钮")
        except Exception:
            # 如果没有查询按钮，可能输入后自动触发查询
            pass
        
        # 6. 等待查询结果加载
        print("等待查询结果...")
        await asyncio.sleep(2)  # 等待查询完成
        
        # 7. 提取工单号（优先检查 div.break-all）
        work_order_id = None
        
        # 优先检查 div.break-all
        try:
            primary_element = await page.wait_for_selector(
                SELECTORS['work_order_primary'],
                timeout=5000,
                state='visible'
            )
            
            if primary_element:
                # 获取元素的文本内容
                work_order_text = await primary_element.inner_text()
                
                # 清理文本：去除可能的复制图标等子元素文本
                # div.break-all 可能包含工单号和其他元素，需要提取数字部分
                work_order_id = _extract_work_order_id(work_order_text)
                
                if work_order_id:
                    print(f"从 div.break-all 提取到工单号: {work_order_id}")
                    
        except PlaywrightTimeoutError:
            # 如果找不到 div.break-all，尝试备选方案
            print("未找到 div.break-all，尝试备选选择器...")
            
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
            return {
                'success': True,
                'work_order_id': work_order_id,
                'error': None
            }
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
            # 执行查询
            result = await query_sms_signature(
                page=page,
                pid="100000103722927",
                sign_name="国能e购"
            )
            
            # 处理结果
            if result['success']:
                print(f"\n✓ 查询成功！")
                print(f"工单号: {result['work_order_id']}")
            else:
                print(f"\n✗ 查询失败: {result['error']}")
                
        finally:
            # 清理资源
            print("\n正在关闭浏览器...")
            await context.close()
            await browser.close()
            await playwright.stop()
            print("已关闭浏览器")
    
    # 运行示例
    asyncio.run(main())