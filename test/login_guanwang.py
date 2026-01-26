"""
登录模块
使用Playwright实现阿里云登录功能
"""
import asyncio
import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from config import (
    LOGIN_URL, SESSION_PATH, HEADLESS, BROWSER_TIMEOUT, BROWSER_CHANNEL,
    ALIYUN_USERNAME, ALIYUN_PASSWORD, SSO_USERNAME, SSO_PASSWORD
)
from session_manager import SessionManager

logger = logging.getLogger(__name__)


class LoginManager:
    """登录管理器类"""
    
    def __init__(self, session_manager: SessionManager):
        """
        初始化登录管理器
        
        Args:
            session_manager: 会话管理器实例
        """
        self.session_manager = session_manager
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
    
    async def initialize(self, browser_channel: Optional[str] = None):
        """
        初始化Playwright浏览器
        
        Args:
            browser_channel: 浏览器通道（'chrome'、'chrome-beta'、'msedge'等，None则使用配置或默认Chromium）
        """
        try:
            self.playwright = await async_playwright().start()
            launch_options = {
                'headless': HEADLESS,
                'args': ['--disable-blink-features=AutomationControlled']
            }
            # 如果指定了浏览器通道（如'chrome'、'msedge'），使用本地浏览器
            channel = browser_channel if browser_channel is not None else BROWSER_CHANNEL
            if channel:
                launch_options['channel'] = channel
                logger.info(f"使用本地浏览器: {channel}")
            else:
                logger.info("使用Playwright自带的Chromium")
            
            self.browser = await self.playwright.chromium.launch(**launch_options)
            # 设置viewport为屏幕的一半大小，方便调试
            self.context = await self.browser.new_context(
                viewport={'width': 960, 'height': 540},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            self.page = await self.context.new_page()
            logger.info("Playwright浏览器已初始化")
        except Exception as e:
            logger.error(f"初始化浏览器失败: {e}")
            raise
    
    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        执行登录操作
        从环境变量读取用户名和密码，如果参数未提供则使用环境变量中的值
        
        Args:
            username: 用户名（可选，如果不提供则从环境变量读取）
            password: 密码（可选，如果不提供则从环境变量读取）
            
        Returns:
            bool: 登录是否成功
        """
        if not self.page:
            await self.initialize()
        
        # 从环境变量读取用户名和密码（如果参数未提供）
        if not username:
            username = ALIYUN_USERNAME
        if not password:
            password = ALIYUN_PASSWORD
        
        # 验证用户名和密码是否已配置
        if not username or not password:
            error_msg = (
                "登录凭据未配置！\n"
                "请在 .env 文件中配置以下环境变量：\n"
                "  ALIYUN_USERNAME=your_username\n"
                "  ALIYUN_PASSWORD=your_password\n"
                "或者通过命令行参数传入用户名和密码。"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            logger.info(f"正在访问登录页面: {LOGIN_URL}")
            # 使用 domcontentloaded 而不是 networkidle，因为登录页面可能有很多异步请求
            await self.page.goto(LOGIN_URL, wait_until='domcontentloaded', timeout=BROWSER_TIMEOUT)
            
            # 等待页面基本加载完成
            await self.page.wait_for_load_state('domcontentloaded')
            
            # 尝试等待 networkidle，但不强制（超时后继续）
            try:
                await self.page.wait_for_load_state('networkidle', timeout=30000)
            except:
                logger.warning("等待networkidle超时，继续执行...")
            
            logger.info("开始自动填写登录信息...")
            
            # 等待页面完全加载（增加等待时间）
            await asyncio.sleep(3)
            
            # 尝试等待页面中的关键元素出现
            try:
                # 等待任何输入框出现
                await self.page.wait_for_selector('input', timeout=10000)
                logger.info("检测到输入框元素")
            except:
                logger.warning("等待输入框超时，继续尝试...")
            
            # 输出页面标题和URL用于调试
            page_title = await self.page.title()
            current_url = self.page.url
            logger.info(f"页面标题: {page_title}")
            logger.info(f"当前URL: {current_url}")
            
            # 检查是否有iframe
            iframes = await self.page.query_selector_all('iframe')
            logger.info(f"检测到 {len(iframes)} 个iframe")
            
            # 尝试在iframe中查找输入框
            page_to_use = self.page
            if iframes:
                logger.info("尝试在iframe中查找输入框...")
                for i, iframe in enumerate(iframes):
                    try:
                        iframe_content = await iframe.content_frame()
                        if iframe_content:
                            # 检查iframe中是否有输入框
                            inputs_in_iframe = await iframe_content.query_selector_all('input')
                            logger.info(f"iframe {i} 中找到 {len(inputs_in_iframe)} 个input元素")
                            if len(inputs_in_iframe) > 0:
                                logger.info(f"使用iframe {i} 作为登录表单")
                                page_to_use = iframe_content
                                break
                    except Exception as e:
                        logger.debug(f"检查iframe {i} 失败: {e}")
                        continue
            
            # 统计页面中的输入框数量
            all_inputs = await page_to_use.query_selector_all('input')
            logger.info(f"页面中共找到 {len(all_inputs)} 个input元素")
            if len(all_inputs) > 0:
                # 输出前几个input的属性用于调试
                for i, inp in enumerate(all_inputs[:5]):
                    try:
                        input_type = await inp.get_attribute('type')
                        input_name = await inp.get_attribute('name')
                        input_id = await inp.get_attribute('id')
                        input_placeholder = await inp.get_attribute('placeholder')
                        logger.info(f"  input[{i}]: type={input_type}, name={input_name}, id={input_id}, placeholder={input_placeholder}")
                    except:
                        pass
            
            # 查找用户名输入框（根据实际日志，优先使用已验证有效的选择器）
            username_selectors = [
                'input[type="text"]',  # 已验证成功的选择器
                'input[name="username"]',  # 常见标准选择器
                'input[autocomplete="username"]',  # HTML5标准属性
                'input[name="loginName"]',  # 备用选择器
                '#username',  # ID选择器
                'input[placeholder*="用户名"]'  # 中文placeholder
            ]
            
            password_selectors = [
                'input[type="password"]',  # 已验证成功的选择器（HTML标准）
                'input[name="password"]',  # 常见标准选择器
                '#password',  # ID选择器
                'input[placeholder*="密码"]'  # 中文placeholder
            ]
            
            # 尝试填写用户名
            username_filled = False
            for selector in username_selectors:
                try:
                    # 使用 wait_for_selector 等待元素出现（在正确的页面/iframe中）
                    element = await page_to_use.wait_for_selector(selector, timeout=2000, state='visible')
                    if element:
                        # 确保元素可见且可编辑
                        await element.scroll_into_view_if_needed()
                        await element.click()  # 先点击聚焦
                        await asyncio.sleep(0.3)
                        await element.fill(username)
                        username_filled = True
                        logger.info(f"用户名已填写（使用选择器: {selector}）")
                        await asyncio.sleep(0.5)  # 等待一下，避免操作过快
                        break
                except Exception as e:
                    logger.debug(f"尝试选择器 {selector} 失败: {e}")
                    continue
            
            if not username_filled:
                error_msg = "未找到用户名输入框，请检查登录页面结构是否变化"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # 尝试填写密码
            password_filled = False
            for selector in password_selectors:
                try:
                    # 在正确的页面/iframe中查找密码输入框
                    element = await page_to_use.wait_for_selector(selector, timeout=2000, state='visible')
                    if element:
                        await element.scroll_into_view_if_needed()
                        await element.click()  # 先点击聚焦
                        await asyncio.sleep(0.3)
                        await element.fill(password)
                        password_filled = True
                        logger.info(f"密码已填写（使用选择器: {selector}）")
                        await asyncio.sleep(0.5)  # 等待一下，避免操作过快
                        break
                except Exception as e:
                    logger.debug(f"尝试选择器 {selector} 失败: {e}")
                    continue
            
            if not password_filled:
                error_msg = "未找到密码输入框，请检查登录页面结构是否变化"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # 尝试点击登录按钮（根据实际日志，优先使用已验证有效的选择器）
            login_selectors = [
                'button[type="submit"]',  # 已验证成功的选择器
                'input[type="submit"]',  # HTML标准提交按钮
                'button:has-text("登录")',  # 文本匹配备用
            ]
            
            login_clicked = False
            for selector in login_selectors:
                try:
                    # 在正确的页面/iframe中查找登录按钮
                    element = await page_to_use.wait_for_selector(selector, timeout=2000, state='visible')
                    if element:
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        login_clicked = True
                        logger.info(f"已点击登录按钮（使用选择器: {selector}）")
                        await asyncio.sleep(1)  # 等待登录请求
                        break
                except Exception as e:
                    logger.debug(f"尝试选择器 {selector} 失败: {e}")
                    continue
            
            if not login_clicked:
                error_msg = "未找到登录按钮，请检查登录页面结构是否变化"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # 等待登录成功
            logger.info("等待登录成功...")
            try:
                # 等待URL变化（登录成功后通常会跳转）
                await self.page.wait_for_url(
                    lambda url: 'console' in url or 'home' in url or ('aliyun.com' in url and 'login' not in url),
                    timeout=BROWSER_TIMEOUT
                )
                logger.info("检测到URL变化，登录可能已成功")
            except Exception as e:
                logger.warning(f"等待URL变化超时: {e}")
                # 继续验证登录状态
            
            # 验证登录状态（检查是否有用户信息或特定元素）
            try:
                # 等待页面加载完成
                await self.page.wait_for_load_state('networkidle', timeout=30000)
                
                # 检查当前URL，如果还在登录页面，可能登录失败
                current_url = self.page.url
                if 'login' in current_url.lower():
                    error_msg = f"仍在登录页面，登录可能失败。当前URL: {current_url}"
                    logger.error(error_msg)
                    return False
                
                logger.info(f"登录成功，当前URL: {current_url}")
                return True
                
            except Exception as e:
                logger.error(f"验证登录状态失败: {e}")
                return False
                
        except ValueError:
            # 重新抛出ValueError，让调用者处理
            raise
        except Exception as e:
            logger.error(f"登录过程出错: {e}")
            return False
    
    async def save_session(self) -> bool:
        """
        保存当前会话状态
        
        Returns:
            bool: 保存是否成功
        """
        if not self.context:
            logger.error("浏览器上下文不存在，无法保存会话")
            return False
        
        try:
            storage_state = await self.context.storage_state()
            success = self.session_manager.save_session(storage_state)
            
            if success:
                logger.info("会话已成功保存")
            else:
                logger.error("保存会话失败")
            
            return success
            
        except Exception as e:
            logger.error(f"保存会话时出错: {e}")
            return False
    
    async def close(self):
        """关闭浏览器"""
        try:
            if self.browser:
                await self.browser.close()
                logger.info("浏览器已关闭")
            
            if self.playwright:
                await self.playwright.stop()
                logger.info("Playwright已停止")
        except Exception as e:
            logger.error(f"关闭浏览器时出错: {e}")


async def login_aliyun(session_manager: SessionManager, 
                      username: Optional[str] = None, 
                      password: Optional[str] = None,
                      browser_channel: Optional[str] = None) -> bool:
    """
    登录阿里云的便捷函数
    从环境变量读取用户名和密码（如果参数未提供）
    
    Args:
        session_manager: 会话管理器实例
        username: 用户名（可选，如果不提供则从环境变量读取）
        password: 密码（可选，如果不提供则从环境变量读取）
        browser_channel: 浏览器通道（可选，'chrome'、'chrome-beta'、'msedge'等）
        
    Returns:
        bool: 登录是否成功
    """
    login_manager = LoginManager(session_manager)
    
    try:
        await login_manager.initialize(browser_channel=browser_channel)
        success = await login_manager.login(username, password)
        
        if success:
            await login_manager.save_session()
        else:
            logger.error("登录失败，无法保存会话")
        
        # 关闭浏览器
        await login_manager.close()
        
        return success
        
    except ValueError as e:
        # 配置错误，直接抛出
        logger.error(f"登录配置错误: {e}")
        await login_manager.close()
        raise
    except Exception as e:
        logger.error(f"登录过程出错: {e}")
        await login_manager.close()
        return False


async def ensure_logged_in(page: Page, username: str, password: str, is_sso: bool = False):
    """
    确保已登录，如果未登录则执行登录（兼容接口，用于替换 login_module.ensure_logged_in）
    
    Args:
        page: Playwright Page 对象
        username: 用户名
        password: 密码
        is_sso: 是否为SSO登录（True=SSO登录，False=官网登录）
    """
    if is_sso:
        # SSO登录流程
        await page.goto("https://login.alibaba-inc.com/ssoLogin.htm", timeout=60000)
        
        # 填写用户名和密码
        await page.fill("#account", username)
        await asyncio.sleep(0.5)
        await page.fill("#password", password)
        
        # 提交登录表单
        await page.click("button:has-text('登 录')")
        
        # 等待跳转或加载完成
        await asyncio.sleep(1)
        
        # 可选：等待某个登录成功标志出现
        try:
            await page.wait_for_selector("h2:has-text('Welcome')", timeout=10000)
        except Exception:
            pass
        
        # 保存会话状态
        session_manager = SessionManager(SESSION_PATH)
        context = page.context
        storage_state = await context.storage_state()
        session_manager.save_session(storage_state)
        logger.info("SSO登录完成，会话已保存")
    else:
        # 官网登录流程 - 使用 LoginManager
        session_manager = SessionManager(SESSION_PATH)
        login_manager = LoginManager(session_manager)
        login_manager.page = page
        login_manager.context = page.context
        login_manager.browser = page.context.browser
        
        success = await login_manager.login(username, password)
        if success:
            await login_manager.save_session()
            logger.info("官网登录完成，会话已保存")
        else:
            logger.error("官网登录失败")


async def create_playwright_session(
    username: str = None,
    password: str = None,
    browser_type: str = 'chromium',
    browser_channel: str = None,
    headless: bool = False,
    is_sso: bool = False
):
    """
    创建一个已登录的 Playwright 会话（兼容接口，用于替换 login_module.create_playwright_session）
    
    Args:
        username: 用户名，如果不提供则从环境变量读取（SSO登录用SSO_USERNAME，官网登录用ALIYUN_USERNAME）
        password: 密码，如果不提供则从环境变量读取（SSO登录用SSO_PASSWORD，官网登录用ALIYUN_PASSWORD）
        browser_type: 浏览器类型 ('chromium', 'firefox', 'webkit')
        browser_channel: 浏览器渠道（如 'msedge', 'chrome'）
        headless: 是否无头模式
        is_sso: 是否为SSO登录（True=SSO登录，False=官网登录）
        
    Returns:
        tuple: (playwright, browser, context, page) - Playwright 对象、浏览器、上下文和页面
    """
    from playwright.async_api import async_playwright
    
    # 如果未提供用户名和密码，从环境变量读取
    if not username:
        username = SSO_USERNAME if is_sso else ALIYUN_USERNAME
    if not password:
        password = SSO_PASSWORD if is_sso else ALIYUN_PASSWORD
    
    # 验证用户名和密码是否已配置
    if not username or not password:
        login_type = "SSO" if is_sso else "官网"
        env_vars = "SSO_USERNAME/SSO_PASSWORD" if is_sso else "ALIYUN_USERNAME/ALIYUN_PASSWORD"
        raise ValueError(
            f"{login_type}登录凭据未配置！\n"
            f"请在 .env 文件中配置以下环境变量：\n"
            f"  {env_vars}\n"
            "或者通过函数参数传入用户名和密码。"
        )
    
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
    
    # 创建浏览器上下文
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        storage_state=storage_state,  # 如果会话有效，使用会话
        ignore_https_errors=True,
    )
    
    # 创建新页面
    page = await context.new_page()
    
    # 登录检测与自动登录
    await ensure_logged_in(page, username, password, is_sso=is_sso)
    
    return playwright, browser, context, page

