from rest_framework import serializers
from .models import (
    Rol, Usuario, Propiedad, Multa, Pagos, Notificaciones, AreasComunes, Tareas,
    Vehiculo, Pertenece, ListaVisitantes, DetalleMulta, Factura, Finanzas,
    Comunicados, Horarios, Reserva, Asignacion, Envio, Registro, Bitacora,
    PerfilFacial, ReconocimientoFacial, DeteccionPlaca, ReporteSeguridad
)


class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = "__all__"


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = "__all__"


class PropiedadSerializer(serializers.ModelSerializer):
    tamano_m2 = serializers.DecimalField(
        max_digits=12, decimal_places=2,
        coerce_to_string=False, allow_null=True, required=False
    )

    class Meta:
        model = Propiedad
        fields = ("codigo", "nro_casa", "piso", "tamano_m2", "descripcion")


class MultaSerializer(serializers.ModelSerializer):
    monto = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)

    class Meta:
        model = Multa
        # Si tu modelo tiene 'estado', inclúyelo; si no, omítelo.
        fields = ("id", "descripcion", "monto", "estado") if hasattr(Multa, "estado") else ("id", "descripcion", "monto")

    def validate_descripcion(self, value):
        qs = Multa.objects.filter(descripcion__iexact=value.strip())
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe una multa con esa descripción.")
        if not value.strip():
            raise serializers.ValidationError("La descripción es obligatoria.")
        return value

    def validate_monto(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("El monto debe ser mayor a 0.")
        return value




class PagoSerializer(serializers.ModelSerializer):
    monto = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)

    class Meta:
        model = Pagos
        # Si tu modelo tiene 'estado', déjalo en fields; si no, quítalo sin problema.
        fields = ("id", "tipo", "descripcion", "monto", "estado") if hasattr(Pagos, "estado") else ("id", "tipo", "descripcion", "monto")

    def validate(self, attrs):
        tipo = attrs.get("tipo") or getattr(self.instance, "tipo", None)
        descripcion = attrs.get("descripcion") or getattr(self.instance, "descripcion", None)
        monto = attrs.get("monto") if "monto" in attrs else getattr(self.instance, "monto", None)

        if not tipo:
            raise serializers.ValidationError({"tipo": "El tipo es obligatorio."})
        if not descripcion:
            raise serializers.ValidationError({"descripcion": "La descripción es obligatoria."})
        if monto is None or monto <= 0:
            raise serializers.ValidationError({"monto": "El monto debe ser mayor a 0."})
        return attrs

class CargoSerializer(serializers.Serializer):
    tipo = serializers.CharField()
    descripcion = serializers.CharField()
    monto = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False)
    origen = serializers.CharField()  # 'pago' (expensa/servicio) | 'multa'
    fecha = serializers.DateField(required=False, allow_null=True)

class NotificacionesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notificaciones
        fields = "__all__"


class AreasComunesSerializer(serializers.ModelSerializer):
    class Meta:
        model = AreasComunes
        fields = "__all__"


class TareasSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tareas
        fields = "__all__"


class VehiculoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehiculo
        fields = "__all__"


class PerteneceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pertenece
        fields = "__all__"


class ListaVisitantesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListaVisitantes
        fields = "__all__"


class DetalleMultaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleMulta
        fields = "__all__"


class FacturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Factura
        fields = "__all__"


class FinanzasSerializer(serializers.ModelSerializer):
    class Meta:
        model = Finanzas
        fields = "__all__"


class ComunicadosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comunicados
        fields = "__all__"


class HorariosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Horarios
        fields = "__all__"


class ReservaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reserva
        fields = "__all__"


class AsignacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asignacion
        fields = "__all__"


class EnvioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Envio
        fields = "__all__"


class RegistroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Registro
        fields = "__all__"


class BitacoraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bitacora
        fields = "__all__"


# Agregar al final de api/serializers.py

class PerfilFacialSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = PerfilFacial
        fields = ['id', 'codigo_usuario', 'imagen_url', 'fecha_registro', 'activo', 'usuario_nombre']

    def get_usuario_nombre(self, obj):
        return f"{obj.codigo_usuario.nombre} {obj.codigo_usuario.apellido}"


class ReconocimientoFacialSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = ReconocimientoFacial
        fields = "__all__"

    def get_usuario_nombre(self, obj):
        if obj.codigo_usuario:
            return f"{obj.codigo_usuario.nombre} {obj.codigo_usuario.apellido}"
        return "Desconocido"


class DeteccionPlacaSerializer(serializers.ModelSerializer):
    vehiculo_info = serializers.SerializerMethodField()

    class Meta:
        model = DeteccionPlaca
        fields = "__all__"

    def get_vehiculo_info(self, obj):
        if obj.vehiculo:
            return {
                'id': obj.vehiculo.id,
                'descripcion': obj.vehiculo.descripcion,
                'estado': obj.vehiculo.estado
            }
        return None

class PagoRealizadoSerializer(serializers.ModelSerializer):
    """
    Composición Factura + concepto de Pagos.
    Lee de Factura y expone campos amigables para el front.
    """
    id = serializers.IntegerField(read_only=True)
    concepto = serializers.CharField(source="id_pago.descripcion", read_only=True)
    monto = serializers.DecimalField(
        source="id_pago.monto",
        max_digits=12, decimal_places=2,
        read_only=True, coerce_to_string=False
    )
    fecha = serializers.DateField(read_only=True)
    hora = serializers.TimeField(read_only=True)
    tipo_pago = serializers.CharField(read_only=True)
    estado = serializers.CharField(read_only=True)

    class Meta:
        model = Factura
        fields = ("id", "concepto", "monto", "fecha", "hora", "tipo_pago", "estado")

class EstadoCuentaSerializer(serializers.Serializer):
    mes = serializers.CharField()
    propiedades = serializers.ListField(child=serializers.CharField())  # descripciones
    cargos = CargoSerializer(many=True)
    pagos = PagoRealizadoSerializer(many=True)
    totales = serializers.DictField()  # {'cargos': ..., 'pagos': ..., 'saldo': ...}
    mensaje = serializers.CharField(allow_blank=True)

class ReporteSeguridadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReporteSeguridad
        fields = "__all__"
# Publicar Avisos/Comunicados
# -----------------------------
class PublicarComunicadoSerializer(serializers.Serializer):
    """
    Valida la creación/publicación de un comunicado.
    - prioridad se mapea a Comunicados.tipo
    - estado final del comunicado: 'publicado' (en la vista/servicio)
    - destinatarios incluye 'todos'
    """
    titulo = serializers.CharField(max_length=500)
    contenido = serializers.CharField()
    # Prioridad: usamos el campo 'tipo' del modelo Comunicados
    prioridad = serializers.ChoiceField(choices=["normal", "importante", "urgente"])
    # Destinatarios: control en backend (incluye 'todos'); el front solo muestra opciones.
    destinatarios = serializers.ChoiceField(
        choices=["todos", "copropietarios", "inquilinos", "personal", "usuarios"],
        required=True
    )
    # Requerido únicamente cuando destinatarios == "usuarios"
    usuario_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=False
    )
    # Programación opcional; si no vienen, se usarán valores por defecto (ahora) en la vista
    fecha_publicacion = serializers.DateField(required=False)
    hora_publicacion = serializers.TimeField(required=False)

    def validate(self, data):
        dest = data.get("destinatarios")
        if dest == "usuarios" and not data.get("usuario_ids"):
            raise serializers.ValidationError({"usuario_ids": "Requerido cuando destinatarios=usuarios"})
        return data