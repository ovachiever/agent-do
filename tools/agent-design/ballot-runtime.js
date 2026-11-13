// Static exports are viewable. Saving is available only through the local review host.
window.addEventListener('DOMContentLoaded',function(){
  document.getElementById('fb-submit').addEventListener('click',function(){
    document.getElementById('fb-status').textContent='Open this round with agent-do design ballot to save your review locally.';
  });
});
