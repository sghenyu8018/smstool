# SMS工具 - 短信签名查询系统

## 项目简介

这是一个基于 Playwright 的自动化工具，用于查询阿里巴巴内部短信签名相关的工单号和成功率。工具支持自动登录、会话管理和可扩展的查询功能，便于后期添加其他业务功能。

## 功能特性

- ✅ **自动登录**：支持 SSO 自动登录，会话自动保存和恢复
- ✅ **短信签名查询**：根据客户 PID 和签名名称查询工单号
- ✅ **成功率查询**：查询短信签名的成功率统计数据
- ✅ **多行数据支持**：自动识别多行工单号，选择最新的数据
- ✅ **会话管理**：自动管理浏览器会话，支持24小时有效期验证
- ✅ **可扩展设计**：模块化架构，便于添加新的查询功能
- ✅ **错误处理**：完善的异常处理和用户友好的错误提示
- ✅ **配置灵活**：支持环境变量配置，便于不同环境部署

## 安装指南

### 前置要求

- Python 3.8 或更高版本
- 有效的阿里巴巴 SSO 账号

### 安装步骤

1. **克隆或下载项目**

```bash
cd smstool
```

2. **安装 Python 依赖**

```bash
pip install -r requirements.txt
```

3. **安装 Playwright 浏览器**

```bash
playwright install chromium
```

或者如果使用其他浏览器：

```bash
playwright install firefox  # 或 webkit
```

4. **配置环境变量**

创建 `.env` 文件（参考 `.env.example`），并填写以下配置：

```env
# SSO登录凭据（必需）
SSO_USERNAME=your_username
SSO_PASSWORD=your_password
```

## 配置说明

### 环境变量

在项目根目录创建 `.env` 文件，配置以下变量：

| 变量名 | 说明 | 是否必需 | 默认值 |
|--------|------|---------|--------|
| `SSO_USERNAME` | SSO 用户名 | 是 | - |
| `SSO_PASSWORD` | SSO 密码 | 是 | - |
| `SMS_PID` | 客户PID（用于查询） | 否 | - |
| `SMS_SIGN_NAME` | 签名名称（用于查询） | 否 | - |
| `SESSION_FILE` | 会话文件名 | 否 | `aliyun_session.json` |
| `HEADLESS` | 是否无头模式 | 否 | `False` |
| `BROWSER_TYPE` | 浏览器类型 | 否 | `chromium` |
| `BROWSER_CHANNEL` | 浏览器渠道 | 否 | `msedge` |

### 配置文件位置

- 会话文件保存在 `session/` 目录
- 会话有效期：24小时（自动验证）

## 使用示例

### 基本使用

```python
import asyncio
from login_module import create_playwright_session
from sms_signature_query import query_sms_signature

async def main():
    # 1. 创建已登录的浏览器会话
    print("正在创建浏览器会话...")
    playwright, browser, context, page = await create_playwright_session(headless=False)
    
    try:
        # 2. 执行短信签名查询
        result = await query_sms_signature(
            page=page,
            pid="100000103722927",  # 客户PID
            sign_name="国能e购"      # 签名名称
        )
        
        # 3. 处理查询结果
        if result['success']:
            print(f"✓ 查询成功！")
            print(f"工单号: {result['work_order_id']}")
        else:
            print(f"✗ 查询失败: {result['error']}")
            
    finally:
        # 4. 清理资源
        await context.close()
        await browser.close()
        await playwright.stop()

# 运行示例
asyncio.run(main())
```

### 命令行使用

直接运行查询模块：

```bash
python sms_signature_query.py
```

### 批量查询示例

```python
import asyncio
from login_module import create_playwright_session
from sms_signature_query import query_sms_signature

async def batch_query():
    # 查询列表
    queries = [
        {"pid": "100000103722927", "sign_name": "国能e购"},
        {"pid": "100000103722928", "sign_name": "其他签名"},
        # 添加更多查询...
    ]
    
    # 创建会话
    playwright, browser, context, page = await create_playwright_session(headless=False)
    
    try:
        results = []
        for query in queries:
            print(f"\n正在查询: PID={query['pid']}, 签名={query['sign_name']}")
            result = await query_sms_signature(
                page=page,
                pid=query['pid'],
                sign_name=query['sign_name']
            )
            results.append(result)
            
            # 添加延迟，避免请求过快
            await asyncio.sleep(2)
        
        # 输出所有结果
        for i, result in enumerate(results):
            if result['success']:
                print(f"查询 {i+1}: 工单号 = {result['work_order_id']}")
            else:
                print(f"查询 {i+1}: 失败 - {result['error']}")
                
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

asyncio.run(batch_query())
```

### 成功率查询示例

```python
import asyncio
from login_module import create_playwright_session
from sms_signature_query import query_sms_success_rate

async def query_success_rate():
    # 创建会话
    playwright, browser, context, page = await create_playwright_session(headless=False)
    
    try:
        # 执行成功率查询（如果不传参数，会从环境变量读取PID）
        result = await query_sms_success_rate(page=page, pid="100000103722927")
        
        # 处理结果
        if result['success']:
            print(f"✓ 查询成功！")
            print(f"成功率: {result['success_rate']}%")
            
            # 如果有多行数据，显示所有数据
            if result.get('data'):
                print(f"\n共找到 {result.get('total_count', 0)} 条记录:")
                for i, row in enumerate(result['data'], 1):
                    print(f"  {i}. 签名: {row.get('sign_name', 'N/A')}, "
                          f"成功率: {row.get('success_rate', 'N/A')}%")
        else:
            print(f"✗ 查询失败: {result['error']}")
            
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

asyncio.run(query_success_rate())
```

## 模块说明

### login_module.py

登录模块，提供 SSO 自动登录功能。

**主要函数：**
- `create_playwright_session()` - 创建已登录的 Playwright 会话
- `ensure_logged_in()` - 确保已登录，未登录则自动登录
- `perform_login()` - 执行登录操作

**使用示例：**
```python
from login_module import create_playwright_session

playwright, browser, context, page = await create_playwright_session(
    headless=False,  # 是否无头模式
    browser_type='chromium',  # 浏览器类型
    browser_channel='msedge'  # 浏览器渠道
)
```

### sms_signature_query.py

短信签名查询模块，提供查询功能。

**主要函数：**

1. **`query_sms_signature(page, pid, sign_name)`** - 查询短信签名并获取工单号
   - 支持多行工单号查询
   - 根据修改时间自动选择最新的工单号
   - 可从环境变量读取参数

   **返回值：**
   ```python
   {
       'success': bool,           # 是否查询成功
       'work_order_id': str,      # 工单号（成功时，最新的）
       'all_work_orders': List,   # 所有工单号列表（如果有）
       'total_count': int,        # 工单号总数
       'error': str               # 错误信息（失败时）
   }
   ```

2. **`query_sms_success_rate(page, pid)`** - 查询短信签名成功率
   - 自动选择时间范围（本周）
   - 返回详细的统计数据

   **返回值：**
   ```python
   {
       'success': bool,           # 是否查询成功
       'success_rate': str,       # 成功率（百分比）
       'pid': str,                # 客户PID
       'data': List[Dict],        # 所有数据行（包含详细信息）
       'total_count': int,        # 数据行总数
       'error': str               # 错误信息（失败时）
   }
   ```

**配置：**
- 页面 URL 和元素选择器可在模块顶部配置
- 支持自定义超时时间
- 支持从环境变量读取 PID 和签名名称

### config.py

配置管理模块，统一管理项目配置。

**主要配置：**
- SSO 登录凭据
- 会话文件路径
- 浏览器配置
- 日志配置

### session_manager.py

会话管理模块，负责会话的保存、加载和验证。

**主要类：**
- `SessionManager` - 会话管理器

**主要方法：**
- `save_session()` - 保存会话状态
- `get_storage_state()` - 获取会话状态（带有效期验证）
- `is_session_valid()` - 检查会话是否有效

## 扩展指南

### 添加新的查询功能

1. **创建新的查询模块**

在 `sms_signature_query.py` 中添加新函数，或创建新模块：

```python
# 新查询模块示例
async def query_other_function(page: Page, param1: str, param2: str) -> Dict:
    """新的查询功能"""
    # 1. 定义页面选择器（可配置化）
    SELECTORS = {
        'input_field': '#inputId',
        'result_field': '.result-class'
    }
    
    # 2. 实现查询逻辑
    try:
        await page.goto("https://example.com/query")
        await page.fill(SELECTORS['input_field'], param1)
        # ... 其他操作
        
        # 3. 提取结果
        result_element = await page.query_selector(SELECTORS['result_field'])
        result_text = await result_element.inner_text()
        
        # 4. 返回结构化结果
        return {
            'success': True,
            'data': result_text,
            'error': None
        }
    except Exception as e:
        return {
            'success': False,
            'data': None,
            'error': str(e)
        }
```

2. **使用基类（可选）**

继承 `SMSQueryBase` 类来实现新功能：

```python
from sms_signature_query import SMSQueryBase

class MyCustomQuery(SMSQueryBase):
    """自定义查询类"""
    
    async def query(self, param1: str, param2: str):
        # 实现查询逻辑
        pass
```

3. **更新配置**

如果需要新的配置项，在 `config.py` 中添加：

```python
# 新功能配置
MY_FEATURE_URL = os.getenv('MY_FEATURE_URL', 'https://example.com')
MY_FEATURE_TIMEOUT = int(os.getenv('MY_FEATURE_TIMEOUT', 30000))
```

### 模块设计原则

1. **可扩展性**
   - 选择器配置化，便于调整
   - 统一的返回格式
   - 独立的模块封装

2. **可维护性**
   - 清晰的代码结构
   - 详细的文档字符串
   - 完善的错误处理

3. **可测试性**
   - 函数职责单一
   - 参数化配置
   - 易于 mock 测试

## 常见问题

### Q1: 登录失败怎么办？

**A:** 请检查：
1. `.env` 文件中的 `SSO_USERNAME` 和 `SSO_PASSWORD` 是否正确
2. 账号是否有访问权限
3. 网络连接是否正常
4. 会话是否过期（删除 `session/` 目录下的文件后重试）

### Q2: 查询不到工单号？

**A:** 可能的原因：
1. 客户 PID 或签名名称不正确
2. 该签名在系统中不存在
3. 页面结构发生变化（需要更新选择器）

### Q3: 如何更新页面元素选择器？

**A:** 在 `sms_signature_query.py` 文件顶部的 `SELECTORS` 字典中修改：

```python
SELECTORS = {
    'partner_id': '#PartnerId',  # 修改为新选择器
    # ...
}
```

### Q4: 会话过期时间是多少？

**A:** 默认会话有效期为 24 小时。如果会话过期，程序会自动重新登录。

### Q5: 如何修改浏览器类型？

**A:** 有两种方式：
1. 在 `.env` 文件中设置：`BROWSER_TYPE=firefox`
2. 在代码中指定：`create_playwright_session(browser_type='firefox')`

### Q6: 支持无头模式吗？

**A:** 支持。设置 `headless=True`：
```python
playwright, browser, context, page = await create_playwright_session(headless=True)
```

或在 `.env` 文件中设置：`HEADLESS=True`

## 开发说明

### 项目结构

```
smstool/
├── login_module.py          # 登录模块
├── sms_signature_query.py   # 短信签名查询模块
├── config.py                # 配置管理模块
├── session_manager.py       # 会话管理模块
├── requirements.txt         # Python 依赖
├── README.md                # 项目文档
├── CHANGELOG.md             # 更新日志
├── .env.example             # 环境变量示例
├── session/                 # 会话文件目录
└── logs/                    # 日志文件目录
```

### 依赖说明

主要依赖：
- `playwright` - 浏览器自动化
- `python-dotenv` - 环境变量管理
- `aiofiles` - 异步文件操作

### 日志

日志文件保存在 `logs/` 目录，按日期命名（格式：`YYYY-MM-DD.log`）。

### 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 发起 Pull Request

## 许可证

本项目仅供内部使用。

## 联系方式

如有问题或建议，请联系项目维护者。

---

**最后更新：** 2024年