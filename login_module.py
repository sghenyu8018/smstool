"""
登录模块 - 使用纯 Playwright，不依赖 browser-use
"""
import asyncio
import os
from pathlib import Path
from playwright.async_api import Page, BrowserContext
from config import SSO_USERNAME, SSO_PASSWORD, SESSION_PATH
from session_manager import SessionManager

# 确保 session 目录存在
SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)


async def perform_login(page: Page, x_name: str, x_password: str):
    """
    执行登录操作（使用纯 Playwright）
    
    Args:
        page: Playwright Page 对象
        x_name: 用户名
        x_password: 密码
    """
    await page.goto("https://login.alibaba-inc.com/ssoLogin.htm", timeout=60000)

    # 填写用户名和密码
    await page.fill("#account", x_name)
    await asyncio.sleep(0.5)  # 等待一下，模拟人类操作
    await page.fill("#password", x_password)

    # 提交登录表单
    await page.click("button:has-text('登 录')")

    # 等待跳转或加载完成
    await asyncio.sleep(1)

    # 可选：等待某个登录成功标志出现
    try:
        await page.wait_for_selector("h2:has-text('Welcome')", timeout=10000)
    except Exception:
        # 如果找不到欢迎信息，也可能登录成功，继续执行
        pass

    # 保存会话状态到 session/ 目录，使用 SessionManager 统一格式
    session_manager = SessionManager(SESSION_PATH)
    context = page.context
    storage_state = await context.storage_state()
    session_manager.save_session(storage_state)


async def is_logged_in(page: Page) -> bool:
    """
    检查是否已登录（使用纯 Playwright）
    
    Args:
        page: Playwright Page 对象
        
    Returns:
        bool: 是否已登录
    """
    await page.goto("https://login.alibaba-inc.com/ssoLogin.htm", timeout=60000)
    try:
        # 尝试查找登录后的用户信息元素
        user_element = await page.wait_for_selector("h2:has-text('Welcome')", timeout=5000)
        return user_element is not None
    except Exception:
        return False


async def ensure_logged_in(page: Page, x_name: str, x_password: str):
    """
    确保已登录，如果未登录则执行登录（使用纯 Playwright）
    
    Args:
        page: Playwright Page 对象
        x_name: 用户名
        x_password: 密码
    """
    # 检查是否已经登录
    logged_in = await is_logged_in(page)
    if not logged_in:
        print("未检测到登录信息，开始登录流程...")
        await perform_login(page, x_name, x_password)
        print("登录完成，状态已保存至 storage_state")
    else:
        print("当前浏览器会话已登录")


async def create_playwright_session(
    x_name: str = None,
    x_password: str = None,
    browser_type: str = 'chromium',
    browser_channel: str = None,
    headless: bool = False,
    viewport: dict = None
):
    """
    创建一个已登录的 Playwright 会话（使用纯 Playwright，不依赖 browser-use）
    
    Args:
        x_name: 用户名，如果不提供则从环境变量 SSO_USERNAME 读取
        x_password: 密码，如果不提供则从环境变量 SSO_PASSWORD 读取
        browser_type: 浏览器类型 ('chromium', 'firefox', 'webkit')
        browser_channel: 浏览器渠道（如 'msedge', 'chrome'）
        headless: 是否无头模式
        viewport: 浏览器窗口尺寸，格式为 {'width': int, 'height': int}，默认 {'width': 1280, 'height': 1100}
        
    Returns:
        tuple: (playwright, browser, context, page) - Playwright 对象、浏览器、上下文和页面
    """
    # 如果未提供用户名和密码，从环境变量读取
    if not x_name:
        x_name = SSO_USERNAME
    if not x_password:
        x_password = SSO_PASSWORD
    
    # 验证用户名和密码是否已配置
    if not x_name or not x_password:
        raise ValueError(
            "登录凭据未配置！\n"
            "请在 .env 文件中配置以下环境变量：\n"
            "  SSO_USERNAME=your_username\n"
            "  SSO_PASSWORD=your_password\n"
            "或者通过函数参数传入用户名和密码。"
        )
    
    from playwright.async_api import async_playwright
    import tempfile
    
    # 启动 Playwright
    playwright = await async_playwright().start()
    
    # 选择浏览器类型
    if browser_type not in ['chromium', 'firefox', 'webkit']:
        browser_type = 'chromium'
    
    browser_launcher = getattr(playwright, browser_type)
    
    # 构建启动参数
    launch_options = {
        'headless': headless,
    }
    if browser_channel:
        launch_options['channel'] = browser_channel
    
    # 启动浏览器
    browser = await browser_launcher.launch(**launch_options)
    
    # 使用 SessionManager 加载会话（带24小时验证）
    session_manager = SessionManager(SESSION_PATH)
    storage_state = session_manager.get_storage_state(max_age_hours=24)
    
    # 设置默认 viewport 尺寸
    if viewport is None:
        viewport = {'width': 1280, 'height': 1100}
    
    # 创建浏览器上下文（使用指定尺寸）
    context = await browser.new_context(
        viewport=viewport,  # 设置浏览器窗口尺寸
        storage_state=storage_state,  # 如果会话有效，使用会话
        ignore_https_errors=True,  # 对应 disable_security=True
    )
    
    # 创建新页面
    page = await context.new_page()

    # 登录检测与自动登录
    await ensure_logged_in(page, x_name, x_password)
    
    return playwright, browser, context, page


if __name__ == '__main__':
    # 示例：使用默认凭据创建已登录的会话
    async def main():
        playwright, browser, context, page = await create_playwright_session()
        print("浏览器会话已创建并完成登录")
        # 在这里可以进行其他操作
        # 使用完毕后记得关闭
        # await context.close()
        # await browser.close()
        # await playwright.stop()
        
    asyncio.run(main())
