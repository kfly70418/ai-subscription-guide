// Real destinations only. Third-party offers require a source and verified terms.
const providers = [
  { name: 'ChatGPT 官方入口', product: 'ChatGPT', type: '官方', logo: 'G', tone: 'logo-green', description: '查看 ChatGPT 产品与订阅选项，购买前确认账号内显示的套餐和价格。', url: 'https://chatgpt.com/' },
  { name: 'Claude 官方入口', product: 'Claude', type: '官方', logo: '✦', tone: 'logo-amber', description: '查看 Claude 产品与订阅选项，购买前确认账号内显示的套餐和价格。', url: 'https://claude.ai/' }
];
const grid = document.querySelector('#providerGrid');
const searchInput = document.querySelector('#searchInput');
const sortSelect = document.querySelector('#sortSelect');
const count = document.querySelector('#resultCount');
const empty = document.querySelector('#emptyState');
let currentFilter = 'all';
function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function cardTemplate(item) {
  const url = new URL(item.url);
  if (url.protocol !== 'https:') throw new Error('Only HTTPS destinations are supported');
  return `<article class="provider-card"><div class="provider-top"><div class="provider-id"><span class="provider-logo ${escapeHTML(item.tone)}">${escapeHTML(item.logo)}</span><div><h3>${escapeHTML(item.name)}</h3><small>${escapeHTML(item.product)}</small></div></div><span class="badge">官方入口</span></div><p class="provider-desc">${escapeHTML(item.description)}</p><div class="provider-tags"><span>官方订阅</span><span>非第三方代充</span></div><div class="provider-price"><strong style="font-size:18px">以官方页面为准</strong></div><div class="provider-meta"><span>未采集报价</span><span>不参与代充排名</span></div><div class="provider-actions"><a class="primary-link" href="${escapeHTML(url.href)}" target="_blank" rel="noopener noreferrer">访问官网 ↗</a><a class="secondary-link" href="#how">订阅前须知</a></div></article>`;
}
function render() {
  const keyword = searchInput.value.trim().toLowerCase();
  const list = providers.filter(item => (currentFilter === 'all' || item.product === currentFilter || item.type === currentFilter) && `${item.name} ${item.description}`.toLowerCase().includes(keyword));
  if (sortSelect.value === 'name') list.sort((a,b) => a.name.localeCompare(b.name));
  grid.innerHTML = list.map(cardTemplate).join('');
  count.textContent = `显示 ${list.length} 个入口 · 暂无已核验的第三方代充报价`;
  empty.hidden = list.length > 0;
  grid.hidden = list.length === 0;
}
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.filter').forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', String(b === button)); });
  currentFilter = button.dataset.filter;
  render();
}));
searchInput.addEventListener('input', render);
sortSelect.addEventListener('change', render);
render();
