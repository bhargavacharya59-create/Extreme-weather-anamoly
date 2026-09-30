'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, getStoredUser, getToken, HOME_BY_ROLE, login } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import Icon from '@/components/ui/Icon';
import { Logo } from '@/components/ui';

const ROLES = [
  { email: 'officer@demo.in', icon: 'grid', title: 'Government official', text: 'Command dashboard, citizens in the risk zone, alert approval, AI Copilot' },
  { email: 'school@demo.in', icon: 'school', title: 'School / college', text: 'Your campus risk, countdown, preparedness checklist, acknowledge alerts' },
  { email: 'hospital@demo.in', icon: 'hospital', title: 'Hospital', text: 'Surge readiness, risk window and approved guidance for your facility' },
  { email: 'rescue@demo.in', icon: 'shield', title: 'Rescue team', text: 'Pre-position orders, staging point, route and team status' },
  { email: 'citizen@demo.in', icon: 'users', title: 'Citizen', text: 'Location alert, what to do, rain timeline, nearest shelter, helplines' },
  { email: 'driver@demo.in', icon: 'bus', title: 'Traveller / driver', text: 'Warned when your route heads into a risk zone, with a safer route' },
];

function ServerStatus() {
  const [s, setS] = useState({ state: 'checking' });
  useEffect(() => {
    let t;
    const check = async () => {
      try {
        const h = await api('/health');
        setS({ state: h.pipeline === 'ready' ? 'ready' : 'warming', h });
        if (h.pipeline !== 'ready') t = setTimeout(check, 3000);
      } catch (e) {
        setS({ state: 'offline', msg: e.message });
        t = setTimeout(check, 5000);
      }
    };
    check();
    return () => clearTimeout(t);
  }, []);
  const map = {
    checking: ['#8a939c', 'Checking server…'],
    ready: ['#1e8a4c', `Server online · forecast run ready${s.h?.gemini ? ' · Gemini connected' : ''}`],
    warming: ['#d9a82e', s.h?.pipeline === 'training' ? 'Server warming up · training AI models (first start, ~1 min)' : 'Server warming up · running forecast pipeline'],
    offline: ['#9e1b1b', 'Backend offline · start it with: uvicorn app.main:app --port 8000'],
  };
  const [c, text] = map[s.state];
  return (
    <div className="row small" style={{ gap: 8, color: 'var(--muted)' }}>
      <span className={s.state === 'warming' ? 'pulse' : ''} style={{ width: 8, height: 8, borderRadius: 4, background: c }} />
      {text}
    </div>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    setExpired(qs.get('expired') === '1');
    const u = getToken() && getStoredUser();
    if (u && !qs.get('expired')) router.replace(qs.get('next') || HOME_BY_ROLE[u.role] || '/gov');
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const go = async (em, pw, key) => {
    setBusy(key); setErr(null);
    try {
      const u = await login(em, pw);
      setUser(u);
      const next = new URLSearchParams(window.location.search).get('next');
      router.push(next && next.startsWith('/') ? next : HOME_BY_ROLE[u.role]);
    } catch (e) {
      setErr(e.message);
      setBusy(null);
    }
  };

  return (
    <main style={{ display: 'flex', minHeight: '100vh', flexWrap: 'wrap' }}>
      <section style={{ flex: '1 1 440px', maxWidth: 580, background: 'var(--navy)', color: '#f3f2ee', padding: '56px 52px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: 40, position: 'relative', overflow: 'hidden' }}>
        <svg aria-hidden="true" viewBox="0 0 400 400" style={{ position: 'absolute', right: -120, bottom: -120, width: 460, opacity: 0.16 }}>
          {[190, 130, 80].map((r, i) => <circle key={r} cx="200" cy="200" r={r} fill="none" stroke={['#d9a82e', '#dd6b27', '#e0572e'][i]} strokeWidth="2" />)}
          <path d="M40 260 C120 250 150 230 200 200 S300 120 380 110" fill="none" stroke="#f3f2ee" strokeWidth="2" strokeDasharray="6 6" />
        </svg>
        <div className="col" style={{ gap: 28, position: 'relative' }}>
          <div className="row" style={{ gap: 12 }}>
            <Logo size={44} />
            <div>
              <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.01em' }}>WeatherPulse AI</div>
              <div className="small" style={{ color: '#8fa0b0' }}>Team 404 THINKER&apos;S · SIH 2026 · SIH26078</div>
            </div>
          </div>
          <h1 style={{ fontSize: 46, lineHeight: 1.08, fontWeight: 600, letterSpacing: '-0.025em' }}>Detect. Track.<br />Alert. Protect.</h1>
          <p style={{ fontSize: 17, lineHeight: 1.6, color: '#c9d2da', maxWidth: 430 }}>
            Turns medium-range weather forecasts into local impact intelligence: where an extreme event may form, where it is heading, who is in its path, and who should be told.
          </p>
          <div className="col" style={{ gap: 14 }}>
            {[
              ['#e0572e', 'AI anomaly detection on 10-day ensemble forecasts'],
              ['#dd6b27', 'Dynamic 3 / 5 / 8 km impact zones with path uncertainty'],
              ['#d9a82e', 'Citizens in the zone from Census of India 2011 data'],
              ['#7fd1a1', 'Targeted alerts: officials, institutions, citizens and moving vehicles'],
            ].map(([c, t]) => (
              <div key={t} className="row" style={{ gap: 12, fontSize: 15, color: '#dde3e8' }}>
                <span style={{ width: 8, height: 8, borderRadius: 4, background: c, flex: 'none' }} />{t}
              </div>
            ))}
          </div>
        </div>
        <p className="small" style={{ color: '#8fa0b0', lineHeight: 1.6, position: 'relative' }}>
          Prototype for preparedness. It does not replace official forecasts or warnings; those come from IMD and State Disaster Management Authorities.
        </p>
      </section>

      <section style={{ flex: '1 1 560px', padding: '48px 56px', display: 'flex', flexDirection: 'column', gap: 26, maxWidth: 980 }}>
        <div className="row between wrap">
          <h2 style={{ fontSize: 28 }}>Sign in</h2>
          <span className="badge warn mono">DEMO MODE · SYNTHETIC FORECAST</span>
        </div>
        {expired && <div className="banner">Your session ended. Please sign in again.</div>}
        <form className="col" style={{ gap: 16 }} onSubmit={(e) => { e.preventDefault(); go(email, password, 'form'); }}>
          <div className="grid g2" style={{ gap: 16 }}>
            <div className="field">
              <label htmlFor="email">Official email or username</label>
              <input id="email" className="input" type="email" autoComplete="username" placeholder="officer@demo.in" value={email} onChange={(e) => setEmail(e.target.value)} required style={{ height: 48 }} />
            </div>
            <div className="field">
              <label htmlFor="pw">Password</label>
              <input id="pw" className="input" type="password" autoComplete="current-password" placeholder="demo123" value={password} onChange={(e) => setPassword(e.target.value)} required style={{ height: 48 }} />
            </div>
          </div>
          <div className="row between wrap">
            <ServerStatus />
            <button className="btn primary lg" disabled={!!busy}>{busy === 'form' ? 'Signing in…' : 'Sign in securely'}</button>
          </div>
          {err && <div className="banner" style={{ background: 'var(--high-tint)', color: 'var(--high-ink)' }}><Icon name="alert" size={16} />{err}</div>}
        </form>

        <div className="divider" />
        <div>
          <h3 style={{ fontSize: 18 }}>Or open a demo account</h3>
          <p className="muted small" style={{ marginTop: 4 }}>Fictional accounts for judges (password demo123). Each role sees only what it needs.</p>
        </div>
        <div className="grid g3">
          {ROLES.map((r) => (
            <button key={r.email} onClick={() => go(r.email, 'demo123', r.email)} disabled={!!busy}
              className="card" style={{ textAlign: 'left', padding: 18, display: 'flex', flexDirection: 'column', gap: 9, cursor: 'pointer', minHeight: 150, font: 'inherit', color: 'inherit' }}>
              <div className="row between" style={{ width: '100%' }}>
                <span style={{ width: 38, height: 38, borderRadius: 10, background: 'var(--accent-tint)', color: 'var(--accent)', display: 'grid', placeItems: 'center' }}><Icon name={r.icon} size={20} /></span>
                {busy === r.email ? <Icon name="refresh" className="spin" /> : <Icon name="arrowR" size={16} style={{ color: 'var(--faint)' }} />}
              </div>
              <div style={{ fontSize: 16, fontWeight: 600 }}>{r.title}</div>
              <div className="small muted" style={{ lineHeight: 1.45 }}>{r.text}</div>
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
