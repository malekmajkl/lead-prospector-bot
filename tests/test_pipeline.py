from __future__ import annotations

import pytest

from core.pipeline import score_lead, draft_email


class TestScoreLead:
    def test_high_priority_mayor_large_city(self):
        lead = {
            "role": "starosta",
            "municipality": "zlín",
            "email": "jan.novak@zlin.eu",
            "phone": "+420 577 123 456",
            "contact_name": "Jan Novák",
            "source_url": "https://zlin.eu/kontakty",
        }
        score, tier = score_lead(lead)
        assert score >= 75
        assert "High Priority" in tier

    def test_low_priority_no_email_no_phone(self):
        lead = {
            "role": "referent",
            "municipality": "malá ves",
            "email": None,
            "phone": None,
            "contact_name": "X",
            "source_url": "",
        }
        score, tier = score_lead(lead)
        assert score < 50

    def test_generic_email_penalised(self):
        lead_generic = {
            "role": "starosta",
            "municipality": "zlín",
            "email": "info@zlin.eu",
            "phone": None,
            "contact_name": "Jan Novák",
            "source_url": "https://zlin.eu",
        }
        lead_personal = {
            "role": "starosta",
            "municipality": "zlín",
            "email": "jan.novak@zlin.eu",
            "phone": None,
            "contact_name": "Jan Novák",
            "source_url": "https://zlin.eu",
        }
        score_g, _ = score_lead(lead_generic)
        score_p, _ = score_lead(lead_personal)
        assert score_p > score_g

    def test_medium_city_scores_between_large_and_small(self):
        large = {"role": "starosta", "municipality": "kroměříž", "email": "a@b.cz",
                 "phone": None, "contact_name": "A B", "source_url": "https://x.cz"}
        medium = {"role": "starosta", "municipality": "luhačovice", "email": "a@b.cz",
                  "phone": None, "contact_name": "A B", "source_url": "https://x.cz"}
        small = {"role": "starosta", "municipality": "neznámá obec", "email": "a@b.cz",
                 "phone": None, "contact_name": "A B", "source_url": "https://x.cz"}
        s_large, _ = score_lead(large)
        s_medium, _ = score_lead(medium)
        s_small, _ = score_lead(small)
        assert s_large > s_medium > s_small

    def test_score_is_integer(self):
        lead = {"role": "tajemník", "municipality": "brno", "email": "t@brno.cz",
                "phone": "123", "contact_name": "A B", "source_url": "https://brno.cz"}
        score, _ = score_lead(lead)
        assert isinstance(score, int)

    def test_tier_labels_exhaustive(self):
        tiers = set()
        for role, muni, email in [
            ("starosta", "brno", "jan@brno.cz"),
            ("starosta", "luhačovice", "jan@luha.cz"),
            ("referent", "malá ves", "info@malaves.cz"),
            ("referent", "neznámá", None),
        ]:
            _, tier = score_lead({"role": role, "municipality": muni, "email": email,
                                   "phone": None, "contact_name": "A B", "source_url": ""})
            tiers.add(tier)
        assert len(tiers) >= 2


class TestDraftEmail:
    def test_returns_subject_and_body(self):
        lead = {"contact_name": "Jan Novák", "municipality": "Zlín", "role": "starosta"}
        subject, body = draft_email(lead)
        assert "Zlín" in subject
        assert "SolarObec" in subject
        assert "Novák" in body

    def test_female_salutation(self):
        lead = {"contact_name": "Jana Nováková", "municipality": "Brno", "role": "starostka"}
        _, body = draft_email(lead)
        assert "Vážená paní" in body

    def test_male_salutation(self):
        lead = {"contact_name": "Petr Kolář", "municipality": "Olomouc", "role": "ředitel"}
        _, body = draft_email(lead)
        assert "Vážený pane" in body

    def test_neutral_salutation_unknown_role(self):
        lead = {"contact_name": "Alex Novák", "municipality": "Brno", "role": "konzultant"}
        _, body = draft_email(lead)
        assert "Vážená paní / Vážený pane" in body

    def test_empty_name_does_not_crash(self):
        lead = {"contact_name": "", "municipality": "Brno", "role": "starosta"}
        subject, body = draft_email(lead)
        assert isinstance(subject, str)
        assert isinstance(body, str)
