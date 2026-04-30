import { describe, expect, it } from 'vitest'
import { getFallbackSaveDir } from './platform'

describe('getFallbackSaveDir', () => {
  it('uses C drive reports directory on Windows', () => {
    expect(getFallbackSaveDir('Win32')).toBe('C:\\reports')
  })

  it('uses a user-relative downloads path on non-Windows systems', () => {
    expect(getFallbackSaveDir('MacIntel')).toBe('~/Downloads/reports')
  })
})
