'use client';
import { useEffect, useMemo, useState } from 'react';
import MapView, { LEGEND, RiskLegend } from '@/components/map/MapView';
import { Bars } from '@/components/charts';
import RoleHeader from '@/components/RoleHeader';
import { Card, DemoBanner, Empty, ErrorBox, Kpi, RingBadge, Skeleton, toast } from '@/components/ui';
import Icon from '@/components/ui/Icon';
import { api } from '@/lib/api';
import { useRequireRole } from '@/lib/auth';
import { countdown, inr, KIND_LABEL, pct, RISK, timeAgo, TYPE_LABEL } from '@/lib/format';
import { useApi } from '@/lib/useApi';

export default function InstitutionPortal() {
  const { allowed } = useRequireRole('institution', 'official');
  const me = useApi(allowed ? '/institutions/me' : null);
  const st = useApi(me.data ? `/institutions/${me.data.asset_id}/status` : null);
  const [checks, setChecks] = useState([]);
  const [acked, setAcked] = useState(false);
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 60000); return () => clearInterval(t); }, []);
  useEffect(() => { if (st.data) { setChecks(st.data.checklist); setAcked(st.data.acknowledgements.length > 0); } }, [st.data]);

  const d = st.data;
  const a = d?.asset;
  const x = d?.exposure;
  const ev = x?.event;
  const ring = x?.ring;
  const rainBars = useMemo(() => {
    if (!x?.weather) return [];
    const w = x.weather;
    const out = [];
    for (let i = 0; i < w.lead_h.length; i += 2) {
      const h = w.lead_h[i];
      if (h < x.first_lead_h - 24 || h > x.last_lead_h + 24) continue;
      const v = (w.variables.precip.mean[i] || 0) + (w.variables.precip.mean[i + 1] || 0);
      out.push({ label: w.valid_local[i].split(',')[0].slice(0, 3) + ' ' + w.valid_local[i].split(', ')[1]?.slice(0, 2), value: Math.round(v), tip: `${w.valid_local[i]} · 12 h`, color: v > 60 ? RISK.high.fill : v > 25 ? RISK.moderate.fill : '#9ec5f4' });
    }
    return out;
  }, [x]);
  const windowRain = useMemo(() => {
    if (!x?.weather) return null;
    const w = x.weather;
    let s = 0; let lo = 0; let hi = 0;
    w.lead_h.forEach((h, i) => { if (h >= ev.window.start_lead_h && h <= ev.window.end_lead_h) { s += w.variables.precip.mean[i]; lo += w.variables.precip.min[i]; hi += w.variables.precip.max[i]; } });
    return { s, lo, hi };
  }, [x, ev]);

  const toggle = async (item, done) => {
    setChecks((c) => c.map((q) => (q.item === item ? { ...q, done } : q)));
    try { await api(`/institutions/${a.id}/checklist`, { method: 'POST', body: { item, done } }); } catch (e) { toast(e.message); }
  };
  const ack = async () => {
    try {
      await api(`/institutions/${a.id}/acknowledge`, { method: 'POST', body: { alert_id: x?.alerts?.[0]?.alert_id || null, note: 'Acknowledged from institution portal' } });
      setAcked(true); toast('Acknowledged · the district office can see this'); st.reload();
    } catch (e) { toast(e.message); }
  };
  const done = checks.filter((c) => c.done).length;
  const zoneFc = x && { type: 'FeatureCollection', features: ['low', 'moderate', 'high'].map((r) => ({ type: 'Feature', properties: { ring: r, event_id: ev.id, severity: ev.severity }, geometry: { type: 'Polygon', coordinates: [x.zone.rings[r]] } })) };
  const isHosp = a?.kind === 'hospital';

  return (
    <div style={{ minHeight: '100vh' }}>
      <RoleHeader portal={`Institution portal · ${KIND_LABEL[a?.kind] || ''}`} right={a && <span className="small strong" style={{ maxWidth: 360, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</span>} />
      <main className="page" style={{ maxWidth: 1360, margin: '0 auto' }}>
        <DemoBanner>Demo institution and synthetic forecast. Follow official IMD / SDMA / Education Department instructions.</DemoBanner>
        <ErrorBox error={me.error || st.error} onRetry={st.reload} />
        {!d ? <div className="col"><Skeleton h={150} /><Skeleton h={100} /><Skeleton h={360} /></div> : !x ? (
          <Card><Empty icon="check" title="No risk forecast for your site">No anomaly zone reaches {a.name} in the next 10 days. We will alert you if that changes.</Empty></Card>
        ) : (
          <>
            <section className="card" style={{ display: 'flex', overflow: 'hidden' }}>
              <div style={{ width: 10, background: RISK[ring].fill }} />
              <div className="col gap-8" style={{ padding: '22px 24px', flex: 1 }}>
                <div className="row gap-8 wrap">
                  <span className="badge" style={{ background: RISK[ring].fill, color: ring === 'high' ? '#fff' : '#14202b' }}>{RISK[ring].label.toUpperCase()} RISK · YOUR SITE</span>
                  {x.alerts[0] && <span className="small muted">Alert {x.alerts[0].alert_id} · {x.alerts[0].approval_status === 'sent' ? `approved by ${x.alerts[0].approved_by}` : 'awaiting district approval'}</span>}
                </div>
                <h1 style={{ fontSize: 28, lineHeight: 1.2 }}>{TYPE_LABEL[ev.type]} expected at your {isHosp ? 'facility' : 'campus'} · {x.worst_valid_local.split(',')[0]}</h1>
                <p style={{ fontSize: 15, color: 'var(--ink-2)', lineHeight: 1.55, maxWidth: 860 }}>
                  Your site is {x.distance_km} km from the forecast peak, inside the <b>{RISK[ring].label.toLowerCase()}-risk ring ({RISK[ring].range})</b>. The event is expected from <b>{ev.window.start_local}</b> to <b>{ev.window.end_local}</b>, moving {ev.motion.direction} at about {Math.round(ev.motion.speed_kmh)} km/h.
                </p>
              </div>
              <div className="col gap-8" style={{ padding: '22px 24px', borderLeft: '1px solid var(--line-2)', width: 290, justifyContent: 'center' }}>
                {acked ? <div className="badge good" style={{ justifyContent: 'center', height: 44, fontSize: 14 }}><Icon name="check" size={16} />Acknowledged</div>
                  : <button className="btn primary lg" onClick={ack}><Icon name="check" size={16} />Acknowledge alert</button>}
                <button className="btn lg" onClick={() => toast(isHosp ? 'Staff roster notified (demo)' : 'SMS to parents queued (demo, not sent)')}>
                  <Icon name="sms" size={16} />{isHosp ? 'Notify on-call staff' : 'Message parents (SMS)'}
                </button>
                <div className="tiny muted" style={{ textAlign: 'center' }}>The district office sees your acknowledgement</div>
              </div>
            </section>

            <div className="grid g4">
              <Kpi icon="clock" label="Time until onset" value={countdown(d.issue_time, ev.window.start_lead_h)} foot={ev.window.start_local} />
              {ev.type === 'heavy_rainfall' || ev.type === 'cyclone'
                ? <Kpi icon="rain" label="Expected rain at site" value={`${Math.round(windowRain?.lo || 0)}–${Math.round(windowRain?.hi || 0)} mm`} foot={`ensemble range over the event window (mean ${Math.round(windowRain?.s || 0)} mm)`} />
                : <Kpi icon="thermo" label="Peak temperature" value={`${Math.max(...x.weather.variables.t2m.max).toFixed(1)} °C`} foot="highest ensemble member" />}
              <Kpi icon={isHosp ? 'hospital' : 'users'} label={isHosp ? 'Beds' : 'People on campus'} value={inr(a.capacity)} foot={isHosp ? 'registered capacity' : 'students (registry)'} />
              <Kpi icon="target" label="Forecast confidence" value={pct(x.confidence)} foot="share of forecast scenarios that agree" />
            </div>

            <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.1fr) minmax(0, 1fr)' }}>
              <Card title="Your site and the risk zone" footer="Rings move with the storm; this is the forecast at the time of highest risk for your site.">
                <MapView zones={zoneFc} height={380} fit="data" fitKey={a.id} markers={[{ lon: a.lon, lat: a.lat, label: isHosp ? 'Your hospital' : 'Your school', tone: 'shelter' }]}>
                  <div className="map-overlay" style={{ left: 10, bottom: 10 }}><RiskLegend collapsible={false} /></div>
                </MapView>
              </Card>
              <div className="col gap-16">
                <Card title="Preparedness checklist" action={<span className="small muted">{done} of {checks.length} done</span>}>
                  <div className="progress" style={{ marginBottom: 10 }}><div style={{ width: `${(done / Math.max(checks.length, 1)) * 100}%` }} /></div>
                  {checks.map((c) => (
                    <label key={c.item} className="check ringrow" style={{ justifyContent: 'flex-start' }}>
                      <input type="checkbox" checked={c.done} onChange={(e) => toggle(c.item, e.target.checked)} />
                      <span style={{ textDecoration: c.done ? 'line-through' : 'none', color: c.done ? 'var(--muted)' : 'var(--ink)' }}>{c.item}</span>
                    </label>
                  ))}
                </Card>
                <Card title="Official guidance for your institution">
                  <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>{x.guidance.map((g) => <li key={g}>{g}</li>)}</ul>
                </Card>
              </div>
            </div>

            <div className="grid g2">
              <Card title={ev.type === 'heatwave' ? 'Temperature at your site' : 'Rain expected at your site (12-hour totals)'}>
                {rainBars.length ? <Bars data={rainBars} label="Rain by 12-hour period" fmt={(v) => `${v}`} /> : <Empty>No data.</Empty>}
                <div className="tiny muted" style={{ marginTop: 6 }}>mm per 12 h, ensemble mean · colour marks heavy (orange) and very heavy (red) periods</div>
              </Card>
              <Card title="Updates for your site">
                <div className="col gap-12">
                  {d.acknowledgements.map((k) => <div key={k.id} className="row-top small"><span className="mono tiny muted" style={{ width: 90 }}>{timeAgo(k.timestamp)}</span><span><b>Acknowledged</b> by your institution.</span></div>)}
                  {x.alerts.map((al) => <div key={al.alert_id} className="row-top small"><span className="mono tiny muted" style={{ width: 90 }}>{timeAgo(al.created_at)}</span><span><b>{al.title}.</b> {al.approval_status === 'sent' ? 'Sent to you.' : 'Awaiting approval by the district office.'}</span></div>)}
                  <div className="row-top small"><span className="mono tiny muted" style={{ width: 90 }}>{timeAgo(d.issue_time)}</span><span>Risk first detected for your site in forecast run issued {new Date(d.issue_time).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}. <RingBadge ring={ring} /></span></div>
                </div>
              </Card>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
