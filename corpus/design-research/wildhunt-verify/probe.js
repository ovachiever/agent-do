(async () => {
  await document.fonts.ready;
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1;
  const context = canvas.getContext('2d', {willReadFrequently: true});
  const rgba = value => {
    context.clearRect(0, 0, 1, 1);
    context.fillStyle = value;
    context.fillRect(0, 0, 1, 1);
    return Array.from(context.getImageData(0, 0, 1, 1).data);
  };
  const all = Array.from(document.body.querySelectorAll('*'));
  const ids = new Map(all.map((el, index) => [el, index]));
  const nodes = [];
  for (const el of all) {
    if (el.closest('script,style,noscript,template') || (el.closest('svg') && el.tagName.toLowerCase() !== 'svg')) continue;
    const tag = el.tagName.toLowerCase();
    const visual = ['img', 'svg', 'canvas'].includes(tag);
    const text = (el.textContent || '').trim();
    if (!visual && (!text || el.children.length)) continue;
    const style = getComputedStyle(el), box = el.getBoundingClientRect();
    if (style.display === 'none' || style.visibility !== 'visible' || Number(style.opacity) === 0 || box.width <= 0 || box.height <= 0) continue;
    const ancestor = el.parentElement.closest('section,article,nav,aside,header,footer,form,table') || el.parentElement;
    const heading = el.closest('h1,h2,h3,h4,h5,h6');
    nodes.push({
      tag, text_length: text.length, markup: el.outerHTML,
      x: box.x + scrollX, y: box.y + scrollY, width: box.width, height: box.height,
      font_size: parseFloat(style.fontSize), font_weight: Number(style.fontWeight),
      font_family: style.fontFamily, color: rgba(style.color), background: rgba(style.backgroundColor),
      semantic: ids.has(ancestor) ? ids.get(ancestor) : -1,
      heading: heading ? Number(heading.tagName.substring(1)) : null,
      visual
    });
  }
  return {url: location.href, title: document.title, viewport: [innerWidth, innerHeight],
    document: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
    fonts_status: document.fonts.status,
    fonts: Array.from(document.fonts).map(f => ({family: f.family, status: f.status})),
    images: Array.from(document.images).map(i => ({src: i.getAttribute('src'), complete: i.complete, width: i.naturalWidth})),
    browser: navigator.userAgent, node_count: nodes.length, nodes};
})()
