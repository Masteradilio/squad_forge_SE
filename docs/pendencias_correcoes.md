# Pendências, correções e melhorias antes do próximo benchmark HP 12C

**Data:** 2026-08-15
**Escopo:** preparação do ForgeOS para uma nova execução autônoma da HP 12C Platinum
**Regra:** não repetir o benchmark completo enquanto os bloqueadores P0 deste documento não estiverem concluídos.

## 1. Diagnóstico executivo

As duas execuções longas relatadas pelo Product Owner consumiram aproximadamente
25 horas e 17 horas. A primeira terminou com um produto de baixa qualidade; a
segunda não entregou o produto final. O problema não foi apenas a capacidade
do modelo. O Harness ainda permite que falhas de contrato, provider, banco,
visual, testes e release se acumulem até transformar uma Run em
BLOCKED_NEEDS_HUMAN_REVIEW.

Os artefatos versionados confirmam diferentes manifestações do mesmo problema:

- uma Run parou com 18 de 19 tarefas em PR_READY e a tarefa de integração falhou
  no teste de segurança/visual pós-merge;
- outra falhou em TVM com dois testes quebrados após sete ciclos de recuperação;
- as tentativas mais recentes pararam já na primeira tarefa visual porque o
  Chief Engineer não produziu um plano, esgotou timeouts de reparo ou recebeu um
  teste sem arquivo canônico materializado;
- também houve erro de database locked durante heartbeat de task_run;
- uma execução chegou a COMPLETED, mas isso não substitui a comprovação
  independente de fidelidade visual, 40 teclas, 10 funções complexas e produto
  utilizável no navegador.

Evidências de referência:

- benchmarks/workspaces/hp12c-full-access-20260810T021439Z/run_summary.md;
- benchmarks/workspaces/hp12c-full-access-20260810T015618Z/run_summary.md;
- benchmarks/workspaces/hp12c-full-access-20260811T083408Z/run_summary.md;
- benchmarks/workspaces/hp12c-full-access-20260811T090410Z/run_summary.md;
- scripts/run_hp12c_cloud_acceptance.py;
- scripts/fixtures/hp12c_post_merge_challenge.py;
- samples/e2e-hp12c-platinum/docs/PRD.md.

## 2. Critério de bloqueio do próximo benchmark

O próximo benchmark HP 12C só deve ser liberado quando todas as tarefas P0
abaixo tiverem implementação e teste. Uma execução curta de um PRD genérico
deve provar a infraestrutura antes da execução visual grande.

O resultado final aceitável é:

1. PRD recebido e persistido de forma idempotente;
2. backlog criado com contratos executáveis, dependências justificadas e
   matriz visual quando aplicável;
3. todas as tarefas implementadas, verificadas e em PR_READY;
4. em full_access, todas as PR_READY mergeadas em uma main limpa;
5. Security Auditor executado sobre o produto mergeado;
6. Tester/E2E Product Acceptance executado pela interface externa do produto;
7. qualquer falha devolvida à tarefa correta, corrigida e revalidada;
8. produto final entregue com relatório, traces completos e status COMPLETED;
9. nenhuma intervenção manual de outro LLM durante a Run.

## 3. Backlog de correção priorizado

### P0 — Autonomia e recuperação da Run

- [ ] **P0.1 — Tornar o ciclo de falha determinístico.**
  Implementar uma máquina de estados explícita para
  failure -> classify -> repair_handoff -> bounded_repair -> requeue ->
  retest -> PR_READY e para a falha pós-merge
  Security/Tester -> correction -> merge -> revalidate. Nenhum caminho pode
  terminar em BLOCKED_NEEDS_HUMAN_REVIEW apenas porque uma chamada não retornou
  plano.

  **Aceite:** cada falha possui classe, causa, tarefa de origem, tentativa,
  próximo responsável, deadline e evidência persistida. O teste deve simular
  falha de provider, teste quebrado, visual mismatch, conflito de merge e
  database locked, comprovando retomada automática ou bloqueio rápido e
  explicado.

- [ ] **P0.2 — Separar falha recuperável de falha fatal.**
  Centralizar a classificação para provider timeout, resposta inválida,
  ausência de arquivo, teste ausente, teste falho, mismatch visual, erro de
  segurança, conflito Git, lock SQLite, falta de credencial e política de
  segurança. Cada classe deve ter uma estratégia própria; não reutilizar uma
  mensagem genérica de 'Chief action missing'.

  **Aceite:** o mesmo erro repetido não dispara o mesmo reparo indefinidamente;
  a Run usa cooldown, limite global e limite por tarefa e produz diagnóstico
  acionável antes de escalar.

- [ ] **P0.3 — Garantir que full_access não pare na primeira falha.**
  O modo full_access deve automatizar somente decisões autorizadas, mas precisa
  continuar o loop de reparo até o orçamento finito. Human review deve ser
  reservado para orçamento esgotado, risco de segurança não resolvido,
  conflito irrecuperável ou ausência total de provider.

  **Aceite:** um teste injeta uma falha transitória na tarefa 1 e termina todas
  as tarefas sem intervenção; um teste injeta uma falha permanente e termina
  rapidamente com o motivo correto, sem consumir horas.

### P0 — Chief Engineer, providers e orçamento

- [ ] **P0.4 — Corrigir o contrato estruturado do Chief Engineer.**
  O caminho visual retornou 'no plan' e 'no Chief Engineer action applied'.
  Tornar o envelope de resposta obrigatório, validá-lo antes de aplicar ações e
  transformar resposta vazia, JSON truncado, markdown indevido ou tool call
  incompleto em uma falha recuperável com contexto preservado.

  **Aceite:** há testes para plano válido, plano vazio, JSON inválido,
  timeout, resposta truncada e ação fora do contrato. Nenhum caso perde o
  diagnóstico original.

- [ ] **P0.5 — Concluir a cadeia de provider sem loops silenciosos.**
  Implementar preflight, timeout por chamada, timeout total da Run, circuit
  breaker, retry com backoff, fallback e registro de cada decisão. A cadeia
  deve distinguir erro transitório de 401, billing, modelo inexistente,
  contexto excedido e contrato incompatível.

  **Aceite:** uma matriz de testes cobre OmniRoute, Ollama ausente, provider
  free, NVIDIA, OpenRouter pago e todos os erros de configuração. A Run nunca
  fica aguardando uma chamada além do orçamento.

- [ ] **P0.6 — Não confundir API paga com garantia de entrega.**
  O Harness deve registrar modelo, rota, latência, custo, tokens, tentativa,
  resultado semântico e artefato gerado. O pagamento só habilita uma tentativa;
  não aprova código, visual ou release.

  **Aceite:** o relatório mostra por que cada modelo foi usado e por que o
  fallback ocorreu. Uma falha de modelo pago continua entrando no reparo
  interno, sem intervenção externa.

### P0 — Heartbeat, SQLite e retomada

- [ ] **P0.7 — Corrigir o lock de heartbeat do SQLite na origem.**
  O log registra 'database is locked' ao atualizar task_runs. Revisar
  transações concorrentes, duração de sessão, WAL, busy timeout, retry
  transacional e isolamento entre scheduler, heartbeat, tracer e reparo.

  **Aceite:** teste concorrente reproduz o lock em Windows e comprova que o
  heartbeat faz retry limitado sem perder estado, duplicar tarefa ou mudar
  status indevidamente.

- [ ] **P0.8 — Implementar watchdog de progresso.**
  Persistir last_progress_at, fase, tentativa e processo responsável. O
  watchdog deve detectar task sem progresso, heartbeat atrasado, subprocesso
  morto e provider pendurado, cancelar somente o lease vencido e devolver a
  tarefa à fila correta.

  **Aceite:** matar o worker, pausar a rede e interromper um subprocesso não
  deixa a Run viva indefinidamente; após reinício, o Harness retoma exatamente
  do estado persistido.

- [ ] **P0.9 — Tornar transições idempotentes.**
  Repetir importação do PRD, heartbeat, repair handoff, requeue, merge,
  aprovação, evento SSE e finalização da Run não pode criar duplicatas ou
  regressões de estado.

  **Aceite:** cada operação recebe uma chave idempotente e testes repetem a
  operação após timeout, restart e resposta duplicada.

### P0 — PRD, backlog e contratos executáveis

- [ ] **P0.10 — Evitar serialização artificial do backlog.**
  As execuções HP12C mostram 19 tarefas com dependências que podem ampliar
  drasticamente o tempo. O Scrum Master deve criar dependências somente quando
  houver evidência no PRD ou no contrato; tarefas independentes devem executar
  em paralelo dentro dos limites de recursos.

  **Aceite:** o planner explica cada dependência, calcula o caminho crítico e
  um teste confirma que tarefas independentes não ficam bloqueadas por uma
  tarefa visual ou de release.

- [ ] **P0.11 — Materializar o contrato de teste antes do worker.**
  Resolver o conflito entre canonical test command, fixture externa e
  'visual task has no materialized canonical test file'. O backlog deve gerar
  ou copiar o teste canônico para o worktree autorizado, validar o caminho e
  executar no mesmo ambiente que o agente usará.

  **Aceite:** nenhum task_run começa sem teste/cenário materializado, comando
  executável, diretório de trabalho, arquivos permitidos e critério de saída.

- [ ] **P0.12 — Preservar requisitos no contrato, não só no prompt.**
  O contrato deve carregar comportamento, interface, dados, acessibilidade,
  arquivos permitidos, comandos, riscos, artefatos e critérios de aceite. Para
  qualquer PRD visual, a matriz deve ser genérica e conter elementos, linhas,
  colunas, labels, cores, locators, ações e evidências esperadas.

  **Aceite:** um teste com um PRD visual genérico, sem mencionar HP12C, produz
  matriz executável e backlog verificável.

### P0 — Execução, worktree, testes e release

- [ ] **P0.13 — Alinhar diretório de execução e diretório de teste.**
  Garantir que agente, teste, screenshot, servidor frontend e relatório usem o
  mesmo worktree/commit correto. Evitar que o teste veja fixture, módulo
  auxiliar ou produto de uma execução anterior.

  **Aceite:** o trace registra cwd, commit, worktree, branch, hash dos arquivos
  e comando completo para cada teste. Um teste de adulteração comprova que um
  artefato fora do worktree não é considerado produto.

- [ ] **P0.14 — Proibir PR_READY sem evidência independente.**
  PR_READY exige diff, teste canônico aprovado, teste independente, contrato
  verificado, risco, segurança, screenshot quando visual, custo e resumo de
  reparos. Um teste gerado pelo próprio agente não pode ser a única prova.

  **Aceite:** remover uma evidência faz a tarefa voltar a REVIEWING/REPAIRING,
  nunca permanecer em PR_READY.

- [ ] **P0.15 — Corrigir a montagem final e o retorno da falha.**
  A falha em LF-PRD-019 mostrou que o release assembly pode concentrar o
  problema depois de 18 tarefas prontas. O Harness deve identificar o arquivo,
  tarefa e gate que falharam e devolver a correção à origem; não criar um
  task final genérico que absorva todos os defeitos.

  **Aceite:** falha de integração, segurança e visual retorna às tarefas
  responsáveis, reexecuta os gates e só permite merge quando o conjunto estiver
  consistente.

- [ ] **P0.16 — Tornar merge e pós-merge atomicamente observáveis.**
  Full access deve confirmar target limpo, merge de todas as PR_READY, commit
  resultante, execução do Security Auditor, execução do Tester e artefatos de
  release. Falha em qualquer etapa deve preservar a main anterior e o estado
  de reparo.

  **Aceite:** não existe status COMPLETED sem commit final, relatório de
  Security, relatório de Tester e prova de produto acessível.

### P0 — QA funcional, visual e segurança

- [ ] **P0.17 — Fazer o Tester operar pela interface externa.**
  O Tester deve usar Playwright/browser ou equivalente contra o produto
  compilado/servido, e não apenas importar módulos, chamar API ou executar
  fixture interna. Deve verificar navegação, estado, erros, persistência,
  responsividade e fluxos reais.

  **Aceite:** o teste falha quando a API funciona, mas a interface não renderiza
  ou não possui interação utilizável.

- [ ] **P0.18 — Transformar o E2E Tester em Product Acceptance/Visual QA.**
  Além dos fluxos funcionais, comparar screenshot, proporções, regiões,
  tipografia, labels, locators, acessibilidade e matriz visual. A avaliação
  deve usar tolerâncias configuráveis e produzir evidência lado a lado,
  diferenças e causa provável.

  **Aceite:** produto visualmente diferente, mesmo com testes unitários verdes,
  não passa no gate final.

- [ ] **P0.19 — Garantir a cobertura funcional da HP12C sem hardcode no Harness.**
  O benchmark deve fornecer os vetores e o desafio das 10 funções
  complexas — TVM, NPV, IRR, AMORT, SL, SOYD, DB, PRICE, YTM e DATE — como
  dados/fixtures do benchmark. O Tester deve acioná-las pela UI e conferir
  valores, arredondamento, modo RPN, registros e estados.

  **Aceite:** os dez fluxos passam de forma independente e o relatório indica
  qual tecla/ação, entrada, saída e screenshot foram usados.

- [ ] **P0.20 — Separar Security Auditor de Product Acceptance.**
  Security deve auditar dependências, segredos, comandos, rede, XSS, headers,
  permissões, arquivos e superfície visual insegura. O Tester deve julgar
  comportamento e aderência ao PRD. Nenhum dos dois deve validar o próprio
  trabalho sem evidência independente.

  **Aceite:** cada agente produz relatório próprio, com status, evidências,
  severidade, correção sugerida e retorno de tarefa quando necessário.

### P1 — Observabilidade e rastreabilidade

- [ ] **P1.1 — Gravar um trace completo e não truncado.**
  Unificar PRD, hash, backlog, contratos, chamadas LLM, fallback, tool calls,
  arquivos, comandos, stdout/stderr, testes, repairs, eventos, merges,
  Security, Tester, custos e tempos sob um único run_id. Diagnósticos
  comprimidos devem apontar para o log completo preservado.

- [ ] **P1.2 — Criar um painel de stalled/recovery.**
  O frontend deve mostrar fase atual, último progresso, tentativa, motivo,
  próximo agente, tempo consumido e caminho de retorno. Não basta mostrar
  BLOCKED; o usuário deve saber se o Harness está reparando, aguardando provider
  ou realmente esgotado.

- [ ] **P1.3 — Validar o novo workspace do frontend.**
  Corrigir o lint global ainda pendente em
  frontend/src/components/ForgeContinuityView.tsx e adicionar teste de contrato
  para os endpoints de tasks, eventos persistidos, traces e chat. O pipeline
  visual deve consumir eventos persistidos e SSE sem perder evidências.

- [ ] **P1.4 — Manter a generalidade do produto.**
  Prompts, skills, planner, gates, papéis e estados não podem conter lógica
  específica da HP12C. Tudo específico deve ficar em
  samples/e2e-hp12c-platinum, scripts/fixtures ou no PRD/artefato do benchmark.

### P1 — Infraestrutura local

- [ ] **P1.5 — Tornar o preflight de infraestrutura explícito.**
  Antes da Run, verificar Docker, imagem sandbox, Kubernetes/contexto, Redis,
  Helm, portas, volumes, health endpoints e permissões. Helm é uma ferramenta
  de provisionamento, não um servidor; o check deve distinguir CLI disponível,
  chart renderizado e release aplicado.

- [ ] **P1.6 — Subir dependências no contexto correto ou desabilitá-las
  explicitamente.**
  Redis deve ter deployment/service/healthcheck e portas configuradas no
  namespace da Run. Se uma integração opcional não for necessária, o Harness
  deve marcá-la como OPTIONAL e não bloquear a Run; se for requisito do perfil,
  deve falhar no preflight em minutos.

  **Aceite:** nenhum serviço ausente fica sendo tentado silenciosamente por
  horas e nenhum componente obrigatório é considerado saudável só porque a CLI
  existe.

## 4. Testes obrigatórios antes da HP12C

- [ ] Unitários: estados, contratos, idempotência, fallback, circuit breaker,
  classificação de falhas, visual matrix e merge policy.
- [ ] Integração: SQLite sob concorrência, heartbeat, restart, watchdog,
  Redis, sandbox e persistência de eventos.
- [ ] Harness fake: provider determinístico que devolve sucesso, timeout,
  resposta inválida, resposta truncada, erro 429 e falha semântica.
- [ ] PRD pequeno não visual: receber, decompor, implementar, corrigir,
  mergear e testar sem intervenção.
- [ ] PRD pequeno visual genérico: produzir matriz, screenshot, teste externo,
  reparo visual e release.
- [ ] Smoke de full_access: todas as PR_READY mergeiam e Security/Tester
  rodam na ordem correta.
- [ ] Chaos/recovery: matar processo, bloquear SQLite, interromper provider,
  remover arquivo de teste, causar conflito Git e quebrar um gate pós-merge.
- [ ] Frontend: build, lint global, unitários e Playwright contra produto
  compilado com backend saudável.

## 5. Ordem recomendada de implementação

1. P0.1–P0.9: ciclo de vida, provider, heartbeat, watchdog e idempotência.
2. P0.10–P0.16: contratos, worktrees, PR_READY, merge e release.
3. P0.17–P0.20: Tester, visual QA, Security e evidências independentes.
4. P1.1–P1.6: trace, painel, frontend e infraestrutura.
5. Executar os testes obrigatórios com providers fake.
6. Executar um benchmark genérico pequeno.
7. Só então repetir o benchmark HP12C em full_access.

## 6. Definition of Done para liberar a próxima Run HP12C

O plano não está concluído se existir qualquer um dos itens abaixo:

- uma falha transitória que consome a Run inteira;
- uma resposta vazia do Chief Engineer que não entra no reparo;
- uma tarefa em execução sem heartbeat ou sem último progresso;
- database locked sem retry determinístico;
- teste canônico que não existe no worktree;
- PR_READY sem evidência independente;
- Tester usando somente API, módulo ou fixture isolada;
- visual gate sem matriz, screenshot comparável ou locator executável;
- Security e Tester sem relatórios separados;
- full_access que não prova merge, commit final e pós-merge;
- trace truncado que impede descobrir a causa;
- dependência obrigatória ausente detectada somente depois de iniciar a Run.

Quando todos os itens estiverem verdes, registrar no CHANGELOG os comandos,
resultados, commit e evidências antes de iniciar uma nova execução HP12C.
