import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ApiError, apiClient } from '../../api/client.js'
import { StatusBlock } from '../../components/feedback/StatusBlock.jsx'
import { useSession } from './SessionProvider.jsx'
import { useCaptcha } from './useCaptcha.js'
import { AgreementDialog } from './AgreementDialog.jsx'

/** @typedef {import('../../api/generated').components['schemas']['Agreement']} Agreement */
/** @param {{reauthenticate?: boolean, onSuccess?: ()=>void}} props */
export function LoginForm({ reauthenticate = false, onSuccess }) {
  const session = useSession()
  const captcha = useCaptcha()
  const [student, setStudent] = useState(reauthenticate ? session.user?.student_id ?? '' : '')
  const [password, setPassword] = useState('')
  const [answer, setAnswer] = useState('')
  const [readVersion, setReadVersion] = useState('')
  const [accepted, setAccepted] = useState(false)
  const [allowed, setAllowed] = useState(false)
  const [agreementOpen, setAgreementOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(/** @type {ApiError|null} */ (null))
  const submitting = useRef(false)
  const pending = useRef(/** @type {AbortController|null} */ (null))
  useEffect(() => { const request = pending; return () => request.current?.abort() }, [])
  const policy = useQuery({ queryKey: ['agreement'], queryFn: async ({ signal }) =>
    /** @type {Agreement} */ ((await apiClient.request('/auth/agreement', { signal })).data) })
  const currentVersion = policy.data ? `${policy.data.version}:${policy.data.content_hash}` : ''
  const { refresh } = captcha
  useEffect(() => { if (currentVersion) { setAccepted(false); setReadVersion(''); void refresh() } }, [currentVersion, refresh])
  useEffect(() => { setAnswer('') }, [captcha.data?.challenge_id])
  const valid = !!policy.data && readVersion === currentVersion && accepted && student.trim().length > 0 &&
    student.trim().length <= 128 && !/\s/.test(student.trim()) && password.length > 0 && password.length <= 1024 &&
    answer.trim().length > 0 && !!captcha.data && !captcha.expired && !captcha.busy
  /** @param {import('react').FormEvent} event */
  async function submit(event) {
    event.preventDefault()
    if (!valid || submitting.current || !policy.data || !captcha.data) return
    submitting.current = true; setBusy(true); setError(null)
    pending.current = new AbortController()
    try {
      const result = await apiClient.request('/auth/login', { method: 'POST', signal: pending.current.signal, body: {
        student_id: student.trim(), password, challenge_id: captcha.data.challenge_id,
        captcha_answer: answer.trim(), agreement_version: policy.data.version,
        agreement_accepted: true, credential_use_allowed: allowed,
      } })
      const login = /** @type {import('../../api/generated').components['schemas']['LoginResult']} */ (result.data)
      if (!login?.user?.id || !login.user.csrf_token) throw new ApiError('INVALID_RESPONSE', '登录结果无法识别，请检查当前会话', 200)
      setPassword(''); setAnswer('')
      await session.acceptUser(login.user)
      onSuccess?.()
    } catch (cause) {
      const failure = cause instanceof ApiError ? cause : new ApiError('NETWORK_ERROR', '登录未完成，请稍后重试', 0)
      setError(failure)
      if (['SCHOOL_LOGIN_REJECTED', 'CAPTCHA_INVALID', 'CAPTCHA_EXPIRED'].includes(failure.code)) void refresh()
      if (failure.code === 'INVALID_ARGUMENT') { setAccepted(false); void policy.refetch() }
    } finally { submitting.current = false; setBusy(false) }
  }
  return <form onSubmit={submit} className="login-form" aria-label={reauthenticate ? '学校重新认证' : '学校账号登录'}>
    <label>学号<input aria-label="学校账号" placeholder="请输入学号" autoComplete="username" value={student} onChange={event => setStudent(event.target.value)}
      maxLength={128} readOnly={reauthenticate} required /></label>
    <label>密码<input aria-label="学校密码" placeholder="请输入统一认证密码" type="password" autoComplete="current-password" value={password}
      onChange={event => setPassword(event.target.value)} maxLength={1024} required /></label>
    <div className="captcha-field"><label>验证码<input aria-label="验证码答案" value={answer} onChange={event => setAnswer(event.target.value)}
      autoComplete="off" maxLength={32} required placeholder="输入图片算式的结果" /></label>
      <div className="captcha-image">{captcha.data ? <img src={captcha.data.image_data_url} alt="学校算式验证码" /> :
        <span>{captcha.busy ? '取图中…' : '验证码未加载'}</span>}
      <button type="button" className="quiet" disabled={busy || captcha.busy || !policy.data} onClick={() => { setAnswer(''); void refresh() }}>换一张</button></div>
    </div>
    {captcha.expired && <p role="alert" className="form-error">验证码已过期，请换一张。</p>}
    {captcha.error && <StatusBlock title={captcha.error.message} error />}
    {policy.isError && <StatusBlock title="无法加载使用协议" error action={{ label: '重试', onClick: () => { void policy.refetch() } }} />}
    <div className="agreement-check"><label className="checkbox-row"><input type="checkbox" checked={accepted} disabled={readVersion !== currentVersion || !currentVersion}
      onChange={event => setAccepted(event.target.checked)} />我同意应用使用协议</label>
      <button type="button" className="text-button" disabled={!policy.data} onClick={() => setAgreementOpen(true)}>阅读应用协议</button></div>
    {readVersion !== currentVersion && <p className="field-hint">请打开协议并阅读到底部，之后即可勾选。</p>}
    <label className="checkbox-row"><input aria-label="允许后台使用加密凭据恢复学校认证" type="checkbox" checked={allowed} onChange={event => setAllowed(event.target.checked)} />
      允许后台恢复学校登录</label>
    <p className="authorization-note">用于后台查询与已开启的监控，可在账户中撤回。</p>
    {error && <StatusBlock title={error.message} error><p>{error.retryAfterSeconds ? `请至少等待 ${error.retryAfterSeconds} 秒后重试。` :
      '请检查输入或重新获取验证码后重试。'}</p>{error.requestId && <small>请求编号：{error.requestId}</small>}</StatusBlock>}
    <button className="primary-action" type="submit" disabled={!valid || busy}>{busy ? '正在学校认证…' : reauthenticate ? '重新认证' : '登录'}</button>
    {policy.data && <AgreementDialog open={agreementOpen} agreement={policy.data} onClose={() => setAgreementOpen(false)}
      onRead={() => setReadVersion(currentVersion)} />}
  </form>
}
