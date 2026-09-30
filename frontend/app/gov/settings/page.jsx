'use client';
import { useEffect, useState } from 'react';
import { PageHead } from '@/components/gov/widgets';
import { Card, Skeleton, toast } from '@/components/ui';
import Icon from '@/components/ui/Icon';
import { api } from '@/lib/api';
import { invalidate, useApi } from '@/lib/useApi';

const MODE = { synthetic: 'warn', official: 'good', public: 'info' };

export default function SettingsPage() {
  const { data, reload } = useApi('/settings/status');
  const [seed, setSeed] = useState(42);
  const [busy, setBusy] = useState(null);
  const [retrain, setRetrain] = useState(null);

  useEffect(() => {
    if (!retrain?.running) return undefined;
    const t = setInterval(async () => {
      const s = await api('/models/retrain');
      setRetrain(s);
      if (!s.running) { toast('Retraining finished · new model loaded'); reload(); }
    }, 4000);
    return () => clearInterval(t);
  }, [retrain, reload]);

  const runPipeline = async () => {
    setBusy('run');
    try {
      const r = await api('/pipeline/run', { method: 'POST', body: { seed: Number(seed) } });
      invalidate('/');
      toast(`New forecast run ${r.run_id}: ${r.summary.active} anomalies in ${r.runtime_s}s`);
      setTimeout(() => window.location.reload(), 900);
    } catch (e) { toast(e.message); } finally { setBusy(null); }
  };
  const startRetrain = async () => {
    await api('/models/retrain', { method: 'POST' });
    setRetrain({ running: true });
    toast('Retraining started on fresh synthetic hindcasts (about a minute)');
  };

  return (
    <div className="page">
      <PageHead title="Settings" sub="Data-source status, thresholds, integrations, users and model version." />
      {!data ? <Skeleton h={300} /> : (
        <>
          <Card title="Data sources">
            <table className="table">
              <thead><tr><th>Source</th><th>In use</th><th>Type</th><th>How to switch to real data</th></tr></thead>
              <tbody>{data.data_sources.map((d) => (
                <tr key={d.name}><td className="strong small">{d.name}</td><td className="small">{d.value}</td><td><span className={`badge ${MODE[d.mode]}`}>{d.mode}</span></td><td className="small muted">{d.note}</td></tr>))}</tbody>
            </table>
          </Card>
          <div className="grid g3">
            <Card title="Detection thresholds">
              <div className="ringrow"><span>Anomaly threshold</span><span className="num strong">{data.thresholds.z_threshold} σ</span></div>
              <div className="ringrow"><span>Minimum object size</span><span className="num strong">{data.thresholds.min_object_cells} grid cells</span></div>
              <div className="ringrow"><span>Base ring radii</span><span className="num strong">{data.thresholds.ring_radii_km.join(' / ')} km</span></div>
              <div className="ringrow"><span>Vehicle rule</span><span className="strong small">{data.thresholds.vehicle_rule}</span></div>
              <div className="small muted" style={{ marginTop: 8 }}>Change via WP_* variables in backend/.env.</div>
            </Card>
            <Card title="Integrations">
              <div className="ringrow"><span className="row gap-6"><Icon name="spark" size={15} />Gemini (alerts + Copilot)</span>
                {data.integrations.gemini ? <span className="badge good">Connected · {data.integrations.gemini_model}</span> : <span className="badge neutral">Not set · templates</span>}</div>
              <div className="ringrow"><span className="row gap-6"><Icon name="sms" size={15} />SMS</span><span className="badge neutral">{data.integrations.sms}</span></div>
              <div className="ringrow"><span className="row gap-6"><Icon name="mail" size={15} />Email</span><span className="badge neutral">{data.integrations.email}</span></div>
              <div className="small muted" style={{ marginTop: 8 }}>Keys live only in backend/.env on the server, never in the browser.</div>
            </Card>
            <Card title="Model">
              <div className="ringrow"><span>Version</span><span className="mono small">{data.model.version}</span></div>
              <div className="ringrow"><span>Type accuracy</span><span className="num strong">{(data.model.metrics.type_accuracy * 100).toFixed(1)}%</span></div>
              <div className="ringrow"><span>False-alarm rate</span><span className="num strong">{(data.model.metrics.false_alarm_rate * 100).toFixed(1)}%</span></div>
              <button className="btn block" style={{ marginTop: 10 }} onClick={startRetrain} disabled={retrain?.running}>
                <Icon name="refresh" size={15} className={retrain?.running ? 'spin' : ''} />{retrain?.running ? 'Retraining…' : 'Retrain models'}
              </button>
            </Card>
          </div>
          <div className="grid g2">
            <Card title="Run a new forecast scenario">
              <p className="small muted" style={{ marginBottom: 12 }}>Re-runs the whole pipeline (ingest → detect → track → impact → alerts) on a new synthetic ensemble. The demo events stay; the random extra events change with the seed.</p>
              <div className="row gap-8">
                <label htmlFor="seed" className="small">Seed</label>
                <input id="seed" className="input" type="number" value={seed} onChange={(e) => setSeed(e.target.value)} style={{ width: 120 }} />
                <button className="btn primary" onClick={runPipeline} disabled={busy === 'run'}><Icon name="play" size={15} />{busy === 'run' ? 'Running…' : 'Run pipeline'}</button>
              </div>
            </Card>
            <Card title="User accounts">
              <table className="table">
                <thead><tr><th>Account type</th><th>Role</th><th className="r">Accounts</th></tr></thead>
                <tbody>{data.users.map((u) => <tr key={u.role}><td className="small">{u.label}</td><td><span className="badge neutral">{u.role}</span></td><td className="r num">{u.count}</td></tr>)}</tbody>
              </table>
              <div className="small muted" style={{ marginTop: 8 }}>Every institution, rescue unit and bus has its own login; citizens register themselves. Export all demo logins with <span className="mono">python -m scripts.export_accounts</span>. Passwords are stored as salted hashes.</div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
