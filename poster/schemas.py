from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class PosterSocial(BaseModel):
    platform: str = Field(max_length=40)
    url: str = Field(max_length=500)


class PosterBrief(BaseModel):
    business_name: str = Field(min_length=2, max_length=120)
    category: Optional[str] = None

    headline: str = Field(min_length=2, max_length=160)
    subheadline: Optional[str] = Field(default=None, max_length=260)

    offerings: list[str] = Field(default_factory=list, max_length=3)

    cta_text: str = Field(default="Learn more", max_length=80)
    cta_url: Optional[str] = Field(default=None, max_length=500)
    contact_line: Optional[str] = Field(default=None, max_length=160)

    palette_hex: list[str] = Field(default_factory=list, max_length=5)
    primary_color: Optional[str] = None
    tone: Optional[str] = None

    logo_url: Optional[str] = Field(default=None, max_length=1000)
    logo_text: Optional[str] = Field(default=None, max_length=120)
    logo_source_type: Optional[str] = Field(default=None, max_length=60)
    logo_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    pricing_note: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)

    # Evidence-backed social profiles (platform + url) from profile.social_presence.
    social: list[PosterSocial] = Field(default_factory=list, max_length=6)

    # Brand typography (the site's own fonts, from manifest.visual.fonts). Used by
    # the poster when the named family is loadable (Google Fonts); else the poster
    # falls back to a curated modern default. May be a private/generic name.
    heading_font: Optional[str] = Field(default=None, max_length=80)
    body_font: Optional[str] = Field(default=None, max_length=80)


class PosterArtDirection(BaseModel):
    provider_prompt: str
    negative_prompt: str
    concept: str
    category: str
    mood: str
    layout: Literal[
        "magazine_cover",
        "split_editorial",
        "bottom_band",
        "clean_institutional",
        "hero_overlay",
    ]
    background_style: str
    safe_overlay_copy: str
    color_notes: list[str] = Field(default_factory=list)
    source_fields_used: list[str] = Field(default_factory=list)


class BackgroundImageResult(BaseModel):
    provider: str
    model: Optional[str] = None
    prompt: str
    background_path: str
    filename: str
    width: int
    height: int
    fallback_used: bool = False
    fallback_reason: Optional[str] = None


class PosterRenderResult(BaseModel):
    poster_path: str
    filename: str
    width: int
    height: int
    mime_type: Literal["image/png"] = "image/png"


class PosterFromProfileRequest(BaseModel):
    profile: dict[str, Any]
    output_format: Literal["poster_1080x1350", "a4_print"] = "poster_1080x1350"


class PosterFromProfileResponse(BaseModel):
    brief: PosterBrief
    art_direction: PosterArtDirection
    background: BackgroundImageResult
    render: PosterRenderResult
    image_base64: str