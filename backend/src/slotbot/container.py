"""Composition root: the only place that knows which concrete adapter backs each port."""

from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from slotbot.adapters.billing import BillingKillSwitch
from slotbot.adapters.clock import SystemClock
from slotbot.adapters.email import ResendNotifier, SmtpNotifier
from slotbot.adapters.geocoder import Nominatim
from slotbot.adapters.google_auth import GoogleToken
from slotbot.adapters.google_calendar import GoogleCalendar
from slotbot.adapters.triggers import CloudTasksTriggers, LocalTriggers
from slotbot.adapters.vault import Vault
from slotbot.ports import Calendar, Clock, Geocoder, Notifier, Triggers
from slotbot.providers import ProviderRegistry, build_registry
from slotbot.services.agenda import AgendaService
from slotbot.services.local_loop import LocalLoop
from slotbot.services.planner import Planner
from slotbot.services.race import RaceService, Timing
from slotbot.services.sync import SyncService
from slotbot.services.venues import VenueCatalogue
from slotbot.settings import Settings


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker
    google: GoogleToken
    calendar: Calendar
    geocoder: Geocoder
    providers: ProviderRegistry
    triggers: Triggers
    vault: Vault
    clock: Clock
    catalogue: VenueCatalogue
    sync: SyncService
    race: RaceService
    agenda: AgendaService
    notifier: Notifier | None
    kill_switch: BillingKillSwitch | None
    local_loop: LocalLoop | None


def build_container(settings: Settings, http: httpx.AsyncClient) -> Container:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    clock = SystemClock()
    google = GoogleToken(settings.google_service_account)
    calendar = GoogleCalendar(http, google)
    agent = f"slotbot/0.1 ({settings.contact_email or 'self-hosted'})"
    geocoder = Nominatim(http, agent)
    providers = build_registry(http, geocoder, settings)
    vault = Vault(settings.secret_key)
    catalogue = VenueCatalogue(sessions, clock)
    planner = Planner(geocoder, catalogue)
    timing = Timing(
        lead=timedelta(minutes=settings.lead_minutes),
        poll_start=timedelta(seconds=settings.poll_start_seconds),
        poll_every=settings.poll_seconds,
        retry_for=timedelta(seconds=settings.retry_for_seconds),
    )

    triggers: Triggers
    if settings.triggers == "cloudtasks":
        triggers = CloudTasksTriggers(
            http, google, settings.cloud_tasks_queue, settings.public_url, settings.job_token
        )
    else:
        triggers = LocalTriggers(clock)

    notifier: Notifier | None = None
    if settings.resend_api_key:
        notifier = ResendNotifier(http, settings.resend_api_key, settings.email_from)
    elif settings.smtp_user:
        notifier = SmtpNotifier(
            settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password
        )

    sync = SyncService(sessions, calendar, planner, providers, triggers, clock, timing.lead)
    race = RaceService(sessions, calendar, planner, providers, vault, clock, timing, sync, notifier)

    local_loop = None
    if isinstance(triggers, LocalTriggers):
        triggers.fire = race.run
        every = timedelta(minutes=settings.local_sync_minutes)
        local_loop = LocalLoop(sessions, triggers, sync, clock, every)

    loop = local_loop
    agenda = AgendaService(
        sessions,
        calendar,
        providers,
        vault,
        triggers,
        clock,
        sync,
        next_sync=lambda: loop.next_sync if loop else None,  # Cloud Scheduler: not known here
    )

    return Container(
        settings=settings,
        engine=engine,
        sessions=sessions,
        google=google,
        calendar=calendar,
        geocoder=geocoder,
        providers=providers,
        triggers=triggers,
        vault=vault,
        clock=clock,
        catalogue=catalogue,
        sync=sync,
        race=race,
        agenda=agenda,
        notifier=notifier,
        kill_switch=BillingKillSwitch(http, google, settings.gcp_project) if settings.gcp_project else None,
        local_loop=local_loop,
    )
