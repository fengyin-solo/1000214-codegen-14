<template>
  <section class="page" data-module="vfx-vendor">
    <header class="page-head">
      <div>
        <h2>特效镜头供应商权限视图</h2>
        <p class="page-desc">制作供应商只能查看和提交本人镜头；只读人员不能改动审核结果；越权确认一律拒绝。</p>
      </div>
    </header>

    <form class="filter-bar" @submit.prevent="applyIdentity">
      <label class="filter-item">
        <span>当前身份</span>
        <select v-model="roleDraft">
          <option value="admin">审核管理员</option>
          <option value="vendor">制作供应商</option>
          <option value="readonly">只读人员</option>
        </select>
      </label>
      <label v-if="roleDraft === 'vendor'" class="filter-item">
        <span>供应商名称</span>
        <input v-model="vendorDraft" placeholder="填写本人供应商名称" />
      </label>
      <button class="btn" type="submit">切换身份</button>
      <span class="identity-hint">
        当前：{{ roleLabel }}<template v-if="session.role === 'vendor'"> · {{ session.vendorName || '未填写供应商名称' }}</template>
      </span>
    </form>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>镜头编号</span>
        <input v-model="keyword" placeholder="按镜头编号检索" />
      </label>
      <label class="filter-item">
        <span>制作状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <label class="fault-toggle">
        <input v-model="simulateFault" type="checkbox" />
        <span>模拟数据故障（演示失败重试）</span>
      </label>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <template v-if="session.role === 'vendor'">
              <button class="link" type="button" @click="submitShot(row)">提交审核</button>
            </template>
            <template v-else-if="session.role === 'admin'">
              <button class="link" type="button" @click="confirmShot(row)">确认完成</button>
              <button class="link" type="button" @click="assignShot(row)">调整归属</button>
            </template>
            <span v-else class="identity-hint">只读</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">当前身份下暂无可见特效镜头</td>
        </tr>
      </tbody>
    </table>

    <h3 class="section-title">审核记录</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in submissionColumns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="record in submissions" :key="String(record.id)">
          <td v-for="column in submissionColumns" :key="column">{{ record[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-if="record['状态'] === '失败' && session.role !== 'readonly'"
              class="link"
              type="button"
              @click="retrySubmission(record)"
            >
              重试提交
            </button>
            <span v-else class="identity-hint">—</span>
          </td>
        </tr>
        <tr v-if="!submissions.length">
          <td :colspan="submissionColumns.length + 1" class="empty-state">当前身份下暂无审核记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条可见镜头 · {{ submissionTotal }} 条审核记录</span>
      <span v-if="noticeMessage" class="ok-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore, type IdentityRole } from '@/stores/session'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/vfx-vendor'
const columns = ["镜头编号", "所属集数", "特效类型", "制作供应商", "渲染帧数", "预估工时", "交付版本", "制作状态"]
const statuses = ["待制作", "制作中", "待审核", "已完成"]
const submissionColumns = ["记录编号", "镜头编号", "提交供应商", "当前归属供应商", "动作", "状态", "结果", "提交时间", "备注"]
const roleLabels: Record<IdentityRole, string> = { admin: '审核管理员', vendor: '制作供应商', readonly: '只读人员' }

const session = useSessionStore()
const roleDraft = ref<IdentityRole>(session.role)
const vendorDraft = ref(session.vendorName)
const roleLabel = computed(() => roleLabels[session.role])

const rows = ref<Row[]>([])
const total = ref(0)
const submissions = ref<Row[]>([])
const submissionTotal = ref(0)
const keyword = ref('')
const statusFilter = ref('')
const simulateFault = ref(false)
const noticeMessage = ref('')
const errorMessage = ref('')

const stats = computed(() => [
  { label: '可见镜头', value: total.value },
  { label: '有效提交', value: submissions.value.filter((item) => item['状态'] === '有效').length },
  { label: '失败可重试', value: submissions.value.filter((item) => item['状态'] === '失败').length },
])

function applyIdentity() {
  session.setIdentity(roleDraft.value, vendorDraft.value.trim())
  void reload()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function newRequestId(row: Row): string {
  return `REQ-${row.id}-${Date.now()}-${Math.floor(Math.random() * 1000)}`
}

async function runAction(row: Row, values: Record<string, unknown>) {
  noticeMessage.value = ''
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? '操作未生效')
    }
    noticeMessage.value = payload.message ?? '操作成功'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败，请稍后重试'
  }
  await reload()
}

function submitShot(row: Row) {
  // 每个请求编号只对应一次有效提交，网络重试或重复点击都会被去重
  void runAction(row, { action: '提交审核', 请求编号: newRequestId(row), 模拟故障: simulateFault.value })
}

function confirmShot(row: Row) {
  void runAction(row, { action: '确认完成' })
}

function retrySubmission(record: Row) {
  void runAction({ id: record['镜头id'] }, { action: '重试提交', 模拟故障: simulateFault.value })
}

function assignShot(row: Row) {
  const vendor = window.prompt(`将镜头「${row['镜头编号']}」调整给哪个供应商？`, String(row['制作供应商'] ?? ''))
  if (!vendor || !vendor.trim()) {
    return
  }
  void runAction(row, { action: '调整归属', 新供应商: vendor.trim() })
}

async function reload() {
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const [listResp, submissionResp] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/submissions?size=200`),
    ])
    if (!listResp.ok) {
      throw new Error('特效镜头列表读取失败')
    }
    const listPayload = await listResp.json()
    rows.value = listPayload.items ?? []
    total.value = listPayload.total ?? rows.value.length
    if (submissionResp.ok) {
      const submissionPayload = await submissionResp.json()
      submissions.value = submissionPayload.items ?? []
      submissionTotal.value = submissionPayload.total ?? submissions.value.length
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '供应商权限视图读取失败'
  }
}

onMounted(reload)
</script>
