const cards = document.querySelectorAll('.agent-card');
const search = document.getElementById('search');
const statusFilter = document.getElementById('statusFilter');
const departmentFilter = document.getElementById('departmentFilter');
function filterCards(){const q=(search.value||'').toLowerCase();const s=statusFilter.value;const d=(departmentFilter.value||'').toLowerCase();cards.forEach(card=>{const okQ=card.dataset.name.includes(q);const okS=s==='all'||card.dataset.status===s;const okD=!d||card.dataset.department.includes(d);card.style.display=okQ&&okS&&okD?'':'none';});}
[search,statusFilter,departmentFilter].forEach(el=>el&&el.addEventListener('input',filterCards));
function refreshThumbs(){document.querySelectorAll('.thumb').forEach(img=>{if(!img.src.includes('img-placeholder')){const base=img.src.split('?')[0];img.src=base+'?t='+Date.now();}})}
setInterval(refreshThumbs,2000);
if(window.EventSource){const source=new EventSource('/api/events');source.addEventListener('agents',event=>{const data=JSON.parse(event.data);document.getElementById('totalCount').textContent=data.agents.length;const online=data.agents.filter(a=>a.online).length;document.getElementById('onlineCount').textContent=online;document.getElementById('offlineCount').textContent=data.agents.length-online;});}
