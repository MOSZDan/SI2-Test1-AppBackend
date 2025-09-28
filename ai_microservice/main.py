from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import face_recognition
import numpy as np
import base64
import io
from PIL import Image
import easyocr
import re
from typing import List

app = FastAPI()

# Configurar CORS para permitir llamadas desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Frontend en desarrollo
        "http://127.0.0.1:5173",  # Frontend en desarrollo (IP)
        "https://si-2-test1-app.vercel.app",  # Frontend en producción
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

class FaceRecognitionRequest(BaseModel):
    image_base64: str
    known_encodings: list
    known_users: list
    tolerance: float = 0.6

class PlateDetectionRequest(BaseModel):
    image_base64: str

@app.post("/recognize-face/")
def recognize_face(req: FaceRecognitionRequest):
    # Decodificar imagen
    image_data = base64.b64decode(req.image_base64)
    image = np.array(Image.open(io.BytesIO(image_data)))
    # Convertir encodings
    known_encodings = [np.array(enc) for enc in req.known_encodings]
    # Procesar reconocimiento facial
    face_locations = face_recognition.face_locations(image)
    face_encodings = face_recognition.face_encodings(image, face_locations)
    results = []
    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=req.tolerance)
        user = None
        if True in matches:
            first_match_index = matches.index(True)
            user = req.known_users[first_match_index]
        results.append({"user": user, "matches": matches})
    return {"results": results}

@app.post("/detect-plate/")
def detect_plate(req: PlateDetectionRequest):
    image_data = base64.b64decode(req.image_base64)
    image = np.array(Image.open(io.BytesIO(image_data)))
    reader = easyocr.Reader(['es', 'en'])
    result = reader.readtext(image)
    plates = []
    plate_pattern = re.compile(r'^[A-Z]{3}-?\d{4}$|^\d{4}-?[A-Z]{3}$')
    for detection in result:
        text = detection[1]
        confidence = detection[2]
        cleaned = re.sub(r'[^A-Z0-9-]', '', text.upper())
        # Formateo de placa
        if len(cleaned) == 7 and cleaned[3] != '-':
            if cleaned[:3].isalpha() and cleaned[3:].isdigit():
                cleaned = f"{cleaned[:3]}-{cleaned[3:]}"
            elif cleaned[:4].isdigit() and cleaned[4:].isalpha():
                cleaned = f"{cleaned[:4]}-{cleaned[4:]}"
        if plate_pattern.match(cleaned):
            plates.append({"plate": cleaned, "confidence": confidence})
    return {"plates": plates}

# ========= ENDPOINTS PARA COMPATIBILIDAD CON FRONTEND =========

# Endpoint de salud del servicio
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "timestamp": "2025-09-28T00:00:00Z",
        "services": {
            "facial_recognition": True,
            "plate_detection": True,
            "easyocr": True
        }
    }

@app.get("/info")
def service_info():
    return {
        "version": "1.0.0",
        "models": ["face_recognition", "easyocr"],
        "capabilities": ["facial_recognition", "plate_detection"]
    }

# Endpoints que tu frontend espera
@app.post("/api/facial/recognize")
def api_facial_recognize(file: UploadFile = File(...)):
    """Endpoint para reconocimiento facial compatible con tu frontend"""
    # Leer imagen
    image_data = file.file.read()
    image = np.array(Image.open(io.BytesIO(image_data)))

    # Por ahora retornar respuesta mock - necesitarás conectar con Django para obtener perfiles conocidos
    return {
        "success": True,
        "message": "Reconocimiento completado",
        "data": {
            "id": 1,
            "user_name": "Usuario Detectado",
            "confidence": 0.85,
            "is_resident": True,
            "detection_time": "2025-09-28T00:00:00Z",
            "camera_location": "Web App"
        }
    }

@app.post("/api/facial/register")
def api_facial_register(file: UploadFile = File(...), user_id: int = None):
    """Endpoint para registrar perfil facial compatible con tu frontend"""
    # Procesar imagen
    image_data = file.file.read()
    image = np.array(Image.open(io.BytesIO(image_data)))

    # Obtener encodings faciales
    face_locations = face_recognition.face_locations(image)
    face_encodings = face_recognition.face_encodings(image, face_locations)

    if not face_encodings:
        return {
            "success": False,
            "message": "No se detectó ningún rostro en la imagen",
            "error": "No face detected"
        }

    # Aquí necesitarás guardar en Django/base de datos
    return {
        "success": True,
        "message": "Perfil registrado exitosamente",
        "data": {
            "profile_id": 1,
            "user_id": user_id,
            "user_name": "Usuario Registrado",
            "registration_time": "2025-09-28T00:00:00Z"
        }
    }

@app.get("/api/facial/profiles")
def api_facial_profiles():
    """Listar perfiles faciales registrados"""
    return {
        "success": True,
        "data": []  # Conectar con Django para obtener perfiles reales
    }

@app.delete("/api/facial/profiles/{profile_id}")
def api_facial_delete_profile(profile_id: int):
    """Eliminar perfil facial"""
    return {
        "success": True,
        "message": f"Perfil {profile_id} eliminado"
    }

@app.get("/api/facial/stats")
def api_facial_stats():
    """Estadísticas de reconocimiento facial"""
    return {
        "success": True,
        "data": {
            "total_recognitions": 0,
            "successful_matches": 0,
            "unknown_faces": 0
        }
    }

@app.post("/api/plates/detect")
def api_plates_detect(file: UploadFile = File(...)):
    """Endpoint para detección de placas compatible con tu frontend"""
    # Leer imagen
    image_data = file.file.read()
    image = np.array(Image.open(io.BytesIO(image_data)))

    # Detectar texto con EasyOCR
    reader = easyocr.Reader(['es', 'en'])
    result = reader.readtext(image)

    plates = []
    plate_pattern = re.compile(r'^[A-Z]{3}-?\d{4}$|^\d{4}-?[A-Z]{3}$')

    for detection in result:
        text = detection[1]
        confidence = detection[2]
        cleaned = re.sub(r'[^A-Z0-9-]', '', text.upper())

        # Formateo de placa
        if len(cleaned) == 7 and cleaned[3] != '-':
            if cleaned[:3].isalpha() and cleaned[3:].isdigit():
                cleaned = f"{cleaned[:3]}-{cleaned[3:]}"
            elif cleaned[:4].isdigit() and cleaned[4:].isalpha():
                cleaned = f"{cleaned[:4]}-{cleaned[4:]}"

        if plate_pattern.match(cleaned):
            plates.append({"plate": cleaned, "confidence": confidence})

    if plates:
        best_plate = max(plates, key=lambda x: x['confidence'])
        return {
            "success": True,
            "message": "Placa detectada",
            "data": {
                "id": 1,
                "plate": best_plate["plate"],
                "confidence": best_plate["confidence"],
                "is_authorized": False,  # Conectar con Django para verificar autorización
                "detection_time": "2025-09-28T00:00:00Z",
                "camera_location": "Estacionamiento"
            }
        }
    else:
        return {
            "success": False,
            "message": "No se detectó ninguna placa válida",
            "error": "No valid plate detected"
        }

@app.get("/api/plates/detections")
def api_plates_detections():
    """Listar detecciones de placas"""
    return {
        "success": True,
        "data": []  # Conectar con Django para obtener detecciones reales
    }

@app.get("/api/plates/stats")
def api_plates_stats():
    """Estadísticas de detección de placas"""
    return {
        "success": True,
        "data": {
            "total_detections": 0,
            "authorized_vehicles": 0,
            "unauthorized_vehicles": 0
        }
    }

@app.get("/api/stats/general")
def api_stats_general():
    """Estadísticas generales del sistema"""
    return {
        "success": True,
        "data": {
            "facial_recognitions": 0,
            "plate_detections": 0,
            "system_uptime": "1 day"
        }
    }

@app.get("/api/stats/today")
def api_stats_today():
    """Estadísticas de hoy"""
    return {
        "success": True,
        "data": {
            "recognitions_today": 0,
            "detections_today": 0
        }
    }

@app.get("/api/stats/week")
def api_stats_week():
    """Estadísticas de la semana"""
    return {
        "success": True,
        "data": {
            "recognitions_week": 0,
            "detections_week": 0
        }
    }
