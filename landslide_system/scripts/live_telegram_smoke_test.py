import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.alerts.telegram_config import TelegramConfig
from src.alerts.alert_evaluator import AlertEvaluator
from src.alerts.telegram_dispatcher import TelegramDispatcher
from src.alerts.providers.telegram_provider import TelegramProvider
import datetime

# Ensure mode is REAL
os.environ["TELEGRAM_MODE"] = "REAL"

async def main():
    try:
        config = TelegramConfig()
    except Exception as e:
        print(f"Failed to load TelegramConfig: {e}")
        sys.exit(1)

    print(f"Config Mode: {config.mode}")
    print(f"Chat ID: {config.chat_id}")

    # Construct Mock RiskResponse dictionary
    risk_response = {
        "location_id": "TARGET-001",
        "status": "success",
        "risk_level": "HIGH",
        "latitude": 10.0,
        "longitude": 20.0,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "observation_date": datetime.date.today().isoformat(),
        "stale": False,
        "data_source": "MOCK/SMOKE_TEST",
        "probability": 0.78,
        "susceptibility_class": "HIGH",
        "dynamic_risk": "HIGH",
        "rainfall_trigger_state": "WARNING",
        "rainfall_trigger_score": 10,
        "rainfall_3d": 185.4,
        "top_risk_factors": [
            {"factor": "Rainfall_3D", "shap_value": 0.42},
            {"factor": "Slope_Angle", "shap_value": 0.28}
        ],
        "trigger_reason": "3-day cumulative rainfall (185.4mm) exceeded threshold"
    }

    evaluator = AlertEvaluator()
    event = evaluator.evaluate_target_risk("TARGET-001", risk_response)
    
    if not event.event_emitted:
        print("Alert Policy blocked the event from emitting.")
        print(event.policy_decision)
        sys.exit(1)

    print(f"Event Emitted! Target: {event.target_id}, Severity: {event.current_risk_level}")

    dispatcher = TelegramDispatcher(config)
    print("Dispatching to Telegram...")
    try:
        result = await dispatcher.send_alert_event(event)
        
        if result["status"] == "DISPATCH_SUCCESS":
            print("========================================")
            print("SMOKE TEST SUCCESSFUL!")
            print(f"Message ID: {result.get('message_id')}")
            print("========================================")
        else:
            print("========================================")
            print("SMOKE TEST FAILED!")
            print(f"Status: {result.get('status')}")
            detail = result.get('detail', '')
            print(f"Detail: {detail.encode('ascii', 'ignore').decode('ascii')}")
            print("========================================")
            
    except Exception as e:
        print(f"Dispatch threw exception: {e}")
        
if __name__ == "__main__":
    asyncio.run(main())
