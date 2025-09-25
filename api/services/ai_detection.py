# api/services/ai_detection.py
import cv2
import face_recognition
import numpy as np
import json
import base64
import io
from PIL import Image
import easyocr
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
    """Servicio para reconocimiento facial usando face_recognition"""

    def __init__(self):
        self.tolerance = settings.AI_IMAGE_SETTINGS.get('FACE_TOLERANCE', 0.6)
        self.known_encodings = []
        self.known_users = []
        self.storage_service = SupabaseStorageService()
        self.load_known_faces()

    def load_known_faces(self):
        """Carga las caras conocidas desde la base de datos"""
        try:
            perfiles = PerfilFacial.objects.filter(activo=True).select_related('codigo_usuario')

            self.known_encodings = []
            self.known_users = []

            for perfil in perfiles:
                try:
                    encoding = np.array(json.loads(perfil.encoding_facial))
                    self.known_encodings.append(encoding)
                    self.known_users.append(perfil.codigo_usuario)
                except Exception as e:
                    logger.error(f"Error cargando perfil facial {perfil.id}: {e}")

            logger.info(f"Cargados {len(self.known_encodings)} perfiles faciales")

        except Exception as e:
            logger.error(f"Error cargando caras conocidas: {e}")

    def register_face(self, user_id: int, image_base64: str) -> bool:
        """Registra una nueva cara en el sistema"""
        try:
            image = self._base64_to_image(image_base64)
            if image is None:
                return False

            face_locations = face_recognition.face_locations(image)
            if not face_locations:
                logger.warning("No se detectó ninguna cara en la imagen")
                return False

            face_encodings = face_recognition.face_encodings(image, face_locations)
            if not face_encodings:
                logger.warning("No se pudo generar encoding facial")
                return False

            encoding = face_encodings[0]

            upload_result = self.storage_service.upload_base64_image(
                image_base64,
                folder="profiles",
                prefix=f"user_{user_id}"
            )

            if not upload_result:
                logger.error("Error subiendo imagen a Supabase")
                return False

            usuario = Usuario.objects.get(codigo=user_id)
            perfil, created = PerfilFacial.objects.get_or_create(
                codigo_usuario=usuario,
                defaults={
                    'encoding_facial': json.dumps(encoding.tolist()),
                    'imagen_path': upload_result['file_path'],
                    'imagen_url': upload_result['public_url'],
                    'activo': True
                }
            )

            if not created:
                if perfil.imagen_path:
                    self.storage_service.delete_file(perfil.imagen_path)

                perfil.encoding_facial = json.dumps(encoding.tolist())
                perfil.imagen_path = upload_result['file_path']
                perfil.imagen_url = upload_result['public_url']
                perfil.activo = True
                perfil.save()

            self.load_known_faces()

            logger.info(f"Cara registrada para usuario {user_id}")
            return True

        except Usuario.DoesNotExist:
            logger.error(f"Usuario {user_id} no existe")
            return False
        except Exception as e:
            logger.error(f"Error registrando cara: {e}")
            return False

    def recognize_face(self, image_base64: str, camera_location: str = "Principal") -> Dict:
        """Reconoce una cara en la imagen usando el microservicio de IA"""
        try:
            # Serializar encodings y usuarios conocidos
            known_encodings = [enc.tolist() for enc in self.known_encodings]
            known_users = [str(u.codigo) for u in self.known_users]
            payload = {
                "image_base64": image_base64,
                "known_encodings": known_encodings,
                "known_users": known_users,
                "tolerance": self.tolerance
            }
            # Llamar al microservicio
            url = settings.AI_MICROSERVICE_URL + "/recognize-face/"
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # Procesar respuesta
            results = data.get("results", [])
            for result in results:
                user_codigo = result.get("user")
                if user_codigo:
                    usuario = Usuario.objects.filter(codigo=user_codigo).first()
                    confidence = 100.0  # El microservicio no calcula confianza, puedes ajustar si lo deseas
                    return self._create_recognition_result(
                        True, usuario, confidence, image_base64, camera_location
                    )
            return self._create_recognition_result(False, None, 0.0, image_base64, camera_location)
        except Exception as e:
            logger.error(f"Error en reconocimiento facial (microservicio): {e}")
            return self._create_recognition_result(False, None, 0.0, image_base64, camera_location)

    def _create_recognition_result(self, is_resident: bool, usuario: Optional[Usuario],
                                   confidence: float, image_base64: str, camera_location: str) -> Dict:
        """Crea y guarda el resultado del reconocimiento"""
        try:
            upload_result = self.storage_service.upload_base64_image(
                image_base64,
                folder="facial",
                prefix=f"detection_{camera_location.lower().replace(' ', '_')}"
            )

            reconocimiento = ReconocimientoFacial.objects.create(
                codigo_usuario=usuario,
                imagen_path=upload_result['file_path'] if upload_result else None,
                imagen_url=upload_result['public_url'] if upload_result else None,
                confianza=confidence,
                es_residente=is_resident,
                ubicacion_camara=camera_location,
                estado='permitido' if is_resident else 'denegado'
            )

            return {
                'id': reconocimiento.id,
                'is_resident': is_resident,
                'user': {
                    'codigo': usuario.codigo if usuario else None,
                    'nombre': f"{usuario.nombre} {usuario.apellido}" if usuario else "Desconocido",
                    'correo': usuario.correo if usuario else None
                } if usuario else None,
                'confidence': round(confidence, 2),
                'timestamp': reconocimiento.fecha_deteccion.isoformat(),
                'camera_location': camera_location,
                'status': 'permitido' if is_resident else 'denegado',
                'image_url': reconocimiento.imagen_url
            }

        except Exception as e:
            logger.error(f"Error creando resultado de reconocimiento: {e}")
            return {
                'id': None,
                'is_resident': False,
                'user': None,
                'confidence': 0.0,
                'timestamp': None,
                'camera_location': camera_location,
                'status': 'error',
                'image_url': None
            }

    def _base64_to_image(self, base64_string: str) -> Optional[np.ndarray]:
        """Convierte base64 a imagen numpy"""
        try:
            if base64_string.startswith('data:image'):
                base64_string = base64_string.split(',', 1)[1]

            image_data = base64.b64decode(base64_string)
            image = Image.open(io.BytesIO(image_data))

            if image.mode != 'RGB':
                image = image.convert('RGB')

            return np.array(image)

        except Exception as e:
            logger.error(f"Error convirtiendo base64 a imagen: {e}")
            return None
    def register_face_from_file(self, user_id: int, image_file: InMemoryUploadedFile) -> bool:
        """Registra una nueva cara desde un archivo Django"""
        try:
            # Convertir archivo Django a imagen numpy
            image = self._file_to_image(image_file)
            if image is None:
                return False

            face_locations = face_recognition.face_locations(image)
            if not face_locations:
                logger.warning("No se detectó ninguna cara en la imagen")
                return False

            face_encodings = face_recognition.face_encodings(image, face_locations)
            if not face_encodings:
                logger.warning("No se pudo generar encoding facial")
                return False

            encoding = face_encodings[0]

            # Subir archivo directamente a Supabase
            upload_result = self.storage_service.upload_django_file(
                image_file,
                folder="profiles",
                prefix=f"user_{user_id}"
            )

            if not upload_result:
                logger.error("Error subiendo imagen a Supabase")
                return False

            usuario = Usuario.objects.get(codigo=user_id)
            perfil, created = PerfilFacial.objects.get_or_create(
                codigo_usuario=usuario,
                defaults={
                    'encoding_facial': json.dumps(encoding.tolist()),
                    'imagen_path': upload_result['file_path'],
                    'imagen_url': upload_result['public_url'],
                    'activo': True
                }
            )

            if not created:
                if perfil.imagen_path:
                    self.storage_service.delete_file(perfil.imagen_path)

                perfil.encoding_facial = json.dumps(encoding.tolist())
                perfil.imagen_path = upload_result['file_path']
                perfil.imagen_url = upload_result['public_url']
                perfil.activo = True
                perfil.save()

            self.load_known_faces()

            logger.info(f"Cara registrada para usuario {user_id}")
            return True

        except Usuario.DoesNotExist:
            logger.error(f"Usuario {user_id} no existe")
            return False
        except Exception as e:
            logger.error(f"Error registrando cara desde archivo: {e}")
            return False

    def recognize_face_from_file(self, image_file: InMemoryUploadedFile, camera_location: str = "Principal") -> Dict:
        """Reconoce una cara desde un archivo Django"""
        try:
            image = self._file_to_image(image_file)
            if image is None:
                return self._create_recognition_result_from_file(False, None, 0.0, image_file, camera_location)

            face_locations = face_recognition.face_locations(image)
            if not face_locations:
                return self._create_recognition_result_from_file(False, None, 0.0, image_file, camera_location)

            face_encodings = face_recognition.face_encodings(image, face_locations)
            if not face_encodings:
                return self._create_recognition_result_from_file(False, None, 0.0, image_file, camera_location)

            for face_encoding in face_encodings:
                if not self.known_encodings:
                    break

                matches = face_recognition.compare_faces(
                    self.known_encodings, face_encoding, tolerance=self.tolerance
                )
                face_distances = face_recognition.face_distance(
                    self.known_encodings, face_encoding
                )

                if any(matches):
                    best_match_index = np.argmin(face_distances)
                    if matches[best_match_index]:
                        usuario = self.known_users[best_match_index]
                        confidence = (1 - face_distances[best_match_index]) * 100

                        return self._create_recognition_result_from_file(
                            True, usuario, confidence, image_file, camera_location
                        )

            return self._create_recognition_result_from_file(False, None, 0.0, image_file, camera_location)

        except Exception as e:
            logger.error(f"Error en reconocimiento facial desde archivo: {e}")
            return self._create_recognition_result_from_file(False, None, 0.0, image_file, camera_location)

    def _create_recognition_result_from_file(self, is_resident: bool, usuario: Optional[Usuario],
                                           confidence: float, image_file: InMemoryUploadedFile, camera_location: str) -> Dict:
        """Crea y guarda el resultado del reconocimiento desde archivo"""
        try:
            upload_result = self.storage_service.upload_django_file(
                image_file,
                folder="facial",
                prefix=f"detection_{camera_location.lower().replace(' ', '_')}"
            )

            reconocimiento = ReconocimientoFacial.objects.create(
                codigo_usuario=usuario,
                imagen_path=upload_result['file_path'] if upload_result else None,
                imagen_url=upload_result['public_url'] if upload_result else None,
                confianza=confidence,
                es_residente=is_resident,
                ubicacion_camara=camera_location,
                estado='permitido' if is_resident else 'denegado'
            )

            return {
                'id': reconocimiento.id,
                'is_resident': is_resident,
                'user': {
                    'codigo': usuario.codigo if usuario else None,
                    'nombre': f"{usuario.nombre} {usuario.apellido}" if usuario else "Desconocido",
                    'correo': usuario.correo if usuario else None
                } if usuario else None,
                'confidence': round(confidence, 2),
                'timestamp': reconocimiento.fecha_deteccion.isoformat(),
                'camera_location': camera_location,
                'status': 'permitido' if is_resident else 'denegado',
                'image_url': reconocimiento.imagen_url
            }

        except Exception as e:
            logger.error(f"Error creando resultado de reconocimiento desde archivo: {e}")
            return {
                'id': None,
                'is_resident': False,
                'user': None,
                'confidence': 0.0,
                'timestamp': None,
                'camera_location': camera_location,
                'status': 'error',
                'image_url': None
            }

    def _file_to_image(self, image_file: InMemoryUploadedFile) -> Optional[np.ndarray]:
        """Convierte archivo Django a imagen numpy"""
        try:
            image_file.seek(0)  # Asegurar que estamos al inicio del archivo
            image_data = image_file.read()
            image = Image.open(io.BytesIO(image_data))

            if image.mode != 'RGB':
                image = image.convert('RGB')

            return np.array(image)

        except Exception as e:
            logger.error(f"Error convirtiendo archivo a imagen: {e}")
            return None

# En la clase PlateDetectionService, agregar estos métodos:

    def detect_plate_from_file(self, image_file: InMemoryUploadedFile, camera_location: str = "Estacionamiento",
                              access_type: str = "entrada") -> Dict:
        """Detecta placa desde un archivo Django"""
        try:
            image = self._file_to_image(image_file)
            if image is None:
                return self._create_detection_result_from_file(None, False, 0.0, image_file,
                                                             camera_location, access_type)

            processed_image = self._preprocess_image(image)
            results = self.reader.readtext(processed_image)

            for (bbox, text, confidence) in results:
                clean_text = self._clean_plate_text(text)

                if self._is_valid_plate(clean_text) and confidence > self.confidence_threshold:
                    is_authorized = self._check_authorization(clean_text)

                    return self._create_detection_result_from_file(
                        clean_text, is_authorized, confidence * 100,
                        image_file, camera_location, access_type
                    )

            return self._create_detection_result_from_file(None, False, 0.0, image_file,
                                                         camera_location, access_type)

        except Exception as e:
            logger.error(f"Error en detección de placa desde archivo: {e}")
            return self._create_detection_result_from_file(None, False, 0.0, image_file,
                                                         camera_location, access_type)

    def _create_detection_result_from_file(self, plate: Optional[str], is_authorized: bool,
                                         confidence: float, image_file: InMemoryUploadedFile, camera_location: str,
                                         access_type: str) -> Dict:
        """Crea y guarda el resultado de la detección desde archivo"""
        try:
            upload_result = self.storage_service.upload_django_file(
                image_file,
                folder="plates",
                prefix=f"{access_type}_{camera_location.lower().replace(' ', '_')}"
            )

            vehiculo = None
            if plate:
                vehiculo = Vehiculo.objects.filter(nro_placa__iexact=plate).first()

            deteccion = DeteccionPlaca.objects.create(
                placa_detectada=plate or "No detectada",
                vehiculo=vehiculo,
                imagen_path=upload_result['file_path'] if upload_result else None,
                imagen_url=upload_result['public_url'] if upload_result else None,
                confianza=confidence,
                es_autorizado=is_authorized,
                ubicacion_camara=camera_location,
                tipo_acceso=access_type
            )

            return {
                'id': deteccion.id,
                'plate': plate,
                'is_authorized': is_authorized,
                'vehicle': {
                    'id': vehiculo.id if vehiculo else None,
                    'descripcion': vehiculo.descripcion if vehiculo else None,
                    'estado': vehiculo.estado if vehiculo else None
                } if vehiculo else None,
                'confidence': round(confidence, 2),
                'timestamp': deteccion.fecha_deteccion.isoformat(),
                'camera_location': camera_location,
                'access_type': access_type,
                'status': 'autorizado' if is_authorized else 'no_autorizado',
                'image_url': deteccion.imagen_url
            }

        except Exception as e:
            logger.error(f"Error creando resultado de detección desde archivo: {e}")
            return {
                'id': None,
                'plate': plate,
                'is_authorized': False,
                'vehicle': None,
                'confidence': 0.0,
                'timestamp': None,
                'camera_location': camera_location,
                'access_type': access_type,
                'status': 'error',
                'image_url': None
            }

    def _file_to_image(self, image_file: InMemoryUploadedFile) -> Optional[np.ndarray]:
        """Convierte archivo Django a imagen numpy"""
        try:
            image_file.seek(0)
            image_data = image_file.read()
            image = Image.open(io.BytesIO(image_data))

            if image.mode != 'RGB':
                image = image.convert('RGB')

            return np.array(image)

        except Exception as e:
            logger.error(f"Error convirtiendo archivo a imagen: {e}")
            return None

class PlateDetectionService:
    """Servicio para detección de placas usando EasyOCR"""

    def __init__(self):
        self.reader = easyocr.Reader(['en', 'es'])
        self.plate_pattern = re.compile(r'^[A-Z]{3}-?\d{4}$|^\d{4}-?[A-Z]{3}$')
        self.storage_service = SupabaseStorageService()
        self.confidence_threshold = settings.AI_IMAGE_SETTINGS.get('PLATE_CONFIDENCE_THRESHOLD', 0.5)

    def detect_plate(self, image_base64: str, camera_location: str = "Estacionamiento",
                     access_type: str = "entrada") -> Dict:
        """Detecta placa en la imagen usando el microservicio de IA"""
        try:
            payload = {"image_base64": image_base64}
            url = settings.AI_MICROSERVICE_URL + "/detect-plate/"
            resp = requests.post(url, json=payload, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            plates = data.get("plates", [])
            # Buscar la placa con mayor confianza
            best_plate = None
            best_conf = 0.0
            for plate_info in plates:
                if plate_info["confidence"] > best_conf:
                    best_plate = plate_info["plate"]
                    best_conf = plate_info["confidence"]
            if best_plate:
                is_authorized = self._check_authorization(best_plate)
                return self._create_detection_result(
                    best_plate, is_authorized, best_conf * 100,
                    image_base64, camera_location, access_type
                )
            return self._create_detection_result(None, False, 0.0, image_base64, camera_location, access_type)
        except Exception as e:
            logger.error(f"Error en detección de placa (microservicio): {e}")
            return self._create_detection_result(None, False, 0.0, image_base64, camera_location, access_type)

    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocesa la imagen para mejor detección de placas"""
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(blurred)
            return enhanced
        except Exception as e:
            logger.error(f"Error preprocesando imagen: {e}")
            return image

    def _clean_plate_text(self, text: str) -> str:
        """Limpia el texto detectado de la placa"""
        cleaned = re.sub(r'[^A-Z0-9-]', '', text.upper())

        if len(cleaned) == 7 and cleaned[3] != '-':
            if cleaned[:3].isalpha() and cleaned[3:].isdigit():
                cleaned = f"{cleaned[:3]}-{cleaned[3:]}"
            elif cleaned[:4].isdigit() and cleaned[4:].isalpha():
                cleaned = f"{cleaned[:4]}-{cleaned[4:]}"

        return cleaned

    def _is_valid_plate(self, text: str) -> bool:
        """Verifica si el texto parece una placa válida"""
        return bool(self.plate_pattern.match(text))

    def _check_authorization(self, plate: str) -> bool:
        """Verifica si la placa está autorizada"""
        try:
            vehiculo = Vehiculo.objects.filter(
                nro_placa__iexact=plate,
                estado='activo'
            ).first()
            return vehiculo is not None
        except Exception as e:
            logger.error(f"Error verificando autorización de placa {plate}: {e}")
            return False

    def _create_detection_result(self, plate: Optional[str], is_authorized: bool,
                                 confidence: float, image_base64: str, camera_location: str,
                                 access_type: str) -> Dict:
        """Crea y guarda el resultado de la detección"""
        try:
            upload_result = self.storage_service.upload_base64_image(
                image_base64,
                folder="plates",
                prefix=f"{access_type}_{camera_location.lower().replace(' ', '_')}"
            )

            vehiculo = None
            if plate:
                vehiculo = Vehiculo.objects.filter(nro_placa__iexact=plate).first()

            deteccion = DeteccionPlaca.objects.create(
                placa_detectada=plate or "No detectada",
                vehiculo=vehiculo,
                imagen_path=upload_result['file_path'] if upload_result else None,
                imagen_url=upload_result['public_url'] if upload_result else None,
                confianza=confidence,
                es_autorizado=is_authorized,
                ubicacion_camara=camera_location,
                tipo_acceso=access_type
            )

            return {
                'id': deteccion.id,
                'plate': plate,
                'is_authorized': is_authorized,
                'vehicle': {
                    'id': vehiculo.id if vehiculo else None,
                    'descripcion': vehiculo.descripcion if vehiculo else None,
                    'estado': vehiculo.estado if vehiculo else None
                } if vehiculo else None,
                'confidence': round(confidence, 2),
                'timestamp': deteccion.fecha_deteccion.isoformat(),
                'camera_location': camera_location,
                'access_type': access_type,
                'status': 'autorizado' if is_authorized else 'no_autorizado',
                'image_url': deteccion.imagen_url
            }

        except Exception as e:
            logger.error(f"Error creando resultado de detección: {e}")
            return {
                'id': None,
                'plate': plate,
                'is_authorized': False,
                'vehicle': None,
                'confidence': 0.0,
                'timestamp': None,
                'camera_location': camera_location,
                'access_type': access_type,
                'status': 'error',
                'image_url': None
            }

    def _base64_to_image(self, base64_string: str) -> Optional[np.ndarray]:
        """Convierte base64 a imagen numpy"""
        try:
            if base64_string.startswith('data:image'):
                base64_string = base64_string.split(',', 1)[1]

            image_data = base64.b64decode(base64_string)
            image = Image.open(io.BytesIO(image_data))

            if image.mode != 'RGB':
                image = image.convert('RGB')

            return np.array(image)

        except Exception as e:
            logger.error(f"Error convirtiendo base64 a imagen: {e}")
            return None
