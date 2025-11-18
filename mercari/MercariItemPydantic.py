"""
Pydantic-based data models for Mercari API responses.

This module provides robust validation and automatic handling of optional fields
to eliminate KeyError issues when parsing API responses.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Union


class BaseModelWithIdCoercion(BaseModel):
    """Base model that automatically converts integer IDs to strings."""

    @field_validator('id', mode='before', check_fields=False)
    @classmethod
    def coerce_id_to_str(cls, v):
        """Convert integer IDs to strings."""
        return str(v) if v is not None and v != "" else ""

    class Config:
        extra = "ignore"


class Ratings(BaseModel):
    """Seller rating breakdown."""

    good: int = 0
    normal: int = 0
    bad: int = 0

    class Config:
        extra = "ignore"


class ConvertedPrice(BaseModel):
    """Price converted to another currency."""

    price: int = 0
    currency_code: str = ""
    rate_updated: int = 0

    class Config:
        extra = "ignore"


class Seller(BaseModelWithIdCoercion):
    """Seller information and ratings."""

    id: str = ""
    name: str = ""
    photo_url: str = ""
    photo_thumbnail_url: str = ""
    created: int = 0
    num_sell_items: int = 0
    ratings: Optional[Ratings] = None
    num_ratings: int = 0
    score: float = 0.0
    is_official: bool = False
    quick_shipper: bool = False
    is_followable: bool = False
    is_blocked: bool = False
    star_rating_score: float = 0.0


class ItemCategory(BaseModelWithIdCoercion):
    """Item category information."""

    id: str = ""
    name: str = ""
    display_order: int = 0
    parent_category_id: int = 0
    parent_category_name: str = ""
    root_category_id: int = 0
    root_category_name: str = ""


class ItemCategoryNTiers(ItemCategory):
    """Extended category information with brand group."""

    brand_group_id: int = 0


class ParentCategoryNTier(BaseModelWithIdCoercion):
    """Parent category tier information."""

    id: str = ""
    name: str = ""
    display_order: int = 0


class ItemCondition(BaseModelWithIdCoercion):
    """Item condition status."""

    id: str = ""
    name: str = ""


class ShippingPayer(BaseModelWithIdCoercion):
    """Shipping payment responsibility."""

    id: str = ""
    name: str = ""
    code: str = ""


class ShippingMethod(BaseModelWithIdCoercion):
    """Shipping method details."""

    id: str = ""
    name: str = ""
    is_deprecated: bool = False


class ShippingFromArea(BaseModelWithIdCoercion):
    """Shipping origin area."""

    id: str = ""
    name: str = ""


class ShippingDuration(BaseModelWithIdCoercion):
    """Expected shipping duration."""

    id: str = ""
    name: str = ""
    min_days: int = 0
    max_days: int = 0


class ShippingClass(BaseModelWithIdCoercion):
    """Shipping class and fee breakdown."""

    id: str = ""
    fee: int = 0
    icon_id: int = 0
    pickup_fee: int = 0
    shipping_fee: int = 0
    total_fee: int = 0
    is_pickup: bool = False


class ItemAttributeValue(BaseModelWithIdCoercion):
    """Individual attribute value."""

    id: str = ""
    text: str = ""


class ItemAttribute(BaseModelWithIdCoercion):
    """Item attribute with possible values."""

    id: str = ""
    text: str = ""
    values: List[ItemAttributeValue] = Field(default_factory=list)
    deep_facet_filterable: bool = False
    show_on_ui: bool = False


class Color(BaseModelWithIdCoercion):
    """Item color information."""

    id: str = ""
    name: str = ""
    rgb: str = ""


class ItemAuction(BaseModelWithIdCoercion):
    """Auction information for items being auctioned."""

    id: str = ""
    bid_deadline: str = ""
    total_bid: str = "0"
    highest_bid: str = "0"

    @field_validator('total_bid', 'highest_bid', mode='before')
    @classmethod
    def coerce_bid_to_str(cls, v):
        """Convert integer bid values to strings."""
        return str(v) if v is not None else "0"


class Comment(BaseModelWithIdCoercion):
    """Comment information on an item."""

    id: str = ""
    created: int = 0

    class Config:
        extra = "ignore"


class Item(BaseModel):
    """
    Full Mercari item details with Pydantic validation.

    This model provides robust handling of optional fields and automatic
    validation of API responses to eliminate KeyError issues.
    """

    # Required fields - always present in API response
    id: str
    name: str
    price: int
    status: str
    created: int
    updated: int

    # Optional nested objects - may be missing or null
    converted_price: Optional[ConvertedPrice] = None
    seller: Optional[Seller] = None
    item_condition: Optional[ItemCondition] = None
    shipping_payer: Optional[ShippingPayer] = None
    shipping_method: Optional[ShippingMethod] = None
    shipping_from_area: Optional[ShippingFromArea] = None
    shipping_duration: Optional[ShippingDuration] = None
    shipping_class: Optional[ShippingClass] = None
    item_category: Optional[ItemCategory] = None
    item_category_ntiers: Optional[ItemCategoryNTiers] = None
    auction: Optional[ItemAuction] = None

    # Optional strings with empty defaults
    description: str = ""
    pager_id: str = ""
    checksum: str = ""
    is_shop_item: str = ""
    organizational_user_status: str = ""
    meta_title: str = ""
    meta_subtitle: str = ""

    # Lists - use Field(default_factory=list) to avoid mutable default issues
    photos: List[str] = Field(default_factory=list)
    photo_paths: List[str] = Field(default_factory=list)
    thumbnails: List[str] = Field(default_factory=list)
    parent_categories_ntiers: List[ParentCategoryNTier] = Field(default_factory=list)
    colors: List[Color] = Field(default_factory=list)
    item_attributes: List[ItemAttribute] = Field(default_factory=list)
    comments: List[Comment] = Field(default_factory=list)
    photo_descriptions: List[str] = Field(default_factory=list)
    hash_tags: List[str] = Field(default_factory=list)
    additional_services: List[str] = Field(default_factory=list)

    # Integer counters with zero defaults
    num_likes: int = 0
    num_comments: int = 0
    registered_prices_count: int = 0

    # Boolean flags with False defaults
    liked: bool = False
    is_dynamic_shipping_fee: bool = False
    is_anonymous_shipping: bool = False
    is_web_visible: bool = False
    is_offerable: bool = False
    is_organizational_user: bool = False
    is_stock_item: bool = False
    is_cancelable: bool = False
    shipped_by_worker: bool = False
    has_additional_service: bool = False
    has_like_list: bool = False
    is_offerable_v2: bool = False
    is_dismissed: bool = False

    # Dictionary for unknown structure
    application_attributes: dict = Field(default_factory=dict)

    @field_validator('pager_id', mode='before')
    @classmethod
    def coerce_pager_id_to_str(cls, v):
        """Convert integer pager_id to string."""
        return str(v) if v is not None else ""

    class Config:
        extra = "ignore"  # Ignore unknown fields from API for forward compatibility

    def __str__(self) -> str:
        """String representation for debugging."""
        return f"Item(id={self.id!r}, name={self.name!r}, price={self.price}, status={self.status!r})"

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"Item(id={self.id!r}, name={self.name!r}, price={self.price}, "
            f"status={self.status!r}, created={self.created}, updated={self.updated})"
        )


# Alias for backward compatibility with existing code
MercariItemFull = Item


__all__ = [
    "Ratings",
    "ConvertedPrice",
    "Seller",
    "ItemCategory",
    "ItemCategoryNTiers",
    "ParentCategoryNTier",
    "ItemCondition",
    "ShippingPayer",
    "ShippingMethod",
    "ShippingFromArea",
    "ShippingDuration",
    "ShippingClass",
    "ItemAttributeValue",
    "ItemAttribute",
    "Color",
    "Comment",
    "ItemAuction",
    "Item",
    "MercariItemFull",
]
