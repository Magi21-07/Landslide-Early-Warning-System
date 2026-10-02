# Running the Landslide Early Warning System Dashboard

This guide explains how to start both the Phase-6 FastAPI backend and the Phase-7 Vite frontend.

## 1. Start the Backend (Terminal 1)
Open a terminal, activate your virtual environment, and navigate to the project root. Run:
```bash
uvicorn src.api.main:app --reload
```
The backend will run on `http://localhost:8000`.

## 2. Start the Frontend (Terminal 2)
Open a new terminal and navigate to the `frontend` directory. Run:
```bash
cd frontend
npm run dev
```

## 3. View the Dashboard
Open your local browser and navigate to:
**http://localhost:5173**
