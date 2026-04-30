export type Market = 'A股' | '港股' | 'auto'
export type ReportType = '年报' | '一季报' | '半年报' | '三季报'
export type TaskStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled'
export type ItemStatus =
  | 'pending'
  | 'searching'
  | 'downloading'
  | 'success'
  | 'failed'
  | 'skipped'

export interface CreateTaskRequest {
  codes: string[]
  market_mode: Market
  years: number[]
  report_types: ReportType[]
  save_dir: string
  request_interval_seconds: number
  concurrency: number
  auto_slowdown: boolean
  overwrite_existing: boolean
}

export interface TaskItem {
  id: string
  code: string
  market: Market
  year: number
  report_type: ReportType
  status: ItemStatus
  message: string
  name?: string
  file_path?: string
  file_size?: number
  announcement_title?: string
  pdf_url?: string
}

export interface TaskStats {
  total: number
  success: number
  failed: number
  skipped: number
  pending: number
}

export interface TaskDetail {
  id: string
  status: TaskStatus
  items: TaskItem[]
  stats: TaskStats
}

export interface TaskLogEvent {
  time: string
  level: 'debug' | 'info' | 'warn' | 'error'
  task_id: string
  code?: string
  message: string
}

export interface ItemUpdatedEvent {
  task_id: string
  item_id?: string
  code: string
  year?: number
  report_type?: string
  status: ItemStatus
  message?: string
  name?: string
  file_path?: string
  file_size?: number
}

export interface TaskCompletedEvent {
  task_id: string
  status: TaskStatus
}

export interface ReportCandidate {
  code: string
  market: Market
  name?: string
  sec_name?: string
  year: number
  report_type: ReportType
  announcement_title: string
  pdf_url: string
  announcement_date: string
  score: number
}

export interface SearchReportsRequest {
  code: string
  market: Market
  year: number
  report_type: ReportType
}

export interface AppSettings {
  request_interval_seconds?: number
  default_request_interval_seconds?: number
  concurrency?: number
  auto_slowdown?: boolean
  default_save_dir?: string
}
