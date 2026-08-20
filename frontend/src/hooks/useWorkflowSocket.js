import { useEffect, useRef, useState } from "react";
import { ALL_NODE_IDS, RESETTABLE_NODE_IDS, WHATSAPP_TRIGGER_NODE_IDS } from "../data/liveWorkflow";

// Same VITE_API_URL the REST layer resolves against (lib/api.js) — unset in
// dev, where requests proxy through Vite to localhost:8000. There's no dev
// proxy for WebSockets configured, so in dev we point straight at the
// backend's default port instead of going through Vite.
export function deriveWorkflowSocketUrl() {
  const apiBase = import.meta.env.VITE_API_URL || "";
  if (!apiBase) return "ws://localhost:8000/ws/pipeline";
  const wsBase = apiBase.replace(/^https:/i, "wss:").replace(/^http:/i, "ws:");
  return `${wsBase.replace(/\/+$/, "")}/ws/pipeline`;
}

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 10000];

function idleNodeStatus() {
  return Object.fromEntries(ALL_NODE_IDS.map((id) => [id, "idle"]));
}

// Connects to the backend's live pipeline event stream and replays events
// into a per-node status map. Auto-reconnects with capped backoff so a
// backend restart or flaky wifi never leaves the homepage diagram frozen —
// callers should treat `connected: false` as "showing a fallback," not an
// error to surface.
//
// One lane since the 2026-08-20 orchestrator merge (see data/liveWorkflow.js)
// — every event the backend emits now comes from WhatsApp Agent, so there's
// no more `source`-based branching between two independent lanes/summaries.
export function useWorkflowSocket() {
  const [connected, setConnected] = useState(false);
  const [nodeStatus, setNodeStatus] = useState(idleNodeStatus);
  const [currentLabel, setCurrentLabel] = useState(null);
  const [lastRunSummary, setLastRunSummary] = useState(null);
  const [lastEventAt, setLastEventAt] = useState(null);

  const socketRef = useRef(null);
  const attemptRef = useRef(0);
  const reconnectTimerRef = useRef(null);
  const closedByUsRef = useRef(false);

  useEffect(() => {
    closedByUsRef.current = false;

    function scheduleReconnect() {
      if (closedByUsRef.current) return;
      const delay = RECONNECT_DELAYS[Math.min(attemptRef.current, RECONNECT_DELAYS.length - 1)];
      attemptRef.current += 1;
      reconnectTimerRef.current = setTimeout(connect, delay);
    }

    function handleEvent(evt) {
      setCurrentLabel(evt.label ?? null);
      setLastEventAt(Date.now());

      if (evt.type === "step" && evt.node) {
        const status =
          evt.status === "start"
            ? "active"
            : evt.status === "success"
              ? "success"
              : evt.status === "error"
                ? "error"
                : evt.status === "skipped"
                  ? "idle"
                  : null;
        if (!status) return;

        // A trigger node starting is this lane's equivalent of a run
        // beginning — reset every other resettable node (other triggers,
        // the screening sub-steps, all tool groups) to idle first, then
        // apply this node's own status below, so a leftover "success" from
        // the previous run never lingers into the next one.
        if (evt.status === "start" && WHATSAPP_TRIGGER_NODE_IDS.includes(evt.node)) {
          setNodeStatus((prev) => {
            const next = { ...prev };
            for (const id of RESETTABLE_NODE_IDS) next[id] = "idle";
            next[evt.node] = "active";
            return next;
          });
          return;
        }

        setNodeStatus((prev) => (prev[evt.node] === status ? prev : { ...prev, [evt.node]: status }));
        return;
      }

      if (evt.type === "run_end") {
        setLastRunSummary(evt.label ?? null);
      }
    }

    function connect() {
      let socket;
      try {
        socket = new WebSocket(deriveWorkflowSocketUrl());
      } catch {
        scheduleReconnect();
        return;
      }
      socketRef.current = socket;

      socket.onopen = () => {
        attemptRef.current = 0;
        setConnected(true);
      };

      socket.onmessage = (msg) => {
        let evt;
        try {
          evt = JSON.parse(msg.data);
        } catch {
          return;
        }
        handleEvent(evt);
      };

      socket.onerror = () => {
        socket.close();
      };

      socket.onclose = () => {
        setConnected(false);
        if (socketRef.current === socket) socketRef.current = null;
        scheduleReconnect();
      };
    }

    connect();

    return () => {
      closedByUsRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, []);

  return { connected, nodeStatus, currentLabel, lastRunSummary, lastEventAt };
}
