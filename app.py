import streamlit as st
import pandas as pd
import ccxt
import pandas_ta as ta

# Configuração da página
st.set_page_config(
    page_title="Scanner de Oportunidades Cripto",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Funções de Lógica ---

@st.cache_data(ttl=600) # Cache de 10 minutos
def get_binance_data(timeframe, top_n=200):
    """
    Busca e processa dados da Binance para as top N moedas do mercado de futuros perpétuos.
    Calcula os indicadores RSI e MACD.
    """
    try:
        exchange = ccxt.binance({
            'options': {
                'defaultType': 'future',  # Especifica o mercado de futuros
            },
            'hostname': 'binance.com', # Força um domínio para evitar bloqueio geográfico
        })
        
        # 1. Buscar todos os mercados e filtrar por Futuros Perpétuos com par USDT
        markets = exchange.load_markets()
        usdt_pairs = {
            s: m for s, m in markets.items() 
            if m.get('swap') and m.get('linear') and m.get('quoteId') == 'USDT'
        }
        
        if not usdt_pairs:
            st.error("Nenhum par de futuros perpétuos com USDT encontrado.")
            return pd.DataFrame()

        # 2. Buscar tickers para pegar o volume e ordenar
        tickers = exchange.fetch_tickers(list(usdt_pairs.keys()))
        
        # Filtrar tickers que não tem volume
        valid_tickers = {s: t for s, t in tickers.items() if t and t.get('quoteVolume') is not None}
        
        # Ordenar por volume e pegar o top N
        sorted_symbols = sorted(valid_tickers, key=lambda s: valid_tickers[s]['quoteVolume'], reverse=True)
        top_symbols = sorted_symbols[:top_n]
        
        all_data = []
        
        # 3. Para cada símbolo no top N, buscar os dados de velas
        for symbol in top_symbols:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100) # Pegar 100 velas para calcular indicadores
            if len(ohlcv) < 20: # Checagem mínima para ter dados suficientes
                continue
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['symbol'] = symbol
            
            # 4. Calcular Indicadores com pandas-ta
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            
            all_data.append(df.iloc[-1:]) # Pegar apenas a última linha (vela atual) com os indicadores calculados
            
        if not all_data:
            st.warning("Não foi possível obter dados para os principais pares. Tente outro tempo gráfico.")
            return pd.DataFrame()
            
        # Concatenar todos os dataframes em um só
        final_df = pd.concat(all_data)
        return final_df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Ocorreu um erro ao buscar os dados: {e}")
        return pd.DataFrame()


# Título e descrição
st.title("Scanner de Oportunidades Cripto")
st.markdown("""
Este aplicativo escaneia o mercado de criptomoedas em busca de oportunidades com base em indicadores técnicos.
Use os filtros na barra lateral para refinar sua busca.
""")

# --- Barra Lateral (Sidebar) com os Filtros ---
st.sidebar.header("Filtros")

timeframe = st.sidebar.selectbox(
    "Tempo Gráfico", 
    ['5m', '15m', '30m', '1h', '2h', '4h', '1d'], 
    index=5 # Padrão para 4h
)

rsi_value = st.sidebar.slider("RSI Menor que:", min_value=1, max_value=100, value=30, step=1)

macd_filter = st.sidebar.selectbox("Sinal MACD", ["Qualquer", "Cruzamento de Alta", "Cruzamento de Baixa"])


# --- Área Principal (Resultados) ---
st.info(f"Buscando e processando dados para o tempo gráfico de {timeframe}...")

df = get_binance_data(timeframe)

if not df.empty:
    
    # --- Lógica de Filtragem ---
    
    # 1. Filtro de RSI
    df_filtered = df[df['RSI_14'] <= rsi_value]
    
    # 2. Filtro de MACD
    if macd_filter == "Cruzamento de Alta":
        # MACD cruzou para cima da linha de sinal
        df_filtered = df_filtered[(df_filtered['MACD_12_26_9'] > df_filtered['MACDs_12_26_9'])]
    elif macd_filter == "Cruzamento de Baixa":
        # MACD cruzou para baixo da linha de sinal
        df_filtered = df_filtered[(df_filtered['MACD_12_26_9'] < df_filtered['MACDs_12_26_9'])]

    st.success(f"Encontradas {len(df_filtered)} moedas com os critérios selecionados.")

    # --- Exibição da Tabela ---
    
    # Selecionar e renomear colunas para exibição
    df_display = df_filtered[['symbol', 'close', 'volume', 'RSI_14', 'MACD_12_26_9', 'MACDs_12_26_9']]
    df_display = df_display.rename(columns={
        'symbol': 'Par',
        'close': 'Preço',
        'volume': 'Volume (Moeda)',
        'RSI_14': 'RSI',
        'MACD_12_26_9': 'MACD',
        'MACDs_12_26_9': 'Sinal MACD'
    })
    
    st.dataframe(df_display.style.format({'Preço': '{:.4f}', 'RSI': '{:.2f}'}), use_container_width=True)

else:
    st.warning("Nenhum dado para exibir. Verifique os filtros ou tente novamente mais tarde.")

# Para rodar este aplicativo, salve o arquivo como app.py e execute no seu terminal:
# streamlit run app.py 