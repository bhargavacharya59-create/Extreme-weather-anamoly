'use client';
import { useMemo, useState } from 'react';
import { useGov } from '@/components/gov/Shell';
import { PageHead, useMapLayers } from '@/components/gov/widgets';
import MapView, { RiskLegend } from '@/components/map/MapView';
import { RingStack } from '@/components/charts';
import { Card, DemoBanner, Empty, Kpi, Skeleton } from '@/components/ui';
import Icon from '@/components/ui/Icon';
import { compact, inr } from '@/lib/format';
import { useApi } from '@/lib/useApi';

export default function PopulationPage() {
  const { leadH, events, summary, selected, setSelected } = useGov();
  const layers = useMapLayers(leadH, { assets: false, vehicles: false });
  const impact = useApi(selected ? `/anomalies/${selected}/impact${leadH != null ? `?lead_h=${leadH}` : ''}` : null);
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const districts = useApi(query ? `/population/districts?q=${encodeURIComponent(query)}&limit=20` : '/population/districts?state=Karnataka&limit=40');
  const s = summary.data;
  const rows = useMemo(() => (events.data || [])
    .filter((e) => e.peak.population.total > 0)
    .map((e) => ({ label: `${e.id.replace('WX-', '')} · ${e.place.split(',')[0]}`, ...e.peak.population }))
    .sort((a, b) => b.total - a.total), [events.data]);
  const hl = impact.data?.population?.wards?.map((w) => w.ward_no) || [];
  const sel = events.data?.find((e) => e.id === selected);

  return (
    <div className="page">
      <PageHead title="Affected areas & population" sub="How many citizens live inside each anomaly's risk rings, from official Census of India 2011 data." />
      <DemoBanner>Weather events are synthetic; population figures come from the Census of India 2011 (Registrar General) and are scaled to today with an all-India projection factor.</DemoBanner>

      <div className="grid g4">
        {!s ? [0, 1, 2, 3].map((i) => <Skeleton key={i} h={100} />) : (
          <>
            <Kpi hero icon="users" label="Citizens in anomaly areas" value={compact(s.population.total)} foot={`${inr(s.population.total)} people, 0–8 km`} />
            <Kpi icon="alert" label="High-risk rings (0–3 km)" value={compact(s.population.high)} accent="var(--high-ink)" foot="closest to the anomaly core" />
            <Kpi icon="target" label="Moderate rings (3–5 km)" value={compact(s.population.moderate)} accent="var(--mod-ink)" foot="prepare to act" />
            <Kpi icon="info" label="Lower rings (5–8 km)" value={compact(s.population.low)} foot="stay informed" />
          </>
        )}
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.1fr) minmax(0, 1fr)' }}>
        <Card title="People by risk ring, per event" footer="Hover a segment for exact numbers. Events over open sea are not shown.">
          {!events.data ? <Skeleton h={220} /> : rows.length ? <RingStack rows={rows} /> : <Empty>No populated zones.</Empty>}
        </Card>
        <div className="col gap-12">
          <MapView zones={layers.zones} tracks={layers.tracks} wards={layers.wards} highlightWards={hl} selectedEvent={selected} onSelectEvent={setSelected}
            height={360} fit="data" fitKey={`pop-${selected}`} focus={sel ? { lon: sel.peak.lon, lat: sel.peak.lat, zoom: 10 } : undefined} show={{ tracks: false }}>
            <div className="map-overlay" style={{ left: 12, top: 12 }}><div className="maptag">{sel?.place || 'Select an event'}</div></div>
            <div className="map-overlay" style={{ left: 12, bottom: 12 }}>
              <RiskLegend collapsible={false} extra={[{ label: 'Ward density (people / km²)', color: '#3987e5' }, { label: 'Ward inside the zone (outlined)', color: '#184f95', stroke: '#14202b' }]} />
            </div>
          </MapView>
          <Card title={`Wards and districts · ${selected || ''}`}>
            {!impact.data ? <Skeleton h={100} /> : impact.data.population.wards?.length ? (
              <div className="scroll" style={{ maxHeight: 210 }}>
                <table className="table">
                  <thead><tr><th>BBMP ward</th><th className="r">People in zone</th><th className="r">Share of ward</th></tr></thead>
                  <tbody>{impact.data.population.wards.map((w) => <tr key={w.ward_no}><td className="small">{w.ward_name}</td><td className="r num">{inr(w.people)}</td><td className="r num small">{Math.round(w.share_of_ward * 100)}%</td></tr>)}</tbody>
                </table>
              </div>
            ) : impact.data.population.districts?.length ? (
              <table className="table"><thead><tr><th>District</th><th>State</th><th className="r">People in zone</th></tr></thead>
                <tbody>{impact.data.population.districts.map((d) => <tr key={d.district}><td>{d.district}</td><td className="small muted">{d.state}</td><td className="r num">{inr(d.people)}</td></tr>)}</tbody></table>
            ) : <Empty icon="globe">No resident population (open sea).</Empty>}
          </Card>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)' }}>
        <Card title="Census of India 2011 · district lookup" action={
          <form className="row gap-6" onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }}>
            <label htmlFor="dq" className="sr-only">District</label>
            <input id="dq" className="input" style={{ height: 36, width: 220 }} placeholder="Search a district…" value={q} onChange={(e) => setQ(e.target.value)} />
            <button className="btn sm"><Icon name="search" size={15} />Search</button>
          </form>}>
          {!districts.data ? <Skeleton h={160} /> : !districts.data.length ? <Empty>No district matches “{query}”.</Empty> : (
            <div className="scroll" style={{ maxHeight: 320 }}>
              <table className="table">
                <thead><tr><th>District</th><th>State</th><th className="r">Population 2011</th><th className="r">Estimated today</th><th className="r">Area km²</th><th className="r">Density /km²</th></tr></thead>
                <tbody>{districts.data.map((d) => (
                  <tr key={`${d.state}-${d.district}`}><td className="strong small">{d.district}</td><td className="small muted">{d.state}</td>
                    <td className="r num">{inr(d.population_2011)}</td><td className="r num">{inr(d.population_now)}</td><td className="r num small">{inr(d.area_km2)}</td><td className="r num small">{inr(d.density_2011)}</td></tr>))}</tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="How the count is made">
          <ol className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
            <li>Each risk ring is sampled on a 250 m grid.</li>
            <li>Every sample takes the density of the Census unit it falls in: the <b>BBMP ward</b> in Bengaluru (198 wards), otherwise the <b>district</b> (640 districts).</li>
            <li>Density × area gives residents per ring; the total is scaled from 2011 to today (×1.18, all-India RGI projection).</li>
            <li>Results are estimates at the resolution of the source; a finer grid (e.g. WorldPop 100 m) can be plugged in.</li>
          </ol>
          <div className="divider" style={{ margin: '12px 0' }} />
          <div className="small muted">Sources: Office of the Registrar General &amp; Census Commissioner, India (Census 2011 PCA); BBMP ward boundaries via DataMeet (CC BY-SA 2.5 IN).</div>
        </Card>
      </div>
    </div>
  );
}
