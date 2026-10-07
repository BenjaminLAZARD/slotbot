import { CheckIcon, CircleIcon } from 'lucide-react'
import type { Profile } from '@/api/client'
import { useCheckLogin, useMeta } from '@/api/hooks'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

/** Shown until the profile can actually book: what is done, what is missing, one click to fix it. */
export function SetupCard({ profile, onOpenSettings }: { profile: Profile; onOpenSettings: () => void }) {
  const meta = useMeta()
  const checkLogin = useCheckLogin(profile.id)
  const provider = meta.data?.providers.find((p) => p.key === profile.config.provider)
  const needsAccount = (provider?.credential_fields.length ?? 0) > 0
  if (!needsAccount || (profile.has_credentials && checkLogin.isSuccess)) return null

  const steps = [
    { done: Boolean(profile.config.calendar_id), label: 'Calendar ID set (and shared with the bot)' },
    { done: Boolean(profile.config.home), label: 'Home area set' },
    { done: profile.has_credentials, label: `${provider?.label ?? 'Booking site'} account stored` },
    { done: checkLogin.isSuccess, label: 'Login tested' },
  ]

  return (
    <Card className="border-primary/40">
      <CardHeader>
        <CardTitle>Finish setup</CardTitle>
        <CardDescription>The bot can only book once your booking-site account is stored and works.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <ul className="grid gap-1 text-sm">
          {steps.map((s) => (
            <li key={s.label} className="flex items-center gap-2">
              {s.done ? <CheckIcon className="size-4 text-primary" /> : <CircleIcon className="size-4 text-muted-foreground" />}
              <span className={s.done ? '' : 'text-muted-foreground'}>{s.label}</span>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2">
          {!profile.has_credentials ? (
            <Button onClick={onOpenSettings}>Add your account</Button>
          ) : (
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
