# api/services/avisos.py
from typing import Iterable, Tuple
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from ..models import (
    Usuario, Rol, Comunicados, Notificaciones, Envio, Bitacora
)

class PushService:
    """
    Stub de notificaciones push. Aquí integrarías FCM/OneSignal.
    Devuelve (ok, mensaje).
    """
    @staticmethod
    def send_push(usuario: Usuario, titulo: str, cuerpo: str) -> Tuple[bool, str]:
        try:
            # TODO: integrar proveedor real (FCM/OneSignal)
            return True, "ok"
        except Exception as e:
            return False, str(e)

def _usuarios_por_destinatario(kind: str, usuario_ids=None) -> Iterable[Usuario]:
    base = Usuario.objects.filter(Q(estado__iexact="activo") | Q(estado__iexact="activa"))
    if kind == "todos":
        return base
    if kind == "usuarios":
        return base.filter(codigo__in=(usuario_ids or []))

    # Filtrado por rol (ajusta si tu taxonomía está en Rol.tipo en lugar de descripcion)
    rol_map = {
        "copropietarios": ["copropietario", "copropietarios"],
        "inquilinos": ["inquilino", "inquilinos"],
        "personal": ["personal", "guardia", "seguridad", "admin", "administrador"],
    }
    nombres = rol_map.get(kind, [])
    if not nombres:
        return base.none()
    return base.filter(idrol__descripcion__iregex="|".join(nombres))

@transaction.atomic
def publicar_comunicado_y_notificar(
    admin: Usuario,
    titulo: str,
    contenido: str,
    prioridad: str,           # normal|importante|urgente  (se guarda en Comunicados.tipo)
    destinatarios: str,       # todos|copropietarios|inquilinos|personal|usuarios
    fecha_pub,                # date
    hora_pub,                 # time
    usuario_ids=None,         # list[int] si destinatarios == "usuarios"
):
    # 1) Persistir el comunicado (estado publicado)
    comunicado = Comunicados.objects.create(
        tipo=prioridad,
        fecha=fecha_pub,
        hora=hora_pub,
        titulo=titulo,
        contenido=contenido,
        estado="publicado",
        codigo_usuario=admin,
    )

    # 2) Crear cabecera de notificación
    notif = Notificaciones.objects.create(tipo="comunicado", descripcion=titulo)

    # 3) Resolver destinatarios
    usuarios = list(_usuarios_por_destinatario(destinatarios, usuario_ids))
    enviados, errores = 0, 0

    # 4) Crear envíos y despachar push
    for u in usuarios:
        envio = Envio.objects.create(
            codigo_usuario=u,
            id_notific=notif,
            fecha=timezone.now().date(),
            hora=timezone.now().time(),
            estado="pendiente",
        )
        ok, msg = PushService.send_push(u, titulo, contenido)
        envio.estado = "enviado" if ok else "error"
        envio.save(update_fields=["estado"])
        enviados += 1 if ok else 0
        errores  += 0 if ok else 1

    # 5) Bitácora
    Bitacora.objects.create(
        codigo_usuario=admin,
        accion=f"Publicó comunicado: {titulo} (dest:{destinatarios}, prio:{prioridad}, env:{enviados}, err:{errores})",
        fecha=timezone.now().date(),
        hora=timezone.now().time(),
        ip="system",
    )

    return comunicado, {"total": len(usuarios), "enviados": enviados, "errores": errores}
