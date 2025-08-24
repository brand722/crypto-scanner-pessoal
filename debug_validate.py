#!/usr/bin/env python3
"""
Script de debug para validar se o timestamp está sendo atualizado corretamente
"""
import time
from datetime import datetime

def test_timestamp_update():
    """Simula o comportamento de atualização do timestamp"""
    
    # Simular session_state
    session_state = {}
    
    print("=== TESTE 1: Inicialização ===")
    # Inicialização (primeira vez)
    if 'data_update_timestamp' not in session_state:
        session_state['data_update_timestamp'] = time.time()
    
    initial_time = datetime.fromtimestamp(session_state['data_update_timestamp']).strftime("%H:%M:%S")
    print(f"Horário inicial: {initial_time}")
    
    time.sleep(2)  # Simular passagem de tempo
    
    print("\n=== TESTE 2: Atualização Manual ===")
    # Simular atualização (força refresh)
    session_state['data_update_timestamp'] = time.time()
    updated_time = datetime.fromtimestamp(session_state['data_update_timestamp']).strftime("%H:%M:%S")
    print(f"Horário após atualização: {updated_time}")
    
    time.sleep(2)
    
    print("\n=== TESTE 3: Múltiplas Atualizações ===")
    for i in range(3):
        time.sleep(1)
        session_state['data_update_timestamp'] = time.time()
        current_time = datetime.fromtimestamp(session_state['data_update_timestamp']).strftime("%H:%M:%S")
        print(f"Atualização {i+1}: {current_time}")
    
    print("\n=== TESTE 4: Verificação Final ===")
    final_time = datetime.fromtimestamp(session_state['data_update_timestamp']).strftime("%H:%M:%S")
    print(f"Horário final: {final_time}")
    
    print(f"\nInicial: {initial_time}")
    print(f"Final:   {final_time}")
    print(f"Diferentes? {initial_time != final_time}")

def check_streamlit_session_state():
    """Simula como o Streamlit pode estar gerenciando o session_state"""
    print("\n" + "="*50)
    print("SIMULAÇÃO DO COMPORTAMENTO STREAMLIT")
    print("="*50)
    
    # Primeira execução
    session_state_1 = {}
    if 'data_update_timestamp' not in session_state_1:
        session_state_1['data_update_timestamp'] = time.time()
    time1 = datetime.fromtimestamp(session_state_1['data_update_timestamp']).strftime("%H:%M:%S")
    print(f"1ª execução: {time1}")
    
    time.sleep(1)
    
    # Segunda execução (rerun)
    session_state_2 = session_state_1.copy()  # Streamlit preserva estado
    session_state_2['data_update_timestamp'] = time.time()  # Nova atualização
    time2 = datetime.fromtimestamp(session_state_2['data_update_timestamp']).strftime("%H:%M:%S")
    print(f"2ª execução: {time2}")
    
    time.sleep(1)
    
    # Terceira execução
    session_state_3 = session_state_2.copy()
    session_state_3['data_update_timestamp'] = time.time()
    time3 = datetime.fromtimestamp(session_state_3['data_update_timestamp']).strftime("%H:%M:%S")
    print(f"3ª execução: {time3}")
    
    print(f"\nTodos diferentes? {len(set([time1, time2, time3])) == 3}")

if __name__ == "__main__":
    test_timestamp_update()
    check_streamlit_session_state()
    
    print("\n" + "="*50)
    print("POSSÍVEIS PROBLEMAS:")
    print("="*50)
    print("1. Cache do Streamlit pode estar interferindo")
    print("2. Session state não está sendo persistido corretamente")
    print("3. Lógica de atualização tem condições que impedem a execução")
    print("4. O st.rerun() pode estar causando problemas") 