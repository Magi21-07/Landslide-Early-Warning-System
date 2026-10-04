# Landslide Early Warning System (LEWS)
**Machine Learning-Driven Real-Time Landslide Risk Prediction & Emergency Alert Pipeline**

## 1. Executive Overview
The Landslide Early Warning System (LEWS) is an end-to-end predictive pipeline designed to evaluate and alert on potential landslide risks in real-time. Powered by a robust 14-feature XGBoost v2.0.0 model ($ROC\text{-}AUC = 0.8707$), the system integrates dynamic SHAP (SHapley Additive exPlanations) explainability (XAI), a real-time GIS spatial distance engine, and an automated Telegram alert dispatch pipeline. LEWS aims to provide rapid, transparent, and accurate risk assessments to safeguard vulnerable communities.

## 2. System Architecture

```text
┌─────────────────────────────────┐
│  React Frontend                 │
│  (Vite + Tailwind + TypeScript) │
└───────────────┬─────────────────┘
                │ REST API
                ▼
┌─────────────────────────────────┐
│  FastAPI REST Backend           │
│  (Python 3.11+)                 │
└───────────────┬─────────────────┘
                │
    ┌───────────┼────────────┐
    ▼           ▼            ▼
┌────────┐  ┌────────┐  ┌───────────┐
│ XGBoost│  │ Spatial│  │ Async     │
│ v2.0.0 │  │ Engine │  │ Telegram  │
│ + SHAP │  │ (GIS)  │  │ Alerts    │
└────────┘  └────────┘  └───────────┘
```

## 3. Key Features & Capabilities
*   **ML & Explainability**: 14-factor risk assessment powered by XGBoost with dynamic SHAP feature attributions (e.g., +Rainfall, +Slope, +Soil Saturation), ensuring that predictions are fully interpretable.
*   **Real-Time Spatial Calculations**: Dynamic distance-to-river spatial lookups and proximity evaluations based on target latitude and longitude without relying on hardcoded fallbacks.
*   **Alert Pipeline**: Asynchronous, policy-gated Telegram alert dispatcher featuring alert deduplication, retry exponential backoff, and a historical audit ledger to prevent spam and ensure reliable delivery.
*   **Interactive Demo Simulator (`/demo`)**: A sandboxed scenario simulator that allows users to override environmental parameters, replay historical disasters via presets, scan a live QR code for push notifications, and observe system behavior without mutating persistent data.

## 4. Tech Stack
*   **Backend**: Python 3.11+, FastAPI, XGBoost v2.0.0, SHAP, GeoPandas / Shapely, Pydantic, Pytest.
*   **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons, React Router DOM.
*   **Integrations**: Telegram Bot API, CHIRPS Weather Data.

## 5. Prerequisites & Environment Setup
**Prerequisites:**
*   Python 3.11+
*   Node.js 18+
*   npm

**Environment Configuration (`.env` file template):**
Create a `.env` file in the root backend directory:
```env
# System Settings
ENVIRONMENT=development
LOG_LEVEL=INFO

# Telegram Configuration
TELEGRAM_ENABLED=true
TELEGRAM_MODE=TEST  # Set to REAL for live mobile push notifications
TELEGRAM_BOT_TOKEN="your_bot_token_here"
TELEGRAM_CHAT_ID="your_chat_id_here"
```

## 6. Step-by-Step Local Installation & Running

**Backend Setup:**
```bash
# Create & activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows (or source .venv/bin/activate on Linux/Mac)

# Install dependencies
pip install -r requirements.txt

# Launch FastAPI Server
uvicorn src.api.main:app --reload --port 8000
```

**Frontend Setup:**
```bash
cd frontend
npm install
npm run dev
```

**App Links:**
*   Frontend Dashboard: [http://localhost:5173](http://localhost:5173)
*   Swagger API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## 7. Running the Test Suite
**Backend Pytest command:**
```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

**Frontend Build Verification:**
```bash
cd frontend && npm run build
```

## 8. Judge Demonstration & Demo Simulator Guide
To evaluate the LEWS Sandbox environment, navigate to the Interactive Demo page at `/demo` (or click **"⚡ Live Demo Simulator"** in the sidebar).

**Interactive Testing Steps:**
1.  **Join the Channel**: Scan the on-screen Telegram QR code with a mobile device to join the alert broadcast channel.
2.  **Adjust Sliders**: Drag the environmental parameters (3-day rainfall, soil saturation, terrain slope) manually. Observe the real-time risk gauge shifts and the dynamic SHAP factor bar updates as the model evaluates the new scenario.
3.  **Trigger Scenarios**: Click the quick-access presets (e.g., `Cloudburst Emergency` or `Shimla 2023 Disaster Replay`) to trigger a real-time, sandboxed Telegram push notification directly to the scanned phone, demonstrating the full alert pipeline.
