#!/bin/bash

# 🚀 Script de Deploy Automatizado para VPS
# Scanner de Oportunidades Cripto

set -e  # Parar em caso de erro

echo "🚀 Iniciando deploy do Scanner de Oportunidades Cripto..."

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função para log colorido
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# Verificar se está rodando como root
if [[ $EUID -eq 0 ]]; then
   error "Este script não deve ser executado como root. Use um usuário com sudo."
fi

# Verificar sistema operacional
if [[ ! -f /etc/os-release ]]; then
    error "Sistema operacional não suportado"
fi

source /etc/os-release
if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
    warn "Sistema operacional não testado: $ID. Continuando..."
fi

log "Sistema detectado: $ID $VERSION_ID"

# 1. Atualizar sistema
log "📦 Atualizando sistema..."
sudo apt update && sudo apt upgrade -y

# 2. Instalar dependências
log "🔧 Instalando dependências..."
sudo apt install -y python3 python3-pip python3-venv git curl wget nginx supervisor htop

# 3. Configurar firewall
log "🔥 Configurando firewall..."
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw allow 8501  # Streamlit (temporário)
sudo ufw --force enable

# 4. Criar diretório do projeto
PROJECT_DIR="/home/$USER/tabela-ind"
log "📁 Configurando diretório do projeto: $PROJECT_DIR"

if [[ -d "$PROJECT_DIR" ]]; then
    log "Diretório já existe. Fazendo backup..."
    mv "$PROJECT_DIR" "${PROJECT_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
fi

mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# 5. Copiar arquivos do projeto
log "📋 Copiando arquivos do projeto..."
# Assumindo que o script está sendo executado do diretório do projeto
cp -r . "$PROJECT_DIR/" 2>/dev/null || {
    log "Arquivos não encontrados no diretório atual. Clonando do Git..."
    git clone https://github.com/seu-usuario/tabela-ind.git .
}

# 6. Configurar ambiente virtual
log "🐍 Configurando ambiente virtual Python..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 7. Testar aplicação
log "🧪 Testando aplicação..."
timeout 30s streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true &
STREAMLIT_PID=$!
sleep 10

if kill -0 $STREAMLIT_PID 2>/dev/null; then
    log "✅ Aplicação iniciada com sucesso"
    kill $STREAMLIT_PID
else
    error "❌ Falha ao iniciar aplicação"
fi

# 8. Configurar Nginx
log "🌐 Configurando Nginx..."
sudo tee /etc/nginx/sites-available/streamlit-app > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header Host \$host;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_connect_timeout 86400;
    }
}
EOF

# Ativar configuração
sudo ln -sf /etc/nginx/sites-available/streamlit-app /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# 9. Configurar Supervisor
log "🔄 Configurando Supervisor..."
sudo tee /etc/supervisor/conf.d/streamlit-app.conf > /dev/null <<EOF
[program:streamlit-app]
command=$PROJECT_DIR/venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
directory=$PROJECT_DIR
user=$USER
autostart=true
autorestart=true
stderr_logfile=/var/log/streamlit-app.err.log
stdout_logfile=/var/log/streamlit-app.out.log
environment=HOME="/home/$USER"
EOF

# Ativar Supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start streamlit-app

# 10. Aguardar aplicação iniciar
log "⏳ Aguardando aplicação iniciar..."
sleep 10

# 11. Verificar status
if sudo supervisorctl status streamlit-app | grep -q "RUNNING"; then
    log "✅ Aplicação rodando com sucesso!"
else
    error "❌ Falha ao iniciar aplicação via Supervisor"
fi

# 12. Configurar SSL (opcional)
read -p "🔒 Deseja configurar SSL/HTTPS com Let's Encrypt? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log "🔒 Configurando SSL..."
    sudo apt install -y certbot python3-certbot-nginx
    
    read -p "🌐 Digite seu domínio (ex: meusite.com): " DOMAIN
    if [[ -n "$DOMAIN" ]]; then
        sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@$DOMAIN
        log "✅ SSL configurado para $DOMAIN"
    else
        warn "Domínio não fornecido. SSL não configurado."
    fi
fi

# 13. Criar script de deploy
log "📝 Criando script de deploy..."
tee deploy.sh > /dev/null <<EOF
#!/bin/bash
cd $PROJECT_DIR
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo supervisorctl restart streamlit-app
echo "✅ Deploy concluído!"
EOF

chmod +x deploy.sh

# 14. Configurar renovação SSL automática
if command -v certbot &> /dev/null; then
    log "🔄 Configurando renovação automática SSL..."
    (crontab -l 2>/dev/null; echo "0 12 * * * /usr/bin/certbot renew --quiet") | crontab -
fi

# 15. Informações finais
log "🎉 Deploy concluído com sucesso!"
echo
echo "📊 Informações da aplicação:"
echo "   🌐 URL local: http://localhost:8501"
echo "   🌐 URL pública: http://$(curl -s ifconfig.me):8501"
echo "   📁 Diretório: $PROJECT_DIR"
echo "   🔄 Supervisor: sudo supervisorctl status streamlit-app"
echo "   📝 Logs: sudo tail -f /var/log/streamlit-app.out.log"
echo "   🚀 Deploy: ./deploy.sh"
echo
echo "🔧 Comandos úteis:"
echo "   sudo supervisorctl restart streamlit-app  # Reiniciar aplicação"
echo "   sudo supervisorctl status                 # Ver status"
echo "   sudo tail -f /var/log/streamlit-app.err.log  # Ver erros"
echo "   htop                                      # Monitorar recursos"
echo

# 16. Teste final
log "🧪 Realizando teste final..."
if curl -s http://localhost:8501 > /dev/null; then
    log "✅ Aplicação respondendo corretamente!"
else
    warn "⚠️  Aplicação pode não estar respondendo. Verifique os logs."
fi

log "🎯 Deploy finalizado! Acesse http://localhost:8501 para usar a aplicação." 