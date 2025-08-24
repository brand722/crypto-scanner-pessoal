import pandas as pd
import numpy as np
import requests
import ccxt
import pandas_ta as ta
from datetime import datetime
import time
import warnings
warnings.filterwarnings('ignore')

def fetch_huobi_debug(timeframe="1h"):
    """Busca dados da HUOBI para debug"""
    try:
        # API v1 da HUOBI para tickers spot
        tickers_url = "https://api.huobi.pro/market/tickers"
        resp = requests.get(tickers_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("status") != "ok" or not data.get("data"):
            print("   ❌ Resposta inesperada da API da HUOBI")
            return pd.DataFrame()
        
        # Mapear timeframe
        timeframe_map = {
            "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "60min", "2h": "2hour", "4h": "4hour", "1d": "1day"
        }
        huobi_timeframe = timeframe_map.get(timeframe, "60min")
        
        # Pares alvo (formato HUOBI: btcusdt, ethusdt, etc.)
        target_pairs = ["btcusdt", "ethusdt", "solusdt", "xrpusdt", "adausdt"]
        results = []
        
        for symbol in target_pairs:
            try:
                klines_url = f"https://api.huobi.pro/market/history/kline"
                params = {
                    "symbol": symbol,
                    "period": huobi_timeframe,
                    "size": 50
                }
                
                kline_resp = requests.get(klines_url, params=params, timeout=10)
                kline_resp.raise_for_status()
                kline_data = kline_resp.json()
                
                if kline_data.get("status") != "ok" or not kline_data.get("data"):
                    continue
                
                klines = kline_data["data"]
                if len(klines) < 20:
                    continue
                
                # Criar DataFrame
                df = pd.DataFrame(klines)
                df = df[["id", "open", "high", "low", "close", "vol"]]
                df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
                
                # Converter tipos
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                df = df.dropna()
                
                # Reverter ordem (HUOBI retorna mais recentes primeiro)
                df = df.sort_values(by="timestamp").reset_index(drop=True)
                
                if len(df) < 20:
                    continue
                
                # Calcular indicadores
                df.ta.rsi(length=14, append=True)
                df.ta.uo(length=[7, 14, 28], append=True)
                
                # % change
                pct_change = ((df['close'].iloc[-1] - df['close'].iloc[-4]) / df['close'].iloc[-4]) * 100 if len(df) >= 4 else 0
                
                result = {
                    'symbol': symbol.upper().replace("USDT", "/USDT"),
                    'price': df['close'].iloc[-1],
                    'volume': df['volume'].iloc[-1],
                    'pct_change': pct_change,
                    'RSI': df['RSI_14'].iloc[-1] if 'RSI_14' in df.columns else 0,
                    'UO': df['UO_7_14_28'].iloc[-1] if 'UO_7_14_28' in df.columns else 0
                }
                results.append(result)
            except Exception as e:
                print(f"   ⚠️ Erro com {symbol}: {e}")
                continue
        
        return pd.DataFrame(results) if results else pd.DataFrame()
    except Exception as e:
        print(f"   ❌ Erro HUOBI geral: {e}")
        return pd.DataFrame()

def fetch_bingx_debug(timeframe="1h"):
    """Busca dados da BingX via CCXT para debug"""
    try:
        exchange = ccxt.bingx({
            'enableRateLimit': True,
            'sandbox': False,
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
            except Exception as e:
                print(f"   ⚠️ Erro com {symbol}: {e}")
                continue
                
        return pd.DataFrame(results) if results else pd.DataFrame()
    except Exception as e:
        print(f"   ❌ Erro BingX geral: {e}")
        return pd.DataFrame()

def debug_missing_exchanges():
    """
    Debug específico para PHEMEX, HUOBI e BingX
    """
    
    timeframe = "1h"
    target_pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"]
    
    print("🔍 DEBUG DAS EXCHANGES RESTANTES")
    print(f"📊 Timeframe: {timeframe}")
    print(f"🎯 Pares alvo: {', '.join(target_pairs)}")
    print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    results = {}
    
    # 1. Testar PHEMEX (via CCXT)
    print(f"\n🔄 Testando PHEMEX...")
    start_time = time.time()
    try:
        exchange = ccxt.phemex({
            'enableRateLimit': True,
            'sandbox': False,
        })
        
        markets = exchange.load_markets()
        target_symbols = []
        
        for symbol, market in markets.items():
            if (market.get('spot', False) and 
                market.get('quote', '') == 'USDT' and
                market.get('base', '') in ['BTC', 'ETH', 'SOL', 'XRP', 'ADA']):
                target_symbols.append(symbol)
        
        phemex_results = []
        for symbol in target_symbols[:5]:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=50)
                if len(ohlcv) >= 20:
                    df = pd.DataFrame(ohlcv)
                    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                    
                    df.ta.rsi(length=14, append=True)
                    df.ta.uo(length=[7, 14, 28], append=True)
                    
                    pct_change = ((df['close'].iloc[-1] - df['close'].iloc[-4]) / df['close'].iloc[-4]) * 100 if len(df) >= 4 else 0
                    
                    result = {
                        'symbol': symbol,
                        'price': df['close'].iloc[-1],
                        'volume': df['volume'].iloc[-1],
                        'pct_change': pct_change,
                        'RSI': df['RSI_14'].iloc[-1] if 'RSI_14' in df.columns else 0,
                        'UO': df['UO_7_14_28'].iloc[-1] if 'UO_7_14_28' in df.columns else 0
                    }
                    phemex_results.append(result)
            except:
                continue
        
        elapsed = time.time() - start_time
        if phemex_results:
            print(f"✅ PHEMEX: {len(phemex_results)} pares ({elapsed:.2f}s)")
            results['PHEMEX'] = phemex_results
        else:
            print(f"❌ PHEMEX: Falhou")
            results['PHEMEX'] = None
            
    except Exception as e:
        print(f"❌ PHEMEX: Erro - {e}")
        results['PHEMEX'] = None
    
    # 2. Testar HUOBI
    print(f"\n🔄 Testando HUOBI...")
    start_time = time.time()
    huobi_data = fetch_huobi_debug(timeframe)
    elapsed = time.time() - start_time
    
    if not huobi_data.empty:
        print(f"✅ HUOBI: {len(huobi_data)} pares ({elapsed:.2f}s)")
        results['HUOBI'] = huobi_data.to_dict('records')
    else:
        print(f"❌ HUOBI: Falhou")
        results['HUOBI'] = None
    
    # 3. Testar BingX
    print(f"\n🔄 Testando BingX...")
    start_time = time.time()
    bingx_data = fetch_bingx_debug(timeframe)
    elapsed = time.time() - start_time
    
    if not bingx_data.empty:
        print(f"✅ BingX: {len(bingx_data)} pares ({elapsed:.2f}s)")
        results['BingX'] = bingx_data.to_dict('records')
    else:
        print(f"❌ BingX: Falhou")
        results['BingX'] = None
    
    print("\n" + "=" * 80)
    print("📊 ANÁLISE COMPARATIVA")
    print("=" * 80)
    
    # Análise por par
    for target_pair in target_pairs:
        print(f"\n🪙 {target_pair}:")
        found_exchanges = []
        prices = []
        
        for exchange_name, exchange_data in results.items():
            if exchange_data:
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
            spread = ((max(prices) - min(prices)) / avg_price) * 100 if len(prices) > 1 else 0
            print(f"   📊 Resumo: {len(found_exchanges)} exchanges | Spread: {spread:.2f}%")
        else:
            print(f"   ❌ Não encontrado")
    
    # Resumo final
    print("\n" + "=" * 80)
    print("📋 RESUMO DAS EXCHANGES RESTANTES")
    print("=" * 80)
    
    working = [ex for ex, data in results.items() if data is not None]
    failed = [ex for ex, data in results.items() if data is None]
    
    print(f"✅ Funcionando: {len(working)}/3")
    if working:
        print(f"   {', '.join(working)}")
    
    if failed:
        print(f"❌ Com problemas: {len(failed)}/3")
        print(f"   {', '.join(failed)}")
    
    print("\n🏁 DEBUG DAS EXCHANGES RESTANTES CONCLUÍDO!")
    return results

if __name__ == "__main__":
    debug_results = debug_missing_exchanges() 