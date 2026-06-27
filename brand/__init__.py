"""Brand understanding — a one-time, multimodal BrandBook that the creative studio
(poster + reel) reads from, instead of re-deriving the brand on every generation."""
from .brand_book import (
    BrandBook,
    BrandVisualIdentity,
    build_brand_book,
    load_brand_book,
    save_brand_book,
)

__all__ = [
    "BrandBook",
    "BrandVisualIdentity",
    "build_brand_book",
    "save_brand_book",
    "load_brand_book",
]
