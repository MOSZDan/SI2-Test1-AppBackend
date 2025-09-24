from fastapi import FastAPI, UploadFile, File
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
