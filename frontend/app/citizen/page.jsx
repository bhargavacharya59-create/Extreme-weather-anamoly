'use client';
import { useMemo, useState } from 'react';
import MapView from '@/components/map/MapView';
import RoleHeader from '@/components/RoleHeader';
import { ErrorBox, Skeleton, toast } from '@/components/ui';
import Icon from '@/components/ui/Icon';
import { useRequireRole } from '@/lib/auth';
import { pct, RISK, TYPE_LABEL } from '@/lib/format';
import { useApi } from '@/lib/useApi';

// Headings in Kannada; detailed guidance stays in English unless Gemini translation is configured.
const T = {
  en: { high: 'HIGH RISK NEAR YOU', moderate: 'MODERATE RISK NEAR YOU', low: 'RISK NEARBY', safe: 'No risk forecast at your location', todo: 'What to do now', rain: 'Rain expected at your location', shelter: 'Nearest safe shelter', help: 'Disaster helpline', loc: 'Use my location', you: 'You' },
  kn: { high: 'ನಿಮ್ಮ ಬಳಿ ಹೆಚ್ಚಿನ ಅಪಾಯ', moderate: 'ನಿಮ್ಮ ಬಳಿ ಮಧ್ಯಮ ಅಪಾಯ', low: 'ಹತ್ತಿರದಲ್ಲಿ ಅಪಾಯ', safe: 'ನಿಮ್ಮ ಸ್ಥಳದಲ್ಲಿ ಅಪಾಯದ ಮುನ್ಸೂಚನೆ ಇಲ್ಲ', todo: 'ಈಗ ಏನು ಮಾಡಬೇಕು', rain: 'ನಿಮ್ಮ ಸ್ಥಳದಲ್ಲಿ ನಿರೀಕ್ಷಿತ ಮಳೆ', shelter: 'ಹತ್ತಿರದ ಸುರಕ್ಷಿತ ಆಶ್ರಯ', help: 'ವಿಪತ್ತು ಸಹಾಯವಾಣಿ', loc: 'ನನ್ನ ಸ್ಥಳ ಬಳಸಿ', you: 'ನೀವು' },
};

export default function CitizenApp() {
  const { allowed } = useRequireRole('citizen', 'official');
  const [loc, setLoc] = useState(null);
  const [lang, setLang] = useState('en');
  const t = T[lang];
  const q = loc ? `?lat=${loc.lat}&lon=${loc.lon}` : '';
  const { data: d, error, reload } = useApi(allowed ? `/citizen/status${q}` : null);
  const r = d?.risk;

  const useMine = () => {
    if (!navigator.geolocation) return toast('Location is not available on this device');
    navigator.geolocation.getCurrentPosition((p) => setLoc({ lat: p.coords.latitude.toFixed(4), lon: p.coords.longitude.toFixed(4) }), () => toast('Location permission denied; showing demo location'));
  };

  const bars = useMemo(() => {
    if (!d?.weather) return [];
    const w = d.weather;
    const start = r ? Math.max(0, r.event.window.start_lead_h - 24) : 0;
    const out = [];
    for (let i = 0; i < w.lead_h.length && out.length < 10; i++) {
      if (w.lead_h[i] < start) continue;
      out.push({ label: w.valid_local[i].replace(' IST', '').split(', ')[1], day: w.valid_local[i].split(',')[0], v: w.variables.precip.mean[i] });
    }
    return out;
  }, [d, r]);
  const maxV = Math.max(10, ...bars.map((b) => b.v));
  const zoneFc = r && { type: 'FeatureCollection', features: ['low', 'moderate', 'high'].map((k) => ({ type: 'Feature', properties: { ring: k, event_id: r.event.id, severity: r.event.severity }, geometry: { type: 'Polygon', coordinates: [r.zone.rings[k]] } })) };
  const ring = r?.ring;

  return (
    <div className="app-mobile">
      <div className="app-col">
        <RoleHeader portal="Citizen alerts" right={
          <button className="btn sm" onClick={() => setLang((l) => (l === 'en' ? 'kn' : 'en'))} aria-label="Switch language" style={{ fontFamily: 'var(--sans), "Noto Sans Kannada"' }}>{lang === 'en' ? 'ಕನ್ನಡ' : 'English'}</button>} />
        <div className="m-body" style={{ fontFamily: lang === 'kn' ? 'var(--sans), "Noto Sans Kannada"' : undefined }}>
          <div className="banner small"><span className="tag">DEMO</span>Synthetic scenario. Official warnings: IMD / KSNDMC.</div>
          <ErrorBox error={error} onRetry={reload} />
          {!d ? <><Skeleton h={150} /><Skeleton h={220} /></> : !r ? (
            <div className="m-card col gap-8" style={{ background: 'var(--good-tint)', borderColor: '#bfe0cb' }}>
              <div className="row gap-8 strong" style={{ color: 'var(--good)' }}><Icon name="check" />{t.safe}</div>
              <div className="small">No anomaly zone reaches {d.ward ? d.ward.ward_name : 'your location'} in the next 10 days.</div>
            </div>
          ) : (
            <>
              <section className="col gap-8" style={{ background: ring === 'low' ? RISK.low.fill : RISK[ring].fill, color: ring === 'low' ? '#14202b' : '#fff', borderRadius: 16, padding: 18 }} role="alert">
                <div className="row between tiny" style={{ fontWeight: 700, letterSpacing: '0.04em' }}><span>{t[ring]}</span><span style={{ opacity: 0.9, fontWeight: 500 }}>{pct(r.event.probability)} confidence</span></div>
                <div style={{ fontSize: 22, fontWeight: 600, lineHeight: 1.25 }}>{TYPE_LABEL[r.event.type]} likely {r.event.window.start_local.replace(' IST', '')} to {r.event.window.end_local.replace(' IST', '')}</div>
                <div className="small" style={{ lineHeight: 1.5, opacity: 0.95 }}>
                  You are {r.distance_km} km from the forecast centre{d.ward ? ` (${d.ward.ward_name} ward)` : ''}, in the {RISK[ring].label.toLowerCase()}-risk ring. {r.event.type === 'heavy_rainfall' ? 'Underpasses and low roads may flood.' : ''}
                </div>
              </section>

              <MapView zones={zoneFc} height={260} fit="data" fitKey={`${d.lat}`} interactive={false} title={d.home_label || d.ward?.ward_name || 'Your area'}
                markers={[{ lon: d.lon, lat: d.lat, label: t.you }, ...(d.shelter ? [{ lon: d.shelter.lon, lat: d.shelter.lat, label: 'Shelter', tone: 'shelter' }] : [])]} />

              <section className="m-card col gap-10">
                <h2 style={{ fontSize: 16 }}>{t.todo}</h2>
                {r.guidance.map((g, i) => (
                  <div key={g} className="row-top small" style={{ gap: 10, lineHeight: 1.45 }}>
                    <span style={{ minWidth: 22, height: 22, borderRadius: 11, background: 'var(--navy)', color: '#fff', fontSize: 12, fontWeight: 700, display: 'grid', placeItems: 'center' }}>{i + 1}</span>{g}
                  </div>
                ))}
              </section>

              {(r.event.type === 'heavy_rainfall' || r.event.type === 'cyclone') && (
                <section className="m-card col gap-8">
                  <h2 style={{ fontSize: 16 }}>{t.rain}</h2>
                  <div className="row" style={{ alignItems: 'flex-end', gap: 5, height: 110 }} role="img" aria-label="Rain by 6-hour period">
                    {bars.map((b, i) => (
                      <div key={i} className="col" style={{ flex: 1, alignItems: 'center', gap: 4 }} title={`${b.day} ${b.label}: ${b.v.toFixed(0)} mm`}>
                        <span className="tiny num muted">{b.v >= 5 ? Math.round(b.v) : ''}</span>
                        <div style={{ width: '100%', height: Math.max(3, (b.v / maxV) * 72), borderRadius: 4, background: b.v > 40 ? RISK.high.fill : b.v > 15 ? RISK.moderate.fill : '#9ec5f4' }} />
                        <span className="tiny muted" style={{ fontSize: 10 }}>{b.label}</span>
                      </div>
                    ))}
                  </div>
                  <div className="tiny muted">mm per 6 hours (ensemble mean). Red = very heavy, orange = heavy.</div>
                </section>
              )}

              <div className="grid g2" style={{ gap: 10 }}>
                {d.shelter && (
                  <a className="m-card col gap-4" style={{ color: 'var(--ink)', padding: 14 }} href={`https://www.openstreetmap.org/directions?to=${d.shelter.lat}%2C${d.shelter.lon}`} target="_blank" rel="noreferrer">
                    <span className="tiny muted">{t.shelter}</span>
                    <span className="small strong">{d.shelter.name}</span>
                    <span className="tiny muted">{d.shelter.distance_km} km · directions</span>
                  </a>
                )}
                <a className="col gap-4" href="tel:1070" style={{ background: 'var(--navy)', color: '#fff', borderRadius: 14, padding: 14 }}>
                  <span className="tiny" style={{ color: '#c9d2da' }}>{t.help}</span>
                  <span className="num" style={{ fontSize: 24, fontWeight: 600 }}>1070</span>
                  <span className="tiny" style={{ color: '#c9d2da' }}>Emergency 112</span>
                </a>
              </div>
            </>
          )}
          <button className="btn block" onClick={useMine}><Icon name="pin" size={16} />{t.loc}</button>
          <p className="tiny muted" style={{ textAlign: 'center' }}>Your location is used only to check risk while this page is open. Demo location: {d ? `${d.lat}, ${d.lon}` : '…'}</p>
        </div>
      </div>
    </div>
  );
}
