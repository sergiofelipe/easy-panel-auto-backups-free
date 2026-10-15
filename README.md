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

On Easypanel Free (and similar cases where the panel scheduler does not run), you can still configure database backup destinations and schedules in the UI, but those jobs may never fire automatically. This project polls inside its own container (default: every minute) and calls the same API used by **Manual Run** (`runDatabaseBackup`) **only when each backup’s EasyPanel Cron matches the current time**, so schedules configured in the panel are honored.

### Features

- Discovers projects and database services via `listProjectsAndServices`
- Lists backup configs with `listDatabaseBackups` (Postgres, MySQL, MariaDB, Mongo)
- Triggers each matching backup with `runDatabaseBackup`
- Respects the **Cron** field from each EasyPanel backup config (`RESPECT_BACKUP_CRON`)
- Worker poll interval inside Docker (`CRON_SCHEDULE`, default every minute; timezone via `TZ`)
- Optional force run once on container start (`RUN_ON_START`, ignores per-backup cron)
- Filters by project/service and by `enabled` flag
- Dry-run mode (list only, no POST)
- Logs to **stdout** for Docker / [Dozzle](https://dozzle.dev/) (quiet when nothing is due)
- On failures, WhatsApp alert via Meta Cloud API template `system_alert` (`{{1}}` = failure details)

### Requirements

- Easypanel instance + API key (Settings → Server → Users → Generate API Key)
- Docker and Docker Compose (or deploy the image as an app on Easypanel)
- Optional: Meta WhatsApp Cloud API credentials and an approved `system_alert` template for failure alerts

### Quick start (local Docker Compose)

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

4. Check logs (`docker compose logs -f` or Dozzle). With default `RUN_ON_START=true`, one forced run happens immediately; then the worker polls on `CRON_SCHEDULE` and only triggers backups whose EasyPanel Cron is due.

### Deploy on Easypanel

Run this project **as a service on the same Easypanel panel** it backs up. It is an internal cron worker — no public HTTP app is required. Prefer an **App** service built with the repo **Dockerfile** (simpler than Compose for this project).

1. **Create the service**  
   In Easypanel, open a project → **Create service** → choose **App** (not Compose, unless you specifically want Compose).

2. **Source → Git (HTTPS)**  
   Under source / repository, select **Git** and paste the **public HTTPS** URL (not SSH):

   ```text
   https://github.com/sergiofelipe/easy-panel-auto-backups-free.git
   ```

   - **Branch:** `main`  
   - **Build path:** `/` (repository root)  
   - **Build method:** **Dockerfile** (uses the root `Dockerfile`)

   **If you see “Cannot access repository”:** you likely used an SSH URL (`git@github.com:...`) without a deploy key. Either switch the source URL to the HTTPS form above, or use **Generate SSH Key** in Easypanel and add that public key as a **Deploy Key** on the GitHub repo (Settings → Deploy keys). For this public repo, HTTPS is enough — no deploy key needed.

3. **No public domain**  
   Leave domains / public HTTP disabled (or ignore them). This container does not expose a web app; it only needs to stay **running** so cron can fire.

4. **API key (`EASYPANEL_TOKEN`)**  
   In Easypanel: **Settings → Users → Generate API Key** (sometimes under Settings → Server → Users). Copy the key — that value is `EASYPANEL_TOKEN`.

5. **Environment variables**  
   In the service **Environment** tab, paste the variables from [`.env.example`](.env.example) (at least `EASYPANEL_URL` and `EASYPANEL_TOKEN`).

   **Required — enable Create env file**

   Cron jobs inside this container start with a nearly empty process environment. Easypanel must write your variables to a file the worker can read:

   1. Open **Environment**
   2. Turn **on** **Create env file** (sometimes labeled like “Create e…”)
   3. Set **Env file path** to `.env` (default is fine)
   4. **Save** and redeploy / restart the service

   Without this, the first run on start may work (or partially work) while later minute polls fail with `EASYPANEL_URL and EASYPANEL_TOKEN are required`. In healthy logs you should see something like `merged /app/.env` and `EASYPANEL_URL: set`.

   Important ones:

   | Variable | Notes |
   |---|---|
   | `EASYPANEL_URL` | Panel URL, e.g. `https://panel.yourdomain.com` or `http://IP:3000` (with or without `/api`) |
   | `EASYPANEL_TOKEN` | API key from step 4 |
   | `CRON_SCHEDULE` | Worker poll interval — default `* * * * *` (every minute) |
   | `RESPECT_BACKUP_CRON` | Default `true` — honor each backup’s Cron from the EasyPanel UI |
   | `TZ` | Default `America/Sao_Paulo` (must match how you think about panel schedules) |
   | `RUN_ON_START` | Default `true` — one forced run right after deploy (ignores per-backup cron; handy to validate) |
   | `ONLY_ENABLED` | Default `true` — only backup configs marked enabled in the UI |
   | `DRY_RUN` | Optional: `true` once to list targets without triggering backups |
   | `EASYPANEL_PROJECTS` / `EASYPANEL_SERVICES` | Optional comma-separated filters |

6. **Optional: WhatsApp failure alerts**  
   If you want alerts only when a run has failures, also set `WHATSAPP_SYSTEM_PHONE_NUMBER_ID`, `WHATSAPP_SYSTEM_ACCESS_TOKEN`, and `WHATSAPP_NUMBER_TO`, and create the Meta template `system_alert` (see [WhatsApp template](#whatsapp-template-system_alert) below). Skip these vars if you do not need alerts. These must be in the same Environment editor with **Create env file** enabled so cron can read them too.

7. **Deploy**  
   Save and deploy / enable the service. Wait for the image build and container start.

8. **Verify in Logs / Dozzle**  
   Open **Logs** in Easypanel (or [Dozzle](https://dozzle.dev/)). With `RUN_ON_START=true`, you should see something like:

   - `[entrypoint] EASYPANEL_URL: set` / `EASYPANEL_TOKEN: set` (not `MISSING`)
   - `merged /app/.env` (when Create env file is on)
   - `BACKUP RUN START`
   - auth ok against the Easypanel API
   - discovery of DB services / backup configs
   - `RUN | ...` (or `DRY_RUN | ...`) for each backup triggered
   - `BACKUP RUN END`

   On the database service itself, a backup task may appear in progress (e.g. **Backup database**), same as when you click Manual Run in the UI. Afterwards the worker polls every minute and only runs a backup when its EasyPanel **Cron** matches.

Tip: start with `DRY_RUN=true` and `RUN_ON_START=true` once to confirm discovery and filters, then set `DRY_RUN=false` for real `runDatabaseBackup` calls. Set backup times in each app’s EasyPanel backup UI (e.g. `0 2 * * *`).

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `EASYPANEL_URL` | yes | — | Panel URL (with or without `/api`) |
| `EASYPANEL_TOKEN` | yes | — | Bearer API key |
| `CRON_SCHEDULE` | no | `* * * * *` | How often this worker checks for due backups (container local time) |
| `RESPECT_BACKUP_CRON` | no | `true` | If `true`, only run when the backup’s EasyPanel Cron matches now |
| `TZ` | no | `America/Sao_Paulo` | Timezone for schedule matching and logs |
| `RUN_ON_START` | no | `true` | Force-run all matching backups once when the container starts |
| `ONLY_ENABLED` | no | `true` | If `true`, only configs with `enabled=true` |
| `EASYPANEL_PROJECTS` | no | (all) | Comma-separated project names to include |
| `EASYPANEL_SERVICES` | no | (all) | Comma-separated service names to include |
| `DRY_RUN` | no | `false` | If `true`, only log what would run (no `runDatabaseBackup`) |
| `VERBOSE_POLL` | no | `false` | If `true`, log skips on every quiet poll tick |
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

No Easypanel Free (e em casos semelhantes em que o agendador do painel não executa), você ainda pode configurar destinos e horários de backup de banco na UI, mas esses jobs podem nunca disparar sozinhos. Este projeto faz poll dentro do próprio container (padrão: a cada minuto) e chama a mesma API do **Execução Manual** (`runDatabaseBackup`) **somente quando o Cron de cada backup no EasyPanel bate com o horário atual**, respeitando o que foi configurado na tela.

### Funcionalidades

- Descobre projetos e serviços de banco via `listProjectsAndServices`
- Lista configs de backup com `listDatabaseBackups` (Postgres, MySQL, MariaDB, Mongo)
- Dispara cada backup correspondente com `runDatabaseBackup`
- Respeita o campo **Cron** de cada config de backup no EasyPanel (`RESPECT_BACKUP_CRON`)
- Intervalo de verificação no Docker (`CRON_SCHEDULE`, padrão a cada minuto; fuso via `TZ`)
- Execução forçada opcional ao subir o container (`RUN_ON_START`, ignora o cron de cada config)
- Filtros por projeto/serviço e pela flag `enabled`
- Modo dry-run (só lista, sem POST)
- Logs no **stdout** para Docker / [Dozzle](https://dozzle.dev/) (silencioso quando nada está na hora)
- Em falhas, alerta WhatsApp via Meta Cloud API com o template `system_alert` (`{{1}}` = detalhes da falha)

### Requisitos

- Instância Easypanel + chave de API (Settings → Server → Users → Generate API Key)
- Docker e Docker Compose (ou deploy da imagem como app no Easypanel)
- Opcional: credenciais Meta WhatsApp Cloud API e template `system_alert` aprovado para alertas de falha

### Início rápido (Docker Compose local)

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

4. Confira os logs (`docker compose logs -f` ou Dozzle). Com `RUN_ON_START=true` (padrão), uma execução forçada ocorre na subida; depois o worker faz poll em `CRON_SCHEDULE` e só dispara backups cujo Cron no EasyPanel está na hora.

### Instalar no Easypanel

Rode este projeto **como um serviço no próprio Easypanel** que ele fará backup. É um worker de cron interno — não precisa de app HTTP público. Prefira um serviço **App** com build pelo **Dockerfile** do repositório (mais simples que Compose neste projeto).

1. **Criar o serviço**  
   No Easypanel, abra um projeto → **Create service** → escolha **App** (não Compose, a menos que você queira Compose de propósito).

2. **Source → Git (HTTPS)**  
   Em source / repositório, selecione **Git** e cole a URL **HTTPS pública** (não SSH):

   ```text
   https://github.com/sergiofelipe/easy-panel-auto-backups-free.git
   ```

   - **Branch:** `main`  
   - **Build path:** `/` (raiz do repositório)  
   - **Método de build:** **Dockerfile** (usa o `Dockerfile` na raiz)

   **Se aparecer “Cannot access repository”:** provavelmente foi usada uma URL SSH (`git@github.com:...`) sem deploy key. Troque a URL para o HTTPS acima, **ou** use **Generate SSH Key** no Easypanel e adicione a chave pública como **Deploy Key** no GitHub (Settings → Deploy keys). Neste repositório público, HTTPS basta — não precisa de deploy key.

3. **Sem domínio público**  
   Deixe domínio / HTTP público desativado (ou ignore). Este container não expõe app web; só precisa permanecer **rodando** para o cron disparar.

4. **API key (`EASYPANEL_TOKEN`)**  
   No Easypanel: **Settings → Users → Generate API Key** (às vezes em Settings → Server → Users). Copie a chave — esse valor é o `EASYPANEL_TOKEN`.

5. **Variáveis de ambiente**  
   Na aba **Environment** do serviço, cole as variáveis de [`.env.example`](.env.example) (no mínimo `EASYPANEL_URL` e `EASYPANEL_TOKEN`).

   **Obrigatório — ativar Create env file**

   Os jobs do cron neste container sobem com o ambiente do processo quase vazio. O Easypanel precisa gravar as variáveis num arquivo que o worker consiga ler:

   1. Abra **Environment** (Variáveis de ambiente)
   2. Ative **Create env file** (às vezes aparece como “Create e…”)
   3. Em **Env file path**, use `.env` (o padrão serve)
   4. **Salve** e faça redeploy / restart do serviço

   Sem isso, a execução na subida pode funcionar (ou parecer ok) e os polls seguintes falharem com `EASYPANEL_URL and EASYPANEL_TOKEN are required`. Nos logs saudáveis deve aparecer algo como `merged /app/.env` e `EASYPANEL_URL: set`.

   As importantes:

   | Variável | Notas |
   |---|---|
   | `EASYPANEL_URL` | URL do painel, ex.: `https://panel.seudominio.com` ou `http://IP:3000` (com ou sem `/api`) |
   | `EASYPANEL_TOKEN` | API key do passo 4 |
   | `CRON_SCHEDULE` | Intervalo de verificação do worker — padrão `* * * * *` (a cada minuto) |
   | `RESPECT_BACKUP_CRON` | Padrão `true` — respeita o Cron de cada backup na UI do EasyPanel |
   | `TZ` | Padrão `America/Sao_Paulo` (use o mesmo fuso em que você pensa os horários do painel) |
   | `RUN_ON_START` | Padrão `true` — uma execução forçada logo após o deploy (ignora cron das configs; útil para validar) |
   | `ONLY_ENABLED` | Padrão `true` — só configs de backup marcadas como enabled na UI |
   | `DRY_RUN` | Opcional: `true` uma vez para listar alvos sem disparar backups |
   | `EASYPANEL_PROJECTS` / `EASYPANEL_SERVICES` | Filtros opcionais separados por vírgula |

6. **Opcional: alertas WhatsApp em falha**  
   Se quiser alertas só quando a execução tiver falhas, configure também `WHATSAPP_SYSTEM_PHONE_NUMBER_ID`, `WHATSAPP_SYSTEM_ACCESS_TOKEN` e `WHATSAPP_NUMBER_TO`, e crie o template Meta `system_alert` (veja [Template WhatsApp](#template-whatsapp-system_alert) abaixo). Pule essas vars se não precisar de alertas. Elas também precisam estar no mesmo editor de Environment com **Create env file** ativo para o cron conseguir lê-las.

7. **Deploy**  
   Salve e faça o deploy / ative o serviço. Aguarde o build da imagem e a subida do container.

8. **Conferir nos Logs / Dozzle**  
   Abra os **Logs** no Easypanel (ou o [Dozzle](https://dozzle.dev/)). Com `RUN_ON_START=true`, você deve ver algo como:

   - `[entrypoint] EASYPANEL_URL: set` / `EASYPANEL_TOKEN: set` (não `MISSING`)
   - `merged /app/.env` (quando Create env file está ligado)
   - `BACKUP RUN START`
   - autenticação ok na API do Easypanel
   - descoberta de serviços de banco / configs de backup
   - `RUN | ...` (ou `DRY_RUN | ...`) para cada backup disparado
   - `BACKUP RUN END`

   No próprio serviço de banco, pode aparecer uma tarefa de backup em andamento (ex.: **Backup database**), igual ao Manual Run na UI. Depois disso o worker verifica a cada minuto e só roda um backup quando o **Cron** dele no EasyPanel bate.

Dica: comece com `DRY_RUN=true` e `RUN_ON_START=true` uma vez para validar descoberta e filtros; depois volte `DRY_RUN` para `false`. Configure os horários em cada app na tela de backup do EasyPanel (ex.: `0 2 * * *`).

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `EASYPANEL_URL` | sim | — | URL do painel (com ou sem `/api`) |
| `EASYPANEL_TOKEN` | sim | — | API key (Bearer) |
| `CRON_SCHEDULE` | não | `* * * * *` | De quanto em quanto este worker verifica se há backup na hora |
| `RESPECT_BACKUP_CRON` | não | `true` | Se `true`, só roda quando o Cron da config no EasyPanel bate agora |
| `TZ` | não | `America/Sao_Paulo` | Fuso para matching de agenda e logs |
| `RUN_ON_START` | não | `true` | Força todos os backups elegíveis uma vez ao iniciar o container |
| `ONLY_ENABLED` | não | `true` | Se `true`, só configs com `enabled=true` |
| `EASYPANEL_PROJECTS` | não | (todos) | Projetos a incluir, separados por vírgula |
| `EASYPANEL_SERVICES` | não | (todos) | Serviços a incluir, separados por vírgula |
| `DRY_RUN` | não | `false` | Se `true`, só registra o que rodaria (sem `runDatabaseBackup`) |
| `VERBOSE_POLL` | não | `false` | Se `true`, loga os skips a cada tick quieto |
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
