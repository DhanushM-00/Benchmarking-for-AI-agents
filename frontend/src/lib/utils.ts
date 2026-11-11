import { clsx, type ClassValue } from 'clsx'

export const cn = (...inputs: ClassValue[]): string => clsx(inputs)

export const clamp = (n: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, n))

/** Deterministic PRNG (mulberry32) so fixture data is stable across reloads. */
export const seededRandom = (seed: number): (() => number) => {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export const hashString = (s: string): number => {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

export const sum = (arr: number[]): number => arr.reduce((a, b) => a + b, 0)

export const mean = (arr: number[]): number => (arr.length ? sum(arr) / arr.length : 0)

export const quantile = (arr: number[], q: number): number => {
  if (!arr.length) return 0
  const sorted = [...arr].sort((x, y) => x - y)
  const pos = (sorted.length - 1) * q
  const base = Math.floor(pos)
  const rest = pos - base
  return sorted[base + 1] !== undefined
    ? sorted[base] + rest * (sorted[base + 1] - sorted[base])
    : sorted[base]
}

export const groupBy = <T, K extends string | number>(
  arr: T[],
  key: (item: T) => K,
): Record<K, T[]> =>
  arr.reduce((acc, item) => {
    const k = key(item)
    ;(acc[k] ||= []).push(item)
    return acc
  }, {} as Record<K, T[]>)
