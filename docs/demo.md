# LocalForge OS — Guia de Demonstração de Fluxo de Trabalho (E2E Demo)

Este guia demonstra como executar e auditar um ciclo de desenvolvimento de software completo (ponta a ponta) utilizando a interface de linha de comando (CLI) do LocalForge OS.

---

## Ciclo de Vida do Desenvolvimento: Importar, Planejar e Executar

Siga os passos a seguir em uma pasta de projeto de teste limpa, como a fornecida
em `samples/demo-lf-smoke-prd/`:

### 1. Inicializar o Workspace
Inicializa a estrutura interna do LocalForge no diretório atual (criando a pasta `.localforge/` contendo bancos de dados, políticas e caches):
```bash
localforge init
```

### 2. Importar o PRD (Product Requirement Document)
Importa o arquivo de requisitos do produto em Markdown, dividindo-o em tarefas e épicos estruturados no backlog:
```bash
localforge import-prd PRD.md
```
Após a importação, as tarefas recém-criadas estarão no estado `BACKLOG` ou `PLANNING` aguardando a sua revisão e aprovação.

### 3. Visualizar e Aprovar o Planejamento (Plan)
Visualize as tarefas e planos de implementação gerados e pendentes de aprovação:
```bash
localforge plan
```
Para aprovar todas as tarefas e colocá-las em estado de execução (`READY`), utilize a flag de aprovação em lote:
```bash
localforge plan --approve-all
```
Você também pode aprovar tarefas de forma individual fornecendo a chave correspondente:
```bash
localforge plan --approve LF-1001
```

### 4. Executar a Pipeline de Agentes (Run)
Dispare a execução autônoma das tarefas aprovadas. A flag `--unattended` faz com que o pipeline de agentes (Planner, Coder, Tester, Reviewer) execute o ciclo completo, compile códigos, execute testes locais, e finalize sem solicitar permissões de alteração interativas no terminal:
```bash
localforge run --unattended
```
Durante o processo, você acompanhará na tela o status da execução e a conclusão de cada tarefa em tempo real.

### 5. Verificar os Resultados e Pull Requests Propostas
Liste as Pull Requests locais que foram geradas para cada uma das tarefas concluídas com sucesso:
```bash
localforge prs
```
Isso exibirá a tabela com os links diretos para os patches `.patch` de código e o arquivo Markdown final de proposta de PR (`pr.md`) contendo sumário, alterações, riscos avaliados e evidências de testes executados com sucesso.
