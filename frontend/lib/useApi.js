'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';

// Small data hook with in-memory cache, refetch, polling and warm-up retry.
const cache = new Map();

export function useApi(path, { poll = 0, keep = true } = {}) {
  const [data, setData] = useState(() => (path && cache.has(path) ? cache.get(path) : null));
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(!!path && !cache.has(path));
  const alive = useRef(true);
  const retry = useRef(null);

  const load = useCallback(async (silent = false) => {
    if (!path) return;
    if (!silent) setLoading(true);
    try {
      const d = await api(path);
      cache.set(path, d);
      if (alive.current) { setData(d); setError(null); }
    } catch (e) {
      if (!alive.current) return;
      setError(e);
      if (e.status === 503) {           // backend warming up: retry shortly
        clearTimeout(retry.current);
        retry.current = setTimeout(() => load(true), 3000);
      }
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    alive.current = true;
    if (!keep || !cache.has(path)) setData(path && cache.has(path) ? cache.get(path) : null);
    load(path && cache.has(path));
    let t;
    if (poll) t = setInterval(() => load(true), poll);
    return () => { alive.current = false; clearInterval(t); clearTimeout(retry.current); };
  }, [path, poll, load, keep]);

  return { data, error, loading, reload: () => load(true), setData };
}

export function invalidate(prefix = '') {
  for (const k of [...cache.keys()]) if (k.startsWith(prefix)) cache.delete(k);
}
