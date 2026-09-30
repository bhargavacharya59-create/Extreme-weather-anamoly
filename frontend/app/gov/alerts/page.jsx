'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useGov } from '@/components/gov/Shell';
import { PageHead } from '@/components/gov/widgets';
import { Drawer, Empty, Modal, Skeleton, Tabs, toast } from '@/components/ui';
import Icon from '@/components/ui/Icon';
import { api } from '@/lib/api';
import { inr, ROLE_LABEL, timeAgo } from '@/lib/format';
import { invalidate, useApi } from '@/lib/useApi';

const ROLE_ICON = { official: 'grid', school: 'school', hospital: 'hospital', rescue: 'shield', citizen: 'users', traveller: 'bus' };
const CH_ICON = { sms: 'sms', email: 'mail', app: 'bell', push: 'wifi' };
const STEPS = ['Anomaly detected', 'Impact estimated', 'Draft written', 'Official approves', 'Delivered & logged'];

function AlertCard({ a, onChanged, onLog }) {
  const [edit, setEdit] = useState(false);
  const [msg, setMsg] = useState(a.message);
  const [busy, setBusy] = useState(null);
  const act = async (kind) => {
    setBusy(kind);
    try {
      if (kind === 'save') await api(`/alerts/${a.alert_id}`, { method: 'PATCH', body: { message: msg } });
      if (kind === 'approve') await api(`/alerts/${a.alert_id}/approve`, { method: 'POST' });
      if (kind === 'reject') await api(`/alerts/${a.alert_id}/reject`, { method: 'POST', body: { reason: 'Rejected by officer' } });
      toast({ save: 'Draft updated', approve: `Approved · delivering to ${inr(a.recipients)} recipients`, reject: 'Draft rejected' }[kind]);
      invalidate('/alerts'); invalidate('/dashboard');
      setEdit(false);
      onChanged();
    } catch (e) { toast(e.message); } finally { setBusy(null); }
  };
  const sev = a.target?.severity;
  return (
    <article className="card" style={{ display: 'flex', gap: 0, overflow: 'hidden' }}>
      <div style={{ width: 5, background: sev === 'High' ? 'var(--high)' : sev === 'Moderate' ? 'var(--mod)' : 'var(--low)' }} />
      <div className="col gap-8" style={{ padding: '14px 18px', flex: 1, minWidth: 0 }}>
        <div className="row between wrap gap-8">
          <div className="row gap-8">
            <span style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--accent-tint)', color: 'var(--accent)', display: 'grid', placeItems: 'center' }}><Icon name={ROLE_ICON[a.role]} size={17} /></span>
            <div>
              <div className="strong">{a.title}</div>
              <div className="tiny muted">
                <Link href={`/gov/anomalies/${a.event_id}`} className="mono">{a.event_id}</Link> · {ROLE_LABEL[a.role]} · {inr(a.recipients)} recipients · {a.language.toUpperCase()} · created {timeAgo(a.created_at)} by {a.target?.created_by || 'system'}
              </div>
            </div>
          </div>
          <div className="row gap-6">
            {a.channels.map((c) => <span key={c} className="badge neutral" title={c}><Icon name={CH_ICON[c]} size={12} />{c}</span>)}
            <span className={`badge ${a.generated_by.startsWith('gemini') ? 'info' : 'neutral'}`}>{a.generated_by.startsWith('gemini') ? 'Gemini' : 'Template'}{a.generated_by.includes('edited') ? ' · edited' : ''}</span>
          </div>
        </div>
        {edit ? (
          <>
            <label htmlFor={`m-${a.alert_id}`} className="sr-only">Message</label>
            <textarea id={`m-${a.alert_id}`} className="textarea" rows={4} value={msg} onChange={(e) => setMsg(e.target.value)} />
          </>
        ) : <p className="small" style={{ lineHeight: 1.6, background: 'var(--surface-2)', borderRadius: 8, padding: '10px 12px' }}>{a.message}</p>}
        <div className="row between wrap gap-8">
          <div className="tiny muted">
            {a.approval_status === 'sent' && <>Approved by <b>{a.approved_by}</b> · {timeAgo(a.approved_at)}</>}
            {a.approval_status === 'rejected' && <>Rejected by <b>{a.approved_by}</b></>}
            {a.approval_status === 'draft' && (a.requires_approval ? 'Requires approval before sending' : 'Standing order')}
          </div>
          <div className="row gap-6">
            {a.approval_status === 'draft' && !edit && <>
              <button className="btn sm ghost danger" disabled={!!busy} onClick={() => act('reject')}>Reject</button>
              <button className="btn sm" onClick={() => setEdit(true)}><Icon name="edit" size={14} />Edit</button>
              <button className="btn sm primary" disabled={!!busy} onClick={() => act('approve')}><Icon name="send" size={14} />{busy === 'approve' ? 'Sending…' : 'Approve & send'}</button>
            </>}
            {edit && <>
              <button className="btn sm" onClick={() => { setEdit(false); setMsg(a.message); }}>Cancel</button>
              <button className="btn sm primary" disabled={!!busy} onClick={() => act('save')}>Save draft</button>
            </>}
            {a.approval_status === 'sent' && <button className="btn sm" onClick={() => onLog(a)}><Icon name="file" size={14} />Delivery log</button>}
          </div>
        </div>
      </div>
    </article>
  );
}

function NewDraft({ open, onClose, events, onDone }) {
  const [eid, setEid] = useState('');
  const [role, setRole] = useState('citizen');
  const [lang, setLang] = useState('en');
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try {
      await api('/alerts/draft', { method: 'POST', body: { event_id: eid || events[0].id, role, language: lang } });
      toast('Draft created'); invalidate('/alerts'); onDone(); onClose();
    } catch (e) { toast(e.message); } finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="New alert draft" footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy} onClick={go}>Create draft</button></>}>
      <div className="col gap-16">
        <div className="field"><label htmlFor="ev">Event</label>
          <select id="ev" className="select" value={eid} onChange={(e) => setEid(e.target.value)}>
            {events.map((e) => <option key={e.id} value={e.id}>{e.id} · {e.severity} · {e.place}</option>)}
          </select></div>
        <div className="grid g2">
          <div className="field"><label htmlFor="r">Audience</label>
            <select id="r" className="select" value={role} onChange={(e) => setRole(e.target.value)}>{Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
          <div className="field"><label htmlFor="l">Language</label>
            <select id="l" className="select" value={lang} onChange={(e) => setLang(e.target.value)}>
              {[['en', 'English'], ['kn', 'Kannada'], ['hi', 'Hindi'], ['ta', 'Tamil'], ['te', 'Telugu'], ['or', 'Odia'], ['mr', 'Marathi'], ['bn', 'Bengali']].map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></div>
        </div>
      </div>
    </Modal>
  );
}

export default function AlertsPage() {
  const { events } = useGov();
  const { data, reload } = useApi('/alerts', { poll: 20000 });
  const [tab, setTab] = useState('draft');
  const [role, setRole] = useState('all');
  const [log, setLog] = useState(null);
  const [nd, setNd] = useState(false);
  const deliveries = useApi(log ? `/alerts/${log.alert_id}/deliveries` : null);
  const counts = useMemo(() => ({ draft: 0, sent: 0, rejected: 0, ...(data || []).reduce((m, a) => ({ ...m, [a.approval_status]: (m[a.approval_status] || 0) + 1 }), {}) }), [data]);
  const list = (data || []).filter((a) => a.approval_status === tab && (role === 'all' || a.role === role));

  return (
    <div className="page">
      <PageHead title="Alerts & approvals" sub="Drafts are written from verified event facts. Nothing reaches citizens or institutions until an official approves it.">
        <button className="btn primary" onClick={() => setNd(true)} disabled={!events.data?.length}><Icon name="plus" size={16} />New draft</button>
      </PageHead>

      <div className="card card-pad">
        <div className="row" style={{ gap: 0 }}>
          {STEPS.map((s, i) => (
            <div key={s} className="row grow" style={{ gap: 8 }}>
              <span style={{ width: 26, height: 26, borderRadius: 13, flex: 'none', display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 700,
                background: i === 3 ? 'var(--accent)' : 'var(--sunken)', color: i === 3 ? '#fff' : 'var(--ink-2)' }}>{i + 1}</span>
              <span className={`small ${i === 3 ? 'strong' : 'muted'}`}>{s}</span>
              {i < STEPS.length - 1 && <span className="grow" style={{ height: 1, background: 'var(--line)', margin: '0 10px' }} />}
            </div>
          ))}
        </div>
      </div>

      <div className="row between wrap">
        <Tabs value={tab} onChange={setTab} tabs={[{ value: 'draft', label: 'Awaiting approval', count: counts.draft }, { value: 'sent', label: 'Sent', count: counts.sent }, { value: 'rejected', label: 'Rejected', count: counts.rejected }]} />
        <label className="small muted row gap-6">Audience
          <select className="select" style={{ height: 36 }} value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="all">All audiences</option>{Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>

      <div className="col gap-12">
        {!data ? [0, 1, 2].map((i) => <Skeleton key={i} h={140} />) : !list.length ? (
          <div className="card"><Empty icon={tab === 'draft' ? 'check' : 'bell'} title={tab === 'draft' ? 'Queue is clear' : 'Nothing here yet'}>{tab === 'draft' ? 'Every draft has been reviewed.' : ''}</Empty></div>
        ) : list.map((a) => <AlertCard key={a.alert_id} a={a} onChanged={reload} onLog={setLog} />)}
      </div>

      <Drawer open={!!log} onClose={() => setLog(null)} title={`Delivery log · ${log?.alert_id || ''}`}>
        {!deliveries.data ? <Skeleton h={200} /> : (
          <div className="col gap-8">
            <p className="small muted">“simulated” means the channel is not configured with real credentials, so the message was logged instead of sent. Add Twilio / SMTP / Firebase keys in backend/.env to deliver for real.</p>
            <table className="table">
              <thead><tr><th>Channel</th><th>Recipient</th><th>Status</th><th>Time</th></tr></thead>
              <tbody>{deliveries.data.map((d) => (
                <tr key={d.id}><td className="small nowrap"><span className="row gap-6"><Icon name={CH_ICON[d.channel]} size={14} />{d.channel}</span></td><td className="small">{d.recipient}</td>
                  <td><span className={`badge ${d.delivery_status === 'delivered' || d.delivery_status === 'sent' ? 'good' : d.delivery_status === 'failed' ? 'high' : 'neutral'}`}>{d.delivery_status}</span></td>
                  <td className="tiny muted nowrap">{timeAgo(d.timestamp)}</td></tr>))}</tbody>
            </table>
          </div>
        )}
      </Drawer>
      {events.data && <NewDraft open={nd} onClose={() => setNd(false)} events={events.data} onDone={reload} />}
    </div>
  );
}
