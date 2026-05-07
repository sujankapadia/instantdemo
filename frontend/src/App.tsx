import { useEffect, useState } from 'react'

type HealthState =
  | { status: 'loading' }
  | { status: 'ok'; data: unknown }
  | { status: 'error'; message: string }

function App() {
  const [health, setHealth] = useState<HealthState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data) => {
        if (!cancelled) setHealth({ status: 'ok', data })
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : String(err)
          setHealth({ status: 'error', message })
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem' }}>
      <h1>InstantDemo</h1>
      <p>
        Backend health:{' '}
        {health.status === 'loading' && <em>checking…</em>}
        {health.status === 'ok' && (
          <code>{JSON.stringify(health.data)}</code>
        )}
        {health.status === 'error' && (
          <span style={{ color: 'crimson' }}>error: {health.message}</span>
        )}
      </p>
    </div>
  )
}

export default App
