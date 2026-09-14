"""Section-boundary chunking using the actual embedding tokenizer."""
from dataclasses import dataclass, replace
from app.core.config import settings
from app.services.extraction import Block
from app.services.tags import extract_tags


@dataclass
class Chunk:
    content: str
    embedding_text: str
    token_count: int
    section_path: list[str]
    page_start: int
    page_end: int
    bounding_boxes: list[dict]
    content_type: str


class Chunker:
    def __init__(self, tokenizer, target=None, maximum=None, overlap=None):
        self.tokenizer = tokenizer
        self.target = target or settings.chunk_target_tokens
        self.maximum = maximum or settings.chunk_max_tokens
        self.overlap = settings.chunk_overlap_tokens if overlap is None else overlap

    def count(self, text):
        return len(self.tokenizer.encode(text, add_special_tokens=True))

    def contextualize(self, title, section, content):
        tags = extract_tags(content)
        context = "Document: " + title
        if section:
            context += "\nSection: " + " > ".join(section)
        if tags["equipment_tags"]:
            context += "\nEquipment: " + ", ".join(tags["equipment_tags"])
        return context + "\n\n" + content

    def split_block(self, block, title):
        """Use source character offsets; never decode tokens into altered quotes."""
        text = block.text
        while text:
            if self.count(self.contextualize(title, block.section_path, text)) <= self.maximum:
                yield replace(block, text=text)
                break
            lo, hi = 1, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if self.count(self.contextualize(title, block.section_path, text[:mid])) <= self.target:
                    lo = mid
                else:
                    hi = mid - 1
            if lo <= 1 or self.count(self.contextualize(title, block.section_path, text[:lo])) > self.maximum:
                raise ValueError("Document headings leave no room for chunk content")
            # Prefer paragraph/step boundaries; fall back to whitespace for very long paragraphs.
            boundary = text.rfind("\n", 0, lo)
            if boundary < lo // 2:
                boundary = text.rfind(" ", 0, lo)
            end = boundary if boundary > lo // 2 else lo
            piece = text[:end].strip()
            yield replace(block, text=piece)
            next_start = end
            if self.overlap:
                offsets = self.tokenizer(piece, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
                if len(offsets) > self.overlap:
                    next_start = offsets[-self.overlap][0]
            text = text[max(1, next_start):].lstrip()

    def chunk(self, blocks: list[Block], title: str) -> list[Chunk]:
        chunks = []
        pending = []

        def emit():
            if not pending:
                return
            content = "\n\n".join(b.text for b in pending)
            embedded = self.contextualize(title, pending[0].section_path, content)
            boxes = []
            for b in pending:
                for box in b.bounding_boxes:
                    if box not in boxes:
                        boxes.append(box)
            chunks.append(Chunk(
                content, embedded, self.count(embedded), pending[0].section_path.copy(),
                min(b.page_start for b in pending), max(b.page_end for b in pending), boxes,
                pending[0].content_type if len({b.content_type for b in pending}) == 1 else "mixed",
            ))

        for original in blocks:
            for block in self.split_block(original, title):
                if pending and block.section_path != pending[0].section_path:
                    emit()
                    pending = []
                candidate = "\n\n".join(b.text for b in pending + [block])
                n = self.count(self.contextualize(title, block.section_path, candidate))
                if pending and (n > self.maximum or (
                    self.count(self.contextualize(title, block.section_path, "\n\n".join(b.text for b in pending))) >= self.target
                )):
                    emit()
                    # Repeat complete small trailing blocks only within the same section.
                    trailing = []
                    for old in reversed(pending):
                        if self.count("\n\n".join(b.text for b in [old] + trailing)) > self.overlap:
                            break
                        trailing.insert(0, old)
                    pending = trailing
                    if self.count(self.contextualize(title, block.section_path, "\n\n".join(b.text for b in pending + [block]))) > self.maximum:
                        pending = []
                pending.append(block)
        emit()
        # Small isolated sections remain intact; never merge unrelated sections or discard evidence.
        return chunks
