import { describe, expect, it, vi } from 'vitest'
import { subscribeTaskEvents } from './events'

class MockEventSource extends EventTarget {
  static instances: MockEventSource[] = []
  url: string
  closed = false

  constructor(url: string) {
    super()
    this.url = url
    MockEventSource.instances.push(this)
  }

  close() {
    this.closed = true
  }

  emit(type: string, payload: unknown) {
    this.dispatchEvent(new MessageEvent(type, { data: JSON.stringify(payload) }))
  }
}

describe('subscribeTaskEvents', () => {
  it('routes log item and completion events', () => {
    vi.stubGlobal('EventSource', MockEventSource)
    const onLog = vi.fn()
    const onItemUpdated = vi.fn()
    const onTaskCompleted = vi.fn()

    const source = subscribeTaskEvents('task-1', { onLog, onItemUpdated, onTaskCompleted })
    const instance = MockEventSource.instances.at(-1)!

    expect(instance.url).toBe('/api/tasks/task-1/events')

    instance.emit('log', { task_id: 'task-1', message: '等待 2.0 秒后继续请求' })
    instance.emit('item_updated', { task_id: 'task-1', code: '000001', status: 'success' })
    instance.emit('task_completed', { task_id: 'task-1', status: 'completed' })

    expect(onLog).toHaveBeenCalledWith({ task_id: 'task-1', message: '等待 2.0 秒后继续请求' })
    expect(onItemUpdated).toHaveBeenCalledWith({ task_id: 'task-1', code: '000001', status: 'success' })
    expect(onTaskCompleted).toHaveBeenCalledWith({ task_id: 'task-1', status: 'completed' })
    expect((source as unknown as MockEventSource).closed).toBe(true)
  })
})
