import { createRouter, createWebHistory } from 'vue-router'

import Dashboard from '@/views/Dashboard.vue'
const Script = () => import('@/views/script/index.vue')
const Scene = () => import('@/views/scene/index.vue')
const Casting = () => import('@/views/casting/index.vue')
const Crew = () => import('@/views/crew/index.vue')
const Notice = () => import('@/views/notice/index.vue')
const Location = () => import('@/views/location/index.vue')
const Prop = () => import('@/views/prop/index.vue')
const Costume = () => import('@/views/costume/index.vue')
const Makeup = () => import('@/views/makeup/index.vue')
const Equipment = () => import('@/views/equipment/index.vue')
const Shooting = () => import('@/views/shooting/index.vue')
const Footage = () => import('@/views/footage/index.vue')
const Edit = () => import('@/views/edit/index.vue')
const Vfx = () => import('@/views/vfx/index.vue')
const VfxSupplier = () => import('@/views/vfx-supplier/index.vue')
const Review = () => import('@/views/review/index.vue')
const Budget = () => import('@/views/budget/index.vue')
const Expense = () => import('@/views/expense/index.vue')
const Schedule = () => import('@/views/schedule/index.vue')
const Permit = () => import('@/views/permit/index.vue')
const Wrap = () => import('@/views/wrap/index.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/script', name: 'script', component: Script },
    { path: '/scene', name: 'scene', component: Scene },
    { path: '/casting', name: 'casting', component: Casting },
    { path: '/crew', name: 'crew', component: Crew },
    { path: '/notice', name: 'notice', component: Notice },
    { path: '/location', name: 'location', component: Location },
    { path: '/prop', name: 'prop', component: Prop },
    { path: '/costume', name: 'costume', component: Costume },
    { path: '/makeup', name: 'makeup', component: Makeup },
    { path: '/equipment', name: 'equipment', component: Equipment },
    { path: '/shooting', name: 'shooting', component: Shooting },
    { path: '/footage', name: 'footage', component: Footage },
    { path: '/edit', name: 'edit', component: Edit },
    { path: '/vfx', name: 'vfx', component: Vfx },
    { path: '/vfx-supplier', name: 'vfx-supplier', component: VfxSupplier },
    { path: '/review', name: 'review', component: Review },
    { path: '/budget', name: 'budget', component: Budget },
    { path: '/expense', name: 'expense', component: Expense },
    { path: '/schedule', name: 'schedule', component: Schedule },
    { path: '/permit', name: 'permit', component: Permit },
    { path: '/wrap', name: 'wrap', component: Wrap },
  ],
})

export default router
