# app/downloader.py
import os
import subprocess
import shutil
import time

# ---------- Localização do yt-dlp ----------
def find_ytdlp_binary():
    """
    Procura o executável standalone do yt-dlp no caminho fixo deste PC.
    """
    fixed_path = r"C:\Users\Emerson Gustavo\Downloads\yt-dlp.exe"
    if os.path.exists(fixed_path):
        return fixed_path

    # fallback (caso mude no futuro)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath(os.path.join(here, "..", "venv", "Scripts", "yt-dlp.exe")),
        os.path.join(os.path.expanduser("~"), "Downloads", "yt-dlp.exe"),
        shutil.which("yt-dlp.exe") or shutil.which("yt-dlp"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)

    raise RuntimeError(f"yt-dlp.exe não encontrado em {fixed_path} nem nos locais padrões.")

# ---------- Montagem do comando ----------
def _build_cmd(ytdlp, batch_file, out_dir, cookies_path, referer,
               ffmpeg_path, archive_path, workers):
    cmd = [
        ytdlp,
        "--no-check-certificate",
        "--cookies", cookies_path,
        "--referer", referer,
        "-P", out_dir,
        "--batch-file", batch_file,
        "-N", str(max(1, int(workers))),
        "-f", "bv*+ba/b",
        "-o", "%(title)s [%(id)s].%(ext)s",

        "--ignore-errors",
        "--continue",
        "--retries", "infinite",
        "--fragment-retries", "100",
        "--retry-sleep", "http:exp=10:600:2",
        "--retry-sleep", "fragment:exp=10:600:2",
        "--no-abort-on-unavailable-fragments",
        "--socket-timeout", "30",
        "--hls-prefer-native",
        "--fixup", "warn",
        "--merge-output-format", "mp4",
    ]

    if archive_path:
        cmd += ["--download-archive", archive_path]
    if ffmpeg_path and os.path.exists(ffmpeg_path):
        cmd += ["--ffmpeg-location", ffmpeg_path]

    return cmd

def _terminate(proc):
    try:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:
        pass

# ---------- Runner com autotune ----------
def run_ytdlp(batch_file, out_dir, cookies_path, referer,
              ffmpeg_dir=None, archive_path=None, workers=3, logger=print):
    ytdlp = find_ytdlp_binary()

    ffmpeg_path = None
    if ffmpeg_dir:
        if os.path.isdir(ffmpeg_dir):
            cand = os.path.join(ffmpeg_dir, "ffmpeg.exe")
            ffmpeg_path = cand if os.path.exists(cand) else ffmpeg_dir
        else:
            ffmpeg_path = ffmpeg_dir

    min_workers = 1
    max_restarts = 3
    err_threshold_consecutive = 5
    keywords = (
        "HTTP Error 403", "HTTP Error 404",
        "403: Forbidden", "404 Not Found",
        "ERROR: 403", "ERROR: 404",
    )

    current_workers = max(min_workers, int(workers))
    restarts = 0

    while True:
        cmd = _build_cmd(
            ytdlp=ytdlp,
            batch_file=batch_file,
            out_dir=out_dir,
            cookies_path=cookies_path,
            referer=referer,
            ffmpeg_path=ffmpeg_path,
            archive_path=archive_path,
            workers=current_workers,
        )

        logger(" ".join(f'"{c}"' if (" " in c and not c.startswith("--")) else c for c in cmd))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        errors_consec = 0
        autotune_triggered = False

        for line in proc.stdout:
            line = line.rstrip("\n")
            logger(line)
            if any(k in line for k in keywords):
                errors_consec += 1
            else:
                if line.strip():
                    errors_consec = 0
            if errors_consec >= err_threshold_consecutive:
                autotune_triggered = True
                break

        try:
            rc = proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            rc = None

        if autotune_triggered and current_workers > min_workers and restarts < max_restarts:
            logger(f"⚠️ Muitos erros 403/404 detectados. Reduzindo -N: {current_workers} → {current_workers - 1}")
            _terminate(proc)
            current_workers -= 1
            restarts += 1
            time.sleep(2)
            continue

        return rc if rc is not None else 1
