const test = require('node:test');
const assert = require('node:assert/strict');
const { coincide } = require('../home/static/home/catalogo_filtros.js');
const { calcular } = require('../pedidos/static/pedidos/descuentos_pago.js');
const datos = { cat: '1', name: 'Remera Algodón', talles: '2,3', colores: '5,6,' };
const vm = require('node:vm');
const fs = require('node:fs');

function navegadorCsrf() {
  const llamadas = [];
  const eventos = {};
  const document = { cookie: 'csrftoken=actual', addEventListener: (name, fn) => { eventos[name] = fn; }, querySelectorAll: () => [] };
  const window = { addEventListener: (name, fn) => { eventos[name] = fn; }, fetch: (url, options) => { llamadas.push({ url, options }); return Promise.resolve({ status: 403 }); } };
  vm.runInNewContext(fs.readFileSync('home/static/home/csrf.js', 'utf8'), {
    document, window, location: { href: 'https://www.indiragold.com.ar/', origin: 'https://www.indiragold.com.ar' },
    URL, URLSearchParams, FormData, Headers,
  });
  return { document, window, llamadas, eventos };
}

test('CSRF actualiza cuerpo y header con la cookie vigente después de un login', async () => {
  const { document, window, llamadas } = navegadorCsrf();
  for (const body of [new FormData(), new URLSearchParams()]) {
    document.cookie = 'csrftoken=rotado';
    body.set('csrfmiddlewaretoken', 'antiguo');
    await window.fetch('/carritos/agregar/', { method: 'POST', body });
    const options = llamadas.at(-1).options;
    assert.equal(options.body.get('csrfmiddlewaretoken'), 'rotado');
    assert.equal(options.headers.get('X-CSRFToken'), 'rotado');
    assert.equal(options.credentials, 'same-origin');
  }
  assert.equal(llamadas.length, 2); // Un 403 no reenvía el POST.
});

test('CSRF actualiza formulario y cuerpo URL encoded sin enviar token a otros orígenes', async () => {
  const { window, llamadas, eventos } = navegadorCsrf();
  const input = { value: 'antiguo' };
  eventos.submit({ target: { action: '/users/login/', querySelectorAll: () => [input] } });
  assert.equal(input.value, 'actual');
  await window.fetch('/users/confirmar-direccion/', {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'calle=Prueba&csrfmiddlewaretoken=antiguo',
  });
  assert.equal(new URLSearchParams(llamadas[0].options.body).get('csrfmiddlewaretoken'), 'actual');
  const opciones = { method: 'POST', body: 'dato=1' };
  await window.fetch('https://otro.example/', opciones);
  assert.equal(llamadas[1].options, opciones);
  assert.equal(llamadas[1].options.headers, undefined);
});
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
