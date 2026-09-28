"""P&ID OCR contracts. Coordinates are pixels in stored rendered images."""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.config import settings

Category = Literal["equipment_tag", "instrument_tag", "valve_tag", "line_number",
                   "temperature_value", "pressure_value", "drawing_title", "revision", "other_text"]


class PreprocessOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grayscale: bool = True
    contrast_normalization: bool = True
    adaptive_threshold: bool = False
    denoise: bool = False
    rotation_degrees: Literal[0, 90, 180, 270] = 0


class PIDProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_path: str = Field(min_length=1, max_length=500, description="Path relative to data/raw/pids/source")
    document_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    revision: str | None = Field(default=None, max_length=100)
    synthetic: bool = False
    access_scope: str = Field(default="internal", min_length=1, max_length=50)
    render_dpi: int = Field(default_factory=lambda: settings.pid_render_dpi, ge=300, le=400)
    preprocessing: PreprocessOptions = Field(default_factory=PreprocessOptions)


class OCRDetection(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    text: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    bbox: tuple[float, float, float, float]
    polygon: list[tuple[float, float]] = Field(min_length=3)
    page: int = Field(ge=1)
    source_image: str
    image_width: int = Field(ge=1)
    image_height: int = Field(ge=1)
    ocr_engine: Literal["paddleocr_ppocrv5"] = "paddleocr_ppocrv5"
    category: Category
    identified_tags: dict[str, list[str]]
    ocr_derived: Literal[True] = True
    status: Literal["unverified", "ambiguous"] = "unverified"

    @model_validator(mode="after")
    def validate_coordinates(self):
        # Recognition confidence never verifies an asset against a registry.
        if self.confidence < 0.6:
            self.status = "ambiguous"
        left, top, right, bottom = self.bbox
        if not (0 <= left < right <= self.image_width and 0 <= top < bottom <= self.image_height):
            raise ValueError("Bounding box lies outside the rendered image or has no area")
        if any(not (left <= x <= right and top <= y <= bottom) for x, y in self.polygon):
            raise ValueError("Polygon lies outside bounding box")
        return self


class VisualCandidate(BaseModel):
    """Untrusted model observations in rendered-page pixels, never authority."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    bbox: tuple[float, float, float, float]
    region_type: Literal["equipment_symbol", "label", "arrow", "line_fragment", "title_block", "annotation_block"]
    tag: str | None = Field(default=None, max_length=100)
    confidence: float = Field(ge=0, le=1)
    uncertainty: Literal["unverified_visual_observation", "ambiguous_label", "ambiguous_symbol", "partial_region"]

    @model_validator(mode="after")
    def valid_box(self):
        x1, y1, x2, y2 = self.bbox
        if not (0 <= x1 < x2 and 0 <= y1 < y2):
            raise ValueError("Invalid visual bounding box")
        if self.tag:
            from app.services.pid_identifiers import classify_text
            normalized, category, _ = classify_text(self.tag)
            if category not in {"equipment_tag", "instrument_tag", "valve_tag"}:
                raise ValueError("Visual tag must be a single recognized identifier")
            self.tag = normalized
        return self


class VisualPageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[VisualCandidate] = Field(default_factory=list, max_length=100)


class VisionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["available", "unavailable"] = "unavailable"
    model: str | None = None
    page: int = Field(ge=1)
    source_image_uri: str
    candidates: list[VisualCandidate] = Field(default_factory=list, max_length=100)
    fallback_reason: str | None = None
    call_count: int = Field(default=0, ge=0, le=1)
    latency_ms: float = Field(default=0, ge=0)
    evidence_origin: Literal["VISUAL_MODEL"] = "VISUAL_MODEL"


class RegionFusion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_candidate: str | None
    raw_ocr_text: str | None = None
    normalized_text: str | None = None
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    visual_candidate: str | None = None
    visual_confidence: float | None = Field(default=None, ge=0, le=1)
    registry_status: Literal["VERIFIED", "CANDIDATE", "UNVERIFIED", "CONFLICTING", "UNKNOWN"]
    evidence_origin: list[Literal["OCR", "VISUAL_MODEL", "REGISTRY", "DOCUMENT_METADATA", "HUMAN_VERIFIED"]]
    provenance: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = False


class OCRRegion(BaseModel):
    ocr_derived: Literal[True] = True
    region_id: UUID
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    text_items: list[OCRDetection]
    combined_text: str
    identified_tags: dict[str, list[str]]
    region_type: Literal["equipment_label", "instrument_cluster", "title_block", "annotation_block"]
    source_image_uri: str
    visual_candidates: list[VisualCandidate] = Field(default_factory=list)
    visual_model: str | None = None


class PIDPage(BaseModel):
    page: int = Field(ge=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    source_image_uri: str
    processed_image_uri: str
    render_dpi: int | None
    original_resolution: dict
    preprocessing: PreprocessOptions
    processed_to_rendered: list[list[float]]


class PIDManifest(BaseModel):
    ocr_derived: Literal[True] = True
    document_id: UUID
    document_version_id: UUID
    source_filename: str
    source_uri: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    page_count: int = Field(ge=1)
    render_dpi: int | None
    ocr_engine: Literal["paddleocr_ppocrv5"] = "paddleocr_ppocrv5"
    ocr_model: list[str]
    pipeline_version: Literal["3b1.1"] = "3b1.1"
    processed_at: datetime
    synthetic: bool
    warnings: list[str]
    pages: list[PIDPage]
    ocr_json_uri: str
    region_json_uri: str
    ocr_detections: int = Field(ge=0)
    regions: int = Field(ge=0)
    equipment_tags: list[str]
    instrument_tags: list[str]
    vision: list[VisionEvidence] = Field(default_factory=list)
    operational_metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_pages(self):
        if [p.page for p in self.pages] != list(range(1, self.page_count + 1)):
            raise ValueError("Manifest pages must be consecutive and complete")
        return self


class PIDProcessResponse(BaseModel):
    document_id: UUID
    document_version_id: UUID
    filename: str
    source_sha256: str
    status: Literal["processed", "duplicate"]
    pages: int
    ocr_detections: int
    regions: int
    equipment_tags: list[str]
    instrument_tags: list[str]
    manifest_uri: str
    warnings: list[str]
