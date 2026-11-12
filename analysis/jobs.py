"""Background analysis jobs with progress, consumed through Server-Sent Events.

Analysis runs in its own thread so it survives a page refresh: reconnecting
to the stream simply re-attaches to the running job. Jobs are serialised with
a lock, so only one game is analysed at a time; how many Stockfish processes
work on that game is the "effort" setting.
"""
import json
import threading
import time

import config

from analysis import store
from analysis.engine import AnalysisCancelled, analyse_line_parallel
from analysis.review import parse_pgn

_jobs = {}
_jobs_lock = threading.Lock()
_engine_lock = threading.Lock()


class Job:
    def __init__(self, game_id, depth):
        self.game_id = game_id
        self.depth = depth
        self.status = "queued"        # queued | running | done | error | cancelled
        self.cancel = threading.Event()
        self.done = 0                 # positions analysed so far
        self.total = 0
        self.san = None               # last move analysed
        self.error = None
        self.cond = threading.Condition()

    def _update(self, **fields):
        with self.cond:
            for key, value in fields.items():
                setattr(self, key, value)
            self.cond.notify_all()

    def snapshot(self):
        return {"status": self.status, "done": self.done, "total": self.total,
                "move": self.san, "error": self.error}

    def run(self):
        try:
            row = store.get_game(self.game_id)
            if row is None:
                raise ValueError("Game not found.")
            _, board, moves, _ = parse_pgn(row["pgn"])
            self._update(total=len(moves) + 1)
            with _engine_lock:
                self._update(status="running")
                workers = config.effort(store.get_settings()["effort"])["workers"]
                positions = analyse_line_parallel(
                    board, moves, self.depth, workers=workers,
                    max_seconds=config.max_seconds_for_depth(self.depth),
                    progress=lambda done, total, san: self._update(done=done, san=san),
                    cancel=self.cancel,
                )
            store.save_analysis(self.game_id, self.depth, positions)
            self._update(status="done")
        except AnalysisCancelled as exc:
            self._update(status="cancelled", error=str(exc))
        except Exception as exc:      # report any failure to the client
            self._update(status="error", error=str(exc) or exc.__class__.__name__)


def start(game_id, depth):
    """Start (or re-attach to) the analysis job for a game at a depth."""
    key = (game_id, depth)
    with _jobs_lock:
        job = _jobs.get(key)
        if job is None or job.status in ("done", "error", "cancelled"):
            job = Job(game_id, depth)
            _jobs[key] = job
            threading.Thread(target=job.run, daemon=True, name=f"analysis-{game_id}").start()
        return job


def _event(name, data):
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def stream(job):
    """Generator of SSE messages: ``progress`` events, then ``done`` or ``failed``."""
    last = None
    while True:
        with job.cond:
            if (job.done, job.status) == last:
                job.cond.wait(timeout=10)
            snap = job.snapshot()
        state = (snap["done"], snap["status"])
        if state != last:
            last = state
            yield _event("progress", snap)
        else:
            yield ": keep-alive\n\n"
        if snap["status"] == "done":
            yield _event("done", snap)
            return
        if snap["status"] in ("error", "cancelled"):
            yield _event("failed", snap)
            return


# --------------------------------------------------------------------------
# Batch: "analyse my last N games" (stats page)
# --------------------------------------------------------------------------
# The batch lives on the server, not in the page: it keeps going while you
# browse elsewhere, every page can show its progress, and only one can run.
class Batch:
    def __init__(self, batch_id, games, depth):
        self.id = batch_id
        self.games = games            # [{"id", "label"}], in the order they are analysed
        self.depth = depth
        self.status = "running"       # running | stopping | stopped | done | error
        self.index = 0                # game being analysed
        self.completed = []           # ids of the games this batch has finished
        self.reverted = 0
        self.revert = False           # on stop: delete what this batch had finished
        self.error = None
        self.job = None
        self.cancel = threading.Event()
        self.lock = threading.Lock()

    @property
    def active(self):
        return self.status in ("running", "stopping")

    def snapshot(self):
        with self.lock:
            job = self.job.snapshot() if self.job else {"done": 0, "total": 0}
            game = self.games[min(self.index, len(self.games) - 1)]
            return {"id": self.id, "active": self.active, "status": self.status,
                    "depth": self.depth, "total": len(self.games), "index": self.index,
                    "completed": len(self.completed), "reverted": self.reverted,
                    "label": game["label"], "done": job["done"], "positions": job["total"],
                    "error": self.error}

    def run(self):
        try:
            for index, game in enumerate(self.games):
                if self.cancel.is_set():
                    break
                with self.lock:
                    self.index = index
                    self.job = None
                if store.get_analysis(game["id"], self.depth) is not None:
                    continue                      # analysed meanwhile (e.g. from the review page)
                job = start(game["id"], self.depth)
                with self.lock:
                    self.job = job
                with job.cond:
                    while job.status not in ("done", "error", "cancelled"):
                        if self.cancel.is_set():
                            job.cancel.set()
                        job.cond.wait(timeout=0.25)
                if job.status == "done":
                    with self.lock:
                        self.completed.append(game["id"])
                elif job.status == "error":
                    raise RuntimeError(job.error)
            if self.cancel.is_set():
                if self.revert:
                    for game_id in self.completed:
                        store.delete_analysis(game_id, self.depth)
                    from analysis.review import cached_review
                    cached_review.cache_clear()
                    with self.lock:
                        self.reverted, self.completed = len(self.completed), []
                final = "stopped"
            else:
                final = "done"
            with self.lock:
                self.index = min(self.index, len(self.games) - 1)
                self.status = final
        except Exception as exc:
            with self.lock:
                self.status, self.error = "error", str(exc) or exc.__class__.__name__


_batch = None
_batch_lock = threading.Lock()
_batch_counter = 0


def batch_state():
    """Snapshot of the current (or last) batch; ``{"active": False}`` if none."""
    batch = _batch
    return batch.snapshot() if batch else {"id": None, "active": False, "status": "idle"}


def start_batch(game_ids, depth):
    """Start a batch. Returns ``(state, started)``; refuses while one is running."""
    global _batch, _batch_counter
    with _batch_lock:
        if _batch is not None and _batch.active:
            return _batch.snapshot(), False
        games = []
        for game_id in game_ids:
            row = store.get_game(game_id)
            if row is None or store.get_analysis(game_id, depth) is not None:
                continue
            meta = row["meta"]
            opponent = meta.get("black" if meta.get("hero") == "w" else "white") or {}
            games.append({"id": game_id, "label": opponent.get("name") or "?"})
        if not games:
            return batch_state(), False
        _batch_counter += 1
        _batch = Batch(f"{int(time.time())}-{_batch_counter}", games, depth)
        threading.Thread(target=_batch.run, daemon=True, name="analysis-batch").start()
        return _batch.snapshot(), True


def stop_batch(revert=False):
    """Stop the running batch; ``revert`` also deletes what it had finished."""
    batch = _batch
    if batch is not None and batch.active:
        with batch.lock:
            batch.revert = bool(revert)
            batch.status = "stopping"
        batch.cancel.set()
    return batch_state()
