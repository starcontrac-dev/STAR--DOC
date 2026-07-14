import re
from datetime import date

def format_sentence_citation(corte: str, radicado: str, fecha: date, magistrado_ponente: str = None) -> str:
    """
    Formatea una cita bibliográfica de una sentencia judicial colombiana.
    Ej: "Corte Constitucional, Sentencia T-302 de 2017 (M.P. Aquiles Arrieta Gómez)"
    """
    base_citation = f"{corte}, Sentencia {radicado} del {fecha.year}"
    if magistrado_ponente:
        base_citation += f" (M.P. {magistrado_ponente})"
    return base_citation

def is_valid_nit(nit_str: str) -> bool:
    """
    Valida un NIT colombiano y su dígito de verificación.
    El NIT debe venir en formato "123456789-0" o "1234567890" o numérico puro
    Retorna True si el código de verificación corresponde al NIT base.
    """
    nit_str = str(nit_str).replace(".", "").replace(" ", "").strip()
    
    # Separar dígito de verificación si viene con guion o como último caracter
    if "-" in nit_str:
        parts = nit_str.split("-")
        if len(parts) != 2:
            return False
        nit_base, dv_proporcionado = parts[0], parts[1]
    else:
        # Se asume que el último dígito es el DV
        if len(nit_str) < 2:
            return False
        nit_base = nit_str[:-1]
        dv_proporcionado = nit_str[-1]

    if not nit_base.isdigit() or not dv_proporcionado.isdigit():
        return False

    # Algoritmo DIAN para Dígito de Verificación
    primos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    suma = 0
    nit_base = nit_base.zfill(15) # Rellenar con ceros a la izquierda

    for i in range(15):
        suma += int(nit_base[i]) * primos[14 - i]
    
    residuo = suma % 11
    if residuo > 1:
        dv_calculado = 11 - residuo
    else:
        dv_calculado = residuo

    return str(dv_calculado) == dv_proporcionado

def anonymize_colombian_data(text: str) -> str:
    """
    Sanitiza y anonimiza información sensible colombiana en un texto (Ley 1581 de 2012).
    Reemplaza cédulas, NITs, correos y números telefónicos por marcadores genéricos.
    
    Args:
        text: El texto original del documento o contrato.
        
    Returns:
        str: El texto anonimizado.
    """
    if not text:
        return text
        
    # 1. Anonimizar Correos Electrónicos
    text = re.sub(r'(?i)\b[\w\.-]+@[\w\.-]+\.[a-z]{2,4}\b', '[CORREO_ANONIMIZADO]', text)
    
    # 2. Anonimizar Teléfonos Celulares (10 dígitos empezando por 3, con posibles guiones, puntos o espacios)
    text = re.sub(r'\b3\d{2}[-.\s]?\d{3}[-.\s]?\d{4}\b', '[CELULAR_ANONIMIZADO]', text)
    
    # 3. Anonimizar Teléfonos Fijos (7 dígitos locales o 10 dígitos con indicativo nacional 60X)
    text = re.sub(r'\b60[1-8][-.\s]?\d{3}[-.\s]?\d{4}\b', '[TELEFONO_ANONIMIZADO]', text) # Nacional 60X
    text = re.sub(r'\b[2-8]\d{2}[-.\s]?\d{4}\b', '[TELEFONO_ANONIMIZADO]', text) # Fijos locales 7 dígitos
    
    # 4. Anonimizar Cédulas de Ciudadanía o Extranjería (C.C., CC, C.E., CE, Cédula de Ciudadanía/Extranjería)
    # Rango de 6 a 15 para incluir puntos y comas sin dejar dígitos residuales.
    text = re.sub(
        r'(?i)\b(?:c\.?c\.?|c\.?e\.?|cédula(?:\s+de\s+(?:ciudadanía|extranjería))?)\b\s*(?:no\.?|número)?\s*[\d\.\,\s-]{6,15}\b', 
        'C.C. [CEDULA_ANONIMIZADA]', 
        text
    )
    
    # 5. Anonimizar NITs (Número de Identificación Tributaria, con o sin guion y DV)
    text = re.sub(
        r'(?i)\bnit\b\s*(?:no\.?|número)?\s*[\d\.\,\s-]{6,15}(?:\s*-\s*\d)?\b', 
        'NIT [NIT_ANONIMIZADO]', 
        text
    )
    
    return text
