"""
Middleware para manejar reconexiones automáticas con el Transaction Pooler de Supabase
"""
import logging
from django.db import connection
from django.http import JsonResponse
import psycopg2

logger = logging.getLogger(__name__)

class DatabaseReconnectionMiddleware:
    """
    Middleware que maneja reconexiones automáticas cuando se pierden las conexiones
    con el transaction pooler de Supabase
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Lista de errores que indican pérdida de conexión
        self.connection_errors = [
            'server closed the connection unexpectedly',
            'connection to server at',
            'could not connect to server',
            'timeout expired',
            'connection refused',
            'no connection to the server'
        ]

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except Exception as e:
            # Si hay un error de conexión a la base de datos, intentar reconectar
            if self._is_connection_error(str(e).lower()):
                logger.warning(f"Detectado error de conexión: {e}")

                # Cerrar la conexión actual
                try:
                    connection.close()
                    logger.info("Conexión cerrada, intentando reconectar...")
                except:
                    pass

                # Intentar la petición una vez más
                try:
                    response = self.get_response(request)
                    logger.info("Reconexión exitosa")
                    return response
                except Exception as retry_error:
                    logger.error(f"Error después de reintento: {retry_error}")
                    return JsonResponse({
                        'error': 'Error de conexión a la base de datos',
                        'detail': 'Por favor, inténtalo de nuevo en unos segundos'
                    }, status=503)

            # Re-lanzar la excepción si no es un error de conexión
            raise e

    def _is_connection_error(self, error_message):
        """Verifica si el error es relacionado con conexión de base de datos"""
        return any(error_keyword in error_message for error_keyword in self.connection_errors)

    def process_exception(self, request, exception):
        """Procesar excepciones relacionadas con la base de datos"""
        if isinstance(exception, (psycopg2.OperationalError, psycopg2.InterfaceError)):
            logger.warning(f"Error de base de datos capturado: {exception}")

            # Cerrar conexión
            try:
                connection.close()
            except:
                pass

            return JsonResponse({
                'error': 'Error temporal de base de datos',
                'detail': 'El servicio se está reconectando, inténtalo de nuevo'
            }, status=503)

        return None
