# Compañeros IA (versión móvil y gratis)

Chat con personajes de IA que tienen memoria, nivel de afinidad, historia que se desbloquea, **fotos realistas** y **voz natural**. Todo gratis.

| Parte | Servicio | Coste |
|---|---|---|
| Conversación | Google Gemini (nivel gratuito) | 0 € (sin tarjeta) |
| Fotos | Pollinations.ai, modelo FLUX | 0 € (sin registro) |
| Voz | edge-tts (voces neuronales) | 0 € |
| Alojamiento para el móvil | Streamlit Community Cloud | 0 € |

---

## 1. Consigue tu clave gratis de Gemini (2 minutos)
1. Entra en https://aistudio.google.com con tu cuenta de Google.
2. Pulsa **Get API key** → **Create API key**. Cópiala. **No hace falta tarjeta.**

## 2. Súbelo a internet para usarlo en el móvil
1. Crea una cuenta en https://github.com y un repositorio nuevo (por ejemplo `companeros`).
2. Pulsa **Add file → Upload files** y sube todos los archivos de esta carpeta (no subas `partida.db`).
3. Entra en https://share.streamlit.io, inicia sesión con GitHub y pulsa **Create app**.
4. Elige tu repositorio y `app.py` como archivo principal.
5. En **Advanced settings → Secrets** pega esto (cambia los valores):
   ```toml
   GEMINI_API_KEY = "tu-clave-de-gemini"
   CLAVE_APP = "una-contraseña-que-elijas"
   ```
   La contraseña sirve para que nadie más use tu app ni gaste tu cuota gratuita.
6. Pulsa **Deploy**. En unos minutos tendrás una dirección tipo `https://tu-app.streamlit.app`.

## 3. Ponlo como app en el móvil
Abre esa dirección en el móvil:
- **Android (Chrome):** menú ⋮ → **Añadir a pantalla de inicio**.
- **iPhone (Safari):** botón compartir → **Añadir a pantalla de inicio**.

Te quedará un icono como si fuera una app.

---

## 💬 Chat como de verdad
- Escribe a su manera (Lucía con "q" y emojis, Kai en minúsculas...), a veces manda **varios mensajes seguidos** con "escribiendo…" y **notas de voz**.
- Ves **🟢 en línea** o **últ. vez hace 2 h** según lo que esté haciendo, y **✓✓ Leído** en tus mensajes.
- **Te escribe primero** si llevas más de 3 horas sin entrar.
- **Mándale fotos** con el clip 📎 del chat (tu comida, tu perro, un paisaje...) y las comenta.
- **📖 Historias de hoy:** fotos de lo que ha hecho durante el día.

## 🌍 Vida propia
- **Rutina diaria:** trabaja, hace recados, sale el finde, duerme. Si está trabajando contesta corto; si está durmiendo, tarda.
- **El mundo real:** sabe la fecha, la hora, los festivos y **el tiempo real** de su ciudad (Lucía en Madrid, Kai en Barcelona).
- **Estado de ánimo** que cambia cada día.
- **Fechas importantes:** si le dices "el jueves tengo un examen", lo apunta y luego te pregunta cómo te fue (☰ → Fechas).

## 📍 Escenarios que cambian
- Siempre está en algún sitio (arriba: "📍 en un bar de tapas · por la noche · Madrid: lloviendo, 12 °C").
- Si en la conversación quedáis en algún sitio, **cambia de lugar** (durante 3 h; luego vuelve a su rutina).
- Fotos, llamadas y quedadas usan ese fondo, con la luz de la hora y el tiempo real.

## 📹 Videollamada
Botón **📹 Llamar**: su cara a pantalla completa, reloj de llamada, le hablas con el micro y responde con su voz. Su imagen cambia según lo que hace (se ríe, se mueve...) con un fundido suave.

## 💞 Quedar en persona
Botón **💞 Quedar** → eliges el sitio → **Ir ahora**.
- **La ves como con tus propios ojos**, frente a ti, en ese lugar. Cada momento genera una imagen nueva de lo que hace.
- Te **narra** sus gestos y el ambiente (*se ríe y se aparta el pelo mientras el camarero deja dos cafés*) y **te habla con su voz**.
- Tú hablas por el micro o escribes, y puedes hacer acciones entre *asteriscos* (`*te invito a otra ronda*`) o con los botones 🥂 🚶 🤗 😂.
- Si proponéis ir a otro sitio, la escena cambia de lugar.
- **👋 Despedirse** para terminar la quedada. Todo lo que pase queda en su memoria.

Consejos: la primera vez el móvil pedirá permiso para el micrófono. Si el audio no suena solo, toca **▶ Escuchar**.

## Cosas a saber
- **Límites gratuitos:** Gemini gratis tiene un máximo de mensajes por minuto y por día. Si lo pasas, la app te avisará; espera un rato.
- **Las fotos** tardan unos segundos en aparecer. La cara del personaje se parece entre fotos, pero no es idéntica siempre.
- **La partida en la nube** se puede borrar si la app se reinicia o se "duerme" tras días sin uso. Usa **☰ → Guardar / cargar partida** para descargarla y recuperarla.
- **Voz:** activa "Leer sus mensajes en voz alta" en el menú ☰.
- **Cada imagen nueva** (fotos, llamada, quedada) tarda unos segundos en generarse; mientras tanto ves la anterior.

## Probar en el ordenador
```bash
pip install -r requirements.txt
# Windows (PowerShell):  $env:GEMINI_API_KEY="tu-clave"; streamlit run app.py
# Mac / Linux:           GEMINI_API_KEY=tu-clave streamlit run app.py
```
Sin clave puedes probar la interfaz con `BACKEND=demo`.

## Personalizar
- **Personajes:** `personajes.json`. El campo `apariencia` (en inglés) define cómo salen en las fotos; `voz` es la voz de edge-tts (por ejemplo `es-ES-ElviraNeural`, `es-ES-AlvaroNeural`, `es-MX-DaliaNeural`, `es-AR-ElenaNeural`).
- **Estilo de las fotos:** `ESTILO_FOTO` en `motor.py`.
- **Niveles:** `NIVELES` en `motor.py`.
- **Rutina:** `rutina` en `personajes.json` (días `laborables`, `finde` o `todos`, horas, lugar y qué hace).
- **Cada cuánto te escribe primero:** `HORAS_PARA_ESCRIBIR_PRIMERO` en `motor.py`.
