"""Who may use the app: Google sign-in checked against the invite list, and who owns which profile."""

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from slotbot.models import Profile, User
from slotbot.ports import Clock, IdentityVerifier

LOCAL_EMAIL = "local@localhost"


class NotInvited(Exception):
    pass


class AccountService:
    def __init__(
        self,
        sessions: async_sessionmaker,
        verifier: IdentityVerifier,
        clock: Clock,
        client_id: str,
        invited: list[str],
    ):
        self._sessions = sessions
        self._verifier = verifier
        self._clock = clock
        self._client_id = client_id
        self._invited = invited
        self._local: User | None = None

    @property
    def enabled(self) -> bool:
        """Sign-in is on whenever a Google client ID is configured (always, outside localhost)."""
        return bool(self._client_id)

    @property
    def client_id(self) -> str:
        return self._client_id

    def invited(self, email: str) -> bool:
        return email.lower() in self._invited

    async def sign_in(self, credential: str) -> User:
        """Verify a "Sign in with Google" credential; raises ValueError (bad token) or NotInvited."""
        identity = await self._verifier.verify(credential, self._client_id)
        if not self.invited(identity.email):
            raise NotInvited(identity.email)
        owner = identity.email == self._invited[0]
        return await self._upsert(identity.email, identity.subject, identity.name, owner)

    async def local_user(self) -> User:
        """Sign-in off (localhost only): one implicit user owns every profile."""
        if self._local is None:
            self._local = await self._upsert(LOCAL_EMAIL, None, "local", owner=True)
        return self._local

    async def _upsert(self, email: str, subject: str | None, name: str, owner: bool) -> User:
        async with self._sessions() as db:
            match = (
                User.email == email
                if subject is None
                else or_(User.google_sub == subject, User.email == email)
            )
            user = await db.scalar(select(User).where(match))
            if user is None:
                user = User(email=email)
                db.add(user)
            user.email, user.google_sub = email, subject or user.google_sub
            user.name = name or user.name
            user.last_login_at = self._clock.now()
            await db.flush()
            if owner:  # profiles from before sign-in existed belong to the instance owner
                await db.execute(update(Profile).where(Profile.owner_id.is_(None)).values(owner_id=user.id))
            await db.commit()
            return user
