// Where the backend lives. In production this comes from an environment variable.
const API = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

async function request(path, options) {
  let response
  try {
    response = await fetch(`${API}${path}`, options)
  } catch {
    throw new Error('Cannot reach the server. Is the backend running?')
  }

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data?.detail
    throw new Error(
      typeof detail === 'string' ? detail : 'Please check your input and try again.',
    )
  }
  return data
}

export const checkHealth = () => request('/health')

export const addRepo = (url) =>
  request('/repos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })

export const getRepo = (id) => request(`/repos/${id}`)


// Sends a question and calls onEvent(event) for every event the server streams back.
export async function streamAsk(repoId, question, onEvent, signal) {
  let response
  try {
    response = await fetch(`${API}/repos/${repoId}/ask/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') return
    throw new Error('Cannot reach the server. Is the backend running?')
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'The request failed.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // Events end with a blank line. The last piece may be half-received: keep it.
      const parts = buffer.split('\n\n')
      buffer = parts.pop()
      for (const part of parts) {
        const line = part.split('\n').find((l) => l.startsWith('data: '))
        if (line) onEvent(JSON.parse(line.slice(6)))
      }
    }
  } catch (error) {
    if (error.name !== 'AbortError') {
      throw new Error('The connection was interrupted.')
    }
  }
}

// Lines of a file around start-end (for the code viewer).
export const getFileWindow = (repoId, path, start, end) =>
  request(`/repos/${repoId}/file?${new URLSearchParams({ path, start, end })}`)



// Settings the backend wants the page to know about (for example demo mode).
export const getConfig = () => request('/config')

// Repositories that are indexed (in demo mode, only finished ones).
export const listRepos = () => request('/repos')