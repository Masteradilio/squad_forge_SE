# PRD - Mini Checklist

## Objetivo

Entregar uma pequena lista de tarefas web, persistente e revisavel, com
contrato explicito para exercitar o ciclo de PR do ForgeOS sem depender de uma
interface visual complexa.

## Requisitos funcionais

1. **Criar e listar itens**
   - Um item possui `id`, `title`, `completed` e `created_at`.
   - O produto deve permitir criar um item e listar os itens existentes.

2. **Concluir itens com validacao**
   - Um item pode ser marcado como concluido.
   - O produto deve rejeitar um item sem titulo e preservar o estado apos
     reiniciar.

3. **Exportar um resumo JSON**
   - O produto deve exportar `total`, `completed` e `pending`.
   - Os testes devem cobrir a criacao, conclusao, rejeicao e exportacao.

## Acceptance Contract: frontend observability

Para que a aceitação exercite o produto real sem depender de nomes inventados
pelos agentes, a página `app/mini_checklist.html` deve expor estes elementos:

- `#add-form` com `#title-input` e um botão de envio;
- `#checklist`, contendo cada item como `li` com um checkbox;
- `#exportBtn`, que gera o resumo em JSON dentro de `#export-output`.

O estado deve ser persistido no `localStorage` do navegador e a exportação deve
refletir os itens atualmente exibidos.

## Aceitacao

- Todos os requisitos possuem implementacao, testes e evidencia de PR.
- O escopo e limitado a uma pequena aplicacao e seus testes.
- Nao ha merge ou deploy automatico; a revisao humana permanece obrigatoria.
