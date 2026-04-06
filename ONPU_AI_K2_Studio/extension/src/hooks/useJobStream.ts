/**
 * SSE hook for real-time job progress.
 * Prompt 004 — use EventSource for /api/jobs/:id/stream.
 */
import { useEffect, useRef, useState } from 'react';

export interface JobStreamEvent {
  status: string;
  progress: string;
  timestamp: string;
  result_url?: string;
}

export function useJobStream(
  jobId: string | null,
  baseUrl: string = ''
): { data: JobStreamEvent | null; error: Error | null; done: boolean } {
  const [data, setData] = useState<JobStreamEvent | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [done, setDone] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId || !baseUrl) {
      return undefined;
    }
    const url = `${baseUrl.replace(/\/$/, '')}/api/jobs/${jobId}/stream`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as JobStreamEvent;
        setData(payload);
        if (
          payload.status === 'complete' ||
          payload.status === 'failed' ||
          payload.status === 'cancelled' ||
          payload.status === 'unknown'
        ) {
          setDone(true);
          es.close();
        }
      } catch (e) {
        setError(e instanceof Error ? e : new Error(String(e)));
      }
    };

    es.onerror = () => {
      setError(new Error('EventSource error'));
      es.close();
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [jobId, baseUrl]);

  return { data, error, done };
}

export default useJobStream;
