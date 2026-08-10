# Plano de ação — cobertura completa do ForgeOS

**Status:** concluído; PA-001 a PA-014 aprovados no benchmark integrado final.  
**Objetivo:** transformar as comprovações superficiais do benchmark ForgeLedger em provas operacionais reais e criar um benchmark grande, visual e executado a partir de um Pod Kubernetes.

**Estado atual:** todas as tarefas do plano estão concluídas. A comprovação final
foi executada no Docker Desktop Kubernetes com perfil aplicado, Pod executor
não privilegiado, frontend/backend live, Redis, PostgreSQL, OmniRoute, Context7,
Playwright, recuperação, segurança e carga.

## 1. Ponto de partida

O benchmark de referência atual foi aceito com 15/15 afirmações selecionadas do
README, cinco tarefas `PR_READY`, control plane concluído, oito testes de
produto/fixtures aprovados e evidências auditáveis.

Esse resultado comprova muito bem o caminho principal:

```text
PRD -> contratos -> worktrees -> Harness -> LLM -> testes -> reparo/revisão
    -> artefatos -> control plane -> PR_READY
```

O benchmark integrado final comprovou operacionalmente:

1. Context7, Redis e Helm em funcionamento com serviços reais.
2. Frontend compilado, navegador desktop/mobile e contrato live da API.
3. ForgeOS executando dentro de Kubernetes com RBAC, volumes, secrets e rede
   controlados.
4. Multi-tenancy e isolamento de dados por API e serviços.
5. Aprovações por API/CLI/UI, expiração, idempotência, identidade e auditoria.
6. Boundary de CI/PR, sinais, pausa, retomada e recuperação após
   reinício de Pod.
7. Segurança operacional, scans e desempenho sob carga controlada.
8. Pacote único, hashado e reproduzível de evidências para todos os gates.

O plano abaixo trata essas lacunas sem converter uma superfície estrutural em
uma alegação de produção antes de existir evidência correspondente.

## 2. Regras de execução futura

- Este arquivo é o plano operacional da fase de cobertura. As tarefas são
  executadas em ordem de dependência e seu estado deve ser refletido nos
  artefatos e no changelog.
- Toda implementação futura deve continuar seguindo o PRD, o backlog mestre,
  o Safety Kernel, o ActionGateway e os gates humanos existentes.
- O benchmark deve ser executado pelo ForgeOS e pelos LLMs configurados. O
  runner pode criar infraestrutura, fixtures, manifests e relatórios, mas não
  pode corrigir o produto gerado depois que o Harness começar.
- O validador independente pode ler o produto, executar testes, consultar o
  banco e observar o cluster; não pode escrever no produto gerado.
- Nenhuma aprovação `PR_READY` pode ser fabricada por um script externo.
- Toda etapa deve produzir evidência com timestamp, hash, comando, exit code,
  origem e relação com uma afirmação do README.
- Nenhum segredo, token, kubeconfig ou credencial deve ser salvo no Git.
- `PR_READY` continua significando pronto para revisão humana no modo padrão
  `human_approval`; não significa merge, deploy ou publicação automática por si
  só.
- O benchmark unattended que valida a promoção técnica local opta explicitamente
  por `LOCALFORGE_RELEASE_PROMOTION_MODE=full_access`; esse modo é um opt-in de
  execução local e não representa deploy de produção nem aceitação humana do
  produto.

### 2.1 Estado de execução

- **PA-001 — concluído:** matriz de claims README gerada e validada.
- **PA-002 — concluído:** perfil Kubernetes aplicado; Pod não privilegiado,
  RBAC, PVC, quotas, NetworkPolicy, Secrets runtime e limpeza verificados.
- **PA-003 — concluído:** probe live do Context7 e decisão de tarefa vinculada.
- **PA-004 — concluído:** Redis real, cache, Pub/Sub, locks, expiração,
  recovery e fail-closed comprovados.
- **PA-005 — concluído:** Helm lint/template, cluster live, readiness failure,
  rollback e estado final saudável comprovados.
- **PA-006 — concluído:** dependências, lint, typecheck, testes e build frontend.
- **PA-007 — concluído:** jornada Playwright live em desktop e mobile.
- **PA-008 — concluído:** isolamento multi-tenant por API e serviços.
- **PA-009 — concluído:** aprovação API/CLI/UI, expiração, replay, identidade e
  auditoria.
- **PA-010 — concluído:** reinício real de Pod, lease expirado, retomada
  idempotente, identidade do goal e receipt único.
- **PA-011 — concluído:** CI/PR assinado, ordenado e com boundary humano.
- **PA-012 — concluído:** SAST/Ruff crítico, SCA, npm audit, pip-audit, Trivy,
  runtime probe e scan de imagem sem bloqueios.
- **PA-013 — concluído:** carga pequena, média, sustentada e falha de
  dependência com resultado fail-closed.
- **PA-014 — concluído:** manifesto único `ACCEPTED` com todos os gates PASS.

### 2.2 Revalidação inicial após habilitar Kubernetes no Docker Desktop

**Executado em 2026-08-07:**

- O contexto `docker-desktop` esta ativo, com no `Ready` e Kubernetes v1.34.1.
- O chart Helm foi instalado com sucesso no namespace `forgeos` e ficou
  `STATUS: deployed`; os PVCs de PostgreSQL e Redis permaneceram `Bound`.
- O job de migracao foi corrigido para executar depois dos recursos normais,
  transportar `uv.lock`, reparar workspaces parciais e normalizar timestamps
  UTC para PostgreSQL.
- O backend e frontend passaram por probes HTTP a partir do cluster; o probe
  Redis dentro de um pod passou cache, Pub/Sub, lock sequencial e lock
  concorrente.
- O frontend passou `npm ci`, lint, typecheck, 6 testes e build; o lockfile foi
  atualizado e `npm audit --audit-level=high` retornou zero vulnerabilidades.
- A suite backend passou `596` testes, com `1` skip limitado a symlink sem
  privilegio no Windows.
- O relatorio de seguranca desta rodada esta em
  `.localforge/artifacts/reports/cycle_1/relatorio_conformidade_seguranca.md`.

As pendências registradas nessa rodada histórica foram encerradas na verificação
final abaixo. O benchmark Mission Control Studio da seção 5 continua sendo uma
especificação de produto futura, distinta do benchmark de cobertura do plano.

### 2.3 Verificação final de compliance

**Run aprovado:** `compliance-final-20260808-r2`  
**Veredito:** `ACCEPTED` — PA-001 a PA-014 em `PASS`  
**Manifesto:** `.localforge/artifacts/full-coverage/run-compliance-final-20260808-r2/manifest.json`  
**Relatório:** `.localforge/artifacts/full-coverage/run-compliance-final-20260808-r2/relatorio_conformidade_total.md`

| Tarefa | Evidência principal |
|---|---|
| PA-001 | `readme/readme_claim_matrix.json` |
| PA-002 | `kubernetes-profile-live/compliance-report.json` |
| PA-003 | `context7_probe.json` e `context7-decision/context7_decision.json` |
| PA-004 | `redis_probe.json` e `redis_recovery.json` |
| PA-005 | `helm_rollout_evidence.json` e comandos Helm/Kubernetes no manifesto |
| PA-006 | comandos frontend no manifesto |
| PA-007 | `playwright/run-manifest.json` |
| PA-008 | `tenancy/pytest.xml` |
| PA-009 | `approval/approval_compliance.json` e teste de UI |
| PA-010 | `recovery/kubernetes_recovery.json` e `recovery_compliance.json` |
| PA-011 | `ci-pr/ci_pr_compliance.json` |
| PA-012 | `security/security_audit.json` e `security/runtime_probe.json` |
| PA-013 | `load/kubernetes_load_compliance.json` |
| PA-014 | `manifest.json`, `metrics.json` e relatório Markdown |

## 3. Lista de tarefas

### P0 — fechar a linha de base e os critérios de evidência

#### PA-001 — Congelar a matriz README versus evidência

**Status:** concluído.

**Dependências:** nenhuma.

- Transformar cada afirmação operacional do README em um identificador estável
  (`README-001`, `README-002`, ...).
- Classificar cada item como `LIVE`, `STRUCTURAL`, `OPTIONAL` ou `NOT_PROVEN`.
- Associar cada item a um teste, artefato, log, métrica ou decisão humana.
- Separar claramente evidência de presença de arquivo, evidência de contrato,
  evidência de execução e evidência de produção.

**Aceite:** a matriz não possui claims sem fonte de evidência nem claims
`PASS` sustentados apenas por existência de código.

**Evidência:** `docs/e2e/full-coverage/readme_claim_matrix.json` e relatório
Markdown gerado pelo runner.

#### PA-002 — Criar o perfil de benchmark Kubernetes

**Status:** concluído.

**Dependências:** PA-001.

- Definir namespace isolado e identificador único por execução.
- Definir `ServiceAccount` e RBAC mínimo para o Pod executor.
- Definir volumes efêmeros para worktrees e volumes persistentes somente para
  artefatos que precisem sobreviver ao reinício.
- Definir Secrets e ConfigMaps injetados em runtime.
- Definir limites de CPU, memória, PIDs, tempo e egress.
- Definir política de limpeza segura do namespace ao final.

**Aceite:** o benchmark inicia em um Pod sem acesso privilegiado ao host, sem
`hostPath` amplo e sem segredo versionado.

**Evidência:** manifests renderizados, `kubectl describe`, RBAC auditado,
`NetworkPolicy`, eventos do Pod e manifesto de execução.

### P1 — transformar integrações superficiais em integrações executáveis

#### PA-003 — Context7 em modo live ou adaptador local verificável

**Status:** concluído.

**Dependências:** PA-001, PA-002.

- Configurar um endpoint Context7 real ou um adaptador local versionado que
  implemente o contrato MCP utilizado pelo ForgeOS.
- Fazer um agente consultar documentação durante uma tarefa real.
- Registrar consulta, identificador da fonte, conteúdo resumido, timestamp e
  relação com a decisão tomada.
- Testar timeout, resposta inválida, indisponibilidade e tentativa de prompt
  injection na documentação retornada.

**Aceite:** a tarefa do benchmark falha de forma auditável quando a fonte
  obrigatória está indisponível e passa somente quando a resposta consultada
  influencia uma decisão verificável.

**Evidência:** trace MCP, fixture de consulta, resposta sanitizada, artefato de
  decisão e teste negativo de indisponibilidade.

#### PA-004 — Redis real para cache, pub/sub e locks

**Status:** concluído.

**Dependências:** PA-002.

- Subir Redis dentro do namespace com autenticação, Service e NetworkPolicy.
- Exercitar cache de catálogo/estado, publicação de eventos e lock de recurso.
- Testar concorrência entre dois workers e expiração de lease.
- Testar reinício do Pod Redis e comportamento fail-closed do scheduler.
- Confirmar que estado autoritativo continua no banco/control plane, não apenas
  no cache.

**Aceite:** dois workers não executam simultaneamente o mesmo lease; eventos
  chegam ao consumidor; a perda do Redis não produz `PR_READY` falso.

**Evidência:** comandos Redis redigidos, traces de lock, eventos pub/sub,
  métricas de hit/miss, teste de concorrência e sinal de indisponibilidade.

#### PA-005 — Helm e deploy reproduzível

**Status:** concluído.

**Dependências:** PA-002, PA-004.

- Completar values para ambiente de benchmark, probes, resources, HPA,
  ServiceAccounts, Secrets, NetworkPolicies e volumes.
- Executar `helm lint` e `helm template`.
- Instalar em cluster efêmero e confirmar `Deployment`, `Service`, `Job` e
  `HPA`.
- Testar rollout interrompido, readiness failure e rollback.

**Aceite:** uma instalação limpa sobe os componentes previstos e uma falha de
  readiness impede o benchmark de declarar sucesso.

**Evidência:** chart renderizado, release Helm, eventos Kubernetes, probes,
  rollout history e relatório de rollback.

### P2 — provar frontend e jornada visual

#### PA-006 — Build e contrato real do frontend

**Status:** concluído.

**Dependências:** PA-001.

- Instalar dependências frontend de forma reproduzível.
- Executar typecheck, lint, testes unitários e build de produção.
- Servir o build dentro do Pod/Service do benchmark.
- Verificar que as telas usam estado real da API, sem mocks silenciosos.
- Cobrir estados loading, vazio, erro, bloqueado, aprovado e reconectando.

**Aceite:** o build é reprodutível, a aplicação inicia no cluster e nenhuma
  tela crítica depende de dados mockados.

**Evidência:** logs de build, hash do bundle, endpoints chamados, screenshots,
  trace de rede e resultados de testes.

#### PA-007 — E2E visual com Playwright

**Status:** concluído.

**Dependências:** PA-006, PA-005.

- Criar testes para mission control, tasks, agents, skills, memory, safety,
  review, timeline e model routing.
- Testar navegação responsiva em desktop e viewport menor.
- Testar atualização por SSE/WebSocket ou polling real.
- Testar aprovação humana, bloqueio de ação e retorno ao fluxo após aprovação.
- Capturar screenshot, vídeo, trace e console log em cada falha.

**Aceite:** a jornada completa do benchmark é executável no navegador e todos
  os estados críticos têm comportamento observável e não apenas screenshot.

**Evidência:** relatório Playwright, traces, screenshots, vídeos de falha,
  mapa de rotas e vínculo com `README-*`.

### P3 — provar governança, isolamento e recuperação

#### PA-008 — Multi-tenancy e isolamento de dados

**Status:** concluído.

**Dependências:** PA-002, banco relacional configurado.

- Criar pelo menos dois tenants e dois usuários por tenant.
- Aplicar escopo de tenant em projetos, tarefas, runs, artefatos, memória,
  skills, eventos e métricas.
- Implementar ou validar RLS/defesa equivalente no banco.
- Testar acesso cruzado por API, CLI, websocket/SSE, cache e artefatos.
- Confirmar que IDs, logs e mensagens de erro não vazam dados de outro tenant.

**Aceite:** todos os testes de isolamento cruzado falham com autorização
  adequada e nenhuma consulta sem tenant é aceita em caminho de produção.

**Evidência:** matriz de autorização, queries auditadas, testes negativos,
  logs redigidos e relatório de isolamento.

#### PA-009 — Aprovação humana e ações de alto risco

**Status:** concluído.

**Dependências:** PA-006, PA-007, PA-008.

- Criar tarefas que exigem aprovação para dependência, migração, Docker/
  Kubernetes, publicação ou alteração protegida.
- Confirmar bloqueio antes da aprovação.
- Aprovar e negar pela API, CLI e UI.
- Validar identidade do aprovador, expiração, idempotência e auditoria.
- Confirmar que o LLM não consegue autoaprovar nem alterar a política.

**Aceite:** o mesmo fluxo produz estados distintos para negar, expirar e
  aprovar; somente a aprovação válida libera a ação.

**Evidência:** approval records, eventos de auditoria, screenshots, traces,
  testes de replay e relatório de política.

#### PA-010 — Pausa, retomada, lease e reinício de Pod

**Status:** concluído.

**Dependências:** PA-004, PA-005, PA-009.

- Parar o Pod executor durante uma tarefa.
- Reiniciar o Pod e reconectar ao goal persistente.
- Expirar lease de propósito e validar recuperação idempotente.
- Enviar sinal externo de CI, provider failure e human gate.
- Confirmar que o scheduler não duplica tarefa, receipt, chamada ou artefato.

**Aceite:** após reinício, o goal mantém identidade, a frontier é retomada ou
  bloqueada de forma explícita e o resultado é reproduzível.

**Evidência:** snapshots antes/depois, hash-chain/event journal, leases,
  receipts, sinais, métricas de duplicação e relatório de recovery.

#### PA-011 — PR/CI externo simulado com boundary humano

**Status:** concluído.

**Dependências:** PA-009, PA-010.

- Usar um servidor Git/CI local ou fixture HTTP controlada.
- Criar branch e pacote de PR real.
- Enviar status de CI pass, fail e timeout.
- Confirmar que ForgeOS prepara a entrega e, no modo padrão `human_approval`,
  não faz merge automático.
- Testar webhook duplicado, assinatura inválida e resposta fora de ordem.

**Aceite:** `PR_READY` só é emitido com evidência de CI e revisão; no modo
`human_approval`, merge e deploy continuam exigindo ação humana explícita. O
modo opt-in `full_access` pode concluir a promoção técnica local após os gates,
sem representar deploy de produção.

**Evidência:** payloads redigidos, assinaturas, status checks, PR artifact,
  review packet e prova de ausência de merge automático.

### P4 — segurança, performance e observabilidade operacional

#### PA-012 — Segurança de cluster e aplicação

**Status:** concluído.

**Dependências:** PA-005, PA-008.

- Executar SAST, DAST, scan de dependências, scan de imagens e secret scan.
- Testar prompt injection em PRD, documentação, memória, skill e resposta
  Context7.
- Testar path traversal, command injection, SSRF, abuso de webhook e payload
  acima do limite.
- Validar redaction de tokens em logs, traces, artefatos e erros.
- Confirmar container non-root, filesystem restrito e egress mínimo.

**Aceite:** vulnerabilidades bloqueantes impedem `ACCEPTED`; achados aceitos
  possuem justificativa e evidence packet.

**Evidência:** relatórios SAST/DAST/SCA, scan de imagem, policy report e
  inventário de secrets.

#### PA-013 — SLO, custo e carga controlada

**Status:** concluído.

**Dependências:** PA-004, PA-005, PA-007, PA-010.

- Medir latência de API/UI, tempo de fila, duração de turn, tokens, custo,
  retries, cache, locks, banco e eventos.
- Executar carga pequena, média e sustentada dentro dos limites do cluster.
- Confirmar backpressure, quota, cancelamento e graceful shutdown.
- Testar indisponibilidade do LLM, Redis, banco e frontend.

**Aceite:** nenhum SLO definido pode ser violado silenciosamente; quota e
  custo bloqueiam o fluxo antes do gasto acima do limite.

**Evidência:** métricas Prometheus/OpenTelemetry, dashboards exportados,
  traces, relatório de custo e matriz de falhas.

#### PA-014 — Relatório único de conformidade total

**Status:** concluído.

**Dependências:** PA-001 a PA-013.

- Unificar SQLite, control plane, Kubernetes, browser, API, banco, Redis,
  traces, segurança, custo e aprovação humana.
- Gerar matriz `claim -> test -> artifact -> raw evidence -> status`.
- Proibir `PASS` quando uma fonte obrigatória estiver ausente, parcial ou
  meramente estrutural.
- Emitir `ACCEPTED`, `PARTIAL` ou `BLOCKED` com exit code coerente.

**Aceite:** um revisor consegue reproduzir cada afirmação do README sem
  consultar o histórico da conversa.

**Evidência:** `manifest.json`, `metrics.json`, `readme_claim_matrix.json`,
  relatório Markdown, pacote de hashes e diretório timestamped.

## 4. Ordem executada e encerramento da fase

1. PA-001 e PA-002: congelar claims e infraestrutura segura.
2. PA-003, PA-004 e PA-005: transformar integrações opcionais em serviços
   operacionais.
3. PA-006 e PA-007: provar frontend e jornada visual.
4. PA-008, PA-009, PA-010 e PA-011: provar governança, isolamento e recovery.
5. PA-012 e PA-013: provar segurança e operação sob carga.
6. PA-014: executar o benchmark completo e decidir o novo estado do README.

A ordem foi executada sem deixar dependência obrigatória em `BLOCKED` ou
`PARTIAL`. A fase de cobertura está encerrada com o veredito `ACCEPTED`; a
seção 5 permanece como especificação do próximo benchmark de produto.

## 5. Benchmark futuro — ForgeOS Mission Control Studio

Esta seção define um benchmark grande para ser executado somente depois que o
plano acima estiver implementado.

### 5.1 Produto de referência

Construir uma aplicação visual chamada **ForgeOS Mission Control Studio**:

- dashboard responsivo para acompanhar projetos, tasks, agents e runs;
- kanban de tarefas com dependências, leases, quota e estados;
- timeline de eventos em tempo real;
- editor visual de routing/modelos e perfis de agents;
- editor e catálogo de skills;
- painel de memória e relações Graphify;
- Safety Center com policies, approvals e kill switch;
- review center com diff, testes, risco, custo e PR packet;
- tela de integração Context7 e saúde do Redis;
- autenticação, tenants e seleção de workspace;
- estado persistente, reconexão e recuperação após reinício.

O produto deve ser uma aplicação real, sem mocks silenciosos. O PRD poderá
usar tecnologias já previstas no projeto, mas o agente deverá obedecer ao
contrato compilado pelo ForgeOS e não a alterações manuais do benchmark.

### 5.2 Escopo funcional do PRD

#### MC-001 — Workspace, tenants e autenticação

- Usuário autenticado vê somente seus tenants e projetos.
- O administrador pode criar tenant, usuário e projeto.
- O usuário comum não acessa dados de outro tenant.
- A API e a UI retornam erro auditável para acesso cruzado.

#### MC-002 — Mission control e kanban

- Criar, filtrar, ordenar e mover tasks entre `BACKLOG`, `READY`, `RUNNING`,
  `BLOCKED`, `REVIEWING` e `PR_READY`.
- Dependências impedem claim prematuro.
- Lease, quota e owner aparecem visualmente.
- Atualizações recebidas do backend aparecem sem refresh manual.

#### MC-003 — Agent Harness e agentes customizados

- Criar um agente com prompt suplementar, estratégia, retries, contexto,
  permissões e skill declarativa.
- Executar uma operação `predict` e uma operação `code_act` limitada.
- Mostrar no UI contexto utilizado, retries, spans e resultado validado.
- Recusar entrypoint ou ação não allowlisted.

#### MC-004 — Skills, Context7 e memória

- Criar e selecionar `grill-with-docs`, `to-tickets`, `tdd` e uma skill custom.
- Consultar Context7 durante uma tarefa e mostrar a fonte usada.
- Indexar arquivos no Graphify, salvar memória no MemPalace e sintetizar uma
  regra sanitizada com evidência.
- Bloquear prompt injection presente em uma fonte externa.

#### MC-005 — Safety Center e aprovação humana

- Tentar instalar dependência, alterar Kubernetes e publicar PR.
- Cada ação de alto risco deve entrar na fila de aprovação.
- Negação, expiração e aprovação devem atualizar UI, API, auditoria e goal.
- Kill switch deve impedir novos turns e cancelar o que for cancelável.

#### MC-006 — Review center e PR packet

- Exibir diff, testes, review, risco, custo, traces e changed files.
- Exigir testes e receipts antes de `PR_READY`.
- Enviar status para um CI local simulado.
- Preparar o PR packet sem executar merge.

#### MC-007 — Redis, eventos e concorrência

- Dois workers tentam a mesma task; somente um recebe o lease.
- Pub/sub atualiza a timeline.
- Cache acelera uma consulta sem substituir o banco autoritativo.
- Reinício do Redis produz sinal e recuperação segura.

#### MC-008 — Recovery e continuidade

- Pausar o goal, reiniciar o Pod ForgeOS e retomar a execução.
- Expirar lease e recuperar a task sem duplicar receipts.
- Simular timeout de LLM, falha de CI e indisponibilidade de Context7.
- Mostrar no UI o motivo e o próximo passo permitido.

#### MC-009 — Qualidade visual e acessibilidade

- Testar desktop, tablet e viewport estreito.
- Cobrir navegação por teclado, foco, contraste, labels e estados de erro.
- Capturar screenshots de cada tela principal e comparar contra baselines
  versionadas sem aceitar mudanças visuais não revisadas.
- Confirmar que a UI renderiza dados reais do ambiente Kubernetes.

#### MC-010 — Release e operação

- Buildar frontend e backend em imagens versionadas.
- Publicar Helm release no namespace isolado.
- Expor readiness/liveness, métricas, logs estruturados e traces.
- Executar scan de segurança e gerar manifesto de release.

### 5.3 Arquitetura Kubernetes do benchmark

O ForgeOS deve ser executado pelo menos no Pod `forgeos-benchmark-runner`,
responsável por importar o PRD, iniciar o run, observar o control plane e
gerar o pacote final. O ambiente completo poderá conter:

```text
Namespace forgeos-benchmark-<run-id>
├── Pod/Job forgeos-benchmark-runner
├── Deployment forgeos-mission-control-api
├── Deployment forgeos-mission-control-web
├── Deployment omniroute-gateway
├── StatefulSet postgres
├── StatefulSet redis
├── Deployment context7-adapter
├── Job playwright-e2e
└── Job security-and-conformance
```

Requisitos do ambiente:

- RBAC mínimo para o runner; nenhum acesso privilegiado ao host.
- Secrets injetados em runtime e ausentes dos manifests versionados.
- NetworkPolicy permitindo somente as comunicações necessárias.
- `PersistentVolumeClaim` para o banco e artefatos; worktree efêmero por
  task/run.
- Resource requests/limits, probes, termination grace period e HPA testável.
- OmniRoute permanece a única fronteira de inferência.
- O benchmark deve guardar o nome do namespace, imagens, digests, manifests,
  eventos e estado do cluster.

### 5.4 Harness do benchmark

O runner deve executar, nesta ordem:

1. Validar cluster, namespace, RBAC, Secrets, Services e probes.
2. Validar catálogo e probe estruturado do OmniRoute.
3. Importar este PRD pelo CLI real do ForgeOS.
4. Compilar tarefas, contratos, dependências, skills e required APIs.
5. Executar o run unattended dentro do Pod ForgeOS.
6. Injetar somente sinais externos declarados: aprovação humana de teste,
   CI pass/fail, reinício de Pod, timeout e indisponibilidade controlada.
7. Executar Playwright, API tests, DB checks, Redis checks, security scans e
   observabilidade sem alterar o produto.
8. Gerar artefatos por claim e o relatório final.

O runner não pode:

- escrever em `app/`, `frontend/`, `backend/` ou `tests/` do produto gerado;
- corrigir arquivo depois de uma falha;
- marcar task como `PR_READY`;
- aprovar ação humana;
- ignorar falha de Pod, banco, Redis, Context7, browser, CI ou segurança;
- converter um resultado `PARTIAL` em `ACCEPTED`.

### 5.5 Gates de aceitação do benchmark grande

O resultado só pode ser `ACCEPTED` quando todos os gates abaixo forem
verdadeiros:

- 10/10 tarefas do PRD e eventual tarefa de release em `PR_READY`.
- Goal do control plane `COMPLETED`, todos os todos `PASSED`, sem lease ativo.
- Produto final passa testes unitários, integração, API, frontend e Playwright.
- O validador externo confirma os comportamentos reais do produto.
- Context7 consulta uma fonte e registra a evidência.
- Redis executa cache, pub/sub e lock concorrente.
- Helm instala e atualiza o ambiente; probes e rollback passam.
- Pelo menos um restart de Pod é recuperado sem duplicação.
- Pelo menos uma ação é negada, uma expira e uma é aprovada por humano.
- Teste cross-tenant não encontra vazamento.
- SAST, DAST, dependency scan, image scan e secret scan não têm bloqueio
  aberto.
- Métricas, traces, logs e custos estão presentes para cada run.
- Screenshots, traces e testes de acessibilidade passam para todas as telas.
- Todos os model calls registrados usam OmniRoute.
- O relatório contém a matriz completa `README claim -> evidence -> status`.
- Nenhuma evidência depende de edição manual do produto gerado.

Qualquer falha obrigatória deve produzir `PARTIAL` ou `BLOCKED` com o motivo
preservado para a próxima execução. O benchmark não deve ser executado agora;
esta seção é a especificação para uma fase futura.

### 5.6 Pacote de evidências esperado

```text
docs/e2e/full-coverage/run-<timestamp>/
├── manifest.json
├── readme_claim_matrix.json
├── full_coverage_report.md
├── metrics.json
├── control_plane.json
├── events.jsonl
├── kubernetes/
├── helm/
├── playwright/
├── api/
├── database/
├── redis/
├── context7/
├── security/
├── observability/
├── screenshots/
├── traces/
└── hashes.json
```

Esse pacote será a única fonte para decidir quais afirmações podem permanecer
como `LIVE` no README, quais devem continuar como `OPTIONAL` e quais ainda
devem ser marcadas como `NOT_PROVEN`.
