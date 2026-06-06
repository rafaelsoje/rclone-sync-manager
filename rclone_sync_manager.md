# Rclone Sync Manager — Especificação Completa para Implementação com Codex

## 1. Visão geral do projeto

Criar um aplicativo desktop para Linux chamado **Rclone Sync Manager**, com interface gráfica, serviço em background e integração com `rclone`, para sincronizar múltiplos diretórios locais com Google Drive ou outros remotes suportados pelo rclone.

O objetivo é substituir parcialmente ferramentas como Insync, mas com menor consumo de recursos, mais controle sobre sincronização e melhor estabilidade em desktop Linux.

O app NÃO deve implementar diretamente a API do Google Drive. O motor principal de sincronização será o `rclone`.

---

## 2. Objetivos principais

O aplicativo deve permitir que o usuário:

- cadastre várias pastas locais para sincronização;
- escolha o destino remoto do rclone para cada pasta;
- escolha o modo de sincronização: `copy`, `sync` ou `bisync`;
- monitore alterações locais em tempo real;
- agende sincronizações por horário;
- pause e retome sincronizações;
- execute sincronização manualmente;
- visualize status dos jobs;
- visualize logs;
- limite uso de rede, CPU e I/O;
- evite múltiplas sincronizações simultâneas da mesma pasta;
- rode o app automaticamente com o sistema;
- funcione com baixa prioridade para não travar áudio, vídeo ou desktop.

---

## 3. Stack tecnológica

### Backend/local daemon

- Python 3.11+
- `rclone` via subprocess
- `watchdog` para monitoramento de arquivos
- `PyYAML` para configuração opcional
- `sqlite3` para estado, histórico e jobs
- `logging` para logs
- `psutil` para monitoramento de processos e uso de recursos

### Interface gráfica

- PySide6 / Qt

### Integração Linux

- systemd --user
- libnotify / notify-send para notificações desktop
- execução com `nice` e `ionice`

---

## 4. Conceito de arquitetura

```text
Interface Gráfica
        ↓
Serviço/Daemon Python
        ↓
rclone
        ↓
Google Drive / outro remote
```

A interface gráfica não deve executar diretamente o rclone. Ela chama funções internas do app/daemon, que controlam fila, locks, logs e execução.

No MVP completo, tudo pode estar no mesmo processo Python. Em uma versão futura, pode virar daemon separado com API local.

---

## 5. Estrutura de diretórios do projeto

```text
rclone-sync-manager/
├── README.md
├── pyproject.toml
├── requirements.txt
├── config.example.yaml
├── rclone_sync_manager/
│   ├── __init__.py
│   ├── main.py
│   ├── app.py
│   ├── cli.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── runner.py
│   ├── watcher.py
│   ├── scheduler.py
│   ├── queue_manager.py
│   ├── lock_manager.py
│   ├── notifier.py
│   ├── resource_monitor.py
│   ├── utils.py
│   └── gui/
│       ├── __init__.py
│       ├── main_window.py
│       ├── job_form.py
│       ├── job_table.py
│       ├── log_viewer.py
│       ├── settings_dialog.py
│       └── tray.py
├── systemd/
│   └── rclone-sync-manager.service
├── scripts/
│   ├── install.sh
│   ├── uninstall.sh
│   └── dev_run.sh
└── tests/
    ├── test_config.py
    ├── test_runner.py
    ├── test_locks.py
    └── test_queue.py
```

---

## 6. Diretórios locais usados pelo aplicativo

O app deve usar os seguintes caminhos:

```text
~/.config/rclone-sync-manager/config.yaml
~/.local/share/rclone-sync-manager/rsm.db
~/.local/share/rclone-sync-manager/logs/app.log
~/.local/share/rclone-sync-manager/logs/jobs/<job-name>.log
~/.local/share/rclone-sync-manager/state/
~/.local/share/rclone-sync-manager/locks/
```

Criar esses diretórios automaticamente se não existirem.

---

## 7. Modelo de dados

### Tabela `jobs`

```text
id INTEGER PRIMARY KEY
name TEXT UNIQUE NOT NULL
enabled INTEGER DEFAULT 1
local_path TEXT NOT NULL
remote_path TEXT NOT NULL
mode TEXT NOT NULL
realtime INTEGER DEFAULT 0
schedule_time TEXT NULL
debounce_seconds INTEGER DEFAULT 30
transfers INTEGER DEFAULT 2
checkers INTEGER DEFAULT 4
bandwidth_limit TEXT NULL
dry_run INTEGER DEFAULT 0
priority_low INTEGER DEFAULT 1
notify INTEGER DEFAULT 1
created_at TEXT
updated_at TEXT
```

### Tabela `ignore_patterns`

```text
id INTEGER PRIMARY KEY
job_id INTEGER
pattern TEXT
```

### Tabela `job_runs`

```text
id INTEGER PRIMARY KEY
job_id INTEGER
started_at TEXT
finished_at TEXT
status TEXT
exit_code INTEGER
duration_seconds INTEGER
command TEXT
log_file TEXT
error_message TEXT
```

### Tabela `app_settings`

```text
key TEXT PRIMARY KEY
value TEXT
```

---

## 8. Modos de sincronização

### 8.1 Modo `copy`

Copia arquivos da origem para o destino sem apagar arquivos no destino.

Comando base:

```bash
rclone copy LOCAL REMOTO
```

Uso recomendado:

- fotos;
- backups simples;
- arquivos que não precisam espelhar exclusões.

---

### 8.2 Modo `sync`

Espelha a origem no destino. Pode apagar arquivos no destino.

Comando base:

```bash
rclone sync LOCAL REMOTO
```

Regra de segurança:

- antes de permitir `sync`, mostrar alerta informando que arquivos no destino podem ser apagados.

---

### 8.3 Modo `bisync`

Sincronização bidirecional entre local e remoto.

Comando base:

```bash
rclone bisync LOCAL REMOTO
```

Regra de segurança:

- primeira execução deve exigir inicialização manual com `--resync`;
- o app deve alertar que conflitos precisam ser analisados;
- não rodar primeiro bisync automaticamente sem confirmação.

---

## 9. Regras de negócio principais

### 9.1 Jobs independentes

Cada diretório configurado é um job independente.

Um job possui:

- nome;
- pasta local;
- remote do rclone;
- modo de sincronização;
- status ativo/inativo;
- realtime ligado/desligado;
- agendamento opcional;
- limite de transfers;
- limite de checkers;
- limite de banda;
- padrões ignorados;
- log individual.

Erro em um job não pode derrubar os demais.

---

### 9.2 Monitoramento realtime

Quando `realtime = true`, o app deve monitorar a pasta local usando `watchdog`.

Eventos monitorados:

- arquivo criado;
- arquivo alterado;
- arquivo movido;
- arquivo apagado;
- diretório criado;
- diretório removido.

Ao detectar evento:

1. verificar se o arquivo deve ser ignorado;
2. marcar job como pendente;
3. aguardar debounce;
4. adicionar job à fila de execução.

---

### 9.3 Debounce

O app não deve sincronizar imediatamente após cada alteração.

Exemplo:

```text
Arquivo mudou
↓
aguarda 30 segundos
↓
se nada mais mudou, sincroniza
↓
se mudou novamente, reinicia contagem
```

Cada job terá seu próprio `debounce_seconds`.

---

### 9.4 Fila de execução

O app deve ter fila global de sincronização.

Regras:

- não executar o mesmo job duas vezes ao mesmo tempo;
- respeitar limite global de jobs paralelos;
- padrão inicial: 1 job por vez;
- se um job já estiver rodando e novas alterações acontecerem, marcar como pendente;
- após terminar, se estiver pendente, executar novamente depois do debounce.

---

### 9.5 Locks

Cada job deve possuir lock próprio.

Exemplo:

```text
~/.local/share/rclone-sync-manager/locks/Documentos.lock
```

O lock deve conter:

```json
{
  "pid": 12345,
  "job": "Documentos",
  "started_at": "2026-05-14T10:00:00"
}
```

Se o lock existir e o processo estiver vivo, não iniciar outro.

Se o lock existir mas o processo não existir, remover lock antigo.

---

### 9.6 Prioridade baixa

Executar rclone com prioridade baixa para reduzir impacto no sistema:

```bash
ionice -c3 nice -n 19 rclone ...
```

Essa opção deve estar ativada por padrão.

---

### 9.7 Limitação de recursos

Cada job deve aceitar:

```text
transfers
checkers
bandwidth_limit
```

Exemplo de comando final:

```bash
ionice -c3 nice -n 19 rclone bisync /home/rafael/Documentos gdrive:Documentos --transfers 2 --checkers 4 --bwlimit 2M --log-file ~/.local/share/rclone-sync-manager/logs/jobs/Documentos.log --log-level INFO
```

---

### 9.8 Arquivos ignorados

Ignorar por padrão:

```text
*.tmp
*.part
*.crdownload
~*
*.swp
.DS_Store
Thumbs.db
node_modules/**
.git/**
__pycache__/**
vendor/**
storage/logs/**
```

O usuário deve poder editar essa lista na interface gráfica.

---

### 9.9 Agendamento

Cada job pode ter horário diário configurado.

Exemplo:

```text
02:00
```

No MVP completo, implementar apenas horário diário simples.

Futuro:

- intervalo a cada X minutos;
- dias da semana;
- múltiplos horários.

---

### 9.10 Dry-run

Todo job deve ter opção `dry_run`.

Se ativado, adicionar:

```bash
--dry-run
```

Isso permite testar sem copiar/apagar nada.

---

## 10. Interface gráfica

A interface deve ser simples, leve e objetiva.

### 10.1 Tela principal

A tela principal deve exibir uma tabela com os jobs.

Colunas:

```text
Nome
Pasta local
Remoto
Modo
Realtime
Agendamento
Status
Última execução
Último resultado
```

Botões principais:

```text
Adicionar job
Editar job
Remover job
Pausar
Retomar
Sincronizar agora
Ver logs
Configurações
```

---

### 10.2 Formulário de job

Campos:

```text
Nome do job
Pasta local
Remote rclone
Modo: copy / sync / bisync
Ativar realtime
Ativar agendamento
Horário de agendamento
Debounce em segundos
Transfers
Checkers
Limite de banda
Dry-run
Prioridade baixa
Notificações
Padrões ignorados
```

Validações:

- nome obrigatório;
- nome único;
- pasta local deve existir;
- remote não pode ficar vazio;
- modo precisa ser copy, sync ou bisync;
- debounce deve ser maior que 5 segundos;
- transfers deve ser pelo menos 1;
- checkers deve ser pelo menos 1.

---

### 10.3 Tela de logs

A tela de logs deve permitir:

- selecionar job;
- visualizar últimas linhas do log;
- atualizar log;
- abrir arquivo de log;
- limpar visualização;
- filtrar por erro.

---

### 10.4 Tela de configurações

Configurações globais:

```text
Caminho do rclone
Máximo de jobs paralelos
Ativar notificações desktop
Iniciar com o sistema
Tema claro/escuro
Diretório de logs
Diretório de estado
```

---

### 10.5 Ícone de bandeja

Implementar tray icon com menu:

```text
Abrir Rclone Sync Manager
Pausar todas as sincronizações
Retomar todas as sincronizações
Sincronizar todos agora
Ver logs
Sair
```

---

## 11. CLI obrigatória

Mesmo com interface gráfica, criar CLI.

Comandos:

```bash
rsm gui
rsm start
rsm list
rsm status
rsm run --job Documentos
rsm run --all
rsm pause --job Documentos
rsm resume --job Documentos
rsm logs --job Documentos
rsm init-bisync --job Documentos
rsm doctor
```

### 11.1 Comando doctor

O comando `doctor` deve verificar:

- se rclone está instalado;
- se watchdog está instalado;
- se systemd user está disponível;
- se `ionice` existe;
- se `nice` existe;
- se o remote `gdrive:` existe no rclone;
- se os diretórios locais existem;
- se o banco SQLite está acessível.

---

## 12. Fluxos principais

### 12.1 Criar novo job

Fluxo:

1. usuário clica em Adicionar job;
2. preenche nome, pasta local e remote;
3. escolhe modo;
4. escolhe realtime ou agendamento;
5. salva;
6. app valida dados;
7. grava no SQLite;
8. se realtime ativo, inicia watcher para a pasta.

---

### 12.2 Sincronização automática realtime

Fluxo:

1. watchdog detecta mudança;
2. app ignora arquivos temporários;
3. app marca job como pendente;
4. app aguarda debounce;
5. app cria lock;
6. app executa rclone;
7. app salva log;
8. app salva histórico;
9. app remove lock;
10. app notifica resultado.

---

### 12.3 Sincronização manual

Fluxo:

1. usuário seleciona job;
2. clica em Sincronizar agora;
3. app verifica se job está rodando;
4. se não estiver, adiciona à fila;
5. executa rclone;
6. atualiza status na tabela.

---

### 12.4 Pausar job

Fluxo:

1. usuário seleciona job;
2. clica em Pausar;
3. app muda `enabled = 0`;
4. watcher para aquele job é removido;
5. job não roda por realtime nem agendamento.

---

### 12.5 Retomar job

Fluxo:

1. usuário seleciona job;
2. clica em Retomar;
3. app muda `enabled = 1`;
4. se realtime estiver ativo, watcher volta a monitorar.

---

## 13. Serviço systemd

Criar arquivo:

```ini
[Unit]
Description=Rclone Sync Manager
After=network-online.target

[Service]
Type=simple
ExecStart=%h/.local/bin/rsm start
Restart=always
RestartSec=10
Nice=19
IOSchedulingClass=idle

[Install]
WantedBy=default.target
```

Comandos de instalação:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/rclone-sync-manager.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rclone-sync-manager.service
```

---

## 14. Script de instalação

Criar `scripts/install.sh`.

Ele deve:

1. verificar Python;
2. verificar rclone;
3. criar venv;
4. instalar dependências;
5. instalar comando `rsm` em `~/.local/bin`;
6. criar diretórios do app;
7. instalar serviço systemd user;
8. perguntar se deseja iniciar o serviço.

---

## 15. Regras de segurança

- Não implementar OAuth próprio.
- Não manipular diretamente `rclone.conf`.
- Usar apenas remotes já configurados no rclone.
- Alertar antes de usar `sync`.
- Alertar antes de usar `bisync`.
- Nunca rodar primeiro `bisync` sem inicialização.
- Não apagar arquivos locais automaticamente sem confirmação.
- Manter opção `dry-run` visível.
- Registrar comandos executados nos logs.

---

## 16. Tratamento de erros

O app deve tratar:

- rclone não instalado;
- remote inexistente;
- pasta local inexistente;
- permissão negada;
- internet indisponível;
- job já em execução;
- lock antigo;
- erro no bisync;
- conflito de arquivos;
- código de saída diferente de zero.

Em caso de erro:

1. registrar no log;
2. atualizar status do job;
3. exibir notificação;
4. não derrubar o app inteiro.

---

## 17. Status dos jobs

Possíveis status:

```text
idle
pending
running
success
error
paused
disabled
waiting_debounce
scheduled
```

---

## 18. Notificações desktop

Usar `notify-send` quando disponível.

Notificar:

- sync iniciado;
- sync concluído;
- erro de sync;
- conflito;
- job pausado;
- job retomado.

Permitir desativar notificações.

---

## 19. Implementação em etapas para o Codex

### Etapa 1 — Base do projeto

Criar estrutura de pastas, `pyproject.toml`, `requirements.txt`, README inicial e entrypoint CLI `rsm`.

Dependências iniciais:

```text
PySide6
watchdog
PyYAML
psutil
```

---

### Etapa 2 — Banco de dados

Implementar SQLite com tabelas:

- jobs;
- ignore_patterns;
- job_runs;
- app_settings.

Criar funções CRUD para jobs.

---

### Etapa 3 — Runner do rclone

Implementar módulo `runner.py` responsável por montar e executar comandos rclone.

Deve suportar:

- copy;
- sync;
- bisync;
- dry-run;
- transfers;
- checkers;
- bwlimit;
- log-file;
- prioridade baixa com nice/ionice.

---

### Etapa 4 — Lock manager

Implementar locks por job.

Funções:

```python
create_lock(job)
remove_lock(job)
is_locked(job)
cleanup_stale_locks()
```

---

### Etapa 5 — Queue manager

Implementar fila global.

Funções:

```python
enqueue(job)
worker_loop()
is_running(job)
mark_pending(job)
```

---

### Etapa 6 — Watcher

Implementar monitoramento com watchdog.

Cada job realtime deve ter observer próprio ou handler próprio.

Aplicar filtros de ignore patterns.

Aplicar debounce.

---

### Etapa 7 — Scheduler

Implementar agendamento diário simples por horário HH:MM.

O scheduler deve verificar jobs agendados e enfileirar quando chegar o horário.

---

### Etapa 8 — CLI

Implementar comandos:

```bash
rsm list
rsm status
rsm run --job NOME
rsm run --all
rsm pause --job NOME
rsm resume --job NOME
rsm logs --job NOME
rsm doctor
rsm gui
rsm start
```

---

### Etapa 9 — Interface gráfica

Criar PySide6 com:

- MainWindow;
- tabela de jobs;
- formulário de criação/edição;
- tela de logs;
- tela de configurações;
- botões de ação.

---

### Etapa 10 — Tray icon

Criar ícone de bandeja com ações rápidas.

---

### Etapa 11 — systemd

Criar serviço systemd user e script de instalação.

---

### Etapa 12 — Testes

Criar testes unitários para:

- geração de comando rclone;
- locks;
- validação de configuração;
- fila;
- ignore patterns.

---

## 20. Primeiro comportamento esperado

Ao abrir o app pela primeira vez:

1. verificar se rclone está instalado;
2. verificar se existe remote configurado;
3. se não existir, orientar usuário a rodar:

```bash
rclone config
```

4. abrir tela principal vazia;
5. permitir adicionar primeiro job.

---

## 21. Exemplo de comando gerado

Para job Documentos em modo bisync:

```bash
ionice -c3 nice -n 19 rclone bisync /home/rafael/Documentos gdrive:Documentos --transfers 2 --checkers 4 --log-file /home/rafael/.local/share/rclone-sync-manager/logs/jobs/Documentos.log --log-level INFO
```

Para job Fotos em modo copy:

```bash
ionice -c3 nice -n 19 rclone copy /mnt/storage/Fotos gdrive:Fotos --transfers 4 --checkers 8 --log-file /home/rafael/.local/share/rclone-sync-manager/logs/jobs/Fotos.log --log-level INFO
```

---

## 22. Funcionalidades futuras

Depois da versão completa inicial:

- AppImage;
- pacote Arch/Manjaro PKGBUILD;
- integração com KDE;
- pausa automática quando áudio estiver tocando;
- detecção de grandes operações;
- perfis leve/normal/madrugada;
- dashboard local via FastAPI;
- sincronização com múltiplos remotes;
- integração com notificações avançadas;
- histórico visual de execução;
- gráfico de uso de banda;
- modo dark/light automático.

---

## 23. Prioridade de implementação

Implementar nesta ordem:

1. banco SQLite;
2. CRUD de jobs;
3. runner do rclone;
4. CLI básica;
5. locks;
6. fila;
7. watcher realtime;
8. scheduler;
9. interface gráfica;
10. tray icon;
11. systemd;
12. instalador;
13. testes.

---

## 24. Resultado final esperado

O usuário deverá conseguir abrir o app, cadastrar múltiplas pastas, escolher como cada uma será sincronizada e deixar o serviço rodando em background com baixo impacto no sistema.

O app deve ser leve, confiável e adequado para desktop Linux, especialmente para usuários que querem usar Google Drive sem depender de clientes pesados como Insync.

