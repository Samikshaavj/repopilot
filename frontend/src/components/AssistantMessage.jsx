import Answer from './Answer'

function Spinner() {
  return (
    <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700" />
  )
}

export default function AssistantMessage({ message, onCite }) {
  const waiting = message.answer === null && message.error === null
  return (
    <div className="space-y-3">
      {message.steps.length > 0 && (
        <ul className="space-y-1 text-sm text-slate-500">
          {message.steps.map((label, index) => {
            const isLast = index === message.steps.length - 1
            return (
              <li key={index} className="flex items-center gap-2">
                {waiting && isLast ? <Spinner /> : <span className="text-emerald-600">✓</span>}
                {label}
              </li>
            )
          })}
        </ul>
      )}

      {waiting && message.steps.length === 0 && (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Spinner /> Thinking…
        </div>
      )}

      {message.error && (
        <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          {message.error}
        </p>
      )}

      {message.answer !== null && (
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <Answer text={message.answer} onCite={onCite} />
          {message.limited && (
            <p className="mt-4 text-xs text-amber-700">
              The assistant ran out of steps, so this answer may be incomplete.
            </p>
          )}
        </div>
      )}
    </div>
  )
}