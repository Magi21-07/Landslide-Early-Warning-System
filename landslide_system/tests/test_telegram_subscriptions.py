# tests/test_telegram_subscriptions.py
"""
Phase 8.4 — Unit tests for TelegramSubscriptionService & TelegramSubscription.

Coverage
--------
Schema tests (TestTelegramSubscriptionSchema)
    1.  Default creation sets correct field defaults.
    2.  subscription_id is a UUID v4.
    3.  created_at and updated_at are valid ISO UTC timestamps.
    4.  Empty target_id raises ValueError.
    5.  Empty chat_id raises ValueError.
    6.  Invalid minimum_alert_level raises ValueError.
    7.  Valid levels are accepted (LOW / MODERATE / HIGH / CRITICAL).
    8.  Level normalised to uppercase (e.g. "high" → "HIGH").
    9.  No bot token field exists on the schema.
    10. model_dump() output never contains a bot-token-like field.

qualifies_for() tests (TestQualifiesFor)
    11. Disabled subscription never qualifies.
    12. HIGH subscriber qualifies for HIGH.
    13. HIGH subscriber qualifies for CRITICAL.
    14. HIGH subscriber does NOT qualify for MODERATE.
    15. HIGH subscriber does NOT qualify for LOW.
    16. LOW subscriber qualifies for all levels.
    17. CRITICAL subscriber qualifies only for CRITICAL.

Service create_subscription tests (TestCreateSubscription)
    18. Creates subscription with default level HIGH.
    19. Creates subscription with explicit LOW level.
    20. Returns TelegramSubscription instance.
    21. Duplicate (target_id, chat_id) → upserts, does NOT duplicate.
    22. Upsert updates minimum_alert_level and updated_at.
    23. Upsert preserves original subscription_id and created_at.
    24. Upsert re-enables a previously disabled subscription.
    25. Invalid level raises ValueError before storage.

Service disable/enable tests (TestDisableEnable)
    26. disable_subscription sets enabled=False.
    27. disable_subscription returns True when found.
    28. disable_subscription returns False when not found.
    29. enable_subscription sets enabled=True.
    30. enable_subscription returns True when found.
    31. enable_subscription returns False when not found.
    32. Disabled subscription excluded from get_target_subscriptions.
    33. Re-enabled subscription included in get_target_subscriptions.

Service get_target_subscriptions tests (TestGetTargetSubscriptions)
    34. Returns all enabled subscriptions when no level filter.
    35. Returns empty list when no subscriptions exist.
    36. Disabled subscriptions excluded.
    37. Level filter: HIGH event → subscriber with HIGH threshold included.
    38. Level filter: HIGH event → subscriber with CRITICAL threshold excluded.
    39. Level filter: CRITICAL event → subscriber with HIGH threshold included.
    40. Level filter: MODERATE event → subscriber with HIGH threshold excluded.
    41. Level filter: LOW event → subscriber with LOW threshold included only.
    42. Multiple subscribers with mixed thresholds filtered correctly.
    43. Subscriptions for different targets not returned.

Service list_all_subscriptions tests (TestListAll)
    44. Returns all subscriptions including disabled.
    45. target_id filter limits to that target.
    46. Empty store returns empty list.

Persistence tests (TestPersistence)
    47. Subscriptions saved to JSON file after create.
    48. Subscriptions loaded from JSON file on init.
    49. Disable flushed to file.

Security tests (TestSecurityNoTokenLeak)
    50. Subscription record has no bot_token attribute.
    51. model_dump() keys do not include any token-like name.
    52. str(subscription) does not expose secrets.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import uuid
import re
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.alerts.telegram_subscriptions import (
    TelegramSubscription,
    TelegramSubscriptionService,
)

_UUID4_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
)


# ===========================================================================
# 1–10. Schema tests
# ===========================================================================

class TestTelegramSubscriptionSchema:

    def test_default_minimum_alert_level_is_high(self):
        sub = TelegramSubscription(target_id="shimla-01", chat_id="-100111")
        assert sub.minimum_alert_level == "HIGH"

    def test_default_enabled_true(self):
        sub = TelegramSubscription(target_id="shimla-01", chat_id="-100111")
        assert sub.enabled is True

    def test_subscription_id_is_uuid4(self):
        sub = TelegramSubscription(target_id="t1", chat_id="c1")
        assert _UUID4_RE.match(sub.subscription_id), (
            f"subscription_id is not UUID v4: {sub.subscription_id!r}"
        )

    def test_each_subscription_has_unique_id(self):
        s1 = TelegramSubscription(target_id="t1", chat_id="c1")
        s2 = TelegramSubscription(target_id="t1", chat_id="c2")
        assert s1.subscription_id != s2.subscription_id

    def test_created_at_is_valid_iso_utc(self):
        sub = TelegramSubscription(target_id="t1", chat_id="c1")
        dt  = datetime.datetime.fromisoformat(sub.created_at)
        assert dt.tzinfo is not None

    def test_updated_at_is_valid_iso_utc(self):
        sub = TelegramSubscription(target_id="t1", chat_id="c1")
        dt  = datetime.datetime.fromisoformat(sub.updated_at)
        assert dt.tzinfo is not None

    def test_empty_target_id_raises(self):
        with pytest.raises(ValueError):
            TelegramSubscription(target_id="", chat_id="c1")

    def test_whitespace_target_id_raises(self):
        with pytest.raises(ValueError):
            TelegramSubscription(target_id="   ", chat_id="c1")

    def test_empty_chat_id_raises(self):
        with pytest.raises(ValueError):
            TelegramSubscription(target_id="t1", chat_id="")

    def test_whitespace_chat_id_raises(self):
        with pytest.raises(ValueError):
            TelegramSubscription(target_id="t1", chat_id="   ")

    @pytest.mark.parametrize("bad_level", [
        "MEDIUM", "SEVERE", "EMERGENCY", "EXTREME", "NONE", "", "0",
    ])
    def test_invalid_alert_level_raises(self, bad_level):
        with pytest.raises(ValueError):
            TelegramSubscription(
                target_id="t1", chat_id="c1", minimum_alert_level=bad_level
            )

    @pytest.mark.parametrize("level", ["LOW", "MODERATE", "HIGH", "CRITICAL"])
    def test_valid_alert_levels_accepted(self, level):
        sub = TelegramSubscription(target_id="t1", chat_id="c1", minimum_alert_level=level)
        assert sub.minimum_alert_level == level

    def test_level_normalised_to_uppercase(self):
        sub = TelegramSubscription(target_id="t1", chat_id="c1", minimum_alert_level="high")
        assert sub.minimum_alert_level == "HIGH"

    def test_no_bot_token_field(self):
        sub   = TelegramSubscription(target_id="t1", chat_id="c1")
        dumped = sub.model_dump()
        for key in dumped:
            assert "token" not in key.lower(), (
                f"Unexpected token-related field in schema: {key!r}"
            )

    def test_model_dump_keys_do_not_include_token(self):
        sub    = TelegramSubscription(target_id="t1", chat_id="c1")
        fields = set(sub.model_dump().keys())
        expected = {
            "subscription_id", "target_id", "chat_id",
            "minimum_alert_level", "enabled", "created_at", "updated_at",
        }
        assert fields == expected


# ===========================================================================
# 11–17. qualifies_for() tests
# ===========================================================================

class TestQualifiesFor:

    def _sub(self, level: str, enabled: bool = True) -> TelegramSubscription:
        return TelegramSubscription(
            target_id="t1", chat_id="c1",
            minimum_alert_level=level, enabled=enabled,
        )

    def test_disabled_never_qualifies(self):
        sub = self._sub("LOW", enabled=False)
        for level in ("LOW", "MODERATE", "HIGH", "CRITICAL"):
            assert sub.qualifies_for(level) is False

    def test_high_subscriber_qualifies_for_high(self):
        assert self._sub("HIGH").qualifies_for("HIGH") is True

    def test_high_subscriber_qualifies_for_critical(self):
        assert self._sub("HIGH").qualifies_for("CRITICAL") is True

    def test_high_subscriber_not_qualify_for_moderate(self):
        assert self._sub("HIGH").qualifies_for("MODERATE") is False

    def test_high_subscriber_not_qualify_for_low(self):
        assert self._sub("HIGH").qualifies_for("LOW") is False

    def test_low_subscriber_qualifies_for_all(self):
        sub = self._sub("LOW")
        for level in ("LOW", "MODERATE", "HIGH", "CRITICAL"):
            assert sub.qualifies_for(level) is True

    def test_critical_subscriber_qualifies_only_for_critical(self):
        sub = self._sub("CRITICAL")
        assert sub.qualifies_for("CRITICAL") is True
        for level in ("LOW", "MODERATE", "HIGH"):
            assert sub.qualifies_for(level) is False

    def test_moderate_subscriber_qualifies_for_moderate_high_critical(self):
        sub = self._sub("MODERATE")
        assert sub.qualifies_for("LOW") is False
        assert sub.qualifies_for("MODERATE") is True
        assert sub.qualifies_for("HIGH") is True
        assert sub.qualifies_for("CRITICAL") is True


# ===========================================================================
# 18–25. create_subscription tests
# ===========================================================================

class TestCreateSubscription:

    def setup_method(self):
        self.svc = TelegramSubscriptionService()

    def test_creates_with_default_level_high(self):
        sub = self.svc.create_subscription("shimla-01", "-100111")
        assert sub.minimum_alert_level == "HIGH"

    def test_creates_with_explicit_low_level(self):
        sub = self.svc.create_subscription("wayanad-02", "-100222", "LOW")
        assert sub.minimum_alert_level == "LOW"

    def test_returns_telegram_subscription_instance(self):
        sub = self.svc.create_subscription("t1", "c1")
        assert isinstance(sub, TelegramSubscription)

    def test_subscription_stored_in_service(self):
        self.svc.create_subscription("t1", "c1")
        assert len(self.svc) == 1

    def test_duplicate_does_not_create_second_record(self):
        self.svc.create_subscription("t1", "c1", "HIGH")
        self.svc.create_subscription("t1", "c1", "CRITICAL")
        assert len(self.svc) == 1

    def test_duplicate_updates_minimum_alert_level(self):
        self.svc.create_subscription("t1", "c1", "HIGH")
        updated = self.svc.create_subscription("t1", "c1", "CRITICAL")
        assert updated.minimum_alert_level == "CRITICAL"

    def test_upsert_preserves_subscription_id(self):
        first  = self.svc.create_subscription("t1", "c1", "HIGH")
        second = self.svc.create_subscription("t1", "c1", "LOW")
        assert first.subscription_id == second.subscription_id

    def test_upsert_preserves_created_at(self):
        first  = self.svc.create_subscription("t1", "c1", "HIGH")
        second = self.svc.create_subscription("t1", "c1", "LOW")
        assert first.created_at == second.created_at

    def test_upsert_updates_updated_at(self):
        import time
        first  = self.svc.create_subscription("t1", "c1", "HIGH")
        time.sleep(0.01)
        second = self.svc.create_subscription("t1", "c1", "LOW")
        assert second.updated_at >= first.updated_at

    def test_upsert_re_enables_disabled_subscription(self):
        self.svc.create_subscription("t1", "c1", "HIGH")
        self.svc.disable_subscription("t1", "c1")
        re_created = self.svc.create_subscription("t1", "c1", "HIGH")
        assert re_created.enabled is True

    def test_invalid_level_raises_value_error(self):
        with pytest.raises(ValueError):
            self.svc.create_subscription("t1", "c1", "MEDIUM")

    def test_different_chat_ids_create_separate_subscriptions(self):
        self.svc.create_subscription("t1", "c1", "HIGH")
        self.svc.create_subscription("t1", "c2", "HIGH")
        assert len(self.svc) == 2

    def test_different_target_ids_create_separate_subscriptions(self):
        self.svc.create_subscription("t1", "c1", "HIGH")
        self.svc.create_subscription("t2", "c1", "HIGH")
        assert len(self.svc) == 2


# ===========================================================================
# 26–33. disable / enable tests
# ===========================================================================

class TestDisableEnable:

    def setup_method(self):
        self.svc = TelegramSubscriptionService()

    def test_disable_sets_enabled_false(self):
        self.svc.create_subscription("t1", "c1")
        self.svc.disable_subscription("t1", "c1")
        subs = self.svc.list_all_subscriptions()
        assert subs[0].enabled is False

    def test_disable_returns_true_when_found(self):
        self.svc.create_subscription("t1", "c1")
        assert self.svc.disable_subscription("t1", "c1") is True

    def test_disable_returns_false_when_not_found(self):
        assert self.svc.disable_subscription("nonexistent", "c1") is False

    def test_enable_sets_enabled_true(self):
        self.svc.create_subscription("t1", "c1")
        self.svc.disable_subscription("t1", "c1")
        self.svc.enable_subscription("t1", "c1")
        subs = self.svc.list_all_subscriptions()
        assert subs[0].enabled is True

    def test_enable_returns_true_when_found(self):
        self.svc.create_subscription("t1", "c1")
        self.svc.disable_subscription("t1", "c1")
        assert self.svc.enable_subscription("t1", "c1") is True

    def test_enable_returns_false_when_not_found(self):
        assert self.svc.enable_subscription("nonexistent", "c1") is False

    def test_disabled_excluded_from_get_subscriptions(self):
        self.svc.create_subscription("t1", "c1")
        self.svc.disable_subscription("t1", "c1")
        result = self.svc.get_target_subscriptions("t1")
        assert result == []

    def test_re_enabled_included_in_get_subscriptions(self):
        self.svc.create_subscription("t1", "c1")
        self.svc.disable_subscription("t1", "c1")
        self.svc.enable_subscription("t1", "c1")
        result = self.svc.get_target_subscriptions("t1")
        assert len(result) == 1
        assert result[0].enabled is True


# ===========================================================================
# 34–43. get_target_subscriptions tests
# ===========================================================================

class TestGetTargetSubscriptions:

    def setup_method(self):
        self.svc = TelegramSubscriptionService()

    def test_returns_all_enabled_when_no_filter(self):
        self.svc.create_subscription("t1", "c1", "HIGH")
        self.svc.create_subscription("t1", "c2", "LOW")
        result = self.svc.get_target_subscriptions("t1")
        assert len(result) == 2

    def test_returns_empty_list_when_none_exist(self):
        result = self.svc.get_target_subscriptions("nonexistent")
        assert result == []

    def test_disabled_excluded(self):
        self.svc.create_subscription("t1", "c1", "HIGH")
        self.svc.create_subscription("t1", "c2", "LOW")
        self.svc.disable_subscription("t1", "c2")
        result = self.svc.get_target_subscriptions("t1")
        assert len(result) == 1
        assert result[0].chat_id == "c1"

    def test_level_filter_high_event_includes_high_subscriber(self):
        self.svc.create_subscription("t1", "c1", "HIGH")
        result = self.svc.get_target_subscriptions("t1", current_alert_level="HIGH")
        assert len(result) == 1

    def test_level_filter_high_event_excludes_critical_subscriber(self):
        self.svc.create_subscription("t1", "c1", "CRITICAL")
        result = self.svc.get_target_subscriptions("t1", current_alert_level="HIGH")
        assert result == []

    def test_level_filter_critical_event_includes_high_subscriber(self):
        self.svc.create_subscription("t1", "c1", "HIGH")
        result = self.svc.get_target_subscriptions("t1", current_alert_level="CRITICAL")
        assert len(result) == 1

    def test_level_filter_moderate_event_excludes_high_subscriber(self):
        self.svc.create_subscription("t1", "c1", "HIGH")
        result = self.svc.get_target_subscriptions("t1", current_alert_level="MODERATE")
        assert result == []

    def test_level_filter_low_event_only_includes_low_subscriber(self):
        self.svc.create_subscription("t1", "c1", "LOW")
        self.svc.create_subscription("t1", "c2", "HIGH")
        result = self.svc.get_target_subscriptions("t1", current_alert_level="LOW")
        assert len(result) == 1
        assert result[0].chat_id == "c1"

    def test_mixed_thresholds_filtered_correctly_for_critical(self):
        self.svc.create_subscription("t1", "c1", "LOW")
        self.svc.create_subscription("t1", "c2", "MODERATE")
        self.svc.create_subscription("t1", "c3", "HIGH")
        self.svc.create_subscription("t1", "c4", "CRITICAL")
        result = self.svc.get_target_subscriptions("t1", current_alert_level="CRITICAL")
        chat_ids = {s.chat_id for s in result}
        assert chat_ids == {"c1", "c2", "c3", "c4"}

    def test_mixed_thresholds_filtered_correctly_for_high(self):
        self.svc.create_subscription("t1", "c1", "LOW")
        self.svc.create_subscription("t1", "c2", "MODERATE")
        self.svc.create_subscription("t1", "c3", "HIGH")
        self.svc.create_subscription("t1", "c4", "CRITICAL")
        result = self.svc.get_target_subscriptions("t1", current_alert_level="HIGH")
        chat_ids = {s.chat_id for s in result}
        assert chat_ids == {"c1", "c2", "c3"}

    def test_different_target_subscriptions_not_returned(self):
        self.svc.create_subscription("t1", "c1", "HIGH")
        self.svc.create_subscription("t2", "c2", "HIGH")
        result = self.svc.get_target_subscriptions("t1")
        assert all(s.target_id == "t1" for s in result)
        assert len(result) == 1


# ===========================================================================
# 44–46. list_all_subscriptions tests
# ===========================================================================

class TestListAll:

    def setup_method(self):
        self.svc = TelegramSubscriptionService()

    def test_returns_all_including_disabled(self):
        self.svc.create_subscription("t1", "c1")
        self.svc.create_subscription("t1", "c2")
        self.svc.disable_subscription("t1", "c2")
        result = self.svc.list_all_subscriptions()
        assert len(result) == 2

    def test_target_id_filter_limits_results(self):
        self.svc.create_subscription("t1", "c1")
        self.svc.create_subscription("t2", "c2")
        result = self.svc.list_all_subscriptions(target_id="t1")
        assert len(result) == 1
        assert result[0].target_id == "t1"

    def test_empty_store_returns_empty_list(self):
        assert self.svc.list_all_subscriptions() == []


# ===========================================================================
# 47–49. Persistence tests
# ===========================================================================

class TestPersistence:

    def test_subscriptions_saved_to_json(self, tmp_path):
        path = tmp_path / "subs.json"
        svc  = TelegramSubscriptionService(persistence_path=str(path))
        svc.create_subscription("t1", "c1", "HIGH")
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data) == 1

    def test_subscriptions_loaded_from_json(self, tmp_path):
        path = tmp_path / "subs.json"
        # Write first instance
        svc1 = TelegramSubscriptionService(persistence_path=str(path))
        svc1.create_subscription("t1", "c1", "CRITICAL")
        # Load second instance from same file
        svc2 = TelegramSubscriptionService(persistence_path=str(path))
        result = svc2.list_all_subscriptions()
        assert len(result) == 1
        assert result[0].minimum_alert_level == "CRITICAL"
        assert result[0].target_id == "t1"

    def test_disable_flushed_to_file(self, tmp_path):
        path = tmp_path / "subs.json"
        svc  = TelegramSubscriptionService(persistence_path=str(path))
        svc.create_subscription("t1", "c1", "HIGH")
        svc.disable_subscription("t1", "c1")
        # Reload
        svc2    = TelegramSubscriptionService(persistence_path=str(path))
        all_sub = svc2.list_all_subscriptions()
        assert all_sub[0].enabled is False


# ===========================================================================
# 50–52. Security — no bot token leakage
# ===========================================================================

class TestSecurityNoTokenLeak:

    def test_subscription_has_no_token_attribute(self):
        sub = TelegramSubscription(target_id="t1", chat_id="c1")
        assert not hasattr(sub, "bot_token")
        assert not hasattr(sub, "token")

    def test_model_dump_has_no_token_keys(self):
        sub    = TelegramSubscription(target_id="t1", chat_id="c1")
        dumped = sub.model_dump()
        for key in dumped:
            assert "token" not in key.lower(), f"Token-like field found: {key!r}"

    def test_str_representation_has_no_secret(self):
        sub = TelegramSubscription(target_id="t1", chat_id="c1")
        # Ensure no accidental token field shows up in repr
        assert "bot_token" not in str(sub)
        assert "secret" not in str(sub).lower()
