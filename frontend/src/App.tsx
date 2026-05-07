import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { TooltipProvider } from '@/components/ui/tooltip'

type HealthState =
  | { status: 'loading' }
  | { status: 'ok'; data: unknown }
  | { status: 'error'; message: string }

function fetchHealth(): Promise<unknown> {
  return fetch('/api/health').then((res) => {
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.json() as Promise<unknown>
  })
}

function App() {
  const [health, setHealth] = useState<HealthState>({ status: 'loading' })

  const refresh = () => {
    setHealth({ status: 'loading' })
    fetchHealth()
      .then((data) => setHealth({ status: 'ok', data }))
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err)
        setHealth({ status: 'error', message })
      })
  }

  useEffect(() => {
    let cancelled = false
    fetchHealth()
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
    <TooltipProvider>
      <div className="min-h-screen bg-background text-foreground p-8">
        <h1 className="text-3xl font-semibold mb-6">InstantDemo</h1>
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>Backend health</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="text-sm">
              {health.status === 'loading' && (
                <span className="text-muted-foreground">checking…</span>
              )}
              {health.status === 'ok' && (
                <code className="font-mono text-foreground">
                  {JSON.stringify(health.data)}
                </code>
              )}
              {health.status === 'error' && (
                <span className="text-destructive">
                  error: {health.message}
                </span>
              )}
            </div>
            <Button onClick={refresh} variant="secondary">
              Refresh
            </Button>
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  )
}

export default App
