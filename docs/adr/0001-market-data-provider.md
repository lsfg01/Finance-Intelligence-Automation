# ADR 0001 · Proveedor de precios de I1

**Estado.** EODHD seleccionado para precios y valores liquidativos de I1. El BCE aporta FX de referencia. Decisión registrada el 23 de noviembre de 2026.

La selección se apoya en la resolución de las clases de F01, F02 y F03 y en el cotejo del NAV de las tres clases. Para F02 se conserva el valor de EODHD, **13,4877 EUR** por participación el 20 de noviembre de 2026. El cotejo documentado con Fidelity coincide a dos decimales. La matriz conserva los resultados de cada ejecución y los casos con cobertura o validación pendientes. [Matriz del spike](../historico/I1/RESULTADOS_SPIKE_I1.md).

El modo simulado utiliza observaciones fijas sin credenciales. El modo de mercado se inicia por petición explícita y usa símbolos fijados por clase o listing. La observación conserva la fecha efectiva, la recuperación en UTC, la moneda, el proveedor y la clasificación. El BCE aporta USD por EUR y el motor requiere la tasa efectiva de la fecha del precio. [API diaria de EODHD](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes) · [Adaptador del BCE](../ADAPTADOR_FX_BCE.md).

EODHD considera comercial el uso por varias personas y la visualización para terceros. Habilitar el modo de mercado en el equipo requiere acordar el acceso, coste, conservación de snapshots y visualización con las condiciones aplicables. La habilitación local autoriza al proceso API a consultar y guardar datos. La prueba en vivo se ejecuta por separado con una credencial local. [Condiciones de EODHD](https://eodhd.com/help/commercial).
