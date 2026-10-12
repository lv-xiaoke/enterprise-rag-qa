from typing import Annotated
from fastapi import Depends, Query
from backend.auth import administrator, current_user, require_csrf
from backend.models import User

CurrentUser = Annotated[User, Depends(current_user)]
AdminUser = Annotated[User, Depends(administrator)]


def pagination(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return limit, offset
