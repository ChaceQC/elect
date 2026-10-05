// 只保存成功登录时已读的协议版本/正文摘要，不保存账号、凭据或会话。
export const AGREEMENT_READ_KEY = 'elect:agreement-read'

/** @param {string} version */
export function hasReadAgreement(version) {
  try { return !!version && localStorage.getItem(AGREEMENT_READ_KEY) === version }
  catch { return false }
}

/** @param {string} version */
export function rememberReadAgreement(version) {
  try { localStorage.setItem(AGREEMENT_READ_KEY, version) }
  catch { /* 浏览器禁用持久存储时仍允许本次登录。 */ }
}
