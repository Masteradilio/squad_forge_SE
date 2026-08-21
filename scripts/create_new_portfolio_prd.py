# -*- coding: utf-8 -*-
import pathlib

prd_content = """# PRD — Portfólio Profissional Bilíngue de Adilio Farias (Senior Data Scientist & AI/ML Engineer)

## 1. Visão Geral e Identidade

O **Portfólio Profissional Bilíngue de Adilio Farias** é uma aplicação web executiva, moderna, ultra-responsiva e com suporte nativo a dois idiomas (**Português PT-BR** e **English EN**). O objetivo primordial é apresentar a trajetória sênior, as competências arquiteturais e os **7 projetos de código aberto de alto impacto** desenvolvidos por **Adilio Farias (Masteradilio)**.

- **Perfil**: Cientista de Dados Sênior & Engenheiro de Inteligência Artificial / Machine Learning (AI Engineer).
- **Foco Técnico**: Generative AI, Enterprise RAG, Graph RAG, MLOps, Modelagem Preditiva em Séries Temporais, Detecção de Fraudes em Tempo Real e Engenharia de Software Autônoma.
- **GitHub**: https://github.com/Masteradilio
- **LinkedIn**: https://www.linkedin.com/in/adiliofarias
- **Localização**: Brasília, DF - Brasil.

---

## 2. Destaque Especial: Criação 100% Autônoma pelo Squad Forge SE

O site deve declarar e demonstrar explicitamente em uma seção dedicada como foi concebido, arquitetado, codificado, testado e empacotado 100% de forma autônoma pelo **Squad Forge SE** utilizando um modelo local (`llama.cpp` com `qwen3.8-27b` / `Qwen 2.5 Coder 27B`) a um custo de API de **$0.00 USD**.

### Passo a Passo do Ciclo Autônomo do Squad Forge SE:
1. **Fase 1 — Decomposição do PRD & Gestão de Backlog (Scrum Master)**:
   O Scrum Master autônomo analisou este PRD, mapeou as dependências de componentes, calculou a complexidade ciclomática e estruturou os tickets de desenvolvimento em um grafo de tarefas determinístico.
2. **Fase 2 — Definição e Congelamento de Contratos de Interface (Chief Engineer)**:
   O Chief Engineer congelou as interfaces TypeScript/HTML, contratos de i18n (dicionários bilíngues PT/EN), restrições de responsividade TailwindCSS e as regras de segurança semântica do DOM.
3. **Fase 3 — Implementação Local-First sem Custo de Nuvem (Developer)**:
   O Developer implementou cada módulo com apoio exclusivo do modelo local `qwen3.8-27b` executando no servidor `llama.cpp` local (`http://localhost:8080/v1`), consumindo 0 tokens de APIs pagas comerciais.
4. **Fase 4 — Bateria de Testes Automatizados & Validação de Aceite (QA Engineer)**:
   O QA Engineer gerou e executou testes determinísticos de regressão comportamental (`pytest` / `Vitest`), verificando a integridade dos 7 links de projetos, troca instantânea de idiomas e renderização em viewports móveis.
5. **Fase 5 — Auditoria de Segurança, Sanitização & Proteção de Segredos (Security Auditor)**:
   Varredura rigorosa SAST/DAST garantindo ausência total de injeção de script (XSS), validação estrita de inputs e verificação de zero vazamento de credenciais ou chaves sensíveis.
6. **Fase 6 — Compilação do Release & Publicação da Árvore Limpa (PR Writer & Release)**:
   Consolidação do pacote de produção em HTML/CSS/JS autocontido com documentação no `CHANGELOG.md` e geração de evidências imutáveis no repositório.

---

## 3. Catálogo dos 7 Projetos Públicos em Destaque

Cada projeto deve ser apresentado em um card rico, responsivo, com tags tecnológicas, contexto do problema, arquitetura da solução, métricas de impacto e link direto para o repositório público:

1. **Squad Forge SE (Control Plane de Engenharia de Software Autônoma)**
   - *URL*: https://github.com/Masteradilio/squad_forge_SE
   - *Categoria*: Autonomous AI Software Engineering & LLMOps
   - *Problema*: Orquestração de agentes de IA para engenharia de software frequentemente sofre com alucinações, dependência de APIs em nuvem caras e falta de governança de código.
   - *Solução*: Plataforma open-source com arquitetura multi-agente especializada (Scrum Master, Chief Engineer, Dev, QA, Security), suporte local-first (llama.cpp/Ollama), isolamento de worktrees Git e ActionGateway com tolerância zero a falhas.
   - *Stack*: Python, FastAPI, Docker, React, TypeScript, llama.cpp, SQLite, Git Worktrees.

2. **Time Series Predict MIT-510 (Mestrado em IA AGTU)**
   - *URL*: https://github.com/Masteradilio/time_series_predict
   - *Categoria*: Deep Learning & Time Series Forecasting
   - *Problema*: Previsão acurada de séries temporais não-lineares, com sazonalidade complexa e alta volatilidade em cenários industriais e financeiros.
   - *Solução*: Suíte completa de modelagem comparativa combinando Deep Learning (LSTMs, GRUs, Transformers/Informer) e modelos econométricos clássicos (SARIMAX, Auto-ARIMA) desenvolvida para a pós-graduação stricto sensu.
   - *Stack*: Python, PyTorch, Statsmodels, SciPy, Pandas, Matplotlib, Jupyter.

3. **Ontology RAG Guardrail (Governança Semântica para LLMs Corporativos)**
   - *URL*: https://github.com/Masteradilio/ontology_rag_guardrail
   - *Categoria*: Generative AI, Knowledge Graphs & Security
   - *Problema*: Alucinações de modelos de linguagem e violações de regras de compliance em ambientes corporativos regulados.
   - *Solução*: Framework de segurança semântica que une Grafos de Conhecimento (Neo4j) e Ontologias OWL/RDF como guardrail determinístico pré e pós-inferência para sistemas RAG.
   - *Stack*: Python, LangChain, Neo4j (Graph RAG), Pydantic, RDFlib, Vector Databases.

4. **RAG Agente Datasus (Vigilância Epidemiológica & Inteligência em Saúde)**
   - *URL*: https://github.com/Masteradilio/rag_agent_datasus
   - *Categoria*: Generative AI, Health Tech & Public Data Science
   - *Problema*: Extração de insights críticos a partir de volumosas e heterogêneas bases públicas de Síndrome Respiratória Aguda Grave (SRAG) do Ministério da Saúde.
   - *Solução*: Agente inteligente RAG premiado no Desafio Indicium AI capaz de interpretar relatórios epidemiológicos, cruzar dados tabulares e responder perguntas médicas com citação exata de fontes.
   - *Stack*: Python, LlamaIndex, ChromaDB, FastAPI, Streamlit, Pandas.

5. **Credit Risk Model (Esteira de Risco de Crédito Bancário End-to-End)**
   - *URL*: https://github.com/Masteradilio/credit_risk_model
   - *Categoria*: FinTech, Credit Risk & MLOps
   - *Problema*: Mitigação de inadimplência e tomada de decisão de concessão de crédito sob exigências de interpretabilidade regulatória (Banco Central).
   - *Solução*: Pipeline de Machine Learning de ponta a ponta com LightGBM e XGBoost, otimização Bayesiana de hiperparâmetros com Optuna e explicabilidade de decisão via valores SHAP.
   - *Stack*: Python, LightGBM, XGBoost, Optuna, SHAP, Scikit-Learn, MLflow.

6. **Credit Scoring Model (Modelagem Estatística & Scoring Financeiro)**
   - *URL*: https://github.com/Masteradilio/credit_scoring_model
   - *Categoria*: FinTech, Statistical Modeling & Scorecards
   - *Problema*: Construção de scorecards de crédito calibrados com métricas robustas de discriminação (KS, Gini, AUC-ROC) e estabilidade temporal (PSI).
   - *Solução*: Sistema de cálculo de scorecards de crédito com Weight of Evidence (WoE), Information Value (IV), regressão logística regularizada e esteira de calibração de probabilidades de default.
   - *Stack*: Python, Scikit-Learn, Statsmodels, Category Encoders, Pandas, NumPy.

7. **Sentinel PIX (Detecção de Fraudes em Tempo Real em Transações Instantâneas)**
   - *URL*: https://github.com/Masteradilio/sentinel_pix
   - *Categoria*: FinTech, Anti-Fraud & Real-Time Stream Processing
   - *Problema*: Detecção de golpes, transações atípicas e contas laranjas em fluxos de PIX com SLAs ultra-rigorosos de latência de autorização.
   - *Solução*: Arquitetura de processamento em streaming (Apache Kafka) com esteira de inferência de Machine Learning assíncrona operando com latência sub-50ms e alta taxa de throughput.
   - *Stack*: Python, Scikit-Learn, XGBoost, Apache Kafka, FastAPI, Redis, Docker.

---

## 4. Requisitos de Interface, Responsividade & Internacionalização (i18n)

1. **Seletor de Idiomas (PT-BR / EN)**:
   - Localizado no topo direito da barra de navegação.
   - Alternância fluida e instantânea de todos os textos da aplicação sem recarregar a página (via JavaScript com dicionário bilíngue reativo).
   - Persistência da preferência do usuário via `localStorage`.

2. **Total Responsividade Móvel**:
   - Layout fluido (Mobile-First) testado para telas de 320px a 4K.
   - Menu hambúrguer deslizante para smartphones e tablets.
   - Grid de cards adaptativo: 1 coluna em mobile, 2 em tablets e 3 em desktops grandes.
   - Tipografia responsiva (`clamp` e classes Tailwind `sm:`, `md:`, `lg:`).

3. **Matriz de Competências Técnicas**:
   - 4 pilares: *IA Generativa & LLMs*, *Data Science & Machine Learning*, *Engenharia & MLOps*, *Governança & Arquitetura*.

4. **Assistente Virtual Bilíngue (Interactive Career AI Assistant)**:
   - Chat interativo com respostas inteligentes em português e inglês para perguntas sobre a carreira, mestrado e projetos de Adilio.

5. **Formulário de Contato & Footer**:
   - Validação de campos de e-mail e mensagem em tempo real.
   - Botão para cópia rápida do e-mail institucional/pessoal (`adiliobb@gmail.com`).
   - Links verificados para GitHub e LinkedIn.
"""

p = pathlib.Path("samples/e2e-portfolio-masteradilio/PRD.md")
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(prd_content, encoding="utf-8")
print("New PRD written successfully at", p.resolve())
