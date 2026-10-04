import { useState, useEffect } from 'react';
import { ArrowLeft, Zap, AlertTriangle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { simulateRiskScenario, type DemoSimulationResponse } from '../services/api';

export default function DemoPage() {
  const [rainfall, setRainfall] = useState<number>(25.0);
  const [moisture, setMoisture] = useState<number>(35.0);
  const [slope, setSlope] = useState<number>(20.0);
  const [enableTelegram, setEnableTelegram] = useState<boolean>(false);

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<boolean>(false);
  const [simData, setSimData] = useState<DemoSimulationResponse | null>(null);
  const [activePreset, setActivePreset] = useState<string | null>(null);

  const runSimulation = async (r: number, m: number, s: number, tg: boolean) => {
    setLoading(true);
    setError(false);
    try {
      const payload = {
        target_id: 'DEMO-001',
        rainfall_3d_mm: r,
        soil_moisture_pct: m,
        terrain_slope: s,
        trigger_telegram: tg,
      };
      const data = await simulateRiskScenario(payload);
      setSimData(data);
    } catch (err) {
      console.error('Simulation error', err);
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const handler = setTimeout(() => {
      runSimulation(rainfall, moisture, slope, enableTelegram);
    }, 500);
    return () => clearTimeout(handler);
  }, [rainfall, moisture, slope, enableTelegram]);

  const riskLevel = simData?.risk_response?.risk_level || 'LOW';
  const probability = simData?.risk_response?.probability || 0;
  
  let riskColor = 'text-emerald-500';
  let riskBg = 'bg-slate-900 border-slate-700';
  if (riskLevel === 'MODERATE') {
    riskColor = 'text-amber-500';
    riskBg = 'bg-amber-950/20 border-amber-900/50';
  } else if (riskLevel === 'HIGH') {
    riskColor = 'text-orange-500';
    riskBg = 'bg-orange-950/20 border-orange-900/50';
  } else if (riskLevel === 'CRITICAL') {
    riskColor = 'text-rose-500';
    riskBg = 'bg-rose-950/20 border-rose-900/50';
  }

  const handlePreset = (name: string, r: number, m: number, s: number, tg: boolean) => {
    setActivePreset(name);
    setRainfall(r);
    setMoisture(m);
    setSlope(s);
    setEnableTelegram(tg);
    runSimulation(r, m, s, tg);
  };

  return (
    <div className="flex flex-col h-screen w-full bg-slate-950 font-sans text-slate-300 antialiased selection:bg-blue-900 selection:text-white">
      {/* Header Bar */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-slate-800 bg-slate-900">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-slate-400 hover:text-white transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <h1 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-500" /> Interactive Scenario Simulator
          </h1>
        </div>
        <div>
          {loading ? (
            <span className="bg-blue-500/20 text-blue-400 border border-blue-500/30 px-3 py-1 rounded text-xs font-mono font-bold tracking-widest uppercase flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse"></span>
              EVALUATING...
            </span>
          ) : (
            <span className="bg-amber-500/20 text-amber-500 border border-amber-500/30 px-3 py-1 rounded text-xs font-mono font-bold tracking-widest uppercase">
              SANDBOX ISOLATED
            </span>
          )}
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Left Control Panel */}
        <aside className="w-1/3 min-w-[320px] max-w-[400px] bg-slate-900 border-r border-slate-700 p-6 flex flex-col gap-8 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-900">
          <div>
            <h2 className="text-sm font-mono font-bold text-slate-400 uppercase tracking-widest mb-4 border-b border-slate-700 pb-2">
              Environmental Parameters
            </h2>
            
            {/* Sliders */}
            <div className="flex flex-col gap-6">
              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="text-xs font-bold text-slate-300">3-Day Cumulative Rainfall</label>
                  <span className="text-xs font-mono text-blue-400 font-bold">{rainfall} mm</span>
                </div>
                <input 
                  type="range" min="0" max="300" step="1" 
                  value={rainfall} onChange={(e) => { setRainfall(Number(e.target.value)); setActivePreset(null); }}
                  className="w-full accent-blue-500 cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="text-xs font-bold text-slate-300">Soil Moisture Saturation</label>
                  <span className="text-xs font-mono text-emerald-400 font-bold">{moisture} %</span>
                </div>
                <input 
                  type="range" min="0" max="100" step="1" 
                  value={moisture} onChange={(e) => { setMoisture(Number(e.target.value)); setActivePreset(null); }}
                  className="w-full accent-emerald-500 cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="text-xs font-bold text-slate-300">Terrain Slope Angle</label>
                  <span className="text-xs font-mono text-amber-400 font-bold">{slope}°</span>
                </div>
                <input 
                  type="range" min="0" max="60" step="1" 
                  value={slope} onChange={(e) => { setSlope(Number(e.target.value)); setActivePreset(null); }}
                  className="w-full accent-amber-500 cursor-pointer"
                />
              </div>
            </div>
          </div>

          <div>
            <h2 className="text-sm font-mono font-bold text-slate-400 uppercase tracking-widest mb-4 border-b border-slate-700 pb-2">
              Presets
            </h2>
            <div className="grid grid-cols-2 gap-2">
              <button 
                onClick={() => handlePreset('Normal Weather', 10, 20, 15, false)} 
                className={`text-xs font-bold py-2 px-2 transition-colors ${activePreset === 'Normal Weather' ? 'ring-2 ring-cyan-500 bg-slate-800 text-slate-100' : 'bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-300'}`}
              >Normal Weather</button>
              <button 
                onClick={() => handlePreset('Heavy Monsoon', 140, 65, 35, false)} 
                className={`text-xs font-bold py-2 px-2 transition-colors ${activePreset === 'Heavy Monsoon' ? 'ring-2 ring-cyan-500 bg-slate-800 text-slate-100' : 'bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-300'}`}
              >Heavy Monsoon Warning</button>
              <button 
                onClick={() => handlePreset('Cloudburst Emergency', 260, 90, 48, true)} 
                className={`text-xs font-bold py-2 px-2 transition-colors ${activePreset === 'Cloudburst Emergency' ? 'ring-2 ring-cyan-500 bg-slate-800 text-slate-100' : 'bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-300'}`}
              >Cloudburst Emergency</button>
              <button 
                onClick={() => handlePreset('Shimla 2023 Replay', 195, 85, 42, true)} 
                className={`text-xs font-bold py-2 px-2 transition-colors ${activePreset === 'Shimla 2023 Replay' ? 'ring-2 ring-cyan-500 bg-slate-800 text-slate-100' : 'bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-300'}`}
              >Shimla 2023 Replay</button>
            </div>
          </div>

          <div>
            <h2 className="text-sm font-mono font-bold text-slate-400 uppercase tracking-widest mb-4 border-b border-slate-700 pb-2">
              Alert Policies
            </h2>
            <label className="flex items-center gap-3 cursor-pointer">
              <input 
                type="checkbox" 
                checked={enableTelegram} 
                onChange={(e) => { setEnableTelegram(e.target.checked); setActivePreset(null); }}
                className="w-4 h-4 accent-blue-500 bg-slate-800 border-slate-600 rounded"
              />
              <span className="text-sm font-bold text-slate-300">Enable Live Telegram Alert</span>
            </label>
          </div>
        </aside>

        {/* Right Panel (Outputs Placeholder) */}
        <main className="flex-1 bg-slate-800 p-8 overflow-y-auto flex flex-col gap-6 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-800 relative">
          {error && (
            <div className="absolute top-4 right-8 bg-red-900/40 border border-red-500 text-red-200 px-3 py-1.5 rounded flex items-center gap-2 text-xs font-bold shadow-lg z-10">
              <AlertTriangle className="w-4 h-4" /> API Timeout/Error
            </div>
          )}
          
          <div className="grid grid-cols-2 gap-6">
            <div className={`border rounded-lg p-6 flex flex-col items-center justify-center min-h-[200px] transition-all duration-300 ease-in-out ${riskBg}`}>
              <div className="text-sm font-mono font-bold text-slate-400 uppercase tracking-widest mb-2">Risk Level</div>
              <div className={`text-5xl font-black tracking-wider mb-2 transition-colors duration-300 ${riskColor}`}>
                {riskLevel}
              </div>
              <div className="text-xl font-mono text-slate-300">
                Score: {(probability * 100).toFixed(1)}%
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-700 rounded-lg p-6">
              <div className="text-sm font-mono font-bold text-slate-400 uppercase tracking-widest mb-4">Top SHAP Risk Drivers</div>
              <div className="flex flex-col gap-3 h-[180px] overflow-y-auto scrollbar-thin scrollbar-thumb-slate-700 pr-2">
                {simData?.risk_response?.top_risk_factors ? (
                  simData.risk_response.top_risk_factors.slice(0, 5).map((f, i) => (
                    <div key={i} className="flex flex-col gap-1">
                      <div className="flex justify-between text-[10px] font-mono font-bold text-slate-300">
                        <span>{f.factor}</span>
                        <span className={f.contribution.startsWith('+') ? 'text-red-400' : 'text-emerald-400'}>
                          {f.contribution}
                        </span>
                      </div>
                      <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                        <div 
                          className={`h-full ${f.contribution.startsWith('+') ? 'bg-red-500' : 'bg-emerald-500'}`} 
                          style={{ width: `${Math.min(100, parseFloat(f.contribution.replace(/[^\d.]/g, '')))}%` }}
                        ></div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="flex items-center justify-center h-full text-slate-600 font-mono text-sm border-2 border-dashed border-slate-700 p-4">
                    [ SHAP Chart Loading... ]
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-sm font-mono font-bold text-slate-400 uppercase tracking-widest mb-1">Telegram Delivery Status</span>
              <span className="text-xs text-slate-500">Live dispatch status for the current simulation run.</span>
            </div>
            {(() => {
              const tgStatus = simData?.delivery_status?.dispatched_async ? 'SENT' : (simData?.alert_summary?.telegram_enabled ? 'PENDING' : (simData?.alert_summary ? 'SUPPRESSED' : 'NOT_DISPATCHED'));
              let badgeColor = 'bg-slate-800 text-slate-400 border-slate-600';
              if (tgStatus === 'SENT') badgeColor = 'bg-blue-900/40 text-blue-400 border-blue-700/50';
              if (tgStatus === 'SUPPRESSED') badgeColor = 'bg-amber-900/40 text-amber-400 border-amber-700/50';
              return (
                <span className={`border px-3 py-1 rounded text-xs font-mono font-bold tracking-widest ${badgeColor}`}>
                  {tgStatus}
                </span>
              );
            })()}
          </div>

          {/* Telegram QR Code Block */}
          <div className="mt-auto bg-slate-900/50 border border-slate-700 rounded-lg p-6 flex items-center gap-6">
            <div className="w-24 h-24 bg-white p-2 shrink-0">
              <div className="w-full h-full bg-zinc-200 border border-zinc-300 flex items-center justify-center">
                <span className="text-[10px] text-zinc-500 font-bold">QR CODE</span>
              </div>
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-200 mb-1">Receive Live Alerts</h3>
              <p className="text-sm text-slate-400 leading-relaxed max-w-md">
                Scan with your mobile device to join the alert broadcast channel before triggering 'Cloudburst Emergency' or 'Shimla 2023 Replay'.
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
