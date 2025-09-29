from decimal import Decimal
from django.http import FileResponse, Http404
from rest_framework import viewsets, permissions
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from django.utils import timezone
from datetime import timedelta
from .services.ai_detection import FacialRecognitionService, PlateDetectionService
from .services.supabase_storage import SupabaseStorageService
import logging
from rest_framework.parsers import MultiPartParser, FormParser
import traceback
from datetime import date
from django.db import models
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from datetime import datetime, timedelta
from django.db.models import Q, Sum
from .services.avisos import publicar_comunicado_y_notificar

from .models import (
    Rol, Usuario, Propiedad, Multa, Pagos, Notificaciones, AreasComunes, Tareas,
    Vehiculo, Pertenece, ListaVisitantes, DetalleMulta, Factura, Finanzas,
    Comunicados, Horarios, Reserva, Asignacion, Envio, Registro, Bitacora,
    PerfilFacial, ReconocimientoFacial, DeteccionPlaca, ReporteSeguridad
)
from .serializers import (
    RolSerializer, UsuarioSerializer, PropiedadSerializer, MultaSerializer,
    PagoSerializer, NotificacionesSerializer, AreasComunesSerializer, TareasSerializer,
    VehiculoSerializer, PerteneceSerializer, ListaVisitantesSerializer, DetalleMultaSerializer,
    FacturaSerializer, FinanzasSerializer, ComunicadosSerializer, HorariosSerializer,
    ReservaSerializer, AsignacionSerializer, EnvioSerializer, RegistroSerializer,
    BitacoraSerializer, ReconocimientoFacialSerializer, PerfilFacialSerializer, DeteccionPlacaSerializer,
    ReporteSeguridadSerializer, EstadoCuentaSerializer, PagoRealizadoSerializer,
    PublicarComunicadoSerializer, ReservaCreateSerializer, ReservaCancelarSerializer, ReservaReprogramarSerializer,
)


# ---------------------------------------------------------------------
# Base genérica: agrega filtros, búsqueda y ordenamiento a todos
# ---------------------------------------------------------------------
class BaseModelViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    # Cada viewset define: queryset, serializer_class, filterset_fields, search_fields, ordering_fields


# ---------------------------------------------------------------------
# Catálogos / tablas simples
# ---------------------------------------------------------------------
class RolViewSet(BaseModelViewSet):
    queryset = Rol.objects.all().order_by('id')
    serializer_class = RolSerializer
    filterset_fields = ['tipo', 'estado']
    search_fields = ['descripcion', 'tipo', 'estado']
    ordering_fields = ['id', 'tipo', 'estado']


class PropiedadViewSet(BaseModelViewSet):
    queryset = Propiedad.objects.all().order_by('nro_casa', 'piso')
    serializer_class = PropiedadSerializer
    filterset_fields = ['nro_casa', 'piso', 'descripcion']
    search_fields = ['descripcion', 'nro_casa']
    ordering_fields = ['codigo', 'nro_casa', 'piso', 'tamano_m2']

    def get_queryset(self):
        queryset = super().get_queryset()

        # Si se solicita incluir información de residentes
        if self.request.query_params.get('include_residents') == 'true':
            queryset = queryset.prefetch_related('pertenentes__codigo_usuario__idrol')

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            propiedades_data = self._serialize_propiedades_with_residents(page)
            return self.get_paginated_response(propiedades_data)

        propiedades_data = self._serialize_propiedades_with_residents(queryset)
        return Response(propiedades_data)

    def create(self, request, *args, **kwargs):
        # (opcional) pre-chequeo amigable antes de ir a BD
        nro_casa = request.data.get('nro_casa')
        piso = request.data.get('piso', 0)
        if nro_casa is not None and piso is not None:
            if Propiedad.objects.filter(nro_casa=nro_casa, piso=piso).exists():
                return Response(
                    {'detail': f'Ya existe una unidad con número {nro_casa} en piso {piso}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Bitácora (tu lógica existente)
        try:
            usuario = Usuario.objects.get(correo=request.user.email)
            Bitacora.objects.create(
                codigo_usuario=usuario,
                accion=f"Creación de unidad habitacional {nro_casa}",
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=self._get_client_ip(request)
            )
        except Usuario.DoesNotExist:
            pass

        # Intento real de creación (atrapa la UNIQUE constraint)
        try:
            with transaction.atomic():
                return super().create(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {"detail": "La unidad ya existe (NroCasa + Piso)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        # (opcional) pre-chequeo amigable antes de ir a BD
        nro_casa = request.data.get("nro_casa", instance.nro_casa)
        piso = request.data.get("piso", instance.piso if instance.piso is not None else 0)
        if (
                nro_casa is not None
                and piso is not None
                and Propiedad.objects.filter(nro_casa=nro_casa, piso=piso)
                .exclude(pk=instance.pk)
                .exists()
        ):
            return Response(
                {"detail": f"Ya existe una unidad con número {nro_casa} en piso {piso}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Bitácora (tu lógica existente)
        try:
            usuario = Usuario.objects.get(correo=request.user.email)
            Bitacora.objects.create(
                codigo_usuario=usuario,
                accion=f"Edición de unidad habitacional {instance.nro_casa}",
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=self._get_client_ip(request)
            )
        except Usuario.DoesNotExist:
            pass

        # Intento real de actualización (atrapa la UNIQUE constraint)
        try:
            with transaction.atomic():
                return super().update(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {"detail": "La unidad ya existe (NroCasa + Piso)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    def _serialize_propiedades_with_residents(self, propiedades):
        """Serializa propiedades incluyendo información del residente actual"""
        result = []

        for propiedad in propiedades:
            # Datos básicos de la propiedad
            prop_data = PropiedadSerializer(propiedad).data

            # Buscar residente actual (sin fecha_fin o fecha_fin futura)
            residente_actual = None

            # Obtener la vinculación más reciente que esté activa
            vinculacion_activa = Pertenece.objects.filter(
                codigo_propiedad=propiedad,
                fecha_ini__lte=date.today()
            ).filter(
                models.Q(fecha_fin__isnull=True) | models.Q(fecha_fin__gte=date.today())
            ).select_related('codigo_usuario__idrol').order_by('-fecha_ini').first()

            if vinculacion_activa and vinculacion_activa.codigo_usuario:
                usuario = vinculacion_activa.codigo_usuario
                residente_actual = {
                    'codigo': usuario.codigo,
                    'nombre': usuario.nombre,
                    'apellido': usuario.apellido,
                    'correo': usuario.correo,
                    'tipo_rol': usuario.idrol.descripcion if usuario.idrol else 'Sin rol',
                    'fecha_ini': vinculacion_activa.fecha_ini.isoformat(),
                    'fecha_fin': vinculacion_activa.fecha_fin.isoformat() if vinculacion_activa.fecha_fin else None
                }

            prop_data['propietario_actual'] = residente_actual
            result.append(prop_data)

        return result

    def _get_client_ip(self, request):
        """Obtiene la IP del cliente"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class BitacoraMixin:
    def _bitacora(self, request, accion: str):
        try:
            usuario = Usuario.objects.get(correo=getattr(request.user, "email", None))
            Bitacora.objects.create(
                codigo_usuario=usuario,
                accion=accion,
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=self._get_client_ip(request),
            )
        except Usuario.DoesNotExist:
            pass

    def _get_client_ip(self, request):
        xf = request.META.get("HTTP_X_FORWARDED_FOR")
        return xf.split(",")[0] if xf else request.META.get("REMOTE_ADDR")

class MultaViewSet(BitacoraMixin, viewsets.ModelViewSet):
    queryset = Multa.objects.all().order_by("descripcion")
    serializer_class = MultaSerializer
    search_fields = ["descripcion"]
    filterset_fields = (["estado"] if hasattr(Multa, "estado") else [])
    ordering_fields = ["id", "descripcion", "monto"]

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                resp = super().create(request, *args, **kwargs)
                self._bitacora(request, f"Alta de multa: {resp.data.get('descripcion')}")
                return resp
        except IntegrityError:
            # Por si luego agregas UNIQUE en descripcion
            return Response({"detail": "Ya existe una multa con esa descripción."}, status=400)

    def update(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                resp = super().update(request, *args, **kwargs)
                self._bitacora(request, f"Edición de multa: {resp.data.get('descripcion')}")
                return resp
        except IntegrityError:
            return Response({"detail": "Conflicto de BD al actualizar la multa."}, status=400)


class PagoViewSet(BitacoraMixin, viewsets.ModelViewSet):
    queryset = Pagos.objects.all().order_by("tipo", "descripcion")
    serializer_class = PagoSerializer
    search_fields = ["tipo", "descripcion"]
    filterset_fields = ["tipo"] + (["estado"] if hasattr(Pagos, "estado") else [])
    ordering_fields = ["id", "tipo", "descripcion", "monto"]

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                resp = super().create(request, *args, **kwargs)
                self._bitacora(request, f"Alta de pago: {resp.data.get('descripcion')}")
                return resp
        except IntegrityError:
            return Response({"detail": "No se pudo crear el pago (conflicto en BD)."}, status=400)

    def update(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                resp = super().update(request, *args, **kwargs)
                self._bitacora(request, f"Edición de pago: {resp.data.get('descripcion')}")
                return resp
        except IntegrityError:
            return Response({"detail": "No se pudo actualizar el pago (conflicto en BD)."}, status=400)



class NotificacionesViewSet(BaseModelViewSet):
    queryset = Notificaciones.objects.all().order_by('id')
    serializer_class = NotificacionesSerializer
    filterset_fields = ['tipo']
    search_fields = ['tipo', 'descripcion']
    ordering_fields = ['id']


class AreasComunesViewSet(BaseModelViewSet):
    queryset = AreasComunes.objects.all().order_by('id')
    serializer_class = AreasComunesSerializer
    filterset_fields = ['estado', 'capacidad_max', 'costo']
    search_fields = ['descripcion', 'estado']
    ordering_fields = ['id', 'capacidad_max', 'costo']

    def perform_create(self, serializer):
        area = serializer.save()
        # bitácora
        try:
            u = Usuario.objects.get(correo=self.request.user.email)
            Bitacora.objects.create(
                codigo_usuario=u,
                accion=f"Alta área común #{area.id} ({area.descripcion})",
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=self._get_client_ip(self.request),
            )
        except Usuario.DoesNotExist:
            pass

    def perform_update(self, serializer):
        before = self.get_object()
        was_active = (before.estado or "").strip().lower() == "activo"
        area = serializer.save()
        # bitácora
        try:
            u = Usuario.objects.get(correo=self.request.user.email)
            Bitacora.objects.create(
                codigo_usuario=u,
                accion=f"Edición área común #{area.id} ({area.descripcion})",
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=self._get_client_ip(self.request),
            )
        except Usuario.DoesNotExist:
            pass

        # Si la dejas inactiva/mantenimiento, advertimos si hay reservas futuras
        now_d = timezone.now().date()
        new_state = (area.estado or "").strip().lower()
        if new_state in ("inactivo", "mantenimiento") and was_active:
            afectadas = Reserva.objects.filter(id_area_c=area, fecha__gte=now_d).count()
            # No bloqueamos, solo avisamos en el payload de respuesta
            self.extra_warning = f"Área deshabilitada. Hay {afectadas} reserva(s) futura(s) que deberías revisar." if afectadas else None

    def update(self, request, *args, **kwargs):
        resp = super().update(request, *args, **kwargs)
        if hasattr(self, "extra_warning") and self.extra_warning:
            data = resp.data.copy()
            data["_warning"] = self.extra_warning
            return Response(data, status=resp.status_code)
        return resp

    def _get_client_ip(self, request):
        xf = request.META.get("HTTP_X_FORWARDED_FOR")
        return xf.split(",")[0] if xf else request.META.get("REMOTE_ADDR")

    # ---------- Acciones útiles sobre horarios del área ----------

    @action(detail=True, methods=['get'], url_path='horarios')
    def listar_horarios(self, request, pk=None):
        area = self.get_object()
        qs = Horarios.objects.filter(id_area_c=area).order_by('hora_ini')
        return Response(HorariosSerializer(qs, many=True).data, status=200)

    @action(detail=True, methods=['post'], url_path='horarios/agregar')
    def agregar_horario(self, request, pk=None):
        """
        Agrega UNA franja a esta área. Body:
        {
          "hora_ini": "09:00:00",
          "hora_fin": "10:00:00"
        }
        """
        area = self.get_object()
        data = request.data.copy()
        data["id_area_c"] = area.id
        ser = HorariosSerializer(data=data)
        ser.is_valid(raise_exception=True)
        item = ser.save()
        # bitácora
        try:
            u = Usuario.objects.get(correo=request.user.email)
            Bitacora.objects.create(
                codigo_usuario=u,
                accion=f"Alta horario {item.hora_ini}-{item.hora_fin} para área #{area.id}",
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=self._get_client_ip(request),
            )
        except Usuario.DoesNotExist:
            pass
        return Response(ser.data, status=201)

    @action(detail=True, methods=['post'], url_path='horarios/set')
    def set_horarios(self, request, pk=None):
        """
        Bulk ADD (no reemplaza). Body:
        {
          "intervalos": [
            {"hora_ini": "09:00:00", "hora_fin": "10:00:00"},
            {"hora_ini": "10:00:00", "hora_fin": "11:00:00"}
          ]
        }
        Valida solapes con existentes y entre sí.
        """
        area = self.get_object()
        intervalos = request.data.get("intervalos") or []
        if not isinstance(intervalos, list) or not intervalos:
            return Response({"detail": "intervalos debe ser una lista no vacía."}, status=400)

        # Validar entre sí
        def to_tuple(x):
            return x["hora_ini"], x["hora_fin"]
        try:
            new_sorted = sorted(intervalos, key=lambda x: x["hora_ini"])
            for i in range(len(new_sorted)):
                a_ini, a_fin = to_tuple(new_sorted[i])
                if a_fin <= a_ini:
                    return Response({"detail": f"Intervalo inválido: {a_ini}-{a_fin}."}, status=400)
                for j in range(i+1, len(new_sorted)):
                    b_ini, b_fin = to_tuple(new_sorted[j])
                    # solape si a_ini < b_fin y a_fin > b_ini
                    if a_ini < b_fin and a_fin > b_ini:
                        return Response({"detail": f"Solape entre {a_ini}-{a_fin} y {b_ini}-{b_fin}."}, status=400)
        except Exception:
            return Response({"detail": "Formato de intervalos inválido (use 'HH:MM:SS')."}, status=400)

        # Validar contra existentes y persistir
        creados = []
        with transaction.atomic():
            existentes = Horarios.objects.filter(id_area_c=area)
            for it in new_sorted:
                h_ini = it["hora_ini"]
                h_fin = it["hora_fin"]
                conflict = existentes.filter(hora_ini__lt=h_fin, hora_fin__gt=h_ini).exists()
                if conflict:
                    raise IntegrityError(f"Solape con horario existente para {h_ini}-{h_fin}.")
                ser = HorariosSerializer(data={"id_area_c": area.id, "hora_ini": h_ini, "hora_fin": h_fin})
                ser.is_valid(raise_exception=True)
                item = ser.save()
                creados.append(item)

        # bitácora
        try:
            u = Usuario.objects.get(correo=request.user.email)
            Bitacora.objects.create(
                codigo_usuario=u,
                accion=f"Alta masiva de {len(creados)} horario(s) para área #{area.id}",
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=self._get_client_ip(request),
            )
        except Usuario.DoesNotExist:
            pass

        return Response(HorariosSerializer(creados, many=True).data, status=201)

class TareasViewSet(BaseModelViewSet):
    queryset = Tareas.objects.all().order_by('id')
    serializer_class = TareasSerializer
    filterset_fields = ['tipo', 'vigencia', 'costos']
    search_fields = ['tipo', 'descripcion']
    ordering_fields = ['id', 'vigencia', 'costos']


class VehiculoViewSet(BaseModelViewSet):
    queryset = Vehiculo.objects.all().order_by('id')
    serializer_class = VehiculoSerializer
    filterset_fields = ['estado', 'nroplaca']
    search_fields = ['nroplaca', 'descripcion', 'estado']
    ordering_fields = ['id']


# ---------------------------------------------------------------------
# Entidades con FK
# ---------------------------------------------------------------------
class UsuarioViewSet(BaseModelViewSet):
    queryset = Usuario.objects.all().order_by('codigo')
    serializer_class = UsuarioSerializer
    filterset_fields = ['idrol', 'sexo', 'estado', 'correo', 'telefono']
    search_fields = ['nombre', 'apellido', 'correo', 'estado']
    ordering_fields = ['codigo', 'telefono']


class PerteneceViewSet(BaseModelViewSet):
    queryset = Pertenece.objects.all().order_by('-fecha_ini')
    serializer_class = PerteneceSerializer
    filterset_fields = ['codigo_usuario', 'codigo_propiedad', 'fecha_ini', 'fecha_fin']
    search_fields = []
    ordering_fields = ['id', 'fecha_ini', 'fecha_fin']

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filtro para obtener solo vinculaciones activas
        if self.request.query_params.get('activas') == 'true':
            queryset = queryset.filter(
                fecha_ini__lte=date.today()
            ).filter(
                models.Q(fecha_fin__isnull=True) | models.Q(fecha_fin__gte=date.today())
            )

        return queryset

    def create(self, request, *args, **kwargs):
        codigo_usuario = request.data.get('codigo_usuario')
        codigo_propiedad = request.data.get('codigo_propiedad')
        fecha_ini = request.data.get('fecha_ini')
        fecha_fin = request.data.get('fecha_fin')

        # Validaciones
        if not codigo_usuario or not codigo_propiedad or not fecha_ini:
            return Response(
                {'detail': 'Usuario, propiedad y fecha de inicio son obligatorios'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar que el usuario existe y está activo
        try:
            usuario = Usuario.objects.get(codigo=codigo_usuario, estado='activo')
            if usuario.idrol_id not in [1, 2]:  # Solo copropietarios e inquilinos
                return Response(
                    {'detail': 'Solo se pueden vincular copropietarios e inquilinos'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Usuario.DoesNotExist:
            return Response(
                {'detail': 'Usuario no encontrado o inactivo'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verificar que la propiedad existe
        try:
            propiedad = Propiedad.objects.get(codigo=codigo_propiedad)
        except Propiedad.DoesNotExist:
            return Response(
                {'detail': 'Propiedad no encontrada'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verificar fechas
        from datetime import datetime
        fecha_ini_date = datetime.strptime(fecha_ini, '%Y-%m-%d').date()

        if fecha_fin:
            fecha_fin_date = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
            if fecha_fin_date <= fecha_ini_date:
                return Response(
                    {'detail': 'La fecha de fin debe ser posterior a la fecha de inicio'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Verificar que no haya vinculaciones conflictivas
        # (mismo usuario con otra propiedad activa, o misma propiedad con otro usuario activo)

        # Conflicto: usuario ya vinculado a otra propiedad activa
        conflicto_usuario = Pertenece.objects.filter(
            codigo_usuario=usuario,
            fecha_ini__lte=fecha_ini_date
        ).filter(
            models.Q(fecha_fin__isnull=True) | models.Q(fecha_fin__gte=fecha_ini_date)
        ).exclude(codigo_propiedad=propiedad).exists()

        if conflicto_usuario:
            return Response(
                {'detail': 'El usuario ya está vinculado a otra propiedad en el período especificado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Conflicto: propiedad ya vinculada a otro usuario activo
        conflicto_propiedad = Pertenece.objects.filter(
            codigo_propiedad=propiedad,
            fecha_ini__lte=fecha_ini_date
        ).filter(
            models.Q(fecha_fin__isnull=True) | models.Q(fecha_fin__gte=fecha_ini_date)
        ).exclude(codigo_usuario=usuario).exists()

        if conflicto_propiedad:
            return Response(
                {'detail': 'La propiedad ya está vinculada a otro usuario en el período especificado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Registrar en bitácora
        try:
            admin_usuario = Usuario.objects.get(correo=request.user.email)
            Bitacora.objects.create(
                codigo_usuario=admin_usuario,
                accion=f"Vinculación de {usuario.nombre} {usuario.apellido} a unidad {propiedad.nro_casa}",
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=self._get_client_ip(request)
            )
        except Usuario.DoesNotExist:
            pass

        return super().create(request, *args, **kwargs)

    def _get_client_ip(self, request):
        """Obtiene la IP del cliente"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class ListaVisitantesViewSet(BaseModelViewSet):
    queryset = ListaVisitantes.objects.all().order_by('id')
    serializer_class = ListaVisitantesSerializer
    filterset_fields = ['codigopropiedad', 'fechaini', 'fechafin', 'carnet']
    search_fields = ['nombre', 'apellido', 'carnet', 'motivovisita']
    ordering_fields = ['id', 'fechaini', 'fechafin']


class DetalleMultaViewSet(BaseModelViewSet):
    queryset = DetalleMulta.objects.all().order_by('id')
    serializer_class = DetalleMultaSerializer
    filterset_fields = ['codigo_propiedad', 'idmulta', 'fechaemi', 'fechalim']
    search_fields = []
    ordering_fields = ['id', 'fechaemi', 'fechalim']


class FacturaViewSet(BaseModelViewSet):
    queryset = Factura.objects.all().order_by('id')
    serializer_class = FacturaSerializer
    filterset_fields = ['codigousuario', 'idpago', 'fecha', 'estado', 'tipopago']
    search_fields = ['estado', 'tipopago']
    ordering_fields = ['id', 'fecha']


class FinanzasViewSet(BaseModelViewSet):
    queryset = Finanzas.objects.all().order_by('id')
    serializer_class = FinanzasSerializer
    filterset_fields = ['tipo', 'fecha', 'origen', 'idfactura']
    search_fields = ['tipo', 'descripcion', 'origen']
    ordering_fields = ['id', 'fecha', 'monto']


class ComunicadosViewSet(BaseModelViewSet):
    queryset = Comunicados.objects.all().order_by('id')
    serializer_class = ComunicadosSerializer
    # OJO: el campo es 'codigo_usuario' (tu modelo), no 'codigousuario'
    filterset_fields = ['tipo', 'fecha', 'estado', 'codigo_usuario']
    search_fields = ['titulo', 'contenido', 'url', 'tipo', 'estado']
    ordering_fields = ['id', 'fecha']

    @action(detail=False, methods=['post'], url_path='publicar', permission_classes=[IsAuthenticated])
    def publicar(self, request):
        s = PublicarComunicadoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        # Admin por email autenticado
        try:
            admin = Usuario.objects.get(correo=request.user.email)
        except Usuario.DoesNotExist:
            return Response({"detail": "Admin no encontrado"}, status=404)

        now = timezone.localtime()
        fecha_pub = data.get("fecha_publicacion") or now.date()
        hora_pub  = data.get("hora_publicacion")  or now.time()

        try:
            comunicado, stats = publicar_comunicado_y_notificar(
                admin=admin,
                titulo=data["titulo"],
                contenido=data["contenido"],
                prioridad=data["prioridad"],
                destinatarios=data["destinatarios"],  # incluye "todos"
                fecha_pub=fecha_pub,
                hora_pub=hora_pub,
                usuario_ids=data.get("usuario_ids"),
            )
        except Exception as e:
            return Response({"detail": "Error al publicar en la base de datos.", "error": str(e)},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        body = {
            "comunicado": ComunicadosSerializer(comunicado).data,
            "envio": stats,
            "mensaje": "Publicado y notificado." if stats["errores"] == 0 else
                       "Publicado con errores de envío.",
        }
        return Response(body, status=200)


class HorariosViewSet(BaseModelViewSet):
    queryset = Horarios.objects.all().order_by('id')
    serializer_class = HorariosSerializer
    filterset_fields = ['id_area_c', 'hora_ini', 'hora_fin']
    search_fields = []
    ordering_fields = ['id', 'hora_ini', 'hora_fin']

    def perform_create(self, serializer):
        item = serializer.save()
        try:
            u = Usuario.objects.get(correo=self.request.user.email)
            Bitacora.objects.create(
                codigo_usuario=u,
                accion=f"Alta horario {item.hora_ini}-{item.hora_fin} en área #{item.id_area_c_id}",
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=self._get_client_ip(self.request),
            )
        except Usuario.DoesNotExist:
            pass

    def perform_update(self, serializer):
        before = self.get_object()
        item = serializer.save()
        try:
            u = Usuario.objects.get(correo=self.request.user.email)
            Bitacora.objects.create(
                codigo_usuario=u,
                accion=f"Edición horario #{item.id} ({before.hora_ini}-{before.hora_fin} -> {item.hora_ini}-{item.hora_fin})",
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=self._get_client_ip(self.request),
            )
        except Usuario.DoesNotExist:
            pass

    def _get_client_ip(self, request):
        xf = request.META.get("HTTP_X_FORWARDED_FOR")
        return xf.split(",")[0] if xf else request.META.get("REMOTE_ADDR")

class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.all().order_by("id")
    serializer_class = ReservaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["codigousuario", "idareac", "fecha", "estado"]
    search_fields = ["estado"]
    ordering_fields = ["id", "fecha", "horaini", "horafin"]

    # ---------- Helpers ----------
    def _user_catalog(self, request) -> Usuario:
        return Usuario.objects.get(correo=request.user.email)

    def _has_active_tenancy(self, usuario: Usuario) -> bool:
        today = timezone.localdate()
        return Pertenece.objects.filter(
            codigo_usuario=usuario,
            fecha_ini__lte=today
        ).filter(
            models.Q(fecha_fin__isnull=True) | models.Q(fecha_fin__gte=today)
        ).exists()

    def _area_is_active(self, area: AreasComunes) -> bool:
        return (area.estado or "").strip().lower() == "activo"

    @staticmethod
    def _overlaps(a_ini, a_fin, b_ini, b_fin) -> bool:
        # [a_ini, a_fin) vs [b_ini, b_fin)
        return a_ini < b_fin and a_fin > b_ini

    @staticmethod
    def _parse_date_ymd(s: str):
        return datetime.strptime(s, "%Y-%m-%d").date()

    # ---------- Disponibilidad (con "libres") ----------
    @action(detail=False, methods=["get"], url_path="disponibilidad", permission_classes=[IsAuthenticated])
    def disponibilidad(self, request):
        """
        GET /api/reservas/disponibilidad/?idareac=1&fecha=YYYY-MM-DD
        Devuelve: horarios configurados, reservas ocupadas y franjas libres calculadas.
        """
        idareac = request.query_params.get("idareac")
        fecha_str = request.query_params.get("fecha")
        if not idareac or not fecha_str:
            return Response({"detail": "idareac y fecha son requeridos."}, status=400)
        try:
            id_area = int(idareac)
            fecha = self._parse_date_ymd(fecha_str)
        except Exception:
            return Response({"detail": "Parámetros inválidos. Formato fecha: YYYY-MM-DD."}, status=400)

        try:
            area = AreasComunes.objects.get(pk=id_area)
        except AreasComunes.DoesNotExist:
            return Response({"detail": "Área no encontrada."}, status=404)

        horarios = Horarios.objects.filter(id_area_c=area).order_by("hora_ini")
        horarios_ser = HorariosSerializer(horarios, many=True).data

        ocupadas = list(
            Reserva.objects.filter(idareac=area, fecha=fecha)
            .exclude(estado__iexact="cancelada")
            .values("id", "horaini", "horafin", "estado")
        )

        def restar_francas(base: list[tuple], taken: list[tuple]) -> list[tuple]:
            libres = []
            for b_ini, b_fin in base:
                segmentos = [(b_ini, b_fin)]
                for t_ini, t_fin in taken:
                    nuevos = []
                    for s_ini, s_fin in segmentos:
                        if not (s_ini < t_fin and s_fin > t_ini):
                            nuevos.append((s_ini, s_fin))
                            continue
                        if t_ini > s_ini:
                            nuevos.append((s_ini, min(t_ini, s_fin)))
                        if t_fin < s_fin:
                            nuevos.append((max(t_fin, s_ini), s_fin))
                    segmentos = [(a, b) for (a, b) in nuevos if a < b]
                libres.extend(segmentos)
            libres.sort(key=lambda x: x[0])
            return libres

        base = [(h.hora_ini, h.hora_fin) for h in horarios]
        taken = [(r["horaini"], r["horafin"]) for r in ocupadas]
        libres = restar_francas(base, taken)
        libres_ser = [{"hora_ini": li, "hora_fin": lf} for (li, lf) in libres]

        return Response({
            "area": {"id": area.id, "descripcion": area.descripcion, "estado": area.estado},
            "fecha": fecha_str,
            "horarios": horarios_ser,
            "ocupadas": ocupadas,
            "libres": libres_ser,
        }, status=200)

    # ---------- Crear (confirmar reserva) ----------
    def create(self, request, *args, **kwargs):
        payload = ReservaCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        try:
            usuario = self._user_catalog(request)
        except Usuario.DoesNotExist:
            return Response({"detail": "Usuario no registrado en catálogo."}, status=400)

        if not self._has_active_tenancy(usuario):
            return Response({"detail": "No tienes una unidad habitacional activa vinculada."}, status=403)

        try:
            area = AreasComunes.objects.get(pk=data["idareac"])
        except AreasComunes.DoesNotExist:
            return Response({"detail": "Área no encontrada."}, status=404)

        if not self._area_is_active(area):
            return Response({"detail": "Área no disponible (inactiva/mantenimiento)."}, status=400)

        if data["fecha"] < timezone.localdate():
            return Response({"detail": "La fecha debe ser hoy o futura."}, status=400)

        franjas = Horarios.objects.filter(id_area_c=area)
        if not franjas.exists():
            return Response({"detail": "El área no tiene horarios configurados."}, status=400)

        if not any(h.hora_ini <= data["hora_ini"] and data["hora_fin"] <= h.hora_fin for h in franjas):
            return Response({"detail": "El rango solicitado no cae dentro de los horarios del área."}, status=400)

        conflictos = Reserva.objects.filter(
            idareac=area, fecha=data["fecha"]
        ).exclude(estado__iexact="cancelada")

        for r in conflictos:
            if self._overlaps(data["hora_ini"], data["hora_fin"], r.horaini, r.horafin):
                return Response({"detail": "Horario no disponible (solapa con otra reserva)."}, status=409)

        with transaction.atomic():
            res = Reserva.objects.create(
                codigousuario=usuario,
                idareac=area,
                fecha=data["fecha"],
                horaini=data["hora_ini"],
                horafin=data["hora_fin"],
                estado="confirmada",
            )
            try:
                Bitacora.objects.create(
                    codigo_usuario=usuario,
                    accion=f"Reserva confirmada área #{area.id} {area.descripcion} {data['fecha']} {data['hora_ini']}-{data['hora_fin']}",
                    fecha=timezone.now().date(),
                    hora=timezone.now().time(),
                    ip=request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or request.META.get("REMOTE_ADDR"),
                )
            except Exception:
                pass

        return Response(ReservaSerializer(res).data, status=201)

    # ---------- PATCH /reservas/<id>/ (parcial) ----------
    def partial_update(self, request, *args, **kwargs):
        """
        Permite actualizar parcial: fecha, hora_ini, hora_fin.
        Repite validaciones básicas y de solape.
        """
        try:
            usuario = self._user_catalog(request)
        except Usuario.DoesNotExist:
            return Response({"detail": "Usuario no registrado en catálogo."}, status=400)

        try:
            res = Reserva.objects.select_related("idareac", "codigousuario").get(pk=kwargs["pk"])
        except Reserva.DoesNotExist:
            return Response({"detail": "Reserva no encontrada."}, status=404)

        if res.codigousuario != usuario and not request.user.is_staff:
            return Response({"detail": "No puedes editar esta reserva."}, status=403)

        # Validar payload parcial
        payload = ReservaReprogramarSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        # Determinar valores finales propuestos (lo que ya tiene + lo que viene)
        nueva_fecha = data.get("fecha", res.fecha)
        nueva_hini  = data.get("hora_ini", res.horaini)
        nueva_hfin  = data.get("hora_fin", res.horafin)

        # Reglas
        if nueva_fecha < timezone.localdate():
            return Response({"detail": "La fecha debe ser hoy o futura."}, status=400)

        area = res.idareac
        if not self._area_is_active(area):
            return Response({"detail": "Área no disponible (inactiva/mantenimiento)."}, status=400)

        franjas = Horarios.objects.filter(id_area_c=area)
        if not franjas.exists():
            return Response({"detail": "El área no tiene horarios configurados."}, status=400)

        if not any(h.hora_ini <= nueva_hini and nueva_hfin <= h.hora_fin for h in franjas):
            return Response({"detail": "El rango solicitado no cae dentro de los horarios del área."}, status=400)

        # Solapes (excluyéndose a sí misma)
        conflictos = Reserva.objects.filter(
            idareac=area, fecha=nueva_fecha
        ).exclude(estado__iexact="cancelada").exclude(pk=res.pk)

        for r in conflictos:
            if self._overlaps(nueva_hini, nueva_hfin, r.horaini, r.horafin):
                return Response({"detail": "Horario no disponible (solapa con otra reserva)."}, status=409)

        # Guardar cambios reales solo de los campos enviados
        campos = []
        if "fecha" in data:
            res.fecha = nueva_fecha
            campos.append("fecha")
        if "hora_ini" in data:
            res.horaini = nueva_hini
            campos.append("horaini")
        if "hora_fin" in data:
            res.horafin = nueva_hfin
            campos.append("horafin")

        if campos:
            res.estado = "confirmada"
            campos.append("estado")
            res.save(update_fields=campos)

            try:
                Bitacora.objects.create(
                    codigo_usuario=usuario,
                    accion=f"Edición (PATCH) reserva #{res.id} -> {res.fecha} {res.horaini}-{res.horafin}",
                    fecha=timezone.now().date(),
                    hora=timezone.now().time(),
                    ip=request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or request.META.get("REMOTE_ADDR"),
                )
            except Exception:
                pass

        return Response(ReservaSerializer(res).data, status=200)

    # ---------- Mis reservas ----------
    @action(detail=False, methods=["get"], url_path="mias", permission_classes=[IsAuthenticated])
    def mias(self, request):
        try:
            usuario = self._user_catalog(request)
        except Usuario.DoesNotExist:
            return Response({"detail": "Usuario no registrado en catálogo."}, status=400)

        qs = self.filter_queryset(
            self.get_queryset().filter(codigousuario=usuario).order_by("-fecha", "-horaini")
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(ReservaSerializer(page, many=True).data)
        return Response(ReservaSerializer(qs, many=True).data, status=200)

    # ---------- Cancelar ----------
    @action(detail=True, methods=["post"], url_path="cancelar", permission_classes=[IsAuthenticated])
    def cancelar(self, request, pk=None):
        try:
            usuario = self._user_catalog(request)
        except Usuario.DoesNotExist:
            return Response({"detail": "Usuario no registrado en catálogo."}, status=400)

        try:
            res = Reserva.objects.get(pk=pk)
        except Reserva.DoesNotExist:
            return Response({"detail": "Reserva no encontrada."}, status=404)

        if res.codigousuario != usuario and not request.user.is_staff:
            return Response({"detail": "No puedes cancelar esta reserva."}, status=403)

        if (res.estado or "").lower() == "cancelada":
            return Response({"detail": "La reserva ya está cancelada."}, status=400)

        # (opcional) validar payload si mandas motivo
        _ = ReservaCancelarSerializer(data=request.data)
        _.is_valid(raise_exception=False)

        res.estado = "cancelada"
        res.save(update_fields=["estado"])

        try:
            Bitacora.objects.create(
                codigo_usuario=usuario,
                accion=f"Cancelación de reserva #{res.id}",
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or request.META.get("REMOTE_ADDR"),
            )
        except Exception:
            pass

        return Response({"detail": "Reserva cancelada."}, status=200)

    # ---------- Reprogramar (POST /reservas/<id>/reprogramar/) ----------
    @action(detail=True, methods=["post"], url_path="reprogramar", permission_classes=[IsAuthenticated])
    def reprogramar(self, request, pk=None):
        payload = ReservaReprogramarSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        try:
            usuario = self._user_catalog(request)
        except Usuario.DoesNotExist:
            return Response({"detail": "Usuario no registrado en catálogo."}, status=400)

        try:
            res = Reserva.objects.select_related("idareac").get(pk=pk)
        except Reserva.DoesNotExist:
            return Response({"detail": "Reserva no encontrada."}, status=404)

        if res.codigousuario != usuario and not request.user.is_staff:
            return Response({"detail": "No puedes reprogramar esta reserva."}, status=403)

        area = res.idareac
        if not self._area_is_active(area):
            return Response({"detail": "Área no disponible (inactiva/mantenimiento)."}, status=400)

        if data["fecha"] < timezone.localdate():
            return Response({"detail": "La fecha debe ser hoy o futura."}, status=400)

        franjas = Horarios.objects.filter(id_area_c=area)
        if not franjas.exists():
            return Response({"detail": "El área no tiene horarios configurados."}, status=400)

        if not any(h.hora_ini <= data["hora_ini"] and data["hora_fin"] <= h.hora_fin for h in franjas):
            return Response({"detail": "El rango solicitado no cae dentro de los horarios del área."}, status=400)

        conflictos = Reserva.objects.filter(
            idareac=area, fecha=data["fecha"]
        ).exclude(estado__iexact="cancelada").exclude(pk=res.pk)

        for r in conflictos:
            if self._overlaps(data["hora_ini"], data["hora_fin"], r.horaini, r.horafin):
                return Response({"detail": "Horario no disponible (solapa con otra reserva)."}, status=409)

        res.horaini = data["hora_ini"]
        res.horafin = data["hora_fin"]
        res.fecha = data["fecha"]
        res.estado = "confirmada"
        res.save(update_fields=["horaini", "horafin", "fecha", "estado"])

        try:
            Bitacora.objects.create(
                codigo_usuario=usuario,
                accion=f"Reprogramación de reserva #{res.id} -> {data['fecha']} {data['hora_ini']}-{data['hora_fin']}",
                fecha=timezone.now().date(),
                hora=timezone.now().time(),
                ip=request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or request.META.get("REMOTE_ADDR"),
            )
        except Exception:
            pass

        return Response(ReservaSerializer(res).data, status=200)
class AsignacionViewSet(BaseModelViewSet):
    queryset = Asignacion.objects.all().order_by('id')
    serializer_class = AsignacionSerializer
    filterset_fields = ['codigousuario', 'idtarea', 'fechaini', 'fechafin', 'estado']
    search_fields = ['descripcion', 'dificultades', 'estado']
    ordering_fields = ['id', 'fechaini', 'fechafin', 'costo']


class EnvioViewSet(BaseModelViewSet):
    queryset = Envio.objects.all().order_by('id')
    serializer_class = EnvioSerializer
    filterset_fields = ['codigousuario', 'idnotific', 'fecha', 'estado']
    search_fields = ['estado']
    ordering_fields = ['id', 'fecha']


class RegistroViewSet(BaseModelViewSet):
    queryset = Registro.objects.all().order_by('id')
    serializer_class = RegistroSerializer
    filterset_fields = ['codigousuario', 'idvehic', 'fecha']
    search_fields = []
    ordering_fields = ['id', 'fecha', 'hora']


class BitacoraViewSet(BaseModelViewSet):
    queryset = Bitacora.objects.all().order_by('-fecha', '-hora')
    serializer_class = BitacoraSerializer
    filterset_fields = ['codigousuario', 'fecha', 'accion', 'ip']
    search_fields = ['accion', 'ip']
    ordering_fields = ['id', 'fecha', 'hora']


# CU01. Iniciar sesion
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]  # sin auth para poder loguear

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response({"detail": "email y password son requeridos."},
                            status=status.HTTP_400_BAD_REQUEST)

        # 1) Buscar en TU tabla Usuario
        try:
            u = Usuario.objects.get(correo=email)
        except Usuario.DoesNotExist:
            return Response({"detail": "Usuario no existe."}, status=status.HTTP_404_NOT_FOUND)

        # 2) Comparación simple (demo). En prod: NO uses texto plano.
        if u.contrasena != password:
            return Response({"detail": "Credenciales inválidas."}, status=status.HTTP_401_UNAUTHORIZED)

        # 3) Sincronizar/crear auth.User para usar TokenAuth
        dj_user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
        if not dj_user.has_usable_password() or not dj_user.check_password(password):
            dj_user.set_password(password)
            dj_user.save()

        # 4) Crear/obtener token
        token, _ = Token.objects.get_or_create(user=dj_user)

        # 5) Armar payload con datos del usuario (y rol)
        rol_obj = None
        if u.idrol:  # CORREGIDO: usar u.idrol en lugar de u.idrol_id
            try:
                r = u.idrol  # Usar la relación directa
                rol_obj = {
                    "id": r.id,
                    "descripcion": r.descripcion,
                    "tipo": r.tipo,
                    "estado": r.estado,
                }
            except Exception:
                pass

        return Response({
            "token": token.key,
            "user": {
                "codigo": u.codigo,
                "nombre": u.nombre,
                "apellido": u.apellido,
                "correo": u.correo,
                "sexo": u.sexo,
                "telefono": u.telefono,
                "estado": u.estado,
                "idrol": u.idrol.id if u.idrol else None,  # CORREGIDO
                "rol": rol_obj,
            }
        }, status=status.HTTP_200_OK)

# CU02. Registrarse en el sistema
class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data.copy()

        # Validaciones mínimas
        required = ["nombre", "apellido", "correo", "contrasena"]
        missing = [f for f in required if not data.get(f)]
        if missing:
            return Response(
                {"detail": f"Faltan campos requeridos: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ¿correo ya existe?
        if Usuario.objects.filter(correo=data["correo"]).exists():
            return Response(
                {"detail": "El correo ya está registrado."},
                status=status.HTTP_409_CONFLICT
            )

        # ---- Defaults solo si NO vienen desde el front ----
        # estado: si no viene o viene vacío => "pendiente"
        estado = (data.get("estado") or "").strip()
        if not estado:
            data["estado"] = "pendiente"

        # idrol: si no viene => 2
        if data.get("idrol") in [None, "", 0, "0"]:
            data["idrol"] = 2
        # (opcional) convertir a int si vino en string
        try:
            data["idrol"] = int(data["idrol"])
        except Exception:
            return Response({"detail": "idrol debe ser numérico."}, status=status.HTTP_400_BAD_REQUEST)

        # Crea Usuario con serializer general
        serializer = UsuarioSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        u = serializer.save()  # Usuario creado

        # Sincroniza auth.User (para emitir token y usar TokenAuth)
        dj_user, created = User.objects.get_or_create(
            username=u.correo,
            defaults={"email": u.correo, "first_name": u.nombre, "last_name": u.apellido},
        )
        dj_user.set_password(data["contrasena"])  # hash en Django
        dj_user.is_active = True
        dj_user.save()

        token, _ = Token.objects.get_or_create(user=dj_user)

        # Info de rol (si existe)
        rol_obj = None
        if u.idrol_id:
            try:
                r = Rol.objects.get(pk=u.idrol_id)
                rol_obj = {
                    "id": r.id,
                    "descripcion": r.descripcion,
                    "tipo": r.tipo,
                    "estado": r.estado,
                }
            except Rol.DoesNotExist:
                pass

        return Response({
            "token": token.key,
            "user": {
                "codigo": u.codigo,
                "nombre": u.nombre,
                "apellido": u.apellido,
                "correo": u.correo,
                "sexo": u.sexo,
                "telefono": u.telefono,
                "estado": u.estado,    # lo que mandó el front o "pendiente"
                "idrol": u.idrol_id,   # lo que mandó el front o 2
                "rol": rol_obj,
            }
        }, status=status.HTTP_201_CREATED)

# CU04. Cierre de sesion
class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # Si el cliente envía Authorization: Token <...>, DRF pone el token en request.auth
        all_sessions = bool(request.data.get("all", False))

        if all_sessions:
            Token.objects.filter(user=request.user).delete()
            detail = "Sesiones cerradas en todos los dispositivos."
        else:
            # Borra SOLO el token de esta sesión
            try:
                if request.auth:
                    request.auth.delete()
            except Exception:
                # si ya estaba borrado/no válido, seguimos devolviendo 200 para idempotencia
                pass
            detail = "Sesión cerrada."

        return Response({"detail": detail}, status=status.HTTP_200_OK)

# Agregar estos ViewSets al final de api/views.py, después de LogoutView y antes de AIDetectionViewSet:

class ReconocimientoFacialViewSet(BaseModelViewSet):
    queryset = ReconocimientoFacial.objects.all().order_by('-fecha_deteccion')
    serializer_class = ReconocimientoFacialSerializer
    filterset_fields = ['codigo_usuario', 'es_residente', 'ubicacion_camara', 'estado', 'fecha_deteccion']
    search_fields = ['ubicacion_camara', 'estado']
    ordering_fields = ['id', 'fecha_deteccion', 'confianza']


class DeteccionPlacaViewSet(BaseModelViewSet):
    queryset = DeteccionPlaca.objects.all().order_by('-fecha_deteccion')
    serializer_class = DeteccionPlacaSerializer
    filterset_fields = ['placa_detectada', 'vehiculo', 'es_autorizado', 'ubicacion_camara', 'tipo_acceso', 'fecha_deteccion']
    search_fields = ['placa_detectada', 'ubicacion_camara', 'tipo_acceso']
    ordering_fields = ['id', 'fecha_deteccion', 'confianza']


class PerfilFacialViewSet(BaseModelViewSet):
    queryset = PerfilFacial.objects.all().order_by('-fecha_registro')
    serializer_class = PerfilFacialSerializer
    filterset_fields = ['codigo_usuario', 'activo', 'fecha_registro']
    search_fields = ['codigo_usuario__nombre', 'codigo_usuario__apellido', 'codigo_usuario__correo']
    ordering_fields = ['id', 'fecha_registro']


class ReporteSeguridadViewSet(BaseModelViewSet):
    queryset = ReporteSeguridad.objects.all().order_by('-fecha_evento')
    serializer_class = ReporteSeguridadSerializer
    filterset_fields = ['tipo_evento', 'nivel_alerta', 'revisado', 'revisor', 'fecha_evento']
    search_fields = ['descripcion', 'tipo_evento', 'nivel_alerta']
    ordering_fields = ['id', 'fecha_evento', 'nivel_alerta']


logger = logging.getLogger(__name__)


class AIDetectionViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.facial_service = FacialRecognitionService()
        self.plate_service = PlateDetectionService()
        self.storage_service = SupabaseStorageService()

    # ============= RECONOCIMIENTO FACIAL =============
    @action(detail=False, methods=['post'])
    def recognize_face(self, request):
        try:
            # Obtener imagen del FormData
            image_file = request.FILES.get('image')
            camera_location = request.data.get('camera_location', 'Principal')

            if not image_file:
                return Response(
                    {'error': 'La imagen es requerida como archivo'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"Procesando reconocimiento facial - cámara: {camera_location}")

            # USAR EL NUEVO MÉTODO QUE MANEJA ARCHIVOS DIRECTAMENTE
            result = self.facial_service.recognize_face_from_file(image_file, camera_location)

            # Crear reporte de seguridad si es necesario
            if not result['is_resident']:
                ReporteSeguridad.objects.create(
                    tipo_evento='intruso_detectado',
                    reconocimiento_facial_id=result['id'],
                    descripcion=f"Persona no identificada detectada en {camera_location}",
                    nivel_alerta='alto'
                )

            logger.info(f"Reconocimiento completado - residente: {result['is_resident']}")
            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error en reconocimiento facial: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response(
                {'error': 'Error interno del servidor'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # ============= REGISTRO DE PERFILES FACIALES =============
    @action(detail=False, methods=['post'])
    def register_profile(self, request):
        """Registra un nuevo perfil facial para un usuario específico"""
        try:
            user_id = request.data.get('user_id')
            image_file = request.FILES.get('image')

            if not user_id or not image_file:
                return Response({
                    'success': False,
                    'error': 'user_id e imagen son requeridos'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Verificar que el usuario existe
            try:
                usuario = Usuario.objects.get(codigo=user_id)
            except Usuario.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Usuario no encontrado'
                }, status=status.HTTP_404_NOT_FOUND)

            # USAR EL NUEVO MÉTODO QUE MANEJA ARCHIVOS DIRECTAMENTE
            success = self.facial_service.register_face_from_file(int(user_id), image_file)

            if success:
                # Obtener el perfil creado
                perfil = PerfilFacial.objects.get(codigo_usuario=usuario)

                return Response({
                    'success': True,
                    'message': f'Perfil facial registrado exitosamente para {usuario.nombre} {usuario.apellido}',
                    'profile_id': perfil.id,
                    'user': {
                        'codigo': usuario.codigo,
                        'nombre': usuario.nombre,
                        'apellido': usuario.apellido,
                        'correo': usuario.correo
                    },
                    'image_url': perfil.imagen_url
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'error': 'No se pudo registrar el perfil facial'
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error registrando perfil facial: {str(e)}")
            return Response({
                'success': False,
                'error': f'Error interno del servidor: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    @action(detail=False, methods=['post'])
    def register_current_user(self, request):
        """Registra perfil facial del usuario autenticado actual"""
        try:
            # Obtener imagen del FormData
            image_file = request.FILES.get('image')

            logger.info(f"Datos recibidos - image_file: {'Si' if image_file else 'No'}")

            if not image_file:
                return Response({
                    'success': False,
                    'error': 'La imagen es requerida como archivo'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Obtener usuario autenticado desde token
            try:
                usuario = Usuario.objects.get(correo=request.user.email)
                logger.info(f"Usuario encontrado: {usuario.nombre} {usuario.apellido}")
            except Usuario.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Usuario no encontrado en el sistema'
                }, status=status.HTTP_404_NOT_FOUND)

            # Verificar si ya tiene un perfil registrado
            existing_profile = PerfilFacial.objects.filter(codigo_usuario=usuario, activo=True).first()
            if existing_profile:
                logger.info(f"Usuario ya tiene perfil facial: {existing_profile.id}")
                return Response({
                    'success': False,
                    'error': 'Ya tienes un perfil facial registrado. Elimínalo primero si quieres crear uno nuevo.'
                }, status=status.HTTP_400_BAD_REQUEST)

            # USAR EL NUEVO MÉTODO QUE MANEJA ARCHIVOS DIRECTAMENTE
            success = self.facial_service.register_face_from_file(usuario.codigo, image_file)

            if success:
                # Obtener el perfil creado por el servicio
                profile = PerfilFacial.objects.get(codigo_usuario=usuario, activo=True)

                logger.info(f"Perfil facial creado exitosamente: {profile.id}")

                return Response({
                    'success': True,
                    'message': f'Perfil facial registrado exitosamente para {usuario.nombre}',
                    'profile_id': profile.id,
                    'user': {
                        'codigo': usuario.codigo,
                        'nombre': usuario.nombre,
                        'apellido': usuario.apellido,
                        'correo': usuario.correo
                    },
                    'image_url': profile.imagen_url
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'error': 'No se pudo registrar el perfil facial. Verifica que la imagen contenga una cara visible.'
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error registrando perfil del usuario actual: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



    @action(detail=False, methods=['get'])
    def list_profiles(self, request):
        """Lista todos los perfiles faciales registrados"""
        try:
            profiles = PerfilFacial.objects.filter(activo=True).select_related('codigo_usuario')

            profiles_data = []
            for profile in profiles:
                profiles_data.append({
                    'id': profile.id,
                    'user_id': profile.codigo_usuario.codigo,
                    'user_name': f"{profile.codigo_usuario.nombre} {profile.codigo_usuario.apellido}",
                    'user_email': profile.codigo_usuario.correo,
                    'image_url': profile.imagen_url,
                    'fecha_registro': profile.fecha_registro.isoformat(),
                    'activo': profile.activo
                })

            return Response({
                'success': True,
                'profiles': profiles_data,
                'count': len(profiles_data)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error listando perfiles: {str(e)}")
            return Response({
                'success': False,
                'error': 'Error interno del servidor',
                'profiles': [],
                'count': 0
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Y la función delete_profile:

    @action(detail=True, methods=['delete'])
    def delete_profile(self, request, pk=None):
        """Elimina un perfil facial específico"""
        try:
            profile = PerfilFacial.objects.get(id=pk, activo=True)

            # Verificar que el usuario puede eliminar este perfil
            # (solo el propietario o un admin)
            usuario = Usuario.objects.get(correo=request.user.email)
            if profile.codigo_usuario != usuario and not request.user.is_staff:
                return Response({
                    'success': False,
                    'message': 'No tienes permisos para eliminar este perfil'
                }, status=status.HTTP_403_FORBIDDEN)

            # Marcar como inactivo en lugar de eliminar
            profile.activo = False
            profile.save()

            # Opcionalmente, eliminar imagen de Supabase
            try:
                from supabase import create_client, Client
                import os

                supabase_url = os.getenv('SUPABASE_URL')
                supabase_key = os.getenv('SUPABASE_ANON_KEY')
                supabase: Client = create_client(supabase_url, supabase_key)

                if profile.imagen_path:
                    supabase.storage.from_('ai-detection-images').remove([profile.imagen_path])
                    logger.info(f"Imagen eliminada de Supabase: {profile.imagen_path}")
            except Exception as e:
                logger.warning(f"Error eliminando imagen de Supabase: {str(e)}")

            logger.info(f"Perfil facial eliminado: {profile.id}")

            return Response({
                'success': True,
                'message': 'Perfil facial eliminado correctamente'
            }, status=status.HTTP_200_OK)

        except PerfilFacial.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Perfil facial no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error eliminando perfil: {str(e)}")
            return Response({
                'success': False,
                'message': 'Error interno del servidor'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




    @action(detail=False, methods=['get'])
    def list_profiles(self, request):
        """Lista todos los perfiles faciales registrados"""
        try:
            perfiles = PerfilFacial.objects.select_related('codigo_usuario').filter(activo=True)

            profiles_data = []
            for perfil in perfiles:
                profiles_data.append({
                    'id': perfil.id,
                    'user_id': perfil.codigo_usuario.codigo,
                    'user_name': f"{perfil.codigo_usuario.nombre} {perfil.codigo_usuario.apellido}",
                    'user_email': perfil.codigo_usuario.correo,
                    'image_url': perfil.imagen_url,
                    'fecha_registro': perfil.fecha_registro.isoformat(),
                    'activo': perfil.activo
                })

            return Response({
                'success': True,
                'profiles': profiles_data,
                'count': len(profiles_data)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error obteniendo perfiles: {str(e)}")
            return Response({
                'success': False,
                'error': 'Error obteniendo perfiles'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['delete'])
    def delete_profile(self, request, pk=None):
        """Elimina un perfil facial"""
        try:
            perfil = PerfilFacial.objects.get(id=pk)

            # Eliminar imagen de Supabase Storage
            if perfil.imagen_path:
                self.storage_service.delete_file(perfil.imagen_path)

            # Eliminar registro
            user_name = f"{perfil.codigo_usuario.nombre} {perfil.codigo_usuario.apellido}"
            perfil.delete()

            # Recargar perfiles faciales en el servicio
            self.facial_service.load_known_faces()

            return Response({
                'success': True,
                'message': f'Perfil facial de {user_name} eliminado exitosamente'
            }, status=status.HTTP_200_OK)

        except PerfilFacial.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Perfil no encontrado'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error eliminando perfil: {str(e)}")
            return Response({
                'success': False,
                'error': 'Error eliminando perfil'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ============= DETECCIÓN DE PLACAS =============
    @action(detail=False, methods=['post'])
    def detect_plate(self, request):
        try:
            # Obtener datos del FormData
            image_file = request.FILES.get('image')
            camera_location = request.data.get('camera_location', 'Estacionamiento')
            access_type = request.data.get('access_type', 'entrada')

            if not image_file:
                return Response(
                    {'error': 'La imagen es requerida como archivo'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"Procesando detección de placa - cámara: {camera_location}, tipo: {access_type}")

            # USAR EL NUEVO MÉTODO QUE MANEJA ARCHIVOS DIRECTAMENTE
            result = self.plate_service.detect_plate_from_file(
                image_file, camera_location, access_type
            )

            # Crear reporte de seguridad si la placa no está autorizada
            if result['plate'] and not result['is_authorized']:
                ReporteSeguridad.objects.create(
                    tipo_evento='placa_no_autorizada',
                    deteccion_placa_id=result['id'],
                    descripcion=f"Placa no autorizada detectada: {result['plate']} en {camera_location}",
                    nivel_alerta='medio'
                )

            logger.info(f"Detección completada - placa: {result.get('plate', 'No detectada')}")
            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error en detección de placa: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response(
                {'error': 'Error interno del servidor'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    # ============= ESTADÍSTICAS =============
    @action(detail=False, methods=['get'])
    def detection_stats(self, request):
        try:
            now = timezone.now()
            last_24h = now - timedelta(hours=24)
            last_week = now - timedelta(days=7)

            stats = {
                'facial_recognitions_today': ReconocimientoFacial.objects.filter(
                    fecha_deteccion__gte=last_24h
                ).count(),
                'plate_detections_today': DeteccionPlaca.objects.filter(
                    fecha_deteccion__gte=last_24h
                ).count(),
                'residents_detected_today': ReconocimientoFacial.objects.filter(
                    fecha_deteccion__gte=last_24h,
                    es_residente=True
                ).count(),
                'unauthorized_plates_today': DeteccionPlaca.objects.filter(
                    fecha_deteccion__gte=last_24h,
                    es_autorizado=False
                ).count(),
                'security_alerts_week': ReporteSeguridad.objects.filter(
                    fecha_evento__gte=last_week,
                    nivel_alerta__in=['alto', 'critico']
                ).count(),
                'registered_faces': PerfilFacial.objects.filter(activo=True).count()
            }

            return Response(stats, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return Response(
                {'error': 'Error interno del servidor'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# -------- Helpers ----------
def _month_range(yyyy_mm: str):
    """Devuelve (primer_día, último_día) para un 'YYYY-MM'. Si es inválido, usa el mes actual."""
    try:
        y, m = map(int, yyyy_mm.split("-"))
        first = date(y, m, 1)
    except Exception:
        today = date.today()
        y, m = today.year, today.month
        first = date(y, m, 1)

    if m == 12:
        last = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(y, m + 1, 1) - timedelta(days=1)
    return first, last


def _bitacora(request, accion: str):
    try:
        u = Usuario.objects.get(correo=request.user.email)
        Bitacora.objects.create(
            codigo_usuario=u,
            accion=accion,
            fecha=timezone.now().date(),
            hora=timezone.now().time(),
            ip=request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0] or request.META.get("REMOTE_ADDR") or "0.0.0.0",
        )
    except Usuario.DoesNotExist:
        pass


# -------- Endpoint: Estado de Cuenta ----------
class EstadoCuentaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1) usuario
        try:
            user = Usuario.objects.get(correo=request.user.email)
        except Usuario.DoesNotExist:
            return Response({"detail": "Usuario no registrado en catálogo."}, status=400)

        # 2) mes (YYYY-MM)
        mes = request.query_params.get("mes") or date.today().strftime("%Y-%m")
        desde, hasta = _month_range(mes)

        # 3) propiedades del usuario (ocupación vigente en el período)
        pertenencias = (
            Pertenece.objects
            .filter(codigo_usuario=user, fecha_ini__lte=hasta)
            .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=desde))
            .select_related("codigo_propiedad")
        )

        propiedades = [p.codigo_propiedad for p in pertenencias]
        props_desc = [p.codigo_propiedad.descripcion for p in pertenencias]

        # 4) CARGOS
        cargos = []

        # a) cat. Pagos vigentes (si tu tabla Pagos no tiene 'estado', elimina el filter(estado="activo"))
        pagos_catalogo_qs = Pagos.objects.all()
        if hasattr(Pagos, "estado"):
            pagos_catalogo_qs = pagos_catalogo_qs.filter(estado="activo")

        for p in pagos_catalogo_qs:
            cargos.append({
                "tipo": p.tipo,                       # 'Cuota ordinaria', 'Servicio', etc.
                "descripcion": p.descripcion,
                "monto": p.monto,
                "origen": "pago",
                "fecha": None,
            })

        # b) Multas emitidas a sus propiedades dentro del mes
        if propiedades:
            multas_qs = (
                DetalleMulta.objects
                .filter(codigo_propiedad__in=[pp.codigo for pp in propiedades],
                        fechaemi__range=(desde, hasta))
                .select_related("id_multa", "codigo_propiedad")
            )
            for dm in multas_qs:
                m = dm.id_multa
                # si Multa tiene 'estado', sólo contamos activas
                if hasattr(Multa, "estado") and m.estado != "activo":
                    continue
                cargos.append({
                    "tipo": "Multa",
                    "descripcion": m.descripcion,
                    "monto": m.monto,
                    "origen": "multa",
                    "fecha": dm.fecha_emi,
                })

        total_cargos = sum((Decimal(c["monto"]) for c in cargos), Decimal("0.00"))

        # 5) PAGOS del usuario en el mes (Facturas pagadas)
        pagos_qs = (
            Factura.objects
            .filter(codigo_usuario=user, fecha__range=(desde, hasta), estado="pagado")
            .select_related("id_pago", "codigo_usuario")
        )

       # pagos_ser = PagoRealizadoSerializer(pagos_qs, many=True).data   # <- usar serializer de consulta
        total_pagos = pagos_qs.aggregate(s=Sum("id_pago__monto"))["s"] or Decimal("0.00")

        saldo = total_cargos - total_pagos

        # 6) E1: sin info
        mensaje = ""
        if not cargos and not pagos_qs.exists():
            mensaje = "No existen registros para el período seleccionado."

        # 7) Bitácora
        _bitacora(request, f"Consulta estado de cuenta {mes}")

        payload = {
            "mes": mes,
            "propiedades": props_desc,
            "cargos": cargos,
           # "pagos": pagos_ser,
            "pagos" : pagos_qs,
            "totales": {
                "cargos": f"{total_cargos:.2f}",
                "pagos": f"{total_pagos:.2f}",
                "saldo": f"{saldo:.2f}",
            },
            "mensaje": mensaje,
        }
        # Validamos contra el envelope final antes de responder
        return Response(EstadoCuentaSerializer(payload).data, status=200)


# -------- Endpoint: PDF Comprobante ----------
class ComprobantePDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        # Verifica que la factura pertenezca al usuario
        try:
            user = Usuario.objects.get(correo=request.user.email)
            factura = (
                Factura.objects
                .select_related("id_pago", "codigo_usuario")
                .get(id=pk, codigo_usuario=user)
            )
        except (Usuario.DoesNotExist, Factura.DoesNotExist):
            raise Http404()

        # Generar PDF simple
        buff = BytesIO()
        c = canvas.Canvas(buff, pagesize=A4)
        w, h = A4

        c.setFont("Helvetica-Bold", 16)
        c.drawString(40, h - 60, "Smart Condominium - Comprobante de Pago")

        c.setFont("Helvetica", 11)
        y = h - 110
        rows = [
            ("N° Comprobante", str(factura.id)),
            ("Fecha", factura.fecha.strftime("%Y-%m-%d")),
            ("Hora", factura.hora.strftime("%H:%M:%S")),
            ("Usuario", f"{factura.codigo_usuario.nombre} {factura.codigo_usuario.apellido}"),
            ("Correo", factura.codigo_usuario.correo),
            ("Concepto", factura.id_pago.descripcion),
            ("Tipo de Pago", factura.tipo_pago),
            ("Monto", f"{factura.id_pago.monto:.2f}"),
            ("Estado", factura.estado),
        ]
        for label, value in rows:
            c.drawString(40, y, f"{label}: {value}")
            y -= 20

        c.line(40, y - 10, w - 40, y - 10)
        c.drawString(40, y - 30, "Gracias por su pago.")
        c.showPage()
        c.save()
        buff.seek(0)

        # Bitácora
        _bitacora(request, f"Descarga comprobante #{factura.id}")

        return FileResponse(buff, as_attachment=True, filename=f"comprobante_{factura.id}.pdf")

