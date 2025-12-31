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
        "settings_title": "系统设置",
        "logout": "退出登录"
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
        "settings_title": "System Settings",
        "logout": "Logout"
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
