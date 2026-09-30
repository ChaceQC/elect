/** @param {{title: string, children?: import('react').ReactNode, error?: boolean,
 * action?: {label: string, onClick: ()=>void}}} props */
export function StatusBlock({ title, children, error = false, action }) {
  return <section className={`status-block${error ? ' status-error' : ''}`} role={error ? 'alert' : 'status'}>
    <h2>{title}</h2>{children}
    {action && <button onClick={action.onClick}>{action.label}</button>}
  </section>
}
