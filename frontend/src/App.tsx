import { useState } from 'react'
import { LogOutIcon, PlusIcon } from 'lucide-react'
import type { Profile, Session } from '@/api/client'
import { useMeta, useProfiles, useSession, useSignOut } from '@/api/hooks'
import { BookingsPanel } from '@/components/BookingsPanel'
import { Landing } from '@/components/Landing'
import { ProfileSettings } from '@/components/ProfileSettings'
import { VenuesPanel } from '@/components/VenuesPanel'
import { SetupCard } from '@/components/SetupCard'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

export default function App() {
  const session = useSession()
  const [about, setAbout] = useState(false)
  if (session.isPending) return <div className="min-h-svh bg-background" />
  if (!session.data?.signed_in || about) {
    return <Landing session={session.data} onOpenApp={() => setAbout(false)} />
  }
  return <Workspace session={session.data} onAbout={() => setAbout(true)} />
}

function Workspace({ session, onAbout }: { session: Session; onAbout: () => void }) {
  const signOut = useSignOut()
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
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            {meta.data && <span className="hidden text-xs sm:inline">triggers: {meta.data.triggers}</span>}
            <button onClick={onAbout} className="hover:text-foreground">
              About
            </button>
            {session.sign_in_enabled && (
              <>
                <span className="hidden sm:inline">{session.email}</span>
                <Button variant="ghost" size="sm" onClick={() => signOut.mutate()}>
                  <LogOutIcon /> Sign out
                </Button>
              </>
            )}
          </div>
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
          <ProfileView key={current.id} profile={current} onSaved={setSelected} onDeleted={() => setSelected(null)} />
        ) : null}
      </main>
    </div>
  )
}

type ViewProps = { profile: Profile; onSaved: (id: number) => void; onDeleted: () => void }

function ProfileView({ profile, onSaved, onDeleted }: ViewProps) {
  const [tab, setTab] = useState('bookings')
  return (
    <div className="grid content-start gap-4">
      <SetupCard profile={profile} onOpenSettings={() => setTab('settings')} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="w-full">
          <TabsTrigger value="bookings" className="flex-1">Bookings</TabsTrigger>
          <TabsTrigger value="venues" className="flex-1">Courts</TabsTrigger>
          <TabsTrigger value="settings" className="flex-1">Settings &amp; account</TabsTrigger>
        </TabsList>
        <TabsContent value="bookings">
          <BookingsPanel profileId={profile.id} />
        </TabsContent>
        <TabsContent value="venues">
          <VenuesPanel profileId={profile.id} />
        </TabsContent>
        <TabsContent value="settings">
          <ProfileSettings profile={profile} onSaved={onSaved} onDeleted={onDeleted} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
