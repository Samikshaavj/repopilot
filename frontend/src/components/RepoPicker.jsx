import { useEffect, useState } from 'react'
import { listRepos } from '../api'

export default function RepoPicker({ onPicked }) {
  const [repos, setRepos] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    listRepos()
      .then(setRepos)
      .catch((err) => setError(err.message))
  }, [])

  if (error) {
    return (
      <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
        {error}
      </p>
    )
  }
  if (repos === null) return <p className="text-slate-500">Loading repositories…</p>
  if (repos.length === 0) {
    return <p className="text-slate-500">No repositories are available yet.</p>
  }

  return (
    <ul className="grid gap-4 sm:grid-cols-2">
      {repos.map((repo) => (
        <li key={repo.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-lg font-semibold">{repo.name}</h3>
          <p className="mt-1 text-sm text-slate-500">
            {repo.files} files · {repo.symbols} functions and classes
          </p>
          <button
            onClick={() => onPicked(repo.id)}
            className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
          >
            Explore
          </button>
        </li>
      ))}
    </ul>
  )
}