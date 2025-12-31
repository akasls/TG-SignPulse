"use client";

import { useTheme } from "../context/ThemeContext";
import { useLanguage } from "../context/LanguageContext";

export function ThemeLanguageToggle() {
    const { theme, toggleTheme } = useTheme();
    const { language, setLanguage } = useLanguage();

    return (
        <div className="flex items-center gap-2">
            {/* 语言切换 */}
            <button
                onClick={() => setLanguage(language === 'zh' ? 'en' : 'zh')}
                className="p-2.5 hover:bg-white/10 rounded-xl transition-all text-white/70 hover:text-white flex items-center gap-1 text-sm font-medium"
                title={language === 'zh' ? 'Switch to English' : '切换至中文'}
            >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
                </svg>
                <span className="hidden sm:inline">{language === 'zh' ? 'ZH' : 'EN'}</span>
            </button>

            {/* 主题切换 */}
            <button
                onClick={toggleTheme}
                className="p-2.5 hover:bg-white/10 rounded-xl transition-all text-white/70 hover:text-white"
                title={theme === 'dark' ? '切换至日间模式' : '切换至夜间模式'}
            >
                {theme === 'dark' ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                    </svg>
                ) : (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                    </svg>
                )}
            </button>
        </div>
    );
}
