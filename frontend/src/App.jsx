import { useEffect, useState } from 'react'
import { checkHealth, getConfig } from './api'
import AddRepoForm from './components/AddRepoForm'
import Chat from './components/Chat'
import IndexProgress from './components/IndexProgress'
import RepoPicker from './components/RepoPicker'

const STORAGE_KEY = 'repopilot.repoId'

const BADGE_STYLES = {
  checking: 'bg-slate-100 text-slate-600',
  online: 'bg-emerald-100 text-emerald-700',
  offline: 'bg-red-100 text-red-700',
}

export default function App() {
  const [apiStatus, setApiStatus] = useState('checking')
  const [demoMode, setDemoMode] = useState(false)
  const [readyRepo, setReadyRepo] = useState(null)
  const [repoId, setRepoId] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved ? Number(saved) : null
  })

  useEffect(() => {
    checkHealth()
      .then(() => setApiStatus('online'))
      .catch(() => setApiStatus('offline'))
    getConfig()
      .then((config) => setDemoMode(Boolean(config.demo_mode)))
      .catch(() => {})
  }, [])

  function chooseRepo(id) {
    setReadyRepo(null)
    setRepoId(id)
    if (id === null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, String(id))
  }

  let screen
  if (repoId === null) {
    screen = (
      <>
        <h2 className="text-4xl font-bold tracking-tight">Understand any unfamiliar codebase.</h2>
        <p className="mb-8 mt-3 text-lg text-slate-600">
          {demoMode
            ? 'Pick a repository, ask questions in plain English, and get answers that cite the exact lines of code.'
            : 'Paste a GitHub repository. Ask questions in plain English and get answers that cite the exact lines of code.'}
        </p>
        {demoMode ? <RepoPicker onPicked={chooseRepo} /> : <AddRepoForm onAdded={chooseRepo} />}
      </>
    )
  } else if (readyRepo) {
    screen = <Chat repo={readyRepo} onReset={() => chooseRepo(null)} />
  } else {
    screen = (
      <IndexProgress repoId={repoId} onReset={() => chooseRepo(null)} onReady={setReadyRepo} />
    )
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-3xl px-6 py-12">
        <header className="flex items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight">RepoPilot</h1>
          <span className={`rounded-full px-3 py-1 text-sm font-medium ${BADGE_STYLES[apiStatus]}`}>
            API: {apiStatus === 'checking' ? 'waking up…' : apiStatus}
          </span>
        </header>
        <div className="mt-14">{screen}</div>
      </div>
    </main>
  )
}