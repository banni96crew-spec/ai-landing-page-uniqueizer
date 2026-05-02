"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { fetchClientApi } from "../lib/client-api";
import { getResolvedWsBaseUrl } from "./env";
import type { JobDetailResponse, JobLogResponse, JobStatus } from "./types";

type LogItem = {
  message: string;
  timestamp: string;
  level: "info" | "warn" | "error" | string;
};

type WsEvent =
  | { type: "log"; message: string; timestamp: string; level: string }
  | { type: "done"; status: JobStatus };

type WsStatus = "connecting" | "connected" | "closed";

function levelClass(level: string): string {
  if (level === "warn") return "text-warn";
  if (level === "error") return "text-error";
  return "text-accent";
}

export function LogViewer({ jobId }: { jobId: number }) {
  const wsUrl = useMemo(() => getResolvedWsBaseUrl(), []);

  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [terminalStatus, setTerminalStatus] = useState<JobStatus | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const retryRef = useRef<number>(0);
  const terminalStatusRef = useRef<JobStatus | null>(null);
  const logsCountRef = useRef<number>(0);
  const logKeysRef = useRef<Set<string>>(new Set());
  const retryTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [logs.length]);

  function ingestLog(item: { message: string; timestamp: string; level: string }): void {
    const key = `${item.timestamp}|${item.level}|${item.message}`;
    if (logKeysRef.current.has(key)) return;
    logKeysRef.current.add(key);
    setLogs((prev) => [
      ...prev,
      { message: item.message, timestamp: item.timestamp, level: item.level },
    ]);
  }

  useEffect(() => {
    let alive = true;

    async function loadHistory() {
      try {
        const res = await fetchClientApi(`/api/jobs/${jobId}/logs?limit=500&offset=0`, {
          method: "GET",
          cache: "no-store",
        });
        if (!res.ok) return;
        const history = (await res.json()) as JobLogResponse[];
        if (!alive) return;
        for (const row of history) {
          ingestLog({
            message: row.message,
            timestamp: row.timestamp,
            level: row.level,
          });
        }
      } catch {
        // ignore history fetch errors
      }
    }

    loadHistory();
    return () => {
      alive = false;
    };
  }, [jobId]);

  useEffect(() => {
    terminalStatusRef.current = terminalStatus;
  }, [terminalStatus]);

  useEffect(() => {
    logsCountRef.current = logs.length;
  }, [logs.length]);

  useEffect(() => {
    setWsStatus("connecting");
    setLogs([]);
    setTerminalStatus(null);
    retryRef.current = 0;
    terminalStatusRef.current = null;
    logsCountRef.current = 0;
    logKeysRef.current = new Set();
    if (retryTimeoutRef.current !== null) {
      window.clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }

    let ws: WebSocket | null = null;
    let alive = true;

    function connect() {
      if (!alive) return;
      if (terminalStatusRef.current) return;

      setWsStatus("connecting");
      ws = new WebSocket(`${wsUrl}/ws/logs/${jobId}`);

      ws.onopen = () => {
        retryRef.current = 0;
        setWsStatus("connected");
      };

      ws.onerror = () => {
        setWsStatus("closed");
        try {
          ws?.close();
        } catch {
          // ignore
        }
      };

      ws.onclose = (_ev: CloseEvent) => {
        setWsStatus("closed");
        if (!alive) return;
        if (terminalStatusRef.current) return;

        // If the job finishes extremely fast, the WS may close before we got
        // the DB history burst. Retry a couple times to reduce missed logs.
        if (retryRef.current < 2 && logsCountRef.current <= 1) {
          retryRef.current += 1;
          retryTimeoutRef.current = window.setTimeout(() => {
            retryTimeoutRef.current = null;
            connect();
          }, 250);
        }
      };

      ws.onmessage = (event: MessageEvent<string>) => {
        let parsed: WsEvent;
        try {
          parsed = JSON.parse(event.data) as WsEvent;
        } catch {
          return;
        }

        if (parsed.type === "done") {
          setTerminalStatus(parsed.status);
          try {
            ws?.close();
          } catch {
            // ignore
          }
          return;
        }

        if (parsed.type === "log") {
          ingestLog({
            message: parsed.message,
            timestamp: parsed.timestamp,
            level: parsed.level,
          });
        }
      };
    }

    connect();

    return () => {
      alive = false;
      if (retryTimeoutRef.current !== null) {
        window.clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
      try {
        ws?.close();
      } catch {
        // ignore
      }
    };
  }, [jobId, wsUrl]);

  useEffect(() => {
    if (terminalStatus) return;
    if (wsStatus === "connected") return;

    let alive = true;
    const interval = window.setInterval(async () => {
      try {
        const res = await fetchClientApi(`/api/jobs/${jobId}`, { method: "GET" });
        if (!res.ok) return;
        const job = (await res.json()) as JobDetailResponse;
        if (!alive) return;
        if (job.status === "done" || job.status === "failed") {
          setTerminalStatus(job.status);
        }
      } catch {
        // ignore polling errors
      }
    }, 3000);

    return () => {
      alive = false;
      window.clearInterval(interval);
    };
  }, [jobId, terminalStatus, wsStatus]);

  return (
    <section className="rounded-card border border-border bg-bg-secondary p-5">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-text-primary">Logs</div>
        <div className="text-xs text-text-secondary">
          {terminalStatus ? `Status: ${terminalStatus}` : `WS: ${wsStatus}`}
        </div>
      </div>

      <div
        ref={containerRef}
        className="mt-4 h-64 overflow-y-auto rounded-card border border-border bg-bg-primary p-4 font-mono text-xs"
      >
        {wsStatus === "connecting" && logs.length === 0 ? (
          <div className="text-text-secondary">Connecting...</div>
        ) : logs.length === 0 ? (
          <div className="text-text-secondary">No logs yet.</div>
        ) : (
          <div className="flex flex-col gap-1">
            {logs.map((l, idx) => (
              // eslint-disable-next-line react/no-array-index-key
              <div key={idx} className="text-text-secondary hover:text-text-primary">
                <span className={levelClass(l.level)}>{l.timestamp}</span>{" "}
                <span>{l.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

