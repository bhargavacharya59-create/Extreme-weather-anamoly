'use client';
import { useState } from 'react';
import MapView from '@/components/map/MapView';
import RoleHeader from '@/components/RoleHeader';
import { Empty, ErrorBox, Modal, SeverityBadge, Skeleton, toast } from '@/components/ui';
import Icon from '@/components/ui/Icon';
import { api } from '@/lib/api';
import { useRequireRole } from '@/lib/auth';
import { inr, TYPE_LABEL } from '@/lib/format';
import { useApi } from '@/lib/useApi';

const FLOW = [['issued', 'Issued'], ['accepted', 'Accepted'], ['en_route', 'En route'], ['on_site', 'On site'], ['completed', 'Completed']];

export default function RescueApp() {
  const { allowed } = useRequireRole('rescue', 'official');
  const { data, error, reload } = useApi(allowed ? '/rescue/orders' : null);
  const [idx, setIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [constraint, setConstraint] = useState(false);
  const [note, setNote] = useState('');
  const o = data?.[idx];
  const zones = useApi(o ? '/maps/risk-zones' : null);
  const step = o ? FLOW.findIndex(([k]) => k === o.status) : 0;

  const setStatus = async (status, n = '') => {
    setBusy(true);
    try { await api(`/rescue/orders/${o.order_id}/status`, { method: 'POST', body: { status, note: n } }); toast(`Order ${o.order_id}: ${status.replace('_', ' ')}`); reload(); }
    catch (e) { toast(e.message); } finally { setBusy(false); }
  };
  const next = FLOW[Math.min(step + 1, FLOW.length - 1)];
  const zoneFc = zones.data && o && { ...zones.data, features: zones.data.features.filter((f) => f.properties.event_id === o.event_id && ['low', 'moderate', 'high'].includes(f.properties.ring)) };

  return (
    <div className="app-mobile">
      <div className="app-col">
        <RoleHeader portal="Rescue team" />
        <div style={{ background: '#1e6b3f', color: '#fff', padding: '14px 18px' }}>
          <div className="tiny" style={{ opacity: 0.85 }}>{o ? `${o.unit_name}` : 'Your unit'} · demo</div>
          <div style={{ fontSize: 20, fontWeight: 600 }}>{data ? `${data.length} pre-position order${data.length === 1 ? '' : 's'}` : 'Loading orders…'}</div>
        </div>
        <div className="m-body">
          <ErrorBox error={error} onRetry={reload} />
          {!data ? <><Skeleton h={180} /><Skeleton h={220} /></> : !data.length ? <Empty icon="shield" title="No orders">No high-risk events need pre-positioning right now.</Empty> : (
            <>
              {data.length > 1 && (
                <div className="row gap-6" style={{ overflowX: 'auto' }}>
                  {data.map((x, i) => <button key={x.order_id} className={`btn sm ${i === idx ? 'dark' : ''}`} onClick={() => setIdx(i)}>{x.order_id.replace('ORD-', '')}</button>)}
                </div>
              )}
              <section className="m-card col gap-10">
                <div className="row between"><span className="mono tiny muted">{o.order_id} · {o.event_id}</span><SeverityBadge severity={o.severity} solid={o.severity === 'High'}>{o.severity.toUpperCase()}</SeverityBadge></div>
                <div style={{ fontSize: 18, fontWeight: 600, lineHeight: 1.3 }}>Stage near {o.place.split(',')[0]} by {o.stage_by_local.replace(' IST', '')}</div>
                <div className="small" style={{ color: 'var(--ink-2)', lineHeight: 1.5 }}>{TYPE_LABEL[o.type]} expected {o.window.start_local} to {o.window.end_local}.</div>
                <div className="grid g3" style={{ gap: 8 }}>
                  <div className="stat"><div className="k">Distance</div><div className="v">{o.distance_km} km</div></div>
                  <div className="stat"><div className="k">Drive</div><div className="v">{o.drive_min} min</div></div>
                  <div className="stat"><div className="k">In high ring</div><div className="v num">{inr(o.people_high)}</div></div>
                </div>
              </section>

              <MapView zones={zoneFc} height={230} fit="data" fitKey={o.order_id} interactive={false} title="Assigned zone" markers={[{ lon: o.stage_at.lon, lat: o.stage_at.lat, label: 'Staging point', tone: 'stage' }]}>
              </MapView>

              <section className="m-card col gap-8">
                <h3>Status</h3>
                <div className="row" style={{ gap: 4 }}>
                  {FLOW.map(([k, label], i) => (
                    <div key={k} className="col grow" style={{ alignItems: 'center', gap: 4 }}>
                      <div style={{ height: 6, width: '100%', borderRadius: 3, background: i <= step ? '#1e6b3f' : 'var(--sunken)' }} />
                      <span className="tiny" style={{ color: i <= step ? 'var(--ink)' : 'var(--faint)', fontWeight: i === step ? 600 : 400 }}>{label}</span>
                    </div>
                  ))}
                </div>
                {o.status === 'constraint' && <div className="banner small">Constraint reported: {o.status_note}</div>}
              </section>

              {o.priorities?.length > 0 && (
                <section className="m-card col gap-6">
                  <h3>Priority sites</h3>
                  {o.priorities.map((p) => <div key={p} className="row small gap-8"><Icon name="flag" size={15} style={{ color: 'var(--high)' }} />{p}</div>)}
                </section>
              )}
              <section className="m-card col gap-6">
                <h3>Orders</h3>
                <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>{o.guidance.map((g) => <li key={g}>{g}</li>)}</ul>
              </section>

              {o.status !== 'completed' && (
                <button className="btn lg block" style={{ height: 54, background: '#1e6b3f', borderColor: '#1e6b3f', color: '#fff', fontWeight: 700 }} disabled={busy}
                  onClick={() => setStatus(o.status === 'constraint' ? 'accepted' : next[0])}>
                  {o.status === 'issued' ? 'Accept order' : o.status === 'constraint' ? 'Resume order' : `Mark ${next[1].toLowerCase()}`}
                </button>
              )}
              <button className="btn lg block" onClick={() => setConstraint(true)}>Report a constraint</button>
            </>
          )}
        </div>
      </div>
      <Modal open={constraint} onClose={() => setConstraint(false)} title="Report a constraint"
        footer={<><button className="btn" onClick={() => setConstraint(false)}>Cancel</button><button className="btn primary" onClick={() => { setStatus('constraint', note || 'Constraint reported'); setConstraint(false); }}>Send to control room</button></>}>
        <div className="field"><label htmlFor="c">What is blocking the order?</label>
          <textarea id="c" className="textarea" rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. one boat under repair, road to staging point flooded" /></div>
      </Modal>
    </div>
  );
}
