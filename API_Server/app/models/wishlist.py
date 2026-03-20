from pydantic import BaseModel


class WishlistAddRequest(BaseModel):
    series_nm: str


class WishlistAddResponse(BaseModel):
    series_nm: str
    message: str


class WishlistRemoveResponse(BaseModel):
    series_nm: str
    message: str
