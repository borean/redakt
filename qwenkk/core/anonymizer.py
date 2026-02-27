import asyncio
import base64
import json as _json
import logging
import re
from collections import defaultdict

import httpx
from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

from qwenkk.constants import (
    Backend,
    DEFAULT_MODEL,
    LLAMACPP_HOST,
    OLLAMA_HOST,
    VISION_MODEL,
    Language,
)
from qwenkk.core.entities import PIIEntity, PIIResponse
from qwenkk.core.prompts import (
    CHAT_SYSTEM_EN,
    CHAT_SYSTEM_TR,
    CHAT_USER_EN,
    CHAT_USER_TR,
    DETAILED_SUMMARIZE_SYSTEM_EN,
    DETAILED_SUMMARIZE_SYSTEM_TR,
    DETAILED_SUMMARIZE_USER_EN,
    DETAILED_SUMMARIZE_USER_TR,
    SUMMARIZE_SYSTEM_EN,
    SUMMARIZE_SYSTEM_TR,
    SUMMARIZE_USER_EN,
    SUMMARIZE_USER_TR,
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
    "location": "address",
    "city": "address",
    "district": "address",
    "addr": "address",
    "email_address": "email",
}

# Flattened JSON schema for ollama (no $ref — avoids constrained decoding bugs)
_OLLAMA_SCHEMA = PIIResponse.ollama_json_schema()


class Anonymizer(QObject):
    """Core anonymization engine.

    Supports two backends:
    - **ollama**: Uses ollama's ``/api/chat`` with structured ``format`` output.
    - **llamacpp**: Uses llama.cpp server's OpenAI-compatible ``/v1/chat/completions``
      with ``response_format: {type: "json_object"}``.
    """

    progress = Signal(int, str)
    pii_detected = Signal(list)
    anonymization_complete = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        language: Language = Language.TR,
        backend: Backend = Backend.OLLAMA,
    ):
        super().__init__()
        self.model = model
        self.vision_model = VISION_MODEL
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

    # ── Backend: ollama ───────────────────────────────────────────────

    async def _chat_ollama(self, messages: list[dict], model: str | None = None) -> str:
        """Send a chat request to ollama and return the content string."""
        payload = {
            "model": model or self.model,
            "messages": messages,
            "format": _OLLAMA_SCHEMA,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.1, "num_ctx": 8192},
        }
        async with httpx.AsyncClient(timeout=None) as client:
            resp = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
            resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")
        return data.get("message", {}).get("content", "")

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

    async def _chat_freeform_ollama(self, messages: list[dict], model: str | None = None) -> str:
        """Send a free-form chat to ollama (no JSON format constraint)."""
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.3, "num_ctx": 8192},
        }
        async with httpx.AsyncClient(timeout=None) as client:
            resp = await client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
            resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")
        return data.get("message", {}).get("content", "")

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
        """Route free-form (non-JSON) chat to the active backend."""
        if self.backend == Backend.LLAMACPP:
            return await self._chat_freeform_llamacpp(messages)
        return await self._chat_freeform_ollama(messages, model=model)

    # ── Unified chat dispatch ─────────────────────────────────────────

    async def _chat(self, messages: list[dict], model: str | None = None) -> str:
        """Route to the active backend."""
        if self.backend == Backend.LLAMACPP:
            return await self._chat_llamacpp(messages)
        return await self._chat_ollama(messages, model=model)

    # ── Response normalization ─────────────────────────────────────────

    @classmethod
    def _normalize_llm_response(cls, raw_json: str) -> str:
        """Normalize LLM JSON to our schema regardless of field names used.

        Different models return different field conventions:
        - ollama (constrained):  {"original", "category", "placeholder"}
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
        return self._normalize_entities(result)

    async def detect_pii_from_image(self, image_path: str) -> PIIResponse:
        sys_prompt, vis_prompt = self._get_vision_prompt()

        if self.backend == Backend.LLAMACPP:
            # llama.cpp doesn't support vision in this setup;
            # fall back to ollama's vision model
            from ollama import AsyncClient

            client = AsyncClient()
            response = await client.chat(
                model=self.vision_model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": vis_prompt, "images": [image_path]},
                ],
                format=_OLLAMA_SCHEMA,
                options={"temperature": 0.1, "num_ctx": 8192},
                think=False,
            )
            content = response.message.content
        else:
            # ollama: base64-encode the image
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            content = await self._chat_ollama(
                [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": vis_prompt, "images": [img_b64]},
                ],
                model=self.vision_model,
            )

        content = self._normalize_llm_response(content)
        try:
            result = PIIResponse.model_validate_json(content)
        except Exception as e:
            log.warning("Failed to validate image PII response: %s", e)
            result = PIIResponse(entities=[], summary=f"Parse error: {e}")
        return self._normalize_entities(result)

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

    @staticmethod
    def _parse_date(text: str):
        """Parse various date formats common in Turkish medical documents.

        Returns a datetime.date or None.
        """
        from datetime import date as date_type
        import re as _re

        text = text.strip().replace("\u00a0", " ")  # nbsp

        # DD.MM.YYYY or DD/MM/YYYY or DD-MM-YYYY
        m = _re.match(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})", text)
        if m:
            try:
                return date_type(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass

        # YYYY-MM-DD (ISO)
        m = _re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        if m:
            try:
                return date_type(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        # DD Month YYYY (Turkish or English)
        m = _re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", text)
        if m:
            day, month_str, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
            month = Anonymizer._TURKISH_MONTHS.get(month_str)
            if month:
                try:
                    return date_type(year, month, day)
                except ValueError:
                    pass
            # Try English months
            eng_months = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12,
            }
            month = eng_months.get(month_str)
            if month:
                try:
                    return date_type(year, month, day)
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

    def _apply_age_conversion(self, entities: list) -> list:
        """Convert date entities to age-relative format when a birth date is found.

        - Birth date stays fully redacted ([TARIH_1] / [DATE_1])
        - Other dates become "X yaş Y ay" (TR) or "at age X.Y yrs" (EN)
        """
        from qwenkk.constants import Language

        # Find the first parseable birth date entity
        birth_date = None
        birth_entity = None
        for e in entities:
            if e.subcategory in self._BIRTH_DATE_SUBCATS:
                parsed = self._parse_date(e.original)
                if parsed:
                    birth_date = parsed
                    birth_entity = e
                    break

        if not birth_date:
            return entities  # no birth date found

        for e in entities:
            if e.category != "date" or e is birth_entity:
                continue
            parsed = self._parse_date(e.original)
            if not parsed:
                continue
            years, months = self._calc_age_diff(birth_date, parsed)
            if self.language == Language.TR:
                if months > 0:
                    e.placeholder = f"{years} yaş {months} ay"
                else:
                    e.placeholder = f"{years} yaş"
            else:
                if months > 0:
                    frac = round(years + months / 12, 1)
                    e.placeholder = f"at age {frac} yrs"
                else:
                    e.placeholder = f"at age {years} yrs"

        return entities

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

    # ── Document summarization ─────────────────────────────────────

    async def summarize_document(self, text: str) -> str:
        """Generate a concise summary of the document (no PII in output)."""
        if self.language == Language.TR:
            sys_prompt = SUMMARIZE_SYSTEM_TR
            usr_prompt = SUMMARIZE_USER_TR.format(text=text[:12000])
        else:
            sys_prompt = SUMMARIZE_SYSTEM_EN
            usr_prompt = SUMMARIZE_USER_EN.format(text=text[:12000])

        return await self._chat_freeform([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": usr_prompt},
        ])

    async def summarize_document_detailed(self, text: str) -> str:
        """Generate a detailed clinical summary with lab values, progression, auxology."""
        if self.language == Language.TR:
            sys_prompt = DETAILED_SUMMARIZE_SYSTEM_TR
            usr_prompt = DETAILED_SUMMARIZE_USER_TR.format(text=text[:24000])
        else:
            sys_prompt = DETAILED_SUMMARIZE_SYSTEM_EN
            usr_prompt = DETAILED_SUMMARIZE_USER_EN.format(text=text[:24000])

        return await self._chat_freeform([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": usr_prompt},
        ])

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
