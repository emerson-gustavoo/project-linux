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



#comando para rodar atualmente 
>> venv\Scripts\activate
>> python -m playwright install chromium
>> uvicorn app.main:app --reload

## Rodando em VM com Docker (produção)

A imagem já traz **tudo** embutido: Python, FastAPI, Playwright/Chromium, yt-dlp e ffmpeg.
Não é preciso instalar nada disso na VM — só o Docker.

### 1. Pré-requisitos na VM (uma vez)
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER   # relogue depois deste comando
```

### 2. Levar o código para a VM
```bash
git clone https://github.com/emerson-gustavoo/project-linux.git
cd project-linux
```
> Ou copie a pasta via `scp -r ./4linux-downloader usuario@IP_DA_VM:~/`.

### 3. Subir
```bash
docker compose up -d --build     # build + sobe em background
docker compose logs -f           # acompanhar (Ctrl+C sai do log, o app segue rodando)
```

Acesse em **http://IP_DA_VM:8000**

### Uso no formulário (dentro do container)
- **Pasta de destino:** use `/downloads` (mapeado para `./downloads` na VM via volume).
- **FFmpeg:** deixe **vazio** — já está no PATH da imagem.
- **cookies.txt:** faça upload normalmente pela página.

### Onde ficam os arquivos na VM
- `./downloads/` → vídeos baixados
- `./data/` → `run.log`, `cookies.txt`, `urls_unique.txt`, `vimeo_report.csv`, `baixados.txt`

### Comandos úteis
```bash
docker compose ps                # status / healthcheck
docker compose restart           # reiniciar
docker compose down              # parar e remover o container
docker compose up -d --build     # aplicar mudanças de código
```

### Firewall
Se o acesso externo não abrir, libere a porta 8000:
```bash
sudo ufw allow 8000/tcp
```
Em nuvem (AWS/GCP/Azure), libere a porta 8000 também no **Security Group / regra de firewall** do provedor.
