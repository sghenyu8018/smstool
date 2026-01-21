"""
配置文件模块
用于管理项目的配置信息
"""
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 基础路径配置
BASE_DIR = Path(__file__).parent.parent
SESSION_DIR = BASE_DIR / 'session'
DOWNLOAD_DIR = BASE_DIR / 'downloads'

# 确保目录存在
SESSION_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

# 登录配置
LOGIN_URL = 'https://account.aliyun.com/login/login.htm'

# 阿里云登录凭据（可选，如果使用自动登录）
ALIYUN_USERNAME = os.getenv('ALIYUN_USERNAME', '')
ALIYUN_PASSWORD = os.getenv('ALIYUN_PASSWORD', '')

# SSO登录凭据（用于 login_module.py，可选）
SSO_USERNAME = os.getenv('SSO_USERNAME', '')
SSO_PASSWORD = os.getenv('SSO_PASSWORD', '')

# SLS OSS访问日志配置
# region配置：从环境变量读取，例如 'zhangjiakou-2', 'beijing' 等
SLS_OSS_LOG_REGION = os.getenv('SLS_OSS_LOG_REGION', 'zjk')
# 如果直接设置了 SLS_OSS_LOG_URL，则使用直接设置的URL
# 否则根据 region 动态构建URL
SLS_OSS_LOG_URL = os.getenv('SLS_OSS_LOG_URL', '')
if not SLS_OSS_LOG_URL:
    SLS_OSS_LOG_URL = f'https://sls.console.aliyun.com/lognext/project/oss-access-log-{SLS_OSS_LOG_REGION}/logsearch/apache_nginx_user_defined?slsRegion=cn-zhangjiakou-2'
# SLS日志下载任务页面URL

# 下载配置
DOWNLOAD_MINUTES = int(os.getenv('DOWNLOAD_MINUTES', 1))  # 默认下载最近43200分钟（30天）的日志
DOWNLOAD_DIR_PATH = Path(os.getenv('DOWNLOAD_DIR', str(DOWNLOAD_DIR)))
# 时间范围配置：标准时间格式，例如 '2026-01-11 15:58:36 ~ 2026-01-11 16:13:36'
# 如果设置了 TIME_RANGE，则优先使用 TIME_RANGE，忽略 DOWNLOAD_MINUTES
TIME_RANGE = os.getenv('TIME_RANGE', '').strip()  # 时间范围字符串，格式：'YYYY-MM-DD HH:MM:SS ~ YYYY-MM-DD HH:MM:SS'
print(TIME_RANGE)
# 查询配置
QUERY_STATEMENT = os.getenv('QUERY_STATEMENT', 'bucket:shenyu111')  # 默认查询语句，可通过环境变量修改

# 会话配置
SESSION_FILE = os.getenv('SESSION_FILE', 'aliyun_session.json')
SESSION_PATH = SESSION_DIR / SESSION_FILE
# Playwright 的 storage_state 文件路径（统一保存到 session/ 目录）
STORAGE_STATE_FILE = os.getenv('STORAGE_STATE_FILE', 'storage_state.json')
STORAGE_STATE_PATH = SESSION_DIR / STORAGE_STATE_FILE

# 浏览器配置
HEADLESS = os.getenv('HEADLESS', 'False').lower() == 'true'
BROWSER_TIMEOUT = int(os.getenv('BROWSER_TIMEOUT', 60000))  # 毫秒
# 浏览器类型（'chromium'、'firefox'、'webkit'）
BROWSER_TYPE = os.getenv('BROWSER_TYPE', 'chromium')  # 默认使用 chromium
# 浏览器渠道（'chrome'、'msedge'、'chrome-beta'、'chrome-dev'，None则使用Playwright自带的浏览器）
BROWSER_CHANNEL = os.getenv('BROWSER_CHANNEL', 'msedge')  # 默认使用 Edge

# 日志配置
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = BASE_DIR / 'logs'  # 日志文件目录
LOG_DIR.mkdir(parents=True, exist_ok=True)  # 确保日志目录存在

# 按日期生成日志文件名（格式：YYYY-MM-DD.log）
LOG_FILE = datetime.now().strftime('%Y-%m-%d.log')
LOG_PATH = LOG_DIR / LOG_FILE

# DashScope API配置（用于browser-use）
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY', '')
DASHSCOPE_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
DASHSCOPE_MODEL = os.getenv('DASHSCOPE_MODEL', 'qwen-vl-max-latest')

# 短信签名查询配置
SMS_PID = os.getenv('SMS_PID', '')  # 客户PID
SMS_SIGN_NAME = os.getenv('SMS_SIGN_NAME', '')  # 签名名称