"""
Middleware simple para cerrar conexiones después de cada request
Específico para transaction pooler de Supabase
"""
from django.db import connection

class ForceConnectionCloseMiddleware:
    """
    Cierra la conexión de BD después de cada request
    Ideal para transaction pooler que no maneja bien conexiones persistentes
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Cerrar conexión después de cada request
        try:
            connection.close()
        except:
            pass  # Ignorar errores al cerrar

        return response
