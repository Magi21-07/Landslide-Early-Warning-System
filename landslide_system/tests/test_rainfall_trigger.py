"""
tests/test_rainfall_trigger.py
--------------------------------
Unit tests for src/risk/rainfall_trigger.py (RainfallTriggerEngine).
YAML loading is mocked via unittest.mock to provide deterministic thresholds.
No file I/O or network calls occur.

Test threshold config used throughout:
    rainfall_1d:  watch=50,  warning=100, critical=150
    rainfall_3d:  watch=80,  warning=150, critical=250
    rainfall_7d:  watch=120, warning=220, critical=350
    rainfall_15d: watch=180, warning=320, critical=500
"""

import sys
import os
import pytest
from unittest.mock import patch, mock_open

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.risk.rainfall_trigger import (
    RainfallTriggerEngine,
    TriggerResult,
    TRIGGER_SCORES,
)

# ---------------------------------------------------------------------------
# Deterministic mock YAML config
# ---------------------------------------------------------------------------

MOCK_THRESHOLDS = {
    "rainfall_1d":  {"watch": 50.0,  "warning": 100.0, "critical": 150.0},
    "rainfall_3d":  {"watch": 80.0,  "warning": 150.0, "critical": 250.0},
    "rainfall_7d":  {"watch": 120.0, "warning": 220.0, "critical": 350.0},
    "rainfall_15d": {"watch": 180.0, "warning": 320.0, "critical": 500.0},
}

MOCK_YAML_CONTENT = {
    "thresholds": MOCK_THRESHOLDS
}


def _make_engine() -> RainfallTriggerEngine:
    """Create RainfallTriggerEngine with mocked YAML — no disk I/O."""
    with patch('src.risk.rainfall_trigger.RainfallTriggerEngine._load_config',
               return_value=MOCK_THRESHOLDS):
        engine = RainfallTriggerEngine(config_path='mock_path.yaml')
    return engine


def _eval(features: dict) -> TriggerResult:
    """Shortcut: create engine and evaluate a feature dict."""
    return _make_engine().evaluate(features)


# ---------------------------------------------------------------------------
# 1. NORMAL: all features below WATCH threshold
# ---------------------------------------------------------------------------

class TestNormalState:

    def test_all_below_watch_is_normal(self):
        result = _eval({
            "rainfall_1d":  10.0,
            "rainfall_3d":  30.0,
            "rainfall_7d":  60.0,
            "rainfall_15d": 90.0,
        })
        assert result.trigger_state == "NORMAL"
        assert result.trigger_score == 0

    def test_normal_returns_safe_reason(self):
        result = _eval({
            "rainfall_1d": 5.0,
            "rainfall_3d": 10.0,
        })
        assert any("safe limits" in r for r in result.trigger_reasons)

    def test_zero_rainfall_is_normal(self):
        result = _eval({
            "rainfall_1d":  0.0,
            "rainfall_3d":  0.0,
            "rainfall_7d":  0.0,
            "rainfall_15d": 0.0,
        })
        assert result.trigger_state == "NORMAL"

    def test_features_evaluated_count_is_correct(self):
        result = _eval({
            "rainfall_1d": 5.0,
            "rainfall_3d": 20.0,
        })
        assert result.features_evaluated == 2


# ---------------------------------------------------------------------------
# 2. Threshold boundary behaviour
# ---------------------------------------------------------------------------

class TestThresholdBoundaries:

    def test_exactly_at_watch_triggers_watch(self):
        result = _eval({"rainfall_1d": 50.0})   # watch = 50.0
        assert result.trigger_state == "WATCH"
        assert result.trigger_score == 1

    def test_just_below_watch_is_normal(self):
        result = _eval({"rainfall_1d": 49.99})
        assert result.trigger_state == "NORMAL"

    def test_exactly_at_warning_triggers_warning(self):
        result = _eval({"rainfall_1d": 100.0})  # warning = 100.0
        assert result.trigger_state == "WARNING"
        assert result.trigger_score == 2

    def test_exactly_at_critical_triggers_critical(self):
        result = _eval({"rainfall_1d": 150.0})  # critical = 150.0
        assert result.trigger_state == "CRITICAL"
        assert result.trigger_score == 3

    def test_well_above_critical_is_still_critical(self):
        result = _eval({"rainfall_1d": 999.0})
        assert result.trigger_state == "CRITICAL"
        assert result.trigger_score == 3

    def test_each_feature_boundary_watch(self):
        for feat, cfg in MOCK_THRESHOLDS.items():
            result = _eval({feat: cfg["watch"]})
            assert result.trigger_state == "WATCH", \
                f"{feat} at watch={cfg['watch']} should be WATCH"

    def test_each_feature_boundary_critical(self):
        for feat, cfg in MOCK_THRESHOLDS.items():
            result = _eval({feat: cfg["critical"]})
            assert result.trigger_state == "CRITICAL", \
                f"{feat} at critical={cfg['critical']} should be CRITICAL"


# ---------------------------------------------------------------------------
# 3. Highest severity wins
# ---------------------------------------------------------------------------

class TestHighestSeverityWins:

    def test_1d_normal_15d_critical_gives_critical(self):
        result = _eval({
            "rainfall_1d":  10.0,   # below watch  -> NORMAL
            "rainfall_3d":  50.0,   # below watch  -> NORMAL
            "rainfall_7d":  90.0,   # below watch  -> NORMAL
            "rainfall_15d": 500.0,  # at critical  -> CRITICAL
        })
        assert result.trigger_state == "CRITICAL"
        assert result.trigger_score == 3

    def test_1d_watch_7d_warning_gives_warning(self):
        result = _eval({
            "rainfall_1d": 55.0,   # above watch   -> WATCH
            "rainfall_7d": 220.0,  # at warning    -> WARNING
        })
        assert result.trigger_state == "WARNING"
        assert result.trigger_score == 2

    def test_mixed_features_max_severity_selected(self):
        result = _eval({
            "rainfall_1d":  150.0,  # CRITICAL
            "rainfall_3d":  10.0,   # NORMAL
            "rainfall_7d":  220.0,  # WARNING
            "rainfall_15d": 180.0,  # WATCH (exactly)
        })
        assert result.trigger_state == "CRITICAL"

    def test_all_at_different_levels_gives_highest(self):
        result = _eval({
            "rainfall_1d":  55.0,   # WATCH
            "rainfall_3d":  160.0,  # WARNING
            "rainfall_7d":  40.0,   # NORMAL
            "rainfall_15d": 195.0,  # WATCH
        })
        assert result.trigger_state == "WARNING"

    def test_trigger_reasons_includes_all_breaches(self):
        """Every breached feature should appear in trigger_reasons."""
        result = _eval({
            "rainfall_1d":  60.0,   # WATCH
            "rainfall_15d": 350.0,  # WARNING
        })
        reasons_combined = " | ".join(result.trigger_reasons)
        assert "1-day" in reasons_combined
        assert "15-day" in reasons_combined

    def test_trigger_score_matches_state(self):
        for state, expected_score in TRIGGER_SCORES.items():
            result = _eval({
                "rainfall_1d":  {
                    "NORMAL":   10.0,
                    "WATCH":    55.0,
                    "WARNING":  110.0,
                    "CRITICAL": 200.0,
                }[state]
            })
            assert result.trigger_state == state
            assert result.trigger_score == expected_score


# ---------------------------------------------------------------------------
# 4. Missing (None) feature values handled gracefully
# ---------------------------------------------------------------------------

class TestMissingValues:

    def test_none_feature_does_not_crash(self):
        """None must be silently skipped, no TypeError."""
        result = _eval({
            "rainfall_1d":  None,
            "rainfall_3d":  None,
            "rainfall_7d":  None,
            "rainfall_15d": None,
        })
        # No exception; result should be NORMAL with 0 features evaluated
        assert result.trigger_state == "NORMAL"
        assert result.features_evaluated == 0

    def test_partial_none_uses_available_features(self):
        result = _eval({
            "rainfall_1d":  None,    # skip
            "rainfall_15d": 500.0,   # CRITICAL
        })
        assert result.trigger_state == "CRITICAL"
        assert result.features_evaluated == 1

    def test_none_not_treated_as_zero(self):
        """If None were coerced to 0, result would be NORMAL; must still be NORMAL
        for the correct reason (skipped), not because 0 < watch threshold."""
        result = _eval({"rainfall_1d": None})
        assert result.features_evaluated == 0
        assert result.trigger_state == "NORMAL"


# ---------------------------------------------------------------------------
# 5. Partial day flag
# ---------------------------------------------------------------------------

class TestPartialDayFlag:

    def test_partial_flag_appends_note_to_reasons(self):
        result = _eval({
            "rainfall_1d":    5.0,     # NORMAL
            "partial_day_flag": True,
        })
        notes = [r for r in result.trigger_reasons if r.startswith("Note:")]
        assert len(notes) == 1
        assert "incomplete current-day" in notes[0]

    def test_no_partial_flag_no_note(self):
        result = _eval({"rainfall_1d": 5.0})
        notes = [r for r in result.trigger_reasons if r.startswith("Note:")]
        assert len(notes) == 0

    def test_partial_flag_with_critical_still_critical(self):
        result = _eval({
            "rainfall_1d":      200.0,   # CRITICAL
            "partial_day_flag": True,
        })
        assert result.trigger_state == "CRITICAL"
        # Should have both a breach reason and the partial note
        notes = [r for r in result.trigger_reasons if r.startswith("Note:")]
        assert len(notes) == 1

    def test_partial_flag_false_no_note(self):
        result = _eval({
            "rainfall_1d":      10.0,
            "partial_day_flag": False,
        })
        notes = [r for r in result.trigger_reasons if r.startswith("Note:")]
        assert len(notes) == 0


# ---------------------------------------------------------------------------
# 6. Output schema validation
# ---------------------------------------------------------------------------

class TestOutputSchema:

    def test_returns_trigger_result_instance(self):
        result = _eval({"rainfall_1d": 10.0})
        assert isinstance(result, TriggerResult)

    def test_to_dict_contains_required_keys(self):
        result = _eval({"rainfall_1d": 10.0})
        d = result.to_dict()
        for key in ['trigger_state', 'trigger_score', 'trigger_reasons',
                    'features_evaluated']:
            assert key in d

    def test_trigger_reasons_is_list(self):
        result = _eval({"rainfall_1d": 10.0})
        assert isinstance(result.trigger_reasons, list)

    def test_reason_text_contains_threshold_value(self):
        result = _eval({"rainfall_1d": 160.0})   # CRITICAL, limit=150
        reasons_combined = " ".join(result.trigger_reasons)
        assert "150.0" in reasons_combined

    def test_reason_text_contains_observed_value(self):
        result = _eval({"rainfall_1d": 160.0})
        reasons_combined = " ".join(result.trigger_reasons)
        assert "160.0" in reasons_combined

    def test_accepts_dataclass_like_object(self):
        """Engine should accept any object with __dict__."""
        class MockFeatureSet:
            rainfall_1d  = 55.0
            rainfall_3d  = None
            rainfall_7d  = None
            rainfall_15d = None
            partial_day_flag = False

        result = _make_engine().evaluate(MockFeatureSet())
        assert result.trigger_state == "WATCH"

    def test_rejects_invalid_input_type(self):
        with pytest.raises(TypeError):
            _make_engine().evaluate("invalid input")


# ---------------------------------------------------------------------------
# 7. Config loading
# ---------------------------------------------------------------------------

class TestConfigLoading:

    def test_missing_config_file_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            RainfallTriggerEngine(config_path='nonexistent/path.yaml')

    def test_yaml_must_have_thresholds_key(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("not_thresholds:\n  a: 1\n", encoding='utf-8')
        with pytest.raises(ValueError, match="thresholds"):
            RainfallTriggerEngine(config_path=str(bad_yaml))

    def test_valid_yaml_loads_correctly(self, tmp_path):
        yaml_content = (
            "thresholds:\n"
            "  rainfall_1d:\n"
            "    watch: 50.0\n"
            "    warning: 100.0\n"
            "    critical: 150.0\n"
        )
        cfg = tmp_path / "thresholds.yaml"
        cfg.write_text(yaml_content, encoding='utf-8')
        engine = RainfallTriggerEngine(config_path=str(cfg))
        result = engine.evaluate({"rainfall_1d": 55.0})
        assert result.trigger_state == "WATCH"
