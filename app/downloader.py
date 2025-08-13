# app/downloader.py
import os, subprocess, shutil, time

def find_ytdlp_binary():
    path = shutil.which("yt-dlp")
    if path:
        return path
    home = os.path.expanduser("~")
    cand = os.path.join(home, "Downloads", "yt-dlp.exe")
    return cand if os.path.exists(cand) else None

def _build_cmd(ytdlp, batch_file, out_dir, cookies_path, referer, ffmpeg_dir, archive_path, workers):
    """
    Comando do yt-dlp reforçado para downloads longos e instáveis:
      - resume parcial, muitas tentativas, backoff, tolerância a fragmentos ruins
      - força saída mp4 (garante merge com ffmpeg) e prioriza downloader nativo de HLS
    """
    cmd = [
        ytdlp,
        "--no-check-certificate",
        "--cookies", cookies_path,
        "--referer", referer,
        "-P", out_dir,
        "--batch-file", batch_file,
        "-N", str(workers),
        "-f", "bv*+ba/b",
        "-o", "%(title)s [%(id)s].%(ext)s",

        # Resiliência
        "--ignore-errors",                       # não para o lote por erro em 1 vídeo
        "--continue",                            # retoma parciais (yt-dlp já tende a retomar, mas deixamos explícito)
        "--retries", "infinite",                 # tenta sem limite em erros de rede
        "--fragment-retries", "100",             # insiste forte em cada fragmento HLS
        "--retry-sleep", "10,30,60,120,300,600", # backoff progressivo
        "--no-abort-on-unavailable-fragments",   # não aborta por 1 fragmento ruim
        "--socket-timeout", "30",                # timeout de rede razoável
        "--merge-output-format", "mp4",          # garante saída mp4 (merge de trilhas)
        "--hls-prefer-native",                   # costuma ser mais estável para HLS (Vimeo)
        "--fixup", "warn",                       # corrige pequenos problemas de container/TS sem falhar
    ]
    if archive_path:
        cmd += ["--download-archive", archive_path]
    if ffmpeg_dir:
        cmd += ["--ffmpeg-location", ffmpeg_dir]
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

def run_ytdlp(batch_file, out_dir, cookies_path, referer, ffmpeg_dir=None,
              archive_path=None, workers=3, logger=print):
    """
    Executa yt-dlp com autotune de concorrência:
      - Observa o stdout do yt-dlp
      - Se detectar muitos 403/404 seguidos, reduz -N (até 1) e reinicia
    """
    ytdlp = find_ytdlp_binary()
    if not ytdlp:
        raise RuntimeError("yt-dlp não encontrado. Instale (ou coloque o yt-dlp.exe em Downloads).")

    # Parâmetros de autotune
    min_workers = 1
    max_restarts = 3
    err_threshold_consecutive = 5  # 5 erros seguidos 403/404 disparam redução
    keywords = (
        "HTTP Error 403", "HTTP Error 404",
        "403: Forbidden", "404 Not Found",
        "ERROR: 403", "ERROR: 404",
    )

    current_workers = max(min_workers, int(workers))
    restarts = 0

    while True:
        cmd = _build_cmd(ytdlp, batch_file, out_dir, cookies_path, referer, ffmpeg_dir, archive_path, current_workers)
        logger(" ".join(f'"{c}"' if " " in c else c for c in cmd))

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        errors_consec = 0
        autotune_triggered = False

        for line in proc.stdout:
            line = line.rstrip("\n")
            logger(line)

            # Conta erros 403/404
            if any(k in line for k in keywords):
                errors_consec += 1
            else:
                # Qualquer linha "normal" reseta a sequência
                if line.strip():
                    errors_consec = 0

            # Disparo do autotune
            if errors_consec >= err_threshold_consecutive:
                autotune_triggered = True
                break

        # Se saímos do loop de leitura, pegue o código (pode estar ainda rodando)
        try:
            rc = proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            rc = None

        if autotune_triggered and current_workers > min_workers and restarts < max_restarts:
            logger(f"⚠️ Muitos erros 403/404 detectados em sequência. "
                   f"Reduzindo concorrência: {current_workers} → {current_workers - 1} e reiniciando…")
            _terminate(proc)
            current_workers -= 1
            restarts += 1
            # pequeno respiro antes de relançar
            time.sleep(2)
            continue

        # Sem autotune (ou já no mínimo / estourou restarts) — encerra
        return rc if rc is not None else 1
