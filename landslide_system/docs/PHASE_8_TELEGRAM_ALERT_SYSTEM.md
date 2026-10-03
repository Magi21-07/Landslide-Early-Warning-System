# Phase 8: Telegram Alert System
## Landslide Early Warning System Architecture & Operational Manual

---

### 1. System Architecture & Flowchart
The Telegram Alert System acts as the primary external notification mechanism for the Landslide Early Warning System, operating entirely decoupled from the core Phase-5 risk calculation engine.

**End-to-End Pipeline:**
1. **Risk Evaluation API (`/api/v1/risk/evaluate`)**: Completes standard ML-driven risk calculation (Phase 5).
2. **Alert Policy Engine**: Intercepts the final risk response. Verifies non-stale data, applies structural safety gating, and ensures probability mappings meet strictly defined severity thresholds (`HIGH` or `CRITICAL`).
3. **Event Detection & State Machine**: Tracks historical target states (e.g., `shimla-01`). Identifies edge transitions such as `INITIAL_TRIGGER`, `ESCALATION` (Moderate -> High), `RECOVERY` (High -> Low), or `PERSISTENT_UNCHANGED`.
4. **Suppression Engine**: Hashes the alert signature (target + type + severity + factors). Evaluates against deterministic cooldown windows (e.g., 2 hours for High, 1 hour for Critical). Bypasses cooldowns on active escalations.
5. **Async Delivery Dispatcher**: Enqueues the alert payload into a FastAPI `BackgroundTask`, returning the API response instantly to the frontend.
6. **Telegram Formatter & Provider**: Renders an executive Markdown payload. Dispatches via HTTP POST to `api.telegram.org`.
7. **Delivery Tracker & History Service**: Persists an immutable ledger of the alert attempt (Success, Rate-Limited, Network Timeout).
8. **Dashboard UI**: Subscribes to the target's `/api/v1/alerts/history` to render real-time color-coded delivery badges on the React frontend.

---

### 2. Alert Policy Engine
The Policy Engine implements a 7-stage deterministic safety gate to prevent false positives and alert fatigue:
- **Enabled Verification**: Globally skips dispatch if Telegram is disabled.
- **Staleness Check**: Rejects payloads older than 24 hours to prevent out-of-date notifications.
- **Data Quality**: Validates source input integrity.
- **Severity Threshold**: strictly enforces that only `HIGH` or `CRITICAL` risk levels trigger downstream warnings.
- **Subscriber Verification**: Confirms an active, subscribed Telegram Chat ID exists for the region/target.
- **Target Routing**: Determines exactly who receives the alert.
- **Event Hydration**: Generates a unified `AlertDecision` payload.

---

### 3. Event Detection & State Machine
The Event Detection Engine tracks historical target states via the `TargetStateStore`. Transitions are computed dynamically:
- **`INITIAL_TRIGGER`**: Baseline shifts from `LOW/MODERATE` directly to `HIGH/CRITICAL`.
- **`ESCALATION`**: Severity amplifies across an active alert (`HIGH` -> `CRITICAL`).
- **`RECOVERY`**: Severity falls below the trigger threshold (`CRITICAL` -> `MODERATE`). Generates a clear recovery notification.
- **`PERSISTENT_UNCHANGED`**: Severity remains high across evaluations. Submits to the Suppression Engine.

---

### 4. Deduplication, Fingerprinting & Cooldown
The Alert Suppression Engine prevents alert fatigue:
- **Fingerprinting**: Generates a deterministic SHA-256 hash utilizing `target_id`, `event_type`, `severity`, and `trigger_reason`.
- **Cooldown Windows**: 
  - `HIGH`: 120-minute cooldown
  - `CRITICAL`: 60-minute cooldown
- **Escalation Bypass**: If a target elevates from `HIGH` to `CRITICAL`, any active cooldowns are instantly bypassed.

---

### 5. Telegram Bot Setup & Configuration
- **Environment Driven**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `TELEGRAM_MODE` (`TEST` vs `REAL`).
- **SecretStr Protection**: Bot tokens are instantiated as Pydantic `SecretStr`, completely isolated from serialization, structured logging, and JSON error traces.
- **Validation**: On application startup, the `TelegramConfig` dependency enforces that tokens are provided if `mode == 'REAL'`.

---

### 6. Executive Message Templates
Generated dynamically via `TelegramMessageBuilder`, optimized for high-visibility mobile alerts.
- **`HIGH WARNING`**: ⚠️ 🟠 **HIGH WARNING:** Elevated risk detected...
- **`CRITICAL ALERT`**: 🚨 🔴 **CRITICAL EMERGENCY:** Imminent risk evaluated...
- **`RECOVERY`**: ✅ 🟢 **RECOVERY:** Risk normalized...
- **`SYSTEM FAILURE`**: ❌ ⚠️ **DATA QUALITY ALERT:** Stale data detected...
**Strict Disclaimers:** All templates implement enforced deterministic disclaimers regarding ML-driven correlations (SHAP) versus physical causations.

---

### 7. Async Transport & Retry Resilience
- **FastAPI BackgroundTasks**: Dispatches are non-blocking, ensuring the core `/api/v1/risk/evaluate` loop remains fast.
- **Retry Logic**: Implements a binary exponential backoff loop (`max_retries=3`).
- **Rate Limit Parsing**: Reads HTTP 429 `Retry-After` headers and injects accurate `asyncio.sleep` delays.
- **Permanent Exits**: Drops 400 (Bad Request) and 403 (Forbidden) HTTP failures immediately to prevent zombie threads.

---

### 8. Delivery Tracking & Audit Logs
- **Delivery Tracker**: An in-memory concurrent data store mapping `alert_id` -> `chat_id` -> `DeliveryRecord`.
- **Idempotency Protection**: Ensures duplicate background workers cannot dispatch identical `alert_id`s in parallel.
- **States**: `NOT_SENT`, `PENDING`, `RETRYING`, `SENT`, `FAILED`.

---

### 9. Dashboard UI Integration
The React Frontend binds to backend alerting states securely:
- **Active Badges**: Extracts `event_emitted` truthiness for dynamic badge rendering (`ALERT ACTIVE`).
- **Color-Coded Delivery States**: Emerald (`SENT`), Amber (`PENDING/RETRYING`), Red (`FAILED`).
- **Error Tooltips**: Hovers to reveal sanitized delivery network faults.
- **Rule**: Does not recalculate logic on the client; trusts backend payloads implicitly.

---

### 10. Historical Ledger Service
- **Endpoint**: `GET /api/v1/alerts/history/{target_id}`
- **Persistence**: Append-only immutable log of every trigger, escalation, and recovery for a specific location.
- **Pagination**: Implements fast limit/offset cursor paging.

---

### 11. Mode Isolation & Security
- **`TEST` Mode**: Forces the `MockTelegramProvider`, generating a `DeliveryRecord` natively without issuing external HTTP requests. Crucial for isolated pytest CI environments.
- **`REAL` Mode**: Uses `httpx.AsyncClient` securely. Drops responses safely if connection terminates.
- **Redaction**: HTTP errors automatically strip Authorization and Token headers from exception stacks.

---

### 12. Limitations & Operational Guidelines
- **System Boundaries**: The API does not handle bidirectional interaction; the Telegram integration is one-way broadcast only. 
- **Storage**: The `DeliveryTracker` and `AlertHistoryService` run natively in-memory via threading locks. Restarting the FastAPI application clears historical states. Production deployments should attach a SQLite or PostgreSQL adapter.
- **Limits**: Maximum 30 messages/second as enforced by Telegram Global guidelines.

---
*Generated by the Landslide Early Warning System Architecture Agent*
