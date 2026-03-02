"""Tests for date parsing, age calculation, and age-based date conversion."""

from datetime import date

import pytest

from redakt.core.anonymizer import Anonymizer, _CATEGORY_ALIASES
from redakt.core.entities import PIIEntity


@pytest.fixture
def anon_tr():
    from redakt.constants import Language
    return Anonymizer(language=Language.TR)


@pytest.fixture
def anon_en():
    from redakt.constants import Language
    return Anonymizer(language=Language.EN)


# ── _parse_date ──────────────────────────────────────────────────────────


class TestParseDate:
    """Verify _parse_date handles all expected formats."""

    @pytest.mark.parametrize("text, expected", [
        ("29.03.2012", date(2012, 3, 29)),
        ("01.01.2020", date(2020, 1, 1)),
        ("1.1.2020", date(2020, 1, 1)),
        ("29/03/2012", date(2012, 3, 29)),
        ("29-03-2012", date(2012, 3, 29)),
        ("29.3.12", date(2012, 3, 29)),
        ("29.3.99", date(1999, 3, 29)),
    ])
    def test_dd_mm_yyyy(self, text, expected):
        assert Anonymizer._parse_date(text) == expected

    @pytest.mark.parametrize("text, expected", [
        ("2012-03-29", date(2012, 3, 29)),
        ("2024-06-15", date(2024, 6, 15)),
    ])
    def test_iso(self, text, expected):
        assert Anonymizer._parse_date(text) == expected

    @pytest.mark.parametrize("text, expected", [
        ("2012/03/29", date(2012, 3, 29)),
    ])
    def test_yyyy_mm_dd_slash(self, text, expected):
        assert Anonymizer._parse_date(text) == expected

    @pytest.mark.parametrize("text, expected", [
        ("29 Mart 2012", date(2012, 3, 29)),
        ("15 şubat 2020", date(2020, 2, 15)),
        ("1 ocak 2000", date(2000, 1, 1)),
        ("29 March 2012", date(2012, 3, 29)),
        ("15 Feb 2020", date(2020, 2, 15)),
    ])
    def test_dd_month_yyyy(self, text, expected):
        assert Anonymizer._parse_date(text) == expected

    @pytest.mark.parametrize("text, expected", [
        ("March 15, 2012", date(2012, 3, 15)),
        ("Jan 1, 2020", date(2020, 1, 1)),
    ])
    def test_month_dd_yyyy(self, text, expected):
        assert Anonymizer._parse_date(text) == expected

    @pytest.mark.parametrize("text, expected", [
        ("Ekim 2019", date(2019, 10, 1)),
        ("Mar 2012", date(2012, 3, 1)),
    ])
    def test_month_yyyy(self, text, expected):
        assert Anonymizer._parse_date(text) == expected

    @pytest.mark.parametrize("text, expected", [
        ("2019 Ekim", date(2019, 10, 1)),
    ])
    def test_yyyy_month(self, text, expected):
        assert Anonymizer._parse_date(text) == expected

    @pytest.mark.parametrize("text, expected", [
        ("03/2012", date(2012, 3, 1)),
        ("03.2012", date(2012, 3, 1)),
    ])
    def test_mm_yyyy(self, text, expected):
        assert Anonymizer._parse_date(text) == expected

    @pytest.mark.parametrize("text, expected", [
        ("2012", date(2012, 1, 1)),
        ("1990", date(1990, 1, 1)),
    ])
    def test_standalone_year(self, text, expected):
        assert Anonymizer._parse_date(text) == expected

    @pytest.mark.parametrize("text, expected", [
        ("D.T: 29.03.2012", date(2012, 3, 29)),
        ("Tarih: 29.03.2012", date(2012, 3, 29)),
        ("29.03.2012 tarihli", date(2012, 3, 29)),
    ])
    def test_fallback_with_extra_text(self, text, expected):
        assert Anonymizer._parse_date(text) == expected

    def test_returns_none_for_garbage(self):
        assert Anonymizer._parse_date("no date here") is None
        assert Anonymizer._parse_date("abc") is None
        assert Anonymizer._parse_date("") is None

    def test_nbsp_handling(self):
        assert Anonymizer._parse_date("29.03.2012\u00a0") == date(2012, 3, 29)


# ── _calc_age_diff ───────────────────────────────────────────────────────


class TestCalcAgeDiff:
    def test_exact_years(self):
        assert Anonymizer._calc_age_diff(date(2012, 1, 1), date(2024, 1, 1)) == (12, 0)

    def test_years_and_months(self):
        assert Anonymizer._calc_age_diff(date(2012, 3, 29), date(2024, 6, 15)) == (12, 2)

    def test_month_before_birthday(self):
        years, months = Anonymizer._calc_age_diff(date(2012, 6, 15), date(2024, 3, 1))
        assert years == 11
        assert months == 8

    def test_same_date(self):
        assert Anonymizer._calc_age_diff(date(2012, 1, 1), date(2012, 1, 1)) == (0, 0)

    def test_event_before_birth_clamps_to_zero(self):
        years, months = Anonymizer._calc_age_diff(date(2024, 1, 1), date(2012, 1, 1))
        assert years == 0
        assert months == 0


# ── Category aliases ─────────────────────────────────────────────────────


class TestCategoryAliases:
    @pytest.mark.parametrize("raw", [
        "date", "birth_date", "date_of_birth", "dob",
        "tarih", "tarihi", "doğum", "dogum",
        "dogum_tarihi", "doğum_tarihi",
        "visit_date", "report_date", "admission_date",
        "discharge_date", "surgery_date", "date/time",
    ])
    def test_date_aliases(self, raw):
        assert Anonymizer._normalize_category(raw) == "date"

    @pytest.mark.parametrize("raw", ["name", "person", "patient", "doctor"])
    def test_name_aliases(self, raw):
        assert Anonymizer._normalize_category(raw) == "name"


# ── _apply_age_conversion ───────────────────────────────────────────────


class TestApplyAgeConversion:
    """Verify the full age-conversion pipeline."""

    def _make_entities(self, *date_texts, subcategories=None):
        entities = []
        for i, dt in enumerate(date_texts):
            sub = subcategories[i] if subcategories else None
            entities.append(PIIEntity(
                original=dt,
                category="date",
                placeholder=f"[TARIH_{i+1}]",
                subcategory=sub,
            ))
        return entities

    def test_subcategory_based(self, anon_tr):
        entities = self._make_entities(
            "29.03.2012", "15.06.2024",
            subcategories=["date_of_birth", "visit_date"],
        )
        anon_tr._apply_age_conversion(entities, "")
        assert entities[0].placeholder == "[TARIH_1]"
        assert not entities[1].placeholder.startswith("[")
        # When months > 0, format is "X yıl Y aylıkken"; when months == 0, "X yaşındayken"
        assert "yıl" in entities[1].placeholder or "yaş" in entities[1].placeholder

    def test_regex_scan(self, anon_tr):
        entities = self._make_entities("29.03.2012", "15.06.2024")
        doc = "Doğum Tarihi: 29.03.2012\nMuayene: 15.06.2024"
        anon_tr._apply_age_conversion(entities, doc)
        assert entities[0].placeholder == "[TARIH_1]"
        assert not entities[1].placeholder.startswith("[")

    def test_context_based_before(self, anon_tr):
        entities = self._make_entities("29.03.2012", "15.06.2024")
        doc = "Hasta bilgisi: doğum tarihi: 29.03.2012, kontrol tarihi: 15.06.2024"
        anon_tr._apply_age_conversion(entities, doc)
        assert entities[0].placeholder == "[TARIH_1]"
        assert not entities[1].placeholder.startswith("[")

    def test_context_based_after(self, anon_tr):
        entities = self._make_entities("29.03.2012", "15.06.2024")
        doc = "29.03.2012 doğumlu hasta, 15.06.2024 kontrole geldi"
        anon_tr._apply_age_conversion(entities, doc)
        assert entities[0].placeholder == "[TARIH_1]"
        assert not entities[1].placeholder.startswith("[")

    def test_earliest_date_heuristic(self, anon_tr):
        entities = self._make_entities("29.03.2012", "15.06.2024")
        anon_tr._apply_age_conversion(entities, "irrelevant text")
        assert entities[0].placeholder == "[TARIH_1]"
        assert not entities[1].placeholder.startswith("[")

    def test_user_selected_birth_date(self, anon_tr):
        entities = self._make_entities("15.06.2024", "29.03.2012")
        anon_tr._apply_age_conversion(
            entities, "", birth_date_text="29.03.2012",
        )
        assert entities[1].placeholder == "[TARIH_2]"
        assert not entities[0].placeholder.startswith("[")

    def test_single_date_no_conversion(self, anon_tr):
        entities = self._make_entities("29.03.2012")
        anon_tr._apply_age_conversion(entities, "")
        assert entities[0].placeholder == "[TARIH_1]"

    def test_three_dates(self, anon_tr):
        entities = self._make_entities("01.01.2010", "15.06.2015", "20.12.2024")
        anon_tr._apply_age_conversion(entities, "")
        assert entities[0].placeholder == "[TARIH_1]"
        converted = [e for e in entities[1:] if not e.placeholder.startswith("[")]
        assert len(converted) == 2

    def test_english_mode(self, anon_en):
        entities = self._make_entities("29.03.2012", "15.06.2024")
        anon_en._apply_age_conversion(entities, "")
        assert entities[0].placeholder == "[TARIH_1]"
        assert "at age" in entities[1].placeholder

    def test_non_date_entities_untouched(self, anon_tr):
        entities = [
            PIIEntity(original="Ali", category="name", placeholder="[AD_1]"),
            PIIEntity(original="29.03.2012", category="date", placeholder="[TARIH_1]"),
            PIIEntity(original="15.06.2024", category="date", placeholder="[TARIH_2]"),
        ]
        anon_tr._apply_age_conversion(entities, "")
        assert entities[0].placeholder == "[AD_1]"

    def test_entities_with_extra_text_in_original(self, anon_tr):
        """LLM sometimes includes prefix/suffix text around the date."""
        entities = self._make_entities("D.T: 29.03.2012", "15.06.2024")
        anon_tr._apply_age_conversion(
            entities, "", birth_date_text="D.T: 29.03.2012",
        )
        assert entities[0].placeholder == "[TARIH_1]"
        assert not entities[1].placeholder.startswith("[")

    def test_mixed_date_formats(self, anon_tr):
        entities = self._make_entities("2012-03-29", "June 15, 2024")
        anon_tr._apply_age_conversion(entities, "")
        assert entities[0].placeholder == "[TARIH_1]"
        assert not entities[1].placeholder.startswith("[")

    def test_regex_strategy_birth_entity_not_none(self, anon_tr):
        """Strategy 0 must always set birth_entity when birth_date is found.

        Bug: regex scan found birth date in document but couldn't match it
        to an entity (slightly different format), leaving birth_entity=None.
        This caused ALL dates to be age-converted, including the birth date.
        """
        entities = self._make_entities("D.T: 15.03.2012", "20.06.2024")
        doc = "Doğum tarihi: 15.03.2012\nMuayene: 20.06.2024"
        anon_tr._apply_age_conversion(entities, doc, birth_date_text=None)
        # Birth date entity must remain as placeholder, NOT age-converted
        assert entities[0].placeholder == "[TARIH_1]"
        assert not entities[1].placeholder.startswith("[")

    def test_many_visit_dates_no_explicit_birth(self, anon_tr):
        """Real-world scenario: thyroid lab results with many visit dates.

        When no birth date label exists, earliest date heuristic should
        convert the other dates to age-relative format.
        """
        entities = self._make_entities(
            "10.05.2010", "15.06.2022", "20.12.2023", "05.03.2024",
        )
        doc = (
            "10.05.2010 14:07 TSH 0.34 uU/ml\n"
            "15.06.2022 14:04 TSH 0.33 uU/ml\n"
            "20.12.2023 09:01 TSH 0.42 uU/ml\n"
            "05.03.2024 14:34 TSH 0.37 uU/ml"
        )
        anon_tr._apply_age_conversion(entities, doc)
        # Earliest date is birth date — stays as placeholder
        assert entities[0].placeholder == "[TARIH_1]"
        # All others must be age-converted
        for e in entities[1:]:
            assert not e.placeholder.startswith("["), (
                f"Entity '{e.original}' was not age-converted: {e.placeholder}"
            )

    def test_birth_date_not_self_converted(self, anon_tr):
        """Birth date must never get an age-conversion placeholder.

        Even when strategies fail to set birth_entity, the birth date
        itself must remain redacted with its original placeholder.
        """
        entities = self._make_entities("15.03.2012", "20.06.2024")
        doc = "Doğum Tarihi: 15.03.2012\nKontrol: 20.06.2024"
        anon_tr._apply_age_conversion(entities, doc)
        # Birth date stays as [TARIH_1] — must NOT become "doğduğu gün" or age text
        assert entities[0].placeholder == "[TARIH_1]"
        # Visit date gets converted
        assert not entities[1].placeholder.startswith("[")

    def test_duplicate_date_entities(self, anon_tr):
        """Multiple entities with the same date text should all be handled."""
        entities = self._make_entities(
            "01.01.2010", "15.06.2024", "15.06.2024",
        )
        anon_tr._apply_age_conversion(entities, "")
        assert entities[0].placeholder == "[TARIH_1]"
        # Both visit date entities should be converted
        assert not entities[1].placeholder.startswith("[")
        assert not entities[2].placeholder.startswith("[")


# ── Fuzzy span matching ──────────────────────────────────────────────────


class TestFuzzySpanMatching:
    """Verify find_entity_spans handles LLM output variations."""

    def test_exact_match(self):
        from redakt.core.redactor import find_entity_spans
        text = "Patient: Ali Veli, DOB: 29.03.2012"
        entities = [
            PIIEntity(original="Ali Veli", category="name", placeholder="[AD_1]"),
            PIIEntity(original="29.03.2012", category="date", placeholder="[TARIH_1]"),
        ]
        spans = find_entity_spans(text, entities)
        assert len(spans) == 2
        assert text[spans[0].start:spans[0].end] == "Ali Veli"
        assert text[spans[1].start:spans[1].end] == "29.03.2012"

    def test_nbsp_variation(self):
        """Entity with NBSP should still match normal text."""
        from redakt.core.redactor import find_entity_spans
        text = "Date: 29.03.2012 result"
        entities = [
            PIIEntity(original="29.03.2012\u00a0", category="date", placeholder="[TARIH_1]"),
        ]
        spans = find_entity_spans(text, entities)
        assert len(spans) == 1

    def test_extra_whitespace(self):
        """Entity with extra spaces should match collapsed text."""
        from redakt.core.redactor import find_entity_spans
        text = "Patient Ali Veli came in"
        entities = [
            PIIEntity(original="Ali  Veli", category="name", placeholder="[AD_1]"),
        ]
        spans = find_entity_spans(text, entities)
        assert len(spans) == 1

    def test_no_false_positives(self):
        """Short or unrelated entities must NOT fuzzy-match random text."""
        from redakt.core.redactor import find_entity_spans
        text = "TSH 0.34 uU/ml L(0.51 - 4.3)"
        entities = [
            PIIEntity(original="XYZ Hospital", category="institution", placeholder="[KURUM_1]"),
        ]
        spans = find_entity_spans(text, entities)
        assert len(spans) == 0


# ── Redaction rendering with age mode ────────────────────────────────────


class TestRedactionRendering:
    def test_plain_text_age_mode(self):
        from redakt.core.redactor import TextSpan, render_redacted_plain

        text = "Born 29.03.2012, visit 15.06.2024"
        entities = [
            PIIEntity(original="29.03.2012", category="date", placeholder="[TARIH_1]"),
            PIIEntity(original="15.06.2024", category="date", placeholder="12 yaş 2 ay"),
        ]
        spans = [
            TextSpan(start=5, end=15, entity=entities[0]),
            TextSpan(start=23, end=33, entity=entities[1]),
        ]

        result_off = render_redacted_plain(text, spans, age_mode=False)
        assert "\u2588" * 10 in result_off
        assert "12 yaş 2 ay" not in result_off

        result_on = render_redacted_plain(text, spans, age_mode=True)
        assert "12 yaş 2 ay" in result_on
        assert result_on.count("\u2588") == 10  # only birth date blocked

    def test_html_age_mode(self):
        from redakt.core.redactor import TextSpan, render_redacted_html

        text = "Born 29.03.2012, visit 15.06.2024"
        entities = [
            PIIEntity(original="29.03.2012", category="date", placeholder="[TARIH_1]"),
            PIIEntity(original="15.06.2024", category="date", placeholder="12 yaş 2 ay"),
        ]
        spans = [
            TextSpan(start=5, end=15, entity=entities[0]),
            TextSpan(start=23, end=33, entity=entities[1]),
        ]

        result = render_redacted_html(text, spans, age_mode=True)
        assert "12 ya" in result  # "yaş" may be HTML-escaped
        assert "█" in result  # birth date still blocked
