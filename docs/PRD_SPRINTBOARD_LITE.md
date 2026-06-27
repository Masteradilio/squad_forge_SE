# PRD — SprintBoard Lite

## Objetivo
Fornecer um gerenciador de tarefas Kanban simplificado, permitindo a criação, alteração de status por máquina de estados e persistência de itens de trabalho (work items).

## Requisitos Funcionais

1. **Gestão de Itens de Trabalho**:
   - Criar, editar, listar e deletar itens.
   - Cada item possui: `id`, `title`, `description`, `status` (`backlog`, `in_progress`, `review`, `done`), `priority` (`low`, `medium`, `high`), `created_at`, `updated_at`.

2. **Máquina de Estados Determinística**:
   - Transições válidas de status:
     - `backlog` -> `in_progress`
     - `in_progress` -> `review`
     - `review` -> `done` ou `in_progress`
   - Transições proibidas:
     - `done` não pode retornar a `backlog` ou qualquer outro estado inicial.
     - Itens excluídos (deletados) não podem ter transições de status.
     - Itens com título vazio (`""`) são inválidos e devem ser rejeitados na criação/edição.

3. **Filtros e Exportação**:
   - Filtrar itens no board por status e prioridade.
   - Exportar o board completo em formato JSON.

4. **Frontend View**:
   - Fornecer uma visualização em formato de 4 colunas representando cada status do fluxo de trabalho.

5. **Engenharia e Validação**:
   - Implementar testes no backend cobrindo regras de negócio, CRUD e máquina de estados.
   - Fornecer comandos de validação automatizados e PRs contendo o relatório de custos de benchmark.

## Critérios de Aceitação
- Títulos vazios resultam em erro de validação.
- Transições de estados ilegais (ex: `done` -> `backlog`) são bloqueadas com exceção/erro.
- A exportação JSON gera um array contendo todos os campos dos itens ativos.
