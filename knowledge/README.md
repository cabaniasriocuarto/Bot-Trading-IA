# Knowledge Pack (RTLAB)

Paquete base de conocimiento para el loop de investigacion del bot.

Incluye:

- Plantillas de estrategias permitidas
- Filtros/reglas de mercado
- Rangos de parametros para generar candidatos
- Gates/politicas de validacion
- Guardrails de investigacion
- Glosario de metricas

Uso esperado:

1. El backend carga `knowledge/**` con `KnowledgeLoader`.
2. El research loop genera candidatos solo con plantillas/rangos/filtros permitidos.
3. Las recomendaciones se validan con PBO/DSR antes de mostrarse.

