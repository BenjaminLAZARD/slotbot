const dateTime = new Intl.DateTimeFormat('en-GB', {
  weekday: 'short',
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})
const timeOnly = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

export const when = (iso: string) => dateTime.format(new Date(iso))
export const clock = (iso: string) => timeOnly.format(new Date(iso))

/** "in 3 days", "in 4 hours", "5 minutes ago" */
export function fromNow(iso: string): string {
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['day', 86_400],
    ['hour', 3_600],
    ['minute', 60],
  ]
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit)
  }
  return relative.format(Math.round(seconds), 'second')
}
