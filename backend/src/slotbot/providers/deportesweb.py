"""Low-level client for deportesweb.madrid.es (Ayuntamiento de Madrid sports bookings).

The site is ASP.NET WebForms with "partial postbacks": every user action is a form POST to the
current page carrying the page's hidden state (__VIEWSTATE, __EVENTVALIDATION) plus a JSON
`__EVENTARGUMENT` such as {"action": "SelectFacility", "args": {...}}. The server answers in
ASP.NET AJAX's "delta" format, `length|type|id|content|` repeated: updated HTML panels, new hidden
state to send back next time, scripts, or a redirect. Captured from a real session on 2026-10-07.

Flow for one tennis day:
    login page -> SelectMenu "Correo y contraseña" -> Login            (session cookie)
    Home -> SelectSubmenu "Deportes de raqueta" -> SelectMenu "Pista de tenis" -> redirect
    ReservaEspacios?token=... -> SelectFacility -> Seleccionar (usage) -> Continuar (date) -> grid
    grid: pick cells into hdnCuadrante -> Reservar -> CarritoConfirmar (cart)
    cart: ConfirmCart with the wallet (payment type 5) -> CarritoResultado ("Confirmado")
"""

import html
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import unquote, urljoin

import httpx

BASE = "https://deportesweb.madrid.es/DeportesWeb/"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0 Safari/537.36"
)
_INPUT = re.compile(r"<input\b[^>]*>", re.I)
_ATTR = re.compile(r'([\w:$-]+)="([^"]*)"')
_CELL = re.compile(r"celdaCuadrante\('(\d+)','(\d+)','(\d\d:\d\d)'")

# Menu codes observed on the site (stable identifiers in the city's back office).
MENU_EMAIL_LOGIN = {
    "menu_code": "5143",
    "menu_title": "Correo y contraseña",
    "menu_type": 29,
    "authentication_provider_code": "4",
    "submenu_code": None,
}
MENU_ANONYMOUS = {
    "menu_code": "41042",
    "menu_title": "No identificado",
    "menu_type": 30,
    "authentication_provider_code": None,
    "submenu_code": None,
}
GRID_FIELD = "ctl00$ContentFixedSection$uReservaEspacios$uReservaCuadrante$hdnCuadrante"
MENU_RACKET_SPORTS = {"menu_code": "8597", "menu_title": "Deportes de raqueta"}
TENNIS_MENU_CODE = "8598"
TENNIS_ACTIVITY = {"activity_code": "605", "activity_name": "TENIS"}
# Payment methods on the cart page: card 10/25, Bizum 23/30, wallet ("monedero") 5/5.
WALLET = {"payment_method_type": "5", "payment_method_code": "5"}
_TEXT = re.compile(r"\.append\('((?:[^'\\]|\\.)*)'\)")


class SiteError(Exception):
    """The site answered with an error message or an unexpected page."""


@dataclass
class Delta:
    panels: dict[str, str] = field(default_factory=dict)
    hidden: dict[str, str] = field(default_factory=dict)
    scripts: list[str] = field(default_factory=list)
    redirect: str | None = None
    error: str | None = None

    @property
    def text(self) -> str:
        return "\n".join([*self.panels.values(), *self.scripts])


@dataclass
class Page:
    url: str
    fields: dict[str, str]


@dataclass(frozen=True)
class GridCell:
    cell_id: str
    court_code: str
    court_name: str
    start: str  # "HH:MM"
    asks_light: bool  # the site asks "¿Desea que la reserva lleve iluminación?"


@dataclass(frozen=True)
class Cart:
    """What the cart page shows. Its content is rendered by scripts as `.append('text')` literals."""

    items: int
    total: float | None
    wallet: float | None  # available wallet balance, None if the wallet is not offered
    texts: tuple[str, ...]


def page_texts(page_html: str) -> list[str]:
    """Visible strings of pages that render themselves with jQuery `.append('...')` calls."""
    return [html.unescape(t.replace("\\'", "'")) for t in _TEXT.findall(page_html)]


def euros(text: str | None) -> float | None:
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*€", text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def parse_cart(page_html: str) -> Cart:
    texts = page_texts(page_html)

    def after(label: str) -> str | None:
        return next((texts[i + 1] for i, t in enumerate(texts[:-1]) if t == label), None)

    return Cart(texts.count("Inicio"), euros(after("Total")), euros(after("Saldo disponible")), tuple(texts))


def parse_delta(text: str) -> Delta:
    """Parse ASP.NET AJAX's `length|type|id|content|` response format."""
    delta, i = Delta(), 0
    while i < len(text):
        bar = text.index("|", i)
        length = int(text[i:bar])
        type_end = text.index("|", bar + 1)
        kind = text[bar + 1 : type_end]
        id_end = text.index("|", type_end + 1)
        ident = text[type_end + 1 : id_end]
        content = text[id_end + 1 : id_end + 1 + length]
        i = id_end + 1 + length + 1
        if kind == "updatePanel":
            delta.panels[ident] = content
        elif kind == "hiddenField":
            delta.hidden[ident] = content
        elif kind.startswith("script"):
            delta.scripts.append(content)
        elif kind == "pageRedirect":
            delta.redirect = unquote(content)  # sent URL-encoded
        elif kind == "error":
            delta.error = content
    return delta


def form_fields(page_html: str) -> dict[str, str]:
    """The fields a browser would submit: hidden/text inputs and checked checkboxes."""
    fields: dict[str, str] = {}
    for tag in _INPUT.findall(page_html):
        attrs = {k.lower(): html.unescape(v) for k, v in _ATTR.findall(tag)}
        name, kind = attrs.get("name"), attrs.get("type", "text").lower()
        if not name or kind in ("submit", "button", "image", "file"):
            continue
        if kind in ("checkbox", "radio") and "checked" not in tag.lower():
            continue
        fields[name] = attrs.get("value", "on" if kind == "checkbox" else "")
    return fields


def json_after(text: str, marker: str) -> Any:
    """Decode the JSON object literal that follows `marker` in a script."""
    start = text.index(marker) + len(marker)
    start = text.index("{", start)
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def grid_cells(panel_html: str) -> list[GridCell]:
    """Free cells of the availability grid ("cuadrante"); taken/closed cells are not clickable."""
    panel_html = html.unescape(panel_html)  # onclick quotes arrive as &#39;
    names = _court_names(panel_html)
    cells = []
    for m in _CELL.finditer(panel_html):
        cell_id, court, start = m.groups()
        td = re.search(rf'id="[^"]*_tbc{cell_id}"[^>]*>', panel_html)
        asks = bool(td and re.search(r'blnPreguntarLuz="True"', td.group(0), re.I))
        cells.append(GridCell(cell_id, court, names.get(court, f"court {court}"), start, asks))
    return cells


def _court_names(panel_html: str) -> dict[str, str]:
    """Row labels are listed in the same order as the rows of cells; pair them by order."""
    labels = [
        html.unescape(t).strip() for t in re.findall(r'<span class="LABEL\d*">([^<]+)</span>', panel_html)
    ]
    labels = [t for t in labels if not re.match(r"^\d\d:\d\d", t)]
    codes: list[str] = []
    for m in _CELL.finditer(panel_html):
        if m.group(2) not in codes:
            codes.append(m.group(2))
    return dict(zip(codes, labels, strict=False)) if len(labels) >= len(codes) else {}


class DeportesWeb:
    """One browser-like session (its own cookie jar). Use as an async context manager."""

    def __init__(self, timeout: float = 15.0):
        self._http = httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": _UA, "Accept-Language": "es-ES,es"}
        )
        self.page: Page | None = None
        self.html = ""  # last full page loaded
        self.person_code: str | None = None

    async def __aenter__(self) -> "DeportesWeb":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    # -- primitives ---------------------------------------------------------------------------

    async def open(self, path_or_url: str) -> Page:
        r = await self._http.get(urljoin(BASE, path_or_url))
        r.raise_for_status()
        self.page, self.html = Page(str(r.url), form_fields(r.text)), r.text
        if m := re.search(r'person_code\\?"\s*:\s*\\?"([^"\\]+)', r.text):  # JSON, possibly escaped
            self.person_code = m.group(1)
        return self.page

    async def postback(
        self, target: str, argument: dict[str, Any], extra: dict[str, str] | None = None
    ) -> Delta:
        """Replay `__doPostBack(target, JSON.stringify(argument))` like the page's own script."""
        assert self.page, "open a page first"
        unique = "ctl00$" + target.replace("_", "$")
        data = {
            "ctl00$ScriptManager1": f"{unique}|{target}",
            **self.page.fields,
            **(extra or {}),
            "__EVENTTARGET": target,
            "__EVENTARGUMENT": json.dumps(argument, ensure_ascii=False, separators=(",", ":")),
            "__ASYNCPOST": "true",
        }
        r = await self._http.post(
            self.page.url,
            data=data,
            headers={
                "X-MicrosoftAjax": "Delta=true",
                "X-Requested-With": "XMLHttpRequest",
                "Cache-Control": "no-cache",
            },
        )
        r.raise_for_status()
        delta = parse_delta(r.text)
        for panel in delta.panels.values():  # inputs rendered in refreshed panels join the form
            self.page.fields.update(form_fields(panel))
        self.page.fields.update(delta.hidden)
        if delta.error:
            raise SiteError(delta.error)
        return delta

    async def follow(self, delta: Delta) -> Page:
        if not delta.redirect:
            raise SiteError(alert_text(delta) or "expected a redirect")
        return await self.open(urljoin(self.page.url if self.page else BASE, delta.redirect))

    # -- flows --------------------------------------------------------------------------------

    async def login(self, email: str, password: str) -> None:
        await self.open("login")
        await self.postback(
            "ContentFixedSection_uSecciones_uAlert_uplAlert",
            {"action": "SelectMenu", "args": MENU_EMAIL_LOGIN},
        )
        delta = await self.postback(
            "ContentFixedSection_uLogin_uAlert_uplAlert",
            {
                "action": "Login",
                "args": {"authentication_provider_code": MENU_EMAIL_LOGIN["authentication_provider_code"]},
            },
            extra={
                "ctl00$ContentFixedSection$uLogin$txtIdentificador": email,
                "ctl00$ContentFixedSection$uLogin$txtContrasena": password,
            },
        )
        if "uLoginVerification" in delta.text and not delta.redirect:
            raise SiteError("the site asks for an emailed verification code; log in once in a browser first")
        await self.follow(delta)

    async def browse_anonymously(self) -> None:
        await self.open("login")
        await self.follow(
            await self.postback(
                "ContentFixedSection_uSecciones_uAlert_uplAlert",
                {"action": "SelectMenu", "args": MENU_ANONYMOUS},
            )
        )

    async def open_tennis(self) -> None:
        await self.open("Home")
        delta = await self.postback(
            "ContentFixedSection_uSecciones_uAlert_uplAlert",
            {"action": "SelectSubmenu", "args": MENU_RACKET_SPORTS},
        )
        menu = _menu_payload(delta.text, TENNIS_MENU_CODE)
        menu["submenu_code"] = MENU_RACKET_SPORTS["menu_code"]
        await self.follow(
            await self.postback(
                "ContentFixedSection_uSecciones_uAlert_uplAlert", {"action": "SelectMenu", "args": menu}
            )
        )

    def facilities(self, page_text: str | None = None) -> list[dict[str, str]]:
        """Centres listed on the tennis page: facility code, name, address (in page order)."""
        page_text = self.html if page_text is None else page_text
        codes = re.findall(rf"menuCode: '{TENNIS_MENU_CODE}', facilityCode: '(\d+)'", page_text)
        names = re.findall(r"\$collectionItemTitleDiv\.append\('([^']+)'\)", page_text)
        addresses = re.findall(r"\$collectionItemDescriptionDiv\.append\('([^']+)'\)", page_text)
        return [
            {"code": c, "name": html.unescape(n), "address": html.unescape(a)}
            for c, n, a in zip(codes, names[-len(codes) :], addresses[-len(codes) :], strict=False)
        ]

    async def select_facility(self, facility_code: str) -> dict[str, Any]:
        """Open a centre; returns its tennis usage, whose "dates" lists the bookable days."""
        delta = await self.postback(
            "ContentFixedSection_uReservaEspacios_uCentrosSeleccionar_uAlert_uplAlert",
            {
                "action": "SelectFacility",
                "args": {
                    "menu_code": TENNIS_MENU_CODE,
                    "facility_code": facility_code,
                    "activity": TENNIS_ACTIVITY,
                    "date": None,
                },
            },
        )
        return json_after(delta.text, "reservationType:")

    async def select_usage(self, usage: dict[str, Any]) -> None:
        await self.postback(
            "uAlert_uplAlert",
            {
                "controlID": "ContentFixedSection_uReservaEspacios_uUsosSeleccionar",
                "action": "Seleccionar",
                "args": usage,
            },
        )

    async def open_day(self, facility_code: str, day: date) -> list[GridCell]:
        """Select a centre, its 60-minute tennis usage, and a date; return the free cells."""
        await self.select_usage(await self.select_facility(facility_code))
        return await self.day(day)

    async def day(self, day: date) -> list[GridCell]:
        """Reload the grid of the currently selected centre for `day` (one request)."""
        delta = await self.postback(
            "uAlert_uplAlert",
            {
                "controlID": "ContentFixedSection_uReservaEspacios_uFechaSeleccionar",
                "action": "Continuar",
                "args": day.isoformat(),
            },
        )
        panel = next(
            (v for k, v in delta.panels.items() if k.endswith("uReservaCuadrante_uplContenedor")), ""
        )
        return grid_cells(panel)

    async def reserve(self, cell: GridCell, light: bool) -> Delta:
        """Select one cell and press "Reservar"; on success the site redirects to the cart."""
        flag = ("true" if light else "false") if cell.asks_light else "?"
        return await self.postback(
            "uAlert_uplAlert",
            {
                "controlID": "ContentFixedSection_uReservaEspacios_uReservaCuadrante",
                "action": "Reservar",
                "args": {"personCode": self.person_code},
            },
            extra={GRID_FIELD: f"+{cell.court_code}#{cell.start}#{flag};"},
        )

    async def confirm_cart(self, payment: dict[str, str]) -> Delta:
        """Press "Confirmar la compra" on the cart page; on success the site redirects to the result."""
        return await self.postback(
            "ContentFixedSection_uCarritoConfirmar_uAlert_uplAlert",
            {"action": "ConfirmCart", "args": payment},
        )


def _menu_payload(text: str, menu_code: str) -> dict[str, Any]:
    m = re.search(rf"\{{ menu_code: '{menu_code}'[^}}]*\}}", re.sub(r"\s+", " ", text))
    if not m:
        raise SiteError(f"menu {menu_code} not found")
    payload: dict[str, Any] = {}
    for key, value in re.findall(r"(\w+): ('[^']*'|\d+|null)", m.group(0)):
        payload[key] = None if value == "null" else int(value) if value.isdigit() else value.strip("'")
    payload.setdefault("authentication_provider_code", None)
    return payload


def alert_text(delta: Delta) -> str:
    alert = next((v for k, v in delta.panels.items() if k.endswith("uAlert_uplAlert")), "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(alert))).strip(" x")
