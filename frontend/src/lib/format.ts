export function formatCostUsd(value: number): string {
  return `$${value.toFixed(2)}`
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const totalSeconds = Math.round(ms / 1000)
  if (totalSeconds < 120) return `${totalSeconds}s`
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return seconds === 0 ? `${minutes}m` : `${minutes}m ${seconds}s`
}

export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  const now = Date.now()
  const diffSec = Math.round((now - then) / 1000)
  if (diffSec < 60) return 'just now'
  if (diffSec < 3600) {
    const m = Math.round(diffSec / 60)
    return `${m}m ago`
  }
  if (diffSec < 86400) {
    const h = Math.round(diffSec / 3600)
    return `${h}h ago`
  }
  const d = Math.round(diffSec / 86400)
  return `${d}d ago`
}
