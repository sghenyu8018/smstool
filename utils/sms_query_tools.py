"""
短信查询工具模块
提供短信签名查询和成功率查询的核心功能
"""
import asyncio
import re
from datetime import datetime
from typing import Dict, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

# 页面配置
SIGN_QUERY_URL = "https://alicom-ops.alibaba-inc.com/dysms/dysms_sa/analyze_search/sign"
SUCCESS_RATE_QUERY_URL = "https://alicom-ops.alibaba-inc.com/dysms/dysms_schedule_data_center/dysms_datacenter_recommend_failure"

# 页面元素选择器配置（便于后期调整）
SELECTORS = {
    'partner_id': '#PartnerId',  # 客户PID输入框（签名查询页面）
    'sign_name': '#SignName',    # 签名名称输入框
    'table_row': 'tr.dumbo-antd-0-1-18-table-row',  # 表格行
    'work_order_primary': 'div.break-all',  # 工单号（优先选择器）
    'work_order_fallback': 'td.dumbo-antd-0-1-18-table-cell',  # 工单号（备选选择器）
    
    # 成功率查询页面选择器
    'success_rate_menu_item': 'div.MenuItem___2wtEa:has-text("求德大盘")',  # 求德大盘菜单项
    'success_rate_pid_input': 'span.obviz-base-filterText:has-text("pid") ~ * span.obviz-base-filterInput input[autocomplete="off"]',  # PID输入框
    'success_rate_time_selector': 'div[data-spm-click*="time"]',  # 时间选择器
    'success_rate_time_option': 'li.obviz-base-li-block:has-text("30天")',  # 30天选项
    'success_rate_table_row': 'div.obviz-base-easyTable-row',  # 成功率表格行
    'success_rate_value': 'div.table-m__split-container__67f567d5 span',  # 成功率值
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


async def query_sms_success_rate(
    page: Page,
    pid: Optional[str] = None,
    time_range: str = '30天',
    timeout: int = 30000
) -> Dict[str, any]:
    """
    查询短信签名成功率
    
    Args:
        page: Playwright Page 对象（需要已登录的会话）
        pid: 客户PID（如果不提供，则从环境变量 SMS_PID 读取）
        time_range: 时间范围，可选值：'当天', '本周', '一周', '上周', '30天'，默认为'30天'
        timeout: 操作超时时间（毫秒），默认30秒
        
    Returns:
        Dict: 查询结果字典，包含以下字段：
            - success (bool): 是否查询成功
            - success_rate (Optional[str]): 回执成功率（成功时返回，取第一条数据）
            - pid (Optional[str]): 客户PID
            - time_range (str): 查询的时间范围
            - data (Optional[List]): 所有数据行，每行包含：
                - pid: 客户PID
                - signname: 签名名称
                - sms_type: 短信类型
                - submit_count: 提交量
                - receipt_count: 回执量
                - receipt_success_count: 回执成功量
                - receipt_rate: 回执率
                - receipt_success_rate: 回执成功率
                - receipt_rate_10s: 十秒回执率
                - receipt_rate_30s: 三十秒回执率
                - receipt_rate_60s: 六十秒回执率
            - error (Optional[str]): 错误信息（失败时返回）
            
    # Example:
    #     >>> result = await query_sms_success_rate(page=page, pid="100000103722927", time_range="30天")
    #     >>> if result['success']:
    #     ...     print(f"回执成功率：{result['success_rate']}%")
    #     ...     for row in result['data']:
    #     ...         print(f"签名：{row['signname']}, 类型：{row['sms_type']}, 提交量：{row['submit_count']}")
    #     ... else:
    #     ...     print(f"查询失败：{result['error']}")
    """
    # 如果未提供pid，从环境变量读取
    if not pid:
        try:
            from config import SMS_PID
            pid = SMS_PID
            
            if not pid:
                return {
                    'success': False,
                    'success_rate': None,
                    'pid': None,
                    'data': None,
                    'error': '客户PID未提供，请在函数参数中传入或在环境变量中配置 SMS_PID'
                }
        except ImportError:
            return {
                'success': False,
                'success_rate': None,
                'pid': None,
                'data': None,
                'error': '客户PID未提供，且无法从环境变量读取'
            }
    
    try:
        # 1. 导航到查询页面
        print(f"正在访问成功率查询页面: {SUCCESS_RATE_QUERY_URL}")
        await page.goto(SUCCESS_RATE_QUERY_URL, timeout=timeout, wait_until='domcontentloaded')
        
        # 2. 点击"求德大盘"菜单项
        print("正在点击'求德大盘'菜单项...")
        try:
            menu_item = await page.wait_for_selector(
                SELECTORS['success_rate_menu_item'],
                timeout=10000,
                state='visible'
            )
            await menu_item.click()
            print("已点击'求德大盘'菜单项")
            await asyncio.sleep(2)  # 等待页面切换/加载
        except PlaywrightTimeoutError:
            try:
                menu_item = await page.locator('text=求德大盘').first
                if await menu_item.is_visible():
                    await menu_item.click()
                    print("已点击'求德大盘'菜单项（通过文本定位）")
                    await asyncio.sleep(2)
                else:
                    print("警告: 未找到'求德大盘'菜单项，继续执行...")
            except Exception as e:
                print(f"点击'求德大盘'菜单项时出现问题: {e}，继续执行...")
        
        # 3. 等待页面加载完成，查找PID输入框
        print(f"\n{'='*60}")
        print(f"步骤3: 查找并填写客户PID: {pid}")
        print(f"{'='*60}")
        
        # 等待页面完全加载
        print("\n等待页面完全加载...")
        await asyncio.sleep(3)
        
        # 检查是否有iframe
        print("检查页面中是否有iframe...")
        iframes = page.frames
        print(f"  - 找到 {len(iframes)} 个frame（包括主frame）")
        for idx, frame in enumerate(iframes):
            url = frame.url
            name = frame.name or 'unnamed'
            url_display = url[:100] + '...' if len(url) > 100 else url
            print(f"    Frame {idx}: name='{name}', url='{url_display}'")
        
        # 直接定位到Frame 3（SLS iframe）
        sls_frame = None
        print("\n定位SLS iframe (Frame 3)...")
        for idx, frame in enumerate(iframes):
            if 'sls4service.console.aliyun.com' in frame.url and 'dashboard' in frame.url:
                sls_frame = frame
                print(f"  ✓ 找到SLS iframe: Frame {idx}")
                print(f"    URL: {frame.url[:150]}...")
                break
        
        if not sls_frame:
            return {
                'success': False,
                'success_rate': None,
                'pid': pid,
                'data': None,
                'error': '未找到SLS iframe (Frame 3)，请检查页面是否加载完成'
            }
        
        # 等待SLS iframe加载完成
        print("  - 等待SLS iframe加载完成...")
        try:
            await sls_frame.wait_for_load_state('domcontentloaded', timeout=10000)
            await asyncio.sleep(2)
        except Exception as e:
            print(f"  ⚠ SLS iframe加载超时: {e}")
        
        # 在SLS iframe中查找PID输入框
        pid_input_locator = None
        
        print("\n[方式1] 在SLS iframe中查找PID输入框...")
        try:
            # 在SLS iframe中查找pid标签
            pid_label_locator = sls_frame.locator('span.obviz-base-filterText').filter(has_text='pid')
            count = await pid_label_locator.count()
            print(f"  - 找到 {count} 个pid标签")
            
            if count > 0:
                # 找到pid标签后，查找父容器
                container_locator = pid_label_locator.locator('xpath=ancestor::div[contains(@class, "obviz-base-easy-select-inner")]')
                container_count = await container_locator.count()
                print(f"    - 找到 {container_count} 个父容器")
                
                if container_count > 0:
                    # 先尝试查找已存在的可见输入框
                    input_locator = container_locator.locator('span.obviz-base-filterInput input[autocomplete="off"]')
                    input_count = await input_locator.count()
                    print(f"    - 在容器内找到 {input_count} 个输入框")
                    
                    if input_count > 0:
                        # 检查第一个输入框是否可见
                        first_input = input_locator.first
                        is_visible = await first_input.is_visible()
                        value = await first_input.get_attribute('value') or ''
                        print(f"    - 第一个输入框: 可见={is_visible}, 当前值='{value}'")
                        
                        if is_visible:
                            pid_input_locator = first_input
                            
                            # 打印元素信息
                            try:
                                element_info = await first_input.evaluate('''el => {
                                    return {
                                        tagName: el.tagName,
                                        id: el.id || '',
                                        className: el.className || '',
                                        name: el.name || '',
                                        type: el.type || '',
                                        value: el.value || '',
                                        placeholder: el.placeholder || '',
                                        autocomplete: el.autocomplete || '',
                                        outerHTML: el.outerHTML.substring(0, 200) + (el.outerHTML.length > 200 ? '...' : '')
                                    };
                                }''')
                                print(f"  ✓ 在SLS iframe中找到PID输入框（已可见）")
                                print(f"  元素信息:")
                                print(f"    - 标签: {element_info.get('tagName', 'N/A')}")
                                print(f"    - ID: {element_info.get('id', 'N/A')}")
                                print(f"    - Class: {element_info.get('className', 'N/A')}")
                                print(f"    - Name: {element_info.get('name', 'N/A')}")
                                print(f"    - Type: {element_info.get('type', 'N/A')}")
                                print(f"    - Value: {element_info.get('value', 'N/A')}")
                                print(f"    - Placeholder: {element_info.get('placeholder', 'N/A')}")
                                print(f"    - Autocomplete: {element_info.get('autocomplete', 'N/A')}")
                                print(f"    - HTML片段: {element_info.get('outerHTML', 'N/A')}")
                            except Exception as e:
                                print(f"  ✓ 在SLS iframe中找到PID输入框（已可见）")
                                print(f"  (获取元素详细信息时出错: {e})")
                    
                    # 如果输入框不可见或不存在，尝试点击值容器来激活
                    if not pid_input_locator:
                        print(f"    - 输入框不可见或不存在，尝试点击值容器激活...")
                        try:
                            # 尝试多种值容器选择器
                            value_container_selectors = [
                                'div.obviz-base-easy-select-value',
                                'div.obviz-base-easy-select-text-field',
                                '.obviz-base-easy-select-value',
                                '.obviz-base-easy-select-text-field',
                                'div[class*="easy-select-value"]',
                                'div[class*="easy-select-text"]'
                            ]
                            
                            value_container = None
                            for selector in value_container_selectors:
                                try:
                                    value_locator = container_locator.locator(selector).first
                                    if await value_locator.count() > 0:
                                        is_visible = await value_locator.is_visible()
                                        if is_visible:
                                            value_container = value_locator
                                            print(f"    - 找到值容器: {selector}")
                                            break
                                except Exception:
                                    continue
                            
                            if value_container:
                                # 点击值容器来激活输入框
                                print(f"    - 点击值容器激活输入框...")
                                await value_container.click()
                                await asyncio.sleep(1)  # 等待输入框出现
                                
                                # 再次查找输入框
                                input_locator = container_locator.locator('span.obviz-base-filterInput input[autocomplete="off"]')
                                input_count = await input_locator.count()
                                print(f"    - 点击后找到 {input_count} 个输入框")
                                
                                if input_count > 0:
                                    first_input = input_locator.first
                                    is_visible = await first_input.is_visible()
                                    value = await first_input.get_attribute('value') or ''
                                    print(f"    - 输入框: 可见={is_visible}, 当前值='{value}'")
                                    
                                    if is_visible:
                                        pid_input_locator = first_input
                                        
                                        # 打印元素信息
                                        try:
                                            element_info = await first_input.evaluate('''el => {
                                                return {
                                                    tagName: el.tagName,
                                                    id: el.id || '',
                                                    className: el.className || '',
                                                    name: el.name || '',
                                                    type: el.type || '',
                                                    value: el.value || '',
                                                    placeholder: el.placeholder || '',
                                                    autocomplete: el.autocomplete || '',
                                                    outerHTML: el.outerHTML.substring(0, 200) + (el.outerHTML.length > 200 ? '...' : '')
                                                };
                                            }''')
                                            print(f"  ✓ 在SLS iframe中找到PID输入框（已激活）")
                                            print(f"  元素信息:")
                                            print(f"    - 标签: {element_info.get('tagName', 'N/A')}")
                                            print(f"    - ID: {element_info.get('id', 'N/A')}")
                                            print(f"    - Class: {element_info.get('className', 'N/A')}")
                                            print(f"    - Name: {element_info.get('name', 'N/A')}")
                                            print(f"    - Type: {element_info.get('type', 'N/A')}")
                                            print(f"    - Value: {element_info.get('value', 'N/A')}")
                                            print(f"    - Placeholder: {element_info.get('placeholder', 'N/A')}")
                                            print(f"    - Autocomplete: {element_info.get('autocomplete', 'N/A')}")
                                            print(f"    - HTML片段: {element_info.get('outerHTML', 'N/A')}")
                                        except Exception as e:
                                            print(f"  ✓ 在SLS iframe中找到PID输入框（已激活）")
                                            print(f"  (获取元素详细信息时出错: {e})")
                                    else:
                                        print(f"    - 输入框仍然不可见，尝试等待...")
                                        try:
                                            await first_input.wait_for(state='visible', timeout=3000)
                                            pid_input_locator = first_input
                                            print(f"  ✓ 在SLS iframe中找到PID输入框（等待后可见）")
                                        except Exception:
                                            print(f"    - 等待超时，输入框仍未可见")
                            else:
                                # 如果找不到值容器，尝试直接点击容器
                                print(f"    - 未找到值容器，尝试点击整个容器...")
                                await container_locator.first.click()
                                await asyncio.sleep(1)
                                
                                # 再次查找输入框
                                input_locator = container_locator.locator('span.obviz-base-filterInput input[autocomplete="off"]')
                                input_count = await input_locator.count()
                                if input_count > 0:
                                    first_input = input_locator.first
                                    try:
                                        await first_input.wait_for(state='visible', timeout=3000)
                                        pid_input_locator = first_input
                                        print(f"  ✓ 在SLS iframe中找到PID输入框（点击容器后可见）")
                                    except Exception:
                                        pass
                        except Exception as e:
                            print(f"    - 激活输入框时出错: {type(e).__name__} - {str(e)}")
            else:
                print(f"  ✗ 未找到pid标签")
        except Exception as e:
            print(f"  ✗ 查找PID输入框失败: {type(e).__name__} - {str(e)}")
        
        # 方式2: 如果方式1失败，在SLS iframe中查找所有输入框并验证
        if not pid_input_locator:
            print("\n[方式2] 在SLS iframe中查找所有输入框并验证...")
            try:
                all_inputs_locator = sls_frame.locator('span.obviz-base-filterInput input[autocomplete="off"]')
                count = await all_inputs_locator.count()
                print(f"  - 找到 {count} 个输入框")
                
                for inp_idx in range(count):
                    input_loc = all_inputs_locator.nth(inp_idx)
                    is_visible = await input_loc.is_visible()
                    if is_visible:
                        value = await input_loc.get_attribute('value') or ''
                        print(f"    - 输入框 {inp_idx+1}: 可见={is_visible}, 值='{value}'")
                        
                        # 检查是否在pid容器内
                        is_pid_input = await input_loc.evaluate('''el => {
                            const container = el.closest("div.obviz-base-easy-select-inner");
                            if (!container) return false;
                            const pidLabel = container.querySelector('span.obviz-base-filterText');
                            return pidLabel && pidLabel.textContent.trim().toLowerCase() === 'pid';
                        }''')
                        print(f"      - 检查结果: {is_pid_input}")
                        
                        if is_pid_input:
                            pid_input_locator = input_loc
                            
                            # 打印元素信息
                            try:
                                element_info = await input_loc.evaluate('''el => {
                                    return {
                                        tagName: el.tagName,
                                        id: el.id || '',
                                        className: el.className || '',
                                        name: el.name || '',
                                        type: el.type || '',
                                        value: el.value || '',
                                        placeholder: el.placeholder || '',
                                        autocomplete: el.autocomplete || '',
                                        outerHTML: el.outerHTML.substring(0, 200) + (el.outerHTML.length > 200 ? '...' : '')
                                    };
                                }''')
                                print(f"  ✓ 在SLS iframe的输入框 {inp_idx+1}中找到PID输入框")
                                print(f"  元素信息:")
                                print(f"    - 标签: {element_info.get('tagName', 'N/A')}")
                                print(f"    - ID: {element_info.get('id', 'N/A')}")
                                print(f"    - Class: {element_info.get('className', 'N/A')}")
                                print(f"    - Name: {element_info.get('name', 'N/A')}")
                                print(f"    - Type: {element_info.get('type', 'N/A')}")
                                print(f"    - Value: {element_info.get('value', 'N/A')}")
                                print(f"    - Placeholder: {element_info.get('placeholder', 'N/A')}")
                                print(f"    - Autocomplete: {element_info.get('autocomplete', 'N/A')}")
                                print(f"    - HTML片段: {element_info.get('outerHTML', 'N/A')}")
                            except Exception as e:
                                print(f"  ✓ 在SLS iframe的输入框 {inp_idx+1}中找到PID输入框")
                                print(f"  (获取元素详细信息时出错: {e})")
                            
                            break
            except Exception as e:
                print(f"  ✗ 查找失败: {type(e).__name__} - {str(e)}")
        
        # 最终检查
        print(f"\n{'='*60}")
        if not pid_input_locator:
            print("✗ 所有方式都未能找到PID输入框")
            print("调试信息:")
            try:
                for idx, frame in enumerate(iframes):
                    try:
                        pid_labels = await frame.query_selector_all('span.obviz-base-filterText')
                        print(f"  - Frame {idx} 有 {len(pid_labels)} 个filterText元素")
                        for label_idx, label in enumerate(pid_labels[:3], 1):
                            text = await label.inner_text()
                            print(f"    {label_idx}. 文本: '{text}'")
                    except Exception:
                        pass
            except Exception as e:
                print(f"  - 获取调试信息时出错: {e}")
            
            return {
                'success': False,
                'success_rate': None,
                'pid': pid,
                'data': None,
                'error': '未找到PID输入框，请检查页面结构'
            }
        else:
            print(f"✓ PID输入框定位成功 (在SLS iframe中)")
            print(f"{'='*60}\n")
        
        # 4. 填写PID（在SLS iframe中填写）
        print(f"\n{'='*60}")
        print(f"步骤4: 填写PID到输入框")
        print(f"{'='*60}")
        
        print(f"  注意: 输入框在SLS iframe中，将使用SLS iframe进行操作")
        
        try:
            # 方法1: 使用locator点击并填写
            print("  - 点击输入框获取焦点...")
            await pid_input_locator.click()
            await asyncio.sleep(0.3)
            
            print("  - 清空输入框...")
            await pid_input_locator.clear()
            await asyncio.sleep(0.2)
            
            print(f"  - 填写PID: {pid}...")
            await pid_input_locator.fill(pid)
            await asyncio.sleep(0.5)
            
            # 验证输入
            value_after = await pid_input_locator.get_attribute('value') or ''
            print(f"  - 填写后值: '{value_after}'")
            
            if value_after != pid:
                print("  - 值不匹配，尝试使用JavaScript直接设置...")
                await pid_input_locator.evaluate(f'''el => {{
                    el.value = "{pid}";
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}''')
                await asyncio.sleep(0.5)
                
                value_after = await pid_input_locator.get_attribute('value') or ''
                print(f"  - JavaScript设置后值: '{value_after}'")
            
            # 如果还是不行，尝试逐字符输入
            if value_after != pid:
                print("  - 尝试逐字符输入...")
                await pid_input_locator.click()
                await pid_input_locator.clear()
                await asyncio.sleep(0.2)
                
                await pid_input_locator.type(pid, delay=50)
                await asyncio.sleep(0.5)
                
                value_after = await pid_input_locator.get_attribute('value') or ''
                print(f"  - 逐字符输入后值: '{value_after}'")
            
            # 最终验证
            if value_after == pid:
                print(f"  ✓ PID填写成功！当前值: '{value_after}'")
            else:
                print(f"  ⚠ PID填写可能不完整，期望: '{pid}', 实际: '{value_after}'")
            
        except Exception as e:
            print(f"  ✗ 填写PID时出错: {type(e).__name__} - {str(e)}")
            import traceback
            print(f"  详细错误: {traceback.format_exc()}")
        
        # 触发搜索/选择
        print("\n  - 尝试触发搜索/选择...")
        try:
            # 按回车键
            await pid_input_locator.press('Enter')
            await asyncio.sleep(1)
            print("  ✓ 已按回车键")
        except Exception as e:
            print(f"  - 按回车键失败: {e}")
        
        print(f"{'='*60}\n")
        
        # 5. 选择时间范围
        print(f"\n{'='*60}")
        print(f"步骤5: 选择时间范围（{time_range}）")
        print(f"{'='*60}")
        
        # 时间范围映射（用于查找选项）
        time_range_map = {
            '当天': ['当天', '今天', '今日'],
            '本周': ['本周', '本周（相对）'],
            '一周': ['一周', '7天', '7天（相对）'],
            '上周': ['上周', '上周（相对）'],
            '30天': ['30天', '30天（相对）']
        }
        
        try:
            # 在SLS iframe中查找时间选择器
            time_selector_locator = None
            
            print("  - 在SLS iframe中查找时间选择器...")
            try:
                time_selector = sls_frame.locator('div[data-spm-click*="time"]').first
                if await time_selector.count() > 0:
                    is_visible = await time_selector.is_visible()
                    if is_visible:
                        time_selector_locator = time_selector
                        print(f"  ✓ 在SLS iframe中找到时间选择器")
            except Exception as e:
                print(f"  ✗ 在SLS iframe中查找时间选择器失败: {e}")
            
            if time_selector_locator:
                # 点击时间选择器按钮
                print("  - 点击时间选择器按钮...")
                await time_selector_locator.click()
                await asyncio.sleep(1)  # 等待弹窗出现
                
                # 查找并点击时间范围选项
                print(f"  - 在SLS iframe中查找'{time_range}'选项...")
                time_option_locator = None
                
                # 获取该时间范围的所有可能文本
                search_texts = time_range_map.get(time_range, [time_range])
                
                for search_text in search_texts:
                    try:
                        # 方式1: 使用has-text查找
                        option_locator = sls_frame.locator(f'li.obviz-base-li-block:has-text("{search_text}")').first
                        if await option_locator.count() > 0:
                            is_visible = await option_locator.is_visible()
                            if is_visible:
                                time_option_locator = option_locator
                                print(f"  ✓ 在SLS iframe中找到'{search_text}'选项")
                                break
                    except Exception:
                        pass
                
                # 如果找不到，尝试通过文本查找
                if not time_option_locator:
                    for search_text in search_texts:
                        try:
                            option_locator = sls_frame.locator(f'text={search_text}').first
                            if await option_locator.count() > 0:
                                time_option_locator = option_locator
                                print(f"  ✓ 在SLS iframe中通过文本找到'{search_text}'选项")
                                break
                        except Exception:
                            pass
                
                if time_option_locator:
                    # 点击时间范围选项
                    print(f"  - 点击'{time_range}'选项...")
                    await time_option_locator.click()
                    await asyncio.sleep(2)  # 等待页面加载
                    print(f"  ✓ 已选择时间范围：{time_range}")
                else:
                    print(f"  ✗ 未找到'{time_range}'选项，尝试的文本：{search_texts}")
            else:
                print("  ✗ 未找到时间选择器")
        except Exception as e:
            print(f"  ✗ 选择时间范围时出错: {type(e).__name__} - {str(e)}")
            import traceback
            print(f"  详细错误: {traceback.format_exc()}")
        
        print(f"{'='*60}\n")
        
        # 6. 打印SLS iframe中的所有元素（用于调试）
        print(f"\n{'='*60}")
        print(f"步骤6: 打印SLS iframe中的所有元素（用于判断查询条件和输出内容）")
        print(f"{'='*60}")
        
        try:
            print("\n【查询条件区域】")
            # 查找所有筛选条件
            filter_texts = await sls_frame.query_selector_all('span.obviz-base-filterText')
            print(f"  - 找到 {len(filter_texts)} 个筛选条件标签:")
            for idx, filter_text in enumerate(filter_texts[:20], 1):
                try:
                    text = await filter_text.inner_text()
                    print(f"    {idx}. {text}")
                except Exception:
                    pass
            
            # 查找所有输入框
            inputs = await sls_frame.query_selector_all('input')
            print(f"\n  - 找到 {len(inputs)} 个输入框:")
            for idx, inp in enumerate(inputs[:20], 1):
                try:
                    input_type = await inp.get_attribute('type') or 'text'
                    input_id = await inp.get_attribute('id') or ''
                    input_class = await inp.get_attribute('class') or ''
                    input_value = await inp.get_attribute('value') or ''
                    placeholder = await inp.get_attribute('placeholder') or ''
                    print(f"    {idx}. type={input_type}, id={input_id[:50]}, class={input_class[:50]}, value={input_value[:50]}, placeholder={placeholder[:50]}")
                except Exception:
                    pass
            
            # 查找所有按钮
            buttons = await sls_frame.query_selector_all('button, div[role="button"], div[class*="btn"]')
            print(f"\n  - 找到 {len(buttons)} 个按钮:")
            for idx, btn in enumerate(buttons[:20], 1):
                try:
                    btn_text = await btn.inner_text()
                    btn_class = await btn.get_attribute('class') or ''
                    print(f"    {idx}. 文本='{btn_text[:50]}', class={btn_class[:50]}")
                except Exception:
                    pass
            
            print("\n【输出内容区域】")
            # 查找所有表格行
            table_rows = await sls_frame.query_selector_all('div.obviz-base-easyTable-row, tr, div[class*="table"]')
            print(f"  - 找到 {len(table_rows)} 个表格行/行元素")
            
            # 查找所有表格单元格
            table_cells = await sls_frame.query_selector_all('div.obviz-base-easyTable-cell, td, div[class*="table-cell"]')
            print(f"  - 找到 {len(table_cells)} 个表格单元格")
            
            # 查找所有包含数字的元素（可能是成功率等数据）
            print(f"\n  - 查找包含数字的元素（可能是数据）:")
            all_spans = await sls_frame.query_selector_all('span, div[class*="split-container"]')
            number_count = 0
            for span in all_spans[:50]:
                try:
                    text = await span.inner_text()
                    if text and re.match(r'^\d+\.?\d*$', text.strip()):
                        parent_info = await span.evaluate('''el => {
                            const parent = el.parentElement;
                            return {
                                parentTag: parent ? parent.tagName : '',
                                parentClass: parent ? (parent.className || '') : '',
                                outerHTML: el.outerHTML.substring(0, 150)
                            };
                        }''')
                        print(f"    {number_count+1}. 值='{text.strip()}', 父元素={parent_info.get('parentTag', '')}, class={parent_info.get('parentClass', '')[:50]}")
                        print(f"       HTML: {parent_info.get('outerHTML', '')}")
                        number_count += 1
                        if number_count >= 20:
                            break
                except Exception:
                    continue
            
            # 查找所有div元素（可能包含重要信息）
            print(f"\n  - 查找重要的div元素:")
            important_divs = await sls_frame.query_selector_all('div[class*="table"], div[class*="cell"], div[class*="row"], div[class*="container"]')
            print(f"    找到 {len(important_divs)} 个可能重要的div元素")
            for idx, div in enumerate(important_divs[:10], 1):
                try:
                    div_class = await div.get_attribute('class') or ''
                    div_text = await div.inner_text()
                    if div_text and len(div_text.strip()) > 0:
                        print(f"    {idx}. class={div_class[:80]}, text='{div_text[:50]}'")
                except Exception:
                    pass
                    
        except Exception as e:
            print(f"  ✗ 打印元素时出错: {type(e).__name__} - {str(e)}")
            import traceback
            print(f"  详细错误: {traceback.format_exc()}")
        
        print(f"\n{'='*60}")
        print(f"步骤7: 等待数据加载并提取成功率")
        print(f"{'='*60}")
        
        print("  - 等待页面加载完成...")
        await asyncio.sleep(3)
        
        # 7. 从表格中提取数据
        success_rate = None
        all_data = []
        
        try:
            # 在SLS iframe中查找"客户签名视角 -剔除重试过程"表格
            print("  - 在SLS iframe中查找'客户签名视角 -剔除重试过程'表格...")
            
            # 方法1: 先找到包含标题的元素，然后定位到对应的表格
            target_table_container = None
            
            try:
                # 查找包含"客户签名视角 -剔除重试过程"标题的元素
                title_locator = sls_frame.locator('span.chartPanel-m__text__e25a6898:has-text("客户签名视角 -剔除重试过程")')
                title_count = await title_locator.count()
                
                if title_count > 0:
                    print(f"  ✓ 找到标题元素")
                    # 找到标题后，向上查找包含表格的容器
                    # 表格在 id="sls_chart_*" 的容器中
                    title_element = title_locator.first
                    
                    # 通过JavaScript查找包含表格的父容器
                    container_info = await title_element.evaluate('''el => {
                        // 向上查找包含表格的容器
                        let current = el;
                        while (current) {
                            // 查找包含 id="sls_chart_" 的容器
                            if (current.id && current.id.startsWith('sls_chart_')) {
                                return {
                                    found: true,
                                    id: current.id,
                                    hasTable: current.querySelector('div.obviz-base-easyTable-body') !== null
                                };
                            }
                            current = current.parentElement;
                        }
                        return { found: false };
                    }''')
                    
                    if container_info.get('found'):
                        print(f"  ✓ 找到表格容器: {container_info.get('id')}")
                        # 通过ID定位表格容器
                        target_table_container = sls_frame.locator(f'#{container_info["id"]}')
                    else:
                        # 如果找不到ID，尝试通过标题元素的父容器查找
                        print("  - 尝试通过标题元素的父容器查找表格...")
                        target_table_container = title_locator.locator('xpath=ancestor::div[contains(@id, "sls_chart_")]')
                        container_count = await target_table_container.count()
                        if container_count == 0:
                            target_table_container = None
            except Exception as e:
                print(f"  ⚠ 查找标题元素时出错: {e}")
            
            # 方法2: 如果方法1失败，直接查找包含表格的容器
            if not target_table_container:
                print("  - 尝试直接查找包含表格的容器...")
                try:
                    # 查找所有包含表格的容器
                    chart_containers = await sls_frame.query_selector_all('div[id^="sls_chart_"]')
                    print(f"    找到 {len(chart_containers)} 个图表容器")
                    
                    for container in chart_containers:
                        # 检查容器内是否有"客户签名视角"标题
                        title_in_container = await container.query_selector('span:has-text("客户签名视角 -剔除重试过程")')
                        if title_in_container:
                            # 检查容器内是否有表格
                            table_body = await container.query_selector('div.obviz-base-easyTable-body')
                            if table_body:
                                container_id = await container.get_attribute('id')
                                print(f"  ✓ 找到目标表格容器: {container_id}")
                                target_table_container = sls_frame.locator(f'#{container_id}')
                                break
                except Exception as e:
                    print(f"  ⚠ 直接查找容器时出错: {e}")
            
            # 在目标表格容器中查找表格行
            if target_table_container:
                print("  - 在目标表格容器中查找数据行...")
                # 只查找表格body中的行（排除表头）
                table_rows = await target_table_container.locator('div.obviz-base-easyTable-body div.obviz-base-easyTable-row').all()
            else:
                print("  ⚠ 未找到目标表格容器，使用通用选择器查找...")
                # 回退到原来的方法，但只查找表格body中的行
                table_rows = await sls_frame.locator('div.obviz-base-easyTable-body div.obviz-base-easyTable-row').all()
            
            if table_rows and len(table_rows) > 0:
                print(f"  ✓ 找到 {len(table_rows)} 行数据")
                
                for idx, row in enumerate(table_rows):
                    try:
                        # 获取该行的所有单元格（只获取数据单元格，排除表头）
                        cells = await row.query_selector_all('div.obviz-base-easyTable-cell:not(.obviz-base-easyTable-cell-hasFilter)')
                        
                        # 如果上面的选择器没找到，使用通用选择器
                        if not cells or len(cells) < 11:
                            cells = await row.query_selector_all('div.obviz-base-easyTable-cell')
                        
                        if cells and len(cells) >= 11:
                            # 根据HTML结构，提取"客户签名视角"表格的各列数据
                            row_data = {}
                            try:
                                # 从单元格中提取文本（通过 table-m__split-container 容器）
                                async def extract_cell_text(cell):
                                    """从单元格中提取文本，优先从 table-m__split-container 中提取"""
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
                                
                                # 从单元格中提取文本（通过 table-m__split-container 容器）
                                async def extract_cell_text(cell):
                                    """从单元格中提取文本，优先从 table-m__split-container 中提取"""
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
                                
                                # 第1列: PID
                                cell1_text = await extract_cell_text(cells[0])
                                row_data['pid'] = cell1_text.strip()
                                
                                # 第2列: signname（签名名称）
                                cell2_text = await extract_cell_text(cells[1])
                                row_data['signname'] = cell2_text.strip()
                                row_data['sign_name'] = row_data['signname']  # 向后兼容
                                
                                # 第3列: 短信类型
                                cell3_text = await extract_cell_text(cells[2])
                                row_data['sms_type'] = cell3_text.strip()
                                row_data['template_type'] = row_data['sms_type']  # 向后兼容
                                
                                # 第4列: 提交量
                                cell4_text = await extract_cell_text(cells[3]) if len(cells) > 3 else ''
                                row_data['submit_count'] = cell4_text.strip() if cell4_text else ''
                                row_data['total_sent'] = row_data['submit_count']  # 向后兼容
                                
                                # 第5列: 回执量
                                cell5_text = await extract_cell_text(cells[4]) if len(cells) > 4 else ''
                                row_data['receipt_count'] = cell5_text.strip() if cell5_text else ''
                                row_data['total_success'] = row_data['receipt_count']  # 向后兼容
                                
                                # 第6列: 回执成功量
                                cell6_text = await extract_cell_text(cells[5]) if len(cells) > 5 else ''
                                row_data['receipt_success_count'] = cell6_text.strip() if cell6_text else ''
                                row_data['total_failed'] = row_data['receipt_success_count']  # 向后兼容（注意：这个字段名不太准确，但保持兼容）
                                
                                # 第7列: 回执率
                                cell7_text = await extract_cell_text(cells[6]) if len(cells) > 6 else ''
                                row_data['receipt_rate'] = cell7_text.strip() if cell7_text else ''
                                
                                # 第8列: 回执成功率（这是主要需要的字段）
                                cell8_text = await extract_cell_text(cells[7]) if len(cells) > 7 else ''
                                row_data['receipt_success_rate'] = cell8_text.strip() if cell8_text else ''
                                row_data['success_rate'] = row_data['receipt_success_rate']  # 向后兼容
                                
                                # 第9列: 十秒回执率
                                cell9_text = await extract_cell_text(cells[8]) if len(cells) > 8 else ''
                                row_data['receipt_rate_10s'] = cell9_text.strip() if cell9_text else ''
                                
                                # 第10列: 三十秒回执率
                                cell10_text = await extract_cell_text(cells[9]) if len(cells) > 9 else ''
                                row_data['receipt_rate_30s'] = cell10_text.strip() if cell10_text else ''
                                
                                # 第11列: 六十秒回执率
                                cell11_text = await extract_cell_text(cells[10]) if len(cells) > 10 else ''
                                row_data['receipt_rate_60s'] = cell11_text.strip() if cell11_text else ''
                                
                                # 设置主要成功率（用于返回）
                                if not success_rate or idx == 0:
                                    success_rate = row_data['receipt_success_rate']
                                
                                all_data.append(row_data)
                                print(f"  行 {idx+1}: PID={row_data.get('pid', '')}, 签名={row_data.get('signname', '')}, "
                                      f"类型={row_data.get('sms_type', '')}, 提交量={row_data.get('submit_count', '')}, "
                                      f"回执量={row_data.get('receipt_count', '')}, 回执成功率={row_data.get('receipt_success_rate', 'N/A')}%")
                            except Exception as e:
                                print(f"  处理第 {idx+1} 行时出错: {e}")
                                continue
                    except Exception as e:
                        print(f"  解析第 {idx+1} 行时出错: {e}")
                        continue
            else:
                # 如果没有找到表格行，尝试其他方式提取成功率
                try:
                    success_rate_elements = await sls_frame.query_selector_all(SELECTORS['success_rate_value'])
                    for element in success_rate_elements:
                        text = await element.inner_text()
                        if re.match(r'^\d+\.\d+$', text.strip()):
                            success_rate = text.strip()
                            print(f"找到成功率: {success_rate}%")
                            break
                except Exception as e:
                    print(f"尝试其他方式提取成功率时出错: {e}")
        
        except Exception as e:
            print(f"提取数据时出错: {e}")
        
        # 检查是否成功提取到成功率
        if success_rate or all_data:
            result = {
                'success': True,
                'success_rate': success_rate or (all_data[0].get('receipt_success_rate') if all_data else None),
                'pid': pid,
                'time_range': time_range,
                'data': all_data if all_data else None,
                'error': None
            }
            
            if all_data:
                result['total_count'] = len(all_data)
            
            return result
        else:
            return {
                'success': False,
                'success_rate': None,
                'pid': pid,
                'time_range': time_range,
                'data': None,
                'error': '未能从页面中提取到成功率数据，请检查查询条件和页面结构'
            }
            
    except PlaywrightTimeoutError as e:
        error_msg = f"操作超时（超过 {timeout/1000} 秒）: {str(e)}"
        print(f"错误: {error_msg}")
        return {
            'success': False,
            'success_rate': None,
            'pid': pid,
            'time_range': time_range,
            'data': None,
            'error': error_msg
        }
    except Exception as e:
        error_msg = f"查询过程中发生错误: {str(e)}"
        print(f"错误: {error_msg}")
        return {
            'success': False,
            'success_rate': None,
            'pid': pid,
            'time_range': time_range,
            'data': None,
            'error': error_msg
        }
