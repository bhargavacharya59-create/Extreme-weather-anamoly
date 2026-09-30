'use client';
import { createContext, useContext, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import Icon from '@/components/ui/Icon';
import { Logo, Segmented } from '@/components/ui';
import { useAuth, useRequireRole } from '@/lib/auth';
import { useApi } from '@/lib/useApi';

const GovCtx = createContext(null);
export const useGov = () => useContext(GovCtx);

export const LEAD_OPTIONS = [
  { value: null, label: 'Peak impact' },
  { value: 0, label: 'Now' },
  { value: 24, label: '+24 h' },
  { value: 72, label: '+3 days' },
  { value: 168, label: '+7 days' },
  { value: 240, label: '+10 days' },
];

const NAV = [
  { href: '/gov', icon: 'grid', label: 'Overview' },
  { href: '/gov/map', icon: 'map', label: 'Risk map' },
  { href: '/gov/anomalies', icon: 'track', label: 'Anomaly tracking' },
  { href: '/gov/population', icon: 'users', label: 'Affected areas & population' },
  { href: '/gov/institutions', icon: 'school', label: 'Institutions' },
  { href: '/gov/vehicles', icon: 'bus', label: 'Vehicles & transport' },
  { href: '/gov/alerts', icon: 'bell', label: 'Alerts & approvals', badge: 'alerts' },
  { href: '/gov/copilot', icon: 'chat', label: 'AI Copilot' },
  { href: '/gov/reports', icon: 'file', label: 'Reports & analytics' },
  { href: '/gov/settings', icon: 'settings', label: 'Settings' },
];

function Clock() {
  const [t, setT] = useState(null);
  useEffect(() => {
    const f = () => setT(new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' }));
    f();
    const i = setInterval(f, 30000);
    return () => clearInterval(i);
  }, []);
  return <span className="num">{t} IST</span>;
}

export default function GovShell({ children }) {
  const { user, allowed } = useRequireRole('official');
  const { signOut } = useAuth();
  const path = usePathname();
  const [leadH, setLeadH] = useState(null);
  const [selected, setSelected] = useState(null);
  const summary = useApi(allowed ? `/dashboard/summary${leadH != null ? `?lead_h=${leadH}` : ''}` : null, { poll: 60000 });
  const events = useApi(allowed ? '/anomalies' : null, { poll: 120000 });

  useEffect(() => {
    if (!selected && summary.data?.top_event) setSelected(summary.data.top_event);
  }, [summary.data, selected]);

  if (!allowed) return <div className="empty" style={{ minHeight: '100vh' }}><Icon name="refresh" className="spin" />Checking access…</div>;

  const run = summary.data?.run;
  const pending = summary.data?.alerts_pending;
  const value = { leadH, setLeadH, selected, setSelected, summary, events, run };

  return (
    <GovCtx.Provider value={value}>
      <div className="shell">
        <aside className="sidebar" aria-label="Main navigation">
          <Link href="/gov" className="brand">
            <Logo />
            <div>
              <div className="brand-name">WeatherPulse AI</div>
              <div className="brand-sub">Emergency operations</div>
            </div>
          </Link>
          <div className="userbox">
            <div className="n">{user?.name} <span className="small" style={{ color: '#8fa0b0', fontWeight: 400 }}>(demo)</span></div>
            <div className="t">{user?.title}<br />{user?.org}</div>
          </div>
          <nav className="nav">
            {NAV.map((n) => {
              const active = n.href === '/gov' ? path === '/gov' : path.startsWith(n.href);
              return (
                <Link key={n.href} href={n.href} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined}>
                  <Icon name={n.icon} size={17} />{n.label}
                  {n.badge === 'alerts' && pending > 0 && <span className="count">{pending}</span>}
                </Link>
              );
            })}
          </nav>
          <div className="sources">
            <div className="k">Data sources</div>
            <div className="r"><span>Forecast</span><span className="synthetic">Synthetic ensemble</span></div>
            <div className="r"><span>Baseline</span><span className="synthetic">ERA5-like</span></div>
            <div className="r"><span>Population</span><span className="official">Census 2011</span></div>
            <div className="r"><span>Institutions</span><span className="synthetic">Simulated</span></div>
            <div className="r"><span>Map</span><span>OpenStreetMap</span></div>
            <div className="r"><span>Model</span><span className="mono">v0.1</span></div>
          </div>
          <button className="btn ghost" onClick={signOut} style={{ color: '#c9d2da', justifyContent: 'flex-start' }}>
            <Icon name="logout" size={16} />Sign out
          </button>
        </aside>
        <div className="main">
          <header className="topbar">
            <div className="col" style={{ gap: 2, minWidth: 0 }}>
              <div className="row small" style={{ gap: 8, color: 'var(--muted)' }}>
                <span style={{ width: 8, height: 8, borderRadius: 4, background: run ? '#1e8a4c' : '#d9a82e' }} className={run ? '' : 'pulse'} />
                {run ? <>Forecast run <span className="mono">{run.run_id}</span> · issued {run.issue_time_local}</> : 'Loading forecast run…'}
              </div>
              <div className="small faint">{run ? `${run.params.members}-member ensemble · ${run.params.grid_res_deg}° grid · lead time up to 10 days` : ''}</div>
            </div>
            <div className="grow" />
            <Segmented label="Forecast time" options={LEAD_OPTIONS} value={leadH} onChange={setLeadH} />
            <span className="small muted nowrap"><Clock /></span>
          </header>
          {children}
        </div>
      </div>
    </GovCtx.Provider>
  );
}
