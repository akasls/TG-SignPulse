"use client";

import React, { createContext, useContext, useEffect, useState } from 'react';

type Language = 'zh' | 'en';

type Translations = {
    [key in Language]: {
        [key: string]: string;
    };
};

const translations: Translations = {
    zh: {
        "login": "登录",
        "username": "用户名",
        "password": "密码",
        "totp": "两步验证码 (可选)",
        "login_loading": "登录中...",
        "login_success": "登录成功",
        "login_failed": "登录失败",
        "user_or_pass_error": "用户名或密码错误",
        "totp_error": "两步验证码错误或已过期",
        "auth_failed": "认证失败，请重新登录",
        "sidebar_home": "首页",
        "sidebar_accounts": "账号管理",
        "sidebar_settings": "详情设置",
        "sidebar_tasks": "任务列表",
        "add_account": "添加账号",
        "add_task": "新增任务",
        "edit": "编辑",
        "run": "运行",
        "delete": "删除",
        "confirm_delete": "确定要删除吗？",
        "save": "保存",
        "cancel": "取消",
        "settings_desc": "一个完全使用 Antigravity 开发的 Telegram 自动发送消息/签到项目",
        "settings_title": "系统设置",
        "logout": "退出登录",
        "connected": "已连接",
        "logs": "日志",
        "remove": "移除",
        "session_name": "Session 名称 (唯一标识)",
        "phone_number": "手机号码",
        "login_code": "登录验证码",
        "login_code_placeholder": "Telegram 发送的 5 位数",
        "two_step_pass": "两步验证 (Cloud Password)",
        "two_step_placeholder": "未设置请留空",
        "proxy": "SOCKS5 代理 (可选)",
        "proxy_placeholder": "ip:port:user:pass",
        "confirm_connect": "确认连接",
        "next_step": "下一步",
        "back": "返回",
        "send_code": "发送验证码",
        "safety_verify": "安全验证",
        "code_sent": "验证码已发送至您的手机/Telegram 客户端",
        "running_logs": "运行日志",
        "no_logs": "暂无运行日志",
        "close": "关闭",
        "success": "成功",
        "failure": "失败",
        "task_details": "任务详情",
        "manage_tasks_for": "管理账号的所有自动签到任务",
        "refresh_chats": "刷新 Chat 列表",
        "loading": "加载中...",
        "no_tasks": "配置第一个签到目的地",
        "no_tasks_desc": "选择一个频道或群组，设定动作与时间点",
        "create_task": "创建签到任务",
        "edit_task": "编辑任务",
        "task_name": "任务名称",
        "sign_time": "签到时间 (CRON)",
        "random_delay": "随机延迟 (分钟)",
        "action_interval": "动作间隔 (秒)",
        "select_chat": "选择频道/群组 (Chat)",
        "manual_chat_id": "或手动输入 Chat ID",
        "delete_after": "消息删除延迟 (秒, 可选)",
        "action_sequence": "有序动作序列",
        "deploy_now": "立即部署",
        "save_changes": "保存修改",
        "add_action": "添加动作",
        "change_username": "修改用户名",
        "new_username": "新用户名",
        "current_password": "当前密码",
        "change_password": "修改密码",
        "old_password": "旧密码",
        "new_password": "新密码",
        "confirm_new_password": "确认新密码",
        "2fa_settings": "两步验证 (2FA)",
        "2fa_enable_desc": "启用两步验证将显著提升您的账户安全性。启用后，登录时除了密码外，还需要输入由身份验证器生成的动态代码。",
        "start_setup": "开始设置",
        "scan_qr": "1. 扫描二维码",
        "scan_qr_desc": "使用 Google Authenticator 或其他身份验证器扫描左侧二维码",
        "backup_secret": "2. 备份密钥",
        "verify_code": "验证代码",
        "verify": "验证",
        "disable_2fa": "停用两步验证",
        "ai_config": "AI 模型配置",
        "api_key": "API 密钥",
        "base_url": "基础 URL (Base URL)",
        "model": "预设模型 (Model)",
        "test_connection": "连接测试",
        "global_settings": "全局签到设置",
        "sign_interval": "签到间隔 (秒)",
        "sign_interval_desc": "设置将应用于所有启用全局间隔的任务",
        "log_retention": "日志保留天数",
        "save_global_params": "保存全局参数",
        "tg_api_config": "Telegram API 凭据",
        "restore_default": "恢复默认配置",
        "api_id": "API ID",
        "api_hash": "API Hash",
        "apply_api_config": "应用 API 配置",
        "tg_config_warning": "修改此配置可能导致现有登录会话失效，建议仅在添加账号出现 API 兼容性问题时才进行自定义。",
        "backup_migration": "数据备份与迁移",
        "export_config": "导出全部配置",
        "export_desc": "包含所有任务定义与账号基础信息。注意：此文件包含敏感信息，请妥善保管。",
        "download_json": "下载配置文件 (.json)",
        "import_config": "导入配置内容",
        "paste_json": "在此粘贴 JSON 文本内容...",
        "overwrite_conflict": "覆盖冲突的任务",
        "execute_import": "执行导入",
        "upload_json": "上传 JSON 文件",
        "process_successful": "执行成功",
        "process_error": "执行出错",
        "warning_notice": "警告提示",
        "connect_success": "连接成功",
        "action_send_text": "发送文本",
        "action_send_dice": "发送骰子",
        "action_click_button": "点击按钮",
        "action_ai_vision": "AI 图片识别",
        "action_ai_logic": "AI 计算题",
        "placeholder_msg": "发送的消息内容...",
        "placeholder_btn": "要点击的按钮上的文字...",
        "manual_id_placeholder": "手动输入 Chat ID...",
        "delete_after_placeholder": "发送后多久自动删除指令...",
        "no_data": "暂无数据"
    },
    en: {
        "login": "Login",
        "username": "Username",
        "password": "Password",
        "totp": "TOTP Code (Optional)",
        "login_loading": "Logging in...",
        "login_success": "Login Successful",
        "login_failed": "Login Failed",
        "user_or_pass_error": "Invalid username or password",
        "totp_error": "Invalid or expired TOTP code",
        "auth_failed": "Authentication failed, please login again",
        "sidebar_home": "Home",
        "sidebar_accounts": "Accounts",
        "sidebar_settings": "Settings",
        "sidebar_tasks": "Tasks",
        "add_account": "Add Account",
        "add_task": "Add Task",
        "edit": "Edit",
        "run": "Run",
        "delete": "Delete",
        "confirm_delete": "Are you sure you want to delete?",
        "save": "Save",
        "cancel": "Cancel",
        "settings_desc": "A Telegram auto-sign/messaging project developed entirely using Antigravity",
        "settings_title": "System Settings",
        "logout": "Logout",
        "connected": "Connected",
        "logs": "Logs",
        "remove": "Remove",
        "session_name": "Session Name (Unique)",
        "phone_number": "Phone Number",
        "login_code": "Login Code",
        "login_code_placeholder": "5-digit code from Telegram",
        "two_step_pass": "2FA (Cloud Password)",
        "two_step_placeholder": "Leave blank if not set",
        "proxy": "SOCKS5 Proxy (Optional)",
        "proxy_placeholder": "ip:port:user:pass",
        "confirm_connect": "Confirm Connect",
        "next_step": "Next Step",
        "back": "Back",
        "send_code": "Send Code",
        "safety_verify": "Security Verification",
        "code_sent": "Verification code sent to your Phone/Telegram",
        "running_logs": "Running Logs",
        "no_logs": "No logs available",
        "close": "Close",
        "success": "Success",
        "failure": "Failure",
        "task_details": "Task Details",
        "manage_tasks_for": "Manage automatic sign-in tasks for account",
        "refresh_chats": "Refresh Chats",
        "loading": "Loading...",
        "no_tasks": "Configure Your First Task",
        "no_tasks_desc": "Select a channel or group, set actions and timing",
        "create_task": "Create Task",
        "edit_task": "Edit Task",
        "task_name": "Task Name",
        "sign_time": "Sign-in Time (CRON)",
        "random_delay": "Random Delay (Minutes)",
        "action_interval": "Action Interval (Seconds)",
        "select_chat": "Select Channel/Group (Chat)",
        "manual_chat_id": "Or Manual Chat ID",
        "delete_after": "Message Deletion Delay (Sec, Optional)",
        "action_sequence": "Action Sequence",
        "deploy_now": "Deploy Now",
        "save_changes": "Save Changes",
        "add_action": "Add Action",
        "change_username": "Change Username",
        "new_username": "New Username",
        "current_password": "Current Password",
        "change_password": "Change Password",
        "old_password": "Old Password",
        "new_password": "New Password",
        "confirm_new_password": "Confirm New Password",
        "2fa_settings": "Two-Factor Auth (2FA)",
        "2fa_enable_desc": "Enabling 2FA significantly improves your account security. Once enabled, you will need to enter a dynamic code generated by an authenticator app.",
        "start_setup": "Start Setup",
        "scan_qr": "1. Scan QR Code",
        "scan_qr_desc": "Scan the QR code on the left using Google Authenticator or another app",
        "backup_secret": "2. Backup Secret",
        "verify_code": "Verification Code",
        "verify": "Verify",
        "disable_2fa": "Disable 2FA",
        "ai_config": "AI Model Configuration",
        "api_key": "API Key",
        "base_url": "Base URL",
        "model": "Default Model",
        "test_connection": "Test Connection",
        "global_settings": "Global Sign-in Settings",
        "sign_interval": "Sign-in Interval (Sec)",
        "sign_interval_desc": "Applies to all tasks with global interval enabled",
        "log_retention": "Log Retention (Days)",
        "save_global_params": "Save Global Parameters",
        "tg_api_config": "Telegram API Credentials",
        "restore_default": "Restore Default",
        "api_id": "API ID",
        "api_hash": "API Hash",
        "apply_api_config": "Apply API Config",
        "tg_config_warning": "Changing this may invalidate existing sessions. Only customize if encounter API issues.",
        "backup_migration": "Backup & Migration",
        "export_config": "Export All Config",
        "export_desc": "Contains all tasks and account info. Note: Handle this file with care as it contains sensitive data.",
        "download_json": "Download Config (.json)",
        "import_config": "Import Config Content",
        "paste_json": "Paste JSON content here...",
        "overwrite_conflict": "Overwrite Conflicts",
        "execute_import": "Execute Import",
        "action_send_text": "Send Text",
        "action_send_dice": "Send Dice",
        "action_click_button": "Click Button",
        "action_ai_vision": "AI Image Recognition",
        "action_ai_logic": "AI Math Solver",
        "placeholder_msg": "Message to send...",
        "placeholder_btn": "Text on button to click...",
        "manual_id_placeholder": "Manual Chat ID...",
        "delete_after_placeholder": "Auto-delete delay after sending...",
        "no_data": "No Data"
    }
};

interface LanguageContextType {
    language: Language;
    setLanguage: (lang: Language) => void;
    t: (key: string) => string;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
    const [language, setLangState] = useState<Language>('zh');
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        const savedLang = localStorage.getItem('tg-signer-lang') as Language;
        if (savedLang) {
            setLangState(savedLang);
        }
        setMounted(true);
    }, []);

    const setLanguage = (lang: Language) => {
        setLangState(lang);
        localStorage.setItem('tg-signer-lang', lang);
    };

    const t = (key: string) => {
        return translations[language][key] || key;
    };

    if (!mounted) return null;

    return (
        <LanguageContext.Provider value={{ language, setLanguage, t }}>
            {children}
        </LanguageContext.Provider>
    );
}

export function useLanguage() {
    const context = useContext(LanguageContext);
    if (context === undefined) {
        throw new Error('useLanguage must be used within a LanguageProvider');
    }
    return context;
}
