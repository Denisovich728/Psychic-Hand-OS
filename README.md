# PsychicHandOS

Controlador de escritorio y raton sin contacto basado en vision por computadora (MediaPipe Hands + OpenCV + pynput) con motor de gestos configurable en tiempo real.

## Arquitectura

El sistema opera en un pipeline modular de tres nodos desacoplados y un configurador grafico:

1. **`vision_node.py` (`VisionNode`)**
   - Captura los 21 landmarks 3D de la mano mediante MediaPipe Hands.
   - Calcula el estado de extension de cada dedo (`[Pulgar, Indice, Medio, Anular, Menique]`) de forma invariante a escala y rotacion, generando una mascara binaria de 5 bits (`finger_mask`, por ejemplo `"01000"`).
   - Calcula metricas normalizadas de pellizco (`pinch_index`, `pinch_middle`) y relacion de aspecto de la mano.

2. **`gesture_node.py` (`GestureNode`)**
   - Aplica un filtro adaptativo **One-Euro** (`OneEuroFilter`) sobre las coordenadas del puntero para eliminar el temblor en reposo sin introducir latencia al mover la mano.
   - Gestiona modos continuos (cursor, clic/doble clic/arrastre por pinch, scroll vertical) y reglas discretas cargadas desde `gestures_config.json` con recarga en caliente (*hot-reload*).
   - Implementa *dwell time* (`hold_frames`) y *cooldown* por regla para evitar disparos accidentales.

3. **`os_actuator_node.py` (`OSActuatorNode`)**
   - Traduce los comandos del evaluador a eventos nativos de raton, scroll, teclas multimedia y combinaciones de teclado (`ctrl+c`, `win+d`, `alt+tab`, etc.) en Windows.

4. **`configurator_ui.py` (`GestureConfiguratorApp`)**
   - Interfaz grafica en Tkinter para agregar, editar, activar/desactivar o eliminar gestos, ajustar parametros de cursor/scroll y capturar la postura actual de la camara en vivo.

5. **`psychic_hand_os.py`**
   - Bucle principal, renderizado del HUD de telemetria, atajos globales de teclado y lanzamiento del configurador.

---

## Requisitos e Instalacion

- Python 3.10+ (probado en Python 3.14)
- Camara web funcional
- Dependencias Python:
  - `opencv-python`
  - `mediapipe`
  - `numpy`
  - `pynput`

Instalacion rapida:

```bash
pip install opencv-python mediapipe numpy pynput
```

---

## Ejecucion y Controles

Iniciar la aplicacion principal:

```bash
python psychic_hand_os.py
```

Abrir unicamente el configurador de gestos:

```bash
python configurator_ui.py
```

### Atajos globales en ejecucion

| Tecla | Accion |
| :--- | :--- |
| `F7` | Alternar entre vista de camara real y HUD sobre fondo negro |
| `F8` | Activar (`ARMED`) o pausar (`PREVIEW ONLY`) el control sobre Windows |
| `F9` | Recargar configuracion y reiniciar filtros |
| `F10` | Abrir el Configurador de Gestos en una ventana independiente |
| `F11` | Exportar telemetria reciente a `psychic_context.json` |
| `ESC` | Cerrar PsychicHandOS |

Por seguridad, el programa inicia siempre en modo **PREVIEW ONLY (`F8: OFF`)** para que puedas verificar la deteccion antes de habilitar el control del sistema.

---

## Gestos por Defecto

La mascara de 5 bits sigue el orden `[Pulgar, Indice, Medio, Anular, Menique]` (`1` = extendido, `0` = doblado):

| Gesto | Mascara / Disparo | Accion por defecto |
| :--- | :--- | :--- |
| Mover cursor | `01000` (solo indice) | Mueve el puntero del raton |
| Clic izquierdo | Pinch pulgar + indice en modo cursor | Clic izquierdo |
| Doble clic | Dos pinches rapidos en modo cursor | Doble clic izquierdo |
| Arrastrar (Drag) | Mantener pinch pulgar + indice > 0.35s | Mantiene presionado clic izquierdo |
| Scroll vertical | `01100` (indice + medio) | Desplazamiento vertical arriba/abajo |
| Clic derecho | `01110` (3 dedos) | Clic derecho |
| Puno cerrado | `00000` | `win+d` (Mostrar/Ocultar escritorio) |
| Shaka | `10001` (pulgar + menique) | `alt+tab` (Cambiar ventana) |
| Pinch medio | `pinch_middle` | `win+down` (Minimizar ventana actual) |

---

## Configurador y Formato JSON

Al presionar `F10` (o ejecutar `python configurator_ui.py`), puedes:
- Crear nuevas reglas seleccionando los dedos con casillas o presionando **Usar postura en vivo** mientras tu mano esta frente a la camara.
- Elegir el tipo de disparo (`mask`, `pinch_index`, `pinch_middle`, `tilt_side`), `hold_frames` y `cooldown`.
- Asignar acciones de raton, atajos de teclado (`ctrl+c`, `win+tab`, `ctrl+shift+t`, etc.) o teclas multimedia.
- Guardar en `gestures_config.json`; `psychic_hand_os.py` detecta el cambio y aplica las nuevas reglas al instante sin reiniciar.
