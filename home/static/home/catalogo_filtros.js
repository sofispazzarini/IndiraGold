(function (root) {
  function normalizar(texto) {
    return (texto || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }
  function coincide(datos, filtros) {
    const lista = valor => (valor || '').split(',').map(v => v.trim()).filter(Boolean);
    return (!filtros.categoria || datos.cat === filtros.categoria)
      && normalizar(datos.name).includes(normalizar(filtros.busqueda).trim())
      && (!filtros.talles.length || filtros.talles.some(talle => lista(datos.talles).includes(talle)))
      && (!filtros.color || lista(datos.colores).includes(filtros.color));
  }
  const api = { coincide };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.IndiraCatalogo = api;
})(globalThis);
