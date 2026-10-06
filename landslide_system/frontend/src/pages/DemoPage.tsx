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

  let riskColor = 'text-[#38A169]';
  let riskBg = 'bg-[#172331]/85 backdrop-blur-md border border-[#526D82]/50 rounded-2xl shadow-xl';
  if (riskLevel === 'MODERATE') {
    riskColor = 'text-[#E6A23C]';
    riskBg = 'bg-[#314A5E]/90 backdrop-blur-md border-[#d97706] bg-amber-950/20';
  } else if (riskLevel === 'HIGH') {
    riskColor = 'text-[#D94B4B]';
    riskBg = 'bg-[#314A5E]/90 backdrop-blur-md border-[#dc2626] bg-red-950/20';
  } else if (riskLevel === 'CRITICAL') {
    riskColor = 'text-[#D94B4B]';
    riskBg = 'bg-[#314A5E]/90 backdrop-blur-md border-[#dc2626] bg-red-950/20';
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
    <div className="flex flex-col h-screen w-full bg-[#172331] font-['IBM_Plex_Mono',monospace] text-[#F2F7FA] antialiased selection:bg-blue-900 selection:text-[#F2F7FA] relative">
      {/* Himalayan Background Overlay Layer */}
      <div 
        className="fixed inset-0 bg-cover bg-center bg-no-repeat opacity-40 pointer-events-none z-0 mix-blend-luminosity"
        style={{ backgroundImage: "url('/images/himalayas.jpg')" }}
      />
      {/* Dark Vignette / Radial Gradient Overlay to ensure full text readability */}
      <div className="fixed inset-0 bg-gradient-to-b from-[#172331]/80 via-[#172331]/60 to-[#172331]/90 pointer-events-none z-0" />

      {/* Header Bar */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-[#526D82] bg-[#172331]/85 backdrop-blur-md border-b border-[#526D82]/50 relative z-10">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-[#BFD5E2] hover:text-[#F2F7FA] transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <h1 className="text-lg font-bold text-[#F2F7FA] font-['Sora',sans-serif] flex items-center gap-2">
            <Zap className="w-5 h-5 text-[#E6A23C]" /> Interactive Scenario Simulator
          </h1>
        </div>
        <div>
          {loading ? (
            <span className="bg-blue-500/20 text-blue-400 border border-blue-500/30 px-3 py-1 rounded text-xs font-['IBM_Plex_Mono',monospace] font-bold tracking-widest uppercase flex items-center gap-2">
              <span className="w-2 h-2 rounded-none bg-blue-400 animate-pulse"></span>
              EVALUATING...
            </span>
          ) : (
            <span className="bg-amber-950/200/20 text-[#E6A23C] border border-amber-500/30 px-3 py-1 rounded text-xs font-['IBM_Plex_Mono',monospace] font-bold tracking-widest uppercase">
              SANDBOX ISOLATED
            </span>
          )}
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden relative z-10">
        {/* Left Control Panel */}
        <aside className="w-1/3 min-w-[320px] max-w-[400px] bg-[#172331]/85 backdrop-blur-md border-r border-[#526D82]/50 p-6 flex flex-col gap-8 overflow-y-auto scrollbar-thin scrollbar-thumb-[#282d37] scrollbar-track-[#0b0d10]">
          <div>
            <h2 className="text-xs uppercase tracking-[0.2em] text-[#BFD5E2] mb-4 border-b border-[#526D82] pb-2">
              Environmental Parameters
            </h2>

            {/* Sliders */}
            <div className="flex flex-col gap-6">
              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="text-xs font-bold text-[#F2F7FA]">3-Day Cumulative Rainfall</label>
                  <span className="text-xs font-['IBM_Plex_Mono',monospace] text-blue-400 font-bold">{rainfall} mm</span>
                </div>
                <input
                  type="range" min="0" max="300" step="1"
                  value={rainfall} onChange={(e) => { setRainfall(Number(e.target.value)); setActivePreset(null); }}
                  className="w-full accent-[#3B82A0] cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="text-xs font-bold text-[#F2F7FA]">Soil Moisture Saturation</label>
                  <span className="text-xs font-['IBM_Plex_Mono',monospace] text-[#38A169] font-bold">{moisture} %</span>
                </div>
                <input
                  type="range" min="0" max="100" step="1"
                  value={moisture} onChange={(e) => { setMoisture(Number(e.target.value)); setActivePreset(null); }}
                  className="w-full accent-emerald-500 cursor-pointer"
                />
              </div>

              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="text-xs font-bold text-[#F2F7FA]">Terrain Slope Angle</label>
                  <span className="text-xs font-['IBM_Plex_Mono',monospace] text-[#E6A23C] font-bold">{slope}°</span>
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
            <h2 className="text-xs uppercase tracking-[0.2em] text-[#BFD5E2] mb-4 border-b border-[#526D82] pb-2">
              Presets
            </h2>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => handlePreset('Normal Weather', 10, 20, 15, false)}
                className={`text-xs font-bold py-2 px-2 transition-colors ${activePreset === 'Normal Weather' ? "border-2 border-[#3B82A0] bg-[#3B82A0]/20 text-[#FFFFFF] shadow-[0_0_12px_rgba(59,130,160,0.4)] rounded-lg font-['Inter',sans-serif]" : "bg-[#314A5E] hover:bg-[#282d37] border border-[#526D82] text-[#F2F7FA]"}`}
              >Normal Weather</button>
              <button
                onClick={() => handlePreset('Heavy Monsoon', 140, 65, 35, false)}
                className={`text-xs font-bold py-2 px-2 transition-colors ${activePreset === 'Heavy Monsoon' ? "border-2 border-[#3B82A0] bg-[#3B82A0]/20 text-[#FFFFFF] shadow-[0_0_12px_rgba(59,130,160,0.4)] rounded-lg font-['Inter',sans-serif]" : "bg-[#314A5E] hover:bg-[#282d37] border border-[#526D82] text-[#F2F7FA]"}`}
              >Heavy Monsoon Warning</button>
              <button
                onClick={() => handlePreset('Cloudburst Emergency', 260, 90, 48, true)}
                className={`text-xs font-bold py-2 px-2 transition-colors ${activePreset === 'Cloudburst Emergency' ? "border-2 border-[#3B82A0] bg-[#3B82A0]/20 text-[#FFFFFF] shadow-[0_0_12px_rgba(59,130,160,0.4)] rounded-lg font-['Inter',sans-serif]" : "bg-[#314A5E] hover:bg-[#282d37] border border-[#526D82] text-[#F2F7FA]"}`}
              >Cloudburst Emergency</button>
              <button
                onClick={() => handlePreset('Shimla 2023 Replay', 195, 85, 42, true)}
                className={`text-xs font-bold py-2 px-2 transition-colors ${activePreset === 'Shimla 2023 Replay' ? "border-2 border-[#3B82A0] bg-[#3B82A0]/20 text-[#FFFFFF] shadow-[0_0_12px_rgba(59,130,160,0.4)] rounded-lg font-['Inter',sans-serif]" : "bg-[#314A5E] hover:bg-[#282d37] border border-[#526D82] text-[#F2F7FA]"}`}
              >Shimla 2023 Replay</button>
            </div>
          </div>

          <div>
            <h2 className="text-xs uppercase tracking-[0.2em] text-[#BFD5E2] mb-4 border-b border-[#526D82] pb-2">
              Alert Policies
            </h2>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={enableTelegram}
                onChange={(e) => { setEnableTelegram(e.target.checked); setActivePreset(null); }}
                className="w-4 h-4 accent-[#3B82A0] bg-[#314A5E] border-[#526D82] rounded"
              />
              <span className="text-sm font-bold text-[#F2F7FA]">Enable Live Telegram Alert</span>
            </label>
          </div>
        </aside>

        {/* Right Panel (Outputs Placeholder) */}
        <main className="flex-1 bg-transparent p-8 overflow-y-auto flex flex-col gap-6 scrollbar-thin scrollbar-thumb-[#282d37] scrollbar-track-[#0b0d10] relative">
          {error && (
            <div className="absolute top-4 right-8 bg-red-900/40 border border-red-500 text-red-200 px-3 py-1.5 rounded flex items-center gap-2 text-xs font-bold shadow-lg z-10">
              <AlertTriangle className="w-4 h-4" /> API Timeout/Error
            </div>
          )}

          <div className="grid grid-cols-2 gap-6">
            <div className={`border p-6 flex flex-col items-center justify-center min-h-[200px] transition-all duration-300 ease-in-out ${riskBg} rounded-none`}>
              <div className="text-xs uppercase tracking-[0.2em] text-[#BFD5E2] mb-2">Risk Level</div>
              <div className={`text-5xl font-black tracking-wider mb-2 transition-colors duration-300 ${riskColor}`}>
                {riskLevel}
              </div>
              <div className="text-xl font-['IBM_Plex_Mono',monospace] text-[#F2F7FA]">
                Score: {(probability * 100).toFixed(1)}%
              </div>
            </div>

            <div className="bg-[#172331]/85 backdrop-blur-md border border-[#526D82]/50 p-6 rounded-2xl shadow-xl">
              <div className="text-xs uppercase tracking-[0.2em] text-[#BFD5E2] mb-4">Top SHAP Risk Drivers</div>
              <div className="flex flex-col gap-3 h-[180px] overflow-y-auto scrollbar-thin scrollbar-thumb-[#282d37] pr-2">
                {simData?.risk_response?.top_risk_factors ? (
                  simData.risk_response.top_risk_factors.slice(0, 5).map((f, i) => (
                    <div key={i} className="flex flex-col gap-1">
                      <div className="flex justify-between text-[10px] font-['IBM_Plex_Mono',monospace] font-bold text-[#F2F7FA]">
                        <span>{f.factor}</span>
                        <span className={f.contribution.startsWith('+') ? 'text-[#D94B4B]' : 'text-[#38A169]'}>
                          {f.contribution}
                        </span>
                      </div>
                      <div className="w-full bg-[#314A5E] h-1.5 rounded-none overflow-hidden">
                        <div
                          className={`h-full ${f.contribution.startsWith('+') ? 'bg-red-950/200' : 'bg-[#38A169]'}`}
                          style={{ width: `${Math.min(100, parseFloat(f.contribution.replace(/[^\d.]/g, '')))}%` }}
                        ></div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="flex items-center justify-center h-full text-slate-600 font-['IBM_Plex_Mono',monospace] text-sm border-2 border-dashed border-[#526D82] p-4">
                    [ SHAP Chart Loading... ]
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="bg-[#172331]/85 backdrop-blur-md border border-[#526D82]/50 p-6 rounded-2xl shadow-xl flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-xs uppercase tracking-[0.2em] text-[#BFD5E2] mb-1">Telegram Delivery Status</span>
              <span className="text-xs text-[#BFD5E2]">Live dispatch status for the current simulation run.</span>
            </div>
            {(() => {
              const tgStatus = simData?.delivery_status?.dispatched_async ? 'SENT' : (simData?.alert_summary?.telegram_enabled ? 'PENDING' : (simData?.alert_summary ? 'SUPPRESSED' : 'NOT_DISPATCHED'));
              let badgeColor = 'bg-[#314A5E] text-[#BFD5E2] border-[#526D82]';
              if (tgStatus === 'SENT') badgeColor = 'bg-blue-900/40 text-blue-400 border-blue-700/50';
              if (tgStatus === 'SUPPRESSED') badgeColor = 'bg-amber-900/40 text-[#E6A23C] border-amber-700/50';
              return (
                <span className={`border px-3 py-1 rounded text-xs font-['IBM_Plex_Mono',monospace] font-bold tracking-widest ${badgeColor}`}>
                  {tgStatus}
                </span>
              );
            })()}
          </div>

          {/* Telegram QR Code Block */}
          <div className="mt-auto bg-[#172331]/85 backdrop-blur-md border border-[#526D82]/50 p-6 rounded-2xl shadow-xl flex items-center gap-6">
            <div className="w-24 h-24 bg-white p-2 shrink-0">
              <div className="w-full h-full bg-zinc-200 border border-zinc-300 flex items-center justify-center">
                <span className="text-[10px] text-[#BFD5E2] font-bold">QR CODE</span>
              </div>
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-200 mb-1">Receive Live Alerts</h3>
              <p className="text-sm text-[#BFD5E2] leading-relaxed max-w-md">
                Scan with your mobile device to join the alert broadcast channel before triggering 'Cloudburst Emergency' or 'Shimla 2023 Replay'.
              </p>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
