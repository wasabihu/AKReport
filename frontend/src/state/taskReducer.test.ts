import { describe, expect, it } from 'vitest'
import { initialTaskState, taskReducer } from './taskReducer'

describe('taskReducer', () => {
  it('stores task id after creation', () => {
    const state = taskReducer(initialTaskState, { type: 'task_created', taskId: 'task-1' })

    expect(state.currentTaskId).toBe('task-1')
    expect(state.status).toBe('pending')
  })

  it('updates item status by code', () => {
    const loaded = taskReducer(initialTaskState, {
      type: 'task_loaded',
      task: {
        id: 'task-1',
        status: 'running',
        items: [{ id: 'item-1', code: '000001', market: 'A股', year: 2024, report_type: '年报', status: 'downloading', message: '' }],
        stats: { total: 1, success: 0, failed: 0, skipped: 0, pending: 0 },
      },
    })

    const updated = taskReducer(loaded, {
      type: 'item_updated',
      item: { code: '000001', status: 'success', message: '下载完成' },
    })

    expect(updated.items[0]).toMatchObject({ status: 'success', message: '下载完成' })
  })

  it('surfaces auto slowdown notices from logs', () => {
    const state = taskReducer(initialTaskState, {
      type: 'log_received',
      log: {
        time: '2026-04-29T22:10:00+08:00',
        level: 'warn',
        task_id: 'task-1',
        message: '检测到源站繁忙，请求间隔调整为 4.0 秒',
      },
    })

    expect(state.rateLimitNotice).toBe('检测到源站繁忙，请求间隔调整为 4.0 秒')
  })
})
