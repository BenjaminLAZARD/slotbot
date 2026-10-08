# Madrid booking site (deportesweb.madrid.es): how it works

The *Madrid Móvil* app and [deportesweb.madrid.es](https://deportesweb.madrid.es) share one account
(email + password). We automate the **website**. Everything below was captured from a real
logged-in session on 2026-10-07 (read-only: nothing was booked) and is implemented in
`backend/src/slotbot/providers/deportesweb.py` (protocol) and `providers/madrid.py` (mapping).

## Rules (Ayuntamiento de Madrid, Área Delegada de Deporte)

| Rule | Value |
|---|---|
| One-off tennis rental window | 7 days ahead, **day of play included** → opens on D−6 |
| Opening hour | measured with `scripts/probe_madrid_opening.py` (see HISTORY.md); setting `SLOTBOT_MADRID_OPENS_AT` |
| Slots | 60 min, starting at **:30** (08:30 … 20:30 at La Chopera) |
| Payment | card, Bizum, or the in-app wallet (*monedero*); free with some *Abono Deporte Madrid* passes |
| Floodlights | some slots ask "¿Desea que la reserva lleve iluminación?" (paid supplement) |
| Free cancellation | until 24 h before; any booking within 10 min of confirmation |
| No-show penalty | 1st: warning; then 48 h without advance booking |

## Protocol

ASP.NET WebForms with **partial postbacks**. Every action is a `POST` to the current page URL:

```
Headers: X-MicrosoftAjax: Delta=true, X-Requested-With: XMLHttpRequest
Body (form-encoded):
  ctl00$ScriptManager1 = ctl00$<target with _ → $>|<target>
  __EVENTTARGET        = <target>                       e.g. uAlert_uplAlert
  __EVENTARGUMENT      = {"action": "...", "args": ...}  JSON, sometimes with "controlID"
  __VIEWSTATE, __VIEWSTATEGENERATOR, __EVENTVALIDATION   page state, refreshed by every response
  <other form inputs>, __ASYNCPOST = true
```

Responses use ASP.NET AJAX's delta format `length|type|id|content|…`: `updatePanel` (HTML),
`hiddenField` (new page state to send next), `scriptStartupBlock`, `pageRedirect` (URL-encoded).

### Flow

| Step | Target | Argument |
|---|---|---|
| Login page | GET `/DeportesWeb/login` | |
| Choose email login | `ContentFixedSection_uSecciones_uAlert_uplAlert` | `SelectMenu` `{menu_code:"5143", menu_type:29, authentication_provider_code:"4"}` |
| Log in | `ContentFixedSection_uLogin_uAlert_uplAlert` | `Login` `{authentication_provider_code:"4"}` + fields `…$uLogin$txtIdentificador`, `…$uLogin$txtContrasena` → redirect Home |
| (anonymous instead) | same as above | `SelectMenu` `{menu_code:"41042", menu_type:30}` "No identificado" |
| Racket sports | `ContentFixedSection_uSecciones_uAlert_uplAlert` | `SelectSubmenu` `{menu_code:"8597"}` |
| Tennis rental | same | `SelectMenu` `{menu_code:"8598", menu_type:7, submenu_code:"8597"}` → redirect `Modulos/VentaServicios/Alquileres/ReservaEspacios?token=…` |
| Centre list | in that page: tiles `{menuCode:'8598', facilityCode:'52'}` + name + address (33 centres) | |
| Open a centre | `ContentFixedSection_uReservaEspacios_uCentrosSeleccionar_uAlert_uplAlert` | `SelectFacility` `{menu_code:"8598", facility_code, activity:{activity_code:"605"}, date:null}` → usage `{reservation_type_code:"124", "dates":[bookable days]}` |
| Choose usage | `uAlert_uplAlert` | `{controlID:"…_uUsosSeleccionar", action:"Seleccionar", args:<usage>}` |
| Choose day / poll | `uAlert_uplAlert` | `{controlID:"…_uFechaSeleccionar", action:"Continuar", args:"YYYY-MM-DD"}` → grid |
| Book | `uAlert_uplAlert` | `{controlID:"…_uReservaCuadrante", action:"Reservar", args:{personCode}}` + field `…$hdnCuadrante = "+<court>#<HH:MM>#<true|false|?>;"` → redirect `Modulos/VentaServicios/CarritoConfirmar` |
| Pay | `ContentFixedSection_uCarritoConfirmar_uAlert_uplAlert` | `ConfirmCart` `{payment_method_type:"5", payment_method_code:"5"}` (wallet; card is 10/25, Bizum 23/30) → redirect `CarritoResultado` ("Confirmado", `Carrito <n>`, `Operación <n>`) |
| Rentals list | `/Account` → "Alquileres de unidades deportivas" | `Modulos/Alquileres/Alquileres?token=…` |
| Cancel | `uAlert_uplAlert` then `ContentSection_uAlquileres_uCarritosFicha_uAlert_uplAlert` | `{controlID:"ContentSection_uAlquileres", action:"Consultar", args:{cartCode}}`, then `RefundCart {ignorarAdvertencia:false}` (warning) and `RefundCart {ignorarAdvertencia:true}` → "Anulado", refund to the wallet |

Grid cells: free ones carry `celdaCuadrante('<cellId>','<courtCode>','<HH:MM>', …)` (quotes arrive as
`&#39;`) and `blnPreguntarLuz` (asks about floodlights). **A day that is not open yet still renders a
grid** (all cells free, since nobody could book): the reliable "is it open?" signal is the usage's
`dates` list. The anonymous mode sees the centre list and the grids; booking needs the login.

`personCode` is in the page as escaped JSON (`\"person_code\":\"…\"`).

The cart and result pages render themselves with jQuery `.append('text')` literals; the bot reads
those strings (items, `Total`, `Saldo disponible` = wallet balance, `Confirmado`, `Carrito <n>`).

## Payment

Card, Bizum and Google Pay always end in the bank's strong-customer-authentication step (approve in
the banking app), which a bot cannot do. The bot therefore pays **only from the wallet**, which the
user tops up themselves ("Recarga monedero" on Home, any method). Before paying it checks that the
cart holds exactly the slot it reserved and that the balance covers the total; otherwise it stops and
leaves the slot in the cart for the user.

Captured with a real booking on 2026-10-08 (La Chopera, Tenis 2, 12 Oct 16:30, €6.90 from the
wallet), then cancelled and refunded the same minute.

## Not observed yet

What `Reservar` returns when the slot was just taken, and what `ConfirmCart` returns when the wallet
is short: both are handled generically (no redirect → read the alert text → try the next candidate /
report the error).
