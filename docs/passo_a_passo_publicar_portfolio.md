# Guia Completo: Portfólio Bilíngue Autônomo & Assistente de Carreira com RAG

Este documento detalha o resumo executivo, a arquitetura técnica e o passo a passo para publicação e manutenção do portfólio bilíngue de **Adilio de Sousa Farias (@Masteradilio)**, projetado e compilado de forma 100% autônoma pelo **Squad Forge SE**.

---

## 1. Resumo Executivo do Projeto

O portfólio foi concebido para atender tanto o mercado brasileiro quanto recrutadores e contratantes internacionais, apresentando uma trajetória sênior em Ciência de Dados, Engenharia de Inteligência Artificial, MLOps, Prevenção a Fraudes e Modelagem de Risco de Crédito.

### Principais Entregas:
1. **Página Única Bilíngue Responsiva (SPA)**:
   - Seletor de idiomas no canto superior direito (**PT-BR** e **English**) com internacionalização instantânea de 100% dos textos sem recarregar a página.
   - Grid responsivo (TailwindCSS) com filtros de categorias: *Generative AI & RAG*, *Machine Learning & Time Series*, *FinTech, Risk & Anti-Fraud*.
   - Design moderno no estilo Dark Mode, com tipografia limpa, efeitos de vidro (Glassmorphism) e badges de telemetria.

2. **Apresentação Aprofundada dos 7 Repositórios Públicos do GitHub**:
   - `squad_forge_SE`: Control plane open-source de engenharia de software autônoma com orquestração multi-agente.
   - `time_series_predict`: Suíte de séries temporais não-lineares com Deep Learning (LSTMs/Transformers) e SARIMAX (MIT-510 no Mestrado em IA AGTU).
   - `ontology_rag_guardrail`: Governança semântica e Graph RAG (Neo4j) contra alucinações de LLMs corporativos.
   - `rag_agent_datasus`: Agente RAG epidemiológico do Datasus (premiado no Desafio Indicium AI para Engenheiro de IA).
   - `credit_risk_model`: Pipeline end-to-end de risco de crédito com LightGBM/XGBoost, Optuna e SHAP.
   - `credit_scoring_model`: Scorecards estatísticos com Weight of Evidence (WoE), Information Value (IV) e calibração KS.
   - `sentinel_pix`: Detecção de fraudes PIX em tempo real com Apache Kafka e inferência sub-50ms.

3. **Seção de Transparência do Squad Forge SE**:
   - Detalhamento passo a passo de como o Squad Forge SE concebeu o site a partir do PRD utilizando modelo local (`llama.cpp` / `qwen3.8-27b`) com **custo de nuvem de $0.00 USD**.

4. **Assistente Interativo de Carreira com RAG Permanente**:
   - Chat com histórico conversacional, animação de processamento, botões de perguntas rápidas e badge de status do modelo.
   - Base de conhecimento estritamente aterrada (*grounded*) nos 2 currículos completos (Português e Inglês) e nos 7 repositórios.
   - Conexão assíncrona com backend serverless e fallback determinístico local para **100% de disponibilidade** (zero downtime).

5. **Currículos em Formato para Impressão e Download**:
   - `assets/cv_adilio_farias_pt.html`: Currículo formatado para impressão direta em PDF (botão no topo).
   - `assets/cv_adilio_farias_en.html`: Resume em Inglês formatado para impressão em PDF.
   - `assets/cv_adilio_farias_pt.txt` e `assets/cv_adilio_farias_en.txt`: Versões em texto simples.
   - Links de download no Hero, na seção Sobre Mim e dentro do assistente.

---

## 2. Arquitetura do Sistema

```mermaid
flowchart TD
    User["Recrutador / Visitante"] -->|Acessa URL| Site["https://masteradilio.github.io"]
    
    subgraph Frontend["Frontend Estático (GitHub Pages)"]
        SPA["index.html (SPA Bilíngue)"]
        CV_Assets["assets/ (HTML imprimível e TXT)"]
    end
    
    Site --> SPA
    SPA --> CV_Assets
    
    subgraph Backend["Backend Serverless (Cloudflare Worker / Vercel Edge)"]
        Proxy["worker/src/index.js (CORS + RAG Context)"]
        Cascade{"Cascata de Modelos Gratuitos"}
        M1["1. google/gemini-2.0-flash-exp:free"]
        M2["2. meta-llama/llama-3.3-70b-instruct:free"]
        M3["3. deepseek/deepseek-r1:free"]
        M4["4. openrouter/free"]
        Fallback["5. Fallback Determinístico Local"]
    end
    
    SPA -.->|POST / (Pergunta do Usuário)| Proxy
    Proxy --> Cascade
    Cascade --> M1
    Cascade --> M2
    Cascade --> M3
    Cascade --> M4
    Cascade --> Fallback
```

---

## 3. Passo a Passo para Publicar no GitHub Pages (`https://masteradilio.github.io`)

Como você possui o repositório de domínio próprio `Masteradilio/masteradilio.github.io`, o GitHub Pages publica diretamente a branch `main` sem necessidade de configurações adicionais.

### Etapa 1: Gerar os Arquivos Finais (Local)
No repositório `local_forge_os`, execute o comando:
```bash
py -3.11 scripts/generate_bilingual_portfolio.py
```
Isso compilará e criará automaticamente a pasta pronta:
`dist/masteradilio.github.io/`

### Etapa 2: Copiar os Arquivos para o Repositório do Domínio
Copie o conteúdo da pasta `dist/masteradilio.github.io/` para a raiz do seu repositório `Masteradilio/masteradilio.github.io`:
- `index.html`
- Pasta `assets/` (contendo `cv_adilio_farias_pt.html`, `cv_adilio_farias_en.html`, `cv_adilio_farias_pt.txt`, `cv_adilio_farias_en.txt`)

### Etapa 3: Commit e Push
Abra o terminal na pasta do seu repositório `masteradilio.github.io` e execute:
```bash
git add .
git commit -m "feat: publicar portfolio bilingue com assistente RAG e curriculos para download"
git push origin main
```

### Etapa 4: Testar o Acesso
Em até 1 a 2 minutos após o push, acesse:
👉 **`https://masteradilio.github.io`**

---

## 4. Passo a Passo para Publicar o Cloudflare Worker (Opcional para chamada do LLM em tempo real)

O frontend funciona perfeitamente mesmo sem o Cloudflare Worker ativo graças ao fallback determinístico embutido. No entanto, para permitir que o assistente gere respostas criativas e dinâmicas utilizando os modelos Gemini 2.0 Flash / Llama 3.3 70B:

### Opção A: Publicação Rápida via Painel Web da Cloudflare (Sem instalar ferramentas)
1. Acesse o painel da Cloudflare: [dash.cloudflare.com](https://dash.cloudflare.com)
2. No menu lateral esquerdo, clique em **Compute (Workers) > Workers & Pages**.
3. Clique no botão **Create application** (ou **Create Worker**).
4. Dê um nome ao worker (exemplo: `adilio-career-assistant`) e clique em **Deploy**.
5. Clique em **Edit code** (ou **Quick Edit**).
6. Abra o arquivo local [`serverless/cloudflare-worker/src/index.js`](../serverless/cloudflare-worker/src/index.js), copie todo o seu conteúdo, cole no editor da Cloudflare e clique em **Save and deploy**.
7. Volte à página do Worker, vá na aba **Settings > Variables and Secrets** e adicione:
   - **Variable name**: `OPENROUTER_API_KEY`
   - **Value**: Sua chave de API da OpenRouter (gratuita).
   - Clique em **Save and deploy**.

### Opção B: Publicação via Terminal (Wrangler CLI)
Na pasta `serverless/cloudflare-worker/`:
```bash
cd serverless/cloudflare-worker
npm install
npx wrangler login
npx wrangler secret put OPENROUTER_API_KEY
npx wrangler deploy
```

---

## 5. Como Testar e Validar Localmente

Para rodar a bateria de testes automatizados e checagens de segurança:

1. **Testes de Aceite do Portfólio (pytest)**:
   ```bash
   py -3.11 -m pytest scripts/fixtures/portfolio_acceptance.py -v
   ```
2. **Testes de Configuração do Core & 4-Tier Ladder**:
   ```bash
   py -3.11 -m pytest backend/tests/test_core_config.py -v
   ```
3. **Auditoria de Conformidade e Segurança (SAST/Secrets)**:
   ```bash
   py -3.11 scripts/check_security_scans.py
   py -3.11 scripts/check_release_truth.py
   ```

---

## 6. Estrutura dos Arquivos Criados

| Arquivo / Diretório | Função |
|---|---|
| `samples/e2e-portfolio-masteradilio/index.html` | Cópia de referência da SPA bilíngue do portfólio |
| `samples/e2e-portfolio-masteradilio/assets/` | Pasta contendo os currículos em HTML (imprimível) e TXT |
| `dist/masteradilio.github.io/` | Pacote compilado para cópia direta para o repositório do GitHub Pages |
| `serverless/cloudflare-worker/src/index.js` | Código do microsserviço com prompt RAG permanente e cascata de modelos |
| `serverless/cloudflare-worker/wrangler.toml` | Configuração de deploy do Cloudflare Worker |
| `serverless/vercel-edge/api/chat.js` | Endpoint alternativo para deploy na Vercel Edge |
| `scripts/generate_bilingual_portfolio.py` | Script gerador autônomo da aplicação SPA bilíngue |
| `scripts/build_full_portfolio_and_assets.py` | Script auxiliar de geração dos assets e worker |
| `scripts/fixtures/portfolio_acceptance.py` | Suíte de testes de regressão e aceite determinístico |
| `docs/passo_a_passo_publicar_portfolio.md` | Este guia de referência completo |
