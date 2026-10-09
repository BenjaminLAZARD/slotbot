import type { ReactNode } from 'react'
import { BellIcon, CalendarPlusIcon, MapPinnedIcon, TimerIcon } from 'lucide-react'
import type { Session } from '@/api/client'
import { GoogleButton } from '@/components/GoogleButton'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const STEPS = [
  {
    icon: CalendarPlusIcon,
    title: 'Mark the slot',
    text: 'Create an event titled “Candidate Tennis” at the time you want to play. Optional lines in its description narrow it down, e.g. “earliest: 18:00” or “avoid: Eva Duarte”.',
  },
  {
    icon: MapPinnedIcon,
    title: 'slotbot plans it',
    text: 'Within the hour the event becomes “Pending Tennis” and lists the courts within your bike range, closest first, with the minute booking opens.',
  },
  {
    icon: TimerIcon,
    title: 'It races at midnight',
    text: 'Most courts open six days ahead at midnight. slotbot is signed in a few minutes before, checks every second, and takes the closest court at your time, then nearby times: your time or later on weekdays, ±2 h at weekends.',
  },
  {
    icon: BellIcon,
    title: 'You get the result',
    text: '“Success - Tennis” with the court and receipt in your calendar, or “Failure - Tennis” with every attempt. And an email either way.',
  },
]

const NEEDS = [
  'A Google Calendar you share with the bot (permission “Make changes to events”).',
  'A Madrid Deportes / Madrid Móvil account with money in its wallet (monedero). Card payments need your bank to approve them in its app, which a bot cannot do.',
  'An invitation: slotbot is invite-only for now.',
]

type Props = { session?: Session; onOpenApp?: () => void }

export function Landing({ session, onOpenApp }: Props) {
  const signedIn = session?.signed_in
  const signIn = signedIn ? (
    <Button onClick={onOpenApp}>Open my bookings</Button>
  ) : session?.google_client_id ? (
    <GoogleButton clientId={session.google_client_id} />
  ) : null

  return (
    <div className="min-h-svh bg-background">
      <header className="border-b">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
          <span className="text-lg font-semibold">slotbot</span>
          <nav className="flex items-center gap-4 text-sm text-muted-foreground">
            <a href="#how" className="hover:text-foreground">How it works</a>
            <a href="#privacy" className="hover:text-foreground">Privacy</a>
          </nav>
        </div>
      </header>

      <main className="mx-auto grid max-w-5xl gap-16 px-4 py-12 md:py-20">
        <section className="grid gap-6">
          <p className="text-sm font-medium text-muted-foreground">Madrid municipal tennis courts</p>
          <h1 className="max-w-3xl text-4xl font-semibold tracking-tight md:text-5xl">
            Your court, booked the second it opens.
          </h1>
          <p className="max-w-2xl text-lg text-muted-foreground">
            The city opens most courts six days ahead, at midnight, and the good evening slots go in minutes. Put
            “Candidate Tennis” in your calendar; slotbot books the best court near you, pays from your Madrid wallet and
            writes the result back into the event. No alarm, no refreshing.
          </p>
          <div className="flex flex-wrap items-center gap-4">
            {signIn}
            {!signedIn && <span className="text-sm text-muted-foreground">Invite-only for now.</span>}
          </div>
        </section>

        <section id="how" className="grid scroll-mt-8 gap-6">
          <h2 className="text-2xl font-semibold">How it works</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {STEPS.map(({ icon: Icon, title, text }, i) => (
              <Card key={title}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Icon className="size-5 text-muted-foreground" />
                    {i + 1}. {title}
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">{text}</CardContent>
              </Card>
            ))}
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 md:gap-10">
          <Block title="What you need">
            <ul className="grid list-disc gap-2 pl-5">
              {NEEDS.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </Block>
          <Block title="Good to know">
            <p>
              <strong className="text-foreground">Cost.</strong> slotbot is free. Courts cost the city’s price, paid
              from your own wallet; slotbot never sees a card.
            </p>
            <p>
              <strong className="text-foreground">Cancelling.</strong> Cancel from slotbot or the city’s app; the
              city’s refund rules apply.
            </p>
            <p>
              <strong className="text-foreground">Fair play.</strong> It books only what you put in your calendar,
              within the city’s own limits (two bookings per person per day).
            </p>
            <p>
              <strong className="text-foreground">Independent.</strong> slotbot is a personal project, not affiliated
              with the Ayuntamiento de Madrid.
            </p>
          </Block>
        </section>

        <section id="privacy" className="grid scroll-mt-8 gap-4">
          <h2 className="text-2xl font-semibold">Privacy</h2>
          <div className="grid gap-3 text-sm text-muted-foreground md:max-w-3xl">
            <p>
              <strong className="text-foreground">What is stored.</strong> Your Google name and email, to sign you
              in; your profiles (calendar ID, home area, preferences); your booking-site email and password, encrypted
              with a key only the server holds and used only to sign in to the booking site on your behalf; a log of
              each booking attempt.
            </p>
            <p>
              <strong className="text-foreground">What is read.</strong> Only the calendar you share with the bot,
              and the bot only changes events marked for it.
            </p>
            <p>
              <strong className="text-foreground">Where.</strong> Google Cloud in Madrid, a Neon database in
              Frankfurt, emails sent through Resend.
            </p>
            <p>
              <strong className="text-foreground">Your control.</strong> Deleting a profile deletes its data and
              credentials; stop sharing the calendar and the bot can no longer read it. No ads, no tracking; slotbot sets
              no cookie other than the one that keeps you signed in.
            </p>
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex max-w-5xl flex-wrap justify-between gap-2 px-4 py-6 text-xs text-muted-foreground">
          <span>slotbot · an independent project</span>
          <a href="#privacy" className="hover:text-foreground">Privacy</a>
        </div>
      </footer>
    </div>
  )
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="grid content-start gap-3">
      <h2 className="text-2xl font-semibold">{title}</h2>
      <div className="grid gap-3 text-sm text-muted-foreground">{children}</div>
    </div>
  )
}
