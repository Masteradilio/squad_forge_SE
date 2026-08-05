# PRD - Tiny Ledger

## Objetivo

Entregar uma pequena biblioteca Python para registrar valores de tarefas e
produzir um resumo determinístico. O produto deve ser simples, testável e
adequado para uma execução unattended curta do ForgeOS.

## Requisitos funcionais

1. **Criar e listar lançamentos**
   - `add_entry(store, label, amount)` cria um lançamento com `id`, `label`,
     `amount` e `status` igual a `pending`.
   - `list_entries(store)` retorna os lançamentos na ordem de criação.

2. **Validar e liquidar lançamentos**
   - Um label vazio deve ser rejeitado com `ValueError`.
   - `settle_entry(store, entry_id)` muda apenas o lançamento indicado para
     `settled` e retorna o lançamento atualizado.
   - Liquidar um id inexistente deve levantar `KeyError`.

3. **Exportar resumo**
   - `summarize(store)` retorna um dicionário com `total`, `settled` e
     `pending`, contando lançamentos e somando os valores.
   - O resultado precisa ser determinístico e não pode alterar o store.

## Critérios de aceitação e contrato

- Código de produção permitido: `app/tiny_ledger.py`.
- Teste canônico permitido: `tests/test_tiny_ledger.py`.
- A aceitação deve importar e executar as funções reais do produto; cópias do
  algoritmo dentro do teste não são evidência válida.
- Não são necessários frameworks web, serviços externos ou banco de dados.

## Aceitação

- As três capacidades funcionais possuem testes executáveis.
- O scheduler gera evidências de implementação, testes, review, risco, custo e
  PR para cada tarefa.
- O run só é aceito quando todas as tarefas chegam a `PR_READY` e o control
  plane chega a `COMPLETED`.
