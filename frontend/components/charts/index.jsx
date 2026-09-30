'use client';
import { useEffect, useRef, useState } from 'react';
import { inr, RISK } from '@/lib/format';

// Chart ink (recessive axes, text never in series colour)
const INK = { text: '#333d47', muted: '#8a939c', grid: '#ecebe6', axis: '#c3c2b7' };
export const SERIES = { blue: '#2a78d6', gray: '#a4abb2' };

function useWidth(initial = 600) {
  const ref = useRef(null);
  const [w, setW] = useState(initial);
  useEffect(() => {
    if (!ref.current) return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(160, Math.floor(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function niceTicks(min, max, n = 4) {
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  const step0 = span / n;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || step0;
  const t0 = Math.floor(min / step) * step;
  const out = [];
  for (let t = t0; t < max + step - 1e-9; t += step) out.push(+t.toFixed(6));
  return out;
}

/** Single-series line with min-max band, optional reference line and highlighted window. */
export function LineBand({ x, mean, lo, hi, reference, refLabel = 'Normal', unit = '', height = 150, highlight, xFmt = (v) => v, color = SERIES.blue, label }) {
  const [ref, W] = useWidth();
  const [hover, setHover] = useState(null);
  const H = height;
  const m = { l: 40, r: 10, t: 10, b: 22 };
  const iw = W - m.l - m.r;
  const ih = H - m.t - m.b;
  const vals = [...mean, ...(lo || []), ...(hi || []), ...(reference != null ? [reference] : [])].filter((v) => v != null && !Number.isNaN(v));
  const ticks = niceTicks(Math.min(...vals), Math.max(...vals));
  const y0 = ticks[0];
  const y1 = ticks[ticks.length - 1];
  const sx = (i) => m.l + (i / (x.length - 1)) * iw;
  const sy = (v) => m.t + ih - ((v - y0) / (y1 - y0 || 1)) * ih;
  const path = (arr) => arr.map((v, i) => `${i ? 'L' : 'M'}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join('');
  const band = lo && hi ? `${path(hi)}L${[...lo.keys()].reverse().map((i) => `${sx(i).toFixed(1)},${sy(lo[i]).toFixed(1)}`).join('L')}Z` : null;
  const xt = x.map((v, i) => i).filter((i) => i % Math.ceil(x.length / 6) === 0);
  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.round(((e.clientX - r.left - m.l) / iw) * (x.length - 1));
    setHover(i >= 0 && i < x.length ? i : null);
  };
  return (
    <div className="chart" ref={ref} aria-label={label} role="img">
      <svg width={W} height={H} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.l} x2={W - m.r} y1={sy(t)} y2={sy(t)} stroke={INK.grid} />
            <text x={m.l - 6} y={sy(t) + 4} textAnchor="end" fontSize="10.5" fill={INK.muted} className="num">{t}</text>
          </g>
        ))}
        {highlight && (
          <rect x={sx(highlight[0])} width={Math.max(2, sx(highlight[1]) - sx(highlight[0]))} y={m.t} height={ih} fill="#9e1b1b" opacity="0.07" />
        )}
        {band && <path d={band} fill={color} opacity="0.14" />}
        {reference != null && (
          <g>
            <line x1={m.l} x2={W - m.r} y1={sy(reference)} y2={sy(reference)} stroke={INK.text} strokeDasharray="4 4" strokeWidth="1" opacity="0.6" />
            <text x={W - m.r} y={sy(reference) - 4} textAnchor="end" fontSize="10.5" fill={INK.muted}>{refLabel}</text>
          </g>
        )}
        <path d={path(mean)} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
        <line x1={m.l} x2={W - m.r} y1={m.t + ih} y2={m.t + ih} stroke={INK.axis} />
        {xt.map((i) => <text key={i} x={sx(i)} y={H - 6} textAnchor="middle" fontSize="10.5" fill={INK.muted}>{xFmt(x[i])}</text>)}
        {hover != null && (
          <g>
            <line x1={sx(hover)} x2={sx(hover)} y1={m.t} y2={m.t + ih} stroke={INK.text} opacity="0.35" />
            <circle cx={sx(hover)} cy={sy(mean[hover])} r="4.5" fill={color} stroke="#fff" strokeWidth="2" />
          </g>
        )}
        <rect x={m.l} y={m.t} width={iw} height={ih} fill="transparent" />
      </svg>
      {hover != null && (
        <div className="tip" style={{ left: sx(hover), top: sy(mean[hover]) }}>
          <div className="m">{xFmt(x[hover])}</div>
          <div><b>{mean[hover]}</b> {unit}{lo && hi ? <span className="m"> ({lo[hover]}–{hi[hover]})</span> : null}</div>
        </div>
      )}
    </div>
  );
}

/** Vertical bars, one series. */
export function Bars({ data, height = 170, color = SERIES.blue, fmt = (v) => v, label, xLabel = (d) => d.label }) {
  const [ref, W] = useWidth();
  const [hover, setHover] = useState(null);
  const m = { l: 34, r: 8, t: 14, b: 24 };
  const iw = W - m.l - m.r;
  const ih = height - m.t - m.b;
  const max = Math.max(1, ...data.map((d) => d.value));
  const ticks = niceTicks(0, max, 3);
  const top = ticks[ticks.length - 1];
  const bw = iw / data.length;
  const gap = Math.min(8, bw * 0.25);
  return (
    <div className="chart" ref={ref} role="img" aria-label={label}>
      <svg width={W} height={height}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.l} x2={W - m.r} y1={m.t + ih - (t / top) * ih} y2={m.t + ih - (t / top) * ih} stroke={INK.grid} />
            <text x={m.l - 6} y={m.t + ih - (t / top) * ih + 4} textAnchor="end" fontSize="10.5" fill={INK.muted}>{fmt(t)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const h = (d.value / top) * ih;
          const x = m.l + i * bw + gap / 2;
          const w = bw - gap;
          const r = Math.min(4, w / 2, h);
          return (
            <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={m.l + i * bw} y={m.t} width={bw} height={ih} fill="transparent" />
              {h > 0 && <path d={`M${x},${m.t + ih}V${m.t + ih - h + r}Q${x},${m.t + ih - h} ${x + r},${m.t + ih - h}H${x + w - r}Q${x + w},${m.t + ih - h} ${x + w},${m.t + ih - h + r}V${m.t + ih}Z`} fill={d.color || color} opacity={hover == null || hover === i ? 1 : 0.55} />}
              <text x={x + w / 2} y={height - 7} textAnchor="middle" fontSize="10.5" fill={INK.muted}>{xLabel(d)}</text>
            </g>
          );
        })}
        <line x1={m.l} x2={W - m.r} y1={m.t + ih} y2={m.t + ih} stroke={INK.axis} />
      </svg>
      {hover != null && (
        <div className="tip" style={{ left: m.l + hover * bw + bw / 2, top: m.t + ih - (data[hover].value / top) * ih }}>
          <div className="m">{data[hover].tip || xLabel(data[hover])}</div><div><b>{fmt(data[hover].value)}</b></div>
        </div>
      )}
    </div>
  );
}

/** Horizontal stacked bars of people by risk ring (ordinal risk ramp + legend + total label). */
export function RingStack({ rows, height, label = 'People by risk ring' }) {
  const [ref, W] = useWidth();
  const [hover, setHover] = useState(null);
  const rowH = 30;
  const H = height || rows.length * rowH + 8;
  const labW = Math.min(170, W * 0.34);
  const totW = 76;
  const iw = W - labW - totW;
  const max = Math.max(1, ...rows.map((r) => r.high + r.moderate + r.low));
  return (
    <div>
      <div className="chart-legend" style={{ marginBottom: 8 }}>
        {['high', 'moderate', 'low'].map((k) => <span key={k}><i style={{ background: RISK[k].fill }} />{RISK[k].label} · {RISK[k].range}</span>)}
      </div>
      <div className="chart" ref={ref} role="img" aria-label={label}>
        <svg width={W} height={H}>
          {rows.map((r, i) => {
            let x = labW;
            const y = i * rowH + 6;
            const segs = ['high', 'moderate', 'low'].map((k) => {
              const w = (r[k] / max) * iw;
              const seg = { k, x, w: Math.max(0, w - (w > 3 ? 2 : 0)), v: r[k] };
              x += w;
              return seg;
            });
            return (
              <g key={r.label} onMouseLeave={() => setHover(null)}>
                <text x={0} y={y + 14} fontSize="12" fill={INK.text}>{r.label.length > 24 ? `${r.label.slice(0, 23)}…` : r.label}</text>
                {segs.map((s) => s.w > 0 && (
                  <rect key={s.k} x={s.x} y={y} width={s.w} height={18} rx={3} fill={RISK[s.k].fill}
                    onMouseEnter={() => setHover({ i, s })} opacity={hover && hover.i !== i ? 0.6 : 1} />
                ))}
                <text x={W} y={y + 14} textAnchor="end" fontSize="12" fill={INK.text} className="num">{inr(r.high + r.moderate + r.low)}</text>
              </g>
            );
          })}
        </svg>
        {hover && (
          <div className="tip" style={{ left: hover.s.x + hover.s.w / 2, top: hover.i * rowH + 6 }}>
            <div className="m">{rows[hover.i].label} · {RISK[hover.s.k].label}</div><div><b>{inr(hover.s.v)}</b> people</div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Grouped horizontal bars: model vs baseline for a few metrics (0-1). */
export function MetricBars({ rows, series }) {
  return (
    <div className="col gap-8">
      <div className="chart-legend">{series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}</div>
      {rows.map((r) => (
        <div key={r.label} className="col gap-4">
          <div className="row between small"><span>{r.label}</span></div>
          {series.map((s) => r[s.key] != null && (
            <div key={s.key} className="row gap-8">
              <div style={{ flex: 1, height: 12, background: 'var(--sunken)', borderRadius: 4 }}>
                <div style={{ width: `${Math.max(1, r[s.key] * 100)}%`, height: '100%', background: s.color, borderRadius: 4 }} />
              </div>
              <span className="num small" style={{ width: 44, textAlign: 'right' }}>{(r[s.key] * 100).toFixed(1)}%</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
