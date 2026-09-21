"""In-memory user store.

Deliberately not a database: the point of this service is to have a contract
worth checking, not persistence. Keeping it in memory means the container
starts instantly in CI and every run begins from the same seed data, which
matters because Schemathesis fires a lot of requests at it.
"""

from datetime import datetime, timezone
from itertools import count

from app.models import User

_SEED = [
    ("Sohan", "sohan@example.com"),
    ("Ada", "ada@example.com"),
    ("Grace", "grace@example.com"),
]

_ids = count(1)
_users: dict[int, User] = {}


def reset() -> None:
    """Restore the store to its seed state."""
    global _ids
    _ids = count(1)
    _users.clear()
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for name, email in _SEED:
        user_id = next(_ids)
        _users[user_id] = User(id=user_id, name=name, email=email, created_at=created)


def list_users() -> list[User]:
    return list(_users.values())


def get_user(user_id: int) -> User | None:
    return _users.get(user_id)


def create_user(name: str, email: str) -> User:
    user_id = next(_ids)
    user = User(
        id=user_id,
        name=name,
        email=email,
        created_at=datetime.now(tz=timezone.utc),
    )
    _users[user_id] = user
    return user


reset()
