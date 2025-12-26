"""
签到任务服务层
提供签到任务的 CRUD 操作和执行功能
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

from backend.core.config import get_settings

settings = get_settings()


class SignTaskService:
    """签到任务服务类"""

    def __init__(self):
        self.workdir = Path(settings.data_dir) / ".signer"
        self.signs_dir = self.workdir / "signs"
        self.signs_dir.mkdir(parents=True, exist_ok=True)
        print(f"DEBUG: 初始化 SignTaskService, signs_dir={self.signs_dir}, exists={self.signs_dir.exists()}")

    def list_tasks(self, account_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取所有签到任务列表
        
        Args:
            account_name: 可选，按账号名筛选任务
        """
        tasks = []
        
        print(f"DEBUG: 开始扫描任务目录: {self.signs_dir}, account_name={account_name}")
        try:
            # 扫描 signs 目录
            for task_dir in self.signs_dir.iterdir():
                print(f"DEBUG: 发现路径: {task_dir}, is_dir={task_dir.is_dir()}")
                if not task_dir.is_dir():
                    continue
                
                config_file = task_dir / "config.json"
                if not config_file.exists():
                    print(f"DEBUG: 配置文件不存在: {config_file}")
                    continue
                
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    
                    # 如果指定了账号，只返回该账号的任务
                    task_account = config.get("account_name", "")
                    if account_name and task_account != account_name:
                        continue
                    
                    # 基本信息
                    task_info = {
                        "name": task_dir.name,
                        "account_name": task_account,
                        "sign_at": config.get("sign_at", ""),
                        "random_seconds": config.get("random_seconds", 0),
                        "sign_interval": config.get("sign_interval", 1),
                        "chats": config.get("chats", []),
                        "enabled": True,  # 默认启用
                    }
                    
                    tasks.append(task_info)
                    print(f"DEBUG: 成功加载任务: {task_dir.name}")
                except Exception as e:
                    import traceback
                    print(f"加载任务 {task_dir.name} 失败: {str(e)}")
                    traceback.print_exc()
                    # 跳过无效的配置
                    continue
        except Exception as e:
            print(f"DEBUG: 扫描目录出错: {str(e)}")
            import traceback
            traceback.print_exc()
        
        print(f"DEBUG: 扫描结束，共找到 {len(tasks)} 个任务")
        if len(tasks) > 0:
            print(f"DEBUG: 任务数据示例: {tasks[0]}")
        return sorted(tasks, key=lambda x: x["name"])

    def get_task(self, task_name: str) -> Optional[Dict[str, Any]]:
        """
        获取单个任务的详细信息
        
        Args:
            task_name: 任务名称
            
        Returns:
            任务信息，如果不存在返回 None
        """
        task_dir = self.signs_dir / task_name
        config_file = task_dir / "config.json"
        
        if not config_file.exists():
            return None
        
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            return {
                "name": task_name,
                "account_name": config.get("account_name", ""),
                "sign_at": config.get("sign_at", ""),
                "random_seconds": config.get("random_seconds", 0),
                "sign_interval": config.get("sign_interval", 1),
                "chats": config.get("chats", []),
                "enabled": True,
            }
        except Exception:
            return None

    def create_task(
        self,
        task_name: str,
        sign_at: str,
        chats: List[Dict[str, Any]],
        random_seconds: int = 0,
        sign_interval: Optional[int] = None,
        account_name: str = "",
    ) -> Dict[str, Any]:
        """
        创建新的签到任务
        
        Args:
            sign_interval: 签到间隔，None 表示使用全局配置或随机 1-120 秒
        """
        import random
        from backend.services.config import config_service
        
        task_dir = self.signs_dir / task_name
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # 获取 sign_interval
        if sign_interval is None:
            global_settings = config_service.get_global_settings()
            sign_interval = global_settings.get("sign_interval")
        
        # 如果仍然是 None，使用随机值 1-120
        if sign_interval is None:
            sign_interval = random.randint(1, 120)
        
        config = {
            "_version": 3,
            "account_name": account_name,
            "sign_at": sign_at,
            "random_seconds": random_seconds,
            "sign_interval": sign_interval,
            "chats": chats,
        }
        
        config_file = task_dir / "config.json"
        
        print(f"DEBUG: 正在创建任务, file={config_file}, account={account_name}, sign_interval={sign_interval}")
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            print(f"DEBUG: 任务配置文件写如成功")
        except Exception as e:
            print(f"DEBUG: 写入配置文件失败: {str(e)}")
            raise
        
        return {
            "name": task_name,
            "account_name": account_name,
            "sign_at": sign_at,
            "random_seconds": random_seconds,
            "sign_interval": sign_interval,
            "chats": chats,
            "enabled": True,
        }

    def update_task(
        self,
        task_name: str,
        sign_at: Optional[str] = None,
        chats: Optional[List[Dict[str, Any]]] = None,
        random_seconds: Optional[int] = None,
        sign_interval: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        更新签到任务
        
        Args:
            task_name: 任务名称
            sign_at: 签到时间（可选）
            chats: Chat 配置列表（可选）
            random_seconds: 随机延迟秒数（可选）
            sign_interval: 签到间隔秒数（可选）
            
        Returns:
            更新后的任务信息
        """
        # 获取现有配置
        existing = self.get_task(task_name)
        if not existing:
            raise ValueError(f"任务 {task_name} 不存在")
        
        # 更新配置
        config = {
            "_version": 3,
            "sign_at": sign_at if sign_at is not None else existing["sign_at"],
            "random_seconds": random_seconds if random_seconds is not None else existing["random_seconds"],
            "sign_interval": sign_interval if sign_interval is not None else existing["sign_interval"],
            "chats": chats if chats is not None else existing["chats"],
        }
        
        # 保存配置
        task_dir = self.signs_dir / task_name
        config_file = task_dir / "config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        return {
            "name": task_name,
            "sign_at": config["sign_at"],
            "random_seconds": config["random_seconds"],
            "sign_interval": config["sign_interval"],
            "chats": config["chats"],
            "enabled": True,
        }

    def delete_task(self, task_name: str) -> bool:
        """
        删除签到任务
        
        Args:
            task_name: 任务名称
            
        Returns:
            是否成功删除
        """
        task_dir = self.signs_dir / task_name
        
        if not task_dir.exists():
            return False
        
        try:
            # 删除配置文件
            config_file = task_dir / "config.json"
            if config_file.exists():
                config_file.unlink()
            
            # 删除目录
            task_dir.rmdir()
            return True
        except Exception:
            return False

    def get_account_chats(self, account_name: str) -> List[Dict[str, Any]]:
        """
        获取账号的 Chat 列表
        
        Args:
            account_name: 账号名称
            
        Returns:
            Chat 列表
        """
        # 从用户目录读取 latest_chats.json
        users_dir = self.workdir / "users"
        
        chats = []
        for user_dir in users_dir.iterdir():
            if not user_dir.is_dir():
                continue
            
            chats_file = user_dir / "latest_chats.json"
            if not chats_file.exists():
                continue
            
            try:
                with open(chats_file, "r", encoding="utf-8") as f:
                    user_chats = json.load(f)
                    chats.extend(user_chats)
            except Exception:
                continue
        
        return chats

    def run_task(self, account_name: str, task_name: str) -> Dict[str, Any]:
        """
        运行签到任务
        
        Args:
            account_name: 账号名称
            task_name: 任务名称
            
        Returns:
            执行结果
        """
        # 调用 CLI 命令执行任务
        import subprocess
        
        # 构建命令: tg-signer --workdir <workdir> --session_dir <session_dir> --account <account> run-once <task>
        session_dir = str(Path(settings.data_dir) / "sessions")
        
        cmd = [
            "tg-signer",
            "--workdir", str(self.workdir),
            "--session_dir", session_dir,
            "--account", account_name,
            "run-once",  # 使用 run-once 来运行一次
            task_name,
        ]
        
        print(f"DEBUG: 执行命令: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 分钟超时
            )
            
            # 打印 CLI 执行结果，用于调试
            print(f"DEBUG: CLI 返回码: {result.returncode}")
            if result.stdout:
                print(f"DEBUG: CLI stdout:\n{result.stdout}")
            if result.stderr:
                print(f"DEBUG: CLI stderr:\n{result.stderr}")
            
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": "任务执行超时（超过 5 分钟）",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
            }


# 创建全局实例
sign_task_service = SignTaskService()
