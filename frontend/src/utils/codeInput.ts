export function parseStockCodes(input: string): string[] {
  const tokens = input
    .split(/[\s,，;；]+/)
    .map((token) => token.trim())
    .filter(Boolean)

  const seen = new Set<string>()
  const codes: string[] = []

  for (const token of tokens) {
    if (!/^\d+$/.test(token)) {
      throw new Error('股票代码只能包含数字')
    }

    if (!seen.has(token)) {
      seen.add(token)
      codes.push(token)
    }
  }

  return codes
}
