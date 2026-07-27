# Deploy do Studio no Coolify

O Compose de produção usa três imagens prontas no GHCR:

- `ghcr.io/baroni7777/moneyprinterturbo-old-version:latest` para API e WebUI
  legada;
- `ghcr.io/baroni7777/moneyprinterturbo-studio:latest` para o novo frontend.

Antes do primeiro deploy, deixe os dois pacotes GHCR públicos. No GitHub, abra
o pacote, selecione **Package settings** e altere a visibilidade para
**Public**. Caso prefira pacotes privados, configure no Coolify uma credencial
de registry com um token GitHub de leitura de pacotes.

No Coolify, mantenha o domínio da WebUI legada e crie outro para o serviço
`frontend` (por exemplo, `studio.seudominio.com`). O frontend encaminha
`/api/*` internamente para o serviço `api`, portanto o navegador não precisa
de domínio nem CORS separado para a API v2.

Variáveis mínimas de produção:

```env
MPT_DATABASE_URL=sqlite:////MoneyPrinterTurbo/storage/moneyprinterturbo.db
MPT_AUTH_COOKIE_SECURE=true
MPT_AUTH_COOKIE_SAMESITE=lax
```

O volume `./storage:/MoneyPrinterTurbo/storage` precisa permanecer configurado.
Ele contém o SQLite e os arquivos de geração. A API executa `alembic upgrade
head` antes de iniciar, portanto faça um backup desse volume antes de cada
atualização de produção.

O Compose de release inicia Redis com persistência AOF para a fila e o estado
das tarefas. Não desative `MPT_APP_ENABLE_REDIS` nesse ambiente. Em caso de
reinício sem uma tarefa recuperável na fila, a geração fica registrada como
falha na plataforma, com o estágio `restart`, para que seja possível repetir a
solicitação sem perder o histórico.

Por padrão, cada chave de automação aceita até 60 solicitações por minuto. Para
ajustar o limite, defina `MPT_API_KEY_RATE_LIMIT_PER_MINUTE` no Coolify.

Após o primeiro deploy, crie o administrador dentro do container da API:

```bash
python -m app.commands.create_admin --email admin@seudominio.com --name "Administrador"
```

O comando pede a senha sem mostrá-la. Para uma execução não interativa, use
`MPT_BOOTSTRAP_ADMIN_PASSWORD` apenas durante o comando e remova a variável em
seguida.

Para n8n, o usuário cria uma chave no projeto pelo Studio. A chave é exibida
uma única vez. O workflow usa:

```http
POST /api/v2/automation/projects/{project_id}/generations
X-API-Key: mpt_...
Idempotency-Key: identificador-unico-da-execucao
Content-Type: application/json
```

```json
{"video_subject":"Tema do vídeo"}
```

Consulte o progresso com:

```http
GET /api/v2/automation/projects/{project_id}/generations/{generation_id}
X-API-Key: mpt_...
```
