import { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { DetailsPanel } from './components/DetailsPanel';
import { MapArea } from './components/MapArea';
import { StatusBar } from './components/StatusBar';
import { getSystemStatus, getRiskMap, getRiskAtLocation } from './services/api';
import { Routes, Route } from 'react-router-dom';
import DemoPage from './pages/DemoPage';

function Dashboard() {
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null);
  const [locations, setLocations] = useState<any[]>([]);
  const [sysStatus, setSysStatus] = useState<any>(null);
  const [sysError, setSysError] = useState<string | null>(null);
  const [mapData, setMapData] = useState<any>(null);
  const [mapLoading, setMapLoading] = useState(true);
  const [mapError, setMapError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState('ALL');

  // fetchedLocation: result from /risk/evaluate (coordinate search or sidebar live-fetch)
  const [fetchedLocation, setFetchedLocation] = useState<any>(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [customView, setCustomView] = useState<{center: [number, number], zoom: number} | null>(null);

  // Initial data load
  useEffect(() => {
    getSystemStatus()
      .then(setSysStatus)
      .catch(() => setSysError('Offline'));

    getRiskMap()
      .then((data) => {
        setMapData(data);
        if (data && data.features) {
          setLocations(data.features.map((f: any) => f.properties));
        }
      })
      .catch((err) => {
        console.error('Failed to load map data', err);
        setMapError(err.message || 'Failed to load map data');
      })
      .finally(() => setMapLoading(false));
  }, []);

  // Live risk fetch whenever the user selects a location from the sidebar.
  // Extracts lat/lon from the GeoJSON properties (added in previous session).
  const fetchLiveRisk = useCallback(async (lat: number, lon: number, locId: string) => {
    setLiveLoading(true);
    try {
      const result = await getRiskAtLocation(lat, lon);
      // Merge the live API result with stored GeoJSON properties so all fields are available
      setFetchedLocation({ ...result, location_id: locId, latitude: lat, longitude: lon });
    } catch (err: any) {
      console.error('Live risk fetch failed:', err?.response?.data || err?.message);
      // Non-fatal: fall back to static GeoJSON data for this location
      setFetchedLocation(null);
    } finally {
      setLiveLoading(false);
    }
  }, []);

  // On sidebar selection: look up the location's coordinates and fire a live risk fetch
  useEffect(() => {
    if (!selectedLocationId) {
      setFetchedLocation(null);
      return;
    }
    const loc = locations.find(
      (l) => l.id === selectedLocationId || l.location_id === selectedLocationId
    );
    if (loc && loc.latitude !== undefined && loc.longitude !== undefined) {
      fetchLiveRisk(Number(loc.latitude), Number(loc.longitude), selectedLocationId);
    }
  }, [selectedLocationId, locations, fetchLiveRisk]);

  // Coordinate search handler
  const handleCoordinateSearch = async (lat: number, lon: number) => {
    try {
      setMapLoading(true);
      const result = await getRiskAtLocation(lat, lon);
      const locId = result.location_id || `coord-${lat.toFixed(4)}-${lon.toFixed(4)}`;
      setFetchedLocation({ ...result, latitude: lat, longitude: lon, location_id: locId });
      setSelectedLocationId(locId);
      setCustomView({ center: [lon, lat], zoom: 12 });
    } catch (err: any) {
      console.error('Coord search error', err);
      throw err;
    } finally {
      setMapLoading(false);
    }
  };

  // Derive displayed location: prefer live fetchedLocation, fall back to static GeoJSON properties
  const staticLocation = locations.find(
    (loc) => loc.id === selectedLocationId || loc.location_id === selectedLocationId
  ) || null;

  const selectedLocation = fetchedLocation
    ? {
        ...staticLocation,    // static fields: susceptibility_class, rainfall_7d, etc.
        ...fetchedLocation,   // live fields override: risk_level, dynamic_risk, etc.
      }
    : staticLocation;

  return (
    <div className="flex flex-col h-screen w-full overflow-hidden bg-zinc-950 font-sans text-zinc-300 antialiased selection:bg-blue-900 selection:text-white">
      <Header status={sysStatus ? 'Operational' : sysError || 'Connecting...'} />

      <div className="flex-1 flex overflow-hidden border-t border-zinc-800">
        <Sidebar
          locations={locations}
          selectedLocationId={selectedLocationId}
          onSelect={setSelectedLocationId}
          search={search}
          setSearch={setSearch}
          riskFilter={riskFilter}
          setRiskFilter={setRiskFilter}
          onCoordinateSearch={handleCoordinateSearch}
        />
        <DetailsPanel location={selectedLocation} loading={liveLoading} />
        <MapArea
          mapData={mapData}
          loading={mapLoading}
          error={mapError}
          selectedLocationId={selectedLocationId}
          onFeatureSelect={(feature) => {
            setSelectedLocationId(feature.id || feature.location_id);
          }}
          searchQuery={search}
          riskFilter={riskFilter}
          customView={customView}
        />
      </div>

      <StatusBar statusObj={sysStatus} error={sysError} />
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/demo" element={<DemoPage />} />
    </Routes>
  );
}
export default App;
