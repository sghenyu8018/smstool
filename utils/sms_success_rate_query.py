"""
短信签名成功率查询模块
提供短信签名成功率查询功能
"""
import asyncio
import re
from typing import Dict, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from .constants import SUCCESS_RATE_QUERY_URL, SELECTORS
from .helpers import extract_cell_text
from .logger import get_logger


async def _select_time_range_only(
    page: Page,
    pid: Optional[str],
    time_range: str,
    timeout: int
) -> Dict[str, any]:
    """
    只切换时间范围，不重新输入PID（内部函数）
    
    Args:
        page: Playwright Page 对象
        pid: 客户PID（用于日志和结果）
        time_range: 时间范围
        timeout: 操作超时时间
        
    Returns:
        Dict: 查询结果字典
    """
    logger = get_logger('sms_success_rate')
    
    try:
        # 获取SLS iframe（应该已经存在）
        print(f"\n{'='*60}")
        print(f"切换时间范围（{time_range}），PID已输入，无需重新输入")
        print(f"{'='*60}")
        
        # 查找SLS iframe
        iframes = page.frames
        sls_frame = None
        for frame in iframes:
            if 'sls4service.console.aliyun.com' in frame.url and 'dashboard' in frame.url:
                sls_frame = frame
                break
        
        if not sls_frame:
            return {
                'success': False,
                'success_rate': None,
                'pid': pid,
                'time_range': time_range,
                'data': None,
                'error': '未找到SLS iframe，请先执行完整的查询流程'
            }
        
        # 选择时间范围（复用原有逻辑）
        print(f"\n步骤: 选择时间范围（{time_range}）")
        
        time_range_map = {
            '当天': ['当天', '今天', '今日'],
            '本周': ['本周', '本周（相对）'],
            '一周': ['一周', '7天', '7天（相对）'],
            '上周': ['上周', '上周（相对）'],
            '30天': ['30天', '30天（相对）']
        }
        
        try:
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
                print("  - 点击时间选择器按钮...")
                await time_selector_locator.click()
                await asyncio.sleep(1)
                
                print(f"  - 在SLS iframe中查找'{time_range}'选项...")
                time_option_locator = None
                search_texts = time_range_map.get(time_range, [time_range])
                
                for search_text in search_texts:
                    try:
                        option_locator = sls_frame.locator(f'li.obviz-base-li-block:has-text("{search_text}")').first
                        if await option_locator.count() > 0:
                            is_visible = await option_locator.is_visible()
                            if is_visible:
                                time_option_locator = option_locator
                                print(f"  ✓ 在SLS iframe中找到'{search_text}'选项")
                                break
                    except Exception:
                        pass
                
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
                    print(f"  - 点击'{time_range}'选项...")
                    await time_option_locator.click()
                    await asyncio.sleep(2)
                    print(f"  ✓ 已选择时间范围：{time_range}")
                else:
                    print(f"  ✗ 未找到'{time_range}'选项")
                    return {
                        'success': False,
                        'success_rate': None,
                        'pid': pid,
                        'time_range': time_range,
                        'data': None,
                        'error': f"未找到时间范围选项：{time_range}"
                    }
            else:
                print("  ✗ 未找到时间选择器")
                return {
                    'success': False,
                    'success_rate': None,
                    'pid': pid,
                    'time_range': time_range,
                    'data': None,
                    'error': '未找到时间选择器'
                }
        except Exception as e:
            print(f"  ✗ 选择时间范围时出错: {type(e).__name__} - {str(e)}")
            return {
                'success': False,
                'success_rate': None,
                'pid': pid,
                'time_range': time_range,
                'data': None,
                'error': f"选择时间范围时出错: {str(e)}"
            }
        
        # 等待数据加载并提取数据（复用原有逻辑）
        print(f"\n步骤: 等待数据加载并提取成功率")
        
        # 等待表格数据加载
        max_wait_retries = 20
        retry_count = 0
        table_ready = False
        target_table_container = None
        
        while retry_count < max_wait_retries and not table_ready:
            try:
                title_locator = sls_frame.locator('span.chartPanel-m__text__e25a6898:has-text("客户签名视角 -剔除重试过程")')
                title_count = await title_locator.count()
                
                if title_count > 0:
                    title_element = title_locator.first
                    container_info = await title_element.evaluate('''el => {
                        let current = el;
                        while (current) {
                            if (current.id && current.id.startsWith('sls_chart_')) {
                                const tableBody = current.querySelector('div.obviz-base-easyTable-body');
                                const rows = tableBody ? tableBody.querySelectorAll('div.obviz-base-easyTable-row') : [];
                                return {
                                    found: true,
                                    id: current.id,
                                    hasTable: tableBody !== null,
                                    rowCount: rows.length
                                };
                            }
                            current = current.parentElement;
                        }
                        return { found: false };
                    }''')
                    
                    if container_info.get('found'):
                        container_id = container_info.get('id')
                        row_count = container_info.get('rowCount', 0)
                        
                        if row_count > 0:
                            target_table_container = sls_frame.locator(f'#{container_id}')
                            table_ready = True
                            print(f"  ✓ 找到表格容器: {container_id}，包含 {row_count} 行数据")
                            break
            except Exception:
                pass
            
            retry_count += 1
            if not table_ready and retry_count < max_wait_retries:
                await asyncio.sleep(1)
        
        if not table_ready:
            print(f"  ⚠ 等待表格数据加载超时，尝试继续查找...")
        
        await asyncio.sleep(1)
        
        # 提取数据（复用原有逻辑，简化版）
        success_rate = None
        all_data = []
        matched_data = []
        
        try:
            if not target_table_container:
                title_locator = sls_frame.locator('span.chartPanel-m__text__e25a6898:has-text("客户签名视角 -剔除重试过程")')
                title_count = await title_locator.count()
                
                if title_count > 0:
                    title_element = title_locator.first
                    container_info = await title_element.evaluate('''el => {
                        let current = el;
                        while (current) {
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
                        target_table_container = sls_frame.locator(f'#{container_info["id"]}')
            
            if target_table_container:
                table_body = target_table_container.locator('div.obviz-base-easyTable-body')
                rows = table_body.locator('div.obviz-base-easyTable-row')
                row_count = await rows.count()
                print(f"  - 找到 {row_count} 行数据")
                
                for row_idx in range(row_count):
                    row = rows.nth(row_idx)
                    cells = row.locator('div.obviz-base-easyTable-cell')
                    cell_count = await cells.count()
                    
                    if cell_count < 8:
                        continue
                    
                    # 提取数据
                    row_data = {}
                    try:
                        # PID (第1个单元格)
                        pid_cell = cells.nth(0)
                        row_pid = await extract_cell_text(pid_cell)
                        row_data['pid'] = row_pid.strip()
                        
                        # Signname (第2个单元格)
                        signname_cell = cells.nth(1)
                        signname = await extract_cell_text(signname_cell)
                        row_data['signname'] = signname.strip()
                        
                        # SMS Type (第3个单元格)
                        sms_type_cell = cells.nth(2)
                        sms_type = await extract_cell_text(sms_type_cell)
                        row_data['sms_type'] = sms_type.strip()
                        
                        # Submit Count (第4个单元格)
                        submit_count_cell = cells.nth(3)
                        submit_count = await extract_cell_text(submit_count_cell)
                        row_data['submit_count'] = submit_count.strip()
                        
                        # Receipt Success Rate (第8个单元格)
                        success_rate_cell = cells.nth(7)
                        success_rate_text = await extract_cell_text(success_rate_cell)
                        row_data['receipt_success_rate'] = success_rate_text.strip()
                        
                        all_data.append(row_data)
                        
                        # 如果提供了PID，检查是否匹配
                        if pid and row_pid.strip() == pid:
                            matched_data.append(row_data)
                    except Exception as e:
                        print(f"  ⚠ 提取第 {row_idx + 1} 行数据时出错: {e}")
                        continue
                
                if matched_data:
                    success_rate = matched_data[0].get('receipt_success_rate', '')
                    return_data = matched_data
                elif all_data:
                    success_rate = all_data[0].get('receipt_success_rate', '')
                    return_data = all_data
                else:
                    return_data = []
                    success_rate = None
                
                if success_rate and return_data:
                    return {
                        'success': True,
                        'success_rate': success_rate,
                        'pid': pid,
                        'time_range': time_range,
                        'data': return_data,
                        'total_count': len(return_data),
                        'matched_count': len(matched_data) if pid else len(return_data),
                        'error': None
                    }
                else:
                    return {
                        'success': False,
                        'success_rate': None,
                        'pid': pid,
                        'time_range': time_range,
                        'data': None,
                        'error': '未能从页面中提取到成功率数据'
                    }
            else:
                return {
                    'success': False,
                    'success_rate': None,
                    'pid': pid,
                    'time_range': time_range,
                    'data': None,
                    'error': '未找到目标表格容器'
                }
        except Exception as e:
            return {
                'success': False,
                'success_rate': None,
                'pid': pid,
                'time_range': time_range,
                'data': None,
                'error': f"提取数据时出错: {str(e)}"
            }
    except Exception as e:
        return {
            'success': False,
            'success_rate': None,
            'pid': pid,
            'time_range': time_range,
            'data': None,
            'error': f"切换时间范围时出错: {str(e)}"
        }


async def query_sms_success_rate(
    page: Page,
    pid: Optional[str] = None,
    time_range: str = '30天',
    timeout: int = 30000,
    skip_pid_input: bool = False
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
        # 如果跳过PID输入，说明已经输入过PID，只需要切换时间范围
        if skip_pid_input:
            return await _select_time_range_only(page, pid, time_range, timeout)
        
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
            # 1. 等待DOM加载完成
            await sls_frame.wait_for_load_state('domcontentloaded', timeout=15000)
            print("    ✓ DOM加载完成")
            
            # 2. 等待网络请求完成（load状态）
            try:
                await sls_frame.wait_for_load_state('load', timeout=15000)
                print("    ✓ 页面资源加载完成")
            except Exception as e:
                print(f"    ⚠ 等待load状态超时: {e}，继续执行...")
            
            # 3. 等待至少有一些可见元素出现（确保内容已渲染）
            print("    - 等待关键元素出现...")
            max_retries = 10
            retry_count = 0
            elements_ready = False
            
            while retry_count < max_retries and not elements_ready:
                try:
                    # 检查是否有任何可见的输入框或筛选条件
                    input_count = await sls_frame.locator('input').count()
                    filter_count = await sls_frame.locator('span.obviz-base-filterText').count()
                    visible_elements = await sls_frame.locator('body *:visible').count()
                    
                    print(f"    - 尝试 {retry_count + 1}/{max_retries}: 输入框={input_count}, 筛选条件={filter_count}, 可见元素={visible_elements}")
                    
                    # 如果找到至少一些元素，认为页面已加载
                    if input_count > 0 or filter_count > 0 or visible_elements > 10:
                        elements_ready = True
                        print(f"    ✓ 关键元素已出现（输入框: {input_count}, 筛选条件: {filter_count}）")
                        break
                    
                    retry_count += 1
                    if retry_count < max_retries:
                        await asyncio.sleep(1)  # 等待1秒后重试
                        
                except Exception as e:
                    print(f"    ⚠ 检查元素时出错: {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        await asyncio.sleep(1)
            
            if not elements_ready:
                print("    ⚠ 等待关键元素超时，但继续尝试查找PID输入框...")
            
            # 4. 额外等待一段时间，确保JavaScript已执行
            await asyncio.sleep(2)
            print("    ✓ 等待完成，开始查找PID输入框")
            
        except Exception as e:
            print(f"  ⚠ SLS iframe加载过程中出错: {type(e).__name__} - {str(e)}")
            print("    继续尝试查找PID输入框...")
        
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
                            print(f"  ✓ 在SLS iframe中找到PID输入框（已可见）")
                    
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
                                    if is_visible:
                                        pid_input_locator = first_input
                                        print(f"  ✓ 在SLS iframe中找到PID输入框（已激活）")
                                    else:
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
        else:
            print("\n[方式2] 跳过（方式1已成功）")
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
                            print(f"  ✓ 在SLS iframe的输入框 {inp_idx+1}中找到PID输入框")
                            break
            except Exception as e:
                print(f"  ✗ 查找失败: {type(e).__name__} - {str(e)}")
        
        # 最终检查
        print(f"\n{'='*60}")
        if not pid_input_locator:
            print("✗ 所有方式都未能找到PID输入框")
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
            # 方式1已成功，跳过方式2
        
        # 4. 填写PID（在SLS iframe中填写）
        print(f"\n{'='*60}")
        print(f"步骤4: 填写PID到输入框")
        print(f"{'='*60}")
        
        try:
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
            
            if value_after == pid:
                print(f"  ✓ PID填写成功！当前值: '{value_after}'")
            else:
                print(f"  ⚠ PID填写可能不完整，期望: '{pid}', 实际: '{value_after}'")
            
        except Exception as e:
            print(f"  ✗ 填写PID时出错: {type(e).__name__} - {str(e)}")
        
        # 触发搜索/选择
        print("\n  - 尝试触发搜索/选择...")
        try:
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
            #'当天': [ '今天'],
            #'本周': ['本周', '本周（相对）'],
            #'一周': ['1周'],
            #'上周': ['上周', '上周（相对）'],
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
                
                # 在开始查找之前，先打印出所有可用的时间范围选项
                print(f"  - 打印所有可用的时间范围选项:")
                try:
                    all_option_nodes = await sls_frame.query_selector_all("li.obviz-base-li-block")
                    print(f"    - 共找到 {len(all_option_nodes)} 个时间范围选项:")
                    for idx, node in enumerate(all_option_nodes, 1):
                        try:
                            option_text = await node.inner_text()
                            # 尝试获取更多信息（如是否可见、是否有特定属性等）
                            is_visible = await node.is_visible()
                            option_class = await node.get_attribute("class")
                            print(f"      {idx}. {option_text} (可见: {is_visible}, class: {option_class})")
                        except Exception as e:
                            print(f"      {idx}. 读取选项信息失败: {e}")
                except Exception as e:
                    print(f"    - 获取时间范围选项列表失败: {e}")
                
                for search_text in search_texts:
                    try:
                        # 方式1: 使用has-text查找
                        # 使用 Playwright 的 has-text 语法查找包含指定文本的时间选项
                        # li.obviz-base-li-block: 筛选所有时间范围下拉列表项
                        # f-string 动态插入查找的 search_text（如"当天"、"本周"等）
                        # .first 取第一个匹配的元素，以避免多个重复项
                        option_locator = sls_frame.locator(f'li.obviz-base-li-block:has-text("{search_text}")').first
                        if await option_locator.count() > 0:
                            is_visible = await option_locator.is_visible()
                            if is_visible:
                                time_option_locator = option_locator
                                print(f"  ✓ 在SLS iframe中找到'{search_text}'选项")
                                break
                    except Exception:
                        pass
                
                if time_option_locator:
                    # 点击时间范围选项
                    print(f"  - 点击'{time_range}'选项...")
                    await time_option_locator.click()
                    await asyncio.sleep(2)  # 等待页面加载
                    print(f"  ✓ 已选择时间范围：{time_range}")
                    
                    # 滚动页面到底部
                    print("  - 滚动页面到底部...")
                    try:
                        await sls_frame.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        await asyncio.sleep(0.5)  # 等待滚动完成
                        print("  ✓ 已滚动到页面底部")
                    except Exception as e:
                        print(f"  ⚠ 滚动页面时出错: {e}")
                else:
                    print(f"  ✗ 未找到'{time_range}'选项，尝试的文本：{search_texts}")
            else:
                print("  ✗ 未找到时间选择器")
        except Exception as e:
            print(f"  ✗ 选择时间范围时出错: {type(e).__name__} - {str(e)}")
        
        print(f"{'='*60}\n")
        
        # 6. 打印SLS iframe中的所有元素（用于调试）
        logger = get_logger('sms_success_rate')
        logger.log_section("步骤6: 打印SLS iframe中的所有元素（用于判断查询条件和输出内容）")
        
        try:
            logger.info("\n【查询条件区域】")
            
            filter_texts = await sls_frame.query_selector_all('span.obviz-base-filterText')
            filter_text_list = []
            logger.info(f"  - 找到 {len(filter_texts)} 个筛选条件标签:")
            for idx, filter_text in enumerate(filter_texts[:20], 1):
                try:
                    text = await filter_text.inner_text()
                    logger.info(f"    {idx}. {text}")
                    filter_text_list.append(text)
                except Exception:
                    pass
            
            inputs = await sls_frame.query_selector_all('input')
            input_list = []
            logger.info(f"\n  - 找到 {len(inputs)} 个输入框:")
            for idx, inp in enumerate(inputs[:20], 1):
                try:
                    input_type = await inp.get_attribute('type') or 'text'
                    input_value = await inp.get_attribute('value') or ''
                    input_info = f"type={input_type}, value={input_value[:50]}"
                    logger.info(f"    {idx}. {input_info}")
                    input_list.append(input_info)
                except Exception:
                    pass
            
            logger.info("\n【输出内容区域】")
            
            # 查找表格行元素，支持多种表格实现方式
            # - div.obviz-base-easyTable-row: 主要用于新版SLS前端的表格行
            # - tr: 标准HTML表格行
            # - div[class*="table"]: 匹配部分自定义类名含'table'的行元素，兼容不同产品线UI组件
            # 这里的 div[class*="table"] 选择器表示：选择 class 属性中包含 "table" 字符串的所有 div 元素
            # 这用于匹配自定义样式表格行，包括 class="custom-table-row"、class="main-table" 等。
            table_rows = await sls_frame.query_selector_all(
                'div.obviz-base-easyTable-row, tr, div[class*="table"]'
            )
            table_rows_count = len(table_rows)
            logger.info(f"  - 找到 {table_rows_count} 个表格行/行元素（“表格元素”是指表格的每一行，包括可能的tr、div或自定义行元素）")
            
            # 提取表格行的具体内容
            table_rows_content = []
            for idx, row in enumerate(table_rows[:50], 1):  # 限制最多50行，避免日志过大
                try:
                    row_text = await row.inner_text()
                    table_rows_content.append(f"行 {idx}: {row_text[:200]}")  # 限制每行200字符
                    if idx <= 10:  # 前10行详细记录
                        logger.info(f"    行 {idx}: {row_text[:200]}")
                except Exception as e:
                    table_rows_content.append(f"行 {idx}: [提取失败: {str(e)}]")
            
            table_cells = await sls_frame.query_selector_all('div.obviz-base-easyTable-cell, td, div[class*="table-cell"]')
            table_cells_count = len(table_cells)
            logger.info(f"  - 找到 {table_cells_count} 个表格单元格")
            
            # 提取表格单元格的具体内容
            table_cells_content = []
            for idx, cell in enumerate(table_cells[:100], 1):  # 限制最多100个单元格
                try:
                    cell_text = await extract_cell_text(cell)
                    if cell_text.strip():  # 只记录非空单元格
                        table_cells_content.append(f"单元格 {idx}: {cell_text.strip()[:100]}")  # 限制每个单元格100字符
                        if idx <= 20:  # 前20个单元格详细记录
                            logger.info(f"    单元格 {idx}: {cell_text.strip()[:100]}")
                except Exception as e:
                    table_cells_content.append(f"单元格 {idx}: [提取失败: {str(e)}]")
            
            # 使用日志模块记录到专门的日志文件
            log_file = logger.log_iframe_elements(
                pid=pid,
                time_range=time_range,
                filter_texts=filter_text_list,
                inputs=input_list,
                table_rows_count=table_rows_count,
                table_cells_count=table_cells_count,
                table_rows_content=table_rows_content,
                table_cells_content=table_cells_content
            )
                
        except Exception as e:
            logger.error(f"  ✗ 打印元素时出错: {type(e).__name__} - {str(e)}")
        
        print(f"\n{'='*60}")
        print(f"步骤7: 等待数据加载并提取成功率")
        print(f"{'='*60}")
        
        # 7. 等待数据加载完成
        print("  - 等待数据加载完成...")
        
        # 等待表格数据加载：等待"客户签名视角 -剔除重试过程"表格的数据行出现
        max_wait_retries = 20  # 最多等待20次，每次1秒，总共最多20秒
        retry_count = 0
        table_ready = False
        target_table_container = None
        
        while retry_count < max_wait_retries and not table_ready:
            try:
                # 直接使用定位器查找包含"客户签名视角 -剔除重试过程"标题的元素
                title_locator = sls_frame.locator('span.chartPanel-m__text__e25a6898:has-text("客户签名视角 -剔除重试过程")')
                title_count = await title_locator.count()
                
                if title_count > 0:
                    # 找到标题后，查找表格行
                    # 通过定位器找到表格容器，然后查找数据行
                    table_rows_locator = title_locator.locator('xpath=ancestor::div[contains(@id, "sls_chart_")]//div[contains(@class, "obviz-base-easyTable-row")]')
                    row_count = await table_rows_locator.count()
                    
                    if row_count > 0:
                        # 找到数据行，获取容器ID
                        title_element = title_locator.first
                        container_info = await title_element.evaluate('''el => {
                            let current = el;
                            while (current) {
                                if (current.id && current.id.startsWith('sls_chart_')) {
                                    return { found: true, id: current.id };
                                }
                                current = current.parentElement;
                            }
                            return { found: false };
                        }''')
                        
                        if container_info.get('found'):
                            container_id = container_info.get('id')
                            target_table_container = sls_frame.locator(f'#{container_id}')
                            table_ready = True
                            print(f"  ✓ 找到表格容器: {container_id}，包含 {row_count} 行数据（等待 {retry_count + 1} 次）")
                            break
                    else:
                        # 找到标题但还没有数据行，继续等待
                        if retry_count % 3 == 0:  # 每3次打印一次进度
                            print(f"    - 等待中... ({retry_count + 1}/{max_wait_retries})，表格容器已找到但数据未加载")
                else:
                    # 标题元素还未出现
                    if retry_count % 3 == 0:
                        print(f"    - 等待中... ({retry_count + 1}/{max_wait_retries})，标题元素未找到")
                
            except Exception as e:
                if retry_count % 3 == 0:
                    print(f"    - 等待中... ({retry_count + 1}/{max_wait_retries})，检查时出错: {type(e).__name__}")
            
            retry_count += 1
            if not table_ready and retry_count < max_wait_retries:
                await asyncio.sleep(1)  # 等待1秒后重试
        
        if not table_ready:
            print(f"  ⚠ 等待表格数据加载超时（已等待 {retry_count} 秒），尝试继续查找...")
        
        # 额外等待一段时间，确保数据完全渲染
        await asyncio.sleep(1)
        
        # 8. 从表格中提取数据
        success_rate = None
        all_data = []
        matched_data = []  # 存储PID匹配的数据
        
        try:
            # 在SLS iframe中查找"客户签名视角 -剔除重试过程"表格
            print("  - 在SLS iframe中查找'客户签名视角 -剔除重试过程'表格...")
            
            # 如果等待过程中已找到容器，直接使用；否则重新查找
            if not target_table_container:
                try:
                    # 直接使用定位器查找包含"客户签名视角 -剔除重试过程"标题的元素
                    title_locator = sls_frame.locator('span.chartPanel-m__text__e25a6898:has-text("客户签名视角 -剔除重试过程")')
                    title_count = await title_locator.count()
                    
                    if title_count > 0:
                        print(f"  ✓ 找到标题元素")
                        title_element = title_locator.first
                        
                        # 通过JavaScript查找包含表格的父容器
                        container_info = await title_element.evaluate('''el => {
                            let current = el;
                            while (current) {
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
                            target_table_container = sls_frame.locator(f'#{container_info["id"]}')
                        else:
                            target_table_container = title_locator.locator('xpath=ancestor::div[contains(@id, "sls_chart_")]')
                            container_count = await target_table_container.count()
                            if container_count == 0:
                                target_table_container = None
                    else:
                        print(f"  ⚠ 未找到标题元素")
                except Exception as e:
                    print(f"  ⚠ 查找标题元素时出错: {e}")
            
            # 在目标表格容器中查找表格行
            if target_table_container:
                print("  - 在目标表格容器中查找数据行...")
                # 使用 query_selector_all 获取 ElementHandle 列表
                table_rows_locator = target_table_container.locator('div.obviz-base-easyTable-body div.obviz-base-easyTable-row')
                table_rows_count = await table_rows_locator.count()
                table_rows = []
                for i in range(table_rows_count):
                    row_locator = table_rows_locator.nth(i)
                    # 通过 evaluate 获取实际的 DOM 元素
                    row_element = await row_locator.element_handle()
                    if row_element:
                        table_rows.append(row_element)
            else:
                print("  ⚠ 未找到目标表格容器，使用通用选择器查找...")
                # 使用 query_selector_all 获取 ElementHandle 列表
                table_rows = await sls_frame.query_selector_all('div.obviz-base-easyTable-body div.obviz-base-easyTable-row')
            
            if table_rows and len(table_rows) > 0:
                print(f"  ✓ 找到 {len(table_rows)} 行数据")
                
                for idx, row in enumerate(table_rows):
                    try:
                        # 获取该行的所有单元格（row 是 ElementHandle）
                        # 首先尝试排除表头单元格（hasFilter类）
                        cells = await row.query_selector_all('div.obviz-base-easyTable-cell:not(.obviz-base-easyTable-cell-hasFilter)')
                        
                        # 如果排除后单元格数量不足11个，则获取所有单元格（可能是数据行）
                        if not cells or len(cells) < 11:
                            cells = await row.query_selector_all('div.obviz-base-easyTable-cell')
                        
                        # 确保有足够的单元格（至少11个：pid, signname, 短信类型, 提交量, 回执量, 回执成功量, 回执率, 回执成功率, 十秒回执率, 三十秒回执率, 六十秒回执率）
                        if cells and len(cells) >= 11:
                            row_data = {}
                            try:
                                # 提取所有单元格的文本用于调试
                                cell_texts = []
                                for cell in cells[:11]:
                                    cell_text = await extract_cell_text(cell)
                                    cell_texts.append(cell_text.strip())
                                
                                # 验证是否是表头行（表头通常包含"pid", "signname"等文本）
                                if len(cell_texts) > 0 and (cell_texts[0].lower() in ['pid', '客户pid'] or 
                                                             cell_texts[1].lower() in ['signname', '签名']):
                                    print(f"  跳过表头行 {idx+1}")
                                    continue
                                
                                # 使用helpers中的extract_cell_text函数提取数据
                                # 单元格索引对应关系：
                                # 0: pid, 1: signname, 2: 短信类型, 3: 提交量, 4: 回执量, 
                                # 5: 回执成功量, 6: 回执率, 7: 回执成功率, 8: 十秒回执率, 
                                # 9: 三十秒回执率, 10: 六十秒回执率
                                
                                cell1_text = cell_texts[0] if len(cell_texts) > 0 else ''
                                row_data['pid'] = cell1_text
                                
                                cell2_text = cell_texts[1] if len(cell_texts) > 1 else ''
                                row_data['signname'] = cell2_text
                                row_data['sign_name'] = row_data['signname']  # 向后兼容
                                
                                cell3_text = cell_texts[2] if len(cell_texts) > 2 else ''
                                row_data['sms_type'] = cell3_text
                                row_data['template_type'] = row_data['sms_type']  # 向后兼容
                                
                                cell4_text = cell_texts[3] if len(cell_texts) > 3 else ''
                                row_data['submit_count'] = cell4_text
                                row_data['total_sent'] = row_data['submit_count']  # 向后兼容
                                
                                cell5_text = cell_texts[4] if len(cell_texts) > 4 else ''
                                row_data['receipt_count'] = cell5_text
                                row_data['total_success'] = row_data['receipt_count']  # 向后兼容
                                
                                cell6_text = cell_texts[5] if len(cell_texts) > 5 else ''
                                row_data['receipt_success_count'] = cell6_text
                                row_data['total_failed'] = row_data['receipt_success_count']  # 向后兼容
                                
                                cell7_text = cell_texts[6] if len(cell_texts) > 6 else ''
                                row_data['receipt_rate'] = cell7_text
                                
                                # 第8个单元格（索引7）是回执成功率 - 这是用户要的关键字段
                                cell8_text = cell_texts[7] if len(cell_texts) > 7 else ''
                                row_data['receipt_success_rate'] = cell8_text
                                row_data['success_rate'] = row_data['receipt_success_rate']  # 向后兼容
                                
                                cell9_text = cell_texts[8] if len(cell_texts) > 8 else ''
                                row_data['receipt_rate_10s'] = cell9_text
                                
                                cell10_text = cell_texts[9] if len(cell_texts) > 9 else ''
                                row_data['receipt_rate_30s'] = cell10_text
                                
                                cell11_text = cell_texts[10] if len(cell_texts) > 10 else ''
                                row_data['receipt_rate_60s'] = cell11_text
                                
                                all_data.append(row_data)
                                
                                # 检查PID是否匹配（如果提供了PID参数）
                                pid_matched = False
                                if pid:
                                    row_pid = row_data.get('pid', '').strip()
                                    if row_pid == pid:
                                        pid_matched = True
                                        matched_data.append(row_data)
                                        print(f"  ✓ 行 {idx+1}: signname={row_data.get('signname', 'N/A')}, "
                                              f"回执成功率={row_data.get('receipt_success_rate', 'N/A')}%, "
                                              f"PID={row_data.get('pid', '')}, 类型={row_data.get('sms_type', '')} [PID匹配]")
                                    else:
                                        print(f"  - 行 {idx+1}: signname={row_data.get('signname', 'N/A')}, "
                                              f"回执成功率={row_data.get('receipt_success_rate', 'N/A')}%, "
                                              f"PID={row_data.get('pid', '')}, 类型={row_data.get('sms_type', '')} [PID不匹配]")
                                else:
                                    # 如果没有提供PID，显示所有数据
                                    print(f"  ✓ 行 {idx+1}: signname={row_data.get('signname', 'N/A')}, "
                                          f"回执成功率={row_data.get('receipt_success_rate', 'N/A')}%, "
                                          f"PID={row_data.get('pid', '')}, 类型={row_data.get('sms_type', '')}")
                            except Exception as e:
                                print(f"  ✗ 处理第 {idx+1} 行时出错: {type(e).__name__} - {str(e)}")
                                import traceback
                                traceback.print_exc()
                                continue
                        else:
                            print(f"  ⚠ 行 {idx+1}: 单元格数量不足（找到 {len(cells) if cells else 0} 个，需要至少11个）")
                    except Exception as e:
                        print(f"  ✗ 解析第 {idx+1} 行时出错: {type(e).__name__} - {str(e)}")
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
        
        # 确定返回的数据和成功率
        # 如果提供了PID且有匹配的数据，优先使用匹配的数据
        if pid and matched_data:
            print(f"\n  ✓ 找到 {len(matched_data)} 条PID匹配的数据（PID: {pid}）")
            # 使用匹配数据的第一条作为主要成功率（或者可以计算平均值）
            success_rate = matched_data[0].get('receipt_success_rate', '')
            return_data = matched_data
            print(f"  ✓ 使用PID匹配数据的成功率: {success_rate}%")
        elif all_data:
            # 如果没有匹配的数据，使用所有数据
            if pid:
                print(f"\n  ⚠ 未找到PID匹配的数据（PID: {pid}），使用所有数据")
            success_rate = all_data[0].get('receipt_success_rate', '') if all_data else None
            return_data = all_data
        else:
            return_data = []
            success_rate = None
        
        # 检查是否成功提取到成功率
        if success_rate and return_data:
            result = {
                'success': True,
                'success_rate': success_rate,
                'pid': pid,
                'time_range': time_range,
                'data': return_data,
                'total_count': len(return_data),
                'matched_count': len(matched_data) if pid else len(return_data),
                'error': None
            }
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


async def query_sms_success_rate_multi(
    page: Page,
    pid: Optional[str] = None,
    time_ranges: Optional[list] = None,
    timeout: int = 30000
) -> Dict[str, any]:
    """
    查询多个时间范围的短信签名成功率
    
    Args:
        page: Playwright Page 对象（需要已登录的会话）
        pid: 客户PID（如果不提供，则从环境变量 SMS_PID 读取）
        time_ranges: 时间范围列表，可选值：'当天', '本周', '一周', '上周', '30天'
                     如果不提供，默认查询：['当天', '一周', '本周', '30天']
        timeout: 操作超时时间（毫秒），默认30秒
        
    Returns:
        Dict: 查询结果字典，包含以下字段：
            - success (bool): 是否所有查询都成功
            - results (Dict): 每个时间范围的查询结果
            - pid (str): 客户PID
            - time_ranges (list): 查询的时间范围列表
            - error (Optional[str]): 错误信息（失败时返回）
    """
    logger = get_logger('sms_success_rate_multi')
    
    if time_ranges is None:
        time_ranges = ['当天', '一周', '本周', '30天']
    
    all_results = {
        'success': True,
        'results': {},
        'pid': pid,
        'time_ranges': time_ranges,
        'error': None
    }
    
    # 第一次查询：完整流程（包括输入PID）
    first_time_range = time_ranges[0]
    logger.info(f"\n{'='*60}")
    logger.info(f"开始查询PID: {pid} 的短信签名成功率，时间范围: {first_time_range}（首次查询，将输入PID）")
    logger.info(f"{'='*60}")
    
    first_result = await query_sms_success_rate(page, pid, first_time_range, timeout, skip_pid_input=False)
    all_results['results'][first_time_range] = first_result
    
    if not first_result['success']:
        all_results['success'] = False
        all_results['error'] = f"首次查询（时间范围 {first_time_range}）失败: {first_result.get('error', '未知错误')}"
        logger.error(f"  ✗ 首次查询失败: {first_result.get('error', '未知错误')}")
        # 如果首次查询失败，后续查询也无法进行
        return all_results
    else:
        logger.info(f"  ✓ 首次查询成功！")
    
    # 后续查询：只切换时间范围（跳过PID输入）
    for tr in time_ranges[1:]:
        logger.info(f"\n{'='*60}")
        logger.info(f"切换时间范围: {tr}（PID已输入，无需重新输入）")
        logger.info(f"{'='*60}")
        
        result = await query_sms_success_rate(page, pid, tr, timeout, skip_pid_input=True)
        all_results['results'][tr] = result
        
        if not result['success']:
            all_results['success'] = False
            if all_results['error'] is None:
                all_results['error'] = f"时间范围 {tr} 查询失败: {result.get('error', '未知错误')}"
            logger.error(f"  ✗ 时间范围 {tr} 查询失败: {result.get('error', '未知错误')}")
        else:
            logger.info(f"  ✓ 时间范围 {tr} 查询成功！")
    
    return all_results
