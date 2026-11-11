import type { ReactNode } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { agentColor } from '@/lib/format'

export const AXIS = { stroke: '#4b586d', fontSize: 11, tickLine: false, axisLine: false } as const
export const GRID = { stroke: '#1e2735', strokeDasharray: '3 3', vertical: false } as const

export function ChartTooltip({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean
  payload?: { name?: string; value?: number | string; color?: string; dataKey?: string }[]
  label?: string | number
  formatter?: (v: number | string, name?: string) => string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      {label !== undefined && <div className="chart-tooltip-title">{label}</div>}
      {payload.map((p, i) => (
        <div className="chart-tooltip-row" key={`${p.dataKey}-${i}`}>
          <span className="chart-tooltip-key">
            <span className="chart-tooltip-swatch" style={{ background: p.color }} />
            {p.name}
          </span>
          <span className="chart-tooltip-val">
            {formatter ? formatter(p.value ?? 0, p.name) : Number(p.value ?? 0).toFixed(1)}
          </span>
        </div>
      ))}
    </div>
  )
}

/* ---------------------------------------------------------- Radar */

export interface RadarSeries {
  name: string
  colorIndex: number
  values: number[]
}

export function RadarProfile({
  axes,
  series,
  height = 300,
}: {
  axes: string[]
  series: RadarSeries[]
  height?: number
}) {
  const data = axes.map((axis, i) => {
    const row: Record<string, string | number> = { axis }
    series.forEach((s) => (row[s.name] = s.values[i] ?? 0))
    return row
  })

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke="#26314a" />
        <PolarAngleAxis dataKey="axis" tick={{ fill: '#8b97ae', fontSize: 11 }} />
        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
        {series.map((s) => (
          <Radar
            key={s.name}
            name={s.name}
            dataKey={s.name}
            stroke={agentColor(s.colorIndex)}
            fill={agentColor(s.colorIndex)}
            fillOpacity={0.14}
            strokeWidth={1.8}
          />
        ))}
        <Tooltip content={<ChartTooltip />} />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 12, color: '#aab6ca', paddingTop: 6 }}
        />
      </RadarChart>
    </ResponsiveContainer>
  )
}

/* ---------------------------------------------------------- Trend */

export function TrendChart({
  data,
  series,
  height = 260,
  yDomain = [40, 100],
}: {
  data: Record<string, string | number>[]
  series: { name: string; colorIndex: number }[]
  height?: number
  yDomain?: [number, number]
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="label" {...AXIS} />
        <YAxis domain={yDomain} {...AXIS} width={46} />
        <Tooltip content={<ChartTooltip />} cursor={{ stroke: '#2a3547' }} />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 12, color: '#aab6ca', paddingTop: 4 }}
        />
        {series.map((s) => (
          <Line
            key={s.name}
            type="monotone"
            name={s.name}
            dataKey={s.name}
            stroke={agentColor(s.colorIndex)}
            strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0, fill: agentColor(s.colorIndex) }}
            activeDot={{ r: 5 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

/* ---------------------------------------------------------- Grouped bars */

export function GroupedBars({
  data,
  bars,
  height = 260,
  yFormatter,
  yDomain,
  rowColors,
}: {
  data: Record<string, string | number>[]
  bars: { key: string; name: string; colorIndex: number }[]
  height?: number
  yFormatter?: (v: number) => string
  yDomain?: [number, number]
  /** Colour each bar by its row (e.g. one colour per agent). */
  rowColors?: string[]
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 6, right: 8, left: -18, bottom: 0 }} barGap={4}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="name" {...AXIS} />
        <YAxis domain={yDomain} {...AXIS} width={52} tickFormatter={yFormatter} />
        <Tooltip
          content={<ChartTooltip formatter={(v) => (yFormatter ? yFormatter(Number(v)) : Number(v).toFixed(1))} />}
          cursor={{ fill: 'rgba(91,140,255,0.06)' }}
        />
        {bars.length > 1 && (
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 12, color: '#aab6ca', paddingTop: 4 }}
          />
        )}
        {bars.map((b, bi) => (
          <Bar
            key={b.key}
            name={b.name}
            dataKey={b.key}
            fill={agentColor(b.colorIndex)}
            radius={[4, 4, 0, 0]}
            maxBarSize={46}
          >
            {rowColors && bi === 0
              ? data.map((_, di) => <Cell key={di} fill={rowColors[di] ?? agentColor(b.colorIndex)} />)
              : null}
          </Bar>
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

/* ---------------------------------------------------------- Area (single) */

export function AreaSeries({
  data,
  dataKey,
  name,
  color,
  height = 200,
  yFormatter,
  unit = '',
}: {
  data: Record<string, string | number>[]
  dataKey: string
  name: string
  color: string
  height?: number
  yFormatter?: (v: number) => string
  unit?: string
}) {
  const id = `grad-${dataKey.replace(/\W/g, '')}`
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.32} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="label" {...AXIS} />
        <YAxis {...AXIS} width={50} tickFormatter={yFormatter} />
        <Tooltip
          content={
            <ChartTooltip
              formatter={(v) => `${yFormatter ? yFormatter(Number(v)) : Number(v).toFixed(1)}${unit}`}
            />
          }
        />
        <Area
          type="monotone"
          name={name}
          dataKey={dataKey}
          stroke={color}
          strokeWidth={2}
          fill={`url(#${id})`}
          dot={false}
          activeDot={{ r: 4 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/* ---------------------------------------------------------- Donut */

export function Donut({
  data,
  height = 220,
  valueKey = 'value',
  nameKey = 'name',
  centerLabel,
  centerValue,
}: {
  data: { name: string; value: number; color?: string }[]
  height?: number
  valueKey?: string
  nameKey?: string
  centerLabel?: string
  centerValue?: string
}) {
  return (
    <div style={{ position: 'relative' }}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie
            data={data}
            dataKey={valueKey}
            nameKey={nameKey}
            innerRadius="62%"
            outerRadius="88%"
            paddingAngle={3}
            stroke="none"
          >
            {data.map((entry, i) => (
              <Cell key={`${entry.name}-${i}`} fill={entry.color ?? agentColor(i)} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip formatter={(v) => `$${Number(v).toFixed(2)}`} />} />
        </PieChart>
      </ResponsiveContainer>
      {(centerLabel || centerValue) && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'grid',
            placeContent: 'center',
            textAlign: 'center',
            pointerEvents: 'none',
          }}
        >
          <div className="mono" style={{ fontSize: 21, fontWeight: 600 }}>
            {centerValue}
          </div>
          <div className="tiny muted" style={{ letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            {centerLabel}
          </div>
        </div>
      )}
    </div>
  )
}

/* ---------------------------------------------------------- Horizontal bars */

export function HorizontalBars({
  data,
  valueKey = 'value',
  labelKey = 'name',
  formatter,
}: {
  data: { name: string; value: number; color?: string }[]
  valueKey?: string
  labelKey?: string
  formatter?: (v: number) => string
}) {
  const read = (d: (typeof data)[number], key: string): number =>
    key === 'name' ? 0 : Number(d[key as keyof typeof d] ?? 0)
  const label = (d: (typeof data)[number], key: string): string =>
    key === 'name' ? d.name : String(d[key as keyof typeof d] ?? '')

  const max = Math.max(...data.map((d) => read(d, valueKey)), 1)
  return (
    <div className="stack" style={{ gap: 11 }}>
      {data.map((d, i) => (
        <div key={`${label(d, labelKey)}-${i}`}>
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 5 }}>
            <span style={{ fontSize: 12.5 }}>{label(d, labelKey)}</span>
            <span className="mono" style={{ fontSize: 12.5, fontWeight: 600 }}>
              {formatter ? formatter(read(d, valueKey)) : read(d, valueKey).toFixed(1)}
            </span>
          </div>
          <div className="bar">
            <div
              className="bar-fill"
              style={{ width: `${(read(d, valueKey) / max) * 100}%`, background: d.color ?? agentColor(i) }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

export function LegendRow({ items }: { items: { name: string; colorIndex?: number; color?: string }[] }) {
  return (
    <div className="row-wrap" style={{ gap: 14 }}>
      {items.map((it) => (
        <span className="legend-item" key={it.name}>
          <span
            className="legend-swatch"
            style={{ background: it.color ?? agentColor(it.colorIndex ?? 0) }}
          />
          {it.name}
        </span>
      ))}
    </div>
  )
}

export type { ReactNode }
