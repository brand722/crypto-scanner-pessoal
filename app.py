import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
import pandas_ta as ta
import ccxt
import streamlit.components.v1 as components
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import json
import warnings
from binance.client import Client

# Suprimir warnings do pandas sobre SettingWithCopyWarning
warnings.filterwarnings('ignore', category=pd.errors.SettingWithCopyWarning)

# Garantir que o horário da última atualização sempre exista
if 'data_update_timestamp' not in st.session_state:
    st.session_state.data_update_timestamp = time.time()

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

@st.cache_data(ttl=300) # Cache de 10 minutos
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

# --- Nova função para garantir cálculo único de indicadores ---

def compute_indicators(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Calcula todos os indicadores técnicos usados no scanner de forma padronizada.
    Caso as colunas já existam, elas serão sobrescritas garantindo consistência entre exchanges."""
    if df.empty:
        return df

    # --- RSI ---
    rsi_period = get_rsi_period(timeframe)
    if len(df) >= rsi_period:
        df.ta.rsi(length=rsi_period, append=True)
    
    # --- Ultimate Oscillator (UO) ---
    df.ta.uo(length=[7, 14, 28], append=True)

    # --- Awesome Oscillator (AO) ---
    hl2 = (df["high"] + df["low"]) / 2  # type: ignore[operator]
    df["AO"] = hl2.rolling(window=5).mean() - hl2.rolling(window=34).mean()
    df["AO_diff"] = df["AO"].diff()  # type: ignore[attr-defined]

    # --- Chande Momentum Oscillator (CMO) ---
    cmo_period = get_cmo_period(timeframe)
    momm = df["close"].diff()  # type: ignore[attr-defined]
    m1 = momm.where(momm >= 0, 0)
    m2 = (-momm).where(momm < 0, 0)
    sm1 = m1.rolling(window=cmo_period).sum()  # type: ignore[attr-defined]
    sm2 = m2.rolling(window=cmo_period).sum()  # type: ignore[attr-defined]
    df["CMO"] = 100 * (sm1 - sm2) / (sm1 + sm2)

    # --- Klinger Volume Oscillator (KVO) ---
    fast_p, slow_p, trg_p = get_kvo_params(timeframe)
    hlc3 = (df["high"] + df["low"] + df["close"]) / 3
    trend_condition = hlc3 > hlc3.shift(1)
    x_trend = df["volume"].where(trend_condition, -df["volume"]) * 100  # type: ignore[attr-defined]
    x_fast = x_trend.ewm(span=fast_p).mean()
    x_slow = x_trend.ewm(span=slow_p).mean()
    df["KVO"] = x_fast - x_slow
    df["KVO_trigger"] = df["KVO"].ewm(span=trg_p).mean()

    # --- Directional Movement Index (DMI) ---
    dmi_period = get_dmi_period(timeframe)
    df.ta.adx(length=dmi_period, append=True)
    df["ADX"] = df[f"ADX_{dmi_period}"]
    df["DI_plus"] = df[f"DMP_{dmi_period}"]
    df["DI_minus"] = df[f"DMN_{dmi_period}"]

    # --- On Balance Volume (OBV) ---
    obv_ma_p = get_obv_ma_period(timeframe)
    obv_raw = (
        df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df["volume"]
    ).fillna(0)
    df["OBV"] = obv_raw.cumsum()
    df["OBV_MA"] = df["OBV"].ewm(span=obv_ma_p).mean()

    # --- Chaikin Money Flow (CMF) ---
    cmf_p = get_cmf_period(timeframe)
    hl_rng = (df["high"] - df["low"]).replace(0, np.nan)
    ad = ((2 * df["close"] - df["low"] - df["high"]) / hl_rng) * df["volume"]
    cmf_num = ad.rolling(window=cmf_p).sum()
    cmf_den = df["volume"].rolling(window=cmf_p).sum()
    df["CMF"] = cmf_num / cmf_den

    return df

def standardize_final_data(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Padroniza a estrutura final dos dados para todas as exchanges.
    Garante que todos os dados tenham a mesma estrutura e cálculos.
    """
    # Garantir que os indicadores estejam atualizados e consistentes
    df = compute_indicators(df, timeframe)

    if len(df) < 2:
        return pd.DataFrame()
    
    # Pegar apenas a última linha (dados mais recentes)
    last_row = df.iloc[-1:].copy()
    
    # Garantir que temos dados anteriores para cálculos
    if len(df) >= 2:
        last_row["UO_prev"] = df["UO_7_14_28"].iloc[-2]
        last_row["AO_prev"] = df["AO"].iloc[-2]
        last_row["CMO_prev"] = df["CMO"].iloc[-2]
        last_row["KVO_prev"] = df["KVO"].iloc[-2]
        last_row["KVO_trigger_prev"] = df["KVO_trigger"].iloc[-2]
        last_row["OBV_prev"] = df["OBV"].iloc[-2]
        last_row["OBV_MA_prev"] = df["OBV_MA"].iloc[-2]
        last_row["CMF_prev"] = df["CMF"].iloc[-2]
    
    # Calcular % de mudança padronizada (últimas 3 velas)
    if len(df) >= 4:
        pct_change_3 = ((df["close"].iloc[-1] - df["close"].iloc[-4]) / df["close"].iloc[-4]) * 100
        last_row["pct_change"] = pct_change_3
    else:
        last_row["pct_change"] = 0.0
    
    # Garantir que temos informações de preço e volume
    last_row["price"] = df["close"].iloc[-1]
    
    # Adicionar timestamp de processamento para debug
    last_row["processed_at"] = pd.Timestamp.now()
    
    # Validar se todos os indicadores essenciais estão presentes
    required_cols = ['UO_7_14_28', 'AO', 'CMO', 'KVO', 'KVO_trigger', 'OBV', 'OBV_MA', 'CMF']
    missing_cols = [col for col in required_cols if col not in last_row.columns or pd.isna(last_row[col].iloc[0])]
    
    if missing_cols:
        # Retornar DataFrame vazio se dados essenciais estão ausentes
        return pd.DataFrame()
    
    return last_row

def debug_exchange_data(df: pd.DataFrame, exchange_name: str) -> None:
    """
    Função de debug para verificar a qualidade dos dados da exchange.
    """
    if df.empty:
        st.warning(f"⚠️ {exchange_name}: Nenhum dado retornado")
        return
    
    # Verificar se há valores NaN nos indicadores principais
    nan_cols = df.columns[df.isnull().any()].tolist()
    if nan_cols:
        st.warning(f"⚠️ {exchange_name}: Valores NaN encontrados em: {', '.join(nan_cols)}")
    
    # Verificar consistência de pct_change
    if 'pct_change' in df.columns:
        extreme_changes = df[abs(df['pct_change']) > 50]  # Mudanças extremas (>50%)
        if not extreme_changes.empty:
            st.warning(f"⚠️ {exchange_name}: {len(extreme_changes)} moedas com mudanças extremas (>50%)")
    
    # Log de sucesso
    st.success(f"✅ {exchange_name}: {len(df)} moedas processadas com sucesso")

# ----------------- Bybit DATA -----------------
@st.cache_data(ttl=300)  # Cache de 10 minutos

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

                # Usar função padronizada para estruturar dados finais
                standardized_row = standardize_final_data(df, timeframe)
                if not standardized_row.empty:
                    all_data.append(standardized_row)
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
@st.cache_data(ttl=300)  # Cache de 10 minutos
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

                # Usar função padronizada para estruturar dados finais
                standardized_row = standardize_final_data(df, timeframe)
                if not standardized_row.empty:
                    all_data.append(standardized_row)
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
@st.cache_data(ttl=300)  # Cache de 10 minutos

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
                    "type": kucoin_timeframe,
                    # "limit" não é um parâmetro suportado para candles na V1,
                    # a API retorna por padrão um número fixo de velas recentes.
                }
                
                kline_resp = requests.get(klines_url, params=params, timeout=10)
                kline_resp.raise_for_status()
                kline_data = kline_resp.json()
                
                if kline_data.get("code") != "200000" or not kline_data.get("data"):
                    continue
                
                klines = kline_data["data"]

                # Garantir que os dados estão ordenados do mais antigo para o mais recente
                klines = sorted(klines, key=lambda x: int(x[0]))

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

                # Usar função padronizada para estruturar dados finais
                standardized_row = standardize_final_data(df, timeframe)
                if not standardized_row.empty:
                    all_data.append(standardized_row)
            except Exception:
                continue

        if not all_data:
            st.warning("Nenhum dado de velas retornado pela KuCoin.")
            return pd.DataFrame()
        
        final_df = pd.concat(all_data)
        return final_df.sort_values(by="timestamp").reset_index(drop=True)
        
    except Exception as e:
        st.error(f"Erro ao buscar dados da KuCoin: {str(e)}")
        return pd.DataFrame()

# ----------------- OKX DATA -----------------
@st.cache_data(ttl=300)  # Cache de 10 minutos

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

                # A API da OKX retorna do mais recente para o mais antigo, então revertemos.
                klines.reverse()

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

                # Usar função padronizada para estruturar dados finais
                standardized_row = standardize_final_data(df, timeframe)
                if not standardized_row.empty:
                    all_data.append(standardized_row)
            except Exception:
                continue

        if not all_data:
            st.warning("Nenhum dado de velas retornado pela OKX.")
            return pd.DataFrame()
        
        final_df = pd.concat(all_data)
        return final_df.sort_values(by="timestamp").reset_index(drop=True)
        
    except Exception as e:
        st.error(f"Erro ao buscar dados da OKX: {str(e)}")
        return pd.DataFrame()

# ----------------- BingX DATA -----------------
@st.cache_data(ttl=300)  # Cache de 10 minutos
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

                # Usar função padronizada para estruturar dados finais
                standardized_row = standardize_final_data(df, timeframe)
                if not standardized_row.empty:
                    all_data.append(standardized_row)
            except Exception:
                continue

        if not all_data:
            st.warning("Nenhum dado de velas retornado pela BingX.")
            return pd.DataFrame()
        
        final_df = pd.concat(all_data)
        return final_df.sort_values(by="timestamp").reset_index(drop=True)
        
    except Exception as e:
        st.error(f"Erro ao buscar dados da BingX: {str(e)}")
        return pd.DataFrame()

# ----------------- HUOBI DATA -----------------
@st.cache_data(ttl=300)  # Cache de 10 minutos

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
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                df = df.dropna()
                
                # Reverter ordem (HUOBI retorna mais recentes primeiro)
                df = df.sort_values(by="timestamp").reset_index(drop=True)  # type: ignore[arg-type]
                
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

                # Usar função padronizada para estruturar dados finais
                standardized_row = standardize_final_data(df, timeframe)
                if not standardized_row.empty:
                    all_data.append(standardized_row)
            except Exception:
                continue

        if not all_data:
            st.warning("Nenhum dado de velas retornado pela HUOBI.")
            return pd.DataFrame()
        
        final_df = pd.concat(all_data)
        return final_df.sort_values(by="timestamp").reset_index(drop=True)
        
    except Exception as e:
        st.error(f"Erro ao buscar dados da HUOBI: {str(e)}")
        return pd.DataFrame()

# ----------------- PHEMEX DATA -----------------
@st.cache_data(ttl=300)  # Cache de 10 minutos
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
        return final_df.sort_values(by="timestamp").reset_index(drop=True)
    except Exception as e:
        st.error(f"Erro ao buscar dados da PHEMEX: {str(e)}")
        return pd.DataFrame()

# --- Funções auxiliares para validação de pares ---
@st.cache_data(ttl=3600)  # Cache de 1 hora para pares válidos
def get_valid_binance_btc_pairs():
    """Retorna lista de pares BTC válidos da Binance"""
    try:
        client = Client()
        exchange_info = client.get_exchange_info()
        
        valid_pairs = set()
        for symbol_info in exchange_info['symbols']:
            if (symbol_info['status'] == 'TRADING' and 
                symbol_info['quoteAsset'] == 'BTC'):
                valid_pairs.add(symbol_info['symbol'])
        
        return valid_pairs
    except:
        return set()

@st.cache_data(ttl=3600)  # Cache de 1 hora para pares válidos
def get_valid_kucoin_btc_pairs():
    """Retorna lista de pares BTC válidos da KuCoin"""
    try:
        exchange = ccxt.kucoin({'enableRateLimit': True, 'sandbox': False})
        markets = exchange.load_markets()
        
        valid_pairs = set()
        for symbol, market in markets.items():
            if (market['spot'] and market['quote'] == 'BTC' and market['active']):
                # Converter formato KuCoin (ETH-BTC) para Binance (ETHBTC)
                original_id = market['id']  # ETH-BTC
                binance_format = original_id.replace('-', '')  # ETHBTC
                valid_pairs.add(binance_format)
        
        return valid_pairs
    except:
        return set()

# --- Função para calcular indicadores ---
def calculate_indicators(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Calcula todos os indicadores técnicos usados no scanner de forma padronizada."""
    try:
        # Verificar se temos dados suficientes
        rsi_period = get_rsi_period(timeframe)
        if len(df) < rsi_period:
            return df
            
        # RSI
        df.ta.rsi(length=rsi_period, append=True)
        rsi_col = f"RSI_{rsi_period}"
        
        # Ultimate Oscillator (UO)
        df.ta.uo(length=[7, 14, 28], append=True)
        
        # Awesome Oscillator (AO)
        hl2 = (df['high'] + df['low']) / 2
        sma_5 = hl2.rolling(window=5).mean()
        sma_34 = hl2.rolling(window=34).mean()
        df['AO'] = sma_5 - sma_34
        df['AO_diff'] = df['AO'].diff()
        df['AO_prev'] = df['AO'].shift(1)
        
        # Chande Momentum Oscillator (CMO)
        cmo_period = get_cmo_period(timeframe)
        momm = df['close'].diff()
        m1 = momm.where(momm >= 0, 0)
        m2 = (-momm).where(momm < 0, 0)
        sm1 = m1.rolling(window=cmo_period).sum()
        sm2 = m2.rolling(window=cmo_period).sum()
        df['CMO'] = 100 * (sm1 - sm2) / (sm1 + sm2)
        df['CMO_prev'] = df['CMO'].shift(1)
        
        # Klinger Volume Oscillator (KVO)
        fast_period, slow_period, trigger_period = get_kvo_params(timeframe)
        hlc3 = (df['high'] + df['low'] + df['close']) / 3
        trend_condition = hlc3 > hlc3.shift(1)
        x_trend = df['volume'].where(trend_condition, -df['volume']) * 100
        x_fast = x_trend.ewm(span=fast_period).mean()
        x_slow = x_trend.ewm(span=slow_period).mean()
        df['KVO'] = x_fast - x_slow
        df['KVO_trigger'] = df['KVO'].ewm(span=trigger_period).mean()
        df['KVO_prev'] = df['KVO'].shift(1)
        df['KVO_trigger_prev'] = df['KVO_trigger'].shift(1)
        
        # Directional Movement Index (DMI)
        dmi_period = get_dmi_period(timeframe)
        df.ta.adx(length=dmi_period, append=True)
        adx_col = f"ADX_{dmi_period}"
        dip_col = f"DMP_{dmi_period}"
        dim_col = f"DMN_{dmi_period}"
        df['ADX'] = df[adx_col]
        df['DI_plus'] = df[dip_col]
        df['DI_minus'] = df[dim_col]
        df['DI_plus_prev'] = df['DI_plus'].shift(1)
        df['DI_minus_prev'] = df['DI_minus'].shift(1)
        df['ADX_prev'] = df['ADX'].shift(1)
        
        # On Balance Volume (OBV)
        obv_ma_period = get_obv_ma_period(timeframe)
        obv_raw = (df['close'].diff()
                    .apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * df['volume']).fillna(0)
        df['OBV'] = obv_raw.cumsum()
        df['OBV_MA'] = df['OBV'].ewm(span=obv_ma_period).mean()
        df['OBV_prev'] = df['OBV'].shift(1)
        df['OBV_MA_prev'] = df['OBV_MA'].shift(1)
        
        # Chaikin Money Flow (CMF)
        cmf_period = get_cmf_period(timeframe)
        cmf_pos_th, cmf_neg_th = get_cmf_thresholds(timeframe)
        hl_range = (df['high'] - df['low']).replace(0, np.nan)
        ad = ((2 * df['close'] - df['low'] - df['high']) / hl_range) * df['volume']
        cmf_num = ad.rolling(window=cmf_period).sum()
        cmf_den = df['volume'].rolling(window=cmf_period).sum()
        df['CMF'] = cmf_num / cmf_den
        df['CMF_prev'] = df['CMF'].shift(1)
        
        # Remover linhas onde os indicadores são NaN
        df = df.dropna(subset=[rsi_col, 'UO_7_14_28', 'AO', 'CMO', 'KVO', 'KVO_trigger', 'OBV', 'OBV_MA', 'CMF'])
        
        return df
        
    except Exception as e:
        st.warning(f"Erro ao calcular indicadores: {str(e)}")
        return df

# ----------------- BINANCE BTC DATA -----------------
@st.cache_data(ttl=300) # Cache de 10 minutos
def get_binance_btc_data(timeframe, top_n=200):
    """
    Busca e processa dados da Binance para as top N moedas do mercado Spot em pares BTC.
    Calcula os indicadores RSI e MACD.
    """
    try:
        # 1. Obter lista de pares BTC válidos
        valid_btc_pairs = get_valid_binance_btc_pairs()
        if not valid_btc_pairs:
            st.warning("Não foi possível obter lista de pares BTC válidos da Binance.")
            return pd.DataFrame()
        
        # 2. Buscar tickers para todos os pares para pegar o volume via API direta
        tickers_url = "https://api.binance.com/api/v3/ticker/24hr"
        response = requests.get(tickers_url)
        response.raise_for_status()  # Lança exceção para erros HTTP
        all_tickers = response.json()

        # 3. Filtrar por pares BTC válidos e com volume
        btc_tickers = [
            t for t in all_tickers
            if (t['symbol'] in valid_btc_pairs and 
                float(t.get('quoteVolume', 0)) > 0)
        ]

        # Ordenar por volume (quoteVolume) e pegar o top N
        sorted_tickers = sorted(btc_tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
        top_symbols = [t['symbol'] for t in sorted_tickers[:top_n]]

        if not top_symbols:
            st.warning("Não foi possível encontrar pares BTC com volume. A API da Binance pode estar com problemas.")
            return pd.DataFrame()

        all_data = []

        # 3. Para cada símbolo no top N, buscar os dados de velas (klines)
        for symbol in top_symbols:
            try:
                # Mapear timeframe para formato da Binance
                timeframe_map = {
                    "5m": "5m", "15m": "15m", "30m": "30m",
                    "1h": "1h", "2h": "2h", "4h": "4h", "1d": "1d"
                }
                binance_timeframe = timeframe_map.get(timeframe, "1h")
                
                # URL para buscar dados OHLCV
                klines_url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={binance_timeframe}&limit=100"
                klines_response = requests.get(klines_url, timeout=10)
                klines_response.raise_for_status()
                klines = klines_response.json()

                if not klines:
                    continue

                # Converter para DataFrame
                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore'
                ])

                # Converter tipos de dados
                numeric_columns = ['open', 'high', 'low', 'close', 'volume']
                df[numeric_columns] = df[numeric_columns].astype(float)
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

                # Calcular indicadores
                df = calculate_indicators(df, timeframe)
                
                if len(df) == 0:
                    continue
                
                # Verificar se há volume mínimo
                if df['volume'].sum() == 0:
                    continue
                
                # Adicionar informações do símbolo
                df['symbol'] = symbol.replace('BTC', '/BTC')
                df['exchange'] = 'Binance'
                df['pair_type'] = 'BTC'

                # Preparar a última e penúltima vela para detecção de cruzamentos
                if len(df) < 2:
                    continue

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

                # Variação percentual últimas 3 velas
                if len(df) >= 4:
                    pct_change_3 = ((df['close'].iloc[-1] - df['close'].iloc[-4]) / df['close'].iloc[-4]) * 100
                    last_row['pct_change'] = pct_change_3
                else:
                    last_row['pct_change'] = 0.0

                all_data.append(last_row)

            except Exception as e:
                st.warning(f"Erro ao processar {symbol}: {str(e)}")
                continue

        if not all_data:
            st.warning("Nenhum dado válido encontrado para pares BTC na Binance.")
            return pd.DataFrame()

        # Concatenar todos os DataFrames
        final_df = pd.concat(all_data, ignore_index=True)
        
        return final_df

    except Exception as e:
        st.error(f"Erro ao buscar dados da Binance BTC: {str(e)}")
        return pd.DataFrame()

# ----------------- KUCOIN BTC DATA -----------------
@st.cache_data(ttl=300)  # Cache de 10 minutos
def get_kucoin_btc_data(timeframe: str, top_n: int = 200) -> pd.DataFrame:
    """Busca e processa dados Spot da KuCoin para os top N pares BTC.
    Reaproveita a mesma lógica de indicadores já aplicada no scanner."""
    try:
        # 1. Obter lista de pares BTC válidos da KuCoin
        valid_btc_pairs = get_valid_kucoin_btc_pairs()
        if not valid_btc_pairs:
            st.warning("Não foi possível obter lista de pares BTC válidos da KuCoin.")
            return pd.DataFrame()
        
        # 2. API v1 da KuCoin para all tickers
        tickers_url = "https://api.kucoin.com/api/v1/market/allTickers"
        resp = requests.get(tickers_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        # Verificar se a resposta tem o formato esperado
        if data.get("code") != "200000" or not data.get("data", {}).get("ticker"):
            st.warning("Resposta inesperada da API da KuCoin")
            return pd.DataFrame()
        
        tickers_list = data["data"]["ticker"]
        
        # 3. Filtrar apenas pares BTC válidos e com volume
        btc_tickers = []
        for ticker in tickers_list:
            symbol = ticker.get("symbol", "")
            vol_value = float(ticker.get("volValue", 0) or 0)  # Volume em BTC
            
            # Converter formato KuCoin para Binance para verificação
            if symbol.endswith("-BTC"):
                binance_format = symbol.replace("-", "")  # ETH-BTC -> ETHBTC
                if binance_format in valid_btc_pairs and vol_value > 0:
                    btc_tickers.append({
                        "symbol": symbol,
                        "volume": vol_value
                    })
        
        if not btc_tickers:
            st.warning("Não foi possível encontrar pares BTC válidos na KuCoin.")
            return pd.DataFrame()
        
        # Ordenar por volume e pegar os top N
        sorted_tickers = sorted(btc_tickers, key=lambda x: x["volume"], reverse=True)
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
                # Converter formato de símbolo (ETH-BTC -> ETHBTC)
                clean_symbol = symbol.replace("-", "")
                
                # URL para buscar dados OHLCV
                klines_url = f"https://api.kucoin.com/api/v1/market/candles?type={kucoin_timeframe}&symbol={symbol}&limit=100"
                klines_resp = requests.get(klines_url, timeout=15)
                klines_resp.raise_for_status()
                klines_data = klines_resp.json()
                
                if klines_data.get("code") != "200000" or not klines_data.get("data"):
                    continue
                
                klines = klines_data["data"]
                
                if not klines:
                    continue
                
                # Converter para DataFrame (formato KuCoin: [timestamp, open, close, high, low, volume, amount])
                df = pd.DataFrame(klines, columns=[
                    'timestamp', 'open', 'close', 'high', 'low', 'volume', 'amount'
                ])
                
                # Converter tipos de dados
                numeric_columns = ['open', 'high', 'low', 'close', 'volume']
                df[numeric_columns] = df[numeric_columns].astype(float)
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
                
                # Calcular indicadores
                df = calculate_indicators(df, timeframe)
                
                if len(df) == 0:
                    continue
                
                # Verificar se há volume mínimo
                if df['volume'].sum() == 0:
                    continue
                
                # Adicionar informações do símbolo
                df['symbol'] = clean_symbol.replace('BTC', '/BTC')
                df['exchange'] = 'KuCoin'
                df['pair_type'] = 'BTC'
                
                # Preparar a última e penúltima vela para detecção de cruzamentos
                if len(df) < 2:
                    continue

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

                # Variação percentual últimas 3 velas
                if len(df) >= 4:
                    pct_change_3 = ((df['close'].iloc[-1] - df['close'].iloc[-4]) / df['close'].iloc[-4]) * 100
                    last_row['pct_change'] = pct_change_3
                else:
                    last_row['pct_change'] = 0.0
                
                all_data.append(last_row)
                
            except Exception as e:
                st.warning(f"Erro ao processar {symbol}: {str(e)}")
                continue
        
        if not all_data:
            st.warning("Nenhum dado válido encontrado para pares BTC na KuCoin.")
            return pd.DataFrame()
        
        # Concatenar todos os DataFrames
        final_df = pd.concat(all_data, ignore_index=True)
        
        return final_df
        
    except Exception as e:
        st.error(f"Erro ao buscar dados da KuCoin BTC: {str(e)}")
        return pd.DataFrame()

# Título e descrição
st.title("Scanner de Oportunidades Cripto")

# **SISTEMA DE AUTO-REFRESH MELHORADO**
# Verificação adicional para garantir atualização automática
if 'last_auto_check' not in st.session_state:
    st.session_state.last_auto_check = time.time()

# Auto-refresh inteligente: verificar se precisamos atualizar automaticamente
check_interval = 30  # Verificar a cada 30 segundos
time_since_check = time.time() - st.session_state.last_auto_check

if time_since_check >= check_interval:
    st.session_state.last_auto_check = time.time()
    
    # Se os dados estão muito antigos, força uma atualização
    if hasattr(st.session_state, 'last_refresh_time'):
        time_since_last_refresh = time.time() - st.session_state.last_refresh_time
        if time_since_last_refresh >= 420:  # 7 minutos (mesmo valor de REFRESH_INTERVAL)
            st.session_state.force_update = True
            st.rerun()

# Adicionar meta-tag para refresh automático como fallback (apenas em desenvolvimento)
st.markdown(
    """
    <script>
        // Auto-refresh fallback para garantir atualização
        setInterval(function() {
            // Verificar se o timer expirou pelo localStorage
            var allTimers = Object.keys(localStorage).filter(key => key.startsWith('timer_'));
            var hasActiveTimer = false;
            
            allTimers.forEach(function(timerKey) {
                var timestampKey = timerKey.replace('timer_', 'timestamp_');
                var storedTimer = localStorage.getItem(timerKey);
                var storedTimestamp = localStorage.getItem(timestampKey);
                
                if (storedTimer && storedTimestamp) {
                    var elapsed = Math.floor((Date.now() - parseInt(storedTimestamp)) / 1000);
                    var remaining = Math.max(0, parseInt(storedTimer) - elapsed);
                    
                    if (remaining > 0) {
                        hasActiveTimer = true;
                    }
                }
            });
            
            // Se não há timer ativo ou expirou, recarregar
            if (!hasActiveTimer) {
                console.log('Auto-refresh triggered - no active timers found');
                window.parent.location.reload();
            }
        }, 60000); // Verificar a cada 1 minuto
    </script>
    """,
    unsafe_allow_html=True
)

# --- Persistência da Exchange Selecionada via Query Params ---
exchange_options = [
    "Binance", "Binance BTC", "Bybit", "Bitget", "KuCoin", "KuCoin BTC", "OKX", "BingX", "HUOBI", "PHEMEX"
]

# Obter o parâmetro de query (caso exista) para definir a exchange padrão
query_params_proxy = st.query_params
# `st.query_params` se comporta como um dicionário; caso a chave não exista, usamos "Binance".
default_exchange = query_params_proxy.get("exchange", "Binance")
if default_exchange not in exchange_options:
    default_exchange = "Binance"

default_exchange_index = exchange_options.index(default_exchange)

# --- Barra Lateral (Sidebar) com os Filtros ---
st.sidebar.header("Filtros")

# Dropdown de Exchange que preserva seleção após recarregar a página
exchange = st.sidebar.selectbox(
    "Exchange",
    exchange_options,
    index=default_exchange_index,
    key="exchange_select"
)
# Atualizar os parâmetros da URL para refletir a seleção atual (somente se mudou para evitar ciclos de rerun)
if st.query_params.get("exchange") != exchange:
    st.query_params["exchange"] = exchange

# Campo de busca
search_symbol = st.sidebar.text_input(
    "Buscar",
    placeholder="Ex: ADA, BTC, ETH..."
).upper()

# ----------------- Persistência do Timeframe -----------------
timeframe_options = ['5m', '15m', '30m', '1h', '2h', '4h', '1d']

# Ler da URL (ou usar 30m como padrão)
default_tf = st.query_params.get("timeframe", "30m")
if default_tf not in timeframe_options:
    default_tf = "30m"

tf_index = timeframe_options.index(default_tf)

# Selectbox que mantém o timeframe
timeframe = st.sidebar.selectbox(
    "Tempo Gráfico", 
    timeframe_options,
    index=tf_index,
    key="timeframe_select"
)

# Atualizar parâmetro de URL caso mude
if st.query_params.get("timeframe") != timeframe:
    st.query_params["timeframe"] = timeframe

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
    "Binance BTC": get_binance_btc_data,
    "Bybit": get_bybit_data,
    "Bitget": get_bitget_data,
    "KuCoin": get_kucoin_data,
    "KuCoin BTC": get_kucoin_btc_data,
    "OKX": get_okx_data,
    "BingX": get_bingx_data,
    "HUOBI": get_huobi_data,
    "PHEMEX": get_phemex_data
}

# --- SISTEMA DE ATUALIZAÇÃO OTIMIZADO (Exchange Única) ---

def fetch_selected_exchange_data(exchange_name: str, timeframe_param: str):
    """Busca dados apenas para a exchange selecionada com feedback visual."""
    try:
        st.cache_data.clear() 
        
        progress_bar = st.progress(0, text=f"🔄 Buscando dados de {exchange_name} ({timeframe_param})...")
        
        fetch_func = exchange_functions.get(exchange_name)
        if not fetch_func:
            st.error(f"Função de busca não encontrada para {exchange_name}")
            progress_bar.empty()
            return None

        data = fetch_func(timeframe_param)
        
        progress_bar.progress(1.0, text=f"✅ Dados de {exchange_name} carregados!")
        time.sleep(0.5)
        progress_bar.empty()
        
        return data if data is not None else pd.DataFrame()
    except Exception as e:
        if 'progress_bar' in locals() and progress_bar:
            progress_bar.empty()
        st.error(f"Erro ao buscar dados para {exchange_name}: {e}")
        return None

if 'data_cache' not in st.session_state:
    st.session_state.data_cache = {name: pd.DataFrame() for name in exchange_functions}
if 'last_refresh_time' not in st.session_state:
    st.session_state.last_refresh_time = 0
if 'cached_timeframe' not in st.session_state:
    st.session_state.cached_timeframe = None
if 'force_update' not in st.session_state:
    st.session_state.force_update = False
if 'data_update_timestamp' not in st.session_state:
    st.session_state.data_update_timestamp = time.time()

REFRESH_INTERVAL = 420

current_time = time.time()
time_since_refresh = current_time - st.session_state.get('last_refresh_time', 0)

needs_fetch = (
    st.session_state.data_cache.get(exchange, pd.DataFrame()).empty or
    st.session_state.cached_timeframe != timeframe or
    st.session_state.force_update or
    time_since_refresh >= REFRESH_INTERVAL
)

if needs_fetch:
    st.info(f'🔄 Carregando dados para {exchange}...')
    st.session_state.force_update = False
    new_data = fetch_selected_exchange_data(exchange, timeframe)
    
    st.session_state.data_cache[exchange] = new_data if new_data is not None else pd.DataFrame()
    st.session_state.last_refresh_time = current_time
    st.session_state.data_update_timestamp = current_time
    st.session_state.cached_timeframe = timeframe
    
    if new_data is None:
         st.error(f"Não foi possível carregar os dados para {exchange}.")
    
    st.rerun()

st.info(f'🟢 Exibindo dados para {exchange} ({timeframe})')
df = st.session_state.data_cache.get(exchange, pd.DataFrame())

time_since_last = current_time - st.session_state.last_refresh_time
countdown_remaining = int(max(REFRESH_INTERVAL - time_since_last, 0))

status_message = ""
status_color = "transparent"

if countdown_remaining <= 60:
    status_message = "🔄 Atualização iminente..."
    status_color = "rgba(255, 165, 0, 0.3)"

last_update_time = datetime.fromtimestamp(st.session_state.data_update_timestamp).strftime("%H:%M:%S")
data_age_info = f"📊 Última atualização: {last_update_time}"

timer_key = f"timer_{int(st.session_state.last_refresh_time)}"
components.html(
    f"""
    <div style='margin-bottom:15px;'>
        <div style="text-align: left; font-size: 18px; color: #8fa1b3; margin-bottom: 5px; margin-left: 8px;">
            {data_age_info}
        </div>
        
        {f'<div style="background-color: {status_color}; padding: 8px; text-align: center; font-weight: bold; border-radius: 5px; margin-bottom: 8px; border: 2px solid rgba(255,255,255,0.2);">{status_message}</div>' if status_message else ''}
        
        <div style='display: flex; align-items: center; gap: 10px; margin-left: 8px;'>
            <div id="countdown" style='font-size:18px; font-weight:bold; color:#FF7F00;'>
                ⏱️ Próxima atualização em: {countdown_remaining}s
            </div>
            <div id="progress-ring" style='width: 40px; height: 40px;'>
                <svg width="40" height="40" viewBox="0 0 40 40">
                    <circle cx="20" cy="20" r="18" stroke="#333" stroke-width="2" fill="none"/>
                    <circle id="progress-circle" cx="20" cy="20" r="18" stroke="#FF7F00" stroke-width="3" 
                            fill="none" stroke-linecap="round" 
                            stroke-dasharray="113" stroke-dashoffset="0"
                            transform="rotate(-90 20 20)"/>
                </svg>
            </div>
        </div>
    </div>
    
    <script>
        var totalSeconds = {REFRESH_INTERVAL};
        var timerKey = "{timer_key}";
        var countdownElement = document.getElementById("countdown");
        var progressCircle = document.getElementById("progress-circle");
        var circumference = 113;

        var currentSeconds;
        var storedTimer = localStorage.getItem('timer_' + timerKey);
        var storedTimestamp = localStorage.getItem('timestamp_' + timerKey);
        
        if (storedTimer && storedTimestamp) {{
            var elapsed = Math.floor((Date.now() - parseInt(storedTimestamp)) / 1000);
            currentSeconds = Math.max(0, parseInt(storedTimer) - elapsed);
        }} else {{
            currentSeconds = {countdown_remaining};
            localStorage.setItem('timer_' + timerKey, currentSeconds.toString());
            localStorage.setItem('timestamp_' + timerKey, Date.now().toString());
        }}

        function updateProgress() {{
            var progress = (totalSeconds - currentSeconds) / totalSeconds;
            var offset = circumference * (1 - progress);
            progressCircle.style.strokeDashoffset = offset;
            
            if (currentSeconds <= 60) {{
                progressCircle.style.stroke = "#FF4444";
            }} else if (currentSeconds <= 180) {{
                progressCircle.style.stroke = "#FFAA00";
            }} else {{
                progressCircle.style.stroke = "#FF7F00";
            }}
        }}
        
        function updateDisplay() {{
            var minutes = Math.floor(currentSeconds / 60);
            var seconds = currentSeconds % 60;
            var timeText = minutes > 0 ? minutes + "m " + seconds + "s" : seconds + "s";
            countdownElement.innerHTML = "⏱️ Próxima atualização em: " + timeText;
            updateProgress();
        }}
        
        updateDisplay();
        
        var interval = setInterval(function() {{
            currentSeconds--;
            
            localStorage.setItem('timer_' + timerKey, currentSeconds.toString());
            localStorage.setItem('timestamp_' + timerKey, Date.now().toString());
            
            if (currentSeconds <= 0) {{
                countdownElement.innerHTML = "🔄 Atualizando...";
                progressCircle.style.stroke = "#00FF00";
                clearInterval(interval);
                
                localStorage.removeItem('timer_' + timerKey);
                localStorage.removeItem('timestamp_' + timerKey);
                
                setTimeout(function() {{
                    window.parent.location.reload();
                }}, 1000);
            }} else {{
                updateDisplay();
            }}
        }}, 1000);
        
        Object.keys(localStorage).forEach(function(key) {{
            if (key.startsWith('timer_') && key !== 'timer_' + timerKey) {{
                localStorage.removeItem(key);
                localStorage.removeItem(key.replace('timer_', 'timestamp_'));
            }}
        }});
    </script>
    """,
    height=120
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

    if not isinstance(df_filtered, pd.DataFrame):
        df_filtered = pd.DataFrame(df_filtered)

    df_filtered.loc[:, 'AO_color'] = df_filtered.apply(label_ao_color, axis=1)

    # Filtro de busca por símbolo
    if search_symbol:
        df_filtered = df_filtered[df_filtered['symbol'].str.contains(search_symbol, case=False, na=False)].copy()
        if not isinstance(df_filtered, pd.DataFrame):
            df_filtered = pd.DataFrame(df_filtered)

    # 0. Filtro de direção do preço (% variação)
    if price_direction == "Up":
        df_filtered = df_filtered[df_filtered['pct_change'] > 0].copy()
        if not isinstance(df_filtered, pd.DataFrame):
            df_filtered = pd.DataFrame(df_filtered)
        if hasattr(df_filtered, 'empty') and not df_filtered.empty:
            df_filtered = df_filtered.sort_values('pct_change', ascending=False).copy()
    elif price_direction == "Down":
        df_filtered = df_filtered[df_filtered['pct_change'] < 0].copy()
        if not isinstance(df_filtered, pd.DataFrame):
            df_filtered = pd.DataFrame(df_filtered)
        if hasattr(df_filtered, 'empty') and not df_filtered.empty:
            df_filtered = df_filtered.sort_values('pct_change', ascending=True).copy()

    if volume_filter == "Alto":
        volume_median = df['volume'].median()
        df_filtered = df_filtered[df_filtered['volume'] > volume_median].copy()
        if not isinstance(df_filtered, pd.DataFrame):
            df_filtered = pd.DataFrame(df_filtered)
        if hasattr(df_filtered, 'empty') and not df_filtered.empty:
            df_filtered = df_filtered.sort_values('volume', ascending=False).copy()
    elif volume_filter == "Baixo":
        volume_median = df['volume'].median()
        df_filtered = df_filtered[df_filtered['volume'] <= volume_median].copy()
        if not isinstance(df_filtered, pd.DataFrame):
            df_filtered = pd.DataFrame(df_filtered)
        if hasattr(df_filtered, 'empty') and not df_filtered.empty:
            df_filtered = df_filtered.sort_values('volume', ascending=True).copy()

    if rsi_filter == f"RSI abaixo de {rsi_low}":
        df_filtered = df_filtered[df_filtered[rsi_col] <= rsi_low].copy()
    elif rsi_filter == f"RSI acima de {rsi_high}":
        df_filtered = df_filtered[df_filtered[rsi_col] >= rsi_high].copy()

    # 2. Filtro de UO
    if uo_filter == "Cruzamento de Alta (30↑)":
        df_filtered = df_filtered[(df_filtered['UO_prev'] < 30) & (df_filtered['UO_7_14_28'] >= 30)].copy()
    elif uo_filter == "Cruzamento de Baixa (70↓)":
        df_filtered = df_filtered[(df_filtered['UO_prev'] > 70) & (df_filtered['UO_7_14_28'] <= 70)].copy()

    # 3. Filtro de AO
    if ao_filter == "Cruzamento Linha Zero ↑":
        df_filtered = df_filtered[(df_filtered['AO_prev'] < 0) & (df_filtered['AO'] >= 0)].copy()
    elif ao_filter == "Cruzamento Linha Zero ↓":
        df_filtered = df_filtered[(df_filtered['AO_prev'] > 0) & (df_filtered['AO'] <= 0)].copy()
    elif ao_filter == "Mudança para Verde":
        df_filtered = df_filtered[df_filtered['AO_diff'] > 0].copy()
    elif ao_filter == "Mudança para Vermelho":
        df_filtered = df_filtered[df_filtered['AO_diff'] < 0].copy()

    # 3b. Filtro de cor do AO
    if ao_color_filter != "Qualquer":
        df_filtered = df_filtered[df_filtered['AO_color'] == ao_color_filter].copy()

    # 4. Filtro de CMO
    if cmo_filter == "Qualquer":
        pass
    elif cmo_filter == f"Saída Sobrevenda ({cmo_low}↑)":
        df_filtered = df_filtered[(df_filtered['CMO_prev'] < cmo_low) & (df_filtered['CMO'] >= cmo_low)].copy()
    elif cmo_filter == f"Saída Sobrecompra ({cmo_high}↓)":
        df_filtered = df_filtered[(df_filtered['CMO_prev'] > cmo_high) & (df_filtered['CMO'] <= cmo_high)].copy()
    elif cmo_filter == "Cruzamento Zero ↑":
        df_filtered = df_filtered[(df_filtered['CMO_prev'] < 0) & (df_filtered['CMO'] >= 0)].copy()
    elif cmo_filter == "Cruzamento Zero ↓":
        df_filtered = df_filtered[(df_filtered['CMO_prev'] > 0) & (df_filtered['CMO'] <= 0)].copy()

    # 5. Filtro de KVO
    if kvo_filter == "Qualquer":
        pass
    elif kvo_filter == "KVO cruza acima Sinal ↑":
        df_filtered = df_filtered[(df_filtered['KVO_prev'] < df_filtered['KVO_trigger_prev']) & (df_filtered['KVO'] > df_filtered['KVO_trigger'])].copy()
    elif kvo_filter == "KVO cruza abaixo Sinal ↓":
        df_filtered = df_filtered[(df_filtered['KVO_prev'] > df_filtered['KVO_trigger_prev']) & (df_filtered['KVO'] < df_filtered['KVO_trigger'])].copy()
    elif kvo_filter == "KVO cruza acima Zero ↑":
        df_filtered = df_filtered[(df_filtered['KVO_prev'] < 0) & (df_filtered['KVO'] > 0)].copy()
    elif kvo_filter == "KVO cruza abaixo Zero ↓":
        df_filtered = df_filtered[(df_filtered['KVO_prev'] > 0) & (df_filtered['KVO'] < 0)].copy()

    # 6. Filtro de OBV
    if obv_filter == "Qualquer":
        pass
    elif obv_filter == "OBV acima da EMA":
        df_filtered = df_filtered[(df_filtered['OBV'] > df_filtered['OBV_MA'])].copy()
    elif obv_filter == "OBV abaixo da EMA":
        df_filtered = df_filtered[(df_filtered['OBV'] < df_filtered['OBV_MA'])].copy()
    elif obv_filter == "Cruzamento Alta (OBV↑EMA)":
        df_filtered = df_filtered[(df_filtered['OBV_prev'] < df_filtered['OBV_MA_prev']) & (df_filtered['OBV'] >= df_filtered['OBV_MA'])].copy()
    elif obv_filter == "Cruzamento Baixa (OBV↓EMA)":
        df_filtered = df_filtered[(df_filtered['OBV_prev'] > df_filtered['OBV_MA_prev']) & (df_filtered['OBV'] <= df_filtered['OBV_MA'])].copy()

    # 7. Filtro de CMF
    if cmf_filter == "Qualquer":
        pass
    elif cmf_filter == "Cruzamento Alta (0↑)":
        df_filtered = df_filtered[(df_filtered['CMF_prev'] < 0) & (df_filtered['CMF'] >= 0)].copy()
    elif cmf_filter == "Cruzamento Baixa (0↓)":
        df_filtered = df_filtered[(df_filtered['CMF_prev'] > 0) & (df_filtered['CMF'] <= 0)].copy()
    elif cmf_filter == f"CMF > {cmf_pos_th}":
        df_filtered = df_filtered[(df_filtered['CMF'] > cmf_pos_th)].copy()
    elif cmf_filter == f"CMF < {cmf_neg_th}":
        df_filtered = df_filtered[(df_filtered['CMF'] < cmf_neg_th)].copy()

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

    # --- Gerar colunas HTML ---
    if not isinstance(df_filtered, pd.DataFrame):
        df_filtered = pd.DataFrame(df_filtered)
    if not df_filtered.empty:
        # Corrigir possíveis colunas ndarray para Series
        for col in ['pct_change', rsi_col, 'UO_7_14_28', 'AO', 'CMO', 'KVO', 'KVO_trigger', 'OBV', 'OBV_prev', 'CMF', 'DI_plus', 'DI_minus', 'ADX']:
            if col in df_filtered and isinstance(df_filtered[col], np.ndarray):
                df_filtered[col] = pd.Series(df_filtered[col])
        # Garantir DataFrame para .apply
        if not isinstance(df_filtered, pd.DataFrame):
            df_filtered = pd.DataFrame(df_filtered)
        df_filtered.loc[:, 'pct_html'] = df_filtered['pct_change'].apply(pct_to_badge)
        df_filtered.loc[:, 'RSI_html'] = df_filtered[rsi_col].apply(rsi_to_badge)
        df_filtered.loc[:, 'UO_html'] = df_filtered['UO_7_14_28'].apply(uo_to_badge)
        df_filtered.loc[:, 'AO_html'] = df_filtered.apply(ao_to_badge, axis=1)
        df_filtered.loc[:, 'CMO_html'] = df_filtered['CMO'].apply(cmo_to_badge)
        df_filtered.loc[:, 'KVO_html'] = df_filtered.apply(lambda r: kvo_to_badge(r['KVO'], r['KVO_trigger']), axis=1)
        df_filtered.loc[:, 'OBV_html'] = df_filtered.apply(lambda r: obv_to_badge(r['OBV'], r['OBV_prev'], r['pct_change']), axis=1)
        df_filtered.loc[:, 'CMF_html'] = df_filtered['CMF'].apply(cmf_to_badge)
        df_filtered.loc[:, 'DI_plus_html'] = df_filtered.apply(di_plus_badge, axis=1)
        df_filtered.loc[:, 'DI_minus_html'] = df_filtered.apply(di_minus_badge, axis=1)
        df_filtered.loc[:, 'ADX_html'] = df_filtered['ADX'].apply(adx_badge)

        # --- Exibição da Tabela ---
        df_display = df_filtered[['symbol', 'pct_html', 'volume', 'RSI_html', 'UO_html', 'AO_html', 'CMO_html', 'KVO_html', 'OBV_html', 'CMF_html', 'DI_plus_html', 'DI_minus_html', 'ADX_html']].copy()
        if not isinstance(df_display, pd.DataFrame):
            df_display = pd.DataFrame(df_display)
        # Criar links para TradingView
        def create_tradingview_link(symbol):
            tv_symbol = symbol.replace('/', '')
            if exchange == "Binance" or exchange == "Binance BTC":
                tv_prefix = "BINANCE:"
            elif exchange == "Bybit":
                tv_prefix = "BYBIT:"
            elif exchange == "Bitget":
                tv_prefix = "BITGET:"
            elif exchange == "KuCoin" or exchange == "KuCoin BTC":
                tv_prefix = "KUCOIN:"
            elif exchange == "OKX":
                tv_prefix = "OKX:"
            elif exchange == "BingX":
                tv_prefix = "BINGX:"
            elif exchange == "HUOBI":
                tv_prefix = "HUOBI:"
            elif exchange == "PHEMEX":
                tv_prefix = "PHEMEX:"
            else:
                tv_prefix = ""
            # Mapear timeframe selecionado para o parâmetro "interval" do TradingView
            interval_map = {
                '5m': '5',
                '15m': '15',
                '30m': '30',
                '1h': '60',
                '2h': '120',
                '4h': '240',
                '1d': 'D'
            }
            interval_param = interval_map.get(timeframe, '60')  # 60 = 1h como padrão
            tv_url = f"https://www.tradingview.com/chart/?symbol={tv_prefix}{tv_symbol}&interval={interval_param}"
            if exchange == "BingX":
                binance_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{tv_symbol}&interval={interval_param}"
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
        df_display.loc[:, 'TradingView'] = df_display['symbol'].apply(create_tradingview_link)
        df_display = df_display[['symbol', 'TradingView', 'pct_html', 'volume', 'RSI_html', 'UO_html', 'AO_html', 'CMO_html', 'KVO_html', 'OBV_html', 'CMF_html', 'DI_plus_html', 'DI_minus_html', 'ADX_html']]
        if not isinstance(df_display, pd.DataFrame):
            df_display = pd.DataFrame(df_display)
        df_display = pd.DataFrame(df_display)
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
        # HTML da tabela (incluindo índice para servir como "linha seletora")
        table_html = df_display.to_html(escape=False, index=True)

        # CSS para congelar o cabeçalho
        st.markdown(
            """
            <style>
            .table-container {
                max-height: 650px;
                overflow-y: auto;
            }
            .table-container thead th {
                position: sticky;
                top: 0;
                background-color: #0E1117; /* mesma cor do tema escuro do Streamlit */
                z-index: 2;
            }
            .table-container table {
                border-collapse: collapse;
            }
            .table-container th,
            .table-container td {
                text-align: center !important;
                vertical-align: middle !important;
                padding: 8px !important;
            }
            .table-container tbody tr:hover {
                background-color: #262730 !important;
                cursor: pointer;
                box-shadow: 0 2px 5px rgba(255, 255, 255, 0.1);
                transform: scale(1.001);
                transition: all 0.2s ease;
                border: 2px solid #8A2BE2 !important;
            }
            .table-container tbody tr {
                transition: all 0.2s ease;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # Renderizar a tabela dentro do contêiner scrollable
        st.markdown(f'<div class="table-container">{table_html}</div>', unsafe_allow_html=True)

def fetch_selected_exchange_sync_with_progress(exchange_name: str, timeframe_param: str):
    """Busca dados apenas para a exchange selecionada com feedback visual"""
    try:
        st.cache_data.clear()  # Garantir dados frescos para esta exchange
        progress_bar = st.progress(0, text=f"🔄 Buscando dados de {exchange_name}...")

        fetch_func = exchange_functions.get(exchange_name)
        if fetch_func is None:
            st.error(f"❌ Função de busca não encontrada para {exchange_name}")
            return None

        # Chamada direta (sem ThreadPool) para a exchange
        data = fetch_func(timeframe_param)
        progress_bar.progress(1.0, text="✅ Concluído!")
        time.sleep(0.3)
        progress_bar.empty()
        return data if data is not None else pd.DataFrame()
    except Exception as exc:
        if 'progress_bar' in locals():
            progress_bar.empty()
        st.error(f"❌ Erro ao buscar dados de {exchange_name}: {exc}")
        return None

# Para rodar este aplicativo, salve o arquivo como app.py e execute no seu terminal:
# streamlit run app.py

