"""
短信查询工具模块（向后兼容层）
此模块已拆分为多个子模块，此文件仅用于向后兼容
建议使用新的模块结构：
- utils.sms_signature_query: 签名查询
- utils.sms_success_rate_query: 成功率查询
- utils.constants: 常量和选择器
- utils.helpers: 辅助函数
"""

# 向后兼容：从新模块导入所有函数和常量
from .sms_signature_query import query_sms_signature
from .sms_success_rate_query import query_sms_success_rate
from .constants import (
    SIGN_QUERY_URL,
    SUCCESS_RATE_QUERY_URL,
    SELECTORS
)
from .helpers import (
    extract_work_order_id as _extract_work_order_id,
    parse_datetime as _parse_datetime
)

__all__ = [
    'query_sms_signature',
    'query_sms_success_rate',
    'SIGN_QUERY_URL',
    'SUCCESS_RATE_QUERY_URL',
    'SELECTORS',
    '_extract_work_order_id',
    '_parse_datetime'
]
