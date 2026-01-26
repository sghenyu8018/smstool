"""
测试不同窗口尺寸打开短信成功率查询页面

此脚本用于测试在不同窗口尺寸下，短信成功率查询页面的显示效果和功能是否正常。
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径，以便导入根目录的模块
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from login_module import create_playwright_session
from utils.constants import SUCCESS_RATE_QUERY_URL
TEST_URL = 'https://zh.wikipedia.org/wiki/%E4%B8%AD%E5%8D%8E%E4%BA%BA%E6%B0%91%E5%85%B1%E5%92%8C%E5%9B%BD%E8%A1%8C%E6%94%BF%E5%8C%BA%E5%88%92'

# 定义要测试的窗口尺寸
VIEWPORT_SIZES = [
    {'width': 1920, 'height': 1080, 'name': 'Full HD (1920x1080)'},
    {'width': 1600, 'height': 900, 'name': 'HD+ (1600x900)'},
    {'width': 1440, 'height': 900, 'name': 'WXGA+ (1440x900)'},
    {'width': 1280, 'height': 1100, 'name': 'Default (1280x1100)'},
    {'width': 1280, 'height': 720, 'name': 'HD (1280x720)'},
    {'width': 1024, 'height': 768, 'name': 'XGA (1024x768)'},
    {'width': 800, 'height': 600, 'name': 'SVGA (800x600)'},
]


async def test_viewport_size(viewport: dict, pid: str = None, save_screenshot: bool = True):
    """
    测试指定窗口尺寸下的成功率查询页面
    
    Args:
        viewport: 窗口尺寸字典，包含 'width', 'height', 'name'
        pid: 客户PID（可选，用于测试查询功能）
        save_screenshot: 是否保存截图
    """
    print(f"\n{'='*60}")
    print(f"测试窗口尺寸: {viewport['name']} ({viewport['width']}x{viewport['height']})")
    print(f"{'='*60}")
    
    # 创建浏览器会话
    try:
        playwright, browser, context, page = await create_playwright_session(
            headless=False,
            viewport={'width': viewport['width'], 'height': viewport['height']}
        )
        print(f"✓ 浏览器会话已创建，窗口尺寸: {viewport['width']}x{viewport['height']}")
        
        try:
            # 访问成功率查询页面
            print(f"正在访问成功率查询页面...")
            print(f"URL: {SUCCESS_RATE_QUERY_URL}")
            await page.goto(SUCCESS_RATE_QUERY_URL, wait_until='networkidle', timeout=60000)
            print(f"✓ 页面已加载")
            
            # 等待页面完全加载
            await asyncio.sleep(3)
            
            # 检查页面标题
            try:
                title = await page.title()
                print(f"✓ 页面标题: {title}")
            except Exception as e:
                print(f"⚠ 获取页面标题失败: {e}")
            
            # 检查关键元素是否存在
            print("检查关键元素...")
            key_elements = {
                '求德大盘菜单': 'div.MenuItem___2wtEa:has-text("求德大盘")',
                '页面内容': 'body',
            }
            
            for element_name, selector in key_elements.items():
                try:
                    element = page.locator(selector)
                    count = await element.count()
                    if count > 0:
                        is_visible = await element.first.is_visible()
                        print(f"  ✓ {element_name}: 找到 {count} 个，可见: {is_visible}")
                    else:
                        print(f"  ✗ {element_name}: 未找到")
                except Exception as e:
                    print(f"  ⚠ {element_name}: 检查失败 - {e}")
            
            # 检查 iframe
            print("检查 iframe...")
            await asyncio.sleep(2)  # 等待 iframe 加载
            frames = page.frames
            print(f"  找到 {len(frames)} 个 frame（包括主frame）")
            for idx, frame in enumerate(frames):
                try:
                    frame_url = frame.url
                    if 'sls4service.console.aliyun.com' in frame_url:
                        print(f"  ✓ Frame {idx}: SLS iframe - {frame_url[:80]}...")
                    else:
                        print(f"    Frame {idx}: {frame_url[:80]}...")
                except Exception as e:
                    print(f"  ⚠ Frame {idx}: 获取URL失败 - {e}")
            
            # 保存截图
            if save_screenshot:
                screenshot_dir = Path('test_screenshots')
                screenshot_dir.mkdir(exist_ok=True)
                
                # 生成文件名（去除特殊字符）
                safe_name = viewport['name'].replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_')
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                screenshot_path = screenshot_dir / f"{safe_name}_{viewport['width']}x{viewport['height']}_{timestamp}.png"
                
                try:
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                    print(f"✓ 截图已保存: {screenshot_path}")
                except Exception as e:
                    print(f"⚠ 保存截图失败: {e}")
            
            # 如果提供了 PID，尝试点击"求德大盘"菜单
            if pid:
                print(f"\n尝试点击'求德大盘'菜单（PID: {pid}）...")
                try:
                    menu_item = page.locator('div.MenuItem___2wtEa:has-text("求德大盘")')
                    if await menu_item.count() > 0:
                        await menu_item.click()
                        print(f"✓ 已点击'求德大盘'菜单")
                        await asyncio.sleep(3)  # 等待页面加载
                        
                        # 再次保存截图（点击菜单后）
                        if save_screenshot:
                            screenshot_path_after = screenshot_dir / f"{safe_name}_{viewport['width']}x{viewport['height']}_after_menu_{timestamp}.png"
                            try:
                                await page.screenshot(path=str(screenshot_path_after), full_page=True)
                                print(f"✓ 点击菜单后截图已保存: {screenshot_path_after}")
                            except Exception as e:
                                print(f"⚠ 保存截图失败: {e}")
                    else:
                        print(f"✗ 未找到'求德大盘'菜单")
                except Exception as e:
                    print(f"⚠ 点击菜单失败: {e}")
            
            # 等待一段时间，便于观察
            print(f"\n等待 5 秒，便于观察页面...")
            await asyncio.sleep(5)
            
            print(f"✓ 测试完成: {viewport['name']}")
            
        finally:
            # 清理资源
            await context.close()
            await browser.close()
            await playwright.stop()
            print(f"✓ 浏览器已关闭")
            
    except Exception as e:
        print(f"✗ 测试失败: {type(e).__name__} - {str(e)}")
        import traceback
        traceback.print_exc()


async def main():
    """
    主函数：测试所有窗口尺寸
    """
    print("="*60)
    print("短信成功率查询页面 - 窗口尺寸测试")
    print("="*60)
    
    # 从环境变量读取 PID（可选）
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    pid = os.getenv('SMS_PID', None)
    if pid:
        print(f"使用环境变量中的 PID: {pid}")
    else:
        print("未设置 SMS_PID 环境变量，将跳过菜单点击测试")
    
    # 测试所有窗口尺寸
    for viewport in VIEWPORT_SIZES:
        try:
            await test_viewport_size(viewport, pid=pid, save_screenshot=True)
        except Exception as e:
            print(f"✗ 测试 {viewport['name']} 时出错: {e}")
            continue
        
        # 测试间隔
        if viewport != VIEWPORT_SIZES[-1]:
            print(f"\n等待 3 秒后继续下一个测试...")
            await asyncio.sleep(3)
    
    print(f"\n{'='*60}")
    print("所有测试完成！")
    print(f"截图保存在: test_screenshots/ 目录")
    print(f"{'='*60}")


if __name__ == '__main__':
    asyncio.run(main())
