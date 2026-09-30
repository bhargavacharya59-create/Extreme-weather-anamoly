'use client';
import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useGov } from '@/components/gov/Shell';
import { PageHead } from '@/components/gov/widgets';
import { DemoBanner, Segmented, SeverityBadge, Skeleton, TypeLabel } from '@/components/ui';
import Icon from '@/components/ui/Icon';
import { directionWord, inr, pct } from '@/lib/format';

const SEV_ORDER = { High: 0, Moderate: 1, Low: 2 };

export default function AnomaliesPage() {
  const router = useRouter();
  const { events } = useGov();
  const [sev, setSev] = useState('all');
  const [type, setType] = useState('all');
  const [sort, setSort] = useState('severity');
  const list = useMemo(() => {
    let l = events.data || [];
    if (sev !== 'all') l = l.filter((e) => e.severity === sev);
    if (type !== 'all') l = l.filter((e) => e.type === type);
    const key = {
      severity: (e) => [SEV_ORDER[e.severity], -e.peak.population.total],
      people: (e) => [-e.peak.population.total],
      time: (e) => [e.window.start_lead_h],
    }[sort];
    return [...l].sort((a, b) => { const x = key(a); const y = key(b); for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] - y[i]; return 0; });
  }, [events.data, sev, type, sort]);
  const types = [...new Set((events.data || []).map((e) => e.type))];

  return (
    <div className="page">
      <PageHead title="Anomaly tracking" sub="Every anomaly detected in the current 10-day ensemble forecast, tracked across forecast steps." />
      <DemoBanner />
      <div className="row wrap gap-8">
        <Segmented label="Severity" value={sev} onChange={setSev} options={[{ value: 'all', label: 'All severities' }, { value: 'High', label: 'High' }, { value: 'Moderate', label: 'Moderate' }, { value: 'Low', label: 'Low' }]} />
        <Segmented label="Type" value={type} onChange={setType} options={[{ value: 'all', label: 'All types' }, ...types.map((t) => ({ value: t, label: t === 'heavy_rainfall' ? 'Rainfall' : t[0].toUpperCase() + t.slice(1) }))]} />
        <div className="grow" />
        <label className="small muted row gap-6">Sort by
          <select className="select" style={{ height: 36 }} value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="severity">Severity</option><option value="people">People exposed</option><option value="time">Onset time</option>
          </select>
        </label>
      </div>
      <section className="card scroll">
        {!events.data ? <div className="card-pad col"><Skeleton h={40} /><Skeleton h={40} /><Skeleton h={40} /></div> : (
          <table className="table">
            <thead>
              <tr><th>Event</th><th>Type</th><th>Severity</th><th>Location</th><th>Forecast window</th><th>Movement</th><th className="r">Agreement</th><th className="r">People 0–8 km</th><th className="r">Schools</th><th className="r">Hospitals</th><th /></tr>
            </thead>
            <tbody>
              {list.map((e) => (
                <tr key={e.id} className="click" onClick={() => router.push(`/gov/anomalies/${e.id}`)}>
                  <td className="mono small strong nowrap">{e.id}</td>
                  <td className="small nowrap"><TypeLabel type={e.type} size={15} /></td>
                  <td><SeverityBadge severity={e.severity}>{e.severity}</SeverityBadge></td>
                  <td className="small">{e.place}</td>
                  <td className="small nowrap">{e.window.start_local.replace(' IST', '')}<div className="tiny muted">to {e.window.end_local}</div></td>
                  <td className="small nowrap">{directionWord(e.motion.direction)}<div className="tiny muted">{Math.round(e.motion.speed_kmh)} km/h</div></td>
                  <td className="r num small">{pct(e.probability)}</td>
                  <td className="r num small strong">{inr(e.peak.population.total)}</td>
                  <td className="r num small">{e.peak.counts.school}</td>
                  <td className="r num small">{e.peak.counts.hospital}</td>
                  <td><Icon name="chevronR" size={16} style={{ color: 'var(--faint)' }} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <p className="small muted">Agreement = share of the 6 forecast ensemble members that exceed the anomaly threshold at the event&apos;s strongest point. Values at sea have no resident population.</p>
    </div>
  );
}
