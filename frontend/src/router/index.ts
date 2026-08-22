import { createRouter, createWebHistory } from 'vue-router'
import Layout from '../views/Layout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: Layout,
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', name: 'dashboard', component: () => import('../views/Dashboard.vue') },
        { path: 'accounts', name: 'accounts', component: () => import('../views/Accounts.vue') },
        { path: 'tasks', name: 'tasks', component: () => import('../views/Tasks.vue') },
        { path: 'logs', name: 'logs', component: () => import('../views/Logs.vue') },
        { path: 'settings', name: 'settings', component: () => import('../views/Settings.vue') }
      ]
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/Login.vue')
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../views/NotFound.vue')
    }
  ]
})

router.beforeEach((to) => {
  const token = localStorage.getItem('tg-signer-token')
  let isValidToken = false
  if (token) {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      if (!payload.exp || payload.exp * 1000 >= Date.now()) {
        isValidToken = true
      } else {
        localStorage.removeItem('tg-signer-token')
      }
    } catch {
      localStorage.removeItem('tg-signer-token')
    }
  }

  if (to.name === 'login') {
    if (isValidToken) {
      return { name: 'dashboard' }
    }
    return
  }

  if (to.name === 'not-found') {
    return
  }

  if (!isValidToken) {
    return { name: 'login' }
  }
})

export default router
