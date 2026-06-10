import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchStoryboard, type StoryboardResponse } from '@/api/storyboard'

export type StoryboardFetchState =
  | { status: 'loading' }
  | { status: 'error'; error: string }
  | { status: 'success'; data: StoryboardResponse }

/**
 * Fetch + refetch for the storyboard document (M2). Same
 * generation-counter pattern as useSegments: the most recent fetch
 * wins so a stale in-flight response can't clobber fresh state.
 */
export function useStoryboard(): {
  state: StoryboardFetchState
  refetch: () => void
} {
  const [state, setState] = useState<StoryboardFetchState>({
    status: 'loading',
  })
  const fetchIdRef = useRef(0)

  const refetch = useCallback(() => {
    fetchIdRef.current += 1
    const fetchId = fetchIdRef.current
    fetchStoryboard()
      .then((data) => {
        if (fetchIdRef.current !== fetchId) return
        setState({ status: 'success', data })
      })
      .catch((err) => {
        if (fetchIdRef.current !== fetchId) return
        setState({
          status: 'error',
          error: err instanceof Error ? err.message : String(err),
        })
      })
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  return { state, refetch }
}
