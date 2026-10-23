# MAC PDF Watermark — primera versión

Aplicación web local para guardar marcas de agua de texto y logotipos, y aplicarlas a archivos PDF.

## Incluye
- Inicio de sesión y rol administrador.
- Base de datos SQLite permanente en `data/mac_watermark.db`.
- Biblioteca de marcas de agua de texto y logotipos.
- Ajustes de color, transparencia, tamaño, inclinación y posición.
- Aplicación a todas las páginas o solo a la primera.
- Descarga de un nuevo PDF; no modifica el original.
- Creación de cuentas para empleados desde la sesión de administrador.

## Requisitos
- Windows 10/11.
- Python 3.11 o posterior instalado desde https://www.python.org/downloads/
- Durante la instalación de Python, activar **Add Python to PATH**.

## Ejecutar en Windows
1. Descomprime la carpeta del programa en una ubicación estable, por ejemplo `C:\MAC_PDF_Watermark`.
2. Haz doble clic en `run_windows.bat`.
3. La primera vez instalará las dependencias y puede tardar unos minutos.
4. Abre Chrome y entra a http://127.0.0.1:5000
5. Primer acceso: usuario `MAC`, contraseña `marcasdeagua`. La página se titula **Marcas de agua**.
6. Crea usuarios para los empleados y guarda las marcas.

La base de datos y los logotipos se guardan dentro de la carpeta `data`. Haz copias de seguridad de esa carpeta.

## Importante para varios empleados
Si se ejecuta en una sola computadora, el programa está disponible localmente en esa computadora. Para que varios empleados usen una biblioteca compartida, hay que alojarlo en un servidor común o publicarlo en internet. No basta con copiar el programa a varias computadoras: cada copia tendría una base de datos distinta.

## Publicar en internet (resumen)
Esta primera versión está pensada para probarse localmente. Antes de publicar documentos empresariales en internet, realiza estos pasos:
1. Usa un servicio de alojamiento que admita Python/Flask y almacenamiento persistente.
2. Configura `MAC_SECRET_KEY` con una cadena aleatoria larga y secreta.
3. Configura `MAC_ADMIN_USER` y `MAC_ADMIN_PASSWORD` para crear la primera cuenta con credenciales propias.
4. Asegura que `MAC_DATA_DIR` apunte a un disco persistente y con copias de seguridad. El almacenamiento temporal de algunos servicios se borra al reiniciar.
5. Activa HTTPS, limita el acceso y revisa la política de privacidad de la empresa.
6. No uses el servidor de desarrollo de Flask (`python app.py`) para producción. Usa un servidor WSGI como Gunicorn en Linux o el servidor recomendado por tu proveedor.
7. Prueba con copias de PDF no confidenciales antes de usar documentos reales.

### Ejemplo de comando de producción en Linux
`gunicorn --workers 2 --bind 0.0.0.0:$PORT app:app`

**Nota:** Para un uso empresarial más robusto, la siguiente mejora sería usar PostgreSQL, almacenamiento privado de archivos, protección contra CSRF, auditoría y gestión de contraseñas. Esta versión es un prototipo funcional inicial, no una instalación endurecida para documentos altamente confidenciales.

## Limitaciones actuales
- No tiene recuperación de contraseña por correo.
- No tiene vista previa del PDF antes de procesarlo.
- Los logotipos se dibujan dentro de un cuadro cuadrado; para logotipos panorámicos puede ser necesario ajustar la implementación.
- Los PDF con contraseña deben desbloquearse antes de cargarlos.
