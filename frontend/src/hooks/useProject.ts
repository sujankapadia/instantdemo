import { useCallback, useEffect, useState } from 'react'
import { fetchProject, type ProjectState } from '@/api/project'

export type ProjectFetchState =
  | { status: 'loading' }
  | { status: 'success'; data: ProjectState }
  | { status: 'error'; error: string }

interface UseProjectResult {
  state: ProjectFetchState
  refetch: () => void
}

export function useProject(): UseProjectResult {
  const [state, setState] = useState<ProjectFetchState>({ status: 'loading' })

  const refetch = useCallback(() => {
    setState({ status: 'loading' })
    fetchProject()
      .then((data) => setState({ status: 'success', data }))
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err)
        setState({ status: 'error', error: message })
      })
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  return { state, refetch }
}
