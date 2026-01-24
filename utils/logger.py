"""
日志模块
提供统一的日志记录功能
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


class Logger:
    """日志记录器类"""
    
    def __init__(self, name: str = 'smstool', log_dir: str = 'logs'):
        """
        初始化日志记录器
        
        Args:
            name: 日志记录器名称
            log_dir: 日志文件保存目录
        """
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # 创建日志记录器
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # 避免重复添加处理器
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        """设置日志处理器"""
        # 1. 控制台处理器（输出到终端）
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        
        # 2. 文件处理器（输出到文件，包含所有级别）
        timestamp = datetime.now().strftime('%Y%m%d')
        log_file = self.log_dir / f'{self.name}_{timestamp}.log'
        file_handler = logging.FileHandler(
            log_file,
            encoding='utf-8',
            mode='a'  # 追加模式
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        
        # 添加处理器
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def debug(self, message: str):
        """记录DEBUG级别日志"""
        self.logger.debug(message)
    
    def info(self, message: str):
        """记录INFO级别日志"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """记录WARNING级别日志"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """记录ERROR级别日志"""
        self.logger.error(message)
    
    def critical(self, message: str):
        """记录CRITICAL级别日志"""
        self.logger.critical(message)
    
    def log_section(self, title: str, level: str = 'info'):
        """
        记录一个章节标题
        
        Args:
            title: 章节标题
            level: 日志级别
        """
        separator = '=' * 60
        message = f"\n{separator}\n{title}\n{separator}"
        if level == 'info':
            self.info(message)
        elif level == 'debug':
            self.debug(message)
        elif level == 'warning':
            self.warning(message)
        elif level == 'error':
            self.error(message)
    
    def log_iframe_elements(self, pid: Optional[str], time_range: str, 
                           filter_texts: list, inputs: list, 
                           table_rows_count: int, table_cells_count: int):
        """
        记录SLS iframe元素信息到专门的日志文件
        
        Args:
            pid: 客户PID
            time_range: 时间范围
            filter_texts: 筛选条件标签列表
            inputs: 输入框列表
            table_rows_count: 表格行数量
            table_cells_count: 表格单元格数量
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = self.log_dir / f'sls_iframe_elements_{timestamp}.log'
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"{'='*60}\n")
                f.write(f"步骤6: 打印SLS iframe中的所有元素（用于判断查询条件和输出内容）\n")
                f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"PID: {pid}\n")
                f.write(f"时间范围: {time_range}\n")
                f.write(f"{'='*60}\n\n")
                
                f.write("【查询条件区域】\n")
                f.write(f"  - 找到 {len(filter_texts)} 个筛选条件标签:\n")
                for idx, text in enumerate(filter_texts[:20], 1):
                    f.write(f"    {idx}. {text}\n")
                
                f.write(f"\n  - 找到 {len(inputs)} 个输入框:\n")
                for idx, inp_info in enumerate(inputs[:20], 1):
                    f.write(f"    {idx}. {inp_info}\n")
                
                f.write("\n【输出内容区域】\n")
                f.write(f"  - 找到 {table_rows_count} 个表格行/行元素\n")
                f.write(f"  - 找到 {table_cells_count} 个表格单元格\n")
            
            self.info(f"  ✓ 日志已保存到: {log_file}")
            return str(log_file)
        except Exception as e:
            self.error(f"  ✗ 保存日志文件时出错: {e}")
            return None


# 创建默认的日志记录器实例
default_logger = Logger()


def get_logger(name: Optional[str] = None) -> Logger:
    """
    获取日志记录器实例
    
    Args:
        name: 日志记录器名称，如果为None则返回默认记录器
        
    Returns:
        Logger实例
    """
    if name is None:
        return default_logger
    return Logger(name=name)
