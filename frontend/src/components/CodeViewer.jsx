import { useEffect, useRef, useState } from 'react'
import { getFileWindow } from '../api'

export default function CodeViewer({ repoId, target, onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const highlightRef = useRef(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError(null)
    getFileWindow(repoId, target.path, target.start, target.end)
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [repoId, target])

  // Scroll the highlighted lines into view once the code has loaded.
  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: 'center' })
  }, [data])

  // Escape closes the panel.
  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') closeRef.current()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  let firstHighlighted = true

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Source code"
        onClick={(event) => event.stopPropagation()}
        className="flex h-full w-full max-w-3xl flex-col bg-slate-900 text-slate-100 shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-700 px-5 py-4">
          <div className="min-w-0">
            <p className="truncate font-mono text-sm">{data?.path ?? target.path}</p>
            <p className="mt-1 text-xs text-slate-400">
              {data
                ? `Lines ${target.start}-${data.highlight_end} highlighted · ${data.total_lines} lines in the file`
                : 'Loading…'}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-md px-2 py-1 text-slate-300 hover:bg-slate-700"
          >
            ✕
          </button>
        </header>

        <div className="flex-1 overflow-auto py-3 font-mono text-sm leading-6">
          {error && (
            <p role="alert" className="mx-5 rounded-lg bg-red-950 px-4 py-3 text-red-200">
              {error}
            </p>
          )}
          {!data && !error && <p className="px-5 text-slate-400">Loading the file…</p>}
          {data &&
            data.lines.map((text, index) => {
              const number = data.first_line + index
              const highlighted = number >= data.highlight_start && number <= data.highlight_end
              let ref
              if (highlighted && firstHighlighted) {
                ref = highlightRef
                firstHighlighted = false
              }
              return (
                <div
                  key={number}
                  ref={ref}
                  className={`flex ${highlighted ? 'bg-amber-400/20' : ''}`}
                >
                  <span className="w-14 shrink-0 select-none pr-4 text-right text-slate-500">
                    {number}
                  </span>
                  <span className="whitespace-pre pr-6">{text}</span>
                </div>
              )
            })}
        </div>
      </aside>
    </div>
  )
}