"use client";

import { useTheme } from "../context/ThemeContext";
import { useLanguage } from "../context/LanguageContext";
import { Translate, Sun, Moon } from "@phosphor-icons/react";

export function ThemeLanguageToggle() {
    const { theme, toggleTheme } = useTheme();
    const { language, setLanguage } = useLanguage();

    return (
        <div className="flex items-center gap-4">
            {/* 语言切换 */}
            <button
                onClick={() => setLanguage(language === 'zh' ? 'en' : 'zh')}
                className="action-btn"
                title={language === 'zh' ? 'Switch to English' : '切换至中文'}
            >
                <Translate weight="bold" />
            </button>

            {/* 主题切换 */}
            <button
                onClick={toggleTheme}
                className="action-btn"
                title={theme === 'dark' ? '切换至日间模式' : '切换至夜间模式'}
            >
                {theme === 'dark' ? <Sun weight="bold" /> : <Moon weight="bold" />}
            </button>
        </div>
    );
}
