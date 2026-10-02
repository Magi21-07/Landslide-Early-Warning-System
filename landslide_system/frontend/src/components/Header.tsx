import { Activity, Clock } from 'lucide-react';

export const Header = ({ status = 'System Operational' }: { status?: string }) => {
  return (
    <header className="flex items-center justify-between px-3 py-1.5 bg-black text-zinc-300 shrink-0 select-none">
      <div className="flex items-center gap-2">
        <Activity className={`w-4 h-4 ${status === 'Operational' ? 'text-emerald-500' : 'text-red-500'}`} />
        <h1 className="text-xs font-bold tracking-widest uppercase text-zinc-100">LEWS <span className="text-zinc-600 font-normal">|</span> Landslide Early Warning System</h1>
      </div>
      
      <div className="flex items-center gap-4 text-[10px] font-mono uppercase tracking-wider text-zinc-400">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 ${status === 'Operational' ? 'bg-emerald-500 shadow-[0_0_5px_rgba(16,185,129,0.5)]' : 'bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.5)]'}`}></div>
          <span className={status === 'Operational' ? 'text-emerald-400' : 'text-red-400'}>{status === 'Operational' ? 'SYS OP' : `SYS ${status}`}</span>
        </div>
        <div className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          <span>UTC {new Date().toISOString().substring(11, 19)}</span>
        </div>
      </div>
    </header>
  );
};
