import { ApiError } from '../api/client.js'

/** @template T */
export class VersionedDraft {
  /** @param {T} value @param {number} version */
  constructor(value, version) {
    if (!Number.isInteger(version) || version < 1) throw new Error('配置版本必须为正整数')
    this.draft = structuredClone(value)
    this.version = version
    this.reviewRequired = false
  }
  /** @param {number} version */
  acknowledgeCurrent(version) {
    if (!Number.isInteger(version) || version < 1) throw new Error('配置版本必须为正整数')
    this.version = version; this.reviewRequired = false
  }

  /** @param {(draft:T, version:number)=>Promise<{value:T, version:number}>} write
   * @param {()=>Promise<{value:T, version:number}>} readCurrent */
  async save(write, readCurrent) {
    if (this.reviewRequired) throw new ApiError('VERSION_CONFLICT', '请先查看当前设置再提交草稿', 409)
    try {
      const saved = await write(structuredClone(this.draft), this.version)
      this.draft = saved.value; this.version = saved.version
      return { status: 'saved', current: saved }
    } catch (error) {
      if (!(error instanceof ApiError) || !['VERSION_CONFLICT', 'NETWORK_ERROR', 'REQUEST_TIMEOUT'].includes(error.code)) throw error
      this.reviewRequired = true
      const current = await readCurrent().catch(() => null)
      // 比较结果交给调用方展示；不自动重写，也不覆盖用户草稿。
      return { status: error.code === 'VERSION_CONFLICT' ? 'conflict' : 'reconcile', current }
    }
  }
}
