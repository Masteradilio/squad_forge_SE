# Plano DeepCode — evolução do ForgeOS como Squad de Software Engineering

**Status:** implementação end-to-end concluída; benchmark integrado aceito (9/9 gates).

**Objetivo:** incorporar ao ForgeOS as nove capacidades de maior valor
observadas no DeepCode, preservando a proposta original de Squad governada,
local-first, multi-tenant e executável em Kubernetes.

**Princípio de integração:** as capacidades abaixo serão extensões do domínio,
do Harness, do Safety Kernel, do Mission Control e do sistema de evidências
existentes. O ForgeOS não adotará um segundo runtime de agentes, uma segunda
base de sessões ou acesso direto dos agentes a providers fora do OmniRoute.

## Critérios globais

Toda tarefa deve:

- possuir contrato de domínio, API/CLI quando aplicável e evidência persistida;
- preservar isolamento por `project_id` e `tenant_id`;
- não persistir API keys, tokens ou conteúdo sensível sem redaction;
- integrar-se ao Harness, ao control plane e ao Safety Kernel existentes;
- possuir testes determinísticos de unidade e integração;
- produzir eventos e artefatos rastreáveis por `session_id`, `goal_id` ou
  `turn_id` quando esses identificadores forem relevantes;
- falhar de forma explícita e segura, sem fallback silencioso para autonomia.

## Contrato transversal

```text
Project
└── EngineeringSession
    ├── EngineeringGoal (revisável)
    ├── EngineeringTurn (ordenado e imutável após admissão)
    ├── ExecutionProfile (trust + allow/ask/deny)
    ├── SkillBinding (nome, versão, digest)
    ├── ModelVerification
    ├── ReferenceDecision
    ├── AutomationRun
    └── Evidence / AuditEvent
```

Os objetos são complementares aos atuais `ChatSession`, `Run`, `TaskRun`,
`HarnessState` e `ActionApproval`. Migrações devem ser aditivas e portáveis
entre SQLite e PostgreSQL.

## Tarefas priorizadas

### P0 — continuidade e segurança de execução

#### DPC-001 — Sessions, Turns e Goals duráveis

**Status:** concluído e validado em `test_deepcode_continuity.py`.

**Objetivo:** criar uma unidade de trabalho contínua que conecte conversa,
objetivo, execução e evidências sem substituir `Run` ou `Task`.

**Implementação:**

- criar modelos `EngineeringSession`, `EngineeringTurn` e `EngineeringGoal`;
- persistir projeto, tenant, título, status, revisão, sequência, modelo,
  critérios de aceite, timestamps e resultado;
- impedir reordenação ou alteração silenciosa de Turns já admitidos;
- relacionar Turns a `Run`, `Task`, `Artifact` e `AuditEvent` quando presentes;
- oferecer endpoints para criar, listar, obter e encerrar Sessions;
- oferecer endpoints para criar/revisar Goals e registrar Turns;
- expor projeção própria para o Mission Control.

**Aceite:** uma Session sobrevive a reinício do processo, mantém a ordem dos
Turns e permite reconstruir o Goal e suas evidências por API e CLI.

**Evidência:** migração, testes de persistência, API contract tests e fixture
de sessão no benchmark.

#### DPC-002 — Loop Engineering e steering do usuário

**Status:** concluído e validado em `test_deepcode_continuity.py`.

**Objetivo:** transformar o Goal em um loop contínuo, pausável e revisável,
reutilizando o control plane e `RunContinuationPolicy` atuais.

**Implementação:**

- estados explícitos `DRAFT`, `ACTIVE`, `PAUSED`, `BLOCKED`, `COMPLETED`,
  `CANCELLED`;
- comandos de pausar, retomar, revisar objetivo e enfileirar instrução;
- limite de Turns, wall-clock, retries e quality gates;
- cada revisão gera evento/auditoria e nova versão do Goal;
- retomada nunca repete automaticamente um efeito externo já confirmado;
- integrar a decisão de continuação ao Harness e ao Safety Kernel.

**Aceite:** o benchmark pausa um Goal, altera o critério, retoma o mesmo
identificador e comprova que não duplica Turn, receipt ou ação aprovada.

**Evidência:** state-machine tests, recovery fixture, eventos ordenados e
matriz de idempotência.

#### DPC-003 — ExecutionProfile com `allow`, `ask` e `deny`

**Status:** concluído e validado em `test_deepcode_continuity.py`.

**Objetivo:** tornar as permissões compreensíveis e configuráveis por projeto,
Session e Turn sem enfraquecer a autoridade do Safety Kernel.

**Implementação:**

- trust de projeto e modos `READ_ONLY`, `ASK` e `FULL_ACCESS` explícito;
- política por ferramenta com `allow`, `ask` ou `deny`;
- congelar o perfil resolvido quando o Turn for admitido;
- transformar `ask` em `ActionApproval` e retomar a chamada suspensa;
- negar mutações protegidas mesmo que o perfil solicite `allow`;
- expor a matriz no Safety Center e na API.

**Aceite:** a mesma ferramenta produz execução, approval pendente ou negação
determinística; um perfil alterado não muda um Turn já admitido.

**Evidência:** testes negativos de permissão, approval replay, API/CLI e
snapshot do perfil congelado.

### P1 — modelos, Skills e automação operacional

#### DPC-004 — Catálogo verificável de conexões e modelos via OmniRoute

**Status:** concluído e validado em `test_deepcode_capabilities.py`.

**Objetivo:** adicionar descoberta, capabilities e probe real de modelos sem
permitir bypass do OmniRoute.

**Implementação:**

- registrar conexão sem salvar segredo, apenas referência de ambiente;
- listar modelos disponíveis e capacidades declaradas;
- executar probe mínimo de credencial/modelo com timeout e redaction;
- registrar `verified_at`, status, erro sanitizado e capabilities;
- permitir override de modelo para novos Turns da Session;
- preservar modelo e evidência dos Turns anteriores;
- negar endpoints que não pertençam ao gateway configurado.

**Aceite:** uma conexão válida fica `VERIFIED`, uma inválida fica `FAILED`
com motivo sanitizado e nenhuma rota direta externa é aceita.

**Evidência:** fake OmniRoute contract test, probe live opcional, model catalog
fixture e teste de rejeição de bypass.

#### DPC-005 — Identidade e versão de Skills por Turn

**Status:** concluído e validado em `test_deepcode_capabilities.py`.

**Objetivo:** tornar cada Skill usada em uma execução auditável e reproduzível.

**Implementação:**

- calcular digest estável do manifesto/conteúdo da Skill;
- criar `SkillBinding` imutável com nome, versão, digest, origem e Turn;
- registrar bindings no contexto e nos artefatos do Harness;
- impedir que uma atualização posterior altere bindings históricos;
- expor seleção, validação e histórico no backend/frontend;
- preservar compatibilidade com Skills built-in, project-scoped e do usuário.

**Aceite:** duas versões da mesma Skill geram bindings diferentes e uma
reexecução histórica recupera exatamente o manifesto usado.

**Evidência:** digest tests, snapshot de binding e API/UI contract tests.

#### DPC-006 — Automations sobre o runtime existente

**Status:** concluído e validado em `test_deepcode_capabilities.py`.

**Objetivo:** oferecer tarefas manuais ou recorrentes usando o mesmo Harness,
permissões, budgets, approvals e evidências.

**Implementação:**

- criar `Automation` e `AutomationRun` project-scoped;
- suportar execução manual e intervalo mínimo configurável;
- vincular Goal template, ExecutionProfile, budget e tenant;
- pausar, retomar, desabilitar e executar com idempotency key;
- impedir sobreposição do mesmo Automation;
- registrar resultado, próxima execução, falha e artefatos;
- integrar ao Scheduler existente sem criar daemon paralelo.

**Aceite:** uma Automation recorrente pode ser disparada, pausada e retomada;
execuções sobrepostas são recusadas e cada run tem evidência própria.

**Evidência:** scheduler tests, idempotency tests e API/CLI fixture.

### P2 — conhecimento, isolamento local e interoperabilidade

#### DPC-007 — Ingestão de documentos e CodeRAG orientados a referências

**Status:** concluído e validado em `test_deepcode_references.py`.

**Objetivo:** transformar documentos iniciais fornecidos pelo usuário em
contexto citável, decisões verificáveis e um produto final rastreável.

**Implementação:**

- aceitar Markdown, texto e arquivos de referência por API/CLI;
- normalizar, hashear, segmentar por seção e persistir chunks bounded;
- indexar lexicalmente sem exigir dependência externa de embeddings;
- permitir busca por projeto/tenant com score e citações de origem;
- registrar `ReferenceDecision` com query, chunks selecionados, resumo,
  decisão, Turn e artefato relacionado;
- detectar e marcar prompt injection em fontes externas;
- produzir um `ProductBlueprint`/requirements packet a partir das referências,
  sem escrever no produto gerado depois do início do benchmark;
- integrar chunks selecionados a Graphify, MemPalace e Context7 quando
  configurados, sempre mantendo a fonte original.

**Aceite:** um conjunto de documentos de entrada gera um blueprint final com
requisitos, critérios, referências e decisões; busca, citações, hash,
isolamento e bloqueio de injection são verificáveis.

**Evidência:** benchmark específico de CodeRAG, API/CLI, banco, matriz de
claims, documentos redigidos e relatório funcional.

#### DPC-008 — Isolamento de árvore de processos no Windows

**Status:** concluído e validado em `test_deepcode_process_tree.py`.

**Objetivo:** impedir processos filhos órfãos após timeout, cancelamento ou
shutdown do executor local.

**Implementação:**

- criar uma interface `ProcessTreeController` independente do sistema;
- usar Windows Job Objects ou mecanismo equivalente de grupo de processos;
- usar process groups no POSIX;
- integrar criação, timeout, cancelamento e cleanup ao sandbox local;
- registrar PID, estratégia, motivo e resultado sem salvar comandos sensíveis;
- manter fallback seguro que encerra a árvore e nunca promete isolamento
  superior ao mecanismo disponível.

**Aceite:** processo-pai e filhos são encerrados pelo controlador, timeout é
observável e ausência de mecanismo nativo produz `NOT_PROVEN`/bloqueio seguro.

**Evidência:** testes Windows e POSIX condicionais, fixture de processo filho e
relatório de capacidade.

#### DPC-009 — CLI/API compartilhando o mesmo runtime

**Status:** concluído; paridade exercitada pelo núcleo DPC e pela superfície visual, com build/teste frontend verdes.

**Objetivo:** garantir que CLI, API e Mission Control operem sobre as mesmas
Sessions, Goals, Turns, Skills, Automations e evidências.

**Implementação:**

- criar serviços de aplicação compartilhados, sem lógica duplicada em CLI/UI;
- adicionar comandos CLI para Session, Goal, profile, model verify,
  references e automation;
- garantir tenant/user context em CLI e API;
- expor eventos e artefatos com os mesmos IDs e schemas;
- testar criar pela CLI e continuar pela API, e vice-versa;
- documentar comandos headless e contratos de integração.

**Aceite:** uma Session criada por CLI é retomada por API/UI com histórico,
perfil, Goal e evidências idênticos; operações não vazam tenant.

**Evidência:** parity tests API/CLI, fixture headless e jornada Playwright.

## Ordem de implementação

1. DPC-001, DPC-002 e DPC-003: núcleo de continuidade e segurança.
2. DPC-004, DPC-005 e DPC-006: operação de modelos, Skills e automations.
3. DPC-007: referências e CodeRAG, com benchmark orientado a documentos.
4. DPC-008 e DPC-009: isolamento local e interfaces compartilhadas.
5. atualização documental, auditoria, segurança e benchmark final.

## Benchmark final — ForgeOS Reference-to-Product Continuity

O benchmark deve ser executado sem edição manual do produto gerado e deve
produzir artefatos em:

```text
.localforge/artifacts/deepcode-benchmark/run-<id>/
├── manifest.json
├── report.md
├── source_documents/
├── reference_sources.json
├── code_chunks.json
├── reference_decisions.json
├── product_blueprint.json
├── sessions.json
├── permissions.json
├── model_catalog.json
├── skills.json
├── automations.json
├── process_tree.json
├── cli_api_parity.json
└── hashes.json
```

O PRD do benchmark deve descrever uma aplicação visual de gestão de operações
de engenharia, recebendo um PRD principal, uma especificação de API, regras de
segurança e uma referência de design. O fluxo deve:

1. importar e hashear todos os documentos;
2. segmentar e buscar requisitos por consulta;
3. registrar decisão com citações e bloquear uma fonte com prompt injection;
4. gerar um Product Blueprint com módulos, entidades, telas, API e critérios;
5. criar Session, Goal e Turns e revisar o Goal durante a execução;
6. testar `allow`, `ask` e `deny` em ferramentas distintas;
7. verificar modelo via OmniRoute fake/live e registrar Skill versionada;
8. criar, pausar, retomar e deduplicar uma Automation;
9. iniciar e encerrar uma árvore de processos;
10. criar/retomar a mesma Session por CLI e API;
11. validar isolamento por tenant, hashes, auditoria e ausência de segredos;
12. emitir `ACCEPTED` somente quando todos os nove DPC gates passarem.

O relatório deve comparar o estado anterior e posterior do ForgeOS em termos de
continuidade, governança, rastreabilidade documental e capacidade de converter
entradas não estruturadas em um produto verificável.
