const data = JSON.parse(document.querySelector('#quoteData').textContent);
const grid = document.querySelector('#providerGrid');
const search = document.querySelector('#searchInput');
const sort = document.querySelector('#sortSelect');
const plans = document.querySelector('#planSelect');
const freshness = document.querySelector('#freshSelect');
const count = document.querySelector('#resultCount');
const empty = document.querySelector('#emptyState');
let product = 'all';
function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function historical(o) {
  const today = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  return o.historical || (Date.parse(today+'T00:00:00Z') - Date.parse(o.quote_date+'T00:00:00Z')) / 86400000 > 14;
}
function groupKey(o) { return [o.product, o.tier, o.period, o.currency].join(' · '); }
function renderCard(o) {
  const e=escapeHTML;
  const source = new URL(o.source_url);
  if (source.origin !== 'https://daichongbijia.com' || !['/chatgpt/','/claude/'].includes(source.pathname)) throw new Error('Unexpected quote source');
  return `<article class="provider-card"><div class="provider-top"><div class="provider-id"><span class="provider-logo ${o.product==='ChatGPT'?'logo-green':'logo-amber'}">${e(o.merchant[0])}</span><div><h3>${e(o.merchant)}</h3><small>${e(o.product)} · ${e(o.tier)}</small></div></div><span class="badge">${historical(o)?'历史报价':'来源参考价'}</span></div><p class="offer-plan">${e(o.plan)}</p><div class="provider-tags"><span>${e(o.period)}</span><span>${e(o.delivery)}</span></div><p class="provider-desc">来源说明：${e(o.note || '来源未注明更多售后条款，请查看原页面。')}</p><div class="provider-price"><strong>¥${e(o.price)}</strong><small>来源标价 · CNY</small></div><div class="provider-meta"><span>来源报价日 ${e(o.quote_date)}</span></div><div class="provider-actions"><a class="primary-link" href="${e(source.href)}" target="_blank" rel="noopener noreferrer">查看来源与商家入口 ↗</a></div></article>`;
}
function updatePlans() {
  const previous = plans.value;
  const keys = [...new Set(data.offers.filter(o => product === 'all' || o.product === product).map(groupKey))].sort();
  plans.innerHTML = '<option value="all">全部套餐</option>' + keys.map(k => `<option value="${escapeHTML(k)}">${escapeHTML(k)}</option>`).join('');
  plans.value = keys.includes(previous) ? previous : 'all';
}
function render() {
  const keyword=search.value.trim().toLowerCase();
  const list=data.offers.filter(o => (product==='all'||o.product===product) && (plans.value==='all'||groupKey(o)===plans.value) && (freshness.value==='all'||(freshness.value==='historical'?historical(o):!historical(o))) && [o.merchant,o.product,o.plan,o.tier,o.note].join(' ').toLowerCase().includes(keyword));
  const groups=new Map();
  list.forEach(o=>{const k=groupKey(o);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(o);});
  grid.innerHTML=[...groups.keys()].sort().map(k=>{
    const rows=groups.get(k).sort((a,b)=>sort.value==='name'?a.merchant.localeCompare(b.merchant):(Number(historical(a))-Number(historical(b)) || a.price-b.price));
    return `<section class="quote-group"><h3>${escapeHTML(k)}</h3><div class="provider-grid">${rows.map(renderCard).join('')}</div></section>`;
  }).join('');
  count.textContent=`显示 ${list.length} / ${data.offers.length} 条来源报价 · 按同产品、套餐、周期及币种分组；历史报价排在组内末尾`;
  empty.hidden=list.length>0;
  grid.hidden=list.length===0;
}
document.querySelectorAll('.filter').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('.filter').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
  product=button.dataset.filter;updatePlans();render();
}));
search.addEventListener('input',render);
[sort,plans,freshness].forEach(el=>el.addEventListener('change',render));
const age=(Date.now()-Date.parse(data.collected_at))/3600000;
if(age>36){const info=document.querySelector('#syncInfo');info.textContent+=' 更新已超过36小时，请查看来源最新价格。';info.classList.add('stale');}
updatePlans();render();
