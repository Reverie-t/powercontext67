# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Capture every physical PDF page and retrieve evidence pages through Memory."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from io import BytesIO
from typing import Any, NoReturn
from urllib.parse import quote

from pydantic import BaseModel
from pypdf import PdfReader

from powercontext.artifacts import MemoryCitation
from powercontext.builtin.artifacts.search import analyze_fts_query, analyze_text
from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources.definitions import AdapterSourceDefinition
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence

PDF_PAGE_SOURCE_NAME = "pdf-page"
_CANDIDATE_LIMIT = 80
_ANCHOR_LIMIT = 20
_STATEMENT_BONUS = 12.0
_BALANCE_BONUS = 9.0
_CASH_BONUS = 9.0
_SPLIT_LETTER = re.compile(r"(?<=[a-z]{2})\s+(?=[a-z](?:\s|[^a-z]|$))")
_WHITESPACE = re.compile(r"\s+")
_INCOME_HEADINGS = (
    "statementsofincome",
    "statementofincome",
    "statementsofoperations",
    "statementofoperations",
    "statementsofearnings",
    "statementofearnings",
)
_TOKEN_ALIASES = {
    "cashflow": ("cash", "flow"),
    "cyclicality": ("cyclical",),
    "ppne": ("property", "plant", "equipment"),
    "ppe": ("property", "plant", "equipment"),
    "dpo": ("payable",),
    "cogs": ("cost", "sales"),
}
_GEO_TERMS = (
    "geographic",
    "geography",
    "geographies",
    "regions",
    "international",
    "emea",
    "apac",
    "countries",
    "segments",
    "america",
    "europe",
    "latin",
    "operations",
    "lacc",
    "united",
)
_LEGAL_TERMS = ("proceedings", "litigation", "contingencies", "lawsuits", "claims", "proceeding")
_LEGAL_CUES = frozenset({"legal", "lawsuit", "lawsuits", "battle", "battles", "litigation"})


class PDFDocumentInput(BaseModel):
    """One complete original PDF addressed by a caller-stable document id."""

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """One physical page, including blank pages, tied to the file digest."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str


class PDFPageSource(Source):
    """Captured page whose identity changes when the PDF bytes change."""

    source_id: str
    document_id: str
    document_sha256: str
    page_number: int
    text: str


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Parse every physical page before returning any of them."""

    if value.document_id.strip() == "":
        _invalid("document_id must not be blank")
    try:
        return _pages(value.document_id, value.content)
    except ValueError:
        raise
    except Exception:
        _invalid("PDF could not be parsed completely")


def _page_source_id(document_id: str, document_sha256: str, page_number: int) -> str:
    source_id = f"pdf:{quote(document_id, safe='')}:{document_sha256}:{page_number}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        _invalid("source id must not exceed 256 characters")
    return source_id


class PDFPageSourceAdapter:
    """Resolve one parsed page and read that same page back."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        source_id = _page_source_id(value.document_id, value.document_sha256, value.page_number)
        return PDFPageSource(
            name=source_id,
            source_id=source_id,
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            document_sha256=value.document_sha256,
            page_number=value.page_number,
            text=value.text,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class PDFPageTextEvidenceProjection:
    """Expose one page as document-tagged text addressed by its physical page number."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.name,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


async def search_pdf_pages(memory: Any, question: str, limit: int = 10) -> tuple[MemoryCitation, ...]:
    """Return distinct page citations after ranking every stored page for the question."""

    if limit < 1 or question.strip() == "":
        return ()
    records = await _stored_pages(memory, question)
    return tuple(record.citation for record in _rank_pages(question, records)[:limit])


def _pages(document_id: str, content: bytes) -> tuple[PDFPageInput, ...]:
    digest = hashlib.sha256(content).hexdigest()
    reader = PdfReader(BytesIO(content))
    if reader.is_encrypted and reader.decrypt("") == 0:
        _invalid("PDF user password is not empty")
    pages: list[PDFPageInput] = []
    for page_number, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        text = "" if extracted.strip() == "" else extracted
        _page_source_id(document_id, digest, page_number)
        pages.append(
            PDFPageInput(
                document_id=document_id,
                document_sha256=digest,
                page_number=page_number,
                text=text,
            )
        )
    if not pages:
        _invalid("PDF contains no pages")
    return tuple(pages)


async def _stored_pages(memory: Any, question: str) -> list[Any]:
    if hasattr(memory, "list"):
        listed = await memory.list()
        if listed.entries:
            return list(listed.entries)
    return await _search_pages(memory, question)


async def _search_pages(memory: Any, question: str) -> list[Any]:
    from powercontext.builtin.runtime.models import SearchMemoryRequest

    hits: list[Any] = []
    seen_queries: set[str] = set()
    for query, query_limit in _queries(question):
        if query in seen_queries:
            continue
        seen_queries.add(query)
        page = await memory.search(SearchMemoryRequest(query=query, mode="fts", limit=query_limit))
        hits.extend(_SearchPage(hit) for hit in page.hits)
    return hits


def _queries(question: str) -> tuple[tuple[str, int], ...]:
    terms = _question_terms(question)
    queries = [(question, _CANDIDATE_LIMIT)]
    anchors = [term for term in terms if any(character.isdigit() for character in term) or len(term) >= 7]
    queries.extend((term, _ANCHOR_LIMIT) for term in anchors[:12])
    for start in range(0, len(terms), 4):
        window = terms[start : start + 4]
        if len(window) >= 2:
            queries.append((" ".join(window), _ANCHOR_LIMIT))
    return tuple(queries)


def _rank_pages(question: str, records: list[Any]) -> list[Any]:
    unique = _unique_pages(records)
    prepared = [_prepare_page(record) for record in unique]
    document_frequency: Counter[str] = Counter()
    for terms, _counts, _compact in prepared:
        document_frequency.update(terms)
    surface = set(_surface_terms(question))
    anchors = _anchor_terms(surface)
    page_count = len(prepared)
    scores = [
        _page_score(terms, counts, compact, anchors, surface, document_frequency, page_count)
        for terms, counts, compact in prepared
    ]
    order = sorted(range(len(unique)), key=lambda index: scores[index], reverse=True)
    return [unique[index] for index in order]


def _prepare_page(record: Any) -> tuple[set[str], Counter[str], str]:
    repaired = _repair_splits(_page_text(record).casefold())
    tokens = [_stem(token) for token in analyze_text(repaired).split()]
    return set(tokens), Counter(tokens), _WHITESPACE.sub("", repaired)


def _page_text(record: Any) -> str:
    entry = getattr(record, "entry", None)
    if entry is not None:
        return entry.text
    return record.text


def _unique_pages(records: list[Any]) -> list[Any]:
    unique: list[Any] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        key = (record.citation.entry_id, record.citation.entry_version_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def _question_terms(question: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(analyze_fts_query(question).split()))


def _surface_terms(question: str) -> tuple[str, ...]:
    terms: list[str] = []
    for token in _question_terms(question):
        terms.extend(_token_aliases(token))
    if "p&l" in question.casefold():
        terms.extend(("income", "operations"))
    return tuple(dict.fromkeys(terms))


def _token_aliases(token: str) -> tuple[str, ...]:
    short_year = re.fullmatch(r"fy(\d{2})", token)
    if short_year is not None:
        return (token, f"20{short_year.group(1)}")
    full_year = re.fullmatch(r"fy(\d{4})", token)
    if full_year is not None:
        return (token, full_year.group(1))
    return (token, *_TOKEN_ALIASES.get(token, ()))


def _anchor_terms(surface: set[str]) -> set[str]:
    anchors = {_stem(token) for token in surface}
    anchors.update(_stem(token) for token in _extra_terms(surface))
    return anchors


def _extra_terms(surface: set[str]) -> tuple[str, ...]:
    return _financial_terms(surface) + _topic_terms(surface)


def _financial_terms(surface: set[str]) -> tuple[str, ...]:
    extra: list[str] = []
    if "ebitda" in surface:
        extra.extend(("depreciation", "amortization", "operating"))
    if "capex" in surface or "expenditure" in surface:
        extra.extend(("expenditures", "expenditure", "purchases", "property"))
    if "quick" in surface or "liquidity" in surface:
        extra.extend(("assets", "liabilities", "inventory", "receivable", "equivalents", "current"))
    if "gross" in surface or "margin" in surface:
        extra.extend(("profit", "sales", "revenue", "cost", "operating"))
    if "restructuring" in surface:
        extra.extend(("restructuring", "reorganization", "severance"))
    if {"tax", "rate"} <= surface:
        extra.extend(("tax", "effective", "income"))
    if "debt" in surface:
        extra.extend(("debt", "borrowing", "notes"))
    return tuple(extra)


def _topic_terms(surface: set[str]) -> tuple[str, ...]:
    extra: list[str] = []
    if any(token.startswith("geograph") for token in surface):
        extra.extend(_GEO_TERMS)
    if surface & _LEGAL_CUES:
        extra.extend(_LEGAL_TERMS)
    if surface & {"acquisition", "acquisitions", "acquired"}:
        extra.extend(("acquisition", "acquired"))
    if surface & {"customer", "customers", "concentration"}:
        extra.extend(("customer", "concentration"))
    if surface & {"product", "service", "products", "services"}:
        extra.extend(("product", "service"))
    if "dividend" in surface:
        extra.append("dividend")
    if "segment" in surface:
        extra.append("segment")
    if "inventory" in surface:
        extra.append("inventory")
    if surface & {"retiree", "retirees"}:
        extra.extend(("retiree", "postretirement", "pension"))
    return tuple(extra)


def _page_score(
    terms: set[str],
    counts: Counter[str],
    compact: str,
    anchors: set[str],
    surface: set[str],
    document_frequency: Counter[str],
    page_count: int,
) -> float:
    lexical = sum(
        math.log((page_count + 1) / (document_frequency[anchor] + 1)) for anchor in anchors if anchor in terms
    )
    return lexical + _statement_bonus(compact, surface) + _topic_bonus(compact, surface, counts)


def _statement_bonus(compact: str, surface: set[str]) -> float:
    bonus = 0.0
    if _wants_balance(surface) and "balancesheet" in compact:
        bonus += _BALANCE_BONUS
    if _wants_balance(surface) and "currentassets" in compact:
        bonus += 4
    if _wants_income(surface) and any(heading in compact for heading in _INCOME_HEADINGS):
        bonus += _STATEMENT_BONUS
    if _wants_cash(surface) and ("statementofcashflow" in compact or "cashflowsfromoperating" in compact):
        bonus += _CASH_BONUS
    return bonus


def _topic_bonus(compact: str, surface: set[str], counts: Counter[str]) -> float:
    bonus = 0.0
    if any(token.startswith("geograph") for token in surface) and ("geographic" in compact or "geographies" in compact):
        bonus += 6
    if surface & _LEGAL_CUES:
        bonus += 8 if "legalproceeding" in compact else 3 if "litigation" in compact else 0
    if _wants_segment(surface) and "businesssegment" in compact:
        bonus += 7
    if "cyclicality" in surface and "cyclical" in compact:
        bonus += 6
    if surface & {"customer", "customers"}:
        bonus += 3.2 * math.log1p(counts.get("customer", 0))
    if surface & {"retiree", "retirees"} and ("retiree" in compact or "postretirement" in compact):
        bonus += 7
    if "gross" in surface and "margin" in surface and "costofproductssold" in compact and "percenttosales" in compact:
        bonus += 8
    if surface & {"acquired", "acquisition", "acquisitions"}:
        bonus += 2.4 * math.log1p(counts.get("acquired", 0) + counts.get("acquisition", 0))
    return bonus


def _wants_balance(surface: set[str]) -> bool:
    if surface & {"quick", "liquidity", "liability", "liabilities", "roa", "ppne", "ppe", "payable", "dpo"}:
        return True
    if {"balance", "sheet"} <= surface or {"financial", "position"} <= surface:
        return True
    return "inventory" in surface and bool(surface & {"turnover", "sold"})


def _wants_income(surface: set[str]) -> bool:
    if surface & {"margin", "ebitda", "restructuring", "gross", "payable", "cogs"}:
        return True
    if {"tax", "rate"} <= surface or {"income", "statement"} <= surface or {"net", "income"} <= surface:
        return True
    if "revenue" in surface and surface & {"change", "growth", "drove"}:
        return True
    if "inventory" in surface and surface & {"turnover", "sold"}:
        return True
    return {"balance", "sheet", "statement"} <= surface


def _wants_cash(surface: set[str]) -> bool:
    if surface & {"capex", "ebitda", "cashflow"}:
        return True
    if "cash" in surface and surface & {"flow", "flows"}:
        return True
    if {"investing", "financing"} <= surface:
        return True
    return "capital" in surface and "expenditure" in surface


def _wants_segment(surface: set[str]) -> bool:
    return "segment" in surface or ("product" in surface and "categories" in surface)


def _stem(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 4:
        return token[:-1]
    return token


def _repair_splits(text: str) -> str:
    return _SPLIT_LETTER.sub("", text)


class _SearchPage:
    """Search hit shaped like a listed Memory entry for ranking."""

    def __init__(self, hit: Any) -> None:
        self.text = hit.text
        self.citation = MemoryCitation(
            memory_ref=hit.memory_ref,
            entry_id=hit.entry_id,
            entry_version_id=hit.entry_version_id,
        )


def _invalid(detail: str) -> NoReturn:
    raise ValueError(detail)


PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(
    PDFPageSourceAdapter(),
    projections=(PDFPageTextEvidenceProjection(),),
)
