/**
 * Lector de dimensiones de imagen sin dependencias externas.
 * Soporta PNG y JPEG (los formatos aceptados por pptxgenjs).
 */
import fs from 'fs';

/**
 * Devuelve { width, height } leyendo los headers del archivo.
 * @param {string} filePath
 * @returns {{width:number,height:number}|null}
 */
export function getImageSize(filePath) {
  let buf;
  try {
    buf = fs.readFileSync(filePath);
  } catch {
    return null;
  }
  if (!buf || buf.length < 24) return null;

  // PNG: firma 8 bytes + IHDR (largo 4 + tipo 4) -> ancho en 16, alto en 20 (BE)
  if (buf.toString('ascii', 1, 4) === 'PNG') {
    return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
  }

  // JPEG: recorrer marcadores hasta SOF0-2 (0xC0/0xC1/0xC2)
  if (buf[0] === 0xff && buf[1] === 0xd8) {
    let off = 2;
    while (off + 9 < buf.length) {
      if (buf[off] !== 0xff) { off += 1; continue; }
      const marker = buf[off + 1];
      const isSOF = marker >= 0xc0 && marker <= 0xcf
        && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc;
      if (isSOF) {
        return {
          height: buf.readUInt16BE(off + 5),
          width: buf.readUInt16BE(off + 7),
        };
      }
      off += 2 + buf.readUInt16BE(off + 2);
    }
  }
  return null;
}

/**
 * Calcula encaje proporcional (contain) de la imagen en el marco.
 * @returns {{dw:number,dh:number}}
 */
export function containFit(width, height, frameW, frameH) {
  if (!width || !height) return { dw: frameW, dh: frameH };
  const ir = width / height;
  const fr = frameW / frameH;
  if (ir > fr) return { dw: frameW, dh: frameW / ir };
  return { dw: frameH * ir, dh: frameH };
}
