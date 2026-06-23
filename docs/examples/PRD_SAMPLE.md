# PRD — LocalForge Version API Endpoint

## Objetivo
Expor uma nova rota pública de API (`/version`) que retorne a versão atual estável do LocalForge OS. Isso ajuda scripts e ferramentas CLI locais a detectarem a compatibilidade com a API.

## Requisitos Funcionais
1. Expor endpoint `GET /version` público.
2. O retorno deve ser em formato JSON com a seguinte estrutura:
   - `version`: a versão estrita do software (ex: `"0.1.0"`).
   - `build_date`: data e hora do build em formato ISO 8601.
3. Adicionar teste de integração para validar se o endpoint retorna status 200 e o payload JSON correto.

## Critérios de Aceitação
- Chamar `GET /version` na API retorna código HTTP 200 e payload JSON contendo a versão.
