<template>
  <section class="page" data-module="vfx-supplier">
    <header class="page-head">
      <div>
        <h2>特效镜头供应商权限视图</h2>
        <p class="page-desc">
          供应商只能查看、提交本人名下镜头；只读人员不能改动审核结果；确认完成与重新指派仅审核管理员可操作，越权一律拒绝。
        </p>
      </div>
      <div class="page-actions">
        <label class="identity-switch">
          <span>当前身份</span>
          <select v-model="identityKey" @change="switchIdentity">
            <option v-for="item in identityOptions" :key="item.key" :value="item.key">{{ item.label }}</option>
          </select>
        </label>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>镜头编号</span>
        <input v-model="filters.keyword" placeholder="按镜头编号检索" />
      </label>
      <label class="filter-item">
        <span>制作状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column.key">{{ column.label }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column.key">{{ row[column.key] ?? '—' }}</td>
          <td class="row-actions">
            <template v-if="rowActions(row).length">
              <button
                v-for="action in rowActions(row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="muted-text">只读</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">当前身份下暂无可见镜头</td>
        </tr>
      </tbody>
    </table>

    <section v-if="reassignTarget" class="reassign-panel">
      <span>重新指派 {{ reassignTarget['镜头编号'] }} 的供应商归属：</span>
      <select v-model="reassignSupplier">
        <option v-for="supplier in suppliers" :key="supplier" :value="supplier">{{ supplier }}</option>
      </select>
      <button class="btn primary" type="button" @click="confirmReassign">确认指派</button>
      <button class="btn ghost" type="button" @click="cancelReassign">取消</button>
      <span class="muted-text">渲染帧数与交付版本为受保护字段，不随归属变更</span>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条可见镜头 · {{ session.operator }}（{{ session.roleLabel }}）</span>
      <span v-if="errorMessage" class="error-text">
        {{ errorMessage }}
        <button v-if="retryAction" class="link" type="button" @click="retryLast">按原请求编号重试</button>
      </span>
    </footer>

    <section class="records-panel">
      <h3 class="records-title">审核记录（与列表同一可见口径）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in recordColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in records" :key="String(record.id)">
            <td v-for="column in recordColumns" :key="column">{{ record[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!records.length">
            <td :colspan="recordColumns.length" class="empty-state">暂无审核记录</td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { NETWORK_ERROR_PREFIX, readError, request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

interface PendingAction {
  kind: 'action' | 'reassign'
  entryId: number
  requestId: string
  action?: string
  supplier?: string
}

const ENDPOINT = '/api/vfx-supplier'
const columns = [
  { key: '镜头编号', label: '镜头编号' },
  { key: '所属集数', label: '所属集数' },
  { key: '特效类型', label: '特效类型' },
  { key: '制作供应商', label: '制作供应商' },
  { key: '渲染帧数', label: '渲染帧数' },
  { key: '交付版本', label: '交付版本' },
  { key: 'status', label: '制作状态' },
]
const statuses = ['待制作', '制作中', '待审核', '已完成']
const recordColumns = ['时间', '镜头编号', '动作', '操作人', '操作角色', '归属供应商', '结果', '请求编号']

const identityOptions = [
  { key: 'reviewer', label: '审核管理员 · 值班管理员', operator: '值班管理员', role: 'reviewer', supplier: '' },
  { key: 'spark', label: '制作供应商 · 星火视效', operator: '星火视效-制片', role: 'supplier', supplier: '星火视效' },
  { key: 'mirage', label: '制作供应商 · 幻彩数字', operator: '幻彩数字-制片', role: 'supplier', supplier: '幻彩数字' },
  { key: 'readonly', label: '只读人员 · 只读观察员', operator: '只读观察员', role: 'readonly', supplier: '' },
]

const session = useSessionStore()

const identityKey = ref('reviewer')
const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<{ label: string; value: number }[]>([])
const records = ref<Row[]>([])
const suppliers = ref<string[]>([])
const filters = ref({ keyword: '', status: '' })
const errorMessage = ref('')
const reassignTarget = ref<Row | null>(null)
const reassignSupplier = ref('')
// 数据失败可重试：保留失败操作的现场（含请求编号），重试时原样重发，服务端幂等去重
const retryAction = ref<PendingAction | null>(null)

function newRequestId(): string {
  return `REQ-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function rowActions(row: Row): string[] {
  if (session.role === 'supplier') {
    if (row['制作供应商'] !== session.supplier) return []
    if (row['status'] === '待制作') return ['开始制作']
    if (row['status'] === '制作中') return ['提交审核']
    return []
  }
  if (session.role === 'reviewer') {
    const actions: string[] = []
    if (row['status'] === '待审核') actions.push('确认完成')
    actions.push('重新指派')
    return actions
  }
  return []
}

function switchIdentity() {
  const chosen = identityOptions.find((item) => item.key === identityKey.value) ?? identityOptions[0]
  session.applyIdentity(chosen)
  reassignTarget.value = null
  retryAction.value = null
  errorMessage.value = ''
  void reload()
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

async function runAction(action: string, row: Row) {
  if (action === '重新指派') {
    reassignTarget.value = row
    reassignSupplier.value = String(row['制作供应商'] ?? '')
    return
  }
  await execute({ kind: 'action', entryId: Number(row.id), action, requestId: newRequestId() })
}

async function confirmReassign() {
  if (!reassignTarget.value) return
  await execute({
    kind: 'reassign',
    entryId: Number(reassignTarget.value.id),
    supplier: reassignSupplier.value,
    requestId: newRequestId(),
  })
}

function cancelReassign() {
  reassignTarget.value = null
}

async function retryLast() {
  if (retryAction.value) {
    await execute(retryAction.value)
  }
}

async function execute(pending: PendingAction) {
  errorMessage.value = ''
  retryAction.value = null
  try {
    const isReassign = pending.kind === 'reassign'
    const url = isReassign ? `${ENDPOINT}/${pending.entryId}/reassign` : `${ENDPOINT}/${pending.entryId}/actions`
    const body = isReassign
      ? { values: { 制作供应商: pending.supplier, 请求编号: pending.requestId } }
      : { values: { action: pending.action, 请求编号: pending.requestId } }
    const response = await request(url, { method: 'POST', body: JSON.stringify(body) })
    if (!response.ok) {
      const message = await readError(response)
      // 5xx 属于数据失败，保留现场可按原请求编号重试；4xx 是规则拒绝，直接展示原因
      if (response.status >= 500) retryAction.value = pending
      throw new Error(message)
    }
    if (isReassign) reassignTarget.value = null
    await reload()
  } catch (error) {
    const message = error instanceof Error ? error.message : '操作失败'
    if (message.startsWith(NETWORK_ERROR_PREFIX)) retryAction.value = pending
    errorMessage.value = message
  }
}

async function loadList() {
  const params = new URLSearchParams()
  if (filters.value.keyword) params.set('keyword', filters.value.keyword)
  if (filters.value.status) params.set('status', filters.value.status)
  const response = await request(`${ENDPOINT}?${params.toString()}`)
  if (!response.ok) throw new Error(await readError(response))
  const payload = await response.json()
  rows.value = payload.items ?? []
  total.value = payload.total ?? rows.value.length
}

async function loadSummary() {
  const response = await request(`${ENDPOINT}/summary`)
  if (!response.ok) throw new Error(await readError(response))
  const payload = await response.json()
  stats.value = payload.items ?? []
}

async function loadRecords() {
  const response = await request(`${ENDPOINT}/review-records`)
  if (!response.ok) throw new Error(await readError(response))
  const payload = await response.json()
  records.value = payload.items ?? []
}

async function reload() {
  errorMessage.value = ''
  try {
    await Promise.all([loadList(), loadSummary(), loadRecords()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '供应商视图数据读取失败'
  }
}

onMounted(async () => {
  session.applyIdentity(identityOptions[0])
  try {
    const response = await request(`${ENDPOINT}/suppliers`)
    if (response.ok) {
      const payload = await response.json()
      suppliers.value = payload.suppliers ?? []
    }
  } catch {
    suppliers.value = []
  }
  await reload()
})
</script>
