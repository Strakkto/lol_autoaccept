#!/usr/bin/env python3
"""
lol_jarvis.py
=============
Jarvis para League of Legends — control total por voz vía LCU API.

COMANDOS DE VOZ:
  "jarvis acepta la partida"   →  activa auto-accept (toggle ON)
  "jarvis pausa"               →  desactiva auto-accept (toggle OFF)
  "jarvis buscar partida"      →  inicia búsqueda de partida inmediatamente
  "jarvis juega <campeón>"     →  selecciona campeón (pide confirmación)

TECLADO:
  Ctrl+Alt+A   →  toggle auto-accept ON/OFF
  Ctrl+C       →  salir

USO:
  pip install -r requirements.txt
  python lol_jarvis.py
"""

import time
import os
import threading
import asyncio
import tempfile
import sys
import speech_recognition as sr
import keyboard
import edge_tts
import pygame

from lcu_client import LCUClient, LCUError
from champions import resolve_champion

# ─── Configuración ────────────────────────────────────────────────────────────

HOTKEY = "ctrl+alt+a"
VOICE_LANG = "es-CL"
JARVIS_VOICE = "es-MX-JorgeNeural"

# Intervalo entre checks de auto-accept (segundos)
CHECK_INTERVAL = 1.0

# Tiempo máximo esperando confirmación de campeón (segundos)
CONFIRM_TIMEOUT = 5.0

# ─── Palabras clave de voz ────────────────────────────────────────────────────

VOICE_ON = [
    "jarvis acepta la partida",
    "jarvis acepta",
    "jarvis aceptar",
]
VOICE_OFF = [
    "jarvis pausa",
    "jarvis pausar",
    "jarvis detente",
]
VOICE_SEARCH = [
    "jarvis buscar partida",
    "jarvis busca partida",
    "jarvis encuentra partida",
]
VOICE_PICK_PREFIX = [
    "jarvis juega",
    "jarvis elige",
    "jarvis pickea",
    "jarvis selecciona",
    "jarvis instalocker",
]
VOICE_CONFIRM = ["sí", "si", "confirma", "confirmar", "dale", "ok"]
VOICE_CANCEL = ["no", "cancela", "cancelar", "aborta", "para"]

# ─── Frases de Jarvis ─────────────────────────────────────────────────────────

JARVIS_READY = "Sistemas online. Estaré atento a la cola por usted, señor."
JARVIS_PAUSED = "Entendido. Esperando instrucciones."
JARVIS_ACCEPTED = "Partida encontrada, señor. Aceptando ahora."
JARVIS_SEARCHING = "Iniciando búsqueda de partida."
JARVIS_SEARCH_FAIL = "No pude iniciar la búsqueda. Verifique que esté en el lobby."
JARVIS_NO_CLIENT = "Cliente de League no detectado. Por favor, abra el cliente primero."
JARVIS_PICK_CONFIRM = "¿Confirmo {}?"
JARVIS_PICK_OK = "Lockeando {}. Buena suerte, señor."
JARVIS_PICK_FAIL = "No se pudo seleccionar a {}. Verifique que esté en champion select."
JARVIS_PICK_CANCEL = "Selección cancelada."
JARVIS_PICK_TIMEOUT = "Sin confirmación. Selección cancelada."
JARVIS_CHAMP_NOT_FOUND = "No reconocí ese campeón. Intente de nuevo."

# ─── Estado compartido ───────────────────────────────────────────────────────

_lock = threading.Lock()
_active = True           # auto-accept ON por defecto
_stop = False            # señal de cierre global

# Estado de confirmación de campeón
_pending_champ: tuple[str, int] | None = None   # (nombre, id) esperando confirm
_confirm_event = threading.Event()
_confirm_result: bool = False


def is_active() -> bool:
    with _lock:
        return _active


def set_active(value: bool, source: str = ""):
    global _active
    with _lock:
        _active = value
    estado = "▶  ACTIVO" if value else "⏸  PAUSADO"
    tag = f"[{source}]" if source else ""
    print(f"\n  {estado} {tag}\n")
    phrase = JARVIS_READY if value else JARVIS_PAUSED
    _speak_async(phrase)


def toggle(source: str = ""):
    set_active(not is_active(), source)


# ─── TTS ──────────────────────────────────────────────────────────────────────

def _speak_async(text: str):
    """Lanza speak() en hilo separado para no bloquear."""
    threading.Thread(target=speak, args=(text,), daemon=True).start()


def speak(text: str):
    """Genera audio con Edge TTS y lo reproduce con pygame."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        async def _generate():
            communicate = edge_tts.Communicate(text, JARVIS_VOICE)
            await communicate.save(tmp_path)

        asyncio.run(_generate())

        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)

        os.unlink(tmp_path)

    except Exception as e:
        print(f"  ⚠  TTS error: {e}")


# ─── Hilo: Reconocimiento de voz ─────────────────────────────────────────────

def voice_thread(lcu: LCUClient):
    """
    Escucha comandos de voz continuamente y los despacha.
    Corre en hilo separado del loop de detección.
    """
    global _pending_champ, _confirm_result

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.6
    recognizer.energy_threshold = 300

    print("  🎙  Micrófono listo — escuchando comandos de voz...")

    with sr.Microphone() as mic:
        recognizer.adjust_for_ambient_noise(mic, duration=1)

        while not _stop:
            try:
                audio = recognizer.listen(mic, timeout=3, phrase_time_limit=6)
                texto = recognizer.recognize_google(audio, language=VOICE_LANG).lower()
                print(f"  🎙  Escuché: '{texto}'")

                # ── Confirmación de campeón pendiente ──────────────────────
                if _pending_champ is not None:
                    if any(p in texto for p in VOICE_CONFIRM):
                        _confirm_result = True
                        _confirm_event.set()
                    elif any(p in texto for p in VOICE_CANCEL):
                        _confirm_result = False
                        _confirm_event.set()
                    continue  # mientras espera confirmación, ignorar otros comandos

                # ── Toggle auto-accept ──────────────────────────────────────
                if any(p in texto for p in VOICE_ON):
                    if not is_active():
                        set_active(True, "voz")

                elif any(p in texto for p in VOICE_OFF):
                    if is_active():
                        set_active(False, "voz")

                # ── Buscar partida ──────────────────────────────────────────
                elif any(p in texto for p in VOICE_SEARCH):
                    _handle_search(lcu)

                # ── Seleccionar campeón ─────────────────────────────────────
                elif any(texto.startswith(p) for p in VOICE_PICK_PREFIX):
                    # Se lanza en hilo separado para que voice_thread quede
                    # libre de seguir escuchando el "sí" / "no" de confirmación
                    threading.Thread(
                        target=_handle_pick,
                        args=(texto, lcu),
                        daemon=True,
                    ).start()

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"  ⚠  Error API voz: {e}")
                time.sleep(3)
            except Exception as e:
                print(f"  ⚠  Voz: {e}")
                time.sleep(1)


def _handle_search(lcu: LCUClient):
    """Ejecuta búsqueda de partida vía LCU."""
    print("  🔍  Iniciando búsqueda de partida...")
    try:
        ok = lcu.search_match()
        if ok:
            print("  ✅  Búsqueda iniciada.")
            _speak_async(JARVIS_SEARCHING)
        else:
            print("  ⚠  No se pudo iniciar la búsqueda.")
            _speak_async(JARVIS_SEARCH_FAIL)
    except LCUError:
        print("  ⚠  Cliente no detectado.")
        _speak_async(JARVIS_NO_CLIENT)


def _handle_pick(texto: str, lcu: LCUClient):
    """
    Flujo completo de selección de campeón:
      1. Extrae el nombre del campeón del texto
      2. Fuzzy match contra lista oficial
      3. Pide confirmación por voz (timeout: CONFIRM_TIMEOUT segundos)
      4. Si confirma → lockea vía LCU
    """
    global _pending_champ, _confirm_result

    # Extraer nombre: todo lo que viene después del prefijo
    raw_name = texto
    for prefix in VOICE_PICK_PREFIX:
        if texto.startswith(prefix):
            raw_name = texto[len(prefix):].strip()
            break

    if not raw_name:
        _speak_async(JARVIS_CHAMP_NOT_FOUND)
        return

    result = resolve_champion(raw_name)
    if result is None:
        print(f"  ⚠  Campeón no reconocido: '{raw_name}'")
        _speak_async(JARVIS_CHAMP_NOT_FOUND)
        return

    champ_name, champ_id = result
    print(f"  🎮  Campeón detectado: {champ_name} (id={champ_id})")

    # ── Pedir confirmación ──────────────────────────────────────────────────
    _pending_champ = (champ_name, champ_id)
    _confirm_event.clear()
    _confirm_result = False

    speak(JARVIS_PICK_CONFIRM.format(champ_name))  # bloqueante para que se escuche antes

    confirmed = _confirm_event.wait(timeout=CONFIRM_TIMEOUT)

    _pending_champ = None  # liberar estado de confirmación

    if not confirmed:
        print("  ⏱  Timeout de confirmación.")
        _speak_async(JARVIS_PICK_TIMEOUT)
        return

    if not _confirm_result:
        print("  ❌  Selección cancelada por el usuario.")
        _speak_async(JARVIS_PICK_CANCEL)
        return

    # ── Lockear campeón ─────────────────────────────────────────────────────
    print(f"  🔒  Lockeando {champ_name}...")
    try:
        ok = lcu.select_champion(champ_id)
        if ok:
            print(f"  ✅  {champ_name} lockeado.")
            _speak_async(JARVIS_PICK_OK.format(champ_name))
        else:
            print(f"  ⚠  No se pudo lockear {champ_name}.")
            _speak_async(JARVIS_PICK_FAIL.format(champ_name))
    except LCUError as e:
        print(f"  ⚠  LCU Error: {e}")
        _speak_async(JARVIS_PICK_FAIL.format(champ_name))


# ─── Hilo: Auto-accept loop ───────────────────────────────────────────────────

def accept_loop(lcu: LCUClient):
    """
    Cuando auto-accept está activo, consulta la LCU cada CHECK_INTERVAL
    segundos para ver si hay una cola esperando y la acepta automáticamente.
    """
    accepted = 0

    while not _stop:
        if not is_active():
            time.sleep(0.3)
            continue

        try:
            ready_check = lcu.get_ready_check()

            if ready_check and ready_check.get("state") == "InProgress":
                ok = lcu.accept_match()
                if ok:
                    accepted += 1
                    print(f"  🟢  ¡Cola aceptada! (total: {accepted})")
                    _speak_async(JARVIS_ACCEPTED)
                    time.sleep(3.0)  # cooldown para no re-aceptar

            else:
                print(f"  🔍  Monitoreando cola... (aceptadas: {accepted})", end="\r")

        except LCUError:
            print("  ⚠  Cliente no detectado. Reintentando...", end="\r")
            lcu.connect()

        time.sleep(CHECK_INTERVAL)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global _stop

    pygame.mixer.init()

    print("╔══════════════════════════════════════════════╗")
    print("║          Jarvis para LoL  🎮  🤖             ║")
    print("╠══════════════════════════════════════════════╣")
    print("║  🎹  Ctrl+Alt+A  →  toggle auto-accept       ║")
    print("║  🎙  'jarvis acepta la partida'               ║")
    print("║  🎙  'jarvis buscar partida'                  ║")
    print("║  🎙  'jarvis juega <campeón>'                 ║")
    print("║  🎙  'jarvis pausa'                           ║")
    print("║  🛑  Ctrl+C para salir                       ║")
    print("╠══════════════════════════════════════════════╣")
    print("║  Estado inicial: ▶  ACTIVO                    ║")
    print("╚══════════════════════════════════════════════╝\n")

    # ── Conectar con LCU ───────────────────────────────────────────────────
    lcu = LCUClient()
    print("  🔌  Conectando con el cliente de LoL...")

    if not lcu.connect():
        print("  ⚠  Cliente no detectado. El script funcionará cuando lo abras.")
        print("      (El auto-accept y los comandos de acción avisarán si no hay cliente)\n")
    else:
        print("  ✅  Conectado al cliente de LoL.\n")

    # ── Hotkey ────────────────────────────────────────────────────────────
    keyboard.add_hotkey(HOTKEY, lambda: toggle("tecla"))
    print(f"  ✅  Hotkey '{HOTKEY}' registrado.\n")

    # ── Hilos ─────────────────────────────────────────────────────────────
    t_voice = threading.Thread(target=voice_thread, args=(lcu,), daemon=True)
    t_voice.start()

    t_accept = threading.Thread(target=accept_loop, args=(lcu,), daemon=True)
    t_accept.start()

    try:
        while not _stop:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\n  👋  Cerrando Jarvis...")
    finally:
        _stop = True
        keyboard.unhook_all()
        pygame.mixer.quit()


if __name__ == "__main__":
    main()