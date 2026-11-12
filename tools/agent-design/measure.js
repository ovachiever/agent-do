/* Decode the original image and sample every pixel in each named region. */
async function measureImage(regions) {
  const image=document.querySelector('img');await image.decode();
  const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
  const context=canvas.getContext('2d',{willReadFrequently:true,colorSpace:'srgb'});
  context.drawImage(image,0,0);
  const pixels=context.getImageData(0,0,canvas.width,canvas.height);
  const samples=regions.map(region=>{
    const counts=new Map();
    for(let y=region.y;y<region.y+region.height;y++) for(let x=region.x;x<region.x+region.width;x++) {
      const offset=(y*canvas.width+x)*4;
      const rgba=[...pixels.data.slice(offset,offset+4)];const key=rgba.join(',');
      counts.set(key,(counts.get(key)||0)+1);
    }
    let maximum=0;
    for (const count of counts.values()) maximum=Math.max(maximum,count);
    const modes=[...counts].filter(([,count])=>count===maximum).sort((a,b)=>a[0].localeCompare(b[0]));
    return {...region,pixels:region.width*region.height,
      distinct_colors:counts.size,
      colors:modes.map(([rgba,count])=>({rgba:rgba.split(',').map(Number),pixels:count,area_fraction:count/(region.width*region.height)})),
      method:'all equally most frequent exact RGBA colors over every pixel in the declared rectangle, decoded through Canvas sRGB'};
  });
  return {width:canvas.width,height:canvas.height,color_space:pixels.colorSpace || 'srgb',samples};
}
