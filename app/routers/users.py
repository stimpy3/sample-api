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
    responses={201: {"description": "The newly created user."}},
)
def create_user(payload: UserCreate) -> User:
    return store.create_user(name=payload.name, email=payload.email)
