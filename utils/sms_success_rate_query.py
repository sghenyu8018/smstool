"""
短信签名成功率查询模块
提供短信签名成功率查询功能
"""
import asyncio
import re
from typing import Dict, Optional, Tuple
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from .constants import SUCCESS_RATE_QUERY_URL, SELECTORS
from .helpers import extract_cell_text
from .logger import get_logger


async def _find_sls_iframe(page: Page):
    """
    查找SLS iframe
    
    Args:
        page: Playwright Page 对象
        
    Returns:
        Frame: SLS iframe对象，如果未找到则返回None
    """
    iframes = page.frames
    for frame in iframes:
        if 'sls4service.console.aliyun.com' in frame.url and 'dashboard' in frame.url:
            return frame
    return None


async def _wait_for_iframe_load(sls_frame, timeout: int = 15000):
    """
    等待SLS iframe加载完成
    
    Args:
        sls_frame: SLS iframe对象
        timeout: 超时时间（毫秒），默认15秒
    """
    print("  - 等待SLS iframe加载完成...")
    try:
        # 1. 等待DOM加载完成
        await sls_frame.wait_for_load_state('domcontentloaded', timeout=timeout)
        print("    ✓ DOM加载完成")
        
        # 2. 等待网络请求完成（load状态）
        try:
            await sls_frame.wait_for_load_state('load', timeout=timeout)
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


async def _scroll_to_bottom(sls_frame):
    """
    滚动页面到底部，确保表格内容完全可见
    
    Args:
        sls_frame: SLS iframe对象
    """
    print("  - 滚动页面到底部...")
    try:
        # 方法1: 滚动到页面底部
        await sls_frame.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(1)  # 等待滚动完成
        
        # 方法2: 尝试滚动到表格元素（如果存在）
        try:
            title_locator = sls_frame.locator('span.chartPanel-m__text__e25a6898:has-text("客户签名视角 -剔除重试过程")')
            if await title_locator.count() > 0:
                await title_locator.first.scroll_into_view_if_needed()
                await asyncio.sleep(1)  # 等待滚动完成
                print("  ✓ 已滚动到表格元素")
        except Exception:
            pass
        
        # 方法3: 再次滚动到底部，确保所有内容都可见
        await sls_frame.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(1)  # 等待滚动和内容渲染完成
        
        # 验证滚动位置
        scroll_position = await sls_frame.evaluate('window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop')
        max_scroll = await sls_frame.evaluate('Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, document.body.offsetHeight, document.documentElement.offsetHeight, document.body.clientHeight, document.documentElement.clientHeight)')
        
        # 如果位置是0但最大滚动也很小，说明页面不需要滚动
        if scroll_position == 0 and max_scroll <= 100:
            print(f"  ✓ 页面内容已完全可见（无需滚动，内容高度: {max_scroll}）")
        else:
            print(f"  ✓ 已滚动到页面底部（位置: {scroll_position}, 最大: {max_scroll}）")
    except Exception as e:
        print(f"  ⚠ 滚动页面时出错: {e}")


async def _select_time_range(
    sls_frame,
    time_range: str,
    page: Optional[Page] = None,
    need_reacquire_frame: bool = False
) -> Tuple[bool, any, Optional[str]]:
    """
    选择时间范围
    
    Args:
        sls_frame: SLS iframe对象
        time_range: 时间范围（'当天', '本周', '一周', '上周', '30天'）
        page: Playwright Page 对象（如果需要重新获取iframe引用）
        need_reacquire_frame: 是否需要重新获取iframe引用（切换时间范围后iframe可能重新加载）
        
    Returns:
        Tuple: (success, updated_sls_frame, error_message)
            - success: 是否成功选择时间范围
            - updated_sls_frame: 更新后的sls_frame引用
            - error_message: 错误信息（如果失败）
    """
    # 时间范围映射（用于查找选项）
    time_range_map = {
        '当天': ['当天', '今天', '今日'],
        '本周': ['本周', '本周（相对）'],
        '一周': ['1周', '7天', '7天（相对）'],
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
        
        if not time_selector_locator:
            return (False, sls_frame, '未找到时间选择器')
        
        # 点击时间选择器按钮
        print("  - 点击时间选择器按钮...")
        await time_selector_locator.click()
        await asyncio.sleep(1)  # 等待弹窗出现
        
        # 查找并点击时间范围选项
        print(f"  - 在SLS iframe中查找'{time_range}'选项...")
        time_option_locator = None
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
        
        # 如果方式1失败，尝试使用text=查找
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
        
        if not time_option_locator:
            return (False, sls_frame, f"未找到时间范围选项：{time_range}")
        
        # 点击时间范围选项
        print(f"  - 点击'{time_range}'选项...")
        await time_option_locator.click()
        await asyncio.sleep(3 if need_reacquire_frame else 2)  # 切换时间范围需要更长的等待时间
        print(f"  ✓ 已选择时间范围：{time_range}")
        
        # 如果需要重新获取iframe引用（切换时间范围后iframe可能重新加载）
        if need_reacquire_frame and page:
            print("  - 重新获取SLS iframe引用（切换时间范围后可能重新加载）...")
            await asyncio.sleep(2)  # 等待iframe重新加载
            
            # 重新查找SLS iframe
            updated_sls_frame = await _find_sls_iframe(page)
            
            if not updated_sls_frame:
                return (False, sls_frame, '切换时间范围后未找到SLS iframe，可能iframe已重新加载')
            
            # 等待iframe重新加载完成
            try:
                await updated_sls_frame.wait_for_load_state('domcontentloaded', timeout=10000)
                print("  ✓ SLS iframe重新加载完成")
                await asyncio.sleep(2)  # 额外等待，确保内容渲染完成
            except Exception as e:
                print(f"  ⚠ 等待iframe加载时出错: {e}，继续执行...")
                await asyncio.sleep(2)
            
            sls_frame = updated_sls_frame
        
        # 滚动页面到底部，确保表格内容完全可见
        await _scroll_to_bottom(sls_frame)
        
        return (True, sls_frame, None)
        
    except Exception as e:
        error_msg = f"选择时间范围时出错: {str(e)}"
        print(f"  ✗ {error_msg}")
        return (False, sls_frame, error_msg)


async def _wait_for_table_ready(
    page: Page,
    sls_frame,
    pid: Optional[str],
    max_wait_retries: int = 30,
    reacquire_frame: bool = False
) -> Tuple[bool, Optional[any], any]:
    """
    等待表格数据加载完成
    
    Args:
        page: Playwright Page 对象
        sls_frame: SLS iframe对象（如果reacquire_frame=True，可能会被更新）
        pid: 客户PID（用于检查表格是否包含PID）
        max_wait_retries: 最大等待次数，默认30次
        reacquire_frame: 是否在每次重试前重新获取iframe引用
        
    Returns:
        tuple: (table_ready, target_table_container, updated_sls_frame)
            - table_ready: 表格是否已加载完成
            - target_table_container: 表格容器定位器（如果找到）
            - updated_sls_frame: 更新后的sls_frame引用
    """
    retry_count = 0
    table_ready = False
    target_table_container = None
    current_sls_frame = sls_frame
    
    while retry_count < max_wait_retries and not table_ready:
        try:
            # 如果需要重新获取iframe引用（切换时间范围后iframe可能重新加载）
            if reacquire_frame:
                current_sls_frame = await _find_sls_iframe(page)
                
                if not current_sls_frame:
                    if retry_count % 3 == 0:
                        print(f"    - 等待中... ({retry_count + 1}/{max_wait_retries})，SLS iframe未找到")
                    retry_count += 1
                    if retry_count < max_wait_retries:
                        await asyncio.sleep(1)
                    continue
            
            # 在等待过程中，定期滚动页面以触发懒加载
            if retry_count % 5 == 0 and retry_count > 0:  # 每5次重试滚动一次
                try:
                    await current_sls_frame.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
            
            # 查找表格标题
            title_locator = current_sls_frame.locator('span.chartPanel-m__text__e25a6898:has-text("客户签名视角 -剔除重试过程")')
            title_count = await title_locator.count()
            
            if title_count > 0:
                # 获取表格行数（两种方式都尝试）
                title_element = title_locator.first
                
                # 方式1: 使用JavaScript获取行数（更准确）
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
                
                # 方式2: 如果方式1失败，使用xpath查找
                if not container_info.get('found'):
                    table_rows_locator = title_locator.locator('xpath=ancestor::div[contains(@id, "sls_chart_")]//div[contains(@class, "obviz-base-easyTable-row")]')
                    row_count = await table_rows_locator.count()
                    if row_count > 0:
                        # 获取容器ID
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
                            container_info['rowCount'] = row_count
                
                if container_info.get('found'):
                    container_id = container_info.get('id')
                    row_count = container_info.get('rowCount', 0)
                    
                    if row_count > 0:
                        # 检查表格中是否包含PID来判断是否加载完成
                        if pid:
                            # 获取表格容器并检查是否包含PID
                            temp_container = current_sls_frame.locator(f'#{container_id}')
                            table_body = temp_container.locator('div.obviz-base-easyTable-body')
                            rows = table_body.locator('div.obviz-base-easyTable-row')
                            
                            # 检查前几行数据是否包含PID
                            pid_found = False
                            for i in range(min(row_count, 10)):  # 检查前10行
                                try:
                                    row = rows.nth(i)
                                    cells = row.locator('div.obviz-base-easyTable-cell')
                                    if await cells.count() > 0:
                                        # 第一个单元格通常是PID
                                        pid_cell = cells.nth(0)
                                        cell_text = await extract_cell_text(pid_cell)
                                        if pid in cell_text.strip():
                                            pid_found = True
                                            print(f"    - 在表格第 {i+1} 行找到PID: {pid}，判断表格已加载完成")
                                            break
                                except Exception:
                                    continue
                            
                            # 如果找到了PID，认为表格已加载完成
                            if pid_found:
                                target_table_container = temp_container
                                table_ready = True
                                print(f"  ✓ 找到表格容器: {container_id}，包含 {row_count} 行数据，已找到PID（等待 {retry_count + 1} 次）")
                                break
                            else:
                                # 如果表格有足够的数据行（超过5行），即使没有找到PID，也认为表格已加载完成
                                # 因为PID可能不在前10行，但数据已经加载完成
                                if row_count > 5:
                                    target_table_container = temp_container
                                    table_ready = True
                                    print(f"  ✓ 找到表格容器: {container_id}，包含 {row_count} 行数据（等待 {retry_count + 1} 次）")
                                    print(f"    - 注意：未在前10行找到PID，但表格有足够数据，认为已加载完成")
                                    break
                                else:
                                    if retry_count % 3 == 0:
                                        print(f"    - 等待中... ({retry_count + 1}/{max_wait_retries})，表格有数据但未找到PID，继续等待...")
                        else:
                            # 如果没有PID，只要有数据行就认为加载完成
                            target_table_container = current_sls_frame.locator(f'#{container_id}')
                            table_ready = True
                            print(f"  ✓ 找到表格容器: {container_id}，包含 {row_count} 行数据（等待 {retry_count + 1} 次）")
                            break
                    else:
                        if retry_count % 3 == 0:
                            print(f"    - 等待中... ({retry_count + 1}/{max_wait_retries})，表格容器已找到但数据未加载")
            else:
                if retry_count % 3 == 0:
                    print(f"    - 等待中... ({retry_count + 1}/{max_wait_retries})，标题元素未找到")
        except Exception as e:
            if retry_count % 3 == 0:
                print(f"    - 等待中... ({retry_count + 1}/{max_wait_retries})，检查时出错: {type(e).__name__}")
        
        retry_count += 1
        if not table_ready and retry_count < max_wait_retries:
            await asyncio.sleep(1)
    
    if not table_ready:
        print(f"  ⚠ 等待表格数据加载超时（已等待 {retry_count} 秒），尝试继续查找...")
    
    return (table_ready, target_table_container, current_sls_frame)


async def _extract_table_data(
    sls_frame,
    pid: Optional[str],
    time_range: str
) -> Dict[str, any]:
    """
    从SLS iframe的表格中提取数据
    
    Args:
        sls_frame: SLS iframe对象
        pid: 客户PID（用于匹配数据）
        time_range: 时间范围（用于错误信息）
        
    Returns:
        Dict: 包含以下字段：
            - all_data: 所有提取的数据行
            - matched_data: PID匹配的数据行
            - success_rate: 成功率
            - error: 错误信息（如果有）
    """
    success_rate = None
    all_data = []
    matched_data = []
    
    try:
        # 在SLS iframe中查找"客户签名视角 -剔除重试过程"表格
        print("  - 在SLS iframe中查找'客户签名视角 -剔除重试过程'表格...")
        
        try:
            # 直接使用定位器查找包含"客户签名视角 -剔除重试过程"标题的元素
            title_locator = sls_frame.locator('span.chartPanel-m__text__e25a6898:has-text("客户签名视角 -剔除重试过程")')
            title_count = await title_locator.count()
            
            if title_count > 0:
                print(f"  ✓ 找到标题元素")
                # 找到标题元素后，直接使用通用选择器查找表格行
                print("  - 使用通用选择器查找表格行...")
                table_rows = await sls_frame.query_selector_all('div.obviz-base-easyTable-body div.obviz-base-easyTable-row')
            else:
                print(f"  ⚠ 未找到标题元素")
                table_rows = []
        except Exception as e:
            print(f"  ⚠ 查找标题元素时出错: {e}")
            table_rows = []
        
        # 如果找到了表格行，继续处理
        if not table_rows:
            print("  ⚠ 未找到表格行，尝试使用通用选择器查找...")
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
                            if pid:
                                row_pid = row_data.get('pid', '').strip()
                                if row_pid == pid:
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
                        # 单元格数量不足的行可能是表头行或特殊行，静默跳过
                        # 只在调试模式下打印警告
                        pass
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
        
        # 确定返回的数据和成功率
        # 如果提供了PID且有匹配的数据，优先使用匹配的数据
        if pid and matched_data:
            print(f"\n  ✓ 找到 {len(matched_data)} 条PID匹配的数据（PID: {pid}）")
            # 使用匹配数据的第一条作为主要成功率（或者可以计算平均值）
            success_rate = matched_data[0].get('receipt_success_rate', '')
            print(f"  ✓ 使用PID匹配数据的成功率: {success_rate}%")
        elif all_data:
            # 如果没有匹配的数据，使用所有数据
            if pid:
                print(f"\n  ⚠ 未找到PID匹配的数据（PID: {pid}），使用所有数据")
            success_rate = all_data[0].get('receipt_success_rate', '') if all_data else None
        
        return {
            'all_data': all_data,
            'matched_data': matched_data,
            'success_rate': success_rate,
            'error': None
        }
        
    except Exception as e:
        return {
            'all_data': [],
            'matched_data': [],
            'success_rate': None,
            'error': f"提取数据时出错: {str(e)}"
        }


async def _select_time_range_only(
    page: Page,
    pid: Optional[str],
    time_range: str,
    timeout: int
) -> Dict[str, any]:
    """
    只切换时间范围，不重新输入PID（内部函数）
    从"按回车键触发搜索/选择"之后的流程开始，即直接选择时间范围
    
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
        print(f"切换时间范围（{time_range}），PID已输入，从选择时间范围开始")
        print(f"{'='*60}")
        
        # 查找SLS iframe
        sls_frame = await _find_sls_iframe(page)
        
        if not sls_frame:
            return {
                'success': False,
                'success_rate': None,
                'pid': pid,
                'time_range': time_range,
                'data': None,
                'error': '未找到SLS iframe，请先执行完整的查询流程'
            }
        
        # 从"按回车键触发搜索/选择"之后的流程开始
        # 即：直接选择时间范围（跳过输入PID和按回车键的步骤）
        print(f"\n步骤: 选择时间范围（{time_range}）")
        
        # 使用统一的时间范围选择函数（切换时间范围后需要重新获取iframe引用）
        success, sls_frame, error_msg = await _select_time_range(
            sls_frame, time_range, page=page, need_reacquire_frame=True
        )
        
        if not success:
            return {
                'success': False,
                'success_rate': None,
                'pid': pid,
                'time_range': time_range,
                'data': None,
                'error': error_msg or '选择时间范围失败'
            }
        
        # 等待数据加载并提取数据
        print(f"\n步骤: 等待数据加载并提取成功率")
        
        # 使用统一的等待表格加载函数（切换时间范围后需要重新获取iframe引用）
        table_ready, target_table_container, sls_frame = await _wait_for_table_ready(
            page, sls_frame, pid, max_wait_retries=30, reacquire_frame=True
        )
        
        await asyncio.sleep(1)
        
        # 提取数据（使用统一的提取函数）
        # 重新获取sls_frame引用（确保使用最新的引用）
        current_sls_frame = await _find_sls_iframe(page)
        
        if not current_sls_frame:
            return {
                'success': False,
                'success_rate': None,
                'pid': pid,
                'time_range': time_range,
                'data': None,
                'error': '未找到SLS iframe'
            }
        
        # 使用统一的提取函数
        extract_result = await _extract_table_data(current_sls_frame, pid, time_range)
        
        # 确定返回的数据和成功率
        all_data = extract_result['all_data']
        matched_data = extract_result['matched_data']
        success_rate = extract_result['success_rate']
        
        # 如果提供了PID且有匹配的数据，优先使用匹配的数据
        if pid and matched_data:
            return_data = matched_data
        elif all_data:
            return_data = all_data
        else:
            return_data = []
        
        # 检查是否成功提取到成功率
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
            error_msg = extract_result.get('error') or '未能从页面中提取到成功率数据，请检查查询条件和页面结构'
            return {
                'success': False,
                'success_rate': None,
                'pid': pid,
                'time_range': time_range,
                'data': None,
                'error': error_msg
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
        # print(f"  - 找到 {len(iframes)} 个frame（包括主frame）")
        # for idx, frame in enumerate(iframes):
        #     url = frame.url
        #     name = frame.name or 'unnamed'
        #     url_display = url[:100] + '...' if len(url) > 100 else url
        #     print(f"    Frame {idx}: name='{name}', url='{url_display}'")
        
        # 直接定位到Frame 3（SLS iframe）
        print("\n定位SLS iframe (Frame 3)...")
        sls_frame = await _find_sls_iframe(page)
        if sls_frame:
            # 找到iframe后，打印信息
            iframes = page.frames
            for idx, frame in enumerate(iframes):
                if frame == sls_frame:
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
        
        # 等待SLS iframe加载完成（使用统一的等待函数）
        await _wait_for_iframe_load(sls_frame)
        
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
        
        # 使用统一的时间范围选择函数（首次查询不需要重新获取iframe引用）
        success, sls_frame, error_msg = await _select_time_range(
            sls_frame, time_range, page=page, need_reacquire_frame=False
        )
        
        if not success:
            print(f"  ✗ {error_msg}")
        
        print(f"{'='*60}\n")
        
        # 6. 打印SLS iframe中的所有元素（用于调试）
        # logger = get_logger('sms_success_rate')
        # logger.log_section("步骤6: 打印SLS iframe中的所有元素（用于判断查询条件和输出内容）")
        # 
        # try:
        #     logger.info("\n【查询条件区域】")
        #     
        #     filter_texts = await sls_frame.query_selector_all('span.obviz-base-filterText')
        #     filter_text_list = []
        #     logger.info(f"  - 找到 {len(filter_texts)} 个筛选条件标签:")
        #     for idx, filter_text in enumerate(filter_texts[:20], 1):
        #         try:
        #             text = await filter_text.inner_text()
        #             logger.info(f"    {idx}. {text}")
        #             filter_text_list.append(text)
        #         except Exception:
        #             pass
        #     
        #     inputs = await sls_frame.query_selector_all('input')
        #     input_list = []
        #     logger.info(f"\n  - 找到 {len(inputs)} 个输入框:")
        #     for idx, inp in enumerate(inputs[:20], 1):
        #         try:
        #             input_type = await inp.get_attribute('type') or 'text'
        #             input_value = await inp.get_attribute('value') or ''
        #             input_info = f"type={input_type}, value={input_value[:50]}"
        #             logger.info(f"    {idx}. {input_info}")
        #             input_list.append(input_info)
        #         except Exception:
        #             pass
        #     
        #     logger.info("\n【输出内容区域】")
        #     
        #     # 查找表格行元素，支持多种表格实现方式
        #     # - div.obviz-base-easyTable-row: 主要用于新版SLS前端的表格行
        #     # - tr: 标准HTML表格行
        #     # - div[class*="table"]: 匹配部分自定义类名含'table'的行元素，兼容不同产品线UI组件
        #     # 这里的 div[class*="table"] 选择器表示：选择 class 属性中包含 "table" 字符串的所有 div 元素
        #     # 这用于匹配自定义样式表格行，包括 class="custom-table-row"、class="main-table" 等。
        #     table_rows = await sls_frame.query_selector_all(
        #         'div.obviz-base-easyTable-row, tr, div[class*="table"]'
        #     )
        #     table_rows_count = len(table_rows)
        #     logger.info(f"  - 找到 {table_rows_count} 个表格行/行元素（"表格元素"是指表格的每一行，包括可能的tr、div或自定义行元素）")
        #     
        #     # 提取表格行的具体内容
        #     table_rows_content = []
        #     for idx, row in enumerate(table_rows[:50], 1):  # 限制最多50行，避免日志过大
        #         try:
        #             row_text = await row.inner_text()
        #             table_rows_content.append(f"行 {idx}: {row_text[:200]}")  # 限制每行200字符
        #             if idx <= 10:  # 前10行详细记录
        #                 logger.info(f"    行 {idx}: {row_text[:200]}")
        #         except Exception as e:
        #             table_rows_content.append(f"行 {idx}: [提取失败: {str(e)}]")
        #     
        #     table_cells = await sls_frame.query_selector_all('div.obviz-base-easyTable-cell, td, div[class*="table-cell"]')
        #     table_cells_count = len(table_cells)
        #     logger.info(f"  - 找到 {table_cells_count} 个表格单元格")
        #     
        #     # 提取表格单元格的具体内容
        #     table_cells_content = []
        #     for idx, cell in enumerate(table_cells[:100], 1):  # 限制最多100个单元格
        #         try:
        #             cell_text = await extract_cell_text(cell)
        #             if cell_text.strip():  # 只记录非空单元格
        #                 table_cells_content.append(f"单元格 {idx}: {cell_text.strip()[:100]}")  # 限制每个单元格100字符
        #                 if idx <= 20:  # 前20个单元格详细记录
        #                     logger.info(f"    单元格 {idx}: {cell_text.strip()[:100]}")
        #         except Exception as e:
        #             table_cells_content.append(f"单元格 {idx}: [提取失败: {str(e)}]")
        #     
        #     # 使用日志模块记录到专门的日志文件
        #     log_file = logger.log_iframe_elements(
        #         pid=pid,
        #         time_range=time_range,
        #         filter_texts=filter_text_list,
        #         inputs=input_list,
        #         table_rows_count=table_rows_count,
        #         table_cells_count=table_cells_count,
        #         table_rows_content=table_rows_content,
        #         table_cells_content=table_cells_content
        #     )
        #         
        # except Exception as e:
        #     logger.error(f"  ✗ 打印元素时出错: {type(e).__name__} - {str(e)}")
        
        print(f"\n{'='*60}")
        print(f"步骤7: 等待数据加载并提取成功率")
        print(f"{'='*60}")
        
        # 7. 等待数据加载完成
        print("  - 等待数据加载完成...")
        
        # 使用统一的等待表格加载函数（首次查询不需要重新获取iframe引用）
        table_ready, target_table_container, sls_frame = await _wait_for_table_ready(
            page, sls_frame, pid, max_wait_retries=20, reacquire_frame=False
        )
        
        # 额外等待一段时间，确保数据完全渲染
        await asyncio.sleep(1)
        
        # 8. 从表格中提取数据（使用统一的提取函数）
        extract_result = await _extract_table_data(sls_frame, pid, time_range)
        
        # 确定返回的数据和成功率
        all_data = extract_result['all_data']
        matched_data = extract_result['matched_data']
        success_rate = extract_result['success_rate']
        
        # 如果提供了PID且有匹配的数据，优先使用匹配的数据
        if pid and matched_data:
            return_data = matched_data
        elif all_data:
            return_data = all_data
        else:
            return_data = []
        
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
            error_msg = extract_result.get('error') or '未能从页面中提取到成功率数据，请检查查询条件和页面结构'
            return {
                'success': False,
                'success_rate': None,
                'pid': pid,
                'time_range': time_range,
                'data': None,
                'error': error_msg
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
