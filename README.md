# easy-panel-auto-backups-free

Cron + Docker service that triggers Easypanel database backups via the public API — a workaround when scheduled backups are configured but do not auto-run (e.g. Free license).

Serviço cron + Docker que dispara backups de banco do Easypanel pela API pública — contorno quando os backups agendados estão configurados mas não rodam sozinhos (ex.: licença Free).

| | |
|---|---|
| **Repository** | [github.com/sergiofelipe/easy-panel-auto-backups-free](https://github.com/sergiofelipe/easy-panel-auto-backups-free) |
| **License** | [MIT](LICENSE) |
| **API docs** | [easypanel.io/docs/api](https://easypanel.io/docs/api) |

---

## English

### What it solves

On Easypanel Free (and similar cases where the panel scheduler does not run), you can still configure database backup destinations and schedules in the UI, but those jobs may never fire automatically. This project runs on a schedule inside its own container and calls the same API used by **Manual Run** (`runDatabaseBackup`), so backups actually execute.

### Features

- Discovers projects and database services via `listProjectsAndServices`
- Lists backup configs with `listDatabaseBackups` (Postgres, MySQL, MariaDB, Mongo)
- Triggers each matching backup with `runDatabaseBackup`
- Cron schedule inside Docker (`CRON_SCHEDULE`, timezone via `TZ`)
- Optional run once on container start (`RUN_ON_START`)
- Filters by project/service and by `enabled` flag
- Dry-run mode (list only, no POST)
- Logs to **stdout** for Docker / [Dozzle](https://dozzle.dev/)
- On failures, WhatsApp alert via Meta Cloud API template `system_alert` (`{{1}}` = failure details)

### Requirements

- Easypanel instance + API key (Settings → Server → Users → Generate API Key)
- Docker and Docker Compose (or deploy the image as an app on Easypanel)
- Optional: Meta WhatsApp Cloud API credentials and an approved `system_alert` template for failure alerts

### Quick start

1. Clone the repo and copy the env template:

```bash
git clone https://github.com/sergiofelipe/easy-panel-auto-backups-free.git
cd easy-panel-auto-backups-free
cp .env.example .env
```

2. Edit `.env` — at minimum set `EASYPANEL_URL` and `EASYPANEL_TOKEN`. See [Environment variables](#environment-variables) and `.env.example` (never commit real secrets).

3. Build and run:

```bash
docker compose up -d --build
```

4. Check logs (`docker compose logs -f` or Dozzle). With default `RUN_ON_START=true`, one run happens immediately; then cron waits for `CRON_SCHEDULE`.

**Deploy on Easypanel:** create an App from this repo (or a built image), set the same env vars as in `.env.example`, and keep the container running so cron stays active. No public HTTP port is required.

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `EASYPANEL_URL` | yes | — | Panel URL (with or without `/api`) |
| `EASYPANEL_TOKEN` | yes | — | Bearer API key |
| `CRON_SCHEDULE` | no | `0 2 * * *` | Cron expression (container local time) |
| `TZ` | no | `America/Sao_Paulo` | Timezone for cron and logs |
| `RUN_ON_START` | no | `true` | Run backups once when the container starts |
| `ONLY_ENABLED` | no | `true` | If `true`, only configs with `enabled=true` |
| `EASYPANEL_PROJECTS` | no | (all) | Comma-separated project names to include |
| `EASYPANEL_SERVICES` | no | (all) | Comma-separated service names to include |
| `DRY_RUN` | no | `false` | If `true`, only log what would run (no `runDatabaseBackup`) |
| `WHATSAPP_SYSTEM_PHONE_NUMBER_ID` | for alerts | — | Meta phone number ID |
| `WHATSAPP_SYSTEM_ACCESS_TOKEN` | for alerts | — | Meta access token |
| `WHATSAPP_NUMBER_TO` | for alerts | — | Recipient digits only (country + area + number), e.g. `5511999999999` |
| `WHATSAPP_TEMPLATE_NAME` | no | `system_alert` | Template name |
| `WHATSAPP_TEMPLATE_LANG` | no | `pt_BR` | Template language code |
| `WHATSAPP_API_VERSION` | no | `v21.0` | Graph API version |

Full comments and template notes: [`.env.example`](.env.example).

### WhatsApp template (`system_alert`)

Alerts are sent **only when there are failures**. If WhatsApp env vars are missing, the script logs a warning and skips the alert.

1. In Meta Business Suite → WhatsApp → Message templates, create:

   - **Name:** `system_alert`
   - **Category:** Utility
   - **Language:** Portuguese (BR) → `pt_BR` (or change `WHATSAPP_TEMPLATE_LANG`)
   - **Body** with exactly one variable `{{1}}`, for example:

     `Alerta do sistema: {{1}}`

2. Provide a sample value for `{{1}}` when Meta asks (e.g. a short failure summary).
3. After approval, set `WHATSAPP_SYSTEM_PHONE_NUMBER_ID`, `WHATSAPP_SYSTEM_ACCESS_TOKEN`, and `WHATSAPP_NUMBER_TO` in `.env`.

### Logs and Dozzle

All application and cron output goes to container **stdout/stderr**. With the default `docker-compose.yml` (`json-file` logging + `logging=dozzle` label), Dozzle (or `docker logs`) shows the same stream — look for banners like `BACKUP RUN START` / `BACKUP RUN END`.

### License

[MIT](LICENSE) — Copyright (c) 2026.

---

## Português (Brasil)

### O que resolve

No Easypanel Free (e em casos semelhantes em que o agendador do painel não executa), você ainda pode configurar destinos e horários de backup de banco na UI, mas esses jobs podem nunca disparar sozinhos. Este projeto roda em cron dentro do próprio container e chama a mesma API do **Execução Manual** (`runDatabaseBackup`), para que os backups de fato executem.

### Funcionalidades

- Descobre projetos e serviços de banco via `listProjectsAndServices`
- Lista configs de backup com `listDatabaseBackups` (Postgres, MySQL, MariaDB, Mongo)
- Dispara cada backup correspondente com `runDatabaseBackup`
- Agendamento cron no Docker (`CRON_SCHEDULE`, fuso via `TZ`)
- Execução opcional ao subir o container (`RUN_ON_START`)
- Filtros por projeto/serviço e pela flag `enabled`
- Modo dry-run (só lista, sem POST)
- Logs no **stdout** para Docker / [Dozzle](https://dozzle.dev/)
- Em falhas, alerta WhatsApp via Meta Cloud API com o template `system_alert` (`{{1}}` = detalhes da falha)

### Requisitos

- Instância Easypanel + chave de API (Settings → Server → Users → Generate API Key)
- Docker e Docker Compose (ou deploy da imagem como app no Easypanel)
- Opcional: credenciais Meta WhatsApp Cloud API e template `system_alert` aprovado para alertas de falha

### Início rápido

1. Clone o repositório e copie o modelo de env:

```bash
git clone https://github.com/sergiofelipe/easy-panel-auto-backups-free.git
cd easy-panel-auto-backups-free
cp .env.example .env
```

2. Edite o `.env` — no mínimo `EASYPANEL_URL` e `EASYPANEL_TOKEN`. Veja [Variáveis de ambiente](#variáveis-de-ambiente) e `.env.example` (nunca faça commit de segredos reais).

3. Build e execução:

```bash
docker compose up -d --build
```

4. Confira os logs (`docker compose logs -f` ou Dozzle). Com `RUN_ON_START=true` (padrão), uma execução ocorre na subida; depois o cron aguarda `CRON_SCHEDULE`.

**Deploy no Easypanel:** crie um App a partir deste repo (ou de uma imagem buildada), configure as mesmas variáveis do `.env.example` e mantenha o container rodando para o cron ficar ativo. Não é necessária porta HTTP pública.

### Variáveis de ambiente

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `EASYPANEL_URL` | sim | — | URL do painel (com ou sem `/api`) |
| `EASYPANEL_TOKEN` | sim | — | API key (Bearer) |
| `CRON_SCHEDULE` | não | `0 2 * * *` | Expressão cron (horário local do container) |
| `TZ` | não | `America/Sao_Paulo` | Fuso para cron e logs |
| `RUN_ON_START` | não | `true` | Executa backups uma vez ao iniciar o container |
| `ONLY_ENABLED` | não | `true` | Se `true`, só configs com `enabled=true` |
| `EASYPANEL_PROJECTS` | não | (todos) | Projetos a incluir, separados por vírgula |
| `EASYPANEL_SERVICES` | não | (todos) | Serviços a incluir, separados por vírgula |
| `DRY_RUN` | não | `false` | Se `true`, só registra o que rodaria (sem `runDatabaseBackup`) |
| `WHATSAPP_SYSTEM_PHONE_NUMBER_ID` | para alertas | — | Phone number ID da Meta |
| `WHATSAPP_SYSTEM_ACCESS_TOKEN` | para alertas | — | Access token da Meta |
| `WHATSAPP_NUMBER_TO` | para alertas | — | Destinatário só dígitos (DDI+DDD+número), ex.: `5511999999999` |
| `WHATSAPP_TEMPLATE_NAME` | não | `system_alert` | Nome do template |
| `WHATSAPP_TEMPLATE_LANG` | não | `pt_BR` | Código do idioma do template |
| `WHATSAPP_API_VERSION` | não | `v21.0` | Versão da Graph API |

Comentários e notas do template: [`.env.example`](.env.example).

### Template WhatsApp (`system_alert`)

Alertas são enviados **somente quando há falhas**. Se as variáveis WhatsApp estiverem ausentes, o script registra um aviso e pula o alerta.

1. No Meta Business Suite → WhatsApp → Modelos de mensagem, crie:

   - **Nome:** `system_alert`
   - **Categoria:** Utilidade (Utility)
   - **Idioma:** Portuguese (BR) → `pt_BR` (ou altere `WHATSAPP_TEMPLATE_LANG`)
   - **Corpo** com exatamente uma variável `{{1}}`, por exemplo:

     `Alerta do sistema: {{1}}`

2. Informe um exemplo para `{{1}}` quando a Meta pedir (ex.: resumo curto de falha).
3. Após a aprovação, configure `WHATSAPP_SYSTEM_PHONE_NUMBER_ID`, `WHATSAPP_SYSTEM_ACCESS_TOKEN` e `WHATSAPP_NUMBER_TO` no `.env`.

### Logs e Dozzle

Toda a saída da aplicação e do cron vai para **stdout/stderr** do container. Com o `docker-compose.yml` padrão (logging `json-file` + label `logging=dozzle`), o Dozzle (ou `docker logs`) mostra o mesmo fluxo — procure banners como `BACKUP RUN START` / `BACKUP RUN END`.

### Licença

[MIT](LICENSE) — Copyright (c) 2026.
