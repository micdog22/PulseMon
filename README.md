# PulseMon - Uptime por Heartbeat + Status Page

PulseMon é um monitor de disponibilidade auto-hospedado baseado em **heartbeats**. Cada serviço sob monitoração precisa “bater ponto” periodicamente em uma URL. Se o batimento não chegar dentro do intervalo configurado (com margem de tolerância), o estado muda para **DOWN**, um evento é registrado e um **webhook** opcional é disparado. O projeto inclui um **painel administrativo** simples e uma **status page pública**.

---

## Sumário
- [Principais recursos](#principais-recursos)
- [Arquitetura em alto nível](#arquitetura-em-alto-nível)
- [Instalação rápida](#instalação-rápida)
- [Configuração via ambiente](#configuração-via-ambiente)
- [Uso básico](#uso-básico)
  - [Criando monitores no painel](#criando-monitores-no-painel)
  - [Enviando heartbeats](#enviando-heartbeats)
  - [Status page pública](#status-page-pública)
- [Execução com Docker](#execução-com-docker)
- [API de referência](#api-de-referência)
  - [Autenticação administrativa](#autenticação-administrativa)
  - [Monitores](#monitores)
  - [Heartbeats](#heartbeats)
  - [Histórico](#histórico)
- [Integrações por webhook](#integrações-por-webhook)
- [Segurança](#segurança)
- [Solução de problemas](#solução-de-problemas)
- [Roadmap](#roadmap)
- [Licença](#licença)

---

## Principais recursos

- Monitores de heartbeat com `interval_seconds`, `grace_seconds`, `token` secreto e `webhook_url` opcional.
- Verificador em **background** que atualiza estados automaticamente (UP/DOWN) e grava histórico.
- **Status page pública** pronta para uso (`/status`), sem autenticação.
- Painel **admin** enxuto para criar, listar e remover monitores.
- **API REST** minimalista, útil para automações.
- Persistência em **SQLite** (padrão) via SQLAlchemy; deployment simples com Docker.

---

## Arquitetura em alto nível

- **FastAPI** expõe:
  - Rotas administrativas (guardadas por token de sessão)
  - Rota pública de heartbeat (`/h/{slug}/{token}`)
  - Status page (`/status`)
  - API REST
- **Worker** em background (loop assíncrono) avalia periodicamente todos os monitores:
  - Calcula `delta = now - last_ping`
  - Se `delta <= interval + grace`: estado **UP**; caso contrário: **DOWN**
  - Em transições, grava evento em `history` e dispara webhook (se houver)

Tabelas principais:
- `monitors(id, slug, name, token, interval_seconds, grace_seconds, last_ping, status, webhook_url, created_at, updated_at)`
- `history(id, slug, prev_status, new_status, note, created_at)`

---

## Instalação rápida

Requisitos: Python 3.11+

```bash
git clone <seu-fork-ou-repo>
cd PulseMon
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edite .env e defina ADMIN_TOKEN
uvicorn app.main:app --reload --host 0.0.0.0 --port 8088
```

Acesse:
- Painel admin: `http://localhost:8088/`
- Status page: `http://localhost:8088/status`
- Documentação interativa: `http://localhost:8088/docs`

---

## Configuração via ambiente

Variáveis suportadas (exemplo em `.env.example`):

- `ADMIN_TOKEN` — token exigido para login no painel e cabeçalho de admin na API.
- `WORKER_INTERVAL_SEC` — frequência (em segundos) do verificador em background. Padrão: `60`.
- `PUBLIC_STATUS_TITLE` — título exibido na status page. Ex.: `Status — Minha Empresa`.
- `DATABASE_URL` — URL do banco. Padrão: `sqlite:///./pulsemon.db`.
- `APP_HOST`, `APP_PORT` — host/porta para execução (usado no Dockerfile/compose).
- `ADMIN_SESSION_SECRET` — segredo para assinar cookie de sessão do painel.

---

## Uso básico

### Criando monitores no painel
1. Abra `http://localhost:8088/` e faça login com o `ADMIN_TOKEN`.
2. Preencha:
   - **name**: nome amigável do serviço (ex.: `Backup Noturno`)
   - **slug**: identificador sem espaços (ex.: `backup-noite`)
   - **interval_seconds**: período esperado entre batimentos (ex.: `900` para 15 min)
   - **grace_seconds**: tolerância (ex.: `120`)
   - **webhook_url**: opcional (ex.: um webhook do Discord/Slack/HTTP)
3. O painel exibirá a URL de ping, no formato `/h/{slug}/{token}`.

### Enviando heartbeats

Use a URL de ping ao final do seu job (ou a cada ciclo):
```bash
curl -fsS "http://localhost:8088/h/backup-noite/SEU_TOKEN" || true
```

Outras formas:
- **Cron**:
  ```cron
  */15 * * * * curl -fsS "http://seu-host/h/backup-noite/SEU_TOKEN" || true
  ```
- **systemd** (no ExecStartPost de um serviço):
  ```ini
  ExecStartPost=/usr/bin/curl -fsS http://seu-host/h/backup-noite/SEU_TOKEN
  ```
- **GitHub Actions** (job de rotina):
  ```yaml
  - name: Heartbeat
    run: curl -fsS "$HEARTBEAT_URL" || true
  ```

### Status page pública
Disponível em `GET /status`. Mostra nome, slug, último ping, intervalo e estado atual de cada monitor.

---

## Execução com Docker

Build manual:
```bash
docker build -t pulsemon:latest .
docker run --env-file .env -p 8088:8088 pulsemon:latest
```

Compose:
```bash
docker compose up --build
```

---

## API de referência

### Autenticação administrativa

- A maioria dos endpoints de administração exige o cabeçalho:
  ```
  X-Admin-Token: <ADMIN_TOKEN>
  ```
- No painel, o login grava um cookie de sessão assinado (apenas para o uso do painel).

### Monitores

**Criar monitor**  
`POST /api/monitors`  
Headers: `X-Admin-Token`  
Body JSON:
```json
{
  "name": "Backup Noturno",
  "slug": "backup-noite",
  "interval_seconds": 900,
  "grace_seconds": 120,
  "webhook_url": "https://seu-webhook.tld/endpoint"
}
```
Resposta:
```json
{
  "name": "Backup Noturno",
  "slug": "backup-noite",
  "interval_seconds": 900,
  "grace_seconds": 120,
  "status": "UNKNOWN",
  "last_ping": null,
  "webhook_url": "https://seu-webhook.tld/endpoint"
}
```

**Listar monitores**  
`GET /api/monitors`  
Headers: `X-Admin-Token`

**Detalhar monitor**  
`GET /api/monitors/{slug}`  
Headers: `X-Admin-Token`

**Excluir monitor**  
`DELETE /api/monitors/{slug}`  
Headers: `X-Admin-Token`

### Heartbeats

**Ping do serviço monitorado**  
`GET /h/{slug}/{token}`  
Sem autenticação adicional. Retorna `{"ok": true}` em caso de sucesso.

### Histórico

**Eventos de status**  
`GET /api/history/{slug}`  
Headers: `X-Admin-Token`  
Retorna eventos com `prev_status`, `new_status`, `note` e `created_at`.

---

## Integrações por webhook

Quando um monitor muda de estado (UP → DOWN ou DOWN → UP), se `webhook_url` estiver configurado, o PulseMon envia:
```json
{
  "slug": "backup-noite",
  "name": "Backup Noturno",
  "status": "DOWN",
  "occurred_at": "2025-09-18T17:00:00Z",
  "interval_seconds": 900,
  "grace_seconds": 120,
  "last_ping": "2025-09-18T16:42:10Z"
}
```

Exemplo simples para Discord (Webhook Inbound):
```bash
curl -X POST "$DISCORD_WEBHOOK_URL"   -H "Content-Type: application/json"   -d '{"content":"[PulseMon] backup-noite mudou para DOWN"}'
```

---

## Segurança

- Guarde o **token** do monitor como segredo. Quem possui o token consegue “bater ponto”.
- Proteja o painel com `ADMIN_TOKEN` forte e, em produção, considere colocá-lo atrás de um proxy com autenticação adicional e HTTPS.
- Configure **rate limits** e firewall no seu proxy reverso, se exposto à internet.

---

## Solução de problemas

- **Worker não muda estados**: verifique `WORKER_INTERVAL_SEC` e se a aplicação está no modo normal (não apenas servindo estático).
- **Status sempre UNKNOWN**: seu serviço ainda não fez o primeiro ping.
- **Token incorreto**: a rota `/h/{slug}/{token}` retorna 404 se o token não confere.
- **Webhooks não chegam**: teste manual com `curl` e verifique logs do servidor de destino.

---

## Roadmap

- Checagens HTTP ativas (pingar URL e validar 2xx/tempo de resposta).
- Agrupamento por ambiente (prod/dev), tags e ordenação customizável na status page.
- Cálculo e gráfico de SLA (7/30 dias).
- Autenticação multiusuário e RBAC.
- Exportação/Importação de monitores em JSON.
- Templates prontos de webhook (Discord/Slack/Telegram).

---

## Licença

MIT. Consulte o arquivo `LICENSE`.
