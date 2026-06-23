# LocalForge OS — Planejamento de Backlog Futuro (v0.2)

Este documento descreve as propostas e prioridades de evolução técnica planejadas para o ciclo de desenvolvimento **v0.2** do LocalForge OS.

---

## 1. Extensões de IDE (VS Code & Cursor)
**Objetivo**: Integrar o assistente de desenvolvimento diretamente no fluxo diário do programador.
- **Painel Lateral Nativo**: Exibir o status de tarefas do backlog, aprovações pendentes de segurança e andamento dos runs diretamente na barra lateral do editor.
- **Aprovação Inline**: Botões sobre as linhas de código ou notificações nativas da IDE para aprovar ou rejeitar comandos do Safety Kernel com apenas um clique.
- **Criação de Tarefas sob Cursor**: Permitir selecionar um trecho de código de pitfall ou blocker no editor e criar um Fact de Memory correspondente instantaneamente.

---

## 2. Empacotamento Desktop (Tauri ou Electron)
**Objetivo**: Transformar o LocalForge OS em um aplicativo local nativo de instalação simples.
- **Tauri Application**: Usar Rust e Tauri para envolver o frontend React e instanciar o backend local em Python de forma otimizada.
- **Distribuição Multiplataforma**: Instaladores `.msi` para Windows, `.dmg` para macOS e `.deb`/`.rpm` para Linux.
- **Tray Icon**: Ícone na bandeja do sistema indicando o status do daemon e permitindo parar/pausar todas as execuções autônomas imediatamente (Emergency Kill Switch).

---

## 3. Habilidades Avançadas de Agentes (Advanced Skills)
**Objetivo**: Habilitar a resolução de problemas mais complexos pelos agentes.
- **Interactive Debugging Skill**: Habilidade de inspecionar variáveis em tempo de execução ao receber exceções, inserindo breakpoints dinâmicos para isolar a causa raiz dos bugs de teste.
- **UI Component Visual Testing**: Habilidade de capturar screenshots de componentes web dentro de sandboxes e comparar layouts visuais via algoritmos de regressão visual para garantir fidelidade às especificações de design.
- **Performance Profiling Skill**: Gerar gráficos de consumo de CPU/Memória pós-papel do agente para evitar introdução de gargalos de performance.

---

## 4. Benchmark de Modelos Locais (Model Benchmark Harness)
**Objetivo**: Identificar quais modelos de linguagem locais atendem melhor aos diferentes papéis do pipeline.
- **Métricas de Sucesso**: Dashboard de desempenho medindo:
  - Taxa de sucesso de compilação pós-Coder.
  - Taxa de falhas de sintaxe JSON do modelo.
  - Latência e vazão de tokens gerados.
  - Consumo de memória RAM da máquina local.
- **Roteamento Dinâmico**: Recomendar e ajustar de forma dinâmica a rota dos modelos com base nos benchmarks locais rodados sob o hardware do desenvolvedor.

---

## 5. Suporte a Multi-Repositórios (Multi-Repo Support)
**Objetivo**: Apoiar fluxos de trabalho distribuídos entre múltiplos projetos e bibliotecas.
- **DAG Multi-Repositório**: Permitir que uma tarefa em uma biblioteca seja definida como blocker de outra tarefa no projeto da aplicação cliente.
- **Orquestração de Worktrees Simultâneas**: Clonar e gerenciar worktrees em repositórios distintos mantendo as dependências locais linkadas (ex: `npm link` ou pacotes Python locais editáveis).
