import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchSegments, type SegmentsResponse } from '@/api/project'

export type SegmentsFetchState =
  | { status: 'loading' }
  | { status: 'success'; data: SegmentsResponse }
  | { status: 'error'; error: string }

export interface UseSegmentsResult {
  state: SegmentsFetchState
  refetch: () => void
}

export function useSegments(): UseSegmentsResult {
  const [state, setState] = useState<SegmentsFetchState>({ status: 'loading' })
  // Generation counter — each refetch increments this; only the most
  // recent fetch is allowed to update state. Avoids races where a slow
  // initial fetch resolves after a manual refetch.
  const fetchIdRef = useRef(0)

  const refetch = useCallback(() => {
    fetchIdRef.current += 1
    const myFetchId = fetchIdRef.current
    setState({ status: 'loading' })
    fetchSegments()
      .then((data) => {
        if (myFetchId === fetchIdRef.current) {
          setState({ status: 'success', data })
        }
      })
      .catch((err: unknown) => {
        if (myFetchId === fetchIdRef.current) {
          const message = err instanceof Error ? err.message : String(err)
          setState({ status: 'error', error: message })
        }
      })
  }, [])

  useEffect(() => {
    refetch()
    return () => {
      // Bump fetchId so any in-flight fetch is ignored after unmount.
      fetchIdRef.current += 1
    }
  }, [refetch])

  return { state, refetch }
}
