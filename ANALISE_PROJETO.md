# ANÁLISE DO PROJETO: Scanner de Oportunidades Cripto

## 1. Visão Geral do Produto

O objetivo é criar um aplicativo web pessoal, desenvolvido em Python com a biblioteca Streamlit, que funcione como um "screener" ou "scanner" do mercado de criptomoedas. O aplicativo irá analisar um conjunto de criptomoedas em tempo real, calcular indicadores técnicos e apresentar os resultados em uma tabela interativa, permitindo ao usuário filtrar e encontrar oportunidades de trading com base em critérios específicos.

## 2. Público-Alvo

Uso estritamente pessoal do desenvolvedor para agilizar a análise de mercado e a identificação de configurações técnicas de interesse.

## 3. Arquitetura e Tecnologias

- **Linguagem:** Python
- **Framework Web/UI:** Streamlit
- **Bibliotecas Principais:**
  - `pandas`: Para manipulação e estruturação dos dados.
  - `ccxt`: Para buscar dados de preços e volume da exchange (Binance será a fonte inicial).
  - `pandas-ta`: Para o cálculo eficiente de indicadores técnicos.
- **Hospedagem:** Streamlit Community Cloud (com acesso restrito por e-mail para garantir a privacidade).
- **Versionamento:** Git e GitHub.

## 4. Funcionalidades do MVP (Produto Mínimo Viável)

A primeira versão do aplicativo terá as seguintes funcionalidades:

### Interface do Usuário (Filtros)

1.  **Seleção de Tempo Gráfico:** Um seletor (`st.selectbox`) para que o usuário escolha o timeframe da análise (ex: `15m`, `1h`, `4h`, `1d`).
2.  **Filtro de RSI (Índice de Força Relativa):** Um slider (`st.slider`) para definir um valor máximo de RSI. O usuário poderá, por exemplo, buscar por moedas "sobrevendidas" (ex: com RSI abaixo de 30).
3.  **Filtro de MACD (Convergência/Divergência de Médias Móveis):** Um seletor para encontrar moedas que tiveram um "cruzamento de alta" (MACD cruzou acima da linha de sinal) ou "cruzamento de baixa" recentemente.

### Tabela de Resultados

Uma tabela de dados interativa (`st.dataframe`) exibirá os resultados do scan. A tabela será atualizada automaticamente ao alterar os filtros e conterá as seguintes colunas:

- **Par:** O símbolo da criptomoeda (ex: `BTC/USDT`).
- **Preço Atual:** O último preço negociado.
- **Volume (24h):** O volume de negociação nas últimas 24 horas em USDT.
- **RSI (14):** O valor atual do RSI no tempo gráfico selecionado.
- **Sinal MACD:** Uma indicação textual (ex: "Cruzamento de Alta", "Cruzamento de Baixa", "Nenhum").

### Lógica do Back-end

- O aplicativo irá buscar a lista das 200 principais moedas com par USDT na Binance, no mercado de **Futuros Perpétuos**.
- Para cada moeda, fará o download dos dados históricos (velas/candlesticks) necessários para o tempo gráfico selecionado.
- Calculará os indicadores (RSI, MACD) para todas as moedas.
- Aplicará os filtros definidos pelo usuário.
- Exibirá a lista filtrada na tabela de resultados. 