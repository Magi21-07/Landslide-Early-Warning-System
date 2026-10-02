import { RiskMap } from './RiskMap';

interface MapAreaProps {
  mapData: any;
  loading?: boolean;
  error?: string | null;
  selectedLocationId: string | null;
  onFeatureSelect: (feature: any) => void;
  searchQuery: string;
  riskFilter: string;
  customView: {center: [number, number], zoom: number} | null;
}

export const MapArea = ({ mapData, loading, error, selectedLocationId, onFeatureSelect, searchQuery, riskFilter, customView }: MapAreaProps) => {
  return (
    <main className="flex-1 bg-zinc-950 relative overflow-hidden min-h-0">
      <RiskMap 
         mapData={mapData} 
         loading={loading}
         error={error}
         selectedLocationId={selectedLocationId}
         onFeatureSelect={onFeatureSelect} 
         searchQuery={searchQuery}
         riskFilter={riskFilter}
         customView={customView}
      />
    </main>
  );
};
