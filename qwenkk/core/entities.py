from pydantic import BaseModel, Field


class PIIEntity(BaseModel):
    """A single detected PII entity."""

    original: str = Field(description="The exact text as it appears in the document")
    category: str = Field(
        description="PII category: name, date, id, address, phone, email, institution, age"
    )
    placeholder: str = Field(description="The replacement placeholder, e.g. [AD_1], [TARIH_1]")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    subcategory: str | None = Field(
        default=None,
        description="Semantic sub-type from LLM, e.g. 'date_of_birth', 'visit_date'"
    )


class PIIResponse(BaseModel):
    """Structured response from the LLM anonymization pass."""

    entities: list[PIIEntity] = Field(default_factory=list)
    summary: str = Field(default="", description="Brief summary of what was found")

    @staticmethod
    def ollama_json_schema() -> dict:
        """Return a flattened JSON schema without $ref/$defs.

        Ollama's constrained decoding can fail with Pydantic's default
        ``model_json_schema()`` because of ``$ref`` references.  This
        method inlines the ``PIIEntity`` definition directly so ollama
        can parse it correctly.
        """
        return {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "original": {
                                "type": "string",
                                "description": "Exact text from the document",
                            },
                            "category": {
                                "type": "string",
                                "description": (
                                    "PII category: name, date, id, address, "
                                    "phone, email, institution, age"
                                ),
                            },
                            "placeholder": {
                                "type": "string",
                                "description": "Replacement placeholder, e.g. [AD_1]",
                            },
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                            "subcategory": {
                                "type": "string",
                                "description": "Semantic sub-type, e.g. 'date_of_birth', 'visit_date', 'report_date'",
                            },
                        },
                        "required": ["original", "category", "placeholder"],
                    },
                },
                "summary": {
                    "type": "string",
                    "description": "Brief summary of findings",
                },
            },
            "required": ["entities", "summary"],
        }
