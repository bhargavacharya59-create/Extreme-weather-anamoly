'use client';
import { PageHead } from '@/components/gov/widgets';
import { Bars, MetricBars, RingStack, SERIES } from '@/components/charts';
import { Card, Kpi, Skeleton } from '@/components/ui';
import Icon from '@/components/ui/Icon';
import { download } from '@/lib/api';
import { inr, timeAgo, TYPE_LABEL } from '@/lib/format';
import { useApi } from '@/lib/useApi';

export default function ReportsPage() {
  const { data: a } = useApi('/analytics');
  const { data: r } = useApi('/reports');
  const { data: events } = useApi('/anomalies');
  const m = a?.model;
  return (
    <div className="page">
      <PageHead title="Reports & analytics" sub="Downloadable reports, model performance and an auditable history of every run, alert and Copilot query.">
        <button className="btn" onClick={() => download('/reports/events.csv', 'weatherpulse_events.csv')}><Icon name="download" size={16} />Events (CSV)</button>
        <button className="btn primary" onClick={() => download('/reports/situation.pdf', 'weatherpulse_situation_report.pdf')}><Icon name="download" size={16} />Situation report (PDF)</button>
      </PageHead>

      <div className="grid g4">
        {!a ? [0, 1, 2, 3].map((i) => <Skeleton key={i} h={96} />) : (
          <>
            <Kpi icon="target" label="Event-type accuracy" value={`${(m.type_accuracy * 100).toFixed(1)}%`} foot={`vs ${(m.rule_baseline_accuracy * 100).toFixed(1)}% rule-based baseline`} />
            <Kpi icon="check" label="Detection precision / recall" value={`${Math.round(m.detection_precision * 100)} / ${Math.round(m.detection_recall * 100)}`} foot="event vs noise, held-out scenarios" />
            <Kpi icon="alert" label="False-alarm rate" value={`${(m.false_alarm_rate * 100).toFixed(1)}%`} foot="noise objects flagged as events" />
            <Kpi icon="bell" label="Alerts this run" value={a.alerts.total} foot={`${a.alerts.by_status.sent} sent · ${a.alerts.by_status.draft} awaiting approval`} />
          </>
        )}
      </div>

      <div className="grid g2">
        <Card title="Model vs rule-based baseline" footer={m ? `${m.split} · ${m.n_train} training / ${m.n_test} test anomaly objects · backend ${m.backend}` : ''}>
          {!m ? <Skeleton h={180} /> : (
            <MetricBars series={[{ key: 'model', label: 'WeatherPulse model', color: SERIES.blue }, { key: 'base', label: 'Rule-based baseline', color: SERIES.gray }]}
              rows={[
                { label: 'Event-type accuracy', model: m.type_accuracy, base: m.rule_baseline_accuracy },
                { label: 'Macro F1 (5 classes)', model: m.type_macro_f1 },
                { label: 'Detection precision', model: m.detection_precision },
                { label: 'Detection recall', model: m.detection_recall },
                { label: 'Severity accuracy (3 levels)', model: m.severity_accuracy },
              ]} />
          )}
        </Card>
        <Card title="Per-class F1 on held-out scenarios">
          {!a ? <Skeleton h={180} /> : (
            <Bars label="F1 by class" fmt={(v) => `${Math.round(v * 100)}%`}
              data={['heavy_rainfall', 'cyclone', 'heatwave', 'coldwave', 'noise'].filter((k) => a.model_report[k]).map((k) => ({ label: { heavy_rainfall: 'Rainfall', cyclone: 'Cyclone', heatwave: 'Heatwave', coldwave: 'Cold wave', noise: 'Noise' }[k], value: a.model_report[k]['f1-score'], tip: `${TYPE_LABEL[k] || 'Noise'} · support ${a.model_report[k].support}` }))} />
          )}
        </Card>
      </div>

      <div className="grid g2">
        <Card title="Citizens exposed per event (Census 2011, projected)">
          {!events ? <Skeleton h={200} /> : <RingStack rows={events.filter((e) => e.peak.population.total > 0).map((e) => ({ label: `${e.id.replace('WX-', '')} · ${e.place.split(',')[0]}`, ...e.peak.population })).sort((x, y) => y.total - x.total)} />}
        </Card>
        <Card title="Anomaly onsets by forecast day">
          {!a ? <Skeleton h={180} /> : <Bars label="Events by onset day" data={a.by_lead_day.map((d) => ({ label: `D${d.day}`, value: d.events, tip: `Day ${d.day}: ${d.events} event(s)` }))} />}
          <div className="small muted" style={{ marginTop: 8 }}>Pipeline: {a?.pipeline.objects} anomaly objects → {a?.pipeline.tracks} tracks → {events?.length} events in {a?.pipeline.runtime_s}s · {Object.values(a?.pipeline.qc?.missing_filled || {}).reduce((x, y) => x + y, 0).toLocaleString('en-IN')} missing values filled</div>
        </Card>
      </div>

      <div className="grid g2">
        <Card title="Event reports">
          {!events ? <Skeleton h={160} /> : (
            <table className="table">
              <thead><tr><th>Event</th><th>Place</th><th className="r">People</th><th /></tr></thead>
              <tbody>{events.map((e) => (
                <tr key={e.id}><td className="mono small nowrap">{e.id}</td><td className="small">{e.place}</td><td className="r num small">{inr(e.peak.population.total)}</td>
                  <td className="r"><button className="btn sm" onClick={() => download(`/reports/${e.id}.pdf`, `${e.id}.pdf`)}><Icon name="download" size={14} />PDF</button></td></tr>))}</tbody>
            </table>
          )}
        </Card>
        <Card title="Audit log" footer="Approvals, acknowledgements, feedback and every Copilot question are recorded.">
          {!r ? <Skeleton h={160} /> : (
            <div className="scroll" style={{ maxHeight: 330 }}>
              <table className="table">
                <thead><tr><th>When</th><th>User</th><th>Action</th><th>Detail</th></tr></thead>
                <tbody>{r.audit.map((x) => {
                  let d = x.detail; try { const j = JSON.parse(x.detail); d = j.q || j.alert_id || j.asset_id || j.order_id || j.event_id || x.detail; } catch { /* raw */ }
                  return <tr key={x.id}><td className="tiny muted nowrap">{timeAgo(x.timestamp)}</td><td className="mono tiny">{x.user_id}</td><td className="small nowrap">{x.action.replace('_', ' ')}</td><td className="small" style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{String(d)}</td></tr>;
                })}
                {!r.audit.length && <tr><td colSpan={4} className="small muted">No actions yet.</td></tr>}</tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <Card title="Forecast run history">
        {!r ? <Skeleton h={80} /> : (
          <table className="table">
            <thead><tr><th>Run</th><th>Issued</th><th>Provider</th><th>Mode</th><th className="r">Events</th><th className="r">People exposed</th><th>Model</th></tr></thead>
            <tbody>{r.runs.map((x) => (
              <tr key={x.run_id}><td className="mono small">{x.run_id}</td><td className="small">{new Date(x.issue_time).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}</td><td className="small">{x.provider}</td>
                <td><span className="badge warn">{x.data_mode}</span></td><td className="r num">{x.summary.active}</td><td className="r num">{inr(x.summary.population_exposed)}</td><td className="mono tiny">{x.model_version}</td></tr>))}</tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
