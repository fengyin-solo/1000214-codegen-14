<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">影视剧组拍摄制作管理平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向剧本分场、选角档期、拍摄通告、场地器材、后期特效与杀青结算的一体化剧组管理后台。</span>
        <span class="head-user">当前值班：{{ store.operator }} · {{ store.roleLabel }} · {{ store.shiftLabel }}</span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "剧本管理", path: "/script" }, { label: "分场大纲", path: "/scene" }, { label: "角色选角", path: "/casting" }, { label: "剧组人员", path: "/crew" }, { label: "拍摄通告", path: "/notice" }, { label: "场地租用", path: "/location" }, { label: "道具管理", path: "/prop" }, { label: "服装造型", path: "/costume" }, { label: "化妆造型", path: "/makeup" }, { label: "器材管理", path: "/equipment" }, { label: "拍摄进度", path: "/shooting" }, { label: "素材管理", path: "/footage" }, { label: "后期剪辑", path: "/edit" }, { label: "特效制作", path: "/vfx" }, { label: "供应商视图", path: "/vfx-supplier" }, { label: "审片意见", path: "/review" }, { label: "预算科目", path: "/budget" }, { label: "费用报销", path: "/expense" }, { label: "档期协调", path: "/schedule" }, { label: "外景许可", path: "/permit" }, { label: "杀青结算", path: "/wrap" }]
</script>
