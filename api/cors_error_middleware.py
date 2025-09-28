"""
Middleware para asegurar que las cabeceras CORS se envíen incluso con errores 500
"""
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
import logging

logger = logging.getLogger(__name__)

class CORSErrorMiddleware(MiddlewareMixin):
    """
    Middleware que asegura que las cabeceras CORS se envíen incluso cuando hay errores 500
    """

    def process_response(self, request, response):
        """Agrega cabeceras CORS a todas las respuestas, incluyendo errores"""
        if hasattr(request, 'META') and 'HTTP_ORIGIN' in request.META:
            origin = request.META['HTTP_ORIGIN']

            # Lista de orígenes permitidos
            allowed_origins = [
                'https://si-2-test1-app.vercel.app',
                'http://localhost:5173',
                'http://localhost:3000'
            ]

            if origin in allowed_origins:
                response['Access-Control-Allow-Origin'] = origin
                response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'authorization, content-type, x-csrftoken, x-requested-with, accept, origin, user-agent'
                response['Access-Control-Allow-Credentials'] = 'true'
                response['Access-Control-Max-Age'] = '86400'

        return response

    def process_exception(self, request, exception):
        """
        Procesa excepciones y devuelve una respuesta JSON con cabeceras CORS
        """
        logger.error(f"Error 500 interceptado: {exception}")

        # Crear respuesta JSON de error
        response = JsonResponse({
            'error': 'Error interno del servidor',
            'detail': 'Error de conexión a la base de datos. Por favor, inténtalo de nuevo.',
            'status': 500
        }, status=500)

        # Agregar cabeceras CORS
        if hasattr(request, 'META') and 'HTTP_ORIGIN' in request.META:
            origin = request.META['HTTP_ORIGIN']
            allowed_origins = [
                'https://si-2-test1-app.vercel.app',
                'http://localhost:5173',
                'http://localhost:3000'
            ]

            if origin in allowed_origins:
                response['Access-Control-Allow-Origin'] = origin
                response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'authorization, content-type, x-csrftoken, x-requested-with, accept, origin, user-agent'
                response['Access-Control-Allow-Credentials'] = 'true'
                response['Access-Control-Max-Age'] = '86400'

        return response
