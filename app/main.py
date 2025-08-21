# app/main.py
import os, threading, time, csv
from fastapi import FastAPI, Request, UploadFile, Form
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import traceback


from .crawler import collect_vimeo_ids, COURSE_HOST
from .downloader import run_ytdlp
from .utils import write_lines

app = FastAPI()
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

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
async def start(request: Request,
                course_url: str = Form(...),
                out_dir: str = Form(...),
                ffmpeg_dir: str = Form(""),
                workers: int = Form(3),
                cookies: UploadFile = None):
    reset_log()
    # salva cookies
    if cookies is not None:
        content = await cookies.read()
        with open(COOKIES_PATH, "wb") as f:
            f.write(content)
        log(f"Cookies salvos em {COOKIES_PATH} ({len(content)} bytes)")
    else:
        log("Nenhum arquivo de cookies recebido.")
        return templates.TemplateResponse("index.html", {"request": request, "error": "Envie o cookies.txt (Netscape)."})

    def worker():
        try:
            log("Iniciando coleta de IDs…")
            ids, mods, rows = collect_vimeo_ids(
                course_url=course_url,
                cookies_path=COOKIES_PATH,
                logger=log
            )
            if not ids:
                log("Nenhum video_id encontrado. Verifique URL/cookies.")
                return

            # salva URLs
            urls = [f"https://player.vimeo.com/video/{vid}" for vid in ids]
            write_lines(URLS_PATH, urls)
            log(f"Salvo {len(urls)} URLs em {URLS_PATH}")

            # salva relatório CSV
            with open(REPORT_PATH, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ordem", "title", "video_id", "url"])
                for r in rows:
                    w.writerow([r.get("ordem"), r.get("title", ""), r.get("video_id", ""), r.get("url")])
            log(f"Relatório salvo em {REPORT_PATH} (módulos={mods} | ids={len(ids)})")

            # iniciar downloads
            os.makedirs(out_dir, exist_ok=True)
            log("Iniciando downloads com yt-dlp…")
            rc = run_ytdlp(
                batch_file=URLS_PATH,
                out_dir=out_dir,
                cookies_path=COOKIES_PATH,
                referer=f"https://{COURSE_HOST}/",
                ffmpeg_dir=ffmpeg_dir or None,
                archive_path=ARCHIVE_PATH,
                workers=int(workers),
                logger=log
            )
            log(f"yt-dlp finalizado com código {rc}")
        except Exception as e:
            log(f"ERRO: {repr(e)}\n{traceback.format_exc()}")


    threading.Thread(target=worker, daemon=True).start()
    return templates.TemplateResponse("index.html", {"request": request, "message": "Processo iniciado. Veja os logs abaixo."})
