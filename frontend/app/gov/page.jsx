'use client';
import { useState } from 'react';
import { useGov } from '@/components/gov/Shell';
import { AlertQueue, EventPanel, EventStrip, PageHead, PopulationCard, useMapLayers, VehiclesCard } from '@/components/gov/widgets';
import MapView, { LEGEND, RiskLegend } from '@/components/map/MapView';
import { DemoBanner, ErrorBox, Kpi, Skeleton } from '@/components/ui';
import { download } from '@/lib/api';
import { compact, hoursLabel, inr } from '@/lib/format';
import Icon from '@/components/ui/Icon';

export default function Overview() {
  const { leadH, selected, setSelected, summary, events } = useGov();
  const s = summary.data;
  const layers = useMapLayers(leadH);
  const [fitKey, setFitKey] = useState(1);
  const sel = events.data?.find((e) => e.id === selected);

  return (
    <div className="page">
      <PageHead title="Operations overview" sub={`Showing ${leadH == null ? 'each event at its highest-impact time' : `forecast at ${hoursLabel(leadH)}`} · all figures update with the time selector`}>
        <button className="btn" onClick={() => download('/reports/situation.pdf', 'weatherpulse_situation_report.pdf')}><Icon name="download" size={16} />Situation report (PDF)</button>
      </PageHead>
      <DemoBanner />
      <ErrorBox error={summary.error} onRetry={summary.reload} />

      <div className="grid" style={{ gridTemplateColumns: '1fr 1.7fr 1fr 1fr 1fr' }}>
        {!s ? [0, 1, 2, 3, 4].map((i) => <Skeleton key={i} h={112} />) : (
          <>
            <Kpi label="Active anomalies" icon="alert" value={s.active}
              foot={<><span style={{ color: 'var(--high-ink)', fontWeight: 600 }}>{s.by_severity.High} High</span> · <span style={{ color: 'var(--mod-ink)', fontWeight: 600 }}>{s.by_severity.Moderate} Moderate</span> · {s.by_severity.Low} Low</>} />
            <Kpi hero label={<>Citizens in anomaly areas <span style={{ marginLeft: 'auto' }} className="tiny">0–8 km rings</span></>} icon="users"
              value={inr(s.population.total)}
              foot={<><span className="hi" style={{ fontWeight: 600 }}>{compact(s.population.high)} in high-risk rings</span> · Census of India 2011, projected</>} />
            <Kpi label="Schools / colleges" icon="school" value={s.schools} foot="inside risk rings" />
            <Kpi label="Hospitals" icon="hospital" value={s.hospitals} foot={`${s.rescue_teams} rescue units in zones`} />
            <Kpi label="Vehicles heading in" icon="bus" value={s.vehicles_toward} accent="var(--mod-ink)" foot={`of ${inr(s.vehicles_tracked)} tracked (simulated)`} />
          </>
        )}
      </div>

      <EventStrip events={events.data} selected={selected} leadH={leadH} onSelect={(id) => { setSelected(id); setFitKey((k) => k + 1); }} />

      <div className="row-top" style={{ gap: 16 }}>
        <div className="grow">
          <MapView zones={layers.zones} tracks={layers.tracks} assets={layers.assets} vehicles={layers.vehicles} wards={layers.wards}
            selectedEvent={selected} onSelectEvent={(id) => { setSelected(id); }} height={580} fit="data" fitKey={`${fitKey}-${!!layers.zones}-${leadH}`}
            focus={sel && fitKey > 0 ? { lon: sel.peak.lon, lat: sel.peak.lat, zoom: 10.2 } : undefined}
            show={{ grid: false }}>
            <div className="map-overlay" style={{ left: 12, top: 12 }}>
              <div className="maptag">{sel ? sel.place : 'India · all active anomalies'}</div>
            </div>
            <div className="map-overlay" style={{ left: 12, bottom: 12 }}>
              <RiskLegend extra={[LEGEND.track, LEGEND.cone, LEGEND.school, LEGEND.hospital, LEGEND.rescue, LEGEND.vehicleIn]} />
            </div>
            <div className="map-overlay row gap-6" style={{ right: 52, top: 12 }}>
              <button className="btn sm" onClick={() => setFitKey((k) => k + 1)} disabled={!sel || fitKey > 0}><Icon name="target" size={15} />Zoom to selected</button>
              <button className="btn sm" onClick={() => setFitKey(0)} disabled={fitKey === 0}><Icon name="globe" size={15} />All India</button>
            </div>
          </MapView>
        </div>
        <div style={{ width: 400, flex: '0 0 400px' }}>
          <EventPanel eventId={selected} height={580} />
        </div>
      </div>

      <div className="grid g3">
        <PopulationCard eventId={selected} leadH={leadH} />
        <AlertQueue eventId={null} />
        <VehiclesCard eventId={selected} />
      </div>
    </div>
  );
}
