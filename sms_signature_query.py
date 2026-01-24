"""
短信签名查询模块
提供可扩展的短信签名查询功能，便于后期调整和扩展其他功能

此模块作为主入口，实际的查询功能已拆分到 utils/sms_query_tools.py
"""
import asyncio
from typing import Dict
from playwright.async_api import Page

# 从工具模块导入查询函数和配置
from utils.sms_query_tools import (
    query_sms_signature,
    query_sms_success_rate,
    SELECTORS
)

# 为了向后兼容，重新导出这些函数
__all__ = [
    'query_sms_signature',
    'query_sms_success_rate',
    'SELECTORS',
    'SMSQueryBase'
]


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
            
            success_rate_result = await query_sms_success_rate(page=page, time_range='30天')
            
            # 处理成功率查询结果
            if success_rate_result['success']:
                print(f"\n[OK] 成功率查询成功！")
                print(f"成功率: {success_rate_result['success_rate']}%")
                
                # 如果有多行数据，显示所有数据
                if success_rate_result.get('data'):
                    matched_count = success_rate_result.get('matched_count', 0)
                    total_count = success_rate_result.get('total_count', 0)
                    if matched_count > 0:
                        print(f"\n共找到 {matched_count} 条PID匹配的记录（总计 {total_count} 条）:")
                    else:
                        print(f"\n共找到 {total_count} 条记录:")
                    for i, row in enumerate(success_rate_result['data'], 1):
                        sign_name = row.get('signname') or row.get('sign_name', 'N/A')
                        success_rate = row.get('receipt_success_rate') or row.get('success_rate', 'N/A')
                        sms_type = row.get('sms_type') or row.get('template_type', 'N/A')
                        submit_count = row.get('submit_count') or row.get('total_sent', 'N/A')
                        print(f"  {i}. 签名: {sign_name}, "
                              f"成功率: {success_rate}%, "
                              f"短信类型: {sms_type}, "
                              f"提交量: {submit_count}")
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
