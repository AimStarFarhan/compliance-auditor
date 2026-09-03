import { CheckCircle2, XCircle, HelpCircle, AlertTriangle } from 'lucide-react'

export function StatusPill({ status }) {
  const map = {
    pass: { cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: CheckCircle2 },
    fail: { cls: 'bg-red-50 text-red-700 border-red-200', icon: XCircle },
    needs_review: { cls: 'bg-amber-50 text-amber-700 border-amber-200', icon: HelpCircle },
  }
  const cfg = map[status] || { cls: 'bg-veil text-ink-soft border-line', icon: HelpCircle }
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-semibold uppercase tracking-wide ${cfg.cls}`}>
      <Icon className="size-3.5" /> {status.replace('_', ' ')}
    </span>
  )
}

export function SeverityBadge({ severity }) {
  const map = {
    high: 'bg-red-500/10 text-red-700 border border-red-200',
    medium: 'bg-amber-500/10 text-amber-700 border border-amber-200',
    low: 'bg-veil text-ink-soft border border-line',
  }
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-medium uppercase tracking-wide ${map[severity] || map.low}`}>
      {severity}
    </span>
  )
}

export function UnmappedStatusPill({ status }) {
  const map = {
    unmapped: 'bg-veil text-ink-soft border-line',
    ai_suggested: 'bg-blue-50 text-blue-700 border-blue-200',
    human_confirmed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    rejected: 'bg-red-50 text-red-600 border-red-200',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-semibold ${map[status] || ''}`}>
      {status === 'human_confirmed' && <CheckCircle2 className="size-3.5" />}
      {status === 'ai_suggested' && <AlertTriangle className="size-3.5" />}
      {status.replace('_', ' ')}
    </span>
  )
}

export function Sparkline({ pass, fail, review, size = 96 }) {
  const total = Math.max(pass + fail + review, 1)
  const r = size / 2
  const stroke = 12
  const radius = r - stroke / 2
  const c = 2 * Math.PI * radius
  const segs = [
    { n: fail, color: '#dc2626' },
    { n: pass, color: '#059669' },
    { n: review, color: '#d97706' },
  ]
  let offset = 0
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
      <circle cx={r} cy={r} r={radius} fill="none" stroke="#E4E9F1" strokeWidth={stroke} />
      {segs.map((s, i) => {
        const len = (s.n / total) * c
        const el = (
          <circle
            key={i}
            cx={r}
            cy={r}
            r={radius}
            fill="none"
            stroke={s.color}
            strokeWidth={stroke}
            strokeDasharray={`${len} ${c - len}`}
            strokeDashoffset={-offset}
            strokeLinecap="butt"
          />
        )
        offset += len
        return el
      })}
    </svg>
  )
}
