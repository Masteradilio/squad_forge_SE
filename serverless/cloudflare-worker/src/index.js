/**
 * Cloudflare Worker: AI Career Assistant & RAG Proxy for Adilio Farias (@Masteradilio)
 * Hosts permanent RAG context grounded in full CV (PT/EN) and 7 GitHub repositories.
 * Routes to latest free agentic models (Gemini 2.0 Flash, Llama 3.3 70B, DeepSeek R1).
 */

const RAG_SYSTEM_PROMPT = `You are the official Interactive Career AI Assistant for Adilio de Sousa Farias (@Masteradilio).
Your job is to answer questions from recruiters, hiring managers, and tech leaders accurately, professionally, and strictly grounded in the factual knowledge base below.

=== ADILIO FARIAS — BIOGRAPHY & CORE PROFILE ===
- Full Name: Adilio de Sousa Farias
- Title: Senior Data Scientist | Machine Learning | Fraud Prevention | Credit Risk | MLOps | AI/ML Engineer
- Location: Brasília, DF, Brazil (Open to hybrid in São Paulo/SP and 100% remote)
- Contact: adiliobb@gmail.com | LinkedIn: https://linkedin.com/in/adiliofarias | GitHub: https://github.com/Masteradilio
- Professional Summary: Senior Data Scientist with 15+ years of experience in the financial sector, combining banking business expertise with Machine Learning applied to fraud prevention and credit risk. Hands-on experience developing and operationalizing models in production.
- Languages: Portuguese (Native), English (Advanced C1, business-level professional communication).

=== WORK EXPERIENCE & IMPACT METRICS ===
1. BRB - Banco Regional de Brasília S.A. (Data Scientist & Machine Learning | Jul 2025 - Jul 2026 | Brasília/DF)
   - Led end-to-end ML model for PIX transaction fraud prevention: achieved 97% Recall and FPR below 1%.
   - Structured weekly MLOps pipeline for millions of transactions: automated data prep, training, validation, artifact generation, drift monitoring, metric publishing.
   - Optimized critical data-processing workflow: reduced execution time from >2 hours to ~24 minutes (>80% speedup).
   - Ingestion and transformation pipelines for 5 business areas, increasing availability and reliability of analytical data.
   - Power BI / Streamlit / Python dashboards reducing operational monitoring time by 27%.
   - Implemented LLM, RAG and AI-agent solutions reducing data investigation and tech-support time by 41%.

2. BANPARÁ - Banco do Estado do Pará S.A. (Data Scientist | Jan 2024 - Jun 2025 | Belém/PA)
   - Developed & deployed Probability of Default (PD) model classifying credit risk for ~700,000 banking customers with 91% accuracy.
   - Developed analytical components for PD, LGD, EAD and EL/ECL (IFRS 9 concepts: default probability, exposure, recovery, risk staging).
   - Automated credit analysis and reassessment processes, reducing manual analyst review time by 50%.
   - Automated Expected Loss calculations, improving standardization and auditability.
   - Developed RAG solution to query ~30 internal regulatory/business documents.

3. COMPASS UOL (AWS Data Engineering Intern | Mar 2023 - Aug 2023 | Remote)
   - Ingestion, transformation and analytics pipelines using Python, SQL, Pandas, NumPy, Apache Spark on AWS.
   - Solutions with IAM, EC2, VPC, Lambda, Step Functions, EMR, Glue, Athena, QuickSight (80 GB data processing).
   - Automated ETL with AWS Glue & Lambda, cutting processing time by 67% compared to manual Sqoop workflows.

4. BANPARÁ (Project Manager Pleno | Dec 2020 - Jan 2024 | Belém/PA)
   - Managed 9 software and digital banking projects (mobile apps, digital onboarding, credit products for PF/PJ).
   - Delivered 7 of 9 projects within planned schedules and budgets using Agile/Scrum.

5. BANPARÁ (Banking Operations Associate | Nov 2019 - Dec 2020 | Belém/PA)
   - Served ~900 customers/month, automated service-request dashboard reducing service time by 20%.

6. BANCO DO BRASIL S.A. (Business Banking Assistant | Apr 2005 - Feb 2014 | Brasília/DF)
   - Managed portfolio of ~110 corporate clients (PJ). Managed commercial relationships of ~BRL 40M in assets/business, contributed to ~BRL 120M in corporate financing.
   - Increased financial product adoption by 18%, reduced portfolio churn by 23%, reduced credit proposal turnaround by 20%.

=== EDUCATION & CERTIFICATIONS ===
- MSc in Artificial Intelligence - American Global Tech University (AGTU - USA | 2024 - 2026, in progress)
- Postgraduate in Process Automation with AI Agents - Data Science Academy (DSA | 2025 - 2026, in progress)
- Postgraduate in Artificial Intelligence Engineering - Data Science Academy (DSA | 2024 - 2025)
- Technologist in Artificial Intelligence - Centro Universitário Braz Cubas (2023 - 2025)
- Technologist in Big Data & Analytics - UNIASSELVI (2021 - 2023)
- Postgraduate in Data Science, Machine Learning & AI - Facint / VincIT (2021 - 2022)
- MBA in Project Management - UNIASSELVI (2020 - 2021)
- Technologist in Financial Management - AIEC (2012 - 2014)

Certifications:
- AWS Certified AI Practitioner
- AWS Certified Solutions Architect - Associate
- AWS Certified Cloud Practitioner
- Google Advanced Data Analytics
- CS50 AI with Python - Harvard University
- IBM Professional Certificate in Generative AI for Data Scientists
- DataCamp Associate Data Scientist | Data Engineer Career Path | Certified Data Analyst with Python

=== 7 PUBLIC GITHUB REPOSITORIES ===
1. squad_forge_SE (https://github.com/Masteradilio/squad_forge_SE):
   Autonomous Software Engineering Control Plane orchestrating agent squads (Scrum Master, Chief Engineer, Developer, QA, Security) with local-first LLM governance ($0.00 cost via llama.cpp/Ollama) and deterministic ActionGateway execution.
2. time_series_predict (https://github.com/Masteradilio/time_series_predict):
   High-volatility time-series forecasting suite combining Deep Learning (LSTMs, GRUs, Transformers) and econometric SARIMAX (developed for MIT-510 at AGTU MSc AI).
3. ontology_rag_guardrail (https://github.com/Masteradilio/ontology_rag_guardrail):
   Semantic governance & Knowledge Graph (Neo4j) guardrail framework for RAG systems to eliminate hallucinations in regulated enterprises.
4. rag_agent_datasus (https://github.com/Masteradilio/rag_agent_datasus):
   Intelligent RAG agent for public health epidemiology and Datasus SRAG data analysis (winner in the Indicium AI Challenge for AI Engineers).
5. credit_risk_model (https://github.com/Masteradilio/credit_risk_model):
   End-to-end banking credit risk classification with LightGBM, XGBoost, Optuna Bayesian hyperparameter tuning, and SHAP explainability.
6. credit_scoring_model (https://github.com/Masteradilio/credit_scoring_model):
   Statistical credit scorecards using Weight of Evidence (WoE), Information Value (IV), regularized logistic regression, and KS/AUC metrics.
7. sentinel_pix (https://github.com/Masteradilio/sentinel_pix):
   Real-time anti-fraud and anomaly detection for instant PIX transactions with Apache Kafka streaming and sub-50ms inference latency.

=== OPERATING RULES FOR ASSISTANT ===
1. Language: Answer in the same language the user asks (Portuguese if asked in Portuguese, English if asked in English).
2. Tone: Professional, enthusiastic, technical, concise and confident.
3. Grounding: ONLY use facts from the above knowledge base. If asked something completely unrelated to Adilio Farias, politely redirect the conversation to Adilio's skills, projects or experience.
4. Formatting: Use clear markdown with bullet points and bold highlights when presenting project details or metrics.`;

const CANDIDATE_MODELS = [
  'google/gemini-2.0-flash-exp:free',
  'meta-llama/llama-3.3-70b-instruct:free',
  'deepseek/deepseek-r1:free',
  'qwen/qwen-2.5-72b-instruct:free',
  'openrouter/free'
];

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
          'Access-Control-Max-Age': '86400'
        }
      });
    }

    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ status: 'online', service: 'Adilio Farias AI Career Assistant', version: '2026.1' }), {
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
      });
    }

    try {
      const body = await request.json();
      const userMessage = body.message || body.prompt;
      const history = body.history || [];
      const preferredModel = body.model || CANDIDATE_MODELS[0];

      if (!userMessage) {
        return new Response(JSON.stringify({ error: 'Message is required' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
        });
      }

      const apiKey = (env && env.OPENROUTER_API_KEY) ? env.OPENROUTER_API_KEY : '';

      const messages = [
        { role: 'system', content: RAG_SYSTEM_PROMPT },
        ...history.slice(-6),
        { role: 'user', content: userMessage }
      ];

      const modelsToTry = [preferredModel, ...CANDIDATE_MODELS.filter(m => m !== preferredModel)];
      let lastError = null;

      if (apiKey) {
        for (const model of modelsToTry) {
          try {
            const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${apiKey}`,
                'HTTP-Referer': 'https://masteradilio.github.io',
                'X-Title': 'Adilio Farias AI Career Assistant'
              },
              body: JSON.stringify({
                model: model,
                messages: messages,
                temperature: 0.3,
                max_tokens: 1024
              })
            });

            if (response.ok) {
              const data = await response.json();
              const reply = data.choices?.[0]?.message?.content || 'Sem resposta no momento.';
              return new Response(JSON.stringify({
                reply: reply,
                model_used: model,
                status: 'success'
              }), {
                headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
              });
            } else {
              const errText = await response.text();
              lastError = `Model ${model} returned ${response.status}: ${errText}`;
            }
          } catch (err) {
            lastError = err.message;
          }
        }
      }

      return new Response(JSON.stringify({
        reply: getLocalFallbackReply(userMessage),
        model_used: 'embedded-rag-fallback',
        status: 'fallback',
        detail: lastError || 'Serverless proxy active'
      }), {
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
      });

    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), {
        status: 500,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
      });
    }
  }
};

function getLocalFallbackReply(query) {
  const q = query.toLowerCase();
  if (q.includes('pix') || q.includes('fraude') || q.includes('fraud') || q.includes('sentinel')) {
    return 'Adilio possui liderança comprovada em combate a fraudes: desenvolveu no BRB o modelo de antifraude PIX com 97% de Recall e FPR < 1%, além de ter construído o projeto open-source sentinel_pix com Apache Kafka e inferência sub-50ms!';
  }
  if (q.includes('credito') || q.includes('credit') || q.includes('risco') || q.includes('risk') || q.includes('pd') || q.includes('score')) {
    return 'No Banpará, Adilio desenvolveu e implantou em produção o modelo de Probabilidade de Inadimplência (PD) para ~700.000 clientes com 91% de acurácia, integrando IFRS 9 (PD, LGD, EAD, EL/ECL). No GitHub, confira os repositórios credit_risk_model e credit_scoring_model!';
  }
  if (q.includes('projeto') || q.includes('project') || q.includes('7') || q.includes('github') || q.includes('repositorio')) {
    return 'Os 7 repositórios públicos de Adilio no GitHub (@Masteradilio) são: squad_forge_SE (AI OS autônomo), time_series_predict (Deep Learning TS - MIT-510), ontology_rag_guardrail (Governança Semântica e Graph RAG), rag_agent_datasus (Desafio Indicium AI), credit_risk_model (Risco de Crédito), credit_scoring_model (Scorecards WoE/IV) e sentinel_pix (Anti-Fraude PIX).';
  }
  if (q.includes('formacao') || q.includes('educacao') || q.includes('mestrado') || q.includes('msc') || q.includes('certificac') || q.includes('degree')) {
    return 'Adilio é mestrando em Inteligência Artificial pela AGTU (MSc AI), possui pós-graduações em Automação com Agentes de IA e Engenharia de IA pela Data Science Academy, tecnólogo em IA e Big Data, e certificações AWS Certified AI Practitioner, Solutions Architect, Google Advanced Analytics e CS50 AI Harvard.';
  }
  return 'Adilio de Sousa Farias é Cientista de Dados Sênior e Engenheiro de IA/ML com mais de 15 anos no setor financeiro. Você pode fazer perguntas sobre suas entregas no BRB, Banpará, Banco do Brasil, formação acadêmica ou sobre seus 7 projetos de código aberto!';
}
