# Decisiones por acordar con el equipo

Tras [cerrar la demo de Investing.com](../historico/cartera/CIERRE_DEMO_INVESTING.md), quedan pendientes la validación autenticada de Alpaca Paper, las condiciones de uso de EODHD por el equipo y la adopción de la cartera multiactivo por el consumidor definitivo de inteligencia. La decisión de proveedor cuenta con una [ADR](../adr/0001-market-data-provider.md). El [contexto para la próxima sesión](../../AGENTS.md#siguiente-incremento-módulo-de-fuentes) describe el punto de partida del módulo de fuentes.

## Cartera real

Después de validar las dos vías de la demo, el equipo deberá elegir los orígenes para el primer uso con posiciones reales.

- **Fichero.** Elegir la entidad, el tipo de extracto de posiciones y su formato (CSV o PDF). El extracto de valores de Trade Republic es candidato. Validar en una muestra anonimizada cómo se identifican los instrumentos, las cantidades y la fecha de referencia.
- **API.** Elegir el bróker y la cuenta autorizada para la primera sincronización real. Comprobar que la API oficial permite leer las posiciones con autorización de solo lectura y que sus condiciones permiten el uso previsto.

## Preguntas de planificación inicial

La tabla conserva las opciones consideradas al arrancar el proyecto. En la primera fila, la integración se refiere a las fuentes de noticias.

| Prioridad | Decisión | Recomendación provisional | Impacto |
|---|---|---|---|
| Bloqueante para integración | Qué URLs/secciones exactas quieren monitorizar | Comenzar por 1 fuente editorial y 1 documental con licencia validada | Define conectores y derechos |
| Alta | Para quién se entrega la primera demo | Un usuario, cartera ficticia y posibilidad posterior de cargar la propia | Seguridad y complejidad |
| Alta | Qué instrumentos de verdad probar | 1 acción + 1 ETF con subyacente conocido + 1 fondo con holdings parciales | Casos de aceptación |
| Alta | Qué se espera por propuesta | Mantener/aumentar/reducir/revisar solo cualitativo y con abstención | Evaluación del LLM |
| Alta | Si hay credenciales/cartera real en la demo | No; datos sintéticos y sin despliegue público inicial | Privacidad |
| Alta | Plazo, horas/semana y presupuesto mensual máximo | Definir antes de contratar APIs/hosting/LLM | Prioridades |
| Media | Idioma de interfaz, noticias e informes | UI y reportes en español; fuentes ES/EN | Prompt/evaluación |
| Media | Hosting y herramientas del equipo | GitHub + despliegue demo protegido una vez implementada autenticación | DevOps |
| Media | Elegir proveedor/modelo LLM | Comparar coste, latencia, citas y salidas JSON con un pequeño benchmark | Ingeniería de IA |
| Diferible | RAG, MCP, multiagentes y multiusuario | No en primer prototipo | Evita sobreingeniería |

## Preguntas de la primera reunión

1. ¿El entregable inmediato debe ser una demo local para vuestro equipo o una aplicación accesible públicamente?
2. ¿Qué 2–3 instrumentos concretos (preferiblemente ISIN) usaréis para validar exposición directa e indirecta?
3. ¿Cuáles son las URLs exactas de 1–2 fuentes que consideráis prioritarias, y qué secciones queréis seguir?
4. ¿Cuántas personas desarrollarán, con qué experiencia y horas semanales, y con qué presupuesto total mensual para servicios?
5. ¿Queréis propuestas cualitativas de revisar/mantener/aumentar/reducir o también pesos objetivo? (No recomiendo pesos objetivo en la v1.)

El [acta de I1](../historico/I1/CIERRE_I1_CARTERA_Y_PRECIOS.md) recoge qué decisiones y comprobaciones se cerraron después de esta primera reunión.
