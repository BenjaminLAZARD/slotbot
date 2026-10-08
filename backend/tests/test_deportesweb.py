"""Offline tests for the deportesweb.madrid.es protocol helpers, on snippets shaped like real responses."""

import json

from slotbot.providers.deportesweb import (
    _menu_payload,
    form_fields,
    grid_cells,
    json_after,
    page_texts,
    parse_cart,
    parse_delta,
    person_code,
)
from slotbot.providers.madrid import _key, _plain_address


def test_person_code_is_read_from_the_centre_selection_script():
    # Shaped like the SelectFacility response of a signed-in session (2026-10-08).
    script = (
        "function ContentFixedSection_uReservaEspacios_uUsosSeleccionar_callbackCargar() { "
        '$(\'.cronos-reservations\').data(\'profile\', {"session_token":"aa","identifier":"ME@X.COM",'
        '"person_code":"ff622b96","person_firstname":"Me"});'
    )
    assert person_code(script) == "ff622b96"
    assert person_code('{\\"person_code\\":\\"ab12\\"}') == "ab12"  # escaped JSON in a full page
    assert person_code("let personCode = null; if (profile) personCode = profile.person_code;") is None


def test_cart_page_reads_items_total_and_wallet_balance():
    # Shaped like CarritoConfirmar on 2026-10-08: the page renders itself with jQuery .append('...').
    page = (
        "$t.append('Tenis 2 La Chopera'); $a.append('Inicio'); $b.append('16:30'); $c.append('Fin');"
        "$d.append('17:30'); $e.append('Total'); $f.append('6,90 €'); $g.append('Monedero');"
        "$h.append('Saldo disponible'); $i.append('10,00 €'); $j.append('Confirmar la compra')"
    )
    cart = parse_cart(page)
    assert (cart.items, cart.total, cart.wallet) == (1, 6.9, 10.0)
    # Real pages write each item twice (two layouts) but give it one code: count codes.
    twice = (
        "$a.append('Inicio'); $b.append('Inicio');"
        "f({ cart_item_code: '162248182' }); g({cart_item_code:'162248182'})"
    )
    assert parse_cart(twice).items == 1
    assert "16:30" in cart.texts
    assert parse_cart("$a.append('Total'); $b.append('6,90 €')").wallet is None  # wallet not offered


def test_result_page_texts_carry_confirmation_and_operation():
    page = "$x.append('Confirmado'); $y.append('Pago 6,90 €'); $z.append('Operación 8075908894')"
    texts = page_texts(page)
    assert "Confirmado" in texts and "Operación 8075908894" in texts


def delta(*parts: tuple[str, str, str]) -> str:
    return "".join(f"{len(content)}|{kind}|{ident}|{content}|" for kind, ident, content in parts)


def test_parse_delta_reads_panels_hidden_state_and_encoded_redirect():
    d = parse_delta(
        delta(
            ("updatePanel", "uAlert_uplAlert", "<div>hola | adiós</div>"),
            ("hiddenField", "__VIEWSTATE", "abc=="),
            ("pageRedirect", "", "%2fDeportesWeb%2fHome"),
        )
    )
    assert d.panels == {"uAlert_uplAlert": "<div>hola | adiós</div>"}  # '|' inside content is fine
    assert d.hidden == {"__VIEWSTATE": "abc=="}
    assert d.redirect == "/DeportesWeb/Home"


def test_form_fields_mimic_a_browser_submit():
    page = (
        '<input type="hidden" name="__VIEWSTATE" value="x&amp;y" />'
        '<input type="checkbox" name="keep" />'
        '<input type="checkbox" name="filter" checked="checked" />'
        '<input type="submit" name="go" value="Go" />'
    )
    assert form_fields(page) == {"__VIEWSTATE": "x&y", "filter": "on"}


def test_grid_cells_decode_html_encoded_onclick_and_pair_court_names():
    cell = (
        '<td id="X_tbc{id}" blnPreguntarLuz="{ask}" blnLuz="False"><img id="X_img{id}" estado="Libre" '
        'onclick="javascript:celdaCuadrante(&#39;{id}&#39;,&#39;{court}&#39;,&#39;{start}&#39;,&#39;?&#39;)"></td>'
    )
    panel = (
        '<span class="LABEL3">08:30 09:30</span>'
        '<span class="LABEL3">Tenis 1 La Chopera</span><span class="LABEL3">Tenis 2 La Chopera</span>'
        + cell.format(id="1820830", court="182", start="08:30", ask="False")
        + cell.format(id="1832030", court="183", start="20:30", ask="True")
    )
    cells = grid_cells(panel)
    assert [(c.court_code, c.court_name, c.start, c.asks_light) for c in cells] == [
        ("182", "Tenis 1 La Chopera", "08:30", False),
        ("183", "Tenis 2 La Chopera", "20:30", True),
    ]


def test_menu_payload_and_json_after_read_the_page_scripts():
    script = "$a.on('click', { menu_code: '8598', menu_title: 'Pista de tenis', menu_type: 7 }, f);"
    assert _menu_payload(script, "8598") == {
        "menu_code": "8598",
        "menu_title": "Pista de tenis",
        "menu_type": 7,
        "authentication_provider_code": None,
    }
    usage = {"reservation_type_code": "124", "dates": ["2026-10-07", "2026-10-13"]}
    assert (
        json_after(f"on('click', {{ reservationType: {json.dumps(usage)} }}, f)", "reservationType:") == usage
    )


def test_open_data_names_and_addresses_match_the_booking_site():
    assert _key("Centro Deportivo Municipal Marqués de Samaranch") == _key("Marqués de Samaranch")
    assert _plain_address("Calle X, 99 (Moncloa - Aravaca), 28023, Madrid") == "Calle X, 99, 28023, Madrid"
