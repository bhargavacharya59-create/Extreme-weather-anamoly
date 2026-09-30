'use client';
import { useEffect, useState } from 'react';
import { useGov } from '@/components/gov/Shell';
import { EventPanel } from '@/components/gov/widgets';
import MapView, { LEGEND, RiskLegend } from '@/components/map/MapView';
import Icon from '@/components/ui/Icon';
import { useApi } from '@/lib/useApi';
import { hoursLabel, leadToDate } from '@/lib/format';

const LAYERS = [
  { key: 'zones', label: 'Risk rings (3 / 5 / 8 km)' },
  { key: 'footprints', label: 'Anomaly footprint' },
  { key: 'tracks', label: 'Tracks & uncertainty cone' },
  { key: 'grid', label: 'Anomaly field (σ)' },
  { key: 'wards', label: 'Census wards (Bengaluru)' },
  { key: 'assets', label: 'Schools, hospitals, rescue' },
  { key: 'vehicles', label: 'Vehicles (simulated)' },
];

export default function RiskMapPage() {
  const { selected, setSelected, run } = useGov();
  const [lead, setLead] = useState(72);
  const [playing, setPlaying] = useState(false);
  const [show, setShow] = useState({ zones: true, footprints: true, tracks: true, grid: true, wards: false, assets: true, vehicles: false });
  const [panel, setPanel] = useState(true);
  const [fitKey, setFitKey] = useState(0);
  const zones = useApi(`/maps/risk-zones?lead_h=${lead}`);
  const grid = useApi(show.grid ? `/weather/anomaly-grid?lead_h=${lead}&thr=1.8` : null);
  const tracks = useApi('/maps/tracks');
  const assets = useApi(show.assets ? '/maps/assets' : null);
  const vehicles = useApi(show.vehicles ? '/maps/vehicles' : null);
  const wards = useApi(show.wards ? '/maps/wards' : null);
  const events = useApi(`/anomalies?lead_h=${lead}`);

  useEffect(() => {
    if (!playing) return undefined;
    const t = setInterval(() => setLead((l) => (l >= 240 ? 0 : l + 6)), 1100);
    return () => clearInterval(t);
  }, [playing]);

  return (
    <div className="page" style={{ paddingBottom: 20 }}>
      <div className="row between wrap">
        <div>
          <h1>Risk map</h1>
          <div className="sub small muted">Drag the timeline or press play to watch anomalies form, move and fade over the next 10 days.</div>
        </div>
        <div className="row gap-8">
          <button className="btn" onClick={() => setFitKey((k) => k + 1)}><Icon name="globe" size={16} />All India</button>
          <button className="btn" onClick={() => setPanel((p) => !p)}><Icon name="layers" size={16} />{panel ? 'Hide details' : 'Show details'}</button>
        </div>
      </div>

      <div className="timeline" role="group" aria-label="Forecast timeline">
        <button className="btn dark iconbtn" onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play'}>
          <Icon name={playing ? 'pause' : 'play'} size={16} />
        </button>
        <div className="col gap-4" style={{ width: 170 }}>
          <span className="strong">{hoursLabel(lead)}</span>
          <span className="tiny muted">{run ? `${leadToDate(run.issue_time, lead)} IST` : ''}</span>
        </div>
        <label className="sr-only" htmlFor="lead">Forecast hour</label>
        <input id="lead" type="range" min="0" max="240" step="6" value={lead} onChange={(e) => { setPlaying(false); setLead(+e.target.value); }} />
        <div className="row tiny muted" style={{ gap: 18, width: 260, justifyContent: 'space-between' }}>
          {[0, 48, 96, 144, 192, 240].map((h) => <button key={h} className="btn ghost sm" style={{ height: 24, padding: '0 4px' }} onClick={() => { setPlaying(false); setLead(h); }}>D{h / 24}</button>)}
        </div>
        <span className="badge neutral nowrap">{events.data ? `${events.data.length} active` : '…'}</span>
      </div>

      <div className="row-top" style={{ gap: 16 }}>
        <div className="grow">
          <MapView zones={zones.data} tracks={tracks.data} grid={grid.data} assets={assets.data} vehicles={vehicles.data} wards={wards.data}
            show={show} selectedEvent={selected} onSelectEvent={setSelected} height="calc(100vh - 250px)" fit="india" fitKey={fitKey}>
            <div className="map-overlay" style={{ left: 12, top: 12 }}>
              <div className="layerpanel">
                <div className="strong small row gap-6"><Icon name="layers" size={15} />Layers</div>
                {LAYERS.map((l) => (
                  <label key={l.key} className="check small">
                    <input type="checkbox" checked={!!show[l.key]} onChange={(e) => setShow((s) => ({ ...s, [l.key]: e.target.checked }))} />
                    {l.label}
                  </label>
                ))}
              </div>
            </div>
            <div className="map-overlay" style={{ left: 12, bottom: 12 }}>
              <RiskLegend compact extra={[LEGEND.school, LEGEND.hospital, LEGEND.rescue, LEGEND.vehicleIn, LEGEND.vehicle, LEGEND.track, LEGEND.cone]} />
            </div>
          </MapView>
        </div>
        {panel && (
          <div style={{ width: 380, flex: '0 0 380px' }}>
            <EventPanel eventId={selected} height="calc(100vh - 250px)" />
          </div>
        )}
      </div>
    </div>
  );
}
