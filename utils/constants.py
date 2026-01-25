"""
常量配置模块
包含页面URL和元素选择器配置
"""

# 页面配置
SIGN_QUERY_URL = "https://alicom-ops.alibaba-inc.com/dysms/dysms_sa/analyze_search/sign"
SUCCESS_RATE_QUERY_URL = "https://alicom-ops.alibaba-inc.com/dysms/dysms_schedule_data_center/dysms_datacenter_recommend_failure"
QUALIFICATION_ORDER_QUERY_URL = "https://alicom-ops.alibaba-inc.com/dyorder/dyorder_new/dyorder_search"

# 页面元素选择器配置（便于后期调整）
SELECTORS = {
    'partner_id': '#PartnerId',  # 客户PID输入框（签名查询页面）
    'sign_name': '#SignName',    # 签名名称输入框
    'table_row': 'tr.dumbo-antd-0-1-18-table-row',  # 表格行
    'work_order_primary': 'div.break-all',  # 工单号（优先选择器）
    'work_order_fallback': 'td.dumbo-antd-0-1-18-table-cell',  # 工单号（备选选择器）
    
    # 成功率查询页面选择器
    'success_rate_menu_item': 'div.MenuItem___2wtEa:has-text("求德大盘")',  # 求德大盘菜单项
    'success_rate_pid_input': 'span.obviz-base-filterText:has-text("pid") ~ * span.obviz-base-filterInput input[autocomplete="off"]',  # PID输入框
    'success_rate_time_selector': 'div[data-spm-click*="time"]',  # 时间选择器
    'success_rate_time_option': 'li.obviz-base-li-block:has-text("30天")',  # 30天选项
    'success_rate_table_row': 'div.obviz-base-easyTable-row',  # 成功率表格行
    'success_rate_value': 'div.table-m__split-container__67f567d5 span',  # 成功率值
    
    # 资质工单查询页面选择器
    'qualification_order_id_input': '#OrderId',  # 工单号输入框
    'qualification_query_button': 'button.ant-btn-primary:has-text("查 询")',  # 查询按钮
    'qualification_order_link': 'td.ant-table-cell a[_nk="DYsM21"]',  # 工单号链接
    'qualification_id_row': 'tr.ant-table-row td.ant-table-cell:has-text("关联资质ID")',  # 关联资质ID行
    'qualification_group_id_row': 'tr.ant-table-row td.ant-table-cell:has-text("资质组ID")',  # 资质组ID行
    'qualification_id_value': 'pre[_nk="E7Xi41"]',  # 资质ID值（pre标签）
    'qualification_pid_input': 'input#PartnerId, input[placeholder*="PID"], input[placeholder*="pid"]',  # PID输入框
    'qualification_sms_row': 'tr.ant-table-row:has-text("短信资质(智能)")',  # 包含"短信资质(智能)"的行
}
