# Gestión de secretos — etapa 2 de v0.6.0

Esta etapa incorpora cifrado y archivos de claves. **No implementa SMTP, OAuth2,
notificaciones, tablas ni endpoints de credenciales.** La versión declarada de
Ticketyn permanece sin cambios. Las notas FMS continúan siendo históricas e inmutables.

## Componente

`src/ticketyn/core/secret_store.py` proporciona:

- `SecretCipher.encrypt(texto, context=...)` y `decrypt(valor, context=...)`.
- `get_secret_cipher()`, que utiliza la configuración y carga las claves al operar.
- `create_key_file()`: aprovisionamiento inicial explícito, nunca automático.
- `copy_key_file()`: respaldo/restauración independiente de las mismas claves.
- `validate_key_file()`: valida archivo y devuelve solo el identificador activo.

AES-256-GCM procede de `cryptography`. Cada cifrado genera un nonce aleatorio de
96 bits y conserva la etiqueta de autenticidad completa. La generación aleatoria
hace extremadamente improbable una colisión; no supone una garantía matemática de
unicidad ni usa contadores que puedan repetirse después de restaurar PostgreSQL.
Véase la [documentación de AES-GCM](https://cryptography.io/en/stable/hazmat/primitives/aead/).

El contexto es obligatorio, estable y específico del registro y clase de secreto;
por ejemplo, en una integración futura, `mail:transport:1:smtp-password`.
No contiene la contraseña. Debe ser idéntico al descifrar: cambiarlo, alterar el
contenido o utilizar otra clave hace fallar la autenticación. La versión y el
identificador de clave forman parte de los datos autenticados.

Las contraseñas o tokens solo existirán en texto plano mientras los necesite el
consumidor. No se registran ni se adjuntan a excepciones públicas. Este componente
no debe conectarse a una respuesta API que devuelva el valor descifrado.

## Formatos

Ejemplo **esquemático, no utilizable** de `keys.json`:

```json
{
  "version": 1,
  "active_key_id": "IDENTIFICADOR_GENERADO",
  "keys": {
    "IDENTIFICADOR_GENERADO": "BASE64_URLSAFE_DE_32_BYTES_ALEATORIOS"
  }
}
```

El identificador no es secreto. Las claves son secretas; Base64 es codificación,
no cifrado. No copies este ejemplo como archivo de producción.

El valor cifrado es JSON con `version`, `key_id`, `nonce` y `ciphertext`.
`ciphertext` incluye la etiqueta de autenticidad. Se descifra con `key_id`, aunque
la clave activa sea otra. El archivo admite varias claves para preparar una futura
rotación, pero no existe todavía un procedimiento de rotación ni recifrado masivo.

Se rechazan versiones desconocidas, claves que no tengan 256 bits, identificadores
incoherentes, JSON duplicado o malformado y archivos de más de 64 KiB. El límite
por secreto es 64 KiB de texto UTF-8; el contexto admite hasta 512 bytes.

## Desarrollo sin root

Desde la raíz del repositorio, después de instalar las dependencias de desarrollo:

```bash
install -d -m 0700 "$HOME/.config/ticketyn/mail"
.venv/bin/python -m ticketyn.core.secret_store init \
  --path "$HOME/.config/ticketyn/mail/keys.json"
export MAIL_KEYS_PATH="$HOME/.config/ticketyn/mail/keys.json"
.venv/bin/python -m ticketyn.core.secret_store check --path "$MAIL_KEYS_PATH"
```

También puedes definir `MAIL_KEYS_PATH` en tu `.env` local privado. Utiliza una ruta
absoluta, fuera del repositorio; no se crean directorios automáticamente.
La herramienta de claves no requiere `DATABASE_URL`. `keys.json` está ignorado por
Git como protección adicional; no confíes en esa regla para otros nombres de archivo.

## Producción

Ruta predeterminada: `/etc/ticketyn/mail/keys.json`, fuera de PostgreSQL y releases.
La ruta se integra en `Settings.mail_keys_path`. **No agregues `MAIL_KEYS_PATH` al
archivo administrado `/etc/ticketyn/ticketyn.env`**: instalador, backup y restore
mantienen su contrato actual, limitado a `DATABASE_URL`.

Aprovisionamiento inicial, por un administrador y desde código revisado que ya
contenga el componente y sus dependencias:

```bash
sudo install -d -o root -g ticketyn -m 0750 /etc/ticketyn/mail
sudo /opt/ticketyn/current/.venv/bin/python -m ticketyn.core.secret_store init \
  --path /etc/ticketyn/mail/keys.json --group ticketyn
```

El archivo queda `root:ticketyn`, modo `0640`; el servicio solo necesita lectura.
En desarrollo se utiliza propietario local y modo `0600`. Se aceptan equivalentes
sin permiso de escritura del propietario. Se rechazan permisos para otros,
escritura de grupo, propietarios inesperados, ACL POSIX extendidas, enlaces
simbólicos en la ruta, enlaces duros y archivos no regulares. El directorio inmediato
debe ser privado, sin escritura de grupo ni acceso para otros. Los antecesores
escribibles se rechazan salvo directorios sticky como `/tmp`.

La publicación utiliza un temporal privado, sincronización a disco y enlace atómico
sin reemplazo. Si el destino existe, incluso corrupto, **no se sobrescribe**.
Un error de sincronización puede ocurrir después de publicar: valida el destino
antes de repetir. Los temporales incompletos de un proceso terminado abruptamente
permanecen privados; no se utilizan como claves y requieren revisión administrativa.

La etapa 2 no modificó `install.sh`, systemd, backup ni restore. La unidad actual permite
leer esta ubicación sin relajar `ProtectSystem` o `ProtectHome`. Arrancar Ticketyn
no requiere claves; cifrar o descifrar sí requiere un archivo válido. Nunca se genera
una clave nueva para reparar automáticamente una ausencia o corrupción.

## Respaldo independiente

`backup.sh` publica únicamente dump, entorno, metadatos, manifiesto y hashes; no
recorre `/etc/ticketyn/mail`. Las claves no se guardan en PostgreSQL y no se añaden
al TAR de base de datos. Hay una prueba de regresión de esa exclusión.

Prepara un destino privado separado y copia las claves sin mostrarlas:

```bash
sudo install -d -o root -g root -m 0700 /var/backups/ticketyn-mail-keys
sudo /opt/ticketyn/current/.venv/bin/python -m ticketyn.core.secret_store copy \
  --source /etc/ticketyn/mail/keys.json \
  --destination /var/backups/ticketyn-mail-keys/keys-respaldo-UNICO.json
```

Elige un nombre nuevo por respaldo: la herramienta no reemplaza archivos. La copia
queda `0600`. Custódiala fuera del servidor mediante un medio cifrado y controlado,
separado del backup de PostgreSQL. La copia local no está cifrada; es material maestro.
No la incluyas en tickets, logs, Git ni archivos de inspección públicos.

Conserva juntas las claves y sus identificadores; un hash detecta corrupción, pero
no autentica la procedencia ni sustituye una custodia segura. La retención deberá
permitir recuperar las claves usadas por todos los backups conservados.

## Restauración independiente

No ejecutes `init` para recuperar claves: produciría material diferente e inútil
para los valores cifrados anteriores. En un destino nuevo, con directorio y grupo
preparados como arriba:

```bash
sudo /opt/ticketyn/current/.venv/bin/python -m ticketyn.core.secret_store copy \
  --source /ruta/privada/confiable/keys-respaldo-UNICO.json \
  --destination /etc/ticketyn/mail/keys.json --group ticketyn
sudo /opt/ticketyn/current/.venv/bin/python -m ticketyn.core.secret_store check
```

Si el destino ya existe, detente: no se borra ni sobrescribe automáticamente.
Un administrador debe identificar y custodiar el archivo existente antes de
resolver qué conjunto corresponde. `check` valida estructura y permisos, no prueba
por sí solo la correspondencia con un ciphertext; esa correspondencia se verifica
mediante descifrado autenticado en el consumidor, sin mostrar el secreto.

Las pruebas cubren pérdida del archivo, fracaso con una clave distinta y recuperación
correcta con la copia respaldada. Perder todas las copias impide recuperar los
secretos: habrá que introducir y autorizar credenciales nuevas desde la
configuración de correo disponible desde las etapas 3 y 5.

La [etapa 6](mail-jobs-v0.6.0.md) incorpora pausa persistente y cuarentena de
trabajos tras restaurar. La recuperación de claves sigue siendo independiente de
PostgreSQL y no autoriza por sí misma la reanudación del procesador.

## Límites

Las claves no protegen frente a un proceso del servicio o administrador comprometido.
Python no garantiza borrar de memoria todas las copias de cadenas o bytes; evita
volcados de memoria y logging de variables sensibles. La implementación utiliza
primitivas de archivos POSIX/Linux y espera un sistema de archivos con permisos,
xattrs y enlaces atómicos locales. No almacenes claves en un recurso compartido
con permisos simulados. La rotación completa sigue pendiente; la integración con
correo ya utiliza este componente desde las etapas 3 a 8.
