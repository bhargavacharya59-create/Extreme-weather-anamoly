'use client';
import { useMemo, useState } from 'react';
import { AssetTable, PageHead } from '@/components/gov/widgets';
import MapView, { LEGEND, RiskLegend } from '@/components/map/MapView';
import { Card, DemoBanner, Kpi, Segmented, Skeleton } from '@/components/ui';
import { useApi } from '@/lib/useApi';

export default function InstitutionsPage() {
  const { data } = useApi('/institutions');
  const zones = useApi('/maps/risk-zones');
  const [kind, setKind] = useState('all');
  const [ring, setRing] = useState('all');
  const [sel, setSel] = useState(null);
  const list = useMemo(() => (data || []).filter((a) => (kind === 'all' || a.kind === kind) && (ring === 'all' || a.ring === ring)), [data, kind, ring]);
  const count = (k) => (data || []).filter((a) => a.kind === k).length;
  const acked = (data || []).filter((a) => a.acknowledged).length;
  const assetsFc = useMemo(() => ({ type: 'FeatureCollection', features: list.map((a) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [a.lon, a.lat] }, properties: a })) }), [list]);

  return (
    <div className="page">
      <PageHead title="Institutions" sub="Schools, colleges, hospitals and rescue units inside risk rings at each event's highest-impact time." />
      <DemoBanner>Institutions are fictional demo records placed around real cities; plug in OpenStreetMap or UDISE+ / NHM registries for real use.</DemoBanner>
      <div className="grid g4">
        {!data ? [0, 1, 2, 3].map((i) => <Skeleton key={i} h={96} />) : (
          <>
            <Kpi icon="school" label="Schools / colleges" value={count('school')} foot="inside risk rings" />
            <Kpi icon="hospital" label="Hospitals" value={count('hospital')} foot="inside risk rings" />
            <Kpi icon="shield" label="Rescue units" value={count('rescue_team')} foot="inside risk rings" />
            <Kpi icon="check" label="Acknowledged alerts" value={`${acked} / ${data.length}`} foot="institutions that confirmed" />
          </>
        )}
      </div>
      <div className="row wrap gap-8">
        <Segmented label="Type" value={kind} onChange={setKind} options={[{ value: 'all', label: 'All types' }, { value: 'school', label: 'Schools' }, { value: 'hospital', label: 'Hospitals' }, { value: 'rescue_team', label: 'Rescue units' }]} />
        <Segmented label="Ring" value={ring} onChange={setRing} options={[{ value: 'all', label: 'All rings' }, { value: 'high', label: 'High' }, { value: 'moderate', label: 'Moderate' }, { value: 'low', label: 'Lower' }]} />
      </div>
      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.9fr) minmax(0, 1fr)' }}>
        <Card bodyClass="scroll" style={{ maxHeight: 560 }}>
          {!data ? <Skeleton h={200} /> : <AssetTable assets={list} showEvent onRow={(a) => setSel(a)} selected={sel?.id} />}
        </Card>
        <MapView zones={zones.data} assets={assetsFc} height={560} fit="data" fitKey={`inst-${sel?.id}`}
          focus={sel ? { lon: sel.lon, lat: sel.lat, zoom: 12.5 } : list[0] ? { lon: list[0].lon, lat: list[0].lat, zoom: 10 } : undefined}
          markers={sel ? [{ lon: sel.lon, lat: sel.lat, label: sel.name, tone: 'shelter' }] : []} show={{ tracks: false }}>
          <div className="map-overlay" style={{ left: 12, bottom: 12 }}><RiskLegend extra={[LEGEND.school, LEGEND.hospital, LEGEND.rescue]} /></div>
        </MapView>
      </div>
    </div>
  );
}
