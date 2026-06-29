# PRD — Pomodoro Tracker

## Objetivo
Fornecer um gerenciador de timer Pomodoro simplificado, com máquina de estados determinística para o timer, regras de pausa longa estritas (Regra de Ouro) e visualização visual em página HTML de controle.

## Requisitos Funcionais

1. **Gestão de Sessões de Pomodoro**:
   - Criar, registrar, listar e deletar sessões concluídas no backend.
   - Cada sessão possui: `id`, `session_type` (`work`, `short_break`, `long_break`), `duration_minutes`, `completed_at`.

2. **Máquina de Estados do Timer**:
   - Permitir transições válidas de status do timer: `idle` -> `work`, `work` -> `short_break` ou `long_break`, e pausas retornando para `work` ou `idle`.
   - Bloquear transições proibidas (ex: `idle` direto para break, ou transições para o mesmo estado ativo).

3. **Regra de Ouro do Pomodoro**:
   - Impor que após 4 sessões de `work` consecutivas concluídas no banco de dados, a próxima pausa deve ser obrigatoriamente `long_break`.
   - Rejeitar com erro ou exceção qualquer tentativa de iniciar um `short_break` caso a regra exija `long_break`.

4. **Persistência e Relatórios**:
   - Persistir de forma duradoura as sessões de Pomodoro em banco de dados SQLite.
   - Exportar relatório resumido das sessões concluídas em formato JSON contendo o total por tipo.

5. **Interface Pomodoro View**:
   - Fornecer uma página frontend visual contendo o timer dinâmico regressivo, botões de ação (Start, Pause, Reset, Skip) e a listagem do histórico de sessões do dia.

## Critérios de Aceitação
- Tentativas de transições proibidas da máquina de estados do timer resultam em erro.
- A regra de ouro de 4 sessões de trabalho consecutivas obriga a pausa longa de forma estrita.
- A exportação JSON gera o resumo das estatísticas de sessões de Pomodoro corretas.
