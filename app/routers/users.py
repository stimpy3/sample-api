"""User endpoints.

Every response status this router can return is declared in the decorator.
That is not decoration: Schemathesis' `status_code_conformance` check fails the
build if the API returns a status the spec does not mention, so an undeclared
error path here shows up as a contract violation in CI.
"""

from fastapi import APIRouter, HTTPException, status

from app import store
from app.models import Error, User, UserCreate

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=list[User],
    summary="List all users",
    responses={200: {"description": "Every user currently known to the service."}},
)
def list_users() -> list[User]:
    return store.list_users()


@router.get(
    "/search",
    response_model=list[User],
    summary="Search users by name (deprecated)",
    deprecated=True,
    # Announced for removal. oasdiff honours x-sunset for endpoints: deleting
    # this before the date is reported as api-path-removed-before-sunset, and
    # after it the deletion is clean. That is the zero-exception retirement
    # path, and it is demo scenario 6.
    #
    # Note this works for ENDPOINTS only. A response field gets no such
    # treatment - see the email field, where the cost is paid at the
    # required-to-optional demotion instead.
    openapi_extra={"x-sunset": "2026-03-01"},
    responses={200: {"description": "Users whose name contains the query."}},
)
def search_users(q: str = "") -> list[User]:
    return [u for u in store.list_users() if q.lower() in u.name.lower()]


@router.get(
    "/{user_id}",
    response_model=User,
    summary="Fetch a single user",
    responses={
        200: {"description": "The requested user."},
        404: {"model": Error, "description": "No user exists with that id."},
    },
)
def get_user(user_id: int) -> User:
    user = store.get_user(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No user with id {user_id}.",
        )
    return user


@router.post(
    "",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
    responses={
        201: {"description": "The newly created user."},
        # FastAPI answers 400 when the body is not parseable JSON at all, as
        # distinct from the 422 it returns for JSON that parses but fails
        # validation. Undeclared, this is a contract violation: the conformance
        # check found it by posting malformed bytes, which is the kind of input
        # no hand-written test suite would have thought to try.
        400: {"model": Error, "description": "The request body could not be parsed."},
    },
)
def create_user(payload: UserCreate) -> User:
    return store.create_user(name=payload.name, email=payload.email)
