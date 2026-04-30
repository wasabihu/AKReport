import type { CreateTaskRequest, TaskDetail, TaskStatus, ReportCandidate, SearchReportsRequest, AppSettings } from './types'

export class ApiError extends Error {
  code?: string
  status?: number

  constructor(message: string, code?: string, status?: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData
  const response = await fetch(`/api${path}`, {
    headers: isFormData
      ? { ...(init?.headers ?? {}) }
      : { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(
      payload?.error?.message ?? `请求失败：${response.status}`,
      payload?.error?.code,
      response.status,
    )
  }

  return response.json() as Promise<T>
}

export function createTask(input: CreateTaskRequest) {
  return apiFetch<{ data: { task_id: string; status: TaskStatus }; message: string }>(
    '/tasks',
    {
      method: 'POST',
      body: JSON.stringify(input),
    },
  )
}

export function getTask(taskId: string) {
  return apiFetch<{ data: TaskDetail; message: string }>(`/tasks/${taskId}`)
}

export function cancelTask(taskId: string) {
  return apiFetch<{ data: TaskDetail; message: string }>(`/tasks/${taskId}/cancel`, {
    method: 'POST',
  })
}

export function retryFailedTaskItems(taskId: string) {
  return apiFetch<{ data: TaskDetail; message: string }>(
    `/tasks/${taskId}/retry-failed`,
    { method: 'POST' },
  )
}

export function searchReports(input: SearchReportsRequest) {
  return apiFetch<{ data: ReportCandidate[]; message: string }>(
    '/reports/search',
    {
      method: 'POST',
      body: JSON.stringify(input),
    },
  )
}

export function getSettings() {
  return apiFetch<{ data: AppSettings; message: string }>('/settings')
}

export function updateSettings(input: Partial<AppSettings>) {
  return apiFetch<{ data: AppSettings; message: string }>(
    '/settings',
    {
      method: 'PUT',
      body: JSON.stringify(input),
    },
  )
}

export function browseSaveDirectory() {
  return apiFetch<{ data: AppSettings & { cancelled?: boolean }; message: string }>(
    '/settings/browse-save-dir',
    { method: 'POST' },
  )
}

export interface ImportedStock {
  code: string
  name: string
  market: string
}

export function importExcel(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return apiFetch<{ data: { codes: ImportedStock[]; count: number }; message: string }>(
    '/import/excel',
    {
      method: 'POST',
      body: formData,
    },
  )
}
