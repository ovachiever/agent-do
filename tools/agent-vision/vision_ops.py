#!/usr/bin/env python3
"""
agent-vision - AI-first visual perception.
Capture, detect, describe, react.
"""

import json
import os
import sys
import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple
import tempfile

import cv2
import numpy as np
from PIL import Image

# Optional imports - loaded on demand
def get_yolo():
    from ultralytics import YOLO
    return YOLO

def get_tesseract():
    import pytesseract
    return pytesseract

def get_face_recognition():
    import face_recognition
    return face_recognition


class VisionSession:
    """Manages video source and session state."""
    
    CONFIG_DIR = Path.home() / '.agent-vision'
    SESSION_FILE = CONFIG_DIR / 'session.json'
    FRAME_DIR = CONFIG_DIR / 'frames'
    KNOWN_FACES_DIR = CONFIG_DIR / 'known_faces'
    
    def __init__(self):
        self.CONFIG_DIR.mkdir(exist_ok=True)
        self.FRAME_DIR.mkdir(exist_ok=True)
        self.KNOWN_FACES_DIR.mkdir(exist_ok=True)
        
        self.capture = None
        self.source_type = None
        self.source_path = None
        self.frame_count = 0
        self.last_frame = None
        self.last_frame_path = None
        self.recording = False
        self.video_writer = None
        
        # YOLO model cache
        self._yolo_model = None
        self._yolo_model_name = None
        
        # Known faces cache
        self._known_faces = {}
        self._known_encodings = []
        self._known_names = []
        
        self._load_session()
    
    def _load_session(self):
        """Load session state from file."""
        if self.SESSION_FILE.exists():
            try:
                data = json.loads(self.SESSION_FILE.read_text())
                self.source_type = data.get('source_type')
                self.source_path = data.get('source_path')
                self.frame_count = data.get('frame_count', 0)
                self.last_frame_path = data.get('last_frame_path')
            except:
                pass
    
    def _save_session(self):
        """Save session state to file."""
        data = {
            'source_type': self.source_type,
            'source_path': self.source_path,
            'frame_count': self.frame_count,
            'last_frame_path': self.last_frame_path,
            'connected_at': datetime.now().isoformat(),
        }
        self.SESSION_FILE.write_text(json.dumps(data, indent=2))
    
    def _get_capture(self):
        """Get or create video capture."""
        if self.capture is not None:
            return self.capture
        
        if self.source_type == 'webcam':
            index = int(self.source_path) if self.source_path else 0
            self.capture = cv2.VideoCapture(index)
            if not self.capture.isOpened():
                self.capture = None
                return None
        
        elif self.source_type == 'file':
            if not Path(self.source_path).exists():
                return None
            self.capture = cv2.VideoCapture(self.source_path)
            if not self.capture.isOpened():
                self.capture = None
                return None
        
        elif self.source_type == 'image':
            # For images, we don't use VideoCapture
            pass
        
        return self.capture
    
    def _capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single frame from the current source."""
        if self.source_type == 'image':
            if self.source_path and Path(self.source_path).exists():
                return cv2.imread(self.source_path)
            return None
        
        elif self.source_type == 'screen':
            return self._capture_screen()
        
        elif self.source_type == 'window':
            return self._capture_window(self.source_path)
        
        elif self.source_type == 'ios':
            return self._capture_ios()
        
        else:
            cap = self._get_capture()
            if cap is None:
                return None
            ret, frame = cap.read()
            if not ret:
                return None
            return frame
    
    def _capture_screen(self, display: int = 0) -> Optional[np.ndarray]:
        """Capture screen on macOS."""
        if sys.platform != 'darwin':
            return None
        
        tmp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        tmp_path = tmp_file.name
        tmp_file.close()
        
        try:
            # Try without -D flag first (works better)
            result = subprocess.run(['screencapture', '-x', tmp_path], 
                         capture_output=True)
            if result.returncode != 0:
                return None
            frame = cv2.imread(tmp_path)
            return frame
        except Exception:
            return None
        finally:
            if Path(tmp_path).exists():
                Path(tmp_path).unlink()
    
    def _capture_window(self, window_name: str) -> Optional[np.ndarray]:
        """Capture specific window on macOS."""
        if sys.platform != 'darwin':
            return None
        
        # Get window ID using AppleScript
        script = f'''
        tell application "System Events"
            set windowId to id of first window of (first process whose name is "{window_name}")
            return windowId
        end tell
        '''
        
        try:
            result = subprocess.run(['osascript', '-e', script], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                return None
            
            window_id = result.stdout.strip()
            
            tmp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            tmp_path = tmp_file.name
            tmp_file.close()
            
            subprocess.run(['screencapture', '-x', '-l', window_id, tmp_path],
                         capture_output=True, check=True)
            frame = cv2.imread(tmp_path)
            return frame
        except:
            return None
        finally:
            if 'tmp_path' in locals() and Path(tmp_path).exists():
                Path(tmp_path).unlink()
    
    def _capture_ios(self) -> Optional[np.ndarray]:
        """Capture iOS simulator via agent-ios."""
        tmp_path = '/tmp/ios_capture.png'
        
        try:
            # Use agent-ios screenshot command
            agent_ios = Path(__file__).parent.parent / 'agent-ios'
            if not agent_ios.exists():
                return None
            
            result = subprocess.run([str(agent_ios), 'screenshot', tmp_path],
                                  capture_output=True, text=True)
            if result.returncode != 0:
                return None
            
            frame = cv2.imread(tmp_path)
            return frame
        except:
            return None
    
    def _get_yolo_model(self, model_name: str = 'yolov8n'):
        """Get or load YOLO model."""
        if self._yolo_model is not None and self._yolo_model_name == model_name:
            return self._yolo_model
        
        try:
            YOLO = get_yolo()
            self._yolo_model = YOLO(f'{model_name}.pt')
            self._yolo_model_name = model_name
            return self._yolo_model
        except ImportError:
            return None
        except Exception as e:
            return None
    
    def _load_known_faces(self):
        """Load known faces for recognition."""
        if self._known_faces:
            return
        
        try:
            face_recognition = get_face_recognition()
            
            for face_file in self.KNOWN_FACES_DIR.glob('*.jpg'):
                name = face_file.stem
                image = face_recognition.load_image_file(str(face_file))
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    self._known_faces[name] = encodings[0]
                    self._known_encodings.append(encodings[0])
                    self._known_names.append(name)
        except ImportError:
            pass
    
    # ==================== Commands ====================
    
    def cmd_source(self, source_type: str, source_path: str = None) -> dict:
        """Set video source."""
        # Close existing capture
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        
        self.source_type = source_type
        self.source_path = source_path
        self.frame_count = 0
        
        # Validate source
        if source_type == 'webcam':
            index = int(source_path) if source_path else 0
            cap = cv2.VideoCapture(index)
            if not cap.isOpened():
                cap.release()
                return {
                    "ok": False,
                    "error": f"Webcam {index} not available",
                    "suggestion": "Check if webcam is connected and not in use by another app",
                    "exit_code": 2
                }
            
            # Get properties
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            cap.release()
            
            self._save_session()
            return {
                "ok": True,
                "source": f"webcam:{index}",
                "resolution": [width, height],
                "fps": fps
            }
        
        elif source_type == 'screen':
            self.source_path = source_path or '0'
            self._save_session()
            return {
                "ok": True,
                "source": f"screen:{self.source_path}",
                "note": "Screen capture ready"
            }
        
        elif source_type == 'window':
            if not source_path:
                return {
                    "ok": False,
                    "error": "Window name required",
                    "exit_code": 1
                }
            self._save_session()
            return {
                "ok": True,
                "source": f"window:{source_path}"
            }
        
        elif source_type == 'file':
            if not source_path or not Path(source_path).exists():
                return {
                    "ok": False,
                    "error": f"File not found: {source_path}",
                    "exit_code": 1
                }
            
            cap = cv2.VideoCapture(source_path)
            if not cap.isOpened():
                return {
                    "ok": False,
                    "error": f"Cannot open video file: {source_path}",
                    "exit_code": 1
                }
            
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0
            cap.release()
            
            self._save_session()
            return {
                "ok": True,
                "source": f"file:{source_path}",
                "resolution": [width, height],
                "fps": fps,
                "frames": frame_count,
                "duration_seconds": round(duration, 2)
            }
        
        elif source_type == 'image':
            if not source_path or not Path(source_path).exists():
                return {
                    "ok": False,
                    "error": f"Image not found: {source_path}",
                    "exit_code": 1
                }
            
            img = cv2.imread(source_path)
            if img is None:
                return {
                    "ok": False,
                    "error": f"Cannot read image: {source_path}",
                    "exit_code": 1
                }
            
            height, width = img.shape[:2]
            self._save_session()
            return {
                "ok": True,
                "source": f"image:{source_path}",
                "resolution": [width, height]
            }
        
        elif source_type == 'ios':
            self._save_session()
            return {
                "ok": True,
                "source": "ios:simulator",
                "note": "iOS simulator capture via agent-ios"
            }
        
        elif source_type == 'rtsp':
            cap = cv2.VideoCapture(source_path)
            if not cap.isOpened():
                return {
                    "ok": False,
                    "error": f"Cannot connect to RTSP stream: {source_path}",
                    "exit_code": 1
                }
            cap.release()
            
            self._save_session()
            return {
                "ok": True,
                "source": f"rtsp:{source_path}"
            }
        
        else:
            return {
                "ok": False,
                "error": f"Unknown source type: {source_type}",
                "exit_code": 1
            }
    
    def cmd_status(self) -> dict:
        """Show current source status."""
        if not self.source_type:
            return {
                "ok": True,
                "connected": False,
                "message": "No source configured. Use 'agent-vision source webcam' to start."
            }
        
        return {
            "ok": True,
            "connected": True,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "frame_count": self.frame_count,
            "last_frame": self.last_frame_path
        }
    
    def cmd_disconnect(self) -> dict:
        """Disconnect from source."""
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        
        self.source_type = None
        self.source_path = None
        self._save_session()
        
        return {"ok": True, "message": "Disconnected"}
    
    def cmd_snapshot(self, output: str = None, analyze: bool = False,
                     yolo: bool = False, ocr: bool = False, 
                     faces: bool = False, motion: bool = False) -> dict:
        """Capture a frame and optionally analyze it."""
        if not self.source_type:
            return {
                "ok": False,
                "error": "No source configured",
                "suggestion": "Use 'agent-vision source webcam' first",
                "exit_code": 1
            }
        
        frame = self._capture_frame()
        if frame is None:
            return {
                "ok": False,
                "error": "Failed to capture frame",
                "exit_code": 3
            }
        
        self.frame_count += 1
        
        # Save frame
        if output:
            frame_path = output
        else:
            frame_path = str(self.FRAME_DIR / f'frame_{self.frame_count:04d}.png')
        
        cv2.imwrite(frame_path, frame)
        self.last_frame_path = frame_path
        self.last_frame = frame.copy()
        self._save_session()
        
        height, width = frame.shape[:2]
        
        result = {
            "ok": True,
            "source": f"{self.source_type}:{self.source_path or ''}",
            "timestamp": datetime.now().isoformat(),
            "frame": {
                "path": frame_path,
                "width": width,
                "height": height,
                "number": self.frame_count
            }
        }
        
        # Analysis
        analysis = {}
        
        if yolo:
            detections = self._detect_yolo(frame)
            if detections:
                analysis["detections"] = detections
        
        if ocr:
            text = self._extract_text(frame)
            if text:
                analysis["text"] = text
        
        if faces:
            face_data = self._detect_faces(frame)
            if face_data:
                analysis["faces"] = face_data
        
        if motion and self.last_frame is not None:
            motion_score = self._detect_motion(frame)
            analysis["motion_score"] = motion_score
        
        if analyze:
            description = self._describe_frame(frame)
            if description:
                analysis["description"] = description
        
        if analysis:
            result["analysis"] = analysis
        
        return result
    
    def cmd_detect(self, model: str = 'yolov8n', classes: str = None,
                   confidence: float = 0.5, annotate: bool = False) -> dict:
        """Run object detection on current frame."""
        if not self.source_type:
            return {"ok": False, "error": "No source configured", "exit_code": 1}
        
        frame = self._capture_frame()
        if frame is None:
            return {"ok": False, "error": "Failed to capture frame", "exit_code": 3}
        
        yolo_model = self._get_yolo_model(model)
        if yolo_model is None:
            return {
                "ok": False,
                "error": "YOLO not available. Install with: pip install ultralytics",
                "exit_code": 4
            }
        
        # Filter classes if specified
        filter_classes = classes.split(',') if classes else None
        
        try:
            results = yolo_model(frame, conf=confidence, verbose=False)
            
            detections = []
            counts = {}
            
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    cls_id = int(box.cls[0])
                    cls_name = yolo_model.names[cls_id]
                    
                    if filter_classes and cls_name not in filter_classes:
                        continue
                    
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    
                    detections.append({
                        "class": cls_name,
                        "confidence": round(conf, 3),
                        "box": [int(x1), int(y1), int(x2-x1), int(y2-y1)],
                        "center": [int((x1+x2)/2), int((y1+y2)/2)]
                    })
                    
                    counts[cls_name] = counts.get(cls_name, 0) + 1
            
            result = {
                "ok": True,
                "model": model,
                "detections": detections,
                "counts": counts
            }
            
            if annotate:
                annotated = results[0].plot()
                annotated_path = str(self.FRAME_DIR / f'detected_{self.frame_count:04d}.png')
                cv2.imwrite(annotated_path, annotated)
                result["annotated_frame"] = annotated_path
            
            return result
        
        except Exception as e:
            return {"ok": False, "error": str(e), "exit_code": 3}
    
    def cmd_count(self, class_name: str = None, model: str = 'yolov8n') -> dict:
        """Count objects in frame."""
        result = self.cmd_detect(model=model)
        if not result.get("ok"):
            return result
        
        counts = result.get("counts", {})
        
        if class_name:
            count = counts.get(class_name, 0)
            return {
                "ok": True,
                "class": class_name,
                "count": count
            }
        
        total = sum(counts.values())
        return {
            "ok": True,
            "counts": counts,
            "total": total
        }
    
    def cmd_ocr(self, region: str = None, lang: str = 'eng', find: str = None) -> dict:
        """Extract text from frame."""
        if not self.source_type:
            return {"ok": False, "error": "No source configured", "exit_code": 1}
        
        frame = self._capture_frame()
        if frame is None:
            return {"ok": False, "error": "Failed to capture frame", "exit_code": 3}
        
        # Crop to region if specified
        if region:
            try:
                x, y, w, h = map(int, region.split(','))
                frame = frame[y:y+h, x:x+w]
            except:
                return {"ok": False, "error": "Invalid region format. Use: x,y,w,h", "exit_code": 1}
        
        text = self._extract_text(frame, lang)
        
        if find:
            # Search for specific text
            lines = text.split('\n')
            found_lines = [l for l in lines if find.lower() in l.lower()]
            return {
                "ok": True,
                "search": find,
                "found": len(found_lines) > 0,
                "matches": found_lines
            }
        
        return {
            "ok": True,
            "text": text,
            "lines": [l for l in text.split('\n') if l.strip()]
        }
    
    def cmd_faces(self, identify: bool = False, emotions: bool = False) -> dict:
        """Detect faces in frame."""
        if not self.source_type:
            return {"ok": False, "error": "No source configured", "exit_code": 1}
        
        frame = self._capture_frame()
        if frame is None:
            return {"ok": False, "error": "Failed to capture frame", "exit_code": 3}
        
        faces = self._detect_faces(frame, identify=identify)
        
        return {
            "ok": True,
            "face_count": len(faces),
            "faces": faces
        }
    
    def cmd_face_learn(self, name: str, image_path: str) -> dict:
        """Learn a face for recognition."""
        try:
            face_recognition = get_face_recognition()
        except ImportError:
            return {
                "ok": False,
                "error": "face_recognition not installed. Run: pip install face_recognition",
                "exit_code": 4
            }
        
        if not Path(image_path).exists():
            return {"ok": False, "error": f"Image not found: {image_path}", "exit_code": 1}
        
        image = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(image)
        
        if not encodings:
            return {"ok": False, "error": "No face found in image", "exit_code": 3}
        
        # Save face image
        dest_path = self.KNOWN_FACES_DIR / f'{name}.jpg'
        img = Image.open(image_path)
        img.save(dest_path, 'JPEG')
        
        # Reload known faces
        self._known_faces = {}
        self._known_encodings = []
        self._known_names = []
        self._load_known_faces()
        
        return {
            "ok": True,
            "message": f"Learned face: {name}",
            "known_faces": list(self._known_faces.keys())
        }
    
    def cmd_face_list(self) -> dict:
        """List known faces."""
        self._load_known_faces()
        return {
            "ok": True,
            "known_faces": list(self._known_faces.keys()),
            "count": len(self._known_faces)
        }
    
    def cmd_describe(self, detail: str = 'medium', focus: str = None) -> dict:
        """Describe frame using vision LLM."""
        if not self.source_type:
            return {"ok": False, "error": "No source configured", "exit_code": 1}
        
        frame = self._capture_frame()
        if frame is None:
            return {"ok": False, "error": "Failed to capture frame", "exit_code": 3}
        
        # Save frame temporarily
        tmp_path = '/tmp/vision_describe.png'
        cv2.imwrite(tmp_path, frame)
        
        description = self._describe_frame(frame, detail=detail, focus=focus)
        
        if description:
            return {
                "ok": True,
                "description": description
            }
        else:
            return {
                "ok": False,
                "error": "Vision LLM not available. Set OPENAI_API_KEY or ANTHROPIC_API_KEY",
                "exit_code": 6
            }
    
    def cmd_ask(self, question: str) -> dict:
        """Ask a question about the current frame."""
        if not self.source_type:
            return {"ok": False, "error": "No source configured", "exit_code": 1}
        
        frame = self._capture_frame()
        if frame is None:
            return {"ok": False, "error": "Failed to capture frame", "exit_code": 3}
        
        answer = self._ask_about_frame(frame, question)
        
        if answer:
            return {
                "ok": True,
                "question": question,
                "answer": answer
            }
        else:
            return {
                "ok": False,
                "error": "Vision LLM not available",
                "exit_code": 6
            }
    
    def cmd_watch(self, target: str = None, timeout: int = 60,
                  motion: bool = False, face: str = None, 
                  text: str = None, enter: bool = False, exit_frame: bool = False) -> dict:
        """Watch for event detection."""
        if not self.source_type:
            return {"ok": False, "error": "No source configured", "exit_code": 1}
        
        start_time = time.time()
        last_detections = set()
        
        while True:
            elapsed = time.time() - start_time
            if timeout > 0 and elapsed > timeout:
                return {
                    "ok": False,
                    "error": "Timeout waiting for event",
                    "waited_seconds": round(elapsed, 1),
                    "exit_code": 5
                }
            
            frame = self._capture_frame()
            if frame is None:
                time.sleep(0.5)
                continue
            
            # Check for motion
            if motion:
                if self.last_frame is not None:
                    motion_score = self._detect_motion(frame)
                    motion_threshold = 0.1 if motion is True else float(motion)
                    if motion_score > motion_threshold:
                        frame_path = str(self.FRAME_DIR / f'motion_{int(time.time())}.png')
                        cv2.imwrite(frame_path, frame)
                        return {
                            "ok": True,
                            "event": "motion_detected",
                            "motion_score": round(motion_score, 3),
                            "waited_seconds": round(elapsed, 1),
                            "frame": {"path": frame_path}
                        }
                self.last_frame = frame.copy()
            
            # Check for specific face
            if face:
                faces = self._detect_faces(frame, identify=True)
                for f in faces:
                    if f.get('name') == face:
                        frame_path = str(self.FRAME_DIR / f'face_{int(time.time())}.png')
                        cv2.imwrite(frame_path, frame)
                        return {
                            "ok": True,
                            "event": "face_detected",
                            "face": f,
                            "waited_seconds": round(elapsed, 1),
                            "frame": {"path": frame_path}
                        }
            
            # Check for text
            if text:
                extracted = self._extract_text(frame)
                if text.lower() in extracted.lower():
                    frame_path = str(self.FRAME_DIR / f'text_{int(time.time())}.png')
                    cv2.imwrite(frame_path, frame)
                    return {
                        "ok": True,
                        "event": "text_found",
                        "search": text,
                        "waited_seconds": round(elapsed, 1),
                        "frame": {"path": frame_path}
                    }
            
            # Check for object class
            if target:
                result = self.cmd_detect()
                if result.get("ok"):
                    current_detections = set()
                    for d in result.get("detections", []):
                        if d["class"] == target:
                            current_detections.add(d["class"])
                            
                            # Check enter/exit conditions
                            if enter:
                                if target not in last_detections and target in current_detections:
                                    frame_path = str(self.FRAME_DIR / f'enter_{int(time.time())}.png')
                                    cv2.imwrite(frame_path, frame)
                                    return {
                                        "ok": True,
                                        "event": f"{target}_entered",
                                        "detection": d,
                                        "waited_seconds": round(elapsed, 1),
                                        "frame": {"path": frame_path}
                                    }
                            elif exit_frame:
                                if target in last_detections and target not in current_detections:
                                    frame_path = str(self.FRAME_DIR / f'exit_{int(time.time())}.png')
                                    cv2.imwrite(frame_path, frame)
                                    return {
                                        "ok": True,
                                        "event": f"{target}_exited",
                                        "waited_seconds": round(elapsed, 1),
                                        "frame": {"path": frame_path}
                                    }
                            else:
                                # Simple detection
                                frame_path = str(self.FRAME_DIR / f'detected_{int(time.time())}.png')
                                cv2.imwrite(frame_path, frame)
                                return {
                                    "ok": True,
                                    "event": f"{target}_detected",
                                    "detection": d,
                                    "waited_seconds": round(elapsed, 1),
                                    "frame": {"path": frame_path}
                                }
                    
                    last_detections = current_detections
            
            time.sleep(0.5)  # Check twice per second
    
    def cmd_record(self, duration: float = None, output: str = None,
                   until: str = None, fps: int = 30) -> dict:
        """Record video."""
        if not self.source_type:
            return {"ok": False, "error": "No source configured", "exit_code": 1}
        
        if not output:
            output = str(self.FRAME_DIR / f'recording_{int(time.time())}.mp4')
        
        frame = self._capture_frame()
        if frame is None:
            return {"ok": False, "error": "Failed to capture frame", "exit_code": 3}
        
        height, width = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(output, fourcc, fps, (width, height))
        
        start_time = time.time()
        frame_count = 0
        
        try:
            while True:
                frame = self._capture_frame()
                if frame is None:
                    continue
                
                writer.write(frame)
                frame_count += 1
                
                elapsed = time.time() - start_time
                
                # Check duration
                if duration and elapsed >= duration:
                    break
                
                # Check until condition (object detection)
                if until:
                    result = self.cmd_detect()
                    if result.get("ok"):
                        for d in result.get("detections", []):
                            if d["class"] == until:
                                break
                
                time.sleep(1.0 / fps)
        
        finally:
            writer.release()
        
        return {
            "ok": True,
            "output": output,
            "duration_seconds": round(time.time() - start_time, 1),
            "frames": frame_count,
            "fps": fps
        }
    
    # ==================== Internal Methods ====================
    
    def _detect_yolo(self, frame: np.ndarray, model: str = 'yolov8n') -> List[dict]:
        """Run YOLO detection on frame."""
        yolo_model = self._get_yolo_model(model)
        if yolo_model is None:
            return []
        
        try:
            results = yolo_model(frame, verbose=False)
            detections = []
            
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    cls_id = int(box.cls[0])
                    cls_name = yolo_model.names[cls_id]
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    
                    detections.append({
                        "class": cls_name,
                        "confidence": round(conf, 3),
                        "box": [int(x1), int(y1), int(x2-x1), int(y2-y1)]
                    })
            
            return detections
        except:
            return []
    
    def _extract_text(self, frame: np.ndarray, lang: str = 'eng') -> str:
        """Extract text using OCR."""
        # Try Apple Vision first on macOS
        if sys.platform == 'darwin':
            text = self._ocr_apple_vision(frame)
            if text:
                return text
        
        # Fall back to Tesseract
        try:
            pytesseract = get_tesseract()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            text = pytesseract.image_to_string(gray, lang=lang)
            return text.strip()
        except ImportError:
            return ""
        except Exception:
            return ""
    
    def _ocr_apple_vision(self, frame: np.ndarray) -> str:
        """Use Apple Vision framework for OCR on macOS."""
        try:
            # Save frame temporarily
            tmp_path = '/tmp/ocr_frame.png'
            cv2.imwrite(tmp_path, frame)
            
            # Use swift/objc via subprocess
            script = '''
            import Vision
            import Foundation
            
            let url = URL(fileURLWithPath: "/tmp/ocr_frame.png")
            guard let image = CGImageSourceCreateWithURL(url as CFURL, nil),
                  let cgImage = CGImageSourceCreateImageAtIndex(image, 0, nil) else {
                exit(1)
            }
            
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            
            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
            try? handler.perform([request])
            
            guard let observations = request.results else { exit(1) }
            
            for observation in observations {
                guard let candidate = observation.topCandidates(1).first else { continue }
                print(candidate.string)
            }
            '''
            # This would need a compiled swift helper - skip for now
            return ""
        except:
            return ""
    
    def _detect_faces(self, frame: np.ndarray, identify: bool = False) -> List[dict]:
        """Detect faces in frame."""
        # Try face_recognition library first
        try:
            face_recognition = get_face_recognition()
            
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)
            
            if not face_locations:
                return []
            
            faces = []
            
            if identify:
                self._load_known_faces()
                encodings = face_recognition.face_encodings(rgb_frame, face_locations)
                
                for (top, right, bottom, left), encoding in zip(face_locations, encodings):
                    name = "unknown"
                    
                    if self._known_encodings:
                        matches = face_recognition.compare_faces(self._known_encodings, encoding)
                        if True in matches:
                            idx = matches.index(True)
                            name = self._known_names[idx]
                    
                    faces.append({
                        "box": [left, top, right-left, bottom-top],
                        "name": name
                    })
            else:
                for top, right, bottom, left in face_locations:
                    faces.append({
                        "box": [left, top, right-left, bottom-top]
                    })
            
            return faces
        
        except ImportError:
            pass
        
        # Fall back to OpenCV Haar cascade
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            detected = face_cascade.detectMultiScale(gray, 1.1, 4)
            
            return [{"box": [int(x), int(y), int(w), int(h)]} for (x, y, w, h) in detected]
        except:
            return []
    
    def _detect_motion(self, frame: np.ndarray) -> float:
        """Detect motion by comparing to last frame."""
        if self.last_frame is None:
            return 0.0
        
        try:
            gray1 = cv2.cvtColor(self.last_frame, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            diff = cv2.absdiff(gray1, gray2)
            _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
            
            motion_score = np.sum(thresh) / (thresh.shape[0] * thresh.shape[1] * 255)
            return round(motion_score, 4)
        except:
            return 0.0
    
    def _describe_frame(self, frame: np.ndarray, detail: str = 'medium', 
                        focus: str = None) -> Optional[str]:
        """Describe frame using vision LLM."""
        # Save frame temporarily
        tmp_path = '/tmp/vision_frame.png'
        cv2.imwrite(tmp_path, frame)
        
        # Try OpenAI
        if os.environ.get('OPENAI_API_KEY'):
            return self._describe_openai(tmp_path, detail, focus)
        
        # Try Anthropic
        if os.environ.get('ANTHROPIC_API_KEY'):
            return self._describe_anthropic(tmp_path, detail, focus)
        
        return None
    
    def _describe_openai(self, image_path: str, detail: str, focus: str) -> Optional[str]:
        """Describe image using OpenAI GPT-4V."""
        try:
            import openai
            import base64
            
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            prompt = "Describe what you see in this image."
            if focus:
                prompt = f"Describe what you see in this image, focusing on {focus}."
            if detail == 'high':
                prompt += " Be very detailed."
            elif detail == 'low':
                prompt += " Be brief."
            
            client = openai.OpenAI()
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{image_data}"
                        }}
                    ]
                }],
                max_tokens=500
            )
            
            return response.choices[0].message.content
        except Exception as e:
            return None
    
    def _describe_anthropic(self, image_path: str, detail: str, focus: str) -> Optional[str]:
        """Describe image using Anthropic Claude."""
        try:
            import anthropic
            import base64
            
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            prompt = "Describe what you see in this image."
            if focus:
                prompt = f"Describe what you see in this image, focusing on {focus}."
            if detail == 'high':
                prompt += " Be very detailed."
            elif detail == 'low':
                prompt += " Be brief."
            
            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data
                        }},
                        {"type": "text", "text": prompt}
                    ]
                }]
            )
            
            return response.content[0].text
        except Exception as e:
            return None
    
    def _ask_about_frame(self, frame: np.ndarray, question: str) -> Optional[str]:
        """Ask a question about the frame."""
        tmp_path = '/tmp/vision_frame.png'
        cv2.imwrite(tmp_path, frame)
        
        if os.environ.get('OPENAI_API_KEY'):
            return self._describe_openai(tmp_path, 'medium', None)
        
        if os.environ.get('ANTHROPIC_API_KEY'):
            return self._describe_anthropic(tmp_path, 'medium', None)
        
        return None


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='AI-first visual perception')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # source
    p = subparsers.add_parser('source', help='Set video source')
    p.add_argument('type', choices=['webcam', 'screen', 'window', 'file', 'image', 'ios', 'rtsp'])
    p.add_argument('path', nargs='?', help='Source path/index')
    
    # status
    subparsers.add_parser('status', help='Show source status')
    
    # disconnect
    subparsers.add_parser('disconnect', help='Disconnect from source')
    
    # snapshot
    p = subparsers.add_parser('snapshot', help='Capture frame')
    p.add_argument('--output', '-o', help='Output path')
    p.add_argument('--analyze', '-a', action='store_true', help='Run vision LLM')
    p.add_argument('--yolo', '-y', action='store_true', help='Run YOLO detection')
    p.add_argument('--ocr', action='store_true', help='Run OCR')
    p.add_argument('--faces', '-f', action='store_true', help='Detect faces')
    p.add_argument('--motion', '-m', action='store_true', help='Detect motion')
    p.add_argument('--all', action='store_true', help='Run all analysis')
    
    # detect
    p = subparsers.add_parser('detect', help='Run object detection')
    p.add_argument('--model', default='yolov8n', help='YOLO model')
    p.add_argument('--classes', help='Filter classes (comma-separated)')
    p.add_argument('--confidence', type=float, default=0.5, help='Confidence threshold')
    p.add_argument('--annotate', action='store_true', help='Save annotated image')
    
    # count
    p = subparsers.add_parser('count', help='Count objects')
    p.add_argument('class_name', nargs='?', help='Class to count')
    p.add_argument('--model', default='yolov8n', help='YOLO model')
    
    # ocr
    p = subparsers.add_parser('ocr', help='Extract text')
    p.add_argument('--region', help='Region: x,y,w,h')
    p.add_argument('--lang', default='eng', help='Language')
    p.add_argument('--find', help='Search for text')
    
    # faces
    p = subparsers.add_parser('faces', help='Detect faces')
    p.add_argument('--identify', action='store_true', help='Identify known faces')
    p.add_argument('--emotions', action='store_true', help='Detect emotions')
    
    # face learn/list
    p = subparsers.add_parser('face', help='Face management')
    p.add_argument('action', choices=['learn', 'forget', 'list'])
    p.add_argument('name', nargs='?', help='Face name')
    p.add_argument('image', nargs='?', help='Image path')
    
    # describe
    p = subparsers.add_parser('describe', help='Describe frame with LLM')
    p.add_argument('--detail', choices=['low', 'medium', 'high'], default='medium')
    p.add_argument('--focus', help='Focus description on topic')
    
    # ask
    p = subparsers.add_parser('ask', help='Ask question about frame')
    p.add_argument('question', help='Question to ask')
    
    # watch
    p = subparsers.add_parser('watch', help='Watch for events')
    p.add_argument('target', nargs='?', help='Object class to watch for')
    p.add_argument('--timeout', type=int, default=60, help='Timeout in seconds')
    p.add_argument('--motion', action='store_true', help='Watch for motion')
    p.add_argument('--face', help='Watch for specific face')
    p.add_argument('--text', help='Watch for text (OCR)')
    p.add_argument('--enter', action='store_true', help='Watch for object entering')
    p.add_argument('--exit', action='store_true', help='Watch for object exiting')
    
    # record
    p = subparsers.add_parser('record', help='Record video')
    p.add_argument('duration', nargs='?', type=float, help='Duration in seconds')
    p.add_argument('output', nargs='?', help='Output file')
    p.add_argument('--until', help='Record until object detected')
    p.add_argument('--fps', type=int, default=30, help='Frames per second')
    
    args = parser.parse_args()
    
    session = VisionSession()
    result = {"ok": False, "error": "Unknown command"}
    
    if args.command == 'source':
        result = session.cmd_source(args.type, args.path)
    elif args.command == 'status':
        result = session.cmd_status()
    elif args.command == 'disconnect':
        result = session.cmd_disconnect()
    elif args.command == 'snapshot':
        all_flags = args.all
        result = session.cmd_snapshot(
            output=args.output,
            analyze=args.analyze or all_flags,
            yolo=args.yolo or all_flags,
            ocr=args.ocr or all_flags,
            faces=args.faces or all_flags,
            motion=args.motion or all_flags
        )
    elif args.command == 'detect':
        result = session.cmd_detect(
            model=args.model,
            classes=args.classes,
            confidence=args.confidence,
            annotate=args.annotate
        )
    elif args.command == 'count':
        result = session.cmd_count(args.class_name, args.model)
    elif args.command == 'ocr':
        result = session.cmd_ocr(region=args.region, lang=args.lang, find=args.find)
    elif args.command == 'faces':
        result = session.cmd_faces(identify=args.identify, emotions=args.emotions)
    elif args.command == 'face':
        if args.action == 'learn':
            result = session.cmd_face_learn(args.name, args.image)
        elif args.action == 'list':
            result = session.cmd_face_list()
        else:
            result = {"ok": False, "error": "Not implemented"}
    elif args.command == 'describe':
        result = session.cmd_describe(detail=args.detail, focus=args.focus)
    elif args.command == 'ask':
        result = session.cmd_ask(args.question)
    elif args.command == 'watch':
        result = session.cmd_watch(
            target=args.target,
            timeout=args.timeout,
            motion=args.motion,
            face=args.face,
            text=args.text,
            enter=args.enter,
            exit_frame=getattr(args, 'exit', False)
        )
    elif args.command == 'record':
        result = session.cmd_record(
            duration=args.duration,
            output=args.output,
            until=args.until,
            fps=args.fps
        )
    elif args.command is None:
        parser.print_help()
        sys.exit(0)
    
    print(json.dumps(result, indent=2, default=str))
    sys.exit(result.get('exit_code', 0) if not result.get('ok') else 0)


if __name__ == '__main__':
    main()
