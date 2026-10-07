"""Find the hour Madrid opens D-6 tennis slots, anonymously, by watching the bookable-dates list.

    uv run python scripts/probe_madrid_opening.py 2026-10-14

Polls once a minute (every 5 s around 00:00, 07:00, 08:00, 09:00) and prints the first moment the
given date appears in the site's list of bookable dates. One request per poll, no login.
"""

import asyncio
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from slotbot.providers.deportesweb import TENNIS_ACTIVITY, TENNIS_MENU_CODE, DeportesWeb, json_after

MADRID = ZoneInfo("Europe/Madrid")
ANONYMOUS = {
    "menu_code": "41042",
    "menu_title": "No identificado",
    "menu_type": 30,
    "authentication_provider_code": None,
    "submenu_code": None,
}


async def bookable_dates(s: DeportesWeb) -> list[str]:
    delta = await s.postback(
        "ContentFixedSection_uReservaEspacios_uCentrosSeleccionar_uAlert_uplAlert",
        {
            "action": "SelectFacility",
            "args": {
                "menu_code": TENNIS_MENU_CODE,
                "facility_code": "10",
                "activity": TENNIS_ACTIVITY,
                "date": None,
            },
        },
    )
    return json_after(delta.text, "reservationType:")["dates"]


async def session() -> DeportesWeb:
    s = DeportesWeb()
    await s.open("login")
    await s.follow(
        await s.postback(
            "ContentFixedSection_uSecciones_uAlert_uplAlert", {"action": "SelectMenu", "args": ANONYMOUS}
        )
    )
    await s.open_tennis()
    return s


async def main(target: date) -> None:
    s = await session()
    last: list[str] = []
    while True:
        now = datetime.now(MADRID)
        try:
            dates = await bookable_dates(s)
        except Exception as e:  # session expired or hiccup: start a fresh one
            print(f"{now:%H:%M:%S} error {type(e).__name__}: {e}; new session", flush=True)
            await asyncio.sleep(5)
            s = await session()
            continue
        if dates != last:
            print(
                f"{now:%Y-%m-%d %H:%M:%S} bookable: {dates[0]} .. {dates[-1]} ({len(dates)} days)", flush=True
            )
            last = dates
        if target.isoformat() in dates:
            print(f"OPENED: {target} became bookable by {now:%Y-%m-%d %H:%M:%S %Z}", flush=True)
            return
        near = any(
            abs((now.hour * 60 + now.minute) - h * 60) <= 4
            or (h == 0 and now.hour == 23 and now.minute >= 56)
            for h in (0, 7, 8, 9)
        )
        await asyncio.sleep(5 if near else 60)


if __name__ == "__main__":
    asyncio.run(main(date.fromisoformat(sys.argv[1])))
