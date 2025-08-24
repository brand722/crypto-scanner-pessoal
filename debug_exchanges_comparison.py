import pandas as pd
import numpy as np
import requests
import ccxt
import pandas_ta as ta
from datetime import datetime
import time
import warnings
warnings.filterwarnings('ignore')

def fetch_binance_debug(timeframe="1h"):
    """Busca dados da Binance para debug"""
    try:
        # Buscar dados dos pares específicos
        pairs = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
        results = []
        
        for pair in pairs:
            url = f"https://api.binance.com/api/v3/klines?symbol={pair}&interval={timeframe}&limit=50"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                klines = response.json()
                if klines:
                    df = pd.DataFrame(klines)
                    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_volume', 'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore']
                    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].astype(float)
                    
                    if len(df) >= 20:
                        # Calcular RSI
                        df.ta.rsi(length=14, append=True)
                        df.ta.uo(length=[7, 14, 28], append=True)
                        
                        # Últimas 3 velas para % change
                        pct_change = ((df['close'].iloc[-1] - df['close'].iloc[-4]) / df['close'].iloc[-4]) * 100 if len(df) >= 4 else 0
                        
                        result = {
                            'symbol': pair.replace('USDT', '/USDT'),
                            'price': df['close'].iloc[-1],
                            'volume': df['volume'].iloc[-1],
                            'pct_change': pct_change,
                            'RSI': df['RSI_14'].iloc[-1] if 'RSI_14' in df.columns else 0,
                            'UO': df['UO_7_14_28'].iloc[-1] if 'UO_7_14_28' in df.columns else 0
                        }
                        results.append(result)
        
        return pd.DataFrame(results) if results else pd.DataFrame()
    except Exception as e:
        print(f"Erro Binance: {e}")
        return pd.DataFrame()

def fetch_ccxt_debug(exchange_name, timeframe="1h"):
    """Busca dados via CCXT para outras exchanges"""
    try:
        # Inicializar exchange
        exchange_classes = {
            'bybit': ccxt.bybit,
            'bitget': ccxt.bitget,
            'kucoin': ccxt.kucoin,
            'okx': ccxt.okx,
            'phemex': ccxt.phemex
        }
        
        if exchange_name.lower() not in exchange_classes:
            return pd.DataFrame()
            
        exchange = exchange_classes[exchange_name.lower()]({
            'enableRateLimit': True,
            'sandbox': False
        })
        
        markets = exchange.load_markets()
        target_symbols = []
        
        # Encontrar símbolos equivalentes
        for symbol, market in markets.items():
            if (market.get('spot', False) and 
                market.get('quote', '') == 'USDT' and
                market.get('base', '') in ['BTC', 'ETH', 'SOL', 'XRP', 'ADA']):
                target_symbols.append(symbol)
        
        results = []
        for symbol in target_symbols[:5]:  # Máximo 5
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=50)
                if len(ohlcv) >= 20:
                    df = pd.DataFrame(ohlcv)
                    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                    
                    # Calcular indicadores básicos
                    df.ta.rsi(length=14, append=True)
                    df.ta.uo(length=[7, 14, 28], append=True)
                    
                    # % change
                    pct_change = ((df['close'].iloc[-1] - df['close'].iloc[-4]) / df['close'].iloc[-4]) * 100 if len(df) >= 4 else 0
                    
                    result = {
                        'symbol': symbol,
                        'price': df['close'].iloc[-1],
                        'volume': df['volume'].iloc[-1],
                        'pct_change': pct_change,
                        'RSI': df['RSI_14'].iloc[-1] if 'RSI_14' in df.columns else 0,
                        'UO': df['UO_7_14_28'].iloc[-1] if 'UO_7_14_28' in df.columns else 0
                    }
                    results.append(result)
            except:
                continue
                
        return pd.DataFrame(results) if results else pd.DataFrame()
    except Exception as e:
        print(f"Erro {exchange_name}: {e}")
        return pd.DataFrame()

def debug_exchanges_comparison():
    """
    Debug das 8 exchanges comparando 5 pares específicos: BTC, ETH, SOL, XRP, ADA
    """
    
    # Configurações
    timeframe = "1h"  # Usar 1h para ter dados mais estáveis
    target_pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"]
    
    print("🔍 INICIANDO DEBUG SIMPLIFICADO DAS EXCHANGES")
    
    print("🔍 INICIANDO DEBUG DAS EXCHANGES")
    print(f"📊 Timeframe: {timeframe}")
    print(f"🎯 Pares alvo: {', '.join(target_pairs)}")
    print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Estrutura para armazenar resultados
    results = {}
    
    # 1. Testar Binance
    print(f"\n🔄 Testando Binance...")
    start_time = time.time()
    binance_data = fetch_binance_debug(timeframe)
    elapsed = time.time() - start_time
    
    if not binance_data.empty:
        print(f"✅ Binance: {len(binance_data)} pares ({elapsed:.2f}s)")
        results['Binance'] = binance_data.to_dict('records')
    else:
        print(f"❌ Binance: Falhou")
        results['Binance'] = None
    
    # 2. Testar exchanges via CCXT
    ccxt_exchanges = ['bybit', 'bitget', 'kucoin', 'okx', 'phemex']
    
    for exchange_name in ccxt_exchanges:
        print(f"\n�� Testando {exchange_name.title()}...")
        start_time = time.time()
        data = fetch_ccxt_debug(exchange_name, timeframe)
        elapsed = time.time() - start_time
        
        if not data.empty:
            print(f"✅ {exchange_name.title()}: {len(data)} pares ({elapsed:.2f}s)")
            results[exchange_name.title()] = data.to_dict('records')
        else:
            print(f"❌ {exchange_name.title()}: Falhou")
            results[exchange_name.title()] = None
     
    print("\n" + "=" * 80)
    print("📊 ANÁLISE COMPARATIVA DOS RESULTADOS")
    print("=" * 80)
    
    # Análise por par
    for target_pair in target_pairs:
        print(f"\n🪙 {target_pair}:")
        found_exchanges = []
        prices = []
        
        for exchange_name, exchange_data in results.items():
            if exchange_data:
                # Procurar o par (pode ter formatos diferentes)
                pair_found = None
                for record in exchange_data:
                    symbol = record['symbol']
                    if (target_pair == symbol or 
                        target_pair.replace('/', '') == symbol.replace('/', '') or
                        target_pair.replace('/', '-') == symbol or
                        target_pair.replace('/', '_') == symbol):
                        pair_found = record
                        break
                
                if pair_found:
                    found_exchanges.append(exchange_name)
                    prices.append(pair_found['price'])
                    print(f"   {exchange_name}: ${pair_found['price']:.6f} | RSI:{pair_found['RSI']:.1f} | %:{pair_found['pct_change']:.2f}%")
        
        if prices:
            avg_price = np.mean(prices)
            spread = ((max(prices) - min(prices)) / avg_price) * 100
            print(f"   📊 Resumo: {len(found_exchanges)} exchanges | Spread: {spread:.2f}%")
        else:
            print(f"   ❌ Não encontrado")
     
    # Resumo geral
    print("\n" + "=" * 80)
    print("📋 RESUMO GERAL")
    print("=" * 80)
    
    working_exchanges = [ex for ex, data in results.items() if data is not None]
    failed_exchanges = [ex for ex, data in results.items() if data is None]
    
    print(f"✅ Exchanges funcionando: {len(working_exchanges)}/8")
    if working_exchanges:
        print(f"   {', '.join(working_exchanges)}")
    
    if failed_exchanges:
        print(f"❌ Exchanges com problemas: {len(failed_exchanges)}/8")
        print(f"   {', '.join(failed_exchanges)}")
    
    print("\n🏁 DEBUG CONCLUÍDO!")
    return results

if __name__ == "__main__":
    debug_results = debug_exchanges_comparison() 