import { Info, MapPin, CloudRain, ShieldAlert, ActivitySquare, AlertTriangle, Database, BarChart3, Activity } from 'lucide-react';
import { getRiskStyle } from '../utils/riskStyles';
import { RainfallChart } from './RainfallChart';

interface DetailsPanelProps {
  location?: any;
  loading?: boolean;
}

export const DetailsPanel = ({ location, loading }: DetailsPanelProps) => {
  if (!location) {
    return (
      <section className="w-80 shrink-0 flex flex-col bg-zinc-950 border-r border-zinc-800 h-full overflow-y-auto relative z-10 font-mono">
        <div className="flex-1 flex flex-col items-center justify-center text-zinc-600 text-[10px] uppercase tracking-widest p-6 text-center">
          <Info className="w-8 h-8 mb-3 opacity-20" />
          <p>AWAITING TARGET SELECTION...</p>
        </div>
      </section>
    );
  }

  const riskStr = location.dynamic_risk || location.risk_level || location.risk || location.properties?.dynamic_risk || location.properties?.risk_level || location.properties?.risk || 'UNKNOWN';
  const riskStyle = getRiskStyle(riskStr);
  const explanations: string[] = Array.isArray(location.explanation) 
    ? location.explanation 
    : location.explanation 
      ? [location.explanation] 
      : [];
      
  const isStale = location.is_stale === true || location.data_age_hours > 24;

  return (
    <section className="w-80 shrink-0 flex flex-col bg-zinc-950 border-r border-zinc-800 h-full overflow-y-auto scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-zinc-950 relative z-10">
      <div className="flex-col flex">
        
        {/* 1. Location Info */}
        <div className="p-3 border-b border-zinc-800 bg-zinc-900 sticky top-0 z-20">
          <h2 className="text-[11px] font-mono font-bold text-zinc-200 break-words flex items-start gap-1.5 uppercase">
            <MapPin className="w-3.5 h-3.5 text-blue-500 shrink-0" />
            {location.name || location.location_id || 'UNKNOWN_TGT'}
          </h2>
          <div className="flex items-center gap-3 mt-1.5 ml-5 text-[9px] text-zinc-500 font-mono uppercase tracking-widest">
            <span>LAT:{location.latitude !== undefined ? Number(location.latitude).toFixed(4) : '--'}</span>
            <span>LON:{location.longitude !== undefined ? Number(location.longitude).toFixed(4) : '--'}</span>
            {loading && <span className="text-blue-500 animate-pulse">FETCHING LIVE DATA...</span>}
          </div>
        </div>

        {/* 5. Dynamic Risk (Promoted for visibility) */}
        <div className="p-3 border-b border-zinc-800 bg-zinc-950/50">
          <div className="flex items-center gap-1.5 mb-2 text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">
            <ShieldAlert className="w-3 h-3" />
            EVAL: DYNAMIC RISK
          </div>
          <div className="p-2.5 border border-zinc-800 bg-black flex items-center justify-between rounded-none">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-none" style={{ backgroundColor: riskStyle.markerColor, boxShadow: `0 0 5px ${riskStyle.markerColor}` }}></span>
              <span className="font-mono font-bold text-[11px] tracking-widest uppercase" style={{ color: riskStyle.markerColor }}>{riskStyle.id}</span>
            </div>
            {location.risk_score !== undefined && (
              <span className="text-[10px] font-mono font-bold text-zinc-400">
                SC:{Number(location.risk_score).toFixed(2)}
              </span>
            )}
          </div>
        </div>

        {isStale && (
          <div className="px-3 py-1.5 bg-red-950 border-b border-red-900 text-red-500 flex items-center gap-2 text-[9px] font-mono font-bold tracking-widest uppercase">
            <AlertTriangle className="w-3 h-3" />
            WARNING: STALE DATA DETECTED
          </div>
        )}

        {/* 5b. Telegram Alert & Delivery Status */}
        <div className="p-3 border-b border-zinc-800">
          <div className="flex items-center gap-1.5 mb-2 text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">
            <ShieldAlert className="w-3 h-3" />
            SYS: ALERT & DELIVERY STATUS
          </div>
          <div className="bg-black p-2 border border-zinc-800 flex flex-col gap-2 text-[10px] font-mono">
            {(() => {
              const summary = location.alert_summary;
              const delivery = location.delivery_status;
              
              const alertStatusLabel = summary?.current_risk_level ? `${summary.current_risk_level} ${summary.current_risk_level === 'CRITICAL' ? 'EMERGENCY' : 'WARNING'}` : 'Not Available';
              const triggerReason = summary?.trigger_reason || 'Not Available';
              const triggeredAt = summary?.triggered_at ? `${new Date(summary.triggered_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC', hour12: false })} UTC` : '--';
              
              const delStatus = delivery?.status || 'NOT_SENT';
              const lastAttempt = delivery?.last_attempt_at ? `${new Date(delivery.last_attempt_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC', hour12: false })} UTC` : '--';
              const errorMsg = delivery?.error_message || '';
              
              let badgeClasses = 'bg-slate-800 text-slate-400 border-slate-700';
              if (delStatus === 'SENT') badgeClasses = 'bg-emerald-950 text-emerald-400 border-emerald-800';
              else if (delStatus === 'PENDING' || delStatus === 'RETRYING') badgeClasses = 'bg-amber-950 text-amber-400 border-amber-800';
              else if (delStatus === 'FAILED') badgeClasses = 'bg-red-950 text-red-400 border-red-800';

              return (
                <>
                  <div className="flex justify-between border-b border-zinc-900 pb-1.5">
                    <span className="text-zinc-600">SEVERITY</span>
                    <span className="text-zinc-300 font-bold">{alertStatusLabel}</span>
                  </div>
                  <div className="flex justify-between border-b border-zinc-900 pb-1.5">
                    <span className="text-zinc-600">REASON</span>
                    <span className="text-zinc-300 text-right max-w-[180px] truncate" title={triggerReason}>{triggerReason}</span>
                  </div>
                  <div className="flex justify-between border-b border-zinc-900 pb-1.5">
                    <span className="text-zinc-600">TRIGGERED AT</span>
                    <span className="text-zinc-300">{triggeredAt}</span>
                  </div>
                  <div className="flex justify-between border-b border-zinc-900 pb-1.5 items-center">
                    <span className="text-zinc-600">TELEGRAM</span>
                    <span className={`px-1.5 py-0.5 border ${badgeClasses} font-bold uppercase`}>
                      {delStatus}
                    </span>
                  </div>
                  <div className="flex justify-between pt-0.5 items-center">
                    <span className="text-zinc-600">LAST ATTEMPT</span>
                    <div className="flex items-center gap-1">
                      <span className="text-zinc-300">{lastAttempt}</span>
                      {delStatus === 'FAILED' && errorMsg && (
                        <div className="group relative flex items-center">
                          <Info className="w-3 h-3 text-red-500 cursor-help" />
                          <div className="absolute right-0 bottom-full mb-1 hidden group-hover:block w-48 p-1.5 bg-zinc-900 border border-zinc-700 text-zinc-300 text-[9px] z-50 rounded-none shadow-lg break-words">
                            {errorMsg}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </>
              );
            })()}
          </div>
        </div>
        
        {/* 2. Static Susceptibility */}
        <div className="p-3 border-b border-zinc-800">
          <div className="flex items-center gap-1.5 mb-2 text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">
            <ActivitySquare className="w-3 h-3" />
            EVAL: STATIC SUSCEPTIBILITY
          </div>
          <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
            <div className="bg-black p-2 border border-zinc-800 flex flex-col gap-0.5">
              <span className="text-zinc-600 uppercase tracking-widest text-[8px]">Probability</span>
              <span className="font-medium text-zinc-300">
                {location.probability !== undefined ? Number(location.probability).toFixed(3) : 
                 (location.susceptibility_probability !== undefined ? Number(location.susceptibility_probability).toFixed(3) : 'N/A')}
              </span>
            </div>
            <div className="bg-black p-2 border border-zinc-800 flex flex-col gap-0.5">
              <span className="text-zinc-600 uppercase tracking-widest text-[8px]">Class</span>
              <span className="font-medium text-zinc-300 uppercase">
                {location.susceptibility_class || 'UNKNOWN'}
              </span>
            </div>
          </div>
        </div>

        {/* 3 & 4. Recent Rainfall & Chart */}
        <div className="p-3 border-b border-zinc-800">
          <div className="flex items-center gap-1.5 mb-2 text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">
            <CloudRain className="w-3 h-3" />
            DATA: RAINFALL (15-DAY)
          </div>
          <div className="grid grid-cols-4 gap-1 text-center text-[10px] font-mono mb-3">
            <div className="bg-black border border-zinc-800 p-1.5 flex flex-col gap-0.5">
              <span className="text-[8px] text-zinc-600 uppercase tracking-widest">1D</span>
              <span className="text-zinc-300">{location.rainfall_1d !== undefined ? `${location.rainfall_1d}` : '-'}</span>
            </div>
            <div className="bg-black border border-zinc-800 p-1.5 flex flex-col gap-0.5">
              <span className="text-[8px] text-zinc-600 uppercase tracking-widest">3D</span>
              <span className="text-zinc-300">{location.rainfall_3d !== undefined ? `${location.rainfall_3d}` : '-'}</span>
            </div>
            <div className="bg-black border border-zinc-800 p-1.5 flex flex-col gap-0.5">
              <span className="text-[8px] text-zinc-600 uppercase tracking-widest">7D</span>
              <span className="text-zinc-300">{location.rainfall_7d !== undefined ? `${location.rainfall_7d}` : '-'}</span>
            </div>
            <div className="bg-black border border-zinc-800 p-1.5 flex flex-col gap-0.5">
              <span className="text-[8px] text-zinc-600 uppercase tracking-widest">15D</span>
              <span className="text-zinc-300">{location.rainfall_15d !== undefined ? `${location.rainfall_15d}` : '-'}</span>
            </div>
          </div>

          <div className="grayscale opacity-90 contrast-125">
            <RainfallChart 
              latitude={location.latitude} 
              longitude={location.longitude} 
              triggerState={location.trigger_state} 
            />
          </div>
        </div>

        {/* 6. Data Status */}
        <div className="p-3 border-b border-zinc-800">
          <div className="flex items-center gap-1.5 mb-2 text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">
            <Database className="w-3 h-3" />
            SYS: DATA INTEGRITY
          </div>
          <div className="flex flex-col gap-1 text-[10px] font-mono text-zinc-400 bg-black p-2 border border-zinc-800">
            <div className="flex justify-between border-b border-zinc-900 pb-1">
              <span className="text-zinc-600">SOURCE</span>
              <span className="uppercase text-zinc-300">{location.source || 'CHIRPS'}</span>
            </div>
            <div className="flex justify-between border-b border-zinc-900 py-1">
              <span className="text-zinc-600">OBS DATE</span>
              <span className="text-zinc-300">{location.observation_date || '--'}</span>
            </div>
            <div className="flex justify-between pt-1">
              <span className="text-zinc-600">STATE</span>
              <span className="flex items-center gap-1">
                {isStale ? (
                   <span className="text-red-500 font-bold">STALE</span>
                ) : (
                   <span className="text-emerald-500 font-bold">NOMINAL</span>
                )}
              </span>
            </div>
          </div>
        </div>

        {/* 7. Risk Factor Breakdown (SHAP) */}
        {location.top_risk_factors && location.top_risk_factors.length > 0 && (
          <div className="p-3 border-b border-zinc-800">
            <div className="flex items-center gap-1.5 mb-2 text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">
              <BarChart3 className="w-3 h-3" />
              EVAL: TOP RISK FACTORS (SHAP)
            </div>
            <div className="flex flex-col gap-2">
              {location.top_risk_factors.slice(0, 5).map((rf: any, idx: number) => {
                const isPositive = rf.contribution.startsWith('+');
                const val = parseFloat(rf.contribution.replace(/[+%\\-]/g, ''));
                return (
                  <div key={idx} className="flex flex-col gap-1">
                    <div className="flex justify-between items-end text-[9px] font-mono uppercase tracking-widest">
                      <span className="text-zinc-300 truncate pr-2">{rf.factor}</span>
                      <span className={isPositive ? "text-red-400 font-bold" : "text-emerald-400 font-bold"}>{rf.contribution}</span>
                    </div>
                    <div className="h-1 bg-zinc-900 w-full overflow-hidden">
                      <div 
                        className={`h-full ${isPositive ? "bg-red-500" : "bg-emerald-500"}`} 
                        style={{ width: `${Math.min(val, 100)}%` }}
                      ></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 8. Dynamic Mini-Metrics */}
        <div className="p-3 border-b border-zinc-800">
          <div className="flex items-center gap-1.5 mb-2 text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">
            <Activity className="w-3 h-3" />
            EVAL: SATELLITE & SPATIAL METRICS
          </div>
          <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
            <div className="bg-black p-2 border border-zinc-800 flex flex-col gap-0.5">
              <span className="text-zinc-600 uppercase tracking-widest text-[8px]">NDVI</span>
              <span className="font-medium text-zinc-300">
                {location.ndvi !== undefined && location.ndvi !== null ? Number(location.ndvi).toFixed(3) : 'UNAVAILABLE'}
              </span>
            </div>
            <div className="bg-black p-2 border border-zinc-800 flex flex-col gap-0.5">
              <span className="text-zinc-600 uppercase tracking-widest text-[8px]">SAR Moisture Proxy</span>
              <span className="font-medium text-zinc-300">
                {location.sar_moisture_proxy !== undefined && location.sar_moisture_proxy !== null ? `${Number(location.sar_moisture_proxy).toFixed(1)} dB` : 'UNAVAILABLE'}
              </span>
            </div>
            <div className="bg-black p-2 border border-zinc-800 flex flex-col gap-0.5 col-span-2">
              <span className="text-zinc-600 uppercase tracking-widest text-[8px]">Distance to River</span>
              <span className="font-medium text-zinc-300">
                {location.distance_to_river_m !== undefined && location.distance_to_river_m !== null ? `${Number(location.distance_to_river_m).toFixed(1)} m` : 'UNAVAILABLE'}
              </span>
            </div>
          </div>
        </div>

        {/* 9. Risk Explanation */}
        {explanations.length > 0 && (
          <div className="p-3">
            <div className="flex items-center gap-1.5 mb-2 text-[9px] font-mono font-bold text-zinc-500 uppercase tracking-widest">
              <Info className="w-3 h-3 text-zinc-600" />
              LOG: EVAL FACTORS
            </div>
            <ul className="flex flex-col gap-1.5">
              {explanations.map((exp, idx) => (
                <li key={idx} className="text-[9px] font-mono text-zinc-400 leading-tight bg-black p-2 border-l-2 border-zinc-700">
                  {exp}
                </li>
              ))}
            </ul>
          </div>
        )}
        
      </div>
    </section>
  );
};
