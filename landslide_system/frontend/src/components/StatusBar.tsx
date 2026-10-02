import { Database, Server, RefreshCw, AlertTriangle } from 'lucide-react';

export const StatusBar = ({ statusObj, error }: { statusObj?: any, error?: string | null }) => {
  const isOnline = !!statusObj && !error;
  
  return (
    <footer className="h-6 shrink-0 border-t border-zinc-800 bg-zinc-950 flex items-center justify-between px-2 text-[9px] font-mono uppercase tracking-widest text-zinc-500 select-none">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <Server className="w-3 h-3" />
          <span>API: {isOnline ? 'OK' : 'ERR'}</span>
        </div>
        <div className="flex items-center gap-1.5 border-l border-zinc-800 pl-4">
          <Database className="w-3 h-3" />
          <span>DB: {statusObj?.status === 'ok' ? 'OK' : 'N/A'}</span>
        </div>
        <div className="flex items-center gap-1.5 border-l border-zinc-800 pl-4">
           <RefreshCw className="w-3 h-3" />
           <span>Model: {statusObj?.model_version || 'N/A'}</span>
        </div>
      </div>
      
      <div className="flex items-center gap-1.5">
        {!isOnline && <AlertTriangle className="w-3 h-3 text-red-500" />}
        <span className={isOnline ? 'text-zinc-500' : 'text-red-500'}>
           {isOnline ? 'SYSTEM NOMINAL' : error || 'SYSTEM OFFLINE'}
        </span>
      </div>
    </footer>
  );
};
