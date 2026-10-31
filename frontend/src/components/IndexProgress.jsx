import { useEffect, useState } from 'react'
import { getRepo } from '../api'

const STAGES = [
  { key: 'pending', label: 'Queued' },
  { key: 'cloning', label: 'Downloading the repository' },
  { key: 'parsing', label: 'Reading the code' },
  { key: 'embedding', label: 'Understanding it (the slowest step)' },
  { key: 'saving', label: 'Saving the index' },
  { key: 'ready', label: 'Ready' },
]
const IN_PROGRESS = ['pending', 'cloning', 'parsing', 'embedding', 'saving']

function Spinner() {
  return (
    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700" />
  )
}

export default function IndexProgress({ repoId, onReset, onReady }) {
  const [repo, setRepo] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    let timer

    async function poll() {
      try {
        const data = await getRepo(repoId)
        if (cancelled) return
        setRepo(data)
        setError(null)
        if (data.status === 'ready') {
          onReady(data)
        } else if (IN_PROGRESS.includes(data.status)) {
          timer = setTimeout(poll, 2000)
        }
      } catch (err) {
        if (cancelled) return
        if (err.message === 'Repository not found') {
          onReset() // the saved repository no longer exists: go back to the start
          return
        }
        setError(err.message)
        timer = setTimeout(poll, 4000)
      }
    }

    poll()
    // Cleanup: runs when the component disappears or repoId changes.
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId])

  if (!repo) {
    return (
      <div className="flex items-center gap-3 text-slate-600">
        <Spinner /> {error ?? 'Loading…'}
      </div>
    )
  }

  const currentIndex = STAGES.findIndex((stage) => stage.key === repo.status)

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-slate-500">Repository</p>
        <h2 className="text-2xl font-semibold">{repo.name}</h2>
      </div>

      {repo.status === 'failed' ? (
        <div className="rounded-lg bg-red-50 p-5 text-red-800">
          <p className="font-medium">Indexing failed</p>
          <p className="mt-1 text-sm">{repo.error ?? 'Something went wrong.'}</p>
          <button
            onClick={onReset}
            className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
          >
            Try another repository
          </button>
        </div>
      ) : (
        <ol className="space-y-3">
          {STAGES.map((stage, index) => {
            const done = index < currentIndex || repo.status === 'ready'
            const active = index === currentIndex && repo.status !== 'ready'
            return (
              <li
                key={stage.key}
                className={`flex items-center gap-3 ${
                  done || active ? 'text-slate-900' : 'text-slate-400'
                }`}
              >
                <span className="flex h-5 w-5 items-center justify-center">
                  {done ? <span className="text-emerald-600">✓</span> : active ? <Spinner /> : '•'}
                </span>
                {stage.label}
              </li>
            )
          })}
        </ol>
      )}

      {error && repo.status !== 'failed' && (
        <p className="text-sm text-amber-700">Connection problem, retrying… ({error})</p>
      )}
    </div>
  )
}