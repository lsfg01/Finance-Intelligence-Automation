const byId = id => document.getElementById(id);
const portfolioSelect = byId('portfolio-select');
const analysisButton = byId('run');
const importButton = byId('open-import');
const priceButton = byId('refresh-prices');
const importedViewButton = byId('show-imported');
const importDialog = byId('import-dialog');
const importForm = byId('import-holdings');
const accountInput = byId('investing-account');
const fileInput = byId('investing-file');
const previewButton = byId('preview-investing');
const confirmButton = byId('confirm-investing');
const cancelButton = byId('cancel-import');
const reportSelect = byId('report-select');

let active = null;
let pendingImport = null;
let portfolioBusy = false;
let analysisBusy = false;
let confirming = false;
let previewRequest = 0;

const percent = value => value == null ? '—' : `${fmt(value)} %`;
const quantity = value => value == null ? '—' : String(value).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '').replace('.', ',');
const amount = (value, currency) => value == null ? '—' : `${fmt(value)} ${esc(currency)}`;
const money = value => value ? amount(value.amount, value.currency) : '—';
const withSign = (value, formatted) => Number(value) > 0 ? `+${formatted}` : formatted;
function profit(value) {
 if (!value) return '—';
 const details = [];
 if (value.money) details.push(withSign(value.money.amount, money(value.money)));
 if (value.percentage != null) details.push(withSign(value.percentage, percent(value.percentage)));
 return details.join(' · ') || '—';
}
function metrics(totals, calculated) {
 const items = [];
 if (calculated !== undefined) items.push(['Valor calculado en moneda base', calculated]);
 if (totals) items.push(
  ['Valor declarado por Investing.com', money(totals.market_value)],
  ['B/P abierto', profit(totals.open_pnl)],
  ['B/P diario', profit(totals.daily_pnl)],
  ['B/P total (Investing.com)', profit(totals.total_pnl)]
 );
 return items.length ? `<dl class="metrics">${items.map(([label, value])=>`<div><dt>${label}</dt><dd>${value}</dd></div>`).join('')}</dl>` : '';
}
function updateControls() {
 analysisButton.hidden = !active?.valuation;
 analysisButton.disabled = analysisBusy || portfolioBusy || !active?.valuation;
 priceButton.hidden = !active;
 priceButton.disabled = portfolioBusy;
 importButton.classList.toggle('secondary', Boolean(active));
 importButton.textContent = active ? 'Importar…' : 'Importar cartera';
 importButton.disabled = portfolioBusy;
 portfolioSelect.disabled = portfolioBusy;
 importedViewButton.hidden = !active?.imported || active.valuation_mode === 'imported';
 importedViewButton.disabled = portfolioBusy;
}
const identity = row => JSON.stringify([row.instrument_id,row.listing_id]);
const coverage = {COMPLETE:'Completa', PARTIAL:'Parcial', MISSING:'Sin importes calculados en moneda base'};
const issues = {
 MISSING_FX:'FX no disponible', AMBIGUOUS_FX:'FX ambiguo', MISSING_PRICE:'Precio no disponible',
 STALE_PRICE:'Precio desactualizado', UNKNOWN_INSTRUMENT:'Instrumento desconocido',
 MISSING_LISTING:'Plaza no disponible', AMBIGUOUS_LISTING:'Plaza ambigua',
 INVALID_LISTING:'Plaza inválida', UNSUPPORTED_ASSET:'Activo sin método de valoración',
 PRICE_CURRENCY_MISMATCH:'La moneda del precio no coincide', AMBIGUOUS_PRICE:'Precio ambiguo'
};

function lotsDetail(row) {
 if (!row) return '';
 if (row.lots === null) return '<div class="small muted">Lotes no disponibles</div>';
 const lots = row.lots.map(lot=>`<li>${esc(quantity(lot.quantity))} · ${esc(lot.opened_on ?? 'Fecha no disponible')} · ${money(lot.entry_price)}</li>`).join('');
 return `<details><summary>${row.lots.length} ${row.lots.length === 1 ? 'lote' : 'lotes'}</summary><ul>${lots}</ul></details>`;
}

function renderValuation(data) {
 active = data;
 const table = byId('valuation');
 const summary = byId('valuation-metrics');
 table.replaceChildren();
 summary.replaceChildren();
 table.hidden = !data;
 byId('valuation-title').textContent = 'Cartera';
 byId('versions').textContent = '';
 if (!data) {
  byId('valuation-status').textContent = 'Importa un CSV de Investing.com Holdings para empezar.';
  updateControls();
  return;
 }
 const {portfolio, valuation, valuation_mode: mode, imported, source, instruments, listings} = data;
 const importedView = mode === 'imported';
 const reference = source?.reference_date ?? 'no disponible';
 const origin = source?.reference_origin === 'filename' ? ' (nombre del archivo)' : '';
 byId('valuation-title').textContent = portfolioSelect.selectedOptions[0]?.textContent ?? 'Cartera';
 byId('versions').textContent = `Versión ${portfolio.version} · Moneda base ${portfolio.base_currency}` +
  (source ? ` · ${source.provider === 'investing.com' ? 'CSV de Investing.com' : 'Alpaca Paper'} · Referencia ${reference}${origin} · Carga ${new Date(source.loaded_at).toLocaleString('es-ES')}` : '');
 const quoteCount = (valuation?.positions ?? []).filter(row=>row.quote_value !== null).length;
 const baseState = importedView && quoteCount && valuation.valued_positions < valuation.total_positions
  ? 'Cobertura parcial en moneda base' : coverage[valuation?.status];
 const baseCoverage = valuation && `${baseState} · ${valuation.valued_positions} de ${valuation.total_positions} posiciones con valor en ${valuation.base_currency}`;
 byId('valuation-status').textContent = importedView
  ? `Valoración importada · ${quoteCount} de ${valuation.total_positions} posiciones con valor en su moneda · ${baseCoverage}`
  : valuation ? `Precios ${mode === 'live' ? 'de mercado' : 'simulados'} · Fecha de valoración ${valuation.as_of} · ${baseCoverage}`
  : 'Precios pendientes. Aún no hay una valoración guardada.';
 const totals = imported?.export.totals;
 const calculated = valuation?.total_value == null
  ? (valuation?.valued_positions ? `Indeterminado · conocido ${amount(valuation.known_value,portfolio.base_currency)}` : 'Indeterminado')
  : amount(valuation.total_value,portfolio.base_currency);
 summary.innerHTML = metrics(totals, valuation ? calculated : undefined)
  + (imported ? `<p class="small muted">Datos declarados y B/P del CSV · Referencia ${esc(reference)}${origin}. El archivo acredita las posiciones vigentes y deja sin acreditar el historial de resultados realizados.</p>` : '');
 const importedRows = new Map((imported?.export.rows ?? []).map(row=>[identity(row),row]));
 const instrumentById = new Map(instruments.map(item=>[item.instrument_id,item]));
 const listingById = new Map(listings.map(item=>[item.listing_id,item]));
 const prices = new Map((valuation?.price_observations ?? []).map(item=>[item.observation_id,item]));
 const rates = new Map((valuation?.fx_observations ?? []).map(item=>[item.observation_id,item]));
 const values = new Map((valuation?.positions ?? []).map(row=>[row.position.position_id,row]));
 const body = portfolio.positions.map(position=>{
  const row = values.get(position.position_id);
  const original = importedRows.get(identity(position));
  const economics = original?.economics;
  const instrument = instrumentById.get(position.instrument_id);
  const listing = listingById.get(position.listing_id);
  const price = prices.get(row?.price_observation_id);
  const fx = rates.get(row?.fx_observation_id);
  const computed = importedView && !economics?.market_value && row?.quote_value != null;
  const name = original?.name || instrument?.name || position.instrument_id.split(':').at(-1);
  const shownValue = importedView && economics?.market_value
   ? money(economics.market_value) : amount(row?.quote_value,row?.quote_currency);
  const sourceDetails = importedView
   ? economics?.quote_time ? `<div class="small muted">Hora en el CSV · ${esc(economics.quote_time)}</div>` : ''
   : price ? `<div class="small muted">${esc(price.provider)} · ${esc(price.price_as_of)}</div>` : '';
  return `<tr><td><strong>${esc(name)}</strong><div class="small muted">${esc(original?.label ?? listing?.ticker)} · ${esc(listing?.mic)}</div>${lotsDetail(original)}</td>
   <td>${esc(quantity(position.quantity))}</td>
   <td>${money(economics?.average_price)}</td>
   <td>${importedView ? money(economics?.current_price) : amount(price?.value,price?.currency)}${sourceDetails}</td>
   <td>${shownValue}${computed ? '<div class="small muted">Calculado</div>' : ''}
   ${importedView && original?.warnings.length ? `<div class="small muted">${esc(original.warnings.join(' · '))}</div>` : ''}</td>
   <td>${amount(row?.base_value,portfolio.base_currency)}${fx ? `<div class="small muted">${esc(fx.provider)} · ${esc(fx.as_of)}</div>` : ''}
   ${row?.issue ? `<div class="small muted">${esc(issues[row.issue] ?? row.issue)}</div>` : ''}</td>
   <td>${percent(economics?.weight_pct)}</td>
   <td>${profit(economics?.net_pnl)}</td></tr>`;
 }).join('');
 table.innerHTML = `<table><thead><tr><th>Instrumento</th><th>Cantidad</th><th>Precio medio</th><th>Precio actual</th>
  <th>Valor de posición</th><th>Valor en ${esc(portfolio.base_currency)}</th><th>Peso declarado</th><th>B/P neto</th>
  </tr></thead><tbody>${body || '<tr><td colspan="8">Sin posiciones abiertas</td></tr>'}</tbody></table>`;
 updateControls();
}

async function selectPortfolio(view) {
 const id = portfolioSelect.value;
 sessionStorage.setItem('active-portfolio', id);
 const query = new URLSearchParams({portfolio_id:id});
 if (view) query.set('view',view);
 renderValuation(id ? await api('/api/portfolio/valuation?' + query) : null);
}

async function loadPortfolios(selected = sessionStorage.getItem('active-portfolio')) {
 const choices = await api('/api/portfolio/holdings');
 portfolioSelect.replaceChildren(new Option('Ninguna cartera',''), ...choices.map(row=>new Option(row.name,row.portfolio_id)));
 portfolioSelect.value = selected !== null && [...portfolioSelect.options].some(option=>option.value === selected)
  ? selected : choices.find(row=>row.portfolio_id.startsWith('investing:'))?.portfolio_id ?? '';
 await selectPortfolio();
}

async function portfolioOperation(action, statusId) {
 portfolioBusy = true;
 updateControls();
 const message = byId(statusId);
 message.hidden = false;
 try { await action(); }
 catch (error) { message.textContent = error.message; }
 finally { portfolioBusy = false; updateControls(); }
}

portfolioSelect.addEventListener('change',()=>portfolioOperation(async()=>{
 byId('refresh-status').hidden = true;
 renderValuation(null);
 await selectPortfolio();
},'valuation-status'));
priceButton.addEventListener('click',()=>portfolioOperation(async()=>{
 byId('refresh-status').textContent = 'Actualizando precios…';
 const query = new URLSearchParams({portfolio_id:portfolioSelect.value, mode:'live'});
 renderValuation(await api('/api/portfolio/refresh-prices?' + query,{method:'POST'}));
 byId('refresh-status').textContent = 'Valoración de mercado guardada.';
},'refresh-status'));
importedViewButton.addEventListener('click',()=>portfolioOperation(async()=>{
 await selectPortfolio('imported');
 byId('refresh-status').hidden = true;
},'refresh-status'));

function clearPreview() {
 previewRequest++;
 pendingImport = null;
 confirmButton.hidden = true;
 byId('investing-preview').replaceChildren();
 byId('preview-metrics').replaceChildren();
 byId('investing-status').textContent = '';
}
function setSource(file) {
 clearPreview();
 importForm.hidden = !file;
 byId('connect-account').hidden = file;
}
document.querySelectorAll('input[name="import-source"]').forEach(input=>{
 input.addEventListener('change',()=>setSource(input.id !== 'account-source'));
});
importButton.addEventListener('click',()=>{
 importForm.reset();
 accountInput.value = active?.source?.provider === 'investing.com'
  ? active.portfolio.accounts[0].name.replace(/^Investing\.com · /,'') : '';
 const fileSource = document.querySelector('input[name="import-source"]');
 fileSource.checked = true;
 setSource(true);
 importDialog.showModal();
 fileSource.focus();
});
cancelButton.addEventListener('click',()=>importDialog.close());
importDialog.addEventListener('cancel',event=>{ if (confirming) event.preventDefault(); });
importDialog.addEventListener('close',()=>{
 clearPreview();
 importButton.focus();
});
accountInput.addEventListener('input',clearPreview);
fileInput.addEventListener('change',clearPreview);

const sendJson = (url, body) => api(url, {
 method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
});
importForm.addEventListener('submit',async event=>{
 event.preventDefault();
 clearPreview();
 const request = previewRequest;
 const file = fileInput.files[0];
 const message = byId('investing-status');
 try {
  if (file.size > 1_000_000) throw new Error('El CSV supera 1 MB.');
  const csv = new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
  const payload = {account:accountInput.value,csv,filename:file.name};
  message.textContent = 'Preparando vista previa…';
  const {rows, totals, reference_date, reference_origin, preview_token} = await sendJson('/api/portfolio/investing/preview',payload);
  if (request !== previewRequest || !importDialog.open) return;
  byId('preview-metrics').innerHTML = metrics(totals);
  byId('investing-preview').innerHTML = `<table><thead><tr><th>Fila</th><th>Instrumento</th><th>Mercado</th>
   <th>Cantidad</th><th>Precio actual</th><th>Valor declarado</th><th>Lotes</th><th>Estado</th></tr></thead><tbody>${rows.map(row=>
   `<tr><td>${row.line}</td><td>${esc(row.name || row.label)}<div class="small muted">${esc(row.label)}</div></td><td>${esc(row.exchange || '—')}</td>
    <td>${esc(quantity(row.quantity))}</td><td>${money(row.economics?.current_price)}</td><td>${money(row.economics?.market_value)}</td>
    <td>${row.lots?.length ?? '—'}</td><td>${esc([row.issue,...row.warnings].filter(Boolean).join(' · ') || 'Lista para importar')}</td></tr>`
  ).join('')}</tbody></table>`;
  if (preview_token) pendingImport = {...payload,preview_token};
  confirmButton.hidden = !pendingImport;
  message.textContent = (reference_date ? `Referencia ${reference_date}${reference_origin === 'filename' ? ' según el nombre del archivo' : ''}. ` : '')
   + (pendingImport ? 'Revisa las posiciones antes de importar.' : 'Resuelve las filas indicadas para importar.');
 } catch (error) {
  if (request === previewRequest && importDialog.open) message.textContent = error.message;
 }
});
confirmButton.addEventListener('click',async()=>{
 if (confirming || !pendingImport) return;
 confirming = true;
 const controls = [confirmButton,cancelButton,accountInput,fileInput,previewButton,...document.querySelectorAll('input[name="import-source"]')];
 controls.forEach(control=>control.disabled = true);
 const message = byId('investing-status');
 try {
  message.textContent = 'Guardando cartera y valoración…';
  const {portfolio_id} = await sendJson('/api/portfolio/investing/confirm',pendingImport);
  await loadPortfolios(portfolio_id);
  byId('refresh-status').hidden = true;
  importDialog.close();
 } catch (error) {
  message.textContent = error.message;
 } finally {
  confirming = false;
  controls.forEach(control=>control.disabled = false);
 }
});

function renderPortfolioReport(report) {
 const data = report.result;
 const context = report.input_snapshot.portfolio_analysis;
 const tag = byId('report-version');
 tag.hidden = false;
 tag.textContent = `Cartera v${report.portfolio_version} · Perfil v${report.profile_version}`;
 const funds = data.funds_without_holdings;
 byId('report').innerHTML = `<h3>Análisis de prueba</h3>
  <p><strong>${esc(data.portfolio_name)}</strong> · Versión ${data.selection.portfolio_version} · ${esc(data.decision)}</p>
  <p class="small muted">Valoración <code>${esc(data.selection.valuation_id)}</code>${data.declared_valuation_id && data.declared_valuation_id !== data.selection.valuation_id
   ? ` · Datos declarados del CSV <code>${esc(data.declared_valuation_id)}</code> · Referencia ${esc(context.source?.reference_date ?? 'no disponible')}` : ''}</p>
  ${metrics(data.declared_valuation_id ? {market_value:data.declared_total,open_pnl:data.open_pnl,daily_pnl:data.daily_pnl,total_pnl:data.total_pnl} : null)}
  <h4>Posiciones directas</h4><ul>${data.direct_positions.map(row=>`<li><strong>${esc(row.name)}</strong>${row.ticker ? ` (${esc(row.ticker)})` : ''}
   · ${esc(quantity(row.quantity))} ${row.ticker === 'MSFT' ? 'acciones' : 'unidades'} · Peso directo ${percent(row.weight_pct)}
   ${row.weight_source === 'declared' ? '(declarado)' : row.weight_source === 'calculated' ? '(calculado)' : ''}</li>`).join('')}</ul>
  <p>Cobertura · ${context.view.valuation.positions.filter(row=>row.quote_value !== null).length} de ${context.view.valuation.total_positions} posiciones con valor en su moneda.
   ${context.view.valuation.valued_positions} con valor en ${esc(context.view.valuation.base_currency)}.</p>
  ${funds.length ? `<p>Exposición indirecta desconocida · composición sin detalle de ${esc(funds.join(', '))}.</p>` : ''}
  <p class="small muted">El informe queda asociado a la cartera, valoración y perfil seleccionados al encolar.</p>`;
}

async function loadReports(selected) {
 const reports = await api('/api/reports');
 byId('report-picker').hidden = !reports.length;
 reportSelect.replaceChildren(...reports.map(row=>new Option(
  `Cartera v${row.portfolio_version} · ${new Date(row.created_at).toLocaleString('es-ES')}`,row.id
 )));
 if (selected) reportSelect.value = selected;
 if (reportSelect.value) await showReport(reportSelect.value);
}
reportSelect.addEventListener('change',()=>showReport(reportSelect.value).catch(error=>{
 byId('report').textContent = error.message;
}));

async function followAnalysis(runId) {
 for (let tries=0; tries<120; tries++) {
  const run = await api('/api/analyses/' + encodeURIComponent(runId));
  const message = byId('status');
  if (run.status === 'completed') {
   sessionStorage.removeItem('portfolio-analysis-run');
   await loadReports(run.report_id);
   message.textContent = 'Informe de prueba disponible.';
   byId('report-link').hidden = false;
   return;
  }
  if (run.status === 'failed') {
   sessionStorage.removeItem('portfolio-analysis-run');
   throw new Error(run.error || 'No se pudo completar el análisis.');
  }
  message.textContent = run.status === 'queued' ? 'Análisis en cola…' : 'Análisis en curso…';
  await new Promise(resolve=>setTimeout(resolve,1000));
 }
 byId('status').textContent = 'El análisis sigue pendiente. Recarga para consultar su estado.';
}

async function analysisOperation(action) {
 analysisBusy = true;
 updateControls();
 const message = byId('status');
 message.hidden = false;
 try { await action(); }
 catch (error) { message.textContent = error.message; }
 finally { analysisBusy = false; updateControls(); }
}

analysisButton.addEventListener('click',()=>analysisOperation(async()=>{
 const {portfolio,valuation} = active;
 byId('report-link').hidden = true;
 byId('status').textContent = 'Encolando análisis…';
 const {id} = await sendJson('/api/analyses',{
  portfolio_id:portfolio.portfolio_id, portfolio_version:portfolio.version, valuation_id:valuation.snapshot_id
 });
 sessionStorage.setItem('portfolio-analysis-run',id);
 await followAnalysis(id);
}));

portfolioOperation(()=>loadPortfolios(),'valuation-status');
refresh().catch(error=>{ byId('profile').textContent = error.message; });
loadReports().then(()=>{
 const runId = sessionStorage.getItem('portfolio-analysis-run');
 if (runId && !analysisBusy) analysisOperation(()=>followAnalysis(runId));
}).catch(error=>{ byId('report').textContent = error.message; });
