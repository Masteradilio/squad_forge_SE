# LocalForge OS — Guia de Resolução de Problemas (Troubleshooting)

Este guia documenta os problemas de ambiente e execução mais comuns e como solucioná-los.

---

## 1. Ollama não está executando
### Sintomas
- A inicialização do agente trava ou reporta falhas ao realizar chamadas de completamento de chat.
- O comando `localforge doctor` apresenta avisos ou erros na seção `ollama`.

### Resolução
1. Certifique-se de que o daemon do Ollama está rodando na sua máquina.
   - **Windows/macOS**: Abra o aplicativo Ollama.
   - **Linux**: Execute `systemctl status ollama` ou inicie o serviço manualmente.
2. Teste a conectividade local executando uma requisição simples no seu terminal:
   ```bash
   curl http://localhost:11434
   ```
   A resposta deve ser: `Ollama is running`.
3. Caso utilize uma porta ou host customizado, certifique-se de configurar a variável de ambiente correspondente ou atualizar a seção `models` no arquivo de configuração do LocalForge.

---

## 2. Modelo de Linguagem Ausente (Model Missing)
### Sintomas
- Logs exibem erros do tipo `ModelNotFoundError` ou mensagens HTTP informando que o modelo especificado não foi encontrado no provedor.

### Resolução
1. Por padrão, o LocalForge OS tenta rotear as chamadas para perfis de modelos específicos (ex: `qwen2.5-coder:7b`).
2. Certifique-se de baixar o modelo correto via Ollama executando no terminal:
   ```bash
   ollama run qwen2.5-coder:7b
   ```
3. Se desejar utilizar outro modelo local já baixado, altere o mapeamento de perfis de modelo acessando a aba **Models** no painel visual (Frontend) ou editando as tabelas de rotas no banco de dados.

---

## 3. Estado "Dirty" do Git (Excesso de arquivos modificados)
### Sintomas
- Erros de orçamento como `Workspace file count budget exceeded` ou `Workspace diff growth budget exceeded` durante a execução de tarefas.
- O `SafeFileEditor` bloqueia edições reportando que mais de 20 arquivos foram modificados.

### Resolução
1. O LocalForge OS monitora alterações no repositório de trabalho (worktree) isolado da tarefa. Se o diretório pai ou a worktree possuir arquivos soltos e não ignorados (ex: arquivos de log, dumps, ou dependências no local incorreto), eles serão contabilizados.
2. Certifique-se de que pastas como `.venv`, `__pycache__` e `node_modules` estão devidamente incluídas no seu arquivo `.gitignore` na raiz do projeto.
3. Se houver modificações não salvas que não pertencem à tarefa atual no repositório principal, salve-as temporariamente:
   ```bash
   git stash
   ```
4. Se necessário, aumente o limite de arquivos modificados nas configurações do run (`budgets.max_file_count` no `.localforge/config.yaml`).

---

## 4. Docker Daemon Indisponível
### Sintomas
- A execução de comandos do Safety Kernel falha ao tentar inicializar em modo sandboxed (`DockerSandbox`).
- O comando `localforge doctor` apresenta o status `WARN` ou `FAIL` para o serviço de contêineres Docker.

### Resolução
1. Caso tenha configurado o LocalForge OS para utilizar o provedor de sandbox `"docker"`, certifique-se de que o **Docker Desktop** (ou o daemon Docker local) está ativo.
2. Se estiver rodando no Windows via WSL2, garanta que a integração com a sua distro WSL padrão está habilitada nas configurações do Docker Desktop.
3. Certifique-se de que as dependências de desenvolvimento do Python (`docker` SDK) estão instaladas no ambiente virtual rodando:
   ```bash
   python manage.py setup-backend
   ```
4. Se o daemon Docker não estiver instalado ou não puder ser iniciado, o LocalForge OS executará uma regressão segura automática (graceful fallback) utilizando o `"local"` sandbox (isolamento baseado em subdiretórios de worktree).

---

## 5. Credenciais de PR do GitHub Ausentes
### Sintomas
- As tarefas são concluídas com sucesso localmente (passando no pipeline e testes, alcançando o estado `PR_READY`), mas a Pull Request não aparece no repositório do GitHub.

### Resolução
1. Por padrão, a integração direta com a API remota do GitHub é **opcional**. Caso desativada, o sistema gera o artefato local de proposta de PR (`pr.md`) na pasta de artefatos da tarefa.
2. Para habilitar a criação automática de Pull Requests no GitHub:
   - Crie um arquivo `.env` na raiz do projeto contendo as seguintes variáveis:
     ```env
     LOCALFORGE_ENABLE_GITHUB_PR=true
     LOCALFORGE_GITHUB_TOKEN=seu_personal_access_token_aqui
     ```
   - O token gerado deve possuir escopo de escrita em repositórios (`repo`).
3. Nunca insira tokens de acesso diretamente no código do projeto. Utilize sempre o arquivo `.env` local (que está devidamente adicionado ao `.gitignore`).
