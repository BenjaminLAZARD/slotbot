import { RefreshCwIcon } from 'lucide-react'
import { useRefreshVenues, useVenues } from '@/api/hooks'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

export function VenuesPanel({ profileId }: { profileId: number }) {
  const venues = useVenues(profileId)
  const refresh = useRefreshVenues(profileId)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Courts in range</CardTitle>
        <CardDescription>
          From your home address, closest first. Bike time is estimated (straight line × 1.3 at your
          speed). Each event uses its own location when it has one. The list refreshes after every
          booking, or now:
        </CardDescription>
        <CardAction>
          <Button variant="outline" size="sm" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
            <RefreshCwIcon className={refresh.isPending ? 'animate-spin' : ''} />
            Refresh from provider
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {venues.error ? (
          <Alert>
            <AlertTitle>Can't rank courts yet</AlertTitle>
            <AlertDescription>{venues.error.message}</AlertDescription>
          </Alert>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8">#</TableHead>
                <TableHead>Venue</TableHead>
                <TableHead>Address</TableHead>
                <TableHead className="text-right">By bike</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(venues.data ?? []).map((v, i) => (
                <TableRow key={v.id}>
                  <TableCell className="text-muted-foreground">{i + 1}</TableCell>
                  <TableCell className="font-medium">{v.name}</TableCell>
                  <TableCell className="text-muted-foreground">{v.address}</TableCell>
                  <TableCell className="text-right tabular-nums">{v.minutes} min</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
