import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchVoice, type VoiceState } from '@/api/voice'

export type VoiceFetchState =
  | { status: 'loading' }
  | { status: 'error'; error: string }
  | { status: 'success'; data: VoiceState }

/** Fetch + refetch for the project voice config (M3). Same
 * generation-counter pattern as useSegments/useStoryboard. */
export function useVoice(): {
  state: VoiceFetchState
  refetch: () => void
  /** Replace state directly with a server response (PUT/upload
   * responses return the new VoiceState — saves a round-trip). */
  apply: (data: VoiceState) => void
} {
  const [state, setState] = useState<VoiceFetchState>({ status: 'loading' })
  const fetchIdRef = useRef(0)

  const refetch = useCallback(() => {
    fetchIdRef.current += 1
    const fetchId = fetchIdRef.current
    fetchVoice()
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

  const apply = useCallback((data: VoiceState) => {
    fetchIdRef.current += 1
    setState({ status: 'success', data })
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  return { state, refetch, apply }
}
