import { useEffect, useState } from 'react'
import { fetchSegments, type SegmentsResponse } from '@/api/project'

export type SegmentsFetchState =
  | { status: 'loading' }
  | { status: 'success'; data: SegmentsResponse }
  | { status: 'error'; error: string }

export function useSegments(): SegmentsFetchState {
  const [state, setState] = useState<SegmentsFetchState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    fetchSegments()
      .then((data) => {
        if (!cancelled) setState({ status: 'success', data })
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : String(err)
          setState({ status: 'error', error: message })
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
