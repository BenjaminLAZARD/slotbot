import { Fragment, useState } from 'react'
import { RefreshCwIcon, RotateCcwIcon } from 'lucide-react'
import type { Booking } from '@/api/client'
import { useBookings, useRetry, useSync } from '@/api/hooks'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { clock, fromNow, when } from '@/lib/format'

const STATUS: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  booked: 'default',
  pending: 'secondary',
  racing: 'outline',
  failed: 'destructive',
  cancelled: 'outline',
}

export function BookingsPanel({ profileId }: { profileId: number }) {
  const bookings = useBookings(profileId)
  const sync = useSync(profileId)
  const rows = bookings.data ?? []
  const next = rows.filter((b) => b.status === 'pending' || b.status === 'racing').at(-1)

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Next booking</CardTitle>
          <CardDescription>
            The bot reads your calendar daily, picks the next candidate event and wakes up a few minutes
            before its booking window opens.
          </CardDescription>
          <CardAction>
            <Button variant="outline" size="sm" disabled={sync.isPending} onClick={() => sync.mutate(false)}>
              <RefreshCwIcon className={sync.isPending ? 'animate-spin' : ''} />
              Sync calendar now
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          {next ? (
            <dl className="grid gap-4 sm:grid-cols-3">
              <Fact label="Event" value={next.title} hint={when(next.play_start)} />
              <Fact label="Booking opens" value={when(next.opens_at)} hint={fromNow(next.opens_at)} />
              <Fact
                label="Bot wakes up"
                value={when(next.trigger_at)}
                hint={next.status === 'racing' ? 'racing now…' : fromNow(next.trigger_at)}
              />
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">
              Nothing planned. Add an event whose title contains your candidate marker, then sync.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>History</CardTitle>
          <CardDescription>Every race, with each attempt in the order it was made.</CardDescription>
        </CardHeader>
        <CardContent>
          {rows.length ? (
            <HistoryTable rows={rows} profileId={profileId} />
          ) : (
            <p className="text-sm text-muted-foreground">No bookings yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function Fact({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground uppercase">{label}</dt>
      <dd className="font-medium">{value}</dd>
      <dd className="text-sm text-muted-foreground">{hint}</dd>
    </div>
  )
}

function HistoryTable({ rows, profileId }: { rows: Booking[]; profileId: number }) {
  const [open, setOpen] = useState<number | null>(null)
  const retry = useRetry(profileId)

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Play time</TableHead>
          <TableHead>Event</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Result</TableHead>
          <TableHead className="text-right">Attempts</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((b) => (
          <Fragment key={b.id}>
            <TableRow className="cursor-pointer" onClick={() => setOpen(open === b.id ? null : b.id)}>
              <TableCell>{when(b.play_start)}</TableCell>
              <TableCell className="max-w-48 truncate">{b.title}</TableCell>
              <TableCell>
                <Badge variant={STATUS[b.status] ?? 'outline'}>{b.status}</Badge>
              </TableCell>
              <TableCell className="max-w-72 truncate">{summary(b)}</TableCell>
              <TableCell className="text-right">
                {b.status === 'failed' ? (
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={(e) => {
                      e.stopPropagation()
                      retry.mutate(b.id)
                    }}
                  >
                    <RotateCcwIcon /> retry
                  </Button>
                ) : null}
                {b.attempts.length}
              </TableCell>
            </TableRow>
            {open === b.id && (
              <TableRow>
                <TableCell colSpan={5} className="bg-muted/40">
                  <Attempts booking={b} />
                </TableCell>
              </TableRow>
            )}
          </Fragment>
        ))}
      </TableBody>
    </Table>
  )
}

function Attempts({ booking }: { booking: Booking }) {
  if (!booking.attempts.length) return <p className="text-sm text-muted-foreground">No attempts recorded.</p>
  return (
    <ol className="grid gap-1 font-mono text-xs">
      {booking.attempts.map((a, i) => (
        <li key={i}>
          {clock(String(a.at))} · {String(a.venue)} {a.start ? clock(String(a.start)).slice(0, 5) : ''} →{' '}
          <span className={a.outcome === 'booked' ? 'font-semibold' : ''}>{String(a.outcome)}</span>
          {a.detail ? <span className="text-muted-foreground"> ({String(a.detail)})</span> : null}
        </li>
      ))}
    </ol>
  )
}

function summary(b: Booking): string {
  const r = b.result ?? {}
  if (b.status === 'booked') return `${r.venue} · ${when(String(r.start))}`
  if (r.reason) return String(r.reason)
  return b.status === 'pending' ? `opens ${fromNow(b.opens_at)}` : ''
}
