import { useEffect, useState } from 'react'
import {
  fetchArtifact,
  type ArtifactResponse,
  type PhaseNumber,
} from '@/api/project'

export type ArtifactFetchState =
  | { status: 'loading' }
  | { status: 'success'; data: ArtifactResponse }
  | { status: 'error'; error: string }

export function useArtifact(phase: PhaseNumber): ArtifactFetchState {
  const [state, setState] = useState<ArtifactFetchState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    fetchArtifact(phase)
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
  }, [phase])

  return state
}
