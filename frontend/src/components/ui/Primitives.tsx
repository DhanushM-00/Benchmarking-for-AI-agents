import type { ReactNode } from 'react'
import { AlertTriangle, Check, CheckCircle2, Info, Loader2, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

/* ---------------------------------------------------------- Badge */

type BadgeTone = 'neutral' | 'accent' | 'teal' | 'amber' | 'rose' | 'violet'

export function Badge({
  children,
  tone = 'neutral',
  dot = false,
  className,
}: {
  children: ReactNode
  tone?: BadgeTone
  dot?: boolean
  className?: string
}) {
  return (
    <span className={cn('badge', `badge-${tone}`, dot && 'badge-dot', className)}>{children}</span>
  )
}

/* ---------------------------------------------------------- Button */

export function Button({
  children,
  variant = 'default',
  size = 'md',
  icon,
  loading = false,
  block = false,
  className,
  ...rest
}: {
  children?: ReactNode
  variant?: 'default' | 'primary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  icon?: ReactNode
  loading?: boolean
  block?: boolean
  className?: string
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(
        'btn',
        variant === 'primary' && 'btn-primary',
        variant === 'ghost' && 'btn-ghost',
        variant === 'danger' && 'btn-danger',
        size === 'sm' && 'btn-sm',
        size === 'lg' && 'btn-lg',
        block && 'btn-block',
        className,
      )}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading ? <Loader2 className="spin" style={{ animation: 'spin 0.9s linear infinite' }} /> : icon}
      {children}
    </button>
  )
}

/* ---------------------------------------------------------- Progress */

export function Progress({
  value,
  color = 'var(--accent)',
  large = false,
  className,
}: {
  value: number
  color?: string
  large?: boolean
  className?: string
}) {
  return (
    <div className={cn('bar', large && 'bar-lg', className)}>
      <div
        className="bar-fill"
        style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: color }}
      />
    </div>
  )
}

/* ---------------------------------------------------------- Switch */

export function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label?: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={cn('switch', checked && 'on')}
      onClick={() => onChange(!checked)}
    />
  )
}

/* ---------------------------------------------------------- Checkbox */

export function Checkbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label?: string
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      aria-label={label}
      className={cn('checkbox', checked && 'on')}
      onClick={() => onChange(!checked)}
    >
      {checked && <Check />}
    </button>
  )
}

/* ---------------------------------------------------------- Field */

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string
  hint?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('field', className)}>
      <label className="label">{label}</label>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </div>
  )
}

/* ---------------------------------------------------------- Empty state */

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="empty">
      {icon}
      <div className="empty-title">{title}</div>
      {description && <div className="empty-desc">{description}</div>}
      {action}
    </div>
  )
}

/* ---------------------------------------------------------- Callout */

export function Callout({
  tone = 'info',
  icon,
  children,
  style,
}: {
  tone?: 'info' | 'teal' | 'amber' | 'rose'
  icon?: ReactNode
  children: ReactNode
  style?: React.CSSProperties
}) {
  const fallback =
    tone === 'teal' ? <CheckCircle2 /> : tone === 'amber' ? <AlertTriangle /> : tone === 'rose' ? <XCircle /> : <Info />
  return (
    <div className={cn('callout', tone !== 'info' && tone)} style={style}>
      {icon ?? fallback}
      <div>{children}</div>
    </div>
  )
}

/* ---------------------------------------------------------- Skeleton */

export function Skeleton({ h = 16, w = '100%', radius = 6 }: { h?: number; w?: number | string; radius?: number }) {
  return <div className="skeleton" style={{ height: h, width: w, borderRadius: radius }} />
}

/* ---------------------------------------------------------- Status pill */

const STATUS_TONE: Record<string, BadgeTone> = {
  queued: 'neutral',
  running: 'accent',
  completed: 'teal',
  failed: 'rose',
  cancelled: 'neutral',
}

const STATUS_LABEL: Record<string, string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

export function StatusPill({ status }: { status: string }) {
  return (
    <Badge tone={STATUS_TONE[status] ?? 'neutral'} dot className={status === 'running' ? 'status-running' : ''}>
      {STATUS_LABEL[status] ?? status}
    </Badge>
  )
}

/* ---------------------------------------------------------- Score pill */

export function ScorePill({
  score,
  size = 'md',
}: {
  score: number
  size?: 'sm' | 'md'
}) {
  const tone: BadgeTone = score >= 85 ? 'teal' : score >= 70 ? 'accent' : score >= 55 ? 'amber' : 'rose'
  return (
    <Badge tone={tone} className={size === 'sm' ? 'tiny' : ''}>
      {score.toFixed(1)}
    </Badge>
  )
}
