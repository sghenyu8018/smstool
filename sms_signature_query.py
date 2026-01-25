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
    query_sms_success_rate_multi,
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
        playwright, browser, context, page = await create_playwright_session(
            headless=False,
            viewport={'width': 1280, 'height': 1100}  # 设置浏览器窗口尺寸为 1280×1100
        )
        print("浏览器会话已创建")
        
        try:
            # 执行查询（如果不传参数，会从环境变量读取）
            signature_result = await query_sms_signature(page=page)
            
            # 处理结果
            if signature_result['success']:
                print(f"\n[OK] 查询成功！")
                print(f"工单号（最新）: {signature_result['work_order_id']}")
                
                # 如果有多行数据，显示所有工单号
                if 'all_work_orders' in signature_result and signature_result['all_work_orders']:
                    print(f"\n共找到 {signature_result['total_count']} 个工单号:")
                    for i, wo in enumerate(signature_result['all_work_orders'], 1):
                        print(f"  {i}. 工单号: {wo['work_order_id']}, 修改时间: {wo['modify_time']}")
            else:
                print(f"\n[FAIL] 查询失败: {signature_result['error']}")
            
            # 查询短信签名成功率（多时间范围）
            print("\n" + "="*60)
            print("开始查询短信签名成功率（多时间范围）...")
            print("="*60)
            
            # 查询多个时间范围的成功率
            multi_result = await query_sms_success_rate_multi(
                page=page,
                time_ranges=['当天', '一周', '本周', '30天']
            )
            
            # 处理多时间范围查询结果
            if multi_result['success']:
                print(f"\n[OK] 成功率查询成功！")
                
                # 按用户要求的格式输出：时间范围、签名、成功率、短信类型、提交量
                for time_range in multi_result['time_ranges']:
                    # 检查该时间范围的结果是否存在
                    if time_range not in multi_result['results']:
                        print(f"\n{time_range}成功率")
                        print("-" * 60)
                        print(f"查询失败: 该时间范围的查询结果不存在")
                        continue
                    
                    result = multi_result['results'][time_range]
                    
                    if result['success'] and result.get('data'):
                        print(f"\n{time_range}成功率")
                        print("-" * 60)
                        print(f"{'签名':<20} {'成功率':<15} {'短信类型':<15} {'提交量':<15}")
                        print("-" * 60)
                        
                        for row in result['data']:
                            sign_name = row.get('signname') or row.get('sign_name', 'N/A')
                            success_rate = row.get('receipt_success_rate') or row.get('success_rate', 'N/A')
                            sms_type = row.get('sms_type') or row.get('template_type', 'N/A')
                            submit_count = row.get('submit_count') or row.get('total_sent', 'N/A')
                            
                            # 格式化成功率显示（移除%符号，只保留数字）
                            if isinstance(success_rate, (int, float)):
                                success_rate_str = f"{success_rate}"
                            else:
                                # 移除%符号，只保留数字
                                success_rate_str = str(success_rate).replace('%', '').strip()
                            
                            # 格式化提交量（保持原始格式，不添加千位分隔符）
                            if isinstance(submit_count, (int, float)):
                                submit_count_str = f"{int(submit_count)}"
                            else:
                                submit_count_str = str(submit_count)
                            
                            print(f"{sign_name:<20} {success_rate_str:<15} {sms_type:<15} {submit_count_str:<15}")
                    else:
                        print(f"\n{time_range}成功率")
                        print("-" * 60)
                        if not result.get('success', False):
                            print(f"查询失败: {result.get('error', '未知错误')}")
                        else:
                            print("未找到数据")
            else:
                print(f"\n[FAIL] 成功率查询失败: {multi_result.get('error', '未知错误')}")
                
                # 即使部分失败，也显示成功的结果
                has_success = False
                for time_range in multi_result['time_ranges']:
                    # 检查该时间范围的结果是否存在
                    if time_range not in multi_result['results']:
                        print(f"\n{time_range}成功率")
                        print("-" * 60)
                        print(f"查询失败: 该时间范围的查询结果不存在（可能因为首次查询失败导致后续查询未执行）")
                        continue
                    
                    result = multi_result['results'][time_range]
                    if result.get('success', False) and result.get('data'):
                        if not has_success:
                            print(f"\n部分查询成功，显示成功的结果：")
                            has_success = True
                        
                        print(f"\n{time_range}成功率")
                        print("-" * 60)
                        print(f"{'签名':<20} {'成功率':<15} {'短信类型':<15} {'提交量':<15}")
                        print("-" * 60)
                        
                        for row in result['data']:
                            sign_name = row.get('signname') or row.get('sign_name', 'N/A')
                            success_rate = row.get('receipt_success_rate') or row.get('success_rate', 'N/A')
                            sms_type = row.get('sms_type') or row.get('template_type', 'N/A')
                            submit_count = row.get('submit_count') or row.get('total_sent', 'N/A')
                            
                            # 格式化成功率显示（移除%符号，只保留数字）
                            if isinstance(success_rate, (int, float)):
                                success_rate_str = f"{success_rate}"
                            else:
                                # 移除%符号，只保留数字
                                success_rate_str = str(success_rate).replace('%', '').strip()
                            
                            # 格式化提交量（保持原始格式，不添加千位分隔符）
                            if isinstance(submit_count, (int, float)):
                                submit_count_str = f"{int(submit_count)}"
                            else:
                                submit_count_str = str(submit_count)
                            
                            print(f"{sign_name:<20} {success_rate_str:<15} {sms_type:<15} {submit_count_str:<15}")
            
            # 最后汇总输出：工单号和成功率数据
            print("\n" + "="*60)
            print("查询结果汇总")
            print("="*60)
            
            # 输出工单号信息
            if signature_result.get('success'):
                print(f"\n工单号信息：")
                print(f"  最新工单号: {signature_result.get('work_order_id', 'N/A')}")
                if 'all_work_orders' in signature_result and signature_result['all_work_orders']:
                    print(f"  共找到 {signature_result.get('total_count', 0)} 个工单号")
                    for i, wo in enumerate(signature_result['all_work_orders'][:3], 1):  # 只显示前3个
                        print(f"    {i}. {wo['work_order_id']} (修改时间: {wo['modify_time']})")
            else:
                print(f"\n工单号信息：查询失败 - {signature_result.get('error', '未知错误')}")
            
            # 输出成功率数据汇总（完整表格格式）
            print(f"\n成功率数据汇总：")
            has_success_data = False
            for time_range in multi_result.get('time_ranges', []):
                if time_range in multi_result.get('results', {}):
                    result = multi_result['results'][time_range]
                    if result.get('success') and result.get('data'):
                        has_success_data = True
                        # 输出完整表格格式（美化）
                        print(f"\n{time_range}成功率")
                        print("-" * 60)
                        print(f"{'签名':<20} {'成功率':<15} {'短信类型':<15} {'提交量':<15}")
                        print("-" * 60)
                        
                        for row in result['data']:
                            sign_name = row.get('signname') or row.get('sign_name', 'N/A')
                            success_rate = row.get('receipt_success_rate') or row.get('success_rate', 'N/A')
                            sms_type = row.get('sms_type') or row.get('template_type', 'N/A')
                            submit_count = row.get('submit_count') or row.get('total_sent', 'N/A')
                            
                            # 格式化成功率显示（移除%符号，只保留数字）
                            if isinstance(success_rate, (int, float)):
                                success_rate_str = f"{success_rate}"
                            else:
                                # 移除%符号，只保留数字
                                success_rate_str = str(success_rate).replace('%', '').strip()
                            
                            # 格式化提交量（保持原始格式，不添加千位分隔符）
                            if isinstance(submit_count, (int, float)):
                                submit_count_str = f"{int(submit_count)}"
                            else:
                                submit_count_str = str(submit_count)
                            
                            print(f"{sign_name:<20} {success_rate_str:<15} {sms_type:<15} {submit_count_str:<15}")
                    elif not result.get('success'):
                        print(f"\n{time_range}成功率")
                        print("-" * 60)
                        print(f"查询失败: {result.get('error', '未知错误')}")
                else:
                    print(f"\n{time_range}成功率")
                    print("-" * 60)
                    print(f"查询结果不存在")
            
            if not has_success_data:
                print("  无成功查询的数据")
                
        finally:
            # 清理资源
            print("\n正在关闭浏览器...")
            await context.close()
            await browser.close()
            await playwright.stop()
            print("已关闭浏览器")
    
    # 运行示例
    asyncio.run(main())
