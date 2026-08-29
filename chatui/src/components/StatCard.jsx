export default function StatCard({ label, value, detail, tone = 'green', icon: Icon }) {
  return <article className={`stat-card soft-outset ${tone}`}><div className="stat-icon"><Icon size={19} /></div><div><p>{label}</p><strong>{value}</strong><small>{detail}</small></div></article>;
}
