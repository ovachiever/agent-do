(function(){
  var template=null;
  function state(){return JSON.parse(document.getElementById('fb-state').textContent);}
  function status(message){document.getElementById('fb-status').textContent=message;}
  function render(){
    var value=state();
    Object.keys(value.feedback || {}).forEach(function(key){
      var field=document.querySelector('textarea[data-fb="'+key+'"]');
      if(field) field.value=value.feedback[key];
      var saved=document.querySelector('[data-fb-saved="'+key+'"]');
      if(saved){saved.textContent='Saved'+(value.submitted_at?' · '+value.submitted_at:'');saved.hidden=false;}
    });
    if(value.submitted_at) status('Last submitted '+value.submitted_at);
  }
  window.addEventListener('DOMContentLoaded',function(){
    template='<!doctype html>\n'+document.documentElement.outerHTML;
    render();document.getElementById('fb-submit').addEventListener('click',submit);
  });
  async function submit(){
    var feedback={},button=document.getElementById('fb-submit');
    document.querySelectorAll('textarea[data-fb]').forEach(function(field){
      if(field.value.trim()) feedback[field.dataset.fb]=field.value; // Preserve original whitespace and typos.
    });
    if(!Object.keys(feedback).length){status('Write a note before submitting.');return;}
    try{
      if(typeof claude==='undefined') throw new Error('Claude Artifact capability unavailable');
      var api=await claude.use('artifact');
      if(!api) throw new Error('Claude Artifact capability unavailable');
      var payload=JSON.stringify({feedback:feedback,submitted_at:new Date().toISOString()}).replace(/</g,'\\u003c');
      var doc=template.replace(/<script type="application\/json" id="fb-state">[\s\S]*?<\/script>/,
          '<script type="application/json" id="fb-state">'+payload+'<\/script>');
      button.disabled=true;status('Saving…');await api.publish(doc);status('Saved.');
    }catch(error){button.disabled=false;status(error.code==='conflict'?'A newer version exists. Reload before submitting.':'Could not save: '+error.message);}
  }
})();
