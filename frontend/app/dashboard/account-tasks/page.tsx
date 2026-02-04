"use client";

import { Suspense } from "react";
import AccountTasksContent from "./AccountTasksContent";
import { useLanguage } from "../../../context/LanguageContext";

export default function AccountTasksPage() {
    const { t } = useLanguage();
    return (
        <Suspense fallback={<div className="min-h-screen flex items-center justify-center">{t("loading")}</div>}>
            <AccountTasksContent />
        </Suspense>
    );
}
