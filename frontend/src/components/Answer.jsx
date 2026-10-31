import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'

const CITATION = /([\w./-]+\.py):(\d+)(?:-(\d+))?/g

// Clean up the model's text, and turn "path:start-end" into a special link we render as a badge.
function prepare(text) {
  return text
    .replace(/`([\w./-]+\.py:\d+(?:-\d+)?)`/g, '$1') // unwrap citations written in backticks
    .replace(/(\d)[\u2010-\u2014](\d)/g, '$1-$2') // fancy dashes inside number ranges
    .replace(/\d+†/g, '') // stray "1†" source numbers some models add
    .replace(/[【】]/g, '') // brackets some models put around citations
    .replace(CITATION, (match, path, start, end) => `[${match}](cite:${path}:${start}-${end ?? start})`)
}

function Citation({ href }) {
  const match = href.match(/^cite:(.+):(\d+)-(\d+)$/)
  if (!match) return href
  const [, path, start, end] = match
  const file = path.split('/').pop()
  const label = start === end ? `${file}:${start}` : `${file}:${start}-${end}`
  return (
    <span
      title={path}
      className="mx-0.5 inline-block rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-700"
    >
      {label}
    </span>
  )
}

const components = {
  a({ href, children }) {
    if (href?.startsWith('cite:')) return <Citation href={href} />
    return (
      <a href={href} target="_blank" rel="noreferrer" className="text-blue-600 underline">
        {children}
      </a>
    )
  },
  p: ({ children }) => <p className="leading-7">{children}</p>,
  ul: ({ children }) => <ul className="list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1 pl-6">{children}</ol>,
  pre: ({ children }) => (
    <pre className="overflow-x-auto rounded-lg bg-slate-900 p-4 text-sm text-slate-100">{children}</pre>
  ),
  code({ className, children }) {
    const isBlock = Boolean(className) || String(children).includes('\n')
    if (isBlock) return <code>{children}</code>
    return <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[0.9em]">{children}</code>
  },
}

// Keep our own "cite:" links; every other link goes through the library's safety filter.
const urlTransform = (url) => (url.startsWith('cite:') ? url : defaultUrlTransform(url))

export default function Answer({ text }) {
  return (
    <div className="space-y-4 text-slate-800">
      <ReactMarkdown components={components} urlTransform={urlTransform}>
        {prepare(text)}
      </ReactMarkdown>
    </div>
  )
}