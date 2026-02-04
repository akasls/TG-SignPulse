"use client";

import { useTheme } from "../context/ThemeContext";
import { useLanguage } from "../context/LanguageContext";
import { Translate, Sun, Moon } from "@phosphor-icons/react";

export function ThemeLanguageToggle() {
    const { theme, toggleTheme } = useTheme();
    const { language, setLanguage, t } = useLanguage();

    return (
        <div className="flex items-center gap-4">
            {/* 语言切换 */}
            <button
                onClick={() => setLanguage(language === 'zh' ? 'en' : 'zh')}
                className="action-btn"
                title={language === 'zh' ? t("switch_to_english") : t("switch_to_chinese")}
            >
                <Translate weight="bold" />
            </button>

            {/* 主题切换 */}
            <button
                onClick={toggleTheme}
                className="action-btn"
                title={theme === 'dark' ? t("switch_to_light") : t("switch_to_dark")}
            >
                {theme === 'dark' ? <Sun weight="bold" /> : <Moon weight="bold" />}
            </button>
        </div>
    );
}
