const playbooks: Record<string, string> = {
  "Tendencia + Pullback + Confirmación Order Flow": `Tendencia + pullback con confirmacion de microestructura.
- Regimen de tendencia en marco mayor (EMA20/EMA50/EMA200 + ADX).
- Trigger en 5m: pullback a EMA20 + RSI en rango valido + ruptura de vela previa.
- Confirmacion order flow: OBI/CVD coherentes en 1m antes de enviar orden.
- Ejecucion sensible a costos con guardas de spread/slippage.`,
  "trend-pullback": `Tendencia + pullback con confirmacion de microestructura.
- Regimen de tendencia en marco mayor.
- Entrada en pullback a soporte/resistencia dinamica.
- Gate de order flow: OBI/CVD/VPIN.
- Ejecucion consciente de costos y guarda de spread.`,
  "mean-reversion": `Mean reversion con guardas de volatilidad y liquidez.
- Detecta desvio extremo respecto de media movil.
- Solo habilita reversa en regimen no tendencial.
- Invalidacion ajustada + time-stop.
- Tamaño de posicion ajustado por estado de drawdown.`,
  momentum: `Momentum cross-sectional con control de turnover.
- Rankea simbolos por momentum ajustado por riesgo.
- Entra top decil bajo limites de spread/volumen.
- Salidas dinamicas con trailing + volatilidad.
- Probado bajo shocks de fee/slippage.`,
};

export function getPlaybook(strategyName: string) {
  return playbooks[strategyName] || "No hay playbook disponible.";
}
