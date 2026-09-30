'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useGov } from '@/components/gov/Shell';
import { AssetTable, shortTime } from '@/components/gov/widgets';
import MapView, { LEGEND, RiskLegend } from '@/components/map/MapView';
import { LineBand } from '@/components/charts';
import { Card, DemoBanner, Empty, ErrorBox, Modal, SeverityBadge, Skeleton, Stat, Tabs, toast } from '@/components/ui';
import Icon, { KIND_ICON, TYPE_ICON } from '@/components/ui/Icon';
import { api, download } from '@/lib/api';
import { directionWord, inr, pct, RISK, ROLE_LABEL, TYPE_LABEL } from '@/lib/format';
import { invalidate, useApi } from '@/lib/useApi';

const VARS = [
  { key: 'precip', icon: 'rain', title: 'Rainfall (6-hour total)' },
  { key: 't2m', icon: 'thermo', title: 'Temperature (2 m)' },
  { key: 'wind', icon: 'wind', title: 'Wind speed (10 m)' },
  { key: 'mslp', icon: 'gauge', title: 'Sea-level pressure' },
];

function DraftModal({ event, open, onClose }) {
  const [role, setRole] = useState('citizen');
  const [lang, setLang] = useState('en');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const a = await api('/alerts/draft', { method: 'POST', body: { event_id: event.id, role, language: lang } });
      invalidate('/alerts'); invalidate('/dashboard');
      toast(a.approval_status === 'draft' ? `Draft ${a.alert_id} added to the approval queue` : `Alert ${a.alert_id} sent (standing order)`);
      onClose();
    } catch (e) { toast(e.message); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Draft a new alert"
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={submit} disabled={busy}>{busy ? 'Drafting…' : 'Create draft'}</button></>}>
      <div className="col gap-16">
        <p className="small muted">The message is written from verified event facts (Gemini if configured, otherwise a template). Citizen and institution alerts wait for your approval before sending.</p>
        <div className="field"><label htmlFor="aud">Audience</label>
          <select id="aud" className="select" value={role} onChange={(e) => setRole(e.target.value)}>
            {Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></div>
        <div className="field"><label htmlFor="lang">Language</label>
          <select id="lang" className="select" value={lang} onChange={(e) => setLang(e.target.value)}>
            {[['en', 'English'], ['kn', 'ಕನ್ನಡ Kannada'], ['hi', 'हिन्दी Hindi'], ['ta', 'தமிழ் Tamil'], ['te', 'తెలుగు Telugu'], ['mr', 'मराठी Marathi'], ['or', 'ଓଡ଼ିଆ Odia'], ['bn', 'বাংলা Bengali']].map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <span className="tiny muted">Non-English drafts need a Gemini key; otherwise English is used.</span></div>
      </div>
    </Modal>
  );
}

function FeedbackModal({ event, open, onClose }) {
  const [observed, setObserved] = useState(true);
  const [notes, setNotes] = useState('');
  const send = async () => {
    try {
      await api('/feedback', { method: 'POST', body: { event_id: event.id, observed, observed_type: event.type, observed_severity: event.severity, notes } });
      toast('Thanks, feedback stored for the next model retraining');
      onClose();
    } catch (e) { toast(e.message); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Did this event happen?"
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" onClick={send}>Save feedback</button></>}>
      <div className="col gap-16">
        <p className="small muted">Field outcomes feed the continuous-learning loop (verification statistics and retraining).</p>
        <div className="row gap-16">
          <label className="check"><input type="radio" name="obs" checked={observed} onChange={() => setObserved(true)} />Yes, it was observed</label>
          <label className="check"><input type="radio" name="obs" checked={!observed} onChange={() => setObserved(false)} />No, false alarm</label>
        </div>
        <div className="field"><label htmlFor="n">Notes (optional)</label><textarea id="n" className="textarea" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. 92 mm recorded at the KSNDMC gauge, two underpasses flooded" /></div>
      </div>
    </Modal>
  );
}

export default function AnomalyDetail() {
  const { id } = useParams();
  const { run } = useGov();
  const { data: e, error, reload } = useApi(`/anomalies/${id}`);
  const [lead, setLead] = useState(null);
  const [tab, setTab] = useState('population');
  const [draft, setDraft] = useState(false);
  const [fb, setFb] = useState(false);
  const activeLead = lead ?? e?.peak.lead_h;
  const impact = useApi(e ? `/anomalies/${id}/impact?lead_h=${activeLead}` : null);
  const zones = useApi(e ? `/maps/risk-zones?lead_h=${activeLead}` : null);
  const tracks = useApi('/maps/tracks');
  const assets = useApi(`/maps/assets?event_id=${id}`);
  const vehicles = useApi(`/maps/vehicles?event_id=${id}`);
  const wards = useApi('/maps/wards');
  const wx = useApi(e ? `/weather/forecast?lat=${e.peak.lat}&lon=${e.peak.lon}` : null);
  const alerts = useApi(`/alerts?event_id=${id}`);
  const ev = zones.data && { ...zones.data, features: zones.data.features.filter((f) => f.properties.event_id === id) };
  const tr = tracks.data && { ...tracks.data, features: tracks.data.features.filter((f) => f.properties.event_id === id) };
  const hlWards = useMemo(() => impact.data?.population?.wards?.map((w) => w.ward_no) || [], [impact.data]);

  if (error) return <div className="page"><ErrorBox error={error} onRetry={reload} /></div>;
  if (!e) return <div className="page"><Skeleton h={40} w="40%" /><Skeleton h={120} /><Skeleton h={420} /></div>;

  const pk = e.peak;
  const pt = e.track.find((q) => q.lead_h === activeLead) || e.track[0];
  const pop = impact.data?.population;
  const win = wx.data ? [wx.data.lead_h.indexOf(e.window.start_lead_h), wx.data.lead_h.indexOf(e.window.end_lead_h)] : null;

  return (
    <div className="page">
      <div className="row small"><Link href="/gov/anomalies" className="row gap-4"><Icon name="chevronL" size={15} />All anomalies</Link></div>
      <div className="page-head">
        <div className="col gap-6">
          <div className="row gap-8 wrap">
            <span className="mono small muted">{e.id}</span>
            <span className="badge warn mono tiny">SYNTHETIC SCENARIO</span>
            <span className="badge neutral">No official IMD warning linked</span>
          </div>
          <h1 className="row gap-8" style={{ fontSize: 28 }}><Icon name={TYPE_ICON[e.type]} size={28} />{TYPE_LABEL[e.type]} anomaly</h1>
          <div className="row gap-8 wrap"><SeverityBadge severity={e.severity} /><span className="muted">{e.place}</span></div>
        </div>
        <div className="row gap-8 wrap">
          <button className="btn" onClick={() => setFb(true)}><Icon name="check" size={16} />Field feedback</button>
          <button className="btn" onClick={() => download(`/reports/${e.id}.pdf`, `${e.id}.pdf`)}><Icon name="download" size={16} />Event report (PDF)</button>
          <button className="btn primary" onClick={() => setDraft(true)}><Icon name="bell" size={16} />Draft alert</button>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: 10 }}>
        <Stat k="Forecast window" v={<span style={{ fontSize: 13 }}>{shortTime(e.window.start_local)}<br />→ {shortTime(e.window.end_local)}</span>} />
        <Stat k="Movement" v={`${directionWord(e.motion.direction)}`} sub={`${Math.round(e.motion.speed_kmh)} km/h · ${Math.round(e.motion.heading_deg)}°`} />
        <Stat k="Ensemble agreement" v={pct(e.probability)} sub="members exceeding threshold" />
        <Stat k="Path uncertainty" v={`± ${Math.round(pk.uncertainty_km)} km`} sub="ensemble centroid spread" />
        <Stat k="Classifier confidence" v={pct(e.type_confidence)} sub={`anomaly score ${e.anomaly_score.toFixed(2)}`} />
        <Stat k={`Peak ${e.why.label}`} v={`${e.why.value} ${e.why.unit}`} sub={`${e.why.z > 0 ? '+' : ''}${e.why.z}σ vs baseline`} />
      </div>

      <div className="row-top" style={{ gap: 16 }}>
        <div className="grow col gap-12">
          <MapView zones={ev} tracks={tr} assets={assets.data} vehicles={vehicles.data} wards={wards.data} highlightWards={hlWards}
            height={520} fit="data" fitKey={`${id}-${!!zones.data}`} focus={{ lon: pt.lon, lat: pt.lat, zoom: 10.6 }} compact
            title={`${e.place.split(' (')[0].split(',')[0]} · Risk Zone Analysis`}
            legend={[LEGEND.school, LEGEND.hospital, LEGEND.rescue, LEGEND.vehicleIn, LEGEND.ward, LEGEND.track, LEGEND.cone]}>
          </MapView>
          <div className="card card-pad col gap-8">
            <div className="row between wrap">
              <h3>Track through the forecast</h3>
              <span className="small muted">Select a step to see the zone and exposure at that time</span>
            </div>
            <div className="row gap-4" style={{ overflowX: 'auto', paddingBottom: 4 }} role="listbox" aria-label="Track steps">
              {e.track.map((q) => {
                const on = q.lead_h === activeLead;
                const ring = q.severity === 'High' ? 'high' : q.severity === 'Moderate' ? 'moderate' : 'low';
                return (
                  <button key={q.lead_h} role="option" aria-selected={on} onClick={() => setLead(q.lead_h)} title={q.valid_local}
                    style={{ flex: '0 0 auto', width: 64, border: on ? '2px solid var(--ink)' : '1px solid var(--line)', borderRadius: 8, background: '#fff', padding: '6px 4px', cursor: 'pointer', font: 'inherit' }}>
                    <div style={{ height: 6, borderRadius: 3, background: RISK[ring].fill, marginBottom: 5 }} />
                    <div className="tiny strong">+{q.lead_h}h</div>
                    <div className="tiny muted num">{q.people >= 1e5 ? `${(q.people / 1e5).toFixed(1)}L` : inr(q.people)}</div>
                    {q.lead_h === pk.lead_h && <div className="tiny" style={{ color: 'var(--high-ink)', fontWeight: 600 }}>peak</div>}
                  </button>
                );
              })}
              {e.predicted.length > 0 && <div className="tiny muted" style={{ alignSelf: 'center', padding: '0 8px', whiteSpace: 'nowrap' }}>+ {e.predicted.length} projected steps (dashed on map)</div>}
            </div>
          </div>
        </div>

        <div style={{ width: 380, flex: '0 0 380px' }} className="col gap-12">
          <Card title="Citizens in the zone" action={<span className="small muted">{pt.valid_local}</span>}
            footer={pop && `Census of India 2011 · ${pop.sources?.join(', ').replace(/Census 2011 · /g, '')} · projected ×${pop.projection_factor}`}>
            {!pop ? <Skeleton h={140} /> : (
              <div className="col gap-8">
                <div className="num" style={{ fontSize: 30, fontWeight: 600 }}>{inr(pop.total)}</div>
                <div>
                  {['high', 'moderate', 'low'].map((r) => (
                    <div className="ringrow" key={r}><span><span className="swatch" style={{ background: RISK[r].fill }} />{RISK[r].label} · {RISK[r].range}</span><span className="num strong">{inr(pop[r])}</span></div>
                  ))}
                  <div className="ringrow"><span className="muted">Male / female</span><span className="num">{inr(pop.male)} / {inr(pop.female)}</span></div>
                  <div className="ringrow"><span className="muted">Households (est.)</span><span className="num">{inr(pop.households)}</span></div>
                </div>
              </div>
            )}
          </Card>
          <Card title="Why it was flagged">
            <p className="small" style={{ lineHeight: 1.6 }}>{e.why.text}</p>
            <div className="row wrap gap-6" style={{ marginTop: 10 }}>
              {Object.entries(pk.z).map(([k, v]) => <span key={k} className="chip">{k} {v > 0 ? '+' : ''}{v}σ</span>)}
            </div>
          </Card>
          <Card title={<h3 className="row gap-6">AI situation summary <span className="badge info tiny">{e.summary.generated_by}</span></h3>}>
            <p className="small" style={{ lineHeight: 1.6 }}>{e.summary.text}</p>
          </Card>
        </div>
      </div>

      <section className="card card-pad col gap-12">
        <div className="row between wrap"><h3>Forecast at the event location</h3><span className="small muted">Line: ensemble mean · band: min–max of members · dashed: September baseline · shaded: event window</span></div>
        {!wx.data ? <Skeleton h={160} /> : (
          <div className="grid g4">
            {VARS.map((v) => {
              const d = wx.data.variables[v.key];
              return (
                <div key={v.key} className="col gap-4">
                  <div className="row gap-6 small strong"><Icon name={v.icon} size={15} />{v.title} <span className="muted" style={{ fontWeight: 400 }}>({d.unit})</span></div>
                  <LineBand label={v.title} x={wx.data.lead_h} mean={d.mean} lo={d.min} hi={d.max} reference={d.climatology} unit={d.unit}
                    highlight={win && win[0] >= 0 ? win : null} xFmt={(h) => `D${Math.floor(h / 24)}`} height={150} />
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="card">
        <div style={{ padding: '6px 18px 0' }}>
          <Tabs value={tab} onChange={setTab} tabs={[
            { value: 'population', label: 'Wards & districts', count: pop ? (pop.wards?.length || pop.districts?.length || 0) : null },
            { value: 'institutions', label: 'Institutions', count: impact.data?.assets?.length },
            { value: 'vehicles', label: 'Vehicles heading in', count: impact.data?.vehicles?.length },
            { value: 'alerts', label: 'Alerts', count: alerts.data?.length },
          ]} />
        </div>
        <div className="scroll" style={{ maxHeight: 440 }}>
          {tab === 'population' && (!pop ? <div className="card-pad"><Skeleton h={80} /></div> : pop.wards?.length ? (
            <table className="table">
              <thead><tr><th>BBMP ward (Census 2011)</th><th className="r">People in zone (est.)</th><th className="r">Share of ward</th></tr></thead>
              <tbody>{pop.wards.map((w) => <tr key={w.ward_no}><td className="small">{w.ward_name} <span className="muted tiny">#{w.ward_no}</span></td><td className="r num">{inr(w.people)}</td><td className="r num small">{pct(w.share_of_ward)}</td></tr>)}</tbody>
            </table>
          ) : pop.districts?.length ? (
            <table className="table">
              <thead><tr><th>District (Census 2011)</th><th>State</th><th className="r">People in zone (est.)</th></tr></thead>
              <tbody>{pop.districts.map((d) => <tr key={d.district}><td>{d.district}</td><td className="small muted">{d.state}</td><td className="r num">{inr(d.people)}</td></tr>)}</tbody>
            </table>
          ) : <Empty icon="globe">Over open sea: no resident population.</Empty>)}
          {tab === 'institutions' && <AssetTable assets={impact.data?.assets} />}
          {tab === 'vehicles' && (impact.data?.vehicles?.length ? (
            <table className="table">
              <thead><tr><th>Vehicle</th><th>Type</th><th>Status</th><th className="r">Distance</th><th className="r">Speed</th><th className="r">ETA</th><th>Suggested action</th></tr></thead>
              <tbody>{impact.data.vehicles.map((v) => (
                <tr key={v.id}><td className="mono small nowrap">{v.id}</td><td className="small nowrap"><span className="row gap-6"><Icon name={KIND_ICON[v.kind]} size={15} />{v.kind.replace('_', ' ')}</span></td>
                  <td>{v.status === 'inside' ? <span className="badge high"><span className="dot" />Inside</span> : <span className="badge moderate"><span className="dot" />Heading in</span>}</td>
                  <td className="r num">{v.distance_km} km</td><td className="r num">{Math.round(v.speed_kmh)} km/h</td><td className="r num">{v.eta_min ? `${v.eta_min} min` : 'now'}</td>
                  <td className="small">{v.status === 'inside' ? 'Stop at a safe raised place' : `Turn to ${Math.round(v.detour_heading_deg)}°, avoid zone`}</td></tr>))}</tbody>
            </table>
          ) : <Empty icon="bus">{activeLead === pk.lead_h ? 'No vehicles heading into this zone.' : 'Vehicle checks are computed at the peak-impact step.'}</Empty>)}
          {tab === 'alerts' && (alerts.data?.length ? (
            <table className="table">
              <thead><tr><th>Alert</th><th>Audience</th><th>Message</th><th>Status</th><th className="r">Recipients</th></tr></thead>
              <tbody>{alerts.data.map((a) => (
                <tr key={a.alert_id}><td className="mono small nowrap">{a.alert_id}</td><td className="small nowrap">{ROLE_LABEL[a.role]}</td><td className="small" style={{ maxWidth: 480 }}>{a.title}</td>
                  <td><span className={`badge ${a.approval_status === 'sent' ? 'good' : a.approval_status === 'rejected' ? 'neutral' : 'warn'}`}>{a.approval_status}</span></td><td className="r num">{inr(a.recipients)}</td></tr>))}</tbody>
            </table>
          ) : <Empty icon="bell">No alerts for this event yet.</Empty>)}
        </div>
      </section>

      <DemoBanner />
      <DraftModal event={e} open={draft} onClose={() => { setDraft(false); alerts.reload(); }} />
      <FeedbackModal event={e} open={fb} onClose={() => setFb(false)} />
    </div>
  );
}
