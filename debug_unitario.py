import pandas as pd
from app import (
    get_binance_data,
    get_bybit_data,
    get_bitget_data,
    get_kucoin_data,
    get_okx_data,
    get_bingx_data,
    get_huobi_data,
    get_phemex_data,
    get_rsi_period
)

# --- Configurações do Teste ---
TIMEFRAME = '1h'
SYMBOLS_TO_CHECK = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
TOP_N_COINS = 20 # Buscar um número menor de moedas para agilizar o teste
RSI_PERIOD = get_rsi_period(TIMEFRAME)
INDICATORS_TO_CHECK = [f'RSI_{RSI_PERIOD}', 'UO_7_14_28', 'AO']

EXCHANGE_FUNCTIONS = {
    "Binance": get_binance_data,
    "Bybit": get_bybit_data,
    "Bitget": get_bitget_data,
    "KuCoin": get_kucoin_data,
    "OKX": get_okx_data,
    "BingX": get_bingx_data,
    "HUOBI": get_huobi_data,
    "PHEMEX": get_phemex_data,
}

def run_debug():
    """
    Executa um teste unitário em todas as exchanges, comparando os
    valores dos indicadores para moedas de referência.
    """
    all_results = []

    print(f"--- Iniciando Depuração Unitária ---")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"Moedas: {', '.join(SYMBOLS_TO_CHECK)}")
    print("-" * 35)

    for exchange_name, fetch_function in EXCHANGE_FUNCTIONS.items():
        print(f"🔍 Testando {exchange_name}...")
        try:
            # Buscar dados da exchange
            df = fetch_function(timeframe=TIMEFRAME, top_n=TOP_N_COINS)

            if df.empty:
                print(f"  ❌ {exchange_name}: Nenhum dado retornado.")
                continue

            # Filtrar para as moedas de interesse
            
            # Ajuste para KuCoin e outros que podem ter formatos diferentes
            df['symbol_std'] = df['symbol'].str.replace('-', '/')
            
            filtered_df = df[df['symbol_std'].isin(SYMBOLS_TO_CHECK)]

            if filtered_df.empty:
                print(f"  ⚠️ {exchange_name}: Nenhuma das moedas de referência encontrada no top {TOP_N_COINS}.")
                continue

            for symbol in SYMBOLS_TO_CHECK:
                symbol_data = filtered_df[filtered_df['symbol_std'] == symbol]
                if not symbol_data.empty:
                    result = {
                        'Exchange': exchange_name,
                        'Symbol': symbol,
                        'Close': symbol_data['close'].iloc[0]
                    }
                    for indicator in INDICATORS_TO_CHECK:
                        if indicator in symbol_data.columns:
                            result[indicator] = symbol_data[indicator].iloc[0]
                        else:
                            result[indicator] = 'N/A'
                    all_results.append(result)
            print(f"  ✅ {exchange_name}: Teste concluído.")

        except Exception as e:
            print(f"  🚨 ERRO em {exchange_name}: {e}")

    if not all_results:
        print("\nNenhum resultado para exibir. Verifique as configurações.")
        return

    # --- Processar e Exibir Resultados ---
    results_df = pd.DataFrame(all_results)
    
    # Pivotar a tabela para comparar lado a lado
    for indicator in ['Close'] + INDICATORS_TO_CHECK:
        print(f"\n\n--- Comparativo: {indicator} ---")
        
        pivot_df = results_df.pivot(index='Symbol', columns='Exchange', values=indicator)
        
        # Formatação para melhor visualização
        if indicator != 'Close':
             print(pivot_df.to_string(float_format="%.2f"))
        else:
             print(pivot_df.to_string(float_format="%.2f"))


if __name__ == "__main__":
    run_debug() 