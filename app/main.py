# app/main.py
from __future__ import annotations
import os, threading, time, csv, json, traceback, asyncio
from tempfile import NamedTemporaryFile
from fastapi import FastAPI, Request, UploadFile, Form, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .crawler import collect_vimeo_ids, COURSE_HOST
from .downloader import (
    router as downloader_router,
    run_ytdlp_async,
    cookies_to_netscape_lines,
    CookieItem,
)

app = FastAPI(title="4linux-downloader")

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# rotas do downloader sob /api (ex.: /api/convert-cookies JSON e /api/download)
app.include_router(downloader_router, prefix="/api")

LOG_PATH     = os.path.join(DATA_DIR, "run.log")
URLS_PATH    = os.path.join(DATA_DIR, "urls_unique.txt")
COOKIES_PATH = os.path.join(DATA_DIR, "cookies.txt")
ARCHIVE_PATH = os.path.join(DATA_DIR, "baixados.txt")
REPORT_PATH  = os.path.join(DATA_DIR, "vimeo_report.csv")

def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)

def reset_log():
    open(LOG_PATH, "w", encoding="utf-8").close()

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/logs", response_class=PlainTextResponse)
def get_logs():
    if not os.path.exists(LOG_PATH):
        return ""
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/download/urls")
def download_urls():
    if not os.path.exists(URLS_PATH):
        return PlainTextResponse("Nenhum arquivo gerado ainda.", status_code=404)
    return FileResponse(URLS_PATH, media_type="text/plain", filename="urls_unique.txt")

@app.get("/download/report")
def download_report():
    if not os.path.exists(REPORT_PATH):
        return PlainTextResponse("Relatório não gerado ainda.", status_code=404)
    return FileResponse(REPORT_PATH, media_type="text/csv", filename="vimeo_report.csv")

@app.post("/start", response_class=HTMLResponse)
async def start(
    request: Request,
    course_url: str = Form(...),
    out_dir: str = Form(...),
    ffmpeg_dir: str = Form(""),
    workers: int = Form(3),
    limit_rate: str = Form(""),
    sleep_interval: int = Form(0),
    fragments: int = Form(4),
    cookies: UploadFile = File(None),
):
    reset_log()

    # salva cookies (Netscape)
    if cookies is not None:
        content = await cookies.read()
        with open(COOKIES_PATH, "wb") as f:
            f.write(content)
        log(f"Cookies salvos em {COOKIES_PATH} ({len(content)} bytes)")
    else:
        log("Nenhum arquivo de cookies recebido.")
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": "Envie o cookies.txt (Netscape)."}
        )

    def worker():
        try:
            log("Iniciando coleta de IDs…")
            ids, mods, rows = collect_vimeo_ids(
                course_url=course_url,
                cookies_path=COOKIES_PATH,
                logger=log,
            )
            if not ids:
                log("Nenhum video_id encontrado. Verifique URL/cookies.")
                return

            # salva URLs
            urls = [f"https://player.vimeo.com/video/{vid}" for vid in ids]
            with open(URLS_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(urls) + "\n")
            log(f"Salvo {len(urls)} URLs em {URLS_PATH}")

            # salva relatório CSV
            with open(REPORT_PATH, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ordem", "title", "video_id", "url"])
                for r in rows:
                    w.writerow([r.get("ordem"), r.get("title", ""), r.get("video_id", ""), r.get("url")])
            log(f"Relatório salvo em {REPORT_PATH} (módulos={mods} | ids={len(ids)})")

            # iniciar downloads com runner assíncrono
            os.makedirs(out_dir, exist_ok=True)

            # normaliza os freios vindos do form
            rate = (limit_rate or "").strip() or None
            sleep_s = int(sleep_interval or 0)
            frags = int(fragments or 4)

            freios = []
            if rate:
                freios.append(f"limit-rate={rate}")
            if sleep_s > 0:
                freios.append(f"sleep={sleep_s}s")
            freios.append(f"fragmentos={frags}")
            log(f"Iniciando downloads com yt-dlp… (workers={workers} | {' | '.join(freios)})")

            # lê cookies.txt para passar inline
            with open(COOKIES_PATH, "r", encoding="utf-8") as f:
                cookies_txt = f.read()

            extra_args = [
                "--download-archive", ARCHIVE_PATH,
                "--referer", f"https://{COURSE_HOST}/",
                "--no-call-home",
                "--restrict-filenames",
            ]
            if ffmpeg_dir:
                extra_args += ["--ffmpeg-location", ffmpeg_dir]

            result = asyncio.run(run_ytdlp_async(
                urls=urls,
                concurrency=int(workers),
                output_dir=out_dir,
                cookies_txt=cookies_txt,
                extra_args=extra_args,
                limit_rate=rate,
                sleep_interval=sleep_s,
                concurrent_fragments=frags,
            ))

            log(
                f"yt-dlp finalizado. Sucesso={result.get('ok')} | "
                f"baixados/total={sum(1 for j in result['jobs'] if j.get('returncode') == 0)}/{len(result['jobs'])} | "
                f"duracao={result.get('duration')}s"
            )
        except Exception as e:
            log(f"ERRO: {repr(e)}\n{traceback.format_exc()}")

    threading.Thread(target=worker, daemon=True).start()
    return templates.TemplateResponse("index.html", {"request": request, "message": "Processo iniciado. Veja os logs abaixo."})

# upload de arquivo JSON e retorno de cookies.txt como attachment (para baixar no navegador)
@app.post("/convert-cookies")
async def convert_cookies(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        data = json.loads(raw)  # espera lista de objetos cookie (Chrome/ETC)
        if not isinstance(data, list):
            raise ValueError("JSON deve ser uma lista de objetos de cookie.")

        cookies = [CookieItem(**c) for c in data]
        lines = cookies_to_netscape_lines(cookies)
        header = "# Netscape HTTP Cookie File\n# Generated by 4linux-downloader\n"
        content = header + "\n".join(lines) + "\n"

        # cria arquivo temporário para devolver como attachment
        with NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        return FileResponse(
            tmp_path,
            media_type="text/plain",
            filename="cookies.txt"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Falha ao converter cookies: {e}")
