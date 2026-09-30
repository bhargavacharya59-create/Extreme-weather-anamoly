'use client';
import { useEffect, useRef, useState } from 'react';
import { RISK } from '@/lib/format';

// Free vector base map, no API key (OpenFreeMap, OpenStreetMap data).
const STYLE_URL = process.env.NEXT_PUBLIC_MAP_STYLE || 'https://tiles.openfreemap.org/styles/positron';
// Used when the base map cannot load (offline demo venue): overlays still render.
const FALLBACK_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#e7ebe8' } }],
};
const EMPTY = { type: 'FeatureCollection', features: [] };
const INDIA = [[68, 6.5], [97.5, 35.5]];

const C = {
  school: '#1f4e8c',
  hospital: '#9e1b1b',
  rescue: '#1e6b3f',
  vehicleIn: '#dd6b27',
  vehicle: '#6b7680',
  track: '#14202b',
  safer: '#1e8a4c',
  current: '#b3261e',
};

const ringColor = ['match', ['get', 'ring'], 'high', RISK.high.fill, 'moderate', RISK.moderate.fill, 'low', RISK.low.fill, '#888'];
const sevColor = ['match', ['get', 'severity'], 'High', RISK.high.fill, 'Moderate', RISK.moderate.fill, 'Low', RISK.low.fill, '#888'];

function addLayers(map) {
  const src = (id) => { if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: EMPTY }); };
  ['wp-wards', 'wp-grid', 'wp-zones', 'wp-tracks', 'wp-routes', 'wp-assets', 'wp-vehicles'].forEach(src);
  const add = (spec) => { if (!map.getLayer(spec.id)) map.addLayer(spec); };

  add({ id: 'wards-fill', type: 'fill', source: 'wp-wards', paint: {
    'fill-color': ['interpolate', ['linear'], ['get', 'density_2011'], 0, '#eef3fa', 10000, '#9ec5f4', 30000, '#3987e5', 60000, '#184f95'],
    'fill-opacity': ['case', ['boolean', ['get', 'hl'], false], 0.75, 0.45] } });
  add({ id: 'wards-line', type: 'line', source: 'wp-wards', paint: {
    'line-color': ['case', ['boolean', ['get', 'hl'], false], '#14202b', '#ffffff'],
    'line-width': ['case', ['boolean', ['get', 'hl'], false], 1.6, 0.6] } });
  add({ id: 'grid-circles', type: 'circle', source: 'wp-grid', paint: {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2.5, 6, 7, 9, 18],
    'circle-color': ['interpolate', ['linear'], ['get', 'z'], 1.5, '#f8efcf', 2.5, '#d9a82e', 4, '#dd6b27', 6, '#9e1b1b'],
    'circle-opacity': 0.55, 'circle-blur': 0.6 } });
  add({ id: 'foot-fill', type: 'fill', source: 'wp-zones', filter: ['==', ['get', 'ring'], 'footprint'],
    paint: { 'fill-color': sevColor, 'fill-opacity': 0.10 } });
  add({ id: 'foot-line', type: 'line', source: 'wp-zones', filter: ['==', ['get', 'ring'], 'footprint'],
    paint: { 'line-color': sevColor, 'line-width': 1.2, 'line-dasharray': [3, 2], 'line-opacity': 0.9 } });
  add({ id: 'cone-fill', type: 'fill', source: 'wp-tracks', filter: ['==', ['get', 'kind'], 'cone'],
    paint: { 'fill-color': '#1f4e8c', 'fill-opacity': 0.10 } });
  add({ id: 'cone-line', type: 'line', source: 'wp-tracks', filter: ['==', ['get', 'kind'], 'cone'],
    paint: { 'line-color': '#1f4e8c', 'line-width': 1, 'line-dasharray': [2, 2], 'line-opacity': 0.6 } });
  add({ id: 'zones-fill', type: 'fill', source: 'wp-zones', filter: ['in', ['get', 'ring'], ['literal', ['high', 'moderate', 'low']]],
    paint: { 'fill-color': ringColor, 'fill-opacity': ['match', ['get', 'ring'], 'high', 0.45, 'moderate', 0.32, 'low', 0.24, 0] } });
  add({ id: 'zones-line', type: 'line', source: 'wp-zones', filter: ['in', ['get', 'ring'], ['literal', ['high', 'moderate', 'low']]],
    paint: { 'line-color': ringColor, 'line-width': 1.4 } });
  add({ id: 'track-line', type: 'line', source: 'wp-tracks', filter: ['==', ['get', 'kind'], 'track'],
    paint: { 'line-color': C.track, 'line-width': 2.2 } });
  add({ id: 'pred-line', type: 'line', source: 'wp-tracks', filter: ['==', ['get', 'kind'], 'predicted'],
    paint: { 'line-color': C.track, 'line-width': 2, 'line-dasharray': [2, 2] } });
  add({ id: 'track-pts', type: 'circle', source: 'wp-tracks', filter: ['==', ['get', 'kind'], 'position'],
    paint: { 'circle-radius': 3, 'circle-color': '#ffffff', 'circle-stroke-color': C.track, 'circle-stroke-width': 1.5 } });
  add({ id: 'route-current', type: 'line', source: 'wp-routes', filter: ['==', ['get', 'kind'], 'current'],
    paint: { 'line-color': C.current, 'line-width': 5, 'line-opacity': 0.9 } });
  add({ id: 'route-safer', type: 'line', source: 'wp-routes', filter: ['==', ['get', 'kind'], 'safer'],
    paint: { 'line-color': C.safer, 'line-width': 5, 'line-dasharray': [2, 1.2] } });
  add({ id: 'assets-circle', type: 'circle', source: 'wp-assets', paint: {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 2.5, 9, 5, 12, 7],
    'circle-color': ['match', ['get', 'kind'], 'school', C.school, 'hospital', '#ffffff', 'rescue_team', C.rescue, '#555'],
    'circle-stroke-color': ['match', ['get', 'kind'], 'hospital', C.hospital, '#ffffff'],
    'circle-stroke-width': ['match', ['get', 'kind'], 'hospital', 2.5, 1.5] } });
  add({ id: 'vehicles-circle', type: 'circle', source: 'wp-vehicles', paint: {
    'circle-radius': ['case', ['==', ['get', 'status'], 'clear'], 3, 5],
    'circle-color': ['case', ['==', ['get', 'status'], 'clear'], C.vehicle, C.vehicleIn],
    'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.5,
    'circle-opacity': ['case', ['==', ['get', 'status'], 'clear'], 0.55, 1] } });
  add({ id: 'zone-center', type: 'circle', source: 'wp-zones', filter: ['==', ['get', 'ring'], 'center'], paint: {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 7, 7, 6, 10, 5],
    'circle-color': sevColor, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 } });
}

function fc(x) { return x && x.type === 'FeatureCollection' ? x : EMPTY; }

function boundsOf(features) {
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  const walk = (c) => {
    if (typeof c[0] === 'number') { x0 = Math.min(x0, c[0]); x1 = Math.max(x1, c[0]); y0 = Math.min(y0, c[1]); y1 = Math.max(y1, c[1]); return; }
    c.forEach(walk);
  };
  features.forEach((f) => f.geometry && walk(f.geometry.coordinates));
  return x0 > x1 ? null : [[x0, y0], [x1, y1]];
}

/**
 * Declarative MapLibre map for WeatherPulse layers.
 * props: zones, tracks, assets, vehicles, wards, grid (FeatureCollections), routes {current, safer},
 * markers [{lon, lat, label, tone}], selectedEvent, highlightWards, highlightAssets,
 * fit ('data' | 'india' | [[x0,y0],[x1,y1]]), focus {lon, lat, zoom}, show {layer: bool},
 * onSelectEvent(id), onSelectAsset(props), onSelectVehicle(props), height
 */
export default function MapView({
  zones, tracks, assets, vehicles, wards, grid, routes, markers = [],
  selectedEvent, highlightWards, highlightAssets, fit = 'data', fitKey, focus,
  show = {}, onSelectEvent, onSelectAsset, onSelectVehicle, height = 520, className = '', children, interactive = true,
}) {
  const ref = useRef(null);
  const mapRef = useRef(null);
  const libRef = useRef(null);
  const markerRefs = useRef([]);
  const [ready, setReady] = useState(false);
  const [baseFailed, setBaseFailed] = useState(false);
  const [styleV, setStyleV] = useState(0);   // bumps when a (fallback) style reloads, to re-push data
  const cb = useRef({});
  cb.current = { onSelectEvent, onSelectAsset, onSelectVehicle };

  // create map once
  useEffect(() => {
    let map;
    let cancelled = false;
    let fallbackTimer;
    import('maplibre-gl').then((mod) => {
      if (cancelled || !ref.current) return;
      const maplibregl = mod.default || mod;
      libRef.current = maplibregl;
      map = new maplibregl.Map({
        container: ref.current, style: STYLE_URL, bounds: INDIA, fitBoundsOptions: { padding: 20 },
        attributionControl: { compact: true }, interactive, cooperativeGestures: false,
      });
      mapRef.current = map;
      if (interactive) map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
      const onStyle = () => { addLayers(map); setReady(true); };
      map.on('load', onStyle);
      map.on('style.load', () => { addLayers(map); setStyleV((v) => v + 1); });
      fallbackTimer = setTimeout(() => {
        if (!map.isStyleLoaded || !map.loaded || !map.isStyleLoaded()) { setBaseFailed(true); map.setStyle(FALLBACK_STYLE); }
      }, 7000);
      map.on('error', (e) => {
        if (!map.isStyleLoaded() && /style|Failed to fetch|NetworkError/i.test(String(e?.error?.message || ''))) {
          clearTimeout(fallbackTimer); setBaseFailed(true); map.setStyle(FALLBACK_STYLE);
        }
      });
      const clickable = ['zones-fill', 'zone-center', 'foot-fill'];
      clickable.forEach((l) => {
        map.on('click', l, (e) => { const id = e.features?.[0]?.properties?.event_id; if (id) cb.current.onSelectEvent?.(id); });
        map.on('mouseenter', l, () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', l, () => { map.getCanvas().style.cursor = ''; });
      });
      const popup = (e, html) => new maplibregl.Popup({ closeButton: false, offset: 10 }).setLngLat(e.lngLat).setHTML(html).addTo(map);
      map.on('click', 'assets-circle', (e) => {
        const p = e.features[0].properties;
        popup(e, `<div style="font-weight:600">${p.name}</div><div style="color:#5a6570;font-size:12px">${p.kind.replace('_', ' ')}${p.ring && p.ring !== 'null' ? ` · ${p.ring} risk ring` : ''}</div>`);
        cb.current.onSelectAsset?.(p);
      });
      map.on('click', 'vehicles-circle', (e) => {
        const p = e.features[0].properties;
        const st = p.status === 'clear' ? 'Not heading into a zone' : p.status === 'inside' ? 'Inside risk zone' : `Heading in · ETA ${p.eta_min} min`;
        popup(e, `<div style="font-weight:600">${p.id}</div><div style="color:#5a6570;font-size:12px">${p.kind.replace('_', ' ')} · ${Math.round(p.speed_kmh)} km/h · simulated</div><div style="font-size:12px;margin-top:2px">${st}</div>`);
        cb.current.onSelectVehicle?.(p);
      });
      ['assets-circle', 'vehicles-circle'].forEach((l) => {
        map.on('mouseenter', l, () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', l, () => { map.getCanvas().style.cursor = ''; });
      });
    });
    return () => { cancelled = true; clearTimeout(fallbackTimer); markerRefs.current.forEach((m) => m.remove()); map?.remove(); mapRef.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // data
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const set = (id, data) => map.getSource(id)?.setData(data);
    const hlW = new Set(highlightWards || []);
    const hlA = highlightAssets ? new Set(highlightAssets) : null;
    set('wp-wards', { type: 'FeatureCollection', features: fc(wards).features.map((f) => ({ ...f, properties: { ...f.properties, hl: hlW.has(f.properties.ward_no) } })) });
    set('wp-grid', fc(grid));
    set('wp-zones', fc(zones));
    set('wp-tracks', fc(tracks));
    set('wp-assets', hlA ? { type: 'FeatureCollection', features: fc(assets).features.filter((f) => hlA.has(f.properties.id)) } : fc(assets));
    set('wp-vehicles', fc(vehicles));
    const rf = [];
    if (routes?.current) rf.push({ type: 'Feature', properties: { kind: 'current' }, geometry: { type: 'LineString', coordinates: routes.current } });
    if (routes?.safer) rf.push({ type: 'Feature', properties: { kind: 'safer' }, geometry: { type: 'LineString', coordinates: routes.safer } });
    set('wp-routes', { type: 'FeatureCollection', features: rf });
  }, [ready, styleV, zones, tracks, assets, vehicles, wards, grid, routes, highlightWards, highlightAssets]);

  // visibility
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const groups = {
      wards: ['wards-fill', 'wards-line'], grid: ['grid-circles'], footprints: ['foot-fill', 'foot-line'],
      zones: ['zones-fill', 'zones-line', 'zone-center'], tracks: ['track-line', 'pred-line', 'track-pts', 'cone-fill', 'cone-line'],
      assets: ['assets-circle'], vehicles: ['vehicles-circle'], routes: ['route-current', 'route-safer'],
    };
    const defaults = { wards: true, grid: true, footprints: true, zones: true, tracks: true, assets: true, vehicles: true, routes: true };
    Object.entries(groups).forEach(([g, ids]) => {
      const vis = (show[g] ?? defaults[g]) ? 'visible' : 'none';
      ids.forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', vis));
    });
  }, [ready, styleV, show]);

  // selection emphasis
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const sel = selectedEvent || '';
    map.setPaintProperty('zones-line', 'line-width', ['case', ['==', ['get', 'event_id'], sel], 2.6, 1.2]);
    map.setPaintProperty('zone-center', 'circle-stroke-width', ['case', ['==', ['get', 'event_id'], sel], 3.5, 2]);
    map.setPaintProperty('zone-center', 'circle-stroke-color', ['case', ['==', ['get', 'event_id'], sel], '#14202b', '#ffffff']);
  }, [ready, styleV, selectedEvent]);

  // camera
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (focus) { map.flyTo({ center: [focus.lon, focus.lat], zoom: focus.zoom ?? 11, duration: 900 }); return; }
    if (fit === 'india') { map.fitBounds(INDIA, { padding: 20, duration: 600 }); return; }
    let b = Array.isArray(fit) ? fit : null;
    if (fit === 'data') {
      const feats = [...fc(zones).features, ...(routes?.current ? [{ geometry: { coordinates: routes.current } }] : []), ...(routes?.safer ? [{ geometry: { coordinates: routes.safer } }] : [])];
      b = boundsOf(feats);
    }
    if (b) map.fitBounds(b, { padding: 50, maxZoom: 12.5, duration: 700 });
  }, [ready, fitKey, focus?.lon, focus?.lat, focus?.zoom]); // eslint-disable-line react-hooks/exhaustive-deps

  // HTML markers (you / shelter / vehicle)
  useEffect(() => {
    const map = mapRef.current;
    const lib = libRef.current;
    if (!ready || !map || !lib) return;
    markerRefs.current.forEach((m) => m.remove());
    markerRefs.current = markers.map((mk) => {
      const el = document.createElement('div');
      el.className = `wp-marker wp-marker-${mk.tone || 'you'}`;
      el.innerHTML = `<span class="wp-dot"></span>${mk.label ? `<span class="wp-label">${mk.label}</span>` : ''}`;
      return new lib.Marker({ element: el, anchor: 'left', offset: [-9, 0] }).setLngLat([mk.lon, mk.lat]).addTo(map);
    });
  }, [ready, JSON.stringify(markers)]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className={`mapwrap ${className}`} style={{ height }}>
      <div ref={ref} style={{ position: 'absolute', inset: 0 }} aria-label="Risk map" role="region" />
      {!ready && <div className="skel" style={{ position: 'absolute', inset: 0, borderRadius: 0 }} />}
      {baseFailed && (
        <div className="map-overlay small" style={{ right: 10, bottom: 10, background: '#fff', padding: '3px 8px', borderRadius: 6, border: '1px solid var(--line)' }}>
          Base map offline · overlays shown
        </div>
      )}
      {children}
    </div>
  );
}

export function RiskLegend({ extra = [], title = 'Modelled risk (not an official warning)', collapsible = true }) {
  const [open, setOpen] = useState(!collapsible);
  return (
    <div className="legend">
      <div className="row between gap-8">
        <div className="t">{title}</div>
        {collapsible && extra.length > 0 && (
          <button className="btn ghost sm" style={{ height: 22, padding: '0 6px', fontSize: 11 }} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            {open ? 'Less' : `+${extra.length} layers`}
          </button>
        )}
      </div>
      {['high', 'moderate', 'low'].map((r) => (
        <div className="li" key={r}>
          <span className="ring" style={{ borderColor: RISK[r].fill, background: `${RISK[r].fill}55` }} />
          {RISK[r].label} · {RISK[r].range}
        </div>
      ))}
      {open && extra.map((x) => (
        <div className="li" key={x.label}>
          {x.line ? <span style={{ width: 20, borderTop: `3px ${x.dashed ? 'dashed' : 'solid'} ${x.color}` }} />
            : <span style={{ width: 12, height: 12, borderRadius: '50%', background: x.color, border: `2px solid ${x.stroke || '#fff'}`, boxShadow: '0 0 0 1px #0002' }} />}
          {x.label}
        </div>
      ))}
    </div>
  );
}

export const LEGEND = {
  track: { label: 'Track · dashed = projected', color: '#14202b', line: true },
  cone: { label: 'Path uncertainty cone', color: '#1f4e8c', line: true, dashed: true },
  school: { label: 'School / college', color: C.school },
  hospital: { label: 'Hospital', color: '#fff', stroke: C.hospital },
  rescue: { label: 'Rescue unit', color: C.rescue },
  vehicleIn: { label: 'Vehicle heading into zone', color: C.vehicleIn },
  vehicle: { label: 'Other vehicle (simulated)', color: C.vehicle },
  current: { label: 'Current route', color: C.current, line: true },
  safer: { label: 'Safer route', color: C.safer, line: true, dashed: true },
};
