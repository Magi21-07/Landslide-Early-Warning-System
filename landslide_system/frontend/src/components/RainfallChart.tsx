import { useState, useEffect } from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { Loader2, AlertCircle } from 'lucide-react';
import { getRecentRainfall } from '../services/api';
import { getRiskStyle } from '../utils/riskStyles';

interface RainfallChartProps {
  latitude?: number;
  longitude?: number;
  triggerState?: string;
}

export const RainfallChart = ({ latitude, longitude, triggerState }: RainfallChartProps) => {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (latitude === undefined || longitude === undefined) return;
    
    let isMounted = true;
    const fetchRainfall = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await getRecentRainfall(latitude, longitude, 15);
        if (isMounted) {
          if (result && result.rainfall_observations) {
             const formattedData = result.rainfall_observations.map((obs: any) => ({
                date: obs.date ? obs.date.substring(5) : '',
                rainfall: obs.rainfall_mm || 0
             }));
             setData(formattedData);
          } else {
             setData([]);
          }
        }
      } catch (err: any) {
        if (isMounted) setError(err.message || 'Failed to fetch rainfall');
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    
    fetchRainfall();
    return () => { isMounted = false; };
  }, [latitude, longitude]);

  const style = getRiskStyle(triggerState);

  return (
    <div className="w-full flex flex-col gap-2 font-mono">
      <div className="flex justify-between items-center bg-black p-2 border border-zinc-800 rounded-none">
        <span className="text-[9px] text-zinc-500 uppercase tracking-widest font-bold">Trigger State</span>
        <span className={`text-[9px] font-bold uppercase tracking-widest ${style.textColor}`}>
          {triggerState || 'UNKNOWN'}
        </span>
      </div>
      
      <div className="h-44 w-full relative mt-1 bg-black border border-zinc-800 p-2 pt-4 rounded-none">
        {loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 z-10 text-zinc-500 text-[10px] uppercase tracking-widest">
            <Loader2 className="w-5 h-5 animate-spin mb-1 text-zinc-600" />
            LOADING TRACE...
          </div>
        )}
        
        {error && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black z-10 text-red-500 text-[10px] uppercase tracking-widest text-center p-2">
            <AlertCircle className="w-5 h-5 mb-1" />
            {error}
          </div>
        )}
        
        {!loading && !error && data.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black z-10 text-zinc-600 text-[10px] uppercase tracking-widest">
            NO TRACE DATA
          </div>
        )}
        
        {!loading && !error && data.length > 0 && (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 0, right: 5, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="1 3" vertical={false} stroke="#27272a" />
              <XAxis dataKey="date" tick={{ fontSize: 8, fill: '#52525b', fontFamily: 'monospace' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 8, fill: '#52525b', fontFamily: 'monospace' }} axisLine={false} tickLine={false} width={40} />
              <Tooltip 
                 contentStyle={{ fontSize: '9px', padding: '4px 8px', borderRadius: '0px', backgroundColor: '#09090b', borderColor: '#27272a', color: '#e4e4e7', fontFamily: 'monospace' }}
                 cursor={{ fill: '#18181b' }}
              />
              <Bar dataKey="rainfall" fill="#3b82f6" radius={[0, 0, 0, 0]} name="mm" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
};
