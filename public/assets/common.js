(() => {
  const site = document.body.dataset.site;
  const $ = (q, root = document) => root.querySelector(q);
  const $$ = (q, root = document) => [...root.querySelectorAll(q)];
  const esc = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = n => new Intl.NumberFormat('ru-RU').format(n) + ' ₽';
  const api = new URL('./api/submit', location.href);
  const request = async data => {
    const r = await fetch(api, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const value = await r.json();
    if (!r.ok || !value.ok) throw new Error(value.error || 'Не удалось отправить форму');
    return value;
  };
  $$('[data-menu-toggle]').forEach(button => button.addEventListener('click', () => {
    const nav = document.getElementById(button.getAttribute('aria-controls'));
    const open = nav.classList.toggle('is-open');
    button.setAttribute('aria-expanded', String(open));
  }));
  $$('[data-open]').forEach(button => button.addEventListener('click', () => {
    const target = document.getElementById(button.dataset.open);
    if (target && !target.open) target.showModal();
  }));
  $$('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
  $$('dialog').forEach(d => d.addEventListener('click', e => { if (e.target === d) d.close(); }));
  $$('input[type=date]').forEach(input => {
    const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    input.min = d.toISOString().slice(0,10);
  });
  $$('[data-request]').forEach(form => form.addEventListener('submit', async e => {
    e.preventDefault();
    const status = $('[data-status]', form), button = $('button[type=submit]', form);
    const fields = Object.fromEntries(new FormData(form).entries());
    button.disabled = true; status.textContent = 'Сохраняем…';
    try {
      const result = await request({site, kind:'request', ...fields});
      form.reset();
      status.textContent = `Готово! Демо-заявка № ${result.reference} сохранена. Реальная запись не создана.`;
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  }));
  const shop = $('[data-shop]');
  if (shop) initShop();
  async function initShop() {
    let products;
    try {
      const response = await fetch(new URL('./assets/products.json', location.href));
      if (!response.ok) throw Error();
      products = (await response.json())[site];
      if (!Array.isArray(products)) throw Error();
    } catch { $('[data-product-grid]').textContent = 'Каталог не загрузился. Обновите страницу.'; return; }
    const grid = $('[data-product-grid]'), cartList = $('[data-cart-list]'), storage = 'portfolio-cart-' + site;
    let cart;
    try { cart = JSON.parse(localStorage.getItem(storage) || '{}'); } catch { cart = {}; }
    if (!cart || typeof cart !== 'object' || Array.isArray(cart)) cart = {};
    Object.keys(cart).forEach(id => { if (!products.some(p => p.id === id) || !Number.isInteger(cart[id]) || cart[id] < 1 || cart[id] > 20) delete cart[id]; });
    let category = 'Все';
    const imageClass = site === 'forma' ? 'furniture-sheet' : 'coffee-sheet';
    function save(){ try { localStorage.setItem(storage, JSON.stringify(cart)); } catch {} renderCart(); }
    function image(p){ return `<div class="product-image ${imageClass}" style="background-position:${esc(p.position)}" aria-hidden="true"></div>`; }
    function renderProducts(){
      const term = ($('[data-search]')?.value || '').toLowerCase().trim();
      const visible = products.filter(p => (category === 'Все' || p.category === category) && (p.name+' '+p.note).toLowerCase().includes(term));
      grid.innerHTML = visible.length ? visible.map(p => `<article class="product-card"><button class="product-picture" type="button" data-details="${esc(p.id)}" aria-label="Подробнее: ${esc(p.name)}">${image(p)}<span class="product-plus">↗</span></button><div class="product-meta"><div><h3>${esc(p.name)}</h3><p>${esc(p.note)}</p></div><strong>${money(p.price)}</strong></div><button class="product-add" type="button" data-add="${esc(p.id)}">В корзину <span>+</span></button></article>`).join('') : '<p class="empty">Ничего не нашлось. Попробуйте другой запрос.</p>';
    }
    function renderCart(){
      const entries = products.filter(p => cart[p.id]);
      const count = entries.reduce((n,p) => n + cart[p.id], 0), total = entries.reduce((n,p) => n + p.price * cart[p.id], 0);
      $$('[data-cart-count]').forEach(el => el.textContent = count);
      cartList.innerHTML = entries.length ? entries.map(p => `<div class="cart-item"><div>${image(p)}</div><div><b>${esc(p.name)}</b><p>${money(p.price)}</p><div class="quantity"><button type="button" data-dec="${esc(p.id)}" aria-label="Уменьшить количество">−</button><span>${cart[p.id]}</span><button type="button" data-inc="${esc(p.id)}" aria-label="Увеличить количество">+</button></div></div><button class="text-button" type="button" data-remove="${esc(p.id)}" aria-label="Удалить">×</button></div>`).join('') : '<p class="empty">Корзина пока пуста. Выберите что-нибудь в каталоге.</p>';
      $('[data-total]').textContent = money(total);
      $('[data-checkout]').disabled = !entries.length;
    }
    $$('[data-filter]').forEach(b => b.addEventListener('click', () => {category = b.dataset.filter; $$('[data-filter]').forEach(x => x.classList.toggle('active', x === b)); renderProducts();}));
    $('[data-search]')?.addEventListener('input', renderProducts);
    document.addEventListener('click', e => {
      let b = e.target.closest('[data-add],[data-details],[data-inc],[data-dec],[data-remove]'); if(!b) return;
      let id = b.dataset.add || b.dataset.details || b.dataset.inc || b.dataset.dec || b.dataset.remove;
      const p = products.find(x => x.id === id); if (!p) return;
      if (b.dataset.details) {
        const d = $('#product-dialog');
        $('[data-detail-content]', d).innerHTML = `${image(p)}<div><p class="eyebrow">${esc(p.category)} / КОЛЛЕКЦИЯ</p><h2>${esc(p.name)}</h2><p>${esc(p.note)}. Предмет из демонстрационного каталога, созданного для знакомства с возможностями магазина.</p><p class="detail-price">${money(p.price)}</p><button class="button" type="button" data-add="${esc(p.id)}">Добавить в корзину <span>↗</span></button></div>`;
        d.showModal();
      } else if (b.dataset.add || b.dataset.inc) { cart[id] = Math.min(20, (cart[id] || 0) + 1); save(); b.textContent = 'Добавлено ✓'; setTimeout(() => renderProducts(), 900); }
      else if (b.dataset.dec) {cart[id]--; if (!cart[id]) delete cart[id]; save();}
      else if (b.dataset.remove) {delete cart[id]; save();}
    });
    $('[data-order-form]').addEventListener('submit', async e => {
      e.preventDefault(); const form=e.currentTarget, status=$('[data-status]',form), button=$('[data-checkout]');
      button.disabled=true; status.textContent='Оформляем демо-заказ…';
      try {
        const result = await request({site,kind:'order',delivery:new FormData(form).get('delivery'),items:Object.entries(cart).map(([id,quantity])=>({id,quantity}))});
        cart={}; save(); status.textContent=`Демо-заказ № ${result.reference} создан на ${money(result.total)}. Оплата и доставка не выполняются.`;
      } catch(err) {status.textContent=err.message; button.disabled=false;}
    });
    renderProducts(); renderCart();
  }
  $$('[data-billing]').forEach(button => button.addEventListener('click', () => {
    $$('[data-billing]').forEach(b => b.classList.toggle('active', b === button));
    $$('[data-monthly]').forEach(price => price.textContent = button.dataset.billing === 'year' ? price.dataset.yearly : price.dataset.monthly);
    const label=$('[data-billing-label]'); if(label) label.textContent=button.dataset.billing === 'year' ? 'за месяц при оплате за год' : 'за месяц';
  }));
})();
