'use client';
import { useMemo, useState } from 'react';
import { useGov } from '@/components/gov/Shell';
import { PageHead } from '@/components/gov/widgets';
import MapView, { LEGEND, RiskLegend } from '@/components/map/MapView';
import { Card, DemoBanner, Kpi, Segmented, Skeleton } from '@/components/ui';
import Icon, { KIND_ICON } from '@/components/ui/Icon';
import { KIND_LABEL } from '@/lib/format';
import { useApi } from '@/lib/useApi';

export default function VehiclesPage() {
  const { selected, setSelected, events } = useGov();
  const { data } = useApi('/vehicles');
  const zones = useApi('/maps/risk-zones');
  const vfc = useApi(selected ? `/maps/vehicles?event_id=${selected}` : '/maps/vehicles');
  const [kind, setKind] = useState('all');
  const [sel, setSel] = useState(null);
  const toward = data?.toward || [];
  const list = useMemo(() => toward.filter((v) => (kind === 'all' || v.kind === kind) && (!selected || v.event_id === selected)), [toward, kind, selected]);
  const ev = events.data?.find((e) => e.id === selected);
  const inside = toward.filter((v) => v.status === 'inside').length;
  const buses = toward.filter((v) => v.kind === 'bus').length;

  return (
    <div className="page">
      <PageHead title="Vehicles & transport" sub="Buses, cars and trucks inside or heading into a risk zone are alerted automatically, with a safer route.">
        <label className="small muted row gap-6">Event
          <select className="select" style={{ height: 38 }} value={selected || ''} onChange={(e) => setSelected(e.target.value || null)}>
            {(events.data || []).filter((e) => e.peak.counts.vehicles_toward > 0).map((e) => <option key={e.id} value={e.id}>{e.id} · {e.place.split(',')[0]}</option>)}
          </select>
        </label>
      </PageHead>
      <DemoBanner>Vehicle positions are a simulated GPS feed for the prototype; authorised fleet feeds (KSRTC / BMTC, logistics) can replace it.</DemoBanner>
      <div className="grid g4">
        {!data ? [0, 1, 2, 3].map((i) => <Skeleton key={i} h={96} />) : (
          <>
            <Kpi icon="bus" label="Vehicles tracked" value={data.tracked} foot="simulated, near active zones" />
            <Kpi icon="nav" label="Heading into zones" value={toward.length - inside} accent="var(--mod-ink)" foot="projected entry within 60 min" />
            <Kpi icon="alert" label="Already inside a zone" value={inside} accent="var(--high-ink)" foot="told to stop at a safe place" />
            <Kpi icon="bell" label="Buses notified" value={buses} foot="driver app + fleet control" />
          </>
        )}
      </div>
      <Card>
        <div className="row gap-12" style={{ alignItems: 'flex-start' }}>
          <Icon name="info" size={18} style={{ color: 'var(--accent)', marginTop: 2 }} />
          <div className="small" style={{ lineHeight: 1.6 }}>
            <b>Detection rule.</b> A vehicle is flagged when it is inside any ring, or when its heading points within 30° of the zone centre <i>and</i> its path over the next 60 minutes at current speed enters a ring. Flagged drivers get an in-app alert (spoken while driving) with a safer route around the outer ring; fleet control sees whether they rerouted.
          </div>
        </div>
      </Card>
      <div className="row-top" style={{ gap: 16 }}>
        <div className="grow">
          <MapView zones={zones.data} vehicles={vfc.data} height={560} fit="data" fitKey={`veh-${selected}`}
            focus={sel ? { lon: sel.lon, lat: sel.lat, zoom: 12 } : ev ? { lon: ev.peak.lon, lat: ev.peak.lat, zoom: 9.6 } : undefined}
            markers={sel ? [{ lon: sel.lon, lat: sel.lat, label: sel.id, tone: 'vehicle' }] : []} show={{ tracks: false }}
            title={`${(ev?.place || 'All zones').split(',')[0]} · Vehicles`} legend={[LEGEND.vehicleIn, LEGEND.vehicle]}>
          </MapView>
        </div>
        <div style={{ width: 480, flex: '0 0 480px' }} className="col gap-8">
          <Segmented label="Vehicle type" value={kind} onChange={setKind} options={[{ value: 'all', label: 'All' }, { value: 'bus', label: 'Buses' }, { value: 'car', label: 'Cars' }, { value: 'truck', label: 'Trucks' }, { value: 'two_wheeler', label: '2-wheelers' }]} />
          <section className="card scroll" style={{ maxHeight: 510 }}>
            <table className="table">
              <thead><tr><th>Vehicle</th><th>Status</th><th className="r">Dist.</th><th className="r">ETA</th><th>Alert</th></tr></thead>
              <tbody>
                {list.map((v) => (
                  <tr key={v.id} className={`click ${sel?.id === v.id ? 'sel' : ''}`} onClick={() => setSel(v)}>
                    <td className="nowrap"><div className="row gap-6"><Icon name={KIND_ICON[v.kind]} size={15} /><span className="mono small strong">{v.id}</span></div><div className="tiny muted">{KIND_LABEL[v.kind]} · {v.operator} · {Math.round(v.speed_kmh)} km/h</div></td>
                    <td>{v.status === 'inside' ? <span className="badge high"><span className="dot" />Inside</span> : <span className="badge moderate"><span className="dot" />Heading in</span>}</td>
                    <td className="r num small">{v.distance_km} km</td>
                    <td className="r num small">{v.eta_min ? `${v.eta_min} min` : 'now'}</td>
                    <td><span className="badge good"><Icon name="check" size={12} />Sent</span></td>
                  </tr>
                ))}
                {!list.length && <tr><td colSpan={5} className="small muted" style={{ textAlign: 'center', padding: 24 }}>No vehicles match.</td></tr>}
              </tbody>
            </table>
          </section>
        </div>
      </div>
    </div>
  );
}
