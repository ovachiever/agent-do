(function(){
  window.addEventListener('DOMContentLoaded',function(){
    var config=window.designLocal, saved=config.saved, status=document.getElementById('fb-status');
    var button=document.getElementById('fb-submit');button.textContent='Save review';
    var controls=document.createElement('fieldset');
    var legend=document.createElement('legend');legend.textContent='Your selection for this part';controls.appendChild(legend);
    config.labels.forEach(function(label){
      var row=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.dataset.choice=label;
      row.appendChild(box);row.appendChild(document.createTextNode(' Select candidate '+label));controls.appendChild(row);
    });
    var confirm=document.createElement('input');confirm.type='checkbox';confirm.id='confirm-selection';
    var row=document.createElement('label');row.appendChild(confirm);row.appendChild(document.createTextNode(' Confirm these choices (none checked means reject all in this part)'));controls.appendChild(row);
    button.parentNode.insertBefore(controls,button);
    if(saved){
      document.querySelectorAll('textarea[data-fb]').forEach(function(field){field.value=saved.feedback[field.dataset.fb]||'';});
      document.querySelectorAll('[data-choice]').forEach(function(box){box.checked=saved.selected_labels.includes(box.dataset.choice);});
      confirm.checked=saved.complete;status.textContent='Saved '+saved.submitted_at;
    }
    button.addEventListener('click',async function(){
      var feedback={},selected=[];
      document.querySelectorAll('textarea[data-fb]').forEach(function(field){if(field.value.trim())feedback[field.dataset.fb]=field.value;});
      document.querySelectorAll('[data-choice]:checked').forEach(function(box){selected.push(box.dataset.choice);});
      if(selected.length&&!confirm.checked){status.textContent='Confirm your choices, or uncheck them to save notes only.';return;}
      button.disabled=true;status.textContent='Saving…';
      try{
        var response=await fetch(config.endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({feedback:feedback,selected_labels:selected,complete:confirm.checked})});
        var result=await response.json();if(!response.ok)throw new Error(result.error);
        status.textContent='Saved. '+result.result.status;
      }catch(error){status.textContent='Could not save: '+error.message;}
      finally{button.disabled=false;}
    });
  });
})();
