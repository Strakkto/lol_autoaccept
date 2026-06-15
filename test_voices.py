#!/usr/bin/env python3
"""
Script para listar todas las voces disponibles en edge-tts
"""

import asyncio
import edge_tts

async def list_voices():
    voices = await edge_tts.list_voices()
    print(f"Total de voces disponibles: {len(voices)}\n")
    
    # Filtrar voces en español
    spanish_voices = [v for v in voices if v['Locale'].startswith('es-')]
    print(f"Voces en español ({len(spanish_voices)}):")
    print("-" * 70)
    
    for voice in spanish_voices:
        print(f"  Locale: {voice['Locale']:<8} | Nombre: {voice['ShortName']:<30} | Género: {voice['Gender']}")

asyncio.run(list_voices())
