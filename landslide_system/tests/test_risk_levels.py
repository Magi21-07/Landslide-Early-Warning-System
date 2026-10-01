"""
tests/test_risk_levels.py
--------------------------
Unit tests for src/risk/risk_levels.py (classify_risk, RiskLevel, RiskLevelEnum).
All tests use a deterministic inline YAML written to tmp_path — no production
config is read, no network calls occur.

Canonical boundary layout (from config):
    LOW      [0.00, 0.25)
    MODERATE [0.25, 0.50)
    HIGH     [0.50, 0.75)
    CRITICAL [0.75, 1.00]

Boundary rule: at shared edges the HIGHER tier wins
    (0.25 -> MODERATE, 0.50 -> HIGH, 0.75 -> CRITICAL)
"""

import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.risk.risk_levels import (
    classify_risk,
    RiskLevel,
    RiskLevelEnum,
)

# ---------------------------------------------------------------------------
# Shared test YAML fixture (written to tmp_path to avoid disk reads)
# ---------------------------------------------------------------------------

RISK_DEFS_YAML = """\
risk_levels:
  LOW:
    numeric_code: 1
    machine_name: "RISK_LOW"
    human_description: "Background risk. Normal geological conditions."
    color_hex: "#28a745"
    ui_severity: "SUCCESS"
    min_score: 0.0
    max_score: 0.25

  MODERATE:
    numeric_code: 2
    machine_name: "RISK_MODERATE"
    human_description: "Elevated risk. Soil saturation or slope weakness observed."
    color_hex: "#ffc107"
    ui_severity: "WARNING"
    min_score: 0.25
    max_score: 0.50

  HIGH:
    numeric_code: 3
    machine_name: "RISK_HIGH"
    human_description: "High risk. Heavy rainfall overlay on susceptible terrain."
    color_hex: "#fd7e14"
    ui_severity: "DANGER"
    min_score: 0.50
    max_score: 0.75

  CRITICAL:
    numeric_code: 4
    machine_name: "RISK_CRITICAL"
    human_description: "Critical risk. Severe landslide threat active."
    color_hex: "#dc3545"
    ui_severity: "CRITICAL"
    min_score: 0.75
    max_score: 1.00

string_mappings:
  MINIMAL:  "LOW"
  LOW:      "LOW"
  MODERATE: "MODERATE"
  HIGH:     "HIGH"
  SEVERE:   "CRITICAL"
  CRITICAL: "CRITICAL"
"""


@pytest.fixture(scope="module")
def cfg_path(tmp_path_factory) -> str:
    tmp = tmp_path_factory.mktemp("config")
    p = tmp / "risk_definitions.yaml"
    p.write_text(RISK_DEFS_YAML, encoding='utf-8')
    return str(p)


# Shortcut
def _(val, cfg):
    return classify_risk(val, config_path=cfg)


# ---------------------------------------------------------------------------
# 1. Numeric classification — interior values
# ---------------------------------------------------------------------------

class TestNumericInterior:

    def test_low_interior(self, cfg_path):
        result = _(0.10, cfg_path)
        assert result.level_enum == RiskLevelEnum.LOW

    def test_moderate_interior(self, cfg_path):
        result = _(0.35, cfg_path)
        assert result.level_enum == RiskLevelEnum.MODERATE

    def test_high_interior(self, cfg_path):
        result = _(0.60, cfg_path)
        assert result.level_enum == RiskLevelEnum.HIGH

    def test_critical_interior(self, cfg_path):
        result = _(0.90, cfg_path)
        assert result.level_enum == RiskLevelEnum.CRITICAL

    def test_int_input_treated_as_numeric(self, cfg_path):
        """Integer 0 should classify as LOW, integer 1 as CRITICAL."""
        assert _(0, cfg_path).level_enum == RiskLevelEnum.LOW
        assert _(1, cfg_path).level_enum == RiskLevelEnum.CRITICAL


# ---------------------------------------------------------------------------
# 2. Exact boundary conditions
# ---------------------------------------------------------------------------

class TestBoundaryConditions:

    def test_boundary_0_0_is_low(self, cfg_path):
        result = _(0.0, cfg_path)
        assert result.level_enum == RiskLevelEnum.LOW

    def test_boundary_0_25_is_moderate_not_low(self, cfg_path):
        """Shared boundary 0.25: MODERATE wins over LOW (higher tier)."""
        result = _(0.25, cfg_path)
        assert result.level_enum == RiskLevelEnum.MODERATE

    def test_boundary_0_50_is_high_not_moderate(self, cfg_path):
        """Shared boundary 0.50: HIGH wins over MODERATE."""
        result = _(0.50, cfg_path)
        assert result.level_enum == RiskLevelEnum.HIGH

    def test_boundary_0_75_is_critical_not_high(self, cfg_path):
        """Shared boundary 0.75: CRITICAL wins over HIGH."""
        result = _(0.75, cfg_path)
        assert result.level_enum == RiskLevelEnum.CRITICAL

    def test_boundary_1_0_is_critical(self, cfg_path):
        result = _(1.0, cfg_path)
        assert result.level_enum == RiskLevelEnum.CRITICAL

    def test_just_below_0_25_is_low(self, cfg_path):
        result = _(0.2499, cfg_path)
        assert result.level_enum == RiskLevelEnum.LOW

    def test_just_above_0_75_is_critical(self, cfg_path):
        result = _(0.7501, cfg_path)
        assert result.level_enum == RiskLevelEnum.CRITICAL


# ---------------------------------------------------------------------------
# 3. Invalid float inputs
# ---------------------------------------------------------------------------

class TestInvalidFloatInputs:

    def test_negative_float_raises_value_error(self, cfg_path):
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            _(-0.01, cfg_path)

    def test_above_one_raises_value_error(self, cfg_path):
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            _(1.01, cfg_path)

    def test_large_negative_raises_value_error(self, cfg_path):
        with pytest.raises(ValueError):
            _(-100.0, cfg_path)

    def test_large_positive_raises_value_error(self, cfg_path):
        with pytest.raises(ValueError):
            _(999.0, cfg_path)

    def test_boolean_is_not_treated_as_numeric(self, cfg_path):
        """bool is a subclass of int — must raise TypeError, not classify."""
        with pytest.raises(TypeError):
            classify_risk(True, config_path=cfg_path)


# ---------------------------------------------------------------------------
# 4. String mappings
# ---------------------------------------------------------------------------

class TestStringMappings:

    def test_minimal_maps_to_low(self, cfg_path):
        assert _("MINIMAL", cfg_path).level_enum == RiskLevelEnum.LOW

    def test_low_maps_to_low(self, cfg_path):
        assert _("LOW", cfg_path).level_enum == RiskLevelEnum.LOW

    def test_moderate_maps_to_moderate(self, cfg_path):
        assert _("MODERATE", cfg_path).level_enum == RiskLevelEnum.MODERATE

    def test_high_maps_to_high(self, cfg_path):
        assert _("HIGH", cfg_path).level_enum == RiskLevelEnum.HIGH

    def test_severe_maps_to_critical(self, cfg_path):
        assert _("SEVERE", cfg_path).level_enum == RiskLevelEnum.CRITICAL

    def test_critical_maps_to_critical(self, cfg_path):
        assert _("CRITICAL", cfg_path).level_enum == RiskLevelEnum.CRITICAL

    def test_lowercase_input_normalised(self, cfg_path):
        assert _("minimal", cfg_path).level_enum == RiskLevelEnum.LOW
        assert _("severe",  cfg_path).level_enum == RiskLevelEnum.CRITICAL
        assert _("moderate", cfg_path).level_enum == RiskLevelEnum.MODERATE

    def test_mixed_case_normalised(self, cfg_path):
        assert _("Moderate", cfg_path).level_enum == RiskLevelEnum.MODERATE
        assert _("Critical", cfg_path).level_enum == RiskLevelEnum.CRITICAL

    def test_unknown_string_raises_value_error(self, cfg_path):
        with pytest.raises(ValueError, match="Unknown risk string"):
            _("CATASTROPHIC", cfg_path)

    def test_empty_string_raises_value_error(self, cfg_path):
        with pytest.raises(ValueError, match="Unknown risk string"):
            _("", cfg_path)

    def test_whitespace_stripped_before_lookup(self, cfg_path):
        """Leading/trailing whitespace should be stripped."""
        assert _("  SEVERE  ", cfg_path).level_enum == RiskLevelEnum.CRITICAL


# ---------------------------------------------------------------------------
# 5. Return object — RiskLevel schema validation
# ---------------------------------------------------------------------------

class TestRiskLevelSchema:

    def test_returns_risk_level_instance(self, cfg_path):
        result = _(0.1, cfg_path)
        assert isinstance(result, RiskLevel)

    def test_level_enum_is_risk_level_enum(self, cfg_path):
        result = _(0.6, cfg_path)
        assert isinstance(result.level_enum, RiskLevelEnum)

    def test_numeric_code_is_int(self, cfg_path):
        result = _(0.1, cfg_path)
        assert isinstance(result.numeric_code, int)

    def test_numeric_codes_are_1_through_4(self, cfg_path):
        expected = {
            RiskLevelEnum.LOW:      1,
            RiskLevelEnum.MODERATE: 2,
            RiskLevelEnum.HIGH:     3,
            RiskLevelEnum.CRITICAL: 4,
        }
        for val, (enum_val, code) in zip(
            [0.10, 0.35, 0.60, 0.90],
            expected.items()
        ):
            result = _(val, cfg_path)
            assert result.numeric_code == code, \
                f"{enum_val}: expected code {code}, got {result.numeric_code}"

    def test_machine_name_is_str(self, cfg_path):
        result = _(0.1, cfg_path)
        assert isinstance(result.machine_name, str)

    def test_machine_name_prefixed_risk(self, cfg_path):
        for val in [0.1, 0.35, 0.6, 0.9]:
            result = _(val, cfg_path)
            assert result.machine_name.startswith("RISK_")

    def test_human_description_is_non_empty_str(self, cfg_path):
        for val in [0.1, 0.35, 0.6, 0.9]:
            result = _(val, cfg_path)
            assert isinstance(result.human_description, str)
            assert len(result.human_description) > 0

    def test_color_hex_format(self, cfg_path):
        for val in [0.1, 0.35, 0.6, 0.9]:
            result = _(val, cfg_path)
            assert result.color_hex.startswith("#")
            assert len(result.color_hex) == 7    # #RRGGBB

    def test_ui_severity_is_str(self, cfg_path):
        result = _(0.9, cfg_path)
        assert isinstance(result.ui_severity, str)

    def test_min_max_score_are_float(self, cfg_path):
        result = _(0.35, cfg_path)
        assert isinstance(result.min_score, float)
        assert isinstance(result.max_score, float)

    def test_to_dict_returns_dict_with_required_keys(self, cfg_path):
        result = _(0.60, cfg_path)
        d = result.to_dict()
        for key in ['level_enum', 'numeric_code', 'machine_name',
                    'human_description', 'color_hex', 'ui_severity',
                    'min_score', 'max_score']:
            assert key in d, f"Missing key in to_dict(): {key}"

    def test_to_dict_level_enum_is_string(self, cfg_path):
        """Enum must be serialised as string value in to_dict."""
        result = _(0.60, cfg_path)
        d = result.to_dict()
        assert isinstance(d['level_enum'], str)
        assert d['level_enum'] == "HIGH"

    def test_all_metadata_from_yaml_not_hardcoded(self, tmp_path):
        """Overwrite the YAML with custom values; module must use them."""
        custom_yaml = """\
risk_levels:
  LOW:
    numeric_code: 99
    machine_name: "CUSTOM_LOW"
    human_description: "Custom description."
    color_hex: "#aabbcc"
    ui_severity: "CUSTOM"
    min_score: 0.0
    max_score: 0.25
  MODERATE:
    numeric_code: 100
    machine_name: "CUSTOM_MOD"
    human_description: "Custom moderate."
    color_hex: "#ddeeff"
    ui_severity: "CUSTOM2"
    min_score: 0.25
    max_score: 0.50
  HIGH:
    numeric_code: 101
    machine_name: "CUSTOM_HIGH"
    human_description: "Custom high."
    color_hex: "#112233"
    ui_severity: "CUSTOM3"
    min_score: 0.50
    max_score: 0.75
  CRITICAL:
    numeric_code: 102
    machine_name: "CUSTOM_CRIT"
    human_description: "Custom critical."
    color_hex: "#445566"
    ui_severity: "CUSTOM4"
    min_score: 0.75
    max_score: 1.00
string_mappings:
  MINIMAL: "LOW"
  LOW: "LOW"
  MODERATE: "MODERATE"
  HIGH: "HIGH"
  SEVERE: "CRITICAL"
  CRITICAL: "CRITICAL"
"""
        cfg = tmp_path / "custom.yaml"
        cfg.write_text(custom_yaml, encoding='utf-8')
        result = classify_risk(0.10, config_path=str(cfg))
        assert result.numeric_code      == 99
        assert result.machine_name      == "CUSTOM_LOW"
        assert result.color_hex         == "#aabbcc"
        assert result.human_description == "Custom description."


# ---------------------------------------------------------------------------
# 6. Config loading edge cases
# ---------------------------------------------------------------------------

class TestConfigEdgeCases:

    def test_missing_config_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            classify_risk(0.5, config_path="nonexistent/path.yaml")

    def test_yaml_missing_risk_levels_key_raises(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("other_key:\n  a: 1\n", encoding='utf-8')
        with pytest.raises(ValueError, match="risk_levels"):
            classify_risk(0.5, config_path=str(bad))

    def test_yaml_missing_string_mappings_key_raises(self, tmp_path):
        bad = tmp_path / "no_mappings.yaml"
        bad.write_text("risk_levels:\n  LOW:\n    numeric_code: 1\n", encoding='utf-8')
        with pytest.raises(ValueError, match="string_mappings"):
            classify_risk(0.5, config_path=str(bad))

    def test_path_object_accepted(self, tmp_path):
        """classify_risk should accept pathlib.Path as config_path."""
        cfg = tmp_path / "defs.yaml"
        cfg.write_text(RISK_DEFS_YAML, encoding='utf-8')
        result = classify_risk(0.1, config_path=cfg)   # Path object
        assert result.level_enum == RiskLevelEnum.LOW
