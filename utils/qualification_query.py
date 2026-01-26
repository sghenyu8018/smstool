"""
资质工单查询模块
提供资质工单查询功能
"""
import asyncio
from typing import Dict, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from .constants import QUALIFICATION_ORDER_QUERY_URL, SELECTORS


async def query_qualification_work_order(
    page: Page,
    work_order_id: str,
    pid: Optional[str] = None,
    timeout: int = 30000
) -> Dict[str, any]:
    """
    查询资质工单
    
    操作流程：
    1. 进入工单查询页面
    2. 输入工单号并查询
    3. 点击工单号进入详情页面，获取关联资质ID
    4. 返回查询页面，输入PID查询
    5. 找到包含"短信资质(智能)"的行
    6. 点击工单号进入详情页面，获取资质组ID
    7. 比较两个ID，如果一致则返回工单号
    
    Args:
        page: Playwright Page 对象（需要已登录的会话）
        work_order_id: 工单号
        pid: 客户PID（如果不提供，则从环境变量 SMS_PID 读取）
        timeout: 操作超时时间（毫秒），默认30秒
        
    Returns:
        Dict: 查询结果字典，包含以下字段：
            - success (bool): 是否查询成功
            - work_order_id (Optional[str]): 匹配的工单号（成功时返回）
            - qualification_id (Optional[str]): 关联资质ID
            - qualification_group_id (Optional[str]): 资质组ID
            - error (Optional[str]): 错误信息（失败时返回）
            
    # Example:
    #     >>> result = await query_qualification_work_order(page, "20051875589", "100000041462041")
    #     >>> if result['success']:
    #     ...     print(f"匹配的工单号：{result['work_order_id']}")
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
                    'work_order_id': None,
                    'qualification_id': None,
                    'qualification_group_id': None,
                    'error': '客户PID未提供，请在函数参数中传入或在环境变量中配置 SMS_PID'
                }
        except ImportError:
            return {
                'success': False,
                'work_order_id': None,
                'qualification_id': None,
                'qualification_group_id': None,
                'error': '客户PID未提供，且无法从环境变量读取'
            }
    
    try:
        # 步骤1: 进入工单查询页面
        print(f"正在访问工单查询页面: {QUALIFICATION_ORDER_QUERY_URL}")
        await page.goto(QUALIFICATION_ORDER_QUERY_URL, timeout=timeout, wait_until='domcontentloaded')
        await asyncio.sleep(1)
        
        # 步骤2: 输入工单号
        print(f"正在输入工单号: {work_order_id}")
        order_id_input = await page.wait_for_selector(
            SELECTORS['qualification_order_id_input'],
            timeout=timeout,
            state='visible'
        )
        await order_id_input.fill(work_order_id)
        await asyncio.sleep(0.5)
        
        # 步骤3: 点击查询按钮
        print("正在点击查询按钮...")
        query_button = await page.wait_for_selector(
            SELECTORS['qualification_query_button'],
            timeout=5000,
            state='visible'
        )
        # 添加短暂延迟，避免请求过于频繁
        await asyncio.sleep(0.5)
        await query_button.click()
        # 增加等待时间，确保查询完成且避免频繁请求
        await asyncio.sleep(3)  # 等待查询结果加载
        
        # 步骤4: 点击工单号链接，进入详情页面
        print("正在点击工单号链接，进入详情页面...")
        order_link = await page.wait_for_selector(
            f'a:has-text("{work_order_id}")',
            timeout=10000,
            state='visible'
        )
        await order_link.click()
        await asyncio.sleep(2)  # 等待详情页面加载
        
        # 步骤5: 获取关联资质ID
        print("正在获取关联资质ID...")
        qualification_id = None
        try:
            # 查找包含"关联资质ID"的行
            qualification_id_row = await page.wait_for_selector(
                'tr.ant-table-row:has-text("关联资质ID")',
                timeout=5000,
                state='visible'
            )
            # 在同一行中查找pre标签（不依赖可变属性，直接查找pre标签）
            qualification_id_pre = await qualification_id_row.query_selector('pre')
            if qualification_id_pre:
                qualification_id = (await qualification_id_pre.inner_text()).strip()
                print(f"  ✓ 获取到关联资质ID: {qualification_id}")
            else:
                # 如果pre标签不存在，尝试查找其他可能包含ID的元素（如td中的文本）
                print("  ⚠ 未找到pre标签，尝试其他方式...")
                # 尝试查找行中的所有td，找到包含数字的单元格
                tds = await qualification_id_row.query_selector_all('td')
                for td in tds:
                    td_text = (await td.inner_text()).strip()
                    # 如果单元格包含数字（可能是ID），使用它
                    if td_text and td_text.isdigit():
                        qualification_id = td_text
                        print(f"  ✓ 从td中获取到关联资质ID: {qualification_id}")
                        break
                if not qualification_id:
                    print("  ⚠ 未找到关联资质ID")
        except Exception as e:
            print(f"  ✗ 获取关联资质ID失败: {e}")
        
        if not qualification_id:
            return {
                'success': False,
                'work_order_id': None,
                'qualification_id': None,
                'qualification_group_id': None,
                'error': '未能获取到关联资质ID'
            }
        
        # 步骤6: 返回工单查询页面
        print("正在返回工单查询页面...")
        await page.goto(QUALIFICATION_ORDER_QUERY_URL, timeout=timeout, wait_until='domcontentloaded')
        await asyncio.sleep(1)
        
        # 步骤7: 输入PID并查询
        print(f"正在输入PID: {pid}")
        # 尝试多种PID输入框选择器（按优先级排序）
        pid_input = None
        pid_selector = [
            '#UserId',
            'input#UserId', 
            'input[placeholder="请输入"]'
          ]
        for selector in pid_selector:
            try:
                #wait for selector
                pid_input = await page.wait_for_selector(selector, timeout=5000, state='visible')
                break
            except Exception as e:  
                print(f"  - 查找 {selector} 失败: {e}")
                continue
        if not pid_input:
            print("  ✗ 未找到PID输入框")
            return {
                'success': False,
                'work_order_id': None,
                'qualification_id': qualification_id,
                'qualification_group_id': None,
                'error': '未找到PID输入框'
            }
            
        # 清空输入框并填写PID
        await pid_input.click()  # 先点击获取焦点
        await pid_input.fill('')  # 清空现有内容
        await asyncio.sleep(0.2)
        await pid_input.fill(pid)  # 填写新的PID
        await asyncio.sleep(0.3)
        
        # 验证输入是否成功
        input_value = await pid_input.input_value()
        if input_value == pid:
            print(f"  ✓ PID填写成功: {input_value}")
        else:
            print(f"  ⚠ PID填写后验证不一致: 期望={pid}, 实际={input_value}")
        
        # 点击查询按钮
        print("正在点击查询按钮...")
        query_button = await page.wait_for_selector(
            SELECTORS['qualification_query_button'],
            timeout=5000,
            state='visible'
        )
        # 添加短暂延迟，避免请求过于频繁
        await asyncio.sleep(0.5)
        await query_button.click()
        # 增加等待时间，确保查询完成且避免频繁请求
        await asyncio.sleep(3)  # 等待查询结果加载
        
        # 步骤8: 查找所有包含"短信资质"的行，提取工单号列表（支持分页）
        print("正在查找所有包含'短信资质'的行...")
        work_order_ids = []  # 存储工单号列表，而不是元素引用
        page_num = 1
        
        while True:
            print(f"\n--- 处理第 {page_num} 页 ---")
            
            # 等待当前页的表格加载
            await asyncio.sleep(1)
            
            # 查找当前页所有表格行
            sms_rows = await page.query_selector_all('tr.ant-table-row')
            print(f"  第 {page_num} 页找到 {len(sms_rows)} 行数据")
            current_page_count = 0
            
            for row in sms_rows:
                try:
                    row_text = await row.inner_text()
                    if '短信资质' in row_text:
                        # 提取工单号并保存，而不是保存元素引用
                        order_link = await row.query_selector('td.ant-table-cell a')
                        if order_link:
                            work_order_id = (await order_link.inner_text()).strip()
                            if work_order_id and work_order_id not in work_order_ids:  # 避免重复
                                work_order_ids.append(work_order_id)
                                current_page_count += 1
                                print(f"  ✓ 找到包含'短信资质'的行，工单号: {work_order_id}")
                except Exception:
                    continue
            
            print(f"  第 {page_num} 页找到 {current_page_count} 个包含'短信资质'的工单")
            
            # 检查是否有下一页
            has_next_page = False
            try:
                next_page_button = await page.query_selector('li.ant-pagination-next')
                if next_page_button:
                    # 检查是否被禁用
                    is_disabled = await next_page_button.get_attribute('aria-disabled')
                    has_disabled_class = await next_page_button.evaluate('el => el.classList.contains("ant-pagination-disabled")')
                    
                    if is_disabled != 'true' and not has_disabled_class:
                        has_next_page = True
                        print(f"  发现还有下一页，准备点击...")
            except Exception as e:
                print(f"  检查下一页时出错: {e}")
            
            # 如果没有下一页，退出循环
            if not has_next_page:
                print(f"  已处理完所有页面，共找到 {len(work_order_ids)} 个包含'短信资质'的工单")
                break
            
            # 点击下一页
            try:
                next_page_button = await page.query_selector('li.ant-pagination-next button')
                if next_page_button:
                    await next_page_button.click()
                    page_num += 1
                    print(f"  ✓ 已点击下一页，等待页面加载...")
                    # 等待下一页数据加载完成（增加等待时间）
                    await asyncio.sleep(3)  # 增加等待时间，确保数据加载完成
                    
                    # 等待表格行出现（确保数据已加载）
                    try:
                        await page.wait_for_selector('tr.ant-table-row', timeout=5000, state='visible')
                    except Exception:
                        print(f"  ⚠ 等待表格行加载超时，继续处理...")
                else:
                    print(f"  ⚠ 未找到下一页按钮，停止分页")
                    break
            except Exception as e:
                print(f"  ✗ 点击下一页失败: {e}")
                break
        
        if not work_order_ids:
            return {
                'success': False,
                'work_order_id': None,
                'qualification_id': qualification_id,
                'qualification_group_id': None,
                'error': '未找到包含"短信资质"的行'
            }
        
        print(f"共找到 {len(work_order_ids)} 个包含'短信资质'的工单，开始依次检查...")
        
        # 步骤9-11: 对每个工单号，依次进入详情页面检查资质组ID
        for idx, work_order_id_to_check in enumerate(work_order_ids, 1):
            print(f"\n--- 检查第 {idx}/{len(work_order_ids)} 个工单 ---")
            
            # 如果不是第一个工单，需要返回查询页面并重新查找对应的行
            if idx > 1:
                print("正在返回工单查询页面...")
                await page.goto(QUALIFICATION_ORDER_QUERY_URL, timeout=timeout, wait_until='domcontentloaded')
                await asyncio.sleep(1)
                
                # 重新输入PID并查询
                print("重新输入PID并查询...")
                pid_input = await page.query_selector('#UserId')
                if pid_input:
                    await pid_input.click()
                    await pid_input.fill('')
                    await asyncio.sleep(0.2)
                    await pid_input.fill(pid)
                    await asyncio.sleep(0.3)
                
                query_button = await page.wait_for_selector(
                    SELECTORS['qualification_query_button'],
                    timeout=5000,
                    state='visible'
                )
                # 添加短暂延迟，避免请求过于频繁
                await asyncio.sleep(0.5)
                await query_button.click()
                # 增加等待时间，确保查询完成且避免频繁请求
                await asyncio.sleep(3)  # 等待查询结果加载
            
            # 通过工单号查找对应的行并点击（支持分页查找）
            print(f"正在查找工单号 {work_order_id_to_check} 并进入详情页面...")
            order_link = None
            page_num = 1
            
            # 遍历所有页面查找工单号
            while True:
                try:
                    # 尝试在当前页查找工单号
                    order_link = await page.query_selector(f'a:has-text("{work_order_id_to_check}")')
                    if order_link:
                        is_visible = await order_link.is_visible()
                        if is_visible:
                            print(f"  ✓ 在第 {page_num} 页找到工单号: {work_order_id_to_check}")
                            break
                        else:
                            order_link = None
                except Exception:
                    pass
                
                # 检查是否有下一页
                has_next_page = False
                try:
                    next_page_button = await page.query_selector('li.ant-pagination-next')
                    if next_page_button:
                        is_disabled = await next_page_button.get_attribute('aria-disabled')
                        has_disabled_class = await next_page_button.evaluate('el => el.classList.contains("ant-pagination-disabled")')
                        if is_disabled != 'true' and not has_disabled_class:
                            has_next_page = True
                except Exception:
                    pass
                
                # 如果没有找到且还有下一页，点击下一页
                if not order_link and has_next_page:
                    try:
                        next_page_btn = await page.query_selector('li.ant-pagination-next button')
                        if next_page_btn:
                            await next_page_btn.click()
                            page_num += 1
                            await asyncio.sleep(2)  # 等待下一页加载
                            print(f"  未找到，翻到第 {page_num} 页继续查找...")
                            continue
                    except Exception:
                        break
                
                # 如果找不到且没有下一页，退出循环
                break
            
            if not order_link:
                print(f"  ✗ 在所有页面中未找到工单号 {work_order_id_to_check}")
                continue
            
            # 点击工单号链接
            try:
                await order_link.click()
                await asyncio.sleep(2)  # 等待详情页面加载
            except Exception as e:
                print(f"  ✗ 点击工单号链接失败: {e}")
                continue
            
            # 获取资质组ID
            print("正在获取资质组ID...")
            qualification_group_id = None
            try:
                # 查找包含"资质组ID"的行
                qualification_group_row = await page.wait_for_selector(
                    'tr.ant-table-row:has-text("资质组ID")',
                    timeout=5000,
                    state='visible'
                )
                # 在同一行中查找pre标签（不依赖可变属性，直接查找pre标签）
                qualification_group_pre = await qualification_group_row.query_selector('pre')
                if qualification_group_pre:
                    qualification_group_id = (await qualification_group_pre.inner_text()).strip()
                    print(f"  ✓ 获取到资质组ID: {qualification_group_id}")
                else:
                    # 如果pre标签不存在，尝试查找其他可能包含ID的元素（如td中的文本）
                    print("  ⚠ 未找到pre标签，尝试其他方式...")
                    tds = await qualification_group_row.query_selector_all('td')
                    for td in tds:
                        td_text = (await td.inner_text()).strip()
                        if td_text and td_text.isdigit():
                            qualification_group_id = td_text
                            print(f"  ✓ 从td中获取到资质组ID: {qualification_group_id}")
                            break
                    if not qualification_group_id:
                        print("  ⚠ 未找到资质组ID")
            except Exception as e:
                print(f"  ✗ 获取资质组ID失败: {e}")
            
            # 比较两个ID
            if qualification_group_id:
                print(f"比较资质ID: 关联资质ID={qualification_id}, 资质组ID={qualification_group_id}")
                if qualification_id == qualification_group_id:
                    print(f"  ✓ 资质ID匹配！返回工单号: {work_order_id_to_check}")
                    return {
                        'success': True,
                        'work_order_id': work_order_id_to_check,
                        'qualification_id': qualification_id,
                        'qualification_group_id': qualification_group_id,
                        'error': None
                    }
                else:
                    print(f"  ✗ 资质ID不匹配，继续检查下一个工单")
            else:
                print(f"  ⚠ 未能获取到资质组ID，继续检查下一个工单")
        
        # 如果所有工单都检查完毕仍未找到匹配的
        print(f"\n所有 {len(work_order_ids)} 个工单都已检查完毕，未找到匹配的资质ID")
        return {
            'success': False,
            'work_order_id': None,
            'qualification_id': qualification_id,
            'qualification_group_id': None,
            'error': f'已检查所有包含"短信资质"的工单（共 {len(work_order_ids)} 个），但未找到匹配的资质ID'
        }
            
    except PlaywrightTimeoutError as e:
        error_msg = f"操作超时（超过 {timeout/1000} 秒）: {str(e)}"
        print(f"错误: {error_msg}")
        return {
            'success': False,
            'work_order_id': None,
            'qualification_id': None,
            'qualification_group_id': None,
            'error': error_msg
        }
    except Exception as e:
        error_msg = f"查询过程中发生错误: {str(e)}"
        print(f"错误: {error_msg}")
        return {
            'success': False,
            'work_order_id': None,
            'qualification_id': None,
            'qualification_group_id': None,
            'error': error_msg
        }
