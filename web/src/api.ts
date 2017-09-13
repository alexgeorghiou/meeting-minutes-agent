import type {
  ActionItem,
  ActionItemPatch,
  ExportResult,
  Health,
  Job,
  Minutes,
  UploadOptions,
} from './types'

const BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}/api${path}`, init)
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') {
        detail = body.detail
      } else if (Array.isArray(body.detail)) {
        detail = body.detail.map((d: { msg?: string }) => d.msg ?? '').join('; ')
      }
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export const api = {
  health: () => request<Health>('/health'),

  uploadAudio(file: File, options: UploadOptions = {}): Promise<Job> {
    const form = new FormData()
    form.append('file', file)
    if (options.title) form.append('title', options.title)
    if (options.meetingDate) form.append('meeting_date', options.meetingDate)
    if (options.attendees) form.append('attendees', options.attendees)
    return request<Job>('/jobs', { method: 'POST', body: form })
  },

  submitTranscript(transcript: string, options: UploadOptions = {}): Promise<Job> {
    const attendees = (options.attendees ?? '')
      .split(/[,;]/)
      .map((a) => a.trim())
      .filter(Boolean)
    return request<Job>(
      '/jobs/transcript',
      json('POST', {
        transcript,
        title: options.title || null,
        meeting_date: options.meetingDate || null,
        attendees,
      }),
    )
  },

  job: (id: string) => request<Job>(`/jobs/${id}`),
  jobs: (limit = 10) => request<Job[]>(`/jobs?limit=${limit}`),
  minutes: (id: string) => request<Minutes>(`/jobs/${id}/minutes`),
  saveMinutes: (id: string, minutes: Minutes) =>
    request<Minutes>(`/jobs/${id}/minutes`, json('PUT', minutes)),

  updateActionItem: (jobId: string, itemId: string, patch: ActionItemPatch) =>
    request<ActionItem>(`/jobs/${jobId}/action-items/${itemId}`, json('PATCH', patch)),
  deleteActionItem: (jobId: string, itemId: string) =>
    request<void>(`/jobs/${jobId}/action-items/${itemId}`, { method: 'DELETE' }),

  exporters: () => request<string[]>('/exporters'),
  exportTo: (jobId: string, target: string) =>
    request<ExportResult>(`/jobs/${jobId}/exports/${target}`, { method: 'POST' }),
  markdownUrl: (jobId: string) => `${BASE}/api/jobs/${jobId}/minutes.md`,
}
