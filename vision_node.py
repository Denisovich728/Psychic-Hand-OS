# Archivo: vision_node.py
"""Nodo de vision por computadora basado en MediaPipe Hands para PsychicHandOS."""

import json
import math
import os
import time
import urllib.request
from collections import deque

import cv2
import mediapipe as mp
import numpy as np

HAND_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task"
)

_USE_TASKS_API = not hasattr(mp, "solutions")
if not _USE_TASKS_API:
    mp_hands = mp.solutions.hands
else:
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe.tasks.python.core import base_options as mp_base_options


class VisionNode:
    """Extrae topologia de mano, estado de extension de cada dedo y metricas de pinch."""

    TIP_INDICES = (4, 8, 12, 16, 20)
    PIP_INDICES = (3, 6, 10, 14, 18)
    DIP_INDICES = (3, 7, 11, 15, 19)
    MCP_INDICES = (2, 5, 9, 13, 17)
    INFLECTION_INDICES = (2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, 18, 19)
    FINGER_CONNECTIONS = (
        (0, 1, 2, 3, 4),
        (0, 5, 6, 7, 8),
        (0, 9, 10, 11, 12),
        (0, 13, 14, 15, 16),
        (0, 17, 18, 19, 20),
    )

    def __init__(self, json_path="psychic_context.json", model_path=DEFAULT_MODEL_PATH):
        self.json_path = json_path
        self.telemetry_buffer = deque(maxlen=60)
        self._last_ts_ms = 0

        if _USE_TASKS_API:
            if not os.path.exists(model_path):
                print(f"[VisionNode] Descargando modelo hand_landmarker.task...")
                urllib.request.urlretrieve(HAND_LANDMARKER_URL, model_path)
            options = mp_vision.HandLandmarkerOptions(
                base_options=mp_base_options.BaseOptions(model_asset_path=model_path),
                running_mode=mp_vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.70,
                min_hand_presence_confidence=0.70,
                min_tracking_confidence=0.70,
            )
            self.landmarker = mp_vision.HandLandmarker.create_from_options(options)
            self.hands = None
        else:
            self.hands = mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=0.70,
                min_tracking_confidence=0.70,
            )
            self.landmarker = None

    def export_context_json(self, extra_note="mp_dump"):
        """Exporta muestras recientes de telemetria a JSON."""
        samples = list(self.telemetry_buffer)
        payload = {
            "app": "PsychicHandOS",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "MEDIAPIPE_HANDS",
            "note": extra_note,
            "recent_telemetry": samples[-10:] if samples else [],
        }
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    @staticmethod
    def _dist(p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    @staticmethod
    def _dist_3d(lm1, lm2):
        return math.sqrt(
            (lm1.x - lm2.x) ** 2 + (lm1.y - lm2.y) ** 2 + (lm1.z - lm2.z) ** 2
        )

    def _compute_finger_states(self, landmarks):
        """Determina [pulgar, indice, medio, anular, menique] extendidos de forma invariante."""
        wrist = landmarks[0]
        palm_scale = max(1e-4, self._dist_3d(wrist, landmarks[9]))

        # Pulgar: distancia de yema (4) al nudillo del menique (17) vs articulacion MCP (2)
        thumb_ext = (
            self._dist_3d(landmarks[4], landmarks[17])
            > self._dist_3d(landmarks[2], landmarks[17]) * 1.15
            and self._dist_3d(landmarks[4], landmarks[5]) > palm_scale * 0.42
        )

        states = [thumb_ext]
        for finger_idx in range(1, 5):
            tip = landmarks[self.TIP_INDICES[finger_idx]]
            dip = landmarks[self.DIP_INDICES[finger_idx]]
            pip = landmarks[self.PIP_INDICES[finger_idx]]
            mcp = landmarks[self.MCP_INDICES[finger_idx]]

            d_tip_wrist = self._dist_3d(tip, wrist)
            d_pip_wrist = self._dist_3d(pip, wrist)
            d_dip_wrist = self._dist_3d(dip, wrist)
            d_tip_mcp = self._dist_3d(tip, mcp)
            d_pip_mcp = self._dist_3d(pip, mcp)

            is_extended = (
                d_tip_wrist > d_pip_wrist * 1.12
                and d_tip_wrist > d_dip_wrist * 1.02
                and d_tip_mcp > d_pip_mcp * 1.15
            )
            states.append(is_extended)

        return states

    def extract_topology(self, frame):
        """Procesa un frame BGR y devuelve topologia completa de la mano detectada."""
        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        if _USE_TASKS_API:
            ts_ms = max(self._last_ts_ms + 1, int(time.monotonic() * 1000))
            self._last_ts_ms = ts_ms
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            results = self.landmarker.detect_for_video(mp_img, ts_ms)
            if not results.hand_landmarks:
                return {"valid": False, "hands": [], "frame_size": (w, h)}
            lms = results.hand_landmarks[0]
        else:
            results = self.hands.process(rgb_frame)
            if not results.multi_hand_landmarks:
                return {"valid": False, "hands": [], "frame_size": (w, h)}
            lms = results.multi_hand_landmarks[0].landmark

        pts = [(int(lm.x * w), int(lm.y * h)) for lm in lms]

        extended_fingers = self._compute_finger_states(lms)
        finger_mask = "".join("1" if ext else "0" for ext in extended_fingers)
        extended_count = sum(1 for ext in extended_fingers if ext)

        tips = [pts[i] for i in self.TIP_INDICES]
        extended_tips = [pts[self.TIP_INDICES[i]] for i, ext in enumerate(extended_fingers) if ext]
        inflections = [pts[i] for i in self.INFLECTION_INDICES]

        cx = int((pts[0][0] + pts[9][0]) / 2)
        cy = int((pts[0][1] + pts[9][1]) / 2)
        palm_radius = int(max(25.0, self._dist(pts[0], (cx, cy)) * 1.2))
        palm_scale = max(1e-4, self._dist_3d(lms[0], lms[9]))

        pinch_index = self._dist_3d(lms[4], lms[8]) / palm_scale
        pinch_middle = self._dist_3d(lms[4], lms[12]) / palm_scale

        chains = [[pts[idx] for idx in conn] for conn in self.FINGER_CONNECTIONS]

        all_x = [p[0] for p in pts]
        all_y = [p[1] for p in pts]
        aspect_ratio = min(
            1.0,
            (max(all_x) - min(all_x) + 1.0) / (max(all_y) - min(all_y) + 1.0),
        )

        pts_array = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
        hull_pts = cv2.convexHull(pts_array)

        self.telemetry_buffer.append({
            "backend": "mediapipe",
            "mask": finger_mask,
            "extended": extended_count,
            "pinch_index": round(pinch_index, 3),
            "pinch_middle": round(pinch_middle, 3),
            "aspect": round(aspect_ratio, 2),
        })

        return {
            "valid": True,
            "hands": [{
                "centroid": (cx, cy),
                "radius": palm_radius,
                "aspect_ratio": aspect_ratio,
                "pts": pts,
                "inflections": inflections,
                "tips": tips,
                "extended_tips": extended_tips,
                "extended_fingers": extended_fingers,
                "finger_mask": finger_mask,
                "extended_count": extended_count,
                "pinch_index": pinch_index,
                "pinch_middle": pinch_middle,
                "chains": chains,
                "hull": hull_pts,
            }],
            "frame_size": (w, h),
        }
