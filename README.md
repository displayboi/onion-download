# onion-download
Este script permite la descarga recursiva de todos los archivos de un listado tipo "Index of" alojado en un servicio `.onion`, a través de Tor (SOCKS5), con descargas en paralelo.

Está pensado para casos en los que gestores de descargas como JDownloader no logran analizar bien el listado (por la lentitud de Tor, timeouts o porque solo leen un nivel de carpetas).

## Características

- Recorre **todas las subcarpetas** del listado y reproduce la misma estructura en local.
- **Descargas en paralelo**, cada una por un circuito de Tor distinto, para aprovechar mejor el ancho de banda.
- **Reanuda** las descargas interrumpidas (usa archivos `.part` y cabeceras `Range`).
- **Omite los archivos ya descargados**, de modo que puedes volver a ejecutarlo para bajar solo lo nuevo.
- **Reintentos automáticos** con espera creciente ante timeouts o errores de conexión.
- Filtro opcional por **extensión** (`7z`, `jpg`, `txt`...).
- Modo `--list-only` para ver qué hay sin descargar nada.
- La resolución DNS la hace Tor (`socks5h`), así que no hay fugas de DNS.

## Requisitos

- Python 3.8 o superior
- Tor en ejecución en tu equipo (Tor Browser abierto, o el servicio Tor)
- La librería `requests` con soporte SOCKS

## Instalación

```bash
git clone https://github.com/TU_USUARIO/onion-download.git
cd onion-download
pip install "requests[socks]"
```

## Preparar Tor

El script necesita un proxy SOCKS5 de Tor activo en local:

| Cómo ejecutas Tor | Puerto SOCKS |
|---|---|
| Tor Browser abierto y conectado | `9150` (por defecto en el script) |
| Servicio Tor independiente (`tor`) | `9050` (usa `--port 9050`) |

## Uso

```bash
python onion_download.py URL [opciones]
```

La URL debe apuntar al directorio que quieres descargar. Usa `http://` (la mayoría de servicios `.onion` no usan HTTPS).

### Ejemplos

Comprobar qué archivos hay, sin descargar nada:

```bash
python onion_download.py http://xxxxxxxx.onion/carpeta/ --list-only
```

Descargar todo en la carpeta `descargas`:

```bash
python onion_download.py http://xxxxxxxx.onion/carpeta/ -o descargas
```

Descargar solo archivos `.7z` y `.jpg`, con 5 descargas simultáneas:

```bash
python onion_download.py http://xxxxxxxx.onion/carpeta/ -o descargas --ext 7z,jpg -w 5
```

Usar el servicio Tor independiente en lugar de Tor Browser:

```bash
python onion_download.py http://xxxxxxxx.onion/carpeta/ --port 9050
```

Guardar en otra ubicación (Windows):

```bash
python onion_download.py http://xxxxxxxx.onion/carpeta/ -o "D:\Onion\descargas"
```

### Opciones

| Opción | Descripción | Por defecto |
|---|---|---|
| `url` | URL del directorio a descargar | (obligatorio) |
| `-o`, `--output` | Carpeta de destino (se crea si no existe) | `descargas` |
| `-p`, `--port` | Puerto SOCKS de Tor | `9150` |
| `-w`, `--workers` | Número de descargas simultáneas | `4` |
| `--ext` | Solo estas extensiones, separadas por comas | todas |
| `--retries` | Reintentos por operación | `5` |
| `--list-only` | Solo lista los archivos, no descarga | desactivado |

## Estructura de la descarga

La carpeta de destino se crea en el directorio desde el que ejecutas el comando (o en la ruta que indiques) y replica la estructura de la página:

```
descargas/
├── archivo1.7z
├── notas.txt
└── subcarpeta/
    ├── foto1.jpg
    └── info.txt
```

## Buscar archivos nuevos

Si la página se actualiza, basta con volver a ejecutar **el mismo comando** (misma URL y misma carpeta de destino). El script vuelve a listar el contenido, omite lo que ya tienes completo, reanuda los `.part` pendientes y descarga solo lo nuevo.

## Cómo funciona

1. Se conecta a la URL a través del proxy SOCKS5 de Tor y analiza los enlaces del listado.
2. Entra recursivamente en cada subcarpeta y construye la lista completa de archivos.
3. Descarga los archivos en paralelo. Cada hilo usa credenciales SOCKS distintas, lo que hace que Tor le asigne un **circuito propio** (aislamiento por credenciales SOCKS), así las velocidades se suman en lugar de compartir un único circuito.
4. Cada archivo se guarda primero como `nombre.part` y se renombra al terminar, para no confundir descargas incompletas con completas.

## Consejos

- **Número de workers:** entre 3 y 5 suele ser lo mejor. Más no suele acelerar, puede sobrecargar el servicio `.onion` y consume más recursos de la red Tor. Si ves muchos timeouts, baja a `-w 2` o `-w 3`.
- **Progreso detallado:** con `-w 1` se muestra el porcentaje de cada archivo; con más workers se muestra una línea por archivo terminado.
- **Interrumpir:** puedes parar con `Ctrl+C` en cualquier momento y volver a lanzar el script después para continuar.

## Limitaciones

- Solo funciona con listados simples tipo "Index of" (HTML con enlaces `<a href>`). No funciona con páginas que requieran **captcha, login o JavaScript** para mostrar los archivos.
- La detección de archivos ya descargados se hace **solo por nombre**: si el servidor reemplaza un archivo por otro con el mismo nombre, no se detectará el cambio.
- La velocidad depende del servidor `.onion` y del estado de la red Tor; no se puede mejorar más allá de cierto punto.

## Solución de problemas

| Problema | Posible causa y solución |
|---|---|
| `Connection refused` / error de proxy | Tor no está abierto o el puerto es incorrecto. Prueba `--port 9150` (Tor Browser) o `--port 9050` (servicio). |
| `Missing dependencies for SOCKS support` | Instala la dependencia: `pip install "requests[socks]"`. |
| Timeouts frecuentes | Reduce los workers (`-w 2`) o aumenta `--retries`. |
| Encuentra 0 archivos | Abre la URL en Tor Browser y comprueba que es un listado simple, sin captcha ni login. Asegúrate de usar `http://`. |
| Faltan archivos | Vuelve a ejecutar el script; al final se muestra la lista de los que fallaron. |

## Aviso legal y uso responsable

Esta herramienta es un descargador genérico y no está asociada a ningún sitio ni servicio concreto. Eres responsable de asegurarte de que tienes derecho a descargar el contenido al que accedes y de cumplir la legislación aplicable en tu país. Los autores no se hacen responsables del uso que se haga del script.
