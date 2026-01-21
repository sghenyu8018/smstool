"""
会话管理模块
负责会话文件的保存、加载和验证
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SessionManager:
    """会话管理器类"""
    
    def __init__(self, session_path: Path):
        """
        初始化会话管理器
        
        Args:
            session_path: 会话文件路径
        """
        self.session_path = session_path
        self.session_data: Optional[Dict[str, Any]] = None
    
    def save_session(self, storage_state: Dict[str, Any]) -> bool:
        """
        保存会话状态到文件
        
        Args:
            storage_state: Playwright的storage_state数据
            
        Returns:
            bool: 保存是否成功
        """
        try:
            # 添加保存时间戳
            session_data = {
                'storage_state': storage_state,
                'saved_at': datetime.now().isoformat(),
                'version': '1.0'
            }
            
            # 确保目录存在
            self.session_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存到文件
            with open(self.session_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            self.session_data = session_data
            logger.info(f"会话已保存到: {self.session_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存会话失败: {e}")
            return False
    
    def load_session(self) -> Optional[Dict[str, Any]]:
        """
        从文件加载会话状态
        
        Returns:
            Optional[Dict]: 会话数据，如果加载失败返回None
        """
        try:
            if not self.session_path.exists():
                logger.warning(f"会话文件不存在: {self.session_path}")
                return None
            
            with open(self.session_path, 'r', encoding='utf-8') as f:
                self.session_data = json.load(f)
            
            # 提取storage_state
            storage_state = self.session_data.get('storage_state')
            if not storage_state:
                logger.error("会话文件中缺少storage_state数据")
                return None
            
            logger.info(f"会话已加载: {self.session_path}")
            return storage_state
            
        except Exception as e:
            logger.error(f"加载会话失败: {e}")
            return None
    
    def is_session_valid(self, max_age_hours: int = 24) -> bool:
        """
        检查会话是否有效
        
        Args:
            max_age_hours: 会话最大有效期（小时），默认24小时
            
        Returns:
            bool: 会话是否有效
        """
        if not self.session_path.exists():
            return False
        
        try:
            # 加载会话数据
            if not self.session_data:
                self.load_session()
            
            if not self.session_data:
                return False
            
            # 检查保存时间
            saved_at_str = self.session_data.get('saved_at')
            if not saved_at_str:
                logger.warning("会话文件中缺少保存时间戳")
                return False
            
            saved_at = datetime.fromisoformat(saved_at_str)
            age = datetime.now() - saved_at
            
            if age > timedelta(hours=max_age_hours):
                logger.warning(f"会话已过期（超过{max_age_hours}小时），保存时间: {saved_at}, 已过期: {age}")
                return False
            
            # 检查是否有cookies
            storage_state = self.session_data.get('storage_state', {})
            cookies = storage_state.get('cookies', [])
            
            if not cookies:
                logger.warning("会话中没有cookies")
                return False
            
            logger.info(f"会话有效，保存时间: {saved_at}, 已使用: {age}")
            return True
            
        except Exception as e:
            logger.error(f"验证会话失败: {e}")
            return False
    
    def get_storage_state(self, max_age_hours: int = 24) -> Optional[Dict[str, Any]]:
        """
        获取Playwright的storage_state格式数据（会自动清理大型localStorage数据）
        
        Args:
            max_age_hours: 会话最大有效期（小时），默认24小时
            
        Returns:
            Optional[Dict]: 清理后的storage_state数据，如果会话无效或过期返回None
        """
        # 先检查会话是否有效（包括时间检查）
        if not self.is_session_valid(max_age_hours=max_age_hours):
            logger.warning(f"会话无效或已过期（超过{max_age_hours}小时），返回None")
            return None
        
        # 如果会话有效，返回storage_state
        if not self.session_data:
            self.load_session()
        
        if not self.session_data:
            return None
        
        storage_state = self.session_data.get('storage_state')
        if storage_state:
            # 自动清理大型localStorage数据，避免打印到终端
            storage_state = self.clean_storage_state(storage_state)
        
        return storage_state
    
    def clean_storage_state(self, storage_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        清理 storage_state 中的大型 localStorage 数据，避免在加载时打印到终端
        
        Args:
            storage_state: 原始的 storage_state 数据
            
        Returns:
            Dict[str, Any]: 清理后的 storage_state 数据（只保留 cookies，移除 localStorage）
        """
        if not storage_state:
            return storage_state
        
        # 创建 storage_state 的副本，只保留 cookies，完全移除 localStorage 和 sessionStorage
        # 这样可以避免打印大量 JavaScript 代码到终端
        cleaned_state = {
            'cookies': storage_state.get('cookies', [])
        }
        
        # 不再保留 origins（包含 localStorage 和 sessionStorage）
        # 因为 localStorage 中可能包含大量 JavaScript 代码，会导致终端输出混乱
        # cookies 已经足够维持登录状态
        
        return cleaned_state
    
    def delete_session(self) -> bool:
        """
        删除会话文件
        
        Returns:
            bool: 删除是否成功
        """
        try:
            if self.session_path.exists():
                self.session_path.unlink()
                logger.info(f"会话文件已删除: {self.session_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除会话文件失败: {e}")
            return False

