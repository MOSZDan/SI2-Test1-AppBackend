from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from api.views import ComprobantePDFView

def api_status(request):
    """Vista simple para la ruta raíz que confirma que la API está funcionando"""
    return JsonResponse({
        "message": "Condominium API is running",
        "status": "OK",
        "version": "1.0.0",
        "endpoints": {
            "api": "/api/",
            "admin": "/admin/",
            "auth": {
                "login": "/api/auth/login/",
                "register": "/api/auth/register/",
                "logout": "/api/auth/logout/"
            }
        }
    })

urlpatterns = [
    path('', api_status, name='api-status'),  # Ruta raíz
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),   # <--- monta todos los endpoints
    path('api/comprobante/<int:pk>/', ComprobantePDFView.as_view(), name='comprobante-pdf'),
]
