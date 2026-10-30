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