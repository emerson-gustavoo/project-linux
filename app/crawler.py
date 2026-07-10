# app/crawler.py
import os
import re
import time
import random
import sys
import asyncio
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError
from .utils import read_netscape_cookies

# --- Fix p/ Windows: evita NotImplementedError no asyncio/subprocess ---
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

COURSE_HOST = "aia.4linux.com.br"

def _abs_url(base, href):
    if not href:
        return None
    if href.startswith(("http://", "https://")):
        return href
    return urljoin(base, href)

def _pull_module_links(html, base_url):
    """Coleta links de /mod/videotime/view.php?id=XXXX na página."""
    out = set()
    for m in re.finditer(r"/mod/videotime/view\.php\?id=\d+", html):
        out.add(_abs_url(base_url, m.group(0)))
    return out

def _extract_vimeo_ids_from_html(html):
    """Extrai possíveis video_id do Vimeo de vários jeitos."""
    ids = set()
    # padrões usuais
    for m in re.finditer(r'player\.vimeo\.com\/video\/(\d+)', html):
        ids.add(m.group(1))
    for m in re.finditer(r'"video_id"\s*:\s*(\d+)', html):
        ids.add(m.group(1))
    # padrões extras que já vi em temas Moodle/players
    for m in re.finditer(r'data-vimeo-id=["\'](\d+)["\']', html):
        ids.add(m.group(1))
    for m in re.finditer(r'data-setup=["\'].*?"video_id"\s*:\s*(\d+).*?["\']', html):
        ids.add(m.group(1))
    return ids

def _course_id_from_url(url):
    m = re.search(r"/course/view\.php\?id=(\d+)", url) or re.search(r"/mod/videotime/index\.php\?id=(\d+)", url)
    return m.group(1) if m else None

def collect_vimeo_ids(
    course_url: str,
    cookies_path: str,
    max_sections: int = 300,          # cobre cursos grandes
    load_timeout_ms: int = 30000,     # mais tempo p/ páginas lentas
    pause_between=(400, 900),         # pausas curtas com jitter
    empty_stop_after: int = 8,        # early-stop: para após N seções seguidas sem novos links
    logger=print
):
    """Retorna (ids_ordenados, total_modulos, rows[ordem,url,title,video_id])."""
    def pause():
        time.sleep(random.uniform(pause_between[0]/1000.0, pause_between[1]/1000.0))

    cookies = read_netscape_cookies(cookies_path, domain_filter=COURSE_HOST)

    # DEBUG: set DEBUG_HEADFUL=1 para ver o Chromium abrindo
    headless = os.getenv("DEBUG_HEADFUL") not in ("1", "true", "True")

    # Em container (root), o Chromium precisa de --no-sandbox. Ativado via env
    # CHROMIUM_NO_SANDBOX=1 (definido no docker-compose); no Windows fica desligado.
    launch_args = []
    if os.getenv("CHROMIUM_NO_SANDBOX", "").lower() in ("1", "true", "yes"):
        launch_args += ["--no-sandbox", "--disable-dev-shm-usage"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=launch_args)
        ctx = browser.new_context()
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def load(url: str):
            page.goto(url, wait_until="load", timeout=load_timeout_ms)
            # tenta esperar rede ociosa e ativa lazy-load rolando
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            for _ in range(4):
                try:
                    page.mouse.wheel(0, 600)
                except Exception:
                    pass
                page.wait_for_timeout(150)
            page.wait_for_timeout(300)
            return page.content()

        # 1) Coletar todos os links de módulos Videotime
        logger("[1/3] Coletando links de módulos…")
        module_links = set()

        html = load(course_url); pause()
        module_links |= _pull_module_links(html, course_url)

        cid = _course_id_from_url(course_url)
        if cid:
            idx_url = f"https://{COURSE_HOST}/mod/videotime/index.php?id={cid}"
            try:
                html = load(idx_url); pause()
                module_links |= _pull_module_links(html, idx_url)
            except Exception as e:
                logger(f"  Aviso: índice do Videotime indisponível: {e}")

            logger("  Varredura por seções…")
            empty_streak = 0
            for s in range(0, max_sections + 1):
                sec_url = f"https://{COURSE_HOST}/course/view.php?id={cid}&section={s}"
                try:
                    html = load(sec_url)
                    before = len(module_links)
                    module_links |= _pull_module_links(html, sec_url)
                    gained = len(module_links) - before
                    if gained > 0:
                        logger(f"   seção {s:03d}: +{gained} links")
                        empty_streak = 0
                    else:
                        empty_streak += 1
                        if empty_streak >= empty_stop_after:
                            logger(f"   seção {s:03d}: 0 links (parando após {empty_streak} vazias seguidas)")
                            break
                except Exception:
                    empty_streak += 1
                    if empty_streak >= empty_stop_after:
                        logger(f"   seção {s:03d}: erro/0 links (parando após {empty_streak} vazias seguidas)")
                        break
                pause()

        logger(f"  Total de módulos localizados: {len(module_links)}")
        if not module_links:
            raise RuntimeError("Nenhum módulo Videotime encontrado. Confirme URL/cookies.")

        # 2) Visitar cada módulo e extrair video_id
        logger("[2/3] Extraindo IDs…")
        ids = set()
        rows = []

        for i, url in enumerate(sorted(module_links), 1):
            video_id, title = "", ""
            try:
                page.goto(url, wait_until="load", timeout=load_timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                # rolar e tentar clicar no "play" para players preguiçosos
                for _ in range(6):
                    try:
                        page.mouse.wheel(0, 700)
                    except Exception:
                        pass
                    page.wait_for_timeout(160)

                html = page.content()
                got = _extract_vimeo_ids_from_html(html)

                if not got:
                    selectors = [
                        'button[aria-label*="Play"]', '.vjs-big-play-button', '.plyr__control',
                        '.videotime .play', '.startbtn', '.start-button', '.big-play-button',
                        '.overlay', '.click-to-play', '.video-container', '.plyr',
                        'button[title*="Play"]', 'button[aria-label*="Reproduzir"]'
                    ]
                    for _ in range(16):
                        for sel in selectors:
                            try:
                                page.locator(sel).first.click(timeout=500)
                            except Exception:
                                pass
                        page.wait_for_timeout(500)
                        try:
                            page.mouse.wheel(0, 500)
                        except Exception:
                            pass
                        html = page.content()
                        got = _extract_vimeo_ids_from_html(html)
                        if got:
                            break

                if got:
                    video_id = sorted(got)[0]  # se vier mais de um, pega o menor (estável)
                    ids |= got

                title = (page.title() or "").strip()
                logger(f"   ({i}/{len(module_links)}) id={video_id or '-'}  total={len(ids)}")
            except TimeoutError:
                logger(f"   ({i}/{len(module_links)}) TIMEOUT")
            except Exception as e:
                logger(f"   ({i}/{len(module_links)}) ERRO: {e}")

            rows.append({"ordem": i, "url": url, "title": title, "video_id": video_id})
            pause()

        ctx.close()
        browser.close()

    return sorted(ids), len(module_links), rows
