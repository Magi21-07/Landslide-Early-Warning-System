import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Loader2, AlertCircle, SlidersHorizontal, Layers, Maximize, RefreshCcw } from 'lucide-react';
import { RISK_LEVELS } from '../utils/riskStyles';

interface RiskMapProps {
  center?: [number, number];
  zoom?: number;
  mapData?: any;
  loading?: boolean;
  error?: string | null;
  selectedLocationId?: string | null;
  onFeatureSelect?: (properties: any) => void;
  searchQuery?: string;
  riskFilter?: string;
  customView?: {center: [number, number], zoom: number} | null;
}


export const RiskMap = ({ 
  center = [77.1734, 31.1048], 
  zoom = 7,
  mapData,
  loading = false,
  error = null,
  selectedLocationId,
  onFeatureSelect,
  searchQuery = '',
  riskFilter = 'ALL',
  customView = null
}: RiskMapProps) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<maplibregl.Map | null>(null);
  const [opacity, setOpacity] = useState(0.6);
  const [layersVisible, setLayersVisible] = useState({
    polygons: true,
    points: true,
  });

  useEffect(() => {
    if (mapInstance.current || !mapContainer.current) return;

    try {
      mapInstance.current = new maplibregl.Map({
        container: mapContainer.current,
        style: {
          version: 8,
          sources: {
            'esri-dark': {
              type: 'raster',
              tiles: [
                'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
              ],
              tileSize: 256,
              attribution: 'Esri, HERE, Garmin, &copy; OpenStreetMap contributors',
            },
          },
          layers: [
            {
              id: 'esri-dark-layer',
              type: 'raster',
              source: 'esri-dark',
              minzoom: 0,
              maxzoom: 16,
            },
          ],
        },
        center,
        zoom,
        attributionControl: false,
      });

      const map = mapInstance.current;

      map.addControl(new maplibregl.NavigationControl(), 'top-right');
      map.addControl(new maplibregl.FullscreenControl(), 'top-right');
      map.addControl(new maplibregl.GeolocateControl({
        positionOptions: { enableHighAccuracy: true },
        trackUserLocation: true
      }), 'top-right');
      map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

      map.on('load', () => {
        try {
          // Force resize so MapLibre measures the container correctly after mount
          map.resize();

          map.addSource('risk-targets', {
            type: 'geojson',
            data: { type: 'FeatureCollection', features: [] }  // always start empty; data is set reactively
          });

          map.addLayer({
            id: 'risk-target-polygons',
            type: 'fill',
            source: 'risk-targets',
            paint: {
              'fill-color': [
                'match',
                ['get', 'risk_level'],
                'LOW', '#10B981',
                'MODERATE', '#F59E0B',
                'HIGH', '#EF4444',
                'CRITICAL', '#7F1D1D',
                '#6B7280'
              ],
              'fill-opacity': 0.6
            }
          });

          map.addLayer({
            id: 'risk-target-labels',
            type: 'symbol',
            source: 'risk-targets',
            layout: {
              'text-field': ['get', 'name'],
              'text-size': 12,
              'text-anchor': 'top'
            },
            paint: {
              'text-color': '#FFFFFF'
            }
          });

          map.addLayer({
            id: 'risk-highlight',
            type: 'line',
            source: 'risk-targets',
            filter: ['==', ['get', 'location_id'], ''] as maplibregl.FilterSpecification,
            paint: {
              'line-color': '#3b82f6',
              'line-width': 3,
              'line-gap-width': 1
            }
          });

          const interactiveLayers = ['risk-target-polygons'];
          
          interactiveLayers.forEach(layer => {
            map.on('mouseenter', layer, () => {
              map.getCanvas().style.cursor = 'pointer';
            });
            map.on('mouseleave', layer, () => {
              map.getCanvas().style.cursor = '';
            });
            map.on('click', layer, (e: any) => {
              if (!e.features || e.features.length === 0) return;
              const feature = e.features[0];
              if (onFeatureSelect) {
                onFeatureSelect(feature.properties);
              }
            });
          });
        } catch (layerErr) {
          console.error('MAPLIBRE LAYER INIT ERROR:', layerErr);
        }
      });

      map.on('error', (e: maplibregl.ErrorEvent) => {
        console.error('MAPLIBRE MAP ERROR:', e.error);
      });

      // Resize whenever the window changes to avoid a collapsed canvas
      const handleResize = () => map.resize();
      window.addEventListener('resize', handleResize);

      return () => {
        window.removeEventListener('resize', handleResize);
        mapInstance.current?.remove();
        mapInstance.current = null;
      };

    } catch (initErr) {
      console.error('MAPLIBRE INIT ERROR:', initErr);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Handle Dynamic Filters (Search & Risk)
  useEffect(() => {
    if (!mapInstance.current || !mapInstance.current.isStyleLoaded()) return;
    const map = mapInstance.current;
    
    let basePolygonFilter: any[] = ['==', ['geometry-type'], 'Polygon'];
    let basePointFilter: any[] = ['==', ['geometry-type'], 'Point'];
    
    const combinedFilter: any[] = ['all'];
    
    if (riskFilter !== 'ALL') {
       combinedFilter.push(['==', ['upcase', ['get', 'risk_level']], riskFilter]);
    }
    
    if (searchQuery) {
       const sq = searchQuery.toLowerCase();
       combinedFilter.push([
         'any',
         ['in', sq, ['downcase', ['get', 'name']]],
         ['in', sq, ['downcase', ['get', 'id']]],
         ['in', sq, ['downcase', ['get', 'location_id']]]
       ]);
    }

    if (combinedFilter.length > 1) {
       basePolygonFilter = ['all', basePolygonFilter, combinedFilter];
       basePointFilter = ['all', basePointFilter, combinedFilter];
    }
    
    if (map.getLayer('risk-target-polygons')) map.setFilter('risk-target-polygons', basePolygonFilter as maplibregl.FilterSpecification);
    if (map.getLayer('risk-outline')) map.setFilter('risk-outline', basePolygonFilter as maplibregl.FilterSpecification);
    if (map.getLayer('risk-points')) map.setFilter('risk-points', basePointFilter as maplibregl.FilterSpecification);

  }, [searchQuery, riskFilter]);

  // Handle Layer Visibility
  useEffect(() => {
    if (!mapInstance.current || !mapInstance.current.isStyleLoaded()) return;
    const map = mapInstance.current;
    
    if (map.getLayer('risk-target-polygons')) {
       map.setLayoutProperty('risk-target-polygons', 'visibility', layersVisible.polygons ? 'visible' : 'none');
       map.setLayoutProperty('risk-outline', 'visibility', layersVisible.polygons ? 'visible' : 'none');
    }
    if (map.getLayer('risk-points')) {
       map.setLayoutProperty('risk-points', 'visibility', layersVisible.points ? 'visible' : 'none');
    }
  }, [layersVisible]);

  // Handle Opacity Updates
  useEffect(() => {
    if (mapInstance.current && mapInstance.current.isStyleLoaded()) {
      const map = mapInstance.current;
      if (map.getLayer('risk-target-polygons')) {
        map.setPaintProperty('risk-target-polygons', 'fill-opacity', opacity);
      }
    }
  }, [opacity]);

  // Handle Data Updates — guarded against async race between map load and data fetch
  useEffect(() => {
    const map = mapInstance.current;
    if (!map || !mapData) return;

    if (!mapData.features || mapData.features.length === 0) {
      console.warn('GeoJSON risk map empty — no features to display');
    }

    const applyData = () => {
      const source = map.getSource('risk-targets') as maplibregl.GeoJSONSource;
      if (source) {
        source.setData(mapData);
      }
    };

    if (map.isStyleLoaded()) {
      // Style already loaded — apply immediately
      applyData();
    } else {
      // Style not yet loaded — wait for it (handles the race where data arrives first)
      map.once('style.load', applyData);
    }
  }, [mapData]);

  // Handle Selection Updates — expression-only filter syntax (no legacy ['==', 'prop', val] form)
  useEffect(() => {
    const map = mapInstance.current;
    if (!map || !map.isStyleLoaded()) return;

    // Build a strictly expression-based FilterSpecification — no legacy syntax
    const highlightFilter: maplibregl.FilterSpecification = selectedLocationId
      ? ['any',
          ['==', ['get', 'location_id'], selectedLocationId],
          ['==', ['get', 'id'],          selectedLocationId]
        ] as maplibregl.FilterSpecification
      : ['==', ['get', 'location_id'], ''] as maplibregl.FilterSpecification;

    if (map.getLayer('risk-highlight')) {
      map.setFilter('risk-highlight', highlightFilter);
    }

    // FlyTo selected feature
    if (selectedLocationId && mapData?.features && !customView) {
      const feature = mapData.features.find((f: any) =>
        f.properties?.location_id === selectedLocationId ||
        f.properties?.id          === selectedLocationId
      );
      if (feature?.geometry?.type === 'Point') {
        map.flyTo({ center: feature.geometry.coordinates as [number, number], zoom: 11 });
      } else if (feature?.properties?.longitude && feature?.properties?.latitude) {
        map.flyTo({ center: [feature.properties.longitude, feature.properties.latitude], zoom: 11 });
      }
    }
  }, [selectedLocationId, mapData, customView]);

  // Custom Coordinate FlyTo
  useEffect(() => {
     if (customView && mapInstance.current) {
        mapInstance.current.flyTo({ center: customView.center, zoom: customView.zoom });
     }
  }, [customView]);

  const fitBounds = () => {
    if (!mapInstance.current || !mapData || !mapData.features || mapData.features.length === 0) return;
    try {
      const coords = mapData.features.map((f: any) => {
        if (f.geometry.type === 'Point') return f.geometry.coordinates;
        if (f.properties.longitude && f.properties.latitude) return [f.properties.longitude, f.properties.latitude];
        return null;
      }).filter((c: any) => c);
      
      if (coords.length > 0) {
        const bounds = coords.reduce((bounds: maplibregl.LngLatBounds, coord: any) => {
          return bounds.extend(coord);
        }, new maplibregl.LngLatBounds(coords[0], coords[0]));
        
        mapInstance.current.fitBounds(bounds, { padding: 50, maxZoom: 12 });
      }
    } catch(e) {
      console.error('FIT BOUNDS ERROR:', e);
    }
  };

  const resetView = () => {
    if (mapInstance.current) {
      mapInstance.current.flyTo({ center, zoom });
    }
  };

  const isEmpty = !loading && !error && (!mapData || !mapData.features || mapData.features.length === 0);

  return (
    <div className="relative w-full h-full" style={{ minHeight: 0 }}>
      {/* Explicit w/h on the container div — MapLibre REQUIRES non-zero pixel dimensions at render time */}
      <div
        ref={mapContainer}
        style={{ position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, width: '100%', height: '100%' }}
      />
      
      {/* Top Map Controls */}
      <div className="absolute top-4 left-4 flex gap-2 z-10">
         <button onClick={resetView} className="bg-zinc-900/90 backdrop-blur text-zinc-300 hover:text-white p-2 border border-zinc-700 text-xs font-mono font-semibold flex items-center gap-1.5" title="Reset Map View">
            <RefreshCcw className="w-3.5 h-3.5"/> RESET
         </button>
         <button onClick={fitBounds} className="bg-zinc-900/90 backdrop-blur text-zinc-300 hover:text-white p-2 border border-zinc-700 text-xs font-mono font-semibold flex items-center gap-1.5" title="Fit Map to Data">
            <Maximize className="w-3.5 h-3.5"/> FIT
         </button>
         
         {/* Layers Toggle */}
         <div className="bg-zinc-900/90 backdrop-blur text-zinc-300 p-2 border border-zinc-700 text-xs font-mono font-semibold flex items-center gap-3">
            <Layers className="w-3.5 h-3.5"/>
            <label className="flex items-center gap-1 cursor-pointer">
              <input type="checkbox" checked={layersVisible.polygons} onChange={e => setLayersVisible(s => ({...s, polygons: e.target.checked}))} />
              POLY
            </label>
            <label className="flex items-center gap-1 cursor-pointer">
              <input type="checkbox" checked={layersVisible.points} onChange={e => setLayersVisible(s => ({...s, points: e.target.checked}))} />
              PTS
            </label>
         </div>
      </div>

      {/* Legend & Controls */}
      <div className="absolute bottom-6 left-4 flex flex-col gap-2 z-10">
        <div className="bg-zinc-900/90 backdrop-blur-sm p-3 border border-zinc-700 text-xs font-mono w-44">
          <div className="flex items-center justify-between mb-2 text-zinc-400 font-bold uppercase tracking-widest text-[9px]">
            <span className="flex items-center gap-1.5"><SlidersHorizontal className="w-3 h-3"/> OPACITY</span>
            <span>{Math.round(opacity * 100)}%</span>
          </div>
          <input 
            type="range" 
            min="0" max="1" step="0.1" 
            value={opacity} 
            onChange={(e) => setOpacity(parseFloat(e.target.value))}
            className="w-full accent-blue-500"
          />
        </div>

        <div className="bg-zinc-900/90 backdrop-blur-sm p-3 border border-zinc-700 text-xs font-mono w-44">
          <h4 className="font-bold mb-2 text-zinc-400 uppercase tracking-widest text-[9px]">RISK LEVEL</h4>
          <div className="flex flex-col gap-1.5">
            {Object.values(RISK_LEVELS).filter(r => r.id !== 'UNKNOWN').map((risk) => (
              <div key={risk.id} className="flex items-center gap-2">
                <span className="w-2.5 h-2.5" style={{ backgroundColor: risk.fillColor }}></span>
                <span className="text-zinc-400 text-[9px] uppercase tracking-widest">{risk.id}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {loading && (
        <div className="absolute inset-0 bg-black/60 flex items-center justify-center z-20 backdrop-blur-sm">
          <div className="flex flex-col items-center text-zinc-400 bg-zinc-900 p-4 border border-zinc-700 font-mono text-[10px] uppercase tracking-widest">
            <Loader2 className="w-6 h-6 animate-spin mb-2 text-blue-500" />
            LOADING MAP DATA...
          </div>
        </div>
      )}

      {error && !loading && (
        <div className="absolute inset-0 bg-black/70 flex items-center justify-center z-20">
          <div className="flex flex-col items-center text-red-500 bg-zinc-900 p-6 border border-red-900 max-w-sm text-center font-mono">
            <AlertCircle className="w-8 h-8 mb-3" />
            <h3 className="font-bold text-[10px] uppercase tracking-widest mb-1">DATA ERROR</h3>
            <p className="text-[10px] text-zinc-400">{error}</p>
          </div>
        </div>
      )}

      {isEmpty && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-zinc-900/90 backdrop-blur-sm px-4 py-2 border border-zinc-700 text-[10px] font-mono text-zinc-400 z-10 flex items-center gap-2 uppercase tracking-widest">
          <AlertCircle className="w-3.5 h-3.5" />
          NO ACTIVE LOCATIONS
        </div>
      )}
    </div>
  );
};
