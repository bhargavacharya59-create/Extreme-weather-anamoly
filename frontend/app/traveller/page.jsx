'use client';
import { useEffect, useState } from 'react';
import MapView, { LEGEND } from '@/components/map/MapView';
import RoleHeader from '@/components/RoleHeader';
import { ErrorBox, Skeleton, toast } from '@/components/ui';
import Icon from '@/components/ui/Icon';
import { useRequireRole } from '@/lib/auth';
import { KIND_LABEL, RISK, TYPE_LABEL } from '@/lib/format';
import { useApi } from '@/lib/useApi';

export default function TravellerApp() {
  const { allowed } = useRequireRole('traveller', 'official');
  const { data: d, error, reload } = useApi(allowed ? '/traveller/status' : null);
  const [choice, setChoice] = useState(null);
  const v = d?.vehicle;
  const ev = d?.event;

  const speak = () => {
    if (!d?.vehicle || d.clear || typeof window === 'undefined' || !window.speechSynthesis) return;
    const msg = v.status === 'inside'
      ? `Warning. You are inside a ${ev.severity} risk ${TYPE_LABEL[ev.type]} zone. Stop at a safe, raised place.`
      : `Warning. ${TYPE_LABEL[ev.type]} risk zone ahead in about ${v.eta_min} minutes. A safer route adds ${d.routes.extra_min} minutes.`;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(msg));
  };
  useEffect(() => { if (d?.vehicle && !d.clear) { const t = setTimeout(speak, 800); return () => clearTimeout(t); } return undefined; }, [d?.vehicle?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const zoneFc = d?.zone && { type: 'FeatureCollection', features: ['low', 'moderate', 'high'].map((k) => ({ type: 'Feature', properties: { ring: k, event_id: ev.id, severity: ev.severity }, geometry: { type: 'Polygon', coordinates: [d.zone.rings[k]] } })) };
  const inside = v?.status === 'inside';

  return (
    <div className="app-mobile app-dark">
      <div className="app-col">
        <RoleHeader dark portal={v ? `Driver mode · ${v.id}` : 'Driver mode'} right={
          <button className="btn sm" style={{ background: '#1e2e3d', color: '#fff', borderColor: '#33485c' }} onClick={speak} aria-label="Read alert aloud"><Icon name="bell" size={14} />Speak</button>} />
        <div className="m-body">
          <div className="banner small" style={{ background: '#3a2f12', color: '#f5d98c' }}><span className="tag">DEMO</span>Simulated vehicle and synthetic forecast.</div>
          <ErrorBox error={error} onRetry={reload} />
          {!d ? <><Skeleton h={130} style={{ opacity: 0.2 }} /><Skeleton h={360} style={{ opacity: 0.2 }} /></> : d.clear || !v ? (
            <div className="col gap-12">
              <section className="col gap-6" style={{ background: '#15392a', border: '1px solid #2c6b4c', borderRadius: 16, padding: 18 }}>
                <div className="tiny" style={{ fontWeight: 700, letterSpacing: '0.05em', color: '#7fd1a1' }}>ROUTE CLEAR</div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>No risk zone on your route</div>
                <div className="small" style={{ color: '#c9d2da' }}>We check your heading and speed against every forecast risk zone. You will be alerted here if that changes.</div>
              </section>
              {v && <div className="m-card" style={{ background: '#1e2e3d', borderColor: '#33485c', color: '#fff' }}>
                <div className="small" style={{ color: '#9fb0c0' }}>Your vehicle</div>
                <div className="strong">{v.id} · {KIND_LABEL[v.kind]} · {v.operator}</div>
                <div className="small" style={{ color: '#9fb0c0', marginTop: 4 }}>Speed {Math.round(v.speed_kmh)} km/h · heading {Math.round(v.heading_deg)}°</div>
              </div>}
              {d.nearest && <div className="m-card" style={{ background: '#1e2e3d', borderColor: '#33485c', color: '#fff' }}>
                <div className="small" style={{ color: '#9fb0c0' }}>Nearest forecast risk zone</div>
                <div className="strong">{TYPE_LABEL[d.nearest.event.type]} · {d.nearest.event.place}</div>
                <div className="small" style={{ color: '#9fb0c0', marginTop: 4 }}>{d.nearest.distance_km} km away · {d.nearest.event.window.start_local}</div>
              </div>}
            </div>
          ) : (
            <>
              <section role="alert" className="col gap-6" style={{ background: inside ? RISK.high.fill : RISK.moderate.fill, color: inside ? '#fff' : '#14202b', borderRadius: 16, padding: 18 }}>
                <div className="tiny" style={{ fontWeight: 700, letterSpacing: '0.05em' }}>{inside ? 'YOU ARE INSIDE A RISK ZONE' : 'YOU ARE HEADING INTO A RISK ZONE'}</div>
                <div style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.2 }}>
                  {inside ? `${RISK[v.ring].label}-risk ${TYPE_LABEL[ev.type].toLowerCase()} zone` : `${RISK[v.ring].label}-risk zone ahead in about ${v.eta_min} min`}
                </div>
                <div className="small" style={{ lineHeight: 1.45 }}>
                  {inside ? 'Slow down and stop at a safe, raised place. Do not drive through flowing water.' : `${TYPE_LABEL[ev.type]} near ${ev.place.split(',')[0]}; zone centre ${v.distance_km} km away. The safer route skirts the outer ring and adds about ${d.routes.extra_min} min.`}
                </div>
              </section>

              <MapView zones={zoneFc} routes={d.routes} height={360} fit="data" fitKey={v.id}
                markers={[{ lon: v.lon, lat: v.lat, label: `${KIND_LABEL[v.kind]} ${v.id.split('-').pop()}`, tone: 'vehicle' }]}
                title="Route check" legend={[LEGEND.current, LEGEND.safer]} compact>
              </MapView>

              {choice ? (
                <div className="m-card row gap-8" style={{ background: choice === 'safer' ? '#15392a' : '#1e2e3d', borderColor: choice === 'safer' ? '#2c6b4c' : '#33485c', color: '#fff' }}>
                  <Icon name={choice === 'safer' ? 'check' : 'info'} />
                  <div className="small">{choice === 'safer' ? 'Rerouting via the safer route. Fleet control has been informed.' : 'Keeping current route. Drive slowly; alerts will continue.'}</div>
                </div>
              ) : (
                <>
                  <button className="btn lg block" style={{ height: 56, background: '#4cb782', color: '#0e2a1c', border: 0, fontWeight: 700, fontSize: 17 }} onClick={() => { setChoice('safer'); toast('Safer route selected'); }}>
                    <Icon name="route" size={18} />Take safer route
                  </button>
                  <button className="btn lg block" style={{ background: 'transparent', color: '#fff', borderColor: '#3c5064' }} onClick={() => setChoice('keep')}>Keep current route</button>
                </>
              )}

              <div className="grid g3" style={{ gap: 8 }}>
                {[['Event', TYPE_LABEL[ev.type]], ['Zone moves', `${ev.motion.direction} ${Math.round(ev.motion.speed_kmh)} km/h`], ['Until', ev.window.end_local.split(', ')[1]?.replace(' IST', '') || '']].map(([k, val]) => (
                  <div key={k} style={{ background: '#1e2e3d', borderRadius: 10, padding: 10 }}>
                    <div className="tiny" style={{ color: '#9fb0c0' }}>{k}</div><div className="small strong">{val}</div>
                  </div>
                ))}
              </div>
              <ul className="small" style={{ color: '#c9d2da', margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>{d.guidance.map((g) => <li key={g}>{g}</li>)}</ul>
              <p className="tiny" style={{ color: '#9fb0c0' }}>Speed {Math.round(v.speed_kmh)} km/h · heading {Math.round(v.heading_deg)}° · {v.operator} · forecast valid {d.valid_local}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
