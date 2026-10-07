# Madrid booking API: what we know, what to capture

The Madrid municipal sports booking system has no public API. The *Madrid Móvil* app and the
website [deportesweb.madrid.es](https://deportesweb.madrid.es) use the same account (email +
password, linked once to your ID at a sports centre or online). We target the **website**: its
traffic can be inspected from a browser, while the mobile app would need an intercepting proxy and
probably defeats it with certificate pinning.

## Known facts (sources: Ayuntamiento de Madrid, Área Delegada de Deporte)

| Rule | Value |
|---|---|
| One-off tennis rental window | 7 days ahead, **day of play included** → opens on D−6 |
| Opening hour | **unknown**, setting `SLOTBOT_MADRID_OPENS_AT` (default `00:00`) |
| Payment | card, Bizum, or the app's prepaid wallet (*monedero*); free with some *Abono Deporte Madrid* passes |
| Free cancellation | until 24 h before; any booking within 10 min of confirmation |
| No-show penalty | 1st: warning; then 48 h without advance booking (only within 2 h of start) |
| Website stack | ASP.NET WebForms (`__VIEWSTATE`) + AngularJS, login at `/DeportesWeb/login` |

## What `providers/madrid.py` needs

`DeportesWebSession` has three stubs:

1. **Login**: how credentials are posted (form fields, anti-forgery tokens, cookies kept).
2. **Venues**: the list of centres/courts *as the booking system names them*, with the IDs it
   expects. Today venues come from the city's open data (32 centres with tennis courts, with
   coordinates); once we have the booking list we match the two by name to keep coordinates.
3. **Availability** for a date and centre: the request, the response shape, and what it returns
   *before* the window opens (empty? an error?).
4. **Book + pay from wallet**: the request(s) and the success / "already taken" responses.

## Capture session (about 15 minutes, together)

1. Open <https://deportesweb.madrid.es> in the Claude desktop app's browser pane and **sign in
   yourself** (Claude never types your password).
2. Go to court rental → tennis → pick a centre → pick the furthest day offered. Note the date: it
   tells us whether D−6 is already open at the current hour.
3. Pick a slot and continue to the confirmation step **choosing the wallet** as payment. Either stop
   before confirming (we then only miss the final call) or book something you actually want: you can
   cancel free within 10 minutes.
4. Claude reads the network requests from the pane (auth headers and cookies are redacted) and
   writes the adapter, then a dry-run command to check availability without booking.

## Verifying the opening hour

Look at the furthest bookable day at a few times of day (e.g. 23:58 and 00:02, or 08:58 and 09:02):
the hour when D−6 appears is the opening hour. Set it in `.env` as `SLOTBOT_MADRID_OPENS_AT=HH:MM`.
