import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径，以便导入根目录的模块
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from login_module import create_playwright_session
from utils.constants import SUCCESS_RATE_QUERY_URL, QUALIFICATION_ORDER_QUERY_URL, SELECTORS
from playwright.async_api import async_playwright

async def test_locator():
    """测试定位器功能（不需要登录）"""
    # 直接创建 Playwright 会话，不需要登录（用于测试公开网站）
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(viewport={'width': 1280, 'height': 1100})
    page = await context.new_page()
    try:
        TEST_URL = 'https://www.w3schools.com/html/html_tables.asp'
        print(f"正在访问测试页面: {TEST_URL}")
        await page.goto(TEST_URL, timeout=6000, wait_until='domcontentloaded')
        await asyncio.sleep(1)
        
        print("正在查找表格行...")
        # 获取所有 tr 元素
        rows = await page.query_selector_all('tr')
        print(f"找到 {len(rows)} 行数据")
        
        # 遍历表格行
        for idx, row in enumerate(rows, 1):
            print(f"\n--- 第 {idx} 行 ---")
            
            # 获取该行中的所有 td 元素
            tds = await row.query_selector_all('td')
            print(f"找到 {len(tds)} 个 td 元素")
            
            # 遍历并打印每个 td 的内容
            for td_idx, td in enumerate(tds, 1):
                td_text = await td.text_content()
                print(f"  td[{td_idx}]: {td_text.strip() if td_text else ''}")

            await asyncio.sleep(1)
        
        print(f"\n✓ 测试完成，共处理 {len(rows)} 行")
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()
        print("✓ 浏览器已关闭")
async def main():
    """
    主函数：测试所有窗口尺寸
    """
    print("="*60)
    playwright, browser, context, page = await create_playwright_session(
        headless=False,
        viewport={'width': 1280, 'height': 1100}
    )
    try:
        print("正在访问工单查询页面...")
        await page.goto(QUALIFICATION_ORDER_QUERY_URL, timeout=6000, wait_until='domcontentloaded')
        await asyncio.sleep(1)

        # 步骤7: 输入PID并查询
        pid = os.getenv('PID', '100000183762112')
        print(f"正在输入PID: {pid}")
        # 尝试多种PID输入框选择器（按优先级排序）
        pid_input = None
        pid_selectors = [
            '#UserId',  # 最准确的选择器（根据实际页面元素）
            'input[placeholder="请输入"]'  # 通用占位符（最后尝试）
        ]

        for selector in pid_selectors:
            try:
                # pid_input = await page.wait_for_selector(selector)
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
            print("  ✗ 未找到PID输入框")
            return
        
        # 清空输入框并填写PID
        await pid_input.click()  # 先点击获取焦点
        await pid_input.fill('')  # 清空现有内容
        await asyncio.sleep(0.2)
        await pid_input.fill(pid)  # 填写新的PID
        await asyncio.sleep(0.3)
        
        # 验证输入
        value = await pid_input.input_value()
        print(f"✅ 实际填入的 PID 值: '{value}'")
        pid_button = await page.wait_for_selector('button.ant-btn-primary:has-text("查 询")')
        await pid_button.click()
        await asyncio.sleep(10)
        rows = await page.query_selector_all('tr.ant-table-row')
        for row in rows:
            print(row)
            print(await row.text_content())
            print(await row.get_attribute('data-row-key'))
        await asyncio.sleep(10)

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()
        print("✓ 浏览器已关闭")


if __name__ == '__main__':
    # asyncio.run(main())
    asyncio.run(test_locator())