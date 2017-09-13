// Mirrors the Pydantic models exposed by the FastAPI backend.

export type Priority = 'low' | 'medium' | 'high'

export type JobStatus = 'queued' | 'transcribing' | 'processing' | 'completed' | 'failed'

export interface Decision {
  id: string
  summary: string
  rationale: string | null
  made_by: string | null
}

export interface ActionItem {
  id: string
  description: string
  owner: string | null
  due_date: string | null
  due_text: string | null
  priority: Priority
  done: boolean
}

export interface Minutes {
  title: string
  meeting_date: string
  attendees: string[]
  summary: string
  key_points: string[]
  decisions: Decision[]
  action_items: ActionItem[]
  review_notes: string[]
}

export interface Job {
  id: string
  status: JobStatus
  stage: string | null
  progress: number
  title: string | null
  source: string
  error: string | null
  has_minutes: boolean
  created_at: string
  updated_at: string
}

export interface ExportedIssue {
  action_item_id: string
  key: string
  url: string
}

export interface ExportResult {
  target: string
  content: string | null
  content_type: string | null
  issues: ExportedIssue[]
  skipped: string[]
}

export interface Health {
  status: string
  version: string
  llm: string
  transcriber: string
  exporters: string[]
}

export type ActionItemPatch = Partial<Pick<ActionItem, 'description' | 'owner' | 'due_date' | 'priority' | 'done'>>

export interface UploadOptions {
  title?: string
  meetingDate?: string
  attendees?: string
}
