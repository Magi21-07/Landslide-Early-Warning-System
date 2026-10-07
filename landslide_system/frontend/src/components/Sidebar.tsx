import { useState, useMemo } from 'react';
import { Search, MapPin, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';
import { getRiskStyle, getUnifiedRisk } from '../utils/riskStyles';

interface SidebarProps {
  locations: any[];
  selectedLocationId: string | null;
  onSelect: (id: string) => void;
  search: string;
  setSearch: (v: string) => void;
  riskFilter: string;
  setRiskFilter: (v: string) => void;
  onCoordinateSearch: (lat: number, lon: number) => Promise<void>;
}

export const Sidebar = ({ 
  locations, selectedLocationId, onSelect, 
  search, setSearch, riskFilter, setRiskFilter,
  onCoordinateSearch
}: SidebarProps) => {
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [coordError, setCoordError] = useState('');
  const [isSearching, setIsSearching] = useState(false);

  // Strips degree symbols, compass letters, whitespace — keeps only valid float chars
  const sanitizeCoord = (val: string) => val.replace(/[^0-9.-]/g, '');

  const filteredLocations = useMemo(() => {
    return locations.filter((loc) => {
      const matchSearch = (loc.name || loc.id || loc.location_id || '').toLowerCase().includes(search.toLowerCase());
      const locRiskStr = getUnifiedRisk(loc);
      const matchFilter = riskFilter === 'ALL' || locRiskStr.toUpperCase() === riskFilter;
      return matchSearch && matchFilter;
    });
  }, [locations, search, riskFilter]);

  const handleCoordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCoordError('');

    const latNum = parseFloat(sanitizeCoord(lat));
    const lonNum = parseFloat(sanitizeCoord(lon));

    console.log('COORD SEARCH: parsed lat=', latNum, 'lon=', lonNum);

    if (isNaN(latNum) || latNum < -90 || latNum > 90) {
      setCoordError('ERR: LAT RANGE');
      return;
    }
    if (isNaN(lonNum) || lonNum < -180 || lonNum > 180) {
      setCoordError('ERR: LON RANGE');
      return;
    }

    setIsSearching(true);
    try {
      await onCoordinateSearch(latNum, lonNum);
      setLat('');
      setLon('');
    } catch (err: any) {
      console.error('API EVALUATION ERROR:', err?.response?.data || err?.message || err);
      setCoordError('ERR: API FAIL');
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <aside className="w-1/5 shrink-0 flex flex-col bg-[#203447] border-r border-[#BFD5E2]/15 h-full relative z-10">
      <div className="p-3 border-b border-[#BFD5E2]/15 bg-[#203447] flex flex-col gap-2">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-[10px] font-['Inter',sans-serif] font-bold text-[#526D82] uppercase tracking-widest">Target Selection</h3>
          <Link to="/demo" className="flex items-center gap-1.5 px-2 py-1 bg-blue-900/40 hover:bg-blue-800/60 border border-blue-700/50 rounded transition-colors group">
            <Zap className="w-3 h-3 text-[#E6A23C] group-hover:text-amber-300" />
            <span className="text-[9px] font-['Inter',sans-serif] font-bold text-blue-200 uppercase tracking-widest whitespace-nowrap">Live Demo Simulator</span>
          </Link>
        </div>
        
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2 top-1.5 text-[#BFD5E2]" />
          <input 
            type="text" 
            placeholder="Query ID..." 
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-7 pr-7 py-1 text-[11px] font-['Inter',sans-serif] border border-[#BFD5E2]/15 bg-[#172331] text-[#F2F7FA] placeholder-zinc-600 focus:outline-none focus:border-cyan-500 rounded-xl transition-colors"
          />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-2 top-1 text-[#BFD5E2] hover:text-[#F2F7FA] text-xs font-bold">×</button>
          )}
        </div>
        
        <div className="flex items-center justify-between text-[9px] font-['Inter',sans-serif] text-[#BFD5E2] uppercase tracking-widest">
          <span>{filteredLocations.length} Targets</span>
          <select 
            className="bg-transparent text-[#F2F7FA] border-none focus:outline-none cursor-pointer"
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value)}
          >
            <option value="ALL">ALL SEVERITY</option>
            <option value="LOW">LVL: LOW</option>
            <option value="MODERATE">LVL: MOD</option>
            <option value="HIGH">LVL: HIGH</option>
            <option value="CRITICAL">LVL: CRIT</option>
          </select>
        </div>
      </div>
      
      {/* Coordinate Search */}
      <div className="p-2 border-b border-[#BFD5E2]/15 bg-[#203447]">
        <form onSubmit={handleCoordSubmit} className="flex flex-col gap-1.5">
          <div className="flex gap-1">
            <input 
              type="text" placeholder="LAT" value={lat}
              onChange={e => setLat(sanitizeCoord(e.target.value))}
              className="w-full px-1.5 py-1 text-[10px] font-['Inter',sans-serif] border border-[#BFD5E2]/15 bg-[#172331] text-[#F2F7FA] placeholder-zinc-600 focus:outline-none focus:border-cyan-500 rounded-xl"
            />
            <input 
              type="text" placeholder="LON" value={lon}
              onChange={e => setLon(sanitizeCoord(e.target.value))}
              className="w-full px-1.5 py-1 text-[10px] font-['Inter',sans-serif] border border-[#BFD5E2]/15 bg-[#172331] text-[#F2F7FA] placeholder-zinc-600 focus:outline-none focus:border-cyan-500 rounded-xl"
            />
            <button type="submit" disabled={isSearching} className="bg-[#203447] hover:bg-zinc-700 border border-[#BFD5E2]/15 text-[#F2F7FA] px-2 py-1 rounded-xl text-[10px] font-['Inter',sans-serif] font-bold w-10 flex items-center justify-center">
              {isSearching ? '...' : 'GO'}
            </button>
          </div>
          {coordError && <div className="text-[9px] font-['Inter',sans-serif] text-[#D94B4B] uppercase tracking-widest">{coordError}</div>}
        </form>
      </div>

      <div className="flex-1 overflow-y-auto flex flex-col scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-zinc-950">
        {filteredLocations.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-600 text-xs p-6 font-['Inter',sans-serif] text-center">
            <MapPin className="w-6 h-6 mb-2 opacity-20" />
            <p>NO TARGETS FOUND</p>
          </div>
        ) : (
          filteredLocations.map((loc, idx) => {
            const locId = loc.id || loc.location_id || String(idx);
            const riskStr = getUnifiedRisk(loc);
            const style = getRiskStyle(loc);
            const isSelected = selectedLocationId === locId;
            const isStale = loc.is_stale === true || loc.data_age_hours > 24;

            return (
              <div 
                key={locId}
                onClick={() => onSelect(locId)}
                className={`p-2 border-b border-[#BFD5E2]/15 cursor-pointer transition-colors flex flex-col gap-1.5
                  ${isSelected ? 'bg-[#172331] border-l-2 border-l-[#06b6d4]' : 'hover:bg-[#172331]/50 border-l-2 border-l-transparent'}
                `}
              >
                <div className="flex items-start justify-between">
                  <div className="font-['Inter',sans-serif] font-bold text-[11px] text-[#F2F7FA] break-words pr-2 leading-tight flex-1">
                    {loc.name || loc.location_id || 'UNKNOWN_TGT'}
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    {isStale && (
                      <span className="flex items-center gap-1 text-[8px] text-[#E6A23C] bg-[#E6A23C]/10 border border-amber-500/20 px-1 py-0.5 rounded-lg font-bold uppercase tracking-widest font-['Inter',sans-serif] shrink-0">
                        STALE
                      </span>
                    )}
                    {(() => {
                      const alertSummary = loc.alert_summary;
                      const isHighRisk = ['HIGH', 'CRITICAL'].includes(riskStr.toUpperCase());
                      const isActiveAlert = (alertSummary && alertSummary.event_emitted) || isHighRisk;
                      
                      return isActiveAlert ? (
                        <span className="flex items-center gap-1 text-[8px] text-[#D94B4B] bg-red-950/50 border border-red-800 px-1 py-0.5 rounded-lg font-bold uppercase tracking-widest font-['Inter',sans-serif] shrink-0">
                          ALERT ACTIVE
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-[8px] text-[#BFD5E2] bg-[#172331] border border-[#BFD5E2]/15 px-1 py-0.5 rounded-lg font-bold uppercase tracking-widest font-['Inter',sans-serif] shrink-0">
                          NORMAL
                        </span>
                      );
                    })()}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-xl" style={{ backgroundColor: style.markerColor }}></span>
                  <span className={`text-[9px] font-['Inter',sans-serif] font-bold uppercase tracking-widest`} style={{ color: style.markerColor }}>
                    {style.id}
                  </span>
                  {loc.risk_score !== undefined && (
                    <span className="text-[9px] text-[#BFD5E2] font-['Inter',sans-serif] ml-auto">
                      SC: {Number(loc.risk_score).toFixed(2)}
                    </span>
                  )}
                </div>
                {loc.alert_summary?.triggered_at && (
                  <div className="text-[9px] font-['Inter',sans-serif] text-[#BFD5E2] mt-0.5 flex items-center gap-1">
                    <span>TRIGGERED:</span>
                    <span className="text-[#526D82]">
                      {new Date(loc.alert_summary.triggered_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC', hour12: false })} UTC
                    </span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};
