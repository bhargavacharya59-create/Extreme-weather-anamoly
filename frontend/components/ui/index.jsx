'use client';
import { useEffect, useState } from 'react';
import Icon, { TYPE_ICON } from './Icon';
import { RISK, SEV_TO_RING, TYPE_LABEL } from '@/lib/format';

export function SeverityBadge({ severity, solid = false, children }) {
  const ring = SEV_TO_RING[severity] || severity;
  return (
    <span className={`badge ${solid && ring === 'high' ? 'solid-high' : ring}`}>
      {!solid && <span className="dot" />}
      {children || `${RISK[ring]?.label || severity}${solid ? '' : ' risk'}`}
    </span>
  );
}

export function RingBadge({ ring }) {
  if (!ring) return <span className="badge neutral">Outside</span>;
  return <span className={`badge ${ring}`}><span className="dot" />{RISK[ring].label} · {RISK[ring].range}</span>;
}

export function TypeLabel({ type, size = 16 }) {
  return (
    <span className="row gap-6" style={{ display: 'inline-flex' }}>
      <Icon name={TYPE_ICON[type] || 'alert'} size={size} />
      {TYPE_LABEL[type] || type}
    </span>
  );
}

export function Card({ title, action, children, footer, className = '', bodyClass = 'card-body', style }) {
  return (
    <section className={`card ${className}`} style={style}>
      {(title || action) && (
        <div className="card-head">
          {typeof title === 'string' ? <h3>{title}</h3> : title}
          {action}
        </div>
      )}
      <div className={bodyClass}>{children}</div>
      {footer && <div className="card-foot">{footer}</div>}
    </section>
  );
}

export function Kpi({ label, value, foot, hero = false, icon, accent }) {
  return (
    <div className={`card kpi ${hero ? 'hero' : ''}`}>
      <div className="label">{icon && <Icon name={icon} size={15} />}{label}</div>
      <div className="value" style={accent ? { color: accent } : undefined}>{value}</div>
      {foot && <div className="foot">{foot}</div>}
    </div>
  );
}

export function Stat({ k, v, sub }) {
  return (
    <div className="stat">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
      {sub && <div className="small muted">{sub}</div>}
    </div>
  );
}

export function DemoBanner({ children }) {
  return (
    <div className="banner" role="note">
      <span className="tag">DEMO DATA</span>
      <span>{children || 'Synthetic forecast scenario. Weather, institutions and vehicles are simulated; population uses Census of India 2011 (projected). Not an official IMD warning.'}</span>
    </div>
  );
}

export function Skeleton({ h = 16, w = '100%', style }) {
  return <div className="skel" style={{ height: h, width: w, ...style }} />;
}

export function Empty({ icon = 'info', title, children }) {
  return (
    <div className="empty">
      <Icon name={icon} size={26} />
      {title && <div className="strong" style={{ color: 'var(--ink)' }}>{title}</div>}
      {children && <div className="small">{children}</div>}
    </div>
  );
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  const warming = error.status === 503;
  return (
    <div className="card card-pad row" style={{ borderColor: warming ? 'var(--line)' : '#e7b4ad', background: warming ? '#fff' : '#fdf3f1' }}>
      <Icon name={warming ? 'refresh' : 'alert'} className={warming ? 'spin' : ''} />
      <div className="grow">
        <div className="strong">{warming ? 'WeatherPulse is warming up' : 'Something went wrong'}</div>
        <div className="small muted">{error.message}</div>
      </div>
      {onRetry && !warming && <button className="btn sm" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Segmented({ options, value, onChange, label }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} className={o.value === value ? 'on' : ''} aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={t.value === value} className={t.value === value ? 'on' : ''} onClick={() => onChange(t.value)}>
          {t.label}{t.count != null && <span className="n">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

let toastSetter = null;
export function toast(msg) { toastSetter?.(msg); }
export function Toaster() {
  const [msg, setMsg] = useState(null);
  useEffect(() => { toastSetter = setMsg; return () => { toastSetter = null; }; }, []);
  useEffect(() => { if (!msg) return undefined; const t = setTimeout(() => setMsg(null), 3200); return () => clearTimeout(t); }, [msg]);
  if (!msg) return null;
  return <div className="toast" role="status"><Icon name="check" size={16} />{msg}</div>;
}

export function Drawer({ open, onClose, title, children, footer }) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="row between" style={{ padding: '16px 20px', borderBottom: '1px solid var(--line)' }}>
          <h2>{title}</h2>
          <button className="btn ghost iconbtn" aria-label="Close" onClick={onClose}><Icon name="x" /></button>
        </div>
        <div style={{ padding: 20, overflowY: 'auto', flex: 1 }}>{children}</div>
        {footer && <div style={{ padding: '14px 20px', borderTop: '1px solid var(--line)' }}>{footer}</div>}
      </aside>
    </div>
  );
}

export function Modal({ open, onClose, title, children, footer }) {
  if (!open) return null;
  return (
    <div className="backdrop modal-center" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="row between" style={{ padding: '16px 20px', borderBottom: '1px solid var(--line)' }}>
          <h2>{title}</h2>
          <button className="btn ghost iconbtn" aria-label="Close" onClick={onClose}><Icon name="x" /></button>
        </div>
        <div style={{ padding: 20 }}>{children}</div>
        {footer && <div className="row" style={{ padding: '14px 20px', borderTop: '1px solid var(--line)', justifyContent: 'flex-end' }}>{footer}</div>}
      </div>
    </div>
  );
}

export function Logo({ size = 34, dark = false }) {
  return (
    <div className="brand-mark" style={{ width: size, height: size, borderRadius: size * 0.26, background: dark ? '#14202b' : undefined }}>
      <Icon name="pulse" size={size * 0.58} stroke={2.2} style={{ color: '#f3f2ee' }} />
    </div>
  );
}
