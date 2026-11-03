(function (root) {
  function calcular(subtotal, envio, porcentaje, cupon = 0) {
    const centavos = valor => Math.round(Number(valor) * 100);
    const productos = centavos(subtotal);
    const base = Math.max(0, productos - Math.min(Math.max(centavos(cupon), 0), productos)) + centavos(envio);
    const descuento = Math.round(base * Math.round(Number(porcentaje) * 100) / 10000);
    return { descuento: descuento / 100, total: (base - descuento) / 100 };
  }
  const api = { calcular };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.IndiraDescuentos = api;
})(globalThis);
