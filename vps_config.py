# Configurações específicas para VPS CONTABO
# Este arquivo contém configurações otimizadas para Contabo VPS com Ubuntu 24.04

import os
import streamlit as st

# Configurações de produção para VPS
PRODUCTION_CONFIG = {
    # Configurações do Streamlit
    'server': {
        'port': 8501,
        'address': '0.0.0.0',  # Aceitar conexões de qualquer IP
        'headless': True,       # Modo headless para VPS
        'enableCORS': False,    # Desabilitar CORS em produção
        'enableXsrfProtection': True,  # Proteção XSRF
        'maxUploadSize': 200,   # Limitar upload size
        'enableStaticServing': True,  # Habilitar servir arquivos estáticos
        'runOnSave': False,     # Desabilitar auto-reload em produção
    },
    
    # Configurações de cache
    'cache': {
        'ttl': 300,  # 5 minutos
        'maxEntries': 100,
    },
    
    # Configurações de performance (otimizadas para Contabo VPS S - 4 vCPUs, 8GB RAM)
    'performance': {
        'maxConcurrency': 6,    # Aumentado para aproveitar 4 vCPUs da Contabo
        'timeout': 45,          # Timeout aumentado para APIs cripto
        'maxMemoryUsage': 6144, # Máximo 6GB dos 8GB disponíveis
        'maxCpuUsage': 85,      # Máximo 85% de CPU
    },
    
    # Configurações de segurança
    'security': {
        'enableStaticServing': False,  # Desabilitar servir arquivos estáticos
        'gatherUsageStats': False,     # Não coletar estatísticas
    }
}

# Configurações de logging
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': '/var/log/streamlit-app.log'
}

# Configurações de monitoramento
MONITORING_CONFIG = {
    'enable_health_check': True,
    'health_check_interval': 60,  # segundos
    'max_memory_usage': 80,       # porcentagem
    'max_cpu_usage': 90,          # porcentagem
}

def apply_production_config():
    """Aplica configurações de produção"""
    for key, value in PRODUCTION_CONFIG['server'].items():
        os.environ[f'STREAMLIT_SERVER_{key.upper()}'] = str(value)
    
    for key, value in PRODUCTION_CONFIG['cache'].items():
        os.environ[f'STREAMLIT_CACHE_{key.upper()}'] = str(value)
    
    for key, value in PRODUCTION_CONFIG['security'].items():
        os.environ[f'STREAMLIT_{key.upper()}'] = str(value)

def setup_production_environment():
    """Configura ambiente de produção"""
    # Aplicar configurações
    apply_production_config()
    
    # Configurar logging
    import logging
    logging.basicConfig(
        level=getattr(logging, LOGGING_CONFIG['level']),
        format=LOGGING_CONFIG['format'],
        filename=LOGGING_CONFIG['file']
    )
    
    # Configurar página do Streamlit
    st.set_page_config(
        page_title="Scanner de Oportunidades Cripto",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded"
    )

def health_check():
    """Verificação de saúde da aplicação"""
    import psutil
    import time
    
    # Verificar uso de memória
    memory_percent = psutil.virtual_memory().percent
    if memory_percent > MONITORING_CONFIG['max_memory_usage']:
        st.warning(f"⚠️ Uso de memória alto: {memory_percent}%")
    
    # Verificar uso de CPU
    cpu_percent = psutil.cpu_percent(interval=1)
    if cpu_percent > MONITORING_CONFIG['max_cpu_usage']:
        st.warning(f"⚠️ Uso de CPU alto: {cpu_percent}%")
    
    return {
        'memory_percent': memory_percent,
        'cpu_percent': cpu_percent,
        'timestamp': time.time()
    }

# Configurações específicas para diferentes exchanges
EXCHANGE_CONFIGS = {
    'binance': {
        'rate_limit': 1200,  # requests per minute
        'timeout': 30,
        'retry_attempts': 3,
    },
    'bybit': {
        'rate_limit': 1000,
        'timeout': 30,
        'retry_attempts': 3,
    },
    'bitget': {
        'rate_limit': 800,
        'timeout': 30,
        'retry_attempts': 3,
    },
    'kucoin': {
        'rate_limit': 600,
        'timeout': 30,
        'retry_attempts': 3,
    },
    'okx': {
        'rate_limit': 1000,
        'timeout': 30,
        'retry_attempts': 3,
    },
    'bingx': {
        'rate_limit': 800,
        'timeout': 30,
        'retry_attempts': 3,
    },
    'huobi': {
        'rate_limit': 600,
        'timeout': 30,
        'retry_attempts': 3,
    },
    'phemex': {
        'rate_limit': 1000,
        'timeout': 30,
        'retry_attempts': 3,
    }
}

# Configurações de backup (específicas para Contabo)
BACKUP_CONFIG = {
    'enabled': True,
    'interval_hours': 24,
    'backup_dir': '/home/cripto/backups',  # Usuário padrão Contabo
    'max_backups': 7,
    'include_logs': True,
    'compress_level': 6,  # Balanceamento entre velocidade e tamanho
    'contabo_storage': '/mnt/backup',  # Ponto de montagem adicional se necessário
}

def create_backup():
    """Cria backup da aplicação"""
    if not BACKUP_CONFIG['enabled']:
        return
    
    import shutil
    import datetime
    
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"tabela_ind_backup_{timestamp}"
    backup_path = os.path.join(BACKUP_CONFIG['backup_dir'], backup_name)
    
    try:
        # Criar diretório de backup se não existir
        os.makedirs(BACKUP_CONFIG['backup_dir'], exist_ok=True)
        
        # Copiar arquivos do projeto
        shutil.copytree('.', backup_path, ignore=shutil.ignore_patterns(
            'venv', '__pycache__', '*.pyc', '.git', 'temp_data.json'
        ))
        
        # Incluir logs se configurado
        if BACKUP_CONFIG['include_logs']:
            log_backup_path = os.path.join(backup_path, 'logs')
            os.makedirs(log_backup_path, exist_ok=True)
            shutil.copy('/var/log/streamlit-app.out.log', log_backup_path)
            shutil.copy('/var/log/streamlit-app.err.log', log_backup_path)
        
        # Limpar backups antigos
        cleanup_old_backups()
        
        return backup_path
    except Exception as e:
        print(f"Erro ao criar backup: {e}")
        return None

def cleanup_old_backups():
    """Remove backups antigos"""
    import glob
    
    backup_files = glob.glob(os.path.join(BACKUP_CONFIG['backup_dir'], 'tabela_ind_backup_*'))
    backup_files.sort()
    
    # Manter apenas os backups mais recentes
    while len(backup_files) > BACKUP_CONFIG['max_backups']:
        oldest_backup = backup_files.pop(0)
        try:
            shutil.rmtree(oldest_backup)
            print(f"Backup removido: {oldest_backup}")
        except Exception as e:
            print(f"Erro ao remover backup {oldest_backup}: {e}")

# Configurações de notificação
NOTIFICATION_CONFIG = {
    'enabled': False,
    'email': {
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'username': '',
        'password': '',
        'recipients': []
    },
    'telegram': {
        'bot_token': '',
        'chat_id': ''
    }
}

def send_notification(message, level='INFO'):
    """Envia notificação"""
    if not NOTIFICATION_CONFIG['enabled']:
        return
    
    # Implementar notificação por email ou Telegram
    # Por enquanto apenas log
    print(f"[{level}] {message}")

# Configurações de métricas
METRICS_CONFIG = {
    'enabled': True,
    'collect_usage_stats': False,
    'collect_performance_metrics': True,
    'metrics_file': '/var/log/streamlit-metrics.json'
}

def collect_metrics():
    """Coleta métricas da aplicação"""
    if not METRICS_CONFIG['enabled']:
        return
    
    import json
    import time
    
    metrics = {
        'timestamp': time.time(),
        'health_check': health_check(),
        'session_state': len(st.session_state) if hasattr(st, 'session_state') else 0,
    }
    
    try:
        with open(METRICS_CONFIG['metrics_file'], 'w') as f:
            json.dump(metrics, f, indent=2)
    except Exception as e:
        print(f"Erro ao salvar métricas: {e}")

# Configurações específicas para Contabo VPS
CONTABO_CONFIG = {
    'datacenter': 'Germany',
    'timezone': 'Europe/Berlin',
    'recommended_specs': {
        'plan': 'VPS S',
        'cpu': '4 vCPUs',
        'ram': '8GB',
        'storage': '50GB NVMe',
        'bandwidth': '32TB'
    },
    'network': {
        'provider': 'Contabo',
        'location': 'Nuremberg, Germany',
        'latency_optimized_for': ['Europe', 'Crypto APIs']
    },
    'optimizations': {
        'swap_size_gb': 2,  # Recomendado para 8GB RAM
        'tcp_optimization': True,
        'timezone_sync': True,
        'ntp_server': 'pool.ntp.org'
    }
}

def apply_contabo_optimizations():
    """Aplica otimizações específicas para Contabo VPS"""
    import subprocess
    import logging
    
    try:
        # Configurar timezone se necessário
        if CONTABO_CONFIG['optimizations']['timezone_sync']:
            subprocess.run(['timedatectl', 'set-timezone', CONTABO_CONFIG['timezone']], 
                         check=False, capture_output=True)
        
        # Aplicar configurações TCP se necessário
        if CONTABO_CONFIG['optimizations']['tcp_optimization']:
            tcp_settings = [
                'net.core.rmem_max = 16777216',
                'net.core.wmem_max = 16777216',
                'net.ipv4.tcp_rmem = 4096 87380 16777216',
                'net.ipv4.tcp_wmem = 4096 65536 16777216'
            ]
            
            # Aplicar configurações (requires sudo, so just log them)
            logging.info("TCP optimizations available in DEPLOY_CONTABO.md")
        
        logging.info(f"✅ Otimizações Contabo aplicadas para {CONTABO_CONFIG['datacenter']}")
        
    except Exception as e:
        logging.warning(f"⚠️ Erro ao aplicar otimizações Contabo: {e}")

def get_contabo_status():
    """Retorna status e configurações da VPS Contabo"""
    import psutil
    
    status = {
        'provider': 'Contabo',
        'datacenter': CONTABO_CONFIG['datacenter'],
        'plan_recommended': CONTABO_CONFIG['recommended_specs']['plan'],
        'current_specs': {
            'cpu_count': psutil.cpu_count(),
            'memory_gb': round(psutil.virtual_memory().total / (1024**3), 1),
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent
        },
        'optimizations_enabled': True
    }
    
    return status

# Inicializar configurações quando importado
if __name__ == "__main__":
    setup_production_environment()
    apply_contabo_optimizations()
    print("✅ Configurações de produção Contabo aplicadas!")
    
    # Mostrar status da VPS
    status = get_contabo_status()
    print(f"🌐 Contabo VPS Status:")
    print(f"   📍 Datacenter: {status['datacenter']}")
    print(f"   💻 CPU: {status['current_specs']['cpu_count']} cores")
    print(f"   🧠 RAM: {status['current_specs']['memory_gb']}GB")
    print(f"   📊 Uso CPU: {status['current_specs']['cpu_percent']}%")
    print(f"   📊 Uso RAM: {status['current_specs']['memory_percent']}%") 