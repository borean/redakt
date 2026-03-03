import asyncio
import json as _json
import logging
import re
from collections import defaultdict

import httpx
log = logging.getLogger(__name__)

from redakt.constants import Backend, LLAMACPP_API_MODEL, LLAMACPP_HOST, Language
from redakt.core.entities import PIIEntity, PIIResponse
from redakt.core.prompts import (
    CHAT_SYSTEM_EN,
    CHAT_SYSTEM_TR,
    CHAT_USER_EN,
    CHAT_USER_TR,
    SYSTEM_PROMPT_EN,
    SYSTEM_PROMPT_TR,
    USER_PROMPT_TEMPLATE_EN,
    USER_PROMPT_TEMPLATE_TR,
    VISION_PROMPT_EN,
    VISION_PROMPT_TR,
)

# Map LLM's free-form category names to our canonical categories
_CATEGORY_ALIASES: dict[str, str] = {
    # Canonical
    "name": "name",
    "date": "date",
    "id": "id",
    "address": "address",
    "phone": "phone",
    "email": "email",
    "institution": "institution",
    "age": "age",
    # Common LLM variations
    "person": "name",
    "patient": "name",
    "doctor": "name",
    "physician": "name",
    "person_name": "name",
    "patient_name": "name",
    "doctor_name": "name",
    "organization": "institution",
    "org": "institution",
    "hospital": "institution",
    "clinic": "institution",
    "school": "institution",
    "university": "institution",
    "telephone": "phone",
    "tel": "phone",
    "mobile": "phone",
    "phone_number": "phone",
    "national_id": "id",
    "id_number": "id",
    "tc": "id",
    "ssn": "id",
    "protocol": "id",
    "birth_date": "date",
    "date_of_birth": "date",
    "dob": "date",
    "dogum_tarihi": "date",
    "doğum_tarihi": "date",
    "visit_date": "date",
    "report_date": "date",
    "admission_date": "date",
    "tarih": "date",
    "tarihi": "date",
    "doğum": "date",
    "dogum": "date",
    "discharge_date": "date",
    "surgery_date": "date",
    "test_date": "date",
    "exam_date": "date",
    "procedure_date": "date",
    "date/time": "date",
    "datetime": "date",
    "location": "address",
    "city": "address",
    "district": "address",
    "addr": "address",
    "email_address": "email",
}

class Anonymizer:
    """Core anonymization engine.

    Uses llama.cpp server's OpenAI-compatible /v1/chat/completions
    with response_format: {type: "json_object"}, no user setup required.
    """

    def __init__(
        self,
        model: str = LLAMACPP_API_MODEL,
        language: Language = Language.TR,
        backend: Backend = Backend.LLAMACPP,
    ):
        self.model = model or LLAMACPP_API_MODEL
        self.language = language
        self.backend = backend

    # ── Prompt helpers ────────────────────────────────────────────────

    def _get_prompts(self) -> tuple[str, str]:
        if self.language == Language.TR:
            return SYSTEM_PROMPT_TR, USER_PROMPT_TEMPLATE_TR
        return SYSTEM_PROMPT_EN, USER_PROMPT_TEMPLATE_EN

    def _get_vision_prompt(self) -> tuple[str, str]:
        if self.language == Language.TR:
            return SYSTEM_PROMPT_TR, VISION_PROMPT_TR
        return SYSTEM_PROMPT_EN, VISION_PROMPT_EN

    # ── Category normalization ────────────────────────────────────────

    @staticmethod
    def _normalize_category(raw: str) -> str:
        """Map LLM's category output to our canonical set."""
        key = raw.strip().lower().replace(" ", "_")
        return _CATEGORY_ALIASES.get(key, "name")

    def _normalize_entities(self, response: PIIResponse) -> PIIResponse:
        """Fix up entity categories returned by the LLM."""
        for entity in response.entities:
            raw_key = entity.category.strip().lower().replace(" ", "_")
            entity.subcategory = raw_key  # preserve raw LLM category
            entity.category = self._normalize_category(entity.category)
        return response

    # ── Backend: llama.cpp ────────────────────────────────────────────

    @staticmethod
    def _repair_json(text: str) -> str:
        """Attempt to repair common JSON issues from LLM output.

        Handles: trailing commas, truncated JSON, single quotes, unquoted keys,
        control characters, and other common LLM JSON generation errors.
        """
        # Remove BOM and zero-width chars
        text = text.strip().lstrip("\ufeff")

        # Remove trailing commas before } or ]
        text = re.sub(r",\s*([}\]])", r"\1", text)

        # Fix single-quoted strings → double-quoted (only for keys/values)
        # This is a heuristic: replace 'key': 'value' patterns
        text = re.sub(r"(?<=[\[{,])\s*'([^']*?)'\s*:", r' "\1":', text)
        text = re.sub(r":\s*'([^']*?)'\s*(?=[,}\]])", r': "\1"', text)

        # Remove control characters that break JSON parsing
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)

        # Fix truncated JSON — close unclosed brackets/braces
        # Count open vs close brackets
        open_brackets = text.count("[") - text.count("]")
        open_braces = text.count("{") - text.count("}")

        if open_brackets > 0 or open_braces > 0:
            # JSON is truncated — try to find the last complete element
            # Look for the last complete object boundary
            last_brace = text.rfind("}")
            if last_brace > 0:
                text = text[: last_brace + 1]
                # Recount after trim
                open_brackets = text.count("[") - text.count("]")
                open_braces = text.count("{") - text.count("}")
                # Close remaining
                text += "]" * max(0, open_brackets) + "}" * max(0, open_braces)
            else:
                text = '{"entities": [], "summary": "Parse error: truncated response"}'

        return text

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from LLM output that may have markdown fences or extra text."""
        # Strip markdown code fences: ```json ... ``` or ``` ... ```
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()

        # Try to find JSON object or array in the text
        text = text.strip()

        # If response starts with explanatory text before JSON, extract the JSON
        if not text.startswith(("{", "[")):
            # Look for the first { or [
            json_start = -1
            for i, ch in enumerate(text):
                if ch in ("{", "["):
                    json_start = i
                    break
            if json_start >= 0:
                text = text[json_start:]
            else:
                # No JSON found at all — return empty
                return '{"entities": [], "summary": "No JSON found in response"}'

        # If the response is a bare array, wrap it in our expected object
        if text.startswith("["):
            try:
                arr = _json.loads(text)
                return _json.dumps({"entities": arr, "summary": ""})
            except _json.JSONDecodeError:
                pass

        return text

    async def _chat_llamacpp(self, messages: list[dict], max_retries: int = 3) -> str:
        """Send a chat request to llama.cpp server (OpenAI-compatible).

        Retries on 500 errors with exponential backoff.
        """
        # Enhance the system prompt to ensure JSON object output
        enhanced_messages = list(messages)
        if enhanced_messages and enhanced_messages[0]["role"] == "system":
            enhanced_messages[0] = {
                **enhanced_messages[0],
                "content": (
                    enhanced_messages[0]["content"]
                    + '\n\nIMPORTANT: Return your response as a valid JSON object with '
                    '"entities" array and "summary" string. Every string key and value '
                    'must use double quotes. Do NOT use markdown fences or trailing commas.'
                ),
            }

        payload = {
            "model": self.model,
            "messages": enhanced_messages,
            "temperature": 0.1,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
                    resp = await client.post(
                        f"{LLAMACPP_HOST}/v1/chat/completions",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"llama.cpp error: {data['error']}")
                raw = data["choices"][0]["message"]["content"]
                return self._extract_json(raw)
            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code
                if status >= 500 and attempt < max_retries - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    log.warning(
                        "llama.cpp returned %d, retrying in %ds (attempt %d/%d)",
                        status, wait, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(
                    f"llama.cpp server error (HTTP {status}). "
                    f"The server may be overloaded or the model may have run out of memory. "
                    f"Try again or check llama-server logs."
                ) from e
            except httpx.ConnectError as e:
                raise RuntimeError(
                    "Cannot connect to llama-server. "
                    "The server may have crashed. Restart the app to try again."
                ) from e
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

        raise RuntimeError(str(last_error)) if last_error else RuntimeError("Unknown error")

    # ── Free-form (plain text) chat ─────────────────────────────────

    async def _chat_freeform_llamacpp(self, messages: list[dict], max_retries: int = 3) -> str:
        """Send a free-form chat to llama.cpp (no JSON constraint).

        Retries on 500 errors with exponential backoff.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
                    resp = await client.post(
                        f"{LLAMACPP_HOST}/v1/chat/completions",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"llama.cpp error: {data['error']}")
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code
                if status >= 500 and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    log.warning(
                        "llama.cpp returned %d on freeform, retrying in %ds (%d/%d)",
                        status, wait, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(
                    f"llama.cpp server error (HTTP {status}). "
                    f"Try again or restart the app."
                ) from e
            except httpx.ConnectError as e:
                raise RuntimeError(
                    "Cannot connect to llama-server. "
                    "The server may have crashed."
                ) from e
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

        raise RuntimeError(str(last_error)) if last_error else RuntimeError("Unknown error")

    async def _chat_freeform(self, messages: list[dict], model: str | None = None) -> str:
        """Free-form (non-JSON) chat via llama.cpp."""
        return await self._chat_freeform_llamacpp(messages)

    async def _chat(self, messages: list[dict], model: str | None = None) -> str:
        """Chat via llama.cpp."""
        return await self._chat_llamacpp(messages)

    # ── Response normalization ─────────────────────────────────────────

    @classmethod
    def _normalize_llm_response(cls, raw_json: str) -> str:
        """Normalize LLM JSON to our schema regardless of field names used.

        Different models return different field conventions:
        - Qwen3.5 (free-form):  {"value", "type", "context"}
        - Others:               {"text", "label", "replacement"}

        This normalizer handles all of them.  It also repairs common JSON
        errors from LLM output (trailing commas, truncation, etc.).
        """
        # First pass: try strict parsing
        try:
            data = _json.loads(raw_json)
        except _json.JSONDecodeError:
            # Second pass: attempt repair
            repaired = cls._repair_json(raw_json)
            try:
                data = _json.loads(repaired)
            except _json.JSONDecodeError as e:
                log.warning("JSON repair failed: %s — raw: %s", e, raw_json[:500])
                # Return empty result so the app doesn't crash
                return _json.dumps({
                    "entities": [],
                    "summary": f"LLM returned invalid JSON (parse error at char {e.pos})",
                })

        # Find the entity list (different models use different keys)
        entities_raw = (
            data.get("entities")
            or data.get("results")
            or data.get("pii")
            or data.get("pii_entities")
            or []
        )

        normalized = []
        for e in entities_raw:
            if not isinstance(e, dict):
                continue
            original = (
                e.get("original")
                or e.get("value")
                or e.get("text")
                or e.get("entity")
                or ""
            )
            category = (
                e.get("category")
                or e.get("type")
                or e.get("label")
                or e.get("tag")
                or "unknown"
            )
            placeholder = (
                e.get("placeholder")
                or e.get("replacement")
                or e.get("anonymized")
                or ""
            )
            raw_conf = e.get("confidence") or e.get("score") or 1.0
            try:
                confidence = max(0.0, min(1.0, float(raw_conf)))
            except (ValueError, TypeError):
                confidence = 1.0

            if not original:
                continue  # skip entities with no text

            normalized.append({
                "original": original,
                "category": category,
                "placeholder": placeholder or f"[{category.upper()}]",
                "confidence": confidence,
                "subcategory": e.get("subcategory"),  # pass through if present
            })

        return _json.dumps({
            "entities": normalized,
            "summary": data.get("summary", ""),
        })

    # ── PII detection ─────────────────────────────────────────────────

    def _extract_dates_by_regex(self, text: str) -> list[PIIEntity]:
        """Fallback: extract date-like patterns when LLM returns nothing.

        Uses regex to find DD.MM.YYYY, YYYY-MM-DD, and similar formats.
        Returns unique PIIEntity list (deduplicated by original text).
        """
        seen: set[str] = set()
        entities: list[PIIEntity] = []
        patterns = [
            r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}",
            r"\d{4}-\d{1,2}-\d{1,2}",
            r"\d{4}/\d{1,2}/\d{1,2}",
            r"\d{1,2}[\s.\-]+(?:ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)[\s.\-]+\d{4}",
            r"(?:ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)[\s.\-]+\d{1,2},?\s*\d{4}",
            r"\d{1,2}[./]\d{4}",
        ]
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                orig = m.group(0).strip()
                if orig in seen:
                    continue
                if self._parse_date(orig):
                    seen.add(orig)
                    entities.append(
                        PIIEntity(
                            original=orig,
                            category="date",
                            placeholder="",  # renumber later
                            subcategory="date",
                        )
                    )
        return entities

    async def detect_pii_from_text(self, text: str) -> PIIResponse:
        sys_prompt, usr_template = self._get_prompts()

        content = await self._chat([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": usr_template.format(text=text)},
        ])

        # Normalize whatever the LLM returns to our expected schema
        content = self._normalize_llm_response(content)
        try:
            result = PIIResponse.model_validate_json(content)
        except Exception as e:
            log.warning("Failed to validate PII response: %s", e)
            # If Pydantic validation fails, try to extract what we can
            try:
                data = _json.loads(content)
                result = PIIResponse(
                    entities=[],
                    summary=data.get("summary", f"Validation error: {e}"),
                )
            except Exception:
                result = PIIResponse(entities=[], summary=f"Parse error: {e}")

        # Fallback: when LLM returns no entities, use regex to extract dates
        if not result.entities:
            fallback = self._extract_dates_by_regex(text)
            if fallback:
                log.info("LLM returned no PII; using regex fallback for %d date(s)", len(fallback))
                result = PIIResponse(
                    entities=self._renumber_placeholders(fallback),
                    summary="Dates found via pattern matching",
                )

        return self._normalize_entities(result)

    async def detect_pii_from_image(self, image_path: str) -> PIIResponse:
        """Image PII: use OCR to extract text, then run text PII detection."""
        import fitz

        doc = fitz.open(image_path)
        try:
            page = doc[0]
            text = page.get_text("text")
            if not text.strip():
                try:
                    tp = page.get_textpage_ocr(language="tur+eng", dpi=300)
                    text = page.get_text("text", textpage=tp)
                except Exception:
                    text = ""
        finally:
            doc.close()

        if not text.strip():
            return PIIResponse(
                entities=[],
                summary="No text could be extracted from the image. Try a higher resolution image.",
            )
        return await self.detect_pii_from_text(text)

    # ── Chunking ──────────────────────────────────────────────────────

    def chunk_text(self, text: str, max_chars: int = 24000, overlap: int = 500) -> list[str]:
        if len(text) <= max_chars:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + max_chars
            if end < len(text):
                para_break = text.rfind("\n\n", start, end)
                if para_break > start + max_chars // 2:
                    end = para_break
            chunks.append(text[start:end])
            start = end - overlap
        return chunks

    def _renumber_placeholders(self, entities: list[PIIEntity]) -> list[PIIEntity]:
        """Assign consistent placeholder numbers across all entities."""
        counters: dict[str, int] = defaultdict(int)
        prefix_map = {
            "name": "AD" if self.language == Language.TR else "NAME",
            "date": "TARIH" if self.language == Language.TR else "DATE",
            "id": "KIMLIK" if self.language == Language.TR else "ID",
            "address": "ADRES" if self.language == Language.TR else "ADDR",
            "phone": "TELEFON" if self.language == Language.TR else "PHONE",
            "email": "EPOSTA" if self.language == Language.TR else "EMAIL",
            "institution": "KURUM" if self.language == Language.TR else "INST",
            "age": "YAS" if self.language == Language.TR else "AGE",
        }

        seen: dict[str, str] = {}
        result = []
        for entity in entities:
            if entity.original in seen:
                entity.placeholder = seen[entity.original]
            else:
                prefix = prefix_map.get(entity.category, entity.category.upper())
                counters[entity.category] += 1
                placeholder = f"[{prefix}_{counters[entity.category]}]"
                entity.placeholder = placeholder
                seen[entity.original] = placeholder
            result.append(entity)
        return result

    # ── Age-based date conversion ─────────────────────────────────────

    # Turkish month names for date parsing
    _TURKISH_MONTHS = {
        "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4,
        "mayıs": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
        "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
        # ASCII variants (common in medical docs)
        "subat": 2, "mayis": 5, "agustos": 8, "eylul": 9, "kasim": 11, "aralik": 12,
    }

    _BIRTH_DATE_SUBCATS = frozenset({
        "birth_date", "date_of_birth", "dob", "dogum_tarihi",
        "doğum_tarihi", "dogum", "doğum",
    })

    # English month names (full + abbreviated)
    _ENGLISH_MONTHS = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        # 3-letter abbreviations
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    # Merged month lookup (Turkish + English, all lowercase)
    _ALL_MONTHS = {**_TURKISH_MONTHS, **_ENGLISH_MONTHS}

    @staticmethod
    def _parse_date(text: str):
        """Parse various date formats common in Turkish medical documents.

        Handles:
        - DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY
        - YYYY-MM-DD (ISO)
        - DD Month YYYY (Turkish or English, full or abbreviated month names)
        - Month YYYY or YYYY Month (e.g. "Mar 2012", "Ekim 2019")
        - DD Month (assumes current year)
        - Standalone 4-digit year (e.g. "2012") — returns Jan 1 of that year
        - MM/YYYY or MM.YYYY

        Returns a datetime.date or None.
        """
        from datetime import date as date_type
        import re as _re

        text = text.strip().replace("\u00a0", " ")  # nbsp

        def _expand_year(y: int) -> int:
            """Expand 2-digit year to 4-digit (00-49 -> 2000s, 50-99 -> 1900s)."""
            if y < 100:
                return y + 2000 if y < 50 else y + 1900
            return y

        # DD.MM.YYYY or DD/MM/YYYY or DD-MM-YYYY (also handles 2-digit year)
        m = _re.match(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})\b", text)
        if m:
            try:
                return date_type(
                    _expand_year(int(m.group(3))),
                    int(m.group(2)),
                    int(m.group(1)),
                )
            except ValueError:
                pass

        # YYYY-MM-DD (ISO)
        m = _re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
        if m:
            try:
                return date_type(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        # YYYY/MM/DD
        m = _re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})\b", text)
        if m:
            try:
                return date_type(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        # DD Month YYYY (Turkish or English, full or abbreviated)
        m = _re.match(r"(\d{1,2})[\s.\-]+([a-zA-ZçğıöşüÇĞİÖŞÜ]+)[\s.\-]+(\d{4})\b", text)
        if m:
            day, month_str, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            month = Anonymizer._ALL_MONTHS.get(month_str)
            if month:
                try:
                    return date_type(year, month, day)
                except ValueError:
                    pass

        # Month DD, YYYY (English format: "March 15, 2012")
        m = _re.match(
            r"([a-zA-ZçğıöşüÇĞİÖŞÜ]+)[\s.\-]+(\d{1,2}),?\s*(\d{4})\b", text
        )
        if m:
            month_str, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
            month = Anonymizer._ALL_MONTHS.get(month_str)
            if month:
                try:
                    return date_type(year, month, day)
                except ValueError:
                    pass

        # Month YYYY (e.g. "Ekim 2019", "Mar 2012") — day defaults to 1
        m = _re.match(r"([a-zA-ZçğıöşüÇĞİÖŞÜ]+)[\s.\-]+(\d{4})\b", text)
        if m:
            month_str, year = m.group(1).lower(), int(m.group(2))
            month = Anonymizer._ALL_MONTHS.get(month_str)
            if month:
                try:
                    return date_type(year, month, 1)
                except ValueError:
                    pass

        # YYYY Month (e.g. "2019 Ekim")
        m = _re.match(r"(\d{4})[\s.\-]+([a-zA-ZçğıöşüÇĞİÖŞÜ]+)\b", text)
        if m:
            year, month_str = int(m.group(1)), m.group(2).lower()
            month = Anonymizer._ALL_MONTHS.get(month_str)
            if month:
                try:
                    return date_type(year, month, 1)
                except ValueError:
                    pass

        # MM/YYYY or MM.YYYY (e.g. "03/2012")
        m = _re.match(r"(\d{1,2})[./](\d{4})\b", text)
        if m:
            month_val, year = int(m.group(1)), int(m.group(2))
            if 1 <= month_val <= 12:
                try:
                    return date_type(year, month_val, 1)
                except ValueError:
                    pass

        # Standalone 4-digit year (e.g. "2012") — return Jan 1
        m = _re.fullmatch(r"(\d{4})", text.strip())
        if m:
            year = int(m.group(1))
            if 1900 <= year <= 2100:
                try:
                    return date_type(year, 1, 1)
                except ValueError:
                    pass

        # ── Fallback: search for a date anywhere in the text ──────────
        # LLMs sometimes include extra text around the date
        # (e.g. "D.T: 29.03.2012" or "29.03.2012 tarihli")
        m = _re.search(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})", text)
        if m:
            try:
                return date_type(
                    _expand_year(int(m.group(3))),
                    int(m.group(2)),
                    int(m.group(1)),
                )
            except ValueError:
                pass

        m = _re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        if m:
            try:
                return date_type(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        # Fallback: standalone 4-digit year anywhere in text (e.g. "menarş 2022")
        m = _re.search(r"\b(\d{4})\b", text)
        if m:
            year = int(m.group(1))
            if 1900 <= year <= 2100:
                try:
                    return date_type(year, 1, 1)
                except ValueError:
                    pass

        return None

    @staticmethod
    def _calc_age_diff(birth, event) -> tuple[int, int]:
        """Return (years, months) difference between birth and event date."""
        years = event.year - birth.year
        months = event.month - birth.month
        if event.day < birth.day:
            months -= 1
        if months < 0:
            years -= 1
            months += 12
        return max(0, years), max(0, months)

    # Patterns that indicate a birth date in Turkish and English medical documents
    # Used for context scanning BEFORE the date entity
    _BIRTH_CONTEXT_PATTERNS_BEFORE = (
        # Turkish — full forms
        "doğum tarihi", "dogum tarihi", "doğum tar.",
        "d.tarihi", "dtarihi", "d. tarihi", "d tarihi",
        # Turkish — abbreviations and short forms
        "doğum:", "dogum:", "doğ.tar.", "doğ.tar:", "doğ tar",
        "d.t.", "d.t:", "dt:", "dt.",
        # Turkish — age/birth cues
        "yaş:", "yas:", "yaşı:", "yasi:",
        "doğ:", "dog:",
        # English — full forms
        "date of birth", "birth date", "birthdate",
        "born on", "born:",
        # English — abbreviations
        "dob:", "dob ", "dob.", "d.o.b.", "d.o.b:",
        # German (common in medical contexts)
        "geboren:", "geboren am", "geb.", "geb:",
        # Generic label-like patterns
        "doğum", "dogum",
    )

    # Patterns that indicate a birth date AFTER the date entity
    # e.g. "29.03.2012 doğumlu", "2012 doğumlu hasta"
    _BIRTH_CONTEXT_PATTERNS_AFTER = (
        "doğumlu", "dogumlu", "doğ.", "doğumludur",
        "dogumludur",
        "born", "geboren",
        "d.t.", "doğum tarihli", "dogum tarihli",
    )

    def _find_birth_date_by_context(self, entities: list, document_text: str) -> tuple:
        """Fallback: find a birth date by scanning document context around date entities.

        Looks for patterns like 'Doğum Tarihi: 29.03.2012' or '29.03.2012 doğumlu'
        near entity text.  Searches 120 chars before and 40 chars after.
        Returns (parsed_date, entity) or (None, None).
        """
        if not document_text:
            return None, None

        text_lower = document_text.lower()
        for e in entities:
            if e.category != "date":
                continue
            # Find where this date appears in the document
            orig_lower = e.original.lower()
            pos = text_lower.find(orig_lower)
            if pos < 0:
                continue

            # Check 120 chars BEFORE the date for birth-related keywords
            context_start = max(0, pos - 120)
            context_before = text_lower[context_start:pos]
            for pattern in self._BIRTH_CONTEXT_PATTERNS_BEFORE:
                if pattern in context_before:
                    parsed = self._parse_date(e.original)
                    if parsed:
                        log.debug("Birth date found by BEFORE context (%r): %s", pattern, e.original)
                        return parsed, e

            # Check 40 chars AFTER the date for birth-related keywords
            after_start = pos + len(orig_lower)
            after_end = min(len(text_lower), after_start + 40)
            context_after = text_lower[after_start:after_end]
            for pattern in self._BIRTH_CONTEXT_PATTERNS_AFTER:
                if pattern in context_after:
                    parsed = self._parse_date(e.original)
                    if parsed:
                        log.debug("Birth date found by AFTER context (%r): %s", pattern, e.original)
                        return parsed, e

        return None, None

    @staticmethod
    def _is_plausible_birth_date(d) -> bool:
        """Check whether *d* could plausibly be a birth date (age 0-120)."""
        from datetime import date as date_type

        today = date_type.today()
        age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
        return 0 <= age <= 120

    # ── Regex-based birth date detection (Strategy 0) ─────────────────

    # Compiled patterns for direct birth-date extraction from document text.
    # Each pattern has one capture group for the date portion.
    _BIRTH_DATE_REGEX_PATTERNS: list[re.Pattern] = []

    @classmethod
    def _compile_birth_date_patterns(cls) -> list[re.Pattern]:
        """Compile and cache regex patterns for birth date extraction."""
        if cls._BIRTH_DATE_REGEX_PATTERNS:
            return cls._BIRTH_DATE_REGEX_PATTERNS

        _DATE_NUM = r"(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})"
        _DATE_ISO = r"(\d{4}-\d{1,2}-\d{1,2})"  # YYYY-MM-DD
        _DATE_NAMED = r"(\d{1,2}\s+\w+\s+\d{4})"

        # Optional parenthetical (e.g. "(*)" for required fields in medical forms)
        _OPT_PAREN = r"(?:\s*\([^)]*\))?"
        raw_patterns = [
            # ── Turkish patterns ──
            # "Doğum tarihi: 29.03.2012" / "Doğum Tarihi (*) : 23.02.2015"
            r"do[gğ]um\s*tarihi" + _OPT_PAREN + r"\s*[:=]?\s*" + _DATE_NUM,
            r"do[gğ]um\s*tarihi" + _OPT_PAREN + r"\s*[:=]?\s*" + _DATE_ISO,
            r"do[gğ]um\s*tarihi" + _OPT_PAREN + r"\s*[:=]?\s*" + _DATE_NAMED,
            # "D.Tarihi: 29.03.2012" / "D. Tarihi (*) : 23.02.2015"
            r"d\.?\s*tarihi" + _OPT_PAREN + r"\s*[:=]?\s*" + _DATE_NUM,
            r"d\.?\s*tarihi" + _OPT_PAREN + r"\s*[:=]?\s*" + _DATE_ISO,
            r"d\.?\s*tarihi" + _OPT_PAREN + r"\s*[:=]?\s*" + _DATE_NAMED,
            # "D.T.: 29.03.2012" / "DT: 29.03.2012" / "D.T: ..."
            r"d\.?\s*t\.?\s*[:=]\s*" + _DATE_NUM,
            # "Doğumlu: 29.03.2012" (label form)
            r"do[gğ]umlu\s*[:=]?\s*" + _DATE_NUM,
            # "29.03.2012 doğumlu" (postfix form)
            _DATE_NUM + r"\s*do[gğ]umlu",
            # "Doğ.Tar.: 29.03.2012"
            r"do[gğ]\.?\s*tar\.?\s*[:=]?\s*" + _DATE_NUM,

            # ── English patterns ──
            # "Date of Birth: 29/03/2012" / "Date of Birth (*) : 23.02.2015"
            r"(?:date\s*of\s*birth|dob|birth\s*date)" + _OPT_PAREN + r"\s*[:=]?\s*" + _DATE_NUM,
            r"(?:date\s*of\s*birth|dob|birth\s*date)" + _OPT_PAREN + r"\s*[:=]?\s*" + _DATE_ISO,
            r"(?:date\s*of\s*birth|dob|birth\s*date)" + _OPT_PAREN + r"\s*[:=]?\s*" + _DATE_NAMED,
            # "Born: 29/03/2012" / "Born on 29/03/2012"
            r"born\s+(?:on\s+)?" + _DATE_NUM,
            r"born\s+(?:on\s+)?" + _DATE_NAMED,
            # "D.O.B.: 29/03/2012"
            r"d\.o\.b\.?\s*[:=]?\s*" + _DATE_NUM,
        ]

        cls._BIRTH_DATE_REGEX_PATTERNS = [
            re.compile(p, re.IGNORECASE) for p in raw_patterns
        ]
        return cls._BIRTH_DATE_REGEX_PATTERNS

    def _find_birth_date_by_regex_scan(self, document_text: str):
        """Scan the entire document text with regex patterns to find a birth date.

        This bypasses the LLM's subcategory classification entirely and directly
        looks for birth date references like "Doğum Tarihi: 29.03.2012".

        Returns a datetime.date or None.
        """
        if not document_text:
            return None

        patterns = self._compile_birth_date_patterns()

        for pattern in patterns:
            m = pattern.search(document_text)
            if m:
                date_str = m.group(1)
                parsed = self._parse_date(date_str)
                if parsed and self._is_plausible_birth_date(parsed):
                    log.debug(
                        "Birth date found by regex scan (pattern=%s): %s -> %s",
                        pattern.pattern, date_str, parsed,
                    )
                    return parsed

        return None

    # Phrases that indicate birth date (fuzzy match against context before a date)
    _BIRTH_PHRASES = (
        "doğum tarihi", "dogum tarihi", "doğum tarih",
        "d.tarihi", "d.t.", "dt:", "d.t:", "d.tarih",
        "doğumlu", "dogumlu",
        "date of birth", "birth date", "dob", "d.o.b",
        "born", "born on",
    )

    # Phrases that indicate NOT birth date (examination, report, etc.)
    _NON_BIRTH_PHRASES = (
        "muayene tarihi", "examination date", "visit date",
        "rapor tarihi", "report date", "sonuç tarihi",
        "yatış", "taburcu", "admission", "discharge",
    )

    def _find_birth_date_by_fuzzy_scan(self, document_text: str):
        """Fuzzy fallback: find dates whose preceding context resembles birth date.

        Handles unexpected conventions (e.g. "Dogum Tarihi", "DT: 23.02.2015",
        "birth date 23.02.2015", OCR typos). Runs after regex patterns fail.
        """
        if not document_text:
            return None

        try:
            from rapidfuzz.fuzz import partial_ratio
        except ImportError:
            return None

        # Broad date pattern: DD.MM.YYYY, YYYY-MM-DD, DD/MM/YYYY, etc.
        date_re = re.compile(
            r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}"
        )
        context_before = 100

        for m in date_re.finditer(document_text):
            date_str = m.group(0)
            parsed = self._parse_date(date_str)
            if not parsed or not self._is_plausible_birth_date(parsed):
                continue

            start = max(0, m.start() - context_before)
            context = document_text[start: m.end()].lower()

            # Reject if context clearly indicates non-birth date
            for phrase in self._NON_BIRTH_PHRASES:
                if partial_ratio(phrase, context) >= 90:
                    break
            else:
                # No non-birth phrase matched; check for birth phrase
                for phrase in self._BIRTH_PHRASES:
                    if partial_ratio(phrase, context) >= 80:
                        log.debug(
                            "Birth date found by fuzzy scan (phrase=%r): %s -> %s",
                            phrase, date_str, parsed,
                        )
                        return parsed

        return None

    async def _identify_birth_date_via_llm(
        self, entities: list, document_text: str,
    ) -> tuple:
        """Ask the LLM which date is the patient's birth date.

        Sends a short, focused prompt with the document excerpt and the list of
        detected dates.  Returns (parsed_date, entity) or (None, None).
        """
        date_entities = [e for e in entities if e.category == "date"]
        if not date_entities:
            return None, None

        date_list = ", ".join(e.original for e in date_entities)
        excerpt = document_text[:2000]

        if self.language == Language.TR:
            prompt = (
                "Aşağıdaki tıbbi belge metninde hastanın doğum tarihi hangisidir?\n"
                "Sadece tarih metnini yaz, doğum tarihi yoksa 'YOK' yaz.\n\n"
                f"Tarihler: {date_list}\n\n"
                f"Belge:\n{excerpt}"
            )
        else:
            prompt = (
                "Given this medical document excerpt, which of the following dates "
                "is the patient's date of birth?\n"
                "Respond with ONLY the date text, or 'NONE' if no birth date is found.\n\n"
                f"Dates: {date_list}\n\n"
                f"Document:\n{excerpt}"
            )

        try:
            response = await self._chat_freeform([
                {"role": "user", "content": prompt},
            ])
            answer = response.strip().strip("'\"").strip()
            log.debug("LLM birth-date response: %r", answer)

            # Check for explicit "no birth date" answers
            if answer.upper() in ("NONE", "YOK", "N/A", ""):
                return None, None

            # Match the answer to one of our date entities (fuzzy)
            answer_lower = answer.lower().strip(".")
            for e in date_entities:
                if e.original.lower() in answer_lower or answer_lower in e.original.lower():
                    parsed = self._parse_date(e.original)
                    if parsed:
                        log.debug("Birth date identified by LLM: %s", e.original)
                        return parsed, e

            # Try parsing the LLM answer directly and match to closest entity
            parsed_answer = self._parse_date(answer)
            if parsed_answer:
                for e in date_entities:
                    parsed_e = self._parse_date(e.original)
                    if parsed_e and parsed_e == parsed_answer:
                        log.debug("Birth date matched by parsed value: %s", e.original)
                        return parsed_e, e

        except Exception as exc:
            log.warning("LLM birth-date identification failed: %s", exc)

        return None, None

    def _apply_age_conversion(
        self,
        entities: list,
        document_text: str = "",
        birth_date_text: str | None = None,
    ) -> tuple[list, str | None]:
        """Convert date entities to age-relative format when a birth date is found.

        - Birth date stays fully redacted ([TARIH_1] / [DATE_1])
        - Other dates become "X.Y yaşında" (TR) or "at age X.Y yrs" (EN), always decimal

        If *birth_date_text* is provided (the original text of the date entity
        selected by the user), it is used directly — skipping all heuristic
        strategies.  Otherwise falls back to auto-detection strategies:
        0.   Regex scan of entire document text (most reliable automatic method)
        1.   Entity subcategory (LLM classified it as date_of_birth)
        2.   Document context (text near the date mentions "doğum tarihi" etc.)
        3.   Earliest date heuristic (use earliest parseable date as birth date
             when 2+ dates exist — no gap requirement)

        Returns (entities, birth_date_text) where birth_date_text is the accepted
        birth date's original string, or None if no birth date was found.
        """
        from redakt.constants import Language

        birth_date = None
        birth_entity = None

        # ── User-selected birth date (most reliable) ─────────────────
        if birth_date_text:
            for e in entities:
                if e.category == "date" and e.original == birth_date_text:
                    parsed = self._parse_date(e.original)
                    if parsed:
                        birth_date = parsed
                        birth_entity = e
                        log.debug("Birth date selected by user: %s", e.original)
                        break

        # ── Strategy 0: Regex scan of entire document text ────────────
        if not birth_date:
            regex_birth = self._find_birth_date_by_regex_scan(document_text)
            if regex_birth:
                for e in entities:
                    if e.category != "date":
                        continue
                    parsed = self._parse_date(e.original)
                    if parsed and parsed == regex_birth:
                        birth_date = regex_birth
                        birth_entity = e
                        break

        # ── Strategy 0b: Fuzzy scan for unexpected conventions ────────
        if not birth_date:
            fuzzy_birth = self._find_birth_date_by_fuzzy_scan(document_text)
            if fuzzy_birth:
                for e in entities:
                    if e.category != "date":
                        continue
                    parsed = self._parse_date(e.original)
                    if parsed and parsed == fuzzy_birth:
                        birth_date = fuzzy_birth
                        birth_entity = e
                        log.debug(
                            "Birth date matched from fuzzy scan: %s",
                            e.original,
                        )
                        break

        # ── Strategy 1: Find by subcategory ──────────────────────────
        if not birth_date:
            for e in entities:
                if e.subcategory in self._BIRTH_DATE_SUBCATS:
                    parsed = self._parse_date(e.original)
                    if parsed:
                        birth_date = parsed
                        birth_entity = e
                        log.debug("Birth date found by subcategory (%s): %s", e.subcategory, e.original)
                        break

        # ── Strategy 2: Find by document context ─────────────────────
        if not birth_date:
            birth_date, birth_entity = self._find_birth_date_by_context(
                entities, document_text
            )

        # ── Strategy 3: Always use earliest date ──────────────────────
        if not birth_date:
            date_candidates = []
            for e in entities:
                if e.category != "date":
                    continue
                parsed = self._parse_date(e.original)
                if parsed:
                    date_candidates.append((parsed, e))

            if len(date_candidates) >= 2:
                date_candidates.sort(key=lambda x: x[0])
                birth_date, birth_entity = date_candidates[0]
                log.debug(
                    "Birth date found by earliest-date heuristic: %s",
                    birth_entity.original,
                )

        if not birth_date:
            log.debug("No birth date could be determined — skipping age conversion")
            return entities, None

        # ── Convert other dates to age-relative placeholders ─────────
        for e in entities:
            if e.category != "date" or e is birth_entity:
                continue
            parsed = self._parse_date(e.original)
            if not parsed:
                continue
            years, months = self._calc_age_diff(birth_date, parsed)
            if self.language == Language.TR:
                if years == 0 and months == 0:
                    e.placeholder = "doğduğu gün"
                else:
                    frac = round(years + months / 12, 1)
                    e.placeholder = f"{frac} yaşında"
            else:
                frac = round(years + months / 12, 1)
                e.placeholder = f"at age {frac} yrs"

        return entities, birth_entity.original if birth_entity else None

    async def detect_pii_chunked(self, text: str) -> PIIResponse:
        chunks = self.chunk_text(text)
        all_entities: dict[str, PIIEntity] = {}

        for i, chunk in enumerate(chunks):
            self.progress.emit(i + 1, f"Processing chunk {i + 1}/{len(chunks)}")
            response = await self.detect_pii_from_text(chunk)
            for entity in response.entities:
                if entity.original not in all_entities:
                    all_entities[entity.original] = entity

        entities = self._renumber_placeholders(list(all_entities.values()))
        return PIIResponse(entities=entities, summary=f"Processed {len(chunks)} chunk(s)")

    @staticmethod
    def apply_replacements(text: str, entities: list[PIIEntity]) -> str:
        sorted_entities = sorted(entities, key=lambda e: len(e.original), reverse=True)
        result = text
        for entity in sorted_entities:
            result = result.replace(entity.original, entity.placeholder)
        return result

    # ── Document Q&A (chat) ────────────────────────────────────────

    async def chat_with_document(
        self,
        text: str,
        question: str,
        history: list[dict] | None = None,
    ) -> str:
        """Answer a question about the document (no PII in output)."""
        if self.language == Language.TR:
            sys_prompt = CHAT_SYSTEM_TR
            usr_prompt = CHAT_USER_TR.format(text=text[:12000], question=question)
        else:
            sys_prompt = CHAT_SYSTEM_EN
            usr_prompt = CHAT_USER_EN.format(text=text[:12000], question=question)

        messages: list[dict] = [{"role": "system", "content": sys_prompt}]

        # Include conversation history for multi-turn chat
        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": usr_prompt})

        return await self._chat_freeform(messages)
