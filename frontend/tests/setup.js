import '@testing-library/jest-dom/vitest'

// jsdom 不实现原生 dialog；焦点/键盘与真实尺寸在 Playwright 验证。
HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
