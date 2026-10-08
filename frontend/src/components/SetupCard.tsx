import { CheckIcon, CircleIcon } from 'lucide-react'
import type { Profile } from '@/api/client'
import { useCheckCalendar, useCheckLogin, useMeta } from '@/api/hooks'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

/** Shown until the profile can actually book: each step is verified against Google / the booking site. */
export function SetupCard({ profile, onOpenSettings }: { profile: Profile; onOpenSettings: () => void }) {
  const meta = useMeta()
  const checkCalendar = useCheckCalendar(profile.id)
  const checkLogin = useCheckLogin(profile.id)
  const provider = meta.data?.providers.find((p) => p.key === profile.config.provider)
  const needsAccount = (provider?.credential_fields.length ?? 0) > 0
  const accountReady = !needsAccount || profile.login_ok
  if (profile.calendar_ok && profile.config.home && accountReady) return null

  const steps = [
    { done: profile.calendar_ok, label: 'Calendar reachable by the bot (shared with it)' },
    { done: Boolean(profile.config.home), label: 'Home area set' },
    ...(needsAccount
      ? [
          { done: profile.has_credentials, label: `${provider?.label ?? 'Booking site'} account stored` },
          { done: profile.login_ok, label: 'Login tested' },
        ]
      : []),
  ]

  return (
    <Card className="border-primary/40">
      <CardHeader>
        <CardTitle>Finish setup</CardTitle>
        <CardDescription>
          {profile.calendar_ok ? 'The bot can read your calendar.' : (
            <>
              Share your calendar with <code className="rounded bg-muted px-1">{meta.data?.service_account_email}</code>{' '}
              ("Make changes to events"), then test it.
            </>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <ul className="grid gap-1 text-sm">
          {steps.map((s) => (
            <li key={s.label} className="flex items-center gap-2">
              {s.done ? (
                <CheckIcon className="size-4 text-primary" />
              ) : (
                <CircleIcon className="size-4 text-muted-foreground" />
              )}
              <span className={s.done ? '' : 'text-muted-foreground'}>{s.label}</span>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2">
          {!profile.calendar_ok && (
            <Button onClick={() => checkCalendar.mutate()} disabled={checkCalendar.isPending}>
              {checkCalendar.isPending ? 'Reading calendar…' : 'Test calendar'}
            </Button>
          )}
          {needsAccount && !profile.has_credentials && <Button onClick={onOpenSettings}>Add your account</Button>}
          {needsAccount && profile.has_credentials && !profile.login_ok && (
            <Button onClick={() => checkLogin.mutate()} disabled={checkLogin.isPending}>
              {checkLogin.isPending ? 'Logging in…' : 'Test login'}
            </Button>
          )}
          <Button variant="outline" onClick={onOpenSettings}>
            Edit settings
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
