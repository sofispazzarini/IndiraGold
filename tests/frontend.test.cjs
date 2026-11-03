const test = require('node:test');
const assert = require('node:assert/strict');
const { coincide } = require('../home/static/home/catalogo_filtros.js');
const { calcular } = require('../pedidos/static/pedidos/descuentos_pago.js');
const datos = { cat: '1', name: 'Remera Algodón', talles: '2,3', colores: '5,6,' };
const filtros = { categoria: '', busqueda: '', talles: [], color: '' };

test('talles: unión de dos o más seleccionados, sin coincidencia y todos', () => {
  assert.equal(coincide(datos, { ...filtros, talles: ['1', '3'] }), true);
  assert.equal(coincide(datos, { ...filtros, talles: ['1', '4'] }), false);
  assert.equal(coincide(datos, filtros), true);
});
test('combinar talles, categoría, color y búsqueda sin tildes', () => {
  const seleccion = { categoria: '1', busqueda: 'algodon', talles: ['2', '3'], color: '5' };
  assert.equal(coincide(datos, seleccion), true);
  for (const cambio of [{ categoria: '2' }, { busqueda: 'bota' }, { color: '9' }, { talles: ['8'] }]) {
    assert.equal(coincide(datos, { ...seleccion, ...cambio }), false);
  }
});
test('limpiar filtros muestra productos sin talles también', () => {
  assert.equal(coincide({ ...datos, talles: '' }, filtros), true);
  assert.equal(coincide({ ...datos, talles: '' }, { ...filtros, talles: ['2'] }), false);
});
test('cambio de transferencia a efectivo o MP reemplaza el descuento', () => {
  assert.deepEqual(calcular(50000, 8000, 10), { descuento: 5800, total: 52200 });
  assert.deepEqual(calcular(50000, 8000, 15), { descuento: 8700, total: 49300 });
  assert.deepEqual(calcular(50000, 8000, 0), { descuento: 0, total: 58000 });
});
test('cambio de envío recalcula también su descuento', () => {
  assert.deepEqual(calcular(50000, 0, 10), { descuento: 5000, total: 45000 });
  assert.deepEqual(calcular(50000, 8000, 10), { descuento: 5800, total: 52200 });
  assert.deepEqual(calcular(50000, 10000, 10), { descuento: 6000, total: 54000 });
});
test('centavos, porcentajes fraccionarios, cupón y 100%', () => {
  assert.deepEqual(calcular(0.05, 0, 10), { descuento: 0.01, total: 0.04 });
  assert.deepEqual(calcular(123.45, 6.78, 12.34), { descuento: 16.07, total: 114.16 });
  assert.deepEqual(calcular(50000, 8000, 10, 5000), { descuento: 5300, total: 47700 });
  assert.deepEqual(calcular(50000, 8000, 100), { descuento: 58000, total: 0 });
});
