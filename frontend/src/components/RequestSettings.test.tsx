import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { RequestSettings, type RequestSettingsValue } from './RequestSettings'

const defaultValue: RequestSettingsValue = {
  request_interval_seconds: 2,
  concurrency: 1,
  auto_slowdown: true,
}

describe('RequestSettings', () => {
  it('renders safe defaults', () => {
    render(<RequestSettings value={defaultValue} onChange={vi.fn()} />)

    expect(screen.getByLabelText('请求间隔')).toHaveValue('2')
    expect(screen.getByText('2.0 秒')).toBeInTheDocument()
    expect(screen.getByLabelText('并发数')).toHaveTextContent('1')
    expect(screen.getByLabelText('遇到限流自动降速')).toBeChecked()
  })

  it('shows validation when interval is below one second', async () => {
    const user = userEvent.setup()
    render(
      <RequestSettings
        value={{ ...defaultValue, request_interval_seconds: 0.5 }}
        onChange={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: '创建批量任务前校验请求设置' }))

    expect(screen.getByText('请求间隔不能低于 1 秒')).toBeInTheDocument()
  })

  it('does not increase concurrency above three', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <RequestSettings
        value={{ ...defaultValue, concurrency: 3 }}
        onChange={onChange}
      />,
    )

    await user.click(screen.getByRole('button', { name: '增加并发数' }))

    expect(onChange).not.toHaveBeenCalled()
  })
})
