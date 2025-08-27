# 🚀 GUIA COMPLETO: Deploy na VPS CONTABO - Scanner Cripto

## 📋 Especificações Recomendadas da VPS Contabo

### 💰 Planos Recomendados
| Plano | CPU | RAM | Storage | Banda | Preço/mês | Recomendação |
|-------|-----|-----|---------|-------|-----------|--------------|
| **VPS S** | 4 vCPUs | 8GB | 50GB NVMe | 32TB | €4.99 | ✅ **IDEAL** |
| VPS M | 6 vCPUs | 16GB | 100GB NVMe | 32TB | €9.99 | Overkill |
| VPS XS | 2 vCPUs | 4GB | 50GB NVMe | 32TB | €3.99 | Mínimo |

> **💡 Recomendação**: VPS S (4 vCPUs, 8GB RAM) é perfeito para o scanner cripto

### 🌐 Configuração de Rede
- **IP Fixo**: Incluído em todos os planos
- **Localização**: Alemanha (baixa latência para APIs cripto)
- **Bandwidth**: 32TB suficiente para aplicação

## 🛠️ CONFIGURAÇÃO INICIAL - Ubuntu 24.04

### 1. 🔐 Primeiro Acesso SSH
```bash
# Conectar via SSH (substitua pelo seu IP)
ssh root@SEU_IP_VPS

# Criar usuário não-root (recomendado)
adduser cripto
usermod -aG sudo cripto

# Configurar chaves SSH (opcional mas recomendado)
mkdir -p /home/cripto/.ssh
cp ~/.ssh/authorized_keys /home/cripto/.ssh/
chown -R cripto:cripto /home/cripto/.ssh
chmod 700 /home/cripto/.ssh
chmod 600 /home/cripto/.ssh/authorized_keys

# Trocar para usuário cripto
su - cripto
```

### 2. 📦 Atualização do Sistema
```bash
# Atualizar repositórios e sistema
sudo apt update && sudo apt upgrade -y

# Instalar utilitários essenciais
sudo apt install -y curl wget git htop nano vim unzip
```

### 3. 🔥 Configuração de Firewall (UFW)
```bash
# Configurar firewall
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 8501/tcp  # Streamlit (temporário)
sudo ufw --force enable

# Verificar status
sudo ufw status verbose
```

## 🐍 INSTALAÇÃO DO AMBIENTE PYTHON

### 1. Python 3.12 (Ubuntu 24.04)
```bash
# Python já vem instalado no Ubuntu 24.04
python3 --version  # Deve mostrar 3.12.x

# Instalar pip e venv
sudo apt install -y python3-pip python3-venv python3-dev

# Instalar dependências para compilação (necessário para alguns pacotes)
sudo apt install -y build-essential libssl-dev libffi-dev
```

### 2. 🌐 Nginx e Supervisor
```bash
# Instalar Nginx e Supervisor
sudo apt install -y nginx supervisor

# Habilitar serviços
sudo systemctl enable nginx
sudo systemctl enable supervisor
sudo systemctl start nginx
sudo systemctl start supervisor
```

## 📥 DEPLOY DO PROJETO

### 1. 📁 Preparar Diretório
```bash
# Criar diretório do projeto
mkdir -p /home/cripto/apps
cd /home/cripto/apps

# Opção A: Upload via SCP (do seu computador local)
# scp -r "C:\Users\brand\Desktop\Tabela Ind" cripto@SEU_IP:/home/cripto/apps/tabela-ind

# Opção B: Git clone (se tiver repositório)
# git clone https://github.com/seu-usuario/tabela-ind.git

# Opção C: Download direto (vamos criar um zip)
```

### 2. 🔄 Script de Upload Automático
```bash
# No seu computador Windows (PowerShell)
# Criar arquivo upload.ps1:

$VPS_IP = "SEU_IP_VPS"
$VPS_USER = "cripto"
$LOCAL_PATH = "C:\Users\brand\Desktop\Tabela Ind"
$REMOTE_PATH = "/home/cripto/apps/tabela-ind"

# Comprimir projeto
Compress-Archive -Path "$LOCAL_PATH\*" -DestinationPath "tabela-ind.zip" -Force

# Upload via SCP
scp tabela-ind.zip $VPS_USER@$VPS_IP:/home/cripto/apps/

# Conectar e descomprimir
ssh $VPS_USER@$VPS_IP "cd /home/cripto/apps && unzip -o tabela-ind.zip -d tabela-ind && rm tabela-ind.zip"
```

### 3. 🐍 Ambiente Virtual
```bash
cd /home/cripto/apps/tabela-ind

# Criar ambiente virtual
python3 -m venv venv

# Ativar ambiente
source venv/bin/activate

# Atualizar pip
pip install --upgrade pip

# Instalar dependências
pip install -r requirements.txt

# Verificar instalação
pip list
```

### 4. 🧪 Teste Local
```bash
# Testar aplicação
streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true

# Em outro terminal (ou nova conexão SSH)
curl http://localhost:8501

# Se funcionar, parar com Ctrl+C
```

## 🌐 CONFIGURAÇÃO NGINX (Proxy Reverso)

### 1. 📝 Configuração do Nginx
```bash
# Criar configuração
sudo nano /etc/nginx/sites-available/scanner-cripto
```

```nginx
server {
    listen 80;
    server_name SEU_IP_VPS;  # Substitua pelo IP da sua VPS
    
    # Tamanho máximo de upload
    client_max_body_size 100M;
    
    # Configurações de timeout
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Configurações específicas para Streamlit
        proxy_buffering off;
        proxy_cache off;
    }
    
    # Headers de segurança
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
}
```

### 2. ✅ Ativar Configuração
```bash
# Ativar site
sudo ln -s /etc/nginx/sites-available/scanner-cripto /etc/nginx/sites-enabled/

# Remover configuração padrão
sudo rm -f /etc/nginx/sites-enabled/default

# Testar configuração
sudo nginx -t

# Reiniciar Nginx
sudo systemctl restart nginx
```

## 🔄 CONFIGURAÇÃO SUPERVISOR (Gerenciamento de Processo)

### 1. 📝 Configuração do Supervisor
```bash
sudo nano /etc/supervisor/conf.d/scanner-cripto.conf
```

```ini
[program:scanner-cripto]
command=/home/cripto/apps/tabela-ind/venv/bin/streamlit run app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true --server.enableCORS false
directory=/home/cripto/apps/tabela-ind
user=cripto
autostart=true
autorestart=true
startretries=3
stderr_logfile=/var/log/scanner-cripto.err.log
stdout_logfile=/var/log/scanner-cripto.out.log
environment=HOME="/home/cripto",USER="cripto"

# Configurações de recursos
stopwaitsecs=30
killasgroup=true
stopasgroup=true
```

### 2. ✅ Ativar Supervisor
```bash
# Recarregar configurações
sudo supervisorctl reread
sudo supervisorctl update

# Iniciar aplicação
sudo supervisorctl start scanner-cripto

# Verificar status
sudo supervisorctl status scanner-cripto
```

## 🔒 CONFIGURAÇÃO DE SEGURANÇA

### 1. 🔑 SSH Hardening
```bash
# Editar configuração SSH
sudo nano /etc/ssh/sshd_config

# Adicionar/modificar:
Port 2222                    # Mudar porta padrão
PermitRootLogin no          # Desabilitar login root
PasswordAuthentication no   # Apenas chaves SSH
AllowUsers cripto          # Apenas usuário específico

# Reiniciar SSH
sudo systemctl restart sshd

# Atualizar firewall
sudo ufw delete allow 22
sudo ufw allow 2222/tcp
```

### 2. 🛡️ Fail2ban (Proteção contra ataques)
```bash
# Instalar Fail2ban
sudo apt install -y fail2ban

# Configurar
sudo nano /etc/fail2ban/jail.local
```

```ini
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port = 2222
logpath = /var/log/auth.log

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
action = iptables-multiport[name=ReqLimit, port="http,https", protocol=tcp]
logpath = /var/log/nginx/error.log
maxretry = 5
findtime = 600
bantime = 7200
```

```bash
# Reiniciar Fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 3. 🔄 Atualizações Automáticas
```bash
# Instalar unattended-upgrades
sudo apt install -y unattended-upgrades

# Configurar
sudo nano /etc/apt/apt.conf.d/50unattended-upgrades

# Habilitar
sudo systemctl enable unattended-upgrades
```

## 📊 MONITORAMENTO E LOGS

### 1. 📈 Sistema de Monitoramento
```bash
# Instalar ferramentas de monitoramento
sudo apt install -y htop iotop netstat-nat

# Script de monitoramento
nano /home/cripto/monitor.sh
```

```bash
#!/bin/bash
echo "=== STATUS DO SISTEMA ==="
date
echo
echo "=== USO DE CPU ==="
top -bn1 | grep "Cpu(s)" | head -1
echo
echo "=== USO DE MEMÓRIA ==="
free -h
echo
echo "=== USO DE DISCO ==="
df -h /
echo
echo "=== STATUS DA APLICAÇÃO ==="
sudo supervisorctl status scanner-cripto
echo
echo "=== ÚLTIMAS LINHAS DO LOG ==="
sudo tail -5 /var/log/scanner-cripto.out.log
```

```bash
chmod +x /home/cripto/monitor.sh
```

### 2. 📝 Verificação de Logs
```bash
# Logs da aplicação
sudo tail -f /var/log/scanner-cripto.out.log   # Output normal
sudo tail -f /var/log/scanner-cripto.err.log   # Erros

# Logs do Nginx
sudo tail -f /var/log/nginx/access.log         # Acessos
sudo tail -f /var/log/nginx/error.log          # Erros

# Logs do sistema
sudo tail -f /var/log/syslog                   # Sistema geral
```

## 🚀 SCRIPTS DE AUTOMAÇÃO

### 1. 📦 Script de Deploy
```bash
nano /home/cripto/deploy.sh
```

```bash
#!/bin/bash
set -e

echo "🚀 Iniciando deploy do Scanner Cripto..."

# Ir para diretório do projeto
cd /home/cripto/apps/tabela-ind

# Backup da versão atual
if [ -d "backup" ]; then
    rm -rf backup.old
    mv backup backup.old
fi
cp -r . backup/

# Atualizar código (se usando Git)
# git pull origin main

# Atualizar dependências
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Reiniciar aplicação
sudo supervisorctl restart scanner-cripto

# Aguardar inicialização
sleep 10

# Verificar status
if sudo supervisorctl status scanner-cripto | grep -q "RUNNING"; then
    echo "✅ Deploy concluído com sucesso!"
else
    echo "❌ Erro no deploy. Verificar logs:"
    sudo tail -20 /var/log/scanner-cripto.err.log
    exit 1
fi
```

```bash
chmod +x /home/cripto/deploy.sh
```

### 2. 🔄 Script de Backup
```bash
nano /home/cripto/backup.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/home/cripto/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="scanner-cripto-$DATE"

# Criar diretório de backup
mkdir -p $BACKUP_DIR

# Criar backup
cd /home/cripto/apps
tar -czf "$BACKUP_DIR/$BACKUP_NAME.tar.gz" \
    --exclude='tabela-ind/venv' \
    --exclude='tabela-ind/__pycache__' \
    --exclude='tabela-ind/*.pyc' \
    --exclude='tabela-ind/temp_data.json' \
    tabela-ind/

# Backup dos logs
tar -czf "$BACKUP_DIR/$BACKUP_NAME-logs.tar.gz" \
    /var/log/scanner-cripto.* \
    /var/log/nginx/access.log \
    /var/log/nginx/error.log

# Manter apenas últimos 7 backups
cd $BACKUP_DIR
ls -t scanner-cripto-*.tar.gz | tail -n +8 | xargs -r rm

echo "✅ Backup criado: $BACKUP_NAME.tar.gz"
```

```bash
chmod +x /home/cripto/backup.sh

# Configurar cron para backup diário
crontab -e
# Adicionar linha:
0 2 * * * /home/cripto/backup.sh
```

## 🌐 CONFIGURAÇÃO DE DOMÍNIO (Opcional)

### 1. 🏷️ Configurar Domínio
```bash
# Se você tem um domínio, configure:
# 1. No painel da Contabo, configure o DNS reverso
# 2. No seu provedor de domínio, adicione registro A:
#    scanner.seudominio.com → IP_DA_VPS

# Atualizar configuração do Nginx
sudo nano /etc/nginx/sites-available/scanner-cripto

# Substituir:
# server_name SEU_IP_VPS;
# Por:
# server_name scanner.seudominio.com;

sudo systemctl reload nginx
```

### 2. 🔒 SSL/HTTPS com Let's Encrypt
```bash
# Instalar Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obter certificado SSL
sudo certbot --nginx -d scanner.seudominio.com

# Renovação automática
sudo crontab -e
# Adicionar:
0 3 * * * /usr/bin/certbot renew --quiet
```

## ✅ CHECKLIST DE DEPLOY

- [ ] **VPS Contabo configurada** (Ubuntu 24.04)
- [ ] **Usuário não-root criado** e configurado
- [ ] **Firewall UFW configurado** com portas corretas
- [ ] **Python 3.12 e dependências** instaladas
- [ ] **Projeto uploaded** para /home/cripto/apps/tabela-ind
- [ ] **Ambiente virtual criado** e dependências instaladas
- [ ] **Aplicação testada** localmente na porta 8501
- [ ] **Nginx configurado** como proxy reverso
- [ ] **Supervisor configurado** para gerenciar processo
- [ ] **Segurança configurada** (SSH hardening, Fail2ban)
- [ ] **Monitoramento configurado** (logs, scripts)
- [ ] **Scripts de automação** criados (deploy, backup)
- [ ] **Domínio configurado** (opcional)
- [ ] **SSL/HTTPS configurado** (opcional)

## 🎯 COMANDOS ÚTEIS CONTABO

### 📊 Monitoramento
```bash
# Status geral do sistema
./monitor.sh

# Status da aplicação
sudo supervisorctl status scanner-cripto

# Logs em tempo real
sudo tail -f /var/log/scanner-cripto.out.log

# Uso de recursos
htop
```

### 🔄 Gerenciamento
```bash
# Reiniciar aplicação
sudo supervisorctl restart scanner-cripto

# Deploy nova versão
./deploy.sh

# Criar backup
./backup.sh

# Verificar conexões ativas
sudo netstat -tulpn | grep :80
```

### 🚨 Troubleshooting
```bash
# Se aplicação não inicia
sudo supervisorctl status
sudo tail -50 /var/log/scanner-cripto.err.log

# Se Nginx não responde
sudo nginx -t
sudo systemctl status nginx

# Se out of memory
free -h
sudo systemctl restart scanner-cripto
```

## 🌟 OTIMIZAÇÕES ESPECÍFICAS CONTABO

### 1. 💾 Configuração de Swap
```bash
# Criar swap de 2GB (recomendado para VPS S)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Tornar permanente
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Configurar swappiness
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
```

### 2. ⚡ Otimizações de Performance
```bash
# Configurar timezone
sudo timedatectl set-timezone Europe/Berlin

# Otimizar TCP
sudo nano /etc/sysctl.conf
```

```bash
# Adicionar ao final:
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
```

## 🎉 RESULTADO FINAL

Após seguir este guia, você terá:

- ✅ **Scanner Cripto rodando** em produção na Contabo
- ✅ **Alta disponibilidade** com Supervisor
- ✅ **Proxy reverso** Nginx configurado
- ✅ **Segurança robusta** com firewall e fail2ban
- ✅ **Monitoramento completo** com logs e métricas
- ✅ **Scripts de automação** para deploy e backup
- ✅ **Performance otimizada** para VPS Contabo

**🌐 Acesso**: `http://SEU_IP_VPS` ou `https://scanner.seudominio.com`

---

## 💡 DICAS FINAIS CONTABO

1. **💰 Billing**: Contabo cobra mensalmente, configure alertas de uso
2. **📍 Localização**: Datacenter alemão é ideal para APIs europeias
3. **🔄 Backups**: Contabo oferece backups pagos, mas scripts próprios são mais flexíveis
4. **📊 Monitoramento**: Use dashboard da Contabo para monitorar recursos
5. **🎯 Performance**: VPS S é suficiente, upgrade só se necessário

**📞 Suporte Contabo**: Responde rapidamente via ticket system
