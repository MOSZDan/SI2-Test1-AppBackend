# api/services/ai_detection.py
# import cv2  # Comentado para evitar el error en producción
# import face_recognition  # Comentado para evitar el error en producción
import numpy as np
import json
import base64
import io
from PIL import Image
# import easyocr  # Comentado para evitar el error en producción
import re
from typing import List, Tuple, Optional, Dict
from django.conf import settings
from ..models import Usuario, PerfilFacial, ReconocimientoFacial, DeteccionPlaca, Vehiculo
from .supabase_storage import SupabaseStorageService
import logging
from django.core.files.uploadedfile import InMemoryUploadedFile
import requests
logger = logging.getLogger(__name__)


class FacialRecognitionService:
    """Servicio para reconocimiento facial usando el microservicio de IA"""

    def __init__(self):
        self.tolerance = settings.AI_IMAGE_SETTINGS.get('FACE_TOLERANCE', 0.6)
        self.storage_service = SupabaseStorageService()
        self.ai_microservice_url = settings.AI_MICROSERVICE_URL

    def process_facial_recognition(self, image_file: InMemoryUploadedFile) -> Dict:
        """
        Procesa reconocimiento facial usando el microservicio
        """
        try:
            # Preparar archivo para enviar al microservicio
            files = {'image': (image_file.name, image_file.read(), image_file.content_type)}

            # Llamar al microservicio
            response = requests.post(
                f"{self.ai_microservice_url}/facial-recognition/",
                files=files,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Error del microservicio de IA: {response.status_code} - {response.text}")
                return {"success": False, "error": "Error en el servicio de reconocimiento facial"}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error conectando con microservicio de IA: {str(e)}")
            return {"success": False, "error": "Servicio de reconocimiento facial no disponible"}
        except Exception as e:
            logger.error(f"Error procesando reconocimiento facial: {str(e)}")
            return {"success": False, "error": "Error interno en reconocimiento facial"}

    def load_known_faces(self):
        """Método mantenido para compatibilidad"""
        # Este método ahora se maneja en el microservicio
        pass

    def register_face(self, user_id: int, image_file: InMemoryUploadedFile) -> Dict:
        """
        Registra una nueva cara usando el microservicio
        """
        try:
            files = {'image': (image_file.name, image_file.read(), image_file.content_type)}
            data = {'user_id': user_id}

            response = requests.post(
                f"{self.ai_microservice_url}/register-face/",
                files=files,
                data=data,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Error registrando cara: {response.status_code} - {response.text}")
                return {"success": False, "error": "Error registrando el rostro"}

        except Exception as e:
            logger.error(f"Error registrando cara: {str(e)}")
            return {"success": False, "error": "Error interno registrando rostro"}


class PlateDetectionService:
    """Servicio para detección de placas usando el microservicio de IA"""

    def __init__(self):
        self.storage_service = SupabaseStorageService()
        self.ai_microservice_url = settings.AI_MICROSERVICE_URL

    def detect_plate(self, image_file: InMemoryUploadedFile) -> Dict:
        """
        Detecta placas de vehículos usando el microservicio
        """
        try:
            files = {'image': (image_file.name, image_file.read(), image_file.content_type)}

            response = requests.post(
                f"{self.ai_microservice_url}/plate-detection/",
                files=files,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Error en detección de placas: {response.status_code} - {response.text}")
                return {"success": False, "error": "Error en el servicio de detección de placas"}

        except requests.exceptions.RequestException as e:
            logger.error(f"Error conectando con microservicio: {str(e)}")
            return {"success": False, "error": "Servicio de detección de placas no disponible"}
        except Exception as e:
            logger.error(f"Error detectando placa: {str(e)}")
            return {"success": False, "error": "Error interno en detección de placas"}

    def process_plate_detection(self, image_file: InMemoryUploadedFile, vehicle_id: Optional[int] = None) -> Dict:
        """
        Procesa la detección de placas y guarda el resultado
        """
        try:
            # Detectar placa usando el microservicio
            detection_result = self.detect_plate(image_file)

            if not detection_result.get("success"):
                return detection_result

            # Guardar imagen en Supabase
            image_url = self.storage_service.upload_file(
                image_file,
                folder="plate_detections"
            )

            # Crear registro en base de datos
            deteccion = DeteccionPlaca.objects.create(
                texto_placa=detection_result.get("plate_text", ""),
                confianza=detection_result.get("confidence", 0.0),
                imagen_url=image_url,
                vehiculo_id=vehicle_id
            )

            return {
                "success": True,
                "detection_id": deteccion.id,
                "plate_text": deteccion.texto_placa,
                "confidence": deteccion.confianza,
                "image_url": image_url
            }

        except Exception as e:
            logger.error(f"Error procesando detección de placa: {str(e)}")
            return {"success": False, "error": "Error procesando detección de placa"}

    def validate_plate_format(self, plate_text: str) -> bool:
        """
        Valida el formato de placa boliviana
        """
        # Formato boliviano: 3-4 números + 3 letras (ej: 1234-ABC)
        pattern = r'^\d{3,4}-[A-Z]{3}$'
        return bool(re.match(pattern, plate_text.upper()))
