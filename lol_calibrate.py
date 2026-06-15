"""
lol_calibrate.py
================
Dos modos:

  1. Obtener color exacto del botón:
       python lol_calibrate.py
     (espera 5s, deja el mouse sobre el botón ACCEPT)

  2. Ver el rectángulo ROI dibujado en pantalla:
       python lol_calibrate.py --debug
     Abre una ventana con la captura y el rectángulo de búsqueda.
     Úsalo para verificar que el ROI cubre el botón correctamente.
     Ajusta ROI_X1/X2/Y1/Y2 en lol_auto_accept.py hasta que quede bien.
"""

import pyautogui
import cv2
import numpy as np
import time
import sys

# ─── Mismos valores ROI que en lol_auto_accept.py ────────────────────────────
# Copia acá los mismos valores que estés usando allá para verlos dibujados
ROI_X1 = 0.44
ROI_X2 = 0.55
ROI_Y1 = 0.65
ROI_Y2 = 0.75


def get_color_at_mouse():
    screenshot = pyautogui.screenshot()
    img = np.array(screenshot)
    x, y = pyautogui.position()
    pixel_rgb = img[y, x]
    pixel_bgr = np.uint8([[[int(pixel_rgb[2]), int(pixel_rgb[1]), int(pixel_rgb[0])]]])
    pixel_hsv = cv2.cvtColor(pixel_bgr, cv2.COLOR_BGR2HSV)[0][0]
    return img, x, y, pixel_rgb, pixel_hsv


def mode_color():
    print("=== Calibrador de Color ===\n")
    print("Tienes 5 segundos para poner el mouse SOBRE el botón ACCEPT de LoL...")
    for i in range(5, 0, -1):
        print(f"  {i}...", end="\r")
        time.sleep(1)

    img, x, y, rgb, hsv = get_color_at_mouse()
    h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])
    margen_h = 10

    print(f"\n📍 Posición: ({x}, {y})")
    print(f"   RGB : ({rgb[0]}, {rgb[1]}, {rgb[2]})")
    print(f"   HSV : ({h}, {s}, {v})")
    print(f"\n✅ Pega esto en lol_auto_accept.py:")
    print(f"   GREEN_LOWER = np.array([{max(0, h - margen_h)}, {max(0, s - 60)}, {max(0, v - 60)}])")
    print(f"   GREEN_UPPER = np.array([{min(179, h + margen_h)}, 255, 255])")
    print("\n💡 Si el botón tiene animación, repite 2-3 veces y promedia el valor H.")


def mode_debug():
    print("=== Modo Debug ROI ===\n")
    print("Tienes 4 segundos para ir a la pantalla de LoL con el popup visible...")
    for i in range(4, 0, -1):
        print(f"  {i}...", end="\r")
        time.sleep(1)

    screenshot = pyautogui.screenshot()
    img = np.array(screenshot)
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    h_full, w_full = img_bgr.shape[:2]
    x1 = int(w_full * ROI_X1)
    x2 = int(w_full * ROI_X2)
    y1 = int(h_full * ROI_Y1)
    y2 = int(h_full * ROI_Y2)

    # Dibujar rectángulo ROI en rojo y las coordenadas
    debug_img = img_bgr.copy()
    cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 0, 255), 3)
    label = f"ROI: ({x1},{y1}) -> ({x2},{y2})"
    cv2.putText(debug_img, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

    # Guardar imagen con el rectángulo para revisión
    out_path = "roi_debug.png"
    cv2.imwrite(out_path, debug_img)
    print(f"\n✅ Imagen guardada como '{out_path}'")
    print(f"   ROI actual: X {ROI_X1}-{ROI_X2} | Y {ROI_Y1}-{ROI_Y2}")
    print(f"   Píxeles:    X {x1}-{x2} | Y {y1}-{y2}")
    print("\n   Abre 'roi_debug.png' y verifica que el rectángulo rojo cubra el botón ACCEPT.")
    print("   Si no lo cubre, ajusta ROI_X1/X2/Y1/Y2 en lol_auto_accept.py (y acá arriba).")

    # Intentar mostrar ventana (puede no funcionar en todos los entornos)
    try:
        cv2.imshow("ROI Debug - presiona cualquier tecla para cerrar", debug_img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    except Exception:
        print("   (No se pudo abrir ventana, revisa roi_debug.png directamente)")


if __name__ == "__main__":
    if "--debug" in sys.argv:
        mode_debug()
    else:
        mode_color()

