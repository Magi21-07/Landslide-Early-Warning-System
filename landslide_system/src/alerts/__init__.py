# src/alerts/__init__.py
"""
Alert subsystem:
  Phase 8.1  — Policy & Severity Engine
  Phase 8.2  — Event Detection & Transition Engine
  Phase 8.3  — Telegram Bot Configuration, Formatter & Async Dispatcher
  Phase 8.4  — Telegram Alert Subscription Management
"""
from src.alerts.alert_policy import AlertDecision, AlertPolicyEngine
from src.alerts.alert_evaluator import AlertEvent, AlertEvaluator
from src.alerts.state_store import TargetStateStore
from src.alerts.telegram_config import ConfigurationError, TelegramConfig
from src.alerts.telegram_formatter import format_alert_message, format_event
from src.alerts.telegram_dispatcher import TelegramDispatcher
from src.alerts.telegram_subscriptions import (
    TelegramSubscription,
    TelegramSubscriptionService,
)
from src.alerts.alert_suppression import (
    AlertSuppressionEngine,
    SuppressionDecision,
)
from src.alerts.telegram_message import TelegramMessageBuilder
from src.alerts.providers.telegram_provider import TelegramProvider, MockTelegramProvider
from src.alerts.delivery_tracker import DeliveryTracker, DeliveryRecord
from src.alerts.telegram_async import AsyncTelegramDispatcher
from src.alerts.alert_history import AlertHistoryService, AlertHistoryRecord

__all__ = [
    # Phase 8.1
    "AlertDecision",
    "AlertPolicyEngine",
    # Phase 8.2
    "AlertEvent",
    "AlertEvaluator",
    "TargetStateStore",
    # Phase 8.3 — Config
    "TelegramConfig",
    "ConfigurationError",
    # Phase 8.3 — Formatter
    "format_alert_message",
    "format_event",
    # Phase 8.3 — Dispatcher
    "TelegramDispatcher",
    # Phase 8.4 — Subscriptions
    "TelegramSubscription",
    "TelegramSubscriptionService",
    # Phase 8.5 — Suppression
    "AlertSuppressionEngine",
    "SuppressionDecision",
    # Phase 8.6 — Message Builder
    "TelegramMessageBuilder",
    # Phase 8.7 — Provider
    "TelegramProvider",
    "MockTelegramProvider",
    # Phase 8.8 — Async Dispatcher & Delivery Tracker
    "AsyncTelegramDispatcher",
    "DeliveryTracker",
    "DeliveryRecord",
    # Phase 8.10 — Alert History
    "AlertHistoryService",
    "AlertHistoryRecord",
]

