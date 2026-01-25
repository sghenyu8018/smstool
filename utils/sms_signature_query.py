"""
短信签名查询模块
提供短信签名查询功能
"""
import asyncio
from typing import Dict, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from .constants import SIGN_QUERY_URL, SELECTORS
from .helpers import extract_work_order_id, parse_datetime


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
            
    # Example:
    #     >>> result = await query_sms_signature(page, "100000103722927", "国能e购")
    #     >>> if result['success']:
    #     ...     print(f"工单号：{result['work_order_id']}")
    #     ... else:
    #     ...     print(f"查询失败：{result['error']}")
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
        await page.goto(SIGN_QUERY_URL, timeout=timeout, wait_until='domcontentloaded')
        
        # 2. 等待页面加载完成，确保客户PID输入框元素可见
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
        try:
            query_button = await page.query_selector('button:has-text("查 询"), button:has-text("搜 索")')
            if query_button:
                await query_button.click()
                print("已点击查询按钮")
        except Exception:
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
                        # 获取第二列（签名名称）
                        second_cell = await row.query_selector('td.dumbo-antd-0-1-18-table-cell:nth-child(2)')
                        # 获取第三列（修改时间）
                        third_cell = await row.query_selector('td.dumbo-antd-0-1-18-table-cell:nth-child(3)')
                        
                        if first_cell and second_cell and third_cell:
                            work_order_text = await first_cell.inner_text()
                            # 提取签名名称：从div.break-all中提取文本，去除复制按钮等图标
                            sign_name_cell = await second_cell.query_selector('div.break-all')
                            if sign_name_cell:
                                # 获取div.break-all内的文本内容（不包括子元素如复制按钮）
                                sign_name_text = await sign_name_cell.evaluate('''el => {
                                    // 克隆元素以保留原始结构
                                    const clone = el.cloneNode(true);
                                    // 移除所有svg图标（复制按钮）
                                    clone.querySelectorAll("svg, span.anticon").forEach(s => s.remove());
                                    // 返回清理后的文本
                                    return clone.textContent.trim();
                                }''')
                            else:
                                # 如果没有div.break-all，直接获取单元格文本
                                sign_name_text = await second_cell.inner_text()
                            
                            modify_time_text = await third_cell.inner_text()
                            
                            # 清理签名名称：去除空白字符
                            sign_name_text = sign_name_text.strip() if sign_name_text else ""
                            
                            # 对签名名称进行完全匹配
                            if sign_name_text != sign_name:
                                print(f"  行 {idx+1}: 签名名称不匹配（期望: '{sign_name}', 实际: '{sign_name_text}'），跳过")
                                continue
                            
                            extracted_id = extract_work_order_id(work_order_text)
                            modify_time = modify_time_text.strip()
                            
                            if extracted_id and modify_time:
                                work_order_data.append({
                                    'work_order_id': extracted_id,
                                    'modify_time': modify_time,
                                    'sign_name': sign_name_text,
                                    'row_index': idx
                                })
                                print(f"  行 {idx+1}: 工单号={extracted_id}, 签名名称={sign_name_text}, 修改时间={modify_time} [签名匹配]")
                    except Exception as e:
                        print(f"  处理第 {idx+1} 行时出错: {e}")
                        continue
                
                # 根据修改时间选择最新的工单号
                if work_order_data:
                    # 按修改时间排序（最新的在前）
                    work_order_data.sort(
                        key=lambda x: parse_datetime(x['modify_time']),
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
                    work_order_id = extract_work_order_id(work_order_text)
                    
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
                            extracted_id = extract_work_order_id(text)
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
