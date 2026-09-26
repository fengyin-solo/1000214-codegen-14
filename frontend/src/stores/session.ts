import { defineStore } from 'pinia'

export type IdentityRole = 'admin' | 'vendor' | 'readonly'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: 'admin' as IdentityRole,
    vendorName: '',
    shiftLabel: '白班 08:00-20:00',
    scope: '影视剧组拍摄制作管理平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    // 供应商身份时用供应商名称对接口鉴权，其余身份用值班人名称
    identityName: (state) => (state.role === 'vendor' ? state.vendorName : state.operator),
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setIdentity(role: IdentityRole, vendorName = '') {
      this.role = role
      this.vendorName = vendorName
    },
  },
})
