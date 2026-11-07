"""API: endpoint customer (saldo poin loyalty).

Customer hanya bisa melihat poin miliknya sendiri, admin (orders:all) bisa melihat semua customer.
"""
from fastapi import APIRouter, Depends, Security

from app.api.dependencies import get_points_service
from app.api.schemas import ErrorOut, PointsOut
from app.api.security import get_current_user
from app.application.auth_service import CurrentUser
from app.application.points_service import PointsService

router = APIRouter(prefix="/customers", tags=["customers"],
                   responses={401: {"model": ErrorOut, "description": "Belum login"},
                              403: {"model": ErrorOut, "description": "Hanya bisa melihat poin sendiri"}})


@router.get("/{customer}/points", response_model=PointsOut, summary="Saldo poin loyalty customer")
def get_points(customer: str,
               user: CurrentUser = Security(get_current_user, scopes=["orders:write"]),
               service: PointsService = Depends(get_points_service)):
    return PointsOut(customer=customer, points=service.balance(customer, user))
