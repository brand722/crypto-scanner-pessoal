import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
import pandas_ta as ta
import ccxt
import streamlit.components.v1 as components
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuração da página
st.set_page_config(
    page_title="Scanner de Oportunidades Cripto",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Funções de Lógica ---

def get_cmo_period(timeframe):
    """Retorna o período apropriado do CMO baseado no timeframe"""
    timeframe_periods = {
        '5m': 9,
        '15m': 9,
        '30m': 14,
        '1h': 14,
        '2h': 20,
        '4h': 20,
        '1d': 28
    }
    return timeframe_periods.get(timeframe, 14)  # padrão 14

def get_cmo_levels(timeframe):
    """Retorna os níveis de sobrecompra/sobrevenda do CMO baseado no timeframe"""
    if timeframe in ['5m', '15m', '30m']:
        return 50, -50  # +50, -50
    else:
        return 40, -40  # +40, -40

def get_kvo_params(timeframe):
    """Retorna os parâmetros do KVO baseados no timeframe (fast, slow, trigger)"""
    timeframe_params = {
        '5m': (14, 28, 9),
        '15m': (21, 34, 9),
        '30m': (26, 45, 10),
        '1h': (30, 50, 13),
        '2h': (34, 55, 13),
        '4h': (34, 60, 14),
        '1d': (40, 75, 20)
    }
    return timeframe_params.get(timeframe, (34, 55, 13))  # padrão clássico

# ----------------- OBV -----------------
def get_obv_ma_period(timeframe):
    """Retorna o período da média móvel usada para suavizar o OBV de acordo com o timeframe"""
    mapping = {
        '5m': 7,
        '15m': 10,
        '30m': 14,
        '1h': 20,
        '2h': 30,
        '4h': 40,
        '1d': 50
    }
    return mapping.get(timeframe, 20)

# ----------------- CMF -----------------
def get_cmf_period(timeframe):
    """Retorna o período do CMF baseado no timeframe"""
    mapping = {
        '5m': 10,
        '15m': 14,
        '30m': 14,
        '1h': 21,
        '2h': 25,
        '4h': 32,
        '1d': 34
    }
    return mapping.get(timeframe, 20)

def get_cmf_thresholds(timeframe):
    """Retorna (positivo, negativo) thresholds para CMF"""
    if timeframe in ['5m', '15m', '30m']:
        return 0.1, -0.1
    elif timeframe in ['1h', '2h', '4h']:
        return 0.2, -0.2
    else:
        return 0.25, -0.25

# ----------------- RSI -----------------
def get_rsi_period(timeframe):
    """Retorna o período do RSI baseado no timeframe"""
    mapping = {
        '5m': 9,
        '15m': 9,
        '30m': 10,
        '1h': 10,
        '2h': 14,
        '4h': 14,
        '1d': 14
    }
    return mapping.get(timeframe, 14)

def get_rsi_levels(timeframe):
    """Retorna (sobrecompra, sobrevenda) níveis para RSI"""
    if timeframe == '5m':
        return 80, 20
    else:
        return 70, 30

@st.cache_data(ttl=600) # Cache de 10 minutos
def get_binance_data(timeframe, top_n=200):
    """
    Busca e processa dados da Binance para as top N moedas do mercado Spot.
    Calcula os indicadores RSI e MACD.
    """
    try:
        # 1. Buscar tickers para todos os pares para pegar o volume via API direta
        tickers_url = "https://api.binance.com/api/v3/ticker/24hr"
        response = requests.get(tickers_url)
        response.raise_for_status()  # Lança exceção para erros HTTP
        all_tickers = response.json()

        # 2. Filtrar por pares USDT e ordenar por volume
        usdt_tickers = [
            t for t in all_tickers
            if t['symbol'].endswith('USDT') and float(t.get('quoteVolume', 0)) > 0
        ]

        # Ordenar por volume (quoteVolume) e pegar o top N
        sorted_tickers = sorted(usdt_tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
        top_symbols = [t['symbol'] for t in sorted_tickers[:top_n]]

        if not top_symbols:
            st.warning("Não foi possível encontrar pares USDT com volume. A API da Binance pode estar com problemas.")
            return pd.DataFrame()

        all_data = []

        # 3. Para cada símbolo no top N, buscar os dados de velas (klines)
        for symbol in top_symbols:
            try:
                klines_url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={timeframe}&limit=100"
                kline_response = requests.get(klines_url)
                kline_response.raise_for_status()
                ohlcv = kline_response.json()

                if len(ohlcv) < 20:  # Checagem mínima para ter dados suficientes
                    continue

                # Lista completa de colunas devolvidas pela API
                column_names = [
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ]
                # Passamos "type: ignore" para evitar falsos-positivos das stubs do pandas
                df = pd.DataFrame(ohlcv, columns=column_names)  # type: ignore[arg-type]
                
                # Manter apenas as colunas necessárias e converter para numérico
                df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
                
                # Converter para numérico com tratamento de erros
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                
                # Remover linhas com dados inválidos (NaN)
                df = df.dropna()
                
                # Verificar se ainda temos dados suficientes após limpeza
                if len(df) < 20:
                    continue
                
                # Verificar se há variação nos preços (evitar pares "mortos")
                if df['close'].nunique() < 5:  # type: ignore[attr-defined]
                    continue
                
                # Verificar se há volume mínimo
                if df['volume'].sum() == 0:  # Se volume total é zero, pular
                    continue
                
                df['symbol'] = symbol.replace('USDT', '/USDT')

                # 4. Calcular Indicadores com pandas-ta (com tratamento de erro)
                try:
                    # Verificar novamente se temos dados suficientes
                    rsi_period = get_rsi_period(timeframe)
                    if len(df) < rsi_period:
                        continue
                        
                    df.ta.rsi(length=rsi_period, append=True)
                    rsi_col = f"RSI_{rsi_period}"
                    
                    # --- Ultimate Oscillator (UO) ---
                    df.ta.uo(length=[7, 14, 28], append=True)
                    
                    # --- Awesome Oscillator (AO) ---
                    # AO = SMA(HL2, 5) - SMA(HL2, 34)
                    # HL2 = (High + Low) / 2
                    hl2 = (df['high'] + df['low']) / 2  # type: ignore[operator]
                    sma_5 = hl2.rolling(window=5).mean()  # type: ignore[attr-defined]
                    sma_34 = hl2.rolling(window=34).mean()  # type: ignore[attr-defined]
                    df['AO'] = sma_5 - sma_34
                    
                    # Diferença para detectar mudança de cor (verde/vermelho)
                    df['AO_diff'] = df['AO'].diff()  # type: ignore[attr-defined]
                    df['AO_prev'] = df['AO'].shift(1)  # type: ignore[attr-defined]
                    
                    # --- Chande Momentum Oscillator (CMO) ---
                    cmo_period = get_cmo_period(timeframe)
                    
                    # Calcular momentum (mudança do preço)
                    momm = df['close'].diff()  # type: ignore[attr-defined]
                    
                    # Separar gains e losses
                    m1 = momm.where(momm >= 0, 0)  # gains (valores positivos)
                    m2 = (-momm).where(momm < 0, 0)  # losses (valores negativos convertidos para positivos)
                    
                    # Somas móveis
                    sm1 = m1.rolling(window=cmo_period).sum()  # type: ignore[attr-defined]
                    sm2 = m2.rolling(window=cmo_period).sum()  # type: ignore[attr-defined]
                    
                    # CMO = 100 * (sm1 - sm2) / (sm1 + sm2)
                    df['CMO'] = 100 * (sm1 - sm2) / (sm1 + sm2)
                    df['CMO_prev'] = df['CMO'].shift(1)  # type: ignore[attr-defined]
                    
                    # --- Klinger Volume Oscillator (KVO) ---
                    fast_period, slow_period, trigger_period = get_kvo_params(timeframe)
                    
                    # Calcular HLC3 (typical price)
                    hlc3 = (df['high'] + df['low'] + df['close']) / 3
                    
                    # Trend: se HLC3 atual > HLC3 anterior, trend positivo, senão negativo
                    trend_condition = hlc3 > hlc3.shift(1)  # type: ignore[attr-defined]
                    
                    # xTrend = se trend positivo: volume * 100, senão: -volume * 100
                    x_trend = df['volume'].where(trend_condition, -df['volume']) * 100  # type: ignore[attr-defined]
                    
                    # Calcular EMAs
                    x_fast = x_trend.ewm(span=fast_period).mean()  # type: ignore[attr-defined]
                    x_slow = x_trend.ewm(span=slow_period).mean()  # type: ignore[attr-defined]
                    
                    # KVO = EMA_fast - EMA_slow
                    df['KVO'] = x_fast - x_slow
                    
                    # Trigger = EMA do KVO
                    df['KVO_trigger'] = df['KVO'].ewm(span=trigger_period).mean()  # type: ignore[attr-defined]
                    df['KVO_prev'] = df['KVO'].shift(1)  # type: ignore[attr-defined]
                    df['KVO_trigger_prev'] = df['KVO_trigger'].shift(1)  # type: ignore[attr-defined]
                    
                    # --- Directional Movement Index (DMI) ---
                    dmi_period = get_dmi_period(timeframe)
                    df.ta.adx(length=dmi_period, append=True)  # cria ADX_{period}, DMP_{period}, DMN_{period}
                    adx_col = f"ADX_{dmi_period}"
                    dip_col = f"DMP_{dmi_period}"
                    dim_col = f"DMN_{dmi_period}"
                    df['ADX'] = df[adx_col]
                    df['DI_plus'] = df[dip_col]
                    df['DI_minus'] = df[dim_col]
                    # valores anteriores para possíveis filtros futuros
                    df['DI_plus_prev'] = df['DI_plus'].shift(1)  # type: ignore[attr-defined]
                    df['DI_minus_prev'] = df['DI_minus'].shift(1)  # type: ignore[attr-defined]
                    df['ADX_prev'] = df['ADX'].shift(1)  # type: ignore[attr-defined]
                    
                    # --- On Balance Volume (OBV) ---
                    obv_ma_period = get_obv_ma_period(timeframe)
                    # var cumVol = 0 / cumVol += volume. Precisamos do OBV acumulativo com sinal
                    obv_raw = (df['close'].diff()  # type: ignore[attr-defined]
                                .apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df['volume']).fillna(0)
                    df['OBV'] = obv_raw.cumsum()  # type: ignore[attr-defined]
                    # Suavizar OBV com EMA (padrão) do período definido
                    df['OBV_MA'] = df['OBV'].ewm(span=obv_ma_period).mean()  # type: ignore[attr-defined]
                    df['OBV_prev'] = df['OBV'].shift(1)  # type: ignore[attr-defined]
                    df['OBV_MA_prev'] = df['OBV_MA'].shift(1)  # type: ignore[attr-defined]
                    
                    # --- Chaikin Money Flow (CMF) ---
                    cmf_period = get_cmf_period(timeframe)
                    cmf_pos_th, cmf_neg_th = get_cmf_thresholds(timeframe)

                    # Avoid division by zero for (high - low)
                    hl_range = (df['high'] - df['low']).replace(0, np.nan)  # type: ignore[attr-defined]
                    ad = ((2 * df['close'] - df['low'] - df['high']) / hl_range) * df['volume']  # type: ignore[arg-type]
                    cmf_num = ad.rolling(window=cmf_period).sum()  # type: ignore[attr-defined]
                    cmf_den = df['volume'].rolling(window=cmf_period).sum()  # type: ignore[attr-defined]
                    df['CMF'] = cmf_num / cmf_den
                    df['CMF_prev'] = df['CMF'].shift(1)  # type: ignore[attr-defined]
                    
                    # Verificar se os indicadores foram calculados corretamente
                    if (
                        rsi_col not in df.columns
                        or 'UO_7_14_28' not in df.columns
                        or 'AO' not in df.columns
                        or 'CMO' not in df.columns
                        or 'KVO' not in df.columns
                        or 'KVO_trigger' not in df.columns
                        or 'OBV' not in df.columns
                        or 'OBV_MA' not in df.columns
                        or 'CMF' not in df.columns
                    ):
                        continue
                        
                    # Remover linhas onde os indicadores são NaN
                    df = df.dropna(subset=[rsi_col, 'UO_7_14_28', 'AO', 'CMO', 'KVO', 'KVO_trigger', 'OBV', 'OBV_MA', 'CMF'])  # type: ignore[arg-type]
                    
                    if len(df) == 0:
                        continue
                        
                except Exception as indicator_error:
                    # Não mostrar warning para cada erro individual, apenas continuar
                    continue

                # Preparar a última e penúltima vela para detecção de cruzamentos do UO
                if len(df) < 2:
                    continue  # Necessário pelo menos duas velas

                last_row = df.iloc[-1:].copy()
                # Armazenar valor anterior do UO para filtros de cruzamento
                last_row['UO_prev'] = df['UO_7_14_28'].iloc[-2]
                # Armazenar valor anterior do AO para filtros de cruzamento
                last_row['AO_prev'] = df['AO'].iloc[-2]
                # Armazenar valor anterior do CMO para filtros de cruzamento
                last_row['CMO_prev'] = df['CMO'].iloc[-2]
                # Armazenar valores anteriores do KVO para filtros de cruzamento
                last_row['KVO_prev'] = df['KVO'].iloc[-2]
                last_row['KVO_trigger_prev'] = df['KVO_trigger'].iloc[-2]
                last_row['OBV_prev'] = df['OBV'].iloc[-2]
                last_row['OBV_MA_prev'] = df['OBV_MA'].iloc[-2]
                last_row['CMF_prev'] = df['CMF'].iloc[-2]

                # --- Variação percentual últimas 3 velas ---
                if len(df) >= 4:
                    pct_change_3 = ((df['close'].iloc[-1] - df['close'].iloc[-4]) / df['close'].iloc[-4]) * 100
                    last_row['pct_change'] = pct_change_3
                else:
                    last_row['pct_change'] = 0.0

                all_data.append(last_row)
                
            except Exception as symbol_error:
                # Se houver qualquer erro com este símbolo específico, apenas continuar
                continue

        if not all_data:
            st.warning("Não foi possível obter dados de velas para os principais pares. Tente outro tempo gráfico.")
            return pd.DataFrame()

        # Concatenar todos os dataframes em um só
        final_df = pd.concat(all_data)
        return final_df.reset_index(drop=True)

    except requests.exceptions.HTTPError as http_err:
        st.error(f"Erro de HTTP ao conectar com a Binance: {http_err}")
        if http_err.response.status_code == 451:
            st.error("Acesso negado por restrições geográficas (Erro 451).")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Ocorreu um erro ao buscar os dados: {e}")
        return pd.DataFrame()

# ----------------- DMI -----------------
def get_dmi_period(timeframe: str) -> int:
    """Retorna o período do DMI (DI/ADX) baseado no timeframe"""
    mapping = {
        '5m': 10,
        '15m': 10,
        '30m': 14,
        '1h': 14,
        '2h': 20,
        '4h': 20,
        '1d': 25
    }
    return mapping.get(timeframe, 14)

# ----------------- Bybit DATA -----------------
@st.cache_data(ttl=600)  # Cache de 10 minutos

def get_bybit_data(timeframe: str, top_n: int = 200) -> pd.DataFrame:
    """Busca e processa dados da Bybit Spot para os top N pares USDT.
    Calcula os mesmos indicadores usados na Binance."""
    try:
        # 1. Buscar lista completa de tickers 24h (Spot)
        tickers_url = "https://api.bybit.com/v5/market/tickers?category=spot"
        response = requests.get(tickers_url, timeout=10)
        response.raise_for_status()
        json_resp = response.json()
        if json_resp.get("retCode") != 0:
            st.warning("Não foi possível obter tickers da Bybit.")
            return pd.DataFrame()

        tickers_list = json_resp.get("result", {}).get("list", [])
        if not tickers_list:
            st.warning("Lista de tickers da Bybit vazia.")
            return pd.DataFrame()

        # 2. Filtrar pares USDT e ordenar por volume 24h
        usdt_tickers = [t for t in tickers_list if t["symbol"].endswith("USDT") and float(t.get("volume24h", 0)) > 0]
        sorted_tickers = sorted(usdt_tickers, key=lambda x: float(x["volume24h"]), reverse=True)
        top_symbols = [t["symbol"] for t in sorted_tickers[:top_n]]

        if not top_symbols:
            st.warning("Não foi possível encontrar pares USDT na Bybit.")
            return pd.DataFrame()

        # 3. Mapear timeframe para intervalo da Bybit
        tf_map = {
            "5m": "5",
            "15m": "15",
            "30m": "30",
            "1h": "60",
            "2h": "120",
            "4h": "240",
            "1d": "D",
        }
        bybit_interval = tf_map.get(timeframe, "30")

        all_data = []
        for symbol in top_symbols:
            try:
                klines_url = (
                    f"https://api.bybit.com/v5/market/kline?category=spot&symbol={symbol}&interval={bybit_interval}&limit=100"
                )
                kline_resp = requests.get(klines_url, timeout=10)
                kline_resp.raise_for_status()
                kline_json = kline_resp.json()
                if kline_json.get("retCode") != 0:
                    continue
                kline_list = kline_json.get("result", {}).get("list", [])
                if len(kline_list) < 20:
                    continue

                # Bybit devolve as velas em ordem reversa (mais recente primeiro)
                kline_list.reverse()

                # Converter para DataFrame
                df = pd.DataFrame(
                    kline_list,
                    columns=[
                        "timestamp",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "turnover",
                    ],  # type: ignore[arg-type]
                )

                # Converter colunas para numérico
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

                # Limpar dados inválidos
                df = df.dropna()
                if len(df) < 20 or df["close"].nunique() < 5 or df["volume"].sum() == 0:
                    continue

                df["symbol"] = symbol.replace("USDT", "/USDT")

                # Reutilizar a lógica já existente para indicadores
                rsi_period = get_rsi_period(timeframe)
                if len(df) < rsi_period:
                    continue

                # ----- Indicadores -----
                try:
                    df.ta.rsi(length=rsi_period, append=True)
                    rsi_col = f"RSI_{rsi_period}"

                    df.ta.uo(length=[7, 14, 28], append=True)

                    hl2 = (df["high"] + df["low"]) / 2
                    df["AO"] = hl2.rolling(window=5).mean() - hl2.rolling(window=34).mean()
                    df["AO_diff"] = df["AO"].diff()

                    cmo_period = get_cmo_period(timeframe)
                    momm = df["close"].diff()
                    m1 = momm.where(momm >= 0, 0)
                    m2 = (-momm).where(momm < 0, 0)
                    sm1 = m1.rolling(window=cmo_period).sum()
                    sm2 = m2.rolling(window=cmo_period).sum()
                    df["CMO"] = 100 * (sm1 - sm2) / (sm1 + sm2)
                    df["CMO_prev"] = df["CMO"].shift(1)

                    fast_period, slow_period, trigger_period = get_kvo_params(timeframe)
                    hlc3 = (df["high"] + df["low"] + df["close"]) / 3
                    trend_condition = hlc3 > hlc3.shift(1)
                    x_trend = df["volume"].where(trend_condition, -df["volume"]) * 100
                    x_fast = x_trend.ewm(span=fast_period).mean()
                    x_slow = x_trend.ewm(span=slow_period).mean()
                    df["KVO"] = x_fast - x_slow
                    df["KVO_trigger"] = df["KVO"].ewm(span=trigger_period).mean()

                    dmi_period = get_dmi_period(timeframe)
                    df.ta.adx(length=dmi_period, append=True)
                    df["ADX"] = df[f"ADX_{dmi_period}"]
                    df["DI_plus"] = df[f"DMP_{dmi_period}"]
                    df["DI_minus"] = df[f"DMN_{dmi_period}"]
                    df["DI_plus_prev"] = df["DI_plus"].shift(1)
                    df["DI_minus_prev"] = df["DI_minus"].shift(1)
                    df["ADX_prev"] = df["ADX"].shift(1)

                    obv_ma_period = get_obv_ma_period(timeframe)
                    obv_raw = (
                        df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df["volume"]
                    ).fillna(0)
                    df["OBV"] = obv_raw.cumsum()
                    df["OBV_MA"] = df["OBV"].ewm(span=obv_ma_period).mean()
                    df["OBV_prev"] = df["OBV"].shift(1)
                    df["OBV_MA_prev"] = df["OBV_MA"].shift(1)

                    cmf_period = get_cmf_period(timeframe)
                    hl_range = (df["high"] - df["low"]).replace(0, np.nan)
                    ad = ((2 * df["close"] - df["low"] - df["high"]) / hl_range) * df["volume"]
                    cmf_num = ad.rolling(window=cmf_period).sum()
                    cmf_den = df["volume"].rolling(window=cmf_period).sum()
                    df["CMF"] = cmf_num / cmf_den
                    df["CMF_prev"] = df["CMF"].shift(1)

                    # Validação de colunas
                    if (
                        rsi_col not in df.columns
                        or "UO_7_14_28" not in df.columns
                        or "AO" not in df.columns
                        or "CMO" not in df.columns
                        or "KVO" not in df.columns
                        or "KVO_trigger" not in df.columns
                        or "OBV" not in df.columns
                        or "OBV_MA" not in df.columns
                        or "CMF" not in df.columns
                    ):
                        continue
                    df = df.dropna(
                        subset=[
                            rsi_col,
                            "UO_7_14_28",
                            "AO",
                            "CMO",
                            "KVO",
                            "KVO_trigger",
                            "OBV",
                            "OBV_MA",
                            "CMF",
                        ]
                    )
                    if len(df) == 0:
                        continue
                except Exception:
                    continue

                if len(df) < 2:
                    continue

                last_row = df.iloc[-1:].copy()
                last_row["UO_prev"] = df["UO_7_14_28"].iloc[-2]
                last_row["AO_prev"] = df["AO"].iloc[-2]
                last_row["CMO_prev"] = df["CMO"].iloc[-2]
                last_row["KVO_prev"] = df["KVO"].iloc[-2]
                last_row["KVO_trigger_prev"] = df["KVO_trigger"].iloc[-2]
                last_row["OBV_prev"] = df["OBV"].iloc[-2]
                last_row["OBV_MA_prev"] = df["OBV_MA"].iloc[-2]
                last_row["CMF_prev"] = df["CMF"].iloc[-2]

                if len(df) >= 4:
                    pct_change_3 = ((df["close"].iloc[-1] - df["close"].iloc[-4]) / df["close"].iloc[-4]) * 100
                    last_row["pct_change"] = pct_change_3
                else:
                    last_row["pct_change"] = 0.0

                all_data.append(last_row)
            except Exception:
                continue

        if not all_data:
            st.warning("Nenhum dado de velas retornado pela Bybit.")
            return pd.DataFrame()

        final_df = pd.concat(all_data)
        return final_df.reset_index(drop=True)

    except Exception as e:
        st.error(f"Erro ao buscar dados da Bybit: {e}")
        return pd.DataFrame()

# ----------------- Bitget DATA -----------------
@st.cache_data(ttl=600)  # Cache de 10 minutos
def get_bitget_data(timeframe: str, top_n: int = 200) -> pd.DataFrame:
    """Busca e processa dados Spot da Bitget para os top N pares USDT usando CCXT."""
    try:
        # 1. Inicializar exchange Bitget com CCXT
        exchange = ccxt.bitget({
            'enableRateLimit': True,
            'sandbox': False,  # Usar API de produção
        })
        
        # 2. Carregar mercados disponíveis
        markets = exchange.load_markets()
        
        # 3. Filtrar pares USDT do mercado spot
        usdt_spot_pairs = [
            symbol for symbol, market in markets.items()
            if market['spot'] and market['quote'] == 'USDT'
        ]
        
        if not usdt_spot_pairs:
            st.warning("⚠️ Nenhum par USDT Spot encontrado na Bitget.")
            return pd.DataFrame()
        
        # 4. Buscar tickers para obter volume
        tickers = exchange.fetch_tickers(usdt_spot_pairs)
        
        # 5. Ordenar por volume e pegar top N
        pairs_with_volume = []
        for symbol in usdt_spot_pairs:
            if symbol in tickers:
                ticker = tickers[symbol]
                volume = ticker.get('quoteVolume', 0) or 0
                # Garantir que volume é numérico
                try:
                    volume = float(volume) if volume is not None else 0.0
                except (ValueError, TypeError):
                    volume = 0.0
                
                if volume > 0:
                    pairs_with_volume.append((symbol, volume))
        
        # Ordenar por volume decrescente e pegar top N
        pairs_with_volume.sort(key=lambda x: x[1], reverse=True)
        top_pairs = [pair[0] for pair in pairs_with_volume[:top_n]]

        if not top_pairs:
            st.warning("⚠️ Nenhum par com volume > 0 encontrado.")
            return pd.DataFrame()

        all_data: list[pd.DataFrame] = []

        # 6. Buscar dados OHLCV para cada par
        for symbol in top_pairs:
            try:
                # Usar CCXT para buscar dados OHLCV
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
                
                if len(ohlcv) < 20:
                    continue
                
                # Converter para DataFrame
                df = pd.DataFrame(ohlcv)  # type: ignore[arg-type]
                df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']  # type: ignore[assignment]
                
                # Converter timestamp para datetime
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                # Verificar se há dados válidos
                if len(df) < 20 or df["close"].nunique() < 5 or df["volume"].sum() == 0:
                    continue
                
                df["symbol"] = symbol
                
                # ---------------- Indicadores ----------------
                rsi_period = get_rsi_period(timeframe)
                if len(df) < rsi_period:
                    continue
                    
                try:
                    # RSI & UO
                    df.ta.rsi(length=rsi_period, append=True)
                    rsi_col = f"RSI_{rsi_period}"
                    df.ta.uo(length=[7, 14, 28], append=True)
                    
                    # AO
                    hl2 = (df["high"] + df["low"]) / 2
                    df["AO"] = hl2.rolling(window=5).mean() - hl2.rolling(window=34).mean()
                    df["AO_diff"] = df["AO"].diff()
                    
                    # CMO
                    cmo_period = get_cmo_period(timeframe)
                    momm = df["close"].diff()
                    m1 = momm.where(momm >= 0, 0)
                    m2 = (-momm).where(momm < 0, 0)
                    sm1 = m1.rolling(window=cmo_period).sum()
                    sm2 = m2.rolling(window=cmo_period).sum()
                    df["CMO"] = 100 * (sm1 - sm2) / (sm1 + sm2)
                    df["CMO_prev"] = df["CMO"].shift(1)
                    
                    # KVO
                    fast_p, slow_p, trg_p = get_kvo_params(timeframe)
                    hlc3 = (df["high"] + df["low"] + df["close"]) / 3
                    trend_condition = hlc3 > hlc3.shift(1)
                    x_trend = df["volume"].where(trend_condition, -df["volume"]) * 100
                    x_fast = x_trend.ewm(span=fast_p).mean()
                    x_slow = x_trend.ewm(span=slow_p).mean()
                    df["KVO"] = x_fast - x_slow
                    df["KVO_trigger"] = df["KVO"].ewm(span=trg_p).mean()
                    
                    # DMI
                    dmi_p = get_dmi_period(timeframe)
                    df.ta.adx(length=dmi_p, append=True)
                    df["ADX"] = df[f"ADX_{dmi_p}"]
                    df["DI_plus"] = df[f"DMP_{dmi_p}"]
                    df["DI_minus"] = df[f"DMN_{dmi_p}"]
                    df["DI_plus_prev"] = df["DI_plus"].shift(1)
                    df["DI_minus_prev"] = df["DI_minus"].shift(1)
                    df["ADX_prev"] = df["ADX"].shift(1)

                    # OBV
                    obv_ma_p = get_obv_ma_period(timeframe)
                    obv_raw = (
                        df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df["volume"]
                    ).fillna(0)
                    df["OBV"] = obv_raw.cumsum()
                    df["OBV_MA"] = df["OBV"].ewm(span=obv_ma_p).mean()
                    df["OBV_prev"] = df["OBV"].shift(1)
                    df["OBV_MA_prev"] = df["OBV_MA"].shift(1)

                    # CMF
                    cmf_p = get_cmf_period(timeframe)
                    hl_rng = (df["high"] - df["low"]).replace(0, np.nan)
                    ad = ((2 * df["close"] - df["low"] - df["high"]) / hl_rng) * df["volume"]
                    cmf_num = ad.rolling(window=cmf_p).sum()
                    cmf_den = df["volume"].rolling(window=cmf_p).sum()
                    df["CMF"] = cmf_num / cmf_den
                    df["CMF_prev"] = df["CMF"].shift(1)

                    # Validação
                    if (
                        rsi_col not in df.columns
                        or "UO_7_14_28" not in df.columns
                        or "AO" not in df.columns
                        or "CMO" not in df.columns
                        or "KVO" not in df.columns
                        or "KVO_trigger" not in df.columns
                        or "OBV" not in df.columns
                        or "OBV_MA" not in df.columns
                        or "CMF" not in df.columns
                    ):
                        continue

                    df = df.dropna(
                        subset=[
                            rsi_col,
                            "UO_7_14_28",
                            "AO",
                            "CMO",
                            "KVO",
                            "KVO_trigger",
                            "OBV",
                            "OBV_MA",
                            "CMF",
                        ]
                    )
                    if len(df) == 0:
                        continue
                except Exception:
                    continue

                if len(df) < 2:
                    continue

                last_row = df.iloc[-1:].copy()
                last_row["UO_prev"] = df["UO_7_14_28"].iloc[-2]
                last_row["AO_prev"] = df["AO"].iloc[-2]
                last_row["CMO_prev"] = df["CMO"].iloc[-2]
                last_row["KVO_prev"] = df["KVO"].iloc[-2]
                last_row["KVO_trigger_prev"] = df["KVO_trigger"].iloc[-2]
                last_row["OBV_prev"] = df["OBV"].iloc[-2]
                last_row["OBV_MA_prev"] = df["OBV_MA"].iloc[-2]
                last_row["CMF_prev"] = df["CMF"].iloc[-2]

                if len(df) >= 4:
                    pct_change_3 = ((df["close"].iloc[-1] - df["close"].iloc[-4]) / df["close"].iloc[-4]) * 100
                    last_row["pct_change"] = pct_change_3
                else:
                    last_row["pct_change"] = 0.0

                all_data.append(last_row)
            except Exception:
                continue

        if not all_data:
            st.warning("Nenhum dado de velas retornado pela Bitget.")
            return pd.DataFrame()
        
        final_df = pd.concat(all_data)
        return final_df.reset_index(drop=True)
        
    except Exception as e:
        st.error(f"Erro ao buscar dados da Bitget: {str(e)}")
        return pd.DataFrame()

# ----------------- KuCoin DATA -----------------
@st.cache_data(ttl=600)  # Cache de 10 minutos

def get_kucoin_data(timeframe: str, top_n: int = 200) -> pd.DataFrame:
    """Busca e processa dados Spot da KuCoin para os top N pares USDT.
    Reaproveita a mesma lógica de indicadores já aplicada no scanner."""
    try:
        # API v1 da KuCoin para all tickers
        tickers_url = "https://api.kucoin.com/api/v1/market/allTickers"
        resp = requests.get(tickers_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        # Verificar se a resposta tem o formato esperado
        if data.get("code") != "200000" or not data.get("data", {}).get("ticker"):
            st.warning("Resposta inesperada da API da KuCoin")
            return pd.DataFrame()
        
        tickers_list = data["data"]["ticker"]
        
        # Filtrar pares USDT e que tenham volume > 0
        usdt_tickers = []
        for ticker in tickers_list:
            symbol = ticker.get("symbol", "")
            vol_value = float(ticker.get("volValue", 0) or 0)  # Volume em USDT
            
            if symbol.endswith("-USDT") and vol_value > 0:
                usdt_tickers.append({
                    "symbol": symbol,
                    "volume": vol_value
                })
        
        if not usdt_tickers:
            st.warning("Não foi possível encontrar pares USDT na KuCoin.")
            return pd.DataFrame()
        
        # Ordenar por volume e pegar os top N
        sorted_tickers = sorted(usdt_tickers, key=lambda x: x["volume"], reverse=True)
        top_symbols = [t["symbol"] for t in sorted_tickers[:top_n]]
        
        # Mapear timeframe para formato da KuCoin
        timeframe_map = {
            "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "1hour", "2h": "2hour", "4h": "4hour", "1d": "1day"
        }
        
        kucoin_timeframe = timeframe_map.get(timeframe, "1hour")
        all_data: list[pd.DataFrame] = []
        
        for symbol in top_symbols:
            try:
                # API v1 da KuCoin para candles
                klines_url = f"https://api.kucoin.com/api/v1/market/candles"
                params = {
                    "symbol": symbol,
                    "type": kucoin_timeframe
                }
                
                kline_resp = requests.get(klines_url, params=params, timeout=10)
                kline_resp.raise_for_status()
                kline_data = kline_resp.json()
                
                if kline_data.get("code") != "200000" or not kline_data.get("data"):
                    continue
                
                klines = kline_data["data"]
                if len(klines) < 20:  # Dados insuficientes
                    continue
                
                # Criar DataFrame com os dados de velas
                # KuCoin retorna: [timestamp, open, close, high, low, volume, turnover]
                df = pd.DataFrame(klines)
                df.columns = ["timestamp", "open", "close", "high", "low", "volume", "turnover"]
                
                # Converter tipos
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna()
                
                if len(df) < 20 or df["close"].nunique() < 5 or df["volume"].sum() == 0:
                    continue
                
                df["symbol"] = symbol.replace("-USDT", "/USDT")
                
                # ---------------- Indicadores ----------------
                rsi_period = get_rsi_period(timeframe)
                if len(df) < rsi_period:
                    continue
                    
                try:
                    # RSI & UO
                    df.ta.rsi(length=rsi_period, append=True)
                    rsi_col = f"RSI_{rsi_period}"
                    df.ta.uo(length=[7, 14, 28], append=True)
                    
                    # AO
                    hl2 = (df["high"] + df["low"]) / 2
                    df["AO"] = hl2.rolling(window=5).mean() - hl2.rolling(window=34).mean()
                    df["AO_diff"] = df["AO"].diff()
                    
                    # CMO
                    cmo_period = get_cmo_period(timeframe)
                    momm = df["close"].diff()
                    m1 = momm.where(momm >= 0, 0)
                    m2 = (-momm).where(momm < 0, 0)
                    sm1 = m1.rolling(window=cmo_period).sum()
                    sm2 = m2.rolling(window=cmo_period).sum()
                    df["CMO"] = 100 * (sm1 - sm2) / (sm1 + sm2)
                    df["CMO_prev"] = df["CMO"].shift(1)
                    
                    # KVO
                    fast_p, slow_p, trg_p = get_kvo_params(timeframe)
                    hlc3 = (df["high"] + df["low"] + df["close"]) / 3
                    trend_condition = hlc3 > hlc3.shift(1)
                    x_trend = df["volume"].where(trend_condition, -df["volume"]) * 100
                    x_fast = x_trend.ewm(span=fast_p).mean()
                    x_slow = x_trend.ewm(span=slow_p).mean()
                    df["KVO"] = x_fast - x_slow
                    df["KVO_trigger"] = df["KVO"].ewm(span=trg_p).mean()
                    
                    # DMI
                    dmi_p = get_dmi_period(timeframe)
                    df.ta.adx(length=dmi_p, append=True)
                    df["ADX"] = df[f"ADX_{dmi_p}"]
                    df["DI_plus"] = df[f"DMP_{dmi_p}"]
                    df["DI_minus"] = df[f"DMN_{dmi_p}"]
                    df["DI_plus_prev"] = df["DI_plus"].shift(1)
                    df["DI_minus_prev"] = df["DI_minus"].shift(1)
                    df["ADX_prev"] = df["ADX"].shift(1)

                    # OBV
                    obv_ma_p = get_obv_ma_period(timeframe)
                    obv_raw = (
                        df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df["volume"]
                    ).fillna(0)
                    df["OBV"] = obv_raw.cumsum()
                    df["OBV_MA"] = df["OBV"].ewm(span=obv_ma_p).mean()
                    df["OBV_prev"] = df["OBV"].shift(1)
                    df["OBV_MA_prev"] = df["OBV_MA"].shift(1)

                    # CMF
                    cmf_p = get_cmf_period(timeframe)
                    hl_rng = (df["high"] - df["low"]).replace(0, np.nan)
                    ad = ((2 * df["close"] - df["low"] - df["high"]) / hl_rng) * df["volume"]
                    cmf_num = ad.rolling(window=cmf_p).sum()
                    cmf_den = df["volume"].rolling(window=cmf_p).sum()
                    df["CMF"] = cmf_num / cmf_den
                    df["CMF_prev"] = df["CMF"].shift(1)

                    # Validação
                    if (
                        rsi_col not in df.columns
                        or "UO_7_14_28" not in df.columns
                        or "AO" not in df.columns
                        or "CMO" not in df.columns
                        or "KVO" not in df.columns
                        or "KVO_trigger" not in df.columns
                        or "OBV" not in df.columns
                        or "OBV_MA" not in df.columns
                        or "CMF" not in df.columns
                    ):
                        continue

                    df = df.dropna(
                        subset=[
                            rsi_col,
                            "UO_7_14_28",
                            "AO",
                            "CMO",
                            "KVO",
                            "KVO_trigger",
                            "OBV",
                            "OBV_MA",
                            "CMF",
                        ]
                    )
                    if len(df) == 0:
                        continue
                except Exception:
                    continue

                if len(df) < 2:
                    continue

                last_row = df.iloc[-1:].copy()
                last_row["UO_prev"] = df["UO_7_14_28"].iloc[-2]
                last_row["AO_prev"] = df["AO"].iloc[-2]
                last_row["CMO_prev"] = df["CMO"].iloc[-2]
                last_row["KVO_prev"] = df["KVO"].iloc[-2]
                last_row["KVO_trigger_prev"] = df["KVO_trigger"].iloc[-2]
                last_row["OBV_prev"] = df["OBV"].iloc[-2]
                last_row["OBV_MA_prev"] = df["OBV_MA"].iloc[-2]
                last_row["CMF_prev"] = df["CMF"].iloc[-2]

                if len(df) >= 4:
                    pct_change_3 = ((df["close"].iloc[-1] - df["close"].iloc[-4]) / df["close"].iloc[-4]) * 100
                    last_row["pct_change"] = pct_change_3
                else:
                    last_row["pct_change"] = 0.0

                all_data.append(last_row)
            except Exception:
                continue

        if not all_data:
            st.warning("Nenhum dado de velas retornado pela KuCoin.")
            return pd.DataFrame()
        
        final_df = pd.concat(all_data)
        return final_df.reset_index(drop=True)
        
    except Exception as e:
        st.error(f"Erro ao buscar dados da KuCoin: {str(e)}")
        return pd.DataFrame()

# ----------------- OKX DATA -----------------
@st.cache_data(ttl=600)  # Cache de 10 minutos

def get_okx_data(timeframe: str, top_n: int = 200) -> pd.DataFrame:
    """Busca e processa dados Spot da OKX para os top N pares USDT.
    Reaproveita a mesma lógica de indicadores já aplicada no scanner."""
    try:
        # API v5 da OKX para tickers spot
        tickers_url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
        resp = requests.get(tickers_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        # Verificar se a resposta tem o formato esperado
        if data.get("code") != "0" or not data.get("data"):
            st.warning("Resposta inesperada da API da OKX")
            return pd.DataFrame()
        
        tickers_list = data["data"]
        
        # Filtrar pares USDT e que tenham volume > 0
        usdt_tickers = []
        for ticker in tickers_list:
            symbol = ticker.get("instId", "")
            vol_ccy = float(ticker.get("volCcy24h", 0) or 0)  # Volume em USDT
            
            if symbol.endswith("-USDT") and vol_ccy > 0:
                usdt_tickers.append({
                    "symbol": symbol,
                    "volume": vol_ccy
                })
        
        if not usdt_tickers:
            st.warning("Não foi possível encontrar pares USDT na OKX.")
            return pd.DataFrame()
        
        # Ordenar por volume e pegar os top N
        sorted_tickers = sorted(usdt_tickers, key=lambda x: x["volume"], reverse=True)
        top_symbols = [t["symbol"] for t in sorted_tickers[:top_n]]
        
        # Mapear timeframe para formato da OKX
        timeframe_map = {
            "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1H", "2h": "2H", "4h": "4H", "1d": "1D"
        }
        
        okx_timeframe = timeframe_map.get(timeframe, "1H")
        all_data: list[pd.DataFrame] = []
        
        for symbol in top_symbols:
            try:
                # API v5 da OKX para candles
                klines_url = f"https://www.okx.com/api/v5/market/candles"
                params = {
                    "instId": symbol,
                    "bar": okx_timeframe,
                    "limit": "100"
                }
                
                kline_resp = requests.get(klines_url, params=params, timeout=10)
                kline_resp.raise_for_status()
                kline_data = kline_resp.json()
                
                if kline_data.get("code") != "0" or not kline_data.get("data"):
                    continue
                
                klines = kline_data["data"]
                if len(klines) < 20:  # Dados insuficientes
                    continue
                
                # Criar DataFrame com os dados de velas
                # OKX retorna: [timestamp, open, high, low, close, volume, volCcy, volCcyQuote, confirm]
                df = pd.DataFrame(klines)
                df.columns = ["timestamp", "open", "high", "low", "close", "volume", "volCcy", "volCcyQuote", "confirm"]
                
                # Converter tipos
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna()
                
                if len(df) < 20 or df["close"].nunique() < 5 or df["volume"].sum() == 0:
                    continue
                
                df["symbol"] = symbol.replace("-USDT", "/USDT")
                
                # ---------------- Indicadores ----------------
                rsi_period = get_rsi_period(timeframe)
                if len(df) < rsi_period:
                    continue
                    
                try:
                    # RSI & UO
                    df.ta.rsi(length=rsi_period, append=True)
                    rsi_col = f"RSI_{rsi_period}"
                    df.ta.uo(length=[7, 14, 28], append=True)
                    
                    # AO
                    hl2 = (df["high"] + df["low"]) / 2
                    df["AO"] = hl2.rolling(window=5).mean() - hl2.rolling(window=34).mean()
                    df["AO_diff"] = df["AO"].diff()
                    
                    # CMO
                    cmo_period = get_cmo_period(timeframe)
                    momm = df["close"].diff()
                    m1 = momm.where(momm >= 0, 0)
                    m2 = (-momm).where(momm < 0, 0)
                    sm1 = m1.rolling(window=cmo_period).sum()
                    sm2 = m2.rolling(window=cmo_period).sum()
                    df["CMO"] = 100 * (sm1 - sm2) / (sm1 + sm2)
                    df["CMO_prev"] = df["CMO"].shift(1)
                    
                    # KVO
                    fast_p, slow_p, trg_p = get_kvo_params(timeframe)
                    hlc3 = (df["high"] + df["low"] + df["close"]) / 3
                    trend_condition = hlc3 > hlc3.shift(1)
                    x_trend = df["volume"].where(trend_condition, -df["volume"]) * 100
                    x_fast = x_trend.ewm(span=fast_p).mean()
                    x_slow = x_trend.ewm(span=slow_p).mean()
                    df["KVO"] = x_fast - x_slow
                    df["KVO_trigger"] = df["KVO"].ewm(span=trg_p).mean()
                    
                    # DMI
                    dmi_p = get_dmi_period(timeframe)
                    df.ta.adx(length=dmi_p, append=True)
                    df["ADX"] = df[f"ADX_{dmi_p}"]
                    df["DI_plus"] = df[f"DMP_{dmi_p}"]
                    df["DI_minus"] = df[f"DMN_{dmi_p}"]
                    df["DI_plus_prev"] = df["DI_plus"].shift(1)
                    df["DI_minus_prev"] = df["DI_minus"].shift(1)
                    df["ADX_prev"] = df["ADX"].shift(1)

                    # OBV
                    obv_ma_p = get_obv_ma_period(timeframe)
                    obv_raw = (
                        df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df["volume"]
                    ).fillna(0)
                    df["OBV"] = obv_raw.cumsum()
                    df["OBV_MA"] = df["OBV"].ewm(span=obv_ma_p).mean()
                    df["OBV_prev"] = df["OBV"].shift(1)
                    df["OBV_MA_prev"] = df["OBV_MA"].shift(1)

                    # CMF
                    cmf_p = get_cmf_period(timeframe)
                    hl_rng = (df["high"] - df["low"]).replace(0, np.nan)
                    ad = ((2 * df["close"] - df["low"] - df["high"]) / hl_rng) * df["volume"]
                    cmf_num = ad.rolling(window=cmf_p).sum()
                    cmf_den = df["volume"].rolling(window=cmf_p).sum()
                    df["CMF"] = cmf_num / cmf_den
                    df["CMF_prev"] = df["CMF"].shift(1)

                    # Validação
                    if (
                        rsi_col not in df.columns
                        or "UO_7_14_28" not in df.columns
                        or "AO" not in df.columns
                        or "CMO" not in df.columns
                        or "KVO" not in df.columns
                        or "KVO_trigger" not in df.columns
                        or "OBV" not in df.columns
                        or "OBV_MA" not in df.columns
                        or "CMF" not in df.columns
                    ):
                        continue

                    df = df.dropna(
                        subset=[
                            rsi_col,
                            "UO_7_14_28",
                            "AO",
                            "CMO",
                            "KVO",
                            "KVO_trigger",
                            "OBV",
                            "OBV_MA",
                            "CMF",
                        ]
                    )
                    if len(df) == 0:
                        continue
                except Exception:
                    continue

                if len(df) < 2:
                    continue

                last_row = df.iloc[-1:].copy()
                last_row["UO_prev"] = df["UO_7_14_28"].iloc[-2]
                last_row["AO_prev"] = df["AO"].iloc[-2]
                last_row["CMO_prev"] = df["CMO"].iloc[-2]
                last_row["KVO_prev"] = df["KVO"].iloc[-2]
                last_row["KVO_trigger_prev"] = df["KVO_trigger"].iloc[-2]
                last_row["OBV_prev"] = df["OBV"].iloc[-2]
                last_row["OBV_MA_prev"] = df["OBV_MA"].iloc[-2]
                last_row["CMF_prev"] = df["CMF"].iloc[-2]

                if len(df) >= 4:
                    pct_change_3 = ((df["close"].iloc[-1] - df["close"].iloc[-4]) / df["close"].iloc[-4]) * 100
                    last_row["pct_change"] = pct_change_3
                else:
                    last_row["pct_change"] = 0.0

                all_data.append(last_row)
            except Exception:
                continue

        if not all_data:
            st.warning("Nenhum dado de velas retornado pela OKX.")
            return pd.DataFrame()
        
        final_df = pd.concat(all_data)
        return final_df.reset_index(drop=True)
        
    except Exception as e:
        st.error(f"Erro ao buscar dados da OKX: {str(e)}")
        return pd.DataFrame()

# ----------------- BingX DATA -----------------
@st.cache_data(ttl=600)  # Cache de 10 minutos
def get_bingx_data(timeframe: str, top_n: int = 200) -> pd.DataFrame:
    """Busca e processa dados Spot da BingX para os top N pares USDT usando CCXT."""
    try:
        # 1. Inicializar exchange BingX com CCXT
        exchange = ccxt.bingx({
            'enableRateLimit': True,
            'sandbox': False,  # Usar API de produção
        })
        
        # 2. Carregar mercados disponíveis
        markets = exchange.load_markets()
        
        # 3. Filtrar pares USDT do mercado spot
        usdt_spot_pairs = [
            symbol for symbol, market in markets.items()
            if market['spot'] and market['quote'] == 'USDT'
        ]
        
        if not usdt_spot_pairs:
            st.warning("⚠️ Nenhum par USDT Spot encontrado na BingX.")
            return pd.DataFrame()
        
        # 4. Buscar tickers para obter volume
        tickers = exchange.fetch_tickers(usdt_spot_pairs)
        
        # 5. Ordenar por volume e pegar top N
        pairs_with_volume = []
        for symbol in usdt_spot_pairs:
            if symbol in tickers:
                ticker = tickers[symbol]
                volume = ticker.get('quoteVolume', 0) or 0
                # Garantir que volume é numérico
                try:
                    volume = float(volume) if volume is not None else 0.0
                except (ValueError, TypeError):
                    volume = 0.0
                
                if volume > 0:
                    pairs_with_volume.append((symbol, volume))
        
        # Ordenar por volume decrescente e pegar top N
        pairs_with_volume.sort(key=lambda x: x[1], reverse=True)
        top_pairs = [pair[0] for pair in pairs_with_volume[:top_n]]

        if not top_pairs:
            st.warning("⚠️ Nenhum par com volume > 0 encontrado.")
            return pd.DataFrame()

        all_data: list[pd.DataFrame] = []

        # 6. Buscar dados OHLCV para cada par
        for symbol in top_pairs:
            try:
                # Usar CCXT para buscar dados OHLCV
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
                
                if len(ohlcv) < 20:
                    continue
                
                # Converter para DataFrame
                df = pd.DataFrame(ohlcv)  # type: ignore[arg-type]
                df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']  # type: ignore[assignment]
                
                # Converter timestamp para datetime
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                # Verificar se há dados válidos
                if len(df) < 20 or df["close"].nunique() < 5 or df["volume"].sum() == 0:
                    continue
                
                df["symbol"] = symbol
                
                # --- Indicadores (igual aos outros)
                rsi_period = get_rsi_period(timeframe)
                if len(df) < rsi_period:
                    continue
                    
                try:
                    # RSI & UO
                    df.ta.rsi(length=rsi_period, append=True)
                    rsi_col = f"RSI_{rsi_period}"
                    df.ta.uo(length=[7, 14, 28], append=True)
                    
                    # AO
                    hl2 = (df["high"] + df["low"]) / 2
                    df["AO"] = hl2.rolling(window=5).mean() - hl2.rolling(window=34).mean()
                    df["AO_diff"] = df["AO"].diff()
                    
                    # CMO
                    cmo_period = get_cmo_period(timeframe)
                    momm = df["close"].diff()
                    m1 = momm.where(momm >= 0, 0)
                    m2 = (-momm).where(momm < 0, 0)
                    sm1 = m1.rolling(window=cmo_period).sum()
                    sm2 = m2.rolling(window=cmo_period).sum()
                    df["CMO"] = 100 * (sm1 - sm2) / (sm1 + sm2)
                    df["CMO_prev"] = df["CMO"].shift(1)
                    
                    # KVO
                    fast_p, slow_p, trg_p = get_kvo_params(timeframe)
                    hlc3 = (df["high"] + df["low"] + df["close"]) / 3
                    trend_condition = hlc3 > hlc3.shift(1)
                    x_trend = df["volume"].where(trend_condition, -df["volume"]) * 100
                    x_fast = x_trend.ewm(span=fast_p).mean()
                    x_slow = x_trend.ewm(span=slow_p).mean()
                    df["KVO"] = x_fast - x_slow
                    df["KVO_trigger"] = df["KVO"].ewm(span=trg_p).mean()
                    
                    # DMI
                    dmi_p = get_dmi_period(timeframe)
                    df.ta.adx(length=dmi_p, append=True)
                    df["ADX"] = df[f"ADX_{dmi_p}"]
                    df["DI_plus"] = df[f"DMP_{dmi_p}"]
                    df["DI_minus"] = df[f"DMN_{dmi_p}"]
                    df["DI_plus_prev"] = df["DI_plus"].shift(1)
                    df["DI_minus_prev"] = df["DI_minus"].shift(1)
                    df["ADX_prev"] = df["ADX"].shift(1)

                    # OBV
                    obv_ma_p = get_obv_ma_period(timeframe)
                    obv_raw = (
                        df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df["volume"]
                    ).fillna(0)
                    df["OBV"] = obv_raw.cumsum()
                    df["OBV_MA"] = df["OBV"].ewm(span=obv_ma_p).mean()
                    df["OBV_prev"] = df["OBV"].shift(1)
                    df["OBV_MA_prev"] = df["OBV_MA"].shift(1)

                    # CMF
                    cmf_p = get_cmf_period(timeframe)
                    hl_rng = (df["high"] - df["low"]).replace(0, np.nan)
                    ad = ((2 * df["close"] - df["low"] - df["high"]) / hl_rng) * df["volume"]
                    cmf_num = ad.rolling(window=cmf_p).sum()
                    cmf_den = df["volume"].rolling(window=cmf_p).sum()
                    df["CMF"] = cmf_num / cmf_den
                    df["CMF_prev"] = df["CMF"].shift(1)

                    # Validação
                    if (
                        rsi_col not in df.columns
                        or "UO_7_14_28" not in df.columns
                        or "AO" not in df.columns
                        or "CMO" not in df.columns
                        or "KVO" not in df.columns
                        or "KVO_trigger" not in df.columns
                        or "OBV" not in df.columns
                        or "OBV_MA" not in df.columns
                        or "CMF" not in df.columns
                    ):
                        continue

                    df = df.dropna(
                        subset=[
                            rsi_col,
                            "UO_7_14_28",
                            "AO",
                            "CMO",
                            "KVO",
                            "KVO_trigger",
                            "OBV",
                            "OBV_MA",
                            "CMF",
                        ]
                    )
                    if len(df) == 0:
                        continue
                except Exception:
                    continue

                if len(df) < 2:
                    continue

                last_row = df.iloc[-1:].copy()
                last_row["UO_prev"] = df["UO_7_14_28"].iloc[-2]
                last_row["AO_prev"] = df["AO"].iloc[-2]
                last_row["CMO_prev"] = df["CMO"].iloc[-2]
                last_row["KVO_prev"] = df["KVO"].iloc[-2]
                last_row["KVO_trigger_prev"] = df["KVO_trigger"].iloc[-2]
                last_row["OBV_prev"] = df["OBV"].iloc[-2]
                last_row["OBV_MA_prev"] = df["OBV_MA"].iloc[-2]
                last_row["CMF_prev"] = df["CMF"].iloc[-2]

                if len(df) >= 4:
                    pct_change_3 = ((df["close"].iloc[-1] - df["close"].iloc[-4]) / df["close"].iloc[-4]) * 100
                    last_row["pct_change"] = pct_change_3
                else:
                    last_row["pct_change"] = 0.0

                all_data.append(last_row)
            except Exception:
                continue

        if not all_data:
            st.warning("Nenhum dado de velas retornado pela BingX.")
            return pd.DataFrame()
        
        final_df = pd.concat(all_data)
        return final_df.reset_index(drop=True)
        
    except Exception as e:
        st.error(f"Erro ao buscar dados da BingX: {str(e)}")
        return pd.DataFrame()

# ----------------- HUOBI DATA -----------------
@st.cache_data(ttl=600)  # Cache de 10 minutos

def get_huobi_data(timeframe: str, top_n: int = 200) -> pd.DataFrame:
    """Busca e processa dados Spot da HUOBI para os top N pares USDT.
    Reaproveita a mesma lógica de indicadores já aplicada no scanner."""
    try:
        # API v1 da HUOBI para tickers spot
        tickers_url = "https://api.huobi.pro/market/tickers"
        resp = requests.get(tickers_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        # Verificar se a resposta tem o formato esperado
        if data.get("status") != "ok" or not data.get("data"):
            st.warning("Resposta inesperada da API da HUOBI")
            return pd.DataFrame()
        
        tickers_list = data["data"]
        
        # Filtrar pares USDT e que tenham volume > 0
        usdt_tickers = []
        for ticker in tickers_list:
            symbol = ticker.get("symbol", "")
            vol = float(ticker.get("vol", 0) or 0)  # Volume em moeda base
            
            if symbol.endswith("usdt") and vol > 0:
                usdt_tickers.append({
                    "symbol": symbol,
                    "volume": vol
                })
        
        if not usdt_tickers:
            st.warning("Não foi possível encontrar pares USDT na HUOBI.")
            return pd.DataFrame()
        
        # Ordenar por volume e pegar os top N
        sorted_tickers = sorted(usdt_tickers, key=lambda x: x["volume"], reverse=True)
        top_symbols = [t["symbol"] for t in sorted_tickers[:top_n]]
        
        # Mapear timeframe para formato da HUOBI
        timeframe_map = {
            "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "60min", "2h": "2hour", "4h": "4hour", "1d": "1day"
        }
        
        huobi_timeframe = timeframe_map.get(timeframe, "60min")
        all_data: list[pd.DataFrame] = []
        
        for symbol in top_symbols:
            try:
                # API v1 da HUOBI para klines
                klines_url = f"https://api.huobi.pro/market/history/kline"
                params = {
                    "symbol": symbol,
                    "period": huobi_timeframe,
                    "size": 100
                }
                
                kline_resp = requests.get(klines_url, params=params, timeout=10)
                kline_resp.raise_for_status()
                kline_data = kline_resp.json()
                
                if kline_data.get("status") != "ok" or not kline_data.get("data"):
                    continue
                
                klines = kline_data["data"]
                if len(klines) < 20:  # Dados insuficientes
                    continue
                
                # Criar DataFrame com os dados de velas
                # HUOBI retorna: {id: timestamp, open, close, low, high, amount, vol, count}
                df = pd.DataFrame(klines)
                df = df[["id", "open", "high", "low", "close", "vol"]]
                df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
                
                # Converter tipos
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna()
                
                # Reverter ordem (HUOBI retorna mais recentes primeiro)
                df = df.sort_values("timestamp").reset_index(drop=True)
                
                if len(df) < 20 or df["close"].nunique() < 5 or df["volume"].sum() == 0:
                    continue
                
                df["symbol"] = symbol.upper().replace("USDT", "/USDT")
                
                # ---------------- Indicadores ----------------
                rsi_period = get_rsi_period(timeframe)
                if len(df) < rsi_period:
                    continue
                    
                try:
                    # RSI & UO
                    df.ta.rsi(length=rsi_period, append=True)
                    rsi_col = f"RSI_{rsi_period}"
                    df.ta.uo(length=[7, 14, 28], append=True)
                    
                    # AO
                    hl2 = (df["high"] + df["low"]) / 2
                    df["AO"] = hl2.rolling(window=5).mean() - hl2.rolling(window=34).mean()
                    df["AO_diff"] = df["AO"].diff()
                    
                    # CMO
                    cmo_period = get_cmo_period(timeframe)
                    momm = df["close"].diff()
                    m1 = momm.where(momm >= 0, 0)
                    m2 = (-momm).where(momm < 0, 0)
                    sm1 = m1.rolling(window=cmo_period).sum()
                    sm2 = m2.rolling(window=cmo_period).sum()
                    df["CMO"] = 100 * (sm1 - sm2) / (sm1 + sm2)
                    df["CMO_prev"] = df["CMO"].shift(1)
                    
                    # KVO
                    fast_p, slow_p, trg_p = get_kvo_params(timeframe)
                    hlc3 = (df["high"] + df["low"] + df["close"]) / 3
                    trend_condition = hlc3 > hlc3.shift(1)
                    x_trend = df["volume"].where(trend_condition, -df["volume"]) * 100
                    x_fast = x_trend.ewm(span=fast_p).mean()
                    x_slow = x_trend.ewm(span=slow_p).mean()
                    df["KVO"] = x_fast - x_slow
                    df["KVO_trigger"] = df["KVO"].ewm(span=trg_p).mean()
                    
                    # DMI
                    dmi_p = get_dmi_period(timeframe)
                    df.ta.adx(length=dmi_p, append=True)
                    df["ADX"] = df[f"ADX_{dmi_p}"]
                    df["DI_plus"] = df[f"DMP_{dmi_p}"]
                    df["DI_minus"] = df[f"DMN_{dmi_p}"]
                    df["DI_plus_prev"] = df["DI_plus"].shift(1)
                    df["DI_minus_prev"] = df["DI_minus"].shift(1)
                    df["ADX_prev"] = df["ADX"].shift(1)

                    # OBV
                    obv_ma_p = get_obv_ma_period(timeframe)
                    obv_raw = (
                        df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df["volume"]
                    ).fillna(0)
                    df["OBV"] = obv_raw.cumsum()
                    df["OBV_MA"] = df["OBV"].ewm(span=obv_ma_p).mean()
                    df["OBV_prev"] = df["OBV"].shift(1)
                    df["OBV_MA_prev"] = df["OBV_MA"].shift(1)

                    # CMF
                    cmf_p = get_cmf_period(timeframe)
                    hl_rng = (df["high"] - df["low"]).replace(0, np.nan)
                    ad = ((2 * df["close"] - df["low"] - df["high"]) / hl_rng) * df["volume"]
                    cmf_num = ad.rolling(window=cmf_p).sum()
                    cmf_den = df["volume"].rolling(window=cmf_p).sum()
                    df["CMF"] = cmf_num / cmf_den
                    df["CMF_prev"] = df["CMF"].shift(1)

                    # Validação
                    if (
                        rsi_col not in df.columns
                        or "UO_7_14_28" not in df.columns
                        or "AO" not in df.columns
                        or "CMO" not in df.columns
                        or "KVO" not in df.columns
                        or "KVO_trigger" not in df.columns
                        or "OBV" not in df.columns
                        or "OBV_MA" not in df.columns
                        or "CMF" not in df.columns
                    ):
                        continue

                    df = df.dropna(
                        subset=[
                            rsi_col,
                            "UO_7_14_28",
                            "AO",
                            "CMO",
                            "KVO",
                            "KVO_trigger",
                            "OBV",
                            "OBV_MA",
                            "CMF",
                        ]
                    )
                    if len(df) == 0:
                        continue
                except Exception:
                    continue

                if len(df) < 2:
                    continue

                last_row = df.iloc[-1:].copy()
                last_row["UO_prev"] = df["UO_7_14_28"].iloc[-2]
                last_row["AO_prev"] = df["AO"].iloc[-2]
                last_row["CMO_prev"] = df["CMO"].iloc[-2]
                last_row["KVO_prev"] = df["KVO"].iloc[-2]
                last_row["KVO_trigger_prev"] = df["KVO_trigger"].iloc[-2]
                last_row["OBV_prev"] = df["OBV"].iloc[-2]
                last_row["OBV_MA_prev"] = df["OBV_MA"].iloc[-2]
                last_row["CMF_prev"] = df["CMF"].iloc[-2]

                if len(df) >= 4:
                    pct_change_3 = ((df["close"].iloc[-1] - df["close"].iloc[-4]) / df["close"].iloc[-4]) * 100
                    last_row["pct_change"] = pct_change_3
                else:
                    last_row["pct_change"] = 0.0

                all_data.append(last_row)
            except Exception:
                continue

        if not all_data:
            st.warning("Nenhum dado de velas retornado pela HUOBI.")
            return pd.DataFrame()
        
        final_df = pd.concat(all_data)
        return final_df.reset_index(drop=True)
        
    except Exception as e:
        st.error(f"Erro ao buscar dados da HUOBI: {str(e)}")
        return pd.DataFrame()

# ----------------- PHEMEX DATA -----------------
@st.cache_data(ttl=600)  # Cache de 10 minutos
def get_phemex_data(timeframe: str, top_n: int = 200) -> pd.DataFrame:
    """Busca e processa dados Spot da PHEMEX para os top N pares USDT usando CCXT."""
    try:
        # 1. Inicializar exchange Phemex com CCXT
        exchange = ccxt.phemex({
            'enableRateLimit': True,
            'sandbox': False,  # Usar API de produção
        })
        
        # 2. Carregar mercados disponíveis
        markets = exchange.load_markets()
        
        # 3. Filtrar pares USDT do mercado spot
        usdt_spot_pairs = [
            symbol for symbol, market in markets.items()
            if market['spot'] and market['quote'] == 'USDT'
        ]
        
        if not usdt_spot_pairs:
            st.warning("⚠️ Nenhum par USDT Spot encontrado na Phemex.")
            return pd.DataFrame()
        
        # 4. Buscar tickers para obter volume
        tickers = exchange.fetch_tickers(usdt_spot_pairs)
        
        # 5. Ordenar por volume e pegar top N
        pairs_with_volume = []
        for symbol in usdt_spot_pairs:
            if symbol in tickers:
                ticker = tickers[symbol]
                volume = ticker.get('quoteVolume', 0) or 0
                # Garantir que volume é numérico
                try:
                    volume = float(volume) if volume is not None else 0.0
                except (ValueError, TypeError):
                    volume = 0.0
                
                if volume > 0:
                    pairs_with_volume.append((symbol, volume))
        
        # Ordenar por volume decrescente e pegar top N
        pairs_with_volume.sort(key=lambda x: x[1], reverse=True)
        top_pairs = [pair[0] for pair in pairs_with_volume[:top_n]]

        if not top_pairs:
            st.warning("⚠️ Nenhum par com volume > 0 encontrado.")
            return pd.DataFrame()

        all_data: list[pd.DataFrame] = []

        # 6. Buscar dados OHLCV para cada par
        for symbol in top_pairs:
            try:
                # Usar CCXT para buscar dados OHLCV
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
                
                if len(ohlcv) < 20:
                    continue
                
                # Converter para DataFrame
                df = pd.DataFrame(ohlcv)  # type: ignore[arg-type]
                df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']  # type: ignore[assignment]
                
                # Converter timestamp para datetime
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                # Verificar se há dados válidos
                if len(df) < 20 or df["close"].nunique() < 5 or df["volume"].sum() == 0:
                    continue
                
                df["symbol"] = symbol
                # --- Indicadores (igual aos outros)
                rsi_period = get_rsi_period(timeframe)
                if len(df) < rsi_period:
                    continue
                try:
                    df.ta.rsi(length=rsi_period, append=True)
                    rsi_col = f"RSI_{rsi_period}"
                    df.ta.uo(length=[7, 14, 28], append=True)
                    hl2 = (df["high"] + df["low"]) / 2
                    df["AO"] = hl2.rolling(window=5).mean() - hl2.rolling(window=34).mean()
                    df["AO_diff"] = df["AO"].diff()
                    cmo_period = get_cmo_period(timeframe)
                    momm = df["close"].diff()
                    m1 = momm.where(momm >= 0, 0)
                    m2 = (-momm).where(momm < 0, 0)
                    sm1 = m1.rolling(window=cmo_period).sum()
                    sm2 = m2.rolling(window=cmo_period).sum()
                    df["CMO"] = 100 * (sm1 - sm2) / (sm1 + sm2)
                    df["CMO_prev"] = df["CMO"].shift(1)
                    fast_p, slow_p, trg_p = get_kvo_params(timeframe)
                    hlc3 = (df["high"] + df["low"] + df["close"]) / 3
                    trend_condition = hlc3 > hlc3.shift(1)
                    x_trend = df["volume"].where(trend_condition, -df["volume"]) * 100
                    x_fast = x_trend.ewm(span=fast_p).mean()
                    x_slow = x_trend.ewm(span=slow_p).mean()
                    df["KVO"] = x_fast - x_slow
                    df["KVO_trigger"] = df["KVO"].ewm(span=trg_p).mean()
                    dmi_p = get_dmi_period(timeframe)
                    df.ta.adx(length=dmi_p, append=True)
                    df["ADX"] = df[f"ADX_{dmi_p}"]
                    df["DI_plus"] = df[f"DMP_{dmi_p}"]
                    df["DI_minus"] = df[f"DMN_{dmi_p}"]
                    df["DI_plus_prev"] = df["DI_plus"].shift(1)
                    df["DI_minus_prev"] = df["DI_minus"].shift(1)
                    df["ADX_prev"] = df["ADX"].shift(1)
                    obv_ma_p = get_obv_ma_period(timeframe)
                    obv_raw = (
                        df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df["volume"]
                    ).fillna(0)
                    df["OBV"] = obv_raw.cumsum()
                    df["OBV_MA"] = df["OBV"].ewm(span=obv_ma_p).mean()
                    df["OBV_prev"] = df["OBV"].shift(1)
                    df["OBV_MA_prev"] = df["OBV_MA"].shift(1)
                    cmf_p = get_cmf_period(timeframe)
                    hl_rng = (df["high"] - df["low"]).replace(0, np.nan)
                    ad = ((2 * df["close"] - df["low"] - df["high"]) / hl_rng) * df["volume"]
                    cmf_num = ad.rolling(window=cmf_p).sum()
                    cmf_den = df["volume"].rolling(window=cmf_p).sum()
                    df["CMF"] = cmf_num / cmf_den
                    df["CMF_prev"] = df["CMF"].shift(1)
                    if (
                        rsi_col not in df.columns
                        or "UO_7_14_28" not in df.columns
                        or "AO" not in df.columns
                        or "CMO" not in df.columns
                        or "KVO" not in df.columns
                        or "KVO_trigger" not in df.columns
                        or "OBV" not in df.columns
                        or "OBV_MA" not in df.columns
                        or "CMF" not in df.columns
                    ):
                        continue
                    df = df.dropna(
                        subset=[
                            rsi_col,
                            "UO_7_14_28",
                            "AO",
                            "CMO",
                            "KVO",
                            "KVO_trigger",
                            "OBV",
                            "OBV_MA",
                            "CMF",
                        ]
                    )
                    if len(df) == 0:
                        continue
                except Exception:
                    continue
                if len(df) < 2:
                    continue
                last_row = df.iloc[-1:].copy()
                last_row["UO_prev"] = df["UO_7_14_28"].iloc[-2]
                last_row["AO_prev"] = df["AO"].iloc[-2]
                last_row["CMO_prev"] = df["CMO"].iloc[-2]
                last_row["KVO_prev"] = df["KVO"].iloc[-2]
                last_row["KVO_trigger_prev"] = df["KVO_trigger"].iloc[-2]
                last_row["OBV_prev"] = df["OBV"].iloc[-2]
                last_row["OBV_MA_prev"] = df["OBV_MA"].iloc[-2]
                last_row["CMF_prev"] = df["CMF"].iloc[-2]
                if len(df) >= 4:
                    pct_change_3 = ((df["close"].iloc[-1] - df["close"].iloc[-4]) / df["close"].iloc[-4]) * 100
                    last_row["pct_change"] = pct_change_3
                else:
                    last_row["pct_change"] = 0.0
                all_data.append(last_row)
            except Exception:
                continue
        if not all_data:
            st.warning("Nenhum dado de velas retornado pela PHEMEX.")
            return pd.DataFrame()
        final_df = pd.concat(all_data)
        return final_df.reset_index(drop=True)
    except Exception as e:
        st.error(f"Erro ao buscar dados da PHEMEX: {str(e)}")
        return pd.DataFrame()

# Título e descrição
st.title("Scanner de Oportunidades Cripto")

# --- Barra Lateral (Sidebar) com os Filtros ---
st.sidebar.header("Filtros")

# Novo dropdown de Exchange (antes do timeframe)
exchange = st.sidebar.selectbox(
    "Exchange",
    ["Binance", "Bybit", "Bitget", "KuCoin", "OKX", "BingX", "HUOBI", "PHEMEX"],
    index=0
)

# Campo de busca
search_symbol = st.sidebar.text_input(
    "Buscar",
    placeholder="Ex: ADA, BTC, ETH..."
).upper()

timeframe = st.sidebar.selectbox(
    "Tempo Gráfico", 
    ['5m', '15m', '30m', '1h', '2h', '4h', '1d'], 
    index=2 # Padrão para 30m
)

# Filtro de direção do preço
price_direction = st.sidebar.selectbox(
    "Preço",
    [
        "Qualquer",
        "Up",
        "Down"
    ]
)

# Filtro de volume
volume_filter = st.sidebar.selectbox(
    "Volume",
    [
        "Qualquer",
        "Alto",
        "Baixo"
    ]
)

# --- Filtro RSI dinâmico ---
rsi_period = get_rsi_period(timeframe)
rsi_high, rsi_low = get_rsi_levels(timeframe)
rsi_col = f"RSI_{rsi_period}"

rsi_filter = st.sidebar.selectbox(
    f"RSI ({rsi_period})",
    [
        "Qualquer",
        f"RSI abaixo de {rsi_low}",
        f"RSI acima de {rsi_high}"
    ]
)

# Filtro Ultimate Oscillator
uo_filter = st.sidebar.selectbox(
    "Ultimate Oscillator",
    [
        "Qualquer",
        "Cruzamento de Alta (30↑)",
        "Cruzamento de Baixa (70↓)"
    ]
)

# Filtro Awesome Oscillator
ao_filter = st.sidebar.selectbox(
    "Awesome Oscillator",
    [
        "Qualquer",
        "Cruzamento Linha Zero ↑",
        "Cruzamento Linha Zero ↓",
        "Mudança para Verde",
        "Mudança para Vermelho"
    ]
)

# Novo filtro de cor do AO
ao_color_filter = st.sidebar.selectbox(
    "Cor AO",
    [
        "Qualquer",
        "Amarela",
        "Laranja",
        "Verde",
        "Vermelha"
    ]
)

# Filtro Chande Momentum Oscillator (CMO)
# Obter níveis dinâmicos baseados no timeframe
cmo_high, cmo_low = get_cmo_levels(timeframe)
cmo_period = get_cmo_period(timeframe)

cmo_filter = st.sidebar.selectbox(
    "CMO",
    [
        "Qualquer",
        f"Saída Sobrevenda ({cmo_low}↑)",
        f"Saída Sobrecompra ({cmo_high}↓)", 
        "Cruzamento Zero ↑",
        "Cruzamento Zero ↓"
    ]
)

# Filtro Klinger Volume Oscillator (KVO)
# Obter parâmetros dinâmicos baseados no timeframe
fast_kvo, slow_kvo, trigger_kvo = get_kvo_params(timeframe)

kvo_filter = st.sidebar.selectbox(
    f"KVO ({fast_kvo},{slow_kvo},{trigger_kvo})",
    [
        "Qualquer",
        "KVO cruza acima Sinal ↑",
        "KVO cruza abaixo Sinal ↓",
        "KVO cruza acima Zero ↑",
        "KVO cruza abaixo Zero ↓"
    ]
)

# Filtro On Balance Volume (OBV)
obv_ma_period = get_obv_ma_period(timeframe)

obv_filter = st.sidebar.selectbox(
    f"OBV × EMA {obv_ma_period}",
    [
        "Qualquer",
        "OBV acima da EMA",
        "OBV abaixo da EMA",
        "Cruzamento Alta (OBV↑EMA)",
        "Cruzamento Baixa (OBV↓EMA)"
    ]
)

# Filtro Chaikin Money Flow (CMF)
cmf_period = get_cmf_period(timeframe)
cmf_pos_th, cmf_neg_th = get_cmf_thresholds(timeframe)

cmf_filter = st.sidebar.selectbox(
    f"CMF ({cmf_period})",
    [
        "Qualquer",
        "Cruzamento Alta (0↑)",
        "Cruzamento Baixa (0↓)",
        f"CMF > {cmf_pos_th}",
        f"CMF < {cmf_neg_th}"
    ]
)

# --- Área Principal (Resultados) ---

# Dicionário de todas as funções de busca de dados
exchange_functions = {
    "Binance": get_binance_data,
    "Bybit": get_bybit_data,
    "Bitget": get_bitget_data,
    "KuCoin": get_kucoin_data,
    "OKX": get_okx_data,
    "BingX": get_bingx_data,
    "HUOBI": get_huobi_data,
    "PHEMEX": get_phemex_data
}

# Inicializar o estado da sessão se não existir
st.session_state.setdefault('last_full_fetch', 0)
st.session_state.setdefault('cached_timeframe', None)
st.session_state.setdefault('all_data_cache', {name: pd.DataFrame() for name in exchange_functions})
st.session_state.setdefault('is_preloading', False)
st.session_state.setdefault('preload_data_cache', None)

force_refresh = False
current_time = time.time()
REFRESH_INTERVAL = 420  # 7 minutos
PRELOAD_TRIGGER = 240   # Quando atingir 240s, começa a pré-carregar

# Força a atualização se passaram mais de 7 minutos
if (current_time - st.session_state.last_full_fetch) > REFRESH_INTERVAL:
    force_refresh = True

# Força a atualização se o timeframe mudou
if st.session_state.cached_timeframe != timeframe:
    force_refresh = True

if force_refresh:
    progress_bar = st.progress(0, text="Iniciando busca de dados...")
    with ThreadPoolExecutor(max_workers=len(exchange_functions)) as executor:
        future_to_exchange = {
            executor.submit(func, timeframe): name 
            for name, func in exchange_functions.items()
        }
        all_data = {}
        completed_count = 0
        total_count = len(exchange_functions)
        for future in as_completed(future_to_exchange):
            exchange_name = future_to_exchange[future]
            try:
                data = future.result()
                all_data[exchange_name] = data if data is not None else pd.DataFrame()
            except Exception as e:
                st.error(f"Erro ao buscar {exchange_name}: {e}")
                all_data[exchange_name] = pd.DataFrame()
            completed_count += 1
            progress = completed_count / total_count
            progress_bar.progress(progress, text=f"Carregando... {exchange_name} ({completed_count}/{total_count})")
    st.session_state.all_data_cache = all_data
    st.session_state.cached_timeframe = timeframe
    st.session_state.last_full_fetch = current_time
    st.session_state.is_preloading = False
    st.session_state.preload_data_cache = None
    progress_bar.empty()
    st.rerun()

# Recupera o DataFrame da exchange selecionada do cache
df = st.session_state.all_data_cache.get(exchange, pd.DataFrame())

# Lógica de auto-refresh (mantida para recarregar a página e disparar a lógica acima)
if 'last_update' not in st.session_state:
    st.session_state.last_update = time.time()

current_time = time.time()
time_since_update = current_time - st.session_state.last_update

# --- PRÉ-CARREGAMENTO INTELIGENTE ---
if time_since_update >= PRELOAD_TRIGGER and not st.session_state.is_preloading:
    st.session_state.is_preloading = True
    st.session_state.preload_data_cache = None
    st.experimental_set_query_params(preloading='1')
    st.rerun()

# Se está em modo de pré-carregamento, buscar dados em background
if st.session_state.is_preloading and st.session_state.preload_data_cache is None:
    st.info("Atualizando dados em segundo plano...")
    with ThreadPoolExecutor(max_workers=len(exchange_functions)) as executor:
        future_to_exchange = {
            executor.submit(func, timeframe): name 
            for name, func in exchange_functions.items()
        }
        all_data = {}
        for future in as_completed(future_to_exchange):
            exchange_name = future_to_exchange[future]
            try:
                data = future.result()
                all_data[exchange_name] = data if data is not None else pd.DataFrame()
            except Exception as e:
                all_data[exchange_name] = pd.DataFrame()
        st.session_state.preload_data_cache = all_data
    st.rerun()

# Quando o pré-carregamento termina, substitui o cache principal e reinicia o timer
if st.session_state.is_preloading and st.session_state.preload_data_cache is not None:
    st.session_state.all_data_cache = st.session_state.preload_data_cache
    now = time.time()
    st.session_state.last_full_fetch = now
    st.session_state.last_update = now
    st.session_state.is_preloading = False
    st.session_state.preload_data_cache = None
    st.experimental_set_query_params(preloading=None)
    st.rerun()

# Se mais de 7 minutos se passaram, reseta o timer para o momento atual
if time_since_update >= REFRESH_INTERVAL:
    st.session_state.last_update = time.time()
    time_since_update = 0

next_update_in = REFRESH_INTERVAL - (time.time() - st.session_state.last_update)
countdown_start = int(max(next_update_in, 0))
components.html(
    f"""
    <div id="countdown" style='font-size:18px; font-weight:bold; color:#FF7F00; margin-bottom:6px;'>
        ⏱️ Próxima atualização em: {countdown_start}s
    </div>
    <script>
        var seconds = {countdown_start};
        var countdownElement = document.getElementById("countdown");
        var interval = setInterval(function() {{
            seconds--;
            if (seconds < 0) {{
                countdownElement.innerHTML = "⏱️ Atualizando...";
                clearInterval(interval);
                window.parent.location.reload();
            }} else {{
                countdownElement.innerHTML = "⏱️ Próxima atualização em: " + seconds + "s";
            }}
        }}, 1000);
    </script>
    """,
    height=40,
)

# Se o DataFrame estiver vazio, mostra uma mensagem. Senão, processa e exibe.
if df.empty:
    st.warning(f"Nenhum dado encontrado para a exchange '{exchange}' no timeframe '{timeframe}'. Verifique os filtros ou aguarde a próxima atualização.")
else:
    # --- FILTROS ADICIONAIS ---

    # 1. Filtro de RSI
    df_filtered = df.copy()

    # Adicionar coluna de cor do AO para filtragem
    def label_ao_color(row):
        ao_val = row['AO']
        ao_diff = row['AO_diff']
        if ao_val < 0:
            if ao_diff > 0:
                return "Amarela"
            else:
                return "Vermelha"
        elif ao_val > 0:
            if ao_diff < 0:
                return "Laranja"
            else:
                return "Verde"
        else:
            return "Neutra"

    df_filtered['AO_color'] = df_filtered.apply(label_ao_color, axis=1)

    # Filtro de busca por símbolo
    if search_symbol:
        df_filtered = df_filtered[df_filtered['symbol'].str.contains(search_symbol, case=False, na=False)]

    # 0. Filtro de direção do preço (% variação)
    if price_direction == "Up":
        df_filtered = df_filtered[df_filtered['pct_change'] > 0]
        # Ordenar por % decrescente (maiores primeiro)
        df_filtered = df_filtered.sort_values('pct_change', ascending=False)
    elif price_direction == "Down":
        df_filtered = df_filtered[df_filtered['pct_change'] < 0]
        # Ordenar por % crescente (menores/mais negativos primeiro)
        df_filtered = df_filtered.sort_values('pct_change', ascending=True)

    # Filtro de volume (baseado na mediana do dataset)
    if volume_filter == "Alto":
        volume_median = df['volume'].median()
        df_filtered = df_filtered[df_filtered['volume'] > volume_median]
        # Ordenar por volume decrescente (maiores primeiro)
        df_filtered = df_filtered.sort_values('volume', ascending=False)
    elif volume_filter == "Baixo":
        volume_median = df['volume'].median()
        df_filtered = df_filtered[df_filtered['volume'] <= volume_median]
        # Ordenar por volume crescente (menores primeiro)
        df_filtered = df_filtered.sort_values('volume', ascending=True)

    if rsi_filter == f"RSI abaixo de {rsi_low}":
        df_filtered = df_filtered[df_filtered[rsi_col] <= rsi_low]
    elif rsi_filter == f"RSI acima de {rsi_high}":
        df_filtered = df_filtered[df_filtered[rsi_col] >= rsi_high]

    # 2. Filtro de UO
    if uo_filter == "Cruzamento de Alta (30↑)":
        df_filtered = df_filtered[(df_filtered['UO_prev'] < 30) & (df_filtered['UO_7_14_28'] >= 30)]
    elif uo_filter == "Cruzamento de Baixa (70↓)":
        df_filtered = df_filtered[(df_filtered['UO_prev'] > 70) & (df_filtered['UO_7_14_28'] <= 70)]

    # 3. Filtro de AO
    if ao_filter == "Cruzamento Linha Zero ↑":
        df_filtered = df_filtered[(df_filtered['AO_prev'] < 0) & (df_filtered['AO'] >= 0)]
    elif ao_filter == "Cruzamento Linha Zero ↓":
        df_filtered = df_filtered[(df_filtered['AO_prev'] > 0) & (df_filtered['AO'] <= 0)]
    elif ao_filter == "Mudança para Verde":
        df_filtered = df_filtered[df_filtered['AO_diff'] > 0]
    elif ao_filter == "Mudança para Vermelho":
        df_filtered = df_filtered[df_filtered['AO_diff'] < 0]

    # 3b. Filtro de cor do AO
    if ao_color_filter != "Qualquer":
        df_filtered = df_filtered[df_filtered['AO_color'] == ao_color_filter]

    # 4. Filtro de CMO
    if cmo_filter == "Qualquer":
        pass
    elif cmo_filter == f"Saída Sobrevenda ({cmo_low}↑)":
        df_filtered = df_filtered[(df_filtered['CMO_prev'] < cmo_low) & (df_filtered['CMO'] >= cmo_low)]
    elif cmo_filter == f"Saída Sobrecompra ({cmo_high}↓)":
        df_filtered = df_filtered[(df_filtered['CMO_prev'] > cmo_high) & (df_filtered['CMO'] <= cmo_high)]
    elif cmo_filter == "Cruzamento Zero ↑":
        df_filtered = df_filtered[(df_filtered['CMO_prev'] < 0) & (df_filtered['CMO'] >= 0)]
    elif cmo_filter == "Cruzamento Zero ↓":
        df_filtered = df_filtered[(df_filtered['CMO_prev'] > 0) & (df_filtered['CMO'] <= 0)]

    # 5. Filtro de KVO
    if kvo_filter == "Qualquer":
        pass
    elif kvo_filter == "KVO cruza acima Sinal ↑":
        df_filtered = df_filtered[(df_filtered['KVO_prev'] < df_filtered['KVO_trigger_prev']) & (df_filtered['KVO'] > df_filtered['KVO_trigger'])]
    elif kvo_filter == "KVO cruza abaixo Sinal ↓":
        df_filtered = df_filtered[(df_filtered['KVO_prev'] > df_filtered['KVO_trigger_prev']) & (df_filtered['KVO'] < df_filtered['KVO_trigger'])]
    elif kvo_filter == "KVO cruza acima Zero ↑":
        df_filtered = df_filtered[(df_filtered['KVO_prev'] < 0) & (df_filtered['KVO'] > 0)]
    elif kvo_filter == "KVO cruza abaixo Zero ↓":
        df_filtered = df_filtered[(df_filtered['KVO_prev'] > 0) & (df_filtered['KVO'] < 0)]

    # 6. Filtro de OBV
    if obv_filter == "Qualquer":
        pass
    elif obv_filter == "OBV acima da EMA":
        df_filtered = df_filtered[(df_filtered['OBV'] > df_filtered['OBV_MA'])]
    elif obv_filter == "OBV abaixo da EMA":
        df_filtered = df_filtered[(df_filtered['OBV'] < df_filtered['OBV_MA'])]
    elif obv_filter == "Cruzamento Alta (OBV↑EMA)":
        df_filtered = df_filtered[(df_filtered['OBV_prev'] < df_filtered['OBV_MA_prev']) & (df_filtered['OBV'] >= df_filtered['OBV_MA'])]
    elif obv_filter == "Cruzamento Baixa (OBV↓EMA)":
        df_filtered = df_filtered[(df_filtered['OBV_prev'] > df_filtered['OBV_MA_prev']) & (df_filtered['OBV'] <= df_filtered['OBV_MA'])]

    # 7. Filtro de CMF
    if cmf_filter == "Qualquer":
        pass
    elif cmf_filter == "Cruzamento Alta (0↑)":
        df_filtered = df_filtered[(df_filtered['CMF_prev'] < 0) & (df_filtered['CMF'] >= 0)]
    elif cmf_filter == "Cruzamento Baixa (0↓)":
        df_filtered = df_filtered[(df_filtered['CMF_prev'] > 0) & (df_filtered['CMF'] <= 0)]
    elif cmf_filter == f"CMF > {cmf_pos_th}":
        df_filtered = df_filtered[(df_filtered['CMF'] > cmf_pos_th)]
    elif cmf_filter == f"CMF < {cmf_neg_th}":
        df_filtered = df_filtered[(df_filtered['CMF'] < cmf_neg_th)]

    placeholder_success = st.empty()
    placeholder_success.success(f"Encontradas {len(df_filtered)} moedas com os critérios selecionados.")
    time.sleep(3)
    placeholder_success.empty()

    # --- Funções de Badge para outros indicadores ---
    def make_badge(text, bg_color):
        return f'<span style="background-color:{bg_color}; color:black; padding:2px 6px; border-radius:6px; display:inline-block;">{text}</span>'

    # Preço (% change)
    def pct_to_badge(pct):
        color = "#2ECC71" if pct > 0 else "#FF4D4D"
        return make_badge(f"{pct:.2f}%", color)

    # RSI badge
    def rsi_to_badge(val):
        if val < 30:
            color = "#2ECC71"  # verde
        elif val > 70:
            color = "#FF4D4D"  # vermelho
        else:
            color = "#D3D3D3"  # neutro
        return make_badge(f"{val:.2f}", color)

    # UO badge
    def uo_to_badge(val):
        if val < 30:
            color = "#2ECC71"
        elif val > 70:
            color = "#FF4D4D"
        else:
            color = "#D3D3D3"
        return make_badge(f"{val:.2f}", color)

    # CMO badge
    def cmo_to_badge(val):
        if val > 40:
            color = "#FF4D4D"  # vermelho
        elif val > -50:
            color = "#2ECC71"  # verde
        else:
            color = "#D3D3D3"  # neutro
        return make_badge(f"{val:.2f}", color)

    # KVO badge (comparar com sinal)
    def kvo_to_badge(kvo_val, kvo_trg):
        color = "#2ECC71" if kvo_val >= kvo_trg else "#FF4D4D"
        return make_badge(f"{kvo_val:.0f}", color)

    # OBV badge (divergência)
    def obv_to_badge(obv_now, obv_prev, pct):
        if obv_now > obv_prev and pct <= 0:
            color = "#2ECC71"  # bullish divergence
        elif obv_now < obv_prev and pct >= 0:
            color = "#FF4D4D"  # bearish divergence
        else:
            color = "#D3D3D3"  # neutro
        return make_badge(f"{obv_now:.0f}", color)

    # CMF badge
    def cmf_to_badge(val):
        if val > 0.1:
            color = "#2ECC71"
        elif val < -0.1:
            color = "#FF4D4D"
        else:
            color = "#D3D3D3"
        return make_badge(f"{val:.2f}", color)

    # AO badge (mantendo lógica anterior com laranja intensa)
    def ao_to_badge(row):
        ao_val = row['AO']
        ao_diff = row['AO_diff']
        if ao_val < 0:
            if ao_diff > 0:
                color = "#FFD700"  # amarelo
            else:
                color = "#FF4D4D"  # vermelho
        elif ao_val > 0:
            if ao_diff < 0:
                color = "#FF7F00"  # laranja intensa
            else:
                color = "#2ECC71"  # verde
        else:
            color = "#D3D3D3"
        return make_badge(f"{ao_val:.6f}", color)

    # --- DMI Badges ---
    def di_plus_badge(row):
        if row['DI_plus'] > row['DI_minus']:
            color = "#2ECC71"  # verde tendência alta dominante
        else:
            color = "#FF4D4D"  # vermelho
        return make_badge(f"{row['DI_plus']:.2f}", color)

    def di_minus_badge(row):
        if row['DI_minus'] > row['DI_plus']:
            color = "#FF4D4D"  # vermelho tendência baixa dominante
        else:
            color = "#2ECC71"  # verde
        return make_badge(f"{row['DI_minus']:.2f}", color)

    def adx_badge(val):
        th = 25 if timeframe == '1d' else 20
        color = "#2ECC71" if val >= th else "#FF4D4D"
        return make_badge(f"{val:.2f}", color)

    # Gerar colunas HTML
    df_filtered['pct_html'] = df_filtered['pct_change'].apply(pct_to_badge)
    df_filtered['RSI_html'] = df_filtered[rsi_col].apply(rsi_to_badge)
    df_filtered['UO_html'] = df_filtered['UO_7_14_28'].apply(uo_to_badge)
    df_filtered['AO_html'] = df_filtered.apply(ao_to_badge, axis=1)
    df_filtered['CMO_html'] = df_filtered['CMO'].apply(cmo_to_badge)
    df_filtered['KVO_html'] = df_filtered.apply(lambda r: kvo_to_badge(r['KVO'], r['KVO_trigger']), axis=1)
    df_filtered['OBV_html'] = df_filtered.apply(lambda r: obv_to_badge(r['OBV'], r['OBV_prev'], r['pct_change']), axis=1)
    df_filtered['CMF_html'] = df_filtered['CMF'].apply(cmf_to_badge)
    df_filtered['DI_plus_html'] = df_filtered.apply(di_plus_badge, axis=1)
    df_filtered['DI_minus_html'] = df_filtered.apply(di_minus_badge, axis=1)
    df_filtered['ADX_html'] = df_filtered['ADX'].apply(adx_badge)

    # --- Exibição da Tabela ---

    # Selecionar e renomear colunas para exibição (usando versões HTML)
    df_display = df_filtered[['symbol', 'pct_html', 'volume', 'RSI_html', 'UO_html', 'AO_html', 'CMO_html', 'KVO_html', 'OBV_html', 'CMF_html', 'DI_plus_html', 'DI_minus_html', 'ADX_html']].copy()

    # Criar links para TradingView
    def create_tradingview_link(symbol):
        """Cria link do TradingView dinâmico baseado na exchange escolhida."""
        tv_symbol = symbol.replace('/', '')  # Ex: BTC/USDT -> BTCUSDT

        # Determinar prefixo pelo selectbox de exchange
        if exchange == "Binance":
            tv_prefix = "BINANCE:"
        elif exchange == "Bybit":
            tv_prefix = "BYBIT:"
        elif exchange == "Bitget":
            tv_prefix = "BITGET:"
        elif exchange == "KuCoin":
            tv_prefix = "KUCOIN:"
        elif exchange == "OKX":
            tv_prefix = "OKX:"
        elif exchange == "BingX":
            tv_prefix = "BINGX:"
            # Para BingX, alguns símbolos podem não estar disponíveis no TradingView
            # Adicionar fallback para Binance como alternativa
        elif exchange == "HUOBI":
            tv_prefix = "HUOBI:"
        elif exchange == "PHEMEX":
            tv_prefix = "PHEMEX:"
        else:
            tv_prefix = ""  # fallback

        tv_url = f"https://www.tradingview.com/chart/?symbol={tv_prefix}{tv_symbol}"
        
        # Para BingX, adicionar link alternativo para Binance caso o principal não funcione
        if exchange == "BingX":
            binance_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{tv_symbol}"
            return (
                f'<a href="{tv_url}" target="_blank" '
                f'style="text-decoration: none; font-size: 18px;" '
                f'title="Ver no TradingView (BingX - clique com botão direito para Binance se não abrir)">📈</a>'
            )
        else:
            return (
                f'<a href="{tv_url}" target="_blank" '
                f'style="text-decoration: none; font-size: 18px;">📈</a>'
            )

    # Aplicar a função para criar os links
    df_display['TradingView'] = df_display['symbol'].apply(create_tradingview_link)

    # Reordenar colunas para mostrar o link ao lado do símbolo
    df_display = df_display[['symbol', 'TradingView', 'pct_html', 'volume', 'RSI_html', 'UO_html', 'AO_html', 'CMO_html', 'KVO_html', 'OBV_html', 'CMF_html', 'DI_plus_html', 'DI_minus_html', 'ADX_html']]

    df_display = df_display.rename(columns={
        'symbol': 'Par',
        'TradingView': 'Gráfico',
        'pct_html': '%',
        'volume': 'Volume (Moeda)',
        'RSI_html': 'RSI',
        'UO_html': 'UO',
        'AO_html': 'AO',
        'CMO_html': 'CMO',
        'KVO_html': 'KVO',
        'OBV_html': 'OBV',
        'CMF_html': 'CMF',
        'DI_plus_html': '+ DI',
        'DI_minus_html': '- DI',
        'ADX_html': 'ADX'
    })

    # Aplicar formatação de números
    styled_df = df_display.style.format({
        'Volume (Moeda)': '{:.2f}'
    })

    # CSS para centralizar conteúdo da tabela
    st.markdown("""
    <style>
    table {
        text-align: center !important;
    }
    th {
        text-align: center !important;
        vertical-align: middle !important;
    }
    td {
        text-align: center !important;
        vertical-align: middle !important;
    }
    thead th {
        position: sticky;
        top: 0;
        background-color: black;
        color: white !important;
        z-index: 1;
    }
    table {
        filter: brightness(0.9);
    }
    </style>
    """, unsafe_allow_html=True)

    # Exibir tabela com HTML habilitado para os links funcionarem
    st.write(styled_df.to_html(escape=False), unsafe_allow_html=True)

# Para rodar este aplicativo, salve o arquivo como app.py e execute no seu terminal:
# streamlit run app.py 