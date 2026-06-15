#!/usr/bin/env python3
"""
LoL Auto-Accept
================
Detecta el botón ACCEPT de League of Legends y hace clic automáticamente.

CONTROLES:
  - Voz:      "jarvis acepta la partida"  →  enciende la detección
              "jarvis pausa"              →  pausa la detección
  - Teclado:  Ctrl+Alt+A                  →  toggle on/off
  - Salir:    Ctrl+C  o  mouse a esquina superior izquierda

USO:
  1. pip install -r requirements.txt
  2. python lol_auto_accept.py
"""

import pyautogui
import cv2
import numpy as np
import time
import os
import sys
import threading
import asyncio
import tempfile
import speech_recognition as sr
import keyboard
import edge_tts
import pygame

# ─── Configuración ────────────────────────────────────────────────────────────

CHECK_INTERVAL  = 0.4
TEMPLATE_CONF   = 0.78
COOLDOWN_AFTER  = 3.0
TEMPLATE_FILE   = "accept_button.png"
HOTKEY          = "ctrl+alt+a"
VOICE_LANG      = "es-CL"

# Voz de Jarvis — voz masculina en español latinoamericano
JARVIS_VOICE    = "es-MX-JorgeNeural"

# Palabras clave de voz
VOICE_ON  = ["jarvis acepta la partida", "jarvis acepta", "jarvis aceptar", "jarvis tene que acepta"]
VOICE_OFF = ["jarvis pausa"]

# Frases de Jarvis
JARVIS_READY    = "Sistemas online. Estaré atento a la cola por usted, señor. Puedes proceder."
JARVIS_MATCH    = "Partida encontrada, señor. Aceptando ahora."
JARVIS_PAUSED   = "Esperando instrucciones. Solo diga la palabra cuando esté listo."

# ─── Zona de búsqueda (ROI) ───────────────────────────────────────────────────
ROI_X1 = 0.44
ROI_X2 = 0.55
ROI_Y1 = 0.65
ROI_Y2 = 0.75

# ─── Color del botón ─────────────────────────────────────────────────────────
GREEN_LOWER = np.array([85, 100, 100])
GREEN_UPPER = np.array([105, 255, 255])
MIN_BUTTON_AREA = 2000

# ─── Estado compartido ───────────────────────────────────────────────────────
_lock   = threading.Lock()
_active = False
_stop   = False


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
    threading.Thread(target=speak, args=(phrase,), daemon=True).start()

def toggle(source: str = ""):
    set_active(not is_active(), source)


# ─── Jarvis TTS ──────────────────────────────────────────────────────────────

def speak(text: str):
    """
    Genera audio con Edge TTS (voz neural Microsoft) y lo reproduce.
    Corre en hilo separado para no bloquear la detección.
    """
    try:
        # Crear archivo temporal para el audio
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        # Generar audio con edge-tts (async → lo corremos con asyncio.run)
        async def _generate():
            communicate = edge_tts.Communicate(text, JARVIS_VOICE)
            await communicate.save(tmp_path)

        asyncio.run(_generate())

        # Reproducir con pygame
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)

        os.unlink(tmp_path)

    except Exception as e:
        print(f"  ⚠  TTS error: {e}")
        # Fallback silencioso — no interrumpe el script


# ─── Detección de pantalla ───────────────────────────────────────────────────

def capture_screen() -> np.ndarray:
    screenshot = pyautogui.screenshot()
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)


def find_by_template(img_bgr: np.ndarray, template_path: str):
    template = cv2.imread(template_path)
    if template is None:
        return None
    result = cv2.matchTemplate(img_bgr, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= TEMPLATE_CONF:
        h, w = template.shape[:2]
        return max_loc[0] + w // 2, max_loc[1] + h // 2
    return None


def find_by_color(img_bgr: np.ndarray):
    h_full, w_full = img_bgr.shape[:2]
    x1 = int(w_full * ROI_X1)
    x2 = int(w_full * ROI_X2)
    y1 = int(h_full * ROI_Y1)
    y2 = int(h_full * ROI_Y2)
    roi = img_bgr[y1:y2, x1:x2]

    hsv  = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, GREEN_LOWER, GREEN_UPPER)
    k    = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_area = None, MIN_BUTTON_AREA

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > best_area:
            best_area, best = area, cnt

    if best is not None:
        M = cv2.moments(best)
        if M["m00"] != 0:
            return int(M["m10"] / M["m00"]) + x1, int(M["m01"] / M["m00"]) + y1
    return None


# ─── Hilo: Reconocimiento de voz ─────────────────────────────────────────────

def voice_thread():
    recognizer = sr.Recognizer()
    recognizer.pause_threshold  = 0.6
    recognizer.energy_threshold = 300

    print("  🎙  Micrófono iniciado — escuchando comandos de voz...")

    with sr.Microphone() as mic:
        recognizer.adjust_for_ambient_noise(mic, duration=1)

        while not _stop:
            try:
                audio = recognizer.listen(mic, timeout=3, phrase_time_limit=5)
                texto = recognizer.recognize_google(audio, language=VOICE_LANG).lower()
                print(f"  🎙  Escuché: '{texto}'")

                if any(p in texto for p in VOICE_ON):
                    if not is_active():
                        set_active(True, "voz")

                elif any(p in texto for p in VOICE_OFF):
                    if is_active():
                        set_active(False, "voz")

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"  ⚠  Error API voz: {e} (¿hay conexión a internet?)")
                time.sleep(3)
            except Exception as e:
                print(f"  ⚠  Voz: {e}")
                time.sleep(1)


# ─── Hilo: Detección de pantalla ─────────────────────────────────────────────

def detection_loop():
    global _stop
    use_template = os.path.exists(TEMPLATE_FILE)
    accepted = 0

    while not _stop:
        if not is_active():
            time.sleep(0.2)
            continue

        try:
            img = capture_screen()
            result, method = None, ""

            if use_template:
                result = find_by_template(img, TEMPLATE_FILE)
                method = "template"

            if result is None:
                result = find_by_color(img)
                method = "color"

            if result:
                cx, cy = result
                accepted += 1
                print(f"  🟢  ¡Partida encontrada! [{method}] → ({cx}, {cy})")
                threading.Thread(target=speak, args=(JARVIS_MATCH,), daemon=True).start()
                pyautogui.click(cx, cy)
                print(f"  ✅  Aceptada #{accepted} — cooldown {COOLDOWN_AFTER}s...\n")
                time.sleep(COOLDOWN_AFTER)
            else:
                print(f"  🔍  Buscando... (aceptadas: {accepted})", end="\r")

            time.sleep(CHECK_INTERVAL)

        except pyautogui.FailSafeException:
            print("\n  🛑  Failsafe activado (mouse en esquina).")
            _stop = True


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global _stop
    pyautogui.FAILSAFE = True

    # Inicializar pygame mixer para audio
    pygame.mixer.init()

    print("╔══════════════════════════════════════════╗")
    print("║        LoL Auto-Accept  🎮  🤖           ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  🎹  Hotkey : {HOTKEY:<28}║")
    print(f"║  🎙  Voz ON : 'Jarvis acepta la partida' ║")
    print(f"║  🎙  Voz OFF: 'Jarvis pausa'             ║")
    print(f"║  🛑  Salir  : Ctrl+C                     ║")
    print("╠══════════════════════════════════════════╣")
    print("║  Estado inicial: ⏸  PAUSADO               ║")
    print("╚══════════════════════════════════════════╝\n")

    keyboard.add_hotkey(HOTKEY, lambda: toggle("tecla"))
    print(f"  ✅  Hotkey '{HOTKEY}' registrado\n")

    t_voice = threading.Thread(target=voice_thread, daemon=True)
    t_voice.start()

    t_detect = threading.Thread(target=detection_loop, daemon=True)
    t_detect.start()

    try:
        while not _stop:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\n  👋  Cerrando...")
    finally:
        _stop = True
        keyboard.unhook_all()
        pygame.mixer.quit()


if __name__ == "__main__":
    main()
