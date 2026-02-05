#!/usr/bin/env python3
"""
Macro Agent Skill - Desktop macro control for AI agents.

Features:
- Search elements in the screen map
- Move mouse (always smooth)
- Clicks, double-click, drag
- Type text, keys, hotkeys
- Create and run action sequences
"""
import sys
import os
import json
import time
import argparse
import glob
import unicodedata
import base64
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from data_paths import (
    SKILL_DIR as SKILL_DIR_PATH,
    LOCAL_DATA_DIR,
    ELEMENTS_FILE as ELEMENTS_FILE_PATH,
    CAPTURES_DIR as CAPTURES_DIR_PATH,
    SEQUENCES_DIR as SEQUENCES_DIR_PATH,
    ensure_local_data,
)

# Local runtime paths (unversioned), seeded from examples.
SKILL_DIR = str(SKILL_DIR_PATH)
DATA_DIR = str(LOCAL_DATA_DIR)
ELEMENTS_FILE = str(ELEMENTS_FILE_PATH)
CAPTURES_DIR = str(CAPTURES_DIR_PATH)
SEQUENCES_DIR = str(SEQUENCES_DIR_PATH)
ensure_local_data()

# Sound manager (optional audio feedback)
try:
    from sounds_manager import (
        sound_click, sound_double_click, sound_scroll, sound_type, 
        sound_key, sound_hotkey, sound_success, sound_error, sound_screenshot,
        enable_sounds, disable_sounds, sounds_enabled, set_volume, get_status as get_sound_status
    )
    HAS_SOUNDS = True
except ImportError:
    HAS_SOUNDS = False
    def sound_click(): pass
    def sound_double_click(): pass
    def sound_scroll(): pass
    def sound_type(length=0): pass
    def sound_key(): pass
    def sound_hotkey(): pass
    def sound_success(): pass
    def sound_error(): pass
    def sound_screenshot(): pass
    def enable_sounds(): return "Sounds not available"
    def disable_sounds(): return "Sounds not available"
    def sounds_enabled(): return False
    def set_volume(v): return "Sounds not available"
    def get_sound_status(): return {"enabled": False, "available": False}

try:
    import pyautogui
    import cv2
    import numpy as np
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    HAS_PYAUTOGUI = True
    HAS_CV2 = True
except ImportError:
    HAS_PYAUTOGUI = False
    HAS_CV2 = False


def output(data: Dict):
    """Prints result as JSON."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def error(message: str):
    """Prints an error as JSON."""
    output({"success": False, "error": message})
    sys.exit(1)


# ============================================
# ELEMENT FUNCTIONS (JSON)
# ============================================

def load_elements() -> Dict[str, Dict]:
    """Loads elements from JSON."""
    if not os.path.exists(ELEMENTS_FILE):
        return {}
    
    with open(ELEMENTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_elements(elements: Dict[str, Dict]):
    """Saves elements to JSON."""
    with open(ELEMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(elements, f, indent=2, ensure_ascii=False)


def get_element(name: str) -> Optional[Dict]:
    """Gets an element by exact or partial name."""
    elements = load_elements()
    name_lower = name.lower()
    
    # First try exact match
    if name_lower in elements:
        return elements[name_lower]
    
    # Then try partial name
    for key, elem in elements.items():
        if name_lower in key.lower():
            return elem
    
    # Then try tags
    for key, elem in elements.items():
        tags = elem.get('tags', [])
        if any(name_lower in tag.lower() for tag in tags):
            return elem
    
    return None


def add_element(name: str, description: str = "", images: List[str] = None, 
                tags: List[str] = None) -> Dict:
    """Adds or updates an element."""
    elements = load_elements()
    
    name_key = name.lower().replace(' ', '_')
    
    elements[name_key] = {
        "name": name_key,
        "description": description,
        "images": images or [],
        "tags": tags or []
    }
    
    save_elements(elements)
    return elements[name_key]


def add_image_to_element(name: str, image_file: str) -> Optional[Dict]:
    """Adds an image to an existing element or creates a new one."""
    elements = load_elements()
    name_key = name.lower().replace(' ', '_')
    
    if name_key in elements:
        if image_file not in elements[name_key]['images']:
            elements[name_key]['images'].append(image_file)
    else:
        # Create a new element
        elements[name_key] = {
            "name": name_key,
            "description": "",
            "images": [image_file],
            "tags": []
        }
    
    save_elements(elements)
    return elements[name_key]


def find_element(name: str) -> Optional[Dict]:
    """Finds an element by exact or partial name using JSON."""
    return get_element(name)


def find_element_on_screen(name: str, confidence: float = 0.8) -> Tuple[Optional[Tuple[int, int]], str, Dict]:
    """
    Finds an element by image on screen (template matching).
    ALWAYS uses image search, NEVER fixed coordinates.
    
    First checks elements.json to get valid images and exclusions.
    If not present in JSON, searches by name pattern in captures/.
    
    If there are multiple matches, returns the one with highest confidence.
    
    Args:
        name: Element name to search
        confidence: Confidence threshold (0.0 to 1.0)
    
    Returns: (coordinates, method_used, extra_info)
    - If found by image: ((x, y), 'image', {matches_found, best_score, images_tested})
    - If not found: (None, 'not_found', {matches_found, images_tested})
    """
    info = {
        "matches_found": 0,
        "best_score": 0.0,
        "images_tested": 0,
        "all_matches": [],
        "element_config": None
    }
    
    if not HAS_PYAUTOGUI:
        return None, 'no_pyautogui', info
    
    if not HAS_CV2:
        return None, 'no_cv2', info
    
    # Normalize name
    name_normalized = name.replace(' ', '_').lower()
    
    # ============================================
    # STEP 1: Check configuration in elements.json
    # ============================================
    element = get_element(name)
    
    image_files = []
    
    if element:
        info["element_config"] = element['name']
        # Use images defined in the element
        for img in element.get('images', []):
            img_path = os.path.join(CAPTURES_DIR, img)
            if os.path.exists(img_path):
                image_files.append(img_path)
    
    # If JSON has no images, search by pattern (fallback)
    if not image_files:
        patterns = [
            os.path.join(CAPTURES_DIR, f"{name_normalized}.png"),
            os.path.join(CAPTURES_DIR, f"{name_normalized}_*.png"),
            os.path.join(CAPTURES_DIR, f"{name.replace(' ', '_')}.png"),
            os.path.join(CAPTURES_DIR, f"{name.replace(' ', '_')}_*.png"),
        ]
        
        # Try partial matches if name has multiple words
        words = name_normalized.split('_')
        if len(words) > 1:
            all_files = glob.glob(os.path.join(CAPTURES_DIR, "*.png"))
            for f in all_files:
                fname = os.path.basename(f).lower()
                if all(word in fname for word in words):
                    patterns.append(f)
        
        for pattern in patterns:
            image_files.extend(glob.glob(pattern))
        
        # Remove duplicates
        image_files = list(dict.fromkeys(image_files))
    
    info["images_tested"] = len(image_files)
    
    # Capture full-screen screenshot
    try:
        screenshot = pyautogui.screenshot()
        screen_np = np.array(screenshot)
        # Convert RGB to BGR (OpenCV format)
        screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)
    except Exception as e:
        return None, 'screenshot_error', info
    
    # ============================================
    # STEP 2: Search the target element
    # ============================================
    best_match = None
    best_confidence = 0
    
    for img_path in image_files:
        try:
            # Load template in color for better accuracy
            template = cv2.imread(img_path, cv2.IMREAD_COLOR)
            if template is None:
                continue
            
            h, w = template.shape[:2]
            
            # Run color template matching
            result = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)
            
            # Find all locations above threshold
            locations = np.where(result >= confidence)
            
            # Count matches for this image
            matches_for_this_image = len(locations[0])
            if matches_for_this_image > 0:
                info["matches_found"] += matches_for_this_image
            
            # For each location, get exact score
            for pt in zip(*locations[::-1]):  # [::-1] swaps to (x, y)
                match_confidence = result[pt[1], pt[0]]
                
                # Compute center of the match
                center_x = int(pt[0] + w // 2)
                center_y = int(pt[1] + h // 2)
                
                # Record all matches
                info["all_matches"].append({
                    "x": center_x,
                    "y": center_y,
                    "score": float(match_confidence),
                    "image": os.path.basename(img_path)
                })
                
                # Keep the best match
                if match_confidence > best_confidence:
                    best_confidence = float(match_confidence)
                    best_match = (center_x, center_y)
        
        except Exception as e:
            # Continue with next image on error
            continue
    
    # Sort matches by score (descending)
    info["all_matches"].sort(key=lambda x: x["score"], reverse=True)
    info["best_score"] = best_confidence
    
    if best_match:
        return best_match, 'image', info
    
    # NO CSV fallback - image search only
    # If image is not found, return not_found
    return None, 'not_found', info


def search_elements(query: str) -> List[Dict]:
    """Searches elements by text in name, description, or tags."""
    elements = load_elements()
    query_lower = query.lower()
    results = []
    
    for key, elem in elements.items():
        score = 0
        elem_name = elem['name'].lower()
        desc = elem.get('description', '').lower()
        tags = ' '.join(elem.get('tags', [])).lower()
        
        if query_lower == elem_name:
            score = 100
        elif query_lower in elem_name:
            score = 50
        if query_lower in desc:
            score += 20
        if query_lower in tags:
            score += 15
        
        if score > 0:
            results.append({**elem, '_score': score})
    
    results.sort(key=lambda x: x['_score'], reverse=True)
    return results


# ============================================
# HUMAN-LIKE MOVEMENT CONFIGURATION
# ============================================
# IMPORTANT: all mouse functions use move_smooth() with humanize=True
# by default to reduce bot-like patterns. This includes:
# - move_smooth(): movement with Bezier curves, jitter, micro-pauses, and overshoot
# - do_click(): uses move_smooth() before clicking
# - do_double_click(): uses move_smooth() before double-clicking
# - do_drag(): uses move_smooth() to move to start and while dragging
# - do_scroll(): uses move_smooth() when a position is provided
# ============================================
import random
import math

# Tunable parameters for human-like movement
HUMAN_MOVEMENT_CONFIG = {
    # Jitter: small random offsets while moving
    'jitter_min': 1,        # Minimum offset in pixels
    'jitter_max': 4,        # Maximum offset in pixels
    'jitter_frequency': 0.4, # Probability of jitter on each step
    
    # Bezier curve: movement curvature
    'curve_variance_min': 0.15,  # Minimum control-point variance
    'curve_variance_max': 0.35,  # Maximum control-point variance
    
    # Speed: random variation range
    'speed_variance_min': 0.85,  # Minimum speed multiplier
    'speed_variance_max': 1.20,  # Maximum speed multiplier
    
    # Micro-pauses during movement
    'micropause_chance': 0.08,    # Micro-pause probability
    'micropause_min': 0.02,       # Minimum micro-pause duration
    'micropause_max': 0.08,       # Maximum micro-pause duration
    
    # Overshoot: go past target and correct
    'overshoot_chance': 0.20,     # Overshoot probability
    'overshoot_distance_min': 3,  # Minimum overshoot distance
    'overshoot_distance_max': 12, # Maximum overshoot distance
    
    # Movement steps
    'steps_per_second': 60,       # Steps per second (smoothness)
}


def _bezier_curve(t: float, p0: tuple, p1: tuple, p2: tuple, p3: tuple) -> tuple:
    """Computes a point on a cubic Bezier curve."""
    u = 1 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t
    
    x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    
    return (x, y)


def _generate_control_points(start: tuple, end: tuple) -> tuple:
    """Generates random control points for the Bezier curve."""
    cfg = HUMAN_MOVEMENT_CONFIG
    
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = math.sqrt(dx * dx + dy * dy)
    
    variance = random.uniform(cfg['curve_variance_min'], cfg['curve_variance_max'])
    
    mid_x = (start[0] + end[0]) / 2
    mid_y = (start[1] + end[1]) / 2
    
    if distance > 0:
        perp_x = -dy / distance
        perp_y = dx / distance
    else:
        perp_x, perp_y = 0, 0
    
    offset1 = distance * variance * random.choice([-1, 1]) * random.uniform(0.3, 1.0)
    offset2 = distance * variance * random.choice([-1, 1]) * random.uniform(0.3, 1.0)
    
    p1 = (
        start[0] + dx * 0.33 + perp_x * offset1,
        start[1] + dy * 0.33 + perp_y * offset1
    )
    p2 = (
        start[0] + dx * 0.66 + perp_x * offset2,
        start[1] + dy * 0.66 + perp_y * offset2
    )
    
    return (p1, p2)


def _apply_jitter(x: float, y: float) -> tuple:
    """Applies small random jitter offsets to a position."""
    cfg = HUMAN_MOVEMENT_CONFIG
    
    if random.random() < cfg['jitter_frequency']:
        jitter_amount = random.uniform(cfg['jitter_min'], cfg['jitter_max'])
        angle = random.uniform(0, 2 * math.pi)
        x += jitter_amount * math.cos(angle)
        y += jitter_amount * math.sin(angle)
    
    return (x, y)


def _easing_function(t: float) -> float:
    """Easing function for non-linear speed (ease-in-out)."""
    if t < 0.5:
        return 2 * t * t
    else:
        return 1 - pow(-2 * t + 2, 2) / 2


# ============================================
# MOUSE FUNCTIONS
# ============================================

def move_smooth(x: int, y: int, duration: float = 0.5, humanize: bool = True):
    """
    Moves the mouse smoothly with human-like movement.
    
    Characteristics:
    - Bezier curves for non-linear trajectories
    - Jitter to simulate hand tremor
    - Variable speed with acceleration/deceleration
    - Random micro-pauses
    - Optional overshoot and correction
    """
    if not HAS_PYAUTOGUI:
        error("pyautogui not available")
    
    cfg = HUMAN_MOVEMENT_CONFIG
    
    # Get current position
    start_pos = pyautogui.position()
    start = (start_pos.x, start_pos.y)
    end = (float(x), float(y))
    
    # Compute distance
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = math.sqrt(dx * dx + dy * dy)
    
    # If distance is very small, move directly
    if distance < 5:
        pyautogui.moveTo(x, y)
        return
    
    if not humanize:
        # Simple linear movement (legacy)
        pyautogui.moveTo(x, y, duration=duration)
        return
    
    # Apply speed variance
    speed_mult = random.uniform(cfg['speed_variance_min'], cfg['speed_variance_max'])
    actual_duration = duration * speed_mult
    
    # Generate control points for the Bezier curve
    p1, p2 = _generate_control_points(start, end)
    
    # Compute number of steps
    num_steps = max(int(actual_duration * cfg['steps_per_second']), 10)
    step_duration = actual_duration / num_steps
    
    # Execute movement
    for i in range(num_steps + 1):
        t = i / num_steps
        
        # Apply easing for non-linear speed
        t_eased = _easing_function(t)
        
        # Compute position on Bezier curve
        pos = _bezier_curve(t_eased, start, p1, p2, end)
        
        # Apply jitter
        pos = _apply_jitter(pos[0], pos[1])
        
        # Move the mouse
        pyautogui.moveTo(int(pos[0]), int(pos[1]), _pause=False)
        
        # Random micro-pause
        if random.random() < cfg['micropause_chance']:
            time.sleep(random.uniform(cfg['micropause_min'], cfg['micropause_max']))
        else:
            time.sleep(step_duration)
    
    # Overshoot and correction
    if random.random() < cfg['overshoot_chance']:
        if distance > 0:
            dir_x = dx / distance
            dir_y = dy / distance
        else:
            dir_x, dir_y = 0, 0
        
        overshoot_dist = random.uniform(cfg['overshoot_distance_min'], cfg['overshoot_distance_max'])
        overshoot_x = int(end[0] + dir_x * overshoot_dist)
        overshoot_y = int(end[1] + dir_y * overshoot_dist)
        
        pyautogui.moveTo(overshoot_x, overshoot_y, _pause=False)
        time.sleep(random.uniform(0.03, 0.08))
        
        # Correct to final target
        pyautogui.moveTo(x, y, _pause=False)
    else:
        # Ensure we end exactly at the target
        pyautogui.moveTo(x, y, _pause=False)


def do_click(x: int = None, y: int = None, button: str = 'left', duration: float = 0.5):
    """Clicks at position (smooth move if a position is provided)."""
    if not HAS_PYAUTOGUI:
        error("pyautogui not available")
    
    if x is not None and y is not None:
        move_smooth(x, y, duration)
        time.sleep(0.1)
    
    pyautogui.click(button=button)
    sound_click()  # Audio feedback


def do_double_click(x: int = None, y: int = None, duration: float = 0.5):
    """Double-click."""
    if not HAS_PYAUTOGUI:
        error("pyautogui not available")
    
    if x is not None and y is not None:
        move_smooth(x, y, duration)
        time.sleep(0.1)
    
    pyautogui.doubleClick()
    sound_double_click()  # Audio feedback


def do_drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5):
    """Drags from one point to another with human-like movement."""
    if not HAS_PYAUTOGUI:
        error("pyautogui not available")
    
    # Move to start point with human-like movement
    move_smooth(x1, y1, 0.3, humanize=True)
    time.sleep(0.1)
    
    # Press mouse button
    pyautogui.mouseDown()
    time.sleep(0.05)
    
    # Drag to destination with human-like movement
    move_smooth(x2, y2, duration, humanize=True)
    time.sleep(0.05)
    
    # Release mouse button
    pyautogui.mouseUp()


def do_scroll(amount: int, x: int = None, y: int = None):
    """Scroll (with human-like movement if position is provided)."""
    if not HAS_PYAUTOGUI:
        error("pyautogui not available")
    
    if x is not None and y is not None:
        # Move with human-like motion before scrolling
        move_smooth(x, y, 0.3, humanize=True)
        time.sleep(0.1)
    
    pyautogui.scroll(amount)
    sound_scroll()  # Audio feedback


# ============================================
# KEYBOARD FUNCTIONS
# ============================================

def remove_accents(text: str) -> str:
    """Removes accents and diacritics from text."""
    # Normalize to NFD (split base characters and diacritics)
    nfd = unicodedata.normalize('NFD', text)
    # Keep only characters that are not diacritic marks
    return ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')


def do_write(text: str, interval: float = 0.0):
    """Types text (without accents to reduce issues). Handles new lines with Shift+Enter."""
    if not HAS_PYAUTOGUI:
        error("pyautogui not available")
    
    # Remove accents before typing
    text_clean = remove_accents(text)
    
    # Audio feedback based on text length
    sound_type(len(text_clean))
    
    # If text contains line breaks, handle them
    if '\n' in text_clean:
        lines = text_clean.split('\n')
        for i, line in enumerate(lines):
            if line:  # Only type non-empty lines
                pyautogui.write(line, interval=interval)
            # If it is not the last line, use Shift+Enter for new line
            if i < len(lines) - 1:
                pyautogui.hotkey('shift', 'enter')
                time.sleep(0.1)  # Small pause between lines
    else:
        # Text without line breaks, type normally
        pyautogui.write(text_clean, interval=interval)


def do_press(key: str):
    """Presses a key."""
    if not HAS_PYAUTOGUI:
        error("pyautogui not available")
    pyautogui.press(key)
    sound_key()  # Audio feedback


def do_hotkey(*keys):
    """Key combination."""
    if not HAS_PYAUTOGUI:
        error("pyautogui not available")
    pyautogui.hotkey(*keys)
    sound_hotkey()  # Audio feedback


# ============================================
# SEQUENCES
# ============================================

def get_sequence_path(name: str) -> str:
    """Gets the sequence file path."""
    return os.path.join(SEQUENCES_DIR, f"{name}.json")


def load_sequence(name: str) -> Optional[Dict]:
    """Loads a sequence."""
    path = get_sequence_path(name)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_sequence(name: str, data: Dict):
    """Saves a sequence."""
    path = get_sequence_path(name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def execute_action(action: Dict) -> Dict:
    """Executes one action."""
    action_type = action.get('type', '')
    result = {"action": action_type, "success": True}
    
    try:
        if action_type == 'move':
            move_smooth(action['x'], action['y'], action.get('duration', 0.5))
            result['coordinates'] = {"x": action['x'], "y": action['y']}
            
        elif action_type == 'move-to':
            coords, method, info = find_element_on_screen(action['target'], action.get('confidence', 0.8))
            if not coords:
                return {"success": False, "error": f"Element not found: {action['target']}", **info}
            move_smooth(coords[0], coords[1], action.get('duration', 0.5))
            result['target'] = action['target']
            result['coordinates'] = {"x": coords[0], "y": coords[1]}
            result['method'] = method
            result['match_info'] = info
            
        elif action_type == 'click':
            do_click(action.get('x'), action.get('y'), action.get('button', 'left'))
            result['coordinates'] = {"x": action.get('x'), "y": action.get('y')}
            
        elif action_type == 'click-on':
            coords, method, info = find_element_on_screen(action['target'], action.get('confidence', 0.8))
            if not coords:
                return {"success": False, "error": f"Element not found: {action['target']}", **info}
            do_click(coords[0], coords[1], action.get('button', 'left'))
            result['target'] = action['target']
            result['coordinates'] = {"x": coords[0], "y": coords[1]}
            result['method'] = method
            result['match_info'] = info
            
        elif action_type == 'double-click':
            do_double_click(action.get('x'), action.get('y'))
            result['coordinates'] = {"x": action.get('x'), "y": action.get('y')}
            
        elif action_type == 'right-click':
            do_click(action.get('x'), action.get('y'), 'right')
            result['coordinates'] = {"x": action.get('x'), "y": action.get('y')}
            
        elif action_type == 'drag':
            do_drag(action['x1'], action['y1'], action['x2'], action['y2'])
            result['from'] = {"x": action['x1'], "y": action['y1']}
            result['to'] = {"x": action['x2'], "y": action['y2']}
            
        elif action_type == 'scroll':
            do_scroll(action['amount'], action.get('x'), action.get('y'))
            result['amount'] = action['amount']
            
        elif action_type == 'write':
            do_write(action['text'], action.get('interval', 0.0))
            result['text'] = action['text']
            
        elif action_type == 'press':
            do_press(action['key'])
            result['key'] = action['key']
            
        elif action_type == 'hotkey':
            keys = action['keys'] if isinstance(action['keys'], list) else action['keys'].split()
            do_hotkey(*keys)
            result['keys'] = keys
            
        elif action_type == 'wait':
            time.sleep(action.get('seconds', 1))
            result['seconds'] = action.get('seconds', 1)
            
        elif action_type == 'screenshot':
            if HAS_PYAUTOGUI:
                filename = action.get('filename', f"screenshot_{int(time.time())}")
                filepath = os.path.join(CAPTURES_DIR, f"{filename}.png")
                pyautogui.screenshot(filepath)
                result['filepath'] = filepath
                # Encode image to base64 for direct viewing
                with open(filepath, 'rb') as f:
                    img_data = f.read()
                result['image_base64'] = base64.b64encode(img_data).decode('utf-8')
            
        else:
            return {"success": False, "error": f"Unknown action: {action_type}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}
    
    return result


def is_element_visible(name: str, confidence: float = 0.8) -> Tuple[bool, Dict]:
    """Checks if an element is visible on screen without clicking.
    
    Returns: (visible, info)
    """
    coords, method, info = find_element_on_screen(name, confidence)
    return coords is not None, info


def execute_actions(actions: List[Dict]) -> List[Dict]:
    """Executes a list of actions with if-visible conditional support."""
    results = []
    i = 0
    while i < len(actions):
        action = actions[i]
        action_type = action.get('type', '')
        
        # Support for if-visible / if-not-visible conditionals
        if action_type in ('if-visible', 'if-not-visible'):
            target = action.get('target', '')
            then_actions = action.get('then', [])
            else_actions = action.get('else', [])
            
            # Check element visibility
            visible, info = is_element_visible(target, action.get('confidence', 0.8))
            
            # Determine which branch to execute
            if action_type == 'if-visible':
                condition_met = visible
            else:  # if-not-visible
                condition_met = not visible
            
            # Record condition evaluation result
            result = {
                "action": action_type,
                "target": target,
                "condition_met": condition_met,
                "visible": visible,
                "branch": "then" if condition_met else "else",
                "step": i + 1,
                "success": True,
                "match_info": info
            }
            results.append(result)
            
            # Execute the selected branch
            branch_actions = then_actions if condition_met else else_actions
            for branch_action in branch_actions:
                branch_result = execute_action(branch_action)
                branch_result['step'] = i + 1
                branch_result['branch'] = "then" if condition_met else "else"
                results.append(branch_result)
                # Stop if a branch action fails
                if not branch_result.get('success', True):
                    return results
        else:
            # Normal action
            result = execute_action(action)
            result['step'] = i + 1
            results.append(result)
            if not result.get('success', True):
                break
        
        i += 1
    
    return results


# ============================================
# CLI COMMANDS
# ============================================

def cmd_search(args):
    """Search elements."""
    results = search_elements(args.query)
    output({
        "action": "search",
        "query": args.query,
        "count": len(results),
        "results": [{"name": r['name'], "description": r.get('description', '')} for r in results[:10]]
    })


def cmd_find(args):
    """Find by name."""
    elem = find_element(args.name)
    if elem:
        output({
            "success": True,
            "action": "find",
            "element": {
                "name": elem['name'],
                "description": elem.get('description', ''),
                "images": elem.get('images', []),
                "tags": elem.get('tags', [])
            }
        })
    else:
        error(f"Element not found: {args.name}")


def cmd_list(args):
    """List all elements."""
    elements = load_elements()
    output({
        "action": "list",
        "count": len(elements),
        "elements": [{"name": v['name'], "description": v.get('description', '')[:50]} for v in elements.values()]
    })


def cmd_near(args):
    """Deprecated command: fixed coordinates are no longer used."""
    output({
        "action": "near",
        "success": False,
        "message": "This command is deprecated. Image detection is now used instead of fixed coordinates. Use 'find' or 'search'."
    })


def cmd_stats(args):
    """System statistics."""
    elements = load_elements()
    output({
        "action": "stats",
        "total_elements": len(elements),
        "elements_file": ELEMENTS_FILE,
        "captures_dir": CAPTURES_DIR,
        "sequences_dir": SEQUENCES_DIR
    })


def cmd_move(args):
    """Move mouse."""
    result = execute_action({"type": "move", "x": args.x, "y": args.y, "duration": args.duration})
    output(result)


def cmd_move_to(args):
    """Move to element."""
    result = execute_action({"type": "move-to", "target": args.name, "duration": args.duration})
    output(result)


def cmd_click(args):
    """Click at coordinates."""
    result = execute_action({"type": "click", "x": args.x, "y": args.y})
    output(result)


def cmd_click_on(args):
    """Click on element."""
    result = execute_action({"type": "click-on", "target": args.name})
    output(result)


def cmd_double_click(args):
    """Double-click."""
    result = execute_action({"type": "double-click", "x": args.x, "y": args.y})
    output(result)


def cmd_right_click(args):
    """Right-click."""
    result = execute_action({"type": "right-click", "x": args.x, "y": args.y})
    output(result)


def cmd_drag(args):
    """Drag."""
    result = execute_action({"type": "drag", "x1": args.x1, "y1": args.y1, 
                            "x2": args.x2, "y2": args.y2})
    output(result)


def cmd_scroll(args):
    """Scroll."""
    x, y = None, None
    if args.at:
        x, y = map(int, args.at.split(','))
    result = execute_action({"type": "scroll", "amount": args.amount, "x": x, "y": y})
    output(result)


def cmd_write(args):
    """Escribir texto."""
    result = execute_action({"type": "write", "text": args.text})
    output(result)


def cmd_press(args):
    """Press key."""
    result = execute_action({"type": "press", "key": args.key})
    output(result)


def cmd_hotkey(args):
    """Hotkey."""
    result = execute_action({"type": "hotkey", "keys": args.keys})
    output(result)


def cmd_mouse_pos(args):
    """Current mouse position."""
    if HAS_PYAUTOGUI:
        pos = pyautogui.position()
        output({"action": "mouse-pos", "x": pos.x, "y": pos.y})
    else:
        error("pyautogui not available")


def cmd_wait(args):
    """Wait."""
    result = execute_action({"type": "wait", "seconds": args.seconds})
    output(result)


def cmd_screenshot(args):
    """Screenshot."""
    result = execute_action({"type": "screenshot", "filename": args.filename})
    output(result)


def cmd_region_capture(args):
    """Interactive mouse region capture."""
    import subprocess
    
    script_candidates = [
        os.path.join(os.path.dirname(SKILL_DIR), "region-capture", "region_capture.py"),
        os.path.join(os.path.dirname(SKILL_DIR), "macro-capture", "region_capture.py"),
        os.path.join(SKILL_DIR, "region_capture.py"),  # backward compatibility
    ]
    script_path = next((p for p in script_candidates if os.path.exists(p)), None)
    if not script_path:
        error("region_capture script not found (region-capture).")
        return
    
    try:
        # Run the region capture script.
        # By default it saves to the skill's data/local/.
        result = subprocess.run(
            [sys.executable, script_path, "--data-dir", DATA_DIR],
            capture_output=False
        )
        output({
            "success": result.returncode == 0,
            "action": "region-capture",
            "message": "Region capture completed" if result.returncode == 0 else "Region capture closed",
            "data_dir": DATA_DIR
        })
    except Exception as e:
        error(f"Error running region capture: {e}")


def cmd_run(args):
    """Execute actions from JSON."""
    try:
        data = json.loads(args.json_str)
        actions = data.get('actions', [data] if 'type' in data else [])
        results = execute_actions(actions)
        output({
            "action": "run",
            "total": len(actions),
            "completed": len([r for r in results if r.get('success')]),
            "results": results
        })
    except json.JSONDecodeError as e:
        error(f"Invalid JSON: {e}")


def cmd_seq_create(args):
    """Create sequence."""
    seq = {
        "name": args.name,
        "display_name": getattr(args, 'display_name', None) or args.name,
        "description": args.description or "",
        "created": datetime.now().isoformat(),
        "actions": []
    }
    save_sequence(args.name, seq)
    output({
        "action": "seq-create", 
        "name": args.name, 
        "display_name": seq['display_name'],
        "description": seq['description'],
        "success": True
    })


def parse_simple_action(action_str: str) -> Dict:
    """Parses a simple action from string."""
    parts = action_str.split(maxsplit=1)
    action_type = parts[0]
    action = {"type": action_type}
    
    if len(parts) > 1:
        rest = parts[1]
        
        if action_type in ('click-on', 'move-to'):
            action['target'] = rest
        elif action_type == 'write':
            action['text'] = rest.strip("'\"")
        elif action_type == 'press':
            action['key'] = rest
        elif action_type == 'hotkey':
            action['keys'] = rest.split()
        elif action_type == 'wait':
            action['seconds'] = float(rest)
        elif action_type in ('click', 'double-click', 'right-click', 'move'):
            coords = rest.split()
            action['x'] = int(coords[0])
            action['y'] = int(coords[1])
        elif action_type == 'scroll':
            action['amount'] = int(rest)
        elif action_type == 'drag':
            coords = rest.split()
            action['x1'], action['y1'] = int(coords[0]), int(coords[1])
            action['x2'], action['y2'] = int(coords[2]), int(coords[3])
    
    return action


def cmd_seq_add(args):
    """Add action to sequence."""
    seq = load_sequence(args.name)
    if not seq:
        error(f"Sequence not found: {args.name}")
    
    # Parse action from string
    parts = args.action.split(maxsplit=1)
    action_type = parts[0]
    
    # Support for if-visible / if-not-visible
    if action_type in ('if-visible', 'if-not-visible'):
        if len(parts) < 2:
            error(f"{action_type} requires a target")
        
        target = parts[1]
        then_actions = []
        else_actions = []
        
        # Parse --then and --else from args
        if hasattr(args, 'then_actions') and args.then_actions:
            for then_str in args.then_actions:
                then_actions.append(parse_simple_action(then_str))
        
        if hasattr(args, 'else_actions') and args.else_actions:
            for else_str in args.else_actions:
                else_actions.append(parse_simple_action(else_str))
        
        action = {
            "type": action_type,
            "target": target,
            "then": then_actions,
            "else": else_actions
        }
    else:
        # Regular action
        action = parse_simple_action(args.action)
    
    seq['actions'].append(action)
    seq['updated'] = datetime.now().isoformat()
    save_sequence(args.name, seq)
    
    output({
        "action": "seq-add",
        "sequence": args.name,
        "added": action,
        "total_actions": len(seq['actions'])
    })


def cmd_seq_show(args):
    """Show sequence."""
    seq = load_sequence(args.name)
    if not seq:
        error(f"Sequence not found: {args.name}")
    output({"action": "seq-show", "sequence": seq})


def cmd_seq_run(args):
    """Run sequence."""
    seq = load_sequence(args.name)
    if not seq:
        error(f"Sequence not found: {args.name}")
    
    results = execute_actions(seq['actions'])
    output({
        "action": "seq-run",
        "sequence": args.name,
        "total": len(seq['actions']),
        "completed": len([r for r in results if r.get('success')]),
        "results": results
    })


def cmd_seq_list(args):
    """List sequences with complete information."""
    sequences = []
    if os.path.exists(SEQUENCES_DIR):
        for f in os.listdir(SEQUENCES_DIR):
            if f.endswith('.json'):
                seq = load_sequence(f[:-5])
                if seq:
                    # Action summary
                    action_summary = []
                    for act in seq.get('actions', [])[:5]:  # First 5 actions
                        if act['type'] == 'click-on':
                            action_summary.append(f"click:{act.get('target', '?')}")
                        elif act['type'] == 'wait':
                            action_summary.append(f"wait:{act.get('seconds', 0)}s")
                        elif act['type'] == 'write':
                            action_summary.append(f"write:{act.get('text', '')[:10]}...")
                        elif act['type'] == 'press':
                            action_summary.append(f"press:{act.get('key', '?')}")
                        elif act['type'] == 'hotkey':
                            action_summary.append(f"hotkey:{'+'.join(act.get('keys', []))}")
                        else:
                            action_summary.append(act['type'])
                    
                    if len(seq.get('actions', [])) > 5:
                        action_summary.append(f"...+{len(seq['actions'])-5} more")
                    
                    sequences.append({
                        "name": seq['name'],
                        "display_name": seq.get('display_name', seq['name']),
                        "description": seq.get('description', ''),
                        "actions_count": len(seq.get('actions', [])),
                        "actions_preview": action_summary,
                        "created": seq.get('created', ''),
                        "updated": seq.get('updated', '')
                    })
    
    output({
        "action": "seq-list", 
        "count": len(sequences), 
        "sequences": sequences,
        "hint": "Use 'seq-show <name>' for details or 'seq-describe <name> --display-name <name> --description <desc>' to update"
    })


def cmd_seq_delete(args):
    """Delete sequence."""
    path = get_sequence_path(args.name)
    if os.path.exists(path):
        os.remove(path)
        output({"action": "seq-delete", "name": args.name, "success": True})
    else:
        error(f"Sequence not found: {args.name}")


def cmd_seq_describe(args):
    """Update sequence display name and description."""
    seq = load_sequence(args.name)
    if not seq:
        error(f"Sequence not found: {args.name}")
    
    updated = False
    if args.display_name:
        seq['display_name'] = args.display_name
        updated = True
    if args.description:
        seq['description'] = args.description
        updated = True
    
    if updated:
        seq['updated'] = datetime.now().isoformat()
        save_sequence(args.name, seq)
    
    output({
        "action": "seq-describe",
        "name": args.name,
        "display_name": seq.get('display_name', seq['name']),
        "description": seq.get('description', ''),
        "success": True
    })


# ============================================
# ELEMENT COMMANDS (JSON)
# ============================================

def cmd_elem_add(args):
    """Add or update an element."""
    tags = args.tags.split(',') if args.tags else []
    elem = add_element(args.name, args.description or "", tags=tags)
    output({
        "action": "elem-add",
        "success": True,
        "element": elem
    })


def cmd_elem_add_image(args):
    """Add an image to an element."""
    elem = add_image_to_element(args.name, args.image)
    output({
        "action": "elem-add-image",
        "success": True,
        "element": elem
    })


def cmd_elem_show(args):
    """Show an element."""
    elem = get_element(args.name)
    if not elem:
        error(f"Element not found: {args.name}")
    output({
        "action": "elem-show",
        "success": True,
        "element": elem
    })


def cmd_elem_list(args):
    """List all elements."""
    elements = load_elements()
    output({
        "action": "elem-list",
        "count": len(elements),
        "elements": list(elements.values())
    })


def cmd_elem_delete(args):
    """Delete an element."""
    elements = load_elements()
    name_key = args.name.lower().replace(' ', '_')
    
    if name_key not in elements:
        error(f"Element not found: {args.name}")
    
    del elements[name_key]
    save_elements(elements)
    
    output({
        "action": "elem-delete",
        "success": True,
        "name": args.name
    })


# ============================================
# SOUND COMMANDS
# ============================================

def cmd_sounds_on(args):
    """Enable sounds."""
    result = enable_sounds()
    output({
        "action": "sounds-on",
        "success": True,
        "message": result,
        "status": get_sound_status()
    })


def cmd_sounds_off(args):
    """Disable sounds."""
    result = disable_sounds()
    output({
        "action": "sounds-off",
        "success": True,
        "message": result,
        "status": get_sound_status()
    })


def cmd_sounds_status(args):
    """Sound status."""
    status = get_sound_status()
    output({
        "action": "sounds-status",
        "success": True,
        **status
    })


def cmd_sounds_volume(args):
    """Adjust volume."""
    result = set_volume(args.volume)
    output({
        "action": "sounds-volume",
        "success": True,
        "message": result,
        "status": get_sound_status()
    })


def main():
    parser = argparse.ArgumentParser(description="Macro Agent - UI control for AI agents")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Search
    p = subparsers.add_parser('search', help='Search elements')
    p.add_argument('query', help='Text to search')
    p.set_defaults(func=cmd_search)
    
    p = subparsers.add_parser('find', help='Find by name')
    p.add_argument('name', help='Element name')
    p.set_defaults(func=cmd_find)
    
    p = subparsers.add_parser('list', help='List elements')
    p.set_defaults(func=cmd_list)
    
    p = subparsers.add_parser('near', help='Find near coordinates')
    p.add_argument('coords', help='X,Y coordinates')
    p.add_argument('--radius', type=int, default=100, help='Search radius')
    p.set_defaults(func=cmd_near)
    
    p = subparsers.add_parser('stats', help='Statistics')
    p.set_defaults(func=cmd_stats)
    
    # Mouse
    p = subparsers.add_parser('move', help='Move mouse')
    p.add_argument('x', type=int)
    p.add_argument('y', type=int)
    p.add_argument('--duration', type=float, default=0.5)
    p.set_defaults(func=cmd_move)
    
    p = subparsers.add_parser('move-to', help='Move to element')
    p.add_argument('name', help='Element name')
    p.add_argument('--duration', type=float, default=0.5)
    p.set_defaults(func=cmd_move_to)
    
    p = subparsers.add_parser('click', help='Click at coordinates')
    p.add_argument('x', type=int)
    p.add_argument('y', type=int)
    p.set_defaults(func=cmd_click)
    
    p = subparsers.add_parser('click-on', help='Click on element')
    p.add_argument('name', help='Element name')
    p.set_defaults(func=cmd_click_on)
    
    p = subparsers.add_parser('double-click', help='Double-click')
    p.add_argument('x', type=int)
    p.add_argument('y', type=int)
    p.set_defaults(func=cmd_double_click)
    
    p = subparsers.add_parser('right-click', help='Right-click')
    p.add_argument('x', type=int)
    p.add_argument('y', type=int)
    p.set_defaults(func=cmd_right_click)
    
    p = subparsers.add_parser('drag', help='Drag')
    p.add_argument('x1', type=int)
    p.add_argument('y1', type=int)
    p.add_argument('x2', type=int)
    p.add_argument('y2', type=int)
    p.set_defaults(func=cmd_drag)
    
    p = subparsers.add_parser('scroll', help='Scroll')
    p.add_argument('amount', type=int, help='Amount (negative=down)')
    p.add_argument('--at', help='X,Y coordinates')
    p.set_defaults(func=cmd_scroll)
    
    # Keyboard
    p = subparsers.add_parser('write', help='Write text')
    p.add_argument('text', help='Text to write')
    p.set_defaults(func=cmd_write)
    
    p = subparsers.add_parser('press', help='Press key')
    p.add_argument('key', help='Key')
    p.set_defaults(func=cmd_press)
    
    p = subparsers.add_parser('hotkey', help='Key combination')
    p.add_argument('keys', nargs='+', help='Keys')
    p.set_defaults(func=cmd_hotkey)
    
    # Utilidades
    p = subparsers.add_parser('mouse-pos', help='Mouse position')
    p.set_defaults(func=cmd_mouse_pos)
    
    p = subparsers.add_parser('wait', help='Wait')
    p.add_argument('seconds', type=float)
    p.set_defaults(func=cmd_wait)
    
    p = subparsers.add_parser('screenshot', help='Screenshot')
    p.add_argument('filename', help='Filename')
    p.set_defaults(func=cmd_screenshot)
    
    p = subparsers.add_parser('region-capture', help='Interactive region capture with mouse')
    p.set_defaults(func=cmd_region_capture)
    
    # Execute JSON
    p = subparsers.add_parser('run', help='Execute actions from JSON')
    p.add_argument('json_str', help='JSON with actions')
    p.set_defaults(func=cmd_run)
    
    # Sequences
    p = subparsers.add_parser('seq-create', help='Create sequence')
    p.add_argument('name', help='Internal sequence name (no spaces)')
    p.add_argument('--display-name', '-n', dest='display_name', help='Friendly display name')
    p.add_argument('--description', '-d', help='Description of what the sequence does')
    p.set_defaults(func=cmd_seq_create)
    
    p = subparsers.add_parser('seq-add', help='Add action to sequence')
    p.add_argument('name', help='Sequence name')
    p.add_argument('action', help='Action (e.g. "click-on save_button" or "if-visible element")')
    p.add_argument('--then', dest='then_actions', action='append', help='Actions if condition is true (for if-visible)')
    p.add_argument('--else', dest='else_actions', action='append', help='Actions if condition is false (for if-visible)')
    p.set_defaults(func=cmd_seq_add)
    
    p = subparsers.add_parser('seq-show', help='Show sequence')
    p.add_argument('name', help='Sequence name')
    p.set_defaults(func=cmd_seq_show)
    
    p = subparsers.add_parser('seq-run', help='Run sequence')
    p.add_argument('name', help='Sequence name')
    p.set_defaults(func=cmd_seq_run)
    
    p = subparsers.add_parser('seq-list', help='List sequences')
    p.set_defaults(func=cmd_seq_list)
    
    p = subparsers.add_parser('seq-delete', help='Delete sequence')
    p.add_argument('name', help='Sequence name')
    p.set_defaults(func=cmd_seq_delete)
    
    p = subparsers.add_parser('seq-describe', help='Update sequence name/description')
    p.add_argument('name', help='Internal sequence name')
    p.add_argument('--display-name', '-n', dest='display_name', help='New display name')
    p.add_argument('--description', '-d', help='New description')
    p.set_defaults(func=cmd_seq_describe)
    
    # Elements (JSON)
    p = subparsers.add_parser('elem-add', help='Add/update element')
    p.add_argument('name', help='Element name')
    p.add_argument('--description', '-d', help='Description')
    p.add_argument('--tags', '-t', help='Comma-separated tags')
    p.set_defaults(func=cmd_elem_add)
    
    p = subparsers.add_parser('elem-add-image', help='Add image to element')
    p.add_argument('name', help='Element name')
    p.add_argument('image', help='Image filename')
    p.set_defaults(func=cmd_elem_add_image)
    
    p = subparsers.add_parser('elem-show', help='Show element')
    p.add_argument('name', help='Element name')
    p.set_defaults(func=cmd_elem_show)
    
    p = subparsers.add_parser('elem-list', help='List elements')
    p.set_defaults(func=cmd_elem_list)
    
    p = subparsers.add_parser('elem-delete', help='Delete element')
    p.add_argument('name', help='Element name')
    p.set_defaults(func=cmd_elem_delete)
    
    # Sounds
    p = subparsers.add_parser('sounds-on', help='Enable sounds')
    p.set_defaults(func=cmd_sounds_on)
    
    p = subparsers.add_parser('sounds-off', help='Disable sounds')
    p.set_defaults(func=cmd_sounds_off)
    
    p = subparsers.add_parser('sounds-status', help='Sound status')
    p.set_defaults(func=cmd_sounds_status)
    
    p = subparsers.add_parser('sounds-volume', help='Adjust volume')
    p.add_argument('volume', type=float, help='Volume 0.0-1.0')
    p.set_defaults(func=cmd_sounds_volume)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(0)
    
    args.func(args)


if __name__ == '__main__':
    main()
