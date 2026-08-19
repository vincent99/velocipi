// Combines multiple standalone SVG documents (as serialized strings, e.g.
// from AirplaneDiagram/CGChart's exposed svgString() methods) into one
// wrapper SVG for the weight & balance save snapshot: stacked vertically
// with a title/timestamp header. Used by the calculator page to bundle its
// diagram + chart into the single file POST /wb/save writes to disk.
const SVG_NS = 'http://www.w3.org/2000/svg';

function svgSize(svgEl: Element): { width: number; height: number } {
  const viewBox = svgEl.getAttribute('viewBox');
  if (viewBox) {
    const parts = viewBox.split(/\s+/).map(Number);
    const width = parts[2];
    const height = parts[3];
    if (width && height && width > 0 && height > 0) {
      return { width, height };
    }
  }
  const w = parseFloat(svgEl.getAttribute('width') ?? '');
  const h = parseFloat(svgEl.getAttribute('height') ?? '');
  return { width: w || 400, height: h || 300 };
}

export function combineSvgSnapshot(
  svgStrings: string[],
  title: string
): string {
  const parser = new DOMParser();
  const wrapper = document.createElementNS(SVG_NS, 'svg');

  const padding = 16;
  const titleHeight = 30;
  let y = padding + titleHeight;
  let maxWidth = 0;

  for (const raw of svgStrings) {
    if (!raw) {
      continue;
    }
    const doc = parser.parseFromString(raw, 'image/svg+xml');
    const src = doc.documentElement;
    if (src.tagName.toLowerCase() !== 'svg') {
      continue; // malformed input; skip rather than fail the whole snapshot
    }
    const { width, height } = svgSize(src);
    const g = document.createElementNS(SVG_NS, 'g');
    g.setAttribute('transform', `translate(${padding},${y})`);
    while (src.firstChild) {
      g.appendChild(src.firstChild);
    }
    wrapper.appendChild(g);
    y += height + padding;
    maxWidth = Math.max(maxWidth, width + padding * 2);
  }

  const titleEl = document.createElementNS(SVG_NS, 'text');
  titleEl.setAttribute('x', String(padding));
  titleEl.setAttribute('y', String(padding + 16));
  titleEl.setAttribute('font-size', '16');
  titleEl.setAttribute('font-family', 'sans-serif');
  titleEl.setAttribute('fill', '#e0e0e0');
  titleEl.textContent = `${title} — ${new Date().toLocaleString()}`;
  wrapper.insertBefore(titleEl, wrapper.firstChild);

  const bg = document.createElementNS(SVG_NS, 'rect');
  bg.setAttribute('width', String(maxWidth));
  bg.setAttribute('height', String(y));
  bg.setAttribute('fill', '#111111');
  wrapper.insertBefore(bg, wrapper.firstChild);

  wrapper.setAttribute('xmlns', SVG_NS);
  wrapper.setAttribute('viewBox', `0 0 ${maxWidth} ${y}`);
  wrapper.setAttribute('width', String(maxWidth));
  wrapper.setAttribute('height', String(y));

  return new XMLSerializer().serializeToString(wrapper);
}
