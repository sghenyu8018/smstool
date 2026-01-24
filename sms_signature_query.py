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
        # 1. 跳转到短信签名查询页面
        #  - 使用 Playwright 的 goto 方法访问指定查询页面 URL。
        #  - timeout: 本次跳转的超时限制，单位为毫秒。
        #  - wait_until='domcontentloaded   ' 保证页面 DOM 结构加载完成（注：参数多了空格，实际建议为 'domcontentloaded'）。
        await page.goto(SIGN_QUERY_URL, timeout=timeout, wait_until='domcontentloaded')
        
        # 2. 等待页面加载完成，确保客户PID输入框元素可见
        #  - 使用 wait_for_selector 方法等待 SELECTORS['partner_id'] 指定的元素（PID 输入框）变为可见状态
        #  - timeout: 最长等待时间（毫秒）
        # 注意：页面上的输入框实际上并没有"id=partner_id"或者类似“partner_id”字样
        # 这里只是我们在 SELECTORS 中自定义的 key，用于便于书写和维护。
        # SELECTORS['partner_id'] 实际存储的是用于定位“客户PID”输入框的 CSS 选择器，
        # 比如 'span.obviz-base-filterInput input[autocomplete="off"]'
        # 这个选择器意思是：查找 class 为 obviz-base-filterInput 的 span 内部 autocomplete="off" 的 input 框
        # 所以，通过 SELECTORS['partner_id'] 能够定位到页面上的“客户PID”输入框
        await page.wait_for_selector(SELECTORS['partner_id'], timeout=timeout, state='visible')
        
        # 3. 填写客户PID
        #  - 打印当前填写的 PID 信息到控制台用于调试
        #  - 使用 fill 方法向 PID 输入框内填入传入的 pid 值
        #  - 随后等待 0.5 秒（500ms），模拟人类输入，避免被风控。
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


async def query_sms_success_rate(
    page: Page,
    pid: Optional[str] = None,
    timeout: int = 30000
) -> Dict[str, any]:
    """
    查询短信签名成功率
    
    Args:
        page: Playwright Page 对象（需要已登录的会话）
        pid: 客户PID（如果不提供，则从环境变量 SMS_PID 读取）
        timeout: 操作超时时间（毫秒），默认30秒
        
    Returns:
        Dict: 查询结果字典，包含以下字段：
            - success (bool): 是否查询成功
            - success_rate (Optional[str]): 成功率（成功时返回）
            - pid (Optional[str]): 客户PID
            - data (Optional[List]): 所有数据行（如果有多行）
            - error (Optional[str]): 错误信息（失败时返回）
            
    # Example:
    #     >>> result = await query_sms_success_rate(page=page, pid="100000103722927")
    #     >>> if result['success']:
    #     ...     print(f"成功率：{result['success_rate']}%")
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
            # 等待菜单项出现
            menu_item = await page.wait_for_selector(
                SELECTORS['success_rate_menu_item'],
                timeout=10000,
                state='visible'
            )
            await menu_item.click()
            print("已点击'求德大盘'菜单项")
            await asyncio.sleep(2)  # 等待页面切换/加载
        except PlaywrightTimeoutError:
            # 如果找不到精确选择器，尝试其他方式
            try:
                # 尝试通过文本内容查找
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
        await asyncio.sleep(3)  # 增加等待时间，确保动态内容加载完成
        
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
            await asyncio.sleep(2)  # 额外等待，确保内容渲染
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
                                        # 等待输入框变为可见
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
                # 检查所有frame中的相关元素
                for idx, frame in enumerate(iframes):
                    try:
                        pid_labels = await frame.query_selector_all('span.obviz-base-filterText')
                        print(f"  - Frame {idx} 有 {len(pid_labels)} 个filterText元素")
                        for label_idx, label in enumerate(pid_labels[:3], 1):  # 只显示前3个
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
                # 使用JavaScript直接设置值并触发事件
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
                
                await pid_input_locator.type(pid, delay=50)  # 每个字符延迟50ms
                await asyncio.sleep(0.5)
                
                value_after = await pid_input_locator.get_attribute('value') or ''
                print(f"  - 逐字符输入后值: '{value_after}'")
            
            # 最终验证
            if value_after == pid:
                print(f"  ✓ PID填写成功！当前值: '{value_after}'")
            else:
                print(f"  ⚠ PID填写可能不完整，期望: '{pid}', 实际: '{value_after}'")
                # 即使不匹配也继续，可能页面有格式化
            
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
        
        # 不需要点击搜索图标，回车即可触发查询
        
        print(f"{'='*60}\n")
        
        # 5. 选择时间范围（30天）
        print(f"\n{'='*60}")
        print(f"步骤5: 选择时间范围（30天）")
        print(f"{'='*60}")
        
        try:
            # 在SLS iframe中查找时间选择器
            time_selector_locator = None
            
            print("  - 在SLS iframe中查找时间选择器...")
            try:
                # 查找时间选择器按钮
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
                
                # 查找并点击"30天"选项
                print("  - 在SLS iframe中查找'30天'选项...")
                time_option_locator = None
                
                try:
                    option_locator = sls_frame.locator('li.obviz-base-li-block:has-text("30天")').first
                    if await option_locator.count() > 0:
                        is_visible = await option_locator.is_visible()
                        if is_visible:
                            time_option_locator = option_locator
                            print(f"  ✓ 在SLS iframe中找到'30天'选项")
                except Exception:
                    pass
                
                # 如果找不到，尝试通过文本查找
                if not time_option_locator:
                    try:
                        option_locator = sls_frame.locator('text=30天').first
                        if await option_locator.count() > 0:
                            time_option_locator = option_locator
                            print(f"  ✓ 在SLS iframe中通过文本找到'30天'选项")
                    except Exception:
                        pass
                
                if time_option_locator:
                    # 点击30天选项
                    print("  - 点击'30天'选项...")
                    await time_option_locator.click()
                    await asyncio.sleep(2)  # 等待页面加载
                    print("  ✓ 已选择时间范围：30天")
                else:
                    print("  ✗ 未找到'30天'选项")
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
            for idx, filter_text in enumerate(filter_texts[:20], 1):  # 只显示前20个
                try:
                    text = await filter_text.inner_text()
                    print(f"    {idx}. {text}")
                except Exception:
                    pass
            
            # 查找所有输入框
            inputs = await sls_frame.query_selector_all('input')
            print(f"\n  - 找到 {len(inputs)} 个输入框:")
            for idx, inp in enumerate(inputs[:20], 1):  # 只显示前20个
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
            for idx, btn in enumerate(buttons[:20], 1):  # 只显示前20个
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
            for span in all_spans[:50]:  # 只检查前50个
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
                        if number_count >= 20:  # 只显示前20个数字
                            break
                except Exception:
                    continue
            
            # 查找所有div元素（可能包含重要信息）
            print(f"\n  - 查找重要的div元素:")
            important_divs = await sls_frame.query_selector_all('div[class*="table"], div[class*="cell"], div[class*="row"], div[class*="container"]')
            print(f"    找到 {len(important_divs)} 个可能重要的div元素")
            for idx, div in enumerate(important_divs[:10], 1):  # 只显示前10个
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
        await asyncio.sleep(3)  # 等待表格数据加载
        
        # 7. 从表格中提取数据
        success_rate = None
        all_data = []
        
        try:
            # 在SLS iframe中查找表格行
            print("  - 在SLS iframe中查找表格数据...")
            table_rows = await sls_frame.query_selector_all(SELECTORS['success_rate_table_row'])
            
            if table_rows and len(table_rows) > 0:
                print(f"找到 {len(table_rows)} 行数据")
                
                for idx, row in enumerate(table_rows):
                    try:
                        # 获取该行的所有单元格
                        cells = await row.query_selector_all('div.obviz-base-easyTable-cell')
                        
                        if cells and len(cells) >= 11:
                            # 根据HTML结构，提取各列数据
                            row_data = {}
                            try:
                                # 第1列: PID
                                cell1_text = await cells[0].inner_text()
                                row_data['pid'] = cell1_text.strip()
                                
                                # 第2列: 签名名称
                                cell2_text = await cells[1].inner_text()
                                row_data['sign_name'] = cell2_text.strip()
                                
                                # 第3列: 模板类型
                                cell3_text = await cells[2].inner_text()
                                row_data['template_type'] = cell3_text.strip()
                                
                                # 第4-11列: 各种统计数据
                                row_data['total_sent'] = await cells[3].inner_text() if len(cells) > 3 else ''
                                row_data['total_success'] = await cells[4].inner_text() if len(cells) > 4 else ''
                                row_data['total_failed'] = await cells[5].inner_text() if len(cells) > 5 else ''
                                
                                # 提取成功率（使用指定的选择器查找）
                                # 使用 SELECTORS['success_rate_value'] 来查找成功率值
                                success_rate_cells = await row.query_selector_all(SELECTORS['success_rate_value'])
                                if success_rate_cells:
                                    # 查找包含数字的单元格（成功率通常是数字格式，如 100.0, 74.35 等）
                                    for cell in success_rate_cells:
                                        cell_text = await cell.inner_text()
                                        cell_text = cell_text.strip()
                                        # 检查是否是数字格式（可能包含小数点）
                                        if re.match(r'^\d+\.?\d*$', cell_text):
                                            # 通常成功率在表格的特定列，这里取第一个匹配的数字作为成功率
                                            if not row_data.get('success_rate'):
                                                row_data['success_rate'] = cell_text
                                                if not success_rate or idx == 0:
                                                    success_rate = cell_text
                                            break
                                
                                # 如果上面的方法没找到，使用原来的方法
                                if not row_data.get('success_rate'):
                                    for i in range(6, min(11, len(cells))):
                                        cell_text = await cells[i].inner_text()
                                        # 检查是否是百分比格式（包含小数点的数字）
                                        if re.match(r'^\d+\.?\d*$', cell_text.strip()):
                                            if not success_rate or idx == 0:
                                                success_rate = cell_text.strip()
                                            row_data['success_rate'] = cell_text.strip()
                                            break
                                
                                all_data.append(row_data)
                                print(f"  行 {idx+1}: PID={row_data.get('pid', '')}, 签名={row_data.get('sign_name', '')}, 成功率={row_data.get('success_rate', 'N/A')}%")
                            except Exception as e:
                                print(f"  处理第 {idx+1} 行时出错: {e}")
                                continue
                    except Exception as e:
                        print(f"  解析第 {idx+1} 行时出错: {e}")
                        continue
            else:
                # 如果没有找到表格行，尝试其他方式提取成功率
                try:
                    success_rate_elements = await page.query_selector_all(SELECTORS['success_rate_value'])
                    for element in success_rate_elements:
                        text = await element.inner_text()
                        # 检查是否是百分比格式
                        if re.match(r'^\d+\.\d+$', text.strip()):
                            success_rate = text.strip()
                            print(f"找到成功率: {success_rate}%")
                            break
                except Exception as e:
                    print(f"尝试其他方式提取成功率时出错: {e}")
        
        except Exception as e:
            print(f"提取数据时出错: {e}")
        
        # 7. 检查是否成功提取到成功率
        if success_rate or all_data:
            result = {
                'success': True,
                'success_rate': success_rate or (all_data[0].get('success_rate') if all_data else None),
                'pid': pid,
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
            'data': None,
            'error': error_msg
        }


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
            
            # 查询短信签名成功率
            print("\n" + "="*50)
            print("开始查询短信签名成功率...")
            print("="*50)
            
            success_rate_result = await query_sms_success_rate(page=page)
            
            # 处理成功率查询结果
            if success_rate_result['success']:
                print(f"\n[OK] 成功率查询成功！")
                print(f"成功率: {success_rate_result['success_rate']}%")
                
                # 如果有多行数据，显示所有数据
                if success_rate_result.get('data'):
                    print(f"\n共找到 {success_rate_result.get('total_count', 0)} 条记录:")
                    for i, row in enumerate(success_rate_result['data'], 1):
                        print(f"  {i}. 签名: {row.get('sign_name', 'N/A')}, "
                              f"成功率: {row.get('success_rate', 'N/A')}%")
            else:
                print(f"\n[FAIL] 成功率查询失败: {success_rate_result['error']}")
                
        finally:
            # 清理资源
            print("\n正在关闭浏览器...")
            await context.close()
            await browser.close()
            await playwright.stop()
            print("已关闭浏览器")
    
    # 运行示例
    asyncio.run(main())