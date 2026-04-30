import { Clock3, Minus, Plus } from 'lucide-react'
import { useState } from 'react'

export interface RequestSettingsValue {
  request_interval_seconds: number
  concurrency: number
  auto_slowdown: boolean
}

interface RequestSettingsProps {
  value: RequestSettingsValue
  onChange: (value: RequestSettingsValue) => void
  disabled?: boolean
}

export function RequestSettings({ value, onChange, disabled }: RequestSettingsProps) {
  const [error, setError] = useState('')

  function update(next: Partial<RequestSettingsValue>) {
    onChange({ ...value, ...next })
  }

  function validate() {
    if (value.request_interval_seconds < 1) {
      setError('请求间隔不能低于 1 秒')
      return false
    }

    setError('')
    return true
  }

  return (
    <section className="tool-section request-settings" aria-labelledby="request-settings-title">
      <div className="section-heading">
        <Clock3 className="section-icon" size={17} />
        <h2 id="request-settings-title">请求设置</h2>
      </div>

      <div className="setting-row">
        <label htmlFor="request-interval">请求间隔</label>
        <strong>{value.request_interval_seconds.toFixed(1)} 秒</strong>
      </div>
      <input
        id="request-interval"
        aria-label="请求间隔"
        type="range"
        min="1"
        max="10"
        step="0.5"
        value={value.request_interval_seconds}
        disabled={disabled}
        onChange={(event) => update({ request_interval_seconds: Number(event.target.value) })}
      />

      <div className="setting-row">
        <span>并发数</span>
        <div className="stepper">
          <button
            type="button"
            aria-label="减少并发数"
            disabled={disabled || value.concurrency <= 1}
            onClick={() => update({ concurrency: value.concurrency - 1 })}
          >
            <Minus size={14} />
          </button>
          <span aria-label="并发数">{value.concurrency}</span>
          <button
            type="button"
            aria-label="增加并发数"
            disabled={disabled || value.concurrency >= 3}
            onClick={() => {
              if (value.concurrency < 3) {
                update({ concurrency: value.concurrency + 1 })
              }
            }}
          >
            <Plus size={14} />
          </button>
        </div>
      </div>

      <label className="checkbox-row">
        <input
          type="checkbox"
          aria-label="遇到限流自动降速"
          checked={value.auto_slowdown}
          disabled={disabled}
          onChange={(event) => update({ auto_slowdown: event.target.checked })}
        />
        遇到限流自动降速
      </label>

      <button
        type="button"
        className="sr-only"
        aria-label="创建批量任务前校验请求设置"
        onClick={validate}
      >
        校验
      </button>

      {error ? <p className="field-error">{error}</p> : null}
    </section>
  )
}
