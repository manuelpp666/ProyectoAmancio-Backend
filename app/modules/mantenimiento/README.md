# Mantenimiento automático del espacio

Qué hace, cómo se pone en marcha en cPanel y qué decisiones están tomadas.

## Por qué existe

Nada del sistema borraba nada. Lo que entraba se quedaba para siempre:
archivos que se quedaron sin fila en la base, fotos del padrón del CREP de
hace meses que ya no se comparan con nada, intentos de acceso de hace un año.
El servidor tiene 150 GB y nadie mira cuánto queda hasta que deja de quedar.

## Las dos puertas

| Ruta | Quién entra | Qué hace |
|---|---|---|
| `GET /mantenimiento/estado` | ADMIN con sesión | Solo mira. Es la simulación: enseña lo que se borraría. |
| `POST /mantenimiento/limpieza` | El cron, con `X-Service-Key` | Borra de verdad. |

El borrado **no** está en el panel a propósito. Un botón "limpiar" acaba
pulsándose por curiosidad, y el mantenimiento no necesita a nadie delante.

## Poner en marcha el cron en cPanel

**1. La clave.** En el `.env` del backend tiene que existir `CRON_SECRET`. Es
la misma que ya usan las tareas de pensiones y moras. Si no está puesta, el
endpoint responde 401 a todo el mundo (falla cerrado a propósito: mejor que no
corra a que quede abierto).

```
CRON_SECRET=una-cadena-larga-que-nadie-adivine
```

**2. La tarea.** En cPanel → *Cron Jobs*, una vez por semana. Los domingos de
madrugada, cuando no hay nadie usando el campus:

```bash
curl -s -X POST "https://TU-DOMINIO/mantenimiento/limpieza?simular=true" -H "X-Service-Key: LA-CLAVE-DEL-ENV"
```

Fíjate en `simular=true`. **Déjalo así las primeras semanas.** Devuelve el
informe de lo que borraría sin borrar nada. Cuando el informe se vea razonable
—que los archivos que dice sueltos lo sean de verdad—, se quita ese parámetro
y a partir de ahí borra:

```bash
curl -s -X POST "https://TU-DOMINIO/mantenimiento/limpieza" -H "X-Service-Key: LA-CLAVE-DEL-ENV"
```

**3. El aviso.** Cuando el disco pasa del 75%, manda un correo a los
administradores que tengan email cargado. Se cambia el umbral en el `.env`:

```
DISCO_AVISO_PORCENTAJE=80
```

Solo avisa cuando se pasa del umbral. Un correo semanal diciendo que todo va
bien es un correo que nadie abre, y el día que importe tampoco lo abrirán.

## Qué borra, y qué no

| | Se borra | Se conserva |
|---|---|---|
| **Archivos de `media/`** | Los que ninguna fila de la base referencia y llevan más de 24 h sin tocarse | Todo lo referenciado, y lo subido en las últimas 24 h |
| **Fotos del CREP** | El `cuotas_json` de las que tengan más de 90 días | Las 3 últimas enteras, y **la fila de todas**: fecha, totales y estado |
| **Intentos de acceso** | Más de 12 meses | El resto |
| **Solicitudes de acceso** | Atendidas o descartadas de más de 12 meses | **Todas las PENDIENTES**, por viejas que sean |

La ventana de 24 h en los archivos no es capricho: sin ella, una subida que
está a medias —el archivo ya escrito, la fila todavía sin confirmar— parecería
huérfana y se borraría delante del usuario.

Las solicitudes pendientes no se tocan nunca. Que una lleve un año ahí
significa que se le debe una respuesta a alguien.

## La regla de oro

**Nunca se borra un archivo por no encontrarlo en la base si la consulta a la
base falló.** Si `referencias()` no puede leer alguna tabla, la limpieza de
archivos aborta entera y lo deja escrito en `errores`.

Sin esa condición, una tabla caída convertiría "no encuentro ninguna
referencia" en "borra `media/` entera". Está probado: hay un caso en la
batería que simula la base caída y comprueba que no desaparece ni un archivo.

## Lo que este módulo NO puede arreglar

Lo que suele llenar un cPanel no está dentro de la aplicación:

- **Copias de seguridad acumuladas.** Una copia completa pesa lo que toda la
  cuenta. Dos copias = tres veces el sistema.
- **Logs sin rotar**, del servidor web y del propio backend.
- **El buzón** `notificaciones@`, con los rebotes.
- **Builds antiguos del frontend.** Solo hace falta `.next/standalone`
  (~60 MB); la carpeta `.next` entera pesa bastante más.
- **La caché de imágenes de Next** (`.next/cache/images`), que crece sola
  porque `next/image` optimiza las de Cloudinary.

El porcentaje de disco que da `GET /mantenimiento/estado` puede estar hablando
del disco de la máquina y no de la cuota del colegio: en hosting compartido
`disk_usage` mira el volumen, no la cuenta. El número de la cuenta es el del
panel del hosting. Por eso el informe trae también `del_sistema`, que sí es lo
que ocupa este sistema.
