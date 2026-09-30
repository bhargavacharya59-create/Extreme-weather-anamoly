'use client';
import { useEffect, useRef, useState } from 'react';
import Icon from '@/components/ui/Icon';

/*
 * Base maps (no API key needed):
 *  - "satellite": Esri World Imagery + roads + place labels (hybrid, like a GIS operations view)
 *  - "streets":   OpenFreeMap vector tiles (OpenStreetMap data)
 * Optional: NEXT_PUBLIC_MAPTILER_KEY switches satellite to MapTiler Hybrid (recommended for production).
 */
const MAPTILER = process.env.NEXT_PUBLIC_MAPTILER_KEY;
const STREETS_URL = process.env.NEXT_PUBLIC_MAP_STYLE || 'https://tiles.openfreemap.org/styles/liberty';
const DEFAULT_BASE = process.env.NEXT_PUBLIC_MAP_BASE || 'satellite';
const esri = (svc) => `https://server.arcgisonline.com/ArcGIS/rest/services/${svc}/MapServer/tile/{z}/{y}/{x}`;
const SATELLITE_STYLE = MAPTILER ? `https://api.maptiler.com/maps/hybrid/style.json?key=${MAPTILER}` : {
  version: 8,
  sources: {
    sat: { type: 'raster', tiles: [esri('World_Imagery')], tileSize: 256, maxzoom: 19, attribution: 'Imagery © Esri, Maxar, Earthstar Geographics' },
    roads: { type: 'raster', tiles: [esri('Reference/World_Transportation')], tileSize: 256, maxzoom: 19 },
    labels: { type: 'raster', tiles: [esri('Reference/World_Boundaries_and_Places')], tileSize: 256, maxzoom: 19 },
  },
  layers: [
    { id: 'bg', type: 'background', paint: { 'background-color': '#2b3a2f' } },
    { id: 'sat', type: 'raster', source: 'sat', paint: { 'raster-saturation': -0.15, 'raster-brightness-max': 0.92 } },
    { id: 'roads', type: 'raster', source: 'roads', paint: { 'raster-opacity': 0.9 } },
    { id: 'labels', type: 'raster', source: 'labels' },
  ],
};
const FALLBACK_STYLE = { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#dfe5e1' } }] };
const EMPTY = { type: 'FeatureCollection', features: [] };
const INDIA = [[68, 6.5], [97.5, 35.5]];

// Map palette (bright for satellite imagery; always paired with the legend labels)
export const MAPC = {
  high: '#e53935', highLine: '#b71c1c',
  moderate: '#fb8c00', moderateLine: '#e65100',
  low: '#fdd835', lowLine: '#f9a825',
  school: '#1f5fbf', hospital: '#e53935', rescue: '#2e9d57', vehicleIn: '#ef6c00', vehicle: '#4b5560',
  track: '#ffffff', trackCasing: '#14202b', safer: '#22c55e', current: '#ef4444', pin: '#e53935',
};
const ringColor = ['match', ['get', 'ring'], 'high', MAPC.high, 'moderate', MAPC.moderate, 'low', MAPC.low, '#888'];
const ringLine = ['match', ['get', 'ring'], 'high', MAPC.highLine, 'moderate', MAPC.moderateLine, 'low', MAPC.lowLine, '#888'];
const sevColor = ['match', ['get', 'severity'], 'High', MAPC.high, 'Moderate', MAPC.moderate, 'Low', MAPC.low, '#888'];

// Icon glyph paths (24px grid) drawn onto rounded-square markers
const GLYPH = {
  school: 'M2 9l10-5 10 5-10 5zM6 11v5c3 2 9 2 12 0v-5',
  hospital: 'M12 5v14M5 12h14',
  rescue: 'M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7zM12 9v6M9 12h6',
  bus: 'M5 4h14a1 1 0 0 1 1 1v12H4V5a1 1 0 0 1 1-1zM4 11h16M7 20v-3M17 20v-3',
  car: 'M5 16h14M3 16v-3l2-5h14l2 5v3h-2M7 16v2M17 16v2',
};

function drawIcon(bg, glyph, { fg = '#fff', border = '#fff', size = 64, stroke = 3 } = {}) {
  const c = document.createElement('canvas');
  c.width = size; c.height = size;
  const g = c.getContext('2d');
  const r = size * 0.22; const m = 4; const w = size - 2 * m;
  g.shadowColor = 'rgba(0,0,0,0.35)'; g.shadowBlur = 5; g.shadowOffsetY = 1.5;
  g.beginPath();
  g.moveTo(m + r, m); g.arcTo(m + w, m, m + w, m + w, r); g.arcTo(m + w, m + w, m, m + w, r);
  g.arcTo(m, m + w, m, m, r); g.arcTo(m, m, m + w, m, r); g.closePath();
  g.fillStyle = bg; g.fill();
  g.shadowColor = 'transparent';
  g.lineWidth = 3; g.strokeStyle = border; g.stroke();
  g.save();
  const s = (w * 0.62) / 24;
  g.translate(size / 2 - 12 * s, size / 2 - 12 * s); g.scale(s, s);
  g.strokeStyle = fg; g.lineWidth = stroke; g.lineCap = 'round'; g.lineJoin = 'round';
  g.stroke(new Path2D(glyph));
  g.restore();
  return g.getImageData(0, 0, size, size);
}

function drawPin(color) {
  const W = 56; const H = 72;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.shadowColor = 'rgba(0,0,0,0.4)'; g.shadowBlur = 6; g.shadowOffsetY = 2;
  g.beginPath();
  g.moveTo(W / 2, H - 4);
  g.bezierCurveTo(W / 2 - 4, H - 20, 5, H - 34, 5, 25);
  g.arc(W / 2, 25, W / 2 - 5, Math.PI, 0);
  g.bezierCurveTo(W - 5, H - 34, W / 2 + 4, H - 20, W / 2, H - 4);
  g.fillStyle = color; g.fill();
  g.shadowColor = 'transparent';
  g.lineWidth = 3; g.strokeStyle = '#fff'; g.stroke();
  g.beginPath(); g.arc(W / 2, 25, 8, 0, Math.PI * 2); g.fillStyle = '#fff'; g.fill();
  return g.getImageData(0, 0, W, H);
}

function addImages(map) {
  const add = (id, img) => { if (!map.hasImage(id)) map.addImage(id, img, { pixelRatio: 2 }); };
  add('wp-school', drawIcon(MAPC.school, GLYPH.school));
  add('wp-hospital', drawIcon('#ffffff', GLYPH.hospital, { fg: MAPC.hospital, border: MAPC.hospital, stroke: 4.5 }));
  add('wp-rescue', drawIcon(MAPC.rescue, GLYPH.rescue));
  add('wp-bus', drawIcon(MAPC.vehicle, GLYPH.bus));
  add('wp-car', drawIcon(MAPC.vehicle, GLYPH.car));
  add('wp-bus-in', drawIcon(MAPC.vehicleIn, GLYPH.bus));
  add('wp-car-in', drawIcon(MAPC.vehicleIn, GLYPH.car));
  add('wp-pin', drawPin(MAPC.pin));
}

function addLayers(map) {
  addImages(map);
  const src = (id) => { if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: EMPTY }); };
  ['wp-wards', 'wp-grid', 'wp-zones', 'wp-tracks', 'wp-routes', 'wp-assets', 'wp-vehicles'].forEach(src);
  const add = (spec) => { if (!map.getLayer(spec.id)) map.addLayer(spec); };
  const isRing = ['in', ['get', 'ring'], ['literal', ['high', 'moderate', 'low']]];

  add({ id: 'wards-fill', type: 'fill', source: 'wp-wards', paint: {
    'fill-color': ['interpolate', ['linear'], ['get', 'density_2011'], 0, '#eef3fa', 10000, '#9ec5f4', 30000, '#3987e5', 60000, '#184f95'],
    'fill-opacity': ['case', ['boolean', ['get', 'hl'], false], 0.55, 0.3] } });
  add({ id: 'wards-line', type: 'line', source: 'wp-wards', paint: {
    'line-color': ['case', ['boolean', ['get', 'hl'], false], '#ffffff', 'rgba(255,255,255,0.6)'],
    'line-width': ['case', ['boolean', ['get', 'hl'], false], 1.6, 0.5] } });
  add({ id: 'grid-circles', type: 'circle', source: 'wp-grid', paint: {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2.5, 6, 7, 9, 18],
    'circle-color': ['interpolate', ['linear'], ['get', 'z'], 1.5, MAPC.low, 3, MAPC.moderate, 5, MAPC.high],
    'circle-opacity': 0.5, 'circle-blur': 0.6 } });
  add({ id: 'foot-fill', type: 'fill', source: 'wp-zones', filter: ['==', ['get', 'ring'], 'footprint'],
    paint: { 'fill-color': sevColor, 'fill-opacity': 0.12 } });
  add({ id: 'foot-line', type: 'line', source: 'wp-zones', filter: ['==', ['get', 'ring'], 'footprint'],
    paint: { 'line-color': sevColor, 'line-width': 1.4, 'line-dasharray': [3, 2] } });
  add({ id: 'cone-fill', type: 'fill', source: 'wp-tracks', filter: ['==', ['get', 'kind'], 'cone'],
    paint: { 'fill-color': '#ffffff', 'fill-opacity': 0.12 } });
  add({ id: 'cone-line', type: 'line', source: 'wp-tracks', filter: ['==', ['get', 'kind'], 'cone'],
    paint: { 'line-color': '#ffffff', 'line-width': 1.2, 'line-dasharray': [2, 2], 'line-opacity': 0.8 } });
  // risk rings: yellow -> orange -> red, drawn outer to inner so each sits on the one below
  add({ id: 'zones-fill', type: 'fill', source: 'wp-zones', filter: isRing,
    paint: { 'fill-color': ringColor, 'fill-opacity': ['match', ['get', 'ring'], 'high', 0.5, 'moderate', 0.42, 'low', 0.34, 0] } });
  add({ id: 'zones-line', type: 'line', source: 'wp-zones', filter: isRing,
    paint: { 'line-color': ringLine, 'line-width': 1.4, 'line-opacity': 0.9 } });
  add({ id: 'zone-glow', type: 'circle', source: 'wp-zones', filter: ['==', ['get', 'ring'], 'center'], minzoom: 7, paint: {
    'circle-radius': ['interpolate', ['exponential', 2], ['zoom'], 7, 3, 10, 18, 13, 140, 16, 1100],
    'circle-color': MAPC.high, 'circle-opacity': 0.45, 'circle-blur': 1 } });
  add({ id: 'track-casing', type: 'line', source: 'wp-tracks', filter: ['==', ['get', 'kind'], 'track'],
    paint: { 'line-color': MAPC.trackCasing, 'line-width': 4.5, 'line-opacity': 0.6 } });
  add({ id: 'track-line', type: 'line', source: 'wp-tracks', filter: ['==', ['get', 'kind'], 'track'],
    paint: { 'line-color': MAPC.track, 'line-width': 2.2 } });
  add({ id: 'pred-line', type: 'line', source: 'wp-tracks', filter: ['==', ['get', 'kind'], 'predicted'],
    paint: { 'line-color': MAPC.track, 'line-width': 2, 'line-dasharray': [2, 2] } });
  add({ id: 'track-pts', type: 'circle', source: 'wp-tracks', filter: ['==', ['get', 'kind'], 'position'],
    paint: { 'circle-radius': 3, 'circle-color': '#14202b', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.5 } });
  add({ id: 'route-current', type: 'line', source: 'wp-routes', filter: ['==', ['get', 'kind'], 'current'],
    paint: { 'line-color': MAPC.current, 'line-width': 5, 'line-opacity': 0.95 } });
  add({ id: 'route-safer', type: 'line', source: 'wp-routes', filter: ['==', ['get', 'kind'], 'safer'],
    paint: { 'line-color': MAPC.safer, 'line-width': 5, 'line-dasharray': [2, 1.2] } });
  // institutions: dots when zoomed out, icon markers when zoomed in
  add({ id: 'assets-dot', type: 'circle', source: 'wp-assets', maxzoom: 8.5, paint: {
    'circle-radius': 3, 'circle-color': ['match', ['get', 'kind'], 'school', MAPC.school, 'hospital', MAPC.hospital, 'rescue_team', MAPC.rescue, '#555'],
    'circle-stroke-color': '#fff', 'circle-stroke-width': 1 } });
  add({ id: 'assets-icon', type: 'symbol', source: 'wp-assets', minzoom: 8.5, layout: {
    'icon-image': ['match', ['get', 'kind'], 'school', 'wp-school', 'hospital', 'wp-hospital', 'rescue_team', 'wp-rescue', 'wp-school'],
    'icon-size': ['interpolate', ['linear'], ['zoom'], 8.5, 0.6, 11, 0.85, 14, 1], 'icon-allow-overlap': true, 'icon-ignore-placement': true } });
  add({ id: 'vehicles-dot', type: 'circle', source: 'wp-vehicles', maxzoom: 9, paint: {
    'circle-radius': 3, 'circle-color': ['case', ['==', ['get', 'status'], 'clear'], MAPC.vehicle, MAPC.vehicleIn],
    'circle-stroke-color': '#fff', 'circle-stroke-width': 1 } });
  add({ id: 'vehicles-icon', type: 'symbol', source: 'wp-vehicles', minzoom: 9, layout: {
    'icon-image': ['concat', 'wp-', ['case', ['in', ['get', 'kind'], ['literal', ['bus', 'truck']]], 'bus', 'car'],
      ['case', ['==', ['get', 'status'], 'clear'], '', '-in']],
    'icon-size': ['interpolate', ['linear'], ['zoom'], 9, 0.5, 12, 0.75, 15, 0.9], 'icon-allow-overlap': true, 'icon-ignore-placement': true },
    paint: { 'icon-opacity': ['case', ['==', ['get', 'status'], 'clear'], 0.7, 1] } });
  // anomaly location: coloured dot when zoomed out, red pin when zoomed in
  add({ id: 'zone-center', type: 'circle', source: 'wp-zones', filter: ['==', ['get', 'ring'], 'center'], maxzoom: 7, paint: {
    'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 7, 7, 8],
    'circle-color': sevColor, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 } });
  add({ id: 'zone-pin', type: 'symbol', source: 'wp-zones', filter: ['==', ['get', 'ring'], 'center'], minzoom: 7, layout: {
    'icon-image': 'wp-pin', 'icon-anchor': 'bottom', 'icon-size': ['interpolate', ['linear'], ['zoom'], 7, 0.7, 12, 1],
    'icon-allow-overlap': true, 'icon-ignore-placement': true } });
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

function safeGet(k) { try { return window.localStorage.getItem(k); } catch { return null; } }
function safeSet(k, v) { try { window.localStorage.setItem(k, v); } catch { /* ignore */ } }

/**
 * Declarative MapLibre map for WeatherPulse layers.
 * props: zones, tracks, assets, vehicles, wards, grid (FeatureCollections), routes {current, safer},
 * markers [{lon, lat, label, tone}], title, live, legend (array of LEGEND items or true), selectedEvent,
 * highlightWards, highlightAssets, fit ('data' | 'india' | bounds), fitKey, focus {lon, lat, zoom},
 * show {layer: bool}, onSelectEvent, onSelectAsset, onSelectVehicle, height, compact
 */
export default function MapView({
  zones, tracks, assets, vehicles, wards, grid, routes, markers = [], title, live = true, legend,
  selectedEvent, highlightWards, highlightAssets, fit = 'data', fitKey, focus,
  show = {}, onSelectEvent, onSelectAsset, onSelectVehicle, height = 520, className = '', children, interactive = true, compact = false,
}) {
  const ref = useRef(null);
  const mapRef = useRef(null);
  const libRef = useRef(null);
  const markerRefs = useRef([]);
  const [ready, setReady] = useState(false);
  const [baseFailed, setBaseFailed] = useState(false);
  const [styleV, setStyleV] = useState(0);
  const [base, setBase] = useState(DEFAULT_BASE);
  const [legendOpen, setLegendOpen] = useState(typeof height !== 'number' || height >= 450);
  const cb = useRef({});
  cb.current = { onSelectEvent, onSelectAsset, onSelectVehicle };

  const styleFor = (b) => (b === 'streets' ? STREETS_URL : SATELLITE_STYLE);

  useEffect(() => {
    let map;
    let cancelled = false;
    let fallbackTimer;
    const saved = safeGet('wp_map_base');
    const initialBase = saved === 'streets' || saved === 'satellite' ? saved : DEFAULT_BASE;
    setBase(initialBase);
    import('maplibre-gl').then((mod) => {
      if (cancelled || !ref.current) return;
      const maplibregl = mod.default || mod;
      libRef.current = maplibregl;
      map = new maplibregl.Map({
        container: ref.current, style: styleFor(initialBase), bounds: INDIA, fitBoundsOptions: { padding: 20 },
        attributionControl: { compact: true }, interactive,
      });
      mapRef.current = map;
      if (interactive) map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
      map.addControl(new maplibregl.ScaleControl({ unit: 'metric', maxWidth: 110 }), 'bottom-right');
      map.on('load', () => { addLayers(map); setReady(true); });
      map.on('style.load', () => { addLayers(map); setStyleV((v) => v + 1); });
      map.on('styleimagemissing', () => addImages(map));
      fallbackTimer = setTimeout(() => {
        if (!map.isStyleLoaded()) { setBaseFailed(true); map.setStyle(FALLBACK_STYLE); }
      }, 8000);
      map.on('error', (e) => {
        if (!map.isStyleLoaded() && /style|Failed to fetch|NetworkError/i.test(String(e?.error?.message || ''))) {
          clearTimeout(fallbackTimer); setBaseFailed(true); map.setStyle(FALLBACK_STYLE);
        }
      });
      ['zones-fill', 'zone-center', 'zone-pin', 'foot-fill'].forEach((l) => {
        map.on('click', l, (e) => { const id = e.features?.[0]?.properties?.event_id; if (id) cb.current.onSelectEvent?.(id); });
        map.on('mouseenter', l, () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', l, () => { map.getCanvas().style.cursor = ''; });
      });
      const popup = (e, html) => new maplibregl.Popup({ closeButton: false, offset: 14 }).setLngLat(e.lngLat).setHTML(html).addTo(map);
      const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
      ['assets-icon', 'assets-dot'].forEach((l) => map.on('click', l, (e) => {
        const p = e.features[0].properties;
        popup(e, `<div style="font-weight:600">${esc(p.name)}</div><div style="color:#5a6570;font-size:12px">${esc(p.kind).replace('_', ' ')}${p.ring && p.ring !== 'null' ? ` · ${esc(p.ring)} risk ring` : ''}</div>`);
        cb.current.onSelectAsset?.(p);
      }));
      ['vehicles-icon', 'vehicles-dot'].forEach((l) => map.on('click', l, (e) => {
        const p = e.features[0].properties;
        const st = p.status === 'clear' ? 'Not heading into a zone' : p.status === 'inside' ? 'Inside risk zone' : `Heading in · ETA ${p.eta_min} min`;
        popup(e, `<div style="font-weight:600">${esc(p.id)}</div><div style="color:#5a6570;font-size:12px">${esc(p.kind).replace('_', ' ')} · ${Math.round(p.speed_kmh)} km/h · simulated</div><div style="font-size:12px;margin-top:2px">${st}</div>`);
        cb.current.onSelectVehicle?.(p);
      }));
      ['assets-icon', 'vehicles-icon', 'assets-dot', 'vehicles-dot'].forEach((l) => {
        map.on('mouseenter', l, () => { map.getCanvas().style.cursor = 'pointer'; });
        map.on('mouseleave', l, () => { map.getCanvas().style.cursor = ''; });
      });
    });
    return () => { cancelled = true; clearTimeout(fallbackTimer); markerRefs.current.forEach((m) => m.remove()); map?.remove(); mapRef.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const switchBase = (b) => {
    setBase(b); safeSet('wp_map_base', b); setBaseFailed(false);
    mapRef.current?.setStyle(styleFor(b));
  };

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
      zones: ['zones-fill', 'zones-line', 'zone-center', 'zone-pin', 'zone-glow'],
      tracks: ['track-casing', 'track-line', 'pred-line', 'track-pts', 'cone-fill', 'cone-line'],
      assets: ['assets-dot', 'assets-icon'], vehicles: ['vehicles-dot', 'vehicles-icon'], routes: ['route-current', 'route-safer'],
    };
    Object.entries(groups).forEach(([g, ids]) => {
      const vis = (show[g] ?? true) ? 'visible' : 'none';
      ids.forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', vis));
    });
  }, [ready, styleV, show]);

  // selection emphasis
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !map.getLayer('zones-line')) return;
    const sel = selectedEvent || '';
    map.setPaintProperty('zones-line', 'line-width', ['case', ['==', ['get', 'event_id'], sel], 2.4, 1.2]);
    map.setPaintProperty('zone-center', 'circle-stroke-width', ['case', ['==', ['get', 'event_id'], sel], 3.5, 2]);
  }, [ready, styleV, selectedEvent]);

  const fitData = () => {
    const map = mapRef.current;
    if (!map) return;
    const feats = [...fc(zones).features, ...(routes?.current ? [{ geometry: { coordinates: routes.current } }] : []), ...(routes?.safer ? [{ geometry: { coordinates: routes.safer } }] : [])];
    const b = boundsOf(feats);
    if (b) map.fitBounds(b, { padding: 60, maxZoom: 12.5, duration: 700 });
  };

  // camera
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    if (focus) { map.flyTo({ center: [focus.lon, focus.lat], zoom: focus.zoom ?? 11, duration: 900 }); return; }
    if (fit === 'india') { map.fitBounds(INDIA, { padding: 20, duration: 600 }); return; }
    if (Array.isArray(fit)) { map.fitBounds(fit, { padding: 50, duration: 700 }); return; }
    if (fit === 'data') fitData();
  }, [ready, fitKey, focus?.lon, focus?.lat, focus?.zoom]); // eslint-disable-line react-hooks/exhaustive-deps

  // HTML markers (you / shelter / vehicle / staging)
  useEffect(() => {
    const map = mapRef.current;
    const lib = libRef.current;
    if (!ready || !map || !lib) return;
    markerRefs.current.forEach((m) => m.remove());
    markerRefs.current = markers.map((mk) => {
      const el = document.createElement('div');
      el.className = `wp-marker wp-marker-${mk.tone || 'you'}`;
      const dot = document.createElement('span');
      dot.className = 'wp-dot';
      el.appendChild(dot);
      if (mk.label) { const t = document.createElement('span'); t.className = 'wp-label'; t.textContent = mk.label; el.appendChild(t); }
      return new lib.Marker({ element: el, anchor: 'left', offset: [-9, 0] }).setLngLat([mk.lon, mk.lat]).addTo(map);
    });
  }, [ready, JSON.stringify(markers)]); // eslint-disable-line react-hooks/exhaustive-deps

  const legendItems = legend === true ? [] : legend;

  return (
    <div className={`mapwrap ${base === 'satellite' ? 'is-satellite' : ''} ${className}`} style={{ height }}>
      <div ref={ref} style={{ position: 'absolute', inset: 0 }} aria-label="Risk map" role="region" />
      {!ready && <div className="skel" style={{ position: 'absolute', inset: 0, borderRadius: 0 }} />}
      {(title || legend) && (
        <div className="map-overlay col gap-8" style={{ left: 12, top: 12, maxWidth: 'calc(100% - 90px)' }}>
          {title && (
            <div className="map-title">
              <span className="strong">{title}</span>
              {live && <span className="live"><span className="livedot" />LIVE</span>}
            </div>
          )}
          {legend && (legendOpen
            ? <div style={{ position: 'relative', alignSelf: 'flex-start' }}>
                <RiskLegend extra={legendItems} compact={compact} />
                <button className="btn ghost sm" aria-label="Hide legend" onClick={() => setLegendOpen(false)} style={{ position: 'absolute', right: 4, top: 4, height: 24, width: 24, padding: 0 }}><Icon name="x" size={14} /></button>
              </div>
            : <button className="map-title" style={{ border: 0, cursor: 'pointer', font: 'inherit', fontSize: 13 }} onClick={() => setLegendOpen(true)}><Icon name="layers" size={15} />Legend</button>)}
        </div>
      )}
      {interactive && (
        <div className="map-overlay col gap-6" style={{ right: 10, top: 10 }}>
          <button className="map-fab" onClick={() => switchBase(base === 'satellite' ? 'streets' : 'satellite')}
            title={base === 'satellite' ? 'Switch to street map' : 'Switch to satellite'} aria-label="Switch base map">
            <Icon name="layers" size={18} />
          </button>
          <button className="map-fab" onClick={fitData} title="Zoom to risk zones" aria-label="Zoom to risk zones"><Icon name="target" size={18} /></button>
        </div>
      )}
      {baseFailed && (
        <div className="map-overlay small" style={{ left: '50%', transform: 'translateX(-50%)', bottom: 10, background: '#fff', padding: '3px 8px', borderRadius: 6, border: '1px solid var(--line)' }}>
          Base map offline · overlays shown
        </div>
      )}
      {children}
    </div>
  );
}

function Chip({ bg, border, color = '#fff', icon, pin }) {
  if (pin) {
    return (
      <svg width="18" height="22" viewBox="0 0 28 36" aria-hidden="true">
        <path d="M14 34C12 26 3 20 3 12a11 11 0 0 1 22 0c0 8-9 14-11 22z" fill={MAPC.pin} stroke="#fff" strokeWidth="2.5" />
        <circle cx="14" cy="12" r="4" fill="#fff" />
      </svg>
    );
  }
  return (
    <span style={{ width: 20, height: 20, borderRadius: 5, background: bg, border: `1.5px solid ${border || '#fff'}`, display: 'inline-grid', placeItems: 'center', color, boxShadow: '0 1px 2px rgba(0,0,0,.25)', flex: 'none' }}>
      <Icon name={icon} size={13} stroke={2.4} />
    </span>
  );
}

export function RiskLegend({ extra = [], title, collapsible = true, compact = false }) {
  const [open, setOpen] = useState(!collapsible || !compact);
  return (
    <div className="legend" style={{ minWidth: 190 }}>
      {title && <div className="t">{title}</div>}
      <div className="li"><Chip pin />Anomaly location</div>
      {[['high', 'High risk (0–3 km)'], ['moderate', 'Moderate risk (3–5 km)'], ['low', 'Lower risk (5–8 km)']].map(([k, label]) => (
        <div className="li" key={k}>
          <span style={{ width: 20, height: 14, borderRadius: 3, background: MAPC[k], opacity: 0.85, border: `1px solid ${MAPC[`${k}Line`]}`, flex: 'none' }} />{label}
        </div>
      ))}
      {extra.length > 0 && collapsible && compact && (
        <button className="btn ghost sm" style={{ height: 22, padding: '0 4px', fontSize: 11, alignSelf: 'flex-start' }} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? 'Hide layers' : `+ ${extra.length} more`}
        </button>
      )}
      {open && extra.map((x) => (
        <div className="li" key={x.label}>
          {x.line ? <span style={{ width: 20, borderTop: `3px ${x.dashed ? 'dashed' : 'solid'} ${x.color}`, flex: 'none', filter: 'drop-shadow(0 0 1px #0008)' }} />
            : x.icon ? <Chip bg={x.bg} border={x.border} color={x.fg} icon={x.icon} />
              : <span style={{ width: 14, height: 14, borderRadius: 3, background: x.color, flex: 'none' }} />}
          {x.label}
        </div>
      ))}
      <div className="tiny muted" style={{ marginTop: 2 }}>Modelled risk · not an official warning</div>
    </div>
  );
}

export const LEGEND = {
  track: { label: 'Track · dashed = projected', color: '#ffffff', line: true },
  cone: { label: 'Path uncertainty cone', color: '#ffffff', line: true, dashed: true },
  school: { label: 'School / college', icon: 'school', bg: MAPC.school },
  hospital: { label: 'Hospital', icon: 'plus', bg: '#ffffff', border: MAPC.hospital, fg: MAPC.hospital },
  rescue: { label: 'Rescue team', icon: 'shield', bg: MAPC.rescue },
  vehicleIn: { label: 'Vehicle heading into zone', icon: 'car', bg: MAPC.vehicleIn },
  vehicle: { label: 'Vehicle (simulated)', icon: 'car', bg: MAPC.vehicle },
  current: { label: 'Current route', color: MAPC.current, line: true },
  safer: { label: 'Safer route', color: MAPC.safer, line: true, dashed: true },
  ward: { label: 'Census ward in zone', color: '#3987e5' },
};
