# 🚀 GUIA COMPLETO: Deploy na VPS - Scanner de Oportunidades Cripto

## 📋 Pré-requisitos da VPS

### Sistema Operacional
- **Ubuntu 20.04+** (recomendado)
- **Debian 11+** (alternativa)
- **CentOS 8+** (alternativa)

### Especificações Mínimas
- **CPU**: 2 cores
- **RAM**: 4GB
- **Storage**: 20GB
- **Rede**: Conexão estável com internet

## 🔧 Configuração Inicial da VPS

### 1. Atualizar Sistema
```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Instalar Dependências Básicas
```bash
sudo apt install -y python3 python3-pip python3-venv git curl wget nginx supervisor
```

### 3. Configurar Firewall
```bash
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw allow 8501  # Streamlit (temporário)
sudo ufw enable
```

## 📦 Deploy do Projeto

### 1. Clonar Repositório
```bash
cd /home/ubuntu
git clone https://github.com/seu-usuario/tabela-ind.git
cd tabela-ind
```

### 2. Configurar Ambiente Virtual
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Testar Aplicação Localmente
```bash
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

## 🌐 Configuração do Nginx (Proxy Reverso)

### 1. Criar Configuração do Nginx
```bash
sudo nano /etc/nginx/sites-available/streamlit-app
```

### 2. Conteúdo da Configuração
```nginx
server {
    listen 80;
    server_name seu-dominio.com;  # Substitua pelo seu domínio

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_connect_timeout 86400;
    }
}
```

### 3. Ativar Configuração
```bash
sudo ln -s /etc/nginx/sites-available/streamlit-app /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## 🔄 Configuração do Supervisor (Process Manager)

### 1. Criar Configuração do Supervisor
```bash
sudo nano /etc/supervisor/conf.d/streamlit-app.conf
```

### 2. Conteúdo da Configuração
```ini
[program:streamlit-app]
command=/home/ubuntu/tabela-ind/venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
directory=/home/ubuntu/tabela-ind
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/var/log/streamlit-app.err.log
stdout_logfile=/var/log/streamlit-app.out.log
environment=HOME="/home/ubuntu"
```

### 3. Ativar Supervisor
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start streamlit-app
```

## 🔒 Configuração de Segurança

### 1. Configurar SSL/HTTPS (Let's Encrypt)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d seu-dominio.com
```

### 2. Configuração de Segurança Adicional
```bash
# Atualizar configuração do Nginx para HTTPS
sudo nano /etc/nginx/sites-available/streamlit-app
```

```nginx
server {
    listen 443 ssl http2;
    server_name seu-dominio.com;

    ssl_certificate /etc/letsencrypt/live/seu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seu-dominio.com/privkey.pem;

    # Configurações de segurança SSL
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_connect_timeout 86400;
    }
}

# Redirecionar HTTP para HTTPS
server {
    listen 80;
    server_name seu-dominio.com;
    return 301 https://$server_name$request_uri;
}
```

### 3. Atualizar Firewall
```bash
sudo ufw delete allow 8501  # Remover acesso direto ao Streamlit
sudo ufw reload
```

## 📊 Monitoramento e Logs

### 1. Verificar Status da Aplicação
```bash
sudo supervisorctl status streamlit-app
```

### 2. Verificar Logs
```bash
# Logs do Supervisor
sudo tail -f /var/log/streamlit-app.out.log
sudo tail -f /var/log/streamlit-app.err.log

# Logs do Nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 3. Monitoramento de Recursos
```bash
# Instalar htop para monitoramento
sudo apt install htop
htop
```

## 🔄 Atualizações e Manutenção

### 1. Script de Deploy Automático
```bash
nano /home/ubuntu/deploy.sh
```

```bash
#!/bin/bash
cd /home/ubuntu/tabela-ind
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo supervisorctl restart streamlit-app
echo "Deploy concluído!"
```

### 2. Tornar Executável
```bash
chmod +x /home/ubuntu/deploy.sh
```

### 3. Cron para Renovação SSL
```bash
sudo crontab -e
# Adicionar linha:
0 12 * * * /usr/bin/certbot renew --quiet
```

## 🚨 Troubleshooting

### Problemas Comuns e Soluções

#### 1. Aplicação Não Inicia
```bash
# Verificar logs
sudo supervisorctl status streamlit-app
sudo tail -f /var/log/streamlit-app.err.log

# Verificar dependências
source venv/bin/activate
pip list
```

#### 2. Erro de Conexão
```bash
# Verificar se porta está aberta
sudo netstat -tlnp | grep 8501

# Verificar firewall
sudo ufw status
```

#### 3. Problemas de Performance
```bash
# Verificar uso de recursos
htop
df -h
free -h
```

## 📱 Configurações Específicas do Projeto

### 1. Variáveis de Ambiente (Opcional)
```bash
nano /home/ubuntu/tabela-ind/.env
```

```env
# Configurações do Streamlit
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
STREAMLIT_SERVER_HEADLESS=true

# Configurações de Cache
STREAMLIT_CACHE_TTL=300
```

### 2. Otimizações de Performance
```python
# Adicionar ao app.py se necessário
import os
os.environ['STREAMLIT_SERVER_MAX_UPLOAD_SIZE'] = '200'
```

## ✅ Checklist de Deploy

- [ ] VPS configurada com Ubuntu/Debian
- [ ] Dependências básicas instaladas
- [ ] Firewall configurado
- [ ] Projeto clonado e ambiente virtual criado
- [ ] Aplicação testada localmente
- [ ] Nginx configurado como proxy reverso
- [ ] Supervisor configurado para gerenciar processo
- [ ] SSL/HTTPS configurado
- [ ] Logs e monitoramento configurados
- [ ] Script de deploy criado
- [ ] Backup e renovação SSL configurados

## 🎯 Comandos Rápidos

```bash
# Reiniciar aplicação
sudo supervisorctl restart streamlit-app

# Ver status
sudo supervisorctl status

# Ver logs em tempo real
sudo tail -f /var/log/streamlit-app.out.log

# Deploy rápido
./deploy.sh

# Verificar recursos
htop
```

## 📞 Suporte

Para problemas específicos:
1. Verificar logs primeiro
2. Testar aplicação localmente
3. Verificar configurações de rede
4. Consultar documentação do Streamlit 