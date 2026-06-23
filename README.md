# LocalForge OS — Local-First Autonomous Software Engineering OS

O **LocalForge OS** é um sistema operacional de engenharia de software autônomo e focado em privacidade (local-first). Ele é projetado para transformar requisitos brutos descritos em um arquivo `PRD.md` (Product Requirement Document) em tarefas de engenharia testáveis, instanciar agentes de IA locais especializados (Planner, Coder, Tester, Reviewer), executar código e testes dentro de sandboxes isolados, aplicar autocorreção de bugs (self-healing) e estruturar propostas de Pull Requests prontas para revisão humana.

> [!IMPORTANT]
> **Privacidade Garantida**: O LocalForge OS foi construído para rodar 100% offline. Ele não possui dependências em tempo de execução com agentes de nuvem ou serviços externos proprietários, assegurando total proteção à propriedade intelectual do seu código fonte.

---

## 🛠️ Guia Rápido de Instalação e Setup

O desenvolvimento do LocalForge OS é simplificado através de um utilitário central unificado em Python, compatível com Windows, macOS e Linux.

### Pré-requisitos
- **Python 3.11 ou 3.12+**
- **Node.js LTS**
- **Git**

### Passo 1: Configuração do Backend
Execute o script de setup para criar o ambiente virtual, instalar as dependências necessárias e inicializar a pasta de workspace do LocalForge:
- **Windows (PowerShell)**:
  ```powershell
  ./scripts/setup_backend.ps1
  ```
- **Linux / macOS / Git Bash**:
  ```bash
  ./scripts/setup_backend.sh
  ```

### Passo 2: Configuração do Frontend (Painel Visual)
Instale as dependências da aplicação React SPA:
- **Windows (PowerShell)**:
  ```powershell
  ./scripts/setup_frontend.ps1
  ```
- **Linux / macOS / Git Bash**:
  ```bash
  ./scripts/setup_frontend.sh
  ```

---

## 🚀 Executando o LocalForge OS

### 1. Iniciar o Servidor de API (Backend)
Inicia o servidor local FastAPI na porta `8000`:
```bash
# Via scripts de atalho
./scripts/run_backend.sh  # ou .ps1 no Windows

# Alternativa direta via utilitário Python
python manage.py run-backend
```

### 2. Iniciar o Painel de Controle Visual (Frontend)
Inicia o servidor de desenvolvimento React Vite:
```bash
# Via scripts de atalho
./scripts/run_frontend.sh  # ou .ps1 no Windows

# Alternativa direta via utilitário Python
python manage.py run-frontend
```
Abra o navegador em `http://localhost:5173` para acompanhar execuções de agentes em tempo real, gerenciar o backlog e auditar solicitações de segurança do kernel.

### 3. Executar Testes e Linting
```bash
# Executar a suíte de testes unitários e de integração
python manage.py run-tests

# Executar análises estáticas (Ruff no backend, Eslint no frontend)
python manage.py lint
```

---

## 🤖 Configurando Modelos de Linguagem Locais

O LocalForge OS utiliza o **Ollama** para rodar modelos de inteligência artificial de forma local e privada.

1. **Instale o Ollama**: Baixe e instale em [ollama.com](https://ollama.com).
2. **Baixe o Modelo Recomendado**: Recomendamos o uso de modelos da família `Qwen` especializados em código para as tarefas de programação:
   ```bash
   ollama run qwen2.5-coder:7b
   ```
3. **Mapeamento de Perfis**: Configure seus modelos preferidos no painel de controle (aba **Models**) ou ajustando o arquivo de configuração gerado em `.localforge/config.yaml`.

---

## 🛡️ Modelo de Segurança e Execução Autônoma

Para permitir execuções de longa duração de forma autônoma sem riscos ao sistema hospedeiro, o LocalForge OS implementa um **Safety Kernel** rígido:

1. **Filesystem Lock & Isolation**: Quando uma tarefa do backlog é executada por um agente, todas as operações de escrita são restritas à pasta de `worktree` isolada daquela tarefa. Escritas no repositório principal ou em arquivos protegidos (como `.env`) são bloqueadas.
2. **Command AST Validation**: Subprocessos executados pelos agentes passam por um analisador sintático (AST) que bloqueia encadeamentos de shell (como `&&`, `;`, `|`) e comandos destrutivos (como `rm -rf`).
3. **Sandboxing (Docker / Local)**: É possível rodar os comandos em contêineres Docker isolados ou em worktrees com fallback seguro para execução local.
4. **Orçamento de Recursos (Budgets)**: Caso um agente consuma muitas chamadas LLM, altere arquivos demais, crie um diff gigante ou ultrapasse o tempo limite configurado da tarefa, a execução é abortada de forma segura para o estado `FAILED_SAFE`.

> [!WARNING]
> **Aviso de Execução Autônoma (Unattended Mode)**: Certifique-se de configurar limites de budget realistas em `.localforge/config.yaml` sob a seção `budgets` para evitar custos excessivos de chamadas e consumo excessivo de recursos do host durante execuções automáticas de longa duração.

---

## 📂 Projeto de Amostra (Sample Project)

Fornecemos um projeto de demonstração pré-configurado na pasta `samples/demo-project/`.
Este subdiretório simula um repositório real contendo:
- Um arquivo `PRD.md` especificando uma nova funcionalidade simples (Health-check API).
- Um repositório Git local inicializado.

Você pode usá-lo para testar a pipeline de ponta a ponta e observar a geração automática de tarefas e propostas de Pull Requests prontas para envio.

---

## ❓ Resolução de Problemas
Para problemas relacionados a Ollama indisponível, Docker inativo, erros de arquivos modificados ou chaves do GitHub, consulte o guia completo de [Resolução de Problemas (Troubleshooting)](file:///E:/Projetos/local_forge_os/docs/TROUBLESHOOTING.md).
