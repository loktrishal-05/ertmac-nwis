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
