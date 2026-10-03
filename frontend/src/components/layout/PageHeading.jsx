/** @param {{title: string, children?: import('react').ReactNode}} props */
export function PageHeading({ title, children }) {
  return <div className="page-heading"><h1>{title}</h1>{children}</div>
}
