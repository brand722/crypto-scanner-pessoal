#!/usr/bin/env python3
"""
Debug específico para comparar indicadores da Bybit vs Binance
"""
import pandas as pd
import numpy as np
from app import (
    get_binance_data,
    get_bybit_data,
    get_rsi_period,
    compute_indicators
)

def debug_bybit_vs_binance(timeframe='1h', symbols_to_check=['BTC/USDT', 'ETH/USDT', 'SOL/USDT']):
    """
    Compara os indicadores da Bybit vs Binance para symbols específicos
    """
    print(f"=== DEBUG BYBIT vs BINANCE - {timeframe} ===\n")
    
    # Buscar dados das duas exchanges
    print("🔄 Buscando dados da Binance...")
    binance_data = get_binance_data(timeframe, top_n=50)
    
    print("🔄 Buscando dados da Bybit...")
    bybit_data = get_bybit_data(timeframe, top_n=50)
    
    if binance_data.empty:
        print("❌ Erro: Dados da Binance estão vazios")
        return
    
    if bybit_data.empty:
        print("❌ Erro: Dados da Bybit estão vazios")
        return
    
    print(f"✅ Binance: {len(binance_data)} moedas")
    print(f"✅ Bybit: {len(bybit_data)} moedas")
    
    # Verificar colunas disponíveis
    print(f"\n=== COLUNAS DISPONÍVEIS ===")
    print(f"Binance: {list(binance_data.columns)}")
    print(f"Bybit: {list(bybit_data.columns)}")
    
    # Comparar para cada símbolo
    rsi_period = get_rsi_period(timeframe)
    rsi_col = f'RSI_{rsi_period}'
    
    print(f"\n=== COMPARAÇÃO DETALHADA ===")
    
    for symbol in symbols_to_check:
        print(f"\n--- {symbol} ---")
        
        # Filtrar dados do símbolo
        binance_row = binance_data[binance_data['symbol'] == symbol]
        bybit_row = bybit_data[bybit_data['symbol'] == symbol]
        
        if binance_row.empty:
            print(f"❌ {symbol} não encontrado na Binance")
            continue
            
        if bybit_row.empty:
            print(f"❌ {symbol} não encontrado na Bybit")
            continue
        
        # Extrair valores
        binance_vals = binance_row.iloc[0]
        bybit_vals = bybit_row.iloc[0]
        
        # Comparar preços
        binance_price = binance_vals.get('close', binance_vals.get('price', 'N/A'))
        bybit_price = bybit_vals.get('close', bybit_vals.get('price', 'N/A'))
        
        print(f"📊 Preços:")
        print(f"  Binance: {binance_price}")
        print(f"  Bybit:   {bybit_price}")
        
        if isinstance(binance_price, (int, float)) and isinstance(bybit_price, (int, float)):
            price_diff = abs(binance_price - bybit_price)
            price_diff_pct = (price_diff / binance_price) * 100 if binance_price != 0 else 0
            print(f"  Diferença: {price_diff:.2f} ({price_diff_pct:.2f}%)")
        
        # Comparar indicadores
        indicators = [rsi_col, 'UO_7_14_28', 'AO', 'CMO', 'KVO', 'KVO_trigger', 'OBV', 'CMF']
        
        print(f"📈 Indicadores:")
        for indicator in indicators:
            binance_val = binance_vals.get(indicator, 'N/A')
            bybit_val = bybit_vals.get(indicator, 'N/A')
            
            print(f"  {indicator}:")
            print(f"    Binance: {binance_val}")
            print(f"    Bybit:   {bybit_val}")
            
            # Calcular diferença se ambos são numéricos
            if isinstance(binance_val, (int, float)) and isinstance(bybit_val, (int, float)):
                diff = abs(binance_val - bybit_val)
                diff_pct = (diff / abs(binance_val)) * 100 if binance_val != 0 else 0
                print(f"    Diferença: {diff:.4f} ({diff_pct:.2f}%)")
                
                # Alerta para grandes diferenças
                if diff_pct > 10:
                    print(f"    ⚠️ GRANDE DIFERENÇA! ({diff_pct:.2f}%)")
            elif binance_val != bybit_val:
                print(f"    ❌ Valores incompatíveis!")

def debug_raw_data_comparison(timeframe='1h', symbol='BTC/USDT'):
    """
    Compara dados brutos (velas) entre Binance e Bybit
    """
    print(f"\n=== DEBUG DADOS BRUTOS - {symbol} - {timeframe} ===")
    
    # Importar requests para buscar dados brutos
    import requests
    
    # Buscar dados brutos da Binance
    print("🔄 Buscando dados brutos da Binance...")
    binance_symbol = symbol.replace('/', '')
    binance_url = f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval={timeframe}&limit=5"
    
    try:
        binance_resp = requests.get(binance_url, timeout=10)
        binance_klines = binance_resp.json()
        
        print("📊 Binance - Últimas 5 velas:")
        for i, kline in enumerate(binance_klines[-5:]):
            print(f"  Vela {i+1}: O={kline[1]} H={kline[2]} L={kline[3]} C={kline[4]} V={kline[5]}")
    except Exception as e:
        print(f"❌ Erro ao buscar Binance: {e}")
    
    # Buscar dados brutos da Bybit
    print("\n🔄 Buscando dados brutos da Bybit...")
    
    # Mapear timeframe para Bybit
    tf_map = {"5m": "5", "15m": "15", "30m": "30", "1h": "60", "2h": "120", "4h": "240", "1d": "D"}
    bybit_interval = tf_map.get(timeframe, "60")
    
    bybit_symbol = symbol.replace('/', '')
    bybit_url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={bybit_symbol}&interval={bybit_interval}&limit=5"
    
    try:
        bybit_resp = requests.get(bybit_url, timeout=10)
        bybit_data = bybit_resp.json()
        
        if bybit_data.get("retCode") == 0:
            bybit_klines = bybit_data["result"]["list"]
            bybit_klines.reverse()  # Bybit retorna em ordem reversa
            
            print("📊 Bybit - Últimas 5 velas:")
            for i, kline in enumerate(bybit_klines[-5:]):
                print(f"  Vela {i+1}: O={kline[1]} H={kline[2]} L={kline[3]} C={kline[4]} V={kline[5]}")
        else:
            print(f"❌ Erro na API Bybit: {bybit_data}")
    except Exception as e:
        print(f"❌ Erro ao buscar Bybit: {e}")

if __name__ == "__main__":
    # Debug principal
    debug_bybit_vs_binance(timeframe='1h', symbols_to_check=['BTC/USDT', 'ETH/USDT', 'SOL/USDT'])
    
    # Debug dados brutos
    debug_raw_data_comparison(timeframe='1h', symbol='BTC/USDT')
    
    print("\n" + "="*60)
    print("POSSÍVEIS CAUSAS DE DIVERGÊNCIA:")
    print("="*60)
    print("1. APIs retornam dados de timestamps ligeiramente diferentes")
    print("2. Diferenças na precisão dos dados (casas decimais)")
    print("3. Ordem dos dados (mais recente primeiro vs mais antigo primeiro)")
    print("4. Formatos diferentes de volume/turnover")
    print("5. Fusos horários diferentes nos timestamps")
    print("6. Períodos de velas não sincronizados entre exchanges") 