import { Fragment, useState } from 'react'
import { RotateCcwIcon } from 'lucide-react'
import type { Booking } from '@/api/client'
import { useBookings, useRetry } from '@/api/hooks'
import { UpcomingPanel } from '@/components/UpcomingPanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
  const rows = bookings.data ?? []

  return (
    <div className="grid gap-6">
      <UpcomingPanel profileId={profileId} />

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
