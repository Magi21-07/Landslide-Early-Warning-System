import { Activity, Clock } from 'lucide-react';

export const Header = ({ status = 'System Operational' }: { status?: string }) => {
  return (
    <header className="flex items-center justify-between px-3 py-1.5 bg-[#172331] text-zinc-300 shrink-0 select-none">
      <div className="flex items-center gap-2">
        <Activity className={`w-4 h-4 ${status === 'Operational' ? 'text-[#38A169]' : 'text-[#D94B4B]'}`} />
        <h1 className="text-xs font-bold tracking-widest uppercase text-zinc-100 font-['Sora',sans-serif]">〽 LEWS <span className="text-[#526D82] font-normal">|</span> LANDSLIDE EARLY WARNING SYSTEM</h1>
      </div>
      
      <div className="flex items-center gap-4 text-[10px] font-['IBM_Plex_Mono',monospace] uppercase tracking-wider text-zinc-400">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 ${status === 'Operational' ? 'bg-[#38A169] shadow-[0_0_5px_rgba(16,185,129,0.5)]' : 'bg-[#D94B4B] shadow-[0_0_5px_rgba(239,68,68,0.5)]'}`}></div>
          <span className={status === 'Operational' ? 'text-[#38A169]' : 'text-[#D94B4B]'}>{status === 'Operational' ? 'SYSTEM OPERATIONAL | LIVE DATA' : `SYSTEM ${status}`}</span>
        </div>
        <div className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          <span>UTC {new Date().toISOString().substring(11, 19)}</span>
        </div>
      </div>
    </header>
  );
};
