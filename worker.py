# worker.py
import argparse
import io
import os
import pickle
import signal
import sys
import threading
import time
import traceback
from pathlib import Path

# ----------------------------
# Status & tiny utilities
# ----------------------------
def write_status(job_dir: Path, state: str, message: str = ""):
    """Best-effort status files for the polling UI."""
    try:
        (job_dir / "status.txt").write_text(state)
    except Exception:
        pass
    try:
        (job_dir / "status_message.txt").write_text(message or "")
    except Exception:
        pass
    try:
        (job_dir / "status.json").write_text(
            '{"state":"%s","message":"%s","ts":%s,"pid":%s}\n'
            % (
                state.replace('"','\\"'),
                (message or "").replace('"','\\"'),
                time.time(),
                os.getpid(),
            )
        )
    except Exception:
        pass

def _noop_streamlit():
    """Make any accidental Streamlit calls harmless in the worker context."""
    try:
        import streamlit as st  # noqa
        st.warning = lambda *a, **k: None
        st.error   = lambda *a, **k: None
        st.info    = lambda *a, **k: None
        st.success = lambda *a, **k: None
        st.spinner = lambda *a, **k: (_ for _ in ()).throw(StopIteration)
    except Exception:
        pass

def _mask_email(email: str | None) -> str:
    if not email:
        return "unknown_email"
    if len(email) <= 5:
        return email[0] + "*" * (len(email) - 1)
    return email[:5] + "*" * (len(email) - 5)

def _ts_gmt():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

def log_safely(app_main, job_dir: Path, msg: str, retries: int = 3, delay: float = 2.0):
    """Use main.log(msg) with retries; fall back to a local file on failure."""
    for attempt in range(1, retries + 1):
        try:
            app_main.log(msg)
            return
        except Exception as e:
            if attempt == retries:
                try:
                    (job_dir / "log_fallback.txt").write_text(f"{msg}\n(log error: {e})\n")
                except Exception:
                    pass
            else:
                time.sleep(delay)

# ----------------------------
# Heartbeat (lets UI detect stalls)
# ----------------------------
class Heartbeat:
    def __init__(self, job_dir: Path, interval_sec: int = 60):
        self.job_dir = job_dir
        self.interval = interval_sec
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self._stop.is_set():
            try:
                (self.job_dir / "heartbeat.txt").write_text(str(int(time.time())))
            except Exception:
                pass
            self._stop.wait(self.interval)

    def start(self):
        self._t.start()

    def stop(self):
        self._stop.set()
        self._t.join(timeout=2)

# ----------------------------
# Core worker
# ----------------------------
def long_process(job_dir: str) -> int:
    """
    Background runner:
      - loads analyzer.pkl staged by the UI,
      - patches display_output -> write bytes to result.xlsx,
      - runs main.main(...),
      - writes detailed success/error logs in the SAME format your UI used.
    """
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    write_status(job_dir, "running", "Starting…")
    _noop_streamlit()

    # graceful termination => mark as error with message
    def _graceful(signum, frame):
        write_status(job_dir, "error", f"Terminated by signal {signum}")
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _graceful)
        except Exception:
            pass

    hb = Heartbeat(job_dir, interval_sec=60)
    hb.start()

    try:
        import main as app_main

        # Patch: when main.display_output(bytes) is called, save to file instead of UI
        def _save_bytes_to_job(b: bytes):
            try:
                (job_dir / "result.xlsx").write_bytes(b)
            except Exception:
                pass
        app_main.display_output = _save_bytes_to_job

        # Load analyzer
        analyzer_pkl = job_dir / "analyzer.pkl"
        if not analyzer_pkl.exists():
            raise FileNotFoundError(f"Missing analyzer.pkl in {job_dir}")
        with open(analyzer_pkl, "rb") as f:
            gpt_analyzer = pickle.load(f)

        # Normalize PDFs list (avoids Streamlit warning path)
        if not isinstance(getattr(gpt_analyzer, "pdfs", []), (list, tuple)):
            gpt_analyzer.pdfs = [gpt_analyzer.pdfs]

        # Build log header to match your original format
        user_email = getattr(gpt_analyzer, "email", None)
        masked = _mask_email(user_email)
        header = f"{masked}: {_ts_gmt()} GMT \n {gpt_analyzer}"

        # Run pipeline
        openai_key = os.environ.get("OPENAI_API_KEY")
        write_status(job_dir, "running", "Processing…")
        num_pages, output_doc, err = app_main.main(gpt_analyzer, openai_key)

        if err:
            # Detailed error log: header + traceback + context
            tb = "".join(traceback.format_exception_only(type(err), err))
            ctx = [
                f"JOB_ID={job_dir.name}",
                f"PDF_COUNT={len(getattr(gpt_analyzer, 'pdfs', []) or [])}",
                "PDFS:",
                *[f"  - {p}" for p in (getattr(gpt_analyzer, 'pdfs', []) or [])],
            ]
            error_msg = f"{header}\nERROR: {err}\n{tb}\n" + "\n".join(ctx)
            (job_dir / "error.txt").write_text(f"{err}\n{traceback.format_exc()}")
            write_status(job_dir, "error", str(err))
            log_safely(app_main, job_dir, error_msg)
            return 1

        # Persist workbook (even if display_output already wrote bytes)
        try:
            buf = io.BytesIO()
            output_doc.save(buf)
            buf.seek(0)
            (job_dir / "result.xlsx").write_bytes(buf.read())
        except Exception as e:
            tb = traceback.format_exc()
            ctx = [
                f"JOB_ID={job_dir.name}",
                f"PDF_COUNT={len(getattr(gpt_analyzer, 'pdfs', []) or [])}",
                "PDFS:",
                *[f"  - {p}" for p in (getattr(gpt_analyzer, 'pdfs', []) or [])],
            ]
            error_msg = f"{header}\nERROR saving result.xlsx: {e}\n{tb}\n" + "\n".join(ctx)
            (job_dir / "error.txt").write_text(f"{e}\n{tb}")
            write_status(job_dir, "error", "Failed to save result.xlsx")
            log_safely(app_main, job_dir, error_msg)
            return 1

        # SUCCESS log: original header + context lines
        ctx = [
            f"JOB_ID={job_dir.name}",
            f"PAGES={num_pages}",
            f"PDF_COUNT={len(getattr(gpt_analyzer, 'pdfs', []) or [])}",
            "PDFS:",
            *[f"  - {p}" for p in (getattr(gpt_analyzer, 'pdfs', []) or [])],
        ]
        success_msg = f"{header}\n" + "\n".join(ctx)
        write_status(job_dir, "done", f"Finished. Pages: {num_pages}")
        log_safely(app_main, job_dir, success_msg)
        return 0

    except BaseException as e:
        # Catch everything (incl. KeyboardInterrupt/SystemExit in child)
        tb = traceback.format_exc()
        try:
            (job_dir / "error.txt").write_text(f"{e}\n{tb}")
        except Exception:
            pass

        # Try to log with the same rich header if analyzer is available
        try:
            import main as app_main  # may still work even if earlier import failed
            header = f"unknown_email: {_ts_gmt()} GMT \n (no analyzer loaded)"
            # If analyzer.pkl exists, load just to format a better header
            analyzer_pkl = job_dir / "analyzer.pkl"
            if analyzer_pkl.exists():
                try:
                    with open(analyzer_pkl, "rb") as f:
                        an = pickle.load(f)
                    header = f"{_mask_email(getattr(an, 'email', None))}: {_ts_gmt()} GMT \n {an}"
                except Exception:
                    pass
            ctx = [f"JOB_ID={job_dir.name}"]
            error_msg = f"{header}\nERROR (outer): {e}\n{tb}\n" + "\n".join(ctx)
            log_safely(app_main, job_dir, error_msg)
        except Exception:
            pass

        write_status(job_dir, "error", str(e))
        return 1
    finally:
        hb.stop()

# ----------------------------
# CLI entry
# ----------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True, help="Absolute path to the job directory")
    args = ap.parse_args()
    sys.exit(long_process(args.job))
