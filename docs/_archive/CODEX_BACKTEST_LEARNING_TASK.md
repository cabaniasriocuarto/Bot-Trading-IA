SOS CODEX. NO refactor masivo. NO tocar módulos fuera del alcance. Solo implementar lo pedido.

OBJETIVO
Integrar el Knowledge Pack v2 (archivos YAML) para:
1) registrar 5 estrategias (strategy_templates.yaml + strategies_v2.yaml),
2) aprendizaje Opción B (recomienda + requiere aprobación humana),
3) Safe Update with Gates + canary schedule,
4) Backtest UI con colores por KPI (visual_cues.yaml),
5) mantener todo en español en la UI donde corresponda.

ARCHIVOS NUEVOS/ACTUALIZADOS (ya existen en el repo):
- knowledge/templates/strategy_templates.yaml (v2)
- knowledge/templates/parameter_ranges.yaml (v2)
- knowledge/templates/filters.yaml (v2)
- knowledge/policies/gates.yaml (v2)
- knowledge/templates/learning_engines.yaml (nuevo)
- knowledge/templates/visual_cues.yaml (nuevo)
- knowledge/strategies/strategies_v2.yaml (nuevo)

TAREAS (BACKEND)
A) Knowledge Loader:
- Extender KnowledgeLoader para cargar también:
  - knowledge/templates/learning_engines.yaml
  - knowledge/templates/visual_cues.yaml
  - knowledge/strategies/strategies_v2.yaml
- Validar esquema simple (pydantic o validación manual). Si falta algo, levantar error claro.

B) Learning (Opción B):
- Implementar/asegurar que el “cerebro”:
  - NO cambia LIVE sin aprobación humana.
  - Puede recomendar: (estrategia principal sugerida, pesos sugeridos, parámetros sugeridos).
- Exponer endpoints:
  - GET /api/v1/learning/status
  - POST /api/v1/learning/recommend (devuelve recomendación basada en engines activos)
  - POST /api/v1/learning/approve (solo admin) => crea candidato para rollout, NO auto LIVE
  - POST /api/v1/learning/reject

C) Safe Update with Gates + Canary:
- Implementar RolloutManager persistente (sqlite) con estados:
  - CANDIDATE_CREATED -> OFFLINE_EVAL -> GATES_PASS -> CANARY_5 -> CANARY_15 -> CANARY_35 -> CANARY_60 -> LIVE_100
  - rollback inmediato si breach de gate en etapa canary.
- Comparación contra baseline estable antes de avanzar.
- Blending mode soportado: both_must_agree (default).

D) Backtests (data real y costos):
- Confirmar que backtest usa datos reales cuando están descargados (no sintéticos).
- Asegurar que fees/spread/slippage/funding afectan pnl_net (ya hay campos; verificar consistencia).
- Agregar “trade_count / total_entries / total_exits / roundtrips” en métricas siempre.

TAREAS (FRONTEND)
E) KPI Coloring:
- Cargar visual_cues.yaml desde backend (endpoint o include en response).
- Pintar tarjetas/celdas KPI:
  - violeta muy malo, rojo malo, naranja aceptable, amarillo bueno, verde excelente
- Mostrar etiqueta “Muy malo/Malo/Aceptable/Bueno/Excelente”.

F) Toggle Descriptions:
- En el panel “Learning Engines”, al lado de cada switch, mostrar:
  - descripción corta + tooltip con ui_help del YAML.

G) Español:
- Ajustar textos visibles: labels, botones, tooltips y mensajes en español.

RESTRICCIÓN CLAVE
NO modificar nada más del sistema. Si algo falta, crear el mínimo código necesario (nuevo archivo/módulo) sin romper estructura existente.

ENTREGABLE
- Commits pequeños y claros.
- Tests unitarios para:
  - load knowledge v2
  - gates eval
  - rollout transitions
  - backtest metrics (incluye trade_count)
