"""FareRule (GTFS) schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class FareRuleBase(BaseModel):
    """Base fare rule schema"""

    fare_id: str = Field(..., min_length=1, max_length=255, description="GTFS fare_id - references fare_attributes")
    route_id: str = Field("", max_length=255, description="Route ID this fare applies to (empty = all routes)")
    origin_id: str = Field("", max_length=255, description="Origin zone ID (empty = any origin)")
    destination_id: str = Field("", max_length=255, description="Destination zone ID (empty = any destination)")
    contains_id: str = Field("", max_length=255, description="Zone that must be passed through (empty = no constraint)")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Custom/extension fields from GTFS")


class FareRuleCreate(FareRuleBase):
    """Schema for creating a new fare rule"""

    feed_id: int = Field(..., description="Feed ID this fare rule belongs to")


class FareRuleUpdate(BaseModel):
    """Schema for updating a fare rule - allows updating the composite key fields"""

    fare_id: Optional[str] = Field(None, min_length=1, max_length=255)
    route_id: Optional[str] = Field(None, max_length=255)
    origin_id: Optional[str] = Field(None, max_length=255)
    destination_id: Optional[str] = Field(None, max_length=255)
    contains_id: Optional[str] = Field(None, max_length=255)
    custom_fields: Optional[Dict[str, Any]] = None


class FareRuleResponse(FareRuleBase):
    """Schema for fare rule response"""

    feed_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FareRuleList(BaseModel):
    """Paginated list of fare rules"""

    items: List[FareRuleResponse]
    total: int
    skip: int
    limit: int


class FareRuleIdentifier(BaseModel):
    """Identifier for a specific fare rule (all composite key fields)"""

    fare_id: str
    route_id: str = ""
    origin_id: str = ""
    destination_id: str = ""
    contains_id: str = ""


class FareRuleUpdateRequest(BaseModel):
    """Combined request for updating a fare rule - identifier + new values"""

    identifier: FareRuleIdentifier
    update: FareRuleUpdate
