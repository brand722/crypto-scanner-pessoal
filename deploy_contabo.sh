#!/bin/bash

# 🚀 Script de Deploy Automatizado para CONTABO VPS
# Scanner de Oportunidades Cripto - Ubuntu 24.04

set -e  # Parar em caso de erro

echo "🚀 Iniciando deploy na CONTABO VPS com Ubuntu 24.04..."
echo "📍 Datacenter: Alemanha (Nuremberg)"
echo

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Função para log colorido
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] ⚠️  WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ❌ ERROR: $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] ℹ️  $1${NC}"
}

success() {
    echo -e "${PURPLE}[$(date +'%Y-%m-%d %H:%M:%S')] ✅ $1${NC}"
}

# Verificar se está rodando como root
if [[ $EUID -eq 0 ]]; then
   error "Este script não deve ser executado como root. Use: sudo su - cripto"
fi

# Verificar sistema operacional
if [[ ! -f /etc/os-release ]]; then
    error "Sistema operacional não suportado"
fi

source /etc/os-release
if [[ "$ID" != "ubuntu" ]]; then
    warn "Sistema operacional não testado: $ID. Esperado: ubuntu"
fi

if [[ "$VERSION_ID" != "24.04" ]]; then
    warn "Versão Ubuntu não testada: $VERSION_ID. Esperado: 24.04"
fi

log "Sistema detectado: $ID $VERSION_ID"

# Verificar especificações da VPS (Contabo VPS S recomendado)
info "Verificando especificações da VPS..."
CPU_CORES=$(nproc)
MEMORY_GB=$(free -g | awk 'NR==2{printf "%.1f", $2}')
DISK_GB=$(df -BG / | awk 'NR==2{gsub(/G/,"",$2); print $2}')

echo "   💻 CPU: $CPU_CORES cores"
echo "   🧠 RAM: ${MEMORY_GB}GB"
echo "   💾 Disk: ${DISK_GB}GB"

if (( CPU_CORES < 4 )); then
    warn "CPU insuficiente. Recomendado: 4+ cores (Contabo VPS S)"
fi

if (( ${MEMORY_GB%.*} < 6 )); then
    warn "RAM insuficiente. Recomendado: 8GB+ (Contabo VPS S)"
fi

# 1. Atualizar sistema
log "📦 Atualizando sistema Ubuntu 24.04..."
sudo apt update && sudo apt upgrade -y

# 2. Instalar dependências específicas para Contabo
log "🔧 Instalando dependências otimizadas para Contabo..."
sudo apt install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    python3-dev \
    git \
    curl \
    wget \
    nginx \
    supervisor \
    htop \
    iotop \
    netstat-nat \
    unzip \
    build-essential \
    libssl-dev \
    libffi-dev \
    pkg-config \
    software-properties-common

# 3. Configurar timezone para Alemanha
log "🌍 Configurando timezone para datacenter alemão..."
sudo timedatectl set-timezone Europe/Berlin
timedatectl status

# 4. Configurar swap otimizado para 8GB RAM
log "💾 Configurando swap de 2GB (otimizado para Contabo VPS S)..."
if [[ ! -f /swapfile ]]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
    success "Swap de 2GB configurado"
else
    info "Swap já configurado"
fi

# 5. Otimizações TCP para APIs cripto
log "🌐 Aplicando otimizações TCP para APIs cripto..."
sudo tee -a /etc/sysctl.conf > /dev/null <<EOF

# Otimizações TCP para Contabo VPS - APIs Cripto
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.ipv4.tcp_congestion_control = bbr
EOF

sudo sysctl -p

# 6. Configurar firewall UFW
log "🔥 Configurando firewall UFW..."
sudo ufw allow 2222/tcp   # SSH customizado
sudo ufw allow 80/tcp     # HTTP
sudo ufw allow 443/tcp    # HTTPS
sudo ufw allow 8501/tcp   # Streamlit (temporário)
sudo ufw --force enable

# 7. Configuração de segurança SSH
log "🔒 Configurando segurança SSH..."
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup
sudo tee /etc/ssh/sshd_config.d/contabo_security.conf > /dev/null <<EOF
# Configurações de segurança para Contabo VPS
Port 2222
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AllowUsers cripto
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
EOF

# 8. Instalar e configurar Fail2ban
log "🛡️ Configurando Fail2ban..."
sudo apt install -y fail2ban
sudo tee /etc/fail2ban/jail.d/contabo.conf > /dev/null <<EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3
ignoreip = 127.0.0.1/8

[sshd]
enabled = true
port = 2222
logpath = /var/log/auth.log
maxretry = 3

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
action = iptables-multiport[name=ReqLimit, port="http,https", protocol=tcp]
logpath = /var/log/nginx/error.log
maxretry = 5
findtime = 600
bantime = 7200
EOF

sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# 9. Criar diretório do projeto
PROJECT_DIR="/home/cripto/apps/tabela-ind"
log "📁 Configurando diretório do projeto: $PROJECT_DIR"

if [[ -d "$PROJECT_DIR" ]]; then
    log "Fazendo backup da versão atual..."
    mv "$PROJECT_DIR" "${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
fi

mkdir -p /home/cripto/apps
cd /home/cripto/apps

# 10. Obter código do projeto
log "📥 Obtendo código do projeto..."

# Verificar se existe arquivo zip na pasta atual
if [[ -f "tabela-ind.zip" ]]; then
    log "Descompactando tabela-ind.zip..."
    unzip -o tabela-ind.zip -d tabela-ind
elif [[ -d "../Tabela Ind" ]]; then
    log "Copiando de diretório local..."
    cp -r "../Tabela Ind" tabela-ind
else
    info "Para transferir arquivos do Windows para Contabo:"
    echo "   1. Comprimir projeto: Compress-Archive -Path 'C:\\Users\\brand\\Desktop\\Tabela Ind\\*' -DestinationPath 'tabela-ind.zip'"
    echo "   2. Upload: scp tabela-ind.zip cripto@SEU_IP:/home/cripto/apps/"
    echo "   3. Executar novamente este script"
    
    # Criar estrutura básica se não existir
    mkdir -p tabela-ind
    echo "# Scanner de Oportunidades Cripto" > tabela-ind/README.md
    
    warn "Código não encontrado. Criada estrutura básica. Faça upload dos arquivos."
fi

cd "$PROJECT_DIR"

# 11. Configurar ambiente virtual Python 3.12
log "🐍 Configurando ambiente virtual Python 3.12..."
python3.12 -m venv venv
source venv/bin/activate

# Atualizar pip
pip install --upgrade pip

# Instalar dependências se requirements.txt existir
if [[ -f "requirements.txt" ]]; then
    log "📦 Instalando dependências Python..."
    pip install -r requirements.txt
else
    warn "requirements.txt não encontrado. Instalando dependências básicas..."
    pip install streamlit pandas requests numpy ccxt python-binance pandas-ta
fi

# 12. Criar configuração de produção
log "⚙️ Criando configuração de produção..."
cat > .streamlit/config.toml <<EOF
[server]
port = 8501
address = "127.0.0.1"
headless = true
enableCORS = false
enableXsrfProtection = true
maxUploadSize = 200

[browser]
gatherUsageStats = false

[client]
toolbarMode = "minimal"
EOF

mkdir -p .streamlit

# 13. Testar aplicação
log "🧪 Testando aplicação..."
if [[ -f "app.py" ]]; then
    timeout 30s streamlit run app.py --server.port 8501 --server.address 127.0.0.1 &
    STREAMLIT_PID=$!
    sleep 15
    
    if kill -0 $STREAMLIT_PID 2>/dev/null; then
        success "Aplicação iniciada com sucesso"
        kill $STREAMLIT_PID
        wait $STREAMLIT_PID 2>/dev/null || true
    else
        error "Falha ao iniciar aplicação. Verifique app.py"
    fi
else
    warn "app.py não encontrado. Deploy parcial realizado."
fi

# 14. Configurar Nginx otimizado para Contabo
log "🌐 Configurando Nginx para Contabo..."
sudo tee /etc/nginx/sites-available/scanner-cripto > /dev/null <<EOF
# Configuração Nginx otimizada para Contabo VPS
server {
    listen 80;
    server_name _;
    
    # Otimizações para Contabo
    client_max_body_size 100M;
    client_body_timeout 60s;
    client_header_timeout 60s;
    
    # Rate limiting
    limit_req_zone \$binary_remote_addr zone=api:10m rate=10r/s;
    
    location / {
        # Rate limiting
        limit_req zone=api burst=20 nodelay;
        
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Timeouts otimizados para APIs cripto
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;
        
        # Buffering
        proxy_buffering off;
        proxy_cache off;
        proxy_request_buffering off;
    }
    
    # Headers de segurança
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Compressão
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
}
EOF

# Ativar configuração
sudo ln -sf /etc/nginx/sites-available/scanner-cripto /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# 15. Configurar Supervisor
log "🔄 Configurando Supervisor..."
sudo tee /etc/supervisor/conf.d/scanner-cripto.conf > /dev/null <<EOF
[program:scanner-cripto]
command=$PROJECT_DIR/venv/bin/streamlit run app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true
directory=$PROJECT_DIR
user=cripto
autostart=true
autorestart=true
startretries=5
stderr_logfile=/var/log/scanner-cripto.err.log
stdout_logfile=/var/log/scanner-cripto.out.log
environment=HOME="/home/cripto",USER="cripto",PYTHONPATH="$PROJECT_DIR"

# Configurações de recursos para Contabo VPS S
stopwaitsecs=30
killasgroup=true
stopasgroup=true
priority=999
EOF

# Ativar Supervisor
sudo supervisorctl reread
sudo supervisorctl update

# Aguardar um pouco antes de iniciar
sleep 5

if [[ -f "$PROJECT_DIR/app.py" ]]; then
    sudo supervisorctl start scanner-cripto
    sleep 10
    
    # Verificar status
    if sudo supervisorctl status scanner-cripto | grep -q "RUNNING"; then
        success "Aplicação rodando com Supervisor!"
    else
        warn "Aplicação pode não estar rodando. Verifique logs."
        sudo supervisorctl status scanner-cripto
    fi
else
    warn "app.py não encontrado. Supervisor configurado mas não iniciado."
fi

# 16. Configurar atualizações automáticas
log "🔄 Configurando atualizações automáticas..."
sudo apt install -y unattended-upgrades
sudo systemctl enable unattended-upgrades

# 17. Criar scripts de gerenciamento
log "📝 Criando scripts de gerenciamento..."

# Script de deploy
cat > /home/cripto/deploy.sh <<EOF
#!/bin/bash
set -e

echo "🚀 Deploy rápido do Scanner Cripto na Contabo..."

cd $PROJECT_DIR

# Backup rápido
if [ -d "backup" ]; then
    rm -rf backup.old 2>/dev/null || true
    mv backup backup.old 2>/dev/null || true
fi
mkdir -p backup
cp -r app.py requirements.txt *.md backup/ 2>/dev/null || true

# Atualizar dependências
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Reiniciar aplicação
sudo supervisorctl restart scanner-cripto

# Aguardar inicialização
sleep 15

# Verificar status
if sudo supervisorctl status scanner-cripto | grep -q "RUNNING"; then
    echo "✅ Deploy concluído com sucesso!"
    echo "🌐 Acesse: http://\$(curl -s ifconfig.me)"
else
    echo "❌ Erro no deploy. Verificar logs:"
    sudo tail -20 /var/log/scanner-cripto.err.log
    exit 1
fi
EOF

chmod +x /home/cripto/deploy.sh

# Script de monitoramento
cat > /home/cripto/monitor.sh <<EOF
#!/bin/bash

echo "🖥️  === CONTABO VPS MONITOR ==="
echo "📅 \$(date)"
echo "🌍 Timezone: \$(timedatectl show --property=Timezone --value)"
echo

echo "💻 === CPU E MEMÓRIA ==="
echo "🔧 CPU: \$(nproc) cores"
echo "📊 Uso CPU: \$(top -bn1 | grep "Cpu(s)" | awk '{print \$2}' | cut -d'%' -f1)%"
echo "🧠 RAM Total: \$(free -h | awk 'NR==2{print \$2}')"
echo "📈 RAM Uso: \$(free | awk 'NR==2{printf "%.1f%%", \$3/\$2 * 100.0}')"
echo "💾 Swap: \$(free -h | awk 'NR==3{print \$3"/"\\$2}')"
echo

echo "💽 === ARMAZENAMENTO ==="
df -h / | awk 'NR==2{printf "📁 Disco: %s usado de %s (%.1f%%)\n", \$3, \$2, (\$3/\$2)*100}'
echo

echo "🌐 === REDE ==="
echo "📍 IP Público: \$(curl -s ifconfig.me 2>/dev/null || echo 'N/A')"
echo "🔌 Conexões ativas: \$(netstat -an | grep :80 | grep ESTABLISHED | wc -l)"
echo

echo "⚡ === APLICAÇÃO ==="
sudo supervisorctl status scanner-cripto
echo

echo "📊 === LOGS RECENTES ==="
echo "--- Últimas 3 linhas do log ---"
sudo tail -3 /var/log/scanner-cripto.out.log 2>/dev/null || echo "Log não encontrado"
echo

echo "🔥 === FIREWALL ==="
sudo ufw status | head -5
echo

echo "🛡️  === FAIL2BAN ==="
sudo fail2ban-client status | head -3 2>/dev/null || echo "Fail2ban não ativo"
EOF

chmod +x /home/cripto/monitor.sh

# Script de backup
cat > /home/cripto/backup.sh <<EOF
#!/bin/bash
BACKUP_DIR="/home/cripto/backups"
DATE=\$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="scanner-cripto-contabo-\$DATE"

echo "💾 Criando backup do Scanner Cripto..."

# Criar diretório de backup
mkdir -p \$BACKUP_DIR

# Backup da aplicação
cd /home/cripto/apps
tar -czf "\$BACKUP_DIR/\$BACKUP_NAME.tar.gz" \\
    --exclude='tabela-ind/venv' \\
    --exclude='tabela-ind/__pycache__' \\
    --exclude='tabela-ind/*.pyc' \\
    --exclude='tabela-ind/temp_data.json' \\
    --exclude='tabela-ind/.git' \\
    tabela-ind/

# Backup dos logs e configurações
tar -czf "\$BACKUP_DIR/\$BACKUP_NAME-system.tar.gz" \\
    /var/log/scanner-cripto.* \\
    /etc/nginx/sites-available/scanner-cripto \\
    /etc/supervisor/conf.d/scanner-cripto.conf \\
    /home/cripto/*.sh 2>/dev/null

# Manter apenas últimos 7 backups
cd \$BACKUP_DIR
ls -t scanner-cripto-contabo-*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm

echo "✅ Backup criado: \$BACKUP_NAME.tar.gz"
echo "📁 Local: \$BACKUP_DIR"
echo "📊 Tamanho: \$(du -h \$BACKUP_DIR/\$BACKUP_NAME.tar.gz | cut -f1)"
EOF

chmod +x /home/cripto/backup.sh

# 18. Configurar cron jobs
log "⏰ Configurando cron jobs..."
(crontab -l 2>/dev/null; echo "0 2 * * * /home/cripto/backup.sh") | crontab -
(crontab -l 2>/dev/null; echo "0 3 * * * /usr/bin/certbot renew --quiet") | crontab -

# 19. Verificações finais
log "🔍 Realizando verificações finais..."

# Verificar serviços
systemctl is-active --quiet nginx && success "Nginx ativo" || warn "Nginx inativo"
systemctl is-active --quiet supervisor && success "Supervisor ativo" || warn "Supervisor inativo"
systemctl is-active --quiet fail2ban && success "Fail2ban ativo" || warn "Fail2ban inativo"

# Verificar portas
netstat -tlnp | grep -q ":80 " && success "Porta 80 ativa" || warn "Porta 80 inativa"
netstat -tlnp | grep -q ":8501 " && success "Porta 8501 ativa" || warn "Porta 8501 inativa"

# 20. Informações finais
echo
echo "🎉 ==============================================="
echo "   DEPLOY CONTABO CONCLUÍDO COM SUCESSO!"
echo "==============================================="
echo
echo "🌐 ACESSO À APLICAÇÃO:"
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "obter_ip_manualmente")
echo "   📍 URL: http://$PUBLIC_IP"
echo "   🌍 Localização: Alemanha (Nuremberg)"
echo "   🔗 Diretório: $PROJECT_DIR"
echo
echo "🔧 ESPECIFICAÇÕES DA VPS:"
echo "   💻 CPU: $CPU_CORES cores"
echo "   🧠 RAM: ${MEMORY_GB}GB"
echo "   💾 Disk: ${DISK_GB}GB"
echo "   🌍 Timezone: $(timedatectl show --property=Timezone --value)"
echo
echo "⚡ COMANDOS ÚTEIS:"
echo "   🔄 Restart app:    sudo supervisorctl restart scanner-cripto"
echo "   📊 Monitor:        ./monitor.sh"
echo "   🚀 Deploy:         ./deploy.sh"
echo "   💾 Backup:         ./backup.sh"
echo "   📝 Logs:           sudo tail -f /var/log/scanner-cripto.out.log"
echo "   🌐 Status Nginx:   sudo systemctl status nginx"
echo
echo "🔒 SEGURANÇA:"
echo "   🚪 SSH Port: 2222 (não 22!)"
echo "   🛡️  Fail2ban: Ativo"
echo "   🔥 Firewall: UFW ativo"
echo "   🔐 Root login: Desabilitado"
echo
echo "📁 PRÓXIMOS PASSOS:"
if [[ ! -f "$PROJECT_DIR/app.py" ]]; then
    echo "   1. 📤 Upload do projeto:"
    echo "      scp tabela-ind.zip cripto@$PUBLIC_IP:/home/cripto/apps/"
    echo "   2. 🔄 Execute novamente: ./deploy_contabo.sh"
fi
echo "   3. 🌐 Configure domínio (opcional)"
echo "   4. 🔒 Configure SSL com certbot (opcional)"
echo "   5. 📊 Monitore com ./monitor.sh"
echo
echo "🎯 CONTABO VPS OTIMIZADA PARA SCANNER CRIPTO!"
echo "==============================================="

# 21. Teste final de conectividade
if [[ -f "$PROJECT_DIR/app.py" ]]; then
    log "🧪 Teste final de conectividade..."
    if curl -s http://localhost > /dev/null; then
        success "✅ Aplicação respondendo corretamente em http://$PUBLIC_IP"
    else
        warn "⚠️  Aplicação pode não estar totalmente funcional. Verificar logs:"
        echo "   sudo tail -20 /var/log/scanner-cripto.err.log"
    fi
fi

success "🎊 Deploy na CONTABO VPS finalizado!"
