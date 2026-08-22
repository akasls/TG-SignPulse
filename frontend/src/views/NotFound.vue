<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { FileQuestion, ArrowLeft, Github, Globe, Moon, Sun } from 'lucide-vue-next'
import { useI18n } from '../composables/useI18n'
import { useTheme } from '../composables/useTheme'

const router = useRouter()
const { locale, toggleLanguage, t } = useI18n()
const { isDark, toggleTheme } = useTheme()

const isAuthed = computed(() => {
  const token = localStorage.getItem('tg-signer-token')
  if (!token) return false
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return !payload.exp || payload.exp * 1000 >= Date.now()
  } catch {
    return false
  }
})

const handleRedirect = () => {
  if (isAuthed.value) {
    router.push('/dashboard')
  } else {
    router.push('/login')
  }
}

const openGithub = () => {
  window.open('https://github.com/akasls/TG-SignPulse', '_blank')
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-950 flex flex-col items-center justify-center font-sans px-4">
    <div class="w-full max-w-md p-8 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800/60 text-center shadow-sm">
      <div class="w-14 h-14 bg-gray-100 dark:bg-gray-800 mx-auto flex items-center justify-center text-gray-700 dark:text-gray-200 mb-6 rounded-full">
        <FileQuestion class="w-8 h-8 stroke-[1.5]" />
      </div>

      <div class="text-5xl font-mono font-bold text-gray-900 dark:text-gray-100 tracking-wider mb-2">404</div>
      <h1 class="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">{{ t('notFound.title') }}</h1>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-8 leading-relaxed">{{ t('notFound.desc') }}</p>

      <button
        @click="handleRedirect"
        class="w-full inline-flex items-center justify-center gap-2 bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-950 py-2.5 px-4 font-medium hover:bg-gray-800 dark:hover:bg-white transition-colors"
      >
        <ArrowLeft class="w-4 h-4" />
        <span>{{ isAuthed ? t('notFound.backHome') : t('notFound.goToLogin') }}</span>
      </button>

      <!-- Footer icons -->
      <div class="flex items-center justify-center gap-3 mt-8 pt-6 border-t border-gray-200 dark:border-gray-800/60">
        <button @click="openGithub" class="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors rounded" title="GitHub">
          <Github class="w-4 h-4" />
        </button>
        <button @click="toggleLanguage" class="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors rounded" :title="locale === 'zh' ? 'English' : '中文'">
          <Globe class="w-4 h-4" />
        </button>
        <button @click="toggleTheme" class="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors rounded" :title="isDark ? t('common.lightMode') : t('common.darkMode')">
          <Moon v-if="!isDark" class="w-4 h-4" />
          <Sun v-else class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>
