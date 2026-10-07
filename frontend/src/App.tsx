import { useState } from 'react'
import { PlusIcon } from 'lucide-react'
import { useMeta, useProfiles } from '@/api/hooks'
import { BookingsPanel } from '@/components/BookingsPanel'
import { ProfileSettings } from '@/components/ProfileSettings'
import { VenuesPanel } from '@/components/VenuesPanel'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

export default function App() {
  const profiles = useProfiles()
  const meta = useMeta()
  const [selected, setSelected] = useState<number | 'new' | null>(null)
  const list = profiles.data ?? []
  const current = selected === 'new' ? null : (list.find((p) => p.id === selected) ?? list[0] ?? null)
  const creating = selected === 'new' || (profiles.isSuccess && list.length === 0)

  return (
    <div className="min-h-svh bg-muted/40">
      <header className="border-b bg-background">
        <div className="mx-auto flex max-w-6xl items-baseline justify-between gap-4 px-4 py-4">
          <div>
            <h1 className="text-lg font-semibold">slotbot</h1>
            <p className="text-sm text-muted-foreground">
              Books public courts the moment they open, straight from your calendar.
            </p>
          </div>
          {meta.data && <span className="text-xs text-muted-foreground">triggers: {meta.data.triggers}</span>}
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-6 md:grid-cols-[200px_1fr]">
        <nav className="grid content-start gap-1">
          {list.map((p) => (
            <button
              key={p.id}
              onClick={() => setSelected(p.id)}
              className={cn(
                'rounded-md px-3 py-2 text-left text-sm hover:bg-background',
                !creating && current?.id === p.id && 'bg-background font-medium shadow-sm',
              )}
            >
              {p.name}
            </button>
          ))}
          <Button variant="ghost" className="justify-start" onClick={() => setSelected('new')}>
            <PlusIcon /> New profile
          </Button>
        </nav>

        {creating ? (
          <ProfileSettings key="new" profile={null} onSaved={setSelected} onDeleted={() => setSelected(null)} />
        ) : current ? (
          <Tabs defaultValue="bookings" key={current.id}>
            <TabsList>
              <TabsTrigger value="bookings">Bookings</TabsTrigger>
              <TabsTrigger value="venues">Courts</TabsTrigger>
              <TabsTrigger value="settings">Settings</TabsTrigger>
            </TabsList>
            <TabsContent value="bookings">
              <BookingsPanel profileId={current.id} />
            </TabsContent>
            <TabsContent value="venues">
              <VenuesPanel profileId={current.id} />
            </TabsContent>
            <TabsContent value="settings">
              <ProfileSettings profile={current} onSaved={setSelected} onDeleted={() => setSelected(null)} />
            </TabsContent>
          </Tabs>
        ) : null}
      </main>
    </div>
  )
}
