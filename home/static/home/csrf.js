/* El token rota al iniciar sesión, incluso en otra pestaña. No repetir POSTs. */
(function () {
  'use strict';
  function tokenActual() {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    return match ? decodeURIComponent(match[1]) : '';
  }
  function actualizarFormulario(form) {
    const token = tokenActual();
    if (!token) return;
    form.querySelectorAll('[name="csrfmiddlewaretoken"]').forEach(function (input) {
      input.value = token;
    });
  }
  document.addEventListener('submit', function (event) {
    const form = event.target;
    if (new URL(form.action || location.href, location.href).origin === location.origin) {
      actualizarFormulario(form);
    }
  }, true);
  window.addEventListener('pageshow', function () {
    document.querySelectorAll('form').forEach(actualizarFormulario);
  });
  const originalFetch = window.fetch;
  if (!originalFetch) return;
  window.fetch = function (input, options) {
    const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, location.href);
    const method = ((options && options.method) || (input && input.method) || 'GET').toUpperCase();
    if (url.origin === location.origin && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
      options = Object.assign({}, options);
      const token = tokenActual();
      if (token) {
        options.headers = new Headers(options.headers || (input && input.headers));
        options.headers.set('X-CSRFToken', token);
        // Django prefiere el token del cuerpo al header: actualizar los dos.
        if (options.body instanceof FormData || options.body instanceof URLSearchParams) {
          options.body.set('csrfmiddlewaretoken', token);
        } else if (typeof options.body === 'string' &&
                   (options.headers.get('Content-Type') || '').includes('application/x-www-form-urlencoded')) {
          const body = new URLSearchParams(options.body);
          body.set('csrfmiddlewaretoken', token);
          options.body = body.toString();
        }
      }
      if (!options.credentials) options.credentials = 'same-origin';
    }
    return originalFetch.call(window, input, options);
  };
}());
