import type { ItemUpdatedEvent, TaskCompletedEvent, TaskLogEvent } from './types'

export interface TaskEventHandlers {
  onLog: (event: TaskLogEvent) => void
  onItemUpdated: (event: ItemUpdatedEvent) => void
  onTaskCompleted: (event: TaskCompletedEvent) => void
  onError?: () => void
}

export function subscribeTaskEvents(
  taskId: string,
  handlers: TaskEventHandlers,
): EventSource {
  const source = new EventSource(`/api/tasks/${taskId}/events`)

  source.addEventListener('log', (event) => {
    handlers.onLog(JSON.parse((event as MessageEvent).data))
  })

  source.addEventListener('item_updated', (event) => {
    handlers.onItemUpdated(JSON.parse((event as MessageEvent).data))
  })

  source.addEventListener('task_completed', (event) => {
    handlers.onTaskCompleted(JSON.parse((event as MessageEvent).data))
    source.close()
  })

  source.onerror = () => {
    handlers.onError?.()
  }

  return source
}
