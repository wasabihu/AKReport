import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, createTask } from './client'

describe('api client', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('sends create task payload with snake_case fields', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ data: { task_id: 'task-1', status: 'pending' }, message: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await createTask({
      codes: ['000001'],
      market_mode: 'auto',
      years: [2024],
      report_types: ['年报'],
      save_dir: '/tmp/reports',
      request_interval_seconds: 2,
      concurrency: 1,
      auto_slowdown: true,
      overwrite_existing: false,
    })

    expect(fetchMock).toHaveBeenCalledWith('/api/tasks', expect.objectContaining({
      method: 'POST',
      body: expect.stringContaining('request_interval_seconds'),
    }))
  })

  it('throws ApiError for backend error payloads', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'invalid_rate_limit', message: '请求间隔不能低于 1 秒' } }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await expect(createTask({
      codes: ['000001'],
      market_mode: 'auto',
      years: [2024],
      report_types: ['年报'],
      save_dir: '/tmp/reports',
      request_interval_seconds: 0.5,
      concurrency: 1,
      auto_slowdown: true,
      overwrite_existing: false,
    })).rejects.toMatchObject(new ApiError('请求间隔不能低于 1 秒', 'invalid_rate_limit', 400))
  })
})
