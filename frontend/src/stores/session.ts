import { defineStore } from 'pinia'

import { setRequestIdentity } from '@/api/client'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: 'reviewer',
    supplier: '',
    shiftLabel: '白班 08:00-20:00',
    scope: '影视剧组拍摄制作管理平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    roleLabel: (state) => {
      const labels: Record<string, string> = { supplier: '制作供应商', readonly: '只读人员', reviewer: '审核管理员' }
      return labels[state.role] ?? state.role
    },
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    /** 切换当前身份：同步更新请求层携带的身份参数，所有接口随即按新身份取数。 */
    applyIdentity(identity: { operator: string; role: string; supplier?: string }) {
      this.operator = identity.operator
      this.role = identity.role
      this.supplier = identity.supplier ?? ''
      setRequestIdentity({ operator: this.operator, role: this.role, supplier: this.supplier })
    },
  },
})
