'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useGov } from '@/components/gov/Shell';
import MapView, { LEGEND } from '@/components/map/MapView';
import { Card } from '@/components/ui';
import Icon from '@/components/ui/Icon';
import { api } from '@/lib/api';
import { useApi } from '@/lib/useApi';

const SUGGEST = [
  'How many citizens are in the high and moderate rings in Bengaluru, and which hospitals should prepare first?',
  'Which buses are heading into the Bengaluru zone?',
  'List all active events',
  'Tell me about the cyclone',
  'What is the population of Khordha district?',
  'Draft an SMS for citizens in the Bengaluru high-risk ring',
];

const TOOLS = [
  ['Anomaly events, tracks & zones', 'WeatherPulse DB'],
  ['Population by ward / district', 'Census of India 2011'],
  ['Schools, hospitals, rescue units', 'Demo registry (OSM-ready)'],
  ['Vehicle positions', 'Simulated feed'],
  ['Geocoding & routing', 'OpenStreetMap · OSRM'],
  ['Alert drafts (approval queue only)', 'WeatherPulse'],
];

function ToolCall({ c }) {
  const [open, setOpen] = useState(false);
  const args = Object.entries(c.args || {}).map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`).join(', ');
  return (
    <div>
      <button className="chip" style={{ border: 0, cursor: 'pointer' }} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Icon name={open ? 'chevronD' : 'chevronR'} size={12} />{c.name}({args})
      </button>
      {open && <pre className="tiny" style={{ background: '#f4f6f8', border: '1px solid var(--line)', borderRadius: 8, padding: 10, marginTop: 6, maxHeight: 220, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{JSON.stringify(c.result, null, 2)}</pre>}
    </div>
  );
}

export default function CopilotPage() {
  const { events } = useGov();
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [mapState, setMapState] = useState({ events: [], assets: [], wards: [], points: [] });
  const endRef = useRef(null);
  const zones = useApi('/maps/risk-zones');
  const assets = useApi('/maps/assets');
  const wards = useApi('/maps/wards');
  const health = useApi('/health');
  useEffect(() => { const el = endRef.current?.parentElement; if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }); }, [msgs, busy]);

  const ask = async (text) => {
    const question = (text ?? q).trim();
    if (!question || busy) return;
    setQ('');
    const history = msgs.map((m) => ({ role: m.role, content: m.text }));
    setMsgs((m) => [...m, { role: 'user', text: question }]);
    setBusy(true);
    try {
      const r = await api('/copilot/ask', { method: 'POST', body: { question, history } });
      setMsgs((m) => [...m, { role: 'assistant', text: r.answer, calls: r.tool_calls, mode: r.mode, note: r.note }]);
      setMapState(r.map);
    } catch (e) {
      setMsgs((m) => [...m, { role: 'assistant', text: `Sorry, I could not answer: ${e.message}`, calls: [] }]);
    } finally { setBusy(false); }
  };

  const focusEvent = events.data?.find((e) => e.id === mapState.events[0]);
  const zFc = useMemo(() => zones.data && mapState.events.length ? { ...zones.data, features: zones.data.features.filter((f) => mapState.events.includes(f.properties.event_id)) } : zones.data, [zones.data, mapState]);
  const aFc = useMemo(() => assets.data && { ...assets.data, features: assets.data.features.filter((f) => mapState.assets.includes(f.properties.id)) }, [assets.data, mapState]);
  const focus = mapState.points[0] ? { lon: mapState.points[0][0], lat: mapState.points[0][1], zoom: 10 }
    : focusEvent && mapState.events.length === 1 ? { lon: focusEvent.peak.lon, lat: focusEvent.peak.lat, zoom: 10.3 } : undefined;

  return (
    <div className="row-top" style={{ gap: 0, minHeight: 'calc(100vh - 66px)' }}>
      <section aria-label="Conversation" className="col" style={{ flex: '1 1 640px', padding: '22px 28px', gap: 16, borderRight: '1px solid var(--line)', height: 'calc(100vh - 66px)', position: 'sticky', top: 66 }}>
        <div className="row between wrap">
          <div>
            <h1 className="row gap-8"><Icon name="chat" size={24} />AI Copilot</h1>
            <div className="small muted" style={{ marginTop: 3 }}>Answers only from WeatherPulse data and map tools. Every number shows where it came from.</div>
          </div>
          <div className="row gap-6">
            <span className={`badge ${health.data?.gemini ? 'info' : 'neutral'}`}>{health.data?.gemini ? 'Gemini · function calling' : 'Offline mode · rule-based tools'}</span>
            <span className="badge warn mono tiny">DEMO DATA</span>
          </div>
        </div>

        <div className="col gap-16 grow" style={{ overflowY: 'auto', minHeight: 0, paddingRight: 4 }}>
          {!msgs.length && (
            <div className="card card-pad col gap-12" style={{ background: 'var(--surface-2)' }}>
              <div className="strong">Ask about events, people, institutions, vehicles or places. For example:</div>
              <div className="row wrap gap-8">{SUGGEST.map((s) => <button key={s} className="pill-btn" onClick={() => ask(s)}>{s}</button>)}</div>
            </div>
          )}
          {msgs.map((m, i) => m.role === 'user' ? <div key={i} className="bubble-user">{m.text}</div> : (
            <div key={i} className="col gap-8" style={{ maxWidth: '92%' }}>
              {m.calls?.length > 0 && <div className="col gap-4">{m.calls.map((c, j) => <ToolCall key={j} c={c} />)}</div>}
              <div className="bubble-ai">{m.text}</div>
              {m.mode && <div className="tiny muted">{m.mode === 'gemini' ? 'Gemini, grounded on tool results' : (m.note || 'Composed from tool results (add GEMINI_API_KEY for natural-language answers)')} · logged for audit</div>}
            </div>
          ))}
          {busy && <div className="row gap-8 small muted"><Icon name="refresh" size={15} className="spin" />Looking up data and the map…</div>}
          <div ref={endRef} />
        </div>

        <div className="col gap-8">
          {msgs.length > 0 && <div className="row wrap gap-6">{SUGGEST.slice(0, 3).map((s) => <button key={s} className="pill-btn" onClick={() => ask(s)}>{s.length > 52 ? `${s.slice(0, 50)}…` : s}</button>)}</div>}
          <form className="row gap-8" onSubmit={(e) => { e.preventDefault(); ask(); }}>
            <label htmlFor="ask" className="sr-only">Ask the Copilot</label>
            <input id="ask" className="input grow" style={{ height: 50 }} placeholder="Ask about events, population, institutions, vehicles or routes…" value={q} onChange={(e) => setQ(e.target.value)} />
            <button className="btn dark lg" disabled={busy || !q.trim()}><Icon name="send" size={16} />Ask</button>
          </form>
        </div>
      </section>

      <aside className="col gap-16" style={{ flex: '0 0 460px', padding: '22px 24px', position: 'sticky', top: 66 }}>
        <h3>Map result</h3>
        <MapView zones={zFc} assets={aFc} wards={wards.data} highlightWards={mapState.wards} height={380} fit="data" fitKey={JSON.stringify(mapState)} focus={focus}
          markers={mapState.points.map((p) => ({ lon: p[0], lat: p[1] }))} show={{ tracks: false, vehicles: false }}
          title={focusEvent ? `${focusEvent.place.split(',')[0]} · Copilot result` : 'Copilot result'} live={false} legend={[LEGEND.hospital, LEGEND.school, LEGEND.ward]} compact>
        </MapView>
        <Card title="What the Copilot can access" footer="It cannot send alerts: drafts go to the approval queue. Every tool call is written to the audit log.">
          <div className="small muted" style={{ marginBottom: 6 }}>Read-only tools, called automatically:</div>
          {TOOLS.map(([a, b]) => <div key={a} className="ringrow"><span>{a}</span><span className="muted small">{b}</span></div>)}
        </Card>
      </aside>
    </div>
  );
}
