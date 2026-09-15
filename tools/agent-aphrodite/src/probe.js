(async () => {
  await document.fonts.ready;
  await Promise.all(Array.from(document.images).map(i=>i.decode().catch(()=>{})));
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  const canvas=document.createElement('canvas');canvas.width=canvas.height=32;
  const ctx=canvas.getContext('2d',{willReadFrequently:true});
  const typeCanvas=document.createElement('canvas');typeCanvas.width=512;typeCanvas.height=64;
  const typeContext=typeCanvas.getContext('2d',{willReadFrequently:true});
  const typeShape=style=>{
    typeContext.clearRect(0,0,512,64);typeContext.font=`${style.fontWeight} 32px ${style.fontFamily}`;typeContext.fillStyle='#000';
    const sample='Hamburgefontsiv 012345',m=typeContext.measureText(sample);typeContext.fillText(sample,2,44);
    const data=typeContext.getImageData(0,0,512,64).data;let alpha=0;for(let i=3;i<data.length;i+=4)alpha+=data[i]/255;
    return {fingerprint:[m.width/32,m.actualBoundingBoxAscent/32,m.actualBoundingBoxDescent/32],inkDensity:alpha/Math.max(1,m.width*(m.actualBoundingBoxAscent+m.actualBoundingBoxDescent)),method:'fixed glyph sample at 32px; computed stack plus actual raster shape, not a resolved font-file identity'};
  };
  const color=value=>{ctx.clearRect(0,0,32,32);ctx.fillStyle=value;ctx.fillRect(0,0,1,1);return Array.from(ctx.getImageData(0,0,1,1).data);};
  const box=e=>{const r=e.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height};};
  const visible=e=>{for(let a=e;a;a=a.parentElement){const s=getComputedStyle(a);if(s.display==='none'||s.visibility!=='visible'||Number(s.opacity)===0||a.tagName==='DETAILS'&&!a.open&&a!==e)return false;}const b=box(e);return b.width>0&&b.height>0;};
  const background=e=>{
    let result=[0,0,0,0],unsupported=[];
    for(let a=e;a;a=a.parentElement){const s=getComputedStyle(a);if(s.backgroundImage!=='none')unsupported.push('complex background paint');const c=color(s.backgroundColor),alpha=c[3]/255;
      const old=result[3],newAlpha=old+(1-old)*alpha;
      if(newAlpha>0)result=[0,1,2].map(i=>(result[i]*old+c[i]*(1-old)*alpha)/newAlpha).concat(newAlpha);
      if(newAlpha>=.999)break;
    }
    if(result[3]<1)result=[0,1,2].map(i=>result[i]*result[3]+255*(1-result[3])).concat(1);
    return {rgba:result.slice(0,3).concat(255),unsupported};
  };
  const material=image=>{
    if(!image.complete||!image.naturalWidth)return {status:'missing',reason:'image not decoded'};
    try {
      const rect=image.getBoundingClientRect(),fit=getComputedStyle(image).objectFit;
      let sw=image.naturalWidth,sh=image.naturalHeight;
      if(fit==='cover'){const scale=Math.max(rect.width/sw,rect.height/sh);sw=rect.width/scale;sh=rect.height/scale;}
      const sx=(image.naturalWidth-sw)/2,sy=(image.naturalHeight-sh)/2;
      ctx.clearRect(0,0,32,32);ctx.drawImage(image,sx,sy,sw,sh,0,0,32,32);const pixels=ctx.getImageData(0,0,32,32).data;
      const sum=[0,0,0],squares=[0,0,0],bins=new Map();let count=0,edge=0;
      for(let i=0;i<pixels.length;i+=4){if(pixels[i+3]===0)continue;count++;for(let j=0;j<3;j++){sum[j]+=pixels[i+j];squares[j]+=pixels[i+j]**2;}
        const key=[0,1,2].map(j=>Math.floor(pixels[i+j]/32)).join(',');bins.set(key,(bins.get(key)||0)+1);
        if((i/4)%32>0)edge+=Math.abs(pixels[i]-pixels[i-4])+Math.abs(pixels[i+1]-pixels[i-3])+Math.abs(pixels[i+2]-pixels[i-2]);
      }
      if(!count)return {status:'missing',reason:'material is completely transparent'};
      return {status:'measured',method:'32x32 sample of the visible centered crop, eight sRGB bins per channel',crop:{x:sx,y:sy,width:sw,height:sh,objectFit:fit},mean:sum.map(x=>x/count),variance:squares.map((x,j)=>x/count-(sum[j]/count)**2),edge:edge/(count*3*255),coverage:count/1024,palette:[...bins.entries()].sort((a,b)=>b[1]-a[1]).slice(0,5).map(([key,n])=>({rgb:key.split(',').map(Number).map(x=>x*32+16),share:n/count})),natural:[image.naturalWidth,image.naturalHeight]};
    }catch(error){return {status:'missing',reason:`material pixels unavailable: ${error.name}`};}
  };
  const nodes=[];
  for(const el of document.querySelectorAll('[data-ap-node]')) {
    const id=el.getAttribute('data-ap-node');if(!visible(el)){nodes.push({id,visible:false});continue;}
    const s=getComputedStyle(el),b=box(el),range=document.createRange();range.selectNodeContents(el);
    const fragments=Array.from(range.getClientRects()).map(r=>({x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height})).filter(r=>r.width>0&&r.height>0);
    ctx.font=s.font;const metrics=ctx.measureText(el.textContent||'');
    const bg=background(el),image=el.querySelector('img');
    nodes.push({id,visible:true,box:b,text:image?image.alt:el.textContent,tag:el.tagName.toLowerCase(),font:{family:s.fontFamily,size:parseFloat(s.fontSize),weight:Number(s.fontWeight),lineHeight:parseFloat(s.lineHeight)||parseFloat(s.fontSize)*1.2,letterSpacing:parseFloat(s.letterSpacing)||0,advance:metrics.width,ascent:metrics.actualBoundingBoxAscent,descent:metrics.actualBoundingBoxDescent,...typeShape(s)},fragments,
      color:color(s.color),background:bg.rgba,unsupported:bg.unsupported,radius:parseFloat(s.borderTopLeftRadius)||0,stroke:parseFloat(s.borderTopWidth)||0,
      material:image?material(image):null,href:el.tagName==='A'?el.getAttribute('href'):null,
      clipped:el.scrollWidth>el.clientWidth+2&&['hidden','clip'].includes(s.overflowX)||el.scrollHeight>el.clientHeight+2&&['hidden','clip'].includes(s.overflowY),
      imageFit:image?getComputedStyle(image).objectFit:null});
  }
  const groups=Array.from(document.querySelectorAll('[data-ap-group]')).map(el=>({id:el.getAttribute('data-ap-group'),visible:visible(el),box:box(el),padding:['Top','Right','Bottom','Left'].map(side=>parseFloat(getComputedStyle(el)['padding'+side])||0),open:el.tagName==='DETAILS'?el.open:null}));
  return {schema:1,method:'aphrodite-observation-1',url:location.href,viewport:{width:innerWidth,height:innerHeight},document:{width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight},programDigest:document.querySelector('meta[name=aphrodite-program]')?.content,contextDigest:document.querySelector('meta[name=aphrodite-context]')?.content,fontsStatus:document.fonts.status,userAgent:navigator.userAgent,nodes,groups,
    controls:Array.from(document.querySelectorAll('a,summary')).filter(visible).map(el=>({tag:el.tagName.toLowerCase(),id:el.id||null,box:box(el),href:el.getAttribute('href'),focusable:el.tabIndex>=0})),
    diagnostics:{allImagesLoaded:Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0),unboundCanvas:document.querySelectorAll('canvas').length,mediaQueryReduced:matchMedia('(prefers-reduced-motion: reduce)').matches}};
})()
