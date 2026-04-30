import { describe, expect, it } from 'vitest'
import { parseStockCodes } from './codeInput'

describe('parseStockCodes', () => {
  it('parses newline comma and space separated codes', () => {
    expect(parseStockCodes('000001\n600519, 00700 09988')).toEqual([
      '000001',
      '600519',
      '00700',
      '09988',
    ])
  })

  it('removes duplicate codes while keeping order', () => {
    expect(parseStockCodes('000001 000001\n00700')).toEqual(['000001', '00700'])
  })

  it('reports non numeric tokens', () => {
    expect(() => parseStockCodes('000001 abc')).toThrow('股票代码只能包含数字')
  })
})
