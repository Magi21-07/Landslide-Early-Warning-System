"""
tests/test_risk_engine.py
--------------------------
Unit tests for src/risk/risk_engine.py (DynamicRiskEngine).
YAML loading is mocked via tmp_path fixture to guarantee determinism.
No GEE / network calls occur.

Risk matrix used in all tests (mirrors config/risk_rules.yaml):
    VERY_HIGH:  NORMAL->MODERATE  WATCH->HIGH    WARNING->SEVERE   CRITICAL->SEVERE
    HIGH:       NORMAL->LOW       WATCH->MODERATE WARNING->HIGH     CRITICAL->SEVERE
    MODERATE:   NORMAL->LOW       WATCH->LOW     WARNING->MODERATE  CRITICAL->HIGH
    LOW:        NORMAL->MINIMAL   WATCH->LOW     WARNING->LOW       CRITICAL->MODERATE
    VERY_LOW:   NORMAL->MINIMAL   WATCH->MINIMAL WARNING->LOW       CRITICAL->LOW
"""

import sys
import os
import datetime
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.risk.risk_engine import (
    DynamicRiskEngine,
    DynamicRiskAssessment,
    RiskMatrixLookupError,
    VALID_SUSCEPTIBILITY_CLASSES,
    VALID_TRIGGER_STATES,
    VALID_RISK_LEVELS,
)

# ---------------------------------------------------------------------------
# Shared YAML fixture
# ---------------------------------------------------------------------------

RISK_RULES_YAML = """\
risk_matrix:
  VERY_HIGH:
    NORMAL:   MODERATE
    WATCH:    HIGH
    WARNING:  SEVERE
    CRITICAL: SEVERE
  HIGH:
    NORMAL:   LOW
    WATCH:    MODERATE
    WARNING:  HIGH
    CRITICAL: SEVERE
  MODERATE:
    NORMAL:   LOW
    WATCH:    LOW
    WARNING:  MODERATE
    CRITICAL: HIGH
  LOW:
    NORMAL:   MINIMAL
    WATCH:    LOW
    WARNING:  LOW
    CRITICAL: MODERATE
  VERY_LOW:
    NORMAL:   MINIMAL
    WATCH:    MINIMAL
    WARNING:  LOW
    CRITICAL: LOW
"""

EXPECTED_MATRIX = {
    "VERY_HIGH": {"NORMAL": "MODERATE", "WATCH": "HIGH",    "WARNING": "SEVERE",   "CRITICAL": "SEVERE"},
    "HIGH":      {"NORMAL": "LOW",      "WATCH": "MODERATE","WARNING": "HIGH",     "CRITICAL": "SEVERE"},
    "MODERATE":  {"NORMAL": "LOW",      "WATCH": "LOW",     "WARNING": "MODERATE", "CRITICAL": "HIGH"},
    "LOW":       {"NORMAL": "MINIMAL",  "WATCH": "LOW",     "WARNING": "LOW",      "CRITICAL": "MODERATE"},
    "VERY_LOW":  {"NORMAL": "MINIMAL",  "WATCH": "MINIMAL", "WARNING": "LOW",      "CRITICAL": "LOW"},
}


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    """Create a DynamicRiskEngine backed by the test YAML (no disk I/O to prod)."""
    tmp = tmp_path_factory.mktemp("config")
    cfg = tmp / "risk_rules.yaml"
    cfg.write_text(RISK_RULES_YAML, encoding='utf-8')
    return DynamicRiskEngine(config_path=str(cfg))


def _assess(engine, sus_class, sus_prob, trigger_state, trigger_score=0, reasons=None):
    """Shortcut wrapper for engine.assess() with sensible defaults."""
    return engine.assess(
        latitude=27.5,
        longitude=85.5,
        susceptibility_probability=sus_prob,
        susceptibility_class=sus_class,
        rainfall_trigger_state=trigger_state,
        rainfall_trigger_score=trigger_score,
        rainfall_reasons=reasons or ["Rainfall within safe limits."],
    )


# ---------------------------------------------------------------------------
# 1. Full matrix sweep — every combination
# ---------------------------------------------------------------------------

class TestFullMatrix:

    def test_all_matrix_entries_match_expected(self, engine):
        """Every susceptibility x trigger combination must return the expected level."""
        for sus_class, row in EXPECTED_MATRIX.items():
            for trigger_state, expected_level in row.items():
                result = _assess(engine, sus_class, 0.5, trigger_state)
                assert result.final_risk_level == expected_level, (
                    f"[{sus_class}][{trigger_state}]: "
                    f"expected {expected_level}, got {result.final_risk_level}"
                )


# ---------------------------------------------------------------------------
# 2. Extreme cases
# ---------------------------------------------------------------------------

class TestExtremeCases:

    def test_very_high_susceptibility_critical_rainfall_is_severe(self, engine):
        result = _assess(engine, "VERY_HIGH", 0.95, "CRITICAL", 3)
        assert result.final_risk_level == "SEVERE"

    def test_very_high_susceptibility_normal_rainfall_is_moderate(self, engine):
        result = _assess(engine, "VERY_HIGH", 0.90, "NORMAL", 0)
        assert result.final_risk_level == "MODERATE"

    def test_high_susceptibility_critical_rainfall_is_severe(self, engine):
        result = _assess(engine, "HIGH", 0.75, "CRITICAL", 3)
        assert result.final_risk_level == "SEVERE"

    def test_very_low_susceptibility_critical_rainfall_is_low(self, engine):
        result = _assess(engine, "VERY_LOW", 0.05, "CRITICAL", 3)
        assert result.final_risk_level == "LOW"


# ---------------------------------------------------------------------------
# 3. Safe cases
# ---------------------------------------------------------------------------

class TestSafeCases:

    def test_very_low_susceptibility_normal_is_minimal(self, engine):
        result = _assess(engine, "VERY_LOW", 0.05, "NORMAL", 0)
        assert result.final_risk_level == "MINIMAL"

    def test_low_susceptibility_normal_is_minimal(self, engine):
        result = _assess(engine, "LOW", 0.15, "NORMAL", 0)
        assert result.final_risk_level == "MINIMAL"

    def test_very_low_susceptibility_watch_is_minimal(self, engine):
        result = _assess(engine, "VERY_LOW", 0.08, "WATCH", 1)
        assert result.final_risk_level == "MINIMAL"


# ---------------------------------------------------------------------------
# 4. Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:

    def test_probability_above_1_raises(self, engine):
        with pytest.raises(ValueError, match="susceptibility_probability"):
            _assess(engine, "HIGH", 1.5, "NORMAL")

    def test_probability_below_0_raises(self, engine):
        with pytest.raises(ValueError, match="susceptibility_probability"):
            _assess(engine, "HIGH", -0.1, "NORMAL")

    def test_boundary_probability_0_and_1_accepted(self, engine):
        _assess(engine, "VERY_LOW", 0.0, "NORMAL")
        _assess(engine, "VERY_HIGH", 1.0, "CRITICAL")

    def test_invalid_susceptibility_class_raises(self, engine):
        with pytest.raises(ValueError, match="susceptibility_class"):
            _assess(engine, "SUPER_HIGH", 0.9, "NORMAL")

    def test_invalid_trigger_state_raises(self, engine):
        with pytest.raises(ValueError, match="rainfall_trigger_state"):
            _assess(engine, "HIGH", 0.7, "EXTREME")

    def test_invalid_trigger_score_raises(self, engine):
        with pytest.raises(ValueError, match="rainfall_trigger_score"):
            engine.assess(
                latitude=27.5, longitude=85.5,
                susceptibility_probability=0.7,
                susceptibility_class="HIGH",
                rainfall_trigger_state="NORMAL",
                rainfall_trigger_score=5,   # invalid
                rainfall_reasons=[],
            )


# ---------------------------------------------------------------------------
# 5. Missing / invalid matrix key handling
# ---------------------------------------------------------------------------

class TestMatrixKeyHandling:

    def test_missing_susceptibility_key_raises_lookup_error(self, tmp_path):
        """YAML missing a susceptibility class -> RiskMatrixLookupError."""
        incomplete_yaml = (
            "risk_matrix:\n"
            "  HIGH:\n"
            "    NORMAL: LOW\n"
            "    WATCH: MODERATE\n"
            "    WARNING: HIGH\n"
            "    CRITICAL: SEVERE\n"
        )
        cfg = tmp_path / "partial.yaml"
        cfg.write_text(incomplete_yaml, encoding='utf-8')
        eng = DynamicRiskEngine(config_path=str(cfg))
        with pytest.raises(RiskMatrixLookupError, match="VERY_HIGH"):
            eng.assess(
                latitude=27.5, longitude=85.5,
                susceptibility_probability=0.9,
                susceptibility_class="VERY_HIGH",
                rainfall_trigger_state="NORMAL",
                rainfall_trigger_score=0,
                rainfall_reasons=[],
            )

    def test_missing_trigger_state_key_raises_lookup_error(self, tmp_path):
        """YAML missing a trigger state -> RiskMatrixLookupError."""
        incomplete_yaml = (
            "risk_matrix:\n"
            "  HIGH:\n"
            "    NORMAL: LOW\n"
            "    WATCH: MODERATE\n"
            # WARNING and CRITICAL intentionally omitted
        )
        cfg = tmp_path / "missing_trigger.yaml"
        cfg.write_text(incomplete_yaml, encoding='utf-8')
        eng = DynamicRiskEngine(config_path=str(cfg))
        with pytest.raises(RiskMatrixLookupError, match="WARNING"):
            eng.assess(
                latitude=27.5, longitude=85.5,
                susceptibility_probability=0.7,
                susceptibility_class="HIGH",
                rainfall_trigger_state="WARNING",
                rainfall_trigger_score=2,
                rainfall_reasons=[],
            )


# ---------------------------------------------------------------------------
# 6. Output schema validation
# ---------------------------------------------------------------------------

class TestOutputSchema:

    def test_returns_dynamic_risk_assessment_instance(self, engine):
        result = _assess(engine, "HIGH", 0.7, "WATCH", 1)
        assert isinstance(result, DynamicRiskAssessment)

    def test_to_dict_contains_all_required_keys(self, engine):
        result = _assess(engine, "MODERATE", 0.55, "NORMAL")
        d = result.to_dict()
        required = [
            'latitude', 'longitude', 'susceptibility_probability',
            'susceptibility_class', 'rainfall_trigger_state',
            'rainfall_trigger_score', 'final_risk_level', 'reasons', 'timestamp'
        ]
        for key in required:
            assert key in d, f"Missing key: {key}"

    def test_coordinates_preserved_in_output(self, engine):
        result = engine.assess(
            latitude=12.34, longitude=56.78,
            susceptibility_probability=0.5,
            susceptibility_class="MODERATE",
            rainfall_trigger_state="NORMAL",
            rainfall_trigger_score=0,
            rainfall_reasons=[],
        )
        assert result.latitude  == 12.34
        assert result.longitude == 56.78

    def test_probability_rounded_to_4_decimal_places(self, engine):
        result = _assess(engine, "HIGH", 1/3, "NORMAL")
        assert result.susceptibility_probability == round(1/3, 4)

    def test_timestamp_is_valid_iso_utc_string(self, engine):
        result = _assess(engine, "LOW", 0.2, "WATCH", 1)
        # Should parse without error
        dt = datetime.datetime.fromisoformat(result.timestamp)
        assert dt.tzinfo is not None    # must be timezone-aware

    def test_reasons_is_non_empty_list(self, engine):
        result = _assess(engine, "HIGH", 0.7, "WARNING", 2)
        assert isinstance(result.reasons, list)
        assert len(result.reasons) > 0

    def test_reasons_contain_susceptibility_note(self, engine):
        result = _assess(engine, "HIGH", 0.75, "WATCH", 1)
        assert any("HIGH susceptibility" in r for r in result.reasons)

    def test_reasons_contain_risk_level(self, engine):
        result = _assess(engine, "HIGH", 0.75, "WATCH", 1)
        assert any("MODERATE" in r for r in result.reasons)

    def test_rainfall_reasons_merged_into_output_reasons(self, engine):
        rainfall_reason = "7-day cumulative rainfall (120.0 mm) exceeded watch threshold (120.0 mm)"
        result = engine.assess(
            latitude=27.5, longitude=85.5,
            susceptibility_probability=0.7,
            susceptibility_class="HIGH",
            rainfall_trigger_state="WATCH",
            rainfall_trigger_score=1,
            rainfall_reasons=[rainfall_reason],
        )
        assert any("120.0" in r for r in result.reasons)

    def test_final_risk_level_is_valid_level(self, engine):
        for sus_class in VALID_SUSCEPTIBILITY_CLASSES:
            for trigger_state in VALID_TRIGGER_STATES:
                result = _assess(engine, sus_class, 0.5, trigger_state)
                assert result.final_risk_level in VALID_RISK_LEVELS, (
                    f"[{sus_class}][{trigger_state}] returned invalid "
                    f"risk level: {result.final_risk_level}"
                )


# ---------------------------------------------------------------------------
# 7. Config loading
# ---------------------------------------------------------------------------

class TestConfigLoading:

    def test_missing_config_file_raises(self):
        with pytest.raises(FileNotFoundError):
            DynamicRiskEngine(config_path='nonexistent/risk.yaml')

    def test_yaml_without_risk_matrix_key_raises(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("some_other_key:\n  A: B\n", encoding='utf-8')
        with pytest.raises(ValueError, match="risk_matrix"):
            DynamicRiskEngine(config_path=str(bad))

    def test_yaml_with_invalid_risk_level_raises(self, tmp_path):
        bad = tmp_path / "bad_level.yaml"
        bad.write_text(
            "risk_matrix:\n  HIGH:\n    NORMAL: CATASTROPHIC\n",
            encoding='utf-8'
        )
        with pytest.raises(ValueError, match="risk level"):
            DynamicRiskEngine(config_path=str(bad))

    def test_yaml_with_unknown_susceptibility_class_raises(self, tmp_path):
        bad = tmp_path / "bad_class.yaml"
        bad.write_text(
            "risk_matrix:\n  SUPER_HIGH:\n    NORMAL: LOW\n",
            encoding='utf-8'
        )
        with pytest.raises(ValueError, match="susceptibility class"):
            DynamicRiskEngine(config_path=str(bad))

    def test_valid_yaml_produces_correct_matrix(self, tmp_path):
        cfg = tmp_path / "valid.yaml"
        cfg.write_text(RISK_RULES_YAML, encoding='utf-8')
        eng = DynamicRiskEngine(config_path=str(cfg))
        result = eng.assess(
            latitude=27.5, longitude=85.5,
            susceptibility_probability=0.95,
            susceptibility_class="VERY_HIGH",
            rainfall_trigger_state="CRITICAL",
            rainfall_trigger_score=3,
            rainfall_reasons=[],
        )
        assert result.final_risk_level == "SEVERE"
