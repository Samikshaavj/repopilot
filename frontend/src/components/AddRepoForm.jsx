import { useState } from 'react'
import { addRepo } from '../api'

const EXAMPLE = 'https://github.com/pallets/itsdangerous'

export default function AddRepoForm({ onAdded }) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { id } = await addRepo(url.trim())
      onAdded(id)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          type="text"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://github.com/owner/repository"
          disabled={busy}
          className="flex-1 rounded-lg border border-slate-300 bg-white px-4 py-3 text-base shadow-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={busy || url.trim() === ''}
          className="rounded-lg bg-slate-900 px-6 py-3 font-medium text-white shadow-sm hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? 'Starting…' : 'Analyze'}
        </button>
      </div>

      <p className="text-sm text-slate-500">
        Public GitHub repositories only. Python is supported today.{' '}
        <button
          type="button"
          onClick={() => setUrl(EXAMPLE)}
          className="font-medium text-slate-700 underline hover:text-slate-900"
        >
          Try an example
        </button>
      </p>

      {error && (
        <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}