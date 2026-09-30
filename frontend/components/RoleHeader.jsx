'use client';
import { Logo } from '@/components/ui';
import Icon from '@/components/ui/Icon';
import { useAuth } from '@/lib/auth';

export default function RoleHeader({ portal, right, dark = false }) {
  const { user, signOut } = useAuth();
  return (
    <header className="m-head" style={dark ? { background: '#14202b', borderColor: '#22313f', color: '#fff' } : undefined}>
      <div className="row gap-8" style={{ minWidth: 0 }}>
        <Logo size={30} />
        <div style={{ minWidth: 0 }}>
          <div className="strong" style={{ fontSize: 15 }}>WeatherPulse</div>
          <div className="tiny" style={{ color: dark ? '#9fb0c0' : 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{portal}{user ? ` · ${user.name}` : ''}</div>
        </div>
      </div>
      <div className="row gap-6">
        {right}
        <button className="btn ghost iconbtn" onClick={signOut} aria-label="Sign out" title="Sign out" style={dark ? { color: '#c9d2da' } : undefined}><Icon name="logout" size={17} /></button>
      </div>
    </header>
  );
}
