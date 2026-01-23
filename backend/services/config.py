"""
配置管理服务
提供任务配置的导入导出功能
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import get_settings

settings = get_settings()


class ConfigService:
    """配置管理服务类"""

    def __init__(self):
        self.workdir = settings.resolve_workdir()
        self.signs_dir = self.workdir / "signs"
        self.monitors_dir = self.workdir / "monitors"

        # 确保目录存在
        self.signs_dir.mkdir(parents=True, exist_ok=True)
        self.monitors_dir.mkdir(parents=True, exist_ok=True)

    def list_sign_tasks(self) -> List[str]:
        """获取所有签到任务名称列表"""
        tasks = []

        if self.signs_dir.exists():
            for task_dir in self.signs_dir.iterdir():
                if task_dir.is_dir():
                    config_file = task_dir / "config.json"
                    if config_file.exists():
                        tasks.append(task_dir.name)

        return sorted(tasks)

    def list_monitor_tasks(self) -> List[str]:
        """获取所有监控任务名称列表"""
        tasks = []

        if self.monitors_dir.exists():
            for task_dir in self.monitors_dir.iterdir():
                if task_dir.is_dir():
                    config_file = task_dir / "config.json"
                    if config_file.exists():
                        tasks.append(task_dir.name)

        return sorted(tasks)

    def get_sign_config(self, task_name: str) -> Optional[Dict]:
        """
        获取签到任务配置

        Args:
            task_name: 任务名称

        Returns:
            配置字典，如果不存在则返回 None
        """
        config_file = self.signs_dir / task_name / "config.json"

        if not config_file.exists():
            return None

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def save_sign_config(self, task_name: str, config: Dict) -> bool:
        """
        保存签到任务配置

        Args:
            task_name: 任务名称
            config: 配置字典

        Returns:
            是否成功保存
        """
        task_dir = self.signs_dir / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        config_file = task_dir / "config.json"

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    def delete_sign_config(self, task_name: str) -> bool:
        """
        删除签到任务配置

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

            # 删除签到记录文件
            record_file = task_dir / "sign_record.json"
            if record_file.exists():
                record_file.unlink()

            # 删除目录
            task_dir.rmdir()
            return True
        except OSError:
            return False

    def export_sign_task(self, task_name: str) -> Optional[str]:
        """
        导出签到任务配置为 JSON 字符串

        Args:
            task_name: 任务名称

        Returns:
            JSON 字符串，如果任务不存在则返回 None
        """
        config = self.get_sign_config(task_name)

        if config is None:
            return None

        # 添加元数据
        export_data = {
            "task_name": task_name,
            "task_type": "sign",
            "config": config,
        }

        return json.dumps(export_data, ensure_ascii=False, indent=2)

    def import_sign_task(self, json_str: str, task_name: Optional[str] = None) -> bool:
        """
        导入签到任务配置

        Args:
            json_str: JSON 字符串
            task_name: 新任务名称（可选，如果不提供则使用原名称）

        Returns:
            是否成功导入
        """
        try:
            data = json.loads(json_str)

            # 验证数据格式
            if "config" not in data:
                return False

            # 确定任务名称
            final_task_name = task_name or data.get("task_name", "imported_task")

            # 保存配置
            return self.save_sign_config(final_task_name, data["config"])

        except (json.JSONDecodeError, KeyError):
            return False

    def export_all_configs(self) -> str:
        """
        导出所有配置

        Returns:
            包含所有配置的 JSON 字符串
        """
        all_configs = {
            "signs": {},
            "monitors": {},
        }

        # 导出所有签到任务
        for task_name in self.list_sign_tasks():
            config = self.get_sign_config(task_name)
            if config:
                all_configs["signs"][task_name] = config

        # 导出所有监控任务
        for task_name in self.list_monitor_tasks():
            config_file = self.monitors_dir / task_name / "config.json"
            if config_file.exists():
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        all_configs["monitors"][task_name] = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass

        return json.dumps(all_configs, ensure_ascii=False, indent=2)

    def import_all_configs(
        self, json_str: str, overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        导入所有配置

        Args:
            json_str: JSON 字符串
            overwrite: 是否覆盖已存在的配置

        Returns:
            导入结果统计
        """
        result = {
            "signs_imported": 0,
            "signs_skipped": 0,
            "monitors_imported": 0,
            "monitors_skipped": 0,
            "errors": [],
        }

        try:
            data = json.loads(json_str)

            # 导入签到任务
            for task_name, config in data.get("signs", {}).items():
                if not overwrite and self.get_sign_config(task_name):
                    result["signs_skipped"] += 1
                    continue

                if self.save_sign_config(task_name, config):
                    result["signs_imported"] += 1
                else:
                    result["errors"].append(f"Failed to import sign task: {task_name}")

            # 导入监控任务
            for task_name, config in data.get("monitors", {}).items():
                task_dir = self.monitors_dir / task_name
                config_file = task_dir / "config.json"

                if not overwrite and config_file.exists():
                    result["monitors_skipped"] += 1
                    continue

                task_dir.mkdir(parents=True, exist_ok=True)
                try:
                    with open(config_file, "w", encoding="utf-8") as f:
                        json.dump(config, f, ensure_ascii=False, indent=2)
                    result["monitors_imported"] += 1
                except OSError:
                    result["errors"].append(
                        f"Failed to import monitor task: {task_name}"
                    )

        except (json.JSONDecodeError, KeyError) as e:
            result["errors"].append(f"Invalid JSON format: {str(e)}")

        return result

    # ============ AI 配置 ============

    def _get_ai_config_file(self) -> Path:
        """获取 AI 配置文件路径"""
        return self.workdir / ".openai_config.json"

    def get_ai_config(self) -> Optional[Dict]:
        """
        获取 AI 配置

        Returns:
            配置字典，如果不存在则返回 None
        """
        config_file = self._get_ai_config_file()

        if not config_file.exists():
            return None

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def save_ai_config(
        self, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None
    ) -> bool:
        """
        保存 AI 配置

        Args:
            api_key: OpenAI API Key
            base_url: API Base URL（可选）
            model: 模型名称（可选）

        Returns:
            是否成功保存
        """
        config = {
            "api_key": api_key,
        }

        if base_url:
            config["base_url"] = base_url
        if model:
            config["model"] = model

        config_file = self._get_ai_config_file()

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    def delete_ai_config(self) -> bool:
        """
        删除 AI 配置

        Returns:
            是否成功删除
        """
        config_file = self._get_ai_config_file()

        if not config_file.exists():
            return True

        try:
            config_file.unlink()
            return True
        except OSError:
            return False

    async def test_ai_connection(self) -> Dict:
        """
        测试 AI 连接

        Returns:
            测试结果
        """
        config = self.get_ai_config()

        if not config:
            return {"success": False, "message": "未配置 AI API Key"}

        api_key = config.get("api_key")
        base_url = config.get("base_url")
        model = config.get("model", "gpt-4o")

        if not api_key:
            return {"success": False, "message": "API Key 为空"}

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, base_url=base_url)

            # 发送一个简单的测试请求
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Say 'test ok' in 2 words"}],
                max_tokens=10,
            )

            return {
                "success": True,
                "message": f"连接成功！模型响应: {response.choices[0].message.content}",
                "model_used": model,
            }

        except ImportError:
            return {
                "success": False,
                "message": "未安装 openai 库，请运行: pip install openai",
            }
        except Exception as e:
            return {"success": False, "message": f"连接失败: {str(e)}"}

    # ============ 全局设置 ============

    def _get_global_settings_file(self) -> Path:
        """获取全局设置文件路径"""
        return self.workdir / ".global_settings.json"

    def get_global_settings(self) -> Dict:
        """
        获取全局设置

        Returns:
            设置字典
        """
        config_file = self._get_global_settings_file()

        default_settings = {
            "sign_interval": None,  # None 表示使用随机 1-120 秒
        }

        if not config_file.exists():
            return default_settings

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
                # 合并默认设置
                for key, value in default_settings.items():
                    if key not in settings:
                        settings[key] = value
                return settings
        except (json.JSONDecodeError, OSError):
            return default_settings

    def save_global_settings(self, settings: Dict) -> bool:
        """
        保存全局设置

        Args:
            settings: 设置字典

        Returns:
            是否成功保存
        """
        config_file = self._get_global_settings_file()

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    # ============ Telegram API 配置 ============

    # 默认的 Telegram API 凭证
    DEFAULT_TG_API_ID = "611335"
    DEFAULT_TG_API_HASH = "d524b414d21f4d37f08684c1df41ac9c"

    def _get_telegram_config_file(self) -> Path:
        """获取 Telegram API 配置文件路径"""
        return self.workdir / ".telegram_api.json"

    def get_telegram_config(self) -> Dict:
        """
        获取 Telegram API 配置

        Returns:
            配置字典，包含 api_id, api_hash, is_custom (是否为自定义配置)
        """
        config_file = self._get_telegram_config_file()

        # 默认配置
        default_config = {
            "api_id": self.DEFAULT_TG_API_ID,
            "api_hash": self.DEFAULT_TG_API_HASH,
            "is_custom": False,
        }

        if not config_file.exists():
            return default_config

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                # 如果有自定义配置，标记为自定义
                if config.get("api_id") and config.get("api_hash"):
                    config["is_custom"] = True
                    return config
                else:
                    return default_config
        except (json.JSONDecodeError, OSError):
            return default_config

    def save_telegram_config(self, api_id: str, api_hash: str) -> bool:
        """
        保存 Telegram API 配置

        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash

        Returns:
            是否成功保存
        """
        config = {
            "api_id": api_id,
            "api_hash": api_hash,
        }

        config_file = self._get_telegram_config_file()

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    def reset_telegram_config(self) -> bool:
        """
        重置 Telegram API 配置（恢复默认）

        Returns:
            是否成功重置
        """
        config_file = self._get_telegram_config_file()

        if not config_file.exists():
            return True

        try:
            config_file.unlink()
            return True
        except OSError:
            return False


# 创建全局实例
config_service = ConfigService()
