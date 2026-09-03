const API = '/api'

export async function runAudit(file, useAi = true) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${API}/audit?use_ai=${useAi}`, { method: 'POST', body: fd })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Audit failed')
  }
  return res.json()
}

export async function downloadPdf(file, useAi = true) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${API}/audit/report/pdf?use_ai=${useAi}`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error('Report generation failed')
  return res.blob()
}

export async function confirmMapping(rawLine, category) {
  const res = await fetch(`${API}/train/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ raw_line: rawLine, category }),
  })
  if (!res.ok) throw new Error('Confirm failed')
  return res.json()
}

export async function rejectMapping(rawLine, suggestedCategory, confidence) {
  const res = await fetch(`${API}/train/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ raw_line: rawLine, suggested_category: suggestedCategory, confidence }),
  })
  if (!res.ok) throw new Error('Reject failed')
  return res.json()
}

export async function fetchCategories() {
  const res = await fetch(`${API}/categories`)
  return (await res.json()).categories
}

export async function fetchCacheStats() {
  const res = await fetch(`${API}/cache/stats`)
  return res.json()
}

export async function fetchPatterns() {
  const res = await fetch(`${API}/cache/patterns`)
  return (await res.json()).patterns
}

export async function fetchAiStatus() {
  const res = await fetch(`${API}/ai/status`)
  return res.json()
}

export async function fetchSamples() {
  const res = await fetch(`${API}/samples`)
  return (await res.json()).samples
}

export async function fetchSampleFile(name) {
  const res = await fetch(`${API}/samples/${encodeURIComponent(name)}/download`)
  if (!res.ok) throw new Error('Could not load sample')
  return new File([await res.blob()], name, { type: 'text/plain' })
}
