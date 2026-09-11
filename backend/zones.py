"""Geofencing Zone Engine for SafetyLens AI.

Additive post-processing layer for spatial geofencing:
- Normalized polygon coordinate storage [0.0, 1.0] for resolution independence.
- Ray-casting point-in-polygon algorithm (pure Python, zero extra dependencies).
- Person anchor point calculation (bottom-center of bounding box / feet contact).
- PPE-requirement zone breach tagging (reusing temporally confirmed violations).
- RESTRICTED zone breach detection with streak counters and cooldown.
- Visual frame annotation with zone boundaries and labels.
"""

import time
import cv2
import numpy as np

import config
from database import get_zones

VALID_REQUIREMENTS = {
    "HELMET",
    "VEST",
    "GLOVES",
    "BOOTS",
    "GOGGLES",
    "ANY_PPE",
    "RESTRICTED",
}

PPE_REQUIREMENT_MAP = {
    "HELMET": {"NO_HELMET"},
    "VEST": {"NO_VEST"},
    "GLOVES": {"NO_GLOVES"},
    "BOOTS": {"NO_BOOTS"},
    "GOGGLES": {"NO_GOGGLES"},
    "ANY_PPE": {"NO_HELMET", "NO_VEST", "NO_GLOVES", "NO_BOOTS", "NO_GOGGLES"},
}

# Color palette for zone rendering (BGR format for OpenCV)
ZONE_COLORS = {
    "RESTRICTED": (48, 59, 255),    # Industrial Red
    "HELMET": (0, 180, 255),        # Amber
    "VEST": (0, 180, 255),          # Amber
    "ANY_PPE": (0, 180, 255),       # Amber
    "GLOVES": (240, 196, 57),       # Cyan
    "BOOTS": (240, 196, 57),        # Cyan
    "GOGGLES": (240, 196, 57),      # Cyan
}

# In-memory tracking states for RESTRICTED zones:
# Key: (camera_id, zone_id, track_id)
_restricted_streaks: dict[tuple[str, int, int], int] = {}
_restricted_cooldowns: dict[tuple[str, int, int], float] = {}


def point_in_polygon(pt: tuple[float, float], poly: list[list[float]]) -> bool:
    """Ray-casting algorithm to test if point pt=(x, y) is inside polygon.

    Args:
        pt: (x, y) float coordinate.
        poly: list of [x, y] coordinates forming the polygon.

    Returns:
        bool: True if pt is strictly inside or on edge according to ray-casting.
    """
    if not poly or len(poly) < 3:
        return False
    x, y = pt
    inside = False
    n = len(poly)
    p1x, p1y = poly[0]
    for i in range(1, n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def get_person_anchor(box: list[int | float], frame_shape: tuple[int, int] | None = None) -> tuple[float, float]:
    """Calculate the normalized bottom-center feet anchor point for a bounding box.

    Args:
        box: [x1, y1, x2, y2] bounding box.
        frame_shape: Optional (height, width) of the frame.

    Returns:
        (norm_x, norm_y) tuple clamped to [0.0, 1.0].
    """
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2.0
    cy = float(y2)

    if frame_shape is not None and frame_shape[0] > 0 and frame_shape[1] > 0:
        h, w = frame_shape[:2]
        nx = cx / float(w)
        ny = cy / float(h)
    else:
        # If no frame_shape passed, check if coordinates are already normalized
        if max(x2, y2) <= 1.0:
            nx = cx
            ny = cy
        else:
            # Fallback assuming standard 640x480 resolution
            nx = cx / 640.0
            ny = cy / 480.0

    return max(0.0, min(1.0, float(nx))), max(0.0, min(1.0, float(ny)))


def _iou(a: list[int | float], b: list[int | float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def _extract_tracked_persons(detections: list[dict], compliance_state: dict | None = None) -> list[dict]:
    """Extract persons with track IDs from detections and compliance tracking state."""
    min_conf = config.SETTINGS.get("confidence", 0.3)
    persons = [
        d for d in detections
        if d.get("cls") in ("Person", "person") and d.get("conf", 1.0) >= min_conf
    ]

    # Resolve active trackers
    trackers = None
    if compliance_state is not None and "trackers" in compliance_state:
        trackers = compliance_state["trackers"]
    else:
        try:
            import compliance
            trackers = compliance._trackers
        except Exception:
            trackers = None

    results = []
    for i, p in enumerate(persons):
        box = p["box"]
        conf = float(p.get("conf", 1.0))
        # 1. Use explicit pid or track_id if provided
        pid = p.get("pid") or p.get("track_id")

        # 2. Try matching to active compliance trackers via IoU
        if pid is None and trackers:
            best_iou = 0.3
            best_track = None
            for tid, tinfo in trackers.items():
                score = _iou(box, tinfo.get("box", [0, 0, 0, 0]))
                if score > best_iou:
                    best_iou = score
                    best_track = tid
            if best_track is not None:
                pid = best_track

        # 3. Fallback to index-based deterministic id
        if pid is None:
            pid = i + 1

        results.append({"pid": pid, "box": box, "conf": conf})

    return results


def check_zones(
    camera_id: str,
    detections: list[dict],
    violations: list[dict],
    frame_shape: tuple[int, int] | None = None,
    compliance_state: dict | None = None,
) -> list[dict]:
    """Check detections and confirmed violations against configured geofencing zones.

    - PPE requirement zones: If a confirmed violation's person anchor lies inside
      a matching zone, tags the violation in-place with zone_name and severity="CRITICAL".
    - RESTRICTED zones: If a tracked person's anchor lies inside a RESTRICTED zone,
      increments streak count. Once streak >= min_frames and cooldown has elapsed,
      emits a ZONE_BREACH event.

    Args:
        camera_id: Target camera identifier.
        detections: List of detection dicts (cls, conf, box, ...).
        violations: List of confirmed PPE violations from check_compliance.
        frame_shape: Optional (height, width) tuple of the input frame.
        compliance_state: Optional per-camera compliance tracking state.

    Returns:
        list[dict]: List of breach events occurring within zones (both newly triggered
                    RESTRICTED ZONE_BREACH events and in-zone PPE breaches).
    """
    zones = get_zones(camera_id=camera_id, enabled_only=True)
    if not zones:
        return []

    ppe_zones = [z for z in zones if z["requirement"] != "RESTRICTED"]
    restricted_zones = [z for z in zones if z["requirement"] == "RESTRICTED"]

    breaches = []
    now = time.time()

    # --- 1. Evaluate PPE-requirement zones ---
    for v in violations:
        v_type = v.get("type")
        v_box = v.get("box")
        if not v_box:
            continue
        anchor = get_person_anchor(v_box, frame_shape)

        for zone in ppe_zones:
            allowed_types = PPE_REQUIREMENT_MAP.get(zone["requirement"], set())
            if v_type in allowed_types:
                if point_in_polygon(anchor, zone["points"]):
                    v["zone_name"] = zone["name"]
                    v["zone_id"] = zone["id"]
                    v["severity"] = "CRITICAL"
                    if v not in breaches:
                        breaches.append(v)
                    break

    # --- 2. Evaluate RESTRICTED zones ---
    if restricted_zones:
        persons = _extract_tracked_persons(detections, compliance_state)
        min_frames = config.SETTINGS.get("min_frames", 3)
        cooldown_sec = config.SETTINGS.get("cooldown_sec", 30)

        active_restricted_keys = set()

        for p in persons:
            anchor = get_person_anchor(p["box"], frame_shape)
            pid = p["pid"]

            for rz in restricted_zones:
                if point_in_polygon(anchor, rz["points"]):
                    key = (camera_id, rz["id"], pid)
                    active_restricted_keys.add(key)
                    _restricted_streaks[key] = _restricted_streaks.get(key, 0) + 1

                    if _restricted_streaks[key] >= min_frames:
                        if now - _restricted_cooldowns.get(key, 0) >= cooldown_sec:
                            _restricted_cooldowns[key] = now
                            breach_event = {
                                "type": "ZONE_BREACH",
                                "conf": p["conf"],
                                "box": list(p["box"]),
                                "zone_name": rz["name"],
                                "zone_id": rz["id"],
                                "severity": "CRITICAL",
                                "pid": pid,
                            }
                            breaches.append(breach_event)

        # Streak decay for absent tracks
        keys_to_delete = []
        for k in list(_restricted_streaks.keys()):
            if k[0] == camera_id and k not in active_restricted_keys:
                _restricted_streaks[k] -= 1
                if _restricted_streaks[k] <= 0:
                    keys_to_delete.append(k)
        for k in keys_to_delete:
            del _restricted_streaks[k]

    return breaches


def draw_zones(frame: np.ndarray, camera_id: str) -> np.ndarray:
    """Draw enabled zone outlines, translucent fills, and labels on an image frame.

    Visual only — does not affect detection or compliance logic.

    Args:
        frame: OpenCV BGR image frame.
        camera_id: Camera identifier whose zones should be drawn.

    Returns:
        np.ndarray: The annotated frame.
    """
    zones = get_zones(camera_id=camera_id, enabled_only=True)
    if not zones:
        return frame

    h, w = frame.shape[:2]
    overlay = frame.copy()

    for zone in zones:
        poly = zone.get("points", [])
        if len(poly) < 3:
            continue

        req = zone.get("requirement", "ANY_PPE")
        color = ZONE_COLORS.get(req, (0, 180, 255))
        pts = np.array([[int(p[0] * w), int(p[1] * h)] for p in poly], np.int32)

        # Translucent fill
        cv2.fillPoly(overlay, [pts], color)

        # Boundary polygon outline
        cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)

        # Zone label badge
        lx, ly = pts[0][0], pts[0][1]
        label = f"[{req}] {zone['name']}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(frame, (lx, max(0, ly - th - 6)), (lx + tw + 6, ly), (10, 14, 18), -1)
        cv2.rectangle(frame, (lx, max(0, ly - th - 6)), (lx + tw + 6, ly), color, 1)
        cv2.putText(frame, label, (lx + 3, max(10, ly - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    # Blend translucent fill
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
    return frame


def clear_camera_zone_state(camera_id: str):
    """Purge streak and cooldown state for a specific camera."""
    for k in list(_restricted_streaks.keys()):
        if k[0] == camera_id:
            del _restricted_streaks[k]
    for k in list(_restricted_cooldowns.keys()):
        if k[0] == camera_id:
            del _restricted_cooldowns[k]


def clear_zone_state(zone_id: int):
    """Purge streak and cooldown state for a specific zone."""
    for k in list(_restricted_streaks.keys()):
        if k[1] == zone_id:
            del _restricted_streaks[k]
    for k in list(_restricted_cooldowns.keys()):
        if k[1] == zone_id:
            del _restricted_cooldowns[k]


def reset_all_zone_state():
    """Reset all zone tracking state across all cameras (used in tests)."""
    _restricted_streaks.clear()
    _restricted_cooldowns.clear()
