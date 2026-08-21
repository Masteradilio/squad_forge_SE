# Adilio Farias — AI Career Assistant (Cloudflare Worker & RAG Proxy)

Este microsserviço serverless atua como o cérebro do Assistente Interativo de Carreira do portfólio de Adilio Farias (https://masteradilio.github.io).

## Principais Funcionalidades
1. **RAG Permanente e Imutável**: O prompt do sistema incorpora a totalidade da trajetória de Adilio (BRB antifraude PIX com 97% Recall, BANPARÁ modelo de crédito com 91% acurácia e IFRS 9, Compass UOL, Banco do Brasil, Mestrado em IA na AGTU, certificações AWS/Google/Harvard) e os 7 repositórios do GitHub.
2. **Roteamento de Modelos Gratuitos de Última Geração (2025/2026)**:
   - google/gemini-2.0-flash-exp:free (Primário)
   - meta-llama/llama-3.3-70b-instruct:free (Fallback 1)
   - deepseek/deepseek-r1:free (Fallback 2)
   - openrouter/free (Fallback 3)
3. **Fallback Determinístico Local**: Se as APIs externas atingirem rate-limit temporário ou indisponibilidade, o proxy responde deterministicamente com os fatos consolidados da base de conhecimento com zero tempo de inatividade (100% uptime).

## Como Publicar no Cloudflare Workers (Gratuito - 100.000 requisições/dia)

### Opção 1: Via Linha de Comando (Wrangler CLI)
1. Instale o Wrangler se ainda não tiver:
   `ash
   npm install -g wrangler
   `
2. Faça login na sua conta Cloudflare:
   `ash
   wrangler login
   `
3. Defina a chave da OpenRouter (gratuita):
   `ash
   wrangler secret put OPENROUTER_API_KEY
   `
4. Faça o deploy:
   `ash
   wrangler deploy
   `

### Opção 2: Direto pelo Painel Web da Cloudflare (Sem instalar nada)
1. Acesse [dash.cloudflare.com](https://dash.cloudflare.com) -> **Compute (Workers)** -> **Create Application** -> **Create Worker**.
2. Cole o conteúdo de src/index.js no editor web e clique em **Deploy**.
3. Vá em **Settings** -> **Variables and Secrets** -> **Add Variable**:
   - Name: OPENROUTER_API_KEY
   - Value: <sua_chave_openrouter> (ou deixe em branco para usar o RAG determinístico embutido).
4. Copie a URL do seu worker (ex: https://adilio-career-assistant.adiliobb.workers.dev) e, se desejar customizar, defina window.CAREER_BOT_BACKEND_URL no seu HTML.
