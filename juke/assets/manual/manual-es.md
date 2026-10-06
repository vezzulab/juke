# 1. Bienvenido a Juke 1.0

Juke es un reproductor para tu propia música: los archivos de tu computadora o de tu teléfono, las canciones de tu servidor Airsonic / Subsonic y la radio por internet, todo en un solo lugar que se mantiene rápido y cuida la batería.

Este manual es un libro. El índice del costado lista cada capítulo y cada sección; puedes leerlo desde la primera página o saltar a lo que necesitas. También está dentro de la app (pulsa `F1` en Linux, o *Ajustes ▸ Manual* en Android), así que siempre lo tienes contigo y en tu idioma.

## Qué hay de nuevo en 1.0

- **Teclas multimedia y controles del escritorio.** Reproducir, pausar, siguiente y anterior funcionan desde tu teclado, tus auriculares y el widget multimedia de tu escritorio. El control de volumen es el volumen de la computadora, en ambos sentidos.
- **Crossfade.** La siguiente canción entra unos segundos antes de que termine la actual. Una luz bajo el volumen muestra si está activo.
- **Un ecualizador que cualquiera puede usar.** Cada barra dice qué cambia, y hay 35 presets.
- **Letras en cualquier idioma.** Se buscan en varios servicios gratuitos a la vez.
- **Mejores listas.** Una canción nunca se agrega dos veces, te avisa cuando ya está, y el mismo menú la quita.
- **Sabe qué se puede reproducir.** Las canciones de un servidor sin conexión o de un disco desconectado se ven en gris con una nota.
- **Marcas en la lista.** Unas barras bailan junto a la canción que suena y una ✓ verde marca lo que ya sonó.
- **Un manual dentro de la app**, con índice, en español e inglés.

## Cómo está escrito este manual

Las palabras en *cursiva* son nombres que ves en pantalla: menús, botones, pestañas. Las teclas se escriben así: `Ctrl` + `E`. Las partes que solo valen para un sistema lo dicen en el título: **Linux** para la app de computadora, **Android** para la de teléfono y tableta. Todo lo demás es igual en las dos.

---

# 2. Instalar y actualizar

<!--linux-->
## Instalar en Linux

Juke es un solo archivo, un AppImage, con todo adentro (Python, Qt, libVLC). No hay nada más que instalar.

1. Descarga `Juke-x86_64.AppImage` de la última versión en GitHub (unos 190 MB).
2. Permite que se ejecute: clic derecho en el archivo ▸ *Propiedades* ▸ *Permitir ejecutar*, o en una terminal `chmod +x Juke-x86_64.AppImage`.
3. Ábrelo. La primera vez, Juke se agrega solo a tu menú de aplicaciones, con su icono. Solo toca tu propia cuenta de usuario, y puedes deshacerlo en *Ajustes ▸ General*.

En una línea: `curl -fsSL https://vezzulab.github.io/juke/install.sh | sh`.

Lo que necesita: Linux x86_64 con glibc 2.35 o más nueva (Ubuntu 22.04, Debian 12, Fedora 36 o más nuevos), PulseAudio o PipeWire para el sonido, y FUSE 2 (`libfuse2`) o la opción `--appimage-extract-and-run`.

## Instalar desde el código fuente

Juke necesita libVLC en el sistema. Luego `pip install -e .` dentro de la carpeta y ejecuta `juke`. Para agregar el lanzador y el icono a tu menú: `juke --install-desktop` (y `--uninstall-desktop` para quitarlos). Los archivos que le des en la línea de comandos se reproducen: `juke cancion.flac`.
<!--/linux-->

<!--android-->
## Instalar en Android

1. Descarga `Juke-<versión>.apk` de la última versión en GitHub (unos 3 MB).
2. Abre el archivo. Android te pide permitir *Instalar apps desconocidas* para tu navegador o administrador de archivos, una sola vez.
3. Juke necesita Android 8 o más nuevo, en teléfono o tableta.

La primera vez que se abre, Juke pide permiso para leer tu música. Di que sí, o la biblioteca estará vacía.
<!--/android-->

## Actualizar

Juke busca versiones nuevas al abrirse y cada 30 minutos mientras está abierto. Si hay una, te muestra qué versión tienes, cuál salió y qué cambió, y **tú** eliges: *Actualizar ahora*, *Más tarde* u *Omitir esta versión*. La descarga se verifica con su SHA-256 antes de reemplazar nada. Puedes apagar la búsqueda en *Ajustes*, y buscar a mano desde el menú ⋯ ▸ *Buscar actualizaciones…*.

<!--linux-->
Si el AppImage está en una carpeta donde puedes escribir, *Actualizar ahora* lo reemplaza en su lugar y ofrece reiniciar. Si no, Juke te dice dónde descargar el archivo nuevo.
<!--/linux-->

<!--android-->
En Android, Juke descarga el APK nuevo, lo verifica y se lo entrega al instalador de Android. La primera vez permites *Instalar apps desconocidas* para Juke.
<!--/android-->

Si tienes Juke 0.3 o una versión anterior, te ofrecerá la 1.0 solo, de la misma manera. Tu biblioteca, tus listas y tus ajustes se conservan.

---

# 3. Un recorrido por la ventana

<!--linux-->
![La ventana de Juke](img/linux/main.jpg)

Juke tiene tres paneles:

- **Arriba: el reproductor.** Anterior, reproducir / pausa, siguiente y detener; aleatorio y repetir; la pantalla con la portada, el título, la barra de tiempo y el medidor de nivel; el volumen con la luz de *Crossfade* debajo; y el botón del ecualizador.
- **Izquierda: la barra lateral.** Tus fuentes: *Biblioteca* (todas las canciones, por artista, álbum y género), *Servidores*, *Radio*, *Listas* y *Carpetas*. Cuando conectas un teléfono o una tableta aparece una sección *Dispositivos*.
- **Centro: las canciones.** Una tabla con el título, artista, álbum, tiempo, género, bitrate, origen y las listas en que está cada canción. Haz clic en una columna para ordenar; otra vez para invertir; una tercera para volver al orden natural.

Sobre la tabla está el cuadro de búsqueda (`Ctrl` + `F`), el botón de paleta para los temas de color y el menú ⋯ con todo lo demás: *Mostrar* (Favoritas, Reproducidas recientemente, Cola actual), *Buscar duplicados*, *Ajustes*, *Buscar actualizaciones*, *Enviar comentarios*, *Ver registro* y este manual.
<!--/linux-->

<!--android-->
![El reproductor en Android](img/android/player.jpg)

Juke en Android tiene cuatro pestañas abajo (una barra lateral en tableta): **Biblioteca** (tu música, por carpetas), **Servidor** (tu servidor Airsonic / Subsonic), **Radio** y **Ajustes**. Toca la barra del reproductor para abrir el reproductor grande, con la portada, la barra de tiempo y los controles.
<!--/android-->

## La canción que suena

<!--linux-->
La canción que suena tiene una pequeña insignia con barras que se mueven junto a su título. Una ✓ verde marca las canciones que ya sonaron desde que abriste Juke. Las canciones que no se pueden reproducir ahora se ven en gris (mira *Canciones que no están disponibles*).
<!--/linux-->
<!--android-->
La canción que suena aparece resaltada en la lista. Las canciones que no se pueden reproducir ahora se ven en gris.
<!--/android-->

---

# 4. Tu música

## La biblioteca

<!--linux-->
Agrega tus carpetas de música en *Ajustes ▸ Biblioteca* (o con el botón de la biblioteca vacía). Juke las lee en segundo plano, con baja prioridad, y solo vuelve a leer los archivos que cambiaron. Se mantiene rápido con decenas de miles de canciones: buscar, ordenar y filtrar nunca esperan a toda la biblioteca.

Cada vez que vuelves a la ventana, Juke revisa en silencio si hay canciones agregadas, movidas o borradas. Puedes apagar *Buscar cambios al iniciar Juke* en *Ajustes ▸ Biblioteca*.

Explora tu música en *Biblioteca*: **Todas las canciones**, **Por artista**, **Por álbum** y **Por género**. Escribe en el cuadro de búsqueda para filtrar por título, artista, álbum o género.
<!--/linux-->

<!--android-->
Juke lista la música de tu tarjeta o del almacenamiento del teléfono, **por carpetas**, como la tienes guardada. Los teléfonos sin tarjeta muestran el almacenamiento interno. Toca una carpeta para abrirla; el botón atrás sube un nivel. Con el botón de ordenar puedes poner carpetas y canciones de A a Z o de Z a A.
<!--/android-->

## Favoritas y canciones recientes

<!--linux-->
Clic derecho en una canción ▸ *Marcar como favorita*. Muestra tus favoritas, las canciones que reprodujiste hace poco y la cola actual desde el menú ⋯ ▸ *Mostrar*.
<!--/linux-->
<!--android-->
Marca una canción como favorita desde su menú. Tus favoritas están en la biblioteca.
<!--/android-->

<!--linux-->
## Editar etiquetas y portadas

Clic derecho en una canción, o selecciona varias (`Ctrl` + `A`, `Ctrl` + clic, `Mayús` + clic) ▸ *Editar metadatos…*. Solo se escriben en los archivos los campos que cambias. Puedes agregar, reemplazar o quitar la portada, o simplemente soltar una imagen sobre la ventana; se guarda dentro del archivo. Esto vale para canciones de tu computadora; las de un servidor no se pueden editar.

## Buscar duplicados

El menú ⋯ ▸ *Buscar duplicados* muestra canciones repetidas: las que tienen el mismo título, artista y álbum, o exactamente el mismo archivo.
<!--/linux-->

---

<!--linux-->
# 5. Tus propias carpetas

Bajo **Carpetas** en la barra lateral, Juke guarda tu música como tú la acomodas. No hay paso de importar: lo que hagas, simplemente sucede.

- Haz clic en el **+** junto a *Carpetas* (o `Ctrl` + `Mayús` + `N`) para crear una carpeta. Pon carpetas dentro de carpetas.
- Arrastra canciones a una carpeta desde la lista, o suelta archivos y carpetas enteras desde tu administrador de archivos sobre la barra lateral. Las carpetas que sueltas conservan su estructura.
- Clic derecho en una carpeta para renombrarla, duplicarla o borrarla, ordenar lo que tiene (A→Z, Z→A, por número, más nuevas, más viejas), o reproducirla, mezclarla o agregarla a la cola.
- Borrar una carpeta saca sus canciones de Juke. **Los archivos se quedan en tu disco.** Juke nunca mueve, renombra ni borra tus archivos de música.

## Music.juke

Juke crea una carpeta llamada **Music.juke** dentro de tu carpeta Música. Ábrela y encuentras `folders.db` (cómo está organizado todo), un directorio `Folders` con el mismo árbol como accesos a tus canciones, y un README corto. Así tu organización también se ve desde cualquier otro programa.

Si borras o mueves una carpeta en tu administrador de archivos, Juke se da cuenta en cuanto vuelves.
<!--/linux-->

---

# 6. Reproducir música

## Los controles

| Control | Qué hace |
| --- | --- |
| ⏮ Anterior | Vuelve a la canción de antes. Si ya sonaron más de 3 segundos, primero reinicia la canción. Después de elegir una canción del medio de una lista, sube por la lista. |
| ⏯ Reproducir / pausa | Reproduce o pausa. |
| ⏭ Siguiente | Pasa a la siguiente canción. |
| ⏹ Detener | Detiene. No suena nada y las marcas junto a la canción desaparecen. |
| 🔀 Aleatorio | Reproduce la lista en orden al azar: cada canción una vez, ninguna dos veces seguidas. Si lo apagas, la lista sigue en su orden desde la canción actual. |
| 🔁 Repetir | Apagado, repetir toda la lista o repetir una canción. |

Haz clic o arrastra la barra de tiempo para saltar a otro punto. Haz doble clic en una canción, o selecciónala y pulsa `Enter`, para reproducirla desde la lista.

## La cola

Clic derecho en una canción ▸ **Reproducir a continuación** la pone justo después de la actual. **Añadir a la cola** la pone al final. La cola es temporal e independiente: cuando queda vacía, sigue la lista desde la que empezaste. Verla toda en *Cola actual* (<!--linux-->menú ⋯ ▸ *Mostrar*<!--/linux--><!--android-->en el reproductor<!--/android-->): lo que suena, lo que agregaste y lo que sigue.

<!--linux-->
Si sacas una canción de la lista o carpeta que está sonando, también sale de la cola; una canción que agregas espera al final.
<!--/linux-->

## Crossfade

El crossfade mete la siguiente canción mientras la actual se va apagando, para que no haya silencio entre ellas.

<!--linux-->
Bajo el volumen hay una luz con la palabra **Crossfade**: verde cuando está activo, gris cuando está apagado. Haz clic para encenderlo o apagarlo; vuelve con los segundos que tenía la última vez (5 la primera). Para elegir cuántos segundos (de 1 a 12), abre *Ajustes ▸ Reproducción*.
<!--/linux-->
<!--android-->
Enciéndelo y elige los segundos en *Ajustes*.
<!--/android-->

El crossfade solo ocurre cuando una canción termina sola. Si saltas una canción a mano, cambia al instante, y las emisoras de radio nunca llevan fundido. Las canciones de pocos segundos más que el crossfade no se mezclan.

## Volumen

<!--linux-->
El control de volumen **es el volumen de la computadora**: las teclas de volumen de tu teclado, el volumen del panel y el mezclador lo mueven, y moverlo los mueve a ellos. El botón del altavoz silencia. Si prefieres un volumen que sea solo de Juke, apaga *El volumen sigue al de la computadora* en *Ajustes ▸ Reproducción*.
<!--/linux-->
<!--android-->
Usa las teclas de volumen del teléfono. Juke sigue el volumen del sistema.
<!--/android-->

<!--linux-->
## Teclado y teclas multimedia

Reproducir, pausar, detener, siguiente y anterior funcionan con las teclas multimedia de tu teclado o de tus auriculares, con el widget multimedia de tu escritorio (GNOME, KDE y los demás) y con herramientas como `playerctl`. La tecla Play también pausa cuando suena una canción. Los atajos están en el capítulo *Atajos de teclado*.
<!--/linux-->

<!--android-->
## La pantalla de bloqueo y los auriculares

Juke sigue sonando con la pantalla apagada. La tarjeta del reproductor en la pantalla de bloqueo, la notificación y los botones de auriculares y dispositivos Bluetooth funcionan; tocar la notificación abre Juke, y el sistema puede retomar lo que sonaba.
<!--/android-->

## Velocidad y balance

<!--linux-->
En la ventana del ecualizador (mira *El ecualizador*), bajo *Reproducción*: **Velocidad** de 0,5× a 2× y **Balance** entre izquierda y derecha. El balance necesita PulseAudio o PipeWire y una señal estéreo; si no, está desactivado.
<!--/linux-->
<!--android-->
El ecualizador está en el reproductor o en *Ajustes*.
<!--/android-->

---

# 7. Listas de reproducción

## Crear una lista

<!--linux-->
Haz clic en el **+** junto a *Listas* (o `Ctrl` + `N`), escribe un nombre y pulsa *Guardar*. O clic derecho en canciones ▸ *Añadir a la lista* ▸ *Nueva lista…* para crear una que ya tenga esas canciones. Clic derecho en una lista para renombrarla o borrarla. Las listas sobreviven a los reescaneos y a las sincronizaciones del servidor.
<!--/linux-->
<!--android-->
Abre el menú de una canción ▸ *Añadir a la lista* ▸ *Nueva lista…*, o agrégala a una que ya tengas.
<!--/android-->

## Agregar y quitar canciones

<!--linux-->
Clic derecho en una o más canciones ▸ **Añadir a la lista**. En ese menú cada lista muestra lo que tiene:

- **✓ Nombre**: todas las canciones seleccionadas ya están. **Elígela otra vez para sacarlas.**
- **◐ Nombre**: algunas de las canciones están. Elígela para agregar las que faltan.
- **Nombre** sin marca: ninguna está. Elígela para agregarlas.

Una canción que ya está en una lista **nunca se agrega dos veces**; Juke te dice «Esa canción ya está en…». También puedes arrastrar canciones de la lista hasta una lista de la barra lateral.

Dentro de una lista, clic derecho ▸ *Quitar de la lista* saca las canciones seleccionadas. Las listas hechas antes de la 1.0 pueden tener una canción dos veces; puedes quitar cada copia por separado.

Cada canción de la biblioteca también muestra, en la columna **En listas**, los nombres de las listas que la tienen.
<!--/linux-->
<!--android-->
En el menú de una canción, las listas que ya la tienen aparecen marcadas; elige una otra vez para sacar la canción. Una canción nunca se agrega dos veces a la misma lista.
<!--/android-->

---

# 8. Servidores: Airsonic y Subsonic

Juke puede reproducir la música de tu propio servidor: Airsonic, Airsonic-Advanced, Subsonic, Navidrome y todo lo que hable el mismo protocolo. Las canciones se reproducen directamente; no se descarga nada antes.

## Conectar tu servidor

Abre <!--linux-->*Ajustes ▸ Airsonic*<!--/linux--><!--android-->*Ajustes* ▸ la sección del servidor<!--/android--> y escribe la dirección del servidor (por ejemplo `http://tu-servidor:4040`), tu usuario y tu contraseña. Pulsa *Probar conexión*. Luego *Sincronizar Airsonic* importa la biblioteca del servidor. Usa `https://` cuando puedas.

Explora el servidor en **Servidores** **por carpetas**, tal como las muestra, o por artista, álbum y género. Una biblioteca de 6.000 canciones se sincroniza en unos 8 segundos. Las canciones que terminas se informan al servidor (scrobble).

## Canciones que no están disponibles

Una canción de un servidor necesita internet (o tu red) y que el servidor responda. Una canción local necesita su archivo, que puede estar en un NAS o en un disco que no está conectado.

Cuando una canción no se puede reproducir ahora:

- Se pone **gris**, y la columna *Origen* dice **Conéctate** (el servidor no responde) o **Sin conexión** (el disco o la carpeta de red no está).
- Pasa el ratón para ver por qué.
- Si intentas reproducirla, Juke te dice por qué y, si es de un servidor, vuelve a preguntar por si ya regresó.
- Una lista o cola pasa de largo esas canciones en vez de detenerse.

Juke lo revisa al abrirse, cuando vuelves a la ventana, cuando la computadora entra o sale de la red y cuando falla una canción del servidor. Cuando la conexión vuelve, el gris se quita solo y Juke te avisa una vez.

---

# 9. Radio por internet

En **Radio**: *Mis emisoras* (las tuyas) y *Explorar radio* (el directorio de la comunidad).

- **Explorar radio:** busca por nombre o elige una etiqueta. ♥ guarda una emisora; ▶ la sintoniza.
- **Añadir emisora por URL…:** pega cualquier dirección. Juke muestra *Buscando una señal de audio…* mientras lo averigua. Acepta una señal directa (`.mp3`, `.aac`, `.ogg`, `.m3u8`), una dirección Icecast o Shoutcast, una lista `.pls` o `.m3u`, o una página web que tenga un reproductor. Una página con varias emisoras te las ofrece todas. El nombre y el icono salen de la emisora.
- **En el aire:** la pantalla muestra **EN VIVO**, la emisora y la canción que suena, cuando la emisora la envía.
- **Las emisoras se mueven.** Las emisoras cambian de dirección todo el tiempo. Una emisora guardada recuerda de dónde vino y, cuando se mueve, Juke la sigue y recuerda la dirección nueva.

Las emisoras que piden inicio de sesión o usan señales protegidas no se pueden reproducir.

---

# 10. Letras

## Ver la letra

Un panel a la derecha se abre solo cuando la canción que suena tiene letra, y se queda cerrado cuando no la tiene. Las letras **sincronizadas** iluminan la línea que se está cantando. Juke lee la letra que guardaste, un archivo `.lrc` junto a la canción y la letra que traiga el archivo en sus etiquetas.

<!--linux-->
![Letra sincronizada junto a la canción](img/linux/lyrics.jpg)
<!--/linux-->

## Buscar la letra

Clic derecho en una canción ▸ **Buscar letra…**. Juke busca en varios servicios gratuitos a la vez: LRCLIB, NetEase Cloud Music y lyrics.ovh. Juntos cubren inglés, español, portugués, chino, japonés, coreano, árabe, hindi y muchos idiomas más.

- El título se limpia de «(feat. …)», «[Remastered]» y parecidos, en cualquier escritura, y se entiende «Artista - Canción».
- Los resultados se ordenan con la mejor coincidencia primero, las sincronizadas antes que las planas. Puede aparecer la misma canción de otro artista (una versión); revisa el artista antes de usarla.
- Si un servicio está ocupado, Juke vuelve a preguntar y te dice cuál no respondió.
- Lo que encontró se guarda unos días, así que repetir una búsqueda es instantáneo y funciona sin internet.

En los resultados, elige uno y pulsa *Usar*. Solo se envían el nombre, el artista, el álbum y la duración de la canción.

## Agregar la tuya

Clic derecho en una canción ▸ **Añadir letra…**: pégala, o importa un archivo `.lrc` (líneas como `[01:23.45] palabras`, que hacen que siga a la canción). Los archivos antiguos en otras codificaciones (GBK, Shift-JIS, EUC-KR…) se leen bien, y los idiomas de derecha a izquierda se muestran como corresponde.

## Búsqueda automática

En *Ajustes ▸ Biblioteca*, *Buscar letras en línea* busca por sí solo las canciones que no tienen letra, cuando empiezan a sonar. Viene apagado.

<!--android-->
## Karaoke

En Android la pantalla de letras tiene un modo **Karaoke**: líneas grandes y una cuenta regresiva antes de cada frase.
<!--/android-->

---

# 11. El ecualizador

<!--linux-->
Ábrelo con `Ctrl` + `E` o con el botón a la derecha del reproductor.

![El ecualizador](img/linux/equalizer.jpg)
<!--/linux-->
<!--android-->
Abre el ecualizador desde el reproductor.
<!--/android-->

No hace falta ser ingeniero de sonido. Mueve una barra **hacia arriba** para oír **más** de esa parte de la música, **hacia abajo** para oír **menos**. O simplemente elige un preset.

## Qué cambia cada barra

| Barra | Nombre | Qué es |
| --- | --- | --- |
| 60 Hz | **Graves profundos** | El retumbar que sientes en el pecho: bombo, sub-graves, 808. Demasiado suena retumbante. |
| 170 Hz | **Graves** | Pegada y calidez: el bajo y el cuerpo del bombo. |
| 310 Hz | **Medios bajos** | El cuerpo de voces y guitarras. Demasiado suena turbio, muy poco suena delgado. |
| 600 Hz | **Medios** | El centro de casi todos los instrumentos. Demasiado suena encajonado. |
| 1 kHz | **Voz** | Donde están los cantantes y la caja. Súbela para entender mejor la letra. |
| 3 kHz | **Claridad** | Detalle y mordiente. Demasiado es áspero y cansa. |
| 6 kHz | **Nitidez** | Las «s» y los platillos de la batería. Demasiado silba. |
| 12 kHz | **Brillo** | Platillos y destellos. Súbelo para un sonido más brillante. |
| 14 kHz | **Lustre** | El lustre sobre la música. |
| 16 kHz | **Aire** | La sensación abierta de lo más alto. |

Las barras están agrupadas en **Graves**, **Medios** y **Agudos**. La curva sobre las barras muestra el sonido que estás moldeando.

## Nivel (preamp)

La primera barra, *Nivel*, es el nivel general del ecualizador. Si el sonido se distorsiona al subir una banda, bájalo. Los presets lo ajustan solos, así que un realce nunca hace que el sonido se rompa.

## Presets

Treinta y cinco curvas listas: *Plano*, *Rock*, *Pop*, *Jazz*, *Clásica*, *Electrónica*, *Heavy Metal*, *Techno*, *Hip-Hop*, *R&B*, *Baile*, *Acústica*, *Blues*, *Country*, *Reggae*, *Latina*, *Dembow*, *Reggaetón*, *Salsa*, *Merengue*, *Bachata*, *Cumbia*, *Afrobeat*, *K-Pop*, *Voces*, *Voz / Podcast*, *En vivo*, y ajustes para el lugar o la manera de escuchar: *Graves potentes*, *Menos graves*, *Agudos brillantes*, *Menos agudos*, *Realce a bajo volumen*, *Altavoces pequeños*, *Auriculares* y *Noche (silencioso)*.

Mueve una barra y el preset pasa a *Personalizado*. **Guardar preset…** conserva tu propia curva con un nombre; *Borrar* la quita. *Restablecer* vuelve a *Plano*. El ecualizador sigue encendido cuando cambia la canción.

---

# 12. Aspecto e idioma

<!--linux-->
- **Oscuro, claro o como tu escritorio:** *Ajustes ▸ General ▸ Tema*, o `Ctrl` + `T` para cambiar.
- **Veinte temas de color** (diez claros, diez oscuros) desde el botón de paleta junto al menú ⋯. Todos están revisados para que se lean bien.
- **Idioma:** español o inglés, en *Ajustes ▸ General*. Cambia al instante, incluido este manual.
- El medidor de nivel de la pantalla es decorativo (un medidor animado, no un analizador). *Ajustes ▸ Reproducción* deja que se mueva solo con corriente, siempre, o nunca.
<!--/linux-->
<!--android-->
- **Colores:** *Ajustes ▸ Colores* tiene los mismos veinte temas, oscuros y claros.
- **Idioma:** español o inglés, en *Ajustes*.
<!--/android-->

---

<!--linux-->
# 13. Teléfonos y tabletas

Conecta un teléfono o tableta Android con un cable USB y, en el aparato, elige *Transferencia de archivos*. Aparece en **Dispositivos** en la barra lateral.

- Arrastra canciones, o carpetas enteras, al dispositivo para copiarlas.
- Clic derecho en canciones ▸ *Enviar a* el dispositivo.
- Puedes ver lo que hay en el dispositivo, quitar canciones de él y cancelar una transferencia en curso.
- Al terminar, usa el botón de expulsar junto al dispositivo antes de desconectarlo.

Juke solo copia archivos de música y nunca cambia tu biblioteca.
<!--/linux-->

---

# 14. Ajustes

<!--linux-->
Ábrelos con `Ctrl` + `,` o desde el menú ⋯. Hay cuatro pestañas:

![Ajustes, Reproducción](img/linux/settings.jpg)

| Pestaña | Qué tiene |
| --- | --- |
| **General** | Idioma, tema, *Buscar actualizaciones automáticamente*, *Mostrar Juke en el menú de aplicaciones*. |
| **Reproducción** | *El volumen sigue al de la computadora*, *Crossfade* (segundos, o apagado) y el medidor de nivel. |
| **Biblioteca** | Tus carpetas de música, *Buscar cambios al iniciar Juke* y *Buscar letras en línea*. |
| **Airsonic** | La dirección del servidor, el usuario y la contraseña, y *Probar conexión*. |
<!--/linux-->
<!--android-->
*Ajustes* tiene el idioma, los colores, las opciones de letras y de actualizaciones, *Volver a escanear*, el ecualizador y una sección de **Ayuda** con *Enviar comentarios*, el registro de la app (con los datos privados ocultos) y *Apoyar en Ko-fi*.
<!--/android-->

---

# 15. Actualizaciones, comentarios y privacidad

## Comentarios

**Enviar comentarios…** y **Ver registro…** están en el menú ⋯ (*Ajustes ▸ Ayuda* en Android). Un reporte se abre como una nueva incidencia en GitHub para que lo revises antes de enviarlo. Tu carpeta personal, tus contraseñas y la dirección de tu servidor se ocultan primero. Juke no envía nada por sí solo.

## Privacidad

Juke no tiene cuentas, telemetría ni analíticas. Solo se conecta a:

| Qué | Cuándo |
| --- | --- |
| Tu servidor Airsonic / Subsonic | Solo si configuras uno. |
| `api.github.com` | Al abrirse y cada 30 minutos, para buscar una versión nueva, si dejas la búsqueda activada. Solo se envían el nombre del programa y la versión. |
| Radio Browser y las emisoras | Solo cuando abres *Explorar radio*, añades una emisora o sintonizas. |
| `lrclib.net`, `music.163.com`, `api.lyrics.ovh` | Solo cuando pulsas *Buscar letra…*, o si activaste *Buscar letras en línea*. Reciben el nombre, el artista, el álbum y la duración de la canción. |

Tu música, tus listas y tus ajustes siempre son tuyos y se quedan en tu dispositivo.

## Dónde se guarda cada cosa

<!--linux-->
Tu biblioteca es una base de datos en `~/.local/share/juke`, los ajustes están en `~/.config/juke` y las portadas en `~/.cache/juke`. El registro es `juke.log`. Tus carpetas se describen en `Music.juke`, dentro de tu carpeta Música.
<!--/linux-->
<!--android-->
Todo se queda dentro del almacenamiento propio de la app en el teléfono. Al desinstalar Juke se borra.
<!--/android-->

---

<!--linux-->
# 16. Atajos de teclado

| Atajo | Acción |
| --- | --- |
| `Espacio` | Reproducir / pausa |
| `Enter` o doble clic | Reproducir la canción seleccionada |
| `Ctrl` + `→` / `←` | Siguiente / anterior |
| Teclas multimedia | Reproducir, pausar, detener, siguiente, anterior |
| `Ctrl` + `F` | Buscar |
| `Ctrl` + `N` | Nueva lista |
| `Ctrl` + `Mayús` + `N` | Nueva carpeta |
| `Ctrl` + `E` | Ecualizador |
| `Ctrl` + `L` | Mostrar / ocultar la letra |
| `Ctrl` + `T` | Cambiar entre claro y oscuro |
| `Ctrl` + `,` | Ajustes |
| `F1` | Este manual |
| `Ctrl` + `Q` | Salir |
<!--/linux-->

---

# 17. Cuando algo sale mal

**No hay sonido.** Revisa que PulseAudio o PipeWire estén funcionando y que el volumen no esté silenciado. Si apagaste *El volumen sigue al de la computadora*, revisa también el volumen propio de Juke.

**Mi música no aparece.** <!--linux-->Agrega la carpeta en *Ajustes ▸ Biblioteca*; Juke indexa en segundo plano y la barra de estado muestra el avance.<!--/linux--><!--android-->Revisa que le diste a Juke permiso para leer tu música.<!--/android-->

**Las teclas multimedia no hacen nada.** <!--linux-->Cierra cualquier otro reproductor que se abrió antes; las teclas van al último que se anunció. Juke se anuncia al escritorio cuando se abre.<!--/linux--><!--android-->Asegúrate de que ningún otro reproductor se quedó con los botones de los auriculares.<!--/android-->

**Hay canciones en gris.** El servidor no responde o el disco no está conectado. Conéctate o conecta el disco; Juke se da cuenta solo.

**Buscar letra dice que no encontró nada.** Puede que la canción no esté en los servicios gratuitos con esa escritura. Prueba «Artista - Canción» en el título, o agrega la letra tú mismo (mira *Letras*).

**Una emisora de radio dejó de sonar.** Las emisoras se mueven; Juke las sigue cuando puede. Busca la misma emisora en *Explorar radio*.

**¿Sigue sin funcionar?** Usa *Enviar comentarios…*: el reporte incluye el registro con tus datos privados ocultos.

---

# 18. Acerca de Juke

Juke lo hace Vezzu Studio. Es gratis para usarlo con cualquier fin, en todos los ordenadores y dispositivos que tengas. El código está publicado para poder leerlo y comprobarlo; los términos completos están en la Licencia de Juke 1.0. El software de otros que Juke incluye conserva su propia licencia, indicada en `NOTICE.md`.

Si Juke te es útil, puedes apoyarlo en Ko-fi desde el botón de la barra lateral<!--android--> o en *Ajustes*<!--/android-->.

Gracias por escuchar.
