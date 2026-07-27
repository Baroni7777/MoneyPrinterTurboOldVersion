# Plano de ação — Plataforma multiusuário do MoneyPrinterTurbo

Status: implementação do MVP em andamento  
Data: 24 de julho de 2026  
Objetivo: orientar a evolução do MoneyPrinterTurbo para uma plataforma
multiusuário sem interromper a API v1 nem a WebUI Streamlit existentes.

Implementação iniciada:

- SQLAlchemy configurado com SQLite como padrão;
- troca de dialeto por `MPT_DATABASE_URL`;
- driver PostgreSQL incluído;
- Alembic configurado;
- migração inicial da plataforma criada;
- modelos iniciais de usuário, workspace, projeto, perfil, preset, geração,
  arquivo, chave de API e auditoria criados;
- testes de banco e migração adicionados.
- autenticação v2 com sessões revogáveis e cookies `HttpOnly` criada;
- hash de senha Argon2id criado;
- administração inicial de usuários e workspace pessoal automático criados;
- comando de bootstrap do primeiro administrador criado.
- CRUD de projetos com isolamento por workspace criado;
- perfis criativos versionados e presets salvos criados;
- API criativa v2 integrada à fila de geração existente criada;
- frontend Next.js separado com login, dashboard, projeto e nova geração criado.
- chaves de API por projeto, com escopos, hash, revogação e endpoint próprio
  para automações n8n criadas;
- histórico de gerações e entrega autenticada dos arquivos de saída adicionados;
- migrações Alembic executadas automaticamente antes de iniciar a API nos
  Docker Compose locais e de produção.

## 1. Solicitação de produto

Criar um novo frontend, mantendo o frontend atual disponível, no qual:

- usuários entrem com login e senha;
- exista um administrador do sistema;
- cada usuário possa criar vários projetos editoriais;
- cada projeto represente um nicho, público e estilo próprios;
- configurações de geração possam ser salvas e reutilizadas;
- integrações, como n8n, possam gerar vídeos usando as configurações salvas;
- a nova camada criativa ofereça estilos de roteiro, estruturas narrativas,
  planejamento de cenas e maior originalidade visual;
- as APIs atuais continuem funcionando sem alteração de contrato.

Música contextual não faz parte da primeira entrega. Inicialmente, o sistema
continuará usando as opções existentes, poderá gerar o vídeo sem música ou
deixar a música para a ferramenta de publicação de cada plataforma.

## 2. Resultado esperado

O produto deixará de ser apenas uma tela de geração e passará a organizar todo
o processo editorial:

```text
Usuário
  └── Workspace
       ├── Projeto: Canal de produtividade
       │    ├── Perfil editorial
       │    ├── Perfil visual
       │    ├── Preset: YouTube Shorts casual
       │    ├── Preset: YouTube horizontal
       │    └── Gerações e arquivos
       └── Projeto: Canal de curiosidades
            ├── Perfil editorial
            ├── Perfil visual
            ├── Presets
            └── Gerações e arquivos
```

Uma requisição do n8n poderá informar apenas projeto, preset e tema:

```http
POST /api/v2/projects/{project_id}/generations
```

```json
{
  "preset_id": "0190f2c0-6d79-7a3e-bfc1-23df8323b0f2",
  "video_subject": "Como pequenas interrupções prejudicam a concentração",
  "idempotency_key": "n8n-execution-1842-item-1"
}
```

O backend resolverá todas as demais configurações salvas e retornará o
`task_id` para acompanhamento.

## 3. Princípios da implementação

### 3.1 Compatibilidade

- `/api/v1/*` não terá contratos removidos ou renomeados.
- A WebUI Streamlit continuará disponível durante todo o desenvolvimento.
- A nova experiência utilizará `/api/v2/*`.
- A consulta, o streaming e o download de tarefas existentes poderão ser
  reutilizados internamente.
- Testes de contrato garantirão que mudanças na plataforma não quebrem a v1.

### 3.2 Reutilização sem duplicação

Não copiar integralmente `app/services/task.py`, `app/services/video.py` ou os
controladores v1. A API v2 deverá preparar uma configuração mais rica e usar
adaptadores para chamar o pipeline atual.

```text
API v1 ───────────────┐
                     ├── Serviços compartilhados ── Renderização
API v2 → Orquestrador ┘
         criativo
```

Podem ser copiados os padrões de organização dos controladores e testes, mas
não a lógica completa de geração.

### 3.3 Segurança por padrão

- autorização será aplicada no backend, nunca apenas no frontend;
- todas as consultas a recursos privados serão limitadas por workspace;
- senhas serão armazenadas somente como hash forte;
- tokens de API serão mostrados uma única vez e armazenados como hash;
- cookies de autenticação serão `HttpOnly`, `Secure` e com política
  `SameSite` apropriada;
- tokens de autenticação não serão guardados em `localStorage`;
- credenciais de provedores não serão devolvidas ao navegador;
- operações administrativas e sensíveis gerarão auditoria.

### 3.4 Configuração durável

O `config.toml` e as variáveis de ambiente continuarão responsáveis por
infraestrutura e padrões globais. Configurações de usuários, projetos e
presets ficarão no banco de dados.

### 3.5 Evolução incremental

Cada etapa deverá produzir uma versão utilizável. O novo frontend não assumirá
o domínio principal até que autenticação, geração e download estejam
validados.

## 4. Arquitetura proposta

### 4.1 Componentes

```text
┌──────────────────────────────────────────────────────────────┐
│ Novo frontend — Next.js + TypeScript                         │
│ Login, dashboard, projetos, presets, gerações e administração│
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTPS / API v2
┌──────────────────────────────▼───────────────────────────────┐
│ Backend FastAPI existente                                   │
│ Auth, autorização, projetos, presets, API v2 e API v1        │
├───────────────────┬───────────────────┬──────────────────────┤
│ SQLite → Postgres │ Redis             │ Armazenamento        │
│ dados duráveis    │ fila/sessões      │ volume local → S3    │
└───────────────────┴─────────┬─────────┴──────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────┐
│ Worker de geração                                            │
│ LLM, materiais, TTS, legendas e MoviePy/FFmpeg               │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ WebUI Streamlit atual — mantida durante a transição          │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Novo frontend

Recomendação:

- Next.js com App Router;
- TypeScript;
- componentes de servidor para páginas e leitura de dados;
- componentes de cliente apenas onde houver interação;
- biblioteca de componentes acessível e consistente;
- validação de formulários no cliente e novamente no backend;
- testes de interface e jornadas críticas.

O frontend será uma aplicação separada, por exemplo em `frontend/`, com imagem
Docker própria. Ele não será incorporado ao processo Streamlit.

Para reduzir problemas de CORS e autenticação entre domínios, a opção
preferencial é expor a API sob o mesmo domínio da nova aplicação:

```text
https://studio.exemplo.com/       → Next.js
https://studio.exemplo.com/api/*  → FastAPI
```

Se frontend e API permanecerem em subdomínios diferentes, será necessário
configurar explicitamente origem permitida, credenciais, domínio do cookie e
proteção CSRF.

### 4.3 Backend

O FastAPI continuará sendo o backend principal. Serão adicionadas camadas
separadas:

```text
app/
  controllers/
    v1/
    v2/
      auth.py
      admin.py
      projects.py
      presets.py
      generations.py
      assets.py
      api_keys.py
      creative.py
  models/
    schema.py
    creative_schema.py
    platform_schema.py
  domain/
    auth/
    projects/
    generations/
    creative/
  repositories/
  database/
  services/
    creative/
      profiles.py
      script_builder.py
      narrative_planner.py
      scene_planner.py
      originality.py
      adapter.py
```

Controladores devem tratar HTTP. Regras de negócio devem ficar nos serviços
de aplicação/domínio. Acesso ao banco deve ficar nos repositórios.

### 4.4 Banco de dados

Usar SQLite inicialmente como fonte de verdade para contas, projetos,
configurações e histórico. A camada será construída com SQLAlchemy e tipos
portáveis para permitir a migração posterior para PostgreSQL.

A conexão será controlada por uma única variável:

```env
MPT_DATABASE_URL=sqlite:///storage/moneyprinterturbo.db
```

No PostgreSQL:

```env
MPT_DATABASE_URL=postgresql+psycopg://usuario:senha@postgres:5432/moneyprinterturbo
```

A URL seleciona o dialeto e o driver; não haverá uma segunda variável para
“tipo de banco”. A troca de URL não copia os dados existentes. A migração de
SQLite para PostgreSQL exigirá exportação/importação validada, execução das
migrações no destino e uma janela controlada de troca.

Para manter a portabilidade:

- IDs serão UUIDs gerados pela aplicação e armazenados como texto;
- JSON utilizará o tipo genérico do SQLAlchemy;
- estados e papéis serão texto validado pela aplicação;
- migrações evitarão SQL específico de um dialeto;
- chaves estrangeiras serão habilitadas explicitamente no SQLite;
- a suíte executará as migrações em banco SQLite temporário;
- PostgreSQL será validado antes da troca de produção.

SQLite é adequado para o desenvolvimento e o primeiro uso em uma VPS com
concorrência limitada. Quando houver múltiplos workers, maior volume de
escritas ou alta concorrência, PostgreSQL passará a ser obrigatório.

Redis não substitui o banco relacional: continuará responsável por fila,
coordenação, cache e, se adotado, sessões.

As alterações do banco serão versionadas com migrações. Nenhuma tabela deverá
ser criada implicitamente na inicialização de produção.

Comandos operacionais:

```bash
# Aplicar todas as migrações pendentes
uv run alembic upgrade head

# Conferir a revisão instalada
uv run alembic current

# Reverter apenas a última migração, após backup e validação
uv run alembic downgrade -1
```

No container:

```bash
alembic upgrade head
```

O deploy automatizado só deverá executar `upgrade head` depois que houver
backup e estratégia de rollback. `downgrade` nunca será executado
automaticamente em produção.

### 4.5 Armazenamento de arquivos

Primeira fase:

- manter o volume persistente atual;
- organizar arquivos por workspace, projeto e geração;
- nunca aceitar um caminho arbitrário fornecido pelo cliente;
- registrar metadados e propriedade no banco relacional;
- entregar arquivos somente após autorização.

Estrutura lógica:

```text
storage/
  workspaces/{workspace_id}/
    projects/{project_id}/
      assets/
      generations/{generation_id}/
        input/
        intermediate/
        output/
```

O acesso ao armazenamento deve passar por uma interface interna. Isso permitirá
migrar posteriormente para S3, Cloudflare R2 ou MinIO sem alterar a API.

## 5. Modelo de domínio

### 5.1 Usuário

`users`

- `id`;
- `email` normalizado e único;
- `password_hash`;
- `display_name`;
- `system_role`: `admin` ou `user`;
- `status`: `active`, `invited`, `suspended`;
- `last_login_at`;
- `created_at`;
- `updated_at`.

Na primeira versão, contas poderão ser criadas pelo administrador. Cadastro
público e recuperação por e-mail podem ser adicionados depois.

### 5.2 Workspace

`workspaces`

- `id`;
- `name`;
- `slug`;
- `status`;
- `created_at`;
- `updated_at`.

Cada usuário recebe um workspace pessoal automaticamente. A existência dessa
entidade desde o início permite adicionar equipes sem remodelar todas as
tabelas.

### 5.3 Participação

`workspace_memberships`

- `workspace_id`;
- `user_id`;
- `role`: `owner`, `editor` ou `viewer`;
- `created_at`.

No MVP, apenas `owner` será usado na interface, mas a autorização já deverá
reconhecer os três papéis.

### 5.4 Projeto editorial

`projects`

- `id`;
- `workspace_id`;
- `name`;
- `slug`;
- `description`;
- `niche`;
- `primary_language`;
- `target_audience`;
- `status`: `active` ou `archived`;
- `created_by`;
- `created_at`;
- `updated_at`.

“Projeto” representa uma marca ou linha editorial. Não deve ser confundido
com uma conta externa do YouTube.

### 5.5 Canais de publicação

`publication_channels`

- `id`;
- `project_id`;
- `platform`: `youtube`, `tiktok`, `instagram` etc.;
- `display_name`;
- `external_channel_id`;
- `status`;
- referência segura para credenciais;
- `created_at`;
- `updated_at`.

Integração OAuth e publicação automática não fazem parte do primeiro marco,
mas o modelo já ficará preparado.

### 5.6 Perfil criativo versionado

`creative_profiles`

- `id`;
- `project_id`;
- `version`;
- `name`;
- `is_active`;
- `configuration` em JSON validado;
- `created_by`;
- `created_at`.

Configuração sugerida:

```json
{
  "editorial": {
    "tone": "casual_expert",
    "formality": 0.3,
    "humor": 0.2,
    "sentence_length": "short",
    "target_audience": "adultos interessados em produtividade",
    "original_perspective_required": true,
    "concrete_example_required": true,
    "maximum_rhetorical_questions": 2,
    "forbidden_phrases": [
      "você não vai acreditar",
      "assista até o final"
    ]
  },
  "narrative": {
    "allowed_structures": [
      "problem_solution",
      "myth_fact",
      "case_study"
    ],
    "default_structure": "auto"
  },
  "visual": {
    "style": "clean_editorial",
    "match_materials_to_script": true,
    "show_key_phrases": true,
    "avoid_recent_materials": true,
    "material_reuse_window_days": 30
  },
  "compliance": {
    "require_human_review": true,
    "sensitive_topics": [
      "health",
      "finance",
      "legal",
      "politics"
    ]
  }
}
```

Perfis serão imutáveis depois de utilizados. Uma edição cria uma nova versão,
garantindo que uma geração antiga continue reproduzível.

### 5.7 Preset de geração

`generation_presets`

- `id`;
- `project_id`;
- `creative_profile_id`;
- `name`;
- `platform`;
- `configuration` em JSON validado;
- `is_default`;
- `created_at`;
- `updated_at`.

Exemplo:

```json
{
  "platform": "youtube_shorts",
  "video_aspect": "9:16",
  "duration_target_seconds": 60,
  "video_source": "pexels",
  "voice_name": "gemini:Zephyr-Female",
  "voice_rate": 1.0,
  "subtitle_enabled": true,
  "font_name": "STHeitiMedium.ttc",
  "font_size": 60,
  "video_clip_duration": 3,
  "video_transition_mode": null,
  "music_mode": "platform"
}
```

### 5.8 Geração

`generations`

- `id`;
- `workspace_id`;
- `project_id`;
- `preset_id`;
- `creative_profile_id`;
- `creative_profile_version`;
- `legacy_task_id`;
- `requested_by`;
- `status`;
- `video_subject`;
- `resolved_configuration`;
- `script`;
- `scene_plan`;
- `error_stage`;
- `error_message`;
- `started_at`;
- `completed_at`;
- `created_at`.

`resolved_configuration` é uma fotografia completa das configurações usadas,
sem segredos. Isso permite auditoria, repetição e diagnóstico.

### 5.9 Arquivo

`assets`

- `id`;
- `workspace_id`;
- `project_id`;
- `generation_id`, quando aplicável;
- `kind`: `material`, `audio`, `subtitle`, `video`, `thumbnail`;
- `storage_key`;
- `original_filename`;
- `mime_type`;
- `size_bytes`;
- `checksum`;
- `source_provider`;
- metadados de licença;
- `created_at`.

### 5.10 Chave de API

`api_keys`

- `id`;
- `workspace_id`;
- `project_id` opcional;
- `name`;
- `key_prefix`;
- `key_hash`;
- escopos;
- `last_used_at`;
- `expires_at`;
- `revoked_at`;
- `created_by`;
- `created_at`.

Escopos iniciais:

```text
projects:read
presets:read
generations:create
generations:read
assets:read
```

### 5.11 Auditoria

`audit_logs`

- ator;
- workspace;
- ação;
- tipo e ID do recurso;
- endereço IP e agente do cliente;
- metadados sem segredos;
- data.

## 6. Resolução das configurações

Ao iniciar uma geração, a configuração efetiva será calculada nesta ordem:

```text
Padrões seguros do sistema
  → Perfil criativo ativo do projeto
  → Preset selecionado
  → Sobrescritas permitidas na requisição
```

Sobrescritas serão limitadas por uma lista explícita. Uma chave de API de
projeto, por exemplo, não poderá alterar `project_id`, provedor global,
diretório de armazenamento ou credenciais.

Exemplo de sobrescritas permitidas:

- tema;
- roteiro fornecido;
- estrutura narrativa;
- duração dentro dos limites;
- quantidade de vídeos dentro da cota;
- ativação de legendas;
- velocidade da voz dentro dos limites.

## 7. API v2

### 7.1 Autenticação

```text
POST /api/v2/auth/login
POST /api/v2/auth/logout
GET  /api/v2/auth/me
POST /api/v2/auth/change-password
```

Recuperação de senha por e-mail será uma fase posterior. Inicialmente, o
administrador poderá emitir um convite ou redefinição temporária.

### 7.2 Projetos e perfis

```text
GET    /api/v2/projects
POST   /api/v2/projects
GET    /api/v2/projects/{project_id}
PATCH  /api/v2/projects/{project_id}
DELETE /api/v2/projects/{project_id}

GET  /api/v2/projects/{project_id}/creative-profiles
POST /api/v2/projects/{project_id}/creative-profiles
GET  /api/v2/projects/{project_id}/creative-profiles/{profile_id}
POST /api/v2/projects/{project_id}/creative-profiles/{profile_id}/versions
```

O `DELETE` de projeto será inicialmente um arquivamento recuperável.

### 7.3 Presets

```text
GET    /api/v2/projects/{project_id}/presets
POST   /api/v2/projects/{project_id}/presets
GET    /api/v2/projects/{project_id}/presets/{preset_id}
PATCH  /api/v2/projects/{project_id}/presets/{preset_id}
DELETE /api/v2/projects/{project_id}/presets/{preset_id}
POST   /api/v2/projects/{project_id}/presets/{preset_id}/duplicate
```

### 7.4 Planejamento criativo

```text
POST /api/v2/projects/{project_id}/creative/scripts
POST /api/v2/projects/{project_id}/creative/scene-plans
POST /api/v2/projects/{project_id}/creative/previews
```

Implementação atual:

```text
POST /api/v2/projects/{project_id}/creative/scripts
POST /api/v2/projects/{project_id}/creative/scene-plans
POST /api/v2/projects/{project_id}/generations
GET  /api/v2/projects/{project_id}/generations
GET  /api/v2/projects/{project_id}/generations/{generation_id}
```

A criação de geração resolve perfil ativo + preset + tema e a transforma em
`VideoParams` compatível com a fila já utilizada pela API v1. O histórico
armazena o `task_id`, perfil e configuração resolvida.

Esses endpoints podem ser usados separadamente na interface ou no n8n.

### 7.5 Geração

```text
POST /api/v2/projects/{project_id}/generations
GET  /api/v2/projects/{project_id}/generations
GET  /api/v2/projects/{project_id}/generations/{generation_id}
POST /api/v2/projects/{project_id}/generations/{generation_id}/retry
POST /api/v2/projects/{project_id}/generations/{generation_id}/cancel
GET  /api/v2/projects/{project_id}/generations/{generation_id}/assets
```

A criação aceitará `Idempotency-Key` no cabeçalho. Isso impedirá que uma
repetição automática do n8n crie dois vídeos iguais.

### 7.6 Chaves de integração

```text
GET    /api/v2/api-keys
POST   /api/v2/api-keys
DELETE /api/v2/api-keys/{api_key_id}
```

A chave completa só será exibida na resposta de criação.

### 7.7 Administração

```text
GET   /api/v2/admin/users
POST  /api/v2/admin/users
PATCH /api/v2/admin/users/{user_id}
POST  /api/v2/admin/users/{user_id}/reset-password

GET /api/v2/admin/tasks
GET /api/v2/admin/system/health
GET /api/v2/admin/storage
GET /api/v2/admin/audit-logs
GET /api/v2/admin/provider-status
```

Impersonação de usuário não será implementada no MVP devido ao risco de
segurança e à necessidade de auditoria mais rigorosa.

## 8. Orquestrador criativo

### 8.1 Perfis de roteiro

Perfis iniciais:

```text
casual_educational
casual_storytelling
documentary_light
quick_tutorial
myth_vs_fact
case_study
comparison
opinion_commentary
```

O serviço transformará o perfil em instruções para os campos já suportados
por `llm.generate_script`, sem alterar a API v1.

### 8.2 Estruturas narrativas

```text
problem_solution
myth_fact
story_arc
comparison
case_study
step_by_step
question_investigation_answer
before_after
opinion_analysis
```

O modo `auto` escolherá uma estrutura e registrará a escolha na geração.

### 8.3 Planejamento de cenas

O plano de cenas terá um contrato estruturado:

```json
{
  "scenes": [
    {
      "index": 1,
      "narration": "Trecho do roteiro",
      "purpose": "apresentar o problema",
      "visual_intent": "Pessoa interrompida por notificações",
      "search_terms": [
        "phone work distraction"
      ],
      "key_phrase": "O foco tem um custo",
      "transition": "fade"
    }
  ]
}
```

O adaptador extrairá os termos em ordem e acionará o pipeline existente com
`match_materials_to_script=true`.

### 8.4 Originalidade visual — fase inicial

- relacionar materiais a cenas;
- armazenar os identificadores e checksums dos materiais utilizados;
- evitar clipes usados recentemente no mesmo projeto;
- rejeitar material de resolução inadequada;
- controlar repetição de termos de busca;
- selecionar planos visualmente variados;
- registrar a origem e a licença;
- manter concatenação sequencial quando houver plano de cenas.

### 8.5 Originalidade visual — fase avançada

- frases-chave independentes das legendas;
- cards de comparação;
- números e estatísticas em destaque;
- títulos de seção;
- ícones e elementos gráficos;
- zoom e enquadramento guiados por cena;
- templates visuais por projeto;
- geração de miniatura;
- ilustrações exclusivas.

Esses recursos ficarão em um compositor opcional chamado apenas pela v2.

### 8.6 Música no MVP

Modos:

```text
none      → gera sem música
existing  → usa o BGM já suportado pelo projeto
platform  → gera sem música para adicioná-la na plataforma
```

O modo `platform` não deverá baixar e reaproveitar em outra plataforma uma
música licenciada apenas no YouTube, TikTok ou Instagram.

## 9. Novo frontend: mapa de telas

### 9.1 Públicas

- Login.
- Aceitar convite.
- Definir ou redefinir senha.
- Página de indisponibilidade/manutenção.

### 9.2 Área autenticada

#### Dashboard

- projetos recentes;
- gerações em andamento;
- falhas recentes;
- uso de armazenamento;
- atalhos para nova geração.

Implementação inicial disponível no novo frontend:

- `/login`;
- `/dashboard`;
- `/projects/new`;
- `/projects/{project_id}`;
- proxy interno `/api/*` para a API FastAPI.

#### Projetos

- listar, buscar, criar e arquivar projetos;
- visualizar nicho, idioma e status;
- duplicar projeto futuramente.

#### Projeto

Abas:

```text
Visão geral
Identidade editorial
Estilo visual
Presets
Nova geração
Gerações
Arquivos
Canais
Integrações/API
```

#### Assistente de projeto

Passos:

1. nome e nicho;
2. público;
3. idioma e tom;
4. estruturas narrativas;
5. identidade visual;
6. voz, legenda e fonte de materiais;
7. preset inicial;
8. revisão.

#### Nova geração

- selecionar preset;
- informar tema;
- escolher estrutura ou modo automático;
- gerar e editar roteiro;
- visualizar plano de cenas;
- iniciar renderização;
- acompanhar progresso;
- revisar e baixar o resultado.

#### Histórico

- filtros por projeto, status, data e preset;
- prévia;
- detalhes das configurações resolvidas;
- erros por etapa;
- repetir com as mesmas configurações;
- duplicar alterando apenas o tema;
- baixar vídeo, áudio e legenda.

### 9.3 Administração

- usuários;
- workspaces;
- tarefas e fila;
- consumo e cotas;
- saúde dos provedores;
- armazenamento;
- logs de auditoria;
- configurações globais não secretas;
- manutenção.

## 10. Autenticação e autorização

### 10.1 Login

- e-mail e senha;
- hash de senha Argon2id;
- proteção contra tentativas repetidas;
- sessão revogável;
- rotação após login;
- logout encerra a sessão no servidor;
- alteração de senha revoga outras sessões.

Implementação inicial:

```text
POST /api/v2/auth/login
POST /api/v2/auth/logout
GET  /api/v2/auth/me
POST /api/v2/auth/change-password
```

As sessões usam tokens aleatórios. Somente o hash SHA-256 do token é salvo no
banco. As senhas usam Argon2id e nunca são registradas em texto puro.

Antes do primeiro uso:

```bash
uv run alembic upgrade head
```

Criação segura do primeiro administrador:

```bash
uv run python -m app.commands.create_admin \
  --email admin@exemplo.com \
  --name "Administrador"
```

O comando solicita a senha sem exibi-la. Em um terminal não interativo, ela
pode ser fornecida temporariamente por `MPT_BOOTSTRAP_ADMIN_PASSWORD`; a
variável deve ser removida imediatamente depois.

Em produção:

```env
MPT_AUTH_COOKIE_SECURE=true
MPT_AUTH_COOKIE_SAMESITE=lax
CORS_ALLOWED_ORIGINS=https://studio.exemplo.com
```

O padrão CORS não permite credenciais entre origens. Cookies autenticados entre
origens somente serão aceitos quando as origens confiáveis forem listadas
explicitamente.

### 10.2 Matriz de acesso

| Recurso | Admin | Owner | Editor | Viewer |
|---|---:|---:|---:|---:|
| Administrar usuários | Sim | Não | Não | Não |
| Editar projeto | Sim | Sim | Sim | Não |
| Gerenciar membros | Sim | Sim | Não | Não |
| Criar preset | Sim | Sim | Sim | Não |
| Iniciar geração | Sim | Sim | Sim | Não |
| Consultar geração | Sim | Sim | Sim | Sim |
| Criar chave de API | Sim | Sim | Não | Não |
| Arquivar projeto | Sim | Sim | Não | Não |

O papel de administrador não elimina a necessidade de auditoria.

### 10.3 API para n8n

- usar chave específica, não login e senha;
- permitir escopo por projeto;
- aceitar idempotência;
- aplicar limite de requisições;
- registrar último uso;
- permitir revogação imediata;
- nunca registrar o valor completo da chave em logs.

## 11. Fila e execução

Para ambiente multiusuário, tarefas não podem depender apenas da memória do
processo da API.

Primeiro marco:

- Redis obrigatório em produção;
- geração registrada no banco relacional antes de entrar na fila;
- transições de estado persistidas;
- associação obrigatória a usuário, workspace e projeto;
- recuperação após reinício;
- limites de concorrência globais e por workspace.

Evolução:

- separar o worker de renderização do processo FastAPI;
- permitir múltiplos workers;
- reservar tarefas atomicamente;
- heartbeat e detecção de worker perdido;
- cancelamento cooperativo;
- política explícita de repetição por etapa.

## 12. Implantação no Coolify

Serviços previstos:

```text
legacy-webui  → Streamlit existente
frontend      → novo Next.js
api           → FastAPI
worker        → geração de vídeos
database      → SQLite inicialmente; PostgreSQL na fase de escala
redis         → fila, cache e sessões
```

Persistência:

- arquivo SQLite dentro do volume de `storage` no primeiro estágio;
- volume de PostgreSQL depois da migração;
- volume de Redis, se usado para dados recuperáveis;
- volume de `storage`;
- backups externos e testados.

Estratégia de domínio:

```text
legacy.vid.exemplo.com  → Streamlit
studio.vid.exemplo.com  → novo frontend
studio.vid.exemplo.com/api/* → FastAPI
```

Depois da estabilização, o novo frontend pode assumir o domínio principal sem
remover imediatamente a interface legada.

## 13. Observabilidade

Cada requisição e tarefa deverá transportar:

- `request_id`;
- `user_id`;
- `workspace_id`;
- `project_id`;
- `generation_id`;
- `task_id`.

Logs não devem conter:

- senha;
- cookie;
- token;
- chave de API;
- chave de provedor;
- roteiro privado completo por padrão.

Métricas iniciais:

- tarefas em fila;
- tarefas executando;
- duração por etapa;
- falhas por etapa e provedor;
- armazenamento por workspace;
- gerações por usuário;
- taxa de repetição;
- tempo até conclusão.

## 14. Testes obrigatórios

### 14.1 Unidade

- hash e validação de senha;
- escopos de chave de API;
- resolução de configuração;
- versionamento de perfil;
- adaptador v2 para `VideoParams`;
- validação do plano de cenas;
- filtros de repetição de materiais;
- regras de autorização.

### 14.2 Integração

- login, renovação e logout;
- isolamento entre dois usuários;
- CRUD de projetos e presets;
- geração a partir de preset;
- idempotência do n8n;
- persistência de status;
- acesso autorizado a arquivos;
- endpoints administrativos.

### 14.3 Contrato

- executar a suíte atual contra `/api/v1`;
- congelar exemplos OpenAPI essenciais da v1;
- garantir que campos novos não alterem respostas existentes.

### 14.4 Ponta a ponta

Jornada mínima:

```text
admin cria usuário
  → usuário define senha
  → cria projeto
  → configura perfil
  → salva preset
  → gera vídeo
  → acompanha tarefa
  → reproduz e baixa o arquivo
```

Outra jornada deve validar uma geração via chave de API/n8n.

## 15. Fases de desenvolvimento

### Fase 0 — Decisões e base

Entregas:

- registrar decisões arquiteturais;
- definir contratos dos modelos;
- adicionar SQLAlchemy, SQLite e migrações ao ambiente de desenvolvimento;
- configurar migrações;
- criar testes de contrato da v1;
- definir estratégia de domínio e cookies.

Critério de conclusão:

- banco sobe localmente;
- migração inicial funciona em banco vazio;
- APIs e Streamlit existentes continuam funcionando.

### Fase 1 — Identidade e autorização

Entregas:

- usuários;
- workspaces e memberships;
- login/logout/me;
- hash de senha;
- sessões;
- administrador inicial por comando seguro;
- auditoria básica;
- middleware/contexto do usuário.

Critério de conclusão:

- dois usuários não conseguem acessar recursos um do outro;
- admin consegue criar, suspender e reativar usuários;
- nenhuma credencial aparece nos logs.

### Fase 2 — Estrutura do novo frontend

Entregas:

- projeto Next.js separado;
- layout autenticado;
- login;
- dashboard;
- tratamento padronizado de erros;
- cliente de API tipado;
- proteção de rotas no servidor.

Critério de conclusão:

- login e logout funcionam em produção;
- usuário não autenticado não acessa páginas privadas;
- Streamlit permanece acessível no domínio legado.

### Fase 3 — Projetos e configurações

Entregas:

- CRUD de projetos;
- assistente de configuração;
- perfis criativos versionados;
- presets;
- tela de integrações;
- chaves de API com escopos.

Critério de conclusão:

- usuário cria dois projetos com estilos independentes;
- alteração de um projeto não afeta o outro;
- n8n consegue ler um preset com chave limitada ao projeto.

### Fase 4 — API criativa v2

Entregas:

- perfis de roteiro;
- estruturas narrativas;
- geração de roteiro;
- planejamento de cenas;
- adaptador para o pipeline atual;
- endpoints de prévia;
- validação dos contratos estruturados do LLM.

Critério de conclusão:

- a mesma entrada pode ser gerada pela v1 e v2;
- a v1 mantém o comportamento anterior;
- a v2 registra perfil, estrutura e plano utilizados.

### Fase 5 — Geração e originalidade visual

Entregas:

- criar geração por projeto/preset;
- histórico;
- progresso persistente;
- reprodução e download autorizados;
- rastreamento de materiais;
- prevenção de reutilização recente;
- overlays iniciais;
- repetir e cancelar tarefa.

Critério de conclusão:

- geração completa funciona pelo frontend e pelo n8n;
- reinício da API não perde o registro;
- arquivos de um projeto não podem ser acessados por outro.

### Fase 6 — Administração

Entregas:

- usuários e workspaces;
- monitor da fila;
- cotas;
- armazenamento;
- saúde dos provedores;
- auditoria;
- ações de recuperação seguras.

Critério de conclusão:

- administrador identifica uma falha por etapa;
- consegue suspender acesso sem apagar dados;
- ações administrativas ficam registradas.

### Fase 7 — Produção e endurecimento

Entregas:

- worker separado;
- limites e rate limiting;
- backups;
- política de retenção;
- cabeçalhos de segurança;
- varredura de dependências;
- testes de carga da fila;
- documentação operacional;
- plano de rollback.

Critério de conclusão:

- restauração de backup validada;
- deploy não interrompe tarefas concluídas;
- rollback do frontend não exige rollback do banco;
- checklist de segurança aprovado.

### Fase 8 — Publicação multiplataforma

Fora do MVP inicial:

- OAuth para plataformas;
- associação de canais externos;
- variantes por plataforma;
- calendário;
- aprovação editorial;
- publicação;
- métricas;
- música específica por plataforma e licenciamento.

## 16. Primeira sequência de trabalho

Ordem recomendada para começar:

1. escrever as decisões arquiteturais da Fase 0;
2. adicionar PostgreSQL e migrações;
3. criar modelos `User`, `Workspace` e `Membership`;
4. implementar login, sessão e autorização;
5. criar a estrutura do novo frontend;
6. implementar projetos;
7. implementar perfis e presets;
8. criar chaves de API;
9. iniciar a API criativa v2;
10. conectar a geração existente por adaptador;
11. criar histórico e arquivos autorizados;
12. migrar o workflow n8n para a v2.

Não começar pelo editor visual completo. Sem identidade, autorização,
persistência e isolamento, qualquer tela avançada teria que ser refeita.

## 17. Decisões recomendadas

| Tema | Recomendação inicial |
|---|---|
| Frontend | Next.js separado do Streamlit |
| Backend | Manter FastAPI |
| API | Preservar v1 e criar v2 |
| Banco | SQLite inicialmente, PostgreSQL ao escalar |
| Fila | Redis obrigatório em produção |
| Arquivos | Volume local com interface preparada para S3 |
| Login | Sessão segura em cookie HttpOnly |
| Cadastro | Contas criadas/convidadas pelo admin no MVP |
| Modelo de posse | Workspace desde o início |
| Configuração editorial | Banco, com versões |
| Credenciais globais | Ambiente/Coolify |
| Credenciais de usuário | Adiar; quando necessárias, armazenar criptografadas |
| Música | Nenhuma, existente ou adicionada na plataforma |
| Exclusão de projeto | Arquivamento recuperável |
| n8n | Chave de API com escopo e idempotência |
| WebUI atual | Mantida em domínio legado |

## 18. Fora de escopo do MVP

- cobrança e assinatura;
- marketplace de templates;
- aplicativo móvel;
- colaboração em tempo real;
- publicação automática em todas as plataformas;
- editor de vídeo completo no navegador;
- música gerada dinamicamente;
- impersonação administrativa;
- cadastro público irrestrito;
- múltiplas regiões;
- armazenamento distribuído desde o primeiro deploy.

## 19. Riscos principais

### Vazamento entre usuários

Mitigação: autorização no backend, filtros por workspace, testes com dois
usuários e entrega controlada de arquivos.

### Duplicação entre v1 e v2

Mitigação: adaptadores e serviços compartilhados; controladores finos.

### Tarefas perdidas

Mitigação: banco relacional para o registro, Redis para a fila e worker
separado.

### Configurações impossíveis de reproduzir

Mitigação: versionar perfis e salvar a configuração resolvida na geração.

### Exposição de segredos

Mitigação: cookies seguros, hash de chaves, logs sanitizados e credenciais fora
das respostas.

### Crescimento do armazenamento

Mitigação: cotas, checksums, retenção, painel administrativo e abstração S3.

### Complexidade prematura

Mitigação: entregar por fases, manter música e publicação fora do MVP e
reutilizar o pipeline atual.

## 20. Definição de sucesso do MVP

O MVP estará pronto quando:

- o frontend novo e o Streamlit coexistirem;
- admin puder criar e administrar usuários;
- usuário puder entrar com login e senha;
- usuário puder criar vários projetos isolados;
- cada projeto tiver perfil criativo e presets próprios;
- configurações forem persistidas e versionadas;
- frontend puder gerar, acompanhar, reproduzir e baixar um vídeo;
- n8n puder gerar usando uma chave limitada e um preset salvo;
- API v1 continuar compatível;
- reiniciar a API não apagar projetos nem histórico;
- arquivos e dados não vazarem entre usuários;
- logs e auditoria permitirem diagnosticar falhas.
