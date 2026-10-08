import { AlarmClockIcon, RefreshCwIcon } from 'lucide-react'
import type { components } from '@/api/schema'
import { useAgenda, useEventAction, useRetry, useSync } from '@/api/hooks'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { fromNow, when } from '@/lib/format'

type Item = components['schemas']['AgendaEventOut']

const STAGE: Record<string, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  candidate: { label: 'candidate', variant: 'outline' },
  pending: { label: 'pending', variant: 'secondary' },
  racing: { label: 'racing…', variant: 'secondary' },
  booked: { label: 'booked', variant: 'default' },
  failed: { label: 'failed', variant: 'destructive' },
  cancelled: { label: 'cancelled', variant: 'outline' },
  other: { label: 'not for the bot', variant: 'outline' },
}

const CONFIRM = {
  cancelBooked: 'Cancel this paid booking on the booking site? The refund goes to your wallet (free until 24 h before).',
  cancel: 'Stop the bot for this event? It will be titled "cancelled" and skipped.',
  reset: 'Make this a fresh candidate? The bot plans it again, and books right away if its booking window is already open.',
}

export function UpcomingPanel({ profileId }: { profileId: number }) {
  const agenda = useAgenda(profileId)
  const sync = useSync(profileId)
  const action = useEventAction(profileId)
  const retry = useRetry(profileId)
  const data = agenda.data
  const next = data?.next_wake

  const run = (item: Item, kind: 'cancel' | 'reset' | 'retry') => {
    const text = kind === 'cancel' ? (item.stage === 'booked' ? CONFIRM.cancelBooked : CONFIRM.cancel) : kind === 'reset' ? CONFIRM.reset : null
    if (text && !confirm(text)) return
    if (kind === 'retry' && item.booking_id) retry.mutate(item.booking_id)
    else if (kind !== 'retry') action.mutate({ eventId: item.event_id, action: kind })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upcoming</CardTitle>
        <CardDescription>The next events in your calendar and what the bot will do with them.</CardDescription>
        <CardAction>
          <Button variant="outline" size="sm" disabled={sync.isPending} onClick={() => sync.mutate(false)}>
            <RefreshCwIcon className={sync.isPending ? 'animate-spin' : ''} />
            Sync calendar now
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 rounded-md bg-muted/50 px-3 py-2 text-sm">
          <span className="flex items-center gap-1.5 font-medium">
            <AlarmClockIcon className="size-4" />
            {next?.wakes_at ? (
              <>
                Bot wakes {when(next.wakes_at)} ({fromNow(next.wakes_at)}) for “{next.title}”
              </>
            ) : (
              'No booking scheduled'
            )}
          </span>
          <span className="text-muted-foreground">
            Next calendar check: {data?.next_sync ? fromNow(data.next_sync) : 'daily (scheduler)'}
          </span>
        </div>

        {agenda.error ? (
          <p className="text-sm text-destructive">{agenda.error.message}</p>
        ) : (data?.events.length ?? 0) === 0 ? (
          <p className="text-sm text-muted-foreground">No upcoming events in this calendar.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Event</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Booking opens</TableHead>
                <TableHead>Court</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data!.events.map((item) => (
                <TableRow key={item.event_id}>
                  <TableCell className="whitespace-nowrap">{when(item.start)}</TableCell>
                  <TableCell className="max-w-48 truncate">{item.title}</TableCell>
                  <TableCell>
                    <Badge variant={STAGE[item.stage]?.variant ?? 'outline'}>{STAGE[item.stage]?.label ?? item.stage}</Badge>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {item.opens_at ? when(item.opens_at) : '—'}
                    {item.wakes_at && <div className="text-xs">bot wakes {fromNow(item.wakes_at)}</div>}
                  </TableCell>
                  <TableCell className="max-w-40 truncate">{item.court ?? '—'}</TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    {item.actions.map((kind) => (
                      <Button
                        key={kind}
                        size="xs"
                        variant={kind === 'cancel' ? 'ghost' : 'outline'}
                        className={kind === 'cancel' ? 'text-destructive' : ''}
                        disabled={action.isPending || retry.isPending}
                        onClick={() => run(item, kind as 'cancel' | 'reset' | 'retry')}
                      >
                        {kind === 'reset' ? (item.stage === 'other' ? 'Make candidate' : 'Reset') : kind[0].toUpperCase() + kind.slice(1)}
                      </Button>
                    ))}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
