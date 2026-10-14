import queue
import threading

# ── Server-Sent Events (SSE) Live Streaming Hub ──────────────────────────────
_sse_clients = {}  # session_id -> list of queue.Queue
_sse_lock = threading.Lock()

def register_sse_client(session_id, q):
    with _sse_lock:
        if session_id not in _sse_clients:
            _sse_clients[session_id] = []
        _sse_clients[session_id].append(q)

def unregister_sse_client(session_id, q):
    with _sse_lock:
        if session_id in _sse_clients:
            if q in _sse_clients[session_id]:
                _sse_clients[session_id].remove(q)
            if not _sse_clients[session_id]:
                del _sse_clients[session_id]

def broadcast_sse(event_type, data, session_id=None):
    with _sse_lock:
        targets = []
        if session_id and session_id in _sse_clients:
            targets = list(_sse_clients[session_id])
        elif not session_id:
            for s_id, q_list in _sse_clients.items():
                targets.extend(q_list)
        for q in targets:
            try:
                q.put_nowait((event_type, data))
            except queue.Full:
                pass
