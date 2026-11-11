/* Small formatting helpers shared across the UI. */

/**
 * Every formatter tolerates a null/undefined metric.
 *
 * The API returns null for averages that cannot be computed yet (no completed
 * runs, no timing data). Calling `.toFixed()` on those crashed the whole
 * dashboard — the page must render "—" instead.
 */
const dash = (n: number | null | undefined): n is null | undefined =>
  n === null || n === undefined || Number.isNaN(n)

export const fmtNum = (n: number | null | undefined, digits = 0): string =>
  dash(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })

export const fmtUsd = (n: number | null | undefined): string =>
  dash(n)
    ? '—'
    : n > 0 && n < 0.0001
      ? `$${n.toFixed(6)}`
      : n > 0 && n < 0.01
        ? `$${n.toFixed(4)}`
        : `$${n.toFixed(2)}`

export const fmtMs = (n: number | null | undefined): string =>
  dash(n) ? '—' : `${Math.round(n).toLocaleString('en-US')}ms`

export const fmtDuration = (sec: number | null | undefined): string => {
  if (dash(sec)) return '—'
  if (sec < 60) return `${sec.toFixed(1)}s`
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `${m}m ${String(s).padStart(2, '0')}s`
}

export const fmtCompact = (n: number | null | undefined): string => {
  if (dash(n)) return '—'
  if (n < 1000) return String(Math.round(n))
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`
  return `${(n / 1_000_000).toFixed(1)}M`
}

export const fmtDate = (iso: string): string =>
  new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })

export const fmtDateTime = (iso: string): string =>
  new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  })

export const fmtTime = (iso: string): string =>
  new Date(iso).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  })

export const relTime = (iso: string): string => {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.round(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  return fmtDate(iso)
}

export const pct = (n: number | null | undefined, digits = 0): string =>
  dash(n) ? '—' : `${n.toFixed(digits)}%`

/** Score → accessible colour ramp (red → amber → teal → blue). */
export const scoreColor = (score: number): string => {
  if (score >= 85) return '#2dd4a7'
  if (score >= 70) return '#5b8cff'
  if (score >= 55) return '#f5a524'
  return '#f4525f'
}

export const agentColor = (index: number): string =>
  ['#5b8cff', '#2dd4a7', '#f5a524', '#a78bfa', '#f472b6'][index % 5]

export const initials = (name: string): string =>
  name
    .split(/[\s-]+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')

export const slug = (s: string): string =>
  s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
