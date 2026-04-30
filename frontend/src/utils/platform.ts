export function getFallbackSaveDir(platform = navigator.platform): string {
  return /win/i.test(platform) ? 'C:\\reports' : '~/Downloads/reports'
}
