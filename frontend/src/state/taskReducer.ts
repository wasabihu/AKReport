import type {
  ItemUpdatedEvent,
  TaskDetail,
  TaskItem,
  TaskLogEvent,
  TaskStats,
  TaskStatus,
} from '../api/types'

interface TaskState {
  currentTaskId?: string
  status: TaskStatus | 'idle'
  items: TaskItem[]
  logs: TaskLogEvent[]
  stats: TaskStats
  rateLimitNotice?: string
}

type TaskAction =
  | { type: 'task_created'; taskId: string }
  | { type: 'task_loaded'; task: TaskDetail }
  | { type: 'log_received'; log: TaskLogEvent }
  | { type: 'item_updated'; item: Partial<ItemUpdatedEvent> }
  | { type: 'task_completed'; status: TaskStatus }
  | { type: 'reset' }

export const initialTaskState: TaskState = {
  status: 'idle',
  items: [],
  logs: [],
  stats: {
    total: 0,
    success: 0,
    failed: 0,
    skipped: 0,
    pending: 0,
  },
}

function computeStats(items: TaskItem[]): TaskStats {
  return {
    total: items.length,
    success: items.filter((item) => item.status === 'success').length,
    failed: items.filter((item) => item.status === 'failed').length,
    skipped: items.filter((item) => item.status === 'skipped').length,
    pending: items.filter((item) =>
      ['pending', 'searching', 'downloading'].includes(item.status),
    ).length,
  }
}

export function taskReducer(state: TaskState, action: TaskAction): TaskState {
  switch (action.type) {
    case 'task_created':
      return {
        ...initialTaskState,
        currentTaskId: action.taskId,
        status: 'pending',
      }
    case 'task_loaded':
      return {
        ...state,
        currentTaskId: action.task.id,
        status: action.task.status,
        items: action.task.items,
        stats: action.task.stats,
        // Preserve logs from SSE, don't overwrite
      }
    case 'log_received': {
      const isRateLimitNotice =
        action.log.message.includes('请求间隔') || action.log.message.includes('自动降速')

      return {
        ...state,
        logs: [...state.logs, action.log],
        rateLimitNotice: isRateLimitNotice ? action.log.message : state.rateLimitNotice,
      }
    }
    case 'item_updated': {
      const items = state.items.map((item) => {
        const matchById = action.item.item_id && item.id === action.item.item_id
        const matchByComposite =
          !action.item.item_id &&
          action.item.code &&
          item.code === action.item.code &&
          (action.item.year == null || item.year === action.item.year) &&
          (action.item.report_type == null || item.report_type === action.item.report_type)

        return matchById || matchByComposite
          ? {
              ...item,
              status: action.item.status ?? item.status,
              message: action.item.message ?? item.message,
              // Also update file_path / file_size / name if provided (fetched from backend)
              ...(action.item.file_path != null ? { file_path: action.item.file_path } : {}),
              ...(action.item.file_size != null ? { file_size: action.item.file_size } : {}),
              ...(action.item.name != null ? { name: action.item.name } : {}),
            }
          : item
      })

      return {
        ...state,
        items,
        stats: computeStats(items),
      }
    }
    case 'task_completed':
      return {
        ...state,
        status: action.status,
      }
    case 'reset':
      return initialTaskState
    default:
      return state
  }
}
