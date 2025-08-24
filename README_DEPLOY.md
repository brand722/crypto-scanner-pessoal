# 🚀 Deploy na VPS - Scanner de Oportunidades Cripto

## 📋 Resumo Rápido

Este projeto é um scanner de oportunidades de trading em criptomoedas desenvolvido em Python com Streamlit. Este guia mostra como fazer o deploy em uma VPS para acesso remoto.

## 🎯 Funcionalidades

- **Scanner Multi-Exchange**: Binance, Bybit, Bitget, KuCoin, OKX, BingX, Huobi, Phemex
- **Indicadores Técnicos**: RSI, MACD, UO, AO, CMO, KVO, OBV, CMF, DMI
- **Interface Interativa**: Filtros avançados e tabela responsiva
- **Atualização Automática**: Dados em tempo real com refresh automático
- **Links TradingView**: Integração direta com gráficos

## 🖥️ Pré-requisitos da VPS

### Especificações Mínimas
- **CPU**: 2 cores
- **RAM**: 4GB
- **Storage**: 20GB
- **Sistema**: Ubuntu 20.04+ ou Debian 11+

### Conexão
- **Internet**: Estável para APIs de exchanges
- **Portas**: 22 (SSH), 80 (HTTP), 443 (HTTPS)

## ⚡ Deploy Rápido (Recomendado)

### 1. Conectar na VPS
```bash
ssh usuario@ip-da-vps
```

### 2. Baixar e Executar Script Automatizado
```bash
# Baixar projeto
git clone https://github.com/seu-usuario/tabela-ind.git
cd tabela-ind

# Executar deploy automatizado
chmod +x deploy_vps.sh
./deploy_vps.sh
```

### 3. Acessar Aplicação
- **URL Local**: http://localhost:8501
- **URL Pública**: http://IP-DA-VPS:8501
- **Com Domínio**: https://seu-dominio.com (se configurado SSL)

## 🔧 Deploy Manual (Passo a Passo)

### 1. Preparar Sistema
```bash
# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependências
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor
```

### 2. Configurar Projeto
```bash
# Clonar projeto
cd /home/ubuntu
git clone https://github.com/seu-usuario/tabela-ind.git
cd tabela-ind

# Ambiente virtual
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar Nginx
```bash
sudo nano /etc/nginx/sites-available/streamlit-app
```

```nginx
server {
    listen 80;
    server_name _;

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

```bash
# Ativar configuração
sudo ln -s /etc/nginx/sites-available/streamlit-app /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 4. Configurar Supervisor
```bash
sudo nano /etc/supervisor/conf.d/streamlit-app.conf
```

```ini
[program:streamlit-app]
command=/home/ubuntu/tabela-ind/venv/bin/streamlit run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
directory=/home/ubuntu/tabela-ind
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/var/log/streamlit-app.err.log
stdout_logfile=/var/log/streamlit-app.out.log
```

```bash
# Ativar supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start streamlit-app
```

## 🔒 Configuração de Segurança

### 1. Firewall
```bash
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw enable
```

### 2. SSL/HTTPS (Opcional)
```bash
# Instalar Certbot
sudo apt install certbot python3-certbot-nginx

# Configurar SSL
sudo certbot --nginx -d seu-dominio.com
```

## 📊 Monitoramento

### Verificar Status
```bash
# Status da aplicação
sudo supervisorctl status streamlit-app

# Logs em tempo real
sudo tail -f /var/log/streamlit-app.out.log

# Logs de erro
sudo tail -f /var/log/streamlit-app.err.log
```

### Comandos Úteis
```bash
# Reiniciar aplicação
sudo supervisorctl restart streamlit-app

# Ver status do supervisor
sudo supervisorctl status

# Ver logs do Nginx
sudo tail -f /var/log/nginx/access.log
```

## 🔄 Atualizações

### Script de Deploy Automático
```bash
# Criar script
nano deploy.sh
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

```bash
# Tornar executável
chmod +x deploy.sh

# Executar atualização
./deploy.sh
```

## 🚨 Troubleshooting

### Problemas Comuns

#### 1. Aplicação Não Inicia
```bash
# Verificar logs
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
# Verificar recursos
htop
df -h
free -h
```

### Logs Importantes
- **Aplicação**: `/var/log/streamlit-app.out.log`
- **Erros**: `/var/log/streamlit-app.err.log`
- **Nginx**: `/var/log/nginx/access.log`
- **Sistema**: `journalctl -u supervisor`

## 📱 Configurações Avançadas

### Variáveis de Ambiente
```bash
nano .env
```

```env
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
STREAMLIT_SERVER_HEADLESS=true
STREAMLIT_CACHE_TTL=300
```

### Backup Automático
```bash
# Configurar cron para backup diário
crontab -e

# Adicionar linha:
0 2 * * * /home/ubuntu/tabela-ind/backup.sh
```

## 🎯 Checklist de Deploy

- [ ] VPS configurada com Ubuntu/Debian
- [ ] Dependências básicas instaladas
- [ ] Projeto clonado e ambiente virtual criado
- [ ] Aplicação testada localmente
- [ ] Nginx configurado como proxy reverso
- [ ] Supervisor configurado para gerenciar processo
- [ ] Firewall configurado
- [ ] SSL/HTTPS configurado (opcional)
- [ ] Logs e monitoramento configurados
- [ ] Script de deploy criado
- [ ] Backup configurado

## 📞 Suporte

### Recursos Úteis
- **Documentação Streamlit**: https://docs.streamlit.io/
- **Documentação Nginx**: https://nginx.org/en/docs/
- **Documentação Supervisor**: http://supervisord.org/

### Comandos de Emergência
```bash
# Parar tudo
sudo supervisorctl stop streamlit-app
sudo systemctl stop nginx

# Reiniciar tudo
sudo systemctl restart nginx
sudo supervisorctl restart streamlit-app

# Verificar status geral
sudo systemctl status nginx
sudo supervisorctl status
```

## 🎉 Pronto!

Após seguir este guia, sua aplicação estará rodando na VPS e acessível remotamente. A aplicação será reiniciada automaticamente em caso de falha e os logs estarão disponíveis para monitoramento.

**URL de Acesso**: http://IP-DA-VPS ou https://seu-dominio.com 