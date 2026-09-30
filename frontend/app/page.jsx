'use client';
import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, getStoredUser, getToken, HOME_BY_ROLE, login, register } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import Icon from '@/components/ui/Icon';
import { Logo } from '@/components/ui';

const ROLES = [
  { key: 'official', icon: 'grid', title: 'Government', userLabel: 'Username', placeholder: 'GovtOfficer', hint: 'District emergency officials: command dashboard, alert approval, AI Copilot.' },
  { key: 'institution', icon: 'school', title: 'School / Hospital', userLabel: 'Institution name', placeholder: 'Start typing your institution name…', hint: 'Schools, colleges and hospitals sign in with their registered name.' },
  { key: 'rescue', icon: 'shield', title: 'Rescue team', userLabel: 'Unit name', placeholder: 'e.g. SDRF Unit, Koramangala, Bengaluru', hint: 'NDRF / SDRF / fire units see their pre-position orders.' },
  { key: 'traveller', icon: 'bus', title: 'Bus driver', userLabel: 'Bus number', placeholder: 'e.g. BUS-BLR-009', hint: 'Drivers are warned when their route heads into a risk zone.' },
  { key: 'citizen', icon: 'users', title: 'Citizen', userLabel: 'Mobile number', placeholder: '10-digit mobile number', hint: 'Get alerts for your area. New here? Create an account.' },
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
        setS({ state: 'offline' });
        t = setTimeout(check, 5000);
      }
    };
    check();
    return () => clearTimeout(t);
  }, []);
  const map = {
    checking: ['#8a939c', 'Checking server…'],
    ready: ['#1e8a4c', `Server online · forecast ready${s.h?.gemini ? ' · Gemini AI connected' : ''}`],
    warming: ['#d9a82e', s.h?.pipeline === 'training' ? 'Warming up · training AI models (first start, ~1 min)' : 'Warming up · running forecast pipeline'],
    offline: ['#9e1b1b', 'Backend offline · run: uvicorn app.main:app --port 8000'],
  };
  const [c, text] = map[s.state];
  return (
    <div className="row small" style={{ gap: 8, color: 'var(--muted)' }}>
      <span className={s.state === 'warming' ? 'pulse' : ''} style={{ width: 8, height: 8, borderRadius: 4, background: c, flex: 'none' }} />
      {text}
    </div>
  );
}

function NameSuggest({ role, value, onChange, placeholder, id }) {
  const [list, setList] = useState([]);
  useEffect(() => {
    if (!['institution', 'rescue', 'traveller'].includes(role)) { setList([]); return undefined; }
    const t = setTimeout(async () => {
      try { setList(await api(`/auth/directory?role=${role}&q=${encodeURIComponent(value)}&limit=25`)); } catch { setList([]); }
    }, 180);
    return () => clearTimeout(t);
  }, [role, value]);
  return (
    <>
      <input id={id} className="input" list={`${id}-list`} autoComplete="off" placeholder={placeholder} value={value}
        onChange={(e) => onChange(e.target.value)} required style={{ height: 50, fontSize: 15 }} />
      <datalist id={`${id}-list`}>{list.map((x) => <option key={x.username} value={x.username}>{x.title}</option>)}</datalist>
    </>
  );
}

function RegisterForm({ onDone, onCancel }) {
  const [f, setF] = useState({ name: '', phone: '', email: '', password: '', confirm: '', locality_id: '' });
  const [locs, setLocs] = useState([]);
  const [gps, setGps] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  useEffect(() => { api('/auth/localities').then(setLocs).catch(() => setLocs([])); }, []);
  const groups = useMemo(() => locs.reduce((m, l) => ({ ...m, [l.group]: [...(m[l.group] || []), l] }), {}), [locs]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const useGps = () => navigator.geolocation?.getCurrentPosition(
    (p) => { setGps({ lat: +p.coords.latitude.toFixed(5), lon: +p.coords.longitude.toFixed(5) }); setF({ ...f, locality_id: '' }); },
    () => setErr('Location permission denied. Please choose your area from the list.'));
  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    if (f.password !== f.confirm) return setErr('Passwords do not match');
    if (!gps && !f.locality_id) return setErr('Choose your area or use your current location');
    setBusy(true);
    try {
      const u = await register({ name: f.name, phone: f.phone, email: f.email || null, password: f.password, locality_id: f.locality_id || null, ...(gps || {}) });
      onDone(u);
    } catch (e2) { setErr(e2.message); setBusy(false); }
  };
  return (
    <form className="col gap-16" onSubmit={submit}>
      <div className="row between"><h3 style={{ fontSize: 18 }}>Create a citizen account</h3><button type="button" className="btn ghost sm" onClick={onCancel}>Back to sign in</button></div>
      <div className="grid g2" style={{ gap: 14 }}>
        <div className="field"><label htmlFor="r-name">Full name</label><input id="r-name" className="input" value={f.name} onChange={set('name')} required autoComplete="name" /></div>
        <div className="field"><label htmlFor="r-phone">Mobile number</label><input id="r-phone" className="input" inputMode="numeric" value={f.phone} onChange={set('phone')} required placeholder="10 digits" autoComplete="tel" /></div>
        <div className="field"><label htmlFor="r-pw">Password</label><input id="r-pw" className="input" type="password" value={f.password} onChange={set('password')} required minLength={6} autoComplete="new-password" /></div>
        <div className="field"><label htmlFor="r-pw2">Confirm password</label><input id="r-pw2" className="input" type="password" value={f.confirm} onChange={set('confirm')} required autoComplete="new-password" /></div>
        <div className="field"><label htmlFor="r-email">Email (optional)</label><input id="r-email" className="input" type="email" value={f.email} onChange={set('email')} autoComplete="email" /></div>
        <div className="field"><label htmlFor="r-loc">Your area (for alerts)</label>
          <select id="r-loc" className="select" value={f.locality_id} onChange={(e) => { setGps(null); set('locality_id')(e); }}>
            <option value="">{gps ? `Using my location (${gps.lat}, ${gps.lon})` : 'Choose your ward or city…'}</option>
            {Object.entries(groups).map(([g, ls]) => <optgroup key={g} label={g}>{ls.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}</optgroup>)}
          </select>
        </div>
      </div>
      <div className="row between wrap gap-8">
        <button type="button" className="btn" onClick={useGps}><Icon name="pin" size={16} />Use my current location</button>
        <button className="btn primary lg" disabled={busy}>{busy ? 'Creating account…' : 'Create account & sign in'}</button>
      </div>
      <p className="tiny muted">We only store your name, mobile number and home area to send you weather alerts. No Aadhaar or ID is collected.</p>
      {err && <div className="banner" style={{ background: 'var(--high-tint)', color: 'var(--high-ink)' }}><Icon name="alert" size={16} />{err}</div>}
    </form>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useAuth();
  const [role, setRole] = useState('official');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [mode, setMode] = useState('signin');
  const [expired, setExpired] = useState(false);
  const [quick, setQuick] = useState([]);
  const R = ROLES.find((r) => r.key === role);

  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    setExpired(qs.get('expired') === '1');
    const u = getToken() && getStoredUser();
    if (u && !qs.get('expired')) router.replace(qs.get('next') || HOME_BY_ROLE[u.role] || '/gov');
    api('/auth/quick-access').then(setQuick).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const finish = (u) => {
    setUser(u);
    const next = new URLSearchParams(window.location.search).get('next');
    router.push(next && next.startsWith('/') ? next : HOME_BY_ROLE[u.role]);
  };
  const go = async (u, p) => {
    setBusy(true); setErr(null);
    try {
      finish(await login(u, p));   // routes to the portal of the account's own role
    } catch (e) { setErr(e.message === 'Wrong username or password' ? `Wrong ${R.userLabel.toLowerCase()} or password` : e.message); setBusy(false); }
  };
  const q = quick.find((x) => x.role === role);

  return (
    <main style={{ display: 'flex', minHeight: '100vh', flexWrap: 'wrap' }}>
      <section style={{ flex: '1 1 420px', maxWidth: 560, background: 'var(--navy)', color: '#f3f2ee', padding: '52px 48px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: 36, position: 'relative', overflow: 'hidden' }}>
        <svg aria-hidden="true" viewBox="0 0 400 400" style={{ position: 'absolute', right: -130, bottom: -120, width: 480, opacity: 0.22 }}>
          <defs><radialGradient id="g"><stop offset="0" stopColor="#e53935" stopOpacity=".9" /><stop offset="1" stopColor="#e53935" stopOpacity="0" /></radialGradient></defs>
          <circle cx="200" cy="200" r="190" fill="#fdd835" fillOpacity=".25" />
          <circle cx="200" cy="200" r="125" fill="#fb8c00" fillOpacity=".35" />
          <circle cx="200" cy="200" r="75" fill="url(#g)" />
          <path d="M20 280 C120 260 150 235 200 200 S300 120 390 100" fill="none" stroke="#f3f2ee" strokeWidth="2" strokeDasharray="6 6" />
        </svg>
        <div className="col" style={{ gap: 26, position: 'relative' }}>
          <div className="row" style={{ gap: 12 }}>
            <Logo size={46} />
            <div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>WeatherPulse AI</div>
              <div className="small" style={{ color: '#8fa0b0' }}>Team 404 THINKER&apos;S · SIH 2026 · SIH26078</div>
            </div>
          </div>
          <h1 style={{ fontSize: 46, lineHeight: 1.06, fontWeight: 600, letterSpacing: '-0.025em' }}>Detect. Track.<br />Alert. Protect.</h1>
          <p style={{ fontSize: 17, lineHeight: 1.6, color: '#c9d2da', maxWidth: 420 }}>
            Extreme-weather intelligence for India: where an anomaly may form, where it is heading, who is in its path, and who should be told.
          </p>
          <div className="grid g2" style={{ gap: 12, maxWidth: 440 }}>
            {[['10-day', 'ensemble forecast'], ['3 / 5 / 8 km', 'dynamic risk zones'], ['Census 2011', 'population exposure'], ['6 roles', 'targeted alerts']].map(([a, b]) => (
              <div key={a} style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, padding: '12px 14px' }}>
                <div className="num" style={{ fontSize: 18, fontWeight: 600, color: '#fff' }}>{a}</div>
                <div className="small" style={{ color: '#9fb0c0' }}>{b}</div>
              </div>
            ))}
          </div>
        </div>
        <p className="small" style={{ color: '#8fa0b0', lineHeight: 1.6, position: 'relative' }}>
          Prototype for preparedness. It does not replace official warnings from IMD and State Disaster Management Authorities.
        </p>
      </section>

      <section style={{ flex: '1 1 560px', padding: '48px 56px', display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 900 }}>
        <div className="row between wrap">
          <h2 style={{ fontSize: 30 }}>Sign in</h2>
          <ServerStatus />
        </div>
        {expired && <div className="banner">Your session ended. Please sign in again.</div>}

        <div className="grid" style={{ gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: 10 }} role="tablist" aria-label="I am a">
          {ROLES.map((r) => {
            const on = r.key === role;
            return (
              <button key={r.key} role="tab" aria-selected={on} onClick={() => { setRole(r.key); setUsername(''); setPassword(''); setErr(null); setMode('signin'); }}
                style={{ border: on ? '2px solid var(--accent)' : '1px solid var(--line)', background: on ? 'var(--accent-tint)' : '#fff', borderRadius: 12, padding: '14px 8px', cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, font: 'inherit', color: on ? 'var(--accent-2)' : 'var(--ink)' }}>
                <Icon name={r.icon} size={22} />
                <span className="small" style={{ fontWeight: on ? 700 : 500, textAlign: 'center' }}>{r.title}</span>
              </button>
            );
          })}
        </div>

        <div className="card" style={{ padding: 26 }}>
          {role === 'citizen' && mode === 'register' ? <RegisterForm onDone={finish} onCancel={() => setMode('signin')} /> : (
            <form className="col gap-16" onSubmit={(e) => { e.preventDefault(); go(username, password); }}>
              <div className="small muted">{R.hint}</div>
              <div className="field">
                <label htmlFor="user">{R.userLabel}</label>
                {['institution', 'rescue', 'traveller'].includes(role)
                  ? <NameSuggest id="user" role={role} value={username} onChange={setUsername} placeholder={R.placeholder} />
                  : <input id="user" className="input" autoComplete="username" placeholder={R.placeholder} value={username} onChange={(e) => setUsername(e.target.value)} required style={{ height: 50, fontSize: 15 }} />}
              </div>
              <div className="field">
                <label htmlFor="pw">Password</label>
                <div style={{ position: 'relative' }}>
                  <input id="pw" className="input" type={show ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required style={{ height: 50, fontSize: 15, width: '100%', paddingRight: 70 }} />
                  <button type="button" className="btn ghost sm" style={{ position: 'absolute', right: 6, top: 9 }} onClick={() => setShow((x) => !x)}>{show ? 'Hide' : 'Show'}</button>
                </div>
              </div>
              {err && <div className="banner" style={{ background: 'var(--high-tint)', color: 'var(--high-ink)' }}><Icon name="alert" size={16} />{err}</div>}
              <div className="row between wrap gap-8">
                {role === 'citizen'
                  ? <button type="button" className="btn" onClick={() => setMode('register')}><Icon name="plus" size={16} />Create account</button>
                  : <span className="small muted">Logins are listed in the demo accounts sheet.</span>}
                <button className="btn primary lg" disabled={busy} style={{ minWidth: 180 }}>{busy ? 'Signing in…' : 'Sign in'}</button>
              </div>
            </form>
          )}
        </div>

        {q && mode === 'signin' && (
          <div className="row between wrap gap-8" style={{ border: '1px dashed var(--line)', borderRadius: 12, padding: '12px 16px', background: 'var(--surface-2)' }}>
            <div className="small" style={{ minWidth: 0 }}>
              <span className="badge warn mono tiny" style={{ marginRight: 8 }}>JUDGE DEMO</span>
              <span className="muted">Try:</span> <b>{q.username}</b> <span className="muted">/</span> <span className="mono">{q.password}</span>
            </div>
            <button className="btn sm" onClick={() => { setUsername(q.username); setPassword(q.password); }}>Fill in</button>
          </div>
        )}
      </section>
    </main>
  );
}
