# PRD - PulseBoard

## Objetivo

Entregar uma pequena biblioteca Python para registrar pulsos de trabalho em um
arquivo JSON e produzir um resumo deterministico. O produto deve ser simples,
persistente e adequado a uma execucao unattended curta do ForgeOS.

## Requisitos funcionais

1. **Criar e listar pulsos**
   - `add_pulse(store, title)` cria um registro com `id`, `title`, `completed`
     igual a `False` e `created_at`.
   - `id` deve ser um inteiro positivo, estável depois de reabrir o arquivo, e
     `created_at` deve ser uma string ISO-8601 não vazia.
   - `list_pulses(store)` retorna os registros na ordem de criacao.

2. **Validar e concluir pulsos**
   - Um titulo vazio deve levantar `ValueError`.
   - `complete_pulse(store, pulse_id)` conclui somente o registro indicado.
   - Um id inexistente, inclusive um identificador não numérico, deve levantar
     `KeyError` (nunca deixar um `ValueError` de conversão escapar).
   - O estado deve permanecer correto depois de abrir o arquivo novamente.

3. **Exportar resumo**
   - `summarize(store)` retorna `total`, `completed` e `pending`.
   - O resumo deve ser deterministico e nao pode alterar o arquivo.

## Acceptance Contract

- Codigo de producao permitido: `app/pulse_board.py`.
- Testes canonicos permitidos: `tests/test_pulse_board_create.py`,
  `tests/test_pulse_board_validation.py` e `tests/test_pulse_board_summary.py`.
- A aceitacao deve importar e executar as funcoes reais do produto.
- Testes que apenas procuram strings ou duplicam o algoritmo nao sao evidencia.
- A API pode receber `str` ou `Path` para o arquivo JSON.

## Aceitacao

- As tres capacidades funcionais possuem testes executaveis independentes e evidencia de PR.
- O worktree final de release executa `python -m pytest tests -q` e passa em todas as
  capacidades acumuladas, sem depender apenas do status das tarefas anteriores.
- O scheduler gera plan, diff, test, review, risk, cost e PR artifacts.
- O control plane conclui o objetivo somente quando todas as tarefas chegam a
  `PR_READY`.
- Nao ha merge ou deploy automatico; a revisao humana permanece obrigatoria.
