'use client';
import { useState } from 'react';
import Link from 'next/link';
import Icon, { KIND_ICON, TYPE_ICON } from '@/components/ui/Icon';
import { Card, Empty, RingBadge, SeverityBadge, Skeleton, Stat, toast } from '@/components/ui';
import { api, download } from '@/lib/api';
import { compact, directionWord, inr, KIND_LABEL, pct, RISK, ROLE_LABEL, TYPE_LABEL } from '@/lib/format';
import { invalidate, useApi } from '@/lib/useApi';

export const shortTime = (s) => (s || '').replace(' IST', '').replace(',', '');

export function useMapLayers(leadH, { assets = true, vehicles = true, wards = true, eventId } = {}) {
  const zones = useApi(`/maps/risk-zones${leadH != null ? `?lead_h=${leadH}` : ''}`);
  const tracks = useApi('/maps/tracks');
  const a = useApi(assets ? `/maps/assets${eventId ? `?event_id=${eventId}` : ''}` : null);
  const v = useApi(vehicles ? `/maps/vehicles${eventId ? `?event_id=${eventId}` : ''}` : null);
  const w = useApi(wards ? '/maps/wards' : null);
  return { zones: zones.data, tracks: tracks.data, assets: a.data, vehicles: v.data, wards: w.data, loading: zones.loading };
}

export function EventStrip({ events, selected, onSelect, leadH }) {
  if (!events) return <div className="row gap-8">{[0, 1, 2, 3].map((i) => <Skeleton key={i} h={62} w={220} />)}</div>;
  const list = events.filter((e) => leadH == null || (e.first_lead_h <= leadH && e.last_lead_h >= leadH));
  if (!list.length) return <div className="card card-pad small muted">No anomalies are forecast to be active at this time.</div>;
  return (
    <div className="row gap-8" style={{ overflowX: 'auto', paddingBottom: 2 }} role="listbox" aria-label="Active anomalies">
      {list.map((e) => {
        const on = e.id === selected;
        return (
          <button key={e.id} role="option" aria-selected={on} onClick={() => onSelect(e.id)}
            className="card" style={{ flex: '0 0 auto', minWidth: 214, textAlign: 'left', padding: '10px 12px', cursor: 'pointer', font: 'inherit', color: 'inherit',
              borderColor: on ? 'var(--ink)' : 'var(--line)', boxShadow: on ? '0 0 0 1px var(--ink)' : undefined }}>
            <div className="row between" style={{ gap: 8 }}>
              <span className="row gap-6 small strong"><Icon name={TYPE_ICON[e.type]} size={15} />{TYPE_LABEL[e.type]}</span>
              <SeverityBadge severity={e.severity}>{e.severity}</SeverityBadge>
            </div>
            <div className="small" style={{ marginTop: 5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 240 }}>{e.place}</div>
            <div className="row between tiny muted" style={{ marginTop: 2 }}>
              <span className="mono">{e.id}</span><span>{compact(e.peak.population.total)} people</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

export function EventPanel({ eventId, height }) {
  const { data: e, loading } = useApi(eventId ? `/anomalies/${eventId}` : null);
  const [busy, setBusy] = useState(false);
  if (!eventId) return <Card className="grow"><Empty icon="target" title="Select an anomaly">Click a risk zone on the map or an event above.</Empty></Card>;
  if (!e || loading && !e) return <Card><div className="col"><Skeleton h={22} w="60%" /><Skeleton h={120} /><Skeleton h={80} /></div></Card>;
  const pk = e.peak;
  return (
    <section className="card" style={{ display: 'flex', flexDirection: 'column', height, minWidth: 0 }}>
      <div style={{ padding: '16px 18px 12px', borderBottom: '1px solid var(--line-2)' }}>
        <div className="row between" style={{ alignItems: 'flex-start' }}>
          <div className="col gap-4" style={{ minWidth: 0 }}>
            <span className="mono tiny muted">{e.id} · {e.data_source === 'synthetic_demo' ? 'synthetic scenario' : e.data_source}</span>
            <h2 className="row gap-8" style={{ fontSize: 19 }}><Icon name={TYPE_ICON[e.type]} size={20} />{TYPE_LABEL[e.type]} anomaly</h2>
            <span className="small muted">{e.place}</span>
          </div>
          <SeverityBadge severity={e.severity} solid={e.severity === 'High'}>{e.severity.toUpperCase()}</SeverityBadge>
        </div>
      </div>
      <div style={{ padding: '12px 18px', overflowY: 'auto', flex: 1 }} className="col">
        <div className="grid g2" style={{ gap: 8 }}>
          <Stat k="Forecast window" v={<span style={{ fontSize: 13 }}>{shortTime(e.window.start_local)} →<br />{shortTime(e.window.end_local)}</span>} />
          <Stat k="Movement" v={`${directionWord(e.motion.direction)}, ${Math.round(e.motion.speed_kmh)} km/h`} />
          <Stat k="Ensemble agreement" v={`${pct(e.probability)} of scenarios`} />
          <Stat k="Path uncertainty" v={`± ${Math.round(pk.uncertainty_km)} km`} />
          <Stat k="Citizens within 8 km" v={<span className="num">{inr(pk.population.total)}</span>} sub={`${inr(pk.population.high)} in high ring`} />
          <Stat k="Official IMD warning" v={e.official_warning ? 'Linked' : 'None linked'} />
        </div>
        <div className="col gap-4">
          <div className="small strong">Why it was flagged</div>
          <p className="small" style={{ color: 'var(--ink-2)', lineHeight: 1.55 }}>{e.why.text}</p>
        </div>
        <div className="col gap-4">
          <div className="small strong row gap-6">AI situation summary <span className="muted" style={{ fontWeight: 400 }}>· {e.summary.generated_by === 'gemini' ? 'Gemini draft, verify' : 'template'}</span></div>
          <p className="small" style={{ lineHeight: 1.55, background: 'var(--accent-tint)', borderRadius: 8, padding: '10px 12px' }}>{e.summary.text}</p>
        </div>
      </div>
      <div className="row" style={{ padding: '12px 18px', borderTop: '1px solid var(--line-2)', gap: 8 }}>
        <Link className="btn primary grow" href={`/gov/anomalies/${e.id}`}>Open full details<Icon name="arrowR" size={16} /></Link>
        <button className="btn" disabled={busy} onClick={async () => { setBusy(true); try { await download(`/reports/${e.id}.pdf`, `${e.id}.pdf`); } finally { setBusy(false); } }}>
          <Icon name="download" size={16} />PDF
        </button>
      </div>
    </section>
  );
}

export function PopulationCard({ eventId, leadH }) {
  const { data, loading, error } = useApi(eventId ? `/anomalies/${eventId}/impact${leadH != null ? `?lead_h=${leadH}` : ''}` : null);
  const pop = data?.population;
  return (
    <Card title="Citizens in anomaly area" action={<span className="mono tiny muted">{eventId}</span>}
      footer={pop ? `Source: ${pop.sources?.join(', ')}; projected ×${pop.projection_factor} to today. Estimates at data resolution.` : null}>
      {error ? <div className="small muted">{error.status === 404 ? 'This event is not active at the selected time.' : error.message}</div>
        : !pop || loading && !pop ? <div className="col"><Skeleton h={18} /><Skeleton h={18} /><Skeleton h={18} /></div> : (
          <div className="col gap-8">
            <div className="row between" style={{ alignItems: 'baseline' }}>
              <span className="num" style={{ fontSize: 28, fontWeight: 600 }}>{inr(pop.total)}</span>
              <span className="small muted">{data.valid_local}</span>
            </div>
            <div>
              {['high', 'moderate', 'low'].map((r) => (
                <div className="ringrow" key={r}>
                  <span><span className="swatch" style={{ background: RISK[r].fill }} />{RISK[r].label} · {RISK[r].range}</span>
                  <span className="num strong">{inr(pop[r])}</span>
                </div>
              ))}
              <div className="ringrow"><span className="muted">Households (est.)</span><span className="num">{inr(pop.households)}</span></div>
              <div className="ringrow"><span className="muted">{pop.wards_count ? 'BBMP wards intersected' : 'Districts'}</span>
                <span className="num">{pop.wards_count || pop.districts?.map((d) => d.district).join(', ') || '—'}</span></div>
            </div>
          </div>
        )}
    </Card>
  );
}

export function AlertQueue({ eventId, limit = 5, compactView = true }) {
  const { data, reload } = useApi('/alerts?status=draft', { poll: 30000 });
  const [busy, setBusy] = useState(null);
  const list = (data || []).filter((a) => !eventId || a.event_id === eventId).slice(0, limit);
  const approve = async (a) => {
    setBusy(a.alert_id);
    try {
      await api(`/alerts/${a.alert_id}/approve`, { method: 'POST' });
      toast(`Approved and sent: ${ROLE_LABEL[a.role]} · ${a.event_id}`);
      invalidate('/alerts'); invalidate('/dashboard'); reload();
    } catch (e) { toast(e.message); } finally { setBusy(null); }
  };
  return (
    <Card title="Alert approval queue" action={<Link className="small" href="/gov/alerts">All alerts</Link>}>
      {!data ? <div className="col"><Skeleton h={44} /><Skeleton h={44} /></div>
        : !list.length ? <Empty icon="check" title="Nothing waiting">All drafts for this event are reviewed.</Empty> : (
          <div className="col gap-8">
            {list.map((a) => (
              <div key={a.alert_id} className="row" style={{ border: '1px solid var(--line-2)', borderRadius: 8, padding: '8px 10px' }}>
                <div className="grow">
                  <div className="small strong">{ROLE_LABEL[a.role]} <span className="muted" style={{ fontWeight: 400 }}>· {a.event_id}</span></div>
                  <div className="tiny muted">{inr(a.recipients)} recipients · {a.channels.join(' + ')} · {a.generated_by}</div>
                </div>
                <button className="btn primary sm" disabled={busy === a.alert_id} onClick={() => approve(a)}>{busy === a.alert_id ? 'Sending…' : 'Approve'}</button>
              </div>
            ))}
          </div>
        )}
    </Card>
  );
}

export function VehiclesCard({ eventId, limit = 6 }) {
  const { data } = useApi('/vehicles');
  const list = (data?.toward || []).filter((v) => !eventId || v.event_id === eventId);
  return (
    <Card title="Vehicles moving toward the zone" action={<span className="badge neutral">simulated</span>}
      footer="Flagged when heading within 30° of a zone and projected to enter it within 60 minutes.">
      {!data ? <Skeleton h={120} /> : !list.length ? <Empty icon="bus">No vehicles heading into this zone.</Empty> : (
        <table className="table">
          <thead><tr><th>Vehicle</th><th>Status</th><th className="r">Distance</th><th className="r">ETA</th></tr></thead>
          <tbody>
            {list.slice(0, limit).map((v) => (
              <tr key={v.id}>
                <td className="nowrap"><span className="row gap-6"><Icon name={KIND_ICON[v.kind]} size={15} /><span className="mono small">{v.id}</span></span></td>
                <td>{v.status === 'inside' ? <span className="badge high"><span className="dot" />Inside</span> : <span className="badge moderate"><span className="dot" />Heading in</span>}</td>
                <td className="r num">{v.distance_km} km</td>
                <td className="r num">{v.eta_min === 0 ? 'now' : `${v.eta_min} min`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {list.length > limit && <div className="small" style={{ marginTop: 8 }}><Link href="/gov/vehicles">+ {list.length - limit} more vehicles</Link></div>}
    </Card>
  );
}

export function AssetTable({ assets, showEvent = false, onRow, selected }) {
  if (!assets?.length) return <Empty icon="school">No institutions inside the risk zone.</Empty>;
  return (
    <table className="table">
      <thead><tr><th>Institution</th><th>Type</th><th>Risk ring</th><th className="r">Distance</th><th className="r">Capacity</th>{showEvent && <th>Event</th>}{showEvent && <th>Acknowledged</th>}</tr></thead>
      <tbody>
        {assets.map((a) => (
          <tr key={`${a.id}-${a.event_id || ''}`} className={`${onRow ? 'click' : ''} ${selected === a.id ? 'sel' : ''}`} onClick={() => onRow?.(a)}>
            <td><div className="strong small">{a.name}</div><div className="tiny muted mono">{a.id}</div></td>
            <td className="small"><span className="row gap-6"><Icon name={KIND_ICON[a.kind]} size={15} />{KIND_LABEL[a.kind]}</span></td>
            <td><RingBadge ring={a.ring} /></td>
            <td className="r num small">{a.distance_km} km</td>
            <td className="r num small">{inr(a.capacity)}{a.kind === 'hospital' ? ' beds' : a.kind === 'school' ? ' students' : ' staff'}</td>
            {showEvent && <td className="mono small">{a.event_id}</td>}
            {showEvent && <td>{a.acknowledged ? <span className="badge good"><Icon name="check" size={12} />Yes</span> : <span className="badge neutral">Pending</span>}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function PageHead({ title, sub, children }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      <div className="row gap-8 wrap">{children}</div>
    </div>
  );
}
