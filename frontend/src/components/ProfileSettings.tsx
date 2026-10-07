import { useState, type ReactNode } from 'react'
import type { Profile, ProfileConfig } from '@/api/client'
import { useCheckLogin, useDeleteProfile, useMeta, useSaveProfile, useSetCredentials } from '@/api/hooks'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'

const DEFAULTS: ProfileConfig = {
  calendar_id: '',
  provider: 'madrid-tennis',
  home: '',
  max_bike_minutes: 30,
  bike_kmh: 15,
  weekday: { before_minutes: 0, after_minutes: null },
  weekend: { before_minutes: 120, after_minutes: 120 },
  titles: {
    candidate: 'Candidate Tennis',
    pending: 'Pending Tennis',
    success: 'Success - Tennis',
    failure: 'Failure - Tennis',
  },
  lookahead_days: 30,
}

type Props = { profile: Profile | null; onSaved: (id: number) => void; onDeleted: () => void }

export function ProfileSettings({ profile, onSaved, onDeleted }: Props) {
  const meta = useMeta()
  const save = useSaveProfile()
  const remove = useDeleteProfile()
  const [name, setName] = useState(profile?.name ?? 'Me')
  const [cfg, setCfg] = useState<ProfileConfig>(profile?.config ?? DEFAULTS)
  const set = <K extends keyof ProfileConfig>(key: K, value: ProfileConfig[K]) =>
    setCfg((c) => ({ ...c, [key]: value }))
  const provider = meta.data?.providers.find((p) => p.key === cfg.provider)

  const submit = () =>
    save.mutate({ id: profile?.id, body: { name, config: cfg } }, { onSuccess: (p) => onSaved(p.id) })

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <CardTitle>{profile ? 'Settings' : 'New profile'}</CardTitle>
          <CardDescription>One profile = one calendar watched for one booking site.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Profile name">
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Booking site">
              <Select value={cfg.provider} onValueChange={(v) => set('provider', v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {meta.data?.providers.map((p) => (
                    <SelectItem key={p.key} value={p.key}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>

          <Field
            label="Google Calendar ID"
            hint={
              <>
                In Google Calendar: your calendar → Settings and sharing → "Integrate calendar" → Calendar ID.
                Then, under "Share with specific people", add{' '}
                <code className="rounded bg-muted px-1">{meta.data?.service_account_email || '(service account not configured)'}</code>{' '}
                with "Make changes to events".
              </>
            }
          >
            <Input
              value={cfg.calendar_id}
              placeholder="abc123@group.calendar.google.com"
              onChange={(e) => set('calendar_id', e.target.value)}
            />
          </Field>

          <Separator />
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Home (fallback origin)" hint="Used when an event has no location. Address or 'lat, lon'.">
              <Input value={cfg.home} placeholder="Chamberí, Madrid" onChange={(e) => set('home', e.target.value)} />
            </Field>
            <Field label="Max minutes by bike">
              <NumberInput value={cfg.max_bike_minutes} onChange={(v) => set('max_bike_minutes', v ?? 30)} />
            </Field>
            <Field label="Bike speed (km/h)">
              <NumberInput value={cfg.bike_kmh} onChange={(v) => set('bike_kmh', v ?? 15)} />
            </Field>
          </div>

          <Separator />
          <div className="grid gap-4 sm:grid-cols-2">
            <FlexFields title="Weekdays" value={cfg.weekday} onChange={(v) => set('weekday', v)} />
            <FlexFields title="Weekends" value={cfg.weekend} onChange={(v) => set('weekend', v)} />
          </div>

          <Separator />
          <div className="grid gap-4 sm:grid-cols-4">
            {(['candidate', 'pending', 'success', 'failure'] as const).map((k) => (
              <Field key={k} label={`${k[0].toUpperCase()}${k.slice(1)} title`}>
                <Input
                  value={cfg.titles[k]}
                  onChange={(e) => set('titles', { ...cfg.titles, [k]: e.target.value })}
                />
              </Field>
            ))}
          </div>
        </CardContent>
        <CardFooter className="justify-between">
          {profile ? (
            <Button
              variant="ghost"
              className="text-destructive"
              onClick={() => confirm(`Delete "${profile.name}" and its history?`) && remove.mutate(profile.id, { onSuccess: onDeleted })}
            >
              Delete profile
            </Button>
          ) : (
            <span />
          )}
          <Button onClick={submit} disabled={save.isPending}>
            {profile ? 'Save' : 'Create profile'}
          </Button>
        </CardFooter>
      </Card>

      {profile && provider && provider.credential_fields.length > 0 && (
        <CredentialsCard profile={profile} fields={provider.credential_fields} label={provider.label} />
      )}
      <ConstraintsHelp candidate={cfg.titles.candidate} />
    </div>
  )
}

function CredentialsCard({ profile, fields, label }: { profile: Profile; fields: string[]; label: string }) {
  const setCredentials = useSetCredentials(profile.id)
  const checkLogin = useCheckLogin(profile.id)
  const [values, setValues] = useState<Record<string, string>>({})
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {label} account {profile.has_credentials && <Badge variant="secondary">stored</Badge>}
        </CardTitle>
        <CardDescription>
          Write-only: encrypted in the database, never sent back to this page. Pay from the site's wallet,
          so keep it topped up.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => (
          <Field key={f} label={f[0].toUpperCase() + f.slice(1)}>
            <Input
              type={f.includes('password') ? 'password' : 'text'}
              autoComplete="off"
              value={values[f] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [f]: e.target.value }))}
            />
          </Field>
        ))}
      </CardContent>
      <CardFooter className="justify-end gap-2">
        <Button
          variant="ghost"
          disabled={!profile.has_credentials || checkLogin.isPending}
          onClick={() => checkLogin.mutate()}
        >
          {checkLogin.isPending ? 'Logging in…' : 'Test login'}
        </Button>
        <Button
          variant="outline"
          disabled={setCredentials.isPending || fields.some((f) => !values[f])}
          onClick={() => setCredentials.mutate(values, { onSuccess: () => setValues({}) })}
        >
          {profile.has_credentials ? 'Replace credentials' : 'Store credentials'}
        </Button>
      </CardFooter>
    </Card>
  )
}

function ConstraintsHelp({ candidate }: { candidate: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Writing a candidate event</CardTitle>
        <CardDescription>
          Title must contain "{candidate}". The event's time is the slot you want; its location is where you
          ride from. Optional lines in the description narrow things down:
        </CardDescription>
      </CardHeader>
      <CardContent>
        <pre className="rounded-md bg-muted p-3 text-sm">
          {`earliest: 18:00        # overrides the weekday/weekend window
latest: 21:30
only: Chopera, Gallur   # venue name contains one of these
avoid: Casa de Campo
max_bike: 20            # minutes, for this event only`}
        </pre>
      </CardContent>
    </Card>
  )
}

function FlexFields({
  title,
  value,
  onChange,
}: {
  title: string
  value: ProfileConfig['weekday']
  onChange: (v: ProfileConfig['weekday']) => void
}) {
  return (
    <fieldset className="grid grid-cols-2 gap-3">
      <legend className="col-span-2 mb-1 text-sm font-medium">{title}</legend>
      <Field label="Earlier by (min)">
        <NumberInput value={value.before_minutes} onChange={(v) => onChange({ ...value, before_minutes: v ?? 0 })} />
      </Field>
      <Field label="Later by (min)" hint="Empty = any later slot">
        <NumberInput value={value.after_minutes ?? null} onChange={(v) => onChange({ ...value, after_minutes: v })} />
      </Field>
    </fieldset>
  )
}

function NumberInput({ value, onChange }: { value: number | null; onChange: (v: number | null) => void }) {
  return (
    <Input
      type="number"
      min={0}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
    />
  )
}

function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid content-start gap-1.5">
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}
