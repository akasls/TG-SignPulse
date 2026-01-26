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
            # 扫描顶层目录 (兼容旧版)
            for path in self.signs_dir.iterdir():
                if path.is_dir():
                    # Check if it's a task directory (has config.json)
                    if (path / "config.json").exists():
                        tasks.append(path.name)
                    else:
                        # Check if it's an account directory containing tasks
                        for task_dir in path.iterdir():
                            if task_dir.is_dir() and (task_dir / "config.json").exists():
                                tasks.append(task_dir.name)

        return sorted(list(set(tasks)))  # 去重并排序

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

    def _find_sign_task_dirs(self, task_name: str) -> List[Path]:
        matches = []
        if not self.signs_dir.exists():
            return matches

        # 1. 旧版结构: signs/task
        direct_dir = self.signs_dir / task_name
        if (direct_dir / "config.json").exists():
            matches.append(direct_dir)

        # 2. 新版结构: signs/account/task
        for acc_dir in self.signs_dir.iterdir():
            if acc_dir.is_dir():
                nested_task_dir = acc_dir / task_name
                if (nested_task_dir / "config.json").exists():
                    matches.append(nested_task_dir)

        return matches

    def get_sign_config(
        self, task_name: str, account_name: Optional[str] = None
    ) -> Optional[Dict]:
        """
        获取签到任务配置

        Args:
            task_name: 任务名称
            account_name: 账号名称（可选）

        Returns:
            配置字典，如果不存在则返回 None
        """
        if account_name:
            task_dir = self.signs_dir / account_name / task_name
            config_file = task_dir / "config.json"
            if not config_file.exists():
                return None
        else:
            matches = self._find_sign_task_dirs(task_name)
            if not matches:
                return None
            if len(matches) > 1:
                raise ValueError(f"任务 {task_name} 存在于多个账号中，请指定 account_name")
            task_dir = matches[0]
            config_file = task_dir / "config.json"

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
        account_name = config.get("account_name", "")
        
        if account_name:
            # 使用新版结构: signs/account/task
            task_dir = self.signs_dir / account_name / task_name
        else:
            # 兼容旧版或无账号: signs/task
            task_dir = self.signs_dir / task_name

        task_dir.mkdir(parents=True, exist_ok=True)
        config_file = task_dir / "config.json"

        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    def delete_sign_config(
        self, task_name: str, account_name: Optional[str] = None
    ) -> bool:
        """
        删除签到任务配置

        Args:
            task_name: 任务名称
            account_name: 账号名称（可选）

        Returns:
            是否成功删除
        """
        if account_name:
            task_dir = self.signs_dir / account_name / task_name
            if not task_dir.exists():
                return False
        else:
            matches = self._find_sign_task_dirs(task_name)
            if not matches:
                return False
            if len(matches) > 1:
                raise ValueError(f"任务 {task_name} 存在于多个账号中，请指定 account_name")
            task_dir = matches[0]

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
            # 注意：如果是嵌套结构，这里只删除了任务目录，没有删除可能变空的账号目录
            # 这通常是可以接受的，或者我们可以检查父目录是否为空并删除
            import shutil
            shutil.rmtree(task_dir)
            
            return True
        except OSError:
            return False

    def export_sign_task(
        self, task_name: str, account_name: Optional[str] = None
    ) -> Optional[str]:
        """
        导出签到任务配置为 JSON 字符串

        Args:
            task_name: 任务名称
            account_name: 账号名称（可选）

        Returns:
            JSON 字符串，如果任务不存在则返回 None
        """
        config = self.get_sign_config(task_name, account_name=account_name)

        if config is None:
            return None

        config = dict(config)
        config.pop("last_run", None)

        # 添加元数据
        export_data = {
            "task_name": task_name,
            "task_type": "sign",
            "config": config,
        }

        return json.dumps(export_data, ensure_ascii=False, indent=2)

    def import_sign_task(
        self,
        json_str: str,
        task_name: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> bool:
        """
        导入签到任务配置

        Args:
            json_str: JSON 字符串
            task_name: 新任务名称（可选，如果不提供则使用原名称）
            account_name: 新账号名称（可选，如果不提供则使用原名称）

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

            config = data["config"]
            if account_name:
                config["account_name"] = account_name

            # 保存配置
            return self.save_sign_config(final_task_name, config)

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
            "settings": {}, # 新增 settings 字段
        }

        # 导出所有签到任务
        if self.signs_dir.exists():
            # 1. 扫描顶层 (旧版)
            for path in self.signs_dir.iterdir():
                if path.is_dir() and (path / "config.json").exists():
                    try:
                        with open(path / "config.json", "r", encoding="utf-8") as f:
                            config = json.load(f)
                            config.pop("last_run", None)
                            key = path.name
                            if key in all_configs["signs"]:
                                key = f"{key}_{config.get('account_name', 'default')}"
                            all_configs["signs"][key] = config
                    except Exception:
                        pass
                
                # 2. 扫描账号层
                if path.is_dir():
                    for task_dir in path.iterdir():
                        if task_dir.is_dir() and (task_dir / "config.json").exists():
                            try:
                                with open(task_dir / "config.json", "r", encoding="utf-8") as f:
                                    config = json.load(f)
                                    config.pop("last_run", None)
                                    key = f"{task_dir.name}_{path.name}"
                                    account_name = config.get("account_name")
                                    if account_name:
                                        key = f"{config.get('name', task_dir.name)}@{account_name}"
                                    else:
                                        key = config.get("name", task_dir.name)

                                    if key in all_configs["signs"]:
                                        import uuid
                                        key = f"{key}_{str(uuid.uuid4())[:8]}"

                                    all_configs["signs"][key] = config
                            except Exception:
                                pass

        # 导出所有监控任务
        for task_name in self.list_monitor_tasks():
            config_file = self.monitors_dir / task_name / "config.json"
            if config_file.exists():
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                        config.pop("last_run", None)
                        all_configs["monitors"][task_name] = config
                except (json.JSONDecodeError, OSError):
                    pass
        
        # 导出设置 (新增)
        all_configs["settings"] = {
            "global": self.get_global_settings(),
            "ai": self.get_ai_config(),
            "telegram": self.get_telegram_config(),
        }

        return json.dumps(all_configs, ensure_ascii=False, indent=2)

    def import_all_configs(
        self, json_str: str, overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        导入所有配置
        """
        result = {
            "signs_imported": 0,
            "signs_skipped": 0,
            "monitors_imported": 0,
            "monitors_skipped": 0,
            "settings_imported": 0,
            "errors": [],
        }

        try:
            data = json.loads(json_str)

            # 导入签到任务
            for key, config in data.get("signs", {}).items():
                task_name = config.get("name")
                if not task_name:
                    task_name = key.split("@")[0]

                if not overwrite:
                    account_name = config.get("account_name")
                    exists = False
                    if account_name:
                        if (self.signs_dir / account_name / task_name).exists():
                            exists = True
                    else:
                        if (self.signs_dir / task_name).exists():
                            exists = True

                    if exists:
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
            
            # 导入设置 (新增)
            settings_data = data.get("settings", {})
            
            # 导入全局设置
            if "global" in settings_data:
                try:
                    self.save_global_settings(settings_data["global"])
                    result["settings_imported"] += 1
                except Exception as e:
                    result["errors"].append(f"Failed to import global settings: {e}")
            
            # 导入 AI 配置
            if "ai" in settings_data and settings_data["ai"]:
                try:
                    ai_conf = settings_data["ai"]
                    # 注意：如果 masking 处理过 api_key (e.g. ****)，这里需要处理吗？
                    # 当前 export_ai_config 直接读取文件，应该包含完整 key（文件里是明文）。前端展示才 mask。
                    # 所以这里导出的是完整 key，可以直接导入。
                    if ai_conf.get("api_key"):
                        self.save_ai_config(ai_conf["api_key"], ai_conf.get("base_url"), ai_conf.get("model"))
                        result["settings_imported"] += 1
                except Exception as e:
                    result["errors"].append(f"Failed to import AI config: {e}")

            # 导入 Telegram 配置
            if "telegram" in settings_data:
                try:
                    tg_conf = settings_data["telegram"]
                    if tg_conf.get("is_custom") and tg_conf.get("api_id") and tg_conf.get("api_hash"):
                         self.save_telegram_config(str(tg_conf["api_id"]), tg_conf["api_hash"])
                         result["settings_imported"] += 1
                except Exception as e:
                    result["errors"].append(f"Failed to import Telegram config: {e}")

            # 关键修复：清除 SignTaskService 缓存，否则前端刷新也看不到新任务
            try:
                from backend.services.sign_tasks import sign_task_service
                sign_task_service._tasks_cache = None
                
                # 可选：触发调度同步？
                # 如果导入了新任务，调度器并不知道。
                # 只有 _tasks_cache 清除后，下次调用 list_tasks 才会读文件，但调度器是内存常驻的。
                # 我们应该调用 sync_jobs!
                
                # 由于 sync_jobs 是 async 的，而这里是同步方法，可能不太好直接调。
                # 但 FastAPI 路由是 async 的，我们可以在路由层调用 sync_jobs。
                # 这里的职责主要是文件操作。清理 cache 是必须的。
                pass
            except Exception as e:
                 print(f"Failed to clear cache: {e}")

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
