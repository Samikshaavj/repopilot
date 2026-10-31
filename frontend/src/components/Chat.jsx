import { useEffect, useRef, useState } from 'react'
import { streamAsk } from '../api'
import AssistantMessage from './AssistantMessage'
import CodeViewer from './CodeViewer'

const SUGGESTIONS = [
  'Give me an overview of how this project is organised',
  'Where is the main logic, and how does it work?',
  'How are errors handled?',
]

export default function Chat({ repo, onReset }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [viewer, setViewer] = useState(null)
  const nextId = useRef(0)
  const abortRef = useRef(null)
  const bottomRef = useRef(null)

  // Cancel any running request when this screen goes away.
  useEffect(() => () => abortRef.current?.abort(), [])
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function patchAssistant(id, change) {
    setMessages((all) => all.map((m) => (m.id === id ? change(m) : m)))
  }

  async function send(question) {
    const text = question.trim()
    if (!text || busy) return

    const id = ++nextId.current
    setInput('')
    setBusy(true)
    setMessages((all) => [
      ...all,
      { id: `u${id}`, role: 'user', text },
      { id, role: 'assistant', steps: [], answer: null, error: null },
    ])

    abortRef.current = new AbortController()
    let finished = false
    try {
      await streamAsk(
        repo.id,
        text,
        (event) => {
          if (event.type === 'step') {
            patchAssistant(id, (m) => ({ ...m, steps: [...m.steps, event.label] }))
          } else if (event.type === 'answer') {
            finished = true
            patchAssistant(id, (m) => ({
              ...m,
              answer: event.answer,
              limited: event.stopped_at_step_limit,
            }))
          } else if (event.type === 'error') {
            finished = true
            patchAssistant(id, (m) => ({ ...m, error: event.message }))
          }
        },
        abortRef.current.signal,
      )
      if (!finished && !abortRef.current.signal.aborted) {
        patchAssistant(id, (m) => ({ ...m, error: 'The connection closed before an answer arrived.' }))
      }
    } catch (error) {
      patchAssistant(id, (m) => ({ ...m, error: error.message }))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">Repository</p>
          <h2 className="text-2xl font-semibold">{repo.name}</h2>
          <p className="mt-1 text-sm text-slate-500">
            {repo.files} files · {repo.symbols} functions and classes indexed
          </p>
        </div>
        <button
          onClick={onReset}
          className="shrink-0 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-100"
        >
          Change repository
        </button>
      </div>

      {messages.length === 0 && (
        <div className="space-y-2">
          <p className="text-sm text-slate-500">Try asking:</p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => send(suggestion)}
                disabled={busy}
                className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-100 disabled:opacity-50"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-8">
        {messages.map((message) =>
          message.role === 'user' ? (
            <div key={message.id} className="flex justify-end">
              <p className="max-w-[85%] rounded-2xl bg-slate-900 px-4 py-3 text-white">{message.text}</p>
            </div>
          ) : (
            <AssistantMessage key={message.id} message={message} onCite={setViewer} />
          ),
        )}
      </div>
      <div ref={bottomRef} />

      <form
        onSubmit={(event) => {
          event.preventDefault()
          send(input)
        }}
        className="sticky bottom-4 flex gap-3 rounded-xl bg-slate-50 p-2 shadow-lg ring-1 ring-slate-200"
      >
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask about this codebase…"
          maxLength={500}
          disabled={busy}
          className="flex-1 rounded-lg bg-white px-4 py-3 outline-none disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={busy || input.trim() === ''}
          className="rounded-lg bg-slate-900 px-5 py-3 font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? 'Working…' : 'Ask'}
        </button>
      </form>

      {viewer && <CodeViewer repoId={repo.id} target={viewer} onClose={() => setViewer(null)} />}
    </div>
  )
}