"""API: endpoint product. Melihat produk terbuka untuk umum, menambah produk butuh scope products:write.

/best-sellers ditulis sebelum /{product_id}, supaya "best-sellers" tidak dianggap product_id.
"""
from fastapi import APIRouter, Depends, Query, Response, Security

from app.api.dependencies import get_product_service
from app.api.rate_limit import rate_limit
from app.api.schemas import BestSellerOut, ErrorOut, ProductIn, ProductOut
from app.api.security import get_current_user
from app.application.product_service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", status_code=201, response_model=ProductOut, summary="Tambah produk (admin)",
             dependencies=[Security(get_current_user, scopes=["products:write"])],
             responses={401: {"model": ErrorOut, "description": "Belum login"},
                        403: {"model": ErrorOut, "description": "Butuh scope products:write"}})
def create_product(payload: ProductIn, service: ProductService = Depends(get_product_service)):
    return ProductOut.from_domain(service.create_product(payload.name, payload.price, payload.stock))


@router.get("", response_model=list[ProductOut], summary="Daftar produk")
def list_products(service: ProductService = Depends(get_product_service)):
    return [ProductOut.from_domain(p) for p in service.list_products()]


@router.get("/best-sellers", response_model=list[BestSellerOut], summary="Produk terlaris (cache + rate limit)",
            dependencies=[Depends(rate_limit)],
            responses={429: {"model": ErrorOut, "description": "Terlalu banyak request (rate limit)"}})
def best_sellers(response: Response, limit: int = Query(5, ge=1, le=10),
                 service: ProductService = Depends(get_product_service)):
    rows, cache_hit = service.best_sellers(limit)
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    return rows


@router.get("/{product_id}", response_model=ProductOut, summary="Detail produk",
            responses={404: {"model": ErrorOut, "description": "Produk tidak ditemukan"}})
def get_product(product_id: int, service: ProductService = Depends(get_product_service)):
    return ProductOut.from_domain(service.get_product(product_id))
