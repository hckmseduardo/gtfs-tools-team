"""FareAttribute (GTFS) schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field
from datetime import datetime


class FareAttributeBase(BaseModel):
    """Base fare attribute schema"""

    fare_id: str = Field(..., min_length=1, max_length=255, description="GTFS fare_id")
    price: Decimal = Field(..., ge=0, description="Fare price")
    currency_type: str = Field(..., min_length=3, max_length=3, description="ISO 4217 currency code")
    payment_method: int = Field(
        ..., ge=0, le=1, description="0=on board, 1=before boarding"
    )
    transfers: Optional[int] = Field(
        None, ge=0, le=2, description="0=no transfers, 1=once, 2=twice, null=unlimited"
    )
    agency_id: Optional[str] = Field(None, max_length=255, description="GTFS agency_id")
    transfer_duration: Optional[int] = Field(None, ge=0, description="Transfer duration in seconds")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields from GTFS")


class FareAttributeCreate(FareAttributeBase):
    """Schema for creating a new fare attribute"""

    feed_id: int = Field(..., description="Feed ID this fare attribute belongs to")


class FareAttributeUpdate(BaseModel):
    """Schema for updating a fare attribute"""

    fare_id: Optional[str] = Field(None, min_length=1, max_length=255)
    price: Optional[Decimal] = Field(None, ge=0)
    currency_type: Optional[str] = Field(None, min_length=3, max_length=3)
    payment_method: Optional[int] = Field(None, ge=0, le=1)
    transfers: Optional[int] = Field(None, ge=0, le=2)
    agency_id: Optional[str] = Field(None, max_length=255)
    transfer_duration: Optional[int] = Field(None, ge=0)
    custom_fields: Optional[Dict[str, Any]] = None


class FareAttributeResponse(FareAttributeBase):
    """Schema for fare attribute response"""

    feed_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FareAttributeList(BaseModel):
    """Paginated list of fare attributes"""

    items: List[FareAttributeResponse]
    total: int
    skip: int
    limit: int
