import { useEffect, useState } from 'react'
import { checkHealth } from './api'
import AddRepoForm from './components/AddRepoForm'
import IndexProgress from './components/IndexProgress'

const STORAGE_KEY = 'repopilot.repoId'

const BADGE_STYLES = {
  checking: 'bg-slate-100 text-slate-600',
  online: 'bg-emerald-100 text-emerald-700',
  offline: 'bg-red-100 text-red-700',
}

export default function App() {
  const [apiStatus, setApiStatus] = useState('checking')
  const [repoId, setRepoId] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved ? Number(saved) : null
  })

  useEffect(() => {
    checkHealth()
      .then(() => setApiStatus('online'))
      .catch(() => setApiStatus('offline'))
  }, [])

  function chooseRepo(id) {
    setRepoId(id)
    if (id === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, String(id))
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-3xl px-6 py-12">
        <header className="flex items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight">RepoPilot</h1>
          <span className={`rounded-full px-3 py-1 text-sm font-medium ${BADGE_STYLES[apiStatus]}`}>
            API: {apiStatus}
          </span>
        </header>

        <div className="mt-14">
          {repoId === null ? (
            <>
              <h2 className="text-4xl font-bold tracking-tight">
                Understand any unfamiliar codebase.
              </h2>
              <p className="mb-8 mt-3 text-lg text-slate-600">
                Paste a GitHub repository. Ask questions in plain English and get answers that
                cite the exact lines of code.
              </p>
              <AddRepoForm onAdded={chooseRepo} />
            </>
          ) : (
            <IndexProgress repoId={repoId} onReset={() => chooseRepo(null)} />
          )}
        </div>
      </div>
    </main>
  )
}