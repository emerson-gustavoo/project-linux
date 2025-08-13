# 4Linux Downloader (Web)

App web (FastAPI) para coletar IDs do Vimeo de um curso 4Linux/Moodle e baixar com yt-dlp.

## Rodando (Windows)

```powershell
py -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -m playwright install chromium

# iniciar servidor
venv\Scripts\uvicorn app.main:app --reload
```

Abra: http://127.0.0.1:8000

Preencha:
- URL do curso/índice
- cookies.txt (Netscape)
- pasta de saída (vídeos)
- (opcional) pasta do ffmpeg.exe (se não estiver no PATH)
- downloads simultâneos

Acompanhe os logs na página. Quando gerar, baixe a lista em **Baixar lista**.

## Dependências de sistema
- FFmpeg: `winget install --id Gyan.FFmpeg -e` e confirme `where ffmpeg`.
- yt-dlp: coloque `yt-dlp.exe` no PATH **ou** em `C:\Users\SEU_USUARIO\Downloads\yt-dlp.exe`.

## Observações
- Se der 401/403, gere um cookies Netscape novo e reinicie o processo.
- O app cria/usa `data/urls_unique.txt`, `data/run.log`, `data/baixados.txt`.
