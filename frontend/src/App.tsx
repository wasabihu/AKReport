import {
  Download,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  ListPlus,
  RotateCcw,
  Search,
  ShieldCheck,
  Trash2,
  Zap,
} from 'lucide-react'
import { useEffect, useReducer, useState } from 'react'
import { browseSaveDirectory, createTask, getTask, retryFailedTaskItems, searchReports, getSettings, updateSettings, importExcel } from './api/client'
import { subscribeTaskEvents } from './api/events'
import type { Market, ReportType, TaskLogEvent, ReportCandidate } from './api/types'
import { RequestSettings, type RequestSettingsValue } from './components/RequestSettings'
import { initialTaskState, taskReducer } from './state/taskReducer'
import { parseStockCodes } from './utils/codeInput'
import { getFallbackSaveDir } from './utils/platform'
import './App.css'

const reportTypes: ReportType[] = ['年报', '一季报', '半年报', '三季报']
const marketModes: { label: string; value: Market }[] = [
  { label: '自动识别', value: 'auto' },
  { label: 'A 股', value: 'A股' },
  { label: '港股', value: '港股' },
]

const defaultSaveDir = getFallbackSaveDir()

interface BatchStock {
  code: string
  name?: string
  market?: string
}

function nowLog(message: string, level: TaskLogEvent['level'] = 'info'): TaskLogEvent {
  return {
    time: new Date().toISOString(),
    level,
    task_id: 'local',
    message,
  }
}

function App() {
  const [activeTab, setActiveTab] = useState<'single' | 'batch'>('single')
  const [singleCode, setSingleCode] = useState('')
  const [batchStocks, setBatchStocks] = useState<BatchStock[]>([])
  const [selectedBatchCodes, setSelectedBatchCodes] = useState<Set<string>>(new Set())
  const [marketMode, setMarketMode] = useState<Market>('auto')
  const [yearMode, setYearMode] = useState<'single' | 'recent5' | 'recent10'>('single')
  const [singleYear, setSingleYear] = useState(new Date().getFullYear() - 1)

  /** 根据 yearMode 计算出要传给后端的 years 数组 */
  const resolveYears = (): number[] => {
    const current = new Date().getFullYear()
    if (yearMode === 'recent5') {
      return Array.from({ length: 5 }, (_, i) => current - 1 - i)
    }
    if (yearMode === 'recent10') {
      return Array.from({ length: 10 }, (_, i) => current - 1 - i)
    }
    return [singleYear]
  }
  const [selectedReportTypes, setSelectedReportTypes] = useState<ReportType[]>(['年报'])
  const [saveDir, setSaveDir] = useState(defaultSaveDir)
  const [requestSettings, setRequestSettings] = useState<RequestSettingsValue>({
    request_interval_seconds: 2,
    concurrency: 1,
    auto_slowdown: true,
  })
  const [formError, setFormError] = useState('')
  const [searchResults, setSearchResults] = useState<ReportCandidate[]>([])
  const [searching, setSearching] = useState(false)
  const [browsingSaveDir, setBrowsingSaveDir] = useState(false)
  const [taskState, dispatch] = useReducer(taskReducer, initialTaskState)
  const isRunning = taskState.status === 'pending' || taskState.status === 'running'

  // Load settings from backend on mount
  useEffect(() => {
    getSettings()
      .then((res) => {
        const s = res.data
        setRequestSettings({
          request_interval_seconds: s.request_interval_seconds ?? s.default_request_interval_seconds ?? 2,
          concurrency: s.concurrency ?? 1,
          auto_slowdown: s.auto_slowdown ?? true,
        })
        if (s.default_save_dir) setSaveDir(s.default_save_dir)
      })
      .catch(() => {
        // Use defaults if backend settings unavailable
      })
  }, [])

  // Debounced save settings to backend
  useEffect(() => {
    if (isRunning) return
    const timer = setTimeout(() => {
      updateSettings({
        request_interval_seconds: requestSettings.request_interval_seconds,
        concurrency: requestSettings.concurrency,
        auto_slowdown: requestSettings.auto_slowdown,
        default_save_dir: saveDir,
      }).catch(() => {
        // Best effort
      })
    }, 1000)
    return () => clearTimeout(timer)
  }, [requestSettings, saveDir, isRunning])

  function addBatchStocks(stocks: BatchStock[]) {
    setBatchStocks((current) => {
      const seen = new Set(current.map((stock) => stock.code))
      const next = [...current]

      for (const stock of stocks) {
        if (!seen.has(stock.code)) {
          seen.add(stock.code)
          next.push(stock)
        }
      }

      return next
    })
  }

  function toggleBatchSelection(code: string) {
    setSelectedBatchCodes((current) => {
      const next = new Set(current)
      if (next.has(code)) {
        next.delete(code)
      } else {
        next.add(code)
      }
      return next
    })
  }

  function deleteSelectedBatchStocks() {
    setBatchStocks((current) => current.filter((stock) => !selectedBatchCodes.has(stock.code)))
    setSelectedBatchCodes(new Set())
  }

  function clearBatchStocks() {
    setBatchStocks([])
    setSelectedBatchCodes(new Set())
  }

  function toggleReportType(reportType: ReportType) {
    if (isRunning) {
      return
    }

    setSelectedReportTypes((current) =>
      current.includes(reportType)
        ? current.filter((item) => item !== reportType)
        : [...current, reportType],
    )
  }

  function addSingleToBatch() {
    try {
      const [code] = parseStockCodes(singleCode)
      if (!code) {
        setFormError('请输入股票代码')
        return
      }
      addBatchStocks([{ code }])
      setActiveTab('batch')
      setFormError('')
    } catch (error) {
      setFormError(error instanceof Error ? error.message : '股票代码格式错误')
    }
  }

  async function handleSearch() {
    try {
      const [code] = parseStockCodes(singleCode)
      if (!code) {
        setFormError('请输入股票代码')
        return
      }
      if (!selectedReportTypes.length) {
        setFormError('至少选择一种报告类型')
        return
      }
      setFormError('')
      setSearching(true)
      setSearchResults([])
      dispatch({ type: 'log_received', log: nowLog(`正在搜索 ${code}...`) })

      // Search each report type
      const all: ReportCandidate[] = []
      const searchYears = resolveYears()
      for (const rt of selectedReportTypes) {
        for (const y of searchYears) {
          const res = await searchReports({
            code,
            market: marketMode,
            year: y,
            report_type: rt,
          })
          all.push(...res.data)
        }
      }
      setSearchResults(all)
      dispatch({ type: 'log_received', log: nowLog(`搜索完成，找到 ${all.length} 条公告`) })
    } catch (error) {
      dispatch({
        type: 'log_received',
        log: nowLog(error instanceof Error ? error.message : '搜索失败', 'error'),
      })
    } finally {
      setSearching(false)
    }
  }

  async function startTask(mode: 'single' | 'batch') {
    try {
      const codes = mode === 'single' ? parseStockCodes(singleCode) : batchStocks.map((stock) => stock.code)
      if (!codes.length) {
        setFormError('请先添加股票代码')
        return
      }
      if (!selectedReportTypes.length) {
        setFormError('至少选择一种报告类型')
        return
      }
      if (requestSettings.request_interval_seconds < 1) {
        setFormError('请求间隔不能低于 1 秒')
        return
      }

      setFormError('')
      dispatch({ type: 'log_received', log: nowLog('正在创建下载任务') })

      const response = await createTask({
        codes,
        market_mode: marketMode,
        years: resolveYears(),
        report_types: selectedReportTypes,
        save_dir: saveDir,
        request_interval_seconds: requestSettings.request_interval_seconds,
        concurrency: requestSettings.concurrency,
        auto_slowdown: requestSettings.auto_slowdown,
        overwrite_existing: false,
      })

      dispatch({ type: 'task_created', taskId: response.data.task_id })

      // Fetch initial items so SSE item_updated can match by item_id
      try {
        const taskDetail = await getTask(response.data.task_id)
        dispatch({ type: 'task_loaded', task: taskDetail.data })
      } catch {
        // Non-critical: SSE will still push updates
      }

      subscribeTaskEvents(response.data.task_id, {
        onLog: (event) => dispatch({ type: 'log_received', log: event }),
        onItemUpdated: (item) => dispatch({ type: 'item_updated', item }),
        onTaskCompleted: async (event) => {
          dispatch({ type: 'task_completed', status: event.status })
          // Refresh full task detail to get final file_path/name/stats
          try {
            const taskDetail = await getTask(response.data.task_id)
            dispatch({ type: 'task_loaded', task: taskDetail.data })
          } catch {
            // Best effort
          }
        },
        onError: () =>
          dispatch({
            type: 'log_received',
            log: nowLog('日志连接断开，正在等待后端恢复', 'warn'),
          }),
      })
    } catch (error) {
      dispatch({
        type: 'log_received',
        log: nowLog(error instanceof Error ? error.message : '任务创建失败', 'error'),
      })
    }
  }

  async function browseSaveDir() {
    if (browsingSaveDir) {
      return
    }

    setBrowsingSaveDir(true)
    try {
      const res = await browseSaveDirectory()
      if (res.data.cancelled) {
        return
      }

      const nextDir = res.data.default_save_dir
      if (nextDir) {
        setSaveDir(nextDir)
        setFormError('')
        dispatch({ type: 'log_received', log: nowLog(`保存目录已设置为 ${nextDir}`) })
      }
    } catch (error) {
      const fallback = window.prompt('系统目录选择器不可用，请输入保存目录的完整路径', saveDir)
      if (fallback == null) {
        return
      }

      const trimmed = fallback.trim()
      if (!trimmed) {
        setFormError('保存目录不能为空')
        return
      }

      setSaveDir(trimmed)
      setFormError('')
      dispatch({
        type: 'log_received',
        log: nowLog(error instanceof Error ? `已手动设置保存目录：${trimmed}` : `保存目录已设置为 ${trimmed}`, 'warn'),
      })
    } finally {
      setBrowsingSaveDir(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div className="brand">
          <Zap size={24} fill="currentColor" />
          <span>财报 PDF 下载工具</span>
        </div>
        <nav aria-label="主导航">
          <button type="button" className="nav-item active">
            PDF下载
          </button>
          <button type="button" className="nav-item">
            年份匹配
          </button>
          <button type="button" className="nav-item support">
            <ShieldCheck size={16} />
            支持
          </button>
        </nav>
      </header>

      <div className="workspace">
        <aside className="left-panel">
          <section className="tool-section query-card">
            <div className="tab-list" role="tablist" aria-label="查询模式">
              <button
                type="button"
                className={activeTab === 'single' ? 'tab active' : 'tab'}
                onClick={() => setActiveTab('single')}
              >
                单股查询
              </button>
              <button
                type="button"
                className={activeTab === 'batch' ? 'tab active' : 'tab'}
                onClick={() => setActiveTab('batch')}
              >
                多股查询
              </button>
            </div>

            {activeTab === 'single' ? (
              <div className="query-body">
                <label className="field-label" htmlFor="single-code">
                  股票代码
                </label>
                <input
                  id="single-code"
                  value={singleCode}
                  disabled={isRunning}
                  placeholder="例：000001 / 00700"
                  onChange={(event) => setSingleCode(event.target.value)}
                />
                <div className="hint-box">
                  请输入 A 股 6 位代码或港股 1-5 位代码，港股会由后端规范化。
                </div>
                <div className="button-row">
                  <button type="button" className="ghost-button" disabled={isRunning || searching} onClick={addSingleToBatch}>
                    <ListPlus size={16} />
                    加入批量列表
                  </button>
                  <button type="button" className="ghost-button" disabled={isRunning || searching} onClick={handleSearch}>
                    <Search size={16} />
                    {searching ? '搜索中...' : '搜索预览'}
                  </button>
                  <button type="button" className="primary-button" disabled={isRunning} onClick={() => startTask('single')}>
                    <Download size={16} />
                    直接下载
                  </button>
                </div>
              </div>
            ) : (
              <div className="query-body">
                <div className="batch-list-heading">
                  批量股票列表 ({batchStocks.length})
                </div>
                <div className="batch-list" role="listbox" aria-label="批量股票列表">
                  {batchStocks.length ? (
                    batchStocks.map((stock) => {
                      const selected = selectedBatchCodes.has(stock.code)
                      return (
                        <button
                          type="button"
                          className={`batch-stock-row ${selected ? 'selected' : ''}`}
                          key={stock.code}
                          aria-pressed={selected}
                          disabled={isRunning}
                          onClick={() => toggleBatchSelection(stock.code)}
                        >
                          <span className="stock-code">{stock.code}</span>
                          <span className="stock-name">{stock.name || '未命名'}</span>
                          <span className="stock-market">{stock.market || '自动'}</span>
                        </button>
                      )
                    })
                  ) : (
                    <div className="batch-empty">请导入 Excel，或在单股查询中加入批量列表</div>
                  )}
                </div>
                <div className="import-row">
                  <label className={`ghost-button batch-action ${isRunning ? 'disabled' : ''}`} htmlFor="excel-upload">
                    <FileSpreadsheet size={16} />
                    导入 Excel/CSV
                  </label>
                  <a className={`ghost-button batch-action ${isRunning ? 'disabled' : ''}`} href="/api/import/template" download>
                    模板下载
                  </a>
                  <input
                    id="excel-upload"
                    type="file"
                    accept=".xlsx,.xls,.csv"
                    disabled={isRunning}
                    style={{ display: 'none' }}
                    onChange={async (event) => {
                      const file = event.target.files?.[0]
                      if (!file) return
                      try {
                        const res = await importExcel(file)
                        addBatchStocks(res.data.codes)
                        dispatch({
                          type: 'log_received',
                          log: nowLog(`导入成功：${res.data.count} 条股票代码`, 'info'),
                        })
                      } catch (error) {
                        dispatch({
                          type: 'log_received',
                          log: nowLog(error instanceof Error ? error.message : '导入失败', 'error'),
                        })
                      }
                      event.target.value = ''
                    }}
                  />
                  <button
                    type="button"
                    className="danger-button"
                    disabled={isRunning || selectedBatchCodes.size === 0}
                    onClick={deleteSelectedBatchStocks}
                  >
                    删除选中
                  </button>
                  <button
                    type="button"
                    className="danger-button"
                    disabled={isRunning || batchStocks.length === 0}
                    onClick={clearBatchStocks}
                  >
                    清空全部
                  </button>
                  <button
                    type="button"
                    className="primary-button batch-download"
                    disabled={isRunning || batchStocks.length === 0}
                    onClick={() => startTask('batch')}
                  >
                    <Download size={16} />
                    批量下载
                  </button>
                </div>
              </div>
            )}
            {formError ? <p className="field-error">{formError}</p> : null}
          </section>

          <section className="tool-section">
            <div className="section-heading">
              <FileText className="section-icon" size={17} />
              <h2>报告设置</h2>
            </div>
            <div className="compact-grid">
              <label>
                年份范围
                <select
                  value={yearMode}
                  disabled={isRunning}
                  onChange={(event) => setYearMode(event.target.value as 'single' | 'recent5' | 'recent10')}
                >
                  <option value="single">近1年（{new Date().getFullYear() - 1}）</option>
                  <option value="recent5">近5年</option>
                  <option value="recent10">近10年</option>
                </select>
              </label>
              {yearMode === 'single' && (
                <label>
                  指定年份
                  <input
                    type="number"
                    value={singleYear}
                    disabled={isRunning}
                    min="1990"
                    max={new Date().getFullYear()}
                    onChange={(event) => setSingleYear(Number(event.target.value))}
                  />
                </label>
              )}
              <label>
                市场
                <select
                  value={marketMode}
                  disabled={isRunning}
                  onChange={(event) => setMarketMode(event.target.value as Market)}
                >
                  {marketModes.map((market) => (
                    <option key={market.value} value={market.value}>
                      {market.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="segmented" aria-label="报告类型">
              {reportTypes.map((reportType) => (
                <button
                  type="button"
                  key={reportType}
                  className={selectedReportTypes.includes(reportType) ? 'selected' : ''}
                  disabled={isRunning}
                  onClick={() => toggleReportType(reportType)}
                >
                  {reportType}
                </button>
              ))}
            </div>
          </section>

          <RequestSettings
            value={requestSettings}
            disabled={isRunning}
            onChange={setRequestSettings}
          />

          <section className="tool-section">
            <div className="section-heading">
              <FolderOpen className="section-icon" size={17} />
              <h2>保存目录</h2>
            </div>
            <input
              value={saveDir}
              disabled={isRunning}
              onChange={(event) => setSaveDir(event.target.value)}
            />
            <button
              type="button"
              className="ghost-button browse-button"
              disabled={isRunning || browsingSaveDir}
              onClick={browseSaveDir}
              title="选择保存目录"
            >
              {browsingSaveDir ? '选择中...' : '浏览'}
            </button>
            <p className="fine-print">后端会在任务开始前检查目录可写性。</p>
          </section>
        </aside>

        <section className="main-panel">
          <div className="panel-header">
            <h2>下载日志</h2>
            <button type="button" className="ghost-button small" onClick={() => dispatch({ type: 'reset' })}>
              <Trash2 size={15} />
              清空
            </button>
          </div>
          <div className="log-panel" aria-live="polite">
            {taskState.logs.length ? (
              taskState.logs.map((log, index) => (
                <div className={`log-line ${log.level}`} key={`${log.time}-${index}`}>
                  <span>{new Date(log.time).toLocaleTimeString()}</span>
                  <strong>{log.level.toUpperCase()}</strong>
                  <p>{log.code ? `${log.code} ` : ''}{log.message}</p>
                </div>
              ))
            ) : (
              <div className="empty-state">就绪，请添加股票或导入列表</div>
            )}
          </div>

          {searchResults.length > 0 && (
            <>
              <div className="panel-header result-header">
                <h2>搜索结果</h2>
                <button type="button" className="ghost-button small" onClick={() => setSearchResults([])}>
                  <Trash2 size={15} />
                  关闭
                </button>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>代码</th>
                      <th>名称</th>
                      <th>年份</th>
                      <th>类型</th>
                      <th>公告标题</th>
                      <th>公告日期</th>
                      <th>匹配分</th>
                    </tr>
                  </thead>
                  <tbody>
                    {searchResults.map((r, i) => (
                      <tr key={`${r.code}-${r.year}-${r.report_type}-${i}`}>
                        <td>{r.code}</td>
                        <td>{r.name}</td>
                        <td>{r.year}</td>
                        <td>{r.report_type}</td>
                        <td title={r.announcement_title}>{r.announcement_title.slice(0, 30)}{r.announcement_title.length > 30 ? '...' : ''}</td>
                        <td>{r.announcement_date}</td>
                        <td>{r.score.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <div className="panel-header result-header">
            <h2>任务结果</h2>
            <button type="button" className="ghost-button small" disabled={!taskState.currentTaskId} onClick={async () => {
              if (!taskState.currentTaskId) return
              try {
                await retryFailedTaskItems(taskState.currentTaskId)
                dispatch({ type: 'log_received', log: nowLog('正在重试失败项...') })
              } catch (e) {
                dispatch({ type: 'log_received', log: nowLog(e instanceof Error ? e.message : '重试失败', 'error') })
              }
            }}>
              <RotateCcw size={15} />
              重试失败
            </button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>状态</th>
                  <th>代码</th>
                  <th>市场</th>
                  <th>年份</th>
                  <th>类型</th>
                  <th>文件大小</th>
                  <th>消息</th>
                  <th>文件路径</th>
                </tr>
              </thead>
              <tbody>
                {taskState.items.length ? (
                  taskState.items.map((item) => (
                    <tr key={item.id}>
                      <td><span className={`status-pill ${item.status}`}>{item.status}</span></td>
                      <td>{item.code}</td>
                      <td>{item.market}</td>
                      <td>{item.year}</td>
                      <td>{item.report_type}</td>
                      <td>{item.file_size != null ? `${(item.file_size / 1024 / 1024).toFixed(1)}M` : '-'}</td>
                      <td>{item.message}</td>
                      <td className="path-cell" title={item.file_path ?? ''}>{item.file_path ?? '-'}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={8} className="table-empty">暂无任务结果</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <footer className="status-bar">
        <span>状态：{taskState.status === 'idle' ? '就绪' : taskState.status}</span>
        <span>成功 {taskState.stats.success}</span>
        <span>失败 {taskState.stats.failed}</span>
        <span>跳过 {taskState.stats.skipped}</span>
        <span>
          请求间隔 {requestSettings.request_interval_seconds.toFixed(1)} 秒
          {taskState.rateLimitNotice ? `，${taskState.rateLimitNotice}` : ''}
        </span>
      </footer>
    </main>
  )
}

export default App
