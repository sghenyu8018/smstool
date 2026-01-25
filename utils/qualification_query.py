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
        await query_button.click()
        await asyncio.sleep(2)  # 等待查询结果加载
        
        # 步骤4: 点击工单号链接，进入详情页面
        print("正在点击工单号链接，进入详情页面...")
        order_link = await page.wait_for_selector(
            f'a[_nk="DYsM21"]:has-text("{work_order_id}")',
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
        pid_selectors = [
            '#UserId',  # 最准确的选择器（根据实际页面元素）
            # 'input#UserId',  # 备选：带标签的选择器
            # '#PartnerId',  # 备选：其他可能的ID
            # 'input[placeholder*="PID"]',
            # 'input[placeholder*="pid"]',
            # 'input[placeholder*="客户PID"]',
            # 'input[placeholder="请输入"]'  # 通用占位符（最后尝试）
        ]
        
        for selector in pid_selectors:
            try:
                pid_input = await page.query_selector(selector)
                if pid_input:
                    is_visible = await pid_input.is_visible()
                    if is_visible:
                        print(f"  ✓ 找到PID输入框: {selector}")
                        break
                    else:
                        print(f"  - 找到元素但不可见: {selector}")
                        pid_input = None
            except Exception as e:
                print(f"  - 选择器 {selector} 查找失败: {e}")
                continue
        
        if not pid_input:
            # 输出更详细的调试信息
            print("  ✗ 未找到PID输入框，尝试列出所有输入框...")
            try:
                all_inputs = await page.query_selector_all('input[type="text"]')
                print(f"  - 页面中共找到 {len(all_inputs)} 个文本输入框")
                for i, inp in enumerate(all_inputs[:5], 1):  # 只显示前5个
                    try:
                        inp_id = await inp.get_attribute('id')
                        inp_placeholder = await inp.get_attribute('placeholder')
                        inp_class = await inp.get_attribute('class')
                        is_vis = await inp.is_visible()
                        print(f"    输入框 {i}: id={inp_id}, placeholder={inp_placeholder}, class={inp_class}, visible={is_vis}")
                    except Exception:
                        pass
            except Exception as e:
                print(f"  - 列出输入框时出错: {e}")
            
            return {
                'success': False,
                'work_order_id': None,
                'qualification_id': qualification_id,
                'qualification_group_id': None,
                'error': '未找到PID输入框，请检查页面结构'
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
        await query_button.click()
        await asyncio.sleep(2)  # 等待查询结果加载
        
        # 步骤8: 查找包含"短信资质(智能)"的行
        print("正在查找包含'短信资质(智能)'的行...")
        sms_rows = await page.query_selector_all('tr.ant-table-row')
        matching_row = None
        
        for row in sms_rows:
            try:
                row_text = await row.inner_text()
                if '短信资质(智能)' in row_text:
                    matching_row = row
                    print(f"  ✓ 找到包含'短信资质(智能)'的行")
                    break
            except Exception:
                continue
        
        if not matching_row:
            return {
                'success': False,
                'work_order_id': None,
                'qualification_id': qualification_id,
                'qualification_group_id': None,
                'error': '未找到包含"短信资质(智能)"的行'
            }
        
        # 步骤9: 从匹配的行中提取工单号并点击
        print("正在提取工单号并进入详情页面...")
        order_link_in_row = await matching_row.query_selector('a[_nk="DYsM21"]')
        if not order_link_in_row:
            return {
                'success': False,
                'work_order_id': None,
                'qualification_id': qualification_id,
                'qualification_group_id': None,
                'error': '在匹配的行中未找到工单号链接'
            }
        
        matched_work_order_id = (await order_link_in_row.inner_text()).strip()
        print(f"  ✓ 找到匹配的工单号: {matched_work_order_id}")
        
        await order_link_in_row.click()
        await asyncio.sleep(2)  # 等待详情页面加载
        
        # 步骤10: 获取资质组ID
        print("正在获取资质组ID...")
        qualification_group_id = None
        try:
            # 查找包含"资质组ID"的行
            # 等待页面中出现包含"资质组ID"文本的表格行
            # 解释：
            # - 'tr.ant-table-row:has-text("资质组ID")'：选择包含"资质组ID"文本的表格行
            # - timeout=5000：超时时间设为5秒，避免无限等待
            # - state='visible'：要求该元素处于可见状态，确保页面已加载
            # 等待页面中出现包含“资质组ID”的表格行，并确保该元素处于可见状态
            # wait_for_selector 方法作用解释：
            # - 这是 Playwright 异步页面操作中用于等待元素出现的常用方法。
            # - 这里用于查找 table 行（tr.ant-table-row），要求该行中包含 "资质组ID" 文本。
            # - 'state="visible"' 参数表示必须等到该行在页面上变得可见时才继续后续操作，避免出现元素还未渲染完毕时操作导致的报错。
            # - 'timeout=5000' 参数表示最多等待5秒钟，如超时仍未找到会抛出 TimeoutError。
            qualification_group_row = await page.wait_for_selector(
                'tr.ant-table-row:has-text("资质组ID")',  # CSS选择器：查找包含"资质组ID"的行
                timeout=5000,           # 最长等待5秒（单位为毫秒）
                state='visible'         # 直到该元素可见为止
            )
            # 在同一行中查找pre标签（不依赖可变属性，直接查找pre标签）
            qualification_group_pre = await qualification_group_row.query_selector('pre')
            if qualification_group_pre:
                qualification_group_id = (await qualification_group_pre.inner_text()).strip()
                print(f"  ✓ 获取到资质组ID: {qualification_group_id}")
            else:
                # 如果pre标签不存在，尝试查找其他可能包含ID的元素（如td中的文本）
                print("  ⚠ 未找到pre标签，尝试其他方式...")
                # 尝试查找行中的所有td，找到包含数字的单元格
                tds = await qualification_group_row.query_selector_all('td')
                for td in tds:
                    td_text = (await td.inner_text()).strip()
                    # 如果单元格包含数字（可能是ID），使用它
                    if td_text and td_text.isdigit():
                        qualification_group_id = td_text
                        print(f"  ✓ 从td中获取到资质组ID: {qualification_group_id}")
                        break
                if not qualification_group_id:
                    print("  ⚠ 未找到资质组ID")
        except Exception as e:
            print(f"  ✗ 获取资质组ID失败: {e}")
        
        if not qualification_group_id:
            return {
                'success': False,
                'work_order_id': None,
                'qualification_id': qualification_id,
                'qualification_group_id': None,
                'error': '未能获取到资质组ID'
            }
        
        # 步骤11: 比较两个ID
        print(f"\n比较资质ID: 关联资质ID={qualification_id}, 资质组ID={qualification_group_id}")
        if qualification_id == qualification_group_id:
            print(f"  ✓ 资质ID匹配！返回工单号: {matched_work_order_id}")
            return {
                'success': True,
                'work_order_id': matched_work_order_id,
                'qualification_id': qualification_id,
                'qualification_group_id': qualification_group_id,
                'error': None
            }
        else:
            print(f"  ✗ 资质ID不匹配")
            return {
                'success': False,
                'work_order_id': None,
                'qualification_id': qualification_id,
                'qualification_group_id': qualification_group_id,
                'error': f'资质ID不匹配：关联资质ID={qualification_id}, 资质组ID={qualification_group_id}'
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
