#!/usr/bin/env python3
"""
Script para corrigir o erro de importação do pandas_ta com NumPy
Substitui 'from numpy import NaN as npNaN' por 'from numpy import nan as npNaN'
"""

import os
import sys

def fix_pandas_ta_import():
    # Caminho para o arquivo problemático
    venv_path = os.path.join(os.getcwd(), '.venv')
    squeeze_pro_path = os.path.join(
        venv_path, 
        'Lib', 
        'site-packages', 
        'pandas_ta', 
        'momentum', 
        'squeeze_pro.py'
    )
    
    print(f"Procurando arquivo em: {squeeze_pro_path}")
    
    if not os.path.exists(squeeze_pro_path):
        print("❌ Arquivo squeeze_pro.py não encontrado!")
        print("Verifique se o ambiente virtual está na pasta correta.")
        return False
    
    try:
        # Ler o arquivo
        with open(squeeze_pro_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Fazer a substituição
        old_import = "from numpy import NaN as npNaN"
        new_import = "from numpy import nan as npNaN"
        
        if old_import in content:
            content = content.replace(old_import, new_import)
            
            # Salvar o arquivo corrigido
            with open(squeeze_pro_path, 'w', encoding='utf-8') as file:
                file.write(content)
            
            print("✅ Correção aplicada com sucesso!")
            print(f"Substituído: '{old_import}'")
            print(f"Por: '{new_import}'")
            return True
        else:
            print("⚠️  A linha problemática não foi encontrada.")
            print("O arquivo pode já estar corrigido ou ter uma estrutura diferente.")
            return False
            
    except Exception as e:
        print(f"❌ Erro ao processar o arquivo: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Iniciando correção do pandas_ta...")
    success = fix_pandas_ta_import()
    
    if success:
        print("\n🎉 Correção concluída! Agora você pode executar:")
        print("python -m streamlit run app.py")
    else:
        print("\n❌ Falha na correção. Verifique os erros acima.")
    
    input("\nPressione Enter para sair...") 