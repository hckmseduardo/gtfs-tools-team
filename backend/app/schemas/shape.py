"""Pydantic schemas for GTFS shapes"""

from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict


class ShapeBase(BaseModel):
    """Base shape schema"""

    shape_id: str = Field(..., description="Identifier for a shape")
    shape_pt_lat: Decimal = Field(..., description="Latitude of a shape point", ge=-90, le=90)
    shape_pt_lon: Decimal = Field(..., description="Longitude of a shape point", ge=-180, le=180)
    shape_pt_sequence: int = Field(..., description="Sequence in which the shape points connect", ge=0)
    shape_dist_traveled: Optional[Decimal] = Field(None, description="Distance traveled along the shape")


class ShapeCreate(ShapeBase):
    """Schema for creating a shape point"""

    feed_id: int = Field(..., description="Feed ID")


class ShapeUpdate(BaseModel):
    """Schema for updating a shape point"""

    shape_pt_lat: Optional[Decimal] = Field(None, ge=-90, le=90)
    shape_pt_lon: Optional[Decimal] = Field(None, ge=-180, le=180)
    shape_pt_sequence: Optional[int] = Field(None, ge=0)
    shape_dist_traveled: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class ShapeResponse(ShapeBase):
    """Schema for shape response"""

    feed_id: int

    model_config = ConfigDict(from_attributes=True)


class ShapePointCreate(BaseModel):
    """Single point for bulk shape creation"""

    lat: Decimal = Field(..., ge=-90, le=90)
    lon: Decimal = Field(..., ge=-180, le=180)
    sequence: int = Field(..., ge=0)
    dist_traveled: Optional[Decimal] = None


class ShapeBulkCreate(BaseModel):
    """Schema for creating multiple shape points at once"""

    feed_id: int = Field(..., description="Feed ID")
    shape_id: str = Field(..., description="Shape identifier")
    points: List[ShapePointCreate] = Field(..., description="List of shape points")


class ShapePoint(BaseModel):
    """Simple shape point for visualization"""

    lat: float
    lon: float
    sequence: int

    model_config = ConfigDict(from_attributes=True)


class ShapeWithPoints(BaseModel):
    """Shape grouped by shape_id with all points"""

    shape_id: str
    points: List[ShapePoint]
    total_points: int

    model_config = ConfigDict(from_attributes=True)


class ShapeList(BaseModel):
    """Paginated list of shapes"""

    items: List[ShapeResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ShapesByIdList(BaseModel):
    """List of shapes grouped by shape_id"""

    items: List[ShapeWithPoints]
    total: int
