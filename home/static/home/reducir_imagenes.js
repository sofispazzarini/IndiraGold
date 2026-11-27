/* Achica las fotos en el navegador antes de enviar un formulario con archivos.
   El proxy de PythonAnywhere rechaza con 413 los envíos grandes antes de llegar a Django,
   y las fotos de celular pesan 5–27 MB cada una. El servidor genera después sus copias
   WebP de 480/960/1600 px, así que no se pierde calidad visible. Si algo falla, se envía
   el archivo original sin tocar. */
(function (raiz) {
  'use strict';
  const LADO_MAXIMO = 2560;
  const PESO_MINIMO = 1024 * 1024; // Por debajo de 1 MB no vale la pena recomprimir.
  const CALIDAD = 0.85;
  const TIPOS = ['image/jpeg', 'image/png', 'image/webp'];

  function necesitaReducir(archivo) {
    return TIPOS.includes(archivo.type) && archivo.size > PESO_MINIMO;
  }

  function medidas(ancho, alto, lado) {
    const escala = Math.min(1, lado / Math.max(ancho, alto));
    return { ancho: Math.max(1, Math.round(ancho * escala)), alto: Math.max(1, Math.round(alto * escala)) };
  }

  function nombreCon(nombre, tipo) {
    const ext = { 'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp' }[tipo];
    return nombre.replace(/\.[^.]*$/, '') + ext;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { necesitaReducir, medidas, nombreCon };
  }
  if (!raiz.document || !raiz.DataTransfer || !raiz.HTMLCanvasElement) return;

  async function decodificar(archivo) {
    if (raiz.createImageBitmap) {
      try { return await createImageBitmap(archivo, { imageOrientation: 'from-image' }); } catch (e) { /* sigue */ }
    }
    const url = URL.createObjectURL(archivo);
    try {
      const img = new Image();
      img.src = url;
      await img.decode();
      return img;
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  function aBlob(canvas, tipo) {
    return new Promise(function (ok) { canvas.toBlob(ok, tipo, CALIDAD); });
  }

  function tieneTransparencia(ctx, ancho, alto) {
    const datos = ctx.getImageData(0, 0, ancho, alto).data;
    for (let i = 3; i < datos.length; i += 4) if (datos[i] < 255) return true;
    return false;
  }

  async function reducir(archivo) {
    if (!necesitaReducir(archivo)) return archivo;
    try {
      const imagen = await decodificar(archivo);
      const m = medidas(imagen.width, imagen.height, LADO_MAXIMO);
      const canvas = document.createElement('canvas');
      canvas.width = m.ancho;
      canvas.height = m.alto;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(imagen, 0, 0, m.ancho, m.alto);
      let blob;
      if (archivo.type === 'image/jpeg') {
        blob = await aBlob(canvas, 'image/jpeg');
      } else {
        blob = await aBlob(canvas, 'image/webp'); // Conserva transparencia.
        if (!blob || blob.type !== 'image/webp') { // Safari viejo no codifica WebP.
          blob = await aBlob(canvas, tieneTransparencia(ctx, m.ancho, m.alto) ? 'image/png' : 'image/jpeg');
        }
      }
      if (!blob || blob.size >= archivo.size) return archivo;
      return new File([blob], nombreCon(archivo.name, blob.type), { type: blob.type, lastModified: archivo.lastModified });
    } catch (e) {
      return archivo;
    }
  }

  async function reducirFormulario(form) {
    for (const input of form.querySelectorAll('input[type="file"]')) {
      if (!input.files || !Array.from(input.files).some(necesitaReducir)) continue;
      const dt = new DataTransfer();
      for (const archivo of input.files) dt.items.add(await reducir(archivo));
      input.files = dt.files;
    }
  }

  const listos = new WeakSet();
  // Fase de burbujeo en document: corre después de las validaciones propias de cada formulario.
  document.addEventListener('submit', function (event) {
    const form = event.target;
    if (listos.has(form)) { listos.delete(form); return; } // Segunda pasada: ya reducidas.
    if (event.defaultPrevented) return;
    const hayGrandes = Array.from(form.querySelectorAll('input[type="file"]'))
      .some(function (input) { return input.files && Array.from(input.files).some(necesitaReducir); });
    if (!hayGrandes) return;
    event.preventDefault();
    const boton = event.submitter;
    const textoBoton = boton && boton.innerHTML;
    if (boton) { boton.disabled = true; boton.innerHTML = 'Preparando fotos…'; }
    reducirFormulario(form).finally(function () {
      listos.add(form);
      if (boton) { boton.disabled = false; boton.innerHTML = textoBoton; }
      if (form.requestSubmit) form.requestSubmit(boton || undefined); else form.submit();
    });
  });
}(typeof window !== 'undefined' ? window : globalThis));
