# src/alerts/telegram_message.py
"""
Phase 8.6 — Telegram Message Generation Engine
==============================================

Builds mobile-optimized, executive Telegram alert messages from authoritative
Phase FC-4 risk responses.
"""

import datetime
from typing import Any, Dict, List, Optional

class TelegramMessageBuilder:
    @staticmethod
    def build_message(
        target_id: str,
        current_risk_level: str,
        event_type: str,
        probability: float,
        triggered_at: str,
        previous_risk_level: Optional[str] = None,
        data_quality: str = "VALID",
        stale: bool = False,
        model_version: str = "",
        shap_drivers: Optional[List[Dict[str, Any]]] = None,
        ndvi: Optional[float] = None,
        sar_soil_moisture: Optional[float] = None,
        rainfall_3day_mm: Optional[float] = None,
    ) -> str:
        # Templates
        if data_quality != "VALID" or stale:
            header = "🛠️ ⚠️ **LEWS SYSTEM NOTICE / SENSOR DEGRADATION**"
            advisory = "Data quality or sensor staleness flag detected. Proceed with caution."
            action_guidance = ""
        elif event_type in ("RECOVERY", "DE_ESCALATION"):
            header = "🟢 **LANDSLIDE RISK RECOVERY / DE-ESCALATION**"
            advisory = "Landslide risk level has de-escalated to normal/safe baseline."
            action_guidance = ""
        elif current_risk_level == "CRITICAL" or event_type == "ESCALATION":
            header = "🚨 🔴 **CRITICAL LANDSLIDE EMERGENCY**"
            advisory = "Severe landslide risk condition detected. Recommended immediate safety protocols."
            action_guidance = "🆘 *Immediate Action Required:* Evacuate all personnel."
        else:
            header = "⚠️ 🟠 **HIGH LANDSLIDE WARNING**"
            advisory = "Elevated landslide risk detected for target area. Increased monitoring recommended."
            action_guidance = "📡 *Active Monitoring:* Deploy field teams."

        prob_pct = f"{probability * 100:.0f}%"

        try:
            dt = datetime.datetime.fromisoformat(triggered_at.replace("Z", "+00:00"))
            ts_display = dt.strftime("%Y-%m-%d %H:%M:%S") + " UTC"
        except (ValueError, AttributeError):
            ts_display = triggered_at

        lines = [
            header,
            advisory,
            "",
            "**Landslide Early Warning System**",
            f"🗺 *Target ID:* `{target_id}`",
            f"🕒 *Observation Timestamp:* {ts_display}",
            f"📊 *Current Risk Level:* *{current_risk_level}*",
            f"🎯 *Probability:* *{prob_pct}*",
            f"🔄 *Trigger Event Type:* {_fmt_event_type(event_type)}",
        ]
        
        if previous_risk_level:
            lines.append(f"📉 *Transition:* {previous_risk_level} → {current_risk_level}")

        lines.extend([
            f"🔧 *Model Version:* `{model_version if model_version else 'Unavailable'}`",
            f"📡 *Data Freshness:* `{'Stale' if stale else 'Fresh'}` (Quality: {data_quality})",
            "",
        ])
        
        has_env = ndvi is not None or sar_soil_moisture is not None or rainfall_3day_mm is not None
        if has_env:
            lines.append("🛰 *Environmental Metrics:*")
            if rainfall_3day_mm is not None:
                lines.append(f"  • *Rainfall 3-Day:* `{rainfall_3day_mm:.1f} mm`")
            if ndvi is not None:
                lines.append(f"  • *NDVI:* `{ndvi:.3f}`")
            if sar_soil_moisture is not None:
                lines.append(f"  • *SAR Soil Moisture Proxy:* `{sar_soil_moisture:.3f}`")
            lines.append("")

        lines.append("🔬 *Key Risk Drivers (SHAP Attribution):*")
        lines.append("_Note: These factors show statistical correlation, not definitive causation._")

        if shap_drivers:
            for driver in shap_drivers[:3]:
                feature = str(driver.get("feature", "unknown"))
                contrib = float(driver.get("contribution", 0.0))
                sign = "+" if contrib >= 0 else ""
                lines.append(f"  • `{feature}`: {sign}{contrib * 100:.0f}%")
        else:
            lines.append("  • `Unavailable`")

        if action_guidance:
            lines.append("")
            lines.append(action_guidance)
            
        lines.append("")
        lines.append(f"🌐 [Open GIS Dashboard](https://dashboard.landslide.local/target/{target_id})")

        return "\n".join(lines)


def _fmt_event_type(event_type: str) -> str:
    labels = {
        "INITIAL_TRIGGER": "Initial Trigger",
        "ESCALATION": "Escalation",
        "DE_ESCALATION": "De-escalation",
        "RECOVERY": "Recovery",
        "PERSISTENT_UNCHANGED": "Persistent Unchanged",
        "SUPPRESSED": "Suppressed",
    }
    return labels.get(event_type.upper(), event_type)
